# 25tools — toolguest.com

Static tool site. 27 HTML pages, no build step, no framework.

- Live: https://toolguest.com
- Vercel project: `25tools` (team `mk-aamir`), region `lhr1`
- Vercel is **git-linked** to this repository, so **pushing to `main` deploys to
  production**. There is no separate manual upload step.

Because of that link, never push a half-finished change to `main`. Work on a
branch and open a pull request.

## What is served and what is not

Vercel publishes every file in the repository by default. `.vercelignore` keeps
the internal files out of the served output:

```
AGENTS.md  README.md  .gitignore  automation/  tools/  .github/
```

Anything not listed there becomes publicly readable at
`https://toolguest.com/<path>`. Add to `.vercelignore` before committing notes,
scripts, or tooling.

## Adding a tool

Adding a tool means touching **three** places:

1. the new page `<slug>.html`
2. the `CATEGORIES` array in `index.html` (name, slug, desc, tags, icon)
3. `sitemap.xml`

### Search behaviour

`index.html` search is entirely client-side and filters the `CATEGORIES` data
on name, description, slug, category title and tags (`computeResults`). Three
surfaces share one `query` state and one `render()` pass: the hero input, the
directory filter and the ⌘K palette.

The hero input also drives `renderHeroSuggest()`, an inline dropdown that shows
the top 6 matches directly under the box. It exists because the directory card
list sits far below the fold — on a 900 px viewport the first card is ~2100 px
down — so without it a keystroke produced no visible change and search looked
broken. Keep the dropdown in the `render()` pass and keep its items in the
`setActive()` highlight loop (`#heroSuggest .hero-suggest-item`).

### Check whether it already exists first

Adding a page that already exists silently overwrites it.

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://raw.githubusercontent.com/aamiraj60/25tools/main/<slug>.html"
# 200 = already there (edit it)   404 = new (create it)
```

### File naming

One file per tool, named after the URL slug with a `.html` extension:

| Live URL | File in this repo |
|---|---|
| `/font-changer` | `font-changer.html` |
| `/hash-generator` | `hash-generator.html` |
| `/heic-to-jpg` | `heic-to-jpg.html` |
| `/epoch-converter` | `epoch-converter.html` |
| `/` | `index.html` |

Lowercase, hyphen-separated, `.html` suffix. The slug must match the one used in
`index.html` and `sitemap.xml`.

## Which token to use

`GITHUB_TOKEN` in this environment is a GitHub App token (`ghu_...`) and is
**read-only** — pushes fail with `403 Resource not accessible by integration`.

Use **`GIithub_publish`** (a classic PAT) for every write: clone URLs, `git push`
and the REST API. `gh` CLI and the `create_pr` tool default to `GITHUB_TOKEN`, so
pass the token explicitly:

```bash
git clone "https://x-access-token:${GIithub_publish}@github.com/aamiraj60/25tools.git"

curl -X POST -H "Authorization: token ${GIithub_publish}" \
  https://api.github.com/repos/aamiraj60/25tools/issues -d @issue.json
