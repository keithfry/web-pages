"""Generate a podcast MP3 with ID3 chapter markers from enriched data.

Requires ffmpeg on PATH and Kokoro TTS installed (uv sync).
"""

import json
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

_FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

from enricher import KOKORO_VOICES
from config import TTS_WORKERS

_tts_thread_local = threading.local()


def _get_pipeline():
    """Return a thread-local KPipeline, creating it on first use per thread."""
    if not hasattr(_tts_thread_local, "pipeline"):
        from kokoro import KPipeline
        _tts_thread_local.pipeline = KPipeline(lang_code="a")
    return _tts_thread_local.pipeline


def _voice_for(voice_index: int) -> str:
    return KOKORO_VOICES[voice_index % len(KOKORO_VOICES)]


def _build_chapters_json(chapters: list[dict], episode_title: str | None = None) -> str:
    """Build Podcasting 2.0 chapters JSON string."""
    data: dict = {"version": "1.2.0"}
    if episode_title:
        data["title"] = episode_title
    data["chapters"] = chapters
    return json.dumps(data, indent=2)


def _tts_segment(text: str, voice: str, out_wav: Path) -> float:
    """Synthesize text to WAV using thread-local Kokoro pipeline. Returns duration in seconds."""
    import soundfile as sf
    import numpy as np

    pipeline = _get_pipeline()
    audio_chunks = []
    sample_rate = 24000

    for _, _, audio in pipeline(text, voice=voice):
        audio_chunks.append(audio)

    if not audio_chunks:
        raise RuntimeError(f"Kokoro produced no audio for text: {text[:50]!r}")

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
                _FFMPEG, "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-ar", "22050", "-ac", "1", "-b:a", "64k",
                str(out_mp3),
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg failed: {e.stderr.decode()}") from e
    finally:
        concat_file.unlink(missing_ok=True)


def _write_id3_chapters(
    mp3_path: Path,
    chapters: list[dict],
    episode_title: str | None = None,
    cover_path: Path | None = None,
) -> None:
    """Write ID3v2 CHAP frames (and optional cover art) to an MP3 file."""
    from mutagen.id3 import ID3, CHAP, CTOC, TIT2, APIC
    from mutagen.id3 import ID3NoHeaderError

    try:
        tags = ID3(str(mp3_path))
    except ID3NoHeaderError:
        tags = ID3()

    if episode_title:
        tags.add(TIT2(encoding=3, text=[episode_title]))

    if cover_path and cover_path.exists():
        tags.add(APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,
            desc="Cover",
            data=cover_path.read_bytes(),
        ))

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

    tags.add(CTOC(
        element_id="toc",
        flags=0x03,  # top-level, ordered
        child_element_ids=chap_ids,
        sub_frames=[TIT2(encoding=3, text=["Table of Contents"])],
    ))
    tags.save(str(mp3_path), v2_version=3)


