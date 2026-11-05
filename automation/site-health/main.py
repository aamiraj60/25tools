"""Audit toolguest.com: availability, SEO, copy quality, and UK English.

No LLM. Each run:

  1. reads the sitemap and fetches every page
  2. checks HTTP status, titles, descriptions, canonicals, H1s, Open Graph tags
     and JSON-LD structured data
  3. reads visible text only (never markup or script) and flags US spellings
     against a UK English list
  4. reports an overall health score and the exact page each problem is on

Findings are written to the workspace as site-health.json and site-health.md so
a human can read them, and a summary is printed to the run log.

Env injected by the automation service:
  AUTOMATION_CALLBACK_URL + AUTOMATION_CALLBACK_API_KEY + AUTOMATION_RUN_ID
"""

import concurrent.futures as cf
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter

BASE = "https://toolguest.com"
UA = {"User-Agent": "Mozilla/5.0 (compatible; toolguest-health)"}
OUT_JSON = "/tmp/site-health.json"
OUT_MD = "/tmp/site-health.md"

# Findings are published as a GitHub issue, because the sandbox filesystem is
# discarded when the run ends and would otherwise be invisible to the owner.
REPO = "aamiraj60/25tools"
ISSUE_TITLE = "Site health report"
ISSUE_LABEL = "site-health"

MAX_TITLE = 60
MAX_DESC = 158
MIN_DESC = 70

# Years that belong to the tool's subject rather than to the site's own copy.
# 2038 is the Unix timestamp overflow, 2048 a QR bitmap size, 1970 the epoch.
TECHNICAL_YEARS = {"1969", "1970", "2038", "2048"}
EXPECTED_LANG = "en-GB"

# US spellings that must be UK English. Word boundaries only, matched against
# visible text, so identifiers such as Math.floor and CSS properties are safe.
US_TO_UK = {
    r"\banalyz(e|es|ed|ing|er|ers)\b": "analyse",
    r"\bcolor\b": "colour",
    r"\bcolors\b": "colours",
    r"\bcolored\b": "coloured",
    r"\bcoloring\b": "colouring",
    r"\bbehavior(s|al)?\b": "behaviour",
    r"\borganiz(e|es|ed|ing|ation|ations)\b": "organise",
    r"\bcustomiz(e|es|ed|ing|ation)\b": "customise",
    r"\bcenter(s|ed)?\b": "centre",
    r"\bfavorite(s)?\b": "favourite",
    r"\b(honor|labor|neighbor|neighborhood)\b": "honour/labour/neighbour",
    r"\b(defense|offense)\b": "defence/offence",
    r"\b(canceled|traveling|modeling|labeled|signaled)\b": "cancelled/travelling/modelling/labelled",
    r"\bgray(s)?\b": "grey",
    r"\bcatalog(s)?\b": "catalogue",
    r"\bjewelry\b": "jewellery",
    r"\bmustache\b": "moustache",
    r"\baluminum\b": "aluminium",
    r"\bfiber(s)?\b": "fibre",
    r"\bliter(s)?\b": "litre",
    r"\bfulfill(ed|ing)?\b": "fulfil",
    r"\benroll(ed|ing|ment)?\b": "enrol",
    r"\binstallment(s)?\b": "instalment",
    r"\btraveled|traveler(s)?\b": "travelled/traveller",
}

# Words that are correct in UK English too, so they must not be flagged.
# "dialog" is the standard browser print dialog; "meter" is a measuring device
# (only the unit of length is "metre"); "practice" is the noun.
UK_OK = r"\b(dialog|dialogs|meter|meters|practice|practices|program|programs)\b"

# Proper nouns and product names that are spelled the US way on purpose.
BRAND_NAMES = ["Color Palette Generator", "color-palette-generator"]

# Strings that must never reach a visitor.
BROKEN_TEXT = {
    "undefined": r"\bundefined\b",
    "null": r"\bnull\b",
    "NaN": r"(?<![\w.])NaN(?![\w])",
    "[object Object]": r"\[object Object\]",
    "double-escaped entity": r"&amp;(amp|lt|gt|quot|#\d+);",
    "TODO": r"\bTODO\b",
    "FIXME": r"\bFIXME\b",
    "XXX": r"\bXXX\b",
    "TBD": r"\bTBD\b",
}


