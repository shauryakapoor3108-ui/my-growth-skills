---
name: video-edit
description: Tighten and assemble talking-head video with an AI pipeline. Pulls a clip (local path or Google Drive), transcribes it with Groq whisper-large-v3, finds and cuts false starts / restarts / dead-air pauses, optionally overlays screen-capture cutaways and burns captions, re-renders, and pushes back. Use when the user says "edit my video", "tighten this clip", "cut the pauses", "remove dead air / restarts", "assemble the reel", or wants a filmed take trimmed to length.
---

# video-edit

An AI video-editing pipeline built from plain tools: **ffmpeg** + **Groq Whisper** + **auto-editor** + **Playwright**. No timeline app, no manual scrubbing. Everything is scriptable and re-runnable.

## The pipeline

```
pull (Drive/local) -> transcribe (Groq whisper-large-v3) -> find cuts (false starts, restarts, pauses)
   -> tighten (ffmpeg + auto-editor) -> [capture cutaways -> assemble + captions] -> render -> push (Drive)
```

## Keys / deps
- **GROQ_API_KEY** — from the environment or `~/.config/my-growth-skills/.env`. Used for whisper-large-v3 transcription. With no key, transcription falls back to local `faster-whisper`.
- **Google Drive** (optional) — reuses an existing OAuth token with `drive` scope at `~/.config/gcloud/sheets-token.json`. Only needed to pull/push clips from Drive; local files need nothing.
- **ffmpeg** (required), plus optional **auto-editor** (silence removal), **faster-whisper** (local transcription), **playwright** (chromium, for cutaway capture).

## Scripts (all under `scripts/`, run with `~/.venvs/autoeditor/bin/python`)

- **`gdrive.py`** — `list` recent videos · `pull <fileId> <out>` · `push <file> "<name>"` (uploads beside the pulled file).
- **`transcribe.py <audio_or_video>`** — Groq whisper-large-v3 → prints segments with timestamps, writes `.srt` and a `.words.json`. Falls back to local faster-whisper if no key.
- **`tighten.py <in> <out> [--head-cut Ns] [--margin 0.15]`** — cut a leading false start (`--head-cut`), then auto-editor removes internal silences. Reports before/after duration.
- **`capture.py <url> <out.mp4> [--seconds N] [--click "text"]`** — Playwright records a live web UI to video (navigate, optional click e.g. a "Demo mode" button, record N seconds). webm→mp4.
- **`assemble.py <talkinghead> <edl.json> <out.mp4>`** — overlays cutaway clips on the talking head at their timecodes and burns captions from an `.srt`. `edl.json` = `[{"clip":"deck.mp4","at":6.0,"len":4.0}, ...]`.

## Typical run (what made the job video)
```bash
V=~/.venvs/autoeditor/bin/python
$V scripts/gdrive.py list                              # find the clip
$V scripts/gdrive.py pull <fileId> raw.mp4
$V scripts/transcribe.py raw.mp4                       # read transcript, spot the false start + pauses
$V scripts/tighten.py raw.mp4 final.mp4 --head-cut 3.6 # cut junk head + dead air
$V scripts/gdrive.py push final.mp4 "clip - tightened.mp4"
```

## Notes
- Silence removal creates small **jump cuts** on a bare talking head — normal; cutaways (via `capture.py` + `assemble.py`) sit on top and hide them.
- Never print or commit key values. The Drive token and GROQ key stay local.
- Groq transcription is far more accurate than local base whisper (e.g. it correctly heard "evals", not "emails"). Prefer it.
