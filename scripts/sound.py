"""Shred sound design: every sound placed on its frame from the shot data, mixed and mastered in code.

    python scripts/sound.py        -> build/sound/mix.wav (+ stems), after the FO and C shots have rendered

Sources: public-domain paper and shredder recordings (assets/sound, see assets/sound/SOURCES.md), plus synthesis
(tear crackle, whooshes, motor, clicks). The mix is built on a circular buffer of the reel's exact length, so tails
that run past the end wrap onto the start and the loop has no seam. Mastered to -14 LUFS, -1.2 dBTP.
"""
import os, json
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, stft, istft, resample_poly
import pedalboard as pb
import pyloudnorm as pyln

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'assets', 'sound')
OUT = os.path.join(ROOT, 'build', 'sound')
SR = 48000
FPS = 60
NFR = 481
N = int(round(NFR / FPS * SR))
rng = np.random.default_rng(11)

# shot starts (frames) in the cut: H 30, A 112, FO 123, C 216
H0, A0, FO0, C0 = 0, 30, 142, 265
fs = lambda f: f / FPS                    # frame -> s


# ---------------------------------------------------------------- tools
def band(x, lo=None, hi=None, order=2):
    if lo and hi:
        sos = butter(order, [lo, hi], 'bandpass', fs=SR, output='sos')
    elif lo:
        sos = butter(order, lo, 'highpass', fs=SR, output='sos')
    else:
        sos = butter(order, hi, 'lowpass', fs=SR, output='sos')
    return sosfilt(sos, x, axis=0)


def env_adsr(n, a, r, curve=2.0):
    """attack a s (raised cosine), exponential-ish release over the rest."""
    t = np.arange(n) / SR
    na = max(1, int(a * SR))
    e = np.ones(n)
    e[:na] = 0.5 - 0.5 * np.cos(np.pi * np.arange(na) / na)
    rel = np.clip((t - a) / max(r, 1e-4), 0, None)
    e[na:] *= np.exp(-curve * rel[na:] * 2.3)
    return e


def pan(x, p):
    """mono -> stereo, p in -1..1, equal power."""
    a = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], 1)


def pan_sweep(x, p0, p1):
    p = np.linspace(p0, p1, len(x))
    a = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(a), x * np.sin(a)], 1)


def pink(n):
    w = rng.standard_normal(n)
    W = np.fft.rfft(w)
    f = np.fft.rfftfreq(n, 1 / SR)
    W[1:] /= np.sqrt(f[1:])
    W[0] = 0
    p = np.fft.irfft(W, n)
    return p / (np.abs(p).max() + 1e-9)


def sweep_band(x, fc, bw_oct=0.7):
    """time-varying band-pass: fc is an array of centre frequencies (Hz) over the length of x."""
    f, t, Z = stft(x, SR, nperseg=1024, noverlap=768)
    c = np.interp(t, np.linspace(0, len(x) / SR, len(fc)), fc)
    lf = np.log2(np.maximum(f, 20))[:, None]
    M = np.exp(-0.5 * ((lf - np.log2(c)[None, :]) / bw_oct) ** 2)
    _, y = istft(Z * M, SR, nperseg=1024, noverlap=768)
    return y[:len(x)] if len(y) >= len(x) else np.pad(y, (0, len(x) - len(y)))


def crackle(n, rate, lo=1500, hi=9000, seed=None):
    """Paper fibre crackle: Poisson micro-impulses (rate per second, array or scalar), each a 0.2-1 ms tick."""
    r = np.random.default_rng(seed)
    rate = np.broadcast_to(np.asarray(rate, float), (n,))
    hits = r.random(n) < rate / SR
    amp = np.where(hits, r.exponential(1.0, n) ** 1.6 * r.choice([-1, 1], n), 0.0)
    k = np.exp(-np.arange(int(0.0012 * SR)) / (0.00025 * SR))
    y = np.convolve(amp, k)[:n]
    return band(y, lo, hi)


_cache = {}


