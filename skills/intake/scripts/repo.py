#!/usr/bin/env python3
"""
GitHub Repo Extractor — clones shallow, extracts structure + key files.

Exports:
    process(url: str) -> dict

Return shape (success):
    {"status": "ok", "type": "repo", "data": {...}}

Return shape (error):
    {"status": "error", "type": "repo", "error": "..."}
"""

from _config import DEFAULT_DOMAIN, STORE_BASE
import json
import os
import random
import re
import shutil
import string
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

# ── helpers ──────────────────────────────────────────────────────────────

_REPO_PATTERN = re.compile(
    r"^https?://github\.com/([^/]+/[^/]+?)(?:\.git)?(?:/.*)?$"
)

# Config files we read in full regardless of extension
_FULL_TEXT_FILES = frozenset({
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pyproject.toml",
    "go.sum",
    "Cargo.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
})

# Extensions we collect as key files (top-level and direct subdir level)
_KEY_EXTENSIONS = frozenset({".ts", ".py", ".js", ".go", ".rs", ".md"})

_KEY_FILE_MAX_LINES = 300
_README_MAX_BYTES = 10 * 1024  # 10 KB


def _validate_github_repo_url(url: str) -> tuple[str, str]:
    """
    Validate that *url* is a GitHub repo URL (not a user page).
    Returns (owner, repo) on success.
    Raises ValueError on invalid input.
    """
    m = _REPO_PATTERN.match(url.strip())
    if not m:
        raise ValueError(
            f"URL must be a github.com/<user>/<repo> URL, got: {url}"
        )
    full = m.group(1).rstrip("/")
    parts = full.split("/")
    if len(parts) < 2:
        raise ValueError(
            f"URL must point to a specific repo, got: {url}"
        )
    return parts[0], parts[1]


def _random_suffix(length: int = 8) -> str:
    """Return a random alphanumeric string."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _clone_repo(url: str, dest: Path) -> None:
    """Shallow clone *url* into *dest*. Raises subprocess.CalledProcessError on failure."""
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )


def _is_binary(filepath: Path) -> bool:
    """Heuristic: check first 8KB for null bytes."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(8192)
        return b"\0" in chunk
    except OSError:
        return True  # can't read → treat as binary


def _read_file_safe(filepath: Path, max_bytes: int = 0) -> str:
    """Read a text file safely. Returns content up to max_lines lines or max_bytes."""
    try:
        if max_bytes:
            with open(filepath, "rb") as f:
                raw = f.read(max_bytes)
            return raw.decode("utf-8", errors="replace")
        # Read by lines
        lines: list[str] = []
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if _KEY_FILE_MAX_LINES and i >= _KEY_FILE_MAX_LINES:
                    lines.append(f"... (truncated at {_KEY_FILE_MAX_LINES} lines)")
                    break
                lines.append(line)
        return "".join(lines)
    except OSError:
        return "<error reading file>"


def _find_readme(root: Path) -> str:
    """Find README (case-insensitive), read up to 10 KB, return text."""
    for p in root.iterdir():
        if p.is_file() and p.name.lower() == "readme.md":
            return _read_file_safe(p, max_bytes=_README_MAX_BYTES)
    # Check subdirectories too (common in some layouts)
    for subdir in root.iterdir():
        if subdir.is_dir():
            for p in subdir.iterdir():
                if p.is_file() and p.name.lower() == "readme.md":
                    return _read_file_safe(p, max_bytes=_README_MAX_BYTES)
    return ""


