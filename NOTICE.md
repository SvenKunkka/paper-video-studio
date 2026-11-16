# Attribution and modification notice

Paper Video Studio is a modified version of [shred-kit](https://github.com/amirmushichge/shred-kit), originally created by **Amir Mushich**.

The upstream source history, GNU GPL v3.0 license, author attribution, and original template documentation are retained. The upstream documentation is preserved in [README.upstream.md](README.upstream.md).

## Changes by SvenKunkka — 2026-11-16

- Added a local TXT/Markdown-to-video workflow with editable storyboards, complete narration, measured speech subtitles, and text, steps, comparison, and local-image scenes.
- Added macOS speech synthesis and native file-selection launcher source.
- Added content-based job isolation and integrity-checked media caches.
- Added examples, regression tests, and bilingual project documentation.
- Extended the original poster layout to wrap Chinese body text.

The local workflow uses Python, Pillow, ffmpeg, and the host macOS speech engine. It does not require Blender; the original Blender template remains available separately.

## Browser edition changes by SvenKunkka — 2026-11-16

- Added a static browser editor for pasted or imported TXT/Markdown, editable scenes, and explicitly selected local images.
- Added local Chinese Kokoro model inference with measured PCM subtitle timing, audio invalidation after narration/voice/speed edits, and stale-storyboard editing protection.
- Added Canvas/Web Audio/MediaRecorder video export, portrait and landscape layouts, selectable frame sizes, MP4 preference with a WebM fallback, and video/SRT/JSON/cover downloads.
- Added browser build instructions, runtime assets, third-party attribution, and browser/pure-logic verification.

Chinese speech generation and audible MP4 export have been exercised in a real browser. Speech model/voice resources are downloaded from Hugging Face for local inference; scripts and image contents are not uploaded. Third-party components and model files retain their own licenses, described in [THIRD_PARTY_TTS.md](THIRD_PARTY_TTS.md).

Code in this modified project remains available under the **GNU General Public License, version 3.0**. See [LICENSE](LICENSE) for the full license and warranty disclaimer. This notice does not replace or remove any upstream notices.

## Media and platform components

- Upstream recordings in `assets/sound/` are described by their author as public domain. Their source notice is retained in [assets/sound/SOURCES.md](assets/sound/SOURCES.md).
- The upstream demo image is the original author's render. Its permission to use it in videos made with the kit is preserved in the upstream documentation; this notice does not expand that permission.
- System fonts, macOS voices, Blender, ffmpeg, Python, and third-party Python packages are not relicensed by this notice. Their own terms continue to apply.
- Browser speech dependencies, Kokoro model/voice resources, and vendored ONNX Runtime files are covered by their upstream notices. See [THIRD_PARTY_TTS.md](THIRD_PARTY_TTS.md) and the license files under `web/tts/vendor/`; this project does not relicense them as GPL-only components.
- User-supplied writing and images are not made GPL merely by being used as inputs. Rights in supplied media and any source material incorporated in a video remain applicable.

## 中文说明

Paper Video Studio 基于 Amir Mushich 的 shred-kit 改造，保留上游来源、作者署名、GPL v3.0 许可及原模板文档。SvenKunkka 于 2026-11-16 增加本地文案制作、配音字幕、原生入口、缓存隔离、测试和双语说明，并改进原海报的中文排版。同日增加浏览器编辑器、本地中文模型配音、时间轴与字幕、横竖屏视频导出和下载，完成真实浏览器的中文配音与有声 MP4 验证。

项目代码继续采用 GNU GPL v3.0；浏览器配音依赖、模型与运行时的许可见 `THIRD_PARTY_TTS.md`。原音效、演示图、系统组件、用户文案与图片的权利按上述各自说明处理。完整许可与无担保条款见 `LICENSE`。
