# Feature packages

Slug: MOD

Status: **Completed** — all 283 tests and local checks passed.

## Intended behavior

Group attention, forking, pane-to-tab, and diagnostics with their own entrypoints and
supporting code. Keep CLI dispatch at the application boundary and common herdr access,
context, and errors in `shared`. Public action/pane IDs, manifest commands, state formats,
notifications, and navigation/fork behavior remain unchanged.

## Design

- Feature packages depend on themselves and `shared`, never other features or the dispatcher.
- A static entrypoint registry maps public IDs to modules exposing `main(args)`. Dispatch
  imports only the chosen module; help and offline manifest validation use the same registry.
- Validation checks manifest/registry agreement in both directions and target module existence.
- Keep common herdr operations in `shared/herdr.py`, including the shell-readiness helper.
  The terminal line editor belongs to forking until another feature needs it.
- Group tests by feature; retain central fixtures, the mock CLI, and test support. Explicit
  `tests` package imports and unittest's top-level directory prevent package-name collisions.
- This is an internal refactor with no version bump or user-facing changelog entry.

## Implementation and verification

- [x] Move runtime modules into feature/shared packages and update imports.
- [x] Introduce the registry and adapt dispatch/help/manifest validation.
- [x] Group tests and preserve discovery of all 274 existing tests.
- [x] Add registry, lazy-import, and dependency-boundary regression coverage.
- [x] Update repository layout, action-adding instructions, and development documentation.
- [x] Run `make check` and review the diff for behavior changes and stale paths.

Review confirmed that all 16 moved implementation modules retain the same executable syntax
after accounting for imports and local renames. All runtime files parse with Python 3.9 syntax,
and the dispatcher and mock CLI retain their executable permissions.

Live herdr mutations are outside this refactor's automated verification; all action tests use mocks.
