"""Draw the poster texture from the brief. Every letter is real type, so the shreds really are this poster.

    python scripts/poster.py        -> build/tex/poster.png (2400x3600), poster_plain.png, build/preview/poster.png

The layout is fixed (the 3D shots are framed on it); the words, fonts, colours and the picture come from brief.json.
Top to bottom: a small name line, the headline on the accent band, the subline, giant cropped letters, a dense band
of body columns with a halftone picture, the small line again and the footer word.

poster.png carries the accent band; poster_plain.png is the same poster without it, for the background ribbons in
the cascade shot, so the accent stays on the hero ribbon only.
"""
import os, sys, json
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brief as B
import fonts

W, H = 2400, 3600
M = 110                                   # side margin
BAND = (232, 902)                         # accent band rows; the 3D hero ribbon is cut from exactly these rows
CAP = {'headline': 610, 'subline': 400, 'footer': 600}     # tallest a big line's capitals may get (px)


def tex_dir():
    d = B.build_dir('tex')
    os.makedirs(d, exist_ok=True)
    return d


class Poster:
    def __init__(self, br):
        self.br = br
        c = br['colors']
        self.paper, self.ink, self.accent = (B.hex_rgb(c[k]) for k in ('paper', 'ink', 'accent'))
        self.dark_paper = B.luminance(c['paper']) < B.luminance(c['ink'])
        f = br['fonts']
        self.display = fonts.get(f['display']['family'], f['display'].get('weight', 500))
        self.text = fonts.get(f['text']['family'], f['text'].get('weight', 400))

    def font(self, path, px):
        return ImageFont.truetype(path, int(px))

    def width(self, d, word, f, tracking):
        x = 0
        for ch in word:
            x += d.textlength(ch, font=f) + tracking * f.size
        return x - tracking * f.size

    def cap_height(self, f):
        b = f.getbbox('H', anchor='ls')
        return -b[1]

    def fit(self, d, word, width, cap, tracking=-0.035):
        """Largest size at which the word spans the width, capped so its capitals stay under cap px."""
        lo, hi = 20, 2400
        while hi - lo > 2:
            mid = (lo + hi) // 2
            f = self.font(self.display, mid)
            if self.width(d, word, f, tracking) > width or self.cap_height(f) > cap:
                hi = mid
            else:
                lo = mid
        return self.font(self.display, lo)

    def draw_word(self, d, xy, word, f, tracking=-0.035, fill=None):
        x, y = xy
        for ch in word:
            d.text((x, y), ch, font=f, fill=self.ink if fill is None else fill, anchor='ls')
            x += d.textlength(ch, font=f) + tracking * f.size

    def name_line(self, d, y):
        t = self.br['text']
        f = self.font(self.display, 74)
        d.text((M, y), t['top_left'], font=f, fill=self.ink, anchor='ls')
        d.text((W - M, y), t['top_right'], font=f, fill=self.ink, anchor='rs')
        d.line([(M, y + 34), (W - M, y + 34)], fill=self.ink, width=5)

    def halftone(self, w, h, cell=20):
        """Round-dot halftone of the brief's picture. mode 'object': a thing on a plain backdrop; the backdrop
        turns to bare paper and the object is pushed dark, so it still reads after the shredder. mode 'photo':
        the whole picture, tone-mapped. Returns an L image where 0 means ink."""
        im_cfg = self.br['image']
        src = im_cfg['path'] if os.path.isabs(im_cfg['path']) else os.path.join(B.ROOT, im_cfg['path'])
        im = cv2.imread(src, cv2.IMREAD_GRAYSCALE)
        if im is None:
            raise SystemExit(f'cannot read the picture: {src}')
        ih, iw = im.shape
        s = max(w / iw, h / ih)
        im = cv2.resize(im, (int(iw * s) + 1, int(ih * s) + 1), interpolation=cv2.INTER_CUBIC)
        y0, x0 = (im.shape[0] - h) // 2, (im.shape[1] - w) // 2
        im = im[y0:y0 + h, x0:x0 + w].astype(np.float32) / 255
        if im_cfg.get('mode', 'object') == 'object':
            border = np.concatenate([im[:8].ravel(), im[-8:].ravel(), im[:, :8].ravel(), im[:, -8:].ravel()])
            bg = float(np.median(border))
            g = cv2.GaussianBlur(im, (0, 0), 2)
            obj = np.clip((np.abs(g - bg) - 0.025) / 0.04, 0, 1)
            obj = cv2.GaussianBlur(cv2.dilate(obj, np.ones((9, 9), np.uint8)), (0, 0), 3)
            cl = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(6, 6)).apply((im * 255).astype(np.uint8)) / 255.0
            dark = 0.06 + 0.92 * np.clip((cl - 0.30) / 0.62, 0, 1) ** 1.5
            im = obj * dark + (1 - obj) * 1.0
        else:
            lo, hi = np.percentile(im, 2), np.percentile(im, 98)
            im = np.clip((im - lo) / max(hi - lo, 1e-3), 0, 1) ** 0.8
        if self.dark_paper:                 # light ink on dark paper: dots carry the light, the picture stays positive
            im = 1 - im
            if im_cfg.get('mode', 'object') == 'object':
                im = np.where(obj > 0.5, im, 1.0)
        out = Image.new('L', (w, h), 255)
        od = ImageDraw.Draw(out)
        small = cv2.resize(im, (w // cell + 1, h // cell + 1), interpolation=cv2.INTER_AREA)
        for j in range(small.shape[0]):
            for i in range(small.shape[1]):
                r = max(0.0, 1 - small[j, i]) ** 0.5 * cell * 0.74
                if r > 0.9:
                    cx, cy = i * cell + cell / 2, j * cell + cell / 2
                    od.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
        return out

    def columns(self, d, box, ncol, px, lead, seed):
        x0, y0, x1, y1 = box
        f = self.font(self.text, px)
        gap = 36
        cw = (x1 - x0 - gap * (ncol - 1)) / ncol
        words = (self.br['text']['body'] + ' ').split() * 12
        k = seed * 37 % len(words)
        for c in range(ncol):
            cx = x0 + c * (cw + gap)
            y = y0 + px
            while y < y1:
                line = ''
                while True:
                    wd = words[k % len(words)]
                    t = (line + ' ' + wd).strip()
                    if d.textlength(t, font=f) > cw:
                        break
                    line, k = t, k + 1
                if not line:                        # a single word wider than the column: let it overflow
                    line, k = words[k % len(words)], k + 1
                d.text((cx, y), line, font=f, fill=self.ink, anchor='ls')
                y += lead

    def make(self, band):
        t = self.br['text']
        im = Image.new('RGB', (W, H), self.paper)
        d = ImageDraw.Draw(im)
        inner = W - 2 * M
        if band:
            d.rectangle([0, BAND[0], W, BAND[1]], fill=self.accent)
        self.name_line(d, 190)
        sizes = {}
        for key, base in (('headline', 860), ('subline', 1320)):
            f = self.fit(d, t[key], inner, CAP[key])
            self.draw_word(d, (M - 0.02 * f.size, base), t[key], f)
            sizes[key] = f.size
        # giant fragments: the top of a word much bigger than the frame, cut by the band below
        f3 = self.font(self.display, 1150)
        big = Image.new('L', (W, 700), 255)
        self.draw_word(ImageDraw.Draw(big), (-160, 1080), t['fragment'], f3, tracking=-0.05, fill=0)
        im.paste(Image.new('RGB', (W, 300), self.ink), (0, 1450), Image.eval(big.crop((0, 300, W, 600)), lambda v: 255 - v))
        d.line([(M, 1790), (W - M, 1790)], fill=self.ink, width=12)
        # dense band: the halftone picture and body columns
        ht = self.halftone(1060, 760)
        im.paste(Image.new('RGB', ht.size, self.ink), (M, 1860), Image.eval(ht, lambda v: 255 - v))
        self.columns(d, (M + 1100, 1850, W - M, 2630), 2, 40, 50, 1)
        self.columns(d, (M, 2650, W - M, 2800), 4, 40, 50, 7)
        self.name_line(d, 2870)
        f4 = self.fit(d, t['footer'], inner, CAP['footer'])
        self.draw_word(d, (M - 0.02 * f4.size, 3525), t['footer'], f4)
        sizes['footer'] = f4.size
        # paper: faint fibre and print unevenness, weaker on ink
        a = np.asarray(im).astype(np.float32)
        rng = np.random.default_rng(3)
        n = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 1.2) * 3.0
        n += cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 40) * 25
        n *= 0.5 if self.dark_paper else 1.0
        ink = np.abs(a - np.array(self.paper, np.float32)).mean(2, keepdims=True) > 60
        a = a + n[..., None] * np.where(ink, 0.6, 1.0)
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)), sizes


def main():
    br = B.load()
    p = Poster(br)
    band = bool(br['colors'].get('accent_band', True))
    hero, sizes = p.make(band)
    hero.save(os.path.join(tex_dir(), 'poster.png'))
    plain = p.make(False)[0] if band else hero
    plain.save(os.path.join(tex_dir(), 'poster_plain.png'))
    os.makedirs(B.build_dir('preview'), exist_ok=True)
    hero.resize((800, 1200), Image.LANCZOS).save(B.build_dir('preview', 'poster.png'))
    json.dump(sizes, open(B.build_dir('tex', 'sizes.json'), 'w'))
    print('poster ok, type sizes px:', sizes, '->', B.build_dir('preview', 'poster.png'))


if __name__ == '__main__':
    main()
