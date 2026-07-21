#!/usr/bin/env python3
"""Video extractor: download, chunk, extract frames+audio+transcript+vision.

Called as: python3 scripts/video.py [--keep] <youtube-url>
Also exports process(url, keep=False, domain=DEFAULT_DOMAIN) -> dict
and cleanup(temp_dir) -> None.

Vision model: google/gemini-2.5-flash (cheap, fast, vision-capable via OpenRouter).
"""
from __future__ import annotations

from _config import DEFAULT_DOMAIN, STORE_BASE
import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
import urllib.request
import urllib.error


# ── config ──────────────────────────────────────────────────────────────

VISION_MODEL = "google/gemini-2.5-flash"
"""Cheap Gemini Flash model with vision. Change to any OpenRouter vision model."""

VISION_BATCH_SIZE = 10
"""Frames per vision API call. Lower = more reliable, higher = faster & cheaper.
Prompt uses numbered FRAME_N: prefix for reliable splitting."""

VISION_MAX_TOKENS = 4096
"""Max tokens per vision API response."""

FRAMES_PER_CHUNK = 20
"""Number of JPEG frames extracted per 30-minute chunk."""

# ── helpers ──────────────────────────────────────────────────────────────

def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess, return result. Raises on non-zero exit."""
    return subprocess.run(
        cmd, capture_output=True, text=True, check=True, **kwargs
    )


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _format_date(raw: str | None) -> str | None:
    """Convert yt-dlp upload_date (YYYYMMDD) to YYYY-MM-DD."""
    if not raw or len(raw) != 8:
        return None
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _multipart_post(
    url: str, fields: dict, file_field: str, file_path: str, api_key: str
) -> bytes:
    """Make a multipart/form-data POST request using stdlib only."""

    boundary = "----" + uuid.uuid4().hex
    body_parts = []

    for key, value in fields.items():
        part = f"--{boundary}\r\n"
        part += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
        part += f"{value}\r\n"
        body_parts.append(part.encode("utf-8"))

    # File part
    file_data = Path(file_path).read_bytes()
    filename = Path(file_path).name
    disposition_header = (
        f'Content-Disposition: form-data; name="{file_field}";'
        f' filename="{filename}"\r\n'
    ).encode("utf-8")
    file_part = [
        f"--{boundary}\r\n".encode("utf-8"),
        disposition_header,
        b"Content-Type: audio/mpeg\r\n\r\n",
        file_data,
        b"\r\n",
    ]

    body = (b"".join(body_parts) + b"".join(file_part)
            + f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


# ── VTT parsing ─────────────────────────────────────────────────────────

_VTT_TIMESTAMP_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->"
    r"\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)


def _parse_vtt(vtt_path: Path) -> list[dict]:
    """Parse a WebVTT file into [{start, end, text}, ...]."""
    segments: list[dict] = []
    if not vtt_path.exists():
        return segments

    text = vtt_path.read_text(encoding="utf-8", errors="replace")

    current_start: float | None = None
    current_end: float | None = None
    current_lines: list[str] = []

    def _ts_to_sec(h, m, s, ms):
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    for line in text.split("\n"):
        stripped = line.strip()
        m = _VTT_TIMESTAMP_RE.match(stripped)
        if m:
            # Save previous segment
            if current_start is not None and current_lines:
                segments.append({
                    "start": current_start,
                    "end": current_end or current_start,
                    "text": " ".join(current_lines).strip(),
                })
            current_start = _ts_to_sec(
                m.group(1), m.group(2), m.group(3), m.group(4)
            )
            current_end = _ts_to_sec(
                m.group(5), m.group(6), m.group(7), m.group(8)
            )
            current_lines = []
        elif (
            stripped
            and not stripped.startswith("WEBVTT")
            and not stripped.startswith("NOTE")
        ):
            current_lines.append(stripped)

    # Last segment
    if current_start is not None and current_lines:
        segments.append({
            "start": current_start,
            "end": current_end or current_start,
            "text": " ".join(current_lines).strip(),
        })

    return segments


def _format_transcript(segments: list[dict]) -> str:
    """Format transcript segments into a readable text block."""
    lines = []
    for seg in segments:
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "")
        lines.append(f"[{start:.1f}s \u2192 {end:.1f}s] {text}")
    return "\n".join(lines)


# ── Download ────────────────────────────────────────────────────────────

def _download_video(url: str, output_dir: Path) -> dict:
    """Download video + subs using yt-dlp. Returns paths dict."""
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / "video.%(ext)s")

    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",
        "--impersonate", "Chrome-131:Macos-14",
        "--format", "bv*[height<=720]+ba/b[height<=720]/bv+ba/b",
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", "en,en-US,en-GB,en-orig",
        "--sub-format", "vtt",
        "--convert-subs", "vtt",
        "--no-playlist",
        "--ignore-errors",
        "-o", template,
        url,
    ]

    _run(cmd, timeout=600)

    # Find generated files
    video_path: str | None = None
    info_json_path: str | None = None
    subtitle_path: str | None = None

    for f in sorted(output_dir.iterdir()):
        if f.suffix in (".mp4", ".mkv", ".webm"):
            video_path = str(f)
        elif f.suffix == ".json" and "info" in f.name:
            info_json_path = str(f)
        elif f.suffix == ".vtt":
            subtitle_path = str(f)

    if not video_path:
        for f in output_dir.iterdir():
            if f.is_file() and f.suffix not in (
                ".json", ".vtt", ".jpg", ".png"
            ):
                video_path = str(f)
                break

    info = {}
    if info_json_path:
        try:
            info = json.loads(Path(info_json_path).read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "video_path": video_path or "",
        "info": info,
        "info_json_path": info_json_path or "",
        "subtitle_path": subtitle_path or "",
    }


# ── Chunk computation ───────────────────────────────────────────────────

def _compute_chunks(duration_sec: float) -> list[dict]:
    """Split duration into \u226430 min chunks.

    Returns [{index, start_sec, end_sec}].
    """
    chunk_duration = 1800  # 30 min in seconds
    num_chunks = max(1, math.ceil(duration_sec / chunk_duration))
    chunks = []
    for i in range(num_chunks):
        start = i * chunk_duration
        end = min((i + 1) * chunk_duration, duration_sec)
        chunks.append({"index": i, "start_sec": start, "end_sec": end})
    return chunks


# ── Frame extraction ────────────────────────────────────────────────────

def _extract_frames(
    video_path: str,
    output_dir: Path,
    start_sec: float,
    end_sec: float,
    num_frames: int = 100,
) -> list[dict]:
    """Extract `num_frames` frames from the given time range at 512px width.

    Returns list of {"index": int, "timestamp_sec": float, "path": str}.
    """
    chunk_duration = end_sec - start_sec
    if chunk_duration <= 0:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)

    fps = num_frames / chunk_duration
    output_pattern = str(output_dir / "frame-%04d.jpg")

    cmd = [
        "ffmpeg",
        "-ss", str(start_sec),
        "-i", video_path,
        "-vf", f"fps={fps},scale=512:-2",
        "-frames:v", str(num_frames),
        "-q:v", "2",
        "-y",
        output_pattern,
    ]

    try:
        subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=120
        )
    except Exception as exc:
        print(f"[video.py] frame extraction failed: {exc}", file=sys.stderr)
        return []

    frames = []
    for f in sorted(output_dir.iterdir()):
        if f.suffix == ".jpg":
            idx = len(frames)
            timestamp = start_sec + (idx * chunk_duration / num_frames)
            frames.append({
                "index": idx,
                "timestamp_sec": round(timestamp, 1),
                "path": str(f),
            })

    return frames


# ── Audio extraction ────────────────────────────────────────────────────

def _extract_audio(
    video_path: str, output_path: Path, start_sec: float, end_sec: float
) -> str:
    """Extract audio segment as 64kbps mono 16kHz mp3."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = end_sec - start_sec

    cmd = [
        "ffmpeg",
        "-ss", str(start_sec),
        "-i", video_path,
        "-t", str(duration),
        "-vn",
        "-acodec", "libmp3lame",
        "-ar", "16000",
        "-ac", "1",
        "-b:a", "64k",
        "-y",
        str(output_path),
    ]
    _run(cmd, timeout=120)
    return str(output_path)