def get_secret(name):
    # Present directly when running interactively; fetched from the agent server
    # during a scheduled automation run.
    if os.environ.get(name):
        return os.environ[name]
    url = os.environ.get("AGENT_SERVER_URL", "").rstrip("/")
    key = os.environ.get("SESSION_API_KEY") or os.environ.get("OH_SESSION_API_KEYS_0", "")
    if url:
        url = f"{url}/api/settings/secrets/{name}"
    else:
        api = os.environ["OPENHANDS_CLOUD_API_URL"].rstrip("/")
        url = f"{api}/api/v1/sandboxes/{os.environ['SANDBOX_ID']}/settings/secrets/{name}"
    req = urllib.request.Request(url, headers={"X-Session-API-Key": key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode().strip()


def gh(method, path, payload=None):
    token = get_secret("GIithub_publish")
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


def publish_report(body, counts):
    """Keep one issue up to date rather than opening a new one each run."""
    marker = "<!-- site-health-report -->"
    body = f"{marker}\n\n{body}"
    title = ISSUE_TITLE
    watched = ("meta_problems", "us_spellings", "broken_text", "stale_years")
    if any(counts[k] for k in watched):
        title = f"{ISSUE_TITLE} — {sum(counts[k] for k in watched)} issue(s)"

    try:
        issues = gh("GET", f"/repos/{REPO}/issues?state=open&per_page=100")
    except Exception as e:
        print(f"  could not list issues: {e}")
        return None

    existing = next((i for i in issues if i.get("title", "").startswith(ISSUE_TITLE)), None)
    try:
        if existing:
            gh("PATCH", f"/repos/{REPO}/issues/{existing['number']}",
               {"title": title, "body": body})
            print(f"  updated issue #{existing['number']}")
            return existing["number"]
        created = gh("POST", f"/repos/{REPO}/issues",
                     {"title": title, "body": body, "labels": [ISSUE_LABEL]})
        print(f"  opened issue #{created['number']}: {created['html_url']}")
        return created["number"]
    except Exception as e:
        print(f"  could not publish issue: {e}")
        return None


def find_stale_years(slug, text, today_year):
    """Years written into the site's own copy that are no longer current.

    A past year in prose reads as an abandoned site, and search engines and
    answer engines treat it that way. Future years are left alone: a forecast or
    a copyright notice may legitimately name one.
    """
    out = []
    for m in re.finditer(r"\b(19[7-9]\d|20[0-9]{2})\b", text):
        y = m.group(1)
        if y in TECHNICAL_YEARS or int(y) >= today_year:
            continue
        ctx = re.sub(r"\s+", " ", text[max(0, m.start() - 60):m.end() + 60])
        out.append((slug, {"year": y, "context": ctx}))
    return out


def fire_callback(status="COMPLETED", error=None):
    url = os.environ.get("AUTOMATION_CALLBACK_URL", "")
    if not url:
        return
    body = {"status": status, "run_id": os.environ.get("AUTOMATION_RUN_ID", "")}
    if error:
        body["error"] = error
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ.get('AUTOMATION_CALLBACK_API_KEY', '')}",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception as e:
        print(f"callback error: {e}")


def get(url, timeout=45):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


def text_nodes(html):
    """Visible text only: everything outside <script>, <style> and tags."""
    out, pos = [], 0
    for m in re.finditer(r"(?is)<(script|style)\b[^>]*>.*?</\1>|<[^>]+>", html):
        seg = html[pos:m.start()]
        if seg.strip():
            out.append(seg)
        pos = m.end()
    tail = html[pos:]
    if tail.strip():
        out.append(tail)
    return out


def visible_text(html):
    txt = " ".join(text_nodes(html))
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&#39;", "'"), ("&quot;", '"'),
                 ("&lt;", "<"), ("&gt;", ">"), ("&mdash;", "—"), ("&hellip;", "…")]:
        txt = txt.replace(a, b)
    return re.sub(r"\s+", " ", txt).strip()


