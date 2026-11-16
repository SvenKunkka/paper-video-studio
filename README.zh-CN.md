# Paper Video Studio

[English](README.md) · 中文

把本地 TXT 或 Markdown 文案制作成带配音、字幕和纸张风格动画的竖屏视频。正文作为旁白保留，画面从文案中提取标题和重点，可呈现文字、步骤、对比及本地图片。

**当前可用的是 macOS 本地版。网页版本正在开发，尚未作为可用功能发布。** 本地制作使用 Python、Pillow、ffmpeg 和 macOS 的 `say` 配音，不需要云端接口或 API Key，也不上传文案或图片。首次安装依赖可能需要联网。

项目基于 Amir Mushich 的 [shred-kit](https://github.com/amirmushichge/shred-kit) 扩展。原来的 8 秒 Blender 碎纸模板仍保留，见 [原模板说明](README.upstream.md)。新的文案制作流程不需要 Blender。

## 能做什么

- 读取 UTF-8、UTF-8 BOM 或 GB18030 的 `.txt`、`.md`、`.markdown` 文件。
- TXT 按字面保留正文；Markdown 标题用于画面，正文去掉排版标记后作为旁白。
- 按实际配音安排字幕和场景长度，默认输出 1080 × 1920、30 fps 的 MP4。
- 按文案结构安排文字、步骤、对比和本地图片，并使用纸条入场动画。
- 保留原文、可编辑分镜、配音、SRT、MP4、封面、预览图和检查记录。
- 按内容、设置和图片内容隔离制作任务，避免修改文案后串用旧语音或旧画面。

## 准备环境

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

## 选择文案制作

先生成本机文件选择入口：

```sh
.venv/bin/python script_video/build_native_launcher.py
```

然后双击项目目录中的 **文案制作视频.app**，选择文案。制作完成后会打开成片并在访达中显示文件位置。备用入口 **选择文案制作视频.command** 会显示制作进度。生成的 `.app` 使用本地临时签名，需和项目目录中的 `.venv`、`video.py` 一起使用；它不是独立安装包。

原生入口已完成构建、启动和调用逻辑验证；文件选择器中点击文案到成片自动打开的完整界面流程尚未人工点击验收。使用命令入口可直接运行已验证的制作流程。

## 命令入口

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

## 文案与图片

用空行分段即可；Markdown 可额外使用标题、列表、表格和本地图片：

```markdown
# 一次点击的秘密

## 快动机构

按下触动器后，内部弹性机构快速切换触点。

![结构示意](图片/开关.png)
```

图片路径相对文案文件所在目录，也支持绝对路径。图片标记只在 Markdown 中解析；TXT 中的标记按文字保留。缺图、字体不支持的字符或无法容纳的版面会给出错误，不静默裁掉正文。

## 能力与验证范围

本地流程已验证不同主题、本地图片、特殊路径、缓存复用和内容变化隔离，并通过完整视频解码检查及自动化测试。它不自动生成实拍镜头或任意真实产品的三维结构；需要这些画面时应提供素材，或另外设计并核实图示。生成的重点是原文摘取，不能代替事实核查。

本地版目前依赖 macOS 语音与原生入口；没有声称在 Windows 或 Linux 上完成该配音流程验证。网页版本仍在开发，不应从本说明推断浏览器制作能力已经交付。

## 源码与许可

- `video.py`：规划、制作与原生入口的统一命令。
- `script_video/`：文案解析、画面、配音和启动器源代码。
- `tests/`：文案完整性、制作任务和启动器行为测试。
- `examples/`：可直接使用的示例文案。
- [中文使用说明](使用说明-文案制作视频.md)：写作与操作细节。

代码保持 **GNU GPL v3.0**；完整条款见 [LICENSE](LICENSE)，来源及修改说明见 [NOTICE.md](NOTICE.md)。原音效的公共领域说明见 [assets/sound/SOURCES.md](assets/sound/SOURCES.md)；原演示图的使用说明保留在 [原模板文档](README.upstream.md) 中。程序代码的许可与输入素材、系统字体及生成内容各自的权利分开处理。
