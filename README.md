# my-herdr

A [herdr](https://herdr.dev) plugin: a collection of small, independent actions for working with AI
coding agents in herdr.

## Install

```bash
herdr plugin install gysi/my-herdr
```

Then bind a key (see [Keybindings](#keybindings)) — herdr cannot bind keys from a plugin manifest,
so nothing happens until you do.

To work on the plugin instead, clone it and `herdr plugin link .` from the checkout. A linked plugin
and an installed one cannot share an id, so `herdr plugin unlink my-herdr` before switching either
way.

## Actions

| Action | What it does |
|---|---|
| `my-herdr.attention-next` | Go to the agent that needs you, or cycle through all agents when none does |
| `my-herdr.pane-to-tab` | Move the focused pane, and the process in it, into a new tab |
| `my-herdr.ping` | Write the plugin environment to the plugin log, to verify an install |

Written in Python 3 (standard library only): no dependencies, no build step.

Planned for later versions: forking a Claude Code session into a new tab, with and without a prompt.
See [`docs/PLAN.md`](docs/PLAN.md).

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

### `pane-to-tab`

For the moment a split has outgrown its share of the screen. The focused pane moves into a tab of its
own and takes its running process with it — the agent keeps going and lands full width.

The new tab keeps herdr's generic name on purpose: a plugin-set label looks like a manual rename to
tab-renaming plugins, which then leave it alone forever. If the pane is already the only one in its
tab, nothing happens and it says so, rather than destroying the tab and rebuilding it for the same
single pane.

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

- **herdr 0.9.1 or newer.** Developed and tested against 0.9.1. `agent focus` only moves the
  attached client from that release on, which is what makes the jump work.
- **python3 3.9 or newer**, resolvable from the herdr server's `PATH` — which is not necessarily the
  `python3` in your shell.

## Troubleshooting

Actions run headless, so they have no terminal to print to. Everything they write goes to the plugin
log:

```bash
herdr plugin log list --plugin my-herdr --limit 5
```

`my-herdr.ping` writes the whole plugin environment there and changes nothing, so it is the quickest
way to confirm an install is wired up.

A failed action also sends a notification, which is invisible if you have `[ui.toast] delivery =
"off"`; the sound still plays, and the log always has the detail.

## For contributors / agents

Start with [`AGENTS.md`](AGENTS.md).
