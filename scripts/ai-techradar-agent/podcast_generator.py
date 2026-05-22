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


def _tts_segment(text: str, voice: str, out_wav: Path, pipeline) -> float:
    """Synthesize text to WAV using Kokoro pipeline. Returns duration in seconds."""
    import soundfile as sf
    import numpy as np

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
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-ar", "22050", "-b:a", "128k",
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
    from mutagen.id3 import ID3, CHAP, CTOC, TIT2
    from mutagen.id3 import ID3NoHeaderError

    try:
        tags = ID3(str(mp3_path))
    except ID3NoHeaderError:
        tags = ID3()
    # ID3() with no args creates a new header object; tags.save(path) writes it to file.

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
    log=print,
) -> tuple[Path, Path]:
    """Generate MP3 + chapters.json from enriched data.

    Also updates enriched_data['items'] with actual chapter_start_seconds from audio timings.

    Returns:
        (mp3_path, chapters_json_path)
    """
    date_str = date.strftime("%Y-%m-%d")
    mp3_path = output_dir / f"ai-radar-{date_str}.mp3"
    chapters_json_path = output_dir / f"ai-radar-{date_str}.chapters.json"

    podcast_items = [i for i in enriched_data["items"] if i.get("include_in_podcast")]
    intro_script = enriched_data["intro_script"]

    log(f"  Generating audio for intro + {len(podcast_items)} items...")

    log("  Loading Kokoro TTS model...")
    from kokoro import KPipeline
    pipeline = KPipeline(lang_code="a")

    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        wav_files: list[Path] = []
        actual_starts: list[float] = []
        cursor = 0.0

        # Intro segment (always voice 0)
        intro_wav = tmp / "intro.wav"
        log(f"  [tts] intro ({_voice_for(0)}): {intro_script[:60]}...")
        intro_dur = _tts_segment(intro_script, _voice_for(0), intro_wav, pipeline)
        wav_files.append(intro_wav)
        actual_starts.append(cursor)
        cursor += intro_dur

        # Item segments
        for item in podcast_items:
            wav_path = tmp / f"item_{item['rank']:03d}.wav"
            voice = _voice_for(item["voice_index"])
            script = item["audio_script"]
            log(f"  [tts] item {item['rank']} ({voice}): {item['title'][:50]}...")
            dur = _tts_segment(script, voice, wav_path, pipeline)
            wav_files.append(wav_path)
            actual_starts.append(cursor)
            item["chapter_start_seconds"] = int(cursor)
            cursor += dur

        total_duration = int(cursor)
        log(f"  Total audio: {total_duration}s ({total_duration // 60}m {total_duration % 60}s)")

        # Concat all WAV → MP3
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

    # Write Podcasting 2.0 chapters JSON
    chapters_json_path.write_text(_build_chapters_json(chapters), encoding="utf-8")
    log(f"  Wrote chapters JSON: {chapters_json_path}")

    # Embed ID3 chapter tags in MP3
    _write_id3_chapters(mp3_path, chapters)
    log(f"  Wrote ID3 chapters to: {mp3_path}")

    return mp3_path, chapters_json_path
