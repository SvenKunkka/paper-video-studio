#!/usr/bin/env python3
"""Choose a text file, or run `video.py make 文案.md`, to produce a local video."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
os.environ['PATH'] = '/opt/homebrew/bin:/usr/local/bin:' + os.environ.get('PATH', '')


def read_plan(path: Path) -> dict:
    from script_video.planner import validate_plan
    plan = json.loads(path.read_text(encoding='utf-8-sig'))
    validate_plan(plan)
    return plan


def prepare_job(plan: dict, base: Path | None = None) -> tuple[dict, Path]:
    # Hash image bytes and renderer source, so replacing a file at the same path
    # or changing the implementation cannot silently reuse a previous production.
    value = json.loads(json.dumps(plan, ensure_ascii=False))
    image_hashes = {}
    for scene in value['scenes']:
        if scene.get('image'):
            src = Path(scene['image']).resolve(strict=True)
            image_hashes[str(src)] = hashlib.sha256(src.read_bytes()).hexdigest()
    renderer_hash = hashlib.sha256(b''.join(
        p.name.encode() + p.read_bytes()
        for p in sorted((ROOT / 'script_video').glob('*.py'))
        if p.name not in ('launcher.py',)
    )).hexdigest()
    payload = json.dumps({'plan': value, 'images': image_hashes, 'renderer': renderer_hash},
                         sort_keys=True, ensure_ascii=False).encode()
    digest = hashlib.sha256(payload).hexdigest()
    slug = re.sub(r'[^\w\-]+', '-', value['title'], flags=re.UNICODE).strip('-_')[:36] or 'video'
    job = (base or ROOT / 'video_jobs').resolve() / f'{slug}-{digest[:12]}'
    job.mkdir(parents=True, exist_ok=True)
    (job / 'assets').mkdir(exist_ok=True)
    for scene in value['scenes']:
        if scene.get('image'):
            src = Path(scene['image']).resolve()
            dst = job / 'assets' / f'{image_hashes[str(src)][:16]}{src.suffix.lower()}'
            if not dst.exists():
                shutil.copy2(src, dst)
            scene['image'] = str(dst)
    (job / 'source.txt').write_text(value['source']['text'], encoding='utf-8')
    source_path = Path(value['source']['path'])
    if source_path.is_file():
        target = job / ('input' + source_path.suffix.lower())
        if not target.exists():
            shutil.copy2(source_path, target)
    (job / 'plan.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (job / 'job.json').write_text(json.dumps({'fingerprint': digest, 'renderer_sha256': renderer_hash,
                                          'image_sha256': image_hashes}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return value, job


def make_video(source: Path | None = None, *, plan_path: Path | None = None,
               title: str | None = None, voice: str = 'Tingting', rate: int = 240,
               preview: bool = False, output_base: Path | None = None) -> dict:
    from script_video.planner import make_plan
    from script_video.renderer import render_video
    plan = read_plan(plan_path) if plan_path else make_plan(source, title=title, voice=voice, voice_rate=rate)
    frozen, job = prepare_job(plan, output_base)
    print(f'制作目录：{job}', flush=True)
    print(f'文案已分成 {len(frozen["scenes"])} 个画面。', flush=True)
    try:
        result = render_video(frozen, job, preview=preview)
    except Exception as exc:
        (job / 'error.txt').write_text(f'{type(exc).__name__}: {exc}\n', encoding='utf-8')
        raise
    serialized = {k: str(v) if isinstance(v, Path) else v for k, v in result.items()}
    serialized['job_dir'] = str(job)
    (job / ('preview-result.json' if preview else 'result.json')).write_text(
        json.dumps(serialized, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('预览已完成。' if preview else '视频已完成。', flush=True)
    for key in ('video', 'srt', 'storyboard', 'cover', 'contact_sheet'):
        if result.get(key):
            print(f'{key}: {result[key]}', flush=True)
    return serialized


def main() -> int:
    parser = argparse.ArgumentParser(description='选择本地文案，自动制作配音、字幕与动画视频。')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('make', 'plan'):
        p = sub.add_parser(command, help='根据文案生成视频' if command == 'make' else '只生成可编辑分镜')
        p.add_argument('source', type=Path)
        p.add_argument('--title')
        p.add_argument('--voice', default='Tingting')
        p.add_argument('--rate', type=int, default=240)
        p.add_argument('--output-base', type=Path)
        if command == 'make':
            p.add_argument('--preview', action='store_true')
        else:
            p.add_argument('--out', type=Path)
    p = sub.add_parser('render', help='使用已编辑的分镜制作视频')
    p.add_argument('plan', type=Path)
    p.add_argument('--preview', action='store_true')
    p.add_argument('--output-base', type=Path)
    p = sub.add_parser('gui', help='打开本地文案文件选择器')
    p.add_argument('--source', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.command == 'gui':
            from script_video.launcher import launch
            return launch(args.source)
        if args.command == 'make':
            make_video(args.source, title=args.title, voice=args.voice, rate=args.rate,
                       preview=args.preview, output_base=args.output_base)
        elif args.command == 'render':
            make_video(plan_path=args.plan, preview=args.preview, output_base=args.output_base)
        else:
            from script_video.planner import make_plan
            plan = make_plan(args.source, title=args.title, voice=args.voice, voice_rate=args.rate)
            value, job = prepare_job(plan, args.output_base)
            if args.out:
                target = args.out.resolve()
                if target.exists():
                    raise ValueError(f'分镜文件已经存在，请使用新的文件名：{target}')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(f'分镜已保存：{args.out or job / "plan.json"}')
        return 0
    except Exception as exc:
        print(f'制作未完成：{exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
