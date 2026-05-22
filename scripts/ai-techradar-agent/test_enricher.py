"""Tests for enricher.py — pure logic, no LLM calls needed."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


class TestEstimateChapterTimes(unittest.TestCase):
    def test_chapter_times_increase_monotonically(self):
        from enricher import _estimate_chapter_times
        intro = "Welcome to the show."  # ~4 words
        scripts = ["Script one has about ten words total in it.", "Script two also has ten words in it here."]
        times = _estimate_chapter_times(intro, scripts)
        self.assertEqual(len(times), 3)  # intro start + 2 item starts
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


if __name__ == "__main__":
    unittest.main()
