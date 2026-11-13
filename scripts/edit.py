"""Cut the four shots into the reel, finish the frames and write sound cues. kit.py drives it; by hand:

    python scripts/edit.py build/renders/final out/shred_60fps.mp4 [--crf 15] [--ig]

--ig writes the Instagram delivery instead of the master: half the grain, a light sharpen after scaling, a
fixed 16 Mbit/s, plus a 30 fps version (pairs of frames averaged) and two cover stills.

H (hook) and A, C are full bleed; FO (the shredder, one camera move from the feed to under the cutters) sits as
an inset on pure white (844x1500 in 1080x1920). The shots already carry real motion blur; each cut adds a short directional whip on the frames
either side. Finish: a grade (deeper blacks, a gentle S, cool shadows and warm highlights), highlight glow, a soft vignette
and fine grain on the picture (never on the white border). Punches: a short shake and sharpen when the strips rip
in H, a small zoom bump on the final click in C. The shredder inset grows out of the full frame over 8 frames.
The last frame of C equals the first frame of H, so the reel loops without a seam.
Output is tagged BT.709 so players don't tint the white.
"""
import os, re, sys, csv, json, subprocess
import numpy as np, cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1080, 1920
INSET = (844, 1500)
FPS = 60
# shot, frames, inset, screen direction of the whip blur out of the shot, and into it (None: the previous shot's)
ORDER = [('H', 30, False, (1, 0), None), ('A', 112, False, (-0.77, 0.64), (-0.77, 0.64)), ('FO', 123, True, (1, 0), (0, 1)),
         ('C', 216, False, None, None)]
OUT_BLUR = [4, 10, 20, 34]          # px on the last frames of a shot
IN_BLUR = [24, 10]                  # px on the first frames of the next


def mblur(img, length, d):
    if length < 2 or d is None:
        return img
    k = np.zeros((length * 2 + 1, length * 2 + 1), np.float32)
    c = length
    for t in np.linspace(-length / 2, length / 2, length * 2):
        k[int(round(c + t * d[1])), int(round(c + t * d[0]))] = 1
    k /= k.sum()
    return cv2.filter2D(img, -1, k, borderType=cv2.BORDER_REFLECT)


_vig = {}
SHADOW_TINT = np.array([0.012, 0.003, -0.008], np.float32)      # BGR: cool
HIGHLIGHT_TINT = np.array([-0.008, 0.0, 0.008], np.float32)     # BGR: warm


def grade(f):
    f = np.clip((f - 0.015) / 0.985, 0, 1)                      # a slightly deeper black point
    f = f + 0.25 * f * (1 - f) * (2 * f - 1)                     # gentle S
    lum = f.mean(2, keepdims=True)
    return f + (1 - lum) ** 2 * SHADOW_TINT + lum ** 2 * HIGHLIGHT_TINT


def punch(img, scale=1.0, dx=0.0, dy=0.0, sharp=0.0):
    """Zoom about the centre and shift (in output px), then an unsharp pulse."""
    h, w = img.shape[:2]
    k = w / W
    if scale != 1.0 or dx or dy:
        M = np.array([[scale, 0, (1 - scale) * w / 2 + dx * k], [0, scale, (1 - scale) * h / 2 + dy * k]], np.float32)
        img = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    if sharp:
        b = cv2.GaussianBlur(img, (0, 0), 1.2 * k)
        img = cv2.addWeighted(img, 1 + sharp, b, -sharp, 0)
    return img


def finish(img, rng, grain=0.012):
    """Grade, glow on highlights, soft vignette, fine moving grain. img is uint8 BGR of any size."""
    h, w = img.shape[:2]
    f = grade(img.astype(np.float32) / 255)
    lum = f.mean(2)
    hl = np.clip(lum - 0.82, 0, None)
    glow = cv2.GaussianBlur(hl, (0, 0), w / 45)
    f += 0.35 * glow[..., None]
    if (h, w) not in _vig:
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        r = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2) / np.sqrt(2)
        _vig[(h, w)] = (1 - 0.13 * r ** 2.2)[..., None]
    f *= _vig[(h, w)]
    g = rng.normal(0, 1, (h, w)).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), 0.7) * grain
    f += g[..., None] * (0.6 + 0.4 * (1 - np.abs(lum - 0.5) * 2))[..., None]
    return np.clip(f * 255 + 0.5, 0, 255).astype(np.uint8)


