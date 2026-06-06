# Plan: Split AI Techradar into AI + Robotics

## Context

The daily digest at `techradar/AI/` is growing too long — both HTML page and podcast. The RSS feed list already has ~30 robotics-specific feeds (rows 37-66 of `data/ai-rss-feeds.csv`), so the content split is natural. This plan separates the pipeline into two independently-published digests: `techradar/AI/` and `techradar/Robotics/`, each with its own HTML, JSON, and podcast. Feeds that cover both topics appear in both digests. The script directory is also renamed from `scripts/ai-techradar-agent` to `scripts/techradar-agent`.

**Deferred (user-flagged):** Retroactively splitting existing `techradar/AI/` content using existing JSON files — discussed after this work is stable.

---

## Step 1: Add `Category` column to `data/ai-rss-feeds.csv`

Add a `Category` column with values `AI`, `Robotics`, or `Both`.

Pre-populate based on feed names (user should review and adjust before running):
- Feeds clearly robotics-only → `Robotics` (The Robot Report, Robohub, IEEE Spectrum Robotics, Humanoids Daily, MIT News Robotics, Planet ROS, ROS-Industrial, PickNik, AWS Robotics, Robotiq, RoboDK, sUAS News, DRONELIFE, UAS VISION, Rodney Brooks, arXiv cs.RO)
- Feeds clearly AI-only → `AI` (OpenAI, Anthropic, Google AI, DeepMind, LangChain, Hugging Face, Simon Willison, Andrej Karpathy, arXiv cs.AI/cs.LG/stat.ML, VentureBeat AI, etc.)
- Cross-cutting → `Both` (NVIDIA, IEEE Spectrum general, MIT News general, Wired, The Guardian, MIT Technology Review)

The feed fetcher filters on `Verified=Y` — no change needed there. Add topic filtering by `Category`.

---

## Step 2: Add `classify_robotics()` to `llm.py`

Model: same `SUMMARIZE_MODEL` (llama3.2 — small, fast, already loaded during processing).

Pattern: identical to existing `classify_ai()` (file: `scripts/ai-techradar-agent/llm.py`), but prompt asks whether content is robotics/automation/drone/physical-AI-systems related.

```python
def classify_robotics(title: str, summary: str, model: str = SUMMARIZE_MODEL) -> bool:
    # Returns True if content is robotics/automation/physical AI-related
    # Same _chat() / json_mode=True pattern as classify_ai()
```

---

## Step 3: Parameterize `config.py` by topic

Add:
```python
AI_OUTPUT_DIR:       REPO_ROOT / "techradar" / "AI"         # existing
ROBOTICS_OUTPUT_DIR: REPO_ROOT / "techradar" / "Robotics"   # new
```

Keep `OUTPUT_DIR` as `AI_OUTPUT_DIR` for backward compat, or remove after migration.

Add env-overridable `ROBOTICS_CLASSIFY_MODEL` (defaults to `SUMMARIZE_MODEL`).

---

## Step 4: Parameterize `feed_fetcher.py`

`fetch_all_feeds()` currently reads all `Verified=Y` rows. Add a `topic: str` parameter (`"AI"`, `"Robotics"`, `"Both"`) that filters rows where `Category in {topic, "Both"}`.

File: `scripts/ai-techradar-agent/feed_fetcher.py`

---

## Step 5: Parameterize `publisher.py`

`save_html()` and `commit_and_push()` have hardcoded paths and commit messages. Add `output_dir: Path` and `topic: str` params:

- `save_html(html, date, output_dir, prefix)` — `prefix` = `"ai-radar"` or `"robotics-radar"`
- `commit_and_push(paths, date, topic, log)` — commit message: `"Add {topic} radar for YYYY-MM-DD"`

File: `scripts/ai-techradar-agent/publisher.py`

---

## Step 6: Refactor `main.py` — add `--topic` flag and dual-run

Add `--topic {ai,robotics,both}` (default: `both`).

When `both`: run AI pipeline then Robotics pipeline sequentially (single invocation).

Per-topic pipeline:
1. Feed fetch filtered by topic category
2. Email fetch — **AI only** (no robotics email newsletters currently configured)
3. Email fetch — **both topics**, but `classify_robotics()` applied aggressively to filter; expect most newsletters dropped for Robotics
4. `_process_items()` uses topic-specific classifier (`classify_ai` or `classify_robotics`)
5. `classify_ad()` unchanged — runs for both
6. Dedup, enrich, HTML, podcast — all parameterized with topic context
7. Write to `techradar/AI/` or `techradar/Robotics/`

The `_stop_models(log)` call before dedup stays — runs once per topic (before each topic's dedup step).

File: `scripts/ai-techradar-agent/main.py`

---

## Step 7: Create `techradar/Robotics/` directory

Create `techradar/Robotics/` with an empty `.gitkeep` so the directory is tracked. The GitHub Actions `generate-index.sh` script will auto-generate `index.html` there on next push.

---

## Step 8: Rename script directory

`scripts/ai-techradar-agent/` → `scripts/techradar-agent/`

Use `git mv` to preserve history.

Update all references:
- `CLAUDE.md` (3 references to the script path and log pattern)
- `skills/techradar-agent/SKILL.md` (cd path and log path)
- Any GitHub Actions that reference the script path (check `.github/workflows/`)
- Log filename prefix: `ai-techradar-agent-YYYY-MM-DD.log` → `techradar-agent-YYYY-MM-DD.log`

---

## Step 9: Update skill definition

`skills/techradar-agent/SKILL.md` — update:
- `cd` path to `scripts/techradar-agent`
- Note `--topic {ai,robotics,both}` flag
- Output paths for both topics

---

## Files Modified

| File | Change |
|------|--------|
| `data/ai-rss-feeds.csv` | Add `Category` column |
| `scripts/techradar-agent/llm.py` | Add `classify_robotics()` |
| `scripts/techradar-agent/config.py` | Add `ROBOTICS_OUTPUT_DIR`, `ROBOTICS_CLASSIFY_MODEL` |
| `scripts/techradar-agent/feed_fetcher.py` | Add `topic` param to `fetch_all_feeds()` |
| `scripts/techradar-agent/publisher.py` | Parameterize `save_html()`, `commit_and_push()` |
| `scripts/techradar-agent/main.py` | Add `--topic` flag, dual-run loop |
| `CLAUDE.md` | Update script path references |
| `skills/techradar-agent/SKILL.md` | Update paths and flags |
| `.github/workflows/*.yml` | Update script path if referenced |

New:
| Path | Purpose |
|------|---------|
| `techradar/Robotics/.gitkeep` | Create directory |
| `docs/plans/split-ai-robotics.md` | Copy of this plan |

Rename (via `git mv`):
- `scripts/ai-techradar-agent/` → `scripts/techradar-agent/`

---

## Verification

1. **Dry run AI only:** `cd scripts/techradar-agent && uv run main.py --topic ai --dry-run --no-email`
   - Expect: only AI-categorized feeds fetched, `classify_ai()` used, HTML written to `techradar/AI/`

2. **Dry run Robotics only:** `uv run main.py --topic robotics --dry-run --no-email`
   - Expect: only Robotics/Both feeds fetched, `classify_robotics()` used, HTML written to `techradar/Robotics/`

3. **Both default:** `uv run main.py --dry-run --no-email`
   - Expect: two full pipeline runs, two HTML files produced

4. **Feed overlap check:** A `Both`-category feed (e.g., NVIDIA) should appear in both outputs

5. **Log check:** `logs/techradar-agent-YYYY-MM-DD.log` contains step markers for both topics
