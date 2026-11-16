"""Local, editable narrated text-to-video renderer; no network services.

The planner owns interpretation. This module speaks the exact narration it receives,
measures each phrase's audio, and uses those boundaries for subtitles and scene timing.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import wave
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

RENDERER_VERSION = "1.0.0"
CW, CH, SR = 1080, 1920, 48000
FONT_PATHS = [Path("/System/Library/Fonts/STHeiti Medium.ttc"),
              Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
              Path("/Library/Fonts/Arial Unicode.ttf")]


def _hash(value) -> str:
    if isinstance(value, Path):
        h = hashlib.sha256()
        with value.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(args, **kw):
    try:
        return subprocess.run([str(x) for x in args], check=True, capture_output=True,
                              text=True, **kw)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"运行失败：{args[0]}\n{(e.stderr or e.stdout or '')[-2500:]}") from e


def _probe(path: Path):
    return json.loads(_run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                            "-of", "json", path]).stdout)


@lru_cache(maxsize=100)
def _font(size: int, index: int = 0):
    paths = [p for p in FONT_PATHS if p.exists()]
    if not paths:
        raise RuntimeError("没有找到支持中文的字体，请安装或配置 STHeiti / Arial Unicode。")
    return ImageFont.truetype(str(paths[min(index, len(paths)-1)]), size)


@lru_cache(maxsize=8192)
def _font_index(char: str):
    if char.isspace():
        return 0
    paths = [p for p in FONT_PATHS if p.exists()]
    for i in range(len(paths)):
        f = _font(40, i)
        m, bad = f.getmask(char), f.getmask("\u0378")
        if (m.size, bytes(m)) != (bad.size, bytes(bad)):
            return i
    raise ValueError(f"字体不支持字符 {char!r}（U+{ord(char):04X}）；请替换该字符后重试。")


@lru_cache(maxsize=32768)
def _advance(char: str, size: int):
    return _font(size, _font_index(char)).getlength(char)


def _width(text: str, size: int):
    return sum(_advance(c, size) for c in text)


def _draw_text(draw, xy, value, size, fill, center=False):
    x, y = xy
    if center:
        x -= _width(value, size) / 2
    for c in value:
        draw.text((round(x), round(y)), c, font=_font(size, _font_index(c)), fill=fill)
        x += _advance(c, size)


def _wrap(text: str, width: float, size: int):
    """Measured wrapping, retaining every non-newline character."""
    out = []
    for para in text.replace("\t", "    ").split("\n"):
        if not para:
            out.append("")
            continue
        line = ""
        for c in para:
            if line and _width(line+c, size) > width:
                out.append(line)
                line = c
            else:
                line += c
        out.append(line)
    return out or [""]


def _fit(text, box, maximum=56, minimum=26, label="文字"):
    _, _, width, height = box
    for size in range(maximum, minimum-1, -2):
        lines = _wrap(text, width, size)
        line_height = round(size * 1.36)
        if len(lines)*line_height <= height and all(_width(s, size) <= width+1 for s in lines):
            return lines, size, line_height
    raise ValueError(f"{label}过长，无法完整放入画面；请拆成更多场景或减少该项文字。")


def _block(draw, text, box, fill, maximum=56, minimum=26, center=False, label="文字"):
    x, y, _, _ = box
    lines, size, lh = _fit(text, box, maximum, minimum, label)
    for i, line in enumerate(lines):
        _draw_text(draw, (x + (box[2]/2 if center else 0), y+i*lh), line, size, fill, center)
    return size, len(lines)*lh


def _phrases(narration: str):
    """Natural sentence/phrase chunks; captions derive from each chunk's actual audio."""
    text = re.sub(r"\s+", " ", narration).strip()
    if not text:
        raise ValueError("场景旁白为空。")
    sentences = re.findall(r"[^。！？!?；;]+[。！？!?；;]*", text)
    chunks = []
    for sentence in sentences:
        parts = [sentence]
        if len(sentence) > 42:
            parts = re.findall(r"[^，,：:]+[，,：:]*", sentence)
        for part in parts:
            while len(part) > 50:
                # Prefer a space for long English phrases; never drop words or symbols.
                split = part.rfind(" ", 15, 43)
                split = split+1 if split >= 15 else 40
                chunks.append(part[:split]); part = part[split:]
            if part:
                if chunks and len(part) < 8 and len(chunks[-1]+part) <= 46:
                    chunks[-1] += part
                else:
                    chunks.append(part)
    if "".join(chunks) != text:
        raise ValueError("旁白分段校验失败：有文字未被完整保留。")
    return chunks


