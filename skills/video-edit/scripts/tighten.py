#!/usr/bin/env python3
"""Tighten a talking-head clip: drop a leading false start, then remove internal dead air.
Usage: tighten.py <in> <out> [--head-cut Ns] [--tail-cut startS:endS] [--margin 0.15]
  --head-cut 3.6      start the clip at 3.6s (cuts a false start / "restart" at the top)
  --tail-cut 70.6:73  additionally remove the range 70.6..73 (e.g. filler mid/late)
  --margin 0.15       auto-editor silence margin (smaller = tighter, riskier)
Reports before/after duration.
"""
import subprocess, sys, os, tempfile

AE = os.path.expanduser("~/.venvs/autoeditor/bin/auto-editor")

def dur(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", f]).strip())

def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default

if __name__ == "__main__":
    inp, out = sys.argv[1], sys.argv[2]
    head = float(arg("--head-cut", 0) or 0)
    tail = arg("--tail-cut")
    margin = arg("--margin", "0.15")
    before = dur(inp)

    # Stage 1: build the content-cut clip (drop head, and optional tail range) via filter_complex
    stage1 = tempfile.mktemp(suffix=".mp4")
    end = before
    keeps = []  # list of (start, end)
    if tail:
        ts, te = (float(x) for x in tail.split(":"))
        keeps = [(head, ts), (te, end)]
    else:
        keeps = [(head, end)]
    fc = ""
    for i, (a, b) in enumerate(keeps):
        fc += f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS[v{i}];[0:a]atrim={a}:{b},asetpts=PTS-STARTPTS[a{i}];"
    fc += "".join(f"[v{i}][a{i}]" for i in range(len(keeps))) + f"concat=n={len(keeps)}:v=1:a=1[v][a]"
    subprocess.run(["ffmpeg", "-y", "-i", inp, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-c:a", "aac", "-b:a", "192k", stage1],
                   check=True, capture_output=True)

    # Stage 2: auto-editor silence pass
    subprocess.run([AE, stage1, "--margin", f"{margin}sec", "--no-open", "-o", out],
                   check=True, capture_output=True)
    os.unlink(stage1)
    print(f"tightened: {before:.1f}s -> {dur(out):.1f}s   ({out})")
