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

## Daily Digest Skill

The `daily-ai-digest` skill (in `skills/`) orchestrates the full pipeline:
1. Gathers AI-related emails from `kfopenclaw@gmail.com` (past 24h) via Gmail MCP
2. Fetches RSS feeds via the local server
3. Deduplicates via Haiku subagents
4. Generates a styled HTML digest as Opus (orchestrator)
5. Saves to `techradar/AI/ai-radar-YYYY-MM-DD.html`
6. Commits and pushes via `/git-push` endpoint (fallback: bash git commands)

Model strategy: Opus orchestrates, Haiku handles all summarization/text tasks.

Key constraints for digest generation:
- Only include content from the past 24 hours
- arXiv feeds: limit to 10 most recently published papers per feed
- Output filename pattern: `ai-radar-YYYY-MM-DD.html` (not `ai-digest`)
- Git commits require `-c user.name="Keith Fry" -c user.email="keithfry@gmail.com"`
- If `.git/index.lock` exists, delete it before git operations
- Gmail account is `kfopenclaw@gmail.com`; do NOT mark emails as read

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