```

## Site conventions

Every page is self-contained HTML that pulls a shared bundle:

```html
<link rel="stylesheet" href="/assets/fonts.css" />
<link rel="stylesheet" href="/assets/tailwind.css" />
<script src="/assets/rating-widget.js" defer></script>
<script src="/assets/related.js" defer></script>
```

`assets/tailwind.css` is the precompiled, purged Tailwind build. It replaces the
Tailwind Play CDN (`assets/tailwind.js`, now deleted) which shipped a ~407 KB
runtime JIT compiler that had to download, compile and inject styles before the
first paint. The static sheet is ~110 KB (~18 KB gzipped) and is a plain
stylesheet, so it renders immediately.

**Put the `tailwind.css` link at the very end of `<head>`.** The Play CDN
appended its generated `<style>` to the end of `<head>`, so page-level `<style>`
blocks appear *before* it and win specificity ties against Tailwind utilities
(e.g. a page's `.pill { display: inline-flex }` must beat Tailwind's
`.hidden { display: none }`). A link earlier in `<head>` reverses that order and
breaks such pages.

Rebuild the stylesheet after adding or renaming any utility class — a class that
is not in the build simply does not exist:

```bash
python3 tools/build-css.py   # regenerates assets/tailwind.css
```


- `vercel.json` sets `cleanUrls: true`, so pages are served at `/<slug>`, not
  `/<slug>.html`. **Link with clean URLs** (`href="/hash-generator"`), never
  `.html` — the `.html` form costs a 308 redirect hop.
- **Lead every asset path with `/`.** A clean URL has no directory for a
  relative path to resolve against, so `href="icon-192.png"` asks for
  `/icon-192.png` only by luck and breaks the moment a page moves deeper. The
  icon, manifest and stylesheet links are all root-absolute for this reason.
- `assets/fonts.css` holds one `@font-face` per family, weight and subset.
  Keep it deduplicated — repeated rules for the same family and weight are
  dead weight the browser still has to parse.
- Third-party scripts (`lucide.js`, `jspdf`, `qr-code-styling`, the Markdown
  engine) carry `defer` so they never block parsing. `defer` scripts execute
  after the document is parsed but **before** `DOMContentLoaded`, in document
  order. Any inline code that calls one of these libraries at parse time must
  therefore guard the call — `if (window.lucide) lucide.createIcons();` — or move
  it into a `DOMContentLoaded` handler. Otherwise it throws `X is not defined`.
- `robots.txt` deliberately allows AI crawlers (GPTBot, OAI-SearchBot,
  PerplexityBot, ClaudeBot, Google-Extended, Bingbot, Applebot). Keep it that way.
- `llms.txt` is a plain-text summary for answer engines.
- Every page carries the same icon set (`/favicon.ico`, `/icon-192.png`,
  `/icon-512.png`, `/apple-touch-icon.png`, `/site.webmanifest`) and a
  `theme-color` pair, one per colour scheme. Add both when you add a page.

## Logo and icons

The brand mark is the uploaded artwork `ToolGuest.png` (dark navy-to-cyan on
transparency, natural aspect **1.317**). Everything else derives from it, and
`tools/` rebuilds every derived asset so they can never drift apart:

- `logo.png` — the artwork at 384 px wide as a **truecolour** PNG. Keep it
  truecolour: quantising it to a 256-colour palette shifts the gradient and
  visibly changes the mark's colours. 384 px is ~7x the 40 px header, so it
  stays sharp on retina screens.
- `icon-192.png`, `icon-512.png`, `apple-touch-icon.png` — the mark centred on
  a **fully transparent** canvas at 86% width, natural aspect kept.
- `icon-maskable-512.png` — the same transparent canvas at 56% width, so it
  survives Android's circular crop. `site.webmanifest` points its `maskable`
  entry here.
- `favicon.ico` — the same transparent mark at 16/32/48/64 px.

No icon carries a plate or any background. The trade-off is deliberate: the
mark is dark navy-to-cyan, so on a dark browser tab or a dark Google result it
has little contrast. Transparency was chosen over tab legibility. If tab
visibility ever needs to win, add a plate (or an outlined variant) in
`tools/build-icons.py` — never hand-edit the icon files.

```bash
python3 tools/build-icons.py   # rebuild the whole icon set from logo.png
python3 tools/build-og.py      # rebuild assets/og/*.png from each page's own tags
```

**Nothing in the site paints a background behind the mark.** The header logo,
the Open Graph previews and the icon set are all plate-free:

- **Header** — `.tg-logo` in `logo.css` carries no background, border or plate.
  The mark is dark navy-to-cyan and its navy half sinks into a near-black page,
  so `logo.css` recolours it for dark mode with
  `filter: invert(1) hue-rotate(180deg)` — a hue-preserving transform that
  leaves the mark fully transparent. The mark keeps its own colours on the
  light theme. Do not reintroduce a `background` or `box-shadow` plate on
  `.tg-logo`.
  - **Do not add `brightness()` or `saturate()` to this filter.** The two
    functions are exact: rendered, the mark measures hue 231 / saturation 0.95,
    which is the artwork's own hue 231 / saturation 0.98. Any brightness lift
    clips the light half of the gradient towards white and drags the hue
    towards green — `brightness(1.6)` measured hue 98 / saturation 0.43, i.e.
    the brand blue turned into a washed-out grey-mint. Keep it to
    `invert(1) hue-rotate(180deg)`.
- **Open Graph previews** — the `.brand img` rule in `tools/build-og.py` uses
  the same filter, because the preview card is dark too.
- **Icons** — fully transparent, as described above.

Each placement is a single `<img src="/logo.png" class="tg-logo">`. The site has
three dark-mode conventions — `html.dark` (most pages), `html[data-theme="dark"]`
and `body.dark` — and `logo.css` covers all three. All dark modes are
class-based; no page switches theme with a `prefers-color-scheme` media query,
so the class selectors cover every case.

## Open Graph previews

`assets/og/<slug>.png` is the 1200x630 preview for each page, served to social
cards, chat apps and Google. `tools/build-og.py` renders each one with headless
Chromium from a template that reuses the site logo, the self-hosted Inter
webfont and the brand gradient, and it reads the title and description out of
that page's own `og:title` and `og:description`. Edit those tags and re-run the
script — never hand-edit a preview image, and never let a preview show different
copy from the page it points at.

## UK English

The site targets UK readers. Write `colour`, `behaviour`, `analyse`, `centre`,
`organise`, `customise`, `labelled`, `cancelled`, `favourite`, `grey`.

Use `<html lang="en-GB">`. Every page must match.

Three deliberate exceptions:

- **`Color Palette Generator`** is a product name. Leave it as-is, including in
  titles, `og:` tags and JSON-LD.
- **`Entropy Analyzer`** on `password-checker` is likewise a product name and a
  deliberate US-spelling keyword. The target query is
  *password strength checker and entropy analyzer*, and `analyzer` is the
  higher-volume spelling in the US market, so the page keeps it in the title,
  H1, `og:` tags and JSON-LD. Body prose still uses the UK verb — `analyse`,
  `analysed`, `analysis`. The site-health audit will report `analyzer` as a US
  spelling; that is expected and should not be "corrected".
- `scroll-behavior` is a CSS property and `Math.floor` is a JavaScript call.
  Never "correct" code.

Words such as `dialog`, `meter` (a device), `practice` (noun) and `program` are
correct in UK English and must not be changed.

## Dates must never go stale

A past year in prose reads as an abandoned site, and search engines rank it that
way. The footer year is set by JavaScript from `assets/rating-widget.js`, which
every page loads, so the copyright line maintains itself.

When you write a year into body copy, use the current year. Three numbers are
exempt because they describe the tools, not the site: **2038** (Unix timestamp
overflow), **2048** (QR bitmap size) and **1970** (the epoch). The health audit
knows to skip them.

## Target markets

The site is English-only, aimed at the UK, USA, Germany, Ireland, France, the
Netherlands, Spain, Italy, Poland, Sweden, Canada and Australia.

Two signals carry that, and both are on every page:

- `hreflang` declares `en-GB`, `en-US`, `en` and `x-default`, all pointing at
  the same URL. One English page serves every market; the tags tell engines
  which countries it is for.
- `areaServed` on each tool's `SoftwareApplication` block lists the twelve
  countries.

`<html lang>` is `en-GB` and `og:locale` is `en_GB` on every page, including
`epoch-converter`. Keep them consistent.

If a language is ever translated, that is a different job: it needs a real
localised URL per language and its own `hreflang` pair. Do not fake it by
adding a `lang` attribute.

## SEO / AEO content block

Every tool page carries one `<section class="tool-seo-content" id="guide">`
placed immediately before the `<!-- TF-RELATED -->` marker. It is the page's
long-form, answer-engine-ready content and it is built from a fixed shape so
the whole site stays consistent:

1. an intro block (`seo-eyebrow` + `h2` + paragraphs);
2. a **Quick answer** callout (`.seo-aeo`) holding a 40–50 word entity
   definition — the paragraph an AI answer engine is most likely to quote;
3. a "Why it matters" block with a `seo-grid cols-3` of `.seo-card`s;
4. a head-to-head comparison `.seo-table`;
5. Tier-1 geo cards (`.seo-card` with a `.seo-city` label) for the USA, UK,
   Germany, Canada, Australia and Spain;
6. a `.seo-faq` `<details>` accordion mirroring the page's FAQPage JSON-LD.

The supporting CSS lives at the end of each page's `<style>` block, introduced
by the `/* ---- ToolGuest SEO / AEO content system ---- */` comment. Its
dark-mode selectors cover all three site conventions at once —
`html.dark`, `html[data-theme="dark"]` and `body.dark` — so the same CSS works
on every page.

Rendered visible word count must be **1,200+** on every tool page. The health
audit measures this from the rendered text, not the source.

Two more requirements sit alongside the content block:

- **`FAQPage` JSON-LD.** Every page's `@graph` needs a `FAQPage` whose
  `mainEntity` questions match the visible FAQ, and a `SoftwareApplication`
  (a page may use `"@type": ["WebApplication", "SoftwareApplication"]`).
- **A theme toggle.** Every page has a `<button id="themeBtn">` (or
  `#themeToggle`) that flips the theme and persists the choice. Most pages
  store it under `localStorage['tg-theme']`; `ai-humanizer` uses
  `localStorage['theme']`. The default is dark, and a tiny inline script in
  `<head>` applies the stored choice before first paint to avoid a flash.

## Automations

Two cron automations keep the site healthy. Both run without an LLM.

**ToolGuest GitHub Backup (check then upload)** — weekly, Sunday 02:30 UTC.

Reads `sitemap.xml`, fetches every page and asset over HTTP, and compares each
against this repository. It uploads only what is **missing or different**. If
nothing changed it does nothing. It never deletes a file, so `AGENTS.md` and
`automation/` are safe. The live site is the source of truth, so a tool
published outside Git is still captured.

**ToolGuest Site Health + UK English Audit** — every 6 hours.

Audits all 27 pages for HTTP status, titles, descriptions, canonicals, H1s,
Open Graph tags and JSON-LD, then reads visible text only to flag US spellings
and stale years. It updates a single GitHub issue titled `Site health report`
(labelled `site-health`) rather than opening a new one each run.

Both scripts live in `automation/` so the automations can be rebuilt from the
repository if the deployment is lost.
