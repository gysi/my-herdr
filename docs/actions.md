# Action reference

Detailed behavior, setup, and limitations for the actions summarized in the [project README](../README.md#actions). For installation and keybindings, see the [README](../README.md#install); for the plugin log, see its [Troubleshooting](../README.md#troubleshooting) section.

- [`attention-next`](#attention-next)
- [`attention-prev`](#attention-prev)
- [`fork-tab`](#fork-tab)
- [`fork-tab-ask`](#fork-tab-ask)
- [`pane-to-tab`](#pane-to-tab)
- [`ping`](#ping)

## `attention-next`

One key to reach any agent. It reads `herdr agent list` and works from two orderings:

- **The local sidebar's agent order** — grouped follows workspace, tab, and pane layout order; priority puts blocked, done, working, idle, and unknown agents in that order, with the newest state change first within each status. Normal cycling moves to the row below the focused agent and wraps from the bottom to the top.
- **Urgency**, which decides when to leave the ring: `blocked` (waiting for input) before `done` (finished, nobody has looked yet), longest-waiting first.

Each unvisited waiting state stays urgent until you visit it or herdr stops reporting it as waiting. If several answers arrive, successive presses visit each before normal cycling resumes. A visited blocker cannot displace an unread answer or trap navigation. A fresh answer or input request in that pane becomes urgent again when its status or state-change sequence changes, even if its intervening work happened entirely between keypresses. Urgency uses the oldest pending agent even when the sidebar sorts newest first. It works across workspaces and never targets the pane you pressed the key in.

The plugin polls once per keypress; herdr detects whether agents are blocked or finished. Herdr's `done` means finished and unread: viewing the pane clears it to `idle`. A blocked agent keeps that status until its request is resolved, so the plugin remembers which request you visited.

This differs from herdr's built-in `open_notification_target`, which jumps to whichever agent the *currently visible* toast belongs to: that needs toasts enabled and is gone once the toast is. `attention-next` also works with `[ui.toast] delivery = "off"` — with sound left on, a sound tells you somebody needs you and the action takes you there.

## `attention-prev`

Move to the row above the focused agent, wrapping from the top to the bottom. This action always follows sidebar order, even when another agent newly needs attention. For a list `A → B → C → D`, previous from C selects B. It reverses list order, rather than retracing visited agents.

### Shared navigation state and sidebar matching

Both actions start from the currently focused agent, including after mouse selection. From a non-agent pane, they use the last successful attention jump; without one, next starts at the top and previous at the bottom. They share `attention-next.json` in the plugin state directory and save visits only after a successful jump. Both the source and destination count as visited; other pending agents retain their urgency, including after a previous jump. Priority order can change as agents work or finish, so the neighboring rows can change between presses.

Clicking a pane and invoking either action there also counts as a visit. A blocked pane clicked and left entirely between keypresses may still get one urgency visit, since the plugin does not observe those focus changes. On upgrade, existing waiting agents are reconsidered once because older saved state cannot identify visits. Missing or unwritable state keeps navigation usable, but visits cannot be remembered between presses.

**Sidebar matching:** intended for one local client using herdr 0.9.1's standard grouped/priority view. Each press reads herdr's saved session-specific sidebar preference, falling back to `[ui] agent_panel_sort` in its config, then grouped order. The config fallback supports a quoted scalar under `[ui]` or a root `ui.agent_panel_sort` assignment; inline tables are not supported. Missing or unreadable files use the fallback, and malformed or unsupported sort values are logged. Changing the sidebar sort toggle takes effect on the next press.

This relies on herdr's internal preference file format because its public API does not expose the client's current sort choice. Remote sidebars, clients with different settings, and custom agent-view overrides are not guaranteed to match. User configuration and preferences are only read.

## `fork-tab`

For the moment you want to try something without losing where you are. The Claude Code, Codex or OpenCode session in the focused pane is detected automatically and forked into a new tab: the fork starts with the saved conversation and its own session ID, and the source session carries on untouched.

The new tab opens in the source workspace and the agent's foreground directory, falling back to the pane's directory. OpenCode uses its session's directory instead. You land in it straight away and watch the fork come up. A fork that fails to start closes its tab and puts you back where you pressed the key.

The tab keeps herdr's generic name, for the same reason [`pane-to-tab`](#pane-to-tab) does. To name it, use [`fork-tab-ask`](#fork-tab-ask).

### Setup and logging

Install the matching herdr integration (`herdr integration install claude`, `herdr integration install codex`, or `herdr integration install opencode`), then start or resume the session in the pane. All three agents need a nonempty session reference of kind `id` from herdr. Missing or conflicting session metadata is refused before creating a tab or opening a naming popup. The plugin never installs integrations.

For alternate configuration directories, the plugin forwards `CLAUDE_CONFIG_DIR` for Claude and `CODEX_HOME` for Codex when set in the action's environment, inherited from the herdr server. Overrides set only in the source pane's shell are not discovered.

Every fork logs its source pane, agent kind and session ID (`fork: <pane> runs <agent> session <id> …`). Claude also logs the result of its saved-conversation check. See [Troubleshooting](../README.md#troubleshooting) for the plugin log command.

### Codex

Codex runs `codex fork <session-id>`. Codex itself loads and validates the saved conversation; the plugin does not search its transcripts or check its storage beforehand. A missing conversation can therefore leave the new tab visible until startup times out and cleanup closes it.

### OpenCode

For OpenCode, install the current herdr integration and restart the full-screen TUI so it reports the session selected in that pane. Mini and headless clients are not supported by this integration.

OpenCode saves an independent fork through `opencode api`, then the new pane runs `opencode --session <fork-id>`. The plugin uses OpenCode's own service discovery and authentication; it never reads the database or copies transcript files. Forking takes place before the new tab opens, and a requested name titles only the new session, not the source.

OpenCode support targets the normal shared background service under the herdr server's environment. Source-pane `--server`, `--standalone`, shell-only environment overrides, and private-server defaults are not discovered or supported. The API and the new TUI must resolve the same service and session storage. Connection failures stop the action rather than falling back to resuming the source session. No password or inline config is added to logged tab arguments.

If OpenCode saves a fork but naming or startup fails, the saved fork is kept. The error notification names it and tells you how to resume it with `opencode --session <fork-id>`; run that in the project directory. The ID is also logged as `fork: saved OpenCode session <fork-id> from <source-id> …`. Failed startup still closes the new tab and restores focus. API mutations are never automatically retried: a timeout can mean the fork was saved even when no response arrived, in which case check OpenCode before trying again.

### Claude Code

For Claude, the fork resumes what Claude has saved under the id herdr holds for the pane. A session with nothing saved yet — one that has not had its first message — cannot be forked, and the action says so at once instead of opening a tab for a fork that cannot start.

herdr learns a session's id when Claude **starts** in the pane, so the session has to run there: `claude`, `claude -c`, or `claude -r` and pick it from the list (run it from the project's directory, or choose "all projects"). A **background session** cannot be forked. Sessions started with `claude --bg`, opened through `claude agents`, or switched to inside Claude run in Claude's own background service, detached from any pane: herdr still shows their status, but never learns their id. While such a session is running, `claude -r` only offers to *attach* to it, which leaves it in the background. Stop it first (`claude stop <id>`, or from `claude agents`); the conversation is kept, and `claude -r` then resumes it in the pane, where it can be forked.

A pane in that state is refused, or, if herdr still holds the id the pane started with, the fork starts from that session instead of the one on screen. Every fork writes the id it used to the plugin log (`fork: <pane> runs claude session <id> …`), so a mismatch with `/status` in that Claude is easy to spot.

Right after a rewind, the fork may also start from the discarded branch: Claude has no way to resume at a particular message.

## `fork-tab-ask`

`fork-tab` with a name, the way herdr's own new tab asks for one. A small popup asks for the tab name: **Enter** forks, **Esc** cancels, and an empty name forks with herdr's default name. The name labels the tab for every supported agent. For Claude it also becomes the saved session's name, so it is what `claude --resume` lists. For Codex it names only the herdr tab; no session name or initial prompt is sent to Codex. For OpenCode it also becomes the forked session's title through its API.

The pane is checked before the popup opens, so a pane that cannot be forked is reported straight away rather than after you have typed a name. Once you press Enter the popup closes at once and herdr runs `fork-tab` with that name, so you watch the fork come up in the new tab exactly as with `fork-tab`, and its output lands in the plugin log like every other action's.

herdr actions take no arguments, so the name travels as a short-lived `fork-request.json` in the plugin state directory, alongside the source pane and timestamp. It is used once, ignored after ten seconds, and removed as it is read. The fork action re-reads the pane's agent and session when it executes.

A named tab is left alone by tab-renaming plugins: that is what a name you chose should mean.

## `pane-to-tab`

For the moment a split has outgrown its share of the screen. The focused pane moves into a tab of its own and takes its running process with it — the agent keeps going and lands full width.

The new tab keeps herdr's generic name on purpose: a plugin-set label looks like a manual rename to tab-renaming plugins, which then leave it alone forever. If the pane is already the only one in its tab, nothing happens and it says so, rather than destroying the tab and rebuilding it for the same single pane.

## `ping`

Write the plugin environment and invocation context to the plugin log without changing anything. Use it to verify an installation, then read the output with:

```bash
herdr plugin log list --plugin my-herdr --limit 5
```
