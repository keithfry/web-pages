# Transcript Export for Read-Along

Export a `transcript.json` alongside each generated MP3 so the podcast client can display synchronized segment text without needing Whisper transcription.

## Motivation

The generator already knows the exact spoken text (`audio_script`) and exact segment start times (`actual_starts`) for every chapter. Exporting them together enables paragraph-level read-along on the client at zero extra cost.

## Changes

### `podcast_generator.py` — export `transcript.json`

After the chapters list is built in `generate_podcast()`, write a transcript file:

```python
transcript_json_path = output_dir / f"{file_prefix}-{date_str}.transcript.json"

transcript_segments = [
    {
        "startTime": 0,
        "endTime": int(actual_starts[1]) if len(actual_starts) > 1 else total_duration,
        "text": intro_script,
        "voice": _voice_for(0),
    }
]
for item, start, end in zip(
    podcast_items,
    actual_starts[1:],
    actual_starts[2:] + [float(total_duration)],
):
    transcript_segments.append({
        "startTime": int(start),
        "endTime": int(end),
        "text": item["audio_script"],
        "voice": _voice_for(item["voice_index"]),
    })

transcript_json_path.write_text(
    json.dumps({"version": "1.0.0", "segments": transcript_segments}, indent=2),
    encoding="utf-8",
)
log(f"  Wrote transcript JSON: {transcript_json_path}")
```

Return `transcript_json_path` alongside the existing `(mp3_path, chapters_json_path)` tuple, or keep it as a side effect — caller doesn't need to pass it on.

### `podcast_rss.py` — expose transcript URL in feed

Add a `<podcast:transcript>` tag per item so the Android client can discover the file from the RSS feed without hardcoding URL patterns:

```python
transcript_json = output_dir / f"{file_prefix}-{date_str}.transcript.json"
transcript_url = f"{base_url}/{file_prefix}-{date_str}.transcript.json"

transcript_tag = (
    f'      <podcast:transcript url="{transcript_url}" type="application/json"/>\n'
    if transcript_json.exists() else ""
)
```

Add `{transcript_tag}` to the item XML alongside the existing `{chap_tag}`.

### `publisher.py` — include `transcript.json` in upload

Ensure `*.transcript.json` files are included in whatever upload/sync step pushes artifacts to GitHub Pages. Check glob patterns in the publisher.

## Output format

```json
{
  "version": "1.0.0",
  "segments": [
    {
      "startTime": 0,
      "endTime": 47,
      "text": "Welcome to AI Daily Radar for June 6th...",
      "voice": "af_heart"
    },
    {
      "startTime": 47,
      "endTime": 158,
      "text": "From TechCrunch, \"Anthropic releases Claude 4\"...",
      "voice": "am_echo"
    }
  ]
}
```

`startTime` / `endTime` are integer seconds, matching the existing chapters.json convention.

## Accuracy note

Segment boundaries are exact (measured from actual WAV durations). Text within a segment is paragraph-level only — no word timestamps. Word-level sync requires a separate Whisper pass on the client (see client-side plan).
