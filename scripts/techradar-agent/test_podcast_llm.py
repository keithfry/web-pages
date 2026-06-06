"""Smoke tests for podcast LLM functions — requires Ollama running."""
import unittest
from llm import rank_items, generate_audio_script, generate_intro_script
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

SAMPLE_ITEMS = [
    {"title": "Google releases Gemini 2.5 Flash", "source": "Google DeepMind", "summary": "Google announced Gemini 2.5 Flash with improved speed.", "tags": ["model"], "_source_type": "rss"},
    {"title": "OpenAI raises $40B at $340B valuation", "source": "TechCrunch", "summary": "OpenAI closed a record funding round.", "tags": ["policy"], "_source_type": "rss"},
    {"title": "Anthropic releases Claude 4 Opus", "source": "Anthropic", "summary": "Claude 4 Opus is Anthropic's most capable model.", "tags": ["model"], "_source_type": "rss"},
]

MODEL = "llama3.2:3b"

class TestPodcastLLM(unittest.TestCase):
    def test_rank_items_returns_all_with_rank(self):
        ranked = rank_items(SAMPLE_ITEMS, MODEL)
        self.assertEqual(len(ranked), len(SAMPLE_ITEMS))
        self.assertIn("rank", ranked[0])
        ranks = [item["rank"] for item in ranked]
        self.assertEqual(sorted(ranks), list(range(1, len(SAMPLE_ITEMS) + 1)))

    def test_generate_audio_script_returns_string(self):
        script = generate_audio_script(SAMPLE_ITEMS[0], MODEL)
        self.assertIsInstance(script, str)
        self.assertGreater(len(script), 50)
        word_count = len(script.split())
        self.assertLessEqual(word_count, 200, f"Script too long: {word_count} words")

    def test_generate_intro_script_mentions_date(self):
        date = datetime(2026, 5, 21, 8, 0, tzinfo=ET)
        intro = generate_intro_script(SAMPLE_ITEMS, date, MODEL)
        self.assertIsInstance(intro, str)
        self.assertGreater(len(intro), 20)
        self.assertTrue(
            "May" in intro or "2026" in intro,
            f"Intro doesn't mention date: {intro!r}"
        )

if __name__ == "__main__":
    unittest.main()
