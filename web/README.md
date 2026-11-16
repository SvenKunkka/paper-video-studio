# Paper Video Studio — browser edition

[中文说明](#中文说明) · GPL-3.0

Paste a script or import TXT/Markdown, edit the storyboard, add local images, generate Chinese narration, and export a video with burned-in subtitles. SRT, storyboard JSON, and a PNG cover can also be downloaded.

## Run and build

```sh
cd web
npm ci
npm run build
python3 -m http.server 8080 --directory dist
```

Open `http://localhost:8080`. Deploy the contents of `dist/` to an HTTPS static host. No Python rendering server, Blender, API key, or paid inference service is needed by the browser edition. Python above is only an example static file server.

The app uses Canvas, Web Audio, and MediaRecorder. It checks the browser's real encoder support, prefers MP4, and falls back to WebM with the correct extension. Keep the page in the foreground during export; recording takes approximately the video's running time. Select a smaller frame size on slower devices.

Chinese speech is generated locally with the Apache-2.0 Kokoro Chinese model. The first speech request downloads model/voice resources from Hugging Face and caches them in the browser. The total initial download including the local runtime is approximately 370 MB. Network access to Hugging Face is required. Scripts and image contents are not uploaded. Runtime scripts and WASM are shipped with this site; see [third-party notices](../THIRD_PARTY_TTS.md).

The current editor lives in the page's memory. Refreshing clears it; download the finished outputs before leaving. Cancellation discards in-flight results, while a third-party model download or inference that already started may continue internally.

## 中文说明

1. 粘贴文案，或导入 `.txt` / `.md` / `.markdown` 文件。
2. 点击“整理分镜”，可修改每个镜头的标题、完整旁白和画面类型。
3. 需要图片时，先“添加图片”，再给对应镜头选择“关联图片”。网页不读取 Markdown 中的本机路径，避免浏览器无法访问你的文件。
4. 点击“只生成配音”可先试听；点击“制作视频”会生成完整配音并导出。
5. 完成后下载视频、SRT、分镜 JSON 和封面。导出期间保持网页在前台。

TXT 会保留字面内容；Markdown 的标题用于画面，正文用作旁白。上方原文修改后，旧分镜会暂时锁定；重新整理后再编辑，避免两处修改互相覆盖。修改旁白、声音或语速后，对应配音会失效并重新生成。

竖屏 9:16 与横屏 16:9 均可选，提供 480p / 720p / 1080p。视频格式以浏览器实际支持为准，按钮和文件扩展名会标明 MP4 或 WebM。

首次生成中文配音需下载约 370 MB 资源；文案和图片在浏览器本地处理。设备需能运行浏览器模型；没有可用 GPU 时使用较慢的本地 CPU 模式。首次加载或模型生成遇到错误时，会显示原因并停止，不以无声文件充当完成结果。

当前编辑内容存在页面内存中，刷新会清空，请先下载成果。模型下载和正在执行的单次推理不能被第三方库强制中断，取消会丢弃其结果并停止后续工作。

## Checks

```sh
npm test
node --test ../tests/test_web_tts.mjs
```

These automated checks cover text preservation, timing, subtitle integrity, and speech orchestration. Actual browser encoding, downloaded videos, and responsive screenshots are separate acceptance checks.
