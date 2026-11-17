# Paper Video Studio

[English](README.md) · 中文

把 TXT、Markdown 文案和本地图片制作成**三维碎纸短片**：印刷海报撕成纸条、纸带飘落、送入碎纸机切割，再重新拼成海报。默认配纸张与机器音效；中文解说和同步字幕为可选项。旧版的文字、步骤、对比及图片讲解布局仍可选择。

**可选择网页版或 macOS 本地版。** 网页版通过 Three.js 制作三维纸张电影，使用 Worker、OffscreenCanvas、WebCodecs 和 Mediabunny 逐帧导出，启用解说时再运行本地中文模型；macOS 本地版保留 Python、Pillow、ffmpeg 和系统 `say` 的图文讲解流程。两种流程都不需要付费配音接口，不上传文案和图片内容。安装依赖、下载可选配音资源时需要联网。

项目基于 Amir Mushich 的 [shred-kit](https://github.com/amirmushichge/shred-kit) 扩展。原来的 8 秒 Blender 碎纸模板仍保留，见 [原模板说明](README.upstream.md)。新的文案制作流程不需要 Blender。

## 网页版

[打开在线工具](https://paper-video-studio.yujianxi0.chatgpt.site)。网页公开可用，无需登录，也不需要 ChatGPT 账号；[源码仓库](https://github.com/SvenKunkka/paper-video-studio)同样公开，可以按下方步骤自行运行或部署。

1. 粘贴文案，或选择本地 `.txt`、`.md`、`.markdown` 文件。
2. 整理分镜，编辑每张海报的标题和文案；需要图片时，先添加图片，再关联到镜头。
3. 默认选择“三维碎纸 · 原项目风格”和“纸张与机器音效”，预览后制作。需要口播和同步字幕时，再选择“中文解说与音效”。
4. 下载视频、SRT 字幕、分镜 JSON 和 PNG 封面，再刷新或离开页面。

每张海报会演出**至少 8 秒**的完整动画。标准 8 秒相位为：0–0.6 秒撕裂、0.6–2.6 秒纸带飘落、2.6–5.1 秒送纸切割、5.1–8 秒重组。较长的中文解说会相应拉长镜头，并保留四阶段。选择“图文讲解 · 旧版”可使用之前的讲解布局。

可选择 **9:16 竖屏**或 **16:9 横屏**，提供 **480p / 720p / 1080p**。根据浏览器实际编码能力优先导出 **MP4**，不支持时回退 **WebM**；下载按钮和扩展名会标明实际格式。验收中已实际导出并完整解码一条 **64 秒、1080 × 1920、1,920 帧、48 kHz 双声道 AAC** 的 MP4。

默认纸张与机器音效由本地程序合成，**无需下载语音模型**。只有启用中文解说或点击生成配音时，首次才下载约 **370 MB** 的模型、声音和运行时资源，网络需要能访问 **Hugging Face**。推理在浏览器本地完成，文案和图片内容不会发送给模型托管方；模型资源按浏览器存储条件缓存。设备和浏览器需要能够运行模型，没有可用 WebGPU 时，本地 CPU 模式可能较慢。

默认导出在独立 Worker 中逐帧编码，**可以切换标签页继续生成**，但网页仍须保持打开。浏览器冻结或丢弃页面、关闭或刷新网页、系统休眠，都可能暂停或终止任务；这不是服务器后台服务。“兼容前台录制”使用 MediaRecorder 按实际播放录制，仍需保持页面在前台，耗时约等于视频片长。

三维风格需要 **WebGL 2** 和浏览器图形加速；默认导出还需要 Worker、OffscreenCanvas、WebCodecs 音视频编码器及工作线程内可用的编码格式。网页会检查实际能力。遇到图形限制可选择旧版图文布局，编码限制则另可尝试前台兼容录制。浏览器纸张电影采用自己的实时渲染方式，画质和渲染机制不等同于 Blender 光线追踪。

编辑内容与已生成声音保存在页面内存中，刷新会清空，请先下载成果。取消会丢弃待完成结果并停止后续工作；已经开始的可选模型下载或单次推理可能在底层完成后才结束。

修改上方原文后，先重新整理分镜，再编辑各镜头；修改旁白、声音或语速后，对应音轨会失效并重新生成。网页图片必须通过“添加图片”明确选择并关联，不能直接读取 Markdown 中的本机图片路径。

### 构建和打开网页版

在项目根目录执行：

```sh
cd web
npm ci
npm run build
python3 -m http.server 8080 --directory dist --bind 127.0.0.1
```

然后打开 `http://localhost:8080`。生成的 `web/dist/` 可放在 HTTPS 静态托管服务上。这里的 Python 仅用于示例静态文件服务；网页制作不需要 Python 渲染服务、macOS 语音、Blender 或 API Key。详见 [网页版双语说明](web/README.md)；Three.js 和 Mediabunny 归属见 [THIRD_PARTY_MEDIA.md](THIRD_PARTY_MEDIA.md)，可选配音依赖与模型许可见 [THIRD_PARTY_TTS.md](THIRD_PARTY_TTS.md)。

## macOS 本地版能做什么

- 读取 UTF-8、UTF-8 BOM 或 GB18030 的 `.txt`、`.md`、`.markdown` 文件。
- TXT 按字面保留正文；Markdown 标题用于画面，正文去掉排版标记后作为旁白。
- 按实际配音安排字幕和场景长度，默认输出 1080 × 1920、30 fps 的 MP4。
- 按文案结构安排文字、步骤、对比和本地图片，并使用纸条入场动画。
- 保留原文、可编辑分镜、配音、SRT、MP4、封面、预览图和检查记录。
- 按内容、设置和图片内容隔离制作任务，避免修改文案后串用旧语音或旧画面。

## 准备 macOS 本地环境

本地版需要 macOS、Python 3.10+、Pillow、ffmpeg，以及系统 `say` 命令可用的语音。默认中文语音为 **Tingting**；可用 `say -v '?'` 查看本机语音。若没有所需语音，先在 macOS 的语音设置中下载，或通过 `--voice` 选择已安装的语音。

在项目目录执行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install "pillow>=10"
```

ffmpeg 需要同时提供 `ffmpeg` 和 `ffprobe`。已安装 Homebrew 时可使用：

```sh
brew install ffmpeg
```

只有使用原 Blender 模板时，才需要另装 Blender 和 `requirements.txt` 中的完整依赖；步骤见 [原模板说明](README.upstream.md)。

## 在 macOS 选择文案制作

先生成本机文件选择入口：

```sh
.venv/bin/python script_video/build_native_launcher.py
```

然后双击项目目录中的 **文案制作视频.app**，选择文案。制作完成后会打开成片并在访达中显示文件位置。备用入口 **选择文案制作视频.command** 会显示制作进度。生成的 `.app` 使用本地临时签名，需和项目目录中的 `.venv`、`video.py` 一起使用；它不是独立安装包。

原生入口已完成构建、启动和调用逻辑验证；文件选择器中点击文案到成片自动打开的完整界面流程尚未人工点击验收。使用命令入口可直接运行已验证的制作流程。

## macOS 命令入口

```sh
.venv/bin/python video.py make examples/文案示例.md
.venv/bin/python video.py make examples/微动开关文案.txt
.venv/bin/python video.py make examples/文案示例.md --preview
.venv/bin/python video.py make examples/文案示例.md --voice Tingting --rate 240
```

`--preview` 会制作配音、分镜和静态预览，不导出 MP4。要先编辑分镜，再制作视频：

```sh
.venv/bin/python video.py plan examples/文案示例.md --out 新分镜.json
.venv/bin/python video.py render 新分镜.json
```

修改分镜标题、画面类型或要点时，保留完整旁白。若要改旁白，请编辑原文后重新规划。输出默认保存在 `video_jobs/` 的独立任务目录中；可用 `--output-base` 指定其他位置。

## 本地文案与图片

用空行分段即可；Markdown 可额外使用标题、列表、表格和本地图片：

```markdown
# 一次点击的秘密

## 快动机构

按下触动器后，内部弹性机构快速切换触点。

![结构示意](图片/开关.png)
```

图片路径相对文案文件所在目录，也支持绝对路径。图片标记只在 Markdown 中解析；TXT 中的标记按文字保留。缺图、字体不支持的字符或无法容纳的版面会给出错误，不静默裁掉正文。

## 能力与验证范围

网页流程已验证三维纸张动画、程序合成音效和逐帧 MP4 导出，并完成可选中文 FP32 模型配音、文案文件导入与图片选择关联的真实浏览器检查；自动化检查覆盖正文保留、时间轴、字幕、配音编排、音效分块连续性和旧分镜锁定。完整解码检查证明对应成片可读取；具体浏览器与设备是否适用，仍取决于图形、模型和编码能力。这些检查不代表冻结或休眠期间能持续执行。

macOS 本地流程已验证不同主题、本地图片、特殊路径、缓存复用和内容变化隔离，并通过完整视频解码检查及自动化测试。本地 Python 流程仍依赖 macOS 语音与原生入口，没有声称在 Windows 或 Linux 上完成同一配音流程验证。

两种流程都不自动生成实拍镜头或任意真实产品的三维结构；需要这些画面时应提供素材，或另外设计并核实图示。生成的重点是原文摘取，不能代替事实核查。

## 源码与许可

| 文件或目录 | 用途 |
|---|---|
| `web/` | 浏览器编辑器、三维纸张电影、程序音效、本地配音与逐帧导出 |
| [网页版说明](web/README.md) | 构建、静态托管、操作和限制 |
| `video.py` | 规划、制作与原生入口的统一命令 |
| `script_video/` | 文案解析、画面、配音和启动器源代码 |
| `tests/` | 文案完整性、制作任务和启动器行为测试 |
| `examples/` | 可直接使用的示例文案 |
| [中文使用说明](使用说明-文案制作视频.md) | 写作与操作细节 |
| [第三方配音许可](THIRD_PARTY_TTS.md) | 模型、依赖与随站点提供的运行时归属 |
| [第三方媒体许可](THIRD_PARTY_MEDIA.md) | Three.js、Mediabunny 的版本、来源和许可 |

代码保持 **GNU GPL v3.0**；完整条款见 [LICENSE](LICENSE)，来源及修改说明见 [NOTICE.md](NOTICE.md)。Three.js 与 Mediabunny 保留各自许可，见 [THIRD_PARTY_MEDIA.md](THIRD_PARTY_MEDIA.md)；可选浏览器配音依赖、模型和运行时归属见 [THIRD_PARTY_TTS.md](THIRD_PARTY_TTS.md)。原音效的公共领域说明见 [assets/sound/SOURCES.md](assets/sound/SOURCES.md)；原演示图的使用说明保留在 [原模板文档](README.upstream.md) 中。浏览器程序音效由本项目 DSP 代码合成。程序代码的许可与输入素材、系统字体及生成内容各自的权利分开处理。
