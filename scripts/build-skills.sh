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
# than 200 files.
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
  SRC="skills/$SKILL"
  [ -f "$SRC/SKILL.md" ] || { echo "error: $SRC/SKILL.md not found" >&2; exit 1; }

  STAGE="$(mktemp -d)"
  trap 'rm -rf "$STAGE"' EXIT
  mkdir -p "$STAGE/$SKILL/scripts"

  cp "$SRC/SKILL.md" "$STAGE/$SKILL/SKILL.md"
  if [ -d "$SRC/scripts" ]; then
    cp "$SRC"/scripts/*.py "$STAGE/$SKILL/scripts/" 2>/dev/null || true
  fi
  cp scripts/setup.py "$STAGE/$SKILL/scripts/setup.py"   # shared preflight travels with the bundle

  OUT="$REPO_ROOT/dist/$SKILL.skill"
  rm -f "$OUT"
  (cd "$STAGE" && zip -qr "$OUT" "$SKILL")

  COUNT=$(unzip -l "$OUT" | tail -1 | awk '{print $2}')
  SIZE=$(du -h "$OUT" | cut -f1)
  if [ "$COUNT" -gt 200 ]; then
    echo "error: $COUNT files in $OUT, claude.ai's cap is 200" >&2
    exit 1
  fi
  SKILL_MD_COUNT=$(unzip -l "$OUT" | grep -c "SKILL.md" || true)
  if [ "$SKILL_MD_COUNT" -ne 1 ]; then
    echo "error: expected exactly one SKILL.md in $OUT, found $SKILL_MD_COUNT" >&2
    exit 1
  fi

  rm -rf "$STAGE"; trap - EXIT
  echo "built $OUT ($COUNT files, $SIZE)"
done