def generate_podcast(
    enriched_data: dict,
    date: datetime,
    output_dir: Path,
    file_prefix: str = "ai-radar",
    topic_label: str = "AI",
    log=print,
) -> tuple[Path, Path, Path | None, Path | None]:
    """Generate MP3 + chapters.json + episode cover + OG card from enriched data.

    Also updates enriched_data['items'] with actual chapter_start_seconds from audio timings.

    Returns:
        (mp3_path, chapters_json_path, episode_cover_path_or_None, og_card_path_or_None)
    """
    date_str = date.strftime("%Y-%m-%d")
    mp3_path = output_dir / f"{file_prefix}-{date_str}.mp3"
    chapters_json_path = output_dir / f"{file_prefix}-{date_str}.chapters.json"

    tagline = enriched_data.get("episode_tagline", "")
    title_date = f"{date.strftime('%B')} {date.day}, {date.year}"
    episode_title = f"{title_date} : {tagline}" if tagline else f"{topic_label} Radar — {title_date}"

    podcast_items = [i for i in enriched_data["items"] if i.get("include_in_podcast")]
    intro_script = enriched_data["intro_script"]
    outro_script = enriched_data.get("outro_script", "")

    log(f"  Generating audio for intro + {len(podcast_items)} items + outro ({TTS_WORKERS} workers)...")

    output_dir.mkdir(parents=True, exist_ok=True)

    # outro order_index sits after all ranked items
    _outro_idx = max((item["rank"] for item in podcast_items), default=0) + 1

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Build work list: (order_index, wav_path, text, voice, label)
        # order_index 0 = intro, 1..N = items in rank order, N+1 = outro
        work = [(0, tmp / "intro.wav", intro_script, _voice_for(0), "intro")]
        for item in podcast_items:
            work.append((
                item["rank"],
                tmp / f"item_{item['rank']:03d}.wav",
                item["audio_script"],
                _voice_for(item["voice_index"]),
                f"item {item['rank']} ({item['title'][:40]})",
            ))
        if outro_script:
            work.append((_outro_idx, tmp / "outro.wav", outro_script, _voice_for(0), "outro"))

        # Synthesize all segments in parallel; results keyed by order_index
        durations: dict[int, float] = {}

        def _synth(order_idx: int, wav_path: Path, text: str, voice: str, label: str) -> tuple[int, float]:
            log(f"  [tts] {label} ({voice})...")
            dur = _tts_segment(text, voice, wav_path)
            return order_idx, dur

        with ThreadPoolExecutor(max_workers=TTS_WORKERS) as executor:
            futures = {
                executor.submit(_synth, *w): w[0] for w in work
            }
            for future in as_completed(futures):
                order_idx, dur = future.result()
                durations[order_idx] = dur

        # Reconstruct ordered wav list and compute chapter start times
        ordered = sorted(work, key=lambda w: w[0])
        wav_files: list[Path] = []
        actual_starts: list[float] = []
        cursor = 0.0
        for order_idx, wav_path, _, _, _ in ordered:
            wav_files.append(wav_path)
            actual_starts.append(cursor)
            cursor += durations[order_idx]

        # Write actual chapter start times back to items (actual_starts[0] = intro)
        for i, item in enumerate(podcast_items):
            item["chapter_start_seconds"] = int(actual_starts[i + 1])

        total_duration = int(cursor)
        log(f"  Total audio: {total_duration}s ({total_duration // 60}m {total_duration % 60}s)")

        # Concat all WAV → MP3
        log("  Merging WAV segments → MP3...")
        _concat_wavs_to_mp3(wav_files, mp3_path)

    # Build chapters list
    chapters = [{"startTime": 0, "title": "Introduction"}]
    for item, start in zip(podcast_items, actual_starts[1:]):
        chap = {"startTime": int(start), "title": item["title"]}
        if item.get("link"):
            chap["url"] = item["link"]
        chapters.append(chap)

    # Outro chapter — starts at actual_starts[_outro_idx position]
    if outro_script:
        outro_start = int(actual_starts[len(podcast_items) + 1])
        chapters.append({"startTime": outro_start, "title": "Sign Off"})

    # Add endTime to each chapter
    for i, chap in enumerate(chapters):
        if i + 1 < len(chapters):
            chap["endTime"] = chapters[i + 1]["startTime"]
        else:
            chap["endTime"] = total_duration

    # Write Podcasting 2.0 chapters JSON
    chapters_json_path.write_text(_build_chapters_json(chapters, episode_title), encoding="utf-8")
    log(f"  Wrote chapters JSON: {chapters_json_path}")

    # Generate episode cover + OG social card
    date_str = date.strftime("%Y-%m-%d")
    cover_path = output_dir / f"{file_prefix}-{date_str}.jpg"
    og_path = output_dir / f"{file_prefix}-{date_str}.og.jpg"
    try:
        from cover_generator import generate_episode_cover, generate_og_card
        display_tagline = tagline or topic_label
        generate_episode_cover(topic_label, display_tagline, date, total_duration, cover_path)
        generate_og_card(topic_label, display_tagline, date, total_duration, og_path)
        log(f"  Episode cover: {cover_path.name}, OG card: {og_path.name}")
    except Exception as e:
        log(f"  WARNING: cover generation failed: {e}")
        cover_path = None
        og_path = None

    # Embed ID3 chapter tags and cover art in MP3
    _write_id3_chapters(mp3_path, chapters, episode_title, cover_path)
    log(f"  Wrote ID3 tags to: {mp3_path}")

    return mp3_path, chapters_json_path, cover_path, og_path
