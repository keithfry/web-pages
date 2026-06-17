# Podcast Generation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a parallel audio pipeline to the AI Radar digest that generates a daily podcast MP3 with chapter markers, a Podcasting 2.0 RSS feed, and a shared JSON artifact that drives both the HTML and audio outputs.

**Architecture:** After deduplication (existing step 5), a new enrich step ranks items, generates LLM audio scripts, and writes a JSON artifact. HTML generation and podcast audio generation then run in parallel threads, both reading from that JSON. A single git commit publishes HTML + MP3 + chapters JSON + enriched JSON together. GitHub Actions regenerates the RSS feed after each push.

**Tech Stack:** Kokoro TTS, ffmpeg (system), mutagen (ID3 chapters), soundfile (WAV write), standard RSS 2.0 + iTunes + Podcasting 2.0 namespaces, Python threading.

---

## Task 1: Add Python dependencies and verify system deps

**Files:**
- Modify: `scripts/ai-techradar-agent/pyproject.toml`

**Step 1: Add dependencies**

```toml
# In the dependencies list, add:
    "kokoro>=0.9.4",
    "mutagen>=1.47",
    "soundfile>=0.12",
```

**Step 2: Install and verify**

```bash
cd scripts/ai-techradar-agent
uv sync
uv run python -c "import kokoro; import mutagen; import soundfile; print('OK')"
```
Expected: `OK`

**Step 3: Verify ffmpeg is available**

```bash
ffmpeg -version | head -1
```
Expected: `ffmpeg version ...` — if missing, install: `brew install ffmpeg`

**Step 4: Commit**

```bash
git add scripts/ai-techradar-agent/pyproject.toml scripts/ai-techradar-agent/uv.lock
git commit -m "feat: add kokoro, mutagen, soundfile for podcast generation"
```

---

## Task 2: Add LLM functions for audio content generation

**Files:**
- Modify: `scripts/ai-techradar-agent/llm.py`

These follow the exact same `_chat()` pattern as existing functions.

**Step 1: Write tests**

Create `scripts/ai-techradar-agent/test_podcast_llm.py`:

```python
"""Smoke tests for podcast LLM functions — requires Ollama running."""
import unittest
from llm import rank_items, generate_audio_script, generate_intro_script
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

SAMPLE_ITEMS = [
    {"title": "Google releases Gemini 2.5 Flash", "summary": "Google announced Gemini 2.5 Flash with improved speed.", "tags": ["model"], "_source_type": "rss"},
    {"title": "OpenAI raises $40B at $340B valuation", "summary": "OpenAI closed a record funding round.", "tags": ["policy"], "_source_type": "rss"},
    {"title": "Anthropic releases Claude 4 Opus", "summary": "Claude 4 Opus is Anthropic's most capable model.", "tags": ["model"], "_source_type": "rss"},
]

class TestPodcastLLM(unittest.TestCase):
    def test_rank_items_returns_all_with_rank(self):
        ranked = rank_items(SAMPLE_ITEMS, "llama3.2")
        self.assertEqual(len(ranked), len(SAMPLE_ITEMS))
        self.assertIn("rank", ranked[0])
        # Ranks should be 1-indexed and unique
        ranks = [item["rank"] for item in ranked]
        self.assertEqual(sorted(ranks), list(range(1, len(SAMPLE_ITEMS) + 1)))

    def test_generate_audio_script_returns_string(self):
        script = generate_audio_script(SAMPLE_ITEMS[0], "llama3.2")
        self.assertIsInstance(script, str)
        self.assertGreater(len(script), 50)
        word_count = len(script.split())
        self.assertLessEqual(word_count, 120, f"Script too long: {word_count} words")

    def test_generate_intro_script_mentions_date(self):
        date = datetime(2026, 5, 21, 8, 0, tzinfo=ET)
        intro = generate_intro_script(SAMPLE_ITEMS, date, "llama3.2")
        self.assertIsInstance(intro, str)
        self.assertGreater(len(intro), 20)

if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

```bash
cd scripts/ai-techradar-agent
uv run python -m pytest test_podcast_llm.py -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name 'rank_items'` (functions don't exist yet)

**Step 3: Add functions to `llm.py`**

Add after the `deduplicate()` function:

```python
def rank_items(items: list[dict], model: str = SUMMARIZE_MODEL) -> list[dict]:
    """Rank items by AI/robotics relevance and newsworthiness, 1 = most important.

    Returns a new list sorted by rank with a 'rank' field added to each item.
    Falls back to original order if LLM response cannot be parsed.
    """
    if not items:
        return []

    index_lines = "\n".join(
        f"{i}: {item['title']}" for i, item in enumerate(items)
    )
    prompt = (
        "You are an editor ranking AI and robotics news items by importance and interest "
        "for a daily listener. Rank the following items from most to least important. "
        "Consider: breadth of impact, novelty, practical significance for AI practitioners.\n\n"
        "Return a JSON object with key 'ranked' — a list of original indices in order "
        "from most to least important. Include every index exactly once.\n\n"
        f"Items:\n{index_lines}\n\n"
        'Example response: {"ranked": [3, 0, 2, 1]}'
    )
    raw = _chat(prompt, model, json_mode=True)
    try:
        order: list[int] = json.loads(_extract_json(raw)).get("ranked", [])
        # Validate: must contain all indices 0..N-1
        if sorted(order) != list(range(len(items))):
            raise ValueError(f"Bad ranking: {order}")
        ranked = []
        for rank, orig_idx in enumerate(order, 1):
            item = dict(items[orig_idx])
            item["rank"] = rank
            ranked.append(item)
        return ranked
    except (json.JSONDecodeError, AttributeError, ValueError) as e:
        print(f"[warn] rank_items() failed ({e}), using original order", file=sys.stderr)
        return [dict(item, rank=i + 1) for i, item in enumerate(items)]


