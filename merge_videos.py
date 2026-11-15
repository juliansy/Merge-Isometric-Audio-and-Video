#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_videos.py -- 批量合并分离的视频、音频、字幕与封面。

扫描目标目录里的 *.mp4，用 ffprobe 读出每个视频**已有**的音轨 / 字幕轨 / 封面，
再在目录里找同名的侧车文件（.m4a/.aac/.mp3、.ass/.srt/.json/.vtt、.jpg/.jpeg/.png/.webp）。
只补“视频缺、目录有”的那一部分，一次 ffmpeg 调用完成封装，校验通过后原子替换原视频，
失败则原样保留所有源文件。最后逐条汇报：哪个视频合并了、补了哪几轨、是否齐全。

用法:
    merge_videos.py [路径 ...] [选项]

    路径可以是目录（处理其中的 *.mp4），也可以是单个 .mp4；不带路径时处理脚本所在目录。

选项:
    -n, --dry-run       只分析并打印计划，不写任何文件
    -k, --keep          成功后也保留全部源文件（默认删除已并入的侧车）
    -p, --purge         额外删除“视频已有该轨、未使用”的侧车文件
    -j, --jobs N        并行处理的文件数（默认 1）
    -q, --quiet         只输出汇总
        --no-title      不写入 title 元数据（默认把文件名写进 title）
        --ffmpeg PATH   指定 ffmpeg 可执行文件
        --ffprobe PATH  指定 ffprobe 可执行文件
        --log FILE      同时把输出写入日志文件
        --no-pause      由启动器使用：结束不暂停
    -h, --help          显示本帮助
    -V, --version       显示版本

退出码: 0 全部成功或无需处理；1 有文件失败；2 参数或环境错误。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional, Sequence

VERSION = "1.4.0"

AUDIO_EXTS = (".m4a", ".aac", ".mp3")
SUB_EXTS = (".ass", ".srt", ".json", ".vtt")
COVER_EXTS = (".jpg", ".jpeg", ".png", ".webp")
JPEG_EXTS = (".jpg", ".jpeg")
VIDEO_EXTS = (".mp4",)
SIDECAR_EXTS = AUDIO_EXTS + SUB_EXTS + COVER_EXTS

DURATION_TOLERANCE = 2.0     # 产物与原视频时长允许的差（秒）
MIN_OUTPUT_BYTES = 1024
FFPROBE_TIMEOUT = 180
FFMPEG_TIMEOUT = 6 * 3600
STALE_TEMP_SECONDS = 3600

TRACK_AUDIO = "音频"
TRACK_SUB = "字幕"
TRACK_COVER = "封面"
MARK_SHORT = {TRACK_AUDIO: "音", TRACK_SUB: "字", TRACK_COVER: "封"}


# --------------------------------------------------------------------------- #
# 基础设施
# --------------------------------------------------------------------------- #
class ToolError(RuntimeError):
    """ffmpeg / ffprobe 不可用或执行失败。"""


class ProbeError(RuntimeError):
    """ffprobe 无法解析该文件。"""


@dataclass(frozen=True)
class Tools:
    ffmpeg: str
    ffprobe: str

    @classmethod
    def resolve(cls, ffmpeg: Optional[str], ffprobe: Optional[str]) -> "Tools":
        ff = ffmpeg or os.environ.get("MERGE_FFMPEG") or shutil.which("ffmpeg")
        fp = ffprobe or os.environ.get("MERGE_FFPROBE") or shutil.which("ffprobe")
        if not ff or not fp:
            raise ToolError(
                "未找到 ffmpeg / ffprobe。请安装并加入 PATH，"
                "或用 --ffmpeg / --ffprobe 指定路径。"
            )
        return cls(ff, fp)


