"""Shred kit: one entry point for people and agents.

    python kit.py doctor                      check Python packages, ffmpeg, Blender and the GPU
    python kit.py fields                      every field you can change, its current value and its limits
    python kit.py set text.headline "Ship"    change one field in brief.json (dotted path; JSON values allowed)
    python kit.py validate                    check brief.json: lengths, colours, contrast, fonts, picture
    python kit.py poster                      draw the poster (seconds) -> build/preview/poster.png
    python kit.py stills                      four 3D frames at low quality (minutes) -> build/preview/stills.jpg
    python kit.py estimate [--quality final]  time one frame of every shot and project the full render
    python kit.py render [--quality draft] [--social]    render, edit, sound -> out/

Qualities: preview (fast, rough), draft (half resolution, light motion blur), final (full 1080x1920, full blur).
"""
import os, sys, json, time, shutil, subprocess, glob, re, platform

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import brief as B

SHOTS = [('H', 30), ('A', 112), ('FO', 123), ('C', 216)]
QUALITY = {
    #           scale %, samples, sub-frames (motion blur), samples for the shredder shot
    'preview': dict(scale=34, spp=8, subs=1, spp_fo=8),
    'draft': dict(scale=50, spp=16, subs=3, spp_fo=24),
    'final': dict(scale=100, spp=20, subs=5, spp_fo=48),
}
PY = sys.executable
_print = print


def print(*a, **k):
    k.setdefault('flush', True)
    _print(*a, **k)


# ---------------------------------------------------------------- helpers
def blender_path():
    cands = [os.environ.get('BLENDER'), shutil.which('blender')]
    sysname = platform.system()
    if sysname == 'Windows':
        cands += sorted(glob.glob(r'C:\Program Files\Blender Foundation\Blender *\blender.exe'), reverse=True)
    elif sysname == 'Darwin':
        cands += ['/Applications/Blender.app/Contents/MacOS/Blender']
    else:
        cands += ['/snap/bin/blender', '/usr/bin/blender', '/usr/local/bin/blender'] + \
                 sorted(glob.glob(os.path.expanduser('~/blender*/blender')), reverse=True)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def need_blender():
    b = blender_path()
    if not b:
        raise SystemExit('Blender not found. Install Blender 5.x from blender.org, or set BLENDER to its executable.')
    return b


def run_shot(shot, out, scale, spp, subs, frames='all', on_line=None):
    cmd = [need_blender(), '-b', '-P', os.path.join(ROOT, 'scripts', 'shred.py'), '--',
           '--shot', shot, '--out', out, '--scale', str(scale), '--samples', str(spp), '--subs', str(subs),
           '--frames', frames]
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding='utf-8', errors='replace')
    tail = []
    for line in p.stdout:
        tail = (tail + [line.rstrip()])[-40:]
        if on_line:
            on_line(line.rstrip())
    if p.wait() != 0 or any('Traceback' in t or t.startswith('Error') for t in tail):
        print('\n'.join(tail))
        raise SystemExit(f'Blender failed on shot {shot}')


def fmt(sec):
    sec = int(sec)
    return f'{sec // 3600}h {sec % 3600 // 60:02d}m' if sec >= 3600 else f'{sec // 60}m {sec % 60:02d}s'


def poster():
    subprocess.run([PY, os.path.join(ROOT, 'scripts', 'poster.py')], check=True, cwd=ROOT)


def get_path(d, path):
    for k in path.split('.'):
        d = d[k]
    return d


