# my-herdr

A [herdr](https://herdr.dev) plugin: a collection of small, independent actions for working with AI
coding agents in herdr.

> **Status: work in progress.** Nothing is installable yet. See [`docs/PLAN.md`](docs/PLAN.md).

## Planned actions

| Action | What it does |
|---|---|
| `my-herdr.fork-tab` | Fork the Claude Code session in the focused pane into a new tab |
| `my-herdr.fork-tab-ask` | Same, but first ask for a tab name and an optional prompt |
| `my-herdr.pane-to-tab` | Move the focused pane into its own tab |
| `my-herdr.attention-next` | Jump to the agent that is waiting for input or finished unread |

Written in Python 3 (standard library only): no dependencies, no build step.

## Why this exists

Some of these actions overlap with plugins already on the herdr marketplace. I still write my own,
because a herdr plugin runs arbitrary code on my machine. I would have to review someone else's plugin
before installing it, and review it again after every update, since a later release could ship
malicious code even if the version I checked was fine. These actions are small, and what they give
me isn't worth that risk or that ongoing review. When I write the plugin myself, I know what it does
today, and nobody else can change what it does tomorrow.

## Requirements

- **herdr 0.9.1 or newer.** Developed and tested against 0.9.1.
- **python3 3.9 or newer**, resolvable from the herdr server's `PATH`.
- For the fork actions: **Claude Code**, plus `herdr integration install claude` so herdr knows the
  session id to fork.

## For contributors / agents

Start with [`AGENTS.md`](AGENTS.md).
