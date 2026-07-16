# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A personal AI/Robotics news aggregation platform published to GitHub Pages. The primary feature is a daily digest (`/techradar/AI/`) that aggregates content from 40+ RSS feeds and Gmail newsletters. There is also a resume certifications gallery at `/resume/certifications/`.

## No Build System

This project has no package.json, Makefile, or traditional build tooling. It's Python scripts + shell scripts + GitHub Actions.

## Local Automation

The techradar agent runs daily at 8:00 AM ET via a macOS LaunchAgent (`scripts/com.keithfry.ai-techradar-agent.plist`), which wakes the machine if asleep and runs `uv run main.py` in `scripts/techradar-agent/`. See `scripts/README.md` for install/uninstall/update commands. Logs: `logs/ai-techradar-agent.log`.

There is no local HTTP server or build step — invoke the agent directly (see Techradar Agent Skill below).

## RSS Feed Management

Feed list: `data/ai-rss-feeds.csv` (columns: Company/Source, Verified, Feed URL, Summary, Category). Only rows with `Verified = Y` are fetched. `Category` is `AI`, `Robotics`, or `Both` — controls which digest each feed appears in.

## Techradar Agent Skill

Use `Skill(techradar-agent)` to run the daily AI/Robotics digest pipeline. The skill is defined in `skills/techradar-agent/SKILL.md`.

The agent runs as a standalone Python script (no local server required):

```bash
cd scripts/techradar-agent
uv run main.py --date YYYY-MM-DD --time HH:MM
```

Default invocation uses today's date at 08:00 ET and runs **both** AI and Robotics digests. Use `--topic ai` or `--topic robotics` to run a single topic. Supports `--dry-run`, `--no-email`, `--hours`, `--no-podcast`, `--podcast-only`, `--transcript-only`, and `--refresh-token` overrides (see `scripts/techradar-agent/main.py` for the full flag list).

Pipeline steps (run once per topic):
1. Fetches RSS feeds filtered by `Category` column in `data/ai-rss-feeds.csv`
2. Gathers emails from `kfopenclaw@gmail.com` via Gmail API (filtered by topic classifier)
3. Classifies, summarizes, and deduplicates all content via local Ollama models
4. Generates a styled HTML digest, podcast audio/RSS, and cover image
5. Saves to `techradar/AI/ai-radar-YYYY-MM-DD.html` or `techradar/Robotics/robotics-radar-YYYY-MM-DD.html` (plus JSON/MP3/chapters/podcast.rss in the same directory)
6. Runs `.github/scripts/generate-index.sh` locally, then commits/pushes everything

Output log: `logs/techradar-agent-YYYY-MM-DD.log`

## GitHub Actions Workflows

Two workflows run on push to `main`:

1. **`generate-site-assets.yml`**: Creates `resume/certifications/images/images.json` from files in `resume/certifications/images/`. Auto-commits the manifest. (Directory `index.html` generation is NOT done here — the techradar agent runs `generate-index.sh` itself as the last pipeline step before it commits/pushes, per above.)

2. **`deploy-pages.yml`**: Triggered after asset generation completes. Deploys to GitHub Pages, excluding `data/`, `scripts/`, `skills/`, `test/`, `push.sh`, `fetch_errors.txt`, `.claude/`, `.github/`, and `.venv/`.

## Directory Index Generation

`.github/scripts/generate-index.sh` recursively creates `index.html` files for all subdirectories. It parses `YYYY-MM-DD` dates from filenames and groups entries by month, newest first. Called automatically by `main.py` at the end of each techradar run. Run it locally to test:

```bash
bash .github/scripts/generate-index.sh
```

## Git Push Shortcut

```bash
bash push.sh  # equivalent to: git push origin main
```