# ---------------------------------------------------------------- commands
def cmd_doctor(_):
    ok = True

    def row(name, good, info, fix=''):
        nonlocal ok
        ok &= good
        print(f"{'OK     ' if good else 'MISSING'}  {name:16s} {info}" + (f'\n         fix: {fix}' if not good and fix else ''))

    row('python', sys.version_info >= (3, 10), platform.python_version(), 'install Python 3.10+ from python.org')
    missing = []
    for mod in ('numpy', 'cv2', 'PIL', 'scipy', 'soundfile', 'pedalboard', 'pyloudnorm'):
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    row('python packages', not missing, 'all installed' if not missing else 'missing: ' + ', '.join(missing),
        f'{PY} -m pip install -r requirements.txt')
    ff = shutil.which('ffmpeg')
    row('ffmpeg', bool(ff), ff or 'not on PATH',
        {'Windows': 'winget install Gyan.FFmpeg', 'Darwin': 'brew install ffmpeg'}.get(platform.system(), 'sudo apt install ffmpeg'))
    b = blender_path()
    ver = ''
    if b:
        try:
            ver = subprocess.run([b, '-b', '--version'], capture_output=True, text=True, timeout=120).stdout.splitlines()[0]
        except Exception as e:
            ver = f'found but did not start: {e}'
    row('blender', bool(b) and ver.startswith('Blender'), f'{ver} ({b})' if b else 'not found',
        'install Blender 5.x from blender.org (or set BLENDER to its executable)')
    if b and ver.startswith('Blender'):
        m = re.match(r'Blender (\d+)\.(\d+)', ver)
        if m and int(m.group(1)) < 5:
            print('WARN     blender version   the kit is tested with Blender 5.2; 4.x may fail. Prefer 5.x.')
        expr = ("import bpy\np=bpy.context.preferences.addons['cycles'].preferences\nfound=[]\n"
                "for k in ('OPTIX','CUDA','HIP','METAL','ONEAPI'):\n"
                "  try:\n    p.compute_device_type=k\n  except TypeError:\n    continue\n"
                "  p.get_devices()\n  found += [k+': '+d.name for d in p.devices if d.type==k]\n"
                "print('GPUS', ' | '.join(found) if found else 'none')")
        out = subprocess.run([b, '-b', '--python-expr', expr], capture_output=True, text=True, timeout=180).stdout
        g = next((l[5:] for l in out.splitlines() if l.startswith('GPUS ')), 'unknown')
        row('gpu', g not in ('none', 'unknown'), g if g != 'none' else 'no GPU backend: renders run on the CPU (much slower)',
            'it still works on CPU; use quality preview/draft, or run on a machine with an NVIDIA/AMD/Apple GPU')
    free = shutil.disk_usage(ROOT).free / 2 ** 30
    row('disk', free > 4, f'{free:.0f} GB free (a final render needs about 1.5 GB)', 'free some space')
    print('\nready' if ok else '\nnot ready: fix the MISSING rows, then run doctor again')


def cmd_fields(_):
    br = B.load()
    print('TEXT (characters: recommended range / hard max)')
    for key, lo, hi, mx, what in B.TEXT_FIELDS:
        v = br['text'][key]
        shown = v if len(v) < 60 else v[:57] + '...'
        print(f'  text.{key:10s} {lo}-{hi} / {mx:<5d} now {len(v):4d}: "{shown}"\n               {what}')
    print('FONTS (any Google Fonts family, or a path to a .ttf/.otf)')
    for k in ('display', 'text'):
        f = br['fonts'][k]
        print(f'  fonts.{k}.family / .weight   now "{f["family"]}" {f.get("weight")}')
    print('COLOURS (hex)')
    for k in ('paper', 'ink', 'accent'):
        print(f'  colors.{k:8s} now {br["colors"][k]}')
    print(f'  colors.accent_band  now {br["colors"]["accent_band"]}  (false: no band, a mono poster)')
    print('PICTURE')
    print(f'  image.path  now {br["image"]["path"]}\n  image.mode  now {br["image"]["mode"]}  (object: a thing on a plain '
          'backdrop; photo: a full-frame photo)')
    print(f'OTHER\n  sound        now {br["sound"]}\n  output_name  now {br["output_name"]}')


