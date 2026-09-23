# Development documentation

Start with [AGENTS.md](../AGENTS.md) and the plan relevant to the requested task. The
[project README](../README.md) and code describe current behavior. Active plans describe intended
work; completed plans preserve the reasoning behind past development.

## Active plans

| Slug | Plan | Status |
|---|---|---|
| `CFORK` | [Codex support for fork actions](plans/2026-09-23-CFORK-codex-fork-support.md) | Planned |

## Completed plans

- [Initial development](plans/initial-development.md): the plugin's initial design, implementation
  phases, and verification record.

## Research

- [Official herdr documentation](research/official-docs.md): the herdr 0.9.1 plugin contract and
  locally verified CLI behavior. If the live CLI disagrees, trust it and update the research.
- [Community plugins](research/community-plugins.md): examples, patterns, and pitfalls; not the
  specification for this plugin.

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
- Forking agents beyond Claude Code and the planned Codex support.
