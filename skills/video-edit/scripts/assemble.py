#!/usr/bin/env python3
"""Overlay cutaway clips on a talking head at timecodes, keep the talking-head audio,
optionally burn captions. Cutaways are full-frame B-roll (video swaps, voice continues).
Usage: assemble.py <talkinghead.mp4> <edl.json> <out.mp4> [--srt captions.srt]
  edl.json = [{"clip":"deck.mp4","at":6.0,"len":4.0}, {"clip":"lovable.mp4","at":27,"len":4}]
"""
import json, subprocess, sys, os

def probe(f, key):
    return subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                    "-show_entries", f"stream={key}", "-of", "csv=p=0", f]).decode().strip()

if __name__ == "__main__":
    base, edlf, out = sys.argv[1], sys.argv[2], sys.argv[3]
    srt = sys.argv[sys.argv.index("--srt") + 1] if "--srt" in sys.argv else None
    edl = json.load(open(edlf))
    W, H = probe(base, "width"), probe(base, "height")

    inputs = ["-i", base]
    for e in edl:
        inputs += ["-i", e["clip"]]

    fc = f"[0:v]scale={W}:{H},setsar=1[base];"
    cur = "base"
    for i, e in enumerate(edl, start=1):
        at, ln = float(e["at"]), float(e["len"])
        # scale cutaway to full frame, shift its PTS to start at `at`, overlay only during the window
        fc += (f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
               f"setpts=PTS-STARTPTS+{at}/TB[c{i}];"
               f"[{cur}][c{i}]overlay=enable='between(t,{at},{at+ln})'[o{i}];")
        cur = f"o{i}"
    vlabel = cur
    if srt:
        fc += f"[{cur}]subtitles={srt}:force_style='FontSize=22,Outline=1,Shadow=0,MarginV=40'[vf];"
        vlabel = "vf"

    fc = fc.rstrip(";")
    cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", fc,
           "-map", f"[{vlabel}]", "-map", "0:a",
           "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", out]
    subprocess.run(cmd, check=True)
    print("assembled", out)
