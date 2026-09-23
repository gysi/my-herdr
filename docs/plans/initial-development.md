# my-herdr: initial development plan

Status: Completed

This is the historical record of the plugin's initial development, including its design decisions
and completed checklists. It is not a queue of current work. The [README](../../README.md) and code
describe current behavior; start with the [documentation index](../README.md) for active plans and
research, and follow [AGENTS.md](../../AGENTS.md) when contributing.

## Goals

1. **fork-tab**: fork the Claude Code session of the focused pane into a **new tab**. The fork has the
   full conversation context; the original session is unaffected.
2. **fork-tab-ask**: same, but a popup asks for the new **tab's name** first, like herdr's own new tab.
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
[Future ideas](../README.md#future-ideas)).

## Design decisions (made; change only with the maintainer)

| Topic | Decision |
|---|---|
| Plugin id / name | `my-herdr` (lowercase, no dots) |
| Language | **Python 3, standard library only** — no pip, no venv, no build step. Chosen over Bash+jq because: `subprocess` takes argv lists (no shell quoting), `json` replaces jq, real error handling and cleanup, `unittest` built in. Manifest commands name their own interpreter, so one action could still be a shell script if that is ever better. |
| Python baseline | 3.9+ in plugin code (no `tomllib`, no `match`). Only `tests/` may use `tomllib` (3.11+). herdr runs `python3` from its **server's** PATH, which can be an older interpreter than the one in your shell (official-docs §3.3), so the floor is real. |
| `min_herdr_version` | `"0.9.1"`, the current stable herdr. Older releases are out of scope: `agent focus` and `pane move --focus` only move the attached client from 0.9.1 on. |
| Structure | `bin/my-herdr` (executable, `#!/usr/bin/env python3`, dispatcher) + package `myherdr/`: `herdr.py` (CLI wrapper `run()`/`run_json()`), `context.py` (env + `HERDR_PLUGIN_CONTEXT_JSON`), `errors.py`, `actions/<id>.py`, `panes/<id>.py`. One module per action, each exposing `main(args)`. |
| Interactive input | popup plugin pane declared in manifest (`placement = "popup"`), opened by the action with `--env` |
| Fork launch | `herdr agent start <tmp-name> --kind claude --pane <new> -- --resume <sid> --fork-session [-n <name>]`, then `agent rename --clear` |
| Errors | one exception type (`MyHerdrError`): headless actions catch it → `herdr notification show` + stderr log; popups catch it → message + "press Enter" |
| Tests | `unittest` (stdlib). Unit tests patch `myherdr.herdr.run`; a few end-to-end tests run `bin/my-herdr` with `HERDR_BIN_PATH` pointed at a fake `herdr` script that logs argv and serves JSON fixtures |
| Lint | **none**, and no CI. `make check` runs a syntax gate (`compileall` + `py_compile` for the extensionless files), the `tomllib` manifest check and the tests. |
| Keybindings | **no defaults, none suggested.** The README documents the `[[keys.command]]` mechanism with placeholder keys; the user picks. Never auto-installed. |

**Translating the research:** the [original recommendations](#original-recommendations) are written in Bash (helper
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
- [x] **Fork tab label**: an **explicit name always wins** (`fork-tab-ask`, or a future CLI arg). When
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
      [appendix A.1](#a1-manifest-skeleton) and official-docs §2.
- [x] `bin/my-herdr` dispatcher: `#!/usr/bin/env python3`, adds the plugin root to `sys.path`,
      routes `my-herdr <action>` and `my-herdr pane <entrypoint>` to `myherdr.actions.*` /
      `myherdr.panes.*`, unknown → error. Catches `MyHerdrError` centrally (toast or popup message).
      The executable is a 5-line shim; the routing lives in `myherdr/cli.py` so tests can call
      `cli.main([...])` in-process. It resolves the package via `realpath(__file__)`, not cwd,
      because a pane opened with `--cwd` does not start in the plugin root.
- [x] `myherdr/herdr.py`: `run(*args)` (subprocess, argv list, the single seam tests patch),
      `run_json()` / `try_json()` (parse the envelope, raise `MyHerdrError` carrying herdr's own error
      code), `notify()`, `focused_pane()`, `wait_shell_ready()`; `myherdr/context.py` for env +
      `HERDR_PLUGIN_CONTEXT_JSON`. Ported from [appendix A.3](#a3-shared-helper-library).
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

### Phase 5: fork-tab

- [x] `myherdr/fork.py`, `fork_into_new_tab(pane_id, name=None)`, with `myherdr/actions/fork_tab.py`
      as a thin wrapper around it:
      `agent get` → require `agent == "claude"` and `agent_session.kind == "id"` (else toast
      "run `herdr integration install claude`") → `tab create --workspace --cwd [--label] --focus` →
      `wait_shell_ready` →
      `agent start mh-fork-<pid> --kind claude --pane <new> --timeout 60000 -- --resume <sid> --fork-session [-n <name>]`
      → `agent rename <new> --clear`. On failure after tab creation: close the tab **and focus the
      source pane again**, because closing the focused tab drops the client on whichever tab herdr
      picks next. Forward `CLAUDE_CONFIG_DIR` if set (`tab create --env`).
- [x] **Focus:** the tab is focused on creation. `agent start` waits for Claude to replay the
      session — long enough to notice, too short to do anything else in the old pane — so hiding the
      new tab until the fork is up reads as lag with nothing to show for the keypress, while watching
      it boot reads as progress. Focus is not gated on readiness: herdr focuses an ordinary new tab
      before its shell exists.
- [x] Manifest action `fork-tab`.
- [x] Tests with fixtures: happy path argv sequence; non-claude pane; missing session id; agent start
      failure → tab closed. Also: shell never settles, tab created without a pane, `KeyboardInterrupt`
      mid-start (all three close the tab and restore focus), `CLAUDE_CONFIG_DIR` forwarding.
- [x] **Manual:** live smoke test, invoked with the source Claude pane focused (the action reads the
      pane it was invoked from, so a parked shell would test nothing). Verified: the new tab opens
      focused and Claude comes up with the forked conversation; the fork reports its **own** session
      id to herdr, distinct from the source's, so a fork can be forked again; no `mh-fork-*` name is
      left on any agent.

### Phase 6: fork-tab-ask (ask for the tab name)

Asks for a **name only**, like herdr's own new tab. No initial prompt: the fork's tab is focused, so
typing the first message straight into Claude is just as quick and needs no second input.

- [x] Manifest `[[actions]] id = "fork-tab-ask"` and `[[panes]] id = "fork-prompt"`,
      `placement = "popup"`, 64×8, command
      `["sh","-c","exec \"$HERDR_PLUGIN_ROOT/bin/my-herdr\" pane fork-prompt"]` (the `sh -c` wrapper
      only expands `$HERDR_PLUGIN_ROOT`, because a pane's cwd is not necessarily the plugin root).
- [x] `myherdr/actions/fork_tab_ask.py`: `fork.claude_agent()` first, so an unforkable pane is a
      toast before any popup opens, then
      `plugin pane open --plugin my-herdr --entrypoint fork-prompt --env MH_SOURCE_PANE=<pane>`.
      Only the pane is passed: the fork re-reads session, workspace and cwd itself.
- [x] `myherdr/panes/fork_prompt.py`: asks for the name; Enter forks, Esc / Ctrl-C / Ctrl-D cancel
      (exit 0), an empty name forks unnamed. Errors → message + wait for Enter.
- [x] **The popup does not run the fork; herdr does.** A popup stays on screen until its process
      exits, and `agent start` can take seconds, so forking in place would cover the new tab for the
      whole wait. On Enter the popup writes a request (source pane, name, timestamp) to
      `$HERDR_PLUGIN_STATE_DIR/fork-request.json` and runs `herdr plugin action invoke
      my-herdr.fork-tab`, which returns as soon as herdr has started the action, then exits. So the
      fork is an ordinary `fork-tab` run: launched, logged and given the action environment by herdr,
      with nothing running outside its view.
      The file exists because a herdr action takes no parameters: `plugin action invoke` has only
      `--plugin`, and the socket API's `plugin.action.invoke` accepts just a `context` with fixed
      fields. `myherdr/fork_request.py` keeps it one-shot: written atomically, claimed by rename so
      only one run takes it, ignored after 10 s, withdrawn by the popup if the invoke fails. The
      request names the pane, so the fork does not depend on which pane herdr reports as focused
      while a popup is open. Without a request, `fork-tab` forks the focused pane unnamed.
- [x] `myherdr/prompt.py`: a one-line editor in cbreak mode, because `input()` cannot see Esc — the
      terminal just echoes `^[`. An Esc followed at once by more bytes is an arrow or function key
      and is swallowed, not taken as cancel. Backspace, Ctrl-U, UTF-8. Without a TTY it falls back to
      reading a plain line.
- [x] Tests: the line editor key by key; the action's refusals never opening a popup; `ui_busy`;
      the popup's request and invoke, cancel and empty-name paths, a name with quotes, `$` and dashes,
      a failed invoke withdrawing the request; the request file itself (one-shot, age limit,
      malformed content); `fork-tab` with and without a request, end to end against the fake herdr.
- [x] **Manual:** live smoke test with a fresh Claude session. Check: the popup closes on Enter; the
      new tab is focused and named; the fork shows up in `herdr plugin log list` as a `fork-tab` run
      with `named '<name>'`; `fork-request.json` is gone from the state directory afterwards; closing
      the popup does not pull focus back to the source pane.
- [x] **An id with no saved conversation is refused before any tab exists.** Otherwise Claude exits at
      once with "No conversation found" while `agent start` waits out its 60 s timeout, with the tab
      showing the error. It happens when a session is forked before its first message (Claude saves
      nothing until then), and in the stale-id case below. `fork.claude_agent()` checks for
      `<claude config>/projects/*/<id>.jsonl`, with the config directory resolved as the fork will
      resolve it (`CLAUDE_CONFIG_DIR`, else `~/.claude`), so it cannot rule out a session the fork
      would find. No `projects/` directory at all means "cannot tell", and the fork goes ahead. Both
      actions get it; `fork-tab-ask` refuses before the popup opens. Only the file's existence is
      read, never its content. Tests run with a fake `HOME`, so they never see the real store.
- **Known limitation, not worked around:** the fork resumes whatever Claude has on disk for the id
      herdr holds, which can differ from the conversation on screen in two cases. Right after a
      rewind, `--resume` of a session still open elsewhere can pick the discarded branch (Claude has
      no resume-at-message flag). And **background sessions cannot be tied to a pane.** Claude's
      background-sessions feature (`claude agents`, `claude attach`, switching sessions inside the
      TUI) hosts sessions in a Claude daemon; the `claude` in the pane is only a front-end. Verified
      with a temporary probe hook (event, session id, `HERDR_PANE_ID`, process chain per hook):
      switching to a session fires **no hook at all**; that session's hooks run inside the daemon
      with the `HERDR_PANE_ID` of whichever pane first spawned it, even after that pane is closed;
      and the pane itself reports only the front-end's own startup session, or nothing under
      `claude agents`. herdr still follows such a pane's status and title, because it reads those
      from the screen, but it never learns the id. So forking works only for a session started in
      the pane (`claude`, `claude --resume <id>`). Otherwise the check above refuses, or, when herdr
      still holds a startup id that has a saved conversation, the fork starts from that one. Every
      fork logs `fork: <pane> runs claude session <id> (saved conversation: …)`, which makes the case
      visible. The fix has to come from Claude (an event on attach/switch that identifies the
      front-end, or the session id somewhere herdr's screen detection can read it); nothing on the
      plugin side can tell which session a front-end shows.

### Phase 7: docs and release

Released in the order the actions became usable, not in phase order: v0.1.0 `attention-next` and
`ping`, v0.2.0 `pane-to-tab`, v0.3.0 `fork-tab` and `fork-tab-ask`. Publishing early exercised the
install and listing path while the repo was small.

A release is: version bump in `herdr-plugin.toml`, the `[Unreleased]` CHANGELOG entries moved under
the new version, the manifest `description` still true of what ships, `make check`, a commit, an
annotated tag `vX.Y.Z` on it, and both pushed.

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

`main` is what users install, so a broken commit on `main` is a broken release. There is no
`herdr plugin update`, so nothing reaches existing users until they reinstall — see "Updating an
installed plugin" below.

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

## Original recommendations

Historical design sketch recorded on **2026-09-21**, preserved from the first committed community
survey (`fec8e28`). These were proposals, including alternatives the implementation did not adopt;
they are not instructions for current development. Preserve them as history rather than updating
them for new features. The completed phases above record the implementation decisions. Current
behavior belongs in the [README](../../README.md) and code.

The sketch uses Bash + jq, proposed action IDs, and optional CI/lint tools. Section references
beginning with §3 refer to the [community survey](../research/community-plugins.md).

### A.1 Manifest skeleton

```toml
# herdr-plugin.toml — my-herdr: small herdr actions.
# Keybindings are NOT declared here (herdr does not bind manifest keys);
# see README "Keybindings" for [[keys.command]] blocks.

id = "my-herdr"                 # no dots → qualified ids stay unambiguous: my-herdr.<action>
name = "my-herdr"
version = "0.1.0"
min_herdr_version = "0.8.0"     # agent start / pane move used below; local herdr is 0.9.0.
                                # Too high = hard load failure, so pick the oldest that works.
description = "Personal herdr actions: fork the focused Claude Code session into a new tab, move the focused pane into a new tab, and more."
platforms = ["linux", "macos"]

# ---- actions (headless: no TTY, cwd = plugin root, output → plugin log) ----

[[actions]]
id = "fork-claude-tab"
title = "Fork Claude session into new tab"
description = "Resume the focused pane's Claude Code session with --fork-session in a new tab"
contexts = ["pane"]
command = ["bash", "bin/my-herdr", "fork-claude-tab"]

[[actions]]
id = "fork-claude-tab-named"
title = "Fork Claude session into new tab (ask name/prompt)…"
contexts = ["pane"]
command = ["bash", "bin/my-herdr", "fork-claude-tab", "--ask"]

[[actions]]
id = "move-pane-new-tab"
title = "Move pane into a new tab"
contexts = ["pane"]
command = ["bash", "bin/my-herdr", "move-pane-new-tab"]

[[actions]]
id = "ping"
title = "my-herdr: ping (print context to plugin log)"
contexts = ["global", "workspace", "pane"]
command = ["bash", "bin/my-herdr", "ping"]

# ---- panes (interactive: real TTY) ----
# Always locate scripts via $HERDR_PLUGIN_ROOT: when opened with --cwd, the pane's
# cwd is NOT the plugin root, so relative paths break.

[[panes]]
id = "prompt"
title = "my-herdr"
placement = "popup"
width = "60%"
height = 12
command = ["bash", "-c", "exec bash \"$HERDR_PLUGIN_ROOT/bin/my-herdr\" pane prompt"]
```

Notes:

- Actions take **no runtime arguments** (catchup README), so every variant, such as "ask vs no ask", is a separate action id passing different argv. forkr and calebcauthon do the same.
- `contexts` values seen in the wild: `pane`, `tab`, `workspace`, `global`. They control which herdr menus show the action. Keybinding invocation works regardless.

### A.2 Repo layout

```
my-herdr/
  herdr-plugin.toml
  bin/my-herdr              # dispatcher: sources lib, routes <action> and "pane <entrypoint>"
  lib/common.sh             # shared helpers (below)
  lib/actions/fork-claude-tab.sh
  lib/actions/move-pane-new-tab.sh
  lib/actions/ping.sh
  lib/panes/prompt.sh       # popup: read name/prompt, then perform the fork
  tests/run.sh              # runs tests/test_*.sh
  tests/lib.sh              # check/check_contains/... (qu8n style) — or bats if preferred
  tests/mocks/herdr         # fake CLI: logs argv, serves fixtures (ohmyzsh style)
  tests/fixtures/*.json
  tests/test_fork.sh tests/test_move.sh tests/test_manifest.sh
  Makefile                  # test / lint / syntax
  .github/workflows/ci.yml
  README.md  LICENSE  CHANGELOG.md
  docs/research/community-plugins.md
```

This is the "single dispatcher, many modes" pattern (catchup `run.sh`, automatic-rename, herdr-plus subcommands), with one file per action so the plugin grows cleanly. Adding an action means adding a `[[actions]]` block, a `lib/actions/<id>.sh` defining `action_<id>()` (or a sourced file), a test, and a README row.

### A.3 Shared helper library

A `lib/common.sh` synthesis of the surveyed plugins:

```bash
# shellcheck shell=bash
MH_ID="${HERDR_PLUGIN_ID:-my-herdr}"
HERDR="${HERDR_BIN_PATH:-herdr}"
MH_ROOT="${HERDR_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

h() { "$HERDR" "$@"; }                               # every herdr call goes through here (mockable)

log() { printf 'my-herdr: %s\n' "$*" >&2; }          # ends up in `herdr plugin log list --plugin my-herdr`

notify() {                                          # best-effort toast (forkr/calebcauthon)
  h notification show "my-herdr" --body "$1" --sound "${2:-none}" >/dev/null 2>&1 || true
}

die() {                                             # headless failure: log + toast + nonzero
  log "$1"; notify "$1" request; exit 1
}

die_in_pane() {                                     # interactive failure: keep popup visible
  printf '\nmy-herdr: %s\n[press Enter to close]' "$1" >&2
  read -r _ || true                                 # blocking read; NEVER `read -t` in popups
  exit 1
}

need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not on PATH"; }

ctx() {                                             # ctx '.focused_pane_cwd'
  [ -n "${HERDR_PLUGIN_CONTEXT_JSON:-}" ] || return 0
  printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -r "$1 // empty" 2>/dev/null
}

focused_pane() {                                    # env → context → live query
  local p="${HERDR_PANE_ID:-}"
  [ -n "$p" ] || p="$(ctx .focused_pane_id)"
  [ -n "$p" ] || p="$(h pane current 2>/dev/null | jq -r '.result.pane.pane_id // empty')"
  [ -n "$p" ] || return 1
  printf '%s' "$p"
}

wait_shell_ready() {                                # Adapted from t4t5/herdr-forkr/forkr.sh (MIT)
  local pane="$1" i=0 ready
  while [ "$i" -lt 50 ]; do
    ready="$(h pane process-info --pane "$pane" 2>/dev/null | jq -r '
      .result.process_info
      | if (.foreground_processes | length) == 1
           and (.foreground_processes[0].pid == .shell_pid
                or (.foreground_processes[0].name | test("^(zsh|bash|fish|sh|dash|ksh|nu)$")))
        then "yes" else "no" end' 2>/dev/null)"
    [ "$ready" = yes ] && return 0
    i=$((i + 1)); sleep 0.2
  done
  return 1
}

cfg() { :; }  # optional: copy catchup's config.env reader (§3.5) when a setting is needed
```

### A.4 Action recipes

**Move focused pane to new tab** (from drovr's calls):

```bash
action_move_pane_new_tab() {
  need jq
  local pane ws out tab
  pane="$(focused_pane)" || die "no focused pane"
  ws="${HERDR_WORKSPACE_ID:-$(ctx .workspace_id)}"
  [ -n "$ws" ] || ws="$(h pane get "$pane" | jq -r '.result.pane.workspace_id // empty')"
  out="$(h pane move "$pane" --new-tab --workspace "$ws" --no-focus 2>&1)" || die "pane move failed: $out"
  [ "$(printf '%s' "$out" | jq -r '.result.move_result.changed')" = true ] || die "herdr refused the move: $out"
  tab="$(printf '%s' "$out" | jq -r '.result.move_result.pane.tab_id // empty')"
  [ -n "$tab" ] && h tab focus "$tab" >/dev/null 2>&1 || true
}
```

- If the pane is the only one in its tab, the source tab closes (drovr README). Consider refusing or no-oping when `pane list` shows it is alone.
- `--label NAME` names the new tab. An "ask for name" variant would use the popup flow below.

**Fork Claude into a new tab, no prompt** (forkr recipe, Claude only):

1. Get `pane` via `focused_pane`, then `info=$(h agent get "$pane")`.
2. Check `.result.agent.agent == "claude"`. Read `sid` from `.result.agent.agent_session.value` and require `.agent_session.kind == "id"`; otherwise tell the user to run `herdr integration install claude`. Also read `ws` from `.workspace_id` and `cwd` from `.foreground_cwd // .cwd`.
3. `h tab create --workspace "$ws" --cwd "$cwd" [--label "fork: <tab_label>"] --no-focus`, then take `.result.root_pane.pane_id` and `.result.tab.tab_id`.
4. If `CLAUDE_CONFIG_DIR` is set, pass `--env CLAUDE_CONFIG_DIR=...` (fork-from-message).
5. `wait_shell_ready "$new"`, then `h agent start "mh-fork-$$" --kind claude --pane "$new" --timeout 60000 -- --resume "$sid" --fork-session`. Tolerate `agent_not_ready`, then `h agent rename "$new" --clear`.
6. `h tab focus "$tab"` and `notify "Forked $pane -> $new"`.
7. Optional (fork-from-message): if steps 4–5 fail, `h tab close "$tab"` so no half-finished tab is left.

**Fork with name and prompt** (two-stage: action → popup → work):

1. The action does steps 1–2 headless, validating early so errors surface as toasts. Then run `exec h plugin pane open --plugin "$MH_ID" --entrypoint prompt --env MH_SRC_PANE=$pane --env MH_SID=$sid --env MH_WS=$ws --env MH_CWD=$cwd --env MH_TAB_LABEL="$(ctx .tab_label)"`. Omit `--placement` so the manifest's `popup` applies (catchup). Don't pass `--target-pane` for a popup; herdr rejects it.
2. The popup (`lib/panes/prompt.sh`) runs `read -r -p "Tab name [fork]: " name`, then `read -r -p "Initial prompt (optional): " prompt`, using blocking reads. Use the §3.8 `prompt_line` helper if Esc-to-cancel is wanted.
3. The popup then runs steps 3–6 itself. A popup is not a pane, so creating tabs and starting agents from it is fine; drovr does all its moves from the popup.
4. To seed the fork with a prompt, either:
   - pass it to Claude as a positional arg, since `claude [options] [prompt]` is valid (`-- --resume "$sid" --fork-session -n "$name" "$prompt"`, and `-n/--name` sets Claude's session display name, per `claude --help` locally), or
   - (more robust) after `agent start` returns ready, run `h agent prompt "$new" "$prompt"`. `agent prompt <TARGET> <TEXT> [--wait]` rejects with `agent_blocked` if a dialog is open.
5. Use `--label "$name"` on `tab create`.
6. On error, call `die_in_pane` so the popup stays readable. On Esc or empty input, exit 0 silently (drovr treats cancel as success).
7. Don't invoke another plugin action that opens UI from inside the popup: it returns `ui_busy` (plugin-manager).

**`ping` action** (herdr-plus idea): print `env | grep ^HERDR_` and `$HERDR_PLUGIN_CONTEXT_JSON | jq .` to stdout, then check with `herdr plugin log list --plugin my-herdr`. It is a cheap way to discover the real context shape on the installed herdr.

### A.5 Keybindings (README section)

```toml
# ~/.config/herdr/config.toml, then: herdr server reload-config
[[keys.command]]
key = "prefix+f"
type = "plugin_action"
command = "my-herdr.fork-claude-tab"
description = "fork Claude session into new tab"

[[keys.command]]
key = "prefix+shift+f"
type = "plugin_action"
command = "my-herdr.fork-claude-tab-named"
description = "fork Claude session (ask name/prompt)"

[[keys.command]]
key = "prefix+m"
type = "plugin_action"
command = "my-herdr.move-pane-new-tab"
description = "move pane into new tab"
```

- Keys other plugins suggest (possible conflicts if you install them): `prefix+f` (forkr, catchup, floax), `prefix+m` / `prefix+M` (drovr), `prefix+p` (command-palette, plugin-manager), `prefix+a` (agent-handoff), `prefix+c` (catchup, calebcauthon).
- **`prefix+c` is herdr's default `new_tab`**.
- Check `herdr config` or the herdr keyboard docs before choosing. Don't auto-edit config.toml by default; if ever wanted, use a marker-guarded, idempotent `setup-keys` action (floax/agent-handoff pattern).

### A.6 README sections (consensus of the best READMEs)

1. Title plus a one-paragraph what/why (and a table of actions, or agent → command).
2. **Requirements:** herdr ≥ X, `jq`, `claude` on PATH, `herdr integration install claude` (verify with `herdr integration status`).
3. **Install:** `herdr plugin install <owner>/my-herdr`, or `herdr plugin link /path/to/my-herdr` for local development.
4. **Keybindings:** TOML blocks plus `herdr server reload-config`.
5. **Actions:** table of qualified id → behaviour. Include manual invocation: `herdr plugin action invoke my-herdr.<id>`.
6. **How it works:** numbered steps, naming the herdr CLI calls.
7. **Configuration and state:** what goes in `$HERDR_PLUGIN_CONFIG_DIR` / `$HERDR_PLUGIN_STATE_DIR`, or "none".
8. **Failure behaviour and logs:** toasts, `herdr plugin log list --plugin my-herdr`.
9. **Notes and caveats:** the fork is a snapshot of the on-disk transcript, and "allow for this session" grants don't carry over (forkr).
10. **Development:** link, test, lint.
11. License.

### A.7 Marketplace and versioning checklist

- Public repo, GitHub topic `herdr-plugin` (also useful: `herdr`, `claude-code`), `herdr-plugin.toml` at the root on the default branch, all required keys present and parseable. Don't make it a fork or archive it, or it won't be listed.
- Bump `version` in the manifest on every shipped change; the card shows it. Use SemVer, tag `vX.Y.Z`, and optionally auto-create a GitHub release from the CHANGELOG section (qu8n `release.yml`).
- Users update by re-running `herdr plugin install owner/repo`; there is no `update` command.
- A LICENSE file (MIT is universal among studied plugins).

### A.8 Testing approach

- **Fake herdr.** `tests/mocks/herdr` logs `"$*"` to `$HERDR_MOCK_LOG` and serves `$HERDR_MOCK_DIR/*.json` fixtures (§3.7). Run the action with `HERDR_BIN_PATH=$PWD/tests/mocks/herdr HERDR_PLUGIN_CONTEXT_JSON='{...}' HERDR_PANE_ID=w1:p2 bash bin/my-herdr move-pane-new-tab` and assert the logged argv (for example `pane move w1:p2 --new-tab --workspace w1 --no-focus`). For popups, feed stdin: `printf 'myname\nhello\n' | bash bin/my-herdr pane prompt`.
- **Harness.** Every studied Bash plugin avoids bats in favour of ~50 lines of `check`/`check_contains` (qu8n `tests/lib.sh`, calebcauthon `tests/run.sh`). bats-core is fine if preferred, but it is an extra dependency; CI would need `apt-get install bats` or `bats-core/bats-action`.
- **Static checks.** Run `bash -n` on every script (including extensionless `bin/my-herdr` and the mock) and `shellcheck -x` with `# shellcheck source=` directives. Pin the shellcheck version in CI, because findings differ between 0.9 and 0.11 (qu8n).
- **Manifest check** (no studied Bash plugin does this; herdr-plus does it in Go). A small python3 `tomllib` script (Python 3.11+) can check:
  ```python
  import tomllib, re, sys
  m = tomllib.load(open("herdr-plugin.toml", "rb"))
  for k in ("id", "name", "version", "min_herdr_version"):
      assert isinstance(m.get(k), str) and m[k], f"missing {k}"
  assert re.fullmatch(r"[A-Za-z0-9.:_-]+", m["id"])
  for kind in ("actions", "panes", "link_handlers"):
      ids = [e["id"] for e in m.get(kind, [])]
      assert len(ids) == len(set(ids)), f"duplicate {kind} ids"
      for i in ids: assert re.fullmatch(r"[A-Za-z0-9:_-]+", i), f"bad id {i}"
  for e in m.get("actions", []) + m.get("panes", []):
      assert isinstance(e["command"], list) and e["command"], "command must be argv array"
  print("manifest ok")
  ```
  Locally, `herdr plugin link .` is the authoritative validator.
- **CI** (`.github/workflows/ci.yml`), a synthesis of qu8n and plugin-manager:
  ```yaml
  name: ci
  on: { push: { branches: [main] }, pull_request: {} }
  permissions: { contents: read }
  jobs:
    test:
      strategy: { fail-fast: false, matrix: { os: [ubuntu-latest] } }   # add macos-latest for bash 3.2 if ever needed
      runs-on: ${{ matrix.os }}
      steps:
        - uses: actions/checkout@v4
        - run: sudo apt-get update && sudo apt-get install -y jq shellcheck
        - name: Syntax
          run: for f in bin/my-herdr lib/*.sh lib/*/*.sh tests/*.sh tests/mocks/herdr; do bash -n "$f"; done
        - name: Shellcheck
          run: shellcheck -x -s bash bin/my-herdr lib/*.sh lib/*/*.sh tests/*.sh tests/mocks/herdr
        - name: Manifest
          run: python3 tests/check_manifest.py
        - name: Tests
          run: bash tests/run.sh
  ```
  Optionally add plugin-manager's "shipped files changed without a version bump" warning job (§3.8), with its `git diff` paths changed from `bin herdr-plugin.toml` to `bin lib herdr-plugin.toml`.
- **Manual smoke test:** `herdr plugin link .`, `herdr plugin action list --plugin my-herdr`, `herdr plugin action invoke my-herdr.ping`, `herdr plugin log list --plugin my-herdr`.
