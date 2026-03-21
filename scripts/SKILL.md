---
name: daily-ai-digest
description: Daily 8AM ET summary of AI/Robotics emails and blog posts, output as a timestamped HTML page. Uses a local Python server at http://127.0.0.1:5999 to fetch RSS feeds and handle git operations.
---

You are running a daily AI/Robotics news digest. You are the orchestrator (running as Opus). For all content summarization, title creation, and text generation tasks, delegate to Haiku subagents using the Agent tool with model: "haiku" to keep costs down and speed up processing.

## STEP 1: Gather AI Emails (past 24 hours)

1. Use the Gmail MCP tools to search for emails in the kfopenclaw@gmail.com account from the past 24 hours. Use a query like: `newer_than:1d` to find recent messages.
2. Read each email using gmail_read_message.
3. Filter: Only keep emails whose subject or body content is related to **AI, machine learning, robotics, LLMs, or related technology topics**. Discard everything else (promotions, social, unrelated newsletters).
4. For each qualifying email, use an Agent tool call with model "haiku" to:
   - Extract a **title** (use the email subject or derive one from the content).
   - Write a **summary of under 5 sentences** capturing the key points.
   - Identify **links to AI-related web pages** (articles, blog posts, papers) from the email body. Exclude unsubscribe links, tracking pixels, and social media profile links.
   - Return structured output: title, summary, source links.
5. For promising article links found in emails, use the Chrome browser tools to navigate to the page and use get_page_text to read the content, then pass it to a Haiku subagent to summarize.

## STEP 2: Gather Blog Posts from RSS Feeds (past 24 hours)

A local Python server is running at `http://127.0.0.1:5999` that handles all RSS fetching. It reads from `data/ai-rss-feeds.csv` (Verified=Y feeds only) and returns pre-filtered results.

### Fetching feeds via the local server:

1. First verify the server is up by calling the health endpoint:
   ```javascript
   // In a browser tab via javascript_tool:
   fetch('http://127.0.0.1:5999/health')
     .then(r => r.json())
     .then(d => { window._health = d; });
   ```
   Check `window._health` — it should be `{"status": "ok"}`. If the server is down, note this as a critical error and fall back to the Chrome tab-based approach (see Fallback section below).

2. Call `/fetch-feeds` to get all RSS items from the past 24 hours:
   ```javascript
   // This may take 20-30 seconds — all feeds are fetched sequentially
   fetch('http://127.0.0.1:5999/fetch-feeds')
     .then(r => r.json())
     .then(d => { window._feeds = d; });
   ```
   Poll `window._feeds` until it is set (not undefined). The response is a JSON array of feed objects.

3. The response schema is:
   ```json
   [
     {
       "source": "MIT Technology Review - AI & Emerging Tech",
       "feed_url": "https://...",
       "items": [
         {
           "title": "Article title",
           "link": "https://...",
           "published": "2026-03-21T10:00:00+00:00",
           "summary": "Plain-text excerpt from the feed"
         }
       ]
     },
     {
       "source": "Broken Feed",
       "feed_url": "https://...",
       "error": "Connection refused"
     }
   ]
   ```
   - Feeds with an `error` field → add to Problem Feeds (Step 5).
   - Feeds with `items: []` → no recent content, skip silently.
   - Feeds with items → process below.

4. For each feed object that has items, use Haiku subagents (in parallel batches) to:
   - Write a **summary of under 5 sentences** for each item using the provided title and summary fields.
   - If the feed summary is very short (stub only), navigate to the article link in Chrome and use get_page_text to get more content, then pass to Haiku.
   - Return structured output: title, summary, source link.

### Special handling for arXiv feeds (cs.AI, cs.LG, stat.ML, cs.RO):
- The server returns all available arXiv items within the lookback window, which can be large.
- **Limit to the 10 most recently published papers per arXiv feed** — take the first 10 items from each arXiv source in the response.
- For each of those papers, extract the title, authors (if available), and a 1-2 sentence summary from the provided abstract/summary field.
- Include the arXiv link for each paper.

### Fallback (if server is unreachable):
Use the Chrome browser tab-based approach: create 6 tabs, navigate to feed URLs in parallel batches of 6, use javascript_tool to fetch and parse RSS XML with regex-based parsing (not DOMParser, which is blocked by TrustedHTML). Refer to previous run transcripts for the exact parsing pattern.

## STEP 3: Deduplicate

1. Once all items are collected, use an Agent tool call with model "haiku" to:
   - Compare all items from emails and blogs.
   - Identify duplicates covering the same topic/story (same article, same announcement, or very similar content).
   - For each duplicate pair, keep **whichever has the longer, more detailed summary**.
   - Return the deduplicated list.

## STEP 4: Create the HTML Digest