def generate_audio_script(item: dict, model: str = SUMMARIZE_MODEL) -> str:
    """Generate a ~70-word spoken-word script for a single podcast segment.

    More conversational and detailed than the text summary. Written for listening,
    not reading — no bullet points, no markdown, no links.
    """
    prompt = (
        "Write a spoken-word podcast segment about the following AI/tech news item. "
        "Write as if speaking naturally to a listener — conversational, engaging, specific. "
        "No bullet points. No markdown. No URLs. No 'click here' or 'read more'. "
        "Target: approximately 70 words (about 30 seconds at normal speech pace).\n\n"
        f"Title: {item['title']}\n"
        f"Summary: {item.get('summary', '')}\n\n"
        "Spoken segment:"
    )
    return _chat(prompt, model).strip()


def generate_intro_script(items: list[dict], date, model: str = SUMMARIZE_MODEL) -> str:
    """Generate a podcast intro mentioning the date, item count, and top-3 topics.

    'date' should be a datetime object with strftime support.
    """
    date_str = date.strftime("%B %-d, %Y")
    top3 = [item["title"] for item in items[:3]]
    top3_str = "\n".join(f"- {t}" for t in top3)
    prompt = (
        f"Write a short podcast intro (under 45 words). "
        f"Date: {date_str}. Total items: {len(items)}. "
        f"Mention up to 3 top stories by topic (not exact title). "
        f"Sound natural and welcoming. No markdown. End naturally, don't say 'let's get started'.\n\n"
        f"Top stories:\n{top3_str}\n\n"
        "Intro:"
    )
    return _chat(prompt, model).strip()
```

**Step 4: Run tests**

```bash
cd scripts/ai-techradar-agent
uv run python -m pytest test_podcast_llm.py -v
```
Expected: all 3 tests PASS (requires Ollama running with llama3.2)

**Step 5: Commit**

```bash
git add scripts/ai-techradar-agent/llm.py scripts/ai-techradar-agent/test_podcast_llm.py
git commit -m "feat: add rank_items, generate_audio_script, generate_intro_script to llm.py"
```

---

## Task 3: Create `enricher.py`

**Files:**
- Create: `scripts/ai-techradar-agent/enricher.py`
- Create: `scripts/ai-techradar-agent/test_enricher.py`

**Step 1: Write tests (pure logic only — no LLM calls)**

Create `scripts/ai-techradar-agent/test_enricher.py`:

```python
"""Tests for enricher.py — pure logic, no LLM calls needed."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


class TestEstimateChapterTimes(unittest.TestCase):
    def test_chapter_times_increase_monotonically(self):
        from enricher import _estimate_chapter_times
        intro = "Welcome to the show."  # ~4 words
        scripts = ["Script one has about ten words total in it.", "Script two also has ten words in it here."]
        times = _estimate_chapter_times(intro, scripts)
        self.assertEqual(len(times), 3)  # intro + 2 items
        self.assertEqual(times[0], 0)
        self.assertGreater(times[1], times[0])
        self.assertGreater(times[2], times[1])

    def test_chapter_time_estimation_formula(self):
        from enricher import _estimate_chapter_times
        # 100 words at 130 wpm = ~46 seconds
        intro = " ".join(["word"] * 100)
        times = _estimate_chapter_times(intro, [])
        self.assertAlmostEqual(times[0], 0)
        self.assertAlmostEqual(times[1], 46, delta=5)


class TestEnrichJSONSchema(unittest.TestCase):
    def test_enriched_json_has_required_keys(self):
        from enricher import _build_enriched_dict

        date = datetime(2026, 5, 21, 8, 0, tzinfo=ET)
        items = [
            {
                "rank": 1, "title": "Test", "link": "http://x.com",
                "source": "Test Source", "summary": "Summary here.",
                "audio_script": "Spoken version here.", "voice_index": 0,
                "tags": ["model"], "published": None,
                "_source_type": "rss", "_is_arxiv": False,
                "include_in_podcast": True, "chapter_start_seconds": 22,
            }
        ]
        result = _build_enriched_dict(date, "Intro text.", items)
        self.assertEqual(result["date"], "2026-05-21")
        self.assertIn("generated_at", result)
        self.assertEqual(result["intro_script"], "Intro text.")
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        for key in ["rank", "title", "audio_script", "voice_index",
                    "include_in_podcast", "chapter_start_seconds"]:
            self.assertIn(key, item)


class TestWriteEnrichedJSON(unittest.TestCase):
    def test_json_round_trip(self):
        from enricher import _build_enriched_dict, write_enriched_json
        date = datetime(2026, 5, 21, 8, 0, tzinfo=ET)
        data = _build_enriched_dict(date, "Intro.", [])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ai-radar-2026-05-21.json"
            write_enriched_json(data, out)
            loaded = json.loads(out.read_text())
        self.assertEqual(loaded["date"], "2026-05-21")
```

**Step 2: Run tests to verify they fail**

```bash
cd scripts/ai-techradar-agent
uv run python -m pytest test_enricher.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'enricher'`

**Step 3: Create `enricher.py`**

```python
"""Enrich pipeline items with ranking, audio scripts, and chapter time estimates.

