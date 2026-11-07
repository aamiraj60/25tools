"""Rebuild the site icon set from logo.png.

Every icon is the mark drawn straight onto a transparent canvas — no plate, no
background, nothing behind it — so the artwork sits on whatever the browser or
operating system draws behind it. The mark's own colours and its transparency
are never touched.

Note the trade-off this accepts: the mark is dark navy-to-cyan, so on a dark
browser tab or a dark search result it has little contrast. That is the
deliberate choice here — a fully transparent mark over a solid plate. If tab
visibility ever matters more than transparency, the fix is a plate or an
outlined variant, not a change to this script's transparency.

Writes favicon.ico, icon-192.png, icon-512.png, icon-maskable-512.png and
apple-touch-icon.png next to logo.png.

Usage:
    python3 tools/build-icons.py
"""

import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "logo.png")

# width of the mark as a fraction of the canvas. With no plate to inset from,
# the mark can use most of the canvas; the maskable entry stays smaller so it
# survives Android's circular crop.
SIZES = {
    "icon-192.png": (192, 0.86),
    "icon-512.png": (512, 0.86),
    "apple-touch-icon.png": (180, 0.86),
    # maskable icons must keep their content inside a 40% radius safe circle
    "icon-maskable-512.png": (512, 0.56),
}


def draw_icon(mark, size, width_fraction):
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    w = max(1, round(size * width_fraction))
    h = max(1, round(w * mark.height / mark.width))
    art = mark.resize((w, h), Image.LANCZOS)
    canvas.alpha_composite(art, ((size - w) // 2, (size - h) // 2))
    return canvas


def main():
    mark = Image.open(SRC).convert("RGBA")
    for name, (size, wf) in SIZES.items():
        out = os.path.join(ROOT, name)
        draw_icon(mark, size, wf).save(out, optimize=True)
        print(f"{name:24s} {size}x{size}  {os.path.getsize(out) // 1024}KB")

    # .ico with the sizes Windows, browsers and Google ask for. PIL downsamples
    # the base image, so hand it the largest frame and list every size.
    ico = os.path.join(ROOT, "favicon.ico")
    base = draw_icon(mark, 64, 0.90)
    base.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print(f"{'favicon.ico':24s} 16/32/48/64  {os.path.getsize(ico) // 1024}KB")


if __name__ == "__main__":
    main()
