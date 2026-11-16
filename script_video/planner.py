"""Turn a local writing file into an editable, source-preserving video plan.

This module deliberately does not invent a script.  Scene narration is the
document body with Markdown presentation syntax removed; short on-screen items
are separate from the full narration.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

VERSION = 1
SCENE_TARGET = 100
KINDS = {"text", "steps", "compare", "image"}
_IMAGE_START = re.compile(r"!\[(?:\\.|[^\]])*\]\(")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST = re.compile(r"^\s*[-+*]\s+|^\s*(?:\d+\.(?!\d)|\d+[)\u3001]|[一二三四五六七八九十]+[、.)])\s*")
_ORDERED = re.compile(r"^\s*(?:\d+\.(?!\d)|\d+[)\u3001]|[一二三四五六七八九十]+[、.)])\s*")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")


def _read_source(source: Path) -> tuple[Path, str, bytes, str]:
    path = Path(source).expanduser().resolve()
    if path.suffix.lower() not in {".txt", ".md", ".markdown"}:
        raise ValueError("请选择 TXT 或 Markdown 文案文件（.txt / .md）。")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"无法读取文案：{path}\n{exc}") from exc
    if b"\0" in raw:
        raise ValueError(f"文案含有空字节，可能不是纯文本文件：{path.name}")
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            if not text.strip():
                raise ValueError(f"文案为空，请先在 {path.name} 中写入正文。")
            actual_encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else ("utf-8" if encoding == "utf-8-sig" else encoding)
            return path, text, raw, actual_encoding
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别 {path.name} 的文字编码，请另存为 UTF-8 或 GB18030。")


def _image_tokens(text: str, base: Path) -> tuple[str, list[str]]:
    """Extract local images, including paths containing spaces/parentheses."""
    images: list[str] = []
    pieces: list[str] = []
    cursor = 0
    while match := _IMAGE_START.search(text, cursor):
        depth, pos = 1, match.end()
        start = pos
        while pos < len(text) and depth:
            char = text[pos]
            if char == "\\" and pos + 1 < len(text):
                pos += 2
                continue
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            pos += 1
        if depth:
            raise ValueError("图片语法未闭合，请使用 ![说明](本地图片路径)。")
        value = text[start:pos - 1].strip()
        if value.startswith("<"):
            close = value.find(">")
            if close < 0:
                raise ValueError(f"图片路径未闭合：{value}")
            value = value[1:close]
        else:
            # An optional Markdown image title is metadata, not part of a path.
            value = re.sub(r'''\s+["'].*["']\s*$''', "", value)
        value = re.sub(r"\\([ ()\[\]\\])", r"\1", value)
        parsed = urlparse(value)
        if parsed.scheme and parsed.scheme.lower() != "file":
            raise ValueError(f"图片仅支持本地文件，不会下载网络图片：{value}")
        if parsed.scheme == "file":
            if parsed.netloc not in {"", "localhost"}:
                raise ValueError(f"不支持远程文件图片：{value}")
            value = unquote(parsed.path)
        else:
            value = unquote(value)
        if not value:
            raise ValueError("图片路径为空，请在括号中填写本地图片路径。")
        image = Path(value).expanduser()
        if not image.is_absolute():
            image = base / image
        image = image.resolve()
        if not image.is_file():
            raise ValueError(f"找不到图片：{image}\n相对路径以文案所在文件夹为起点。")
        pieces.append(text[cursor:match.start()])
        pieces.append(f"\n\n\x00IMAGE{len(images)}\x00\n\n")
        images.append(str(image))
        cursor = pos
    pieces.append(text[cursor:])
    return "".join(pieces), images


def _inline_plain(text: str) -> str:
    # Read link labels, not URLs or Markdown delimiters.
    text = re.sub(r"\[([^\]]+)\]\([^\n)]*\)", r"\1", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</?[A-Za-z][^>]*>", "", text)
    for pattern in (r"\*\*(.+?)\*\*", r"__(.+?)__", r"~~(.+?)~~", r"`([^`]+)`", r"(?<!\*)\*([^*\n]+)\*(?!\*)"):
        text = re.sub(pattern, r"\1", text)
    return re.sub(r"\\([#*_`\[\]()>!\\])", r"\1", text)


def _body_plain(block: str) -> str:
    lines: list[str] = []
    for raw_line in block.splitlines():
        line = re.sub(r"^\s*>\s?", "", raw_line)
        if _TABLE_RULE.match(line) or re.fullmatch(r"\s*(?:-{3,}|\*{3,}|_{3,})\s*", line):
            continue
        line = _LIST.sub("", line)
        line = re.sub(r"^\[[ xX]\]\s*", "", line)
        if "|" in line and (line.lstrip().startswith("|") or line.rstrip().endswith("|")):
            line = "，".join(part.strip() for part in line.strip().strip("|").split("|"))
        line = _inline_plain(line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _sections(text: str) -> tuple[str | None, list[tuple[str | None, str]]]:
    # Only a leading YAML front matter block is metadata.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if re.match(r"\A---\s*\n", text):
        match = re.match(r"\A---\s*\n.*?\n(?:---|\.\.\.)\s*(?:\n|$)", text, re.S)
        if not match:
            raise ValueError("Markdown 开头的元数据未闭合，请补上独立一行的 ---。")
        text = text[match.end():]
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines = text.splitlines()
    title: str | None = None
    heading: str | None = None
    sections: list[tuple[str | None, str]] = []
    body: list[str] = []
    fence: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            mark = stripped[:3]
            if fence is None:
                fence = mark
            elif fence == mark:
                fence = None
            index += 1
            continue
        match = None if fence else _HEADING.match(line)
        setext = (not fence and index + 1 < len(lines) and line.strip() and
                  re.fullmatch(r"\s*(?:={3,}|-{3,})\s*", lines[index + 1]))
        if match or setext:
            if body:
                sections.append((heading, "\n".join(body)))
                body = []
            new_heading = _inline_plain(match.group(2) if match else line.strip())
            if title is None:
                title = new_heading
            heading = new_heading
            index += 2 if setext else 1
            continue
        body.append(line)
        index += 1
    if body:
        sections.append((heading, "\n".join(body)))
    return title, sections


def _sentences(text: str) -> list[str]:
    # Closing quotes/brackets stay with the preceding complete sentence.
    return re.findall(r'.+?(?:[。！？!?；;]+[”’」』）)\]】]*|\.+[”’」』）)\]】]*(?=\s|$)|(?=\n)|$)', text, flags=re.S)


def _chunks(text: str) -> list[str]:
    result: list[str] = []
    current = ""
    for sentence in _sentences(text):
        if current and len(re.sub(r"\s", "", current + sentence)) > SCENE_TARGET:
            result.append(current.strip())
            current = ""
        current += sentence
    if current.strip():
        result.append(current.strip())
    return result


def _short_title(text: str) -> str:
    first = re.split(r"[。！？!?\n]", text, maxsplit=1)[0].strip()
    clauses = re.split(r"[，,；;：:]", first)
    if clauses and clauses[0] and len(first) > 28:
        first = clauses[0].strip()
    # This only abbreviates the screen title; narration is always unabridged.
    return first if len(first) <= 32 else first[:31] + "…"


def _kind(block: str, text: str) -> str:
    if _TABLE_RULE.search(block) or any(_TABLE_RULE.match(x) for x in block.splitlines()):
        return "compare"
    if re.search(r"对比|比较|相比|区别|差异|优点|缺点|\bvs\.?\b| versus ", text, re.I):
        return "compare"
    list_lines = sum(bool(_LIST.match(x)) for x in block.splitlines())
    transitions = re.findall(r"首先|其次|然后|最后|第一步|第二步|第三步", text)
    if any(_ORDERED.match(x) for x in block.splitlines()) or list_lines >= 2 or len(set(transitions)) >= 2:
        return "steps"
    return "text"


def _items(text: str) -> list[str]:
    candidates = [line.strip() for line in text.splitlines() if line.strip()]
    if len(candidates) <= 1:
        candidates = [x.strip() for x in _sentences(text) if x.strip()]
    # Items are display-only; nothing is removed from narration when condensed.
    return [(x if len(x) <= 42 else x[:41] + "…") for x in candidates[:4]]


def make_plan(source: Path, *, title: str | None = None, voice: str = "Tingting", voice_rate: int = 240) -> dict:
    """Read TXT/MD and return the version-1 storyboard contract.

    Raises ``ValueError`` with a user-readable explanation for invalid input.
    """
    path, original, raw, encoding = _read_source(source)
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise ValueError("视频标题不能是空白。")
    if not isinstance(voice, str) or not voice.strip() or any(c in voice for c in "\r\n\0"):
        raise ValueError("配音名称不能为空或包含换行。")
    if isinstance(voice_rate, bool) or not isinstance(voice_rate, int) or not 80 <= voice_rate <= 450:
        raise ValueError("配音语速需为 80–450 之间的整数。")
    is_markdown = path.suffix.lower() in {".md", ".markdown"}
    # TXT is literal prose: Markdown-looking characters can be meaningful body
    # content.  Only Markdown files opt into headings, metadata and image syntax.
    document_title, sections = _sections(original) if is_markdown else (None, [(None, original)])
    plan_title = (title or document_title or path.stem).strip()
    scenes: list[dict[str, Any]] = []
    body_parts: list[str] = []
    warnings: list[str] = []
    for heading, section in sections:
        tokenized, images = _image_tokens(section, path.parent) if is_markdown else (section, [])
        last_scene: dict[str, Any] | None = None
        pending_image: str | None = None
        for block in re.split(r"\n\s*\n", tokenized):
            image_token = re.fullmatch(r"\s*\x00IMAGE(\d+)\x00\s*", block)
            if image_token:
                image = images[int(image_token.group(1))]
                if last_scene is not None and not last_scene["image"]:
                    last_scene["image"] = image
                    last_scene["kind"] = "image"
                elif pending_image is None:
                    pending_image = image
                else:
                    scenes.append({"kind": "image", "title": heading or plan_title, "narration": "", "items": [], "image": pending_image})
                    pending_image = image
                continue
            narration = _body_plain(block) if is_markdown else block.strip()
            if not narration:
                continue
            body_parts.append(narration)
            kind = _kind(block, narration)
            for chunk in _chunks(narration):
                scene = {"kind": "image" if pending_image else kind, "title": heading or _short_title(chunk) or plan_title,
                         "narration": chunk, "items": _items(chunk), "image": pending_image}
                pending_image = None
                scenes.append(scene)
                last_scene = scene
                if len(re.sub(r"\s", "", chunk)) > SCENE_TARGET:
                    warnings.append(f"第 {len(scenes)} 场有超过 {SCENE_TARGET} 字的完整长句，已保留原文；时长将跟随配音。")
        if pending_image:
            scenes.append({"kind": "image", "title": heading or plan_title, "narration": "", "items": [], "image": pending_image})
    if not scenes:
        raise ValueError("文案没有可制作的正文或本地图片；标题和元数据不会作为旁白。")
    for index, scene in enumerate(scenes, start=1):
        scene["id"] = f"s{index:03d}"
    plan = {"version": VERSION, "title": plan_title,
            "source": {"path": str(path), "text": original, "sha256": hashlib.sha256(raw).hexdigest(),
                       "encoding": encoding, "narration_text": "\n\n".join(body_parts)},
            "settings": {"width": 1080, "height": 1920, "fps": 30, "voice": voice.strip(), "voice_rate": voice_rate,
                         "paper": "#EEECE7", "ink": "#181716", "accent": "#AC1210"},
            "scenes": scenes, "warnings": warnings}
    validate_plan(plan)
    return plan


def validate_plan(plan: dict) -> None:
    """Validate storyboard shape and detect accidental narration loss."""
    if not isinstance(plan, dict) or plan.get("version") != VERSION:
        raise ValueError("分镜版本无效，需要 version: 1。")
    if not isinstance(plan.get("title"), str) or not plan["title"].strip():
        raise ValueError("分镜缺少视频标题。")
    source = plan.get("source")
    if not isinstance(source, dict) or not all(isinstance(source.get(k), str) for k in ("path", "text", "sha256", "narration_text")):
        raise ValueError("分镜缺少原始文案、来源路径或规范化旁白正文。")
    if not Path(source["path"]).is_absolute() or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
        raise ValueError("文案路径或 SHA-256 摘要无效。")
    settings = plan.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("分镜设置必须是对象。")
    for key in ("width", "height", "fps"):
        if isinstance(settings.get(key), bool) or not isinstance(settings.get(key), int) or settings[key] <= 0:
            raise ValueError(f"分镜设置 {key} 必须是正整数。")
    rate = settings.get("voice_rate")
    if isinstance(rate, bool) or not isinstance(rate, int) or not 80 <= rate <= 450:
        raise ValueError("配音语速需为 80–450 之间的整数。")
    if not isinstance(settings.get("voice"), str) or not settings["voice"].strip() or any(c in settings["voice"] for c in "\r\n\0"):
        raise ValueError("分镜缺少配音名称。")
    for key in ("paper", "ink", "accent"):
        if not isinstance(settings.get(key), str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", settings[key]):
            raise ValueError(f"分镜颜色 {key} 需要 #RRGGBB 格式。")
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("分镜没有场景。")
    ids: set[str] = set()
    narration: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        prefix = f"第 {index} 场"
        if not isinstance(scene, dict) or scene.get("kind") not in KINDS:
            raise ValueError(f"{prefix}的画面类型无效。")
        identifier = scene.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            raise ValueError(f"{prefix}缺少唯一场景编号。")
        ids.add(identifier)
        if not isinstance(scene.get("title"), str) or not scene["title"].strip():
            raise ValueError(f"{prefix}缺少画面标题。")
        if not isinstance(scene.get("narration"), str):
            raise ValueError(f"{prefix}的旁白需要是文字。")
        if not isinstance(scene.get("items"), list) or not all(isinstance(x, str) for x in scene["items"]):
            raise ValueError(f"{prefix}的画面要点需要是文字列表。")
        image = scene.get("image")
        if image is not None:
            if not isinstance(image, str) or not Path(image).is_absolute() or not Path(image).is_file():
                raise ValueError(f"{prefix}的本地图片不存在或不是绝对路径：{image}")
            if scene["kind"] != "image":
                raise ValueError(f"{prefix}包含图片，应使用 image 类型。")
        if scene["kind"] == "image" and not image:
            raise ValueError(f"{prefix}缺少本地图片。")
        if not scene["narration"].strip() and not image:
            raise ValueError(f"{prefix}既没有旁白，也没有图片。")
        narration.append(scene["narration"])
    compact = lambda value: re.sub(r"\s+", "", value)
    if compact("".join(narration)) != compact(source["narration_text"]):
        raise ValueError("分镜旁白与文案正文不一致，可能有文字丢失、重复或顺序变化，请重新生成分镜。")
