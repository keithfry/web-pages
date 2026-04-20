---
name: techradar-agent
description: Use when the user asks to run, generate, or produce the AI techradar digest for any date or time.
---

# Techradar Agent

Runs the AI Techradar digest pipeline for a given date/time window.

## How to Run

**Working directory:** `scripts/ai-techradar-agent/` (relative to repo root)

```bash
cd /Users/keithfry/projects/web-pages/scripts/ai-techradar-agent
uv run main.py --date YYYY-MM-DD --time HH:MM
```

## Defaults

Unless the user specifies otherwise, run with **today's date at 08:00 ET**:

```bash
uv run main.py --date 2026-04-18 --time 08:00
```

Always substitute the actual current date from the `currentDate` context variable.

## Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `--date YYYY-MM-DD` | Reference date in ET | today |
| `--time HH:MM` | Cut-off time in ET | current time |
| `--hours N` | Lookback window in hours | 24 |
| `--dry-run` | Generate HTML only, skip git push | off |
| `--no-email` | Skip Gmail, RSS only | off |

## Examples

```bash
# Today at 8 AM (default)
uv run main.py --date 2026-04-18 --time 08:00

# Specific date and time
uv run main.py --date 2026-04-16 --time 08:00

# Dry run (no commit/push)
uv run main.py --date 2026-04-18 --time 08:00 --dry-run

# RSS only, no Gmail
uv run main.py --date 2026-04-18 --time 08:00 --no-email
```

## Output

- HTML saved to: `techradar/AI/ai-radar-YYYY-MM-DD.html`
- Log saved to: `logs/ai-techradar-agent-YYYY-MM-DD.log`
- Committed and pushed automatically (unless `--dry-run`)