def cmd_set(a):
    path, raw = a[0], ' '.join(a[1:])
    try:
        val = json.loads(raw)
    except ValueError:
        val = raw
    user = json.load(open(B.BRIEF, encoding='utf-8')) if os.path.exists(B.BRIEF) else {}
    d = user
    keys = path.split('.')
    get_path(B.DEFAULTS, path)                  # raises KeyError on an unknown field
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = val
    json.dump(user, open(B.BRIEF, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'{path} = {json.dumps(val, ensure_ascii=False)}')


def cmd_validate(_):
    br = B.load()
    errors, warns = [], []
    t = br['text']
    for key, lo, hi, mx, _w in B.TEXT_FIELDS:
        n = len(t[key])
        if n > mx:
            errors.append(f'text.{key} is {n} characters; the maximum is {mx}')
        elif n < lo or n > hi:
            warns.append(f'text.{key} is {n} characters; {lo}-{hi} reads best')
    for key in ('headline', 'footer'):
        if set(t[key]) & B.DESCENDERS:
            warns.append(f'text.{key} "{t[key]}" has letters that hang below the line (g j p q y): they will overlap '
                         'the line below. Capitals or words without them look cleaner.')
    for key in ('headline', 'subline', 'footer', 'fragment'):
        if not t[key].strip():
            errors.append(f'text.{key} is empty')
    c = br['colors']
    try:
        for k in ('paper', 'ink', 'accent'):
            B.hex_rgb(c[k])
    except Exception:
        errors.append('colours must be hex like #EEECE7')
    else:
        cr = B.contrast(c['paper'], c['ink'])
        if cr < 4.5:
            errors.append(f'ink on paper contrast is {cr:.1f}:1; it needs at least 4.5:1 to survive the shredder')
        if c.get('accent_band'):
            ca = B.contrast(c['accent'], c['ink'])
            if ca < 2.0:
                warns.append(f'the headline sits in ink on the accent band: contrast {ca:.1f}:1 is low (2:1 or more)')
            d = sum((x - y) ** 2 for x, y in zip(B.hex_rgb(c['accent']), B.hex_rgb(c['paper']))) ** 0.5
            if d < 60:
                warns.append('the accent is almost the paper colour: the band will not read')
    ip = br['image']['path']
    ip = ip if os.path.isabs(ip) else os.path.join(ROOT, ip)
    if not os.path.exists(ip):
        errors.append(f'image not found: {ip}')
    if br['image'].get('mode') not in B.IMAGE_MODES:
        errors.append(f'image.mode must be one of {B.IMAGE_MODES}')
    import fonts
    for k in ('display', 'text'):
        try:
            fonts.get(br['fonts'][k]['family'], br['fonts'][k].get('weight', 400))
        except SystemExit as e:
            errors.append(f'fonts.{k}: {e}')
    for w in warns:
        print('WARN ', w)
    for e in errors:
        print('ERROR', e)
    print('valid' if not errors else 'invalid')
    return not errors


def cmd_poster(_):
    if not cmd_validate(None):
        raise SystemExit(1)
    poster()


def cmd_stills(_):
    if not cmd_validate(None):
        raise SystemExit(1)
    poster()
    import cv2, numpy as np
    out = os.path.join(ROOT, 'build', 'renders', 'stills')
    picks = [('C', 215), ('A', 40), ('FO', 60), ('C', 100)]
    t0 = time.time()
    for shot, f in picks:
        print(f'rendering still {shot} {f} ...', flush=True)
        run_shot(shot, out, 34, 12, 1, str(f))
    ims = []
    for shot, f in picks:
        im = cv2.imread(os.path.join(out, f'{shot}_{f:04d}.jpg'))
        ims.append(cv2.resize(im, (360, 640), interpolation=cv2.INTER_AREA))
    os.makedirs(os.path.join(ROOT, 'build', 'preview'), exist_ok=True)
    dst = os.path.join(ROOT, 'build', 'preview', 'stills.jpg')
    cv2.imwrite(dst, np.hstack(ims))
    print(f'stills done in {fmt(time.time() - t0)} -> {dst}')


def cmd_estimate(a):
    q = a[a.index('--quality') + 1] if '--quality' in a else 'final'
    Q = QUALITY[q]
    poster()
    out = os.path.join(ROOT, 'build', 'renders', f'estimate_{q}')
    total, rows = 0.0, []
    for shot, n in SHOTS:
        times, build = [], [0.0]

        def on(line):
            m = re.match(r'frame \d+ ([\d.]+)s', line)
            if m:
                times.append(float(m.group(1)))
            m = re.match(r'built ([\d.]+)s', line)
            if m:
                build[0] = float(m.group(1))
        spp = Q['spp_fo'] if shot == 'FO' else Q['spp']
        print(f'timing {shot} ...', flush=True)
        run_shot(shot, out, Q['scale'], spp, Q['subs'], f'{n // 2},{n // 2 + 1}', on)
        per = times[-1] if times else 0
        est = per * n + build[0] + 20
        total += est
        rows.append((shot, n, per, est))
    total += 90                                       # edit, sound, encode
    for shot, n, per, est in rows:
        print(f'  {shot:3s} {n:4d} frames x {per:5.1f}s = {fmt(est)}')
    print(f'ESTIMATE {q}: about {fmt(total)} on this machine')
    json.dump({'quality': q, 'seconds': total, 'shots': rows}, open(os.path.join(ROOT, 'build', f'estimate_{q}.json'), 'w'))
    shutil.rmtree(out, ignore_errors=True)


def cmd_render(a):
    q = a[a.index('--quality') + 1] if '--quality' in a else 'draft'
    Q = QUALITY[q]
    social = '--social' in a
    only = a[a.index('--shots') + 1].split(',') if '--shots' in a else [s for s, _ in SHOTS]
    if not cmd_validate(None):
        raise SystemExit(1)
    br = B.load()
    poster()
    rdir = os.path.join('build', 'renders', q)
    t_all = time.time()
    done_frames, all_frames = 0, sum(n for s, n in SHOTS if s in only)
    for shot, n in SHOTS:
        if shot not in only:
            continue
        t0 = time.time()
        state = {'k': 0}

        def on(line, shot=shot, n=n, t0=t0):
            if line.startswith('frame '):
                state['k'] += 1
                k = state['k']
                if k % 10 == 0 or k == n:
                    el = time.time() - t_all
                    frac = (done_frames + k) / all_frames
                    print(f'  {shot} {k}/{n}  total {frac * 100:4.1f}%  elapsed {fmt(el)}  left ~{fmt(el / frac - el)}',
                          flush=True)
        spp = Q['spp_fo'] if shot == 'FO' else Q['spp']
        print(f'render {shot} ({n} frames, quality {q})', flush=True)
        run_shot(shot, rdir, Q['scale'], spp, Q['subs'], 'all', on)
        done_frames += n
    name = re.sub(r'[^A-Za-z0-9_-]+', '-', br['output_name']) or 'shred'
    os.makedirs(os.path.join(ROOT, 'out'), exist_ok=True)
    silent = os.path.join('build', f'{name}_{q}_60fps.mp4')
    print('edit ...', flush=True)
    subprocess.run([PY, os.path.join(ROOT, 'scripts', 'edit.py'), rdir, silent, '--crf', '15' if q == 'final' else '18'],
                   check=True, cwd=ROOT)
    outs = [(silent, os.path.join('out', f'{name}_{q}_60fps.mp4'))]
    if social:
        ig = os.path.join('build', f'{name}_{q}_social_60fps.mp4')
        subprocess.run([PY, os.path.join(ROOT, 'scripts', 'edit.py'), rdir, ig, '--ig'], check=True, cwd=ROOT)
        outs += [(ig, os.path.join('out', f'{name}_{q}_social_60fps.mp4')),
                 (ig.replace('60fps', '30fps'), os.path.join('out', f'{name}_{q}_social_30fps.mp4'))]
        for cov in glob.glob(os.path.join(ROOT, 'build', f'{name}_{q}_social_cover_*.png')):
            shutil.copy(cov, os.path.join(ROOT, 'out', os.path.basename(cov)))
    shutil.copy(os.path.join(ROOT, silent.replace('.mp4', '_cues.csv')), os.path.join(ROOT, 'out', f'{name}_cues.csv'))
    mix = None
    if br.get('sound', True):
        print('sound ...', flush=True)
        subprocess.run([PY, os.path.join(ROOT, 'scripts', 'sound.py')], check=True, cwd=ROOT)
        mix = os.path.join(ROOT, 'build', 'sound', 'mix.wav')
        shutil.copy(mix, os.path.join(ROOT, 'out', f'{name}_sound.wav'))
    for src, dst in outs:
        if mix:
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', os.path.join(ROOT, src), '-i', mix, '-map', '0:v', '-map',
                            '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '320k', '-shortest', '-movflags', '+faststart',
                            os.path.join(ROOT, dst)], check=True)
        else:
            shutil.copy(os.path.join(ROOT, src), os.path.join(ROOT, dst))
        print('wrote', dst)
    print(f'done in {fmt(time.time() - t_all)}')


COMMANDS = {'doctor': cmd_doctor, 'fields': cmd_fields, 'set': cmd_set, 'validate': cmd_validate, 'poster': cmd_poster,
            'stills': cmd_stills, 'estimate': cmd_estimate, 'render': cmd_render}

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(0 if len(sys.argv) < 2 else 1)
    r = COMMANDS[sys.argv[1]](sys.argv[2:])
    if sys.argv[1] == 'validate' and r is False:
        raise SystemExit(1)
