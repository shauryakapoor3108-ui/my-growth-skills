#!/usr/bin/env python3
"""
Playlist Extractor - fetches YouTube playlist metadata and video list
via yt-dlp --flat-playlist --dump-json. No per-video processing.

Exports:
    process(url: str, domain: str = DEFAULT_DOMAIN) -> dict
"""

from __future__ import annotations

from _config import DEFAULT_DOMAIN, STORE_BASE
import json
import subprocess
import sys


def process(url: str, domain: str = DEFAULT_DOMAIN) -> dict:
    """
    Fetch YouTube playlist metadata using yt-dlp --flat-playlist.

    Parameters
    ----------
    url : str
        YouTube playlist URL.
    domain : str, optional
        Domain slug (default from INTAKE_DOMAIN). Included in the result as domain.

    Returns
    -------
    dict with keys: status, type, data (or error).
    """
    try:
        out = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--dump-json", "--no-warnings", url],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return {
            "status": "error",
            "type": "playlist",
            "error": "yt-dlp not found. Install with: pip install yt-dlp",
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "type": "playlist",
            "error": f"yt-dlp timed out after 60s: {url}",
        }

    if out.returncode != 0:
        return {
            "status": "error",
            "type": "playlist",
            "error": f"yt-dlp failed: {out.stderr.strip() or 'unknown error'}",
        }

    # Parse JSON lines - first line carries playlist metadata
    lines = [l for l in out.stdout.strip().split("\n") if l.strip()]
    if not lines:
        return {
            "status": "error",
            "type": "playlist",
            "error": "No data returned from yt-dlp",
        }

    try:
        entries = [json.loads(l) for l in lines]
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "type": "playlist",
            "error": f"Failed to parse yt-dlp output: {exc}",
        }

    # Playlist-level metadata (from first entry)
    first = entries[0]
    playlist_title: str = first.get("playlist_title") or first.get("title", "Untitled Playlist")
    uploader: str = first.get("uploader") or first.get("channel", "")
    video_count: int = first.get("playlist_count", len(entries))

    # Build flat video list - no per-video processing
    videos: list[dict] = []
    for entry in entries:
        vid_id = entry.get("id", "")
        if not vid_id:
            continue
        videos.append({
            "title": entry.get("title", "Untitled"),
            "url": f"https://www.youtube.com/watch?v={vid_id}",
            "duration_sec": entry.get("duration"),
        })

    return {
        "status": "ok",
        "type": "playlist",
        "data": {
            "title": playlist_title,
            "uploader": uploader,
            "url": url.rstrip("/"),
            "video_count": video_count,
            "videos": videos,
            "domain": domain,
        },
    }


def main() -> int:
    if len(sys.argv) < 2:
        result = {
            "status": "error",
            "type": "playlist",
            "error": "Usage: python3 scripts/intake/playlist.py <playlist-url>",
        }
        print(json.dumps(result))
        return 1

    result = process(sys.argv[1])
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())