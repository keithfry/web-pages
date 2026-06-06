---
name: techradar-agent
description: Use when the user asks to run, generate, or produce the AI or Robotics techradar digest for any date or time.
---

# Techradar Agent

Runs the AI and/or Robotics Techradar digest pipeline for a given date/time window.

## How to Run

**Working directory:** `scripts/techradar-agent/` (relative to repo root)

```bash
cd /Users/keithfry/projects/web-pages/scripts/techradar-agent
uv run main.py --date YYYY-MM-DD --time HH:MM
```

## Defaults

Unless the user specifies otherwise, run with **today's date at 08:00 ET** and **both topics**:

```bash
uv run main.py --date 2026-04-18 --time 08:00
```

Always substitute the actual current date from the `currentDate` context variable.

## Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `--topic {ai,robotics,both}` | Which digest(s) to generate | both |
| `--date YYYY-MM-DD` | Reference date in ET | today |
| `--time HH:MM` | Cut-off time in ET | current time |
| `--hours N` | Lookback window in hours | 24 |
| `--dry-run` | Generate HTML only, skip git push | off |
| `--no-email` | Skip Gmail, RSS only | off |

## Examples

```bash
# Both digests, today at 8 AM (default)
uv run main.py --date 2026-04-18 --time 08:00

# AI digest only
uv run main.py --date 2026-04-18 --time 08:00 --topic ai

# Robotics digest only
uv run main.py --date 2026-04-18 --time 08:00 --topic robotics

# Dry run (no commit/push)
uv run main.py --date 2026-04-18 --time 08:00 --dry-run

# RSS only, no Gmail
uv run main.py --date 2026-04-18 --time 08:00 --no-email
```

## Output

- AI HTML: `techradar/AI/ai-radar-YYYY-MM-DD.html`
- Robotics HTML: `techradar/Robotics/robotics-radar-YYYY-MM-DD.html`
- JSON/MP3/chapters: same directory as HTML, same date prefix
- Log: `logs/techradar-agent-YYYY-MM-DD.log`
- Committed and pushed automatically (unless `--dry-run`)
