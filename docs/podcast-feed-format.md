# Podcast Feed Format

Documents the RSS feed (`podcast.xml`) and all sidecar files produced by the techradar-agent pipeline. Two feeds exist: AI and Robotics.

## Feed URLs

| Feed | URL |
|------|-----|
| AI | `https://keithfry.github.io/web-pages/techradar/AI/podcast.xml` |
| Robotics | `https://keithfry.github.io/web-pages/techradar/Robotics/podcast.xml` |

---

## File Layout Per Episode

```
techradar/{AI|Robotics}/YYYY-MM/
├── {prefix}-YYYY-MM-DD.mp3              # Audio (Kokoro TTS, 64kbps mono MP3)
├── {prefix}-YYYY-MM-DD.chapters.json    # Podcasting 2.0 chapter markers
├── {prefix}-YYYY-MM-DD.transcript.json  # Segment text + timestamps (read-along)
├── {prefix}-YYYY-MM-DD.json             # Full enriched data (internal, not linked from feed)
├── {prefix}-YYYY-MM-DD.jpg              # Episode cover art (1400×1400 JPEG)
└── {prefix}-YYYY-MM-DD.og.jpg           # OG social card (1200×630 JPEG)
```

Where `{prefix}` is `ai-radar` or `robotics-radar`.

---

## `podcast.xml` — RSS Feed

### Namespaces

```xml
xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
xmlns:podcast="https://podcastindex.org/namespace/1.0"
xmlns:atom="http://www.w3.org/2005/Atom"
```

### Channel-Level Fields

| Field | Value |
|-------|-------|
| `<title>` | `AI Daily Radar` or `Robotics Daily Radar` |
| `<link>` | Base URL for the topic directory |
| `<atom:link>` | Self-referencing feed URL (`rel="self"`) |
| `<description>` | Static one-liner |
| `<language>` | `en-us` |
| `<lastBuildDate>` | RFC 2822 timestamp of last generation |
| `<itunes:author>` | `Keith Fry` |
| `<itunes:category>` | `Technology > Tech News` |
| `<itunes:explicit>` | `false` |
| `<itunes:image>` | Channel cover art (`podcast-cover.png` in topic root) — present only if file exists |

### Per-Episode Item Fields

```xml
<item>
  <title>{episode_tagline or "AI Radar — {Month D, YYYY}"}</title>
  <pubDate>{RFC 2822, always 08:00:00 UTC}</pubDate>
  <enclosure url="{mp3_url}" type="audio/mpeg" length="{bytes}"/>
  <itunes:duration>HH:MM:SS</itunes:duration>
  <guid isPermaLink="true">{mp3_url}</guid>
  <description>{topic} Radar for {date}. {N} minutes of news.</description>

  <!-- Present only if episode cover JPEG exists on disk -->
  <itunes:image href="{base_url}/{ym_dir}/{prefix}-{date}.jpg"/>

  <!-- Present only if chapters JSON exists on disk -->
  <podcast:chapters url="{...}.chapters.json" type="application/json+chapters"/>

  <!-- Present only if transcript JSON exists on disk -->
  <podcast:transcript url="{...}.transcript.json" type="application/json"/>
</item>
```

**Episode title:** derived from `episode_tagline` in the enriched JSON (LLM-generated 4-word phrase). Falls back to `"{Topic} Radar — {Month D, YYYY}"` if no tagline.

**GUID:** the MP3 URL — stable, used by podcast clients to deduplicate episodes.

**Feed depth:** last 20 episodes (`MAX_EPISODES = 20` in `podcast_rss.py`).

---

## `{prefix}-YYYY-MM-DD.chapters.json` — Podcasting 2.0 Chapters

Spec: [Podcastindex chapters spec v1.2.0](https://github.com/Podcastindex-org/podcast-namespace/blob/main/chapters/jsonChapters.md)

```json
{
  "version": "1.2.0",
  "title": "June 16, 2026 : AI Power Control Growth",
  "chapters": [
    {
      "startTime": 0,
      "title": "Introduction",
      "endTime": 17
    },
    {
      "startTime": 17,
      "title": "US Export Controls Force Anthropic to Disable AI Models",
      "url": "https://...",
      "endTime": 71
    },
    {
      "startTime": 1462,
      "title": "Sign Off",
      "endTime": 1475
    }
  ]
}
```

| Field | Notes |
|-------|-------|
| `version` | Always `"1.2.0"` |
| `title` | Episode tagline (same as RSS `<title>`) |
| `startTime` / `endTime` | Integer seconds, measured from actual WAV durations |
| `url` | Source article link — present on news items, absent on Introduction and Sign Off |

**Chapter order:** Introduction → ranked news items (by LLM relevance score) → Sign Off.

---

## `{prefix}-YYYY-MM-DD.transcript.json` — Read-Along Transcript

Custom format (not a standard). Designed for segment-level read-along in a podcast client.

```json
{
  "version": "1.0.0",
  "segments": [
    {
      "startTime": 0.0,
      "endTime": 17.0,
      "text": "Welcome to your daily dose of AI intelligence for June 16, 2026...",
      "voice": "af_heart"
    },
    {
      "startTime": 17.0,
      "endTime": 71.325,
      "text": "From a.tldrnewsletter.com, \"US Export Controls Force Anthropic...",
      "voice": "af_heart"
    }
  ]
}
```

| Field | Notes |
|-------|-------|
| `version` | Always `"1.0.0"` |
| `startTime` / `endTime` | Float seconds. From TTS synthesis: float precision. From `--transcript-only` backfill: integer precision (from `chapter_start_seconds`). |
| `text` | Exact TTS input text (`audio_script` from enriched JSON). Not post-processed. |
| `voice` | Kokoro voice ID used to synthesize this segment (e.g. `af_heart`, `am_echo`). |

**Segment count:** 1 intro + N podcast items + 1 outro (if present). Matches chapter count.

**Discovered via:** `<podcast:transcript>` tag in RSS feed — clients should not hardcode URL patterns.

**Backfill:** episodes without a transcript can be regenerated with no audio re-synthesis:
```bash
uv run main.py --date YYYY-MM-DD --time 08:00 --transcript-only
```

---

## Voice Assignments

Voices rotate across ranked items using `KOKORO_VOICES` from `enricher.py`. Intro and outro always use `voice_index=0` (`af_heart`). Items cycle through the pool by `voice_index % len(KOKORO_VOICES)`.

---

## Generation Flow

```
enrich()                    → enriched JSON (audio_script, voice_index, chapter_start_seconds)
generate_podcast()          → MP3 + chapters.json + transcript.json + cover.jpg + og.jpg
generate_podcast_rss()      → podcast.xml (scans all MP3s in output_dir, last 20)
```

`podcast.xml` is regenerated on every run — it always reflects the current state of files on disk. Sidecar files (`chapters.json`, `transcript.json`, cover) are emitted as optional tags only if the file exists at RSS generation time.
