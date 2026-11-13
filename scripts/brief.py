"""The brief: everything a user can change, its defaults and its limits. Standard library only, so Blender's
own Python can import it too.

brief.json at the repo root overrides any subset of DEFAULTS. kit.py validates it against FIELDS.
"""
import os, json, copy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIEF = os.path.join(ROOT, 'brief.json')

DEFAULTS = {
    'output_name': 'shred',
    'text': {
        'top_left': 'Amir Mushich',
        'top_right': 'Creative R&D',
        'headline': 'Shred',
        'subline': 'the brief',
        'fragment': 'R&D',
        'footer': 'Shred',
        'body': ("Every brief arrives whole and leaves in strips. We cut it along the lines nobody questioned, keep "
                 "the pieces that still carry weight and throw the rest on the floor. A prototype is a brief that has "
                 "been through the shredder twice. Read it sideways, slide the strips until the words break, then wait "
                 "for the moment they line up again. That moment is the idea. Creative R&D is the habit of tearing the "
                 "obvious answer into ribbons before anyone asks for it, and rebuilding it with the grain running the "
                 "other way. Tools change every month; the cut stays. Draft, shred, recombine, ship."),
    },
    'fonts': {
        'display': {'family': 'Inter Tight', 'weight': 500},
        'text': {'family': 'Inter Tight', 'weight': 400},
    },
    'colors': {
        'paper': '#EEECE7',
        'ink': '#181716',
        'accent': '#AC1210',
        'accent_band': True,
    },
    'image': {
        'path': 'assets/image/demo.png',
        'mode': 'object',
    },
    'sound': True,
}

# text fields: (recommended min, recommended max, hard max) in characters, and what the line is
TEXT_FIELDS = [
    ('top_left', 0, 20, 26, 'small line, top left (a name, a brand)'),
    ('top_right', 0, 20, 26, 'small line, top right (a role, a tagline, a date)'),
    ('headline', 3, 7, 12, 'the giant word on the accent band; it is also the word on the hero ribbon and the '
                           'first thing the shredder bites'),
    ('subline', 5, 11, 16, 'the second big line under the headline'),
    ('fragment', 2, 4, 5, 'giant letters cropped by the frame (only their tops show), pure texture'),
    ('footer', 3, 7, 12, 'the giant word at the bottom; usually the headline again'),
    ('body', 250, 700, 1500, 'running text in the columns; it repeats to fill, so it only needs to read well'),
]
DESCENDERS = set('gjpqy,;')
IMAGE_MODES = ('object', 'photo')


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=None):
    path = path or os.environ.get('SHRED_BRIEF') or BRIEF
    user = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    return merge(DEFAULTS, user)


def hex_rgb(h):
    h = h.strip().lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def srgb_to_lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin(h):
    return tuple(srgb_to_lin(c) for c in hex_rgb(h))


def luminance(h):
    r, g, b = lin(h)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def out_dir():
    return os.path.join(ROOT, 'out')


def build_dir(*p):
    return os.path.join(ROOT, 'build', *p)