Runs after deduplication. Produces the shared JSON artifact consumed by
html_generator and podcast_generator.
"""

import json
from datetime import datetime
from pathlib import Path

from config import SUMMARIZE_MODEL

# Words per minute for Kokoro TTS (approximate, used for time estimation)
_TTS_WPM = 130

# 5 Kokoro voices for round-robin assignment (American English)
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
    for script in audio_scripts[:-1]:
        cursor += _seconds(_words(script))
        times.append(cursor)
    return times


def _build_enriched_dict(date: datetime, intro_script: str, items: list[dict]) -> dict:
    return {
        "date": date.strftime("%Y-%m-%d"),
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "intro_script": intro_script,
        "items": items,
    }


def write_enriched_json(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def enrich(
    all_items: list[dict],
    date: datetime,
    output_path: Path,
    model: str = SUMMARIZE_MODEL,
    log=print,
) -> dict:
    """Rank, script, and time-estimate all items. Write JSON. Return enriched dict.

    Args:
        all_items: deduplicated items from the pipeline (emails + articles + papers)
        date: as_of datetime (ET)
        output_path: where to write the JSON file
        model: Ollama model for LLM calls
        log: logging function

    Returns:
        enriched dict (same structure as JSON file)
    """
    from llm import rank_items, generate_audio_script, generate_intro_script

    # Separate podcast candidates (emails + articles) from papers
    podcast_candidates = [i for i in all_items if not i.get("_is_arxiv")]
    papers = [i for i in all_items if i.get("_is_arxiv")]

    log(f"  Enriching {len(podcast_candidates)} podcast candidates + {len(papers)} papers (excluded from audio)")

    # Rank podcast candidates
    log("  Ranking items by relevance...")
    ranked = rank_items(podcast_candidates, model)

    # Generate audio script per item (in rank order)
    log(f"  Generating {len(ranked)} audio scripts...")
    for item in ranked:
        item["audio_script"] = generate_audio_script(item, model)
        item["voice_index"] = (item["rank"] - 1) % len(KOKORO_VOICES)
        item["include_in_podcast"] = True
        log(f"    [{item['rank']}] scripted: {item['title'][:60]}")

    # Estimate chapter times
    audio_scripts = [item["audio_script"] for item in ranked]
    log("  Generating intro script...")
    intro_script = generate_intro_script(ranked, date, model)

    chapter_times = _estimate_chapter_times(intro_script, audio_scripts)
    # times[0] = intro start, times[1..N] = item starts
    for i, item in enumerate(ranked):
        item["chapter_start_seconds"] = chapter_times[i + 1] if i + 1 < len(chapter_times) else chapter_times[-1]

    # Add papers back (not in podcast, no audio fields)
    for paper in papers:
        paper["include_in_podcast"] = False
        paper["chapter_start_seconds"] = None

    all_enriched = ranked + papers

    data = _build_enriched_dict(date, intro_script, all_enriched)
    write_enriched_json(data, output_path)
    log(f"  Wrote enriched JSON: {output_path}")

    return data
```

**Step 4: Run tests**

```bash
cd scripts/ai-techradar-agent
uv run python -m pytest test_enricher.py -v
```
Expected: all 4 tests PASS (no Ollama needed — pure logic tests)

**Step 5: Commit**

```bash
git add scripts/ai-techradar-agent/enricher.py scripts/ai-techradar-agent/test_enricher.py
git commit -m "feat: add enricher.py — ranking, audio scripts, chapter time estimation"
```

---

## Task 4: Create `podcast_generator.py`

**Files:**
- Create: `scripts/ai-techradar-agent/podcast_generator.py`
- Create: `scripts/ai-techradar-agent/test_podcast_generator.py`

**Step 1: Write tests**

Create `scripts/ai-techradar-agent/test_podcast_generator.py`:

```python
"""Tests for podcast_generator.py."""
import json
import tempfile
import unittest
from pathlib import Path


class TestChaptersJson(unittest.TestCase):
    def test_chapters_json_structure(self):
        from podcast_generator import _build_chapters_json
        chapters = [
            {"startTime": 0, "title": "Introduction"},
            {"startTime": 22, "title": "Google releases Gemini 2.5 Flash"},
        ]
        result = _build_chapters_json(chapters)
        data = json.loads(result)
        self.assertEqual(data["version"], "1.2.0")
        self.assertEqual(len(data["chapters"]), 2)
        self.assertEqual(data["chapters"][0]["startTime"], 0)
        self.assertEqual(data["chapters"][1]["title"], "Google releases Gemini 2.5 Flash")

    def test_chapters_json_requires_title(self):
        from podcast_generator import _build_chapters_json
        chapters = [{"startTime": 0, "title": ""}]
        data = json.loads(_build_chapters_json(chapters))
        self.assertEqual(data["chapters"][0]["title"], "")


class TestVoiceAssignment(unittest.TestCase):
    def test_voice_index_wraps_around(self):
        from podcast_generator import _voice_for
        from enricher import KOKORO_VOICES
        for i in range(10):
            voice = _voice_for(i)
            self.assertEqual(voice, KOKORO_VOICES[i % len(KOKORO_VOICES)])
```

**Step 2: Run tests to verify they fail**

```bash
cd scripts/ai-techradar-agent
uv run python -m pytest test_podcast_generator.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'podcast_generator'`

**Step 3: Create `podcast_generator.py`**

```python
"""Generate a podcast MP3 with ID3 chapter markers from enriched data.

Requires ffmpeg on PATH and Kokoro TTS installed (uv sync).
"""

import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from enricher import KOKORO_VOICES


def _voice_for(voice_index: int) -> str:
    return KOKORO_VOICES[voice_index % len(KOKORO_VOICES)]


def _build_chapters_json(chapters: list[dict]) -> str:
    """Build Podcasting 2.0 chapters JSON string."""
    return json.dumps({"version": "1.2.0", "chapters": chapters}, indent=2)


def _tts_segment(text: str, voice: str, out_wav: Path) -> float:
    """Synthesize text to WAV using Kokoro. Returns duration in seconds."""
    import soundfile as sf
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code="a")
    audio_chunks = []
    sample_rate = 24000

    for _, _, audio in pipeline(text, voice=voice):
        audio_chunks.append(audio)

    if not audio_chunks:
        raise RuntimeError(f"Kokoro produced no audio for text: {text[:50]!r}")

    import numpy as np
    full_audio = np.concatenate(audio_chunks)
    sf.write(str(out_wav), full_audio, sample_rate)
    return len(full_audio) / sample_rate


def _concat_wavs_to_mp3(wav_files: list[Path], out_mp3: Path) -> None:
    """Use ffmpeg to concat WAV segments into a single MP3."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        concat_file = Path(f.name)
        for wav in wav_files:
            f.write(f"file '{wav.resolve()}'\n")

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-ar", "22050", "-ab", "128k",
                str(out_mp3),
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr.decode()}") from e
    finally:
        concat_file.unlink(missing_ok=True)


def _write_id3_chapters(mp3_path: Path, chapters: list[dict]) -> None:
    """Write ID3v2 CHAP frames to an MP3 file for chapter navigation."""
    from mutagen.id3 import ID3, CHAP, CToc, TIT2

    try:
        tags = ID3(str(mp3_path))
    except Exception:
        tags = ID3()

    # Remove existing chapter tags
    for key in list(tags.keys()):
        if key.startswith("CHAP") or key.startswith("CTOC"):
            del tags[key]

    chap_ids = []
    for i, chap in enumerate(chapters):
        start_ms = int(chap["startTime"] * 1000)
        end_ms = int(chap.get("endTime", chap["startTime"] + 30) * 1000)
        elem_id = f"chap{i}"
        chap_ids.append(elem_id)
        tags.add(CHAP(
            element_id=elem_id,
            start_time=start_ms,
            end_time=end_ms,
            start_offset=0xFFFFFFFF,
            end_offset=0xFFFFFFFF,
            sub_frames=[TIT2(encoding=3, text=[chap["title"]])],
        ))

    tags.add(CToc(
        element_id="toc",
        flags=0x03,  # top-level, ordered
        child_element_ids=chap_ids,
        sub_frames=[TIT2(encoding=3, text=["Table of Contents"])],
    ))
    tags.save(str(mp3_path), v2_version=3)


