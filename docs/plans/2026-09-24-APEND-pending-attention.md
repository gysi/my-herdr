# Preserve pending attention until visited

Slug: APEND

Status: **Completed**

## Problem and evidence

Saving every waiting agent's status and state-change sequence after a jump records observation,
not a visit. When several agents need attention, this removes the others' urgency on the next
press even though their output remains unread. Recording the entire snapshot for `attention-prev`
also suppresses urgency in panes it never reaches. The implementation records visits instead.

The fixture-based regression in
`tests/attention/test_next.py::EndToEndTest.test_second_done_agent_remains_urgent_after_visiting_the_first`
reproduces this through two dispatcher processes sharing the real temporary cursor file:

1. `w1:p1` and `w1:p2` are done; `w1:p1` has the older answer. Start at idle `w1:p3`.
2. The first press correctly focuses `w1:p1`.
3. Viewing it makes it idle. `w1:p2` remains done and unvisited. Priority sidebar order is
   `w1:p2 -> w1:p1 -> w1:p3`.
4. The second press must focus `w1:p2`; focusing idle `w1:p3` reproduces the bug.

Fixtures live under `tests/fixtures/attention_pending_done/{before,after}/agent_list.json`.
The regression fixture and expected destination are unchanged. It passes with the implemented fix.

## Intended behavior

- Forward navigation visits pending agents before resuming normal sidebar cycling.
- A waiting state is identified by pane ID, status (`blocked` or `done`), and state-change
  sequence. It remains pending until visited or until herdr no longer reports that state.
- Rank only pending candidates: blocked before done, oldest sequence first, then the existing
  natural-ID tie breaker. An already-visited blocker cannot displace a pending done agent.
- A visited, unchanged waiting state does not interrupt cycling. Another answer or input request
  in that pane becomes pending when its status or sequence changes, even if all intervening work
  occurs between keypresses.
- The invoking pane is already being viewed and is never a destination. A new state in that pane
  alone must not cause a jump to an unrelated, already-visited blocker.
- Previous navigation always follows sidebar order. It acknowledges only panes actually visited
  by that action and leaves other pending agents eligible for the next forward press.
- Both directions retain current-pane anchoring, the saved anchor outside the agent list,
  wraparound, grouped/priority ordering, and navigation across workspaces.

## Design

### Polling and ownership

Continue reading `herdr agent list` once per invocation through `shared/herdr.py`. Herdr owns
status detection and read state; the plugin owns navigation history. No background watcher or
event subscription is required for this fix.

Keep the implementation within `myherdr/attention/`. Selection and state reconciliation should
be pure functions so their behavior can be tested independently of CLI calls and file writes.
Keep the existing CLI wrapper and feature boundaries.

### Selection and successful state update

For each invocation:

1. Read the current agents, sidebar order, invoking pane, and saved navigation state.
2. Retain saved visit records only when the pane still exists, is waiting, and has exactly the
   recorded status and sequence. Discard stale records for disappeared or changed states.
3. Treat the invoking pane's current waiting state as visited for this selection. Do not infer
   visits to other panes from their presence in the agent list or from other clients' focus flags.
4. For next, select the most urgent pending agent. If none exists, select the next sidebar row.
   For previous, select the previous sidebar row regardless of pending agents.
5. Focus the chosen pane through the wrapper. Only after success, save the destination anchor,
   retained visit records, and the source/destination waiting states observed in step 1.
   Do not acknowledge unrelated pending states.

Use the pre-focus state when acknowledging the destination. If its state changes during the
focus call, the different status/sequence remains eligible at the next invocation. Do not
perform a post-focus poll that could acknowledge an answer not included in the selection.

A failed list or focus must not replace the cursor or consume pending attention. Preserve
existing toast/error handling and best-effort operation when state storage is unavailable.
With no other agent, preserve the existing notification behavior. No state persistence is
needed for that no-jump case.

### Saved state and migration

Retain the `attention-next.json` filename and the shared anchor used by next and previous.
Use an explicit version and a field whose name describes visits, for example:

```json
{
  "version": 2,
  "pane_id": "w1:p1",
  "visited": {"w1:p1": ["blocked", 100]}
}
```

Validate the version, anchor type, and per-pane status/sequence pairs. For legacy files with
either waiting-ID lists or waiting-state mappings, preserve a valid anchor but do not interpret
observed states as visits. Start with no trusted visit records, so existing waiting agents may
be offered once after upgrade. Unknown versions and malformed records must also fail safely
without suppressing pending attention. Write the new format only after successful focus.

### Manual focus and limits

If the user clicks a pane and invokes either action there, that source pane counts as visited.
An answer viewed manually also stops being pending when herdr reports it as idle.

Without focus events, a blocked pane clicked and left entirely between action invocations
cannot reliably be recorded as visited: blocked status does not clear on focus. Such a state
may still receive one urgency visit. Do not promise to reconstruct unobserved mouse navigation.
Multiple clients, event-based focus tracking, and concurrent-invocation coordination are outside
this fix's scope; retain the existing single-local-client assumptions.

### Diagnostics and documentation

Extend successful action logs with the invoking pane, selection reason (`urgent` or `sidebar`),
and pending candidates with their status/sequence. Retain destination, waiting count, and sort
mode. Use pane IDs only; do not add session IDs or conversation content. Test that a skipped
sidebar candidate and a pending urgency candidate can be distinguished from the log.

Update README navigation/state semantics and explain upgrade reconsideration. Update relevant
docstrings. Bump the plugin's next patch version and add a user-visible changelog entry when
the implementation is ready. Preserve completed historical plans.

## Implementation and verification

- [x] Add the two-snapshot regression and confirm its specific failure with the mock CLI.
- [x] Implement visit-state parsing, validation, reconciliation, and legacy migration.
- [x] Select urgency from pending candidates only; retain sidebar fallback behavior.
- [x] Persist only successful source/destination visits, for both next and previous.
- [x] Make the existing regression pass unchanged, including its fixture and expected target.
- [x] Add focused tests for the cases below and update tests that encode whole-snapshot
  acknowledgement. Preserve the previous same-pane-new-answer regressions.
- [x] Add diagnostic fields and verify their meaning in mock action tests.
- [x] Update README/docstrings, manifest version, and changelog.
- [x] Run `make check`; all tests, lint, syntax, and manifest validation must pass.
- [x] Mark this plan completed and move its index entry after verification is complete.

Verification: `make check` passes all 296 tests, Ruff, syntax checks, and manifest validation.
The attention suite contains 91 tests, including the unchanged two-snapshot regression and
pending-state scenarios in `tests/attention/test_pending.py`. Release version: `0.5.3`.

Required automated cases:

| Case | Expected behavior |
| --- | --- |
| Two or more done agents | Each unvisited answer gets an urgency visit before sidebar cycling |
| Pending blocked and done agents | Blocked first, then the still-pending done agent |
| Visited blocker plus new done agent | Select the done agent without revisiting the blocker |
| Multiple persistent blockers | Visit each state once, then allow all other panes to be reached |
| New answer/request in a visited pane | Changed status or sequence restores pending urgency |
| New state only in the invoking pane | Continue cycling unless another pending candidate exists |
| Previous jumps elsewhere | Unvisited pending agents retain forward urgency |
| Previous lands on a waiting pane | That state counts as visited on subsequent next presses |
| Manual focus at invocation | Anchor at and acknowledge the actual source pane |
| Pending pane becomes idle, works, or disappears | Remove it from pending candidates |
| State changes during focus | Acknowledge only the selected snapshot; the new state stays pending |
| List/focus failure | Preserve the saved anchor and visits; retry can still reach pending work |
| Legacy, malformed, or unavailable state | Safe fallback; no false acknowledgement of unread work |
| Grouped/priority views and non-agent sources | Preserve ordering, wraparound, and anchor rules |

All automated tests use the mock CLI. Live herdr settings, plugin registration, and real panes
must not be changed by the implementation or test suite.
