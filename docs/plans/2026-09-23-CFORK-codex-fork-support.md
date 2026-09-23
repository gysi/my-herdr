# Codex support for fork actions

Slug: CFORK
Status: Completed

Implementation and automated verification are complete (`make check`: 239 tests passed).
Live smoke testing succeeded, as confirmed by the user.

## Problem and intended behavior

`fork-tab` and `fork-tab-ask` detect Claude Code or Codex automatically, retaining the existing
action IDs and keybindings. A Codex
fork opens in a new tab with the source conversation and its own session ID, leaving the source
session running.

The naming popup labels the herdr tab for either agent. Claude also receives the name for its
saved conversation; Codex receives no session-name argument because its fork CLI has no equivalent
flag. An empty name keeps herdr's default tab naming.

Codex itself loads and validates its saved conversation. This release adds no Codex transcript
searches, storage prechecks, or background-session workarounds. Revisit those only if actual use
reveals a problem. A missing conversation may leave the new tab visible until startup times out
and the existing cleanup runs.

## Design decisions

### Shared orchestration and agent-specific behavior

Keep `myherdr/fork.py` responsible for the shared lifecycle: read the source, create and focus the
tab, wait for its shell, launch the agent, clear its temporary name, and clean up failures.

Add `myherdr/fork_agents.py` for agent-specific behavior, using ordinary functions and explicit
Claude/Codex branches. Move Claude's saved-conversation check and config-directory helper there.
This module validates session metadata, builds agent arguments, and selects environment variables
to forward. No backend class hierarchy or extensibility framework is needed for two agents.

Replace `claude_agent()` with `forkable_agent(pane_id, env=None)` in the shared flow. Both actions
use it, including validation before opening the naming popup. Preserve the
`fork_into_new_tab(pane_id, name=None, env=None)` interface and its tab/pane return shape.

Support only `claude` and `codex`. Require a nonempty session reference of kind `id`; reject a
session whose reported agent explicitly conflicts with the pane's agent. Missing session IDs
produce agent-specific guidance to install the corresponding herdr integration and start or
resume the session in the pane. Never install integrations automatically.

### Launch, environment, and naming

Preserve Claude's launch arguments and saved-transcript precheck. Launch Codex through the herdr
wrapper with an argv list equivalent to:

```text
herdr agent start <temporary-name> --kind codex --pane <new-pane> --timeout 60000 -- fork <session-id>
```

Use the source workspace and `foreground_cwd`, falling back to `cwd`, as today. Forward
`CLAUDE_CONFIG_DIR` for Claude and `CODEX_HOME` for Codex when present in the action environment.
Do not inspect source-process environments; document that shell-only overrides are not discovered.

A supplied name labels the new tab for either agent. Claude also receives its existing `-n`
argument; Codex receives no name argument or initial prompt. Use neutral popup wording:
“Fork this session into a new tab.” Keep Enter, cancellation, and immediate popup dismissal.

Keep the popup handoff unchanged: store only the source pane, requested name, and existing
timestamp. Re-read the agent and session when the fork action executes. Do not pin a session in
the request or start work outside herdr's action lifecycle.

### Failures and diagnostics

Retain the existing startup timeout, failure notification, tab cleanup, and focus restoration.
Log the source pane, agent kind, and session ID without implying that Codex's saved conversation
was checked beforehand. Claude's existing saved-conversation diagnostics remain available.

No new action IDs, dependencies, configuration settings, or herdr minimum-version changes are
needed. Runtime code remains compatible with Python 3.9 and uses only the standard library.

## Implementation and verification

- [x] Extract agent-specific behavior into `fork_agents.py` and introduce the shared
      `forkable_agent()` validation path. Preserve existing Claude behavior.
- [x] Add Codex launch arguments, agent-specific environment forwarding, and diagnostics.
- [x] Route both fork actions through shared validation and update popup wording while preserving
      the request format and lifecycle.
- [x] Preserve Claude test coverage and move agent-specific helper tests alongside the new module.
      Add Codex named/unnamed cases, exact argv assertions, `CODEX_HOME` forwarding, and checks
      that Claude arguments and transcript checks are not used for Codex.
- [x] Test unsupported agents, missing/unusable session references, and conflicting agent
      metadata. Refuse these before creating a tab or opening a popup.
- [x] Exercise startup failure and shell-timeout cleanup for both agents.
- [x] Add mock-backed end-to-end coverage for Codex direct forks and the named-popup handoff.
      Isolate tests from inherited `CODEX_HOME` and `CLAUDE_CONFIG_DIR`.
- [x] Update manifest action descriptions, README requirements and naming behavior, contributor
      guidance, and research notes to cover both agents. Document the Codex validation limitation.
- [x] Bump the plugin from `0.3.0` to `0.4.0` and add a changelog entry, retaining herdr `0.9.1` as
      the minimum. Run `make check`.
- [x] With the user, smoke-test Codex `fork-tab`: inherited conversation, distinct session ID,
      unchanged source session, correct workspace/directory, immediate focus, and cleared
      temporary agent name. Verify that the fork can itself be forked again.
- [x] With the user, separately smoke-test Codex `fork-tab-ask`: popup dismissal, named and unnamed
      tabs, cancellation, and tab-only naming. Confirm Claude forks still behave as documented.

All automated tests use the mock herdr. Manual verification is recorded from the user's report.
Suggested commit: `feat(CFORK): support Codex in fork actions`.

## Evidence and references

- The installed herdr `0.9.1` CLI lists `codex` for both `agent start --kind` and
  `integration install`. Read-only inspection confirmed Codex panes with `agent_session.kind`
  equal to `id` and source `herdr:codex`; no personal session IDs are recorded here.
- The installed `codex fork --help` accepts a session UUID and offers no session-name flag.
- [Official Codex CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli#codex-fork)
  documents forking a specified session into a new chat while preserving the original transcript.
- [herdr contract research](../research/official-docs.md) and
  [initial development plan](initial-development.md) provide the shared lifecycle context.