def _collect_structure(root: Path) -> tuple[list[str], dict[str, str], int, list[str]]:
    """
    Walk *root* and return:
      - structure: list of paths (relative)
      - key_files: dict of {relative_path: content}
      - file_count: total number of files
      - languages: set of detected extensions
    """
    structure: list[str] = []
    key_files: dict[str, str] = {}
    file_count = 0
    languages: set[str] = set()

    # Map extensions to human-readable language names
    ext_to_lang = {
        ".ts": "TypeScript",
        ".py": "Python",
        ".js": "JavaScript",
        ".go": "Go",
        ".rs": "Rust",
        ".md": "Markdown",
        ".json": "JSON",
        ".toml": "TOML",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".java": "Java",
        ".rb": "Ruby",
        ".php": "PHP",
        ".c": "C",
        ".cpp": "C++",
        ".h": "C",
        ".hpp": "C++",
        ".css": "CSS",
        ".html": "HTML",
        ".sh": "Shell",
        ".bash": "Shell",
        ".sql": "SQL",
        ".rs": "Rust",
        ".zig": "Zig",
        ".kt": "Kotlin",
        ".swift": "Swift",
    }

    git_dir = root / ".git"
    for dirpath_str, dirnames, filenames in os.walk(str(root)):
        dirpath = Path(dirpath_str)
        rel_dir = dirpath.relative_to(root)

        # Skip .git directory
        if dirpath == git_dir or (rel_dir != Path(".") and rel_dir.parts and rel_dir.parts[0] == ".git"):
            # Prune .git subdirectories
            if ".git" in dirnames:
                dirnames.remove(".git")
            continue

        # Prune .git from deeper dirs
        if ".git" in dirnames:
            dirnames.remove(".git")
        # Prune node_modules
        if "node_modules" in dirnames:
            dirnames.remove("node_modules")
        # Prune __pycache__
        if "__pycache__" in dirnames:
            dirnames.remove("__pycache__")
        # Prune .venv, venv
        if ".venv" in dirnames:
            dirnames.remove(".venv")
        if "venv" in dirnames:
            dirnames.remove("venv")

        # Collect directories
        for d in sorted(dirnames):
            rel = str((rel_dir / d).relative_to(Path(".")) if rel_dir != Path(".") else Path(d))
            structure.append(f"{rel}/")
            ext = Path(d).suffix.lower()
            if ext in ext_to_lang:
                languages.add(ext_to_lang[ext])

        # Collect files
        for f in sorted(filenames):
            rel_path = (rel_dir / f).relative_to(Path(".")) if rel_dir != Path(".") else Path(f)
            rel_str = str(rel_path)
            filepath = dirpath / f
            file_count += 1

            ext = f.lower().rsplit(".", 1)[-1] if "." in f else ""
            dot_ext = f".{ext}" if ext else ""

            structure.append(rel_str)

            # Detect language from extension
            if dot_ext in ext_to_lang:
                languages.add(ext_to_lang[dot_ext])

            # Decide whether to read the file
            should_read = False

            # Full-text config files
            if f in _FULL_TEXT_FILES:
                should_read = True
            # Top-level key files by extension
            elif rel_dir == Path(".") and dot_ext in _KEY_EXTENSIONS:
                should_read = True
            # Top-level key files in direct subdirectories (depth 1)
            elif rel_dir != Path(".") and len(rel_dir.parts) == 1:
                # Only collect .md files from depth 1 (docs, etc.)
                if dot_ext in _KEY_EXTENSIONS:
                    should_read = True

            if should_read:
                if _is_binary(filepath):
                    key_files[rel_str] = "<binary file>"
                else:
                    key_files[rel_str] = _read_file_safe(filepath)

    return structure, key_files, file_count, sorted(languages)


