# Paper Video Studio — browser edition

[中文说明](#中文说明) · GPL-3.0

Paste a script or import TXT/Markdown, edit the storyboard, and add local images to make a **three-dimensional paper-shred film**. Each poster tears into strips, drops as ribbons, passes through a shredder, and rebuilds. Procedural paper/machine sound effects are the default; Chinese narration and synchronized subtitles are optional. The earlier text/image explainer style remains selectable. Download the video, storyboard JSON, PNG cover, and SRT when narration is enabled.

[Open the public studio](https://paper-video-studio.yujianxi0.chatgpt.site) — no sign-in or ChatGPT account required. The [source repository](https://github.com/SvenKunkka/paper-video-studio) is public. This GPL-3.0 project extends [Amir Mushich's shred-kit](https://github.com/amirmushichge/shred-kit); its original Blender workflow is preserved in [README.upstream.md](../README.upstream.md).

## Film and sound

The browser film uses Three.js/WebGL 2. Every poster lasts at least eight seconds, with nominal phases at 0–0.6 s (tear), 0.6–2.6 s (falling ribbons), 2.6–5.1 s (feed/cut), and 5.1–8 s (reassembly). Longer narration stretches the scene while retaining the four phases. Its synchronized effects are generated locally by deterministic DSP; the default does not download a voice model.

Select **Chinese narration with effects** to generate speech locally with the Apache-2.0 Kokoro Chinese model and derive subtitle timing from real PCM samples. The first speech request downloads approximately **370 MB** of model, voice, and runtime resources from Hugging Face and caches the model subject to browser storage availability. Access to Hugging Face and a device capable of local inference are required. A local CPU fallback may be slower when WebGPU is unavailable. Model loading/inference errors stop the requested narration workflow instead of pretending speech was produced.

Scripts and image contents are not uploaded. Runtime scripts and WASM ship with the website. See [media notices](../THIRD_PARTY_MEDIA.md) for Three.js/Mediabunny and [speech notices](../THIRD_PARTY_TTS.md) for the optional model and runtime. The browser's real-time paper renderer is a separate implementation, with different rendering quality and techniques from Blender ray tracing.

## Export and browser limits

Default export uses a **Dedicated Worker + OffscreenCanvas + WebCodecs + Mediabunny** to encode frames at explicit timeline timestamps. It does not record the preview in real time. **Switching tabs is supported while the page stays open.** Browser freezing/discarding, closing or reloading the page, and system sleep can pause or terminate the job; this is not a persistent server job.

The **compatible foreground recording** action retains MediaRecorder capture for browsers where the default exporter is unavailable. That mode still needs the page in the foreground, and takes approximately the video's running time.

The three-dimensional style needs WebGL 2 with graphics acceleration. Default export also needs Worker, OffscreenCanvas, WebCodecs audio/video encoders and supported codecs inside the Worker; the app checks capabilities at runtime. Prefer a current browser and reduce resolution on constrained devices. The earlier text/image style can avoid a three-dimensional graphics requirement, while foreground recording is a separate encoder fallback. Export prefers MP4 and can fall back to WebM with the matching extension. The UI reports the format actually produced.

Editing state and generated speech live in page memory. Refreshing clears them; download finished outputs before leaving. Cancellation discards in-flight results and stops later work, while an optional model download or an inference already started may finish internally.

## Run and build

```sh
cd web
npm ci
npm run build
python3 -m http.server 8080 --directory dist
```

Open `http://localhost:8080`. Deploy the contents of `dist/` to an HTTPS static host. No Python rendering server, Blender, API key, or paid inference service is needed by the browser edition. Python above is only an example static file server.

## 中文说明

[打开公开在线工具](https://paper-video-studio.yujianxi0.chatgpt.site)，无需登录或 ChatGPT 账号。项目基于 [Amir Mushich 的 shred-kit](https://github.com/amirmushichge/shred-kit)，保留 GPL-3.0 和[原 Blender 模板说明](../README.upstream.md)。

1. 粘贴文案，或导入 `.txt` / `.md` / `.markdown` 文件。
2. 点击“整理分镜”，修改各海报的标题和文案。默认选择“三维碎纸 · 原项目风格”。
3. 需要图片时，先“添加图片”，再给对应镜头选择“关联图片”。网页不读取 Markdown 中的本机路径，避免浏览器无法访问你的文件。
4. 默认使用“纸张与机器音效”，可直接预览并制作。需要口播和字幕时再选择“中文解说与音效”；“只生成配音”可先试听。
5. 完成后下载视频、分镜 JSON、封面；启用解说时还可下载 SRT 字幕。默认导出可切换标签页，网页须保持打开。

每张海报至少 8 秒，标准相位为 0–0.6 秒撕裂、0.6–2.6 秒纸带飘落、2.6–5.1 秒送纸切割、5.1–8 秒重组；长解说会相应拉长镜头，并保留四阶段。声音默认是程序合成的撕纸、纸带摩擦、机器切割和归位轻响，无需语音模型。“图文讲解 · 旧版”保留之前的文字、步骤、对比和图片布局。

TXT 会保留字面内容；Markdown 的标题用于画面，正文用作旁白。上方原文修改后，旧分镜会暂时锁定；重新整理后再编辑，避免两处修改互相覆盖。修改旁白、声音或语速后，对应配音会失效并重新生成。

竖屏 9:16 与横屏 16:9 均可选，提供 480p / 720p / 1080p。视频格式以浏览器实际支持为准，按钮和文件扩展名会标明 MP4 或 WebM。

只有启用中文解说或请求生成配音，首次才下载约 370 MB 资源，需要能访问 Hugging Face。文案和图片在浏览器本地处理，不上传内容。设备需能运行浏览器模型；没有可用 WebGPU 时使用较慢的本地 CPU 模式。加载或模型生成遇到错误时，会显示原因并停止对应解说制作，不用缺失的配音冒充已完成解说。运行时随网页提供，许可见[第三方配音说明](../THIRD_PARTY_TTS.md)。

默认逐帧导出通过 Worker、OffscreenCanvas、WebCodecs 和 Mediabunny 运行，可切换标签页。浏览器冻结或丢弃页面、关闭或刷新网页、系统休眠，都可能暂停或终止任务，不能保证后台持续执行。“兼容前台录制”仍按播放过程录制，必须保持网页在前台。

三维画面要求 WebGL 2 和图形加速；默认导出还需浏览器在工作线程中提供所需画布、音视频编码器及格式支持，网页会检查实际能力。图形受限时可尝试旧版图文风格，编码受限时可尝试前台兼容录制；两者解决的限制不同。Three.js 和 Mediabunny 归属见[第三方媒体说明](../THIRD_PARTY_MEDIA.md)。浏览器使用实时三维渲染，不等同于原模板的 Blender 光线追踪画质。

当前编辑内容存在页面内存中，刷新会清空，请先下载成果。模型下载和正在执行的单次推理不能被第三方库强制中断，取消会丢弃其结果并停止后续工作。

## Checks

```sh
npm test
node --test ../tests/test_web_tts.mjs
```

These automated checks cover text preservation, timing, subtitle integrity, speech orchestration, and deterministic sound blocks. Actual browser encoding, downloaded videos, and responsive screenshots are separate acceptance checks. A 64-second 1080 × 1920 MP4 with 1,920 frames and 48 kHz stereo AAC has passed full decoding. This establishes the tested output, not every browser/device or uninterrupted execution through freezing/sleep.
