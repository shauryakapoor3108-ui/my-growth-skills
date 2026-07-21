---
description: Extract structured knowledge from a URL (video, playlist, article, repo, creator) and optionally file it into your second brain.
argument-hint: "<url> [--file] [--keep]"
allowed-tools: [Bash, Read]
---

Invoke the `intake` skill (defined in SKILL.md) with: $ARGUMENTS

Infer the extractor type from the URL (youtube watch -> video, youtube playlist ->
playlist, github repo -> repo, github user -> creator, anything else -> article).
Run `scripts/extract.py <type>`. If the user wants it captured rather than just
summarised in chat, pipe the JSON through `skills/feed/scripts/file_note.py` and
report the note path. Use `--keep` for video when follow-up questions are likely.
If an extractor reports a module is unavailable, check for a missing Python
dependency before concluding the feature is unbuilt.
