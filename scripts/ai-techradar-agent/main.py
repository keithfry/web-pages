#!/usr/bin/env python3
"""AI Techradar Agent — daily AI/Robotics digest generator.

Usage:
    uv run main.py                  # 24h lookback, commit and push
    uv run main.py --hours 48       # override lookback window
    uv run main.py --dry-run        # generate HTML only, no git operations
    uv run main.py --no-email       # skip Gmail (RSS only)
"""

import argparse
import sys
from datetime import datetime, timezone

from config import LOOKBACK_HOURS, SUMMARIZE_MODEL, GENERATE_MODEL
from feed_fetcher import fetch_all_feeds, is_arxiv
from email_fetcher import fetch_emails
from article_fetcher import fetch_article_text, source_name_from_url
from llm import summarize, summarize_title, tag, classify_ai, deduplicate
from html_generator import generate_html
from publisher import save_html, commit_and_push

MAX_LINKS_PER_EMAIL = 5


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _process_items(raw_items: list[dict], source_type: str) -> list[dict]:
    """Summarize, classify, and tag a list of raw items. Returns enriched items."""
    label = "email" if source_type == "email" else "article"
    processed = []
    total = len(raw_items)

    for i, item in enumerate(raw_items, 1):
        title = item.get("title", "").strip()
        existing_text = item.get("summary") or item.get("body", "")

        # Linked articles have no title yet — derive one from the content
        if not title and item.get("_from_email_link"):
            if not existing_text.strip():
                log(f"  [{i}/{total}] skip: no title and no content")
                continue
            log(f"  [{i}/{total}] {label} (linked): {item.get('link', '')[:70]}")
            log(f"    → extracting title from content...")
            title = summarize_title(existing_text, SUMMARIZE_MODEL)
            log(f"    → title: {title[:70]}")
        elif not title:
            log(f"  [{i}/{total}] skip: no title")
            continue
        else:
            log(f"  [{i}/{total}] {label}: {title[:70]}")

        # Quick keyword pre-filter before calling LLM
        keywords = {"ai", "ml", "llm", "robot", "model", "neural", "machine learning",
                    "deep learning", "language model", "generative", "autonomous",
                    "reinforcement", "transformer", "diffusion", "anthropic", "openai",
                    "google deepmind", "nvidia", "hugging face"}
        lowered = (title + " " + existing_text).lower()
        probably_ai = any(kw in lowered for kw in keywords)

        if not probably_ai:
            log(f"    → classifying with LLM (no keywords matched)...")
            if not classify_ai(title, existing_text[:500], SUMMARIZE_MODEL):
                log(f"    → skip (not AI-related)")
                continue
            log(f"    → classified as AI-related")

        log(f"    → summarizing...")
        summary_text = summarize(title, existing_text, SUMMARIZE_MODEL)
        log(f"    → tagging...")
        tags = tag(title, summary_text, SUMMARIZE_MODEL)
        log(f"    → done  tags={tags}")

        processed.append({
            "title": title,
            "link": item.get("link", ""),
            "source": item.get("source", ""),
            "summary": summary_text,
            "tags": tags,
            "published": item.get("published"),
            "_source_type": source_type,
            "_is_arxiv": is_arxiv(item.get("source", "")),
        })

    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the daily AI Techradar digest.")
    parser.add_argument("--hours", type=int, default=LOOKBACK_HOURS,
                        help=f"Lookback window in hours (default: {LOOKBACK_HOURS})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate HTML only, skip git commit and push")
    parser.add_argument("--no-email", action="store_true",
                        help="Skip Gmail — fetch RSS feeds only")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    log(f"=== AI Techradar Agent ===")
    log(f"Date:           {now.strftime('%Y-%m-%d %H:%M UTC')}")
    log(f"Lookback:       {args.hours}h")
    log(f"Summarize model: {SUMMARIZE_MODEL}")
    log(f"Generate model:  {GENERATE_MODEL}")
    log(f"Dry run:        {args.dry_run}")
    log("")

    # --- Step 1: Fetch RSS feeds ---
    log("── Step 1: Fetching RSS feeds ──")
    rss_articles, rss_errors = fetch_all_feeds(args.hours)
    log(f"  {len(rss_articles)} articles fetched, {len(rss_errors)} feed errors")
    if rss_errors:
        for e in rss_errors:
            log(f"  ERROR {e['source']}: {e['error']}")
    log("")

    # --- Step 2: Fetch emails ---
    email_items: list[dict] = []
    if not args.no_email:
        log("── Step 2: Fetching Gmail ──")
        try:
            email_items = fetch_emails(args.hours)
            log(f"  {len(email_items)} emails fetched")
            for i, e in enumerate(email_items, 1):
                log(f"  {i}. [{e['source']}] {e['title'][:70]}")
        except FileNotFoundError as e:
            log(f"  WARNING: {e}")
            log("  Continuing without email. Run with --no-email to suppress.")
    else:
        log("── Step 2: Gmail skipped (--no-email) ──")
    log("")

    # --- Step 3: Summarize, classify, tag ---
    log(f"── Step 3: Processing {len(email_items)} emails ──")
    processed_emails = _process_items(email_items, "email")
    log(f"  {len(processed_emails)}/{len(email_items)} emails kept")
    log("")

    # --- Step 3b: Follow links found in emails ---
    log(f"── Step 3b: Following links from emails ──")
    linked_articles: list[dict] = []
    for email in email_items:
        links = email.get("links", [])[:MAX_LINKS_PER_EMAIL]
        if not links:
            continue
        log(f"  [{email['source']}] {len(links)} link(s) to check")
        for j, url in enumerate(links, 1):
            log(f"    [{j}/{len(links)}] fetching: {url[:80]}")
            text = fetch_article_text(url)
            if not text:
                log(f"    → skip (could not fetch)")
                continue
            source = source_name_from_url(url)
            linked_articles.append({
                "title": "",        # will be derived by summarizer from text
                "link": url,
                "source": source,
                "summary": text[:3000],
                "body": text[:3000],
                "_from_email_link": True,
            })
            log(f"    → fetched {len(text):,} chars from {source}")
    log(f"  {len(linked_articles)} linked articles fetched")
    log("")

    log(f"── Step 3c: Processing {len(linked_articles)} linked articles ──")
    processed_links = _process_items(linked_articles, "rss")
    log(f"  {len(processed_links)}/{len(linked_articles)} linked articles kept")
    log("")

    log(f"── Step 4: Processing {len(rss_articles)} RSS articles ──")
    processed_rss = _process_items(rss_articles, "rss")
    log(f"  {len(processed_rss)}/{len(rss_articles)} articles kept")
    log("")

    all_items = processed_emails + processed_links + processed_rss

    # --- Step 4: Deduplicate ---
    log(f"── Step 5: Deduplicating {len(all_items)} items ({len(processed_emails)} newsletters + {len(processed_links)} linked articles + {len(processed_rss)} RSS) ──")
    all_items = deduplicate(all_items, SUMMARIZE_MODEL)
    log(f"  {len(all_items)} items after deduplication")
    log("")

    # --- Step 5: Split into sections ---
    newsletters = [i for i in all_items if i["_source_type"] == "email"]
    papers = [i for i in all_items if i.get("_is_arxiv")]
    articles = [i for i in all_items
                if i["_source_type"] == "rss" and not i.get("_is_arxiv")]

    log(f"── Step 6: Generating HTML ──")
    log(f"  Newsletters: {len(newsletters)}")
    log(f"  Articles:    {len(articles)}")
    log(f"  Papers:      {len(papers)}")
    log(f"  Feed errors: {len(rss_errors)}")
    html = generate_html(
        newsletters=newsletters,
        articles=articles,
        papers=papers,
        errors=rss_errors,
        date=now,
    )
    log(f"  HTML generated ({len(html):,} chars)")
    log("")

    # --- Step 7: Save and publish ---
    log("── Step 7: Saving ──")
    out_path = save_html(html, now)
    log(f"  Saved: {out_path}")

    if args.dry_run:
        log("")
        log("Dry run complete — skipping git commit and push.")
        log(f"Preview: open {out_path}")
        return

    log("")
    log("── Step 8: Committing and pushing ──")
    commit_and_push(out_path, now)
    log("Done.")


if __name__ == "__main__":
    main()
