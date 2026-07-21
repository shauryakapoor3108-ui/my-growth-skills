# ai-skills

A small set of AI tools I actually use, packaged as Claude Code skills. Plain Python, no framework, no runtime dependencies beyond `ffmpeg` and `yt-dlp`.

Each skill does one job end to end and is runnable on its own from the command line, with or without Claude.

## The set

### [`feed`](skills/feed) — keep the second brain fed
Subscribe to YouTube channels and RSS feeds. When something new lands it pulls the transcript, summarises it into claims and takeaways, and files a linked note into an Obsidian vault. You read notes, not a watch-later list.

```
discover (RSS) -> transcript (yt-dlp) -> summarise (Groq) -> Obsidian note -> mark seen
```

### [`video-edit`](skills/video-edit) — cut a talking-head video without a timeline
Pulls a clip (Google Drive or local), transcribes it with Groq `whisper-large-v3`, finds false starts and dead air, cuts them, optionally overlays screen-capture cutaways and burns captions, then renders and pushes the result back.

```
pull -> transcribe -> find cuts -> tighten -> [capture cutaways -> assemble] -> render -> push
```

Built in a day, and its first real job was cutting a 77-second take down to a usable 60.

## Install

Clone anywhere and run the scripts directly, or symlink a skill into `~/.claude/skills/` to make it available to Claude Code:

```bash
git clone https://github.com/shauryakapoor3108-ui/ai-skills.git
ln -s "$PWD/ai-skills/skills/feed"       ~/.claude/skills/feed
ln -s "$PWD/ai-skills/skills/video-edit" ~/.claude/skills/video-edit
```

Requirements: Python 3.10+, `ffmpeg`, `yt-dlp`. `auto-editor` and `playwright` are only needed for the optional silence-cut and screen-capture steps.

## Keys

One file, used by every skill:

```bash
mkdir -p ~/.config/ai-skills
echo 'GROQ_API_KEY=your-key-here' > ~/.config/ai-skills/.env
chmod 600 ~/.config/ai-skills/.env
```

Google Drive access (optional, `video-edit` only) reuses an existing OAuth token with `drive` scope at `~/.config/gcloud/sheets-token.json`.

## Design notes

- **No hidden state.** Config is JSON you can read, notes are markdown you own.
- **Fail loud, retry sensibly.** Feed endpoints throttle, so fetches retry with backoff instead of dying on a transient 500.
- **Nothing disappears.** An item with no captions is still filed, marked as such.
- **Local first.** Transcription falls back to local `faster-whisper` if no API key is present.

## Credits

See [CREDITS.md](CREDITS.md).

## License

MIT
