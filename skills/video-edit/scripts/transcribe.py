#!/usr/bin/env python3
"""Transcribe audio/video with Groq whisper-large-v3 (fallback: local faster-whisper).

Usage:
  transcribe.py <input> [--srt out.srt] [--json out.json] [--gaps 0.8]

Prints segments with timestamps and marks pauses (useful for finding dead air /
false starts before a cut). Key resolution order:
  1. $GROQ_API_KEY
  2. $GROQ_ENV_FILE (path to a .env containing GROQ_API_KEY=...)
  3. ~/.config/my-growth-skills/.env
"""
import io, json, os, subprocess, sys, tempfile, urllib.request

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODEL = os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3")


def groq_key():
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    candidates = [os.environ.get("GROQ_ENV_FILE"), os.path.expanduser("~/.config/my-growth-skills/.env")]
    for path in filter(None, candidates):
        if os.path.exists(path):
            for line in open(path):
                if line.strip().startswith("GROQ_API_KEY"):
                    return line.split("=", 1)[1].strip().strip("\"'")
    return None


def to_wav(inp):
    """Extract mono 16k wav (whisper's preferred input, and small enough to upload)."""
    if inp.lower().endswith(".wav"):
        return inp, False
    wav = tempfile.mktemp(suffix=".wav")
    subprocess.run(["ffmpeg", "-y", "-i", inp, "-ac", "1", "-ar", "16000", wav],
                   check=True, capture_output=True)
    return wav, True


def _multipart(fields, file_field, filename, file_bytes, content_type="audio/wav"):
    """Build a correct multipart/form-data body. (The earlier hand-rolled version
    interleaved headers wrongly and Groq rejected it -- this is the fix.)"""
    boundary = "----my-growth-skills-" + os.urandom(8).hex()
    buf = io.BytesIO()
    for name, value in fields.items():
        buf.write(f"--{boundary}\r\n".encode())
        buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        buf.write(f"{value}\r\n".encode())
    buf.write(f"--{boundary}\r\n".encode())
    buf.write(f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode())
    buf.write(f"Content-Type: {content_type}\r\n\r\n".encode())
    buf.write(file_bytes)
    buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), boundary


def groq_transcribe(wav, key):
    body, boundary = _multipart(
        {"model": MODEL, "response_format": "verbose_json", "timestamp_granularities[]": "segment"},
        "file", os.path.basename(wav), open(wav, "rb").read())
    req = urllib.request.Request(GROQ_URL, data=body, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        # Groq's edge rejects urllib's default UA with a 403.
        "User-Agent": "my-growth-skills/0.1 (+https://github.com/shauryakapoor3108-ui)",
        "Accept": "application/json",
    })
    data = json.load(urllib.request.urlopen(req, timeout=180))
    return [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in data.get("segments", [])]


def local_transcribe(wav):
    from faster_whisper import WhisperModel
    m = WhisperModel(os.environ.get("LOCAL_WHISPER_MODEL", "base.en"), device="cpu", compute_type="int8")
    segs, _ = m.transcribe(wav, vad_filter=True)
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segs]


def srt_ts(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    inp = sys.argv[1]
    wav, temp = to_wav(inp)
    try:
        key = groq_key()
        if key:
            segs = groq_transcribe(wav, key)
            src = f"groq {MODEL}"
        else:
            segs = local_transcribe(wav)
            src = "local faster-whisper (no GROQ_API_KEY found)"
    finally:
        if temp and os.path.exists(wav):
            os.unlink(wav)

    print(f"# {src} — {len(segs)} segments")
    gap_min = float(arg("--gaps", 0.8))
    prev = 0.0
    for s in segs:
        gap = s["start"] - prev
        mark = f"   <-- {gap:.1f}s pause" if gap >= gap_min else ""
        print(f"[{s['start']:7.2f} -> {s['end']:7.2f}] {s['text'].strip()}{mark}")
        prev = s["end"]

    if (srt := arg("--srt")):
        with open(srt, "w") as f:
            for i, s in enumerate(segs, 1):
                f.write(f"{i}\n{srt_ts(s['start'])} --> {srt_ts(s['end'])}\n{s['text'].strip()}\n\n")
        print("wrote", srt)
    if (js := arg("--json")):
        json.dump(segs, open(js, "w"), indent=2)
        print("wrote", js)
    return 0


if __name__ == "__main__":
    sys.exit(main())
