"""Tests for generate-podcast-rss.py RSS generation logic."""
import sys
import tempfile
import json
import unittest
from pathlib import Path
from datetime import datetime, timezone

# Add .github/scripts to path for testing
sys.path.insert(0, str(Path(__file__).parents[2] / ".github" / "scripts"))


class TestRSSGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)

        for date_str in ["2026-05-21", "2026-05-20"]:
            mp3 = self.tmpdir / f"ai-radar-{date_str}.mp3"
            mp3.write_bytes(b"\xff\xfb" * 100)  # fake MP3 bytes

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

    def test_rss_contains_both_items(self):
        from generate_podcast_rss import build_rss_feed
        xml = build_rss_feed(self.tmpdir, "https://example.com/techradar/AI")
        self.assertIn("<rss", xml)
        self.assertIn("ai-radar-2026-05-21.mp3", xml)
        self.assertIn("ai-radar-2026-05-20.mp3", xml)

    def test_rss_limits_to_max_episodes(self):
        from generate_podcast_rss import build_rss_feed
        xml = build_rss_feed(self.tmpdir, "https://example.com/techradar/AI", max_episodes=1)
        self.assertIn("2026-05-21", xml)
        self.assertNotIn("2026-05-20", xml)

    def test_rss_has_required_namespaces(self):
        from generate_podcast_rss import build_rss_feed
        xml = build_rss_feed(self.tmpdir, "https://example.com/techradar/AI")
        self.assertIn("xmlns:itunes", xml)
        self.assertIn("xmlns:podcast", xml)

    def test_rss_duration_from_chapters(self):
        from generate_podcast_rss import build_rss_feed, _duration_from_chapters
        chap_path = self.tmpdir / "ai-radar-2026-05-21.chapters.json"
        duration = _duration_from_chapters(chap_path)
        self.assertEqual(duration, 600)  # endTime of last chapter

    def test_rss_chapters_tag_present(self):
        from generate_podcast_rss import build_rss_feed
        xml = build_rss_feed(self.tmpdir, "https://example.com/techradar/AI")
        self.assertIn("podcast:chapters", xml)
        self.assertIn(".chapters.json", xml)
