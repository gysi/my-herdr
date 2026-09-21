# my-herdr

A [herdr](https://herdr.dev) plugin: a collection of small, independent actions for working with AI
coding agents in herdr.

> **Status: work in progress.** See [`docs/PLAN.md`](docs/PLAN.md).

## Actions

| Action | What it does |
|---|---|
| `my-herdr.attention-next` | Go to the agent that needs you, or cycle through all agents when none does |
| `my-herdr.ping` | Write the plugin environment to the plugin log, to verify an install |

Planned: `my-herdr.fork-tab` (fork the Claude Code session in the focused pane into a new tab),
`my-herdr.fork-tab-ask` (same, but ask for a tab name and an optional prompt) and
`my-herdr.pane-to-tab` (move the focused pane into its own tab).

Written in Python 3 (standard library only): no dependencies, no build step.

### `attention-next`

One key to reach any agent. It reads `herdr agent list` and works from two orderings:

- **A ring of every agent by position** — workspace, then tab, then pane. Repeated presses walk the
  ring and wrap, so this one binding reaches every agent without a second one. The ring ignores
  status, so it does not rearrange itself as agents work and finish.
- **Urgency**, which decides when to leave the ring: `blocked` (waiting for input) before `done`
  (finished, nobody has looked yet), longest-waiting first.

An agent that has *newly* started waiting cuts in and takes the next press. One that merely keeps
waiting does not, so a permanently blocked agent can't trap the key and leave everyone else
unreachable. One that stops waiting doesn't disturb the walk either, so you can answer an agent and
carry on where you were. It works across workspaces and never targets the pane you pressed the key
in.

This differs from herdr's built-in `open_notification_target`, which jumps to whichever agent the
*currently visible* toast belongs to: that needs toasts enabled and is gone once the toast is. It is
also why the action is useful with `[ui.toast] delivery = "off"` — with sound left on, a sound tells
you somebody needs you and this key takes you there, with nothing covering the screen.

## Installing

```bash
git clone https://github.com/gysi/my-herdr
herdr plugin link my-herdr        # or: herdr plugin install gysi/my-herdr
```

## Keybindings

herdr does not bind keys from a plugin manifest, so this plugin ships none and suggests none: pick
keys that do not collide with your own config and add them to `~/.config/herdr/config.toml`.

```toml
[[keys.command]]
key = "prefix+<your-key>"          # or a direct chord: "ctrl+alt+<your-key>"
type = "plugin_action"
command = "my-herdr.attention-next"
description = "next agent waiting"
```

`key` also accepts an array, so one action can have both a prefix binding and a direct one.

Reload with the in-app reload (`prefix+shift+r`, or "reload config" in the global menu), **not**
`herdr server reload-config`: keybindings are client-side and the server-only reload does not pick
them up. Then check the result — `herdr config check` reports conflicts, and `prefix+?` lists what is
bound.

Two things worth knowing before picking a key. A `[[keys.command]]` that collides with a herdr
default silently replaces it, so check `prefix+?` first. A direct binding needs a modifier: an
unmodified printable key is rejected as an unsafe direct keybinding, because it would intercept
typing.

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
