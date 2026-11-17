# Paper Video Studio

English · [中文](README.zh-CN.md)

Turn TXT or Markdown copy and local images into a **three-dimensional paper-shred film**: a printed poster tears into strips, the ribbons fall, a shredder cuts the paper, and the strips rebuild the poster. Paper and machine sound effects are on by default; Chinese narration and synchronized subtitles are optional. The earlier text, steps, comparison, and image explainer layouts remain selectable.

**Choose the browser edition or the macOS local edition.** The browser edition uses Three.js for the paper film and a Worker, OffscreenCanvas, WebCodecs, and Mediabunny for frame-based video export. Chinese speech runs on your device when enabled. The macOS edition retains its Python, Pillow, ffmpeg, and system `say` explainer workflow. Neither workflow needs a paid synthesis API or uploads your scripts and image contents. Installing dependencies and downloading optional browser speech resources require network access.

This project extends [shred-kit](https://github.com/amirmushichge/shred-kit) by **Amir Mushich**. The original eight-second Blender paper-shred template remains available; see the [preserved template documentation](README.upstream.md). Blender is not required for the new script-to-video workflow.

## Browser edition

[Open the hosted studio](https://paper-video-studio.yujianxi0.chatgpt.site). The hosted studio is public and requires no sign-in or ChatGPT account. The [source repository](https://github.com/SvenKunkka/paper-video-studio) is also public, and you can run or host your own copy using the instructions below.

1. Paste a script, or choose a local `.txt`, `.md`, or `.markdown` file.
2. Arrange the storyboard and edit each poster's title and copy. Add local images and associate them with scenes when needed.
3. Keep **three-dimensional paper shred** and **paper/machine sound effects** selected, preview the film, and export. Choose **Chinese narration with effects** when a spoken explanation and synchronized subtitles are wanted.
4. Download the video, SRT subtitles, storyboard JSON, and PNG cover before refreshing or leaving the page.

Each poster gets a complete animation lasting **at least eight seconds**. Its nominal eight-second phases are 0–0.6 s tearing, 0.6–2.6 s falling ribbons, 2.6–5.1 s feeding/cutting, and 5.1–8 s reassembly. Longer narration stretches the scene while retaining all four phases. Select **text/image explainer — earlier edition** for the previous layouts.

Choose **9:16 portrait** or **16:9 landscape**, with **480p / 720p / 1080p** output. Export prefers **MP4** and falls back to **WebM** according to the browser's real encoder support; the download button and extension show the format actually produced. A 64-second, 1080 × 1920 MP4 with 1,920 video frames and 48 kHz stereo AAC has been exported and fully decoded in acceptance checks.

Default paper/machine effects are synthesized locally and **do not download a speech model**. Only enabling Chinese narration or requesting speech generation triggers the first download of approximately **370 MB** of model, voice, and runtime resources. Access to **Hugging Face** is required for that download. Model inference stays in the browser; scripts and image contents are not sent to the model host. Model resources are cached subject to browser storage availability. A capable device and browser are needed; a local CPU fallback can be slower when WebGPU is unavailable.

Default export encodes individual frames in a dedicated Worker, so **you can switch tabs while it runs**. Keep the webpage open. Browser freezing, tab disposal, closing/reloading the page, and system sleep can pause or stop the job; this is not a server-side background service. The separate **compatible foreground recording** option uses real-time MediaRecorder capture and still requires the page to stay in the foreground for approximately the video's running time.

The three-dimensional style requires **WebGL 2** and browser graphics acceleration. Default export also needs Worker, OffscreenCanvas, WebCodecs audio/video encoders, and supported codecs in the Worker. Support is checked at runtime; selecting an earlier text/image layout may help with a graphics limitation, while foreground recording is a separate encoding fallback. The browser paper film uses its own real-time rendering approach; it does not reproduce Blender's ray-traced output.

Editing state and generated speech live in page memory and are cleared by refresh; download the outputs first. Cancelling discards pending results and stops subsequent work, although an optional model download or one inference call already running may finish internally.

After changing the source script, arrange the storyboard again before editing its scenes. Changing narration, voice, or speed invalidates the corresponding audio. Browser images must be explicitly selected with **Add images** and linked to a scene; the browser does not read local image paths embedded in Markdown.

### Build and serve the browser edition

From the project root:

```sh
cd web
npm ci
npm run build
python3 -m http.server 8080 --directory dist --bind 127.0.0.1
```

Open `http://localhost:8080`. The generated `web/dist/` can be served by an HTTPS static host. Python here is only an example static file server; browser production needs no Python rendering service, macOS voice, Blender, or API key. See [web/README.md](web/README.md) for detailed bilingual instructions, [THIRD_PARTY_MEDIA.md](THIRD_PARTY_MEDIA.md) for Three.js/Mediabunny attribution, and [THIRD_PARTY_TTS.md](THIRD_PARTY_TTS.md) for optional speech dependencies and model notices.

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

The browser workflow has been exercised with three-dimensional paper animation, procedural sound effects, frame-based MP4 export, real optional Chinese FP32 model speech, script import, and image selection/association. Automated checks cover text preservation, timing, subtitles, speech orchestration, sound chunk continuity, and stale-editor protection. Full video decoding checks verify the tested output, while browser/device support still depends on graphics, model, and encoding capabilities. These checks do not establish uninterrupted execution through browser freezing or system sleep.

The macOS local workflow has been tested with different topics, local images, special-character paths, cache reuse, content changes, full video decoding, and automated tests. It continues to depend on macOS speech and native entry points; equivalent Python speech production has not been validated on Windows or Linux.

Neither edition creates arbitrary real product geometry or filmed footage from a script. Supply the required media or design and verify additional illustrations separately. Extracted highlights are not a substitute for fact-checking the supplied copy.

## Project files

| Path | Purpose |
|---|---|
| `web/` | Browser editor, three-dimensional paper film, procedural audio, local speech, and frame-based exporter |
| [Browser guide](web/README.md) | Build, static hosting, usage, and browser limits |
| `video.py` | Plan, render, and launch the local workflow |
| `script_video/` | Parsing, rendering, speech, and native launcher source |
| `tests/` | Text integrity, job isolation, and launcher behavior tests |
| `examples/` | Ready-to-use example scripts |
| [Chinese user guide](使用说明-文案制作视频.md) | Detailed script and usage guidance |
| [Upstream documentation](README.upstream.md) | The original Blender template |
| [TTS notices](THIRD_PARTY_TTS.md) | Browser speech dependencies, model, and vendored runtime notices |
| [Media notices](THIRD_PARTY_MEDIA.md) | Three.js and Mediabunny versions, sources, and licenses |

## License and attribution

Code remains under **GNU GPL v3.0**; see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md) for attribution and dated modifications. Three.js and Mediabunny retain their own licenses in [THIRD_PARTY_MEDIA.md](THIRD_PARTY_MEDIA.md); optional browser speech components and model resources are recorded in [THIRD_PARTY_TTS.md](THIRD_PARTY_TTS.md). Preserve the upstream [sound source notice](assets/sound/SOURCES.md) and the demo-image permission in the original documentation. The browser's procedural effects are generated by this project's DSP code. Input media, system components, and any source material incorporated in a video retain their own applicable rights.