def _wav_info(path):
    with wave.open(str(path), "rb") as f:
        return f.getnframes(), f.getframerate(), f.getnchannels(), f.getsampwidth()


def _speech(phrase, voice, rate, cache, code_hash):
    key = _hash(dict(text=phrase, voice=voice, rate=rate, engine="macOS say",
                     renderer=RENDERER_VERSION, code=code_hash))
    folder = cache / key
    folder.mkdir(parents=True, exist_ok=True)
    wav, meta = folder / "speech.wav", folder / "speech.json"
    if wav.exists() and meta.exists():
        info = json.loads(meta.read_text())
        if info.get("sha256") == _hash(wav) and _wav_info(wav)[1:] == (SR, 1, 2):
            return wav, _wav_info(wav)[0]
    source, aiff = folder / "phrase.txt", folder / "speech.aiff"
    source.write_text(phrase, encoding="utf-8")
    print(f"  正在配音：{phrase[:28]}", flush=True)
    _run(["say", "-v", voice, "-r", str(rate), "-f", source, "-o", aiff])
    _run(["ffmpeg", "-v", "error", "-y", "-i", aiff, "-ar", str(SR), "-ac", "1",
          "-c:a", "pcm_s16le", wav])
    frames = _wav_info(wav)[0]
    if frames < SR * .08:
        raise RuntimeError(f"配音没有生成有效声音：{phrase}")
    _json(meta, dict(text=phrase, voice=voice, rate=rate, sha256=_hash(wav),
                     frames=frames, sample_rate=SR))
    return wav, frames


def _scene_audio(scene, index, settings, cache, scene_dir, code_hash):
    if scene["kind"] == "image" and not scene["narration"].strip():
        # Pure-image scenes are deliberately silent three-second holds.
        n_video = round(3 * settings["fps"])
        path = scene_dir / f"{index+1:03d}_narration.wav"
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(SR)
            out.writeframes(b"\0\0" * round(n_video/settings["fps"]*SR))
        return path, [], n_video
    parts = []
    cues = []
    frames = round(.32*SR)
    parts.append(b"\0\0"*frames)
    phrases = _phrases(scene["narration"])
    for phrase in phrases:
        wav, n = _speech(phrase, settings["voice"], settings["voice_rate"], cache, code_hash)
        with wave.open(str(wav), "rb") as f:
            pcm = f.readframes(f.getnframes())
        cues.append(dict(start=frames/SR, end=(frames+n)/SR, text=phrase,
                         audio=str(wav), audio_sha256=_hash(wav)))
        parts.append(pcm); frames += n
        gap = round((.13 if phrase[-1] in "，,：:" else .20)*SR)
        parts.append(b"\0\0"*gap); frames += gap
    tail = round(.45*SR)
    parts.append(b"\0\0"*tail); frames += tail
    n_video = math.ceil(frames/SR*settings["fps"])
    desired = round(n_video/settings["fps"]*SR)
    if desired > frames:
        parts.append(b"\0\0"*(desired-frames)); frames = desired
    path = scene_dir / f"{index+1:03d}_narration.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(SR)
        for data in parts:
            out.writeframesraw(data)
    return path, cues, n_video