def place(img, inset, grow=0.0):
    """grow 1 -> the inset fills the frame, 0 -> 844x1500 on white (the render has the frame's aspect)."""
    if not inset or grow >= 1:
        return cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA if img.shape[1] >= W else cv2.INTER_CUBIC)
    iw = int(round(INSET[0] + (W - INSET[0]) * grow)) // 2 * 2
    ih = int(round(INSET[1] + (H - INSET[1]) * grow)) // 2 * 2
    im = cv2.resize(img, (iw, ih), interpolation=cv2.INTER_AREA if img.shape[1] >= iw else cv2.INTER_CUBIC)
    out = np.full((H, W, 3), 255, np.uint8)
    x0, y0 = (W - iw) // 2, (H - ih) // 2
    out[y0:y0 + ih, x0:x0 + iw] = im
    return out


def _ease(u, p=2.2):
    u = min(1.0, max(0.0, u))
    return u ** p / (u ** p + (1 - u) ** p)


H_RIP = 4                                                    # H frame where the strips rip
H_PUNCH = [(1.012, 6, -4, 0.8), (1.008, -4, 3, 0.5), (1.004, 2, -2, 0.25), (1.001, 0, 0, 0.0)]
C_PUNCH = [1.004, 1.007, 1.005, 1.003, 1.0015, 1.0005]       # zoom bump from the final click
GROW_IN = 8                                                  # frames for the inset to shrink out of full frame


def encoder(dst, fps, ig, crf):
    rate = ['-b:v', '16M', '-maxrate', '20M', '-bufsize', '32M'] if ig else ['-crf', crf]
    return subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}',
                             '-r', str(fps), '-i', '-', '-vf', 'scale=out_color_matrix=bt709:out_range=tv',
                             '-c:v', 'libx264', '-preset', 'slow', '-profile:v', 'high', *rate, '-pix_fmt', 'yuv420p',
                             '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
                             '-movflags', '+faststart', dst], stdin=subprocess.PIPE)


