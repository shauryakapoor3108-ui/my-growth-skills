# ai-skills

A small set of AI tools that live **inside your coding agent**. Claude Code, Codex, OpenCode, Pi — whichever harness you already work in. Each one is also a plain Python script you can run from a terminal with no agent at all.

Plain Python. No framework. No runtime dependencies beyond `ffmpeg` and `yt-dlp`.

## Why this exists

Most AI tooling asks you to leave your environment and go use a product. These do the opposite: they sit in the agent you already have open, so the thing you wanted done happens where you were already working. Same reason they are model-agnostic — the harness and the provider are both config, not architecture.

## The set

### [`feed`](skills/feed) — keep the second brain fed

Subscribe to YouTube channels and RSS feeds. When something new lands, it pulls the transcript, summarises it into claims and takeaways, and files a linked note into an Obsidian vault. You read notes, not a watch-later list.

```
discover (RSS) -> transcript (yt-dlp) -> summarise (LLM) -> Obsidian note -> mark seen
```

Notes land with real frontmatter (`source`, `channel`, `published`, `tags`, `status: unread`), so Dataview and graph view pick them up the moment they are written.

### [`video-edit`](skills/video-edit) — cut a talking-head video without a timeline

Pulls a clip (Google Drive or local), transcribes it, finds false starts and dead air, cuts them, optionally overlays screen-capture cutaways and burns captions, then renders and pushes the result back.

```
pull -> transcribe -> find cuts -> tighten -> [capture cutaways -> assemble] -> render -> push
```

Built in a day. Its first real job was cutting a 77-second take down to a usable 60.

## Install

### Claude Code

```bash
/plugin marketplace add shauryakapoor3108-ui/ai-skills
/plugin install feed@ai-skills
/plugin install video-edit@ai-skills
```

### claude.ai (web)

Download a `.skill` bundle from [Releases](https://github.com/shauryakapoor3108-ui/ai-skills/releases) and upload it in the skills UI, or build one yourself:

```bash
bash scripts/build-skills.sh          # -> dist/feed.skill, dist/video-edit.skill
```

### Codex / OpenCode / Pi

Each skill ships a `.codex-plugin/plugin.json` and a self-contained `scripts/` directory. Point your harness at `skills/<name>`, or just call the scripts directly — they take plain CLI arguments and have no agent-specific code in them.

### Manual

```bash
git clone https://github.com/shauryakapoor3108-ui/ai-skills.git
ln -s "$PWD/ai-skills/skills/feed"       ~/.claude/skills/feed
ln -s "$PWD/ai-skills/skills/video-edit" ~/.claude/skills/video-edit
```

## First run

```bash
python3 scripts/setup.py          # what is missing and how to fix it
python3 scripts/setup.py --check  # silent, exit 0 when ready
```

It never uses sudo, never installs system packages behind your back, and never writes an API key to disk. It prints the exact command and scaffolds an empty key file.

## Bring your own keys

One file, used by every skill:

```bash
mkdir -p ~/.config/ai-skills
echo 'GROQ_API_KEY=your-key-here' > ~/.config/ai-skills/.env
chmod 600 ~/.config/ai-skills/.env
```

**On the provider choice.** Groq is the default because at the time of writing it is the cheapest hosted Whisper available, and `whisper-large-v3` there is both fast and accurate enough to catch things a local `base` model misses. That is a pricing observation, not an architectural commitment. Nothing here is welded to Groq:

- The transcription and chat calls are ordinary OpenAI-compatible HTTP. Point them at another provider by changing the endpoint.
- `FEED_MODEL` picks the summarisation model.
- `GROQ_WHISPER_MODEL` picks the transcription model.
- With no key at all, `video-edit` falls back to local `faster-whisper` and keeps working offline.

Google Drive access (optional, `video-edit` only) reuses an existing OAuth token with `drive` scope at `~/.config/gcloud/sheets-token.json`.

## Design notes

- **No hidden state.** Config is JSON you can read. Notes are markdown you own.
- **Fail loud, retry sensibly.** Feed endpoints throttle, so fetches retry with backoff instead of dying on a transient 500.
- **Nothing disappears.** An item with no captions is still filed and marked as such, rather than silently skipped.
- **Local first where it can be.** Transcription degrades to a local model rather than to an error.
- **Idempotent.** Re-running is safe; `seen` state means you will not double-file a note.

## Structure

```
.claude-plugin/marketplace.json   both skills, installable as one marketplace
skills/<name>/
  SKILL.md                        the skill contract the agent reads
  .claude-plugin/plugin.json      Claude Code manifest
  .codex-plugin/plugin.json       Codex manifest
  commands/<name>.md              slash-command wrapper
  scripts/                        the runtime, plain CLI, agent-agnostic
scripts/setup.py                  shared preflight
scripts/build-skills.sh           build .skill bundles
```

## Develop

```bash
bash scripts/build-skills.sh            # build every skill bundle
bash scripts/build-skills.sh feed       # or just one
git tag v0.1.0 && git push --tags       # CI builds and attaches the bundles
```

## Credits

Prior art and tools are credited in [CREDITS.md](CREDITS.md).

## License

MIT
