# my-herdr: implementation plan

Working document for whoever implements the next piece, human or agent. Work top to bottom, tick
boxes as you go, and add follow-ups at the end. Background: see `AGENTS.md` and `docs/research/`.
It describes intent, not shipped behaviour: the README is what users should read.

## Goals

1. **fork-tab**: fork the Claude Code session of the focused pane into a **new tab**. The fork has the
   full conversation context; the original session is unaffected.
2. **fork-tab (ask)**: same, but a popup asks for a **tab name** and an optional **initial prompt**, so
   the fork starts working right away.
3. **pane-to-tab**: move the focused pane (with its running process) into a **new tab**.
4. **attention-next**: one key jumps to an agent that is waiting for input or finished unread,
   anywhere in the session, without depending on a visible notification.
5. A structure that makes adding further actions trivial.

Non-goals for v0.1: forking non-Claude agents, moving tabs between workspaces (drovr does that),
auto-editing the user's `config.toml`.

## Prior art

A standalone shell script, `cfork` (not part of this repo), predates the plugin and does
goal 1/2 from a shell (`cfork [-p] <name> [prompt...]`). Its core logic:

```bash
sid=$CLAUDE_CODE_SESSION_ID   # or: herdr agent list | select(.focused and .agent=="claude")
cwd=$(herdr agent get "$HERDR_PANE_ID" | jq -r '.result.agent.cwd')
pane=$(herdr tab create --cwd "$cwd" --label "$name" --focus | jq -r '.result.root_pane.pane_id')
herdr pane run "$pane" "claude --resume $sid --fork-session -n $(printf %q "$name") $(printf %q "$prompt")"
```

It works (verified live). The plugin should improve on it using the research: `agent start` instead of
`pane run` (waits for the shell and registers the agent), explicit workspace, and error toasts.
Consider adding a `bin/cfork`-style CLI entry later so the shell workflow stays available (see
Backlog).

## Design decisions (made; change only with the maintainer)

| Topic | Decision |
|---|---|
| Plugin id / name | `my-herdr` (lowercase, no dots) |
| Language | **Python 3, standard library only** — no pip, no venv, no build step. Chosen over Bash+jq because: `subprocess` takes argv lists (no shell quoting), `json` replaces jq, real error handling and cleanup, `unittest` built in. Manifest commands name their own interpreter, so one action could still be a shell script if that is ever better. |
| Python baseline | 3.9+ in plugin code (no `tomllib`, no `match`). Only `tests/` may use `tomllib` (3.11+). herdr runs `python3` from its **server's** PATH, which can be an older interpreter than the one in your shell (official-docs §3.3), so the floor is real. |
| `min_herdr_version` | `"0.9.1"`, the current stable herdr. Older releases are out of scope: `agent focus` and `pane move --focus` only move the attached client from 0.9.1 on. |
| Structure | `bin/my-herdr` (executable, `#!/usr/bin/env python3`, dispatcher) + package `myherdr/`: `herdr.py` (CLI wrapper `run()`/`run_json()`), `context.py` (env + `HERDR_PLUGIN_CONTEXT_JSON`), `errors.py`, `actions/<id>.py`, `panes/<id>.py`. One module per action, each exposing `main(args)`. |
| Interactive input | popup plugin pane declared in manifest (`placement = "popup"`), opened by the action with `--env` |
| Fork launch | `herdr agent start <tmp-name> --kind claude --pane <new> -- --resume <sid> --fork-session -n <name> [prompt]`, then `agent rename --clear` |
| Errors | one exception type (`MyHerdrError`): headless actions catch it → `herdr notification show` + stderr log; popups catch it → message + "press Enter" |
| Tests | `unittest` (stdlib). Unit tests patch `myherdr.herdr.run`; a few end-to-end tests run `bin/my-herdr` with `HERDR_BIN_PATH` pointed at a fake `herdr` script that logs argv and serves JSON fixtures |
| Lint | **none**, and no CI. `make check` runs a syntax gate (`compileall` + `py_compile` for the extensionless files), the `tomllib` manifest check and the tests. |
| Keybindings | **no defaults, none suggested.** The README documents the `[[keys.command]]` mechanism with placeholder keys; the user picks. Never auto-installed. |

**Translating the research:** `docs/research/community-plugins.md` §4 is written in Bash (helper
library, action recipes, mock `herdr`). The *logic and the herdr call sequences* there remain the
spec; port them to Python instead of copying them. The closest Python precedent among the studied
plugins is `dmangla3/herdr-fork-from-message`.

