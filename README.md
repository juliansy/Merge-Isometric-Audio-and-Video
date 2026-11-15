
<div align="center">

[简体中文](README.zh-CN.md) · **English**

</div>

<div align="center">

![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows-0078D4?logo=windows&logoColor=white)
![FFmpeg](https://img.shields.io/badge/ffmpeg-required-4C566A)
![License](https://img.shields.io/badge/license-MIT-2EA043)
[![Release](https://img.shields.io/github/v/release/juliansy/Merge-Isometric-Audio-and-Video?color=orange&label=release)](https://github.com/juliansy/Merge-Isometric-Audio-and-Video/releases)
![Stars](https://img.shields.io/github/stars/juliansy/Merge-Isometric-Audio-and-Video?color=yellow)

</div>

# Merge Audio and Video

Downloads often arrive in pieces: a video with no sound, the audio in a separate file, subtitles and cover art lying next to them. Drop this tool into that folder and they come back together as one normal `.mp4` — no re-encoding, no quality loss.

## What it does

- **Mux** `name.mp4` + `name.m4a` into one `name.mp4` (stream copy).
- **Embed subtitles** from a same-name `.json` (Bilibili subtitle export), `.ass`, `.srt`, or `.vtt`.
- **Attach a cover** from a same-name `.jpg`, `.jpeg`, `.png`, or `.webp` (converted on the fly).
- **Add only what is missing.** Audio, subtitles and cover already inside the video are kept as they are.
- **Report honestly** — which files were merged, what went in, and whether each result is complete.

Works well with Bilibili-Evolved's DASH export and aria2 batch downloads.

## Requirements

- Windows 10 or 11
- [FFmpeg](https://ffmpeg.org/download.html) — `ffmpeg.exe` and `ffprobe.exe` on `PATH`
- Python 3.9 or newer (standard library only)

## Use

Put `merge_videos.py` and `merge.bat` in the folder you want to process.

| Action | Result |
| --- | --- |
| Double-click `merge.bat` | Merge every video in that folder |
| Drop a folder onto `merge.bat` | Merge that folder (add `-R` for subfolders) |
| Drop a `.mp4` onto `merge.bat` | Merge only that file |
| `merge.bat -n` | Dry run — shows the plan, writes nothing |

### Options

| Option | Meaning |
| --- | --- |
| `-n`, `--dry-run` | Analyse only, nothing is written |
| `-k`, `--keep` | Keep every source file |
| `-p`, `--purge` | Also delete sidecars the video didn't need |
| `-j N` | Process N files at the same time |
| `-R` | Include subfolders |
| `--sub-lang LANG` | Language tag for added subtitles (`auto` by default) |
| `-V` | Print the version |

`python merge_videos.py -h` lists everything.

### What you see

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

The columns read left to right: what the video **has**, what the **folder** offers, what was actually **merged in**, and whether the result is now **complete**.

## Safety

- Sources are never edited in place: the output goes to a temp file, is verified, then swapped in.
- A failed file leaves every source untouched; the exit code is `1`.
- Sidecars are deleted only after a verified merge. Use `-k` to keep them and `-n` to preview.
- Files that are already complete are skipped, never rewritten.

## Limitations

- Subtitles end up as `mov_text` (an mp4 limitation): text and timing survive, styling and positioning do not.
- One new audio track and one new subtitle track per video; existing tracks are preserved as-is.
- Command-line messages are in Chinese.
- Paths longer than 260 characters may fail inside FFmpeg on older Windows builds.

## License

MIT — see [LICENSE](LICENSE).
