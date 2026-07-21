#!/usr/bin/env bash
# build-skills.sh — package each skill as a claude.ai-upload-ready .skill file.
# Usage: bash scripts/build-skills.sh [skill-name ...]   (run from repo root)
#
# Produces dist/<skill>.skill — a zip with a single top-level <skill>/ directory
# containing SKILL.md plus its scripts/ runtime. claude.ai's upload caps a bundle
# at 200 files and expects exactly one SKILL.md, so plugin/command/hook metadata
# (which Claude Code needs from the repo, not the bundle) is stripped here.
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

  OUT="dist/$SKILL.skill"
  rm -f "$OUT"
  git archive --format=zip --prefix="$SKILL/" -o "$OUT" HEAD -- "$SRC" scripts/setup.py

  # git archive keeps the skills/<name>/ path; flatten is not possible in-place,
  # so strip the metadata dirs the claude.ai bundle does not need.
  zip -d "$OUT" \
    "$SKILL/$SRC/.claude-plugin/*" \
    "$SKILL/$SRC/.codex-plugin/*" \
    "$SKILL/$SRC/commands/*" \
    > /dev/null 2>&1 || true

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
  echo "built $OUT ($COUNT files, $SIZE)"
done
