# Changelog

## 0.1.0 - 2026-07-21

First release. Two skills.

### feed
- Subscribe to YouTube channels (handles resolved to RSS, no API key) and plain RSS.
- Pull captions with yt-dlp, summarise into TL;DR / key claims / worth stealing / open questions.
- File linked Obsidian notes with frontmatter and `status: unread`.
- Idempotent `seen` state; `backfill` to override it.
- Feed fetches retry with backoff, because feed endpoints throttle with transient 404/500s.
- Items without captions are still filed and marked, never silently dropped.

### video-edit
- Pull from Google Drive or local disk, transcribe with Groq `whisper-large-v3`.
- Report transcripts with pause markers so cuts are chosen deliberately.
- Cut leading false starts and internal dead air; report before/after duration.
- Optional Playwright screen-capture cutaways, overlay assembly, burned captions.
- Falls back to local `faster-whisper` when no API key is present.
- Fixed: Groq rejected requests sending urllib's default User-Agent with a 403.

### packaging
- Claude Code marketplace + per-skill plugin manifests, Codex manifests, slash commands.
- Shared preflight (`scripts/setup.py`): silent `--check`, `--json`, human installer.
- `.skill` bundle builder and tag-triggered release workflow.
