# Transcript Export for Read-Along

## Context

The podcast generator already captures `audio_script` (exact TTS input text) and `chapter_start_seconds` (actual post-synthesis timing) per item. We own the text, so transcripts are **exact** — no Whisper needed. This plan adds a `.transcript.json` sidecar file alongside each episode's `.chapters.json`, and exposes it in the RSS feed via the Podcasting 2.0 `<podcast:transcript>` tag.

Companion plan in `podcast-app`: `docs/plans/2026-06-14-read-along-implementation.md`.

---

## Changes

### `scripts/techradar-agent/podcast_generator.py`

**Add `_build_transcript_json()` helper** (alongside `_build_chapters_json` at line 35):

```python
def _build_transcript_json(
    intro_script: str,
    podcast_items: list[dict],
    actual_starts: list[float],
    total_duration_seconds: float,
) -> str:
    """One segment per chapter: intro + each podcast item, with exact text and timing."""
    segments = []

    # Intro segment
    intro_end = actual_starts[1] if len(actual_starts) > 1 else total_duration_seconds
    segments.append({
        "startTime": 0,
        "endTime": int(intro_end),
        "text": intro_script,
        "voice": "af_heart",
    })

    # One segment per podcast item (actual_starts[0]=intro, actual_starts[1]=item0, ...)
    for i, item in enumerate(podcast_items):
        start = actual_starts[i + 1]
        end = actual_starts[i + 2] if i + 2 < len(actual_starts) else total_duration_seconds
        segments.append({
            "startTime": int(start),
            "endTime": int(end),
            "text": item["audio_script"],
            "voice": _voice_for(item["voice_index"]),
        })

    return json.dumps({"version": "1.0.0", "segments": segments}, indent=2)
```

**Call it after `chapters_json_path.write_text(...)` (line 229)**:

```python
transcript_json_path = chapters_json_path.parent / chapters_json_path.name.replace(
    ".chapters.json", ".transcript.json"
)
total_duration = chapters[-1]["endTime"] if chapters else 0.0
transcript_json_path.write_text(
    _build_transcript_json(intro_script, podcast_items, actual_starts, total_duration),
    encoding="utf-8",
)
```

**Update return value** (line 236) to include transcript path:

```python
return mp3_path, chapters_json_path, transcript_json_path
```

Update callers in `main.py` to unpack 3 values.

---

### `scripts/techradar-agent/podcast_rss.py`

**Context:** chapters tag built at lines 81–84, inserted at line 93. Chapter URL follows pattern `f"{base_url}/{ym_dir}/{file_prefix}-{date_str}.chapters.json"` (line 71).

**After the `chap_tag` block (line 84)**, add:

```python
transcript_path = chap_json.parent / chap_json.name.replace(".chapters.json", ".transcript.json")
transcript_tag = (
    f'<podcast:transcript url="{chap_url.replace(".chapters.json", ".transcript.json")}"'
    f' type="application/json"/>\n'
    if transcript_path.exists() else ""
)
```

**Insert `transcript_tag` into the item XML** (same location as `chap_tag`, line 93):

```xml
{chap_tag}{transcript_tag}
```

No new XML namespace needed — `podcast:` is already declared.

---

## Output

Each episode produces a new sidecar:
```
techradar/{AI|Robotics}/YYYY-MM/
├── {prefix}-YYYY-MM-DD.mp3
├── {prefix}-YYYY-MM-DD.chapters.json
└── {prefix}-YYYY-MM-DD.transcript.json   ← NEW
```

Transcript format:
```json
{
  "version": "1.0.0",
  "segments": [
    { "startTime": 0,  "endTime": 20,  "text": "Welcome to AI Daily Radar...", "voice": "af_heart" },
    { "startTime": 20, "endTime": 131, "text": "From TechCrunch, ...",          "voice": "am_echo"  }
  ]
}
```

---

## Verification

```bash
cd scripts/techradar-agent
uv run main.py --date 2026-06-14 --topic ai --dry-run
```

1. Confirm `techradar/AI/2026-06/ai-radar-2026-06-14.transcript.json` written
2. Segment count = 1 (intro) + N podcast items; `startTime`/`endTime` match chapters.json
3. Run with `--podcast-only` to test just the audio/transcript path
4. Check `podcast.xml` contains `<podcast:transcript url="...transcript.json" type="application/json"/>` per item