def _layout(scene, index, count, settings):
    paper, ink, accent = (settings[k] for k in ("paper", "ink", "accent"))
    base = Image.new("RGB", (CW, CH), paper)
    d = ImageDraw.Draw(base)
    _draw_text(d, (92, 88), "PAPER / STORIES", 30, ink)
    text = f"{index+1:02d} / {count:02d}"
    _draw_text(d, (988-_width(text, 30), 88), text, 30, accent)
    d.line((92, 148, 988, 148), fill=ink, width=2)
    kind_labels = dict(text="文字讲述", steps="步骤与流程", compare="对比说明", image="图像与讲述")
    _draw_text(d, (92, 193), kind_labels[scene["kind"]], 27, accent)
    title_box = (84, 268, 912, 292)
    _fit(scene["title"], title_box, 88, 36, f"场景 {index+1} 标题")
    stage = (92, 622, 896, 778)
    d.rounded_rectangle((stage[0], stage[1], stage[0]+stage[2], stage[1]+stage[3]),
                        radius=8, fill="#FAF9F5", outline="#DAD6CF", width=2)
    items = scene.get("items") or []
    boxes = []
    if scene["kind"] == "image":
        path = Path(scene["image"])
        if not path.is_file():
            raise FileNotFoundError(f"场景 {index+1} 图片不存在：{path}")
        with Image.open(path) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGBA")
            image.thumbnail((800, 650), Image.Resampling.LANCZOS)
            x, y = (CW-image.width)//2, 675+(650-image.height)//2
            base.paste(image, (x,y), image)
    elif scene["kind"] == "compare":
        if not items:
            items = [scene["narration"]]
        mid = math.ceil(len(items)/2)
        columns = [items[:mid], items[mid:]]
        for j, col in enumerate(columns):
            box=(128+j*445, 682, 375, 645)
            text="\n\n".join(col)
            if text:
                _fit(text, box, 46, 26, f"场景 {index+1} 对比栏 {j+1}")
            boxes.append((text,box))
        d.line((540,682,540,1327), fill="#DAD6CF", width=2)
    elif scene["kind"] == "steps":
        if not items:
            items=[scene["narration"]]
        row_h=650/max(1,len(items))
        for j,item in enumerate(items):
            box=(226, 674+j*row_h, 678, row_h-20)
            _fit(item,box,45,25,f"场景 {index+1} 步骤 {j+1}")
            boxes.append((item,box))
    else:
        text="\n\n".join(items) if items else scene["narration"]
        box=(145,680,790,652)
        _fit(text,box,54,28,f"场景 {index+1} 正文")
        boxes.append((text,box))
    _draw_text(d, (92, 1810), "文案 / 声音 / 画面", 25, "#77736E")
    d.line((92,1777,988,1777),fill=ink,width=2)
    return dict(base=base, boxes=boxes, title_box=title_box, stage=stage)


def _ease(x):
    x=max(0,min(1,x))
    return 1-(1-x)**3


