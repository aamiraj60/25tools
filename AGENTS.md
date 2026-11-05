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
<link rel="stylesheet" href="assets/fonts.css" />
<script src="assets/tailwind.js"></script>
<script src="/assets/rating-widget.js" defer></script>
<script src="assets/related.js" defer></script>
```

- `vercel.json` sets `cleanUrls: true`, so pages are served at `/<slug>`, not
  `/<slug>.html`. **Link with clean URLs** (`href="/hash-generator"`), never
  `.html` — the `.html` form costs a 308 redirect hop.
- `robots.txt` deliberately allows AI crawlers (GPTBot, OAI-SearchBot,
  PerplexityBot, ClaudeBot, Google-Extended, Bingbot, Applebot). Keep it that way.
- `llms.txt` is a plain-text summary for answer engines.

## UK English

The site targets UK readers. Write `colour`, `behaviour`, `analyse`, `centre`,
`organise`, `customise`, `labelled`, `cancelled`, `favourite`, `grey`.

Use `<html lang="en-GB">`. Every page must match.

Two deliberate exceptions:

- **`Color Palette Generator`** is a product name. Leave it as-is, including in
  titles, `og:` tags and JSON-LD.
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
