"""Fetch recent AI RSS feed entries.

Adapted from scripts/fetch_ai_feeds.py — uses the same logic and output schema
but returns Python objects instead of printing JSON to stdout.
"""

import csv
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser

from config import FEEDS_CSV, LOOKBACK_HOURS, ARXIV_MAX_PAPERS


def load_feeds(csv_path: Path) -> list[dict]:
    feeds = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Verified", "").strip().upper() != "Y":
                continue
            url = row.get("Feed URL", "").strip()
            source = row.get("Company / Source", "").strip()
            if url and source:
                feeds.append({"source": source, "feed_url": url})
    return feeds


def parse_entry_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_feed(source: str, feed_url: str, cutoff: datetime, as_of: datetime | None = None) -> dict:
    try:
        parsed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"[warn] failed to fetch {feed_url}: {e}", file=sys.stderr)
        return {"source": source, "feed_url": feed_url, "error": str(e)}

    items = []
    for entry in parsed.entries:
        pub = parse_entry_date(entry)
        if pub and pub < cutoff:
            continue
        if pub and as_of and pub > as_of:
            continue

        summary = getattr(entry, "summary", "") or ""
        summary = re.sub(r"<[^>]+>", "", summary).strip()

        items.append({
            "title": getattr(entry, "title", "").strip(),
            "link": getattr(entry, "link", "").strip(),
            "published": pub.isoformat() if pub else None,
            "summary": summary,
            "source": source,
            "feed_url": feed_url,
        })

    return {"source": source, "feed_url": feed_url, "items": items}


def is_arxiv(source: str) -> bool:
    return "arxiv" in source.lower()


def fetch_all_feeds(hours: int = LOOKBACK_HOURS, as_of: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """Fetch all verified feeds.

    Args:
        hours:  Lookback window in hours.
        as_of:  Upper bound for item publication time (defaults to now).
                Items published after this time are excluded.

    Returns:
        (articles, errors) where articles is a flat list of item dicts and
        errors is a list of {source, feed_url, error} dicts.
    """
    feeds = load_feeds(FEEDS_CSV)
    reference = as_of or datetime.now(timezone.utc)
    cutoff = reference - timedelta(hours=hours)

    articles: list[dict] = []
    errors: list[dict] = []

    for feed in feeds:
        result = fetch_feed(feed["source"], feed["feed_url"], cutoff, as_of=as_of)
        if "error" in result:
            errors.append(result)
        else:
            items = result["items"]
            if is_arxiv(feed["source"]):
                items = items[:ARXIV_MAX_PAPERS]
            articles.extend(items)

    return articles, errors
