#!/usr/bin/env python3
"""Fetch recent AI RSS feed entries from the past 24 hours and output as JSON.

Output JSON schema
------------------
Top-level: array of feed objects (one per source that had recent entries).

Feed object (success — always included, even when items is empty):
    source    str   Human-readable name of the company / source.
    feed_url  str   URL of the RSS/Atom feed.
    items     list  Entry objects for entries published within LOOKBACK_HOURS.
                    Empty array if the feed was reachable but had no recent entries.

Feed object (error — returned instead of items when the fetch fails):
    source    str   Human-readable name of the company / source.
    feed_url  str   URL of the RSS/Atom feed.
    error     str   Human-readable error message describing the failure.

Entry object (element of items):
    title      str        Article title.
    link       str        Canonical URL of the article.
    published  str|null   ISO-8601 UTC timestamp (e.g. "2026-03-21T14:30:00+00:00"),
                          or null if the feed entry carries no date.
    summary    str        Plain-text summary/excerpt (HTML tags stripped).

Example:
    [
      {
        "source": "OpenAI",
        "feed_url": "https://openai.com/blog/rss.xml",
        "items": [
          {
            "title": "Introducing GPT-5",
            "link": "https://openai.com/blog/gpt-5",
            "published": "2026-03-21T10:00:00+00:00",
            "summary": "Today we're releasing GPT-5..."
          }
        ]
      },
      {
        "source": "Broken Feed",
        "feed_url": "https://example.com/bad.xml",
        "error": "urlopen error [Errno -2] Name or service not known"
      }
    ]
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser

FEEDS_CSV = Path(__file__).parent.parent / "data" / "ai-rss-feeds.csv"
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", 24))


def load_feeds(csv_path: Path) -> list[dict]:
    feeds = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("Feed URL", "").strip()
            source = row.get("Company / Source", "").strip()
            if url and source:
                feeds.append({"source": source, "feed_url": url})
    return feeds


def parse_entry_date(entry):
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_feed(source: str, feed_url: str, cutoff: datetime) -> dict:
    try:
        parsed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"[warn] failed to fetch {feed_url}: {e}", file=sys.stderr)
        return {"source": source, "feed_url": feed_url, "error": str(e)}

    items = []
    for entry in parsed.entries:
        pub = parse_entry_date(entry)
        if pub and pub < cutoff:
            continue  # too old

        summary = getattr(entry, "summary", "") or ""
        # Strip any HTML-ish tags crudely
        import re
        summary = re.sub(r"<[^>]+>", "", summary).strip()

        items.append({
            "title": getattr(entry, "title", "").strip(),
            "link": getattr(entry, "link", "").strip(),
            "published": pub.isoformat() if pub else None,
            "summary": summary,
        })

    return {
        "source": source,
        "feed_url": feed_url,
        "items": items,
    }


def main():
    feeds = load_feeds(FEEDS_CSV)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

    results = []
    for feed in feeds:
        results.append(fetch_feed(feed["source"], feed["feed_url"], cutoff))

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
