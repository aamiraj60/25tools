"""Rebuild the 1200x630 Open Graph preview images in assets/og/.

Renders each preview with headless Chromium from a template that reuses the
site's own logo, self-hosted Inter webfont and brand gradient, so a shared link
looks like the live page. The title and description are read straight out of
each page's own Open Graph tags, so a preview and its page cannot drift apart.

Usage:
    python3 tools/build-og.py            # rebuild every page
    python3 tools/build-og.py index.html # rebuild one page
"""

import glob
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "og")
CHROME = (
    shutil.which("chromium")
    or shutil.which("chromium-browser")
    or shutil.which("google-chrome")
)

TEMPLATE = """<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<link rel="stylesheet" href="{root}/assets/fonts.css">
<style>
  * {{ margin: 0; box-sizing: border-box; }}
  body {{
    width: 1200px; height: 630px; overflow: hidden; position: relative;
    background: #08080a; color: #fff; font-family: Inter, system-ui, sans-serif;
    -webkit-font-smoothing: antialiased;
  }}
  .glow {{ position: absolute; border-radius: 50%; filter: blur(90px); opacity: .5; }}
  .g1 {{ width: 620px; height: 620px; left: -180px; top: -260px; background: #6366f1; }}
  .g2 {{ width: 520px; height: 520px; right: -150px; top: -180px; background: #d946ef; opacity: .38; }}
  .g3 {{ width: 560px; height: 560px; right: 40px; bottom: -320px; background: #22d3ee; opacity: .3; }}
  .grid {{
    position: absolute; inset: 0; opacity: .07;
    background-image: linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px);
    background-size: 60px 60px;
  }}
  .wrap {{ position: relative; height: 100%; padding: 62px 76px; display: flex; flex-direction: column; }}
  .brand {{ display: flex; align-items: center; gap: 16px; }}
  .brand img {{ height: 52px; width: auto; background: #fff; border-radius: 10px; box-shadow: 0 0 0 7px #fff; }}
  .brand b {{ font-size: 30px; font-weight: 800; letter-spacing: -.03em; }}
  .body {{ margin-top: auto; margin-bottom: auto; padding-top: 22px; }}
  h1 {{
    font-size: {size}px; font-weight: 800; line-height: 1.08; letter-spacing: -.035em;
    max-width: 1000px; text-wrap: balance;
  }}
  h1 .grad {{
    background: linear-gradient(90deg, #818cf8, #e879f9, #67e8f9);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }}
  p {{ margin-top: 24px; font-size: 25px; line-height: 1.45; color: #a1a1aa; max-width: 940px; }}
  .foot {{ display: flex; align-items: center; gap: 14px; font-size: 21px; color: #d4d4d8; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: #34d399; }}
  .url {{ margin-left: auto; font-weight: 600; color: #fff; letter-spacing: -.01em; }}
  .bar {{ position: absolute; left: 0; right: 0; bottom: 0; height: 10px;
    background: linear-gradient(90deg, #6366f1, #d946ef, #22d3ee); }}
</style></head>
<body>
  <div class="glow g1"></div><div class="glow g2"></div><div class="glow g3"></div>
  <div class="grid"></div>
  <div class="wrap">
    <div class="brand">
      <img src="{root}/logo.png" alt="">
      <b>ToolGuest</b>
    </div>
    <div class="body">
      <h1>{title}</h1>
      <p>{desc}</p>
    </div>
    <div class="foot">
      <span class="dot"></span><span>Free &middot; Private &middot; No signup</span>
      <span class="url">toolguest.com</span>
    </div>
  </div>
  <div class="bar"></div>
</body></html>
"""


def field(src, pattern):
    m = re.search(pattern, src, re.S)
    if not m:
        return ""
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    text = text.replace("&amp;", "&").replace("&#39;", "'").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def build(path):
    src = open(path, encoding="utf-8").read()
    title = field(src, r'<meta property="og:title" content="([^"]*)"') or field(
        src, r"<title>(.*?)</title>"
    )
    desc = field(src, r'<meta property="og:description" content="([^"]*)"') or field(
        src, r'<meta name="description" content="([^"]*)"'
    )

    # Emphasise the trailing clause of a title ("A — B" / "A | B") in the brand
    # gradient, matching the hero on the site.
    head, tail, sep = title, "", ""
    for candidate in (" — ", " – ", " | "):
        if candidate in title:
            head, tail, sep = *title.rsplit(candidate, 1), candidate
            break
    if tail:
        title_html = f'{html.escape(head + sep)}<span class="grad">{html.escape(tail)}</span>'
    else:
        title_html = html.escape(title)

    size = 60 if len(title) <= 46 else 52 if len(title) <= 64 else 44
    page = TEMPLATE.format(
        root=ROOT, title=title_html, desc=html.escape(desc), size=size
    )

    slug = os.path.splitext(os.path.basename(path))[0]
    with tempfile.TemporaryDirectory() as tmp:
        page_path = os.path.join(tmp, f"{slug}.html")
        open(page_path, "w", encoding="utf-8").write(page)
        out = os.path.join(OUT, f"{slug}.png")
        subprocess.run(
            [
                CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
                "--hide-scrollbars", "--force-device-scale-factor=1",
                "--virtual-time-budget=3000", "--window-size=1200,630",
                f"--screenshot={out}", f"file://{page_path}",
            ],
            check=True, capture_output=True,
        )
        # Re-save losslessly: Chromium's PNG encoder leaves a lot of slack on
        # flat gradients, and this trims roughly a third off each file.
        Image.open(out).convert("RGB").save(out, optimize=True)
    return out, title


def main():
    args = sys.argv[1:]
    pages = args or sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "*.html"))
    )
    os.makedirs(OUT, exist_ok=True)
    for name in pages:
        out, title = build(os.path.join(ROOT, name))
        print(
            f"{os.path.basename(out):32s} {os.path.getsize(out) // 1024:4d}KB  {title[:58]}"
        )


if __name__ == "__main__":
    main()