def _fetch_github_api(owner: str, repo: str) -> dict[str, Any]:
    """
    Fetch repo metadata from GitHub API. Returns dict with
    description, stars. May return empty fields on rate-limit / error.
    """
    import urllib.request
    import urllib.error

    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    req = urllib.request.Request(api_url, headers={"User-Agent": "sac-intake/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return {
                "description": data.get("description") or "",
                "stars": data.get("stargazers_count", 0),
            }
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return {"description": "", "stars": 0}


# ── public API ───────────────────────────────────────────────────────────

def process(url: str, keep: bool = False, domain: str = DEFAULT_DOMAIN) -> dict:
    """
    Clone *url* (shallow), extract structure + key files, return structured dict.

    Parameters
    ----------
    url : str
        GitHub repository URL (e.g. https://github.com/user/repo)
    keep : bool, optional
        If True, persist the clone to ~/knowledge/<domain>/sources/repos/<repo_name>/
        and skip temp dir cleanup.
    domain : str, optional
        Domain slug for the vault path when keep=True. Defaults to INTAKE_DOMAIN (or "default").
        Also included in the result as domain.

    Returns
    -------
    dict with keys: status, type, data (or error).
    """
    # ── 1. Validate URL ─────────────────────────────────────────────────
    try:
        owner, repo_name = _validate_github_repo_url(url)
    except ValueError as exc:
        return {
            "status": "error",
            "type": "repo",
            "error": str(exc),
        }

    full_name = f"{owner}/{repo_name}"
    # Reconstruct a clean clone URL (strip subpaths like /tree/main)
    clean_clone_url = f"https://github.com/{full_name}.git"

    # ── 2. Clone ─────────────────────────────────────────────────────────
    temp_dir = Path(tempfile.gettempdir()) / f"intake-repo-{_random_suffix()}"
    try:
        try:
            _clone_repo(clean_clone_url, temp_dir)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            if "not found" in stderr.lower() or "repository not found" in stderr.lower():
                return {
                    "status": "error",
                    "type": "repo",
                    "error": f"Repository not found or private: {full_name}",
                }
            if "Authentication failed" in stderr or "could not read" in stderr.lower():
                return {
                    "status": "error",
                    "type": "repo",
                    "error": f"Cannot access repository (private or auth required): {full_name}",
                }
            return {
                "status": "error",
                "type": "repo",
                "error": f"Clone failed: {stderr or str(exc)}",
            }
        except subprocess.TimeoutExpired:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                "status": "error",
                "type": "repo",
                "error": f"Clone timed out after 120s: {full_name}",
            }

        # ── 3. Collect data ─────────────────────────────────────────────
        readme = _find_readme(temp_dir)
        structure, key_files, file_count, languages = _collect_structure(temp_dir)

        # ── 4. Optional: GitHub API metadata ────────────────────────────
        api_data = _fetch_github_api(owner, repo_name)

    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return {
            "status": "error",
            "type": "repo",
            "error": f"Extraction failed: {exc}",
        }

    # ── 5. Handle --keep: persist clone to vault ────────────────────────
    if keep:
        vault_dir = STORE_BASE / domain / "sources" / "repos" / repo_name
        vault_dir.mkdir(parents=True, exist_ok=True)
        # Remove the temp_dir first if it already exists at vault location
        if vault_dir.exists():
            shutil.rmtree(vault_dir, ignore_errors=True)
        shutil.copytree(temp_dir, vault_dir, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.git'))
        # Do NOT clean up temp_dir — skip to keep it available
    else:
        # ── 6. Cleanup (no --keep) ──────────────────────────────────────
        shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "status": "ok",
        "type": "repo",
        "data": {
            "name": repo_name,
            "full_name": full_name,
            "description": api_data.get("description", ""),
            "url": url.rstrip("/"),
            "readme": readme,
            "file_count": file_count,
            "languages": languages,
            "key_files": key_files,
            "structure": structure,
            "domain": domain,
        },
    }


# ── CLI entry point (optional) ───────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 repo.py [--keep] [--domain <slug>] <github-url>", file=sys.stderr)
        sys.exit(1)

    # Parse optional flags before URL
    args = sys.argv[1:]
    keep = "--keep" in args
    domain = DEFAULT_DOMAIN
    if "--domain" in args:
        d_idx = args.index("--domain")
        if d_idx + 1 < len(args):
            domain = args[d_idx + 1]

    # Filter out flags to get URL
    url_args = [a for a in args if not a.startswith("--")]
    url = url_args[0] if url_args else ""

    if not url:
        print("Usage: python3 repo.py [--keep] [--domain <slug>] <github-url>", file=sys.stderr)
        sys.exit(1)

    result = process(url, keep=keep, domain=domain)
    print(json.dumps(result, indent=2))
    if result.get("status") == "error":
        sys.exit(1)