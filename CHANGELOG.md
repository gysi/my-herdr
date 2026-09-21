# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/gysi/my-herdr/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/gysi/my-herdr/releases/tag/v0.1.0