def meta(html, name):
    for pat in (
        r'<meta[^>]+name=["\']' + name + r'["\'][^>]*content=["\']([^"\']*)',
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*name=["\']' + name + r'["\']',
    ):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    return None


def prop(html, name):
    for pat in (
        r'<meta[^>]+property=["\']' + re.escape(name) + r'["\'][^>]*content=["\']([^"\']*)',
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*property=["\']' + re.escape(name) + r'["\']',
    ):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    return None


def jsonld_types(html):
    types, invalid = [], False
    for b in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(b.strip())
        except Exception:
            invalid = True
            continue
        for o in (data if isinstance(data, list) else [data]):
            if not isinstance(o, dict):
                continue
            if o.get("@type"):
                types.append(o["@type"])
            if isinstance(o.get("@graph"), list):
                types += [g.get("@type") for g in o["@graph"] if isinstance(g, dict)]
    return types, invalid


def slugs():
    _, body = get(f"{BASE}/sitemap.xml")
    out = [u.split("//", 1)[-1].split("/", 1)[-1].strip("/")
           for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body.decode("utf-8", "replace"))]
    if not out:
        raise RuntimeError("sitemap listed no pages")
    return out


def audit_page(slug):
    url = f"{BASE}/{slug}" if slug else f"{BASE}/"
    status, body = get(url)
    html = body.decode("utf-8", "replace")
    text = visible_text(html)
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    canon_m = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]*href=["\']([^"\']+)', html, re.I)
    lang_m = re.search(r"<html[^>]+lang=[\"']([^\"']+)", html, re.I)
    h1s = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip()
           for x in re.findall(r"(?is)<h1[^>]*>(.*?)</h1>", html)]
    types, invalid_ld = jsonld_types(html)

    problems = []
    if status != 200:
        problems.append(f"HTTP {status}")
    title = title_m.group(1).strip() if title_m else None
    desc = meta(html, "description")
    if not title:
        problems.append("no <title>")
    elif len(title) > MAX_TITLE:
        problems.append(f"title {len(title)} chars (max {MAX_TITLE})")
    if not desc:
        problems.append("no meta description")
    elif len(desc) > MAX_DESC:
        problems.append(f"description {len(desc)} chars (max {MAX_DESC})")
    elif len(desc) < MIN_DESC:
        problems.append(f"description only {len(desc)} chars")
    if not canon_m:
        problems.append("no canonical")
    if not h1s:
        problems.append("no <h1>")
    elif len(h1s) > 1:
        problems.append(f"{len(h1s)} <h1> tags")
    for p in ("og:title", "og:description", "og:image"):
        if not prop(html, p):
            problems.append(f"no {p}")
    lang = lang_m.group(1) if lang_m else None
    if not lang:
        problems.append("no lang attribute")
    elif lang != EXPECTED_LANG:
        problems.append(f'lang="{lang}" (expected {EXPECTED_LANG})')
    if invalid_ld:
        problems.append("invalid JSON-LD")
    if not types:
        problems.append("no structured data")

    # Scan a scrubbed copy so UK-valid words and product names are not flagged.
    # Replacements keep the same length, so context offsets stay correct.
    blank = lambda m: " " * len(m.group(0))
    scrubbed = re.sub(UK_OK, blank, text, flags=re.I)
    for brand in BRAND_NAMES:
        scrubbed = re.sub(re.escape(brand), blank, scrubbed, flags=re.I)

    us_hits = []
    for pat, uk in US_TO_UK.items():
        for m in re.finditer(pat, scrubbed, re.I):
            ctx = re.sub(r"\s+", " ", text[max(0, m.start() - 55):m.end() + 55])
            us_hits.append({"word": m.group(0), "suggest": uk, "context": ctx})

    broken = []
    for pat in BROKEN_TEXT:
        for m in re.finditer(BROKEN_TEXT[pat], text):
            ctx = re.sub(r"\s+", " ", text[max(0, m.start() - 55):m.end() + 55])
            broken.append({"marker": pat, "context": ctx})

    stale_years = find_stale_years(slug or "/", text, datetime.date.today().year)

    return {
        "slug": slug or "/", "status": status, "bytes": len(body),
        "title": title, "desc": desc, "lang": lang, "h1_count": len(h1s),
        "structured_data": types, "problems": problems,
        "us_spellings": us_hits, "broken_text": broken,
        "stale_years": [h for _, h in stale_years],
    }


