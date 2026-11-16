# Paper Video Studio

English · [中文](README.zh-CN.md)

Turn a TXT or Markdown script into a narrated video with subtitles and paper-style motion. Keep the full body as narration while extracting titles and highlights for text, steps, comparison, and local-image scenes.

**Choose the browser edition or the macOS local edition.** The browser edition generates Chinese speech with a model running on your device and records a video with Canvas, Web Audio, and MediaRecorder. The macOS edition uses Python, Pillow, ffmpeg, and the system `say` command. Neither workflow needs a paid synthesis API or uploads your scripts and image contents. Installing dependencies and downloading browser speech resources require network access.

This project extends [shred-kit](https://github.com/amirmushichge/shred-kit) by **Amir Mushich**. The original eight-second Blender paper-shred template remains available; see the [preserved template documentation](README.upstream.md). Blender is not required for the new script-to-video workflow.

## Browser edition

[Open the hosted studio](https://paper-video-studio.yujianxi0.chatgpt.site). This instance currently requires its owner's ChatGPT account; the source repository is public, and you can also run or host your own copy using the instructions below.

1. Paste a script, or choose a local `.txt`, `.md`, or `.markdown` file.
2. Arrange the storyboard and edit each scene's title, complete narration, and layout. Add local images and associate them with scenes when needed.
3. Generate Chinese speech locally, preview it, and export a video with burned-in subtitles.
4. Download the video, SRT subtitles, storyboard JSON, and PNG cover before refreshing or leaving the page.

Choose **9:16 portrait** or **16:9 landscape**, with **480p / 720p / 1080p** output. The recorder prefers **MP4** and falls back to **WebM** according to the browser's real encoder support; the download button and extension show the format actually produced. MP4 with H.264 video and AAC audio has been verified in a browser.

The first Chinese speech request downloads approximately **370 MB** of model, voice, and runtime resources. Access to **Hugging Face** is required. Model inference stays in the browser; scripts and image contents are not sent to the model host. Model resources are cached subject to browser storage availability. A capable device and browser are needed; a local CPU fallback can be slower when WebGPU is unavailable.

Keep the page **in the foreground during export**. Recording takes approximately the video's running time. Editing state and generated speech live in page memory and are cleared by refresh; download the outputs first. Cancelling discards pending results and stops subsequent work, although a model download or one inference call already running may finish internally.

After changing the source script, arrange the storyboard again before editing its scenes. Changing narration, voice, or speed invalidates the corresponding audio. Browser images must be explicitly selected with **Add images** and linked to a scene; the browser does not read local image paths embedded in Markdown.

### Build and serve the browser edition

From the project root:

```sh
cd web
npm ci
npm run build
python3 -m http.server 8080 --directory dist --bind 127.0.0.1
```

Open `http://localhost:8080`. The generated `web/dist/` can be served by an HTTPS static host. Python here is only an example static file server; browser production needs no Python rendering service, macOS voice, Blender, or API key. See [web/README.md](web/README.md) for detailed bilingual instructions and [THIRD_PARTY_TTS.md](THIRD_PARTY_TTS.md) for speech dependencies and model notices.

## macOS local edition features

- Read `.txt`, `.md`, and `.markdown` in UTF-8, UTF-8 BOM, or GB18030.
- Preserve TXT literally; use Markdown headings on screen and read the body without presentation markup.
- Time subtitles and scenes from the generated speech, with 1080 × 1920, 30 fps MP4 output by default.
- Use paper-strip entrances with text, steps, comparison, or supplied local-image layouts.
- Save source text, editable storyboards, narration, SRT, MP4, covers, previews, and check records.
- Isolate jobs by content, settings, and image bytes, with integrity-checked caches.

## macOS local setup

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

## Choose a script on macOS

Build the native file-picker helper on your Mac:

```sh
.venv/bin/python script_video/build_native_launcher.py
```

Double-click **文案制作视频.app** in the project directory and select a script. A completed video opens in the default player and is revealed in Finder. The alternate **选择文案制作视频.command** entry shows progress in a window. The generated app uses a local ad-hoc signature and runs beside this project's `.venv` and `video.py`; it is not a standalone installer.

Native helper compilation, process startup, and launcher call behavior have been checked. A complete manual click-through from the file picker to the opened video is still unverified. The command-line entry below runs the verified production pipeline directly.

## macOS command-line workflow

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

## Local scripts and images

Use blank lines to separate ideas. Markdown also supports headings, lists, tables, and local images:

```markdown
# A small mechanism

## A clear explanation

Your supplied narration stays in the video.

![Diagram](images/switch.png)
```

Relative image paths resolve from the script's directory. Absolute paths also work. Image syntax is interpreted only in Markdown; TXT preserves it as literal text. Missing images, unsupported glyphs, or content that cannot fit its layout produce readable errors instead of silently cropping narration.

## Scope and validation

The browser workflow has been exercised with real Chinese FP32 model speech, MP4 export, script import, and image selection/association. Automated checks cover text preservation, timing, subtitles, speech orchestration, and stale-editor protection; browser and device support still depend on available model and encoding capabilities.

The macOS local workflow has been tested with different topics, local images, special-character paths, cache reuse, content changes, full video decoding, and automated tests. It continues to depend on macOS speech and native entry points; equivalent Python speech production has not been validated on Windows or Linux.

Neither edition creates arbitrary real product geometry or filmed footage from a script. Supply the required media or design and verify additional illustrations separately. Extracted highlights are not a substitute for fact-checking the supplied copy.

## Project files

| Path | Purpose |
|---|---|
| `web/` | Browser editor, local Chinese model adapter, and video recorder |
| [Browser guide](web/README.md) | Build, static hosting, usage, and browser limits |
| `video.py` | Plan, render, and launch the local workflow |
| `script_video/` | Parsing, rendering, speech, and native launcher source |
| `tests/` | Text integrity, job isolation, and launcher behavior tests |
| `examples/` | Ready-to-use example scripts |
| [Chinese user guide](使用说明-文案制作视频.md) | Detailed script and usage guidance |
| [Upstream documentation](README.upstream.md) | The original Blender template |
| [TTS notices](THIRD_PARTY_TTS.md) | Browser speech dependencies, model, and vendored runtime notices |

## License and attribution

Code remains under **GNU GPL v3.0**; see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md) for attribution and dated modifications. Browser speech components and model resources retain their own licenses, recorded in [THIRD_PARTY_TTS.md](THIRD_PARTY_TTS.md). Preserve the upstream [sound source notice](assets/sound/SOURCES.md) and the demo-image permission in the original documentation. Input media, system components, and any source material incorporated in a video retain their own applicable rights.