1. As the orchestrator (Opus), generate a clean, well-styled HTML page with:
   - A header: "AI & Robotics Daily Digest"
   - A date/timestamp showing the current date and time (e.g., "Wednesday, March 18, 2026 — 8:00 AM ET")
   - A section for each content item containing:
     - **Title** (as a clickable link to the source if available)
     - **Source label** (e.g., "Via: Newsletter" or "Via: TechCrunch RSS")
     - **Summary** (under 5 sentences)
   - Group items by source type if helpful (Emails section, Blogs section), or present as a unified list sorted by relevance.
   - arXiv papers should appear in their own section titled "Latest Research Papers" at the end, before Problem Feeds.
   - Use modern, readable styling (clean fonts, good spacing, subtle colors). Make it look like a professional daily brief.

## STEP 5: Problem Feeds Section

At the **bottom** of the HTML page, include a clearly separated section titled "Problem Feeds" — but ONLY if there are actual errors.

**Only list feeds that had actual errors** (feeds where the server returned an `error` field). Do NOT list feeds that simply had no new items — that is expected and should be silently skipped.

For each problem feed, list:
- **Blog/source name** (from the response)
- **RSS feed URL** (as a clickable link)
- **Reason** for failure (the `error` field from the response)

Style this section distinctly (e.g., lighter text, a warning icon or colored border). If there are zero problem feeds, omit this section entirely.

## STEP 6: Save to GitHub Repo, Commit, and Push

1. Request access to the repo directory using request_cowork_directory with path: /Users/keithfry/projects/web-pages

2. Save the HTML digest file following the existing naming convention:
   `techradar/AI/ai-radar-YYYY-MM-DD.html`

   **IMPORTANT**: The filename pattern is `ai-radar-YYYY-MM-DD.html` (NOT `ai-digest`). This matches the existing files in the directory.

3. Commit and push using the local server's `/git-push` endpoint:
   ```javascript
   const file = 'techradar/AI/ai-radar-YYYY-MM-DD.html';
   const message = 'Add AI radar for YYYY-MM-DD';
   fetch(`http://127.0.0.1:5999/git-push?file=${encodeURIComponent(file)}&message=${encodeURIComponent(message)}`)
     .then(r => r.json())
     .then(d => { window._gitResult = d; });
   ```
   Poll `window._gitResult` and check that `status === "ok"`. If there is an error, the file is already saved locally and Keith can push manually with `git push` from Terminal.

4. If the server is unreachable, fall back to running git commands directly via Bash:
   ```
   cd /path/to/mounted/web-pages
   git pull --rebase
   git add techradar/AI/ai-radar-YYYY-MM-DD.html
   git -c user.name="Keith Fry" -c user.email="keithfry@gmail.com" commit -m "Add AI radar for YYYY-MM-DD"
   git push
   ```

## Local Server Reference

The server runs at `http://127.0.0.1:5999` as a macOS LaunchAgent (`com.keithfry.ai-radar-server`). It auto-starts on login and restarts on crash. Source: `scripts/server.py`. Logs: `logs/server.log`.

| Endpoint | Description |
|---|---|
| `GET /health` | Returns `{"status":"ok"}` if the server is running |
| `GET /fetch-feeds[?hours=N]` | Fetches all Verified=Y feeds from `data/ai-rss-feeds.csv`. Default lookback: 24h |
| `GET /git-push?file=<path>&message=<msg>` | git pull --rebase, add, commit, push. Returns steps array |

Feed list is managed in `data/ai-rss-feeds.csv` (columns: Company / Source, Verified, Feed URL, Summary). Only rows with `Verified = Y` are processed.

## Model Usage Strategy
- **Opus (you, the orchestrator)**: Overall flow control, fetching emails/feeds via server, assembling the final HTML, making editorial decisions about what qualifies as AI content.
- **Haiku (via Agent tool with model "haiku")**: All summarization, title extraction, deduplication comparison, and text generation. Launch multiple Haiku agents in parallel when possible (e.g., summarizing multiple feeds at once) for speed.

## Important Notes
- Be thorough: process ALL qualifying emails and ALL verified RSS feeds.
- Be selective: only include genuinely AI/Robotics/ML related content.
- **CRITICAL: Only include content from the last 24 hours. Do not summarize or include older articles.**
- **arXiv feeds: limit to 10 most recent papers per feed** (filter after receiving server response).
- Summaries must be concise (under 5 sentences each) but informative.
- Always preserve links to original content.
- The Gmail account to search is kfopenclaw@gmail.com.
- Do NOT attempt to mark emails as read — the Gmail connector does not support this.
- Do NOT list feeds with no recent items as problem feeds — only list feeds with actual errors.
- Always use `-c user.name="Keith Fry" -c user.email="keithfry@gmail.com"` flags with git commit commands (for the Bash fallback path).
- If .git/index.lock exists, delete it before any git operations.
