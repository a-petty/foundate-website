"""Generate the social preview image (og-image.jpg) and icons for the Foundate site.

Everything is drawn from the site's own fonts and the plinth-F mark; no source
artwork is needed. Pillow reads the woff2 files directly.

Usage: uv run --with pillow python -I tools/make_images.py docs/assets/fonts docs/assets
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

fonts = Path(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

PAPER = (0xF5, 0xF2, 0xEB)
INK = (0x1C, 0x1B, 0x18)
MUTED = (0x5F, 0x5B, 0x51)
GREEN = (0x1E, 0x4D, 0x3B)

ZILLA = fonts / "ZillaSlab-SemiBold.woff2"
MONO = fonts / "IBMPlexMono-Medium.woff2"
for f in (ZILLA, MONO):
    if not f.exists():
        sys.exit(f"missing font: {f}")

# Plinth F on a 32-unit canvas, the same geometry as the inline SVG favicon.
PLINTH = [(3, 24.5, 29, 29.5), (9, 3, 14, 21.5), (9, 3, 27, 8), (9, 13, 22, 17.5)]  # the F floats above its base


def plinth(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, fill) -> None:
    u = size / 32
    for x0, y0, x1, y1 in PLINTH:
        draw.rectangle((x + x0 * u, y + y0 * u, x + x1 * u, y + y1 * u), fill=fill)


def tracked(draw, xy, text, font, fill, tracking):
    """Draw text with letter-spacing (Pillow has none built in)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking
    return x


# 1. Open Graph image 1200x630: paper, plinth F, name, headline, mono footer.
OG_W, OG_H = 1200, 630
SS = 2  # supersample for crisp text edges
og = Image.new("RGB", (OG_W * SS, OG_H * SS), PAPER)
d = ImageDraw.Draw(og)
name_font = ImageFont.truetype(str(ZILLA), 108 * SS)
head_font = ImageFont.truetype(str(ZILLA), 62 * SS)
mono_font = ImageFont.truetype(str(MONO), 21 * SS)

x = 72 * SS
plinth(d, x, 66 * SS, 84 * SS, GREEN)
d.text((x, 206 * SS), "Foundate", font=name_font, fill=INK, anchor="la")
d.text((x, 354 * SS), "AI you can sign off on.", font=head_font, fill=INK, anchor="la")
foot_y = 548 * SS
tracked(d, (x, foot_y), "AI IMPLEMENTATION, PROVEN BEFORE IT SHIPS", mono_font, MUTED, 1.3 * SS)
right = "FOUNDATE.AI"
rw = sum(d.textlength(c, font=mono_font) + 1.3 * SS for c in right)
tracked(d, (OG_W * SS - x - rw, foot_y), right, mono_font, MUTED, 1.3 * SS)
og = og.resize((OG_W, OG_H), Image.LANCZOS)
og.save(out / "og-image.jpg", "JPEG", quality=90, optimize=True, progressive=True)


# 2. Icons: green rounded square with the plinth F in paper.
def icon(size: int) -> Image.Image:
    ss = 8
    big = size * ss
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    dd = ImageDraw.Draw(im)
    dd.rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 5 / 32, fill=GREEN)
    plinth(dd, 0, 0, big, PAPER)
    return im.resize((size, size), Image.LANCZOS)


icon(180).save(out / "apple-touch-icon.png", "PNG", optimize=True)
icon(32).save(out / "favicon-32.png", "PNG", optimize=True)
icon(192).save(out / "icon-192.png", "PNG", optimize=True)
icon(512).save(out / "icon-512.png", "PNG", optimize=True)

for p in sorted(out.iterdir()):
    if p.is_file():
        print(f"{p.name:24s} {p.stat().st_size/1024:8.1f} KB")
