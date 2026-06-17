#!/usr/bin/env python3
"""Techradar Agent — daily AI and/or Robotics digest generator.

Usage:
    uv run main.py                          # run both AI and Robotics (default)
    uv run main.py --topic ai               # AI digest only
    uv run main.py --topic robotics         # Robotics digest only
    uv run main.py --hours 48               # override lookback window
    uv run main.py --date 2026-04-13        # use a specific date (time defaults to now)
    uv run main.py --time 08:00             # cut off at 08:00 ET today
    uv run main.py --date 2026-04-13 --time 08:00  # cut off at 08:00 ET on that date
    uv run main.py --dry-run                # generate HTML only, no git operations
    uv run main.py --no-email               # skip Gmail (RSS only)
"""

import argparse
import io
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

from config import (
    LOOKBACK_HOURS, SUMMARIZE_MODEL, RANK_MODEL, DEDUP_MODEL, GENERATE_MODEL,
    LLM_WORKERS, URL_WORKERS, AD_DETECTOR_MODEL, AD_GATE_ENABLED,
    AI_OUTPUT_DIR, ROBOTICS_OUTPUT_DIR,
)
from feed_fetcher import fetch_all_feeds, is_arxiv
from email_fetcher import fetch_emails
from article_fetcher import fetch_article_text, source_name_from_url
from llm import summarize, summarize_title, tag, classify_ai, classify_robotics, classify_ad, deduplicate, llm_stats, unload_all_models
from html_generator import generate_html
from publisher import save_html, commit_and_push
from enricher import enrich
from podcast_generator import generate_podcast
from podcast_rss import generate_podcast_rss, BASE_URL_ROOT, AI_OUTPUT_DIR_REL, ROBOTICS_OUTPUT_DIR_REL

MAX_LINKS_PER_EMAIL = 5

_log_lock = threading.Lock()
_log_file: io.TextIOWrapper | None = None

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _open_log_file(date: datetime) -> io.TextIOWrapper:
    log_dir = _REPO_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"techradar-agent-{date.strftime('%Y-%m-%d')}.log"
    return open(log_path, "a", buffering=1)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with _log_lock:
        print(line, flush=True)
        if _log_file:
            print(line, file=_log_file, flush=True)


# ---------------------------------------------------------------------------
# Single-item processor — runs in a thread pool worker
# ---------------------------------------------------------------------------

_AI_KEYWORDS = {
    "ai", "ml", "llm", "robot", "neural", "machine learning",
    "deep learning", "language model", "generative", "autonomous vehicle",
    "reinforcement learning", "transformer model", "diffusion model",
    "anthropic", "openai", "google deepmind", "nvidia ai", "nvidia cuda",
    "hugging face",
}

_ROBOTICS_KEYWORDS = {
    "robot", "robotics", "drone", "uav", "uas", "autonomous vehicle",
    "humanoid", "manipulation", "ros", "servo", "actuator", "end effector",
    "sim-to-real", "embodied", "locomotion", "gripper", "lidar",
    "autonomous systems", "physical ai", "boston dynamics", "spot",
}

# Patterns that strongly indicate promotional/advertisement content
import re as _re
_PRICE_PATTERN = _re.compile(r'\$\d+(\.\d{2})?')
_AD_PHRASES = {
    "shop now", "buy now", "add to cart", "free shipping", "order now",
    "gift idea", "gift guide", "on sale", "discount code",
    "promo code", "coupon", "limited time", "shop our", "browse our",
    "new arrivals", "bestseller", "best seller",
    # Webinar / promotional event phrases
    "register now", "register for free", "register today", "save your seat",
    "save my seat", "reserve your spot", "claim your spot",
    "join us live", "join us for a", "join our webinar", "join our live",
    "free webinar", "live webinar", "upcoming webinar",
}

# Webinar/event phrases to check in the summarized output
_WEBINAR_PHRASES = {
    "webinar", "web seminar", "virtual event", "online event",
    "register to attend", "register for this", "register at",
    "upcoming event", "live session", "live demo",
}