def main():
    src = os.path.join(ROOT, sys.argv[1])
    dst = os.path.join(ROOT, sys.argv[2])
    crf = sys.argv[sys.argv.index('--crf') + 1] if '--crf' in sys.argv else '15'
    srcs = {}                                   # per-shot source folders, e.g. reuse unchanged H and C
    if '--from' in sys.argv:
        for kv in sys.argv[sys.argv.index('--from') + 1].split(','):
            k, v = kv.split('=')
            srcs[k] = os.path.join(ROOT, v)
    ig = '--ig' in sys.argv
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    ff = encoder(dst, FPS, ig, crf)
    ff30 = encoder(dst.replace('60fps', '30fps'), 30, ig, crf) if ig else None
    half = None
    lands = os.path.join(ROOT, 'build', 'c_lands.json')
    c_click = int(round(json.load(open(lands))['land_frames'][-1])) if os.path.exists(lands) else -99
    covers = {('C', ORDER[-1][1] - 1): 'cover_poster', ('A', 40): 'cover_ribbons'} if ig else {}
    rng = np.random.default_rng(7)
    starts, t0 = {}, 0
    for si, (shot, n, inset, d, d_in) in enumerate(ORDER):
        prev_d = ORDER[si - 1][3] if si else None
        starts[shot] = t0
        for f in range(n):
            img = cv2.imread(os.path.join(srcs.get(shot, src), f'{shot}_{f:04d}.jpg'))
            if img is None:
                raise SystemExit(f'missing {shot} {f}')
            k_out = n - 1 - f
            if k_out < len(OUT_BLUR) and si < len(ORDER) - 1:
                img = mblur(img, int(OUT_BLUR[::-1][k_out] * img.shape[1] / W), d)
            if f < len(IN_BLUR) and si:
                img = mblur(img, int(IN_BLUR[f] * img.shape[1] / W), d_in or prev_d)
            if shot == 'H' and 0 <= f - H_RIP < len(H_PUNCH):
                sc_, dx, dy, sh = H_PUNCH[f - H_RIP]
                img = punch(img, sc_, dx, dy, sh)
            if shot == 'C' and 0 <= f - c_click < len(C_PUNCH):
                img = punch(img, C_PUNCH[f - c_click])
            img = finish(img, rng, grain=0.006 if ig else 0.012)
            grow = 1 - _ease(f / GROW_IN) if inset and si and not ORDER[si - 1][2] and f < GROW_IN else 0.0
            out = place(img, inset, grow)
            if ig:
                out = punch(out, sharp=0.3)
            ff.stdin.write(out.tobytes())
            if ff30:
                if half is None:
                    half = out.astype(np.uint16)
                else:
                    ff30.stdin.write(((half + out + 1) // 2).astype(np.uint8).tobytes())
                    half = None
            if (shot, f) in covers:
                cv2.imwrite(dst.replace('_60fps.mp4', f'_{covers[(shot, f)]}.png'), out)
        t0 += n
    ff.stdin.close()
    ff.wait()
    if ff30:
        ff30.stdin.close()
        ff30.wait()

    # sound cues (frames at 60 fps)
    h, a, fo, c = (starts[s] for s in ('H', 'A', 'FO', 'C'))
    rows = [(0, 'H', 'clean poster, still (hook): silence or room tone'),
            (h + H_RIP, 'H', 'strips rip sideways top to bottom (frame shakes): hard paper tear hit + whoosh'),
            (a, 'A', 'cut in, whip: ribbons already falling onto the pile (soft paper flutter, air)'),
            (a + 18, 'A', 'the accent (headline) ribbon lays down on the pile: soft paper flop, small rebound'),
            (a + 30, 'A', 'more ribbons lay down one after another (light flops) until about +1.6 s'),
            (a + 90, 'A', 'speed ramp into the cut (paper rush)'),
            (fo, 'FO', 'the white frame closes in; camera rushes the shredder (whoosh), motor running, paper slides down'),
            (fo + 78, 'FO', 'camera dives under the cutters: crunch gets closer and wetter, strips rustle and flutter'),
            (fo + 102, 'FO', 'whip out of the curtain'),
            (c, 'C', 'cut in: motor stops (spin-down); strips slide in from both sides (dry paper slides), never stop'),
            (c + 216 - 20, 'C', 'poster settled, hold: the poster reads clean; loops back to H')]
    fc = os.path.join(ROOT, 'build', 'fo_cues.json')
    if os.path.exists(fc):
        q = json.load(open(fc))
        rows.append((fo + int(round(q['bite'] * FPS)), 'FO', 'the cutters bite the poster edge: sharp crunch + motor load drop, then steady cutting'))
        rows.append((fo + int(round(q['emerge'] * FPS)), 'FO', 'first strips push out under the comb: paper rustle starts'))
    lands = os.path.join(ROOT, 'build', 'c_lands.json')
    if os.path.exists(lands):
        lf = json.load(open(lands))['land_frames']
        for i, fr in enumerate(lf):
            last = i == len(lf) - 1
            rows.append((c + int(round(fr)), 'C', 'final strip lands: the click (biggest hit, camera bump, light passes down)' if last
                         else f'strip lands in line: click {i + 1} (the wave speeds up)'))
    rows.sort(key=lambda r: r[0])
    with open(dst.replace('.mp4', '_cues.csv'), 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['frame_60fps', 'seconds', 'shot', 'event'])
        for fr, sh, ev in rows:
            w.writerow([fr, f'{fr / FPS:.3f}', sh, ev])
    print('wrote', dst, t0, 'frames')


if __name__ == '__main__':
    main()
