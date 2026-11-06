"""Publish one ToolGuest tool a day to Dev.to and an optional social webhook.

No LLM. Each run:

  1. fetches toolguest.com and reads the tool cards (slug, name, description)
  2. picks today's tool from the date, so it rotates through every tool and
     only repeats once all of them have had a turn
  3. writes a Dev.to article, a Reddit self-post and X / LinkedIn copy
  4. publishes to Dev.to when DEVTO_API_KEY is set
  5. posts Reddit / X / LinkedIn / Medium through SOCIAL_WEBHOOK_URL when set
     (Ayrshare, Postiz, Make, n8n - one webhook reaches all of them)
  6. always records the result as a single GitHub issue, so the copy for the
     platforms that were not automated is still there to paste, and nothing is
     lost when the sandbox filesystem is discarded

Platform reality (checked November 2026): Dev.to is the only platform with a
free write API. Medium's API is deprecated, Hashnode's is paid, X's free tier
cannot post, LinkedIn needs a gated scope, and automated Reddit self-promotion
gets accounts banned. So those go out through the optional webhook or stay as
copy for a human. Nothing here posts to a platform that is not configured.

Env injected by the automation service:
  AGENT_SERVER_URL / OPENHANDS_CLOUD_API_URL + SANDBOX_ID + SESSION_API_KEY  -> secrets
  AUTOMATION_CALLBACK_URL + AUTOMATION_CALLBACK_API_KEY + AUTOMATION_RUN_ID -> completion callback
"""

import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

BASE = "https://toolguest.com"
REPO = "aamiraj60/25tools"
ISSUE_TITLE = "ToolGuest distribution"
ISSUE_LABEL = "distribution"
UA = {"User-Agent": "ToolGuest-Distribution/1.0"}
DEVTO_ENDPOINT = "https://dev.to/api/articles"

# Slug -> platform tags for the Dev.to article. Dev.to allows at most 4 tags,
# lowercase alphanumeric only.
CATEGORY_TAGS = {
    "YouTube & Creator": ["youtube", "video", "creators", "productivity"],
    "AI & Text": ["ai", "writing", "productivity", "tools"],
    "Developer & Utilities": ["webdev", "programming", "productivity", "tools"],
    "Media & Business": ["design", "business", "productivity", "tools"],
    "General": ["tools", "productivity", "webdev", "creators"],
}

CATEGORY_HINTS = {
    "youtube": "YouTube & Creator",
    "video": "YouTube & Creator",
    "thumbnail": "YouTube & Creator",
    "shorts": "YouTube & Creator",
    "creator": "YouTube & Creator",
    "ai-": "AI & Text",
    "humanizer": "AI & Text",
    "case-": "AI & Text",
    "word-": "AI & Text",
    "hash-": "AI & Text",
    "font-": "AI & Text",
    "lorem": "AI & Text",
    "markdown": "AI & Text",
    "diff-": "AI & Text",
    "json": "Developer & Utilities",
    "qr-": "Developer & Utilities",
    "password": "Developer & Utilities",
    "base64": "Developer & Utilities",
    "epoch": "Developer & Utilities",
    "meta-tag": "Developer & Utilities",
    "slug": "Developer & Utilities",
    "aspect-ratio": "Developer & Utilities",
    "image": "Media & Business",
    "heic": "Media & Business",
    "invoice": "Media & Business",
    "color": "Media & Business",
}


# --------------------------------------------------------------------- helpers

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


def optional_secret(name):
    try:
        return get_secret(name)
    except Exception:
        return ""


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
    except Exception as e:  # noqa: BLE001
        print(f"Callback error: {e}")