def _is_advertisement(title: str, text: str) -> bool:
    """Return True if the content looks like a promotional email or advertisement."""
    combined = (title + " " + text).lower()
    # Three or more price mentions is a strong signal
    if len(_PRICE_PATTERN.findall(combined)) >= 3:
        return True
    # Any explicit ad phrase
    if any(phrase in combined for phrase in _AD_PHRASES):
        return True
    return False


def _is_webinar_summary(summary: str) -> bool:
    """Return True if the summary is primarily about attending a webinar or promotional event."""
    lowered = summary.lower()
    if not any(phrase in lowered for phrase in _WEBINAR_PHRASES):
        return False
    cta_signals = {
        "register", "sign up", "sign-up", "rsvp", "attend", "join us",
        "reserve", "claim your", "save your seat", "free to attend",
        "limited seats", "limited spots",
    }
    return any(signal in lowered for signal in cta_signals)


def _process_one(idx: int, total: int, item: dict, source_type: str, topic: str) -> dict | None:
    """Process a single item: classify, optionally derive title, summarize, tag.
    Returns enriched dict or None if the item should be dropped.
    Runs safely in a thread — all state is local.
    """
    label = "email" if source_type == "email" else "article"
    title = item.get("title", "").strip()
    existing_text = item.get("body") or item.get("summary", "")

    # Linked articles have no title — derive from content
    if not title and item.get("_from_email_link"):
        if not existing_text.strip():
            log(f"  [{idx}/{total}] skip: no content")
            return None
        log(f"  [{idx}/{total}] {label} (linked): {item.get('link', '')[:70]}")
        log(f"    [{idx}] → extracting title...")
        title = summarize_title(existing_text, SUMMARIZE_MODEL)
        log(f"    [{idx}] → title: {title[:70]}")
    elif not title:
        log(f"  [{idx}/{total}] skip: no title")
        return None
    else:
        log(f"  [{idx}/{total}] {label}: {title[:70]}")

    # Advertisement pre-filter — drop promotional/sales emails before any LLM call
    if _is_advertisement(title, existing_text):
        log(f"    [{idx}] → skip (advertisement)")
        return None

    # LLM ad gate — catches contextual ads the heuristic misses
    if AD_GATE_ENABLED:
        is_ad, ad_reason = classify_ad(title, existing_text[:1000], AD_DETECTOR_MODEL)
        if is_ad:
            log(f"    [{idx}] → skip (ad gate: {ad_reason})")
            return None

    lowered = (title + " " + existing_text).lower()
    classifier_fn = classify_ai if topic == "AI" else classify_robotics

    if topic == "AI":
        # Keyword fast-path: AI keywords are distinctive enough to skip LLM
        if not any(kw in lowered for kw in _AI_KEYWORDS):
            log(f"    [{idx}] → classifying with LLM (no AI keywords matched)...")
            if not classifier_fn(title, existing_text[:500], SUMMARIZE_MODEL):
                log(f"    [{idx}] → skip (not AI-related)")
                return None
            log(f"    [{idx}] → classified as AI-related")
    else:
        # Robotics: always run LLM — keyword substring matching causes too many false passes
        log(f"    [{idx}] → classifying with LLM (Robotics)...")
        if not classifier_fn(title, existing_text[:500], SUMMARIZE_MODEL):
            log(f"    [{idx}] → skip (not Robotics-related)")
            return None
        log(f"    [{idx}] → classified as Robotics-related")

    log(f"    [{idx}] → summarizing...")
    summary_text = summarize(title, existing_text, SUMMARIZE_MODEL)

    # Post-summarization webinar filter
    if _is_webinar_summary(summary_text):
        log(f"    [{idx}] → skip (webinar/promotional event)")
        return None

    log(f"    [{idx}] → tagging...")
    tags = tag(title, summary_text, SUMMARIZE_MODEL)
    log(f"    [{idx}] → done  tags={tags}")

    return {
        "title": title,
        "link": item.get("link", ""),
        "source": item.get("source", ""),
        "summary": summary_text,
        "tags": tags,
        "published": item.get("published"),
        "_source_type": source_type,
        "_is_arxiv": is_arxiv(item.get("source", "")),
    }


