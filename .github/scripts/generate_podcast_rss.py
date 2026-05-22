#!/usr/bin/env python3
"""Generate podcast.xml RSS feed from ai-radar-*.mp3 files.

Usage (from repo root):
    python3 .github/scripts/generate-podcast-rss.py

Scans techradar/AI/ for MP3 files, reads paired .chapters.json for duration,
writes techradar/AI/podcast.xml. Keeps last 20 episodes.
"""

import json
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
OUTPUT_DIR = REPO_ROOT / "techradar" / "AI"
BASE_URL = "https://keithfry.github.io/web-pages/techradar/AI"
MAX_EPISODES = 20


def _duration_from_chapters(chapters_path: Path) -> int:
    """Return total duration in seconds from the endTime of the last chapter."""
    try:
        data = json.loads(chapters_path.read_text())
        chapters = data.get("chapters", [])
        if chapters:
            return int(chapters[-1].get("endTime", 0))
    except Exception:
        pass
    return 0


def _date_from_filename(mp3_path: Path) -> datetime | None:
    """Parse YYYY-MM-DD from filename ai-radar-YYYY-MM-DD.mp3."""
    stem = mp3_path.stem  # e.g. "ai-radar-2026-05-21"
    parts = stem.split("-")
    # parts: ["ai", "radar", "2026", "05", "21"]
    if len(parts) >= 5:
        try:
            y, m, d = int(parts[2]), int(parts[3]), int(parts[4])
            return datetime(y, m, d, 8, 0, 0, tzinfo=timezone.utc)
        except (ValueError, IndexError):
            pass
    return None


def build_rss_feed(output_dir: Path, base_url: str, max_episodes: int = MAX_EPISODES) -> str:
    """Scan output_dir for MP3 files and build an RSS 2.0 feed string."""
    mp3_files = sorted(output_dir.glob("ai-radar-*.mp3"), reverse=True)[:max_episodes]

    items_xml = []
    for mp3 in mp3_files:
        date = _date_from_filename(mp3)
        if not date:
            continue

        date_str = mp3.stem.replace("ai-radar-", "")  # "2026-05-21"
        chap_json = output_dir / f"ai-radar-{date_str}.chapters.json"
        duration = _duration_from_chapters(chap_json) if chap_json.exists() else 0
        file_size = mp3.stat().st_size
        mp3_url = f"{base_url}/ai-radar-{date_str}.mp3"
        chap_url = f"{base_url}/ai-radar-{date_str}.chapters.json"
        pub_date = format_datetime(date)
        title_date = f"{date.strftime('%B')} {date.day}, {date.year}"

        chap_tag = (
            f'      <podcast:chapters url="{chap_url}" type="application/json+chapters"/>\n'
            if chap_json.exists() else ""
        )

        items_xml.append(f"""  <item>
    <title>AI &amp; Robotics Radar — {title_date}</title>
    <pubDate>{pub_date}</pubDate>
    <enclosure url="{mp3_url}" type="audio/mpeg" length="{file_size}"/>
    <itunes:duration>{duration}</itunes:duration>
    <guid isPermaLink="true">{mp3_url}</guid>
{chap_tag}  </item>""")

    items_block = "\n".join(items_xml)
    now = format_datetime(datetime.now(timezone.utc))

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:podcast="https://podcastindex.org/namespace/1.0">
  <channel>
    <title>AI &amp; Robotics Daily Radar</title>
    <link>{base_url}/</link>
    <description>Daily AI and Robotics news digest in audio form. New episode each weekday.</description>
    <language>en-us</language>
    <lastBuildDate>{now}</lastBuildDate>
    <itunes:author>Keith Fry</itunes:author>
    <itunes:category text="Technology">
      <itunes:category text="Tech News"/>
    </itunes:category>
    <itunes:explicit>false</itunes:explicit>
{items_block}
  </channel>
</rss>
"""


def main() -> None:
    xml = build_rss_feed(OUTPUT_DIR, BASE_URL)
    out = OUTPUT_DIR / "podcast.xml"
    out.write_text(xml, encoding="utf-8")
    print(f"Wrote {out} ({len(xml):,} chars, {xml.count('<item>')} episodes)")


if __name__ == "__main__":
    main()
