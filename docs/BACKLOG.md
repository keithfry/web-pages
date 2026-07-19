# Backlog

## news-radar extraction follow-ups

- **DONE (2026-07-19)**: LaunchAgent repointed from `scripts/com.keithfry.ai-techradar-agent.plist`
  to `~/projects/techradar/com.keithfry.ai-techradar-agent.plist` (old job unloaded, new one
  installed to `~/Library/LaunchAgents/` and loaded). Daily 8am run now publishes only to
  `~/projects/techradar` (docroot for https://keithfry.github.io/techradar/), not this repo.
- **DONE (2026-07-19)**: Removed the superseded `scripts/techradar-agent/` pipeline copy and
  `scripts/com.keithfry.ai-techradar-agent.plist` from this repo — fully replaced by
  `~/projects/techradar/` + `news-radar`.
- **DONE (2026-07-19)**: Removed this repo's stale `techradar/` output directory — spot-checked
  against the live new site (https://keithfry.github.io/techradar/, confirmed serving HTML/MP3/
  podcast RSS via `curl`) before deletion. Old `web-pages.github.io/techradar/...` URLs are now
  dead (no redirect set up — accepted per migration decision).
- This repo's remaining role in the techradar pipeline: hosts `data/ai-rss-feeds.csv`, read by
  `~/projects/techradar/config/topics.toml`'s `feeds_csv`. Nothing else.
- **GitHub Pages 1GB artifact-size limit risk**: the `techradar` repo's deploy
  artifact is already 1.53GB (all of `techradar/` — 865 files, mostly MP3s/
  images) — GitHub Pages warned "exceeds the allowed size of 1 GB, deployment
  might fail" but this run still succeeded. It will only grow with each daily
  digest. Needs a real fix before it silently starts failing: options include
  (a) pruning/archiving old episodes out of the deployed dir on a rolling
  window, (b) moving audio/image assets to external storage (S3, Git LFS +
  a CDN, etc.) and keeping only HTML/RSS in the Pages artifact, or (c) some
  other archival strategy. Not yet decided or implemented. (Lives in the
  `techradar` repo now, not this one — tracked here since it originated from
  this migration.)
- Port `--podcast-only` / `--transcript-only` dev shortcuts from the old `main.py`
  into `news-radar`'s `cli.py` (rebuild podcast/transcript from existing JSON
  without refetching/reclassifying).
- Chromecast casting support (carried over from prior backlog note).
