"""Enrich pipeline items with ranking, audio scripts, and chapter time estimates.

Runs after deduplication. Produces the shared JSON artifact consumed by
html_generator and podcast_generator.
"""

import json
from datetime import datetime
from pathlib import Path

from config import SUMMARIZE_MODEL, RANK_MODEL

# Words per minute for Kokoro TTS (approximate, used for time estimation)
_TTS_WPM = 130

# 5 Kokoro voices for round-robin assignment (American English)
# Note: am_adam and af_nicole are intentionally excluded
KOKORO_VOICES = [
    "af_heart",    # female, warm
    "am_echo",     # male, neutral
    "af_bella",    # female, expressive
    "am_michael",  # male, deep
    "af_nova",     # female, energetic
]


def _words(text: str) -> int:
    return len(text.split())


def _seconds(word_count: int) -> int:
    return round(word_count / _TTS_WPM * 60)


def _estimate_chapter_times(intro_script: str, audio_scripts: list[str]) -> list[int]:
    """Return list of chapter start times in seconds.

    Index 0 = intro start (always 0).
    Index 1..N = item start times, estimated from word counts.
    """
    times = [0]
    cursor = _seconds(_words(intro_script))
    times.append(cursor)
    # Iterate all but the last script: each iteration appends the START of the
    # *next* item. The last item's start = chapter_times[-1] via caller's fallback.
    for script in audio_scripts[:-1]:
        cursor += _seconds(_words(script))
        times.append(cursor)
    return times


def _build_enriched_dict(date: datetime, intro_script: str, episode_tagline: str, items: list[dict]) -> dict:
    return {
        "date": date.strftime("%Y-%m-%d"),
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "intro_script": intro_script,
        "episode_tagline": episode_tagline,
        "items": items,
    }


def write_enriched_json(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def enrich(
    all_items: list[dict],
    date: datetime,
    output_path: Path,
    summarize_model: str = SUMMARIZE_MODEL,
    rank_model: str = RANK_MODEL,
    topic: str = "AI",
    log=print,
) -> dict:
    """Rank, script, and time-estimate all items. Write JSON. Return enriched dict.

    Args:
        all_items: deduplicated items from the pipeline (emails + articles + papers)
        date: as_of datetime (ET)
        output_path: where to write the JSON file
        summarize_model: Ollama model for scripting/intro generation
        rank_model: Ollama model for ranking
        log: logging function

    Returns:
        enriched dict (same structure as JSON file)
    """
    from llm import rank_items, generate_audio_script, generate_intro_script, generate_episode_tagline, unload_all_models

    # Separate podcast candidates (emails + articles) from papers
    podcast_candidates = [i for i in all_items if not i.get("_is_arxiv")]
    papers = [i for i in all_items if i.get("_is_arxiv")]

    log(f"  Enriching {len(podcast_candidates)} podcast candidates + {len(papers)} papers (excluded from audio)")

    # Evict summarize-phase models before loading the (larger) rank model
    evicted = unload_all_models()
    if evicted:
        log(f"  Unloaded models before ranking: {', '.join(evicted)}")

    # Rank podcast candidates
    log(f"  Ranking items by relevance (model: {rank_model})...")
    ranked = rank_items(podcast_candidates, model=rank_model)

    # Generate audio script per item (in rank order)
    log(f"  Generating {len(ranked)} audio scripts (model: {summarize_model})...")
    for item in ranked:
        item["audio_script"] = generate_audio_script(item, model=summarize_model)
        item["voice_index"] = (item["rank"] - 1) % len(KOKORO_VOICES)
        item["include_in_podcast"] = True
        log(f"    [{item['rank']}] scripted: {item['title'][:60]}")

    # Generate intro script and episode tagline
    log("  Generating intro script...")
    intro_script = generate_intro_script(ranked, date, model=summarize_model, topic=topic)
    log("  Generating episode tagline...")
    episode_tagline = generate_episode_tagline(ranked, model=summarize_model)
    log(f"  Episode tagline: {episode_tagline}")

    # Estimate chapter times
    audio_scripts = [item["audio_script"] for item in ranked]
    chapter_times = _estimate_chapter_times(intro_script, audio_scripts)
    # times[0] = intro start (always 0), times[1..N] = item starts
    for i, item in enumerate(ranked):
        item["chapter_start_seconds"] = chapter_times[i + 1] if i + 1 < len(chapter_times) else chapter_times[-1]

    # Add papers back (not in podcast, no audio fields)
    for paper in papers:
        paper["include_in_podcast"] = False
        paper["chapter_start_seconds"] = None

    all_enriched = ranked + papers

    data = _build_enriched_dict(date, intro_script, episode_tagline, all_enriched)
    write_enriched_json(data, output_path)
    log(f"  Wrote enriched JSON: {output_path}")

    return data
