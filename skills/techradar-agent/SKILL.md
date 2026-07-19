---
name: techradar-agent
description: Use when the user asks to run, generate, or produce the AI or Robotics techradar digest for any date or time.
---

# Techradar Agent

Runs the AI and/or Robotics Techradar digest pipeline for a given date/time window.

The pipeline itself lives in the standalone [`news-radar`](https://github.com/keithfry/news-radar)
package (`/Users/keithfry/projects/news-radar`). The runtime consumer — config
and the entrypoint that runs it — lives in its own repo,
`/Users/keithfry/projects/techradar/` (NOT in this repo), which depends on
`news-radar` as an editable local package and publishes generated output back
into this repo's `techradar/` directory via a publish hook.

## How to Run

**Working directory:** `/Users/keithfry/projects/techradar/` (a sibling of this repo, NOT a subdirectory of it)

```bash
cd /Users/keithfry/projects/techradar
uv run run.py --config config/topics.toml --date YYYY-MM-DD --time HH:MM
```

## Defaults

Unless the user specifies otherwise, run with **today's date at 08:00 ET** and **both topics**:

```bash
uv run run.py --config config/topics.toml --date 2026-04-18 --time 08:00
```

Always substitute the actual current date from the `currentDate` context variable.

## Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `--config PATH` | Path to the TOML config file | required |
| `--topic ai,robotics` | Which topic(s) to generate, comma-separated | all configured topics |
| `--date YYYY-MM-DD` | Reference date in ET | today |
| `--time HH:MM` | Cut-off time in ET | current time |
| `--hours N` | Lookback window in hours | from config |
| `--dry-run` | Generate output only, skip the publish hook (git commit/push) | off |
| `--no-email` | Skip Gmail, RSS only | off |

## Examples

```bash
# Both digests, today at 8 AM (default)
uv run run.py --config config/topics.toml --date 2026-04-18 --time 08:00

# AI digest only
uv run run.py --config config/topics.toml --date 2026-04-18 --time 08:00 --topic ai

# Robotics digest only
uv run run.py --config config/topics.toml --date 2026-04-18 --time 08:00 --topic robotics

# Dry run (no commit/push)
uv run run.py --config config/topics.toml --date 2026-04-18 --time 08:00 --dry-run

# RSS only, no Gmail
uv run run.py --config config/topics.toml --date 2026-04-18 --time 08:00 --no-email
```

## Output

- AI HTML: `techradar/AI/ai-radar-YYYY-MM-DD.html`
- Robotics HTML: `techradar/Robotics/robotics-radar-YYYY-MM-DD.html`
- JSON/MP3/chapters: same directory as HTML, same date prefix
- Log: `logs/techradar-agent-YYYY-MM-DD.log`
- Committed and pushed automatically (unless `--dry-run`)
