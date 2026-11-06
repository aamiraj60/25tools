"""Report which pages Google has actually indexed.

Reads sitemap.xml, asks the Search Console URL Inspection API about every URL in
it, and prints the ones Google has not indexed together with the reason it gives.
Sitemap submission alone is not proof of indexing: a page can be submitted and
still be sitting at "Discovered - currently not indexed" for days.

Run this before asking Google to re-crawl anything, so the request goes to the
pages that need it rather than to all of them.

The service account in the SEARCH_CONSOLE secret must be a user of the property
(Search Console > Settings > Users and permissions).

Usage:
    SEARCH_CONSOLE="$(cat key.json)" python3 tools/index-status.py
    SEARCH_CONSOLE="$(cat key.json)" python3 tools/index-status.py --json
"""

import argparse
import json
import os
import re
import sys
import time

SITE = "sc-domain:toolguest.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITEMAP = os.path.join(ROOT, "sitemap.xml")
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def sitemap_urls():
    with open(SITEMAP, encoding="utf-8") as fh:
        return re.findall(r"<loc>([^<]+)</loc>", fh.read())


def client():
    raw = os.environ.get("SEARCH_CONSOLE")
    if not raw:
        sys.exit("SEARCH_CONSOLE is not set. Pass the service account JSON in it.")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=SCOPES
    )
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def inspect(sc, url):
    """Return the index status for one URL, retrying the quota errors."""
    for attempt in range(4):
        try:
            result = sc.urlInspection().index().inspect(
                body={"inspectionUrl": url, "siteUrl": SITE}
            ).execute()
            status = result["inspectionResult"]["indexStatusResult"]
            return {
                "verdict": status.get("verdict", "?"),
                "coverage": status.get("coverageState", "?"),
                "robots": status.get("robotsTxtState", "?"),
                "crawled": status.get("lastCrawlTime", "never"),
            }
        except Exception as exc:  # noqa: BLE001 - the API is rate limited
            if attempt == 3:
                return {"verdict": "ERROR", "coverage": str(exc)[:80],
                        "robots": "?", "crawled": "never"}
            time.sleep(2 ** attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="print the raw result as JSON")
    args = parser.parse_args()

    urls = sitemap_urls()
    sc = client()
    rows = []
    for url in urls:
        status = inspect(sc, url)
        rows.append({"url": url, **status})

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    path = lambda u: u.replace("https://toolguest.com", "") or "/"
    indexed = [r for r in rows if r["verdict"] == "PASS"]
    missing = [r for r in rows if r["verdict"] != "PASS"]

    print(f"{len(indexed)} of {len(rows)} pages indexed\n")
    for r in rows:
        mark = "ok  " if r["verdict"] == "PASS" else "MISS"
        print(f"  {mark} {path(r['url']):30s} {r['coverage']}")

    if missing:
        print(f"\n{len(missing)} page(s) need attention. Paste these into "
              f"Search Console > URL Inspection > Request Indexing:")
        for r in missing:
            print(f"  {r['url']}")
    else:
        print("\nEvery page in the sitemap is indexed.")


if __name__ == "__main__":
    main()
