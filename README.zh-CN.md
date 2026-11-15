<div align="center">

<br>

**简体中文** · [English](README.md)

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

# 合并音频视频

这个脚本针对的是一种情况：下载已经完成，但文件没有合并——画面在一个文件里，声音在另一个文件里，字幕和封面放在旁边。把 `merge_videos.py` 和 `merge.bat` 放进这个文件夹并运行，就能得到一个包含这些东西的 `.mp4`。音视频按原样复制，不重新编码。

**下载：**[最新版本](https://github.com/juliansy/merge-media/releases/latest)——压缩包里是 `merge_videos.py`、`merge.bat`、两份 README 和许可证。

## 它做什么

- 把 `name.mp4` 与 `name.m4a` 合成一个 `name.mp4`。
- 内嵌同名字幕：`.json`（B 站字幕导出）、`.ass`、`.srt`、`.vtt`。
- 内嵌同名封面：`.jpg`、`.jpeg`、`.png`、`.webp`；不是 JPEG 的会先转成 JPEG。
- 只补缺的：视频里已有的音频、字幕、封面一律原样保留。
- 打印这次并入了什么，以及结果是否齐全。

## 文件夹长什么样

脚本只认“同目录、同文件名、只差扩展名”的配套文件。

```text
D:\Videos\
├── lecture-01.mp4      视频                            （必需）
├── lecture-01.m4a      音频                            （可选）
├── lecture-01.json     字幕：.json .ass .srt .vtt      （可选）
├── lecture-01.jpg      封面：.jpg .jpeg .png .webp     （可选）
└── podcast-02.mp4      第二个视频，同一次处理
```

成功之后附件被删掉，视频里什么都有：

```text
D:\Videos\
├── lecture-01.mp4      视频 + 音频 + 字幕 + 封面
└── podcast-02.mp4      只有视频，没有可补的
```

想留着附件就加 `-k`。名字对不上任何视频的文件不会被碰，只会在最后的汇总里列出来。

## 需要什么

- Windows 10 或 11
- [FFmpeg](https://ffmpeg.org/download.html)：`ffmpeg.exe` 与 `ffprobe.exe` 在 `PATH` 里
- Python 3.9 或更高；不需要装额外包

## 怎么用

把这两个文件放进存放视频、音频、字幕、封面的文件夹，然后按你用的终端选一行。

| 你在哪 | 怎么写 |
| --- | --- |
| 资源管理器 | 双击 `merge.bat` |
| cmd | `merge.bat -n "D:\Videos"` |
| PowerShell / pwsh | `.\merge.bat -n "D:\Videos"` 或 `& "D:\Videos\merge.bat" -n` |
| Git Bash | `./merge.bat -n "D:/Videos"` |
| WSL | `cmd.exe /c merge.bat -n "D:\Videos"` |

PowerShell 不从当前目录运行程序，直接写 `merge.bat` 会报 `CommandNotFoundException`——`.\` 就是为这个加的；cmd 里不加也能跑。

也可以直接把东西拖到图标上：

| 操作 | 结果 |
| --- | --- |
| 把文件夹拖到 `merge.bat` 上 | 合并那个文件夹；加 `-R` 连子目录 |
| 把单个 `.mp4` 拖到 `merge.bat` 上 | 只合并这一个文件 |

### 选项

| 选项 | 作用 |
| --- | --- |
| `-n`, `--dry-run` | 只分析，不写文件 |
| `-k`, `--keep` | 保留所有源文件 |
| `-p`, `--purge` | 连视频用不上的同名附件一起删 |
| `-j N` | 同时处理 N 个文件 |
| `-R` | 连子目录一起处理 |
| `--sub-lang LANG` | 新增字幕的语言标记，默认 `auto` |
| `-V` | 显示版本 |

完整参数见 `python merge_videos.py -h`。

### 输出

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

四列从左到右：视频**原有**什么、**目录**里有什么、这次**并入**了什么、结果是否**齐全**。

## 安全

- 源文件不会被原地改写：结果先写临时文件，校验通过再替换。
- 单个文件失败时，它的源文件分毫不动；退出码为 `1`。
- 只有校验通过的合并才会删同名附件；用 `-k` 全部保留，用 `-n` 先看计划。
- 已经齐全的文件直接跳过，不会重写。

## 已知限制

- 字幕存为 `mov_text`——mp4 唯一能播的字幕格式：文字与时间轴保留，字体、位置、特效不保留。
- 每个视频只补一路新音轨、一路新字幕；原有的多轨原样保留。
- 路径超过 260 个字符时，旧版 Windows 上 FFmpeg 可能打不开。

## 许可

MIT，见 [LICENSE](LICENSE)。
