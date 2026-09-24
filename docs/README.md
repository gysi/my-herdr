# Development documentation

Start with [AGENTS.md](../AGENTS.md) and the plan relevant to the requested task. The
[project README](../README.md) and code describe current behavior. Active plans describe intended
work; completed plans preserve the reasoning behind past development.

## Local checks

Plugin users need only Python 3.9+ and herdr. Development checks use Python 3.11+ (for the
standard-library TOML parser), Make, and [mise](https://mise.jdx.dev/installing-mise.html).
Mise manages the Ruff version pinned in `mise.toml`; it does not manage the plugin's Python.

After reviewing the checkout's `mise.toml`, run:

```bash
mise trust
mise install
make check
```

`make check` runs Ruff, syntax checks, manifest validation, and tests. `make lint` runs only
Ruff. Both use `mise exec`, so shell activation is optional. To use an already installed Ruff,
run `make check RUFF=/path/to/ruff` with the version specified in `mise.toml`.

The lint rules catch basic Python errors, missing public function/method docstrings, and missing
parameter entries in existing Google-style `Args:` sections, including `*args` and `**kwargs`.
Descriptive unittest methods do not need docstrings. Review still checks missing `Args:` sections,
private helpers, return values, errors, and the accuracy of the descriptions. Ruff does not format
or rewrite files during checks. See [Ruff's D417 rule](https://docs.astral.sh/ruff/rules/undocumented-param/)
for its parameter-checking limits.

## Code organization

`myherdr/attention`, `forking`, `pane_to_tab`, and `diagnostics` each own their entrypoints
and implementation. Common herdr access, invocation context, and errors live in `shared`.
`cli.py` handles dispatch and error reporting; `entrypoints.py` maps public action/pane IDs
to feature modules without importing them. The manifest checker validates those mappings.

Features may import their own modules and `shared`. Shared code must not import features,
and features must not import the dispatcher or each other. Keep `__init__.py` files minimal.
Add shared abstractions for concrete reuse, and keep small features in one implementation file.
The terminal line editor belongs to forking; common herdr operations belong to the CLI wrapper.

Tests mirror feature ownership. Common fixtures, the mock CLI, and `tests/support.py` stay
central. Run all tests with `python3 -m unittest discover -s tests -t .`, or a feature with
`python3 -m unittest discover -s tests/attention -t .`. Package imports use `tests.*` so
feature test directories cannot shadow runtime packages.

See [AGENTS.md](../AGENTS.md#layout) for the layout and entrypoint-adding checklist.

## Active plans

None.

## Completed plans

- `APEND`: [Preserve pending attention until visited](plans/2026-09-24-APEND-pending-attention.md).
  Unvisited waiting states retain urgency; all 296 tests and local checks passed.
- `MOD`: [Feature packages](plans/2026-09-24-MOD-feature-packages.md).
  Feature packages and grouped tests are complete; all 283 tests and local checks passed.
- `ATTN`: [Sidebar attention navigation](plans/2026-09-24-ATTN-sidebar-attention-navigation.md).
  All 265 automated tests passed; the user confirmed navigation in grouped and priority views.
- `CFORK`: [Codex support for fork actions](plans/2026-09-23-CFORK-codex-fork-support.md).
  Automated checks passed; the user confirmed successful live smoke testing.
- [Initial development](plans/initial-development.md): the plugin's initial design, implementation
  phases, verification record, and [original recommendations](plans/initial-development.md#original-recommendations).

## Research

- [Official herdr documentation](research/official-docs.md): the herdr 0.9.1 plugin contract and
  locally verified CLI behavior. If the live CLI disagrees, trust it and update the research.
- [Community plugins](research/community-plugins.md): examples, patterns, and pitfalls; not the
  specification for this plugin.

Both research notes identify their original snapshot date. Targeted corrections do not move that
date; only a full re-survey or contract review does. Historical recommendations stay in the
completed initial development plan; current plugin behavior belongs in the README and code.

## Plan conventions

Create a plan for a substantial feature or a fix requiring investigation or design decisions.
Small, straightforward fixes do not need one. Filenames have three parts: creation date, short
slug, and descriptive name: `plans/YYYY-MM-DD-slug-descriptive-name.md`. For example,
`2026-09-23-CFORK-codex-fork-support.md` uses the slug `CFORK`. Link each plan from this index.
The initial development record is the naming exception and needs no slug.

Choose a short, meaningful slug using uppercase letters and digits, starting with a letter. Keep
hyphens in the descriptive name so the slug stays a single filename component. Slugs must be
unique across all plans, including completed and dropped ones; keep them stable and never reuse
them. Record the slug in the plan and its index entry.

Each plan contains:

- A descriptive title, `Slug: <slug>`, and status: **Planned**, **In progress**, **Completed**, or **Dropped**.
- An optional GitHub issue link. Issues can host discussion and tracking, but the plan must be
  understandable without access to GitHub.
- The problem and intended behavior, important design decisions, and an implementation and
  verification checklist.

Update an active plan as decisions settle so it describes the agreed solution. Tick tasks only
when completed, record discovered follow-ups, and keep this index's status in sync. Manual checks
stay unchecked until performed with the user.

When work is complete, mark the plan **Completed** and move its index entry to Completed plans;
keep the file at the same path. Preserve it as a historical design record rather than rewriting it
for later releases. For abandoned work, mark it **Dropped**, explain why, and move its link to a
Dropped plans section when one is needed. Neither completed nor dropped plans are current task
queues.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). For work associated
with a plan, use its uppercase slug as the scope in parentheses: `<type>(<slug>): <description>`. The type
still describes the individual change, so several commits can reference the same plan:

```text
feat(CFORK): support Codex sessions
fix(CFORK): restore focus after startup failure
test(CFORK): cover named forks
```

This is the repository's convention for connecting plans to commits. Changes without a related
plan omit the scope, for example `docs: fix installation example`; do not create a plan just to
supply a scope. Use `feat` for features and `fix` for fixes, with types such as `docs`, `test`, and
`refactor` for other changes. No plan-reference footer is needed.

To find a plan's commits:

```bash
git log --fixed-strings --grep='(CFORK):'
```

## Future ideas

These are possibilities, not implementation commitments. Give an idea its own plan when it becomes
concrete.

- `fork-pane`: fork into a split pane instead of a tab (right/down variants).
- Shell entry point (`bin/cfork` or `my-herdr fork <name> [prompt]`) so a `cfork`-style shell workflow
  can use the plugin code.
- `pane-to-tab (ask)`: popup asks for the new tab's name.
- `attention-pick`: popup listing every waiting agent (state icon, workspace/tab, title), pick with
  `1`-`9`, then focus. Shares the popup machinery with `fork-tab-ask`. A popup does not take tiled
  focus, so focusing from inside it sticks when it closes (seen with `fork-tab-ask`).
- `attention-status`: sidebar/status line token or a `notification show` summary of how many agents
  are blocked vs finished-unread.
- `setup-keys` action that idempotently adds chosen keybindings (marker-guarded), opt-in only.
- Forking agents beyond Claude Code and Codex.