def _process_items(raw_items: list[dict], source_type: str, topic: str) -> list[dict]:
    """Process all items in parallel using LLM_WORKERS threads."""
    if not raw_items:
        return []

    total = len(raw_items)
    results: dict[int, dict | None] = {}

    with ThreadPoolExecutor(max_workers=LLM_WORKERS) as executor:
        futures = {
            executor.submit(_process_one, idx, total, item, source_type, topic): idx
            for idx, item in enumerate(raw_items, 1)
        }
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()

    return [results[i] for i in sorted(results) if results[i] is not None]


# ---------------------------------------------------------------------------
# Parallel URL fetcher
# ---------------------------------------------------------------------------

def _fetch_links_parallel(email_items: list[dict]) -> list[dict]:
    """Fetch all email links in parallel. Returns flat list of article dicts."""
    work = []
    for email in email_items:
        links = email.get("links", [])[:MAX_LINKS_PER_EMAIL]
        for url in links:
            work.append((email["source"], url))

    if not work:
        return []

    log(f"  Fetching {len(work)} links across {len(email_items)} emails ({URL_WORKERS} workers)...")

    fetched: list[dict] = []

    def _fetch(email_source: str, url: str) -> dict | None:
        log(f"    → fetching: {url[:80]}")
        text = fetch_article_text(url)
        if not text:
            log(f"    → skip (could not fetch): {url[:60]}")
            return None
        source = source_name_from_url(url)
        log(f"    → fetched {len(text):,} chars from {source}")
        return {
            "title": "",
            "link": url,
            "source": source,
            "summary": text[:3000],
            "body": text[:3000],
            "_from_email_link": True,
        }

    with ThreadPoolExecutor(max_workers=URL_WORKERS) as executor:
        futures = {executor.submit(_fetch, src, url): url for src, url in work}
        for future in as_completed(futures):
            result = future.result()
            if result:
                fetched.append(result)

    return fetched


# ---------------------------------------------------------------------------
# Ollama model cleanup
# ---------------------------------------------------------------------------