def _split_audio_if_needed(audio_path: str, max_mb: int = 20) -> list[str]:
    """Split audio file into \u2264max_mb segments using ffmpeg segment muxer.

    Returns list of file paths.
    """
    audio_file = Path(audio_path)
    size_mb = audio_file.stat().st_size / (1024 * 1024)

    if size_mb <= max_mb:
        return [audio_path]

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True, timeout=30,
    )
    try:
        total_duration = float(result.stdout.strip())
    except (ValueError, TypeError):
        total_duration = 180.0

    num_segments = math.ceil(size_mb / max_mb)
    target_segment_duration = total_duration / num_segments

    output_dir = audio_file.parent / "audio_parts"
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(output_dir / "part-%03d.mp3")

    cmd = [
        "ffmpeg",
        "-i", audio_path,
        "-f", "segment",
        "-segment_time", str(target_segment_duration),
        "-c", "copy",
        "-y",
        pattern,
    ]
    _run(cmd, timeout=120)

    parts = sorted(
        [str(f) for f in output_dir.iterdir() if f.suffix == ".mp3"]
    )
    return parts if parts else [audio_path]


# ── Groq Whisper transcription ─────────────────────────────────────────

def _groq_transcribe(audio_path: str) -> list[dict]:
    """Transcribe audio file using Groq Whisper API.

    Returns list of {"start": float, "end": float, "text": str}.
    Uses GROQ_API_KEY env var. Returns empty list on failure.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return []

    try:
        response = _multipart_post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            fields={
                "model": "whisper-large-v3",
                "response_format": "verbose_json",
            },
            file_field="file",
            file_path=audio_path,
            api_key=api_key,
        )

        result = json.loads(response.decode("utf-8"))

        if "error" in result:
            err = result.get("error", {})
            code = err.get("code", "") if isinstance(err, dict) else ""
            if code in (
                "invalid_api_key", "rate_limit_exceeded",
                "insufficient_quota",
            ):
                print(
                    f"[video.py] Groq API error: {result['error']}",
                    file=sys.stderr,
                )
                return []

        segments = result.get("segments", [])
        return [
            {
                "start": float(s["start"]),
                "end": float(s["end"]),
                "text": s["text"].strip(),
            }
            for s in segments
            if "start" in s and "end" in s and "text" in s
        ]
    except Exception as exc:
        print(f"[video.py] Groq Whisper failed: {exc}", file=sys.stderr)
        return []


def _transcribe_chunk_fallback(subtitle_path: str | None) -> list[dict]:
    """Fallback: parse YouTube auto-sub VTT into transcript segments."""
    if not subtitle_path or not Path(subtitle_path).exists():
        return []
    try:
        return _parse_vtt(Path(subtitle_path))
    except Exception as exc:
        print(f"[video.py] VTT parse fallback failed: {exc}", file=sys.stderr)
        return []


def _transcribe_audio(
    audio_path: str,
    subtitle_path: str | None,
) -> list[dict]:
    """Transcribe audio: try Groq Whisper first, fall back to VTT."""
    segments = _groq_transcribe(audio_path)
    if segments:
        return segments
    return _transcribe_chunk_fallback(subtitle_path)


# ── Chapter parsing ────────────────────────────────────────────────────

def _parse_chapters(info: dict, chunks: list[dict]) -> list[list[dict]]:
    """Parse chapters from info.json and assign them to chunks.

    Returns list of per-chunk chapter lists with spans_chunk_boundary flag.
    """
    raw_chapters = info.get("chapters") or []
    if not raw_chapters:
        return [[] for _ in chunks]

    per_chunk: list[list[dict]] = [[] for _ in chunks]

    for ch in raw_chapters:
        ch_start = float(ch.get("start_time", 0))
        ch_end = float(ch.get("end_time", ch_start))

        for ci, chunk in enumerate(chunks):
            c_start = chunk["start_sec"]
            c_end = chunk["end_sec"]

            if ch_start < c_end and (ch_end > c_start or ch_start >= c_start):
                spans = ch_start < c_end and ch_end > c_end
                per_chunk[ci].append({
                    "title": ch.get("title", ""),
                    "start_time": ch_start,
                    "spans_chunk_boundary": spans,
                })

    return per_chunk


# ── Vision analysis via Gemini 2.5 Flash ────────────────────────────────

def _analyze_frames_vision(frames: list[dict]) -> list[dict]:
    """Send frames to Gemini 2.5 Flash via OpenRouter for vision analysis.

    Batches frames (VISION_BATCH_SIZE per call). Prompt instructs model to
    output exactly one line per frame as ``FRAME_N: <desc>`` for reliable
    splitting.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or not frames:
        for f in frames:
            f["vision_description"] = ""
        return frames

    # Build a flat list of frame descriptions indexed by their position
    results: dict[int, str] = {}

    for batch_start in range(0, len(frames), VISION_BATCH_SIZE):
        batch = frames[batch_start:batch_start + VISION_BATCH_SIZE]

        # Build prompt: list each frame as FRAME_<idx>: <timestamp>s
        lines = []
        for f in batch:
            lines.append(
                f"FRAME_{f['index']}: timestamp {f['timestamp_sec']}s"
            )
        prompt_text = (
            "I will send you several images (frames from a video). "
            "For EACH image, output exactly ONE line in this format:\n"
            "FRAME_<N>: <brief description of what you see>\n"
            "Do NOT skip any frame. Do NOT add extra text.\n"
            "Here are the frames to describe:\n"
            + "\n".join(lines)
        )

        content: list[dict] = [
            {"type": "text", "text": prompt_text},
        ]

        for f in batch:
            try:
                img_data = Path(f["path"]).read_bytes()
                b64 = base64.b64encode(img_data).decode("utf-8")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })
            except Exception:
                content.append({
                    "type": "text",
                    "text": (
                        f"[Frame at {f['timestamp_sec']}s:"
                        " failed to load]"
                    ),
                })

        payload = {
            "model": VISION_MODEL,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": VISION_MAX_TOKENS,
        }

        description_batch = ""
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))

            choice = response_data.get("choices", [{}])[0]
            description_batch = (
                choice.get("message", {}).get("content", "") or ""
            )
        except urllib.error.HTTPError as exc:
            msg = exc.read().decode('utf-8', errors='replace')[:200]
            print(
                f"[video.py] OpenRouter HTTP {exc.code}: {msg}",
                file=sys.stderr,
            )
        except Exception as exc:
            print(
                f"[video.py] OpenRouter vision batch failed: {exc}",
                file=sys.stderr,
            )

        # Parse FRAME_N: <desc> lines from the response.
        # Capture only the text up to the next FRAME_ marker or end of string.
        for f in batch:
            pattern = re.compile(
                rf"FRAME_{f['index']}\s*[:\s]+(.+?)(?=\nFRAME_|\Z)",
                re.IGNORECASE | re.DOTALL,
            )
            m = pattern.search(description_batch)
            if m:
                desc = m.group(1).strip()
                # strip any trailing newline + non-alpha noise
                desc = re.sub(r"\n.*$", "", desc)
                results[f["index"]] = desc

    # Assign descriptions back, defaulting to empty
    for f in frames:
        f["vision_description"] = results.get(f["index"], "")

    return frames


