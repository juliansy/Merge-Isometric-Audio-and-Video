<div align="center">

<br>

[简体中文](README.zh-CN.md) · **English**

<br>

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

This script is for downloads that never got merged: the video has no sound, the audio sits in its own file, subtitles and cover art lie next to them. Put `merge_videos.py` and `merge.bat` into that folder and run it — video, audio, subtitles and cover become one `.mp4`. Video and audio are copied as they are, so nothing is re-encoded.

## What it does

- Merges `name.mp4` and `name.m4a` into one `name.mp4`.
- Embeds a same-name subtitle: `.json` (Bilibili subtitle export), `.ass`, `.srt` or `.vtt`.
- Attaches a same-name cover: `.jpg`, `.jpeg`, `.png` or `.webp`; anything that is not JPEG is converted first.
- Adds only what is missing: audio, subtitles and cover already inside the video stay untouched.
- Prints what it merged and whether the result is complete.

## Requirements

- Windows 10 or 11
- [FFmpeg](https://ffmpeg.org/download.html): `ffmpeg.exe` and `ffprobe.exe` on `PATH`
- Python 3.9 or newer; no extra packages

## How to use

Put `merge_videos.py` and `merge.bat` in the folder that holds the files.

| Action | Result |
| --- | --- |
| Double-click `merge.bat` | Merges every video in that folder |
| Drop a folder onto `merge.bat` | Merges that folder; add `-R` to include subfolders |
| Drop a single `.mp4` onto `merge.bat` | Merges only that file |
| `merge.bat -n` | Shows the plan and writes nothing |

### Options

| Option | Meaning |
| --- | --- |
| `-n`, `--dry-run` | Analyse only; nothing is written |
| `-k`, `--keep` | Keep every source file |
| `-p`, `--purge` | Also delete sidecars the video did not need |
| `-j N` | Process N files at the same time |
| `-R` | Include subfolders |
| `--sub-lang LANG` | Language tag for added subtitles; `auto` by default |
| `-V` | Print the version |

`python merge_videos.py -h` lists every option.

### Output

```text
#  文件            原有        目录        动作 并入           结果                  耗时
-----------------------------------------------------------------------------------------
1  lecture-01.mp4  音✗ 字✗ 封✗ 音✓ 字✓ 封✓ 合并 音频+字幕+封面 齐全                0.4s
     └ 删除 3 个源文件
2  podcast-02.mp4  音✗ 字✗ 封✗ 音✗ 字✗ 封✗ 跳过 —              缺音频/字幕/封面    0.1s
     └ 无可合并素材（缺 音频/字幕/封面）

合并 1 个，跳过 1 个，失败 0 个。
```

The console output is in Chinese. Read the columns left to right: what the video **has**, what the **folder** offers, what was **merged in**, and whether the result is **complete** now.

## Safety

- Source files are never edited in place. The result is written to a temp file, checked, then swapped in.
- If one file fails, its sources stay exactly as they were; the exit code is `1`.
- Sidecars are deleted only after a merge has been verified. Use `-k` to keep them, `-n` to preview.
- Files that are already complete are skipped, never rewritten.

## Limitations

- Subtitles are stored as `mov_text`, the only subtitle format mp4 plays: text and timing survive, styling and positioning do not.
- One new audio track and one new subtitle track per video; existing tracks are kept as they are.
- Paths longer than 260 characters can fail inside FFmpeg on older Windows builds.

## License

MIT — see [LICENSE](LICENSE).
