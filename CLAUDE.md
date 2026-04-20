# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A personal AI/Robotics news aggregation platform published to GitHub Pages. The primary feature is a daily digest (`/techradar/AI/`) that aggregates content from 40+ RSS feeds and Gmail newsletters. There is also a resume certifications gallery at `/resume/certifications/`.

## No Build System

This project has no package.json, Makefile, or traditional build tooling. It's Python scripts + shell scripts + GitHub Actions.

## Local Development Server

A Python HTTP server runs at `http://127.0.0.1:5999` as a macOS LaunchAgent that auto-starts on login.

```bash
# Check if server is running
curl http://127.0.0.1:5999/health

# Start manually if needed
python3 scripts/server.py

# View logs
tail -f logs/server.log
```

Server endpoints:
- `GET /health` — returns `{"status": "ok"}`
- `GET /fetch-feeds[?hours=N]` — fetches all Verified=Y RSS feeds from `data/ai-rss-feeds.csv`, default 24h lookback
- `GET /git-push?file=<path>&message=<msg>` — runs git pull --rebase, add, commit, push

## RSS Feed Management

Feed list: `data/ai-rss-feeds.csv` (columns: Company/Source, Verified, Feed URL, Summary). Only rows with `Verified = Y` are fetched by the server.

## Techradar Agent Skill

Use `Skill(techradar-agent)` to run the daily AI/Robotics digest pipeline. The skill is defined in `skills/techradar-agent/SKILL.md`.

The agent runs as a standalone Python script (no local server required):

```bash
cd scripts/ai-techradar-agent
uv run main.py --date YYYY-MM-DD --time HH:MM
```

Default invocation uses today's date at 08:00 ET. Supports `--dry-run`, `--no-email`, and `--hours` overrides.

Pipeline steps:
1. Fetches RSS feeds from `data/ai-rss-feeds.csv` (Verified=Y rows)
2. Gathers AI-related emails from `kfopenclaw@gmail.com` via Gmail API
3. Classifies, summarizes, and deduplicates all content via local Ollama models
4. Generates a styled HTML digest
5. Saves to `techradar/AI/ai-radar-YYYY-MM-DD.html` and commits/pushes

Output log: `logs/ai-techradar-agent-YYYY-MM-DD.log`

## GitHub Actions Workflows

Two workflows run on push to `main`:

1. **`generate-site-assets.yml`**: Generates `index.html` for all directories (via `.github/scripts/generate-index.sh`) and creates `resume/certifications/images/images.json`. Auto-commits generated assets.

2. **`deploy-pages.yml`**: Triggered after asset generation completes. Deploys to GitHub Pages, excluding `data/`, `scripts/`, `skills/`, and `push.sh`.

## Directory Index Generation

`.github/scripts/generate-index.sh` recursively creates `index.html` files for all subdirectories. It parses `YYYY-MM-DD` dates from filenames and groups entries by month, newest first. Run it locally to test:

```bash
bash .github/scripts/generate-index.sh
```

## Git Push Shortcut

```bash
bash push.sh  # equivalent to: git push origin main
```