def generate_podcast(enriched_data: dict, date: datetime, output_dir: Path, log=print) -> tuple[Path, Path]:
    """Generate MP3 + chapters.json from enriched data. Returns (mp3_path, chapters_json_path).

    Also updates enriched_data['items'] with actual chapter_start_seconds from audio timings.
    """
    date_str = date.strftime("%Y-%m-%d")
    mp3_path = output_dir / f"ai-radar-{date_str}.mp3"
    chapters_json_path = output_dir / f"ai-radar-{date_str}.chapters.json"

    podcast_items = [i for i in enriched_data["items"] if i.get("include_in_podcast")]
    intro_script = enriched_data["intro_script"]

    log(f"  Generating audio for intro + {len(podcast_items)} items...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        wav_files: list[Path] = []
        actual_starts: list[float] = []
        cursor = 0.0

        # Intro segment
        intro_wav = tmp / "intro.wav"
        log(f"  [tts] intro ({_voice_for(0)}): {intro_script[:60]}...")
        intro_dur = _tts_segment(intro_script, _voice_for(0), intro_wav)
        wav_files.append(intro_wav)
        actual_starts.append(cursor)
        cursor += intro_dur

        # Item segments
        for item in podcast_items:
            wav_path = tmp / f"item_{item['rank']:03d}.wav"
            voice = _voice_for(item["voice_index"])
            script = item["audio_script"]
            log(f"  [tts] item {item['rank']} ({voice}): {item['title'][:50]}...")
            dur = _tts_segment(script, voice, wav_path)
            wav_files.append(wav_path)
            actual_starts.append(cursor)
            item["chapter_start_seconds"] = int(cursor)
            cursor += dur

        total_duration = int(cursor)
        log(f"  Total audio duration: {total_duration}s ({total_duration // 60}m {total_duration % 60}s)")

        # Concat to MP3
        log("  Merging WAV segments → MP3...")
        _concat_wavs_to_mp3(wav_files, mp3_path)

    # Build chapters list
    chapters = [{"startTime": 0, "title": "Introduction"}]
    for item, start in zip(podcast_items, actual_starts[1:]):
        chapters.append({"startTime": int(start), "title": item["title"]})

    # Add endTime to each chapter
    for i, chap in enumerate(chapters):
        if i + 1 < len(chapters):
            chap["endTime"] = chapters[i + 1]["startTime"]
        else:
            chap["endTime"] = total_duration

    # Write chapters JSON (Podcasting 2.0)
    chapters_json_path.write_text(_build_chapters_json(chapters), encoding="utf-8")
    log(f"  Wrote chapters JSON: {chapters_json_path}")

    # Embed ID3 chapter tags
    _write_id3_chapters(mp3_path, chapters)
    log(f"  Wrote ID3 chapters to MP3: {mp3_path}")

    return mp3_path, chapters_json_path
```

**Step 4: Run tests**

```bash
cd scripts/ai-techradar-agent
uv run python -m pytest test_podcast_generator.py -v
```
Expected: all 3 tests PASS (no Ollama or ffmpeg needed for these tests)

**Step 5: Commit**

```bash
git add scripts/ai-techradar-agent/podcast_generator.py scripts/ai-techradar-agent/test_podcast_generator.py
git commit -m "feat: add podcast_generator.py — Kokoro TTS, ffmpeg merge, ID3 chapters"
```

---

## Task 5: Update `publisher.py` to commit multiple files

**Files:**
- Modify: `scripts/ai-techradar-agent/publisher.py`

**Step 1: Update `commit_and_push` to accept multiple paths**

In `publisher.py`, change the signature and `git add` call:

Current `commit_and_push(out_path: Path, date: datetime, log=print)` — change to accept a list:

```python
def save_json(data: dict, date: datetime) -> Path:
    """Write enriched JSON to techradar/AI/ai-radar-YYYY-MM-DD.json."""
    import json
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"ai-radar-{date.strftime('%Y-%m-%d')}.json"
    out_path = OUTPUT_DIR / filename
    out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return out_path


def commit_and_push(out_paths: list[Path], date: datetime, log=print) -> None:
    """git pull --rebase, add all out_paths, commit, push."""
    # Support single Path for backwards compatibility
    if isinstance(out_paths, Path):
        out_paths = [out_paths]

    commit_msg = f"Add AI radar for {date.strftime('%Y-%m-%d')}"

    lock = REPO_ROOT / ".git" / "index.lock"
    if lock.exists():
        lock.unlink()
        log("  removed stale .git/index.lock")

    _run(["git", "-C", str(REPO_ROOT), "pull", "--rebase", "--autostash"], log=log)

    for path in out_paths:
        rel = path.relative_to(REPO_ROOT)
        _run(["git", "-C", str(REPO_ROOT), "add", str(rel)], log=log)

    result = _run(
        [
            "git", "-C", str(REPO_ROOT),
            "-c", f"user.name={GIT_USER_NAME}",
            "-c", f"user.email={GIT_USER_EMAIL}",
            "commit", "-m", commit_msg,
        ],
        check=False,
        log=log,
    )
    if result.returncode != 0:
        if "nothing to commit" in result.stdout + result.stderr:
            log("  nothing to commit, skipping push")
            return
        raise RuntimeError(f"git commit failed:\n{result.stderr}")

    _run(["git", "-C", str(REPO_ROOT), "push"], log=log)
    log(f"  pushed: {commit_msg}")
```

**Step 2: Verify no syntax errors**

```bash
cd scripts/ai-techradar-agent
uv run python -c "from publisher import save_html, save_json, commit_and_push; print('OK')"
```
Expected: `OK`

**Step 3: Commit**

```bash
git add scripts/ai-techradar-agent/publisher.py
git commit -m "feat: publisher supports committing multiple output files"
```

---

## Task 6: Update `main.py` — add enrich step, parallelize HTML + podcast

**Files:**
- Modify: `scripts/ai-techradar-agent/main.py`

**Step 1: Add imports at top of `main.py`**

After existing imports, add:

```python
from enricher import enrich
from podcast_generator import generate_podcast
from publisher import save_html, save_json, commit_and_push
```

Also update the `from publisher import` line (remove `save_html, commit_and_push` since they're now in the new import).

**Step 2: Add `--no-podcast` flag to arg parser**

In the `argparse` block, add:

```python
parser.add_argument("--no-podcast", action="store_true",
                    help="Skip podcast audio generation")
```

**Step 3: Replace steps 6-8 in `_run()` with new flow**

Replace the section from `# --- Step 6: Generate HTML ---` through `# --- Step 8: Commit and push ---` with:

```python
    # --- Step 6: Enrich — rank, audio scripts, chapter times, write JSON ---
    log(f"── Step 6: Enriching {len(all_items)} items ──")
    json_path = OUTPUT_DIR / f"ai-radar-{as_of.strftime('%Y-%m-%d')}.json"
    enriched_data = enrich(all_items, as_of, json_path, model=SUMMARIZE_MODEL, log=log)
    log(f"  Enrichment complete — {len([i for i in enriched_data['items'] if i.get('include_in_podcast')])} podcast items")
    log("")

    # --- Steps 7a + 7b: Generate HTML and podcast in parallel ---
    newsletters = [i for i in all_items if i["_source_type"] == "email"]
    papers      = [i for i in all_items if i.get("_is_arxiv")]
    articles    = [i for i in all_items if i["_source_type"] == "rss" and not i.get("_is_arxiv")]

    html_result: list[str] = []
    html_error: list[Exception] = []
    podcast_result: list[tuple] = []
    podcast_error: list[Exception] = []

    def _gen_html():
        try:
            log("── Step 7a: Generating HTML ──")
            log(f"  Newsletters: {len(newsletters)}, Articles: {len(articles)}, Papers: {len(papers)}, Errors: {len(rss_errors)}")
            html = generate_html(newsletters=newsletters, articles=articles, papers=papers, errors=rss_errors, date=as_of)
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
            mp3, chap_json = generate_podcast(enriched_data, as_of, OUTPUT_DIR, log=log)
            podcast_result.append((mp3, chap_json))
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

    if html_error:
        raise html_error[0]

    html = html_result[0]

    # --- Step 8: Save ---
    log("── Step 8: Saving ──")
    html_path = save_html(html, as_of)
    log(f"  Saved HTML: {html_path}")

    out_paths = [html_path, json_path]
    if podcast_result:
        mp3_path, chap_path = podcast_result[0]
        out_paths.extend([mp3_path, chap_path])

    if args.dry_run:
        call_count, total_duration = llm_stats()
        log(f"LLM calls: {call_count}  total time: {total_duration:.3f}s")
        log("")
        log("Dry run complete — skipping git commit and push.")
        log(f"Preview: open {html_path}")
        _stop_models(log)
        return

    # --- Step 9: Commit and push ---
    log("")
    log("── Step 9: Committing and pushing ──")
    commit_and_push(out_paths, as_of, log=log)

    call_count, total_duration = llm_stats()
    log(f"LLM calls: {call_count}  total time: {total_duration:.3f}s")

    # --- Step 10: Release Ollama models ---
    _stop_models(log)
    log("Done.")
```

**Step 4: Smoke test (dry run, no email, no podcast)**

```bash
cd scripts/ai-techradar-agent
uv run main.py --dry-run --no-email --no-podcast --hours 2
```
Expected: runs without error, produces HTML + JSON in `techradar/AI/`

**Step 5: Commit**

```bash
git add scripts/ai-techradar-agent/main.py
git commit -m "feat: main.py — enrich step, parallel HTML+podcast generation, multi-file commit"
```

---

## Task 7: Update `html_generator.py` — scaffold chapter offset attr

**Files:**
- Modify: `scripts/ai-techradar-agent/html_generator.py`

**Step 1: Update `_card()` to emit `data-chapter-offset`**

In `html_generator.py`, the `_card()` function currently generates `data-tags`. Add `data-chapter-offset`:

```python
def _card(item: dict, extra_class: str = "") -> str:
    cls = f"card {extra_class}".strip()
    tag_keys = " ".join(t for t in item.get("tags", []) if t in TAG_META)
    title_html = escape(item.get("title", ""))
    link = item.get("link", "")
    via = escape(item.get("source", ""))
    summary = escape(item.get("summary", ""))

    title_block = (
        f'<h3><a href="{escape(link)}">{title_html}</a></h3>'
        if link else
        f"<h3>{title_html}</h3>"
    )

    tags_html = ""
    tags = item.get("tags", [])
    if tags:
        tag_spans = "".join(
            f'<span class="tag {TAG_META[t][0]}">{TAG_META[t][1]}</span>'
            for t in tags if t in TAG_META
        )
        if tag_spans:
            tags_html = f'\n    <div class="tags">{tag_spans}</div>'

    data_tags = f' data-tags="{tag_keys}"' if tag_keys else ""
    chapter_offset = item.get("chapter_start_seconds")
    data_chapter = f' data-chapter-offset="{chapter_offset}"' if chapter_offset is not None else ""

    return (
        f'  <div class="{cls}"{data_tags}{data_chapter}>\n'
        f'    <div class="via">{via}</div>\n'
        f"    {title_block}\n"
        f"    <p>{summary}</p>{tags_html}\n"
        f"  </div>\n"
    )
```

**Step 2: Verify no regressions**

```bash
cd scripts/ai-techradar-agent
uv run python -c "from html_generator import generate_html; html = generate_html([], [], [], [], __import__('datetime').datetime.now()); print('OK', len(html), 'chars')"
```
Expected: `OK NNN chars`

**Step 3: Commit**

```bash
git add scripts/ai-techradar-agent/html_generator.py
git commit -m "feat: html_generator adds data-chapter-offset attr to cards (podcast link scaffold)"
```

---

## Task 8: Create `generate-podcast-rss.py`

**Files:**
- Create: `.github/scripts/generate-podcast-rss.py`

**Step 1: Write tests**

Create `scripts/ai-techradar-agent/test_podcast_rss.py`:

```python
"""Tests for generate-podcast-rss.py RSS generation logic."""
import sys, tempfile, json, unittest
from pathlib import Path
from datetime import datetime

# Add .github/scripts to path for testing
sys.path.insert(0, str(Path(__file__).parents[2] / ".github" / "scripts"))


class TestRSSGeneration(unittest.TestCase):
    def setUp(self):
        # Create temp directory with fake MP3/JSON files
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)

        # Create fake MP3 files with matching chapters JSON
        for date_str in ["2026-05-21", "2026-05-20"]:
            mp3 = self.tmpdir / f"ai-radar-{date_str}.mp3"
            mp3.write_bytes(b"\xff\xfb" * 100)  # fake MP3 header

            chap_json = self.tmpdir / f"ai-radar-{date_str}.chapters.json"
            chap_json.write_text(json.dumps({
                "version": "1.2.0",
                "chapters": [
                    {"startTime": 0, "endTime": 22, "title": "Introduction"},
                    {"startTime": 22, "endTime": 600, "title": "Top story"},
                ]
            }))

    def tearDown(self):
        self.tmp.cleanup()

    def test_rss_contains_items(self):
        from generate_podcast_rss import build_rss_feed
        base_url = "https://example.com/techradar/AI"
        xml = build_rss_feed(self.tmpdir, base_url, max_episodes=20)
        self.assertIn("<rss", xml)
        self.assertIn("ai-radar-2026-05-21.mp3", xml)
        self.assertIn("ai-radar-2026-05-20.mp3", xml)

    def test_rss_limits_to_max_episodes(self):
        from generate_podcast_rss import build_rss_feed
        xml = build_rss_feed(self.tmpdir, "https://example.com/techradar/AI", max_episodes=1)
        # Only the most recent episode should appear
        self.assertIn("2026-05-21", xml)
        self.assertNotIn("2026-05-20", xml)

    def test_rss_has_itunes_namespace(self):
        from generate_podcast_rss import build_rss_feed
        xml = build_rss_feed(self.tmpdir, "https://example.com/techradar/AI")
        self.assertIn("xmlns:itunes", xml)
        self.assertIn("xmlns:podcast", xml)
```

**Step 2: Run tests to verify they fail**

```bash
cd scripts/ai-techradar-agent
uv run python -m pytest test_podcast_rss.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'generate_podcast_rss'`

**Step 3: Create `.github/scripts/generate-podcast-rss.py`**

```python
#!/usr/bin/env python3
"""Generate podcast.rss RSS feed from ai-radar-*.mp3 files.

Usage: python3 .github/scripts/generate-podcast-rss.py

Scans techradar/AI/ for MP3 files, reads paired .chapters.json for duration,
writes techradar/AI/podcast.rss. Keeps last 20 episodes.

Run from repo root.
"""

import json
import os
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
OUTPUT_DIR = REPO_ROOT / "techradar" / "AI"
BASE_URL = "https://keithfry.github.io/web-pages/techradar/AI"
MAX_EPISODES = 20


def _duration_from_chapters(chapters_path: Path) -> int:
    """Return total duration in seconds from chapters JSON endTime of last chapter."""
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
    stem = mp3_path.stem  # ai-radar-2026-05-21
    parts = stem.split("-")
    if len(parts) >= 5:
        try:
            y, m, d = int(parts[2]), int(parts[3]), int(parts[4])
            return datetime(y, m, d, 8, 0, 0, tzinfo=timezone.utc)
        except (ValueError, IndexError):
            pass
    return None


def build_rss_feed(output_dir: Path, base_url: str, max_episodes: int = MAX_EPISODES) -> str:
    """Build RSS XML string from MP3 files in output_dir."""
    mp3_files = sorted(output_dir.glob("ai-radar-*.mp3"), reverse=True)[:max_episodes]

    items_xml = []
    for mp3 in mp3_files:
        date = _date_from_filename(mp3)
        if not date:
            continue

        date_str = mp3.stem.replace("ai-radar-", "")  # 2026-05-21
        chap_json = output_dir / f"ai-radar-{date_str}.chapters.json"
        duration = _duration_from_chapters(chap_json) if chap_json.exists() else 0
        file_size = mp3.stat().st_size
        chap_url = f"{base_url}/ai-radar-{date_str}.chapters.json"
        mp3_url = f"{base_url}/ai-radar-{date_str}.mp3"
        guid = mp3_url
        pub_date = format_datetime(date)
        title_date = date.strftime("%B %-d, %Y")

        chap_tag = (
            f'      <podcast:chapters url="{chap_url}" type="application/json+chapters"/>\n'
            if chap_json.exists() else ""
        )

        items_xml.append(f"""  <item>
    <title>AI &amp; Robotics Radar — {title_date}</title>
    <pubDate>{pub_date}</pubDate>
    <enclosure url="{mp3_url}" type="audio/mpeg" length="{file_size}"/>
    <itunes:duration>{duration}</itunes:duration>
    <guid isPermaLink="true">{guid}</guid>
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
    <itunes:image href="{base_url}/podcast-cover.jpg"/>
{items_block}
  </channel>
</rss>
"""


def main():
    xml = build_rss_feed(OUTPUT_DIR, BASE_URL)
    out = OUTPUT_DIR / "podcast.rss"
    out.write_text(xml, encoding="utf-8")
    print(f"Wrote {out} ({len(xml):,} chars, {xml.count('<item>')} episodes)")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests**

```bash
cd scripts/ai-techradar-agent
uv run python -m pytest test_podcast_rss.py -v
```
Expected: all 3 tests PASS

**Step 5: Commit**

```bash
git add .github/scripts/generate-podcast-rss.py scripts/ai-techradar-agent/test_podcast_rss.py
git commit -m "feat: generate-podcast-rss.py — builds Podcasting 2.0 RSS feed from MP3 files"
```

---

## Task 9: Update GitHub Actions and index generation

**Files:**
- Modify: `.github/workflows/generate-site-assets.yml`
- Modify: `.github/scripts/generate-index.sh`

**Step 1: Add podcast RSS step to `generate-site-assets.yml`**

After the "Generate indexes" step, add:

```yaml
      - name: Generate podcast RSS feed
        run: |
          python3 .github/scripts/generate-podcast-rss.py
```

This goes before the "Generate certification images manifest" step.

**Step 2: Update `generate-index.sh` to show 🎙 badge**

In `generate-index.sh`, find where file links are written in the HTML. The file writes `<a href="...">filename</a>`. After the link, add a 🎙 symbol if a matching `.mp3` exists.

Find the section that writes the `<a>` tag for each file (around line 100+ in the existing script) and add:

```bash
# After building the link for each file, check for matching MP3
audio_badge=""
if [[ "$fname" =~ ([0-9]{4}-[0-9]{2}-[0-9]{2}) ]]; then
  date_part="${BASH_REMATCH[1]}"
  if [[ -f "$dir/ai-radar-${date_part}.mp3" ]]; then
    audio_badge=' <a href="ai-radar-'"${date_part}"'.mp3" title="Listen to podcast" style="text-decoration:none;">🎙</a>'
  fi
fi
```

And include `${audio_badge}` in the output line after the file link.

Note: Read the full `generate-index.sh` to find the exact line before editing — the file was truncated in exploration.

**Step 3: Test RSS generation locally**

```bash
python3 .github/scripts/generate-podcast-rss.py
head -30 techradar/AI/podcast.rss
```
Expected: valid XML with `<rss version="2.0"` and `xmlns:itunes` attributes

**Step 4: Commit**

```bash
git add .github/workflows/generate-site-assets.yml .github/scripts/generate-index.sh
git commit -m "feat: CI generates podcast RSS feed; index shows 🎙 badge for audio episodes"
```

---

## Task 10: End-to-end dry run verification

**Step 1: Run with `--dry-run` and `--no-email`**

```bash
cd scripts/ai-techradar-agent
uv run main.py --date 2026-05-21 --dry-run --no-email
```
Expected output contains:
- `── Step 6: Enriching N items ──`
- `── Step 7a: Generating HTML ──`
- `── Step 7b: Generating podcast audio ──` (or `skipped` if kokoro model not yet downloaded)
- `── Step 8: Saving ──`
- `Dry run complete`

**Step 2: Verify output files**

```bash
ls -lh ../../techradar/AI/ai-radar-2026-05-21.*
```
Expected: `.html`, `.json` exist (`.mp3` and `.chapters.json` if podcast ran)

**Step 3: Validate JSON structure**

```bash
python3 -c "
import json
from pathlib import Path
data = json.loads(Path('../../techradar/AI/ai-radar-2026-05-21.json').read_text())
print('date:', data['date'])
print('intro:', data['intro_script'][:80])
print('items:', len(data['items']))
podcast_items = [i for i in data['items'] if i.get('include_in_podcast')]
print('podcast items:', len(podcast_items))
if podcast_items:
    print('first item rank:', podcast_items[0]['rank'])
    print('audio_script words:', len(podcast_items[0]['audio_script'].split()))
    print('chapter_start_seconds:', podcast_items[0]['chapter_start_seconds'])
"
```

**Step 4: Validate MP3 chapters (if podcast ran)**

```bash
python3 -c "
from mutagen.id3 import ID3
from pathlib import Path
mp3 = Path('../../techradar/AI/ai-radar-2026-05-21.mp3')
if mp3.exists():
    tags = ID3(str(mp3))
    chaps = [k for k in tags.keys() if k.startswith('CHAP')]
    print(f'{len(chaps)} chapters in MP3')
    for k in chaps[:3]:
        print(f'  {k}: {tags[k].sub_frames}')
else:
    print('MP3 not found — podcast may have been skipped')
"
```

**Step 5: Test RSS feed generation**

```bash
python3 .github/scripts/generate-podcast-rss.py
python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('techradar/AI/podcast.rss')
items = tree.findall('.//{http://www.w3.org/2005/Atom}item') or tree.findall('.//item')
print(f'{len(items)} items in podcast.rss')
"
```

**Step 6: Subscribe in Pocket Casts (manual)**

After pushing to GitHub:
1. Open Pocket Casts → Add Podcast → RSS URL
2. Enter: `https://keithfry.github.io/web-pages/techradar/AI/podcast.rss`
3. Verify episode appears with chapter markers visible
4. Test BT device previous/next to navigate chapters

---

## Notes

- **First run**: Kokoro downloads ~80MB model to `~/.cache/huggingface/` automatically on first TTS call
- **Podcast generation time**: ~5-10 minutes for a full episode (30+ items × ~8s TTS each + ffmpeg)
- **`--no-podcast` flag**: use during development or if audio gen fails — HTML + JSON still committed
- **Podcast errors don't block HTML**: `_gen_podcast()` catches all exceptions, logs warning, HTML commits regardless
- **Future feature**: `data-chapter-offset` attr on HTML cards is scaffolded but inert; activate with JS `<a>` injection in a future task
