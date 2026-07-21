# my-growth-skills

AI skills that compound. Point your coding agent at this repo and it gains the ability to keep your second brain fed and to cut your video without a timeline.

They live **inside the agent you already use** — Claude Code, Codex, OpenCode, Pi. Plain Python underneath, so they also run as ordinary CLI tools with no agent at all.

## Get started in one line

Paste this to Claude Code:

```
/plugin marketplace add shauryakapoor3108-ui/my-growth-skills
```

Then install what you want:

```
/plugin install feed@my-growth-skills
/plugin install video-edit@my-growth-skills
```

**Or just tell your agent in plain English:**

> Install the skills from github.com/shauryakapoor3108-ui/my-growth-skills, then run the preflight and tell me what's missing.

That is the whole setup. It will clone, wire the skills in, check your dependencies, and tell you the one or two things it needs from you.

## The skills

### [`feed`](skills/feed) — keep your second brain fed

Subscribe to YouTube channels and RSS feeds. When something new lands it pulls the transcript, summarises it into claims and takeaways, and files a linked note into your Obsidian vault. You read notes, not a watch-later list.

```
discover (RSS) -> transcript (yt-dlp) -> summarise (LLM) -> Obsidian note -> mark seen
```

```bash
feed add "https://www.youtube.com/@SomeChannel"
feed run --limit 5
```

Notes arrive with real frontmatter (`source`, `channel`, `published`, `type`, `provenance`, `tags`, `status: unread`), so Dataview and graph view pick them up the moment they are written.

### [`video-edit`](skills/video-edit) — cut a talking-head video without a timeline

Pulls a clip (Google Drive or local), transcribes it, finds false starts and dead air, cuts them, optionally overlays screen-capture cutaways and burns captions, then renders and pushes the result back.

```
pull -> transcribe -> find cuts -> tighten -> [capture cutaways -> assemble] -> render -> push
```

Built in a day. Its first real job was cutting a 77-second take down to a usable 60.

## Other ways to install

<details>
<summary>claude.ai (web), Codex / OpenCode / Pi, or manual</summary>

**claude.ai (web)** — download a `.skill` bundle from [Releases](https://github.com/shauryakapoor3108-ui/my-growth-skills/releases) and upload it in the skills UI, or build one:

```bash
bash scripts/build-skills.sh          # -> dist/feed.skill, dist/video-edit.skill
```

**Codex / OpenCode / Pi** — each skill ships a `.codex-plugin/plugin.json` and a self-contained `scripts/` directory. Point your harness at `skills/<name>`, or call the scripts directly. There is no agent-specific code in them.

**Manual**

```bash
git clone https://github.com/shauryakapoor3108-ui/my-growth-skills.git
ln -s "$PWD/my-growth-skills/skills/feed"       ~/.claude/skills/feed
ln -s "$PWD/my-growth-skills/skills/video-edit" ~/.claude/skills/video-edit
```
</details>

## First run

```bash
python3 scripts/setup.py          # what is missing and how to fix it
python3 scripts/setup.py --check  # silent, exit 0 when ready
```

It never uses sudo, never installs system packages behind your back, and never writes an API key to disk. It prints the exact command and scaffolds an empty key file.

## Bring your own keys

One file, used by every skill:

```bash
mkdir -p ~/.config/my-growth-skills
echo 'GROQ_API_KEY=your-key-here' > ~/.config/my-growth-skills/.env
chmod 600 ~/.config/my-growth-skills/.env
```

**On the provider choice.** Groq is the default because at the time of writing it is the cheapest hosted Whisper available, and `whisper-large-v3` there is fast and accurate enough to catch things a local `base` model misses. That is a pricing observation, not an architectural commitment. Nothing here is welded to Groq:

- Transcription and chat are ordinary OpenAI-compatible HTTP. Point them at another provider by changing the endpoint.
- `FEED_MODEL` picks the summarisation model, `GROQ_WHISPER_MODEL` the transcription model.
- With no key at all, `video-edit` falls back to local `faster-whisper` and keeps working offline.

Google Drive access (optional, `video-edit` only) reuses an existing OAuth token with `drive` scope.

## Point it at your vault

`feed` writes into whatever folder you name:

```json
// ~/.config/my-growth-skills/feed.json
{ "vault": "~/your-vault/sources/feed" }
```

Notes are `YYYY-MM-DD-title-slug.md`. If your vault has a filing standard, the frontmatter is designed to slot into it rather than fight it.

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
