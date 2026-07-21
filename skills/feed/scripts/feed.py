#!/usr/bin/env python3
"""feed - subscribe to video/RSS sources, auto-watch new items, file notes into Obsidian.

  feed.py add <youtube-channel-url|rss-url> [--name "Label"]
  feed.py list
  feed.py poll [--limit N]           # show new items, don't process
  feed.py run  [--limit N] [--dry]   # process new items end to end
  feed.py backfill <url> --limit N   # process the N most recent, ignoring state

Pipeline per new item:
  discover (RSS)  ->  transcript (yt-dlp captions)  ->  summarise (Groq LLM)
  ->  write a linked markdown note into the Obsidian vault  ->  mark seen

Config: ~/.config/my-growth-skills/feed.json   (created on first `add`)
  { "vault": "~/vault/sources", "sources": [...], "seen": [...] }
Keys: GROQ_API_KEY via env or ~/.config/my-growth-skills/.env
"""
import json, os, re, subprocess, sys, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone

CFG_DIR = os.path.expanduser("~/.config/my-growth-skills")
CFG = os.path.join(CFG_DIR, "feed.json")
UA = {"User-Agent": "my-growth-skills-feed/0.1", "Accept": "*/*"}
CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
SUMMARY_MODEL = os.environ.get("FEED_MODEL", "llama-3.3-70b-versatile")


# ---------- config ----------
def load_cfg():
    if not os.path.exists(CFG):
        return {"vault": "~/vault/sources", "sources": [], "seen": []}
    return json.load(open(CFG))


def save_cfg(c):
    os.makedirs(CFG_DIR, exist_ok=True)
    json.dump(c, open(CFG, "w"), indent=2)


def groq_key():
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    p = os.path.join(CFG_DIR, ".env")
    if os.path.exists(p):
        for line in open(p):
            if line.strip().startswith("GROQ_API_KEY"):
                return line.split("=", 1)[1].strip().strip("\"'")
    return None


