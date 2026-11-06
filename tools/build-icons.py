"""Rebuild the site icon set from logo.png.

The mark is dark navy to cyan on transparency, so on a dark browser tab or in
Google's dark search results a transparent icon all but disappears. Every icon
is therefore drawn on a white rounded plate, the same treatment the dark theme
gives the header logo, which leaves the mark's own colours untouched and keeps
it legible on any background.

Writes favicon.ico, icon-192.png, icon-512.png, icon-maskable-512.png and
apple-touch-icon.png next to logo.png.

Usage:
    python3 tools/build-icons.py
"""

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "logo.png")
PLATE = (255, 255, 255, 255)

# width of the mark as a fraction of the canvas, and the plate corner radius
# as a fraction of the canvas
SIZES = {
    "icon-192.png": (192, 0.78, 0.22),
    "icon-512.png": (512, 0.78, 0.22),
    "apple-touch-icon.png": (180, 0.78, 0.22),
    # maskable icons must keep their content inside a 40% radius safe circle
    "icon-maskable-512.png": (512, 0.56, 0.50),
}


def draw_icon(mark, size, width_fraction, radius_fraction, plate=True):
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if plate:
        ImageDraw.Draw(canvas).rounded_rectangle(
            (0, 0, size - 1, size - 1),
            radius=round(size * radius_fraction),
            fill=PLATE,
        )
    w = max(1, round(size * width_fraction))
    h = max(1, round(w * mark.height / mark.width))
    art = mark.resize((w, h), Image.LANCZOS)
    canvas.alpha_composite(art, ((size - w) // 2, (size - h) // 2))
    return canvas


def main():
    mark = Image.open(SRC).convert("RGBA")
    for name, (size, wf, rf) in SIZES.items():
        out = os.path.join(ROOT, name)
        draw_icon(mark, size, wf, rf).save(out, optimize=True)
        print(f"{name:24s} {size}x{size}  {os.path.getsize(out) // 1024}KB")

    # .ico with the sizes Windows, browsers and Google ask for. PIL downsamples
    # the base image, so hand it the largest frame and list every size.
    ico = os.path.join(ROOT, "favicon.ico")
    base = draw_icon(mark, 64, 0.82, 0.24)
    base.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print(f"{'favicon.ico':24s} 16/32/48/64  {os.path.getsize(ico) // 1024}KB")


if __name__ == "__main__":
    main()
