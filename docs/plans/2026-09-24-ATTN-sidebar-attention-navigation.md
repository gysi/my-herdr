# Sidebar attention navigation

Slug: ATTN

Status: **Completed** — all 265 automated tests passed; the user confirmed successful
navigation in grouped and priority views.

## Intended behavior

Normal `attention-next` cycling selects the row below the focused agent in the local sidebar.
`attention-prev` selects the row above it without urgency interruptions. Both wrap and follow
the latest grouped/priority order. Forward urgency keeps its existing blocked-before-done,
oldest-first rule and waiting-snapshot semantics.

## Design

- Grouped preserves agent-list response order; priority uses descending status rank and sequence,
  preserving grouped order for ties. Urgency's natural-ID tie breaker remains independent.
- The invoking agent anchors navigation. Outside the agent list, use the saved destination;
  without a valid destination, next starts at the top and previous at the bottom.
- Read local session preferences using herdr 0.9.1's client-socket-path hash and state-directory rules.
  Derive `<API filename stem>-client.sock` from `HERDR_SOCKET_PATH` before hashing.
  Fall back to the configured sort scalar, then grouped. No user settings are written.
- The Python 3.9 standard-library config reader handles a quoted `agent_panel_sort` under `[ui]`
  or root `ui.agent_panel_sort`, comments, and unrelated multiline strings. It is not a general
  TOML parser and does not support inline tables.
- Preserve `attention-next.json` and update its destination and waiting snapshot only after
  successful focus. Neither direction records failed jumps.
- Exact matching targets a single local client with the standard grouped/priority view.
  Remote clients, divergent simultaneous clients, and custom agent views are outside scope.

## Implementation and verification

- [x] Extract shared navigation and add the previous action and manifest entry.
- [x] Read local preferences and implement grouped/priority sidebar ordering.
- [x] Preserve forward urgency and support current-focus anchors in both directions.
- [x] Add isolated preference, traversal, error, and mock dispatcher tests.
- [x] Update README, research, changelog, and plugin version to 0.5.1.
- [x] Run `make check` (Ruff, syntax, manifest, and unit/mock end-to-end tests).
- [x] With the user, verify grouped sidebar navigation.
- [x] Verify the preference filename against herdr's client socket and add fixed-path regression tests.
- [x] With the user, verify navigation in priority view after correcting preference discovery.
- [x] Verify previous and alternating directions through automated tests and the user's live check.
- [x] Verify manual focus anchoring through automated tests.

## Follow-up

- Revisit the internal preference reader when herdr exposes the invoking client's sidebar order
  through an official API.
