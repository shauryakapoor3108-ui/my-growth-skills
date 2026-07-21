---
name: intake
description: Extract structured knowledge from any URL — video, playlist, article, GitHub repo, or creator profile. Videos are chunked, transcribed and analysed frame-by-frame with a vision model. Outputs structured JSON, and pipes into a second-brain note. Use when the user says "ingest this", "extract this video", "read this article", "analyse this repo", "what's in this playlist", or hands over a link they want captured rather than just read.
---

# intake

The extraction engine. Give it a URL, get structured knowledge back.

It is deliberately one job: **turn a source into structured data**. It does not decide where that data lives. Pipe it into [`file_note.py`](../feed/scripts/file_note.py) and it becomes a note in your second brain. That separation is why the same engine serves a one-off link and an automated subscription run.

```
        one-off link ─┐
                      ├─→  intake  ─→  file_note  ─→  second brain
   feed (subscriptions) ─┘
```

## How it fits the set

| Skill | Job |
|---|---|
| [`feed`](../feed) | Finds what is **new** (RSS/YouTube subscriptions, seen-state) |
| **`intake`** | Turns a **URL** into structured knowledge |
| `file_note.py` | Turns that into a **note** with vault-ready frontmatter |

`feed` delegates to `intake` when it is installed, and falls back to a simpler captions-only path when it is not. Use `intake` alone whenever you just want to capture one thing properly.

## Extractors

| Type | What you get |
|---|---|
| `video` | 30-min chunking, frames at 512px, Groq Whisper transcript (VTT fallback), **per-frame vision descriptions** |
| `playlist` | flat video list, ready to loop |
| `article` | clean readable text plus metadata |
| `repo` | structure, key files, README; `--keep` persists the clone |
| `creator` | GitHub profile and top repos |

The vision pass is the part worth knowing about: frames are described by a vision model, so a video that *shows* rather than *says* (diagrams, screen recordings, whiteboards) still yields usable knowledge.

## Usage

```bash
S=skills/intake/scripts

# structured JSON to stdout
python3 $S/extract.py video   "https://youtube.com/watch?v=..."
python3 $S/extract.py article "https://example.com/post"
python3 $S/extract.py repo    "https://github.com/owner/name"
python3 $S/extract.py playlist "https://youtube.com/playlist?list=..."
python3 $S/extract.py creator "https://github.com/owner"

# straight into the second brain
python3 $S/extract.py video "<url>" | python3 skills/feed/scripts/file_note.py

# keep the working directory (frames, audio) for follow-up questions
python3 $S/extract.py video --keep "<url>"
```

`--keep` matters for video: frames and audio stay on disk so you can ask
follow-up questions, compare across videos, or re-transcribe with another model
without downloading again. Without it the working directory is removed as soon
as extraction returns.

## Config

Everything personal is an environment variable, nothing is hardcoded:

| Variable | Default | Purpose |
|---|---|---|
| `INTAKE_DOMAIN` | `default` | Domain slug notes are filed under. Useful if your vault routes by project. |
| `INTAKE_STORE` | `~/knowledge` | Where `--keep` persists durable artifacts. |
| `GROQ_API_KEY` | — | Whisper transcription |
| `OPENROUTER_API_KEY` | — | Frame vision descriptions |

Keys resolve from the environment or `~/.config/my-growth-skills/.env`.

## Output

```json
{ "status": "ok", "type": "video",
  "data": { "title": "...", "url": "...", "channel": "...", "domain": "...",
            "duration_sec": 0, "temp_dir": "...", "chunks": [ ... ] } }
```

`chunks[].transcript_segments[]` carries the speech, `chunks[].frames[].vision_description` the visuals. `file_note.py` understands this shape and every other extractor's, so filing is one pipe regardless of type.

## Requirements

`yt-dlp` and `ffmpeg` for video. `beautifulsoup4` and `readability-lxml` for articles (`pip install beautifulsoup4 readability-lxml`). `git` for repos.

If an extractor reports that a module is unavailable, check for a missing Python
dependency first — that is the usual cause.
