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
[![Release](https://img.shields.io/github/v/release/juliansy/merge-media?color=orange&label=release)](https://github.com/juliansy/merge-media/releases)
![Stars](https://img.shields.io/github/stars/juliansy/merge-media?color=yellow)

</div>

# Merge Audio and Video

This tool is for a download that finished without being assembled: one file holds the picture, another holds the sound, and the subtitles and cover art sit beside them. Put `merge_videos.py` and `merge.bat` into that folder and run it — you get one `.mp4` with all of them inside. Video and audio are copied as they are, so nothing is re-encoded.

**Download:** [latest release](https://github.com/juliansy/merge-media/releases/latest) — a zip with `merge_videos.py`, `merge.bat`, both READMEs and the license.

## What it does

- Merges `name.mp4` and `name.m4a` into one `name.mp4`.
- Embeds a same-name subtitle: `.json` (Bilibili subtitle export), `.ass`, `.srt` or `.vtt`.
- Attaches a same-name cover: `.jpg`, `.jpeg`, `.png` or `.webp`; anything that is not JPEG is converted first.
- Adds only what is missing: audio, subtitles and cover already inside the video stay untouched.
- Prints what it merged and whether the result is complete.

## What a folder looks like

Put both script files into the folder. The media it picks up shares a name and differs only by extension.

```text
D:\Videos\
├── merge.bat           the launcher — double-click this
├── merge_videos.py     the script it runs — keep both together
├── lecture-01.mp4      the video (required)
├── lecture-01.m4a      the audio (optional)
├── lecture-01.json     subtitles (optional; .ass .srt .vtt also work)
├── lecture-01.jpg      cover (optional; .jpeg .png .webp also work)
└── podcast-02.mp4      a second video, same run
```

After a successful run the sidecars are gone and the videos carry everything:

```text
D:\Videos\
├── merge.bat
├── merge_videos.py
├── lecture-01.mp4      video + audio + subtitles + cover
└── podcast-02.mp4      video only, nothing to add
```

Use `-k` if you want the sidecars kept. A file whose name matches no video is left alone and listed at the end.

## Requirements

- Windows 10 or 11
- [FFmpeg](https://ffmpeg.org/download.html): `ffmpeg.exe` and `ffprobe.exe` on `PATH`
- Python 3.9 or newer; no extra packages

## How to use

Put both files in the folder that holds the video, audio, subtitles and cover, then pick the line for your terminal.

| Where | What to type |
| --- | --- |
| File Explorer | double-click `merge.bat` |
| cmd | `merge.bat -n "D:\Videos"` |
| PowerShell / pwsh | `.\merge.bat -n "D:\Videos"` or `& "D:\Videos\merge.bat" -n` |
| Git Bash | `./merge.bat -n "D:/Videos"` |
| WSL | `cmd.exe /c merge.bat -n "D:\Videos"` |

PowerShell does not run programs from the current folder, so a bare `merge.bat` fails with `CommandNotFoundException` — that is what the `.\` is for. In cmd the bare name is fine.

Dropping things on the icon works too:

| Action | Result |
| --- | --- |
| Drop a folder onto `merge.bat` | Merges that folder; add `-R` to include subfolders |
| Drop a single `.mp4` onto `merge.bat` | Merges only that file |

### Options

| Option | Meaning |
| --- | --- |
| `-n`, `--dry-run` | Analyze only; nothing is written |
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
本次并入：音频 1 个，字幕 1 个，封面 1 个。
齐全 1 个，不齐全 0 个。
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
