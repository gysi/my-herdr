# my-herdr

A [herdr](https://herdr.dev) plugin: a collection of small, independent actions for working with AI coding agents in herdr.

## Install

```bash
herdr plugin install gysi/my-herdr
```

Then bind a key (see [Keybindings](#keybindings)) — herdr cannot bind keys from a plugin manifest, so nothing happens until you do.

To work on the plugin instead, clone it and `herdr plugin link .` from the checkout. A linked plugin and an installed one cannot share an id, so `herdr plugin unlink my-herdr` before switching either way.

## Actions

| Action | What it does |
|---|---|
| [`my-herdr.attention-next`](docs/actions.md#attention-next) | Jump to blocked agents, then unread answers, longest-waiting first. Once all of them are visited, cycle down the sidebar's agent list across workspaces. Works with toasts disabled. |
| [`my-herdr.attention-prev`](docs/actions.md#attention-prev) | Move up the sidebar's agent list, wrapping at the top and ignoring urgency interruptions. Reverses list order, not visit history. |
| [`my-herdr.fork-tab`](docs/actions.md#fork-tab) | Fork the focused pane's Claude Code, Codex or OpenCode session into a new tab in the same workspace, leaving the source untouched. The fork gets its own session ID and focus immediately; failed startup closes the tab and restores focus. |
| [`my-herdr.fork-tab-ask`](docs/actions.md#fork-tab-ask) | Like `fork-tab`, but asks for a name first: **Enter** forks, **Esc** cancels, and an empty name keeps herdr's default. Names the tab and, for Claude and OpenCode, the forked session too. The popup closes immediately so you can watch the fork start. |
| [`my-herdr.pane-to-tab`](docs/actions.md#pane-to-tab) | Move the focused pane and its running process into a tab of its own, without restarting anything. Does nothing if already alone in its tab. Keeps herdr's default tab name so tab-renaming plugins can manage it. |
| [`my-herdr.ping`](docs/actions.md#ping) | Write the plugin environment to the plugin log, to verify an install. Changes nothing. |

Written in Python 3 (standard library only): no dependencies, no build step.

**Fork setup:** install the matching herdr integration and start or resume the session in its pane. Claude background sessions are unsupported; OpenCode requires its full-screen TUI and normal shared service. See [setup](docs/actions.md#setup-and-logging) and the caveats for [Claude Code](docs/actions.md#claude-code), [Codex](docs/actions.md#codex), and [OpenCode](docs/actions.md#opencode) before forking.

Both attention actions match the standard grouped/priority sidebar for one local client; see [sidebar matching limits](docs/actions.md#shared-navigation-state-and-sidebar-matching). The [action reference](docs/actions.md) covers detailed behavior, agent-specific setup, and limitations.

## Keybindings

herdr does not bind keys from a plugin manifest, so this plugin ships none and suggests none: pick keys that do not collide with your own config and add them to `~/.config/herdr/config.toml`.

```toml
[[keys.command]]
key = "prefix+<your-key>"          # or a direct chord: "ctrl+alt+<your-key>"
type = "plugin_action"
command = "my-herdr.attention-next"
description = "next agent waiting"

[[keys.command]]
key = "prefix+<your-previous-key>"
type = "plugin_action"
command = "my-herdr.attention-prev"
description = "previous agent in sidebar"
```

`key` also accepts an array, so one action can have both a prefix binding and a direct one.

Reload with the in-app reload (`prefix+shift+r`, or "reload config" in the global menu), **not** `herdr server reload-config`: keybindings are client-side and the server-only reload does not pick them up. Then check the result — `herdr config check` reports conflicts, and `prefix+?` lists what is bound.

Two things worth knowing before picking a key. A `[[keys.command]]` that collides with a herdr default silently replaces it, so check `prefix+?` first. A direct binding needs a modifier: an unmodified printable key is rejected as an unsafe direct keybinding, because it would intercept typing.

## Why this exists

Some of these actions overlap with plugins already on the herdr marketplace. I still write my own, because a herdr plugin runs arbitrary code on my machine. I would have to review someone else's plugin before installing it, and review it again after every update, since a later release could ship malicious code even if the version I checked was fine. These actions are small, and what they give me isn't worth that risk or that ongoing review. When I write the plugin myself, I know what it does today, and nobody else can change what it does tomorrow.

## Requirements

**Testing and maintenance target the latest releases of Claude Code, Codex, and OpenCode.** Older versions may still work, but are not tested or actively supported. Keep your agent CLIs and their herdr integrations up to date; no compatibility guarantees are made for older releases.

- **herdr 0.9.1 or newer.** Developed and tested against 0.9.1. `agent focus` only moves the attached client from that release on, which is what makes the jump work.
- **python3 3.9 or newer**, resolvable from the herdr server's `PATH` — which is not necessarily the `python3` in your shell.
- **For fork actions:** Claude Code, Codex CLI (with `codex fork` support), or OpenCode, available in the new pane's shell, and the matching herdr integration installed. Start or resume the source session in its pane after installing the integration. OpenCode also needs its CLI on the herdr server's `PATH`, a current shared service, and a full-screen TUI with current herdr integration.

## Troubleshooting

Actions run headless, so they have no terminal to print to. Everything they write goes to the plugin log:

```bash
herdr plugin log list --plugin my-herdr --limit 5
```

`my-herdr.ping` writes the whole plugin environment there and changes nothing, so it is the quickest way to confirm an install is wired up.

A failed action also sends a notification, which is invisible if you have `[ui.toast] delivery = "off"`; the sound still plays, and the log has the detail.

## For contributors / agents

Start with [`AGENTS.md`](AGENTS.md). The [documentation index](docs/README.md) links to development plans, the initial development record, and research.
