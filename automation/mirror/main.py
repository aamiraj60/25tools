"""Back up the live toolguest.com site into the aamiraj60/25tools GitHub repo.

No LLM. Each run:

  1. reads the sitemap to find every page
  2. follows the pages, their stylesheets, and the paths the repo already tracks
     to build the full file list
  3. fetches each file over HTTP and compares it against the repository
  4. uploads only the files that are MISSING or DIFFERENT
  5. commits and pushes, but only when something actually changed

The live site is the source of truth, so a tool published outside Git is still
captured. Files that exist on GitHub but are no longer served are reported and
left untouched, so hand-written files such as AGENTS.md are never lost.

Env injected by the automation service:
  AGENT_SERVER_URL / OPENHANDS_CLOUD_API_URL + SANDBOX_ID + SESSION_API_KEY  -> secrets
  AUTOMATION_CALLBACK_URL + AUTOMATION_CALLBACK_API_KEY + AUTOMATION_RUN_ID -> completion callback
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "aamiraj60/25tools"
BRANCH = "main"
BASE = "https://toolguest.com"
REPO_DIR = "/tmp/site-repo"

# Platform config, never served as a static file.
NON_SERVED = {"vercel.json", ".vercelignore", "netlify.toml", ".htaccess"}

# Serverless function source. The live URL returns the function's response, not
# the file, so it must never be fetched over the site and compared.
NON_FETCHABLE = ("api/",)

# Repo-only paths: never mirrored, never deleted.
SKIP_TOP = {".git", ".github", "automation", "node_modules"}
SKIP_FILES = {".gitignore", "AGENTS.md", "README.md"}

# Referenced by convention rather than by markup.
CONVENTIONAL = [
    "favicon.ico", "robots.txt", "sitemap.xml", "llms.txt",
    "site.webmanifest", "apple-touch-icon.png", "icon-192.png",
]

# A real path: no JS interpolation, quotes, spaces or template syntax.
PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

UA = {"User-Agent": "Mozilla/5.0 (compatible; toolguest-backup)"}


def get_secret(name):
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


def fire_callback(status="COMPLETED", error=None):
    """Signal run completion. Called on every exit path.

    The timeout is deliberately short so a failed callback surfaces quickly
    instead of leaving the run in RUNNING until the service kills it.
    """
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


def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])} failed: {p.stderr.strip()[:400]}")
    return p.stdout


def fetch(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def try_fetch(url, timeout=30):
    try:
        return fetch(url, timeout=timeout)
    except Exception:
        return None


def page_slugs():
    """Every page the site publishes, from its sitemap. "" is the homepage."""
    xml = fetch(f"{BASE}/sitemap.xml").decode("utf-8", "replace")
    slugs = []
    for u in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml):
        slugs.append(u.split("//", 1)[-1].split("/", 1)[-1].strip("/"))
    if not slugs:
        raise RuntimeError("sitemap listed no pages")
    return slugs


def assets_from_html(slugs):
    """Local paths referenced by src/href in the pages."""
    found = set()
    for slug in slugs:
        html = try_fetch(f"{BASE}/{slug}" if slug else f"{BASE}/")
        if html is None:
            print(f"  warn: could not read page /{slug}")
            continue
        for m in re.findall(r'(?:src|href)="([^"]+)"', html.decode("utf-8", "replace")):
            if m.startswith(("http://", "https://", "//", "#", "mailto:", "tel:", "data:", "javascript:")):
                continue
            m = m.lstrip("/")
            if m and not m.endswith("/") and PATH_RE.match(m):
                found.add(m)
    return found


def css_candidates(base_dir, ref):
    """Plausible repo paths for a stylesheet reference, best guess first."""
    name = os.path.basename(ref)
    out = []
    if base_dir:
        out.append(f"{base_dir}/{ref}")
        # A leading segment that repeats the stylesheet's own directory, e.g.
        # assets/fa/all.min.css -> url(fa/font.woff2) -> assets/fa/font.woff2
        if ref.startswith(f"{os.path.basename(base_dir)}/"):
            out.append(f"{base_dir}/{ref.split('/', 1)[1]}")
        out.append(f"{base_dir}/{name}")
    out.append(ref)
    ordered, seen = [], set()
    for c in out:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def assets_from_css(assets):
    """Follow url(...) references inside stylesheets, e.g. the font files.

    Resolved by probing candidate URLs rather than by trusting CSS-relative
    rules, because the deployed layout does not always match the original
    package layout.
    """
    found = set()
    for a in sorted(assets):
        if not a.endswith(".css"):
            continue
        css = try_fetch(f"{BASE}/{a}")
        if css is None:
            print(f"  warn: could not read stylesheet {a}")
            continue
        base_dir = os.path.dirname(a)
        for ref in re.findall(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", css.decode("utf-8", "replace")):
            if ref.startswith(("http://", "https://", "//", "data:")):
                continue
            ref = ref.lstrip("/")
            if not PATH_RE.match(ref):
                continue
            for cand in css_candidates(base_dir, ref):
                if cand in assets or cand in found or try_fetch(f"{BASE}/{cand}") is not None:
                    found.add(cand)
                    break
    return found


def repo_paths(repo_dir):
    """Paths the repository already tracks, minus repo-only files."""
    out = set()
    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_TOP]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), repo_dir).replace(os.sep, "/")
            if rel.split("/")[0] in SKIP_TOP or rel in SKIP_FILES or rel in NON_SERVED:
                continue
            out.add(rel)
    return out


def build_targets(slugs, assets, tracked):
    """Map each repo path to the live URL it should be fetched from."""
    targets = {}
    for slug in slugs:
        targets[f"{slug}.html" if slug else "index.html"] = f"{BASE}/{slug}" if slug else f"{BASE}/"

    page_set = set(slugs)
    for a in sorted(assets | tracked | set(CONVENTIONAL)):
        if a in NON_SERVED or a in SKIP_FILES or a.split("/")[0] in SKIP_TOP:
            continue
        if a.startswith(NON_FETCHABLE):
            continue
        # Clean-URL page links such as /hash-generator are not separate files.
        if a in page_set or f"{a}.html" in targets:
            continue
        targets.setdefault(a, f"{BASE}/{a}")
    return targets


def download(targets):
    """Fetch every target. Returns {rel: bytes} and the list of failures."""
    live, failed = {}, []
    for rel, url in targets.items():
        data = try_fetch(url, timeout=90)
        if data is None:
            failed.append(rel)
        else:
            live[rel] = data
    return live, failed


def compare(repo_dir, live):
    missing, different, identical = [], [], []
    for rel, data in sorted(live.items()):
        target = os.path.join(repo_dir, rel)
        if not os.path.exists(target):
            missing.append(rel)
        elif open(target, "rb").read() != data:
            different.append(rel)
        else:
            identical.append(rel)
    return missing, different, identical


def main():
    github_token = get_secret("GIithub_publish")

    run(["rm", "-rf", REPO_DIR])
    run(["git", "clone", "--quiet",
         f"https://x-access-token:{github_token}@github.com/{REPO}.git", REPO_DIR])
    run(["git", "config", "user.name", "openhands"], cwd=REPO_DIR)
    run(["git", "config", "user.email", "openhands@all-hands.dev"], cwd=REPO_DIR)
    run(["git", "checkout", "-q", BRANCH], cwd=REPO_DIR)

    slugs = page_slugs()
    tracked = repo_paths(REPO_DIR)
    assets = assets_from_html(slugs)
    assets |= assets_from_css(assets)
    targets = build_targets(slugs, assets, tracked)
    print(f"live site: {len(slugs)} pages | {len(targets)} paths to check")

    live, failed = download(targets)
    print(f"fetched {len(live)} | not served {len(failed)}")
    for rel in sorted(failed):
        print(f"  not served: {rel}")

    missing, different, identical = compare(REPO_DIR, live)

    print()
    print("=== CHECK: what is already on GitHub? ===")
    print(f"  already uploaded, identical : {len(identical)}")
    print(f"  missing from GitHub         : {len(missing)}")
    print(f"  changed, needs re-upload    : {len(different)}")
    for rel in missing:
        print(f"    + {rel}")
    for rel in different:
        print(f"    ~ {rel}")

    stale = sorted(t for t in tracked - set(live) if not t.startswith(NON_FETCHABLE))
    if stale:
        print(f"  tracked on GitHub but not served (left alone): {len(stale)}")
        for rel in stale:
            print(f"    - {rel}")

    to_upload = missing + different
    if not to_upload:
        print()
        print("nothing to upload - GitHub already matches the live site")
        fire_callback("COMPLETED")
        return

    print()
    print(f"=== UPLOAD: copying {len(to_upload)} file(s) into the repo ===")
    for rel in to_upload:
        dest = os.path.join(REPO_DIR, rel)
        os.makedirs(os.path.dirname(dest) or REPO_DIR, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(live[rel])
        print(f"    {rel}")

    run(["git", "add", "-A"], cwd=REPO_DIR)
    if not run(["git", "status", "--porcelain"], cwd=REPO_DIR).strip():
        print("git saw no change after copying - nothing to commit")
        fire_callback("COMPLETED")
        return

    lines = [f"Backs up {len(live)} files from the live site.", ""]
    if missing:
        lines += [f"Added ({len(missing)}):"] + [f"  {r}" for r in missing]
    if different:
        lines += [f"Updated ({len(different)}):"] + [f"  {r}" for r in different]
    run(["git", "commit", "-q", "-m", "Backup live site to GitHub\n\n" + "\n".join(lines)], cwd=REPO_DIR)
    run(["git", "push", "-q", "origin", BRANCH], cwd=REPO_DIR)
    print(f"pushed commit {run(['git', 'rev-parse', 'HEAD'], cwd=REPO_DIR).strip()[:8]}")

    fire_callback("COMPLETED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        fire_callback("FAILED", str(e))
        sys.exit(1)
