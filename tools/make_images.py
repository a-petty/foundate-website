"""Generate the social preview image (og-image.jpg) and icons for the Foundate site.

The source PNG is the original "foundations" artwork; it appears only in the
right half of the social preview.

Usage: uv run --with pillow python -I tools/make_images.py <source_png> <out_assets_dir>
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

src = Path(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

INK = (0x18, 0x20, 0x1E)
DARK = (0x17, 0x20, 0x1E)
ACCENT = (0xD8, 0xFB, 0x78)
PAPER = (0xF7, 0xF8, 0xF4)

hero = Image.open(src).convert("RGB")
w, h = hero.size
print(f"source {w}x{h}")

# 1. Open Graph image 1200x630: dark panel with wordmark on the left, art on the right.
OG_W, OG_H = 1200, 630
og = Image.new("RGB", (OG_W, OG_H), DARK)
# right panel: art cropped to 600x630
panel_w = 600
scale = OG_H / h
art = hero.resize((round(w * scale), OG_H), Image.LANCZOS)
left = max(0, round(art.width * 0.68) - panel_w // 2)  # keep object-position 68% from the CSS
left = min(left, art.width - panel_w)
og.paste(art.crop((left, 0, left + panel_w, OG_H)), (OG_W - panel_w, 0))

draw = ImageDraw.Draw(og)
font_path = None
for cand in ("/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Helvetica.ttc"):
    if Path(cand).exists():
        font_path = cand
        break
print("font:", font_path)


def font(size, bold=False):
    if font_path is None:
        return ImageFont.load_default()
    # HelveticaNeue.ttc index 0 = Regular, index 1 = Bold (verified empirically below)
    try:
        return ImageFont.truetype(font_path, size, index=1 if bold else 0)
    except OSError:
        return ImageFont.truetype(font_path, size)


x = 72
# wordmark
wm = font(96, bold=True)
draw.text((x, 200), "foundate", font=wm, fill=PAPER)
wm_w = draw.textlength("foundate", font=wm)
badge_font = font(26, bold=False)
bx = x + wm_w + 18
by = 212
draw.rounded_rectangle((bx, by, bx + 54, by + 40), radius=6, outline=PAPER, width=2)
draw.text((bx + 27, by + 20), "AI", font=badge_font, fill=PAPER, anchor="mm")
# tagline
tag = font(40, bold=True)
draw.text((x, 322), "AI you can", font=tag, fill=ACCENT)
draw.text((x, 370), "sign off on.", font=tag, fill=ACCENT)
sub = font(22, bold=False)
draw.text((x, 452), "AI implementation, proven before it ships.", font=sub, fill=(0xB4, 0xC1, 0xB9))
draw.text((x, 484), "foundate.ai", font=sub, fill=(0xB4, 0xC1, 0xB9))
og.save(out / "og-image.jpg", "JPEG", quality=88, optimize=True, progressive=True)

# 2. Icons from the favicon SVG geometry (32-unit canvas): rounded rect + "F" glyph.
F_PATH = [(9, 8), (25, 8), (25, 13), (14, 13), (14, 17), (22, 17), (22, 22), (14, 22), (14, 27), (9, 27)]


def icon(size: int, padded: bool = False) -> Image.Image:
    ss = 8
    big = size * ss
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    unit = big / 32
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=6 * unit, fill=INK)
    d.polygon([(px * unit, py * unit) for px, py in F_PATH], fill=ACCENT)
    return im.resize((size, size), Image.LANCZOS)


icon(180).save(out / "apple-touch-icon.png", "PNG", optimize=True)
icon(32).save(out / "favicon-32.png", "PNG", optimize=True)
icon(192).save(out / "icon-192.png", "PNG", optimize=True)
icon(512).save(out / "icon-512.png", "PNG", optimize=True)

for p in sorted(out.iterdir()):
    print(f"{p.name:24s} {p.stat().st_size/1024:8.1f} KB")
