# Backlog

## news-radar extraction follow-ups

- **The runtime consumer AND the published digest site both moved to
  `~/projects/techradar/`** (own public repo, https://github.com/keithfry/techradar,
  flipped from private to public so GitHub Pages works on the free tier). It
  depends on `newsradar` (https://github.com/keithfry/news-radar, public), and
  its own `techradar/` subdirectory (seeded from this repo's `techradar/`) is
  now the published GitHub Pages docroot at `keithfry.github.io/techradar` —
  NOT this repo anymore. `hooks/publish.py` there commits/pushes to the
  `techradar` repo itself, not this one; `.github/workflows/deploy-pages.yml`
  there deploys it.
  **This repo's own `techradar/` directory (`keithfry.github.io/web-pages/techradar`)
  is now stale** — it's the old publish target, kept live for now per explicit
  decision, to be removed once the new site is confirmed working. Until then,
  don't expect `techradar/` here to keep updating.
  The LaunchAgent should eventually point at `~/projects/techradar/com.keithfry.ai-techradar-agent.plist`
  instead of `scripts/com.keithfry.ai-techradar-agent.plist` — this requires
  `launchctl unload`-ing the old job and loading the new plist, a live system
  change that hasn't been done yet (old job is still installed/active and still
  points at the OLD `scripts/techradar-agent/config/topics.toml`, which still
  publishes into THIS repo — so until repointed, the daily 8am run keeps
  updating the stale `web-pages/techradar/`, not the new site).
- Remove the now-superseded `scripts/techradar-agent/` structure entirely from this
  repo (old pipeline files — `main.py`, `config.py`, `feed_fetcher.py`, `email_fetcher.py`,
  `article_fetcher.py`, `llm.py`, `enricher.py`, `html_generator.py`, `cover_generator.py`,
  `podcast_generator.py`, `podcast_rss.py`, `publisher.py`, `compare_models.py`,
  `update_modelfile.py`, `extract_examples.py`, `AdDetectorModelfile`, `AD_DETECTION.md`,
  `test_*.py`, `test_data/` — AND the `config/`, `hooks/`, `run.py` added during the
  extraction, now duplicated/superseded by `~/projects/techradar/`) once the new
  location has run for real a few times and the LaunchAgent has been repointed.
  Also remove `scripts/com.keithfry.ai-techradar-agent.plist` once the LaunchAgent
  is repointed, and remove this repo's own `techradar/` directory once the new
  site at `keithfry.github.io/techradar` is confirmed working (old URLs will break
  unless redirected — explicitly deferred per decision made during migration).
- **New site confirmed live and working**: https://keithfry.github.io/techradar/
  — HTML, MP3, and podcast RSS (`itunes:author` correctly "Keith Fry") all
  verified serving via `curl`, deployed by `deploy-pages.yml` on 2026-07-19.
  Old `web-pages/techradar/`-removal step above can proceed once you've
  spot-checked it yourself.
- **GitHub Pages 1GB artifact-size limit risk**: the `techradar` repo's deploy
  artifact is already 1.53GB (all of `techradar/` — 865 files, mostly MP3s/
  images) — GitHub Pages warned "exceeds the allowed size of 1 GB, deployment
  might fail" but this run still succeeded. It will only grow with each daily
  digest. Needs a real fix before it silently starts failing: options include
  (a) pruning/archiving old episodes out of the deployed dir on a rolling
  window, (b) moving audio/image assets to external storage (S3, Git LFS +
  a CDN, etc.) and keeping only HTML/RSS in the Pages artifact, or (c) some
  other archival strategy. Not yet decided or implemented.
- Port `--podcast-only` / `--transcript-only` dev shortcuts from the old `main.py`
  into `news-radar`'s `cli.py` (rebuild podcast/transcript from existing JSON
  without refetching/reclassifying).
- Chromecast casting support (carried over from prior backlog note).
