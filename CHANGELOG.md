# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.3] - 2026-09-24

### Fixed

- Unvisited finished answers and input requests retain their urgency across attention jumps.
  `attention-next` visits pending states before resuming sidebar cycling; an already-visited
  blocker cannot displace an unread answer. `attention-prev` preserves pending work in other panes.
- Saved attention state records visits and automatically reconsiders existing waiting agents
  once on upgrade. Navigation logs include the source pane, selection reason, and pending states.

## [0.5.2] - 2026-09-24

### Fixed

- `attention-next` recognizes a fresh answer or input request in a pane that was also waiting
  at the previous navigation action, including when the intervening work was never observed.
  Unchanged waiting states still allow normal cycling. Existing saved navigation state is
  upgraded automatically, reconsidering waiting agents once on the first jump.

## [0.5.1] - 2026-09-24

### Added

- `my-herdr.attention-prev`: move up the local sidebar's agent list, wrapping and ignoring
  urgency interruptions. Shares navigation state with `attention-next`.

### Changed

- Normal `attention-next` cycling follows the sidebar's grouped or priority order from the
  currently focused agent. Its urgency-interruption behavior is unchanged.
- Attention actions read the local session's saved sidebar sort preference on each invocation,
  using herdr's client socket path and falling back to herdr configuration and then grouped order.
  Exact matching is limited to a local client using the standard grouped/priority view.
  Action logs include the selected sort mode for troubleshooting.

## [0.4.0] - 2026-09-23

### Added

- Codex support in `fork-tab` and `fork-tab-ask`, detected automatically alongside Claude Code.
  Codex forks open in the source workspace and directory, with immediate focus and the same
  failure cleanup. `CODEX_HOME` is forwarded when set in the action environment. A requested
  name labels the herdr tab only; Codex validates its saved conversation during startup.

### Changed

- Both fork actions reject unusable session references and conflicting agent metadata before
  opening a tab or popup, with agent-specific integration guidance for missing session IDs.
- Fork action titles and the naming popup use wording that applies to either agent.

## [0.3.0] - 2026-09-21

### Added

- `my-herdr.fork-tab` action: forks the Claude Code session in the focused pane
  into a new tab, conversation included, leaving the original session running.
  The tab opens in the same workspace and directory and is focused immediately,
  so the fork is watched coming up rather than waited out on the old pane. A
  fork that does not start closes its tab again and restores focus. Requires
  `herdr integration install claude`, which is how herdr learns a session's id;
  without it the action says so and changes nothing. A session with no saved
  conversation yet (no first message) is refused at once, before any tab is
  created. Every fork logs the pane and the session id it used. Background
  Claude sessions (`claude --bg`, `claude agents`) cannot be forked, because
  herdr cannot link them to a pane; the README shows how to bring one back
  into a pane first.
- `my-herdr.fork-tab-ask` action: the same fork, asking for the tab's name
  first in a small popup (Enter forks, Esc cancels, an empty name keeps herdr's
  default). The name labels the tab and names the Claude session. The popup
  closes as soon as the name is entered and herdr runs `fork-tab` with it, so
  the fork comes up in the new tab and is logged like any other action.

## [0.2.0] - 2026-09-21

### Added

- `my-herdr.pane-to-tab` action: moves the focused pane, and the process
  running in it, into a new tab in the same workspace. The new tab is left
  unnamed so tab-renaming plugins still manage it. A pane that is already alone
  in its tab is reported instead of moved, and a move herdr declines (a zoomed
  tab makes it a silent no-op) is reported rather than assumed to have worked.

## [0.1.0] - 2026-09-21

### Added

- Plugin skeleton: `herdr-plugin.toml`, the `bin/my-herdr` dispatcher and the
  `myherdr` package (herdr CLI wrapper, invocation context, error type).
- `my-herdr.ping` action: writes the plugin environment and invocation context
  to the plugin log. Read-only, for verifying an install.
- `my-herdr.attention-next` action: focuses the agent that is waiting longest,
  `blocked` before `done`, across workspaces, skipping the pane the key was
  pressed in. Otherwise it walks a ring of every agent in workspace, tab and
  pane order, so a single binding reaches every agent. An agent that starts
  waiting takes the next press; one that merely keeps waiting does not, so a
  permanently blocked agent cannot make the others unreachable.
- Test harness: `unittest` suite with a fake `herdr` CLI and manifest
  validation, all run locally by `make check`.

[Unreleased]: https://github.com/gysi/my-herdr/compare/v0.5.3...HEAD
[0.5.3]: https://github.com/gysi/my-herdr/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/gysi/my-herdr/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/gysi/my-herdr/compare/v0.4.0...v0.5.1
[0.4.0]: https://github.com/gysi/my-herdr/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/gysi/my-herdr/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/gysi/my-herdr/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/gysi/my-herdr/releases/tag/v0.1.0
