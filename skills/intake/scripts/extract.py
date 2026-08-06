#!/usr/bin/env python3
"""Dispatcher: extract.py <type> [--keep] [--domain <slug>] <url>

Types: "video" -> video.py, "article" -> article.py, "repo" -> repo.py,
       "playlist" -> playlist.py, "creator" -> creator.py.

Prints structured JSON result to stdout. Exits 0 on success, 1 on error.
"""
from __future__ import annotations

from _config import DEFAULT_DOMAIN, STORE_BASE
import importlib
import json
import sys
from pathlib import Path


# Ensure the intake scripts directory is on sys.path for imports
_SCRIPTS_DIR = Path(__file__).parent.resolve()
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


EXTRACTORS: dict[str, str] = {
    "video": "video",
    "article": "article",
    "repo": "repo",
    "playlist": "playlist",
    "creator": "creator",
}


def _parse_flags(args: list[str]) -> tuple[bool, str, list[str]]:
    """Parse --keep, --domain <slug> from args. Returns (keep, domain, url_args).

    url_args contains non-flag arguments (everything that doesn't start with
    '--' and isn't a value for a known flag).
    """
    keep = False
    domain = DEFAULT_DOMAIN
    url_args: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--keep":
            keep = True
            i += 1
        elif a == "--domain":
            if i + 1 < len(args):
                domain = args[i + 1]
                i += 2  # skip flag + value
            else:
                i += 1
        elif a.startswith("--"):
            # Unknown flag - skip it (tolerate)
            i += 1
        else:
            url_args.append(a)
            i += 1
    return keep, domain, url_args


def main() -> int:
    if len(sys.argv) < 3:
        result = {
            "status": "error",
            "error": "Usage: python3 scripts/extract.py <type> [--keep] [--domain <slug>] <url>",
        }
        print(json.dumps(result))
        return 1

    args = sys.argv[1:]

    extract_type = args[0]
    remaining_args = args[1:]

    if extract_type not in EXTRACTORS:
        result = {
            "status": "error",
            "type": extract_type,
            "error": f"Unknown extractor type: {extract_type}. "
                     f"Supported types: {', '.join(sorted(EXTRACTORS))}",
        }
        print(json.dumps(result))
        return 1

    # Parse flags properly - skip flag values, tolerate unknown flags
    keep, domain, url_args = _parse_flags(remaining_args)
    url = url_args[0] if url_args else ""

    if not url:
        result = {
            "status": "error",
            "type": extract_type,
            "error": f"No URL provided. Usage: python3 scripts/extract.py <type> [--keep] [--domain <slug>] <url>",
        }
        print(json.dumps(result))
        return 1

    module_name = EXTRACTORS[extract_type]

    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        # Distinguish "the extractor itself is missing" from "the extractor is
        # built but one of its dependencies is not installed". Reporting the
        # second as "not yet built" sends you chasing phantom missing features.
        missing = getattr(exc, "name", "") or ""
        _PIP = {"bs4": "beautifulsoup4", "readability": "readability-lxml",
                "lxml": "lxml", "requests": "requests", "PIL": "pillow"}
        if missing in ("", module_name):
            msg = f"Extractor module '{module_name}' not available (not yet built)"
        else:
            pkg = _PIP.get(missing, missing)
            msg = (f"Extractor '{module_name}' is built but is missing a Python "
                   f"dependency: '{missing}'. Install it with: pip install {pkg}")
        result = {
            "status": "error",
            "type": extract_type,
            "error": msg,
        }
        print(json.dumps(result))
        return 1

    try:
        process_fn = getattr(mod, "process")

        # --domain is passed to all extractor types (not just repo)
        # --keep is passed only to types that manage temp dirs
        kwargs = {"domain": domain}
        if extract_type in ("video", "repo"):
            kwargs["keep"] = keep
        result = process_fn(url, **kwargs)

        print(json.dumps(result))
        return 0 if result.get("status") == "ok" else 1
    except Exception as exc:
        result = {
            "status": "error",
            "type": extract_type,
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(result))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())