# Paper Video Studio

English · [中文](README.zh-CN.md)

Turn a local TXT or Markdown script into a narrated vertical video with subtitles and paper-style motion. Keep the full body as narration while extracting titles and highlights for text, steps, comparison, and local-image scenes.

**The macOS local edition is available. A web edition is under development and has not been released as a usable feature.** Local production uses Python, Pillow, ffmpeg, and macOS `say`. It needs no cloud API or API key and does not upload scripts or images. Installing dependencies may require internet access.

This project extends [shred-kit](https://github.com/amirmushichge/shred-kit) by **Amir Mushich**. The original eight-second Blender paper-shred template remains available; see the [preserved template documentation](README.upstream.md). Blender is not required for the new script-to-video workflow.

## Features

- Read `.txt`, `.md`, and `.markdown` in UTF-8, UTF-8 BOM, or GB18030.
- Preserve TXT literally; use Markdown headings on screen and read the body without presentation markup.
- Time subtitles and scenes from the generated speech, with 1080 × 1920, 30 fps MP4 output by default.
- Use paper-strip entrances with text, steps, comparison, or supplied local-image layouts.
- Save source text, editable storyboards, narration, SRT, MP4, covers, previews, and check records.
- Isolate jobs by content, settings, and image bytes, with integrity-checked caches.

## Requirements and setup

The local edition requires **macOS**, **Python 3.10+**, **Pillow**, **ffmpeg/ffprobe**, and an installed voice for the system `say` command. Chinese speech defaults to **Tingting**. Run `say -v '?'` to list installed voices; download a missing voice through macOS speech settings, or select another installed voice with `--voice`.

From the project directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install "pillow>=10"
```

Install ffmpeg with its `ffprobe` companion. If Homebrew is already available:

```sh
brew install ffmpeg
```

The full `requirements.txt` and Blender are needed only for the original template; follow [README.upstream.md](README.upstream.md) for that workflow.

## Choose a script

Build the native file-picker helper on your Mac:

```sh
.venv/bin/python script_video/build_native_launcher.py
```

Double-click **文案制作视频.app** in the project directory and select a script. A completed video opens in the default player and is revealed in Finder. The alternate **选择文案制作视频.command** entry shows progress in a window. The generated app uses a local ad-hoc signature and runs beside this project's `.venv` and `video.py`; it is not a standalone installer.

Native helper compilation, process startup, and launcher call behavior have been checked. A complete manual click-through from the file picker to the opened video is still unverified. The command-line entry below runs the verified production pipeline directly.

## Command-line workflow

```sh
.venv/bin/python video.py make examples/文案示例.md
.venv/bin/python video.py make examples/微动开关文案.txt
.venv/bin/python video.py make examples/文案示例.md --preview
.venv/bin/python video.py make examples/文案示例.md --voice Tingting --rate 240
```

`--preview` generates speech, storyboards, and still previews without exporting an MP4. To review or edit a storyboard before rendering:

```sh
.venv/bin/python video.py plan examples/文案示例.md --out storyboard.json
.venv/bin/python video.py render storyboard.json
```

Edit scene titles, layout kinds, and display items while keeping the complete narration. To change narration, edit the source script and plan it again. Outputs live in isolated folders under `video_jobs/`; `--output-base` selects another location.

## Scripts and images

Use blank lines to separate ideas. Markdown also supports headings, lists, tables, and local images:

```markdown
# A small mechanism

## A clear explanation

Your supplied narration stays in the video.

![Diagram](images/switch.png)
```

Relative image paths resolve from the script's directory. Absolute paths also work. Image syntax is interpreted only in Markdown; TXT preserves it as literal text. Missing images, unsupported glyphs, or content that cannot fit its layout produce readable errors instead of silently cropping narration.

## Scope and validation

Different topics, local images, special-character paths, cache reuse, and content changes have been exercised through real renders, full video decoding, and automated tests. This workflow does not create arbitrary real product geometry or filmed footage from a script. Supply the required media or design and verify additional illustrations separately. Extracted highlights are not a substitute for fact-checking the supplied copy.

The local workflow currently depends on macOS speech and native entry points; equivalent speech production has not been validated on Windows or Linux. The web edition is still in development, so this README does not claim browser production is available.

## Project files

| Path | Purpose |
|---|---|
| `video.py` | Plan, render, and launch the local workflow |
| `script_video/` | Parsing, rendering, speech, and native launcher source |
| `tests/` | Text integrity, job isolation, and launcher behavior tests |
| `examples/` | Ready-to-use example scripts |
| [Chinese user guide](使用说明-文案制作视频.md) | Detailed script and usage guidance |
| [Upstream documentation](README.upstream.md) | The original Blender template |

## License and attribution

Code remains under **GNU GPL v3.0**; see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md) for attribution and dated modifications. Preserve the upstream [sound source notice](assets/sound/SOURCES.md) and the demo-image permission in the original documentation. Input media, system components, and any source material incorporated in a video retain their own applicable rights.
