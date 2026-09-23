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
| `my-herdr.fork-tab` | Fork the focused pane's Claude Code or Codex session into a new tab |
| `my-herdr.fork-tab-ask` | The same, asking for the new tab's name first |
| `my-herdr.pane-to-tab` | Move the focused pane, and the process in it, into a new tab |
| `my-herdr.ping` | Write the plugin environment to the plugin log, to verify an install |

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

### `fork-tab`

For the moment you want to try something without losing where you are. The Claude Code or Codex
session in the focused pane is detected automatically and forked into a new tab: the fork starts
with the saved conversation and its own session ID, and the source session carries on untouched.

The new tab opens in the source workspace and the agent's foreground directory, falling back to
the pane's directory. You land in it straight away and watch the fork come up. A fork that fails
to start closes its tab and puts you back where you pressed the key.

The tab keeps herdr's generic name, for the same reason `pane-to-tab` does. To name it, use
`fork-tab-ask`.

Install the matching herdr integration (`herdr integration install claude` or
`herdr integration install codex`), then start or resume the session in the pane. Both agents need
a nonempty session reference of kind `id` from herdr. Missing or conflicting session metadata is
refused before creating a tab or opening a naming popup. The plugin never installs integrations.

Codex runs `codex fork <session-id>`. Codex itself loads and validates the saved conversation;
the plugin does not search its transcripts or check its storage beforehand. A missing conversation
can therefore leave the new tab visible until startup times out and cleanup closes it.

For alternate configuration directories, the plugin forwards `CLAUDE_CONFIG_DIR` for Claude and
`CODEX_HOME` for Codex when set in the action's environment, inherited from the herdr server.
Overrides set only in the source pane's shell are not discovered.

Every fork logs its source pane, agent kind and session ID (`fork: <pane> runs <agent> session
<id> …`). Claude also logs the result of its saved-conversation check.

For Claude, the fork resumes what Claude has saved under the id herdr holds for the pane. A
session with nothing saved yet — one that has not had its first message — cannot be forked, and the
action says so at once instead of opening a tab for a fork that cannot start.

herdr learns a session's id when Claude **starts** in the pane, so the session has to run there:
`claude`, `claude -c`, or `claude -r` and pick it from the list (run it from the project's
directory, or choose "all projects"). A **background session** cannot be forked. Sessions started
with `claude --bg`, opened through `claude agents`, or switched to inside Claude run in Claude's own
background service, detached from any pane: herdr still shows their status, but never learns their
id. While such a session is running, `claude -r` only offers to *attach* to it, which leaves it in
the background. Stop it first (`claude stop <id>`, or from `claude agents`); the conversation is
kept, and `claude -r` then resumes it in the pane, where it can be forked.

A pane in that state is refused, or, if herdr still holds the id the pane started with, the fork
starts from that session instead of the one on screen. Every fork writes the id it used to the
plugin log (`fork: <pane> runs claude session <id> …`), so a mismatch with `/status` in that Claude
is easy to spot.

Right after a rewind, the fork may also start from the discarded branch: Claude has no way to resume
at a particular message.

### `fork-tab-ask`

`fork-tab` with a name, the way herdr's own new tab asks for one. A small popup asks for the tab
name: **Enter** forks, **Esc** cancels, and an empty name forks with herdr's default name. The name
labels the tab for either agent. For Claude it also becomes the saved session's name, so it is
what `claude --resume` lists. For Codex it names only the herdr tab; no session name or initial
prompt is sent to Codex.

The pane is checked before the popup opens, so a pane that cannot be forked is reported straight
away rather than after you have typed a name. Once you press Enter the popup closes at once and
herdr runs `fork-tab` with that name, so you watch the fork come up in the new tab exactly as with
`fork-tab`, and its output lands in the plugin log like every other action's.

herdr actions take no arguments, so the name travels as a short-lived `fork-request.json` in the
plugin state directory, alongside the source pane and timestamp. It is used once, ignored after
ten seconds, and removed as it is read. The fork action re-reads the pane's agent and session
when it executes.

A named tab is left alone by tab-renaming plugins: that is what a name you chose should mean.

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
- **For fork actions:** Claude Code or Codex CLI (with `codex fork` support), available in the
  new pane's shell, and the matching herdr integration installed. Start or resume the source
  session in its pane after installing the integration.

## Troubleshooting

Actions run headless, so they have no terminal to print to. Everything they write goes to the plugin
log:

```bash
herdr plugin log list --plugin my-herdr --limit 5
```

`my-herdr.ping` writes the whole plugin environment there and changes nothing, so it is the quickest
way to confirm an install is wired up.

A failed action also sends a notification, which is invisible if you have `[ui.toast] delivery =
"off"`; the sound still plays, and the log has the detail.

## For contributors / agents

Start with [`AGENTS.md`](AGENTS.md). The [documentation index](docs/README.md) links to development
plans, the initial development record, and research.