def main():
    pages = slugs()
    print(f"auditing {len(pages)} pages from {BASE}")

    with cf.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(audit_page, pages))

    problems = [(p["slug"], i) for p in results for i in p["problems"]]
    us = [(p["slug"], h) for p in results for h in p["us_spellings"]]
    broken = [(p["slug"], b) for p in results for b in p["broken_text"]]
    stale = [(p["slug"], y) for p in results for y in p["stale_years"]]

    dup_titles = [(k, v) for k, v in Counter(p["title"] for p in results if p["title"]).items() if v > 1]
    dup_descs = [(k, v) for k, v in Counter(p["desc"] for p in results if p["desc"]).items() if v > 1]

    checked = len(pages) * 10
    score = max(0, round(100 * (checked - len(problems)) / checked))

    print()
    print("=" * 70)
    print(f"  SITE HEALTH: {score}/100   ({len(pages)} pages checked)")
    print("=" * 70)
    print(f"  meta problems     : {len(problems)}")
    print(f"  US spellings      : {len(us)}")
    print(f"  broken text       : {len(broken)}")
    print(f"  stale years       : {len(stale)}")
    print(f"  duplicate titles  : {len(dup_titles)}")
    print(f"  duplicate descs   : {len(dup_descs)}")

    if problems:
        print("\n  --- meta problems ---")
        for slug, issue in problems:
            print(f"    {slug:26} {issue}")
    if us:
        print("\n  --- US spellings (should be UK) ---")
        for slug, h in us:
            print(f"    {slug:26} [{h['word']}] -> {h['suggest']}")
            print(f"        …{h['context']}…")
    if broken:
        print("\n  --- broken text ---")
        for slug, b in broken:
            print(f"    {slug:26} [{b['marker']}] …{b['context']}…")
    if stale:
        print("\n  --- stale years (should be the current year) ---")
        for slug, y in stale:
            print(f"    {slug:26} [{y['year']}] …{y['context']}…")
    if not (problems or us or broken or stale):
        print("\n  no issues found")

    report = {
        "site": BASE, "score": score, "pages": len(pages),
        "counts": {"meta_problems": len(problems), "us_spellings": len(us),
                   "broken_text": len(broken), "stale_years": len(stale),
                   "duplicate_titles": len(dup_titles),
                   "duplicate_descriptions": len(dup_descs)},
        "meta_problems": [{"page": s, "issue": i} for s, i in problems],
        "us_spellings": [{"page": s, **h} for s, h in us],
        "broken_text": [{"page": s, **b} for s, b in broken],
        "stale_years": [{"page": s, **y} for s, y in stale],
        "duplicate_titles": [{"value": k, "count": v} for k, v in dup_titles],
        "duplicate_descriptions": [{"value": k, "count": v} for k, v in dup_descs],
        "pages_audited": results,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(report, f, indent=1)

    lines = [f"Automated audit of {BASE} by the *ToolGuest Site Health* automation.",
             "",
             f"**Score: {score}/100** across {len(pages)} pages.",
             "",
             f"| Check | Count |", "|---|---|",
             f"| Meta problems | {len(problems)} |",
             f"| US spellings (should be UK) | {len(us)} |",
             f"| Broken text | {len(broken)} |",
             f"| Stale years | {len(stale)} |",
             f"| Duplicate titles | {len(dup_titles)} |",
             f"| Duplicate descriptions | {len(dup_descs)} |",
             ""]

    if us:
        by_word = {}
        for slug, h in us:
            by_word.setdefault(f"{h['word']} → {h['suggest']}", []).append(slug)
        lines += ["## US spellings", "",
                  "The site targets UK readers. These should be UK English:", "",
                  "| Found | Should be | Pages |", "|---|---|---|"]
        for k, word_pages in sorted(by_word.items()):
            w, uk = k.split(" → ")
            unique = sorted(set(word_pages))
            pages_txt = ", ".join(f"`{s}`" for s in unique[:6])
            if len(unique) > 6:
                pages_txt += f" +{len(unique)-6} more"
            lines.append(f"| {w} | {uk} | {pages_txt} |")
        lines.append("")

    if problems:
        lines += ["## Meta problems", "", "| Page | Issue |", "|---|---|"]
        lines += [f"| `{s}` | {i} |" for s, i in problems]
        lines.append("")

    if broken:
        lines += ["## Broken text", "", "| Page | Marker | Context |", "|---|---|---|"]
        for s, b in broken:
            ctx = b["context"].replace("|", "\\|")[:120]
            lines.append(f"| `{s}` | `{b['marker']}` | …{ctx}… |")
        lines.append("")

    if stale:
        lines += ["## Stale years", "",
                  "These read as an out-of-date site and should be the current year:", "",
                  "| Page | Year | Context |", "|---|---|---|"]
        for s_, y in stale:
            ctx = y["context"].replace("|", "\\|")[:120]
            lines.append(f"| `{s_}` | {y['year']} | …{ctx}… |")
        lines.append("")

    if not (problems or us or broken or stale):
        lines += ["No issues found. The site passed every check.", ""]

    lines += ["---", f"*Updated by an AI agent (OpenHands) on each scheduled run.*"]

    body = "\n".join(lines)
    with open(OUT_MD, "w") as f:
        f.write(body)

    print(f"\nreport written to {OUT_JSON} and {OUT_MD}")
    publish_report(body, report["counts"])
    fire_callback("COMPLETED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        fire_callback("FAILED", str(e))
        sys.exit(1)
