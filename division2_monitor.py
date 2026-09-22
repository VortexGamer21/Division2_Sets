#!/usr/bin/env python3
"""Monitor official The Division 2 news and create a GitHub Issue for new update notes."""

import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen

NEWS_URL = "https://www.ubisoft.com/de-de/game/the-division/the-division-2/news-updates"
SEEN_FILE = os.path.join(os.path.dirname(__file__), "seen_articles.json")

# Intentionally broad: the bot flags update/patch material for human review.
RELEVANT_TITLE_TERMS = (
    "patch notes", "patch-note", "patchnotizen", "patch notes", "title update",
    "developer notes", "dev notes", "pts", "update", "title update"
)

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self._href = attrs["href"]
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", html.unescape(" ".join(self._text))).strip()
            if text:
                self.links.append((urljoin(NEWS_URL, self._href), text))
            self._href = None
            self._text = []


def fetch(url):
    req = Request(url, headers={"User-Agent": "Division2-News-Monitor/1.0"})
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return []
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_seen(items):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(items[-500:], f, ensure_ascii=False, indent=2)


def is_relevant(title):
    t = title.lower()
    return any(term in t for term in RELEVANT_TITLE_TERMS)


def create_issue(title, url):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("GITHUB_TOKEN/GITHUB_REPOSITORY not available; printing notification instead.")
        print(f"NEW DIVISION 2 UPDATE: {title}\n{url}")
        return

    import urllib.request
    api = f"https://api.github.com/repos/{repo}/issues"
    body = f"""## Neue offizielle Division-2-Meldung\n\n**Titel:** {title}\n\n**Original:** {url}\n\nBitte prüfe deine datengetriebenen Bereiche in `index.html` und aktualisiere sie, falls die Meldung Änderungen enthält.\n\nDer Bot nimmt absichtlich keine automatischen Änderungen an deiner Website vor.\n\n*Automatisch erstellt am {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n"""
    payload = json.dumps({
        "title": f"Division 2 Update: {title}",
        "body": body,
        "labels": ["division2-update"]
    }).encode()
    req = urllib.request.Request(
        api,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Division2-News-Monitor/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("GitHub Issue created:", r.status)
    except Exception as e:
        print("Could not create GitHub Issue:", e, file=sys.stderr)
        raise


def main():
    print("Checking:", NEWS_URL)
    raw = fetch(NEWS_URL)
    parser = PageParser()
    parser.feed(raw)

    seen = set(load_seen())
    current_urls = []
    candidates = []

    for url, title in parser.links:
        if "/news-updates/" not in url:
            continue
        if url in current_urls:
            continue
        current_urls.append(url)
        if is_relevant(title):
            candidates.append((url, title))

    # First run: establish a baseline without flooding the repository.
    first_run = not seen
    new_items = [(u, t) for u, t in candidates if u not in seen]

    if first_run:
        print(f"First run: recording {len(candidates)} relevant articles without notifications.")
    else:
        for url, title in new_items:
            print("New article:", title, url)
            create_issue(title, url)

    save_seen(list(seen.union(current_urls)))

    print(f"Found {len(candidates)} relevant articles; {len(new_items)} new.")

if __name__ == "__main__":
    main()