def http_json(method, url, payload=None, headers=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    merged = dict(UA)
    merged.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=merged, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw else {}


# ------------------------------------------------------------------ site parse

class ToolParser(HTMLParser):
    """Tool cards are <a href="/slug"> wrapping an <h3> name and <p> description."""

    def __init__(self):
        super().__init__()
        self.tools = []
        self._href = None
        self._field = None
        self._name = []
        self._desc = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if re.fullmatch(r"/[a-z0-9-]+/?", href) and href not in ("/", "/blog"):
                self._href = href.strip("/")
                self._name, self._desc = [], []
        elif self._href and tag == "h3":
            self._field = "name"
        elif self._href and tag == "p":
            self._field = "desc"

    def handle_data(self, data):
        if self._field == "name":
            self._name.append(data)
        elif self._field == "desc":
            self._desc.append(data)

    def handle_endtag(self, tag):
        if tag in ("h3", "p"):
            self._field = None
        elif tag == "a" and self._href:
            name = " ".join("".join(self._name).split())
            if name:
                self.tools.append({
                    "slug": self._href,
                    "name": name,
                    "description": " ".join("".join(self._desc).split()),
                })
            self._href, self._field = None, None


def category_for(slug):
    for needle, category in CATEGORY_HINTS.items():
        if needle in slug:
            return category
    return "General"


def fetch_tools():
    req = urllib.request.Request(BASE, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    parser = ToolParser()
    parser.feed(html)
    seen = {}
    for tool in parser.tools:
        seen.setdefault(tool["slug"], tool)
    tools = [
        {
            "slug": t["slug"],
            "name": t["name"],
            "description": t["description"],
            "category": category_for(t["slug"]),
            "url": f"{BASE}/{t['slug']}",
        }
        for t in sorted(seen.values(), key=lambda t: t["slug"])
    ]
    if not tools:
        raise RuntimeError("No tools parsed - the homepage markup may have changed.")
    return tools


def pick_tool(tools):
    # Derived from the date, so no state has to survive between runs.
    return tools[datetime.date.today().toordinal() % len(tools)]


# ------------------------------------------------------------- content builder

def build_content(tool):
    name, desc = tool["name"], tool["description"].rstrip(".")
    url, category = tool["url"], tool["category"]
    tags = CATEGORY_TAGS.get(category, CATEGORY_TAGS["General"])

    article = f"""---
title: "{name}: {desc}"
tags: {json.dumps(tags)}
canonical_url: "{url}"
---

**The problem**

{desc}. The tools that do this usually want an account, an upload or a
watermark before they show you anything.

**The fix**

[{name}]({url}) does it in the browser. Free, no signup, and nothing leaves
your machine. Open the page, do the thing, close the tab.

**How it works**

1. Open [{name}]({url}).
2. Paste or drop what you have.
3. Copy the result. That is the whole flow.

**When it helps**

- When you need this once, right now, without starting a trial.
- When the input is something you would rather not upload to a server.
- When a paid tool would be overkill for a single job.

**Try it**

[{url}]({url})

*Everything runs in your browser, so your data never leaves your device.*
"""

    reddit = f"""title: {name} - {desc}

I kept needing this and every tool I found wanted a signup first, so I built
one that runs entirely in the browser: {url}

No account, nothing uploaded. Feedback welcome - especially if there is a case
it does not handle yet.

(Check the subreddit's self-promotion rules before posting this.)
"""

    linkedin = f"""{name} - {desc}

Most tools for this ask you to create an account before they do anything.
This one runs fully in the browser: no signup, no upload, nothing stored.

{url}"""

    return {
        "article": article,
        "reddit": reddit,
        "x": [trim_x(f"{name}: {desc} - runs in your browser, no signup, nothing uploaded. {url}"),
              trim_x(f"Needed this again. Every tool wanted an account first. Built one that doesn't: {url}")],
        "linkedin": linkedin,
    }


def trim_x(text, limit=280):
    """Keep an X post under the limit without ever cutting the URL off."""
    if len(text) <= limit:
        return text
    url = text.rsplit(" ", 1)[-1]
    head = text[: limit - len(url) - 4].rstrip(" ,-")
    return f"{head}... {url}"


def parse_front_matter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                meta[key.strip()] = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
            else:
                meta[key.strip()] = value.strip("\"'")
    return meta, text[end + 4:].lstrip("\n")


# ------------------------------------------------------------------- publishers

def publish_devto(article_md, dry_run):
    key = optional_secret("DEVTO_API_KEY")
    if not key:
        return {"status": "skipped", "reason": "DEVTO_API_KEY not set"}
    meta, body = parse_front_matter(article_md)
    payload = {"article": {
        "title": meta.get("title", "Untitled"),
        "body_markdown": body,
        "published": True,
        "tags": (meta.get("tags") or [])[:4],
        "canonical_url": meta.get("canonical_url", ""),
    }}
    if dry_run:
        return {"status": "dry-run", "title": payload["article"]["title"]}
    try:
        created = http_json("POST", DEVTO_ENDPOINT,
                            payload, {"api-key": key, "Content-Type": "application/json"})
        return {"status": "published", "url": created.get("url", "")}
    except urllib.error.HTTPError as e:
        return {"status": "failed", "error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "error": str(e)}


def publish_social(content, dry_run):
    url = optional_secret("SOCIAL_WEBHOOK_URL")
    if not url:
        return {"status": "skipped", "reason": "SOCIAL_WEBHOOK_URL not set"}
    token = optional_secret("SOCIAL_WEBHOOK_TOKEN")
    payload = {
        "platforms": ["reddit", "x", "linkedin", "medium"],
        "reddit": content["reddit"],
        "x": content["x"],
        "linkedin": content["linkedin"],
    }
    if dry_run:
        return {"status": "dry-run", "platforms": payload["platforms"]}
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        http_json("POST", url, payload, headers)
        return {"status": "published"}
    except urllib.error.HTTPError as e:
        return {"status": "failed", "error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "error": str(e)}


# --------------------------------------------------------------- github report

def gh_request(method, path, payload=None):
    token = get_secret("GIithub_publish")
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "toolguest-distribution",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def report_issue(body):
    """Update the single distribution issue, creating it on the first run."""
    try:
        issues = gh_request("GET", f"/repos/{REPO}/issues?state=open&labels={ISSUE_LABEL}&per_page=50")
    except urllib.error.HTTPError:
        issues = []
    existing = next((i for i in issues if i.get("title") == ISSUE_TITLE), None)
    if existing:
        gh_request("PATCH", f"/repos/{REPO}/issues/{existing['number']}", {"body": body})
        return existing["html_url"]
    try:
        created = gh_request("POST", f"/repos/{REPO}/issues",
                             {"title": ISSUE_TITLE, "body": body, "labels": [ISSUE_LABEL]})
    except urllib.error.HTTPError:
        created = gh_request("POST", f"/repos/{REPO}/issues", {"title": ISSUE_TITLE, "body": body})
    return created["html_url"]


def build_report(today, tool, content, devto, social, issue_url):
    def line(name, result):
        if result["status"] == "published":
            return f"**{name}**: published {result.get('url', '')}".rstrip()
        if result["status"] == "dry-run":
            return f"**{name}**: dry-run"
        return f"**{name}**: {result['status']} - {result.get('reason') or result.get('error', '')}"

    return f"""## ToolGuest distribution {today}

Tool: **[{tool['name']}]({tool['url']})** ({tool['category']})

| Platform | Result |
|---|---|
| Dev.to | {line('Dev.to', devto)} |
| Reddit / X / LinkedIn / Medium | {line('Social', social)} |

### Dev.to article

```markdown
{content['article']}
```

### Reddit self-post

```text
{content['reddit']}
```

### X posts

```text
1. {content['x'][0]}
2. {content['x'][1]}
```

### LinkedIn post

```text
{content['linkedin']}
```

---
_Generated by the ToolGuest distribution automation{'. This issue is updated in place each run.' if issue_url else '.'}_
"""


# ------------------------------------------------------------------------ main

def main():
    dry_run = "--dry-run" in sys.argv
    today = datetime.date.today().isoformat()

    tools = fetch_tools()
    tool = pick_tool(tools)
    content = build_content(tool)
    print(f"Found {len(tools)} tools. Today's pick: {tool['name']} -> {tool['url']}")

    devto = publish_devto(content["article"], dry_run)
    social = publish_social(content, dry_run)

    print(f"Dev.to: {devto['status']} {devto.get('url', '')}".rstrip())
    print(f"Social: {social['status']} {social.get('reason', '')}".rstrip())

    issue_url = ""
    if not dry_run:
        issue_url = report_issue(build_report(today, tool, content, devto, social, "issue"))
        print(f"Report: {issue_url}")

    if any(r["status"] == "failed" for r in (devto, social)):
        raise RuntimeError("One or more platforms failed to publish")


if __name__ == "__main__":
    try:
        main()
        fire_callback("COMPLETED")
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        fire_callback("FAILED", str(exc))
        sys.exit(1)