def _stop_models(log_fn) -> None:
    log_fn("")
    log_fn("── Stopping Ollama models ──")
    try:
        unloaded = unload_all_models()
        for name in unloaded:
            log_fn(f"  stopped: {name}")
        if not unloaded:
            log_fn("  none loaded")
    except Exception as e:
        log_fn(f"  error unloading models: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global _log_file

    parser = argparse.ArgumentParser(description="Generate the daily AI/Robotics Techradar digest.")
    parser.add_argument("--topic", choices=["ai", "robotics", "both"], default="both",
                        help="Which digest(s) to generate (default: both)")
    parser.add_argument("--hours", type=int, default=LOOKBACK_HOURS,
                        help=f"Lookback window in hours (default: {LOOKBACK_HOURS})")
    parser.add_argument("--date", type=str, default=None,
                        help="Reference date YYYY-MM-DD in ET (default: today)")
    parser.add_argument("--time", type=str, default=None,
                        help="Reference time HH:MM in ET (default: current time). "
                             "Only content published/received before this time is included.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate HTML only, skip git commit and push")
    parser.add_argument("--no-email", action="store_true",
                        help="Skip Gmail — fetch RSS feeds only")
    parser.add_argument("--no-podcast", action="store_true",
                        help="Skip podcast audio generation")
    parser.add_argument("--podcast-only", action="store_true",
                        help="Rebuild podcast from existing JSON (skip fetch/enrich/HTML)")
    parser.add_argument("--refresh-token", action="store_true",
                        help="Delete token.json and re-authenticate with Gmail, then exit")
    args = parser.parse_args()

    if args.refresh_token:
        from config import GMAIL_TOKEN
        from email_fetcher import _get_credentials
        if GMAIL_TOKEN.exists():
            GMAIL_TOKEN.unlink()
            print(f"Deleted {GMAIL_TOKEN}")
        print("Starting Gmail OAuth flow...")
        _get_credentials()
        print("Token refreshed. Exiting.")
        return

    now = datetime.now(ET)

    if args.date or args.time:
        ref_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else now.date()
        ref_time_str = args.time or now.strftime("%H:%M")
        ref_hour, ref_minute = (int(p) for p in ref_time_str.split(":"))
        as_of = datetime(ref_date.year, ref_date.month, ref_date.day,
                         ref_hour, ref_minute, tzinfo=ET)
    else:
        as_of = now

    _log_file = _open_log_file(as_of)
    try:
        topics = []
        if args.topic in ("ai", "both"):
            topics.append("AI")
        if args.topic in ("robotics", "both"):
            topics.append("Robotics")

        as_of_utc = as_of.astimezone(timezone.utc)

        # Fetch emails once — shared across all topics; each topic classifies independently
        email_items: list[dict] = []
        linked_articles: list[dict] = []
        if not args.no_email and not args.podcast_only:
            log("── Fetching Gmail (shared across topics) ──")
            try:
                email_items = fetch_emails(args.hours, as_of=as_of_utc)
                log(f"  {len(email_items)} emails fetched")
                for i, e in enumerate(email_items, 1):
                    log(f"  {i}. [{e['source']}] {e['title'][:70]}")
                log("")
                log(f"── Fetching email links ({URL_WORKERS} workers) ──")
                linked_articles = _fetch_links_parallel(email_items)
                log(f"  {len(linked_articles)} linked articles fetched")
            except FileNotFoundError as e:
                log(f"  WARNING: {e}")
                log("  Continuing without email. Run with --no-email to suppress.")
            except Exception as e:
                from google.auth.exceptions import RefreshError
                if isinstance(e, RefreshError):
                    log("  Gmail token is invalid or expired.")
                    log("  Run: uv run main.py --refresh-token")
                    return
                raise
        elif not args.podcast_only:
            log("── Gmail skipped (--no-email) ──")
        log("")

        for topic in topics:
            log(f"\n{'='*60}")
            log(f"  TOPIC: {topic}")
            log(f"{'='*60}")
            _run_topic(args, as_of, topic, email_items=email_items, linked_articles=linked_articles)

    finally:
        _log_file.close()
        _log_file = None


def _run_topic(
    args: argparse.Namespace,
    as_of: datetime,
    topic: str,
    email_items: list[dict] | None = None,
    linked_articles: list[dict] | None = None,
) -> None:
    email_items = email_items or []
    linked_articles = linked_articles or []

    base_dir = AI_OUTPUT_DIR if topic == "AI" else ROBOTICS_OUTPUT_DIR
    output_dir = base_dir / as_of.strftime("%Y-%m")
    output_dir.mkdir(parents=True, exist_ok=True)
    file_prefix = "ai-radar" if topic == "AI" else "robotics-radar"

    log(f"=== Techradar Agent — {topic} ===")
    log(f"As-of:           {as_of.strftime('%Y-%m-%d %H:%M ET')}")
    log(f"Lookback:        {args.hours}h")
    log(f"Topic:           {topic}")
    log(f"Output dir:      {output_dir}")
    log(f"Summarize model: {SUMMARIZE_MODEL}")
    log(f"Rank model:      {RANK_MODEL}")
    log(f"Dedup model:     {DEDUP_MODEL}")
    log(f"Generate model:  {GENERATE_MODEL}")
    log(f"LLM workers:     {LLM_WORKERS}  (set OLLAMA_NUM_PARALLEL={LLM_WORKERS} to match)")
    log(f"URL workers:     {URL_WORKERS}")
    log(f"Dry run:         {args.dry_run}")
    log("")

    as_of_utc = as_of.astimezone(timezone.utc)

    # --- Podcast-only shortcut ---
    if args.podcast_only:
        json_path = output_dir / f"{file_prefix}-{as_of.strftime('%Y-%m-%d')}.json"
        if not json_path.exists():
            log(f"ERROR: no JSON found at {json_path} — run without --podcast-only first")
            return
        log(f"── Podcast-only mode: loading {json_path.name} ──")
        import json as _json
        from enricher import write_enriched_json
        enriched_data = _json.loads(json_path.read_text())
        log("── Generating podcast audio ──")
        try:
            mp3_path, chap_path, transcript_path, cover_path, og_path = generate_podcast(enriched_data, as_of, output_dir, file_prefix=file_prefix, topic_label=topic, log=log)
            log(f"  Podcast generated: {mp3_path.name}")
        except Exception as e:
            log(f"ERROR: podcast generation failed: {e}")
            return
        write_enriched_json(enriched_data, json_path)
        log("  Updated JSON with actual chapter times")
        if not args.dry_run:
            log("── Committing and pushing ──")
            extras = [p for p in [transcript_path, cover_path, og_path] if p]
            commit_and_push([mp3_path, chap_path, json_path] + extras, as_of, topic=topic, log=log)
        else:
            log("Dry run — skipping commit.")
        return

    # --- Step 1: Fetch RSS feeds ---
    log(f"── Step 1: Fetching {topic} RSS feeds ──")
    rss_articles, rss_errors = fetch_all_feeds(args.hours, as_of=as_of_utc, topic=topic)
    log(f"  {len(rss_articles)} articles fetched, {len(rss_errors)} feed errors")
    if rss_errors:
        for e in rss_errors:
            log(f"  ERROR {e['source']}: {e['error']}")
    log("")

    # --- Step 2: Process emails (fetched once in main, classified per topic) ---
    log(f"── Step 2: Processing {len(email_items)} emails ({LLM_WORKERS} workers) [{topic} filter] ──")
    processed_emails = _process_items(email_items, "email", topic)
    log(f"  {len(processed_emails)}/{len(email_items)} emails kept")
    log("")

    # --- Step 3: Process linked articles (fetched once in main, classified per topic) ---
    log(f"── Step 3: Processing {len(linked_articles)} linked articles ({LLM_WORKERS} workers) [{topic} filter] ──")
    processed_links = _process_items(linked_articles, "rss", topic)
    log(f"  {len(processed_links)}/{len(linked_articles)} linked articles kept")
    log("")

    # --- Step 4: Process RSS articles ---
    log(f"── Step 4: Processing {len(rss_articles)} RSS articles ({LLM_WORKERS} workers) [{topic} filter] ──")
    processed_rss = _process_items(rss_articles, "rss", topic)
    log(f"  {len(processed_rss)}/{len(rss_articles)} articles kept")
    log("")

    all_items = processed_emails + processed_links + processed_rss

    # --- Pre-step 5: Release processing models to free VRAM for dedup ---
    _stop_models(log)
    log("")

    # --- Step 5: Deduplicate ---
    log(f"── Step 5: Deduplicating {len(all_items)} items "
        f"({len(processed_emails)} newsletters + {len(processed_links)} linked + {len(processed_rss)} RSS) ──")
    all_items = deduplicate(all_items, DEDUP_MODEL)
    log(f"  {len(all_items)} items after deduplication")
    log("")

    # --- Step 6: Enrich — rank, audio scripts, chapter times, write JSON ---
    log(f"── Step 6: Enriching {len(all_items)} items ──")
    json_path = output_dir / f"{file_prefix}-{as_of.strftime('%Y-%m-%d')}.json"
    enriched_data = enrich(all_items, as_of, json_path, summarize_model=SUMMARIZE_MODEL, rank_model=RANK_MODEL, topic=topic, log=log)
    podcast_count = len([i for i in enriched_data["items"] if i.get("include_in_podcast")])
    log(f"  Enrichment complete — {podcast_count} podcast items")
    log("")

    # --- Steps 7a + 7b: Generate HTML and podcast in parallel ---
    newsletters = [i for i in all_items if i["_source_type"] == "email"]
    papers      = [i for i in all_items if i.get("_is_arxiv")]
    articles    = [i for i in all_items if i["_source_type"] == "rss" and not i.get("_is_arxiv")]

    html_result: list = []
    html_error: list = []
    podcast_result: list = []
    podcast_error: list = []

    def _gen_html():
        try:
            log("── Step 7a: Generating HTML ──")
            log(f"  Newsletters: {len(newsletters)}, Articles: {len(articles)}, Papers: {len(papers)}, Errors: {len(rss_errors)}")
            topic_dir_rel = AI_OUTPUT_DIR_REL if topic == "AI" else ROBOTICS_OUTPUT_DIR_REL
            ym_dir = as_of.strftime("%Y-%m")
            date_str = as_of.strftime("%Y-%m-%d")
            _mp3_url = None if args.no_podcast else f"{BASE_URL_ROOT}/{topic_dir_rel}/{ym_dir}/{file_prefix}-{date_str}.mp3"
            _rss_url = None if args.no_podcast else f"{BASE_URL_ROOT}/{topic_dir_rel}/podcast.xml"
            _og_url = None if args.no_podcast else f"{BASE_URL_ROOT}/{topic_dir_rel}/{ym_dir}/{file_prefix}-{date_str}.og.jpg"
            html = generate_html(
                newsletters=newsletters, articles=articles,
                papers=papers, errors=rss_errors, date=as_of, topic=topic,
                mp3_url=_mp3_url, podcast_rss_url=_rss_url, og_image_url=_og_url,
            )
            html_result.append(html)
            log(f"  HTML generated ({len(html):,} chars)")
        except Exception as e:
            html_error.append(e)

    def _gen_podcast():
        if args.no_podcast:
            log("── Step 7b: Podcast skipped (--no-podcast) ──")
            return
        try:
            log("── Step 7b: Generating podcast audio ──")
            mp3, chap_json, transcript, cover, og = generate_podcast(enriched_data, as_of, output_dir, file_prefix=file_prefix, topic_label=topic, log=log)
            podcast_result.append((mp3, chap_json, transcript, cover, og))
            log(f"  Podcast generated: {mp3.name}")
        except Exception as e:
            podcast_error.append(e)
            log(f"  WARNING: podcast generation failed: {e}")

    t_html = threading.Thread(target=_gen_html)
    t_pod  = threading.Thread(target=_gen_podcast)
    t_html.start()
    t_pod.start()
    t_html.join()
    t_pod.join()

    # Re-write JSON with actual chapter times from TTS
    if podcast_result:
        from enricher import write_enriched_json
        write_enriched_json(enriched_data, json_path)
        log("  Updated JSON with actual chapter times")

    if html_error:
        raise html_error[0]

    if not html_result:
        raise RuntimeError("HTML generation thread exited without producing output")

    html = html_result[0]

    # --- Step 8: Save ---
    log("── Step 8: Saving ──")
    html_path = save_html(html, as_of, output_dir=output_dir, prefix=file_prefix)
    log(f"  Saved HTML: {html_path}")

    out_paths = [html_path, json_path]
    if podcast_result:
        mp3_path, chap_path, transcript_path, cover_path, og_path = podcast_result[0]
        out_paths.extend([p for p in [mp3_path, chap_path, transcript_path, cover_path, og_path] if p])

    # --- Step 8b: Generate podcast RSS feed ---
    log("── Step 8b: Generating podcast RSS ──")
    rss_path = generate_podcast_rss(base_dir, topic, log=log)
    out_paths.append(rss_path)

    # --- Step 8c: Regenerate techradar index.html ---
    log("── Step 8c: Regenerating techradar index ──")
    import subprocess as _sp
    _index_script = _REPO_ROOT / ".github" / "scripts" / "generate-index.sh"
    _r = _sp.run(["bash", str(_index_script), "techradar"], capture_output=True, text=True, cwd=_REPO_ROOT)
    if _r.stdout.strip():
        log(f"  {_r.stdout.strip()}")
    if _r.returncode != 0:
        log(f"  WARNING: generate-index.sh failed: {_r.stderr.strip()}")
    else:
        # Stage all generated index.html files under techradar/
        import glob as _glob
        for idx_path in _glob.glob(str(_REPO_ROOT / "techradar" / "**" / "index.html"), recursive=True):
            out_paths.append(Path(idx_path))
        log(f"  index regenerated")

    if args.dry_run:
        call_count, total_duration = llm_stats()
        log(f"LLM calls: {call_count}  total time: {total_duration:.3f}s")
        log("")
        log(f"Dry run complete — skipping git commit and push.")
        log(f"Preview: open {html_path}")
        _stop_models(log)
        return

    # --- Step 9: Commit and push ---
    log("")
    log("── Step 9: Committing and pushing ──")
    commit_and_push(out_paths, as_of, topic=topic, log=log)

    call_count, total_duration = llm_stats()
    log(f"LLM calls: {call_count}  total time: {total_duration:.3f}s")

    # --- Step 10: Release Ollama models ---
    _stop_models(log)
    log(f"Done — {topic} digest complete.")


if __name__ == "__main__":
    main()