def _read(name):
    if name not in _cache:
        x, sr = sf.read(os.path.join(SRC, name.replace('.wav', '.flac')), always_2d=True)
        if sr != SR:
            from math import gcd
            g = gcd(SR, sr)
            x = resample_poly(x, SR // g, sr // g, axis=0)
        _cache[name] = (x, SR)
    return _cache[name]


def load(name, t0, dur, gain_db=0.0):
    x, sr = _read(name)
    a = int(t0 * SR)
    seg = x[a:a + int(dur * SR)].mean(1)
    f = int(0.004 * SR)
    seg = seg.copy()
    seg[:f] *= np.linspace(0, 1, f)
    seg[-f:] *= np.linspace(1, 0, f)
    return seg * 10 ** (gain_db / 20)


def speed(x, s):
    """resample: s>1 is faster and higher."""
    up, down = 1000, int(round(1000 * s))
    return resample_poly(x, up, down)


def norm(x, peak=1.0):
    return x * peak / (np.abs(x).max() + 1e-9)


# ---------------------------------------------------------------- the circular mix, by stem
STEMS = {}


def put(stem, x, t, gain_db=0.0):
    """add x (mono or stereo) at time t (s); wraps around the loop."""
    if x.ndim == 1:
        x = pan(x, 0.0)
    buf = STEMS.setdefault(stem, np.zeros((N, 2)))
    a = int(round(t * SR)) % N
    x = x * 10 ** (gain_db / 20)
    i = 0
    while i < len(x):
        k = min(len(x) - i, N - a)
        buf[a:a + k] += x[i:i + k]
        i += k
        a = 0


# ---------------------------------------------------------------- sound recipes
def tear(dur, bright=1.0, seed=None, heavy=1.0):
    """one strip tearing: dense fibre crackle, a ragged noise body, a quick low snap at the start."""
    n = int(dur * SR)
    r = np.random.default_rng(seed)
    t = np.arange(n) / SR
    rate = 2500 * (1 - t / dur) ** 0.5 + 600
    ck = crackle(n, rate, 1800 * bright, 11000, seed)
    body = band(r.standard_normal(n), 900 * bright, 5000 * bright) * (0.4 + 0.6 * r.random(n) ** 3)
    body = band(body, None, 9000)
    snap = band(r.standard_normal(n), 120, 900) * np.exp(-t / 0.012) * heavy
    e = env_adsr(n, 0.003, dur * 0.7, 1.4)
    return norm(ck * 1.0 + body * 0.35, 1.0) * e + snap * 0.5


def whoosh(dur, f0, f1, peak_at=0.6, bw=0.8, seed=None):
    n = int(dur * SR)
    t = np.linspace(0, 1, n)
    fc = f0 * (f1 / f0) ** t
    x = sweep_band(pink(n), fc, bw)
    e = np.where(t < peak_at, (t / peak_at) ** 2.2, np.exp(-(t - peak_at) / (1 - peak_at) * 3.5))
    return norm(x, 1.0) * e


PAGE_PAT = 0.75                               # where the pat sits inside the page-turn segment (s)
CUTS = [1.03, 1.75, 3.12, 3.99, 4.77, 5.82, 6.85, 10.86, 13.56]   # paper snips in the rejection-letter recording


def page_flop(seed, spd=1.0):
    """a real page turn (swish, then the pat as it lays down), sped up: returns (audio, pat position in s)."""
    x = load('Turning_a_page.wav', 1.45, 1.0)
    x = band(speed(x, spd), 150, 14000)
    return norm(x, 1.0), PAGE_PAT / spd


def real_tear(seed, spd=1.3):
    """a real paper snip, sped up, with a little synthetic fibre crackle on top."""
    r = np.random.default_rng(seed)
    x = load('Rejection_letter_cut_into_pieces.wav', CUTS[r.integers(len(CUTS))] - 0.01, 0.22)
    x = norm(band(speed(x, spd), 700, 14000), 1.0)
    ck = crackle(len(x), 1500 * np.exp(-np.arange(len(x)) / SR / 0.05), 2000, 11000, seed)
    return x + norm(ck, 0.35) * np.exp(-np.arange(len(x)) / SR / 0.06)


def flop(seed, size=1.0):
    """a paper ribbon laying down onto paper: an airy slide that ends in a soft pat."""
    r = np.random.default_rng(seed)
    d = 0.16 + 0.1 * size
    n = int(d * SR)
    t = np.arange(n) / SR
    slide = band(pink(n), 1200, 7000) * np.clip(t / d, 0, 1) ** 1.5
    pat_at = int(0.8 * n)
    pat = np.zeros(n)
    m = n - pat_at
    tt = np.arange(m) / SR
    pat[pat_at:] = band(r.standard_normal(m), 250, 2400) * np.exp(-tt / 0.018)
    ck = crackle(n, 300 * np.clip(t / d, 0, 1), 2500, 10000, seed) * 0.6
    y = slide * 0.35 + pat * 1.0 * size + ck
    y *= env_adsr(n, 0.04, d, 0.5)
    return norm(y, 1.0)


def strip_click(i, total, seed, final=False):
    """a strip snapping into line on the poster: dry transient + a small papery body; rises slightly in pitch
    as the wave speeds up. The final one adds weight (book-drop thud, sub)."""
    r = np.random.default_rng(seed)
    d = 0.12 if not final else 0.9
    n = int(d * SR)
    t = np.arange(n) / SR
    tr = band(r.standard_normal(n), 2500, 12000) * np.exp(-t / 0.0016)
    up = 1 + 0.18 * i / max(1, total - 1)
    body = (np.sin(2 * np.pi * 1150 * up * t + r.random() * 6) * np.exp(-t / 0.010) * 0.5
            + np.sin(2 * np.pi * 2900 * up * t) * np.exp(-t / 0.005) * 0.25)
    body += band(r.standard_normal(n), 500 * up, 3500 * up) * np.exp(-t / 0.014) * 0.8
    y = tr * 0.9 + body
    if final:
        th = load('Hardcover_books_dropped.wav', 1.40, 0.35)
        th = band(th, None, 900)
        th = np.pad(th, (0, max(0, n - len(th))))[:n]
        sub = np.sin(2 * np.pi * (70 + 40 * np.exp(-t / 0.03)) * t) * np.exp(-t / 0.09)
        y = (y * 1.3 + norm(th, 0.9) + sub * 0.45) * np.exp(-t / 0.25)
    return norm(y, 1.0)


def motor(dur, f0, pitch, seed=3):
    """shredder motor: a buzzy fundamental and gear whine following pitch(t) (ratio array), plus the recorded hum."""
    n = int(dur * SR)
    p = np.interp(np.arange(n), np.linspace(0, n, len(pitch)), pitch)
    ph = 2 * np.pi * np.cumsum(f0 * p) / SR
    buzz = sum(np.sin(k * ph + k) / k ** 1.1 for k in range(1, 14))
    whine = np.sin(ph * 13.0) * 0.12 + np.sin(ph * 26.0 + 1) * 0.05
    r = np.random.default_rng(seed)
    rough = band(r.standard_normal(n), 200, 2000) * 0.25 * (0.6 + 0.4 * np.sin(ph * 0.5) ** 2)
    hum = load('Shredder_hum.wav', 0.2, 3.6)
    reps = int(np.ceil(n / len(hum))) + 1
    loop = np.concatenate([hum] * reps)
    # read the recorded hum at the motor's speed so it follows the pitch too
    idx = np.cumsum(p)
    loop = np.interp(idx, np.arange(len(loop)), loop)
    y = norm(band(buzz, 40, 4000), 0.6) + whine + rough + norm(loop, 0.7)
    return y


def cutting(dur, rate_hz=21.0, seed=5):
    """paper being cut: crunch grains at the cutter rate on a fibrous bed."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    r = np.random.default_rng(seed)
    am = 0.55 + 0.45 * np.abs(np.sin(np.pi * rate_hz * t + r.random())) ** 3
    grind = band(r.standard_normal(n), 350, 2400) * am
    ck = crackle(n, 1800 * am, 1500, 10000, seed)
    return norm(grind * 0.6 + ck * 1.0, 1.0)


def room(n):
    x = band(pink(n), 60, 3000)
    return norm(x, 1.0)


# ---------------------------------------------------------------- the reel
def build():
    T = N / SR
    # room tone under everything (loop-safe: a constant bed)
    put('room', pan(room(N), 0.0) * 0.5 + pan(room(N), 0.0)[:, ::-1] * 0.5, 0.0, -52)

    # ---- H: clean poster for 4 frames, then the strips rip sideways, top to bottom
    t_rip = fs(H0 + 4)
    hit = tear(0.09, 1.0, seed=1, heavy=2.5)
    put('rip', hit, t_rip, 0)
    put('rip', band(pink(int(0.25 * SR)), 40, 200) * np.exp(-np.arange(int(0.25 * SR)) / SR / 0.05), t_rip, -10)
    n_strips = 22
    for k in range(n_strips):
        tk = t_rip + 0.012 + k * 0.0135 + rng.uniform(-0.003, 0.003)
        x = tear(rng.uniform(0.07, 0.13), 1.15 - 0.35 * k / n_strips, seed=100 + k)
        put('rip', pan(x, rng.uniform(-0.35, 0.35)), tk, -12 - 3 * k / n_strips)
        y = real_tear(150 + k, rng.uniform(1.2, 1.7))
        put('rip', pan(y, rng.uniform(-0.45, 0.45)), tk, -5 - 4 * k / n_strips)
    # the camera lunges at "Shred" and whips into A
    put('whoosh', pan_sweep(whoosh(0.42, 300, 2800, 0.85, seed=2), -0.3, 0.6), fs(H0 + 8), -10)

    # ---- A: ribbons falling onto the pile
    tA = fs(A0)
    put('whoosh', pan_sweep(whoosh(0.32, 2400, 500, 0.15, seed=4), 0.7, -0.6), tA - 0.06, -9)
    nA = int(1.75 * SR)
    t = np.arange(nA) / SR
    flut = band(pink(nA), 1500, 6500) * (0.6 + 0.4 * np.sin(2 * np.pi * (13 + 4 * np.sin(2 * np.pi * 1.3 * t)) * t) ** 2)
    flut *= np.clip(t / 0.05, 0, 1) * np.clip((1.75 - t) / 0.5, 0, 1) * (1 - 0.35 * t / 1.75)
    put('A', pan(norm(flut, 1.0), -0.15) * 0.7 + pan(norm(np.roll(flut, 7000), 1.0), 0.25) * 0.7, tA, -33)
    times = [0.1, 0.18, 0.46, 0.58, 0.72, 0.86, 1.0, 1.12, 1.26, 1.4, 1.55, 1.2, 0.95, 1.6, 0.8, 1.35]
    for i, tl in enumerate(times):
        near = 1 - i / len(times)
        x, pat = page_flop(200 + i, rng.uniform(1.4, 2.0))
        # the pat lands on the touchdown
        put('A', pan(x, rng.uniform(-0.6, 0.6)), tA + tl - pat, -16 - 7 * (1 - near))
        put('A', pan(flop(200 + i, 0.4 + 0.3 * near), rng.uniform(-0.5, 0.5)), tA + tl - 0.8 * len(flop(200 + i, 0.4 + 0.3 * near)) / SR, -26)
    hero, pat = page_flop(300, 1.15)
    put('A', pan(hero, -0.1), tA + 0.3 - pat, -6)
    x, pat = page_flop(301, 2.2)
    put('A', pan(x, -0.1), tA + 0.3 + 0.16 - pat, -22)                                              # the rebound
    # paper rush into the cut
    put('whoosh', pan_sweep(whoosh(0.5, 600, 5000, 0.9, seed=6), -0.4, 0.4), fs(A0 + 90) - 0.13, -12)
    pr = crackle(int(0.45 * SR), np.linspace(200, 2200, int(0.45 * SR)), 2500, 11000, 7)
    put('A', norm(pr, 1.0) * np.linspace(0, 1, len(pr))[:, None].repeat(2, 1)[:, 0], fs(A0 + 90) - 0.08, -22)

    # ---- FO: the shredder
    tF = fs(FO0)
    cues = json.load(open(os.path.join(ROOT, 'build', 'fo_cues.json')))
    t_bite, t_emerge, t_under = (tF + cues[k] for k in ('bite', 'emerge', 'under'))
    t_out = fs(C0)
    dur_m = t_out - tF + 1.0
    pts = np.linspace(0, dur_m, 400)
    pitch = np.ones_like(pts)
    pitch -= 0.07 * np.exp(-np.clip(pts - (t_bite - tF), 0, None) / 0.12) * (pts >= t_bite - tF)   # load drop
    pitch -= 0.03 * (pts >= t_bite - tF)                                                              # under load
    sd = np.clip(pts - (t_out - tF), 0, None)
    pitch = np.where(sd > 0, 0.25 + 0.72 * np.exp(-sd / 0.3), pitch)                               # spin-down in C
    m = motor(dur_m, 46.0, pitch)
    n = len(m)
    tt = np.arange(n) / SR
    lvl = np.ones(n)
    lvl *= np.clip(tt / 0.04, 0, 1)
    lvl *= np.where(tt > t_under - tF, 1.6, 1.0)                                       # closer under the cutters
    lvl *= np.where(tt > t_out - tF, np.exp(-(tt - (t_out - tF)) / 0.35), 1.0)          # spin-down fades
    put('motor', pan(m * lvl, 0.05), tF, -16)
    # the camera rushes the shredder; the white frame closes in
    put('whoosh', pan_sweep(whoosh(0.5, 400, 3500, 0.45, seed=8), -0.5, 0.2), tF - 0.08, -10)
    # paper sliding down into the feed before the bite
    s = load('Book_paper_pages_assorted.wav', 75.75, t_bite - tF + 0.1)
    put('cut', pan(norm(band(s, 800, 9000), 1.0) * np.linspace(0.3, 1, len(s)), 0.0), tF, -22)
    # the bite: a hard crunch, then steady cutting
    bite = tear(0.16, 0.8, seed=9, heavy=3.0)
    put('cut', bite, t_bite, 0)
    put('cut', band(pink(int(0.2 * SR)), 70, 400) * np.exp(-np.arange(int(0.2 * SR)) / SR / 0.06), t_bite, -4)
    put('cut', pan(real_tear(90, 0.9), 0.0), t_bite, -3)
    dc = t_out - t_bite
    c = cutting(dc + 0.15)
    tt = np.arange(len(c)) / SR
    open_ = np.where(tt + t_bite > t_under, 1.0, 0.0)
    # before the dive, the crunch is heard from above, a bit duller; under the cutters it opens up and gets louder
    dull = band(c, None, 3500)
    cc = dull * (1 - open_) + c * open_ * 1.7
    cc *= np.clip((t_out + 0.08 - (tt + t_bite)) / 0.08, 0, 1)
    put('cut', pan(cc, 0.0), t_bite, -8)
    # strips pushed out under the comb: rustle and flutter
    nr = int((t_out - t_emerge) * SR)
    tr_ = np.arange(nr) / SR
    rus = band(pink(nr), 1800, 8000) * (0.55 + 0.45 * np.sin(2 * np.pi * 17 * tr_) ** 2)
    rus *= np.clip(tr_ / 0.3, 0, 1) * np.where(tr_ + t_emerge > t_under, 1.8, 1.0)
    put('cut', pan(norm(rus, 1.0), 0.2) * 0.8 + pan(norm(np.roll(rus, 5000), 1.0), -0.25) * 0.6, t_emerge, -22)
    # whip out of the curtain
    put('whoosh', pan_sweep(whoosh(0.4, 3000, 400, 0.55, seed=10), -0.5, 0.8), fs(FO0 + 102) - 0.05, -9)

    # ---- C: strips slide in from both sides and snap into line
    tC = fs(C0)
    lands = json.load(open(os.path.join(ROOT, 'build', 'c_lands.json')))['land_frames']
    t_last = tC + lands[-1] / FPS
    slides = [(75.75, 1.8), (58.0, 1.9), (60.8, 1.6), (65.2, 1.05), (70.5, 0.75)]
    t = tC + 0.02
    k = 0
    while t < t_last - 0.25:
        st, d = slides[k % len(slides)]
        d = min(d, t_last - t)
        x = load('Book_paper_pages_assorted.wav', st, d)
        x = band(x, 900, 10000)
        x = norm(x, 1.0) * np.linspace(1, 0.4, len(x))
        side = -0.6 if k % 2 == 0 else 0.6
        fade = 1 - 0.75 * (t - tC) / (t_last - tC)
        put('C', pan(x, side), t, -20 + 20 * np.log10(fade))
        t += d * 0.55
        k += 1
    for i, fr in enumerate(lands[:-1]):
        x = strip_click(i, len(lands) - 1, 400 + i)
        x = x * np.exp(-np.arange(len(x)) / SR / 0.05)
        crowd = sum(1 for g in lands[:-1] if abs(g - fr) < 4)          # strips landing within ~65 ms share one hit
        put('click', pan(x, rng.uniform(-0.4, 0.4)), tC + fr / FPS, -17 + 4 * i / len(lands) - 10 * np.log10(crowd))
    fin = strip_click(len(lands), len(lands), 499, final=True)
    put('click', fin, t_last, 0)
    x, pat = page_flop(498, 1.6)
    x = x[int((pat - 0.06) * SR):]
    x[:int(0.02 * SR)] *= np.linspace(0, 1, int(0.02 * SR))
    put('click', x, t_last - 0.06, -1)                       # the final strip's paper slap under the click
    # the soft light pass after the click: a faint airy swell
    put('whoosh', pan_sweep(whoosh(0.5, 6000, 3500, 0.45, bw=0.5, seed=12), 0.0, 0.0), t_last + 0.03, -30)
    # into the loop: a short breath that rises into the rip on frame 4
    pre = whoosh(0.22, 800, 4000, 0.98, seed=13)
    put('whoosh', pan(pre, 0.0), T - 0.22 + t_rip - 0.02, -20)


def master():
    stems = {k: v.copy() for k, v in STEMS.items()}
    space = pb.Pedalboard([pb.Reverb(room_size=0.18, damping=0.6, wet_level=0.12, dry_level=1.0, width=0.8)])
    # tame the crest of the transient stems so loudness normalisation doesn't leave the limiter to flatten them
    for k, thr in (('click', -24), ('rip', -18), ('cut', -18)):
        x = np.concatenate([stems[k], stems[k]]).astype(np.float32)
        comp = pb.Pedalboard([pb.Compressor(threshold_db=thr, ratio=4.0, attack_ms=0.5, release_ms=60),
                              pb.Gain(-thr * 0.45)])
        stems[k] = comp(x.T, SR).T[N:]
    for k in ('rip', 'A', 'cut', 'C', 'click'):
        # circular reverb: render twice around the loop so the tail of the end lands on the start
        x = np.concatenate([stems[k], stems[k]]).astype(np.float32)
        y = space(x.T, SR).T
        stems[k] = y[N:] + 0.0 * y[:N]
    mix = sum(stems.values())
    bus = pb.Pedalboard([pb.HighpassFilter(28), pb.Compressor(threshold_db=-18, ratio=2.0, attack_ms=8, release_ms=120)])
    x2 = np.concatenate([mix, mix]).astype(np.float32)
    mix = bus(x2.T, SR).T[N:]
    meter = pyln.Meter(SR)
    for _ in range(4):                     # gain to -14 LUFS, limit to -1.2 dBTP, repeat until both hold
        lufs = meter.integrated_loudness(np.concatenate([mix] * 3))
        mix = limit(mix * 10 ** ((-14.0 - lufs) / 20), -1.2)
    return mix, stems


def limit(x, ceil_db, look=0.0015, rel=0.06):
    """lookahead peak limiter on 4x-oversampled peaks, circular (the loop wraps)."""
    c = 10 ** (ceil_db / 20)
    up = np.abs(resample_poly(np.concatenate([x[-512:], x, x[:512]]), 4, 1, axis=0)).max(1)
    pk = up.reshape(-1, 4).max(1)[512:512 + len(x)]
    g = np.minimum(1.0, c / (pk + 1e-12))
    L = int(look * SR)
    # hold the minimum over the lookahead window, then release smoothly
    from scipy.ndimage import minimum_filter1d
    g = minimum_filter1d(np.concatenate([g, g]), L * 2 + 1, mode='wrap')
    a = np.exp(-1 / (rel * SR))
    out = np.empty_like(g)
    s = 1.0
    for i in range(len(g)):            # instant attack (lookahead already applied), exponential release
        s = g[i] if g[i] < s else a * s + (1 - a) * g[i]
        out[i] = s
    g = out[len(x):]
    g = np.convolve(np.concatenate([g[-L:], g, g[:L]]), np.ones(L) / L, 'same')[L:L + len(x)]
    return x * np.minimum(g, 1.0)[:, None]


def true_peak(x):
    up = resample_poly(x, 4, 1, axis=0)
    return 20 * np.log10(np.abs(up).max() + 1e-12)


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    build()
    mix, stems = master()
    meter = pyln.Meter(SR)
    print(f'length {len(mix) / SR:.4f}s  LUFS {meter.integrated_loudness(np.concatenate([mix] * 3)):.1f}  '
          f'true peak {true_peak(mix):.1f} dBTP  seam jump {np.abs(mix[0] - mix[-1]).max():.4f}')
    sf.write(os.path.join(OUT, 'mix.wav'), mix, SR, subtype='PCM_24')
    for k, v in stems.items():
        sf.write(os.path.join(OUT, f'stem_{k}.wav'), v, SR, subtype='PCM_24')
        print(f'  stem {k:7s} peak {20 * np.log10(np.abs(v).max() + 1e-12):6.1f} dBFS')