# ── Cleanup ─────────────────────────────────────────────────────────────

def cleanup(temp_dir: str) -> None:
    """Delete a temporary directory (video temp dir) after all inference is done.

    Use this after you have finished extracting all knowledge from the video
    and no longer need the frames, audio, or intermediate files on disk.
    """
    path = Path(temp_dir)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


# ── Main process ────────────────────────────────────────────────────────

def process(url: str, keep: bool = False, domain: str = DEFAULT_DOMAIN) -> dict:
    """Download a video, chunk it, extract frames+audio+transcript+vision.

    Parameters
    ----------
    url : str
        YouTube video URL.
    keep : bool, optional
        If True, persist the temp directory by writing a .keep sentinel
        so that the ``finally`` cleanup block skips deletion.
        **Use keep=True for multi-video progressive sessions where you need
        to cross-reference frames across videos.** Clean up manually with
        cleanup(temp_dir) when done.
    domain : str, optional
        Domain slug (default from INTAKE_DOMAIN). Included in the result as domain.

    Returns
    -------
    dict with key "data" containing the new chunked schema.
    """
    if not _is_url(url):
        return {
            "status": "error",
            "type": "video",
            "error": f"Not a valid URL: {url}",
        }

    work = Path(tempfile.mkdtemp(prefix="intake-video-"))

    try:
        # ── Step 1: Download video + subs ─────────────────────────────
        dl = _download_video(url, work / "download")
        video_path = dl["video_path"]
        info = dl["info"]

        if not video_path or not Path(video_path).exists():
            return {
                "status": "error",
                "type": "video",
                "error": "Download failed \u2014 no video file produced",
            }

        # ── Step 2: Get duration ──────────────────────────────────────
        duration_sec = float(info.get("duration", 0))
        if duration_sec <= 0:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True, text=True, timeout=30,
            )
            try:
                duration_sec = float(result.stdout.strip())
            except (ValueError, TypeError):
                duration_sec = 0.0

        if duration_sec <= 0:
            return {
                "status": "error",
                "type": "video",
                "error": "Could not determine video duration",
            }

        # ── Step 3: Compute chunks ────────────────────────────────────
        chunks = _compute_chunks(duration_sec)
        subtitle_path = dl.get("subtitle_path")

        # ── Step 4: Process each chunk ────────────────────────────────
        chunk_results: list[dict] = []
        chapter_lists = _parse_chapters(info, chunks)

        for ci, chunk in enumerate(chunks):
            chunk_dir = work / f"chunk-{ci}"

            # 4a: Extract frames per chunk
            frames = _extract_frames(
                video_path, chunk_dir / "frames",
                chunk["start_sec"], chunk["end_sec"],
                num_frames=FRAMES_PER_CHUNK,
            )

            # 4b: Extract audio and transcribe
            audio_path = _extract_audio(
                video_path, chunk_dir / "audio.mp3",
                chunk["start_sec"], chunk["end_sec"],
            )

            audio_parts = _split_audio_if_needed(audio_path)
            transcript_segments: list[dict] = []
            for part in audio_parts:
                segs = _transcribe_audio(part, subtitle_path)
                transcript_segments.extend(segs)

            # 4c: Vision analysis via Gemini 2.5 Flash
            frames = _analyze_frames_vision(frames)

            # 4d: Validate vision — every frame must have non-empty vision_description
            pending_frames = [f for f in frames if f.get("vision_description", "") == ""]
            if pending_frames:
                print(f"[video.py] warning: {len(pending_frames)} frames with no vision description", file=sys.stderr)

            # 4e: Assemble chunk result (strip frame paths from output)
            chunk_results.append({
                "index": ci,
                "start_sec": chunk["start_sec"],
                "end_sec": chunk["end_sec"],
                "frames": [
                    {
                        "index": f["index"],
                        "timestamp_sec": f["timestamp_sec"],
                        "vision_description": f.get("vision_description", ""),
                    }
                    for f in frames
                ],
                "transcript_segments": transcript_segments,
                "chapters": (
                    chapter_lists[ci] if ci < len(chapter_lists) else []
                ),
            })

        # ── Step 5: Build metadata ────────────────────────────────────
        title = info.get("title") or "Unknown Title"
        channel = info.get("uploader") or info.get("channel") or ""
        source_url = info.get("url") or url
        upload_date = _format_date(info.get("upload_date"))

        has_captions = bool(subtitle_path) or bool(
            info.get("subtitles") or info.get("automatic_captions")
        )

        # Write .keep sentinel if --keep was requested
        if keep:
            (work / ".keep").touch()

        return {
            "status": "ok",
            "type": "video",
            "data": {
                "title": title,
                "url": source_url,
                "channel": channel,
                "upload_date": upload_date or "",
                "duration_sec": int(round(duration_sec)),
                "has_captions": has_captions,
                "temp_dir": str(work),
                "domain": domain,
                "chunks": chunk_results,
            },
        }

    except subprocess.CalledProcessError as exc:
        return {
            "status": "error",
            "type": "video",
            "error": f"Subprocess failed: {exc.stderr or str(exc)}",
        }
    except Exception as exc:
        return {
            "status": "error",
            "type": "video",
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        # Conditional cleanup: only delete if .keep sentinel is absent
        sentinel = work / ".keep"
        if not sentinel.exists():
            shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Extract video content")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--keep", action="store_true",
                        help="Keep temp directory after extraction")
    args = parser.parse_args()

    result = process(args.url, keep=args.keep)
    print(json.dumps(result))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())