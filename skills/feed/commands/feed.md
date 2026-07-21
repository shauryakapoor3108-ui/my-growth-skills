---
description: Check subscriptions for new videos or articles, pull transcripts, summarise, and file notes into your Obsidian vault.
argument-hint: "[add <url> | list | poll | run] [--limit N]"
allowed-tools: [Bash, Read]
---

Invoke the `feed` skill (defined in SKILL.md) with the user's arguments: $ARGUMENTS

Run the skill's pipeline via `scripts/feed.py`. With no arguments, run `poll` to show
what is new and ask whether to process it. Report the paths of any notes written.
If a source has no captions, say so plainly rather than pretending it was summarised.
