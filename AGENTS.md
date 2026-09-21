# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, …) working in this repository.

## What this project is

`my-herdr` is a **herdr plugin** that bundles small, independent customizations for
[herdr](https://herdr.dev), the terminal workspace manager for AI coding agents. Each customization
is a separate plugin **action** that users bind to a key in their own herdr config.

## Read before writing code

1. `docs/PLAN.md`: scope, design decisions, and the ordered task list. Pick up the first unchecked task.
2. `docs/research/official-docs.md`: herdr plugin contract (manifest, env vars, popups,
   keybindings, CLI JSON shapes) for herdr 0.9.1. **Authoritative.**
3. `docs/research/community-plugins.md`: how existing plugins are built, with recipes, a helper
   library sketch, testing approach, and a list of pitfalls. Use it for patterns, not as the spec.

If the research and the live `herdr` CLI disagree, trust the CLI, then update the research note.

## Tech stack and constraints

- **Python 3, standard library only.** No pip packages, no venv, no build step: herdr runs
  `["python3", …]` straight from the checkout. Plugin code must run on **Python 3.9+** (no `tomllib`,
  no `match`, no `X | Y` annotations); only `tests/` may assume newer. Don't add runtime dependencies
  (including `jq`, `fzf`, `gum`) without asking.
- **No CI and no linter**. Everything runs locally through `make check`.
  Don't add `.github/workflows/`, `ruff`, or any other tool without asking.
- Target the **current stable herdr, 0.9.1**; `min_herdr_version` matches it. Older releases are not
  supported: `agent focus` and `pane move --focus` only move the attached client from 0.9.1 on. A
  `min_herdr_version` above the running herdr is a hard load failure, so raise it only when the
  target moves.
- Linux first; don't break macOS on purpose.
- Every herdr call goes through the wrapper in `myherdr/herdr.py` (`run()` / `run_json()`), which
  uses `HERDR_BIN_PATH` and argv lists, so tests can mock it and nothing needs shell quoting.

## Key facts that are easy to get wrong

- **Actions run headless**: no TTY, cwd = plugin root, stdout/stderr go to
  `herdr plugin log list --plugin my-herdr`. Interactive input needs a **popup plugin pane**
  (`[[panes]] placement = "popup"`) opened by the action with `herdr plugin pane open --env ...`.
- **Popups have no `HERDR_PANE_ID`.** Pass the source pane, session id, and cwd via `--env`. Only one
  popup can be open at a time (`ui_busy`). Use blocking `read`, never `read -t`.
- In pane commands, reference scripts via `$HERDR_PLUGIN_ROOT`, not relative paths.
- Manifest commands are **argv arrays, no shell**. Action/pane ids must not contain dots.
- Keybindings **cannot** be declared in the manifest. Document `[[keys.command]]` blocks
  (`type = "plugin_action"`) in the README.
- `pane move --new-tab` takes `--label` (not `--tab-label`). Check `.result.move_result.changed`.
- Claude session id: `herdr agent get <pane>` → `.result.agent.agent_session.value` (needs
  `herdr integration install claude`).
- Toast failures with `herdr notification show`, because otherwise they're invisible.

## Layout (target)

```
herdr-plugin.toml        manifest
bin/my-herdr             executable dispatcher (#!/usr/bin/env python3)
myherdr/herdr.py         herdr CLI wrapper: run(), run_json(), notify(), focused_pane(), …
myherdr/context.py       env + HERDR_PLUGIN_CONTEXT_JSON
myherdr/errors.py        MyHerdrError
myherdr/actions/<id>.py  one module per action, each with main(args)
myherdr/panes/<id>.py    one module per popup/pane entrypoint
myherdr/cli.py           dispatcher: routes <action> / pane <entrypoint> to a module
tests/                   test_*.py (unittest), support.py, mocks/herdr, fixtures/, check_manifest.py
Makefile                 check / test / syntax / manifest / link / logs
docs/                    PLAN.md, research/
```

**Adding an action** = `[[actions]]` block + `myherdr/actions/<id>.py` with `main(args)` + test +
README row. `tests/check_manifest.py` fails if the block and the module disagree.

## Commands

```bash
make check                                 # syntax + manifest + tests: run before every commit
make test                                  # python3 -m unittest discover -s tests
python3 -m unittest discover -s tests -v   # same, verbose
python3 tests/check_manifest.py            # offline manifest validation
herdr plugin link .                        # authoritative manifest validation + local install
herdr plugin action invoke my-herdr.<action>
herdr plugin log list --plugin my-herdr    # the only place action output goes
```

`make syntax` must `py_compile` `bin/my-herdr` and `tests/mocks/herdr` by name: they have no `.py`
extension, so `compileall` skips them even when named explicitly.

Both of those files need their **executable bit** kept in git; the wrapper reports a non-executable
`HERDR_BIN_PATH` as an error, but the tests spawn them directly.

## Working rules

- **Never `git commit` or `git push`.** Stage nothing unless asked. When a change is ready, propose a
  commit message draft (Conventional Commits style, e.g. `feat: add pane-to-tab action`) and let the
  user commit.
- **Don't touch the user's herdr setup without asking.** That covers `~/.config/herdr/config.toml`
  (keybindings), `herdr plugin link/install/enable`, `herdr server reload-config`, and
  creating/closing/moving real tabs or panes. Unit tests must use the mock, never a live herdr.
- Manual smoke tests against the live herdr are done **with the user**, one action at a time.
- Tick checkboxes in `docs/PLAN.md` as tasks complete; add discovered follow-ups there.
- Bump `version` in `herdr-plugin.toml` and add a `CHANGELOG.md` entry for every user-visible change.
- The repo is **public** (github.com/gysi/my-herdr). Never commit secrets, session ids, or personal
  paths in examples. Use placeholders.
- Copied code from other plugins: MIT only, with a `# Adapted from <repo>/<path> (MIT)` comment.
