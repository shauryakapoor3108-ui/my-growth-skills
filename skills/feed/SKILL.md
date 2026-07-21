---
name: feed
description: Subscribe to YouTube channels and RSS feeds, automatically pull transcripts of new items, summarise them with an LLM, and file structured notes into an Obsidian vault. Use when the user says "check my feeds", "what's new from my subscriptions", "summarise the latest videos", "add this channel", or wants a second brain that keeps itself fed.
---

# feed

A subscription layer for your second brain. It watches sources you care about, and every time something new lands it pulls the transcript, summarises it, and files a linked note in your Obsidian vault. You read the notes, not the feed.

```
discover (RSS)  ->  transcript (yt-dlp captions)  ->  summarise (Groq)
       ->  Obsidian note (frontmatter + links)  ->  mark seen
```

## Why it exists
Subscriptions are a firehose and a second brain is only as good as what reaches it. This closes that gap: the things you subscribe to arrive as searchable, linkable notes with the claims already extracted, instead of a watch-later list you never open.

## Commands

```bash
S=skills/feed/scripts/feed.py

python3 $S add "https://www.youtube.com/@SomeChannel" --name "Some Channel"
python3 $S add "https://example.com/rss"          # plain RSS works too
python3 $S list                                    # sources + how many items seen
python3 $S poll --limit 20                         # what's new, without processing
python3 $S run  --limit 5                          # process new items end to end
python3 $S run  --limit 5 --dry                    # show what it would process
python3 $S backfill "<channel-url>" --limit 3      # process recent items, ignore state
```

YouTube handles (`@channel`) are resolved to their RSS feed automatically, so no API key
and no quota is needed for discovery.

## Config
`~/.config/ai-skills/feed.json`, created on first `add`:

```json
{
  "vault": "~/vault/sources",
  "sources": [{ "name": "...", "feed": "https://...", "added": "..." }],
  "seen": ["videoId", "..."]
}
```

Point `vault` at any folder inside your Obsidian vault. Notes are written as
`YYYY-MM-DD-title-slug.md` with frontmatter (`title`, `source`, `channel`,
`published`, `captured`, `type`, `tags`, `status: unread`) so Dataview and
graph view pick them up immediately.

## Keys
`GROQ_API_KEY` from the environment or `~/.config/ai-skills/.env`.
Summary model is configurable with `FEED_MODEL` (default `llama-3.3-70b-versatile`).

## Requirements
`yt-dlp` and `ffmpeg` on PATH, Python 3.10+. No other runtime dependencies.

## Notes
- Feed endpoints throttle. `fetch()` retries with backoff (1s, 2s, 4s) rather than
  failing on a transient 404/500.
- Items with no captions are still filed, marked `_No transcript available._`, so
  nothing silently disappears.
- `seen` state means re-running is safe and idempotent; use `backfill` to override.
- Pairs with `video-edit` in this repo when a source is worth cutting rather than reading.
