
<div align="center">

**简体中文** · [English](README.md)

</div>

<div align="center">

![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows-0078D4?logo=windows&logoColor=white)
![FFmpeg](https://img.shields.io/badge/ffmpeg-required-4C566A)
![License](https://img.shields.io/badge/license-MIT-2EA043)
[![Release](https://img.shields.io/github/v/release/juliansy/Merge-Isometric-Audio-and-Video?color=orange&label=release)](https://github.com/juliansy/Merge-Isometric-Audio-and-Video/releases)
![Stars](https://img.shields.io/github/stars/juliansy/Merge-Isometric-Audio-and-Video?color=yellow)

</div>

# 合并音频视频

下载器常把一部片子拆成几份：视频没有声音、音频单独一个文件、字幕和封面散落在旁边。把这个工具放进同一个文件夹，它们就会合回一个正常的 `.mp4`——不重新编码，不掉画质。

## 它做什么

- **合并**同名的 `name.mp4` 与 `name.m4a`（流复制，音画无损）。
- **内嵌字幕**：同名 `.json`（B 站字幕导出）、`.ass`、`.srt`、`.vtt`。
- **内嵌封面**：同名 `.jpg`、`.jpeg`、`.png`、`.webp`（非 JPEG 会自动转码后再嵌入）。
- **只补缺的**。视频里已有的音频、字幕、封面原样保留。
- **如实汇报**：哪些文件做了合并、并进了什么、结果是否齐全。

适用于 Bilibili-Evolved 的 DASH 导出、aria2 批量下载这类"音视频分离"的产物。

## 需要什么

- Windows 10 或 11
- [FFmpeg](https://ffmpeg.org/download.html)：`ffmpeg.exe` 与 `ffprobe.exe` 在 `PATH` 里
- Python 3.9 或更高（只用标准库）

## 怎么用

把 `merge_videos.py` 和 `merge.bat` 放进要处理的文件夹。

| 操作 | 结果 |
| --- | --- |
| 双击 `merge.bat` | 合并该文件夹里的所有视频 |
| 把文件夹拖到 `merge.bat` 上 | 合并那个文件夹（加 `-R` 连子目录） |
| 把单个 `.mp4` 拖到 `merge.bat` 上 | 只合并这一个文件 |
| `merge.bat -n` | 预演：只列出计划，一个字节都不写 |

### 选项

| 选项 | 作用 |
| --- | --- |
| `-n`, `--dry-run` | 只分析，不写任何文件 |
| `-k`, `--keep` | 保留所有源文件 |
| `-p`, `--purge` | 连视频用不上的同名附件一起删 |
| `-j N` | 同时处理 N 个文件 |
| `-R` | 连子目录一起处理 |
| `--sub-lang LANG` | 新增字幕的语言标记（默认 `auto` 自动识别） |
| `-V` | 显示版本 |

完整参数见 `python merge_videos.py -h`。

### 输出长什么样

```text
#  文件            原有        目录        动作 并入           结果                  耗时
-----------------------------------------------------------------------------------------
1  lecture-01.mp4  音✗ 字✗ 封✗ 音✓ 字✓ 封✓ 合并 音频+字幕+封面 齐全                0.4s
     └ 删除 3 个源文件
2  podcast-02.mp4  音✗ 字✗ 封✗ 音✗ 字✗ 封✗ 跳过 —              缺音频/字幕/封面    0.1s
     └ 无可合并素材（缺 音频/字幕/封面）

合并 1 个，跳过 1 个，失败 0 个。
本次并入：音频 1 个，字幕 1 个，封面 1 个。
齐全 1 个，不齐全 0 个。
```

四列从左到右是：视频**原有**什么、**目录**里有什么、这次**并入**了什么、结果是否**齐全**。

## 安全

- 源文件不会被原地改写：先写临时文件，校验通过后再替换。
- 单个文件失败时源文件分毫不动，退出码为 `1`。
- 只有校验通过的合并才会删同名附件；用 `-k` 全保留，用 `-n` 先看计划。
- 已经齐全的文件直接跳过，不会重写。

## 已知限制

- 字幕统一转成 `mov_text`（mp4 容器的限制）：文字与时间轴保留，字体、位置、特效不保留。
- 每个视频只补一路新音轨、一路新字幕；原有的多轨原样保留。
- 命令行输出是中文。
- 路径超过 260 个字符时，旧版 Windows 上 FFmpeg 可能打不开。

## 许可

MIT，见 [LICENSE](LICENSE)。
