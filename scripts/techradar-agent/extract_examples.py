#!/usr/bin/env python3
"""Parse digest HTML files and emit labeled-example candidates for ad detection.

Usage:
    uv run extract_examples.py techradar/AI/ai-radar-2026-05-21.html
    uv run extract_examples.py techradar/AI/ai-radar-2026-05-20.html --output candidates.json

Output goes to stdout (newline-delimited JSON) or --output file.
Each item has is_ad=null — set it to true/false manually before saving to labeled_examples.json.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _slug(text: str) -> str:
    """Convert text to kebab-case slug (max 40 chars)."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40]


def parse_digest_html(path: Path) -> list[dict]:
    """Parse a digest HTML file and return one dict per card."""
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    date_str = ""
    m = re.search(r"\d{4}-\d{2}-\d{2}", path.name)
    if m:
        date_str = m.group(0)

    items = []
    for card in soup.find_all("div", class_="card"):
        via_tag = card.find("div", class_="via")
        source = via_tag.get_text(strip=True) if via_tag else ""

        h3 = card.find("h3")
        if not h3:
            continue
        link_tag = h3.find("a")
        link = link_tag["href"] if link_tag else ""
        title = h3.get_text(strip=True)

        p = card.find("p")
        summary = p.get_text(strip=True) if p else ""

        slug = _slug(f"{_slug(source)}-{_slug(title)}-{date_str}")
        items.append(
            {
                "id": slug,
                "title": title,
                "summary": summary[:500],
                "source": source,
                "link": link,
                "is_ad": None,
                "ad_type": None,
                "notes": "",
            }
        )
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract ad-labeling candidates from digest HTML")
    parser.add_argument("html_files", nargs="+", type=Path, help="Digest HTML file(s)")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    all_items: list[dict] = []
    for html_path in args.html_files:
        # Accept paths relative to repo root or cwd
        if not html_path.exists():
            alt = _REPO_ROOT / html_path
            if alt.exists():
                html_path = alt
            else:
                print(f"[warn] not found: {html_path}", file=sys.stderr)
                continue
        items = parse_digest_html(html_path)
        print(f"[extract] {html_path.name}: {len(items)} cards", file=sys.stderr)
        all_items.extend(items)

    if args.output:
        # Wrap in schema envelope
        data = {
            "schema_version": 1,
            "description": "Hand-labeled ad/not-ad examples — set is_ad to true/false before use",
            "examples": all_items,
        }
        args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[extract] wrote {len(all_items)} candidates to {args.output}", file=sys.stderr)
    else:
        for item in all_items:
            print(json.dumps(item, ensure_ascii=False))


if __name__ == "__main__":
    main()