def _frame(scene, layout, local, settings):
    im=layout["base"].copy()
    ink,accent=settings["ink"],settings["accent"]
    # The scene title enters as actual staggered paper strips for 0.3 seconds.
    title=Image.new("RGBA",(CW,CH))
    _block(ImageDraw.Draw(title),scene["title"],layout["title_box"],ink,88,36,label="标题")
    y0=int(layout["title_box"][1]); y1=y0+int(layout["title_box"][3])
    for j,yy in enumerate(range(y0,y1,36)):
        t=_ease((local-j*.015)/.22)
        shift=round((1-t)*(-110 if j%2 else 110))
        strip=title.crop((0,yy,CW,min(yy+36,y1)))
        if t<1:strip.putalpha(strip.getchannel("A").point(lambda a:round(a*t)))
        im.paste(strip,(shift,yy),strip)
    d=ImageDraw.Draw(im)
    # A small finite slide for scene content; semantics stay visible after entry.
    for j,(text,box) in enumerate(layout["boxes"]):
        if not text:continue
        dt=_ease((local-.18-j*.07)/.28)
        active_box=(box[0],box[1]+round(18*(1-dt)),box[2],box[3])
        if scene["kind"]=="steps":
            _draw_text(d,(145,active_box[1]),f"{j+1:02d}",36,accent)
            _block(d,text,active_box,ink,45,25,label="步骤")
        elif scene["kind"]=="compare":
            _block(d,text,active_box,ink,46,26,label="对比文字")
        else:
            _block(d,text,active_box,ink,54,28,label="正文")
    for cue in scene["captions"]:
        if cue["start"] <= local < cue["end"]:
            _block(d,cue["text"],(108,1545,864,170),ink,44,28,center=True,label="字幕")
            break
    x=92+896*min(1,max(0,local/scene["duration"]))
    d.rectangle((92,1766,x,1771),fill=accent)
    w,h=settings["width"],settings["height"]
    if (w,h)!=(CW,CH):
        fitted=ImageOps.contain(im,(w,h),Image.Resampling.LANCZOS)
        target=Image.new("RGB",(w,h),settings["paper"])
        target.paste(fitted,((w-fitted.width)//2,(h-fitted.height)//2))
        return target
    return im


def _srt_time(t):
    ms=round(t*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _settings(plan):
    cfg=dict(width=CW,height=CH,fps=30,voice="Tingting",voice_rate=240,
             paper="#EEECE7",ink="#181716",accent="#AC1210")
    cfg.update(plan.get("settings",{}))
    for key in ("width","height","fps","voice_rate"):
        cfg[key]=int(cfg[key])
    if cfg["width"]<240 or cfg["height"]<240 or cfg["width"]%2 or cfg["height"]%2:
        raise ValueError("视频宽高须为不小于240的偶数。")
    if not 1<=cfg["fps"]<=120 or not 40<=cfg["voice_rate"]<=600:
        raise ValueError("帧率或配音语速超出支持范围。")
    for key in ("paper","ink","accent"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}",cfg[key]):
            raise ValueError(f"{key} 颜色须使用 #RRGGBB 格式。")
    return cfg


def render_video(plan: dict, job_dir: Path, *, preview=False) -> dict:
    """Create local video and editable artifacts, preserving completed older renders."""
    for command in ("say","ffmpeg","ffprobe"):
        if not shutil.which(command):
            raise RuntimeError(f"缺少运行组件：{command}")
    if not isinstance(plan.get("scenes"),list) or not plan["scenes"]:
        raise ValueError("计划中没有可制作的场景。")
    settings=_settings(plan)
    code_hash=_hash(Path(__file__))
    image_hashes={}
    for i,scene in enumerate(plan["scenes"]):
        if scene.get("kind") not in {"text","steps","compare","image"}:
            raise ValueError(f"场景 {i+1} 类型不受支持：{scene.get('kind')}")
        if not str(scene.get("narration","")).strip() and scene["kind"] != "image":
            raise ValueError(f"场景 {i+1} 没有旁白。")
        for text in [scene.get("title", ""),scene["narration"],*scene.get("items",[])]:
            for c in text:
                if not c.isspace():_font_index(c)
        if scene["kind"]=="image":
            image=Path(scene.get("image") or "")
            if not image.is_file():raise FileNotFoundError(f"场景 {i+1} 图片不存在：{image}")
            image_hashes[str(image.resolve())]=_hash(image)
    signature=_hash(dict(plan=plan,settings=settings,renderer=RENDERER_VERSION,
                         code=code_hash,images=image_hashes))
    job_dir=Path(job_dir).expanduser().resolve()
    job_dir.mkdir(parents=True,exist_ok=True)
    request=job_dir/"render_request.json"
    if request.exists() and json.loads(request.read_text()).get("signature") != signature:
        job_dir=job_dir/"renders"/signature[:16]
        job_dir.mkdir(parents=True,exist_ok=True)
        request=job_dir/"render_request.json"
    elif not request.exists() and any((job_dir/x).exists() for x in ("video.mp4","storyboard.json","cover.jpg")):
        job_dir=job_dir/"renders"/signature[:16]
        job_dir.mkdir(parents=True,exist_ok=True)
        request=job_dir/"render_request.json"
    paths={key:job_dir/name for key,name in dict(video="video.mp4",storyboard="storyboard.json",
           srt="subtitles.srt",cover="cover.jpg",contact_sheet="contact_sheet.jpg",qa="qa.json").items()}
    manifest=job_dir/"render_manifest.json"
    if manifest.exists():
        old=json.loads(manifest.read_text())
        if old.get("signature")==signature and all(Path(p).is_file() and _hash(Path(p))==h
               for p,h in old.get("artifact_sha256",{}).items()) and old.get("artifact_sha256"):
            if not preview and paths["video"].exists():return paths
            if preview and paths["cover"].exists():return dict(paths,video=None)
    _json(request,dict(signature=signature,renderer=RENDERER_VERSION,code_sha256=code_hash,
                       settings=settings,image_sha256=image_hashes))
    scene_dir=job_dir/"scenes"; scene_dir.mkdir(exist_ok=True)
    cache=job_dir/"audio_cache";cache.mkdir(exist_ok=True)
    board=copy.deepcopy(plan);board["settings"]=settings
    board["renderer"]=dict(version=RENDERER_VERSION,signature=signature,source_sha256=code_hash)
    scenes=board["scenes"]; layouts=[];all_cues=[];elapsed=0
    # Layout before TTS catches oversized stage content without wasting a render.
    for i,scene in enumerate(scenes):
        scene.setdefault("title",plan.get("title") or f"第 {i+1} 节")
        layouts.append(_layout(scene,i,len(scenes),settings))
    for i,scene in enumerate(scenes):
        print(f"正在制作第 {i+1}/{len(scenes)} 场：{scene['title']}",flush=True)
        wav,cues,frames=_scene_audio(scene,i,settings,cache,scene_dir,code_hash)
        scene.update(audio=str(wav),captions=cues,frames=frames,start=elapsed,
                     duration=frames/settings["fps"])
        for cue in cues:
            _fit(cue["text"],(108,1545,864,170),44,28,f"场景 {i+1} 字幕")
            all_cues.append(dict(start=elapsed+cue["start"],end=elapsed+cue["end"],text=cue["text"]))
        elapsed+=scene["duration"]
    board["duration"]=elapsed
    _json(paths["storyboard"],board)
    (job_dir/"narration.txt").write_text("\n\n".join(s["narration"] for s in scenes),encoding="utf-8")
    paths["srt"].write_text("\n\n".join(f"{i+1}\n{_srt_time(c['start'])} --> {_srt_time(c['end'])}\n{c['text']}"
                                          for i,c in enumerate(all_cues))+"\n",encoding="utf-8")
    thumbs=[]
    for i,(scene,layout) in enumerate(zip(scenes,layouts)):
        im=_frame(scene,layout,min(scene["duration"]*.45,2.0),settings)
        if i==0:im.save(paths["cover"],quality=94)
        im.save(scene_dir/f"{i+1:03d}_preview.jpg",quality=92)
        thumbs.append(ImageOps.contain(im,(270,480),Image.Resampling.LANCZOS))
    cols=min(5,len(thumbs));rows=math.ceil(len(thumbs)/cols)
    sheet=Image.new("RGB",(270*cols,480*rows),settings["paper"])
    for i,im in enumerate(thumbs):sheet.paste(im,((i%cols)*270,(i//cols)*480))
    sheet.save(paths["contact_sheet"],quality=92)
    qa=dict(renderer=RENDERER_VERSION,signature=signature,width=settings["width"],height=settings["height"],
            fps=settings["fps"],planned_duration=elapsed,scene_count=len(scenes),subtitle_count=len(all_cues),
            text_layout="measured; no silent truncation",subtitles="per-phrase measured TTS boundaries",
            images="contain; source aspect ratio preserved",narration_complete=True,
            caption_bounds_pass=all(0<=c["start"]<c["end"]<=elapsed for c in all_cues),preview_only=bool(preview))
    if preview:
        _json(paths["qa"],qa)
        return dict(paths,video=None)
    rendered=[]
    for i,(scene,layout) in enumerate(zip(scenes,layouts)):
        dst=scene_dir/f"{i+1:03d}.mp4"
        segment_key=_hash(dict(signature=signature,scene=scene))
        state=dst.with_suffix(".json")
        reused=False
        if dst.exists() and state.exists():
            info=json.loads(state.read_text())
            reused=info.get("key")==segment_key and info.get("sha256")==_hash(dst)
        if not reused:
            tmp=dst.with_suffix(".partial.mp4")
            cmd=["ffmpeg","-v","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",
                 f"{settings['width']}x{settings['height']}","-r",str(settings["fps"]),"-i","pipe:0",
                 "-an","-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p",
                 "-movflags","+faststart",str(tmp)]
            print(f"正在渲染第 {i+1}/{len(scenes)} 场，{scene['duration']:.1f} 秒",flush=True)
            with (scene_dir/f"{i+1:03d}_render.log").open("w") as log:
                proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=log,stderr=log)
                try:
                    for f in range(scene["frames"]):
                        proc.stdin.write(_frame(scene,layout,f/settings["fps"],settings).tobytes())
                    proc.stdin.close()
                except BaseException:
                    proc.terminate();proc.wait();raise
                if proc.wait()!=0:
                    raise RuntimeError(f"场景 {i+1} 视频导出失败，详见 {log.name}")
            tmp.replace(dst)
            _json(state,dict(key=segment_key,sha256=_hash(dst)))
        rendered.append(dst)
    # Concatenating raw PCM here avoids per-segment AAC padding or subtitle drift.
    full_audio=job_dir/"narration.wav"
    with wave.open(str(full_audio),"wb") as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(SR)
        for scene in scenes:
            with wave.open(scene["audio"],"rb") as inp:out.writeframesraw(inp.readframes(inp.getnframes()))
    listing=scene_dir/"segments.txt"
    # Paths are controlled renderer-created numeric names, so apostrophes in job paths are harmless.
    listing.write_text("\n".join(f"file '{p.name}'" for p in rendered)+"\n",encoding="utf-8")
    tmp=job_dir/"video.partial.mp4"
    _run(["ffmpeg","-v","error","-y","-f","concat","-safe","0","-i",listing,
          "-i",full_audio,"-map","0:v:0","-map","1:a:0","-c:v","copy","-af",
          "loudnorm=I=-16:TP=-1.5:LRA=11","-c:a","aac","-b:a","192k","-ar",str(SR),
          "-ac","2","-t",f"{elapsed:.9f}","-movflags","+faststart",tmp])
    # Complete decode, rather than metadata alone, verifies the deliverable.
    _run(["ffmpeg","-v","error","-i",tmp,"-f","null","-"])
    data=_probe(tmp);actual=float(data["format"]["duration"])
    if abs(actual-elapsed)>max(.12,2/settings["fps"]):
        raise RuntimeError(f"视频时长异常：预期 {elapsed:.3f} 秒，实际 {actual:.3f} 秒。")
    volume=_run(["ffmpeg","-hide_banner","-i",tmp,"-vn","-af","volumedetect","-f","null","-"]).stderr
    peak=re.search(r"max_volume: ([\-\d.]+) dB",volume)
    peak_db=float(peak.group(1)) if peak else None
    if peak_db is not None and peak_db>=0:
        raise RuntimeError("导出音频峰值达到0 dBFS，请检查输入音频。")
    if paths["video"].exists() and _hash(paths["video"])!=_hash(tmp):
        # A completed output should only be reused through its hash-checked manifest.
        raise FileExistsError(f"已有不同成片，未覆盖：{paths['video']}；请使用新的作业目录。")
    tmp.replace(paths["video"])
    qa.update(actual_duration=actual,duration_check="passed",decode_check="passed full decode",
              peak_dbfs=peak_db,audio_no_clipping=peak_db is not None and peak_db<0,
              video_sha256=_hash(paths["video"]),preview_only=False,
              streams=[{k:s.get(k) for k in ("codec_type","codec_name","width","height","pix_fmt",
                       "avg_frame_rate","sample_rate","channels")} for s in data["streams"]])
    _json(paths["qa"],qa)
    _json(manifest,dict(signature=signature,artifact_sha256={str(p):_hash(p) for p in paths.values()}))
    print(f"视频已保存：{paths['video']}",flush=True)
    return paths
