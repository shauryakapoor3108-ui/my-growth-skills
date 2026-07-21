#!/usr/bin/env python3
"""
GitHub Creator Extractor — fetches user/organization profile and top repos.

Exports:
    process(url: str, domain: str = DEFAULT_DOMAIN) -> dict
"""

from __future__ import annotations

from _config import DEFAULT_DOMAIN, STORE_BASE
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def _fetch_json(url: str) -> dict[str, Any] | None:
    """Fetch a JSON response from a URL. Returns None on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "sac-intake/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def process(url: str, domain: str = DEFAULT_DOMAIN) -> dict:
    """
    Fetch GitHub user/organization profile and top 10 repos.

    Parameters
    ----------
    url : str
        GitHub user/org URL (e.g. https://github.com/user)
    domain : str, optional
        Domain slug (default from INTAKE_DOMAIN). Included in the result as domain.

    Returns
    -------
    dict with keys: status, type, data (or error).
    """
    # Parse username from URL
    path = url.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]

    # Extract username from URL path
    from urllib.parse import urlparse
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return {
            "status": "error",
            "type": "creator",
            "error": f"Not a valid GitHub user URL: {url}",
        }

    username = parts[0]

    # ── Fetch user info ────────────────────────────────────────────────
    user_data = _fetch_json(f"https://api.github.com/users/{username}")
    if user_data is None:
        return {
            "status": "error",
            "type": "creator",
            "error": f"Could not fetch GitHub user: {username} (rate-limited or not found)",
        }

    # ── Fetch public repos (top 10 by last updated) ────────────────────
    repos_data = _fetch_json(
        f"https://api.github.com/users/{username}/repos?sort=updated&per_page=10"
    )
    repos: list[dict[str, Any]] = []
    if repos_data and isinstance(repos_data, list):
        for r in repos_data:
            repos.append({
                "name": r.get("name", ""),
                "description": r.get("description") or "",
                "url": r.get("html_url", ""),
                "language": r.get("language") or "",
                "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0),
                "updated": r.get("updated_at", ""),
            })

    return {
        "status": "ok",
        "type": "creator",
        "data": {
            "username": username,
            "name": user_data.get("name") or "",
            "bio": user_data.get("bio") or "",
            "avatar_url": user_data.get("avatar_url", ""),
            "blog": user_data.get("blog", ""),
            "location": user_data.get("location", ""),
            "company": user_data.get("company", ""),
            "public_repos": user_data.get("public_repos", 0),
            "public_gists": user_data.get("public_gists", 0),
            "followers": user_data.get("followers", 0),
            "following": user_data.get("following", 0),
            "created_at": user_data.get("created_at", ""),
            "updated_at": user_data.get("updated_at", ""),
            "type": user_data.get("type", "User"),  # "User" or "Organization"
            "repos": repos,
            "domain": domain,
        },
    }


def main() -> int:
    if len(sys.argv) < 2:
        result = {
            "status": "error",
            "type": "creator",
            "error": "Usage: python3 scripts/intake/creator.py <github-user-url>",
        }
        print(json.dumps(result))
        return 1

    result = process(sys.argv[1])
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())