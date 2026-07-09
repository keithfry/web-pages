"""Central configuration — reads from .env or environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load Gmail credentials from ~/keys/kfopenclaw-gmail.env (outside the repo)
load_dotenv(Path.home() / "keys" / "kfopenclaw-gmail.env")
# Load project .env (non-secret settings); values already set above are not overwritten
load_dotenv(Path(__file__).parent / ".env")

# --- LLM models ---
SUMMARIZE_MODEL: str = os.environ.get("SUMMARIZE_MODEL", "llama3.2")
RANK_MODEL: str = os.environ.get("RANK_MODEL", "qwen3.5:9b")
DEDUP_MODEL: str = os.environ.get("DEDUP_MODEL", "claude-haiku-4-5")
AD_DETECTOR_MODEL: str = os.environ.get("AD_DETECTOR_MODEL", "ad-detector")
AD_GATE_ENABLED: bool = os.environ.get("AD_GATE_ENABLED", "1") not in ("0", "false", "False", "no")

# --- Pipeline ---
LOOKBACK_HOURS: int = int(os.environ.get("LOOKBACK_HOURS", 24))

# --- Gmail ---
# Option A: individual client ID + secret in .env (preferred)
GMAIL_CLIENT_ID: str = os.environ.get("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET: str = os.environ.get("GMAIL_CLIENT_SECRET", "")
# Option B: path to a downloaded credentials.json file
GMAIL_CREDENTIALS: Path = Path(
    os.environ.get("GMAIL_CREDENTIALS", Path(__file__).parent / "credentials.json")
)
GMAIL_TOKEN: Path = Path(
    os.environ.get("GMAIL_TOKEN", Path(__file__).parent / "token.json")
)
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# --- Paths ---
# Repo root is 2 levels up from this file (scripts/techradar-agent/ → project root)
REPO_ROOT: Path = Path(__file__).parent.parent.parent
AI_OUTPUT_DIR: Path = REPO_ROOT / "techradar" / "AI"
ROBOTICS_OUTPUT_DIR: Path = REPO_ROOT / "techradar" / "Robotics"
OUTPUT_DIR: Path = AI_OUTPUT_DIR  # backward-compat alias
FEEDS_CSV: Path = REPO_ROOT / "data" / "ai-rss-feeds.csv"

# --- Git identity (matches existing server.py convention) ---
GIT_USER_NAME = "Keith Fry"
GIT_USER_EMAIL = "keithfry@gmail.com"

# arXiv feeds: max papers per feed to include
ARXIV_MAX_PAPERS = 10

# Parallel workers for LLM summarization — set OLLAMA_NUM_PARALLEL to the same value
# so Ollama actually processes requests concurrently rather than queuing them
LLM_WORKERS: int = int(os.environ.get("LLM_WORKERS", 2))

# Parallel workers for URL fetching (I/O bound — can be higher than LLM_WORKERS)
URL_WORKERS: int = int(os.environ.get("URL_WORKERS", 10))

# Parallel workers for Kokoro TTS synthesis — each worker loads its own KPipeline instance
TTS_WORKERS: int = int(os.environ.get("TTS_WORKERS", 2))
