# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A personal AI/Robotics news aggregation platform published to GitHub Pages. The primary feature is a daily digest (`/techradar/AI/`) that aggregates content from 40+ RSS feeds and Gmail newsletters. There is also a resume certifications gallery at `/resume/certifications/`.

## No Build System

This project has no package.json, Makefile, or traditional build tooling. It's Python scripts + shell scripts + GitHub Actions.

## Local Automation

The techradar agent runs daily at 8:00 AM ET via a macOS LaunchAgent, which wakes the machine if asleep and runs `uv run run.py --config config/topics.toml`. **The canonical runtime now lives outside this repo**, at `/Users/keithfry/projects/techradar/` (own git repo, depends on the `news-radar` package, publishes into this repo's `techradar/` dir via a publish hook) — see its `com.keithfry.ai-techradar-agent.plist`. `scripts/com.keithfry.ai-techradar-agent.plist` and `scripts/techradar-agent/` in this repo are the pre-migration copies, still installed/active until the LaunchAgent is repointed (tracked in `docs/BACKLOG.md`). See `scripts/README.md` for install/uninstall/update commands for the (soon to be superseded) old LaunchAgent. Logs: `logs/ai-techradar-agent.log` (old location) or `~/projects/techradar/logs/ai-techradar-agent.log` (new location, once repointed).

There is no local HTTP server or build step — invoke the agent directly (see Techradar Agent Skill below).

## RSS Feed Management

Feed list: `data/ai-rss-feeds.csv` (columns: Company/Source, Verified, Feed URL, Summary, Category). Only rows with `Verified = Y` are fetched. `Category` is `AI`, `Robotics`, or `Both` — controls which digest each feed appears in.

## Techradar Agent Skill

Use `Skill(techradar-agent)` to run the daily AI/Robotics digest pipeline. The skill is defined in `skills/techradar-agent/SKILL.md`.

**Neither the pipeline nor its consumer are code in this repo.** The pipeline
is the standalone [`news-radar`](https://github.com/keithfry/news-radar)
package (`/Users/keithfry/projects/news-radar`). The consumer — config, publish
hook, entrypoint — is its own repo at `/Users/keithfry/projects/techradar/`
(sibling of this repo, depends on `news-radar` as an editable local package):
- `~/projects/techradar/config/topics.toml` — site identity, models, and the
  AI/Robotics topic definitions (classifier prompts, keywords, output dirs);
  `output_root`/`feeds_csv` point back into this repo's `techradar/`/`data/`
- `~/projects/techradar/hooks/publish.py` — publish hook: regenerates this
  repo's `techradar/` index pages via `generate-index.sh`, then git add/commit/push
  **against this repo** (`WEB_PAGES_REPO` in that file), not the techradar repo
- `~/projects/techradar/run.py` — thin entrypoint that loads Gmail secrets
  from `~/keys/kfopenclaw-gmail.env` and calls `newsradar.cli.main()`

This repo only supplies `data/ai-rss-feeds.csv` (input) and `techradar/` (output,
committed here since this is the GitHub Pages site).

```bash
cd /Users/keithfry/projects/techradar
uv run run.py --config config/topics.toml --date YYYY-MM-DD --time HH:MM
```

Default invocation (no `--topic`) runs **both** AI and Robotics digests. Use `--topic ai` or `--topic robotics` to run a single topic. Supports `--dry-run`, `--no-email`, `--hours`, `--no-podcast`, and `--refresh-token`. (`--podcast-only`/`--transcript-only` dev shortcuts from the old `main.py` haven't been ported to the new CLI yet.)

Pipeline steps (run once per topic, inside the `news-radar` package):
1. Fetches RSS feeds filtered by `Category` column in `data/ai-rss-feeds.csv`
2. Gathers emails from `kfopenclaw@gmail.com` via Gmail API (filtered by topic classifier)
3. Classifies, summarizes, and deduplicates all content via local Ollama models
4. Generates a styled HTML digest, podcast audio/RSS, and cover image
5. Saves to `techradar/AI/ai-radar-YYYY-MM-DD.html` or `techradar/Robotics/robotics-radar-YYYY-MM-DD.html` (plus JSON/MP3/chapters/podcast.rss in the same directory)
6. Hands the written paths to `~/projects/techradar/hooks/publish.py`, which runs `.github/scripts/generate-index.sh` and commits/pushes everything (skipped on `--dry-run`)

Output log: `logs/techradar-agent-YYYY-MM-DD.log`

## GitHub Actions Workflows

Two workflows run on push to `main`:

1. **`generate-site-assets.yml`**: Creates `resume/certifications/images/images.json` from files in `resume/certifications/images/`. Auto-commits the manifest. (Directory `index.html` generation is NOT done here — the techradar agent's publish hook runs `generate-index.sh` itself as the last pipeline step before it commits/pushes, per above.)

2. **`deploy-pages.yml`**: Triggered after asset generation completes. Deploys to GitHub Pages, excluding `data/`, `scripts/`, `skills/`, `test/`, `push.sh`, `fetch_errors.txt`, `.claude/`, `.github/`, and `.venv/`.

## Directory Index Generation

`.github/scripts/generate-index.sh` recursively creates `index.html` files for all subdirectories. It parses `YYYY-MM-DD` dates from filenames and groups entries by month, newest first. Called automatically by `~/projects/techradar/hooks/publish.py` at the end of each techradar run. Run it locally to test:

```bash
bash .github/scripts/generate-index.sh
```

## Git Push Shortcut

```bash
bash push.sh  # equivalent to: git push origin main
```