# ---------- discovery ----------
def fetch(url, retries=4):
    """GET with backoff. Feed endpoints (YouTube especially) throttle with
    transient 404/500s on rapid repeat fetches, so never fail on the first try."""
    import time
    last = None
    for i in range(retries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
        except Exception as e:
            last = e
            if i < retries - 1:
                time.sleep(2 ** i)  # 1s, 2s, 4s
    raise last


def resolve_feed(url):
    """Turn a YouTube channel/handle URL into its RSS feed. Pass through real RSS."""
    if "/feeds/videos.xml" in url or url.endswith(".xml") or url.endswith("/rss"):
        return url
    if "youtube.com" in url or "youtu.be" in url:
        m = re.search(r"channel/([A-Za-z0-9_-]{20,})", url)
        if m:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={m.group(1)}"
        html = fetch(url).decode("utf8", "ignore")
        m = re.search(r'"channelId":"([A-Za-z0-9_-]{20,})"', html) or \
            re.search(r'channel_id=([A-Za-z0-9_-]{20,})', html)
        if m:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={m.group(1)}"
        raise SystemExit("could not resolve a channel id from that URL")
    return url


def parse_feed(feed_url):
    """Return [{id,title,url,published,author}] newest first, for Atom or RSS."""
    root = ET.fromstring(fetch(feed_url))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for e in root.findall("a:entry", ns):  # Atom (YouTube)
        vid = (e.findtext("{http://www.youtube.com/xml/schemas/2015}videoId")
               or e.findtext("a:id", "", ns))
        link = e.find("a:link", ns)
        items.append({
            "id": vid,
            "title": (e.findtext("a:title", "", ns) or "").strip(),
            "url": link.get("href") if link is not None else "",
            "published": e.findtext("a:published", "", ns),
            "author": (e.findtext("a:author/a:name", "", ns) or "").strip(),
        })
    if not items:  # RSS 2.0
        for e in root.findall(".//item"):
            link = (e.findtext("link") or "").strip()
            items.append({
                "id": (e.findtext("guid") or link).strip(),
                "title": (e.findtext("title") or "").strip(),
                "url": link,
                "published": (e.findtext("pubDate") or "").strip(),
                "author": (e.findtext("{http://purl.org/dc/elements/1.1/}creator") or "").strip(),
            })
    return items


# ---------- transcript ----------
def transcript_for(url):
    """Captions via yt-dlp (fast, no download). Returns plain text or ''. """
    import tempfile, glob
    d = tempfile.mkdtemp()
    subprocess.run(["yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs",
                    "--sub-lang", "en.*", "--sub-format", "vtt", "-o",
                    os.path.join(d, "s.%(ext)s"), url],
                   capture_output=True, timeout=300)
    vtts = glob.glob(os.path.join(d, "*.vtt"))
    if not vtts:
        return ""
    raw = open(vtts[0], encoding="utf8", errors="ignore").read()
    lines, seen = [], set()
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln or "-->" in ln or ln.startswith(("WEBVTT", "Kind:", "Language:")) or ln.isdigit():
            continue
        ln = re.sub(r"<[^>]+>", "", ln)
        if ln and ln not in seen:
            seen.add(ln)
            lines.append(ln)
    return " ".join(lines)


# ---------- summarise ----------
def summarise(title, author, url, text, key):
    if not text:
        return None
    prompt = (
        "You are building a second-brain note. Summarise this video transcript for later retrieval.\n"
        "Return markdown with EXACTLY these sections:\n"
        "## TL;DR (2 sentences)\n## Key claims (3-6 bullets, each a standalone assertion)\n"
        "## Worth stealing (tactics/ideas that are actionable)\n## Open questions\n"
        "Be concrete. No preamble, no filler.\n\n"
        f"TITLE: {title}\nCHANNEL: {author}\n\nTRANSCRIPT:\n{text[:24000]}"
    )
    body = json.dumps({"model": SUMMARY_MODEL,
                       "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": 900}).encode()
    req = urllib.request.Request(CHAT_URL, data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", **UA})
    r = json.load(urllib.request.urlopen(req, timeout=180))
    return r["choices"][0]["message"]["content"].strip()


# ---------- file into obsidian ----------
def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:70] or "untitled"


def write_note(cfg, item, summary):
    vault = os.path.expanduser(cfg.get("vault", "~/vault/sources"))
    os.makedirs(vault, exist_ok=True)
    date = (item.get("published") or "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(vault, f"{date}-{slug(item['title'])}.md")
    fm = [
        "---",
        f'title: "{item["title"].replace(chr(34), chr(39))}"',
        f"source: {item['url']}",
        f'channel: "{item.get("author","")}"',
        f"published: {date}",
        f"captured: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "type: source",
        "provenance: ai-generated",
        "tags: [feed, video]",
        "status: unread",
        "---",
        "",
        f"# {item['title']}",
        "",
        f"[Watch]({item['url']}) · {item.get('author','')}",
        "",
    ]
    open(path, "w").write("\n".join(fm) + (summary or "_No transcript available._") + "\n")
    return path


# ---------- commands ----------
def cmd_add(cfg, url, name=None):
    feed_url = resolve_feed(url)
    items = parse_feed(feed_url)
    label = name or (items[0]["author"] if items else feed_url)
    if any(s["feed"] == feed_url for s in cfg["sources"]):
        print("already subscribed:", label)
        return
    cfg["sources"].append({"name": label, "feed": feed_url, "added": datetime.now(timezone.utc).isoformat()})
    save_cfg(cfg)
    print(f"subscribed: {label}\n  {feed_url}\n  {len(items)} items currently in feed")


def new_items(cfg, limit=None):
    seen = set(cfg.get("seen", []))
    out = []
    for s in cfg["sources"]:
        try:
            for it in parse_feed(s["feed"]):
                if it["id"] and it["id"] not in seen:
                    it["source"] = s["name"]
                    out.append(it)
        except Exception as e:
            print(f"  ! {s['name']}: {e}", file=sys.stderr)
    out.sort(key=lambda x: x.get("published", ""), reverse=True)
    return out[:limit] if limit else out


def cmd_run(cfg, limit, dry, ignore_seen=False, only=None):
    key = groq_key()
    if not key:
        raise SystemExit("no GROQ_API_KEY (env or ~/.config/my-growth-skills/.env)")
    items = new_items(cfg, limit) if not ignore_seen else parse_feed(resolve_feed(only))[:limit]
    if not items:
        print("nothing new")
        return
    for it in items:
        print(f"→ {it['title'][:70]}")
        if dry:
            continue
        text = transcript_for(it["url"])
        summary = summarise(it["title"], it.get("author", ""), it["url"], text, key) if text else None
        path = write_note(cfg, it, summary)
        cfg.setdefault("seen", []).append(it["id"])
        save_cfg(cfg)
        print(f"   filed: {path}{'' if text else '  (no captions)'}")


def main():
    cfg = load_cfg()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    a = lambda f, d=None: sys.argv[sys.argv.index(f) + 1] if f in sys.argv else d
    if cmd == "add":
        cmd_add(cfg, sys.argv[2], a("--name"))
    elif cmd == "list":
        print(f"vault: {cfg.get('vault')}\nseen: {len(cfg.get('seen', []))} items")
        for s in cfg["sources"]:
            print(f"  - {s['name']}  {s['feed']}")
    elif cmd == "poll":
        for it in new_items(cfg, int(a("--limit", 20))):
            print(f"  {it.get('published','')[:10]}  {it['source'][:18]:18}  {it['title'][:60]}")
    elif cmd == "run":
        cmd_run(cfg, int(a("--limit", 5)), "--dry" in sys.argv)
    elif cmd == "backfill":
        cmd_run(cfg, int(a("--limit", 3)), "--dry" in sys.argv, ignore_seen=True, only=sys.argv[2])
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
