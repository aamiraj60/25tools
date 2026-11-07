"""Rebuild assets/tailwind.css from the utility classes used in the pages.

The site used to load the Tailwind Play CDN (assets/tailwind.js) at runtime.
That build is a full JIT compiler: the browser had to download ~407 KB of
JavaScript, compile every class on the page, and inject the result as a <style>
tag before the first paint, which stalled rendering and hurt Core Web Vitals.

assets/tailwind.css is that same compiler output, precompiled once and purged
down to the classes the pages actually use (~110 KB, ~18 KB gzipped). Pages link
it as a normal stylesheet at the end of <head> — the same position the Play CDN
appends its <style> — so the cascade is unchanged.

Run this after adding or renaming utility classes in any page, otherwise the new
classes will not exist in the stylesheet.

Usage:
    python3 tools/build-css.py
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG = """\
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: ['%(root)s/*.html', '%(root)s/assets/*.js'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter','ui-sans-serif','system-ui','-apple-system','Segoe UI','sans-serif'],
        mono: ['JetBrains Mono','ui-monospace','SFMono-Regular','monospace'],
        serif: ['"Instrument Serif"','ui-serif','Georgia','serif'],
      },
      opacity: { '2':'.02','3':'.03','4':'.04','6':'.06','8':'.08','12':'.12' },
      keyframes: {
        fadeUp: {'0%%':{opacity:'0',transform:'translateY(10px)'},'100%%':{opacity:'1',transform:'translateY(0)'}},
        scan: {'0%%':{transform:'translateY(-120%%)'},'100%%':{transform:'translateY(220%%)'}},
        glow: {'0%%,100%%':{opacity:'0.5'},'50%%':{opacity:'0.9'}},
        toastIn: {'0%%':{opacity:'0',transform:'translateY(14px) scale(.96)'},'100%%':{opacity:'1',transform:'translateY(0) scale(1)'}},
        floaty: {'0%%,100%%':{transform:'translateY(0)'},'50%%':{transform:'translateY(-6px)'}},
      },
      animation: {
        fadeUp: 'fadeUp .5s cubic-bezier(0.16,1,0.3,1) both',
        scan: 'scan 3.5s linear infinite',
        glow: 'glow 3s ease-in-out infinite',
        toastIn: 'toastIn .28s cubic-bezier(.22,1,.36,1) forwards',
        floaty: 'floaty 6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
""" % {'root': ROOT}

INPUT = '@tailwind base;\n@tailwind components;\n@tailwind utilities;\n'


def main():
    work = os.path.join(ROOT, 'tools', '_css-build')
    os.makedirs(work, exist_ok=True)
    with open(os.path.join(work, 'package.json'), 'w') as fh:
        fh.write('{"name":"toolguest-css-build","private":true}\n')
    with open(os.path.join(work, 'tailwind.config.js'), 'w') as fh:
        fh.write(CONFIG)
    with open(os.path.join(work, 'input.css'), 'w') as fh:
        fh.write(INPUT)

    subprocess.run(['npm', 'install', '-D', 'tailwindcss@3.4.17'], cwd=work, check=True,
                   stdout=subprocess.DEVNULL)

    out = os.path.join(ROOT, 'assets', 'tailwind.css')
    subprocess.run([os.path.join(work, 'node_modules', '.bin', 'tailwindcss'),
                    '-c', os.path.join(work, 'tailwind.config.js'),
                    '-i', os.path.join(work, 'input.css'),
                    '-o', out, '--minify'], check=True)
    print('wrote %s (%d bytes)' % (out, os.path.getsize(out)))


if __name__ == '__main__':
    sys.exit(main())
