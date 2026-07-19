# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A personal site published to GitHub Pages — resume certifications gallery at `/resume/certifications/`. **The AI/Robotics techradar digest has moved off this repo entirely**, now published at https://keithfry.github.io/techradar/ from its own repo (`~/projects/techradar/`). This repo no longer hosts or publishes the digest.

## No Build System

This project has no package.json, Makefile, or traditional build tooling. It's shell scripts + GitHub Actions.

## Local Automation

The techradar agent runs daily at 8:00 AM ET via a macOS LaunchAgent (`com.keithfry.ai-techradar-agent`), which wakes the machine if asleep and runs `uv run run.py --config config/topics.toml`. The runtime lives entirely outside this repo, at `/Users/keithfry/projects/techradar/` (own git repo, depends on the `news-radar` package, publishes into its own `techradar/` dir via a publish hook that commits/pushes that repo). The LaunchAgent is repointed to `~/projects/techradar/com.keithfry.ai-techradar-agent.plist` as of 2026-07-19. Logs: `~/projects/techradar/logs/ai-techradar-agent.log`.

Nothing in this repo runs or triggers the digest anymore.

## RSS Feed Management

Feed list: `data/ai-rss-feeds.csv` (columns: Company/Source, Verified, Feed URL, Summary, Category). Only rows with `Verified = Y` are fetched. `Category` is `AI`, `Robotics`, or `Both` — controls which digest each feed appears in. This file is the one piece of techradar input still owned by this repo; `~/projects/techradar/config/topics.toml`'s `feeds_csv` points back at it.

## Techradar Agent Skill

Use `Skill(techradar-agent)` to run the daily AI/Robotics digest pipeline. The skill is defined in `skills/techradar-agent/SKILL.md`.

**Neither the pipeline nor its consumer are code in this repo, and neither publishes here anymore.** The pipeline
is the standalone [`news-radar`](https://github.com/keithfry/news-radar)
package (`/Users/keithfry/projects/news-radar`). The consumer — config, feed list,
publish hook, entrypoint, and published output — is its own repo at
`/Users/keithfry/projects/techradar/` (public, depends on `news-radar` as an
editable local package):
- `~/projects/techradar/config/topics.toml` — site identity, models, and the
  AI/Robotics topic definitions (classifier prompts, keywords, output dirs)
- `~/projects/techradar/hooks/publish.py` — publish hook: regenerates that
  repo's own `techradar/` index pages via `generate-index.sh`, then
  git pull/add/commit/push **against that repo** — its `techradar/` dir is the
  GitHub Pages docroot at https://keithfry.github.io/techradar/
- `~/projects/techradar/run.py` — thin entrypoint that loads Gmail secrets
  from `~/keys/kfopenclaw-gmail.env` and calls `newsradar.cli.main()`

```bash
cd /Users/keithfry/projects/techradar
uv run run.py --config config/topics.toml --date YYYY-MM-DD --time HH:MM
```

Default invocation (no `--topic`) runs **both** AI and Robotics digests. Use `--topic ai` or `--topic robotics` to run a single topic. Supports `--dry-run`, `--no-email`, `--hours`, `--no-podcast`, and `--refresh-token`. (`--podcast-only`/`--transcript-only` dev shortcuts from the old `main.py` haven't been ported to the new CLI yet.)

## GitHub Actions Workflows

Two workflows run on push to `main`:

1. **`generate-site-assets.yml`**: Creates `resume/certifications/images/images.json` from files in `resume/certifications/images/`. Auto-commits the manifest.

2. **`deploy-pages.yml`**: Triggered after asset generation completes. Deploys to GitHub Pages, excluding `data/`, `scripts/`, `skills/`, `test/`, `push.sh`, `fetch_errors.txt`, `.claude/`, `.github/`, and `.venv/`.

## Git Push Shortcut

```bash
bash push.sh  # equivalent to: git push origin main
```
