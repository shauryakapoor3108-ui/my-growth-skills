# Credits

## Prior art and tools

- **[claude-video / `watch`](https://github.com/bradautomates/claude-video)** by Bradley Bonanno (MIT).
  A Claude Code skill that downloads a video, extracts frames, and pulls a transcript.
  I use it, and the `feed` skill is designed to sit alongside it rather than replace it.
  No code from that project is vendored here.

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** (Unlicense) for feed and caption retrieval.
- **[auto-editor](https://github.com/WyattBlue/auto-editor)** (Unlicense) for silence detection in `video-edit`.
- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** (MIT) for local transcription fallback.
- **ffmpeg** (LGPL/GPL) for everything that touches media.
- **Groq** for `whisper-large-v3` transcription and summarisation.

Everything under `skills/` in this repository is original work.
