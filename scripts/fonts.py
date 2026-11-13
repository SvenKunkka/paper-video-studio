"""Resolve a font for the poster: a path to a .ttf/.otf file, or any Google Fonts family name (downloaded once
into build/fonts from the Google Fonts API, which serves open-licensed fonts)."""
import os, re, sys, urllib.request, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brief as B


def get(family, weight=400):
    if family.lower().endswith(('.ttf', '.otf')):
        p = family if os.path.isabs(family) else os.path.join(B.ROOT, family)
        if not os.path.exists(p):
            raise SystemExit(f'font file not found: {p}')
        return p
    d = B.build_dir('fonts')
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, f"{re.sub(r'[^A-Za-z0-9]+', '', family)}-{weight}.ttf")
    if os.path.exists(dst):
        return dst
    url = None
    for w in (weight, None):
        q = urllib.parse.quote_plus(family) + (f':wght@{w}' if w else '')
        try:
            css = urllib.request.urlopen(urllib.request.Request(
                f'https://fonts.googleapis.com/css2?family={q}', headers={'User-Agent': 'shred-kit'}), timeout=20).read().decode()
        except Exception:
            continue
        m = re.search(r"url\((https://[^)]+\.ttf)\)", css)
        if m:
            url = m.group(1)
            if w is None:
                print(f'note: "{family}" has no weight {weight}; using its regular weight', file=sys.stderr)
            break
    if not url:
        raise SystemExit(f'"{family}" is not a Google Fonts family (check the spelling on fonts.google.com), '
                         'or pass a path to a .ttf/.otf file')
    urllib.request.urlretrieve(url, dst)
    return dst


if __name__ == '__main__':
    print(get(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 400))