### Maintainer decisions

- [x] **License**: **MIT**. `LICENSE` at the repo root.
- [x] **Marketplace**: add the GitHub topics (`herdr-plugin`, `herdr`, `claude-code`) **only after v0.1.0
  works end to end**, not now.
- [x] **Keys**: **no suggested default bindings.** The plugin ships no keys and the README must not
  present a key set as "the" binding. Document the mechanism instead: a `[[keys.command]]`
  `type = "plugin_action"` block per action with a placeholder key, the list of keys herdr's defaults
  already take, and how to reload. Choosing keys is the user's job after install. No `setup-keys`
  action in v0.1 (stays in the backlog, opt-in only).
- [x] **pane-to-tab when the pane is alone in its tab**: **no-op with a toast.** Detect it up front
  (`pane list`/`tab` pane_count) and show "pane is already alone in its tab" instead of mutating, so the
  tab bar does not churn.
- [x] **Fork tab label**: an **explicit name always wins** (`fork-tab (ask)`, or a future CLI arg). When
  no name is given, pass **no `--label` at all**, so the tab keeps herdr's generic default name and
  tab-renaming plugins (for example `kryptamine/herdr-auto-title`,
  `qu8n/herdr-automatic-rename`) or Claude's own title can take it over. Do **not** invent a
  `fork: <label>` string, because a plugin-set label looks like a manual rename to those plugins and
  would never be updated.

## Tasks

### Phase 0: verify assumptions on the live herdr (read-only, no UI changes)

