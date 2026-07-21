#!/usr/bin/env python3
"""file_note.py - turn an intake result into a second-brain note.

This is the filing step intake does not do: it extracts and prints structured
JSON, this writes the durable note. Composes over a pipe, so intake alone can
feed a vault:

  python3 extract.py video --keep <url> | python3 file_note.py
  python3 file_note.py --json result.json --vault ~/vault/sources/feed

Handles every intake type (video, article, repo, creator, playlist) plus the
simpler shape `feed` produces. Frontmatter is written to slot into a vault that
has a filing standard (`type`, `provenance`) rather than fight it.

Usage:
  file_note.py [--json PATH] [--vault DIR] [--no-summary] [--tag X]

Config: ~/.config/my-growth-skills/feed.json  ("vault" key)
Key:    GROQ_API_KEY via env or ~/.config/my-growth-skills/.env
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timezone

CFG_DIR = os.path.expanduser("~/.config/my-growth-skills")
CFG = os.path.join(CFG_DIR, "feed.json")
CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.environ.get("FEED_MODEL", "llama-3.3-70b-versatile")
UA = {"User-Agent": "my-growth-skills/0.1", "Accept": "*/*"}


def cfg():
    if os.path.exists(CFG):
        try:
            return json.load(open(CFG))
        except Exception:
            pass
    return {}


def groq_key():
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    p = os.path.join(CFG_DIR, ".env")
    if os.path.exists(p):
        for line in open(p):
            if line.strip().startswith("GROQ_API_KEY"):
                return line.split("=", 1)[1].strip().strip("\"'")
    return None


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:70] or "untitled"


# ---------- normalise any intake shape into one dict ----------
def normalise(result):
    """intake returns {status,type,data}. feed passes a flatter item. Accept both."""
    if not isinstance(result, dict):
        raise SystemExit("expected a JSON object")
    if result.get("status") == "error":
        raise SystemExit(f"intake reported an error: {result.get('error')}")

    kind = result.get("type", "source")
    d = result.get("data", result)

    text = ""
    # video: transcript lives in chunks[].transcript_segments[].text
    chunks = d.get("chunks") or []
    if chunks:
        parts = []
        for ch in chunks:
            for seg in ch.get("transcript_segments") or []:
                t = (seg.get("text") or "").strip()
                if t:
                    parts.append(t)
        text = " ".join(parts)
    # article / repo / anything that already carried text
    if not text:
        for k in ("text", "content", "transcript", "readme", "body"):
            if d.get(k):
                text = d[k] if isinstance(d[k], str) else json.dumps(d[k])[:20000]
                break

    # vision descriptions are a real asset when there is no speech
    vision = []
    for ch in chunks:
        for f in ch.get("frames") or []:
            v = (f.get("vision_description") or "").strip()
            if v:
                vision.append(v)

    published = (d.get("upload_date") or d.get("published") or "")[:10]
    if len(published) == 8 and published.isdigit():  # yt-dlp YYYYMMDD
        published = f"{published[:4]}-{published[4:6]}-{published[6:8]}"

    return {
        "kind": kind,
        "title": d.get("title") or d.get("name") or "Untitled",
        "url": d.get("url") or d.get("source_url") or d.get("html_url") or "",
        "author": d.get("channel") or d.get("author") or d.get("owner") or "",
        "published": published,
        "domain": d.get("sac_domain") or d.get("domain") or "",
        "duration_sec": d.get("duration_sec"),
        "text": text,
        "vision": vision,
    }


def summarise(item, key):
    body_text = item["text"]
    if not body_text and item["vision"]:
        body_text = "VISUAL DESCRIPTIONS (no speech):\n" + "\n".join(item["vision"][:120])
    if not body_text:
        return None
    prompt = (
        "You are building a second-brain note. Summarise this source for later retrieval.\n"
        "Return markdown with EXACTLY these sections:\n"
        "## TL;DR (2 sentences)\n## Key claims (3-6 bullets, each a standalone assertion)\n"
        "## Worth stealing (tactics/ideas that are actionable)\n## Open questions\n"
        "Be concrete. No preamble, no filler.\n\n"
        f"TITLE: {item['title']}\nSOURCE: {item['author']}\nTYPE: {item['kind']}\n\n"
        f"CONTENT:\n{body_text[:24000]}"
    )
    req = urllib.request.Request(
        CHAT_URL,
        data=json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": 900}).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", **UA})
    r = json.load(urllib.request.urlopen(req, timeout=180))
    return r["choices"][0]["message"]["content"].strip()


def write_note(item, summary, vault):
    vault = os.path.expanduser(vault)
    os.makedirs(vault, exist_ok=True)
    date = item["published"] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(vault, f"{date}-{slug(item['title'])}.md")

    tags = ["feed", item["kind"]]
    fm = ["---",
          f'title: "{item["title"].replace(chr(34), chr(39))}"',
          f"source: {item['url']}",
          f'author: "{item["author"]}"',
          f"published: {date}",
          f"captured: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
          "type: source",
          "provenance: ai-generated",
          f"tags: [{', '.join(tags)}]",
          "status: unread"]
    if item.get("domain"):
        fm.append(f"domain: {item['domain']}")
    if item.get("duration_sec"):
        fm.append(f"duration_sec: {item['duration_sec']}")
    fm += ["---", "", f"# {item['title']}", ""]
    if item["url"]:
        fm.append(f"[Source]({item['url']}){(' · ' + item['author']) if item['author'] else ''}")
        fm.append("")

    body = summary or "_No transcript or text could be extracted._"
    open(path, "w").write("\n".join(fm) + body + "\n")
    return path


def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main():
    raw = open(arg("--json")).read() if arg("--json") else sys.stdin.read()
    if not raw.strip():
        raise SystemExit("no JSON on stdin (pipe intake's output in, or pass --json)")
    item = normalise(json.loads(raw))

    vault = arg("--vault") or cfg().get("vault") or "~/vault/sources"
    summary = None
    if "--no-summary" not in sys.argv:
        key = groq_key()
        if key:
            summary = summarise(item, key)
        else:
            print("warning: no GROQ_API_KEY, filing without a summary", file=sys.stderr)

    path = write_note(item, summary, vault)
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
