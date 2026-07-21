#!/usr/bin/env python3
"""Setup / preflight for ai-skills.

Modes:
  setup.py --check          Silent preflight. Exit 0 if ready, non-zero on failure.
  setup.py --json           Machine-readable status.
  setup.py                  Installer. Reports what is missing and how to fix it.
  setup.py --skill feed     Check only what that skill needs.

Design (deliberate):
- Silent on success, so a skill does not spam "setup is complete" every turn.
- Idempotent: safe to re-run. Never clobbers an existing key.
- Never sudo, never auto-installs system packages. It prints the exact command.
- Never writes an API key to disk. It scaffolds a placeholder file only.
"""
from __future__ import annotations
import json, os, shutil, sys
from pathlib import Path

CFG_DIR = Path(os.path.expanduser("~/.config/ai-skills"))
ENV_FILE = CFG_DIR / ".env"

# binary -> why it is needed
REQUIRED = {
    "feed": {"yt-dlp": "pull captions from YouTube"},
    "video-edit": {"ffmpeg": "cut and render video", "ffprobe": "read media duration"},
}
OPTIONAL = {
    "video-edit": {
        "auto-editor": "silence removal (pip install auto-editor)",
    },
}
INSTALL_HINT = {
    "yt-dlp": "pipx install yt-dlp   (or: pip install --user yt-dlp)",
    "ffmpeg": "sudo apt install ffmpeg   |   brew install ffmpeg",
    "ffprobe": "ships with ffmpeg",
    "auto-editor": "pip install auto-editor",
}


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


def groq_key() -> str | None:
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.strip().startswith("GROQ_API_KEY"):
                val = line.split("=", 1)[1].strip().strip("\"'")
                return val or None
    return None


def status(skill: str | None = None) -> dict:
    skills = [skill] if skill else list(REQUIRED)
    missing, missing_optional = [], []
    for s in skills:
        for b in REQUIRED.get(s, {}):
            if not have(b):
                missing.append(b)
        for b in OPTIONAL.get(s, {}):
            if not have(b):
                missing_optional.append(b)
    key = groq_key()
    return {
        "ready": not missing and bool(key),
        "missing_required": sorted(set(missing)),
        "missing_optional": sorted(set(missing_optional)),
        "has_key": bool(key),
        "env_file": str(ENV_FILE),
    }


def scaffold_env() -> bool:
    """Create a placeholder env file. Never writes a real key."""
    if ENV_FILE.exists():
        return False
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text(
        "# ai-skills keys. Groq is used for Whisper transcription and summaries.\n"
        "# Any OpenAI-compatible endpoint works; see README to swap providers.\n"
        "GROQ_API_KEY=\n"
    )
    ENV_FILE.chmod(0o600)
    return True


def main() -> int:
    args = sys.argv[1:]
    skill = args[args.index("--skill") + 1] if "--skill" in args else None
    st = status(skill)

    if "--json" in args:
        print(json.dumps(st, indent=2))
        return 0 if st["ready"] else 1

    if "--check" in args:
        return 0 if st["ready"] else 1  # silent by design

    # installer / human mode
    print("ai-skills preflight\n")
    if st["missing_required"]:
        print("Missing required tools:")
        for b in st["missing_required"]:
            print(f"  {b:12} {INSTALL_HINT.get(b, '')}")
        print()
    else:
        print("Required tools: ok\n")

    if st["missing_optional"]:
        print("Optional (only needed for some steps):")
        for b in st["missing_optional"]:
            print(f"  {b:12} {INSTALL_HINT.get(b, '')}")
        print()

    if st["has_key"]:
        print(f"API key: found\n")
    else:
        created = scaffold_env()
        print(f"API key: missing.")
        print(f"  {'Created' if created else 'Edit'} {ENV_FILE} and set GROQ_API_KEY=...")
        print("  Groq is the default because it is currently the cheapest hosted Whisper.")
        print("  Nothing is locked to it: set GROQ_API_KEY to any OpenAI-compatible key")
        print("  and override the endpoint if you prefer another provider, or run with no")
        print("  key at all and video-edit falls back to local faster-whisper.\n")

    print("ready" if st["ready"] else "not ready")
    return 0 if st["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
