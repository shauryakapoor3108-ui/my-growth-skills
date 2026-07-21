#!/usr/bin/env bash
# build-skills.sh — package each skill as a claude.ai-upload-ready .skill file.
# Usage: bash scripts/build-skills.sh [skill-name ...]   (run from repo root)
#
# Produces dist/<skill>.skill — a zip whose single top-level directory is the
# skill name, containing SKILL.md and its scripts/ runtime:
#
#   feed/
#     SKILL.md
#     scripts/feed.py
#     scripts/setup.py
#
# Plugin/command/hook metadata is intentionally left out: Claude Code reads that
# from the repo, and claude.ai's bundle wants exactly one SKILL.md and no more
# than 200 files. Zipping is done with Python's zipfile so the only build
# dependency is Python itself (no `zip` binary required).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "error: working tree is dirty; commit or stash before building" >&2
  exit 1
fi

SKILLS=("$@")
if [ ${#SKILLS[@]} -eq 0 ]; then
  mapfile -t SKILLS < <(find skills -maxdepth 1 -mindepth 1 -type d -printf '%f\n' | sort)
fi

mkdir -p dist
for SKILL in "${SKILLS[@]}"; do
  [ -f "skills/$SKILL/SKILL.md" ] || { echo "error: skills/$SKILL/SKILL.md not found" >&2; exit 1; }
  python3 - "$SKILL" <<'PY'
import os, sys, zipfile

skill = sys.argv[1]
src = os.path.join("skills", skill)
out = os.path.join("dist", f"{skill}.skill")
if os.path.exists(out):
    os.remove(out)

members = [(os.path.join(src, "SKILL.md"), f"{skill}/SKILL.md")]
sdir = os.path.join(src, "scripts")
if os.path.isdir(sdir):
    for f in sorted(os.listdir(sdir)):
        if f.endswith(".py"):
            members.append((os.path.join(sdir, f), f"{skill}/scripts/{f}"))
# the shared preflight travels with every bundle
members.append(("scripts/setup.py", f"{skill}/scripts/setup.py"))

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for real, arc in members:
        z.write(real, arc)

with zipfile.ZipFile(out) as z:
    names = z.namelist()
    if len(names) > 200:
        sys.exit(f"error: {len(names)} files in {out}, claude.ai's cap is 200")
    n_skill = sum(1 for n in names if n.endswith("SKILL.md"))
    if n_skill != 1:
        sys.exit(f"error: expected exactly one SKILL.md in {out}, found {n_skill}")

size = os.path.getsize(out)
print(f"built {out} ({len(names)} files, {size/1024:.1f}K)")
PY
done
