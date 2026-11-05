# 25tools — toolguest.com

Static tool site. 27 HTML pages, no build step, no framework.

- Live: https://toolguest.com
- Vercel project: `25tools` (team `mk-aamir`), region `lhr1`
- Deploy: production has been published by **direct upload**, so this repo is a
  **backup mirror** of what is deployed, not the deploy source.

## Always push tool changes to GitHub

When you add or edit a tool page, **push it to this repository** before you finish.
The site's only other copy is the Vercel deployment, and that is easy to lose.

```bash
git clone "https://x-access-token:${GIithub_publish}@github.com/aamiraj60/25tools.git"
cd 25tools && git checkout -b add-<tool-name>
# ... edit files ...
git add -A && git commit -m "Add <tool name> tool"
git push -u origin add-<tool-name>
```

Then open a pull request. Do not push directly to `main` by hand; the daily
backup automation owns `main`.

### Before you add a tool, check whether it is already there

Adding a page that already exists silently overwrites it. Check first:

```bash
# does the file already exist on GitHub?
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://raw.githubusercontent.com/aamiraj60/25tools/main/<slug>.html"
# 200 = already uploaded (update it)   404 = new (create it)

# does the live site already serve it?
curl -s -o /dev/null -w "%{http_code}\n" "https://toolguest.com/<slug>"
```

Then push only what is actually new or changed. A tool added on the live site
is picked up by the backup automation on its next run even if you forget.

### File naming

One file per tool, named after the URL slug with a `.html` extension:

| Live URL | File in this repo |
|---|---|
| `/font-changer` | `font-changer.html` |
| `/hash-generator` | `hash-generator.html` |
| `/heic-to-jpg` | `heic-to-jpg.html` |
| `/epoch-converter` | `epoch-converter.html` |
| `/` | `index.html` |

Lowercase, hyphen-separated, `.html` suffix. The slug in the filename must match
the slug used in `index.html` and `sitemap.xml`.

## Which token to use

`GITHUB_TOKEN` in this environment is a GitHub App token (`ghu_...`) and is
**read-only** — pushes fail with `403 Resource not accessible by integration`.

Use **`GIithub_publish`** (a classic PAT) for any write: clone URLs, `git push`,
and the REST API. `gh` CLI and the `create_pr` tool both default to
`GITHUB_TOKEN`, so pass the token explicitly instead:

```bash
curl -X POST -H "Authorization: token ${GIithub_publish}" \
  https://api.github.com/repos/aamiraj60/25tools/pulls -d @pr.json
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
- Adding a tool means touching **three** places:
  1. the new page `<slug>.html`
  2. the `CATEGORIES` array in `index.html` (name, slug, desc, tags, icon)
  3. `sitemap.xml`
- `robots.txt` deliberately allows AI crawlers (GPTBot, OAI-SearchBot,
  PerplexityBot, ClaudeBot, Google-Extended, Bingbot, Applebot). Keep it that way.
- `llms.txt` is a plain-text summary for answer engines.

## Automatic backup

A cron automation mirrors the live production deployment into this repo daily.
It pulls the newest Vercel production deployment, diffs it against `main`, and
pushes only when something changed. It removes files that the site no longer
serves, so `main` always equals production.

It leaves `AGENTS.md`, `automation/`, and `.gitignore` alone.
