#!/usr/bin/env python3
"""Record a live web UI to video with Playwright (for cutaways / "hyperframes").
Usage: capture.py <url> <out.mp4> [--seconds N] [--click "Button text"] [--w 1920] [--h 1080] [--scroll]
Navigates, optionally clicks an element (e.g. a "Demo mode" button), records N seconds, webm->mp4.
"""
import subprocess, sys, os, tempfile, glob, time

def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default

if __name__ == "__main__":
    url, out = sys.argv[1], sys.argv[2]
    seconds = float(arg("--seconds", 8))
    click = arg("--click")
    w, h = int(arg("--w", 1920)), int(arg("--h", 1080))
    scroll = "--scroll" in sys.argv
    vdir = tempfile.mkdtemp()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": w, "height": h},
                            record_video_dir=vdir, record_video_size={"width": w, "height": h},
                            device_scale_factor=2)
        pg = ctx.new_page()
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print("goto warn:", e)
        pg.wait_for_timeout(4000)  # let the app hydrate/render
        # strip any embed/generator badge (e.g. "Edit with Lovable", gpteng)
        try:
            pg.evaluate("""() => {
              const kill = el => el && el.remove();
              document.querySelectorAll('a[href*="lovable"], a[href*="gpteng"]').forEach(a => kill(a.closest('div')||a));
              [...document.querySelectorAll('*')].forEach(el => {
                const t=(el.textContent||'').trim();
                if ((t==='Edit with Lovable'||t.includes('Edit with Lovable')) && el.children.length<3) kill(el);
              });
            }""")
        except Exception as e:
            print("badge-strip warn:", e)
        if click:
            try:
                pg.get_by_text(click, exact=False).first.click(timeout=8000)
            except Exception as e:
                print("click warn:", e)
        end = time.time() + seconds
        while time.time() < end:
            if scroll:
                pg.mouse.wheel(0, 220)
            pg.wait_for_timeout(500)
        ctx.close(); b.close()

    webm = sorted(glob.glob(os.path.join(vdir, "*.webm")))[-1]
    subprocess.run(["ffmpeg", "-y", "-i", webm, "-t", str(seconds),
                    "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-an", out],
                   check=True, capture_output=True)
    print("captured", out, f"({seconds:.0f}s @ {w}x{h})")
