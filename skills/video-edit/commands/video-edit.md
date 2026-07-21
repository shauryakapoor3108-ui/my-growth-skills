---
description: Tighten a talking-head video. Pull it, transcribe, cut false starts and dead air, optionally overlay cutaways, render.
argument-hint: "<video-path-or-drive-id> [--target-seconds N]"
allowed-tools: [Bash, Read]
---

Invoke the `video-edit` skill (defined in SKILL.md) with the user's arguments: $ARGUMENTS

Follow the skill pipeline: pull the clip, transcribe it with `scripts/transcribe.py`, show
the transcript with pause markers so the cuts can be chosen deliberately, then tighten with
`scripts/tighten.py`. Report before and after duration. Never claim a cut is clean without
re-checking the transcript of the output.