def run_command(cmd: Sequence[str], timeout: int) -> subprocess.CompletedProcess:
    """执行外部命令；stdin 关闭，避免 ffmpeg 等待输入导致挂起。"""
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(
            list(cmd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            **kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"命令超时（{timeout}s）：{cmd[0]}") from exc
    except OSError as exc:
        raise ToolError(f"无法启动 {cmd[0]}：{exc}") from exc


def decode(data: Optional[bytes]) -> str:
    return data.decode("utf-8", "replace") if data else ""


def one_line(text: str, limit: int = 400) -> str:
    flat = " ".join(text.split())
    return flat[-limit:] if len(flat) > limit else flat


_ADDR_RE = re.compile(r"\[[^\]]*@ [0-9a-zA-Z]+\]\s*")


def brief_error(text: str, target: Optional[Path] = None, limit: int = 160) -> str:
    """把 ffmpeg/ffprobe 的长错误压成一句：去地址前缀、去绝对路径、截尾。"""
    flat = " ".join(text.split())
    flat = _ADDR_RE.sub("", flat)
    if target is not None:
        flat = flat.replace(str(target), target.name)
    if len(flat) > limit:
        flat = "…" + flat[-limit:]
    return flat.strip()


# --------------------------------------------------------------------------- #
# 探测：每个文件一次 ffprobe，拿全部轨道信息
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Probe:
    duration: float
    has_video: bool
    has_audio: bool
    has_subs: bool
    has_cover: bool
    audio_count: int
    sub_count: int
    video_codec: str
    audio_codec: str
    sub_codec: str
    cover_codec: str
    stream_count: int
    cover_index: int = 0
    sub_duration: float = 0.0          # 字幕轨自身的时长，0 表示"有轨但没内容"

    @property
    def tracks(self) -> dict[str, bool]:
        return {TRACK_AUDIO: self.has_audio, TRACK_SUB: self.has_subs, TRACK_COVER: self.has_cover}


def probe(tools: Tools, path: Path) -> Probe:
    cmd = [
        tools.ffprobe, "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ]
    proc = run_command(cmd, FFPROBE_TIMEOUT)
    if proc.returncode != 0:
        raise ProbeError(one_line(decode(proc.stderr)) or "ffprobe 返回非零")
    try:
        data = json.loads(decode(proc.stdout) or "{}")
    except json.JSONDecodeError as exc:
        raise ProbeError(f"ffprobe 输出不是合法 JSON：{exc}") from exc

    streams = data.get("streams")
    if not isinstance(streams, list):
        raise ProbeError("ffprobe 输出缺少 streams")
    fmt = data.get("format") or {}

    def kind(stream: dict) -> str:
        return str(stream.get("codec_type") or "")

    def attached(stream: dict) -> bool:
        return int((stream.get("disposition") or {}).get("attached_pic") or 0) == 1

    videos = [s for s in streams if kind(s) == "video" and not attached(s)]
    audios = [s for s in streams if kind(s) == "audio"]
    subs = [s for s in streams if kind(s) == "subtitle"]
    covers = [s for s in streams if kind(s) == "video" and attached(s)]
    video_streams = [s for s in streams if kind(s) == "video"]
    cover_index = next((i for i, s in enumerate(video_streams) if attached(s)), 0)

    try:
        duration = float(fmt.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0

    def codec(item: Optional[dict]) -> str:
        return str((item or {}).get("codec_name") or "")

    def stream_duration(item: Optional[dict]) -> float:
        try:
            return float((item or {}).get("duration") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return Probe(
        duration=duration,
        has_video=bool(videos),
        has_audio=bool(audios),
        has_subs=bool(subs),
        has_cover=bool(covers),
        audio_count=len(audios),
        sub_count=len(subs),
        video_codec=codec(videos[0] if videos else None),
        audio_codec=codec(audios[0] if audios else None),
        sub_codec=codec(subs[0] if subs else None),
        cover_codec=codec(covers[0] if covers else None),
        stream_count=len(streams),
        cover_index=cover_index,
        sub_duration=stream_duration(subs[0] if subs else None),
    )


# --------------------------------------------------------------------------- #
# 侧车文件发现
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Sidecars:
    audio: Optional[Path] = None
    subtitle: Optional[Path] = None
    cover: Optional[Path] = None

    @property
    def tracks(self) -> dict[str, Optional[Path]]:
        return {TRACK_AUDIO: self.audio, TRACK_SUB: self.subtitle, TRACK_COVER: self.cover}

    def paths(self) -> list[Path]:
        return [p for p in self.tracks.values() if p is not None]


def _usable(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


@lru_cache(maxsize=256)
def directory_sidecar_index(directory: str) -> tuple[tuple[str, str, str], ...]:
    """目录内文件的 (NFC 化 stem, 小写后缀, 文件名) 索引。

    macOS / 某些解压工具写出的文件名是 NFD（é 拆成 e + 组合符），
    与 Windows 上的 NFC 视频名逐字符比较会不相等，这里做一次规范化回退。
    """
    entries: list[tuple[str, str, str]] = []
    try:
        for item in Path(directory).iterdir():
            if _usable(item):
                entries.append((unicodedata.normalize("NFC", item.stem), item.suffix.lower(), item.name))
    except OSError:
        return ()
    return tuple(entries)


def pick_sidecar(video: Path, exts: Iterable[str]) -> Optional[Path]:
    """按优先级找第一个存在且非空的同名文件。注意不能改扩展名以外的部分。"""
    for ext in exts:
        candidate = video.with_name(video.stem + ext)
        if _usable(candidate):
            return candidate

    # 规范化回退：同目录里找 NFC(stem) 相同、后缀匹配的文件
    target = unicodedata.normalize("NFC", video.stem)
    wanted = {ext.lower() for ext in exts}
    for nfc_stem, suffix, name in directory_sidecar_index(str(video.parent)):
        if suffix in wanted and nfc_stem == target:
            candidate = video.parent / name
            if _usable(candidate):
                return candidate
    return None


def find_sidecars(video: Path) -> Sidecars:
    return Sidecars(
        audio=pick_sidecar(video, AUDIO_EXTS),
        subtitle=pick_sidecar(video, SUB_EXTS),
        cover=pick_sidecar(video, COVER_EXTS),
    )


# --------------------------------------------------------------------------- #
# 预处理：JSON 字幕转 SRT、非 JPEG 封面转 JPEG
# --------------------------------------------------------------------------- #
def format_timestamp(ms: int) -> str:
    ms = max(0, int(ms))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    seconds, ms = divmod(ms, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_cue_text(value: object) -> str:
    """字幕正文清洗。

    NUL 会让 ffmpeg 的 SRT 解析器整条流失效（产物里只剩一条空字幕），
    其它 C0 控制字符同样没有意义；U+2028/U+2029 按空格处理。
    """
    text = str(value or "").replace("\u2028", " ").replace("\u2029", " ")
    return " ".join(_CONTROL_RE.sub(" ", text).split())


def decode_text(raw: bytes) -> str:
    """按 UTF-8 → GB18030 顺序解码；都失败才用替换字符。

    中文 .srt 很多是 GBK 编码，直接按 UTF-8 读会得到乱码或让 ffmpeg 解析失败。
    """
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def load_cues(path: Path) -> list[dict]:
    text = decode_text(path.read_bytes())
    data = json.loads(text)
    if isinstance(data, dict):
        for key in ("body", "subtitles", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError("JSON 顶层既不是数组，也没有 body/subtitles/data 数组")
    cues = [c for c in data if isinstance(c, dict) and "from" in c and "to" in c]
    if not cues:
        raise ValueError("JSON 里没有 from/to 字幕条目")
    return cues


def json_to_srt(source: Path, target: Path) -> int:
    """把哔哩哔哩字幕 JSON 转成 SRT，返回写入的条数。"""
    blocks: list[str] = []
    for cue in load_cues(source):
        try:
            start = int(round(float(cue["from"]) * 1000))
            end = int(round(float(cue["to"]) * 1000))
        except (TypeError, ValueError):
            continue
        if end <= start:
            end = start + 200
        text = clean_cue_text(cue.get("content"))
        text = text.replace("-->", "- ->")       # 避免字幕正文伪造时间行
        if not text:
            continue
        index = len(blocks) + 1
        blocks.append(f"{index}\n{format_timestamp(start)} --> {format_timestamp(end)}\n{text}\n")
    if not blocks:
        raise ValueError("没有可用的字幕条目")
    target.write_text("\n".join(blocks), encoding="utf-8", newline="\n")
    return len(blocks)


def ensure_playable(path: Path, suffix: str) -> None:
    """粗校验字幕文件里确实有可解析的条目。

    ffmpeg 对"格式不对但扩展名对"的文件不会报错，只会产出一条空字幕轨，
    结果就是视频合并成功、字幕却什么都没留下——这里提前拦住。
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ValueError(f"字幕无法读取：{exc}") from exc
    suffix = suffix.lower()
    if suffix in (".srt", ".vtt"):
        if not re.search(r"^\s*\d{2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->", text, re.M):
            raise ValueError("字幕里没有可识别的时间轴（不是有效的 SRT/VTT）")
        if not _has_subtitle_text(text, suffix):
            raise ValueError("字幕里只有时间轴、没有文字")
    elif suffix in (".ass", ".ssa"):
        if "Dialogue:" not in text:
            raise ValueError("ASS/SSA 字幕里没有 Dialogue 行")
        if not _has_subtitle_text(text, suffix):
            raise ValueError("ASS/SSA 字幕的 Dialogue 行没有文字")
    elif suffix == ".json":
        raise ValueError("JSON 字幕应当走转换流程")


def _has_subtitle_text(text: str, suffix: str = "") -> bool:
    """时间轴行、序号行、头部行都不算内容；WebVTT 允许文字写在时间轴同一行。

    ASS/SSA 的 `[Script Info]`、`Format:` 之类也是"非空行"，
    所以它们的正文只认 Dialogue/Comment 行，其余一律跳过。
    """
    ass_like = suffix.lower() in (".ass", ".ssa")
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line or line.isdigit() or line.upper().startswith("WEBVTT"):
            continue
        if ass_like:
            if not (line.startswith("Dialogue:") or line.startswith("Comment:")):
                continue
            # 形如 Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,正文
            parts = line.split(",", 9)
            if len(parts) >= 10 and parts[9].strip():
                return True
            continue
        if "-->" in line:
            match = re.match(
                r"\d{2}:\d{2}:\d{2}[.,]\d{1,3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{1,3}\s*(.*)$",
                line,
            )
            if match and match.group(1).strip():
                return True
            continue
        return True
    return False


def prepare_subtitle(tools: Tools, subtitle: Path, workdir: Path) -> tuple[Path, Optional[Path]]:
    """返回 (给 ffmpeg 用的字幕路径, 需要额外清理的临时文件)。

    ffmpeg 按 UTF-8 读文本字幕，GBK 的 .srt/.vtt 会乱码，所以先探测编码，
    需要时转存成临时 UTF-8 文件；.json 则整份转成 SRT。
    """
    if subtitle.suffix.lower() == ".json":
        target = workdir / "subtitle.srt"
        count = json_to_srt(subtitle, target)
        if count <= 0:
            raise ValueError("JSON 字幕转换后为空")
        ensure_playable(target, ".srt")
        return target, target

    raw = subtitle.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
        encoding = "utf-8"
    except UnicodeDecodeError:
        try:
            text = raw.decode("gb18030")
            encoding = "gb18030"
        except UnicodeDecodeError as exc:
            raise ValueError(f"字幕编码无法识别（既不是 UTF-8 也不是 GBK）：{exc}") from exc

    had_nul = "\x00" in text
    if had_nul:
        text = text.replace("\x00", "")         # NUL 会让 SRT 解析器整条失效

    if encoding == "utf-8" and not had_nul:
        ensure_playable(subtitle, subtitle.suffix)
        return subtitle, None                    # 本来就是 UTF-8，直接用原文件

    target = workdir / ("subtitle" + subtitle.suffix.lower())
    target.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    ensure_playable(target, subtitle.suffix)
    return target, target


def prepare_cover(tools: Tools, cover: Path, workdir: Path) -> tuple[Path, Optional[Path]]:
    """MP4 的 attached_pic 用 mjpeg 最稳；非 JPEG 先转一张临时 JPEG。"""
    if cover.suffix.lower() in JPEG_EXTS:
        return cover, None
    target = workdir / "cover.jpg"
    cmd = [
        tools.ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
        "-i", str(cover),
        "-frames:v", "1", "-update", "1", "-q:v", "2",
        str(target),
    ]
    proc = run_command(cmd, FFPROBE_TIMEOUT)
    if proc.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        raise ValueError(f"封面转换失败：{one_line(decode(proc.stderr))}")
    return target, target


# --------------------------------------------------------------------------- #
# 计划
# --------------------------------------------------------------------------- #
@dataclass
class Plan:
    video: Path
    probe: Probe
    side: Sidecars
    add_audio: Optional[Path] = None
    add_sub: Optional[Path] = None
    add_cover: Optional[Path] = None
    skip_reason: str = ""

    @property
    def additions(self) -> dict[str, Optional[Path]]:
        return {TRACK_AUDIO: self.add_audio, TRACK_SUB: self.add_sub, TRACK_COVER: self.add_cover}

    @property
    def has_work(self) -> bool:
        return bool(self.add_audio or self.add_sub or self.add_cover)

    def expected_tracks(self) -> dict[str, bool]:
        """处理完成后应存在的轨道。"""
        return {
            TRACK_AUDIO: self.probe.has_audio or bool(self.add_audio),
            TRACK_SUB: self.probe.has_subs or bool(self.add_sub),
            TRACK_COVER: self.probe.has_cover or bool(self.add_cover),
        }


def make_plan(video: Path, pr: Probe, side: Sidecars) -> Plan:
    plan = Plan(
        video=video,
        probe=pr,
        side=side,
        add_audio=None if pr.has_audio else side.audio,
        add_sub=None if pr.has_subs else side.subtitle,
        add_cover=None if pr.has_cover else side.cover,
    )
    if not pr.has_video:
        plan.skip_reason = "没有可用的视频流"
    elif plan.has_work:
        plan.skip_reason = ""
    else:
        lacking = [name for name, ok in pr.tracks.items() if not ok]
        if not lacking:
            plan.skip_reason = "已齐全，无需处理"
        elif not side.paths():
            plan.skip_reason = f"无可合并素材（缺 {'/'.join(lacking)}）"
        else:
            plan.skip_reason = f"缺少的轨道目录里也没有（缺 {'/'.join(lacking)}）"
    return plan


# --------------------------------------------------------------------------- #
# 封装命令
# --------------------------------------------------------------------------- #
_KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
_HANGUL_RE = re.compile(r"[\u1100-\u11ff\uac00-\ud7a3]")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f]")
_HEBREW_RE = re.compile(r"[\u0590-\u05ff]")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")
_THAI_RE = re.compile(r"[\u0e00-\u0e7f]")


def guess_subtitle_language(text: str) -> str:
    """按字符集猜字幕语言（ISO 639-2/B 三字码）。

    日文里有汉字，所以先看假名；韩文有谚文；其余按占比依次判断。
    猜错也只是元数据不对，不影响画面和文字；可以用 --sub-lang 强制指定。
    """
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return "und"
    total = len(letters)
    ratio = lambda pattern: len(pattern.findall(text)) / total
    if ratio(_KANA_RE) >= 0.02:
        return "jpn"
    if ratio(_HANGUL_RE) >= 0.05:
        return "kor"
    if ratio(_CJK_RE) >= 0.05:
        return "chi"
    if ratio(_ARABIC_RE) >= 0.05:
        return "ara"
    if ratio(_HEBREW_RE) >= 0.05:
        return "heb"
    if ratio(_CYRILLIC_RE) >= 0.05:
        return "rus"
    if ratio(_THAI_RE) >= 0.05:
        return "tha"
    return "eng"


def build_command(tools: Tools, plan: Plan, subtitle: Optional[Path],
                  cover: Optional[Path], dest: Path, with_title: bool,
                  sub_lang: str = "auto") -> list[str]:
    """组织 ffmpeg 参数。

    关键点：视频里**已有**的音轨 / 字幕 / 封面必须显式保留，否则只 map 新加的
    那一路会把它们丢掉。输出视频流顺序固定为 [正片, 封面]，因此封面永远是 v:1。
    """
    pr = plan.probe
    inputs: list[tuple[Path, str]] = [(plan.video, "video")]
    index = {"video": 0}

    if plan.add_audio:
        index["audio"] = len(inputs)
        inputs.append((plan.add_audio, "audio"))
    if subtitle:
        index["sub"] = len(inputs)
        inputs.append((subtitle, "sub"))
    if cover:
        index["cover"] = len(inputs)
        inputs.append((cover, "cover"))

    cmd = [tools.ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]
    for path, _ in inputs:
        cmd += ["-i", str(path)]

    cmd += ["-map", "0:v:0"]                       # 正片
    if pr.has_cover:
        cmd += ["-map", f"0:v:{pr.cover_index}"]   # 原封面（按探测到的下标取，不假定 v:1）
    if pr.audio_count:
        cmd += ["-map", "0:a"]                     # 原有全部音轨
    if pr.sub_count:
        cmd += ["-map", "0:s"]                     # 原有全部字幕
    if plan.add_audio:
        cmd += ["-map", f"{index['audio']}:a:0"]
    if subtitle:
        cmd += ["-map", f"{index['sub']}:s:0"]
    if cover:
        cmd += ["-map", f"{index['cover']}:v:0"]

    cmd += ["-c:v", "copy", "-c:a", "copy"]
    if pr.sub_count or subtitle:
        cmd += ["-c:s", "mov_text"]
    if subtitle:
        # 新增字幕排在原有字幕之后；语言用 --sub-lang，默认按文字内容识别
        language = sub_lang
        if language == "auto":
            try:
                language = guess_subtitle_language(subtitle.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                language = "und"
        cmd += ["-metadata:s:s:%d" % pr.sub_count, f"language={language}"]
    if pr.has_cover or cover:
        cmd += ["-disposition:v:1", "attached_pic"]
    cmd += ["-map_metadata", "0", "-movflags", "+faststart",
            "-max_muxing_queue_size", "1024"]   # 大文件 remux 的 interleave 缓冲
    if with_title:
        cmd += ["-metadata", f"title={plan.video.stem}"]
    cmd.append(str(dest))
    return cmd


def verify_output(tools: Tools, dest: Path, plan: Plan) -> list[str]:
    """校验产物：轨道、时长、体积。只要求“计划里应当有的”轨道存在。"""
    try:
        pr = probe(tools, dest)
    except (ProbeError, ToolError) as exc:
        return [f"产物无法解析：{exc}"]

    expected = plan.expected_tracks()
    problems: list[str] = []
    if not pr.has_video:
        problems.append("缺视频流")
    if expected[TRACK_AUDIO] and not pr.has_audio:
        problems.append("缺音轨")
    if expected[TRACK_SUB] and not pr.has_subs:
        problems.append("缺字幕轨")
    if plan.add_sub is not None and pr.has_subs and pr.sub_duration <= 0.0:
        problems.append("字幕轨是空的（源字幕没有可解析的条目）")
    if expected[TRACK_COVER] and not pr.has_cover:
        problems.append("缺封面")
    if plan.probe.duration > 0 and abs(pr.duration - plan.probe.duration) > DURATION_TOLERANCE:
        problems.append(f"时长偏差 {pr.duration - plan.probe.duration:+.1f}s")
    try:
        if dest.stat().st_size < MIN_OUTPUT_BYTES:
            problems.append("产物过小")
    except OSError:
        problems.append("产物不可读")
    return problems


# --------------------------------------------------------------------------- #
# 结果
# --------------------------------------------------------------------------- #
@dataclass
class Result:
    video: Path
    action: str                      # merged / planned / skipped / failed
    before: dict[str, bool]
    available: dict[str, bool]
    added: list[str]
    missing: list[str]
    seconds: float
    note: str = ""
    deleted: list[Path] = field(default_factory=list)


EMPTY_PROBE = Probe(0.0, True, False, False, False, 0, 0, "", "", "", "", 0)


def marks(tracks: dict[str, bool]) -> str:
    return " ".join(f"{MARK_SHORT[name]}{'✓' if ok else '✗'}" for name, ok in tracks.items())


def sidecar_marks(side: Sidecars) -> dict[str, bool]:
    return {name: path is not None for name, path in side.tracks.items()}


def clean_stale_temps(directory: Path, stem: str) -> None:
    """清理上次异常中断留下的临时封装文件（超过 1 小时的才算，避免误删并发实例的）。"""
    now = time.time()
    prefix = f".{stem}.mergetmp."
    try:
        for item in directory.iterdir():
            if not item.name.startswith(prefix) or not item.name.endswith(".mp4"):
                continue
            try:
                if now - item.stat().st_mtime > STALE_TEMP_SECONDS:
                    item.unlink()
            except OSError:
                continue
    except OSError:
        pass


def process_video(ctx: "Context", video: Path) -> Result:
    started = time.perf_counter()
    try:
        pr = probe(ctx.tools, video)
    except (ProbeError, ToolError) as exc:
        return Result(video, "failed", EMPTY_PROBE.tracks, sidecar_marks(Sidecars()),
                      [], [], time.perf_counter() - started, f"视频无法解析：{brief_error(str(exc), video)}")

    side = find_sidecars(video)
    plan = make_plan(video, pr, side)
    before = dict(pr.tracks)
    available = sidecar_marks(side)

    if plan.skip_reason:
        note = plan.skip_reason
        deleted: list[Path] = []
        if not ctx.dry_run:
            clean_stale_temps(video.parent, video.stem)   # 跳过也清残留，否则永远没人收拾
        if ctx.purge and not ctx.dry_run and not ctx.keep and side.paths():
            deleted = remove_files(ctx, side.paths())
            if deleted:
                note += f"；清理 {len(deleted)} 个未使用附件"
        return Result(video, "skipped", before, available, [],
                      [name for name, ok in before.items() if not ok],
                      time.perf_counter() - started, note, deleted)

    if ctx.dry_run:
        added = [name for name, path in plan.additions.items() if path]
        note = "将并入 " + "+".join(added)
        if plan.add_sub and plan.add_sub.suffix.lower() == ".json":
            try:
                note += f"（字幕 {len(load_cues(plan.add_sub))} 条）"
            except (ValueError, OSError) as exc:
                plan.add_sub = None              # 否则“结果”列会声称齐全
                added = [name for name in added if name != TRACK_SUB]
                note = f"预演：字幕 JSON 无法读取（{exc}），其余将并入 " + ("+".join(added) or "无")
        missing = [name for name, ok in plan.expected_tracks().items() if not ok and name not in added]
        return Result(video, "planned", before, available, added, missing,
                      time.perf_counter() - started, note)

    clean_stale_temps(video.parent, video.stem)
    workdir = Path(tempfile.mkdtemp(prefix="mergevid_"))
    dest = video.with_name(f".{video.stem}.mergetmp.{os.getpid()}.mp4")
    temporary: list[Path] = [dest]
    warnings: list[str] = []

    try:
        subtitle: Optional[Path] = None
        cover: Optional[Path] = None
        if plan.add_sub:
            try:
                subtitle, tmp = prepare_subtitle(ctx.tools, plan.add_sub, workdir)
                if tmp:
                    temporary.append(tmp)
            except (ValueError, OSError) as exc:
                warnings.append(f"字幕未并入（{exc}）")
                plan.add_sub = None

        if plan.add_cover:
            try:
                cover, tmp = prepare_cover(ctx.tools, plan.add_cover, workdir)
                if tmp:
                    temporary.append(tmp)
            except (ValueError, OSError) as exc:
                warnings.append(f"封面未并入（{exc}）")
                plan.add_cover = None

        if not plan.has_work:
            return Result(video, "skipped", before, available, [],
                          [name for name, ok in before.items() if not ok],
                          time.perf_counter() - started,
                          warnings_note(warnings) or "没有可并入的内容")

        cmd = build_command(ctx.tools, plan, subtitle, cover, dest, ctx.with_title, ctx.sub_lang)
        proc = run_command(cmd, FFMPEG_TIMEOUT)
        if proc.returncode != 0:
            return Result(video, "failed", before, available, [], [],
                          time.perf_counter() - started,
                          note="ffmpeg 失败：" + (brief_error(decode(proc.stderr), video) or f"退出码 {proc.returncode}")
                          + (("；" + warnings_note(warnings)) if warnings else ""))

        problems = verify_output(ctx.tools, dest, plan)
        if problems:
            return Result(video, "failed", before, available, [], [],
                          time.perf_counter() - started,
                          note="产物校验失败：" + "，".join(problems)
                          + (("；" + warnings_note(warnings)) if warnings else ""))

        os.replace(dest, video)                    # 同目录替换，原子

        added = [name for name, path in plan.additions.items() if path]
        deleted = delete_sources(ctx, plan, added) if not ctx.keep else []
        expected = plan.expected_tracks()
        missing = [name for name, ok in expected.items() if not ok]

        note = warnings_note(warnings)
        if deleted:
            note = (note + "；" if note else "") + f"删除 {len(deleted)} 个源文件"
        return Result(video, "merged", before, available, added, missing,
                      time.perf_counter() - started, note, deleted)
    except (ValueError, ToolError) as exc:
        return Result(video, "failed", before, available, [], [],
                      time.perf_counter() - started,
                      note=str(exc) + (("；" + warnings_note(warnings)) if warnings else ""))
    except OSError as exc:
        return Result(video, "failed", before, available, [], [],
                      time.perf_counter() - started,
                      note=f"文件操作失败：{exc}" + (("；" + warnings_note(warnings)) if warnings else ""))
    finally:
        for tmp in temporary:
            try:
                if tmp.is_file():
                    tmp.unlink()
            except OSError:
                pass
        shutil.rmtree(workdir, ignore_errors=True)


def warnings_note(warnings: Sequence[str]) -> str:
    return "；".join(warnings)


def remove_files(ctx: "Context", paths: Iterable[Path]) -> list[Path]:
    deleted: list[Path] = []
    for path in paths:
        try:
            if path.is_file():
                path.unlink()
                deleted.append(path)
        except OSError as exc:
            ctx.log(f"      ! 删除失败 {path.name}：{exc}")
    return deleted


def delete_sources(ctx: "Context", plan: Plan, added: Sequence[str]) -> list[Path]:
    """删除已并入的侧车；--purge 时再删“视频已有该轨、所以没用上”的那部分。"""
    candidates: list[Path] = []
    for name in added:
        path = plan.additions[name]
        if path:
            candidates.append(path)
    if ctx.purge:
        for name, path in plan.side.tracks.items():
            if path and name not in added:
                candidates.append(path)
    return remove_files(ctx, candidates)


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #
def display_width(text: str) -> int:
    return sum(cluster_width(cluster) for cluster in iterate_clusters(text))


def pad(text: str, width: int) -> str:
    gap = width - display_width(text)
    return text + " " * gap if gap > 0 else text


_ZWJ = "\u200d"
_VARIATION = ("\ufe0e", "\ufe0f")
_KEYCAP = "\u20e3"


def _is_combining(ch: str) -> bool:
    return unicodedata.combining(ch) != 0 or unicodedata.category(ch) in ("Mn", "Me")


def iterate_clusters(text: str):
    """把字符串切成"用户眼里的一个字"。

    终端里 👨‍👩‍👧‍👦 / 👍🏽 / 1️⃣ / 🇨🇳 / e+́ 各自只占 1 个字形宽度，
    但按码点算长度是 7 / 2 / 3 / 2 / 2，直接数字符会让表格全部错位。
    """
    cluster = ""
    for ch in text:
        if not cluster:
            cluster = ch
            continue
        prev = cluster[-1]
        joins = (
            prev == _ZWJ
            or ch == _ZWJ
            or _is_combining(ch)
            or ch in _VARIATION
            or ch == _KEYCAP
            or 0x1F3FB <= ord(ch) <= 0x1F3FF                       # 肤色修饰
            or (0x1F1E6 <= ord(ch) <= 0x1F1FF                       # 旗帜：两个区域指示符成对
                and len(cluster) == 1 and 0x1F1E6 <= ord(prev) <= 0x1F1FF)
        )
        if joins:
            cluster += ch
        else:
            yield cluster
            cluster = ch
    if cluster:
        yield cluster


def cluster_width(cluster: str) -> int:
    marks = (_ZWJ, _KEYCAP, *_VARIATION)
    if all(_is_combining(ch) or ch in marks for ch in cluster):
        return 0
    if any(ch == _ZWJ or ch in _VARIATION or ch == _KEYCAP for ch in cluster):
        return 2
    if len(cluster) == 2 and all(0x1F1E6 <= ord(ch) <= 0x1F1FF for ch in cluster):
        return 2
    if any(0x1F3FB <= ord(ch) <= 0x1F3FF for ch in cluster):
        return 2
    return max(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in cluster)


def shorten(text: str, width: int) -> str:
    if display_width(text) <= width:
        return text
    kept: list[str] = []
    used = 0
    for cluster in iterate_clusters(text):
        w = cluster_width(cluster)
        if used + w > width - 1:
            break
        kept.append(cluster)
        used += w
    return "".join(kept) + "…"


def action_text(result: Result) -> str:
    if result.action == "merged":
        return "合并"
    if result.action == "planned":
        return "预演"
    if result.action == "skipped":
        return "跳过"
    return "失败"


def result_text(result: Result) -> str:
    if result.action == "failed":
        return "失败"
    if result.missing:
        return "缺" + "/".join(result.missing)
    return "齐全"


def render_table(results: Sequence[Result], dry_run: bool) -> list[str]:
    if not results:
        return ["没有找到需要处理的视频。"]

    name_width = min(46, max(14, max(display_width(r.video.name) for r in results)))
    before_width = max(display_width("原有"), max(display_width(marks(r.before)) for r in results)) + 1
    avail_width = max(display_width("目录"), max(display_width(marks(r.available)) for r in results)) + 1
    added_width = max(display_width("并入"),
                      min(24, max(display_width("+".join(r.added) or "—") for r in results))) + 1
    verdict_width = max(display_width("结果"), max(display_width(result_text(r)) for r in results)) + 1
    action_width = max(display_width("动作"), max(display_width(action_text(r)) for r in results)) + 1

    header = (
        f"{'#':<3}{pad('文件', name_width)}  "
        f"{pad('原有', before_width)}{pad('目录', avail_width)}"
        f"{pad('动作', action_width)}{pad('并入', added_width)}"
        f"{pad('结果', verdict_width)}{'耗时':>7}"
    )
    lines = [header, "-" * display_width(header)]

    for i, r in enumerate(results, 1):
        merged = "+".join(r.added) if r.added else "—"
        lines.append(
            f"{i:<3}{pad(shorten(r.video.name, name_width), name_width)}  "
            f"{pad(marks(r.before), before_width)}{pad(marks(r.available), avail_width)}"
            f"{pad(action_text(r), action_width)}{pad(shorten(merged, added_width), added_width)}"
            f"{pad(result_text(r), verdict_width)}{r.seconds:>6.1f}s"
        )
        if r.note:
            lines.append(f"     └ {r.note}")
    return lines


def render_summary(results: Sequence[Result], orphans: dict[Path, list[Path]], dry_run: bool) -> list[str]:
    merged = [r for r in results if r.action == "merged"]
    planned = [r for r in results if r.action == "planned"]
    skipped = [r for r in results if r.action == "skipped"]
    failed = [r for r in results if r.action == "failed"]
    pool = merged or planned

    lines = [""]
    if dry_run:
        lines.append(f"预演结果：将合并 {len(planned)} 个，无需处理 {len(skipped)} 个，"
                     f"无法处理 {len(failed)} 个。")
    else:
        lines.append(f"合并 {len(merged)} 个，跳过 {len(skipped)} 个，失败 {len(failed)} 个。")

    counts = {name: sum(1 for r in pool if name in r.added) for name in (TRACK_AUDIO, TRACK_SUB, TRACK_COVER)}
    lines.append(f"本次并入：{TRACK_AUDIO} {counts[TRACK_AUDIO]} 个，"
                 f"{TRACK_SUB} {counts[TRACK_SUB]} 个，{TRACK_COVER} {counts[TRACK_COVER]} 个。")

    complete = [r for r in merged if not r.missing]
    incomplete = [r for r in merged if r.missing]
    if merged:
        lines.append(f"齐全 {len(complete)} 个，不齐全 {len(incomplete)} 个。")
        for r in incomplete:
            lines.append(f"  · {r.video.name} — 缺 {'/'.join(r.missing)}")

    idle = [r for r in skipped if r.missing]
    if idle:
        lines.append("未处理且不齐全的文件：")
        for r in idle:
            lines.append(f"  · {r.video.name} — 缺 {'/'.join(r.missing)}；{r.note}")

    if failed:
        lines.append("失败：")
        for r in failed:
            lines.append(f"  · {r.video.name} — {r.note}")

    if orphans:
        lines.append("孤立附件（没有同名 mp4，未处理）：")
        for directory, items in orphans.items():
            for item in items:
                lines.append(f"  · {item.name}    [{directory}]")
    return lines


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
@dataclass
class Context:
    tools: Tools
    dry_run: bool
    keep: bool
    purge: bool
    with_title: bool
    log: Callable[[str], None]
    emit: Callable[[str], None]
    sub_lang: str = "auto"


def collect_videos(paths: Sequence[Path], recursive: bool = False) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            entries = path.rglob("*") if recursive else path.iterdir()
            found += [
                item for item in sorted(entries)
                if item.is_file() and item.suffix.lower() in VIDEO_EXTS and not item.name.startswith(".")
            ]
        elif path.is_file() and path.suffix.lower() in VIDEO_EXTS:
            found.append(path)
        else:
            raise ValueError(f"不是目录也不是 mp4：{path}")

    unique: list[Path] = []
    seen: set[str] = set()
    for item in found:
        key = str(item).lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def find_orphans(directories: Iterable[Path], videos: Sequence[Path]) -> dict[Path, list[Path]]:
    stems = {unicodedata.normalize("NFC", str(v.with_suffix(""))).casefold() for v in videos}
    result: dict[Path, list[Path]] = {}
    for directory in {d.resolve() for d in directories}:
        if not directory.is_dir():
            continue
        items = []
        for item in sorted(directory.iterdir()):
            if not item.is_file() or item.suffix.lower() not in SIDECAR_EXTS:
                continue
            if item.name.startswith("."):
                continue
            if unicodedata.normalize("NFC", str(item.with_suffix(""))).casefold() not in stems:
                items.append(item)
        if items:
            result[directory] = items
    return result


def run(paths: Sequence[Path], ctx: Context, jobs: int, recursive: bool = False) -> int:
    videos = collect_videos(paths, recursive)
    if not videos:
        ctx.log("没有找到 *.mp4。")
        return 0

    ctx.log(f"== merge_videos {VERSION} ==")
    ctx.log(f"目标：{paths[0] if len(paths) == 1 else '多个路径'}    共 {len(videos)} 个视频")
    if ctx.dry_run:
        ctx.log("模式：预演（只分析，不写入）")

    def work(video: Path) -> Result:
        try:
            return process_video(ctx, video)
        except Exception as exc:                       # 兜底：任何未预期异常只影响单个文件
            return Result(video, "failed", EMPTY_PROBE.tracks, sidecar_marks(Sidecars()),
                          [], [], 0.0, f"未预期错误：{exc!r}")

    results: list[Result] = []
    if jobs <= 1:
        for i, video in enumerate(videos, 1):
            ctx.log(f"[{i}/{len(videos)}] {video.name}")
            result = work(video)
            results.append(result)
            ctx.log(f"      → {status_line(result)}")
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(work, video) for video in videos]
            for i, future in enumerate(futures, 1):
                result = future.result()
                results.append(result)
                ctx.log(f"[{i}/{len(videos)}] {result.video.name} → {status_line(result)}")

    order = {str(v): i for i, v in enumerate(videos)}
    results.sort(key=lambda r: order.get(str(r.video), 0))

    ctx.log("")
    for line in render_table(results, ctx.dry_run):
        ctx.log(line)
    for line in render_summary(results, find_orphans({v.parent for v in videos}, videos), ctx.dry_run):
        ctx.emit(line)

    return 1 if any(r.action == "failed" for r in results) else 0


def status_line(result: Result) -> str:
    if result.action == "merged":
        state = "齐全" if not result.missing else "缺" + "/".join(result.missing)
        head = "已合并（" + ("+".join(result.added) or "无新增") + "）"
        return f"{head}{state}，{result.seconds:.1f}s"
    if result.action == "planned":
        return "预演，将并入 " + ("+".join(result.added) or "无")
    if result.action == "skipped":
        return f"跳过：{result.note}"
    return f"失败：{result.note}"


# --------------------------------------------------------------------------- #
# 命令行
# --------------------------------------------------------------------------- #
def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="merge_videos.py",
        description="批量合并视频与同名音频、字幕、封面，补齐视频缺的轨道。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  merge_videos.py .                      处理当前目录\n"
            "  merge_videos.py -n D:\\Download\\Aria2   只分析，不写入\n"
            "  merge_videos.py -j 4 .                 4 个文件并行\n"
        ),
    )
    parser.add_argument("paths", nargs="*", help="目录或单个 mp4；留空表示脚本所在目录")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只分析，不写文件")
    parser.add_argument("-k", "--keep", action="store_true", help="保留全部源文件")
    parser.add_argument("-p", "--purge", action="store_true", help="连未使用的侧车一起删")
    parser.add_argument("-j", "--jobs", type=int, default=1, help="并行数，默认 1")
    parser.add_argument("-R", "--recursive", action="store_true", help="递归处理子目录")
    parser.add_argument("-q", "--quiet", action="store_true", help="只输出汇总")
    parser.add_argument("--no-title", action="store_true", help="不写入 title 元数据")
    parser.add_argument("--sub-lang", default="auto",
                        help="新增字幕的语言标记：auto 自动识别，或 chi/eng/jpn…")
    parser.add_argument("--ffmpeg", help="ffmpeg 路径")
    parser.add_argument("--ffprobe", help="ffprobe 路径")
    parser.add_argument("--log", help="同时写入日志文件")
    parser.add_argument("--no-pause", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-V", "--version", action="version", version=f"merge_videos {VERSION}")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = parse_args(argv)

    log_path: Optional[Path] = None
    if args.log:
        log_path = Path(args.log).expanduser().resolve()
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:   # 追加，不覆盖历史
                handle.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
        except OSError as exc:
            print(f"[警告] 无法写入日志 {log_path}：{exc}")
            log_path = None

    def emit(message: str) -> None:
        try:
            print(message, flush=True)
        except OSError:
            pass                       # 控制台被关掉 / 管道断开时不要打断处理
        if log_path is not None:
            try:
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(message + "\n")
            except OSError:
                pass

    try:
        tools = Tools.resolve(args.ffmpeg, args.ffprobe)
    except ToolError as exc:
        emit(f"[错误] {exc}")
        return 2

    paths = [Path(p).expanduser().resolve() for p in args.paths]
    if not paths:
        paths = [Path(__file__).resolve().parent]

    bad = [p for p in paths if not p.exists()]
    if bad:
        for path in bad:
            emit(f"[错误] 路径不存在：{path}")
        return 2

    ctx = Context(
        tools=tools,
        dry_run=args.dry_run,
        keep=args.keep,
        purge=args.purge,
        with_title=not args.no_title,
        log=emit,
        emit=emit,
        sub_lang=args.sub_lang,
    )
    if args.quiet:
        ctx.log = lambda message: None

    try:
        code = run(paths, ctx, max(1, args.jobs), args.recursive)
    except ValueError as exc:
        emit(f"[错误] {exc}")
        return 2
    except KeyboardInterrupt:
        emit("\n已中断。")
        return 130

    if args.quiet:
        emit("")
    emit(f"完成于 {datetime.now():%Y-%m-%d %H:%M:%S}")
    return code


if __name__ == "__main__":
    sys.exit(main())