- [x] `herdr --version` → the targeted release. `herdr integration status` → the claude integration
      installed and current (herdr's hook at `~/.claude/hooks/herdr-agent-state.sh`).
- [x] `agent start`, `pane process-info`, `notification show`, `plugin pane open`, `tab create`,
      `pane move`, `agent list` `--help` all match official-docs §7.4/§9, including the two known
      traps: `plugin pane open --help` still hides `popup`/`--width`/`--height`, and `pane move`
      accepts both `--label` and `--tab-label` at parse time (`--tab-label` with `--new-tab` fails at
      usage level, exit 2). Error envelopes confirmed: JSON on **stderr** with exit 1
      (`{"error":{"code":"pane_not_found","message":"..."}}`), usage text on stderr with exit 2.
- [x] **`done` reachability: CONFIRMED USABLE.** A one-hour read-only poller
      (`agent list` every 250 ms, logging transitions) caught
      `w3:p3 working -> done (focused=False)` and the agent **stayed `done` for the remaining ~24
      minutes**, until the poller stopped. So `done` is not a transient blip: it is durable while the
      agent is unseen, exactly what attention-next needs. **No event hook is required; Phase 3 can
      read `agent list` directly.**
      The nuance to remember: an agent that finishes while its pane is being *looked at* is marked
      seen immediately and goes `working -> idle`, never showing `done`. Decay is tied to
      seen-tracking, not to a timer, so a spot check on a watched pane can look like `done` is
      unreachable. `agent list` items carry **no** seen-related field; `done` vs `idle` *is* the signal.
      `AgentStatus` enum (from `herdr api schema --json`): `idle | working | blocked | done | unknown`.
- [x] Bonus findings worth keeping:
      - The `pane.agent_status_changed` event payload carries `pane_id`, `workspace_id`,
        `agent_status`, `agent`, `title`, `state_labels` — but **no `tab_id`**. A future event-driven
        queue would have to resolve the tab itself.
      - The installed claude hook requires `HERDR_ENV=1`, `HERDR_SOCKET_PATH` **and `HERDR_PANE_ID`**
        in Claude's own environment, or it exits silently without reporting the session id. This is
        the hard reason a forked agent must never be started inside a popup: popups have no pane id,
        so the fork would run but herdr would never learn its session.
      - `agent focus` and `pane move --focus` move the attached client, so Phases 3 and 4 need no
        focus workaround.
      - The claude hook is versioned separately from herdr. After a herdr upgrade,
        `herdr integration status` reports the hook as outdated until `herdr integration install
        claude` is run again, and Claude sessions started before that may keep the old registration
        until they restart.

### Phase 1: skeleton

- [x] `herdr-plugin.toml` with id/name/version `0.1.0`/min_herdr_version/description/platforms and a
      `ping` action (logs `HERDR_*` env + `HERDR_PLUGIN_CONTEXT_JSON`). See research
      community-plugins §4.1 and official-docs §2.
- [x] `bin/my-herdr` dispatcher: `#!/usr/bin/env python3`, adds the plugin root to `sys.path`,
      routes `my-herdr <action>` and `my-herdr pane <entrypoint>` to `myherdr.actions.*` /
      `myherdr.panes.*`, unknown → error. Catches `MyHerdrError` centrally (toast or popup message).
      The executable is a 5-line shim; the routing lives in `myherdr/cli.py` so tests can call
      `cli.main([...])` in-process. It resolves the package via `realpath(__file__)`, not cwd,
      because a pane opened with `--cwd` does not start in the plugin root.
- [x] `myherdr/herdr.py`: `run(*args)` (subprocess, argv list, the single seam tests patch),
      `run_json()` / `try_json()` (parse the envelope, raise `MyHerdrError` carrying herdr's own error
      code), `notify()`, `focused_pane()`, `wait_shell_ready()`; `myherdr/context.py` for env +
      `HERDR_PLUGIN_CONTEXT_JSON`. Ported from community-plugins §4.3.
- [x] `.gitignore`, `LICENSE` (MIT), `CHANGELOG.md` (Keep a Changelog format).
- [x] **Manual smoke test:** `herdr plugin link .` succeeded with no warnings,
      `action list` showed `ping`, `action invoke my-herdr.ping` → `plugin-log-1`
      `status: succeeded`, `exit_code: 0`, empty stderr. Then unlinked again. The real context JSON
      is in official-docs §3.3. Findings:
      - herdr ran the plugin with the **system Python 3.10**, not the newer Python the tests ran
        with: plugin commands inherit the herdr server's PATH, not the shell's. So the 3.9+ rule is
        real: the plugin can run on an older interpreter than `make check` does, and only a live
        smoke test exercises that. Keep `tomllib`, `match` and `X | Y`
        annotations out of `myherdr/` and `bin/`.
      - `invocation_source` for `plugin action invoke` is **`"cli"`**, not `"api"` (research
        corrected).
      - Missing context fields are **left out**, not sent as `null`. `Context` already treats both
        the same.

### Phase 2: test harness

**No CI.** Everything runs locally through `make check`, and there is no linter
(`ruff` was only ever planned as a CI-side tool). Adding CI later is a backlog item, not a gap.

- [x] `tests/mocks/herdr` (executable Python script): logs argv as JSON to `$HERDR_MOCK_LOG`, answers
      from `$HERDR_MOCK_DIR/*.json` (most specific fixture first: `agent_get_w1_p8` → `agent_get`),
      and `HERDR_MOCK_FAIL="<command prefix>:<code>[:<message>]"` makes chosen commands fail exactly
      like herdr (JSON on stderr, exit 1). Mutations answer `{"type":"ok"}` without a fixture; reads
      answer `{}`. The mock has its own tests, so a broken mock cannot fake a passing suite.
- [x] `tests/test_*.py` with `unittest`, 85 tests: `test_herdr.py`, `test_context.py`, `test_cli.py`,
      `test_manifest.py`, `test_end_to_end.py`. Unit tests patch `myherdr.herdr.run`; the end-to-end
      ones run `bin/my-herdr` as a real process with `HERDR_BIN_PATH` pointed at the mock, with every
      inherited `HERDR_*` variable stripped, so running the tests inside a herdr pane cannot leak that
      live session into them.
- [x] `tests/check_manifest.py`: `tomllib` validation of required keys, id rules, argv arrays, pane
      `width`/`height` only with `placement = "popup"`, link handlers pointing at declared actions.
      Also asserts every action/pane id has a matching module **and** that the command actually
      mentions that id, so a copy-pasted block routing to the wrong action fails locally.
- [x] `Makefile`: `make check` (= `syntax manifest test`), plus `link` / `logs` for the herdr dev loop.
      The syntax gate `py_compile`s `bin/my-herdr` and `tests/mocks/herdr` by name: `compileall` only
      looks at `*.py`, so it silently skips the extensionless entry point (even when named
      explicitly), which is exactly where a too-new-syntax failure would surface as a
      traceback in the plugin log.
- [x] Python 3.9 compatibility is not proven by the test run (it uses whatever `python3` is on
      PATH), so it is kept by convention: no `match`, no `X | Y` annotations, no `tomllib` outside `tests/`. Re-check by hand
      if it ever matters.

Found while building the harness (both were real bugs, both now covered by a test):

- `notification show` truncation appended the ellipsis *after* clipping, producing 241 characters for
  herdr's 240-character body cap.
- The CLI wrapper only handled a *missing* herdr binary (`FileNotFoundError`); a present but
  non-executable one (the mock, before `chmod +x`) escaped as a raw `PermissionError` traceback. It
  now catches `OSError`. Keep the exec bit on `bin/my-herdr` and `tests/mocks/herdr` in git.

### Phase 3: attention-next

Why: herdr's own `prefix+o` (`keys.open_notification_target`) jumps to the agent in the *currently
visible* toast. It needs `ui.toast.delivery` enabled, it only reaches one agent, and it is useless a
minute later. This action answers "who needs me now?" from live state instead. Built first among the
actions because it is the simplest one (no session ids, no popup, no TTY), so it shakes out the
dispatcher, `myherdr/herdr.py`, and the test harness. Move it behind the fork-tab phases if those are
more urgent.

- [x] `myherdr/actions/attention_next.py`: `agent list` → filter/sort in Python → `agent focus <pane_id>`.
      Order: `blocked` first, then `done`, each oldest `state_change_seq` first. Skip the pane the key
      was pressed in (`HERDR_PANE_ID`, else context `focused_pane_id`). No candidate → toast
      "no agent waiting". Works across workspaces; no workspace filter.
      Signature confirmed live (read-only `--help`): `herdr agent focus <target>`, target = pane id
      or agent name. Ties (same status and `state_change_seq`) break on `pane_id`, so the order a
      repeated press walks is stable. Any agent kind qualifies, not just Claude.
- [x] Cursor file (JSON) in `$HERDR_PLUGIN_STATE_DIR`: remember the pane last jumped to, so pressing the key
      again moves on instead of bouncing back. Needed because focusing a `blocked` agent does not
      unblock it, so it stays a candidate. Reset the cursor when the entry is gone or the candidate
      set changed.
      Shape: `{"pane_id": ..., "queue": [sorted pane ids]}`. `queue` is the signature that decides
      reset-or-advance, sorted so that a reordering (an agent re-blocking) is not mistaken for a new
      queue. Written only *after* a successful `agent focus`, so a failed jump cannot make the next
      press skip that agent. Every read and write is best-effort: no state dir, an unwritable file or
      a corrupt one costs at most one repeated jump, never the jump itself.
- [x] Manifest `[[actions]] id = "attention-next"`.
- [x] Tests with fixtures: blocked before done; oldest first; current pane skipped; cursor advances and
      wraps; no candidates → toast; candidates in several workspaces; malformed/empty `agent list`.
      `tests/test_attention_next.py`, 31 tests: selection, cursor arithmetic, cursor file, `main()`
      against a patched `run()`, and four end-to-end runs through `bin/my-herdr`.
- [x] **Manual:** live smoke test with at least two waiting agents in different workspaces.
      Verified from outside herdr, across several scenarios and agent priorities: ordering, the
      cursor advancing and wrapping, and `agent focus` moving the attached client. Invoking from a
      pane *inside* herdr makes the context report that pane as focused on the next invocation,
      which looks like focus did not move; it did.
      Re-verified after the walk fix below, with three agents (one blocked, two finished and read):
      repeated presses reach all three.
- [x] **Scope change (maintainer):** when nothing is waiting, cycle through the remaining agents
      instead of doing nothing, so one binding reaches every agent and no second "next agent" key is
      needed. Ordering is waiting agents first (as above), then workspace, tab, pane, with digit runs
      compared as numbers so `p10` follows `p2`. Non-waiting agents deliberately ignore
      `state_change_seq`: a working agent's sequence keeps moving and would reshuffle the walk
      between presses.
      The cursor stores `{"pane_id", "waiting": [sorted waiting pane ids]}` and leaves the ring only
      when an agent has *newly* started waiting, not when one stops. Consequence to keep in mind:
      repeated presses do not cycle only among waiting agents — after visiting a blocked agent the
      next press moves on. That is deliberate; otherwise a persistently blocked agent would make
      every other agent unreachable from this key.
- [x] **Bug found by live testing, fixed:** with three agents the walk ping-ponged between two and
      never reached the third. Cause: the walk was anchored by looking the cursor's pane up in the
      *filtered* candidate list, but that pane is the one the previous press focused, so it is
      exactly the pane the next press excludes as "the pane you pressed the key in". The lookup
      failed every time and the walk restarted at the front. The first smoke test missed it because
      the action was invoked from a shell pane that was never itself a target, so the anchor stayed
      in the list.
      Fix: keep the whole ring (including the current pane), anchor in it, and take the first entry
      after the anchor that is not the current pane. Status no longer affects the ring order at all;
      urgency is a separate decision layered on top. `waiting_ids` is computed over the whole ring
      too, so walking onto a blocked agent does not look like it stopped and restarted waiting.
      Regression tests: `WalkTest.test_the_walk_reaches_every_agent`,
      `ActionTest.test_walks_the_whole_ring_as_focus_follows_along`, and
      `test_a_blocked_agent_does_not_trap_the_walk` at both levels, all of which move the invoking
      pane to the previous target on each press the way the live action does.

Facts and open risks:

- `herdr agent focus` marks the agent seen, reads do not (official docs §agents). So visiting a `done`
  agent removes it from the queue by itself; only `blocked` needs the cursor.
- ~~If Phase 0 shows `done` never appears in `agent list`, fall back to an event hook~~ — not needed:
  Phase 0 measured `done` as reachable and durable for an unseen agent, so the action reads
  `agent list` at keypress time and keeps no queue of its own.
- Filtering and ordering happen in Python over `agent list`. `agent.view.set` is *not* the right tool: it
  changes the sidebar and the next/previous-agent navigation, not a direct jump.
- Open: the cursor advances on every press, including the press that reaches a `done` agent. That
  agent then drops out of the queue by itself, which changes the signature and resets to the front —
  correct, but it means a mixed queue is not walked strictly in order. Revisit only if it annoys in
  practice.

### Phase 4: pane-to-tab

- [x] `myherdr/actions/pane_to_tab.py`: focused pane → `pane move <pane> --new-tab --workspace <ws>
      --focus` → check `.result.move_result.changed`. `--focus` moves the attached client
      (official-docs §9.2), so the move and the focus are one call. "Alone in tab" is detected up
      front via `tab list` `pane_count` and reported instead of mutating.
      No `--label` is passed, per the maintainer decision on tab naming.
- [x] Manifest `[[actions]] id = "pane-to-tab"`, `contexts = ["pane"]`.
- [x] Tests: argv asserted; `changed:false` → toast; alone-in-tab never reaches the move; a failing
      `tab list` does not block the move; `pane get` fallback for a foreign pane.
      New fixtures `tab_list.json` and `pane_move.json` so the end-to-end test exercises the success
      path rather than the mock's generic mutation answer.
- [x] **Manual:** live smoke test via `herdr plugin action invoke my-herdr.pane-to-tab`, from a shell
      outside herdr, on a tab split into two panes. Both paths confirmed: the move created a new tab
      and reported its id, and a second invocation on the pane left alone reported instead of
      mutating, with `tab list` unchanged afterwards. The new tab came out with herdr's generic
      numeric label, confirming no `--label` reaches the CLI.
      Note for later smoke tests: after `pane split`, focus lands on the **new** pane, so the action
      targets that one rather than the pane the split was invoked from.

### Phase 5: fork-tab (no prompt)

- [ ] `myherdr/actions/fork_tab.py`: `agent get` → require `agent == "claude"` and
      `agent_session.kind == "id"` (else toast "run `herdr integration install claude`") →
      `tab create --workspace --cwd --label --no-focus` → `wait_shell_ready` →
      `agent start mh-fork-<pid> --kind claude --pane <new> --timeout 60000 -- --resume <sid> --fork-session -n <name>`
      → `agent rename <new> --clear` → `tab focus`. On failure after tab creation: close the tab.
      Forward `CLAUDE_CONFIG_DIR` if set (`tab create --env`).
- [ ] Manifest action `fork-tab`.
- [ ] Tests with fixtures: happy path argv sequence; non-claude pane; missing session id; agent start failure → tab closed.
- [ ] **Manual:** live smoke test.

### Phase 6: fork-tab (ask name and prompt)

- [ ] Manifest `[[panes]] id = "fork-prompt"`, `placement = "popup"`, small size, command
      `["sh","-c","exec \"$HERDR_PLUGIN_ROOT/bin/my-herdr\" pane fork-prompt"]` (the `sh -c` wrapper
      only expands `$HERDR_PLUGIN_ROOT`, because a pane's cwd is not necessarily the plugin root).
- [ ] `myherdr/actions/fork_tab_ask.py`: same validation as fork-tab (headless, toast errors), then
      `plugin pane open --plugin my-herdr --entrypoint fork-prompt --env MH_SRC_PANE=… --env MH_SID=… --env MH_WS=… --env MH_CWD=…`.
- [ ] `myherdr/panes/fork_prompt.py`: `input("Tab name [default]: ")`, `input("Prompt (optional): ")`,
      empty input / `KeyboardInterrupt` / `EOFError` = cancel (exit 0), then the shared fork routine
      (reuse Phase 5 code, pass the prompt as Claude's positional arg or via `agent prompt` after start).
      Errors → message + wait for Enter before exiting.
- [ ] Put the shared routine in `myherdr/fork.py`: `fork_into_new_tab(sid, ws, cwd, name, prompt=None)`,
      used by both the headless action and the popup.
- [ ] Tests: feed stdin to the pane module; cancel path; prompt with spaces, quotes, `$` and newlines
      (argv lists mean no shell quoting, but assert it anyway).
- [ ] **Manual:** live smoke test.

### Phase 7: docs and release

**v0.1.0 ships `attention-next` and `ping` only.** Releasing before the fork actions was a
deliberate call: the plugin is useful as it stands, and publishing early exercises the install and
listing path while the repo is small. The fork phases move to v0.2.0.

- [x] `README.md`: install first, actions table, how `attention-next` works, keybinding TOML block +
      reload, requirements, troubleshooting via the plugin log. Claims only what ships; the fork
      actions are named as planned, not described as available.
- [x] `CHANGELOG.md` 0.1.0 entry; version `0.1.0` in manifest.
- [x] Manifest `description` rewritten: it is indexed and shown on the marketplace card, so it must
      not advertise actions that do not exist yet.
- [x] Commit and push to `main` (maintainer). The marketplace tracks the **default-branch head**, not
      tags, so whatever is on `main` is what people install.
- [x] Add the GitHub topic `herdr-plugin` (+ `herdr`, `claude-code`) for the marketplace listing.
- [x] Tag `v0.1.0` for humans; optional GitHub release.
- [x] Verify the published path end to end: `herdr plugin unlink my-herdr`, then
      `herdr plugin install gysi/my-herdr`, then invoke the action. Installing over a linked plugin
      with the same id is refused, so the unlink is required, not optional.
      Installed and working from GitHub at commit `5364462`; the `ctrl+n` binding survived the switch
      from linked to installed untouched, because it names the action id, not a path.

**Released. v0.2.0 picks up at Phase 4.** Note for whoever does: `main` is now what users install, so
a broken commit on `main` is a broken release. There is no `herdr plugin update`, so nothing reaches
existing users until they reinstall — see "Updating an installed plugin" below.

### Updating an installed plugin

herdr 0.9.1 has **no `plugin update` command and no automatic update check**. `plugin install` pins
the default-branch head at install time as `source.resolved_commit`, and that commit is frozen until
someone re-runs `herdr plugin install gysi/my-herdr`, which replaces the managed checkout under
`~/.config/herdr/plugins/github/<component>`. `--ref` pins a tag, branch or commit instead.

Consequences worth remembering when releasing:

- Pushing to `main` updates the marketplace card within ~30 minutes but reaches **no existing user**.
- Users get no notification that a new version exists; they compare `resolved_commit` themselves via
  `herdr plugin list --plugin my-herdr --json`, or just reinstall.
- A linked checkout behaves differently: scripts are re-read on every invocation, so edits are live,
  and only a manifest change needs `herdr plugin link .` again.

## Backlog / ideas

- `fork-pane`: fork into a split pane instead of a tab (right/down variants).
- Shell entry point (`bin/cfork` or `my-herdr fork <name> [prompt]`) so a `cfork`-style shell workflow can use the plugin code.
- `pane-to-tab (ask)`: popup asks for the new tab's name.
- `attention-pick`: popup listing every waiting agent (state icon, workspace/tab, title), pick with
  `1`-`9`, then focus. Shares the popup machinery with fork-tab (ask). **Verify first:** a popup is
  session-modal and may restore focus to the pane underneath when it closes, which would undo the
  jump. If it does, focus after the popup exits instead of from inside it.
- `attention-status`: sidebar/status line token or a `notification show` summary of how many agents
  are blocked vs finished-unread.
- `setup-keys` action that idempotently adds the suggested keybindings (marker-guarded), opt-in only.
- Forking other agents (Codex has `resume`/fork equivalents).
