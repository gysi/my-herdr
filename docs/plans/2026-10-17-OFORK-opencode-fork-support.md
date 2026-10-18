# OpenCode fork support

Slug: OFORK
Status: **Completed**

## Goal and scope

Support OpenCode in `fork-tab` and `fork-tab-ask`, alongside Claude Code and Codex. Target the
latest releases of all supported agents for testing and maintenance. Older versions may still
work, but are not tested or actively supported; no legacy compatibility code is maintained.
Attention navigation and pane moving are already agent-independent.
Keep Python 3.9+ and standard-library-only runtime requirements.

## Design

- Require herdr's OpenCode integration to report a native session ID for the source pane.
  Never install integrations automatically.
- OpenCode forks through its session API and launches the new session with
  `opencode --session <fork-id>`; resuming the source ID
  is not a fork.
- Use `opencode api` for service discovery and authentication rather than reading its database
  or constructing unauthenticated HTTP calls. Check the version before mutations.
- Keep all OpenCode-specific subprocess and response handling inside the forking feature.
  Tests mock every external command; no test contacts a live service.
- Select small Claude Code, Codex, and OpenCode adapter modules through one registry.
  Adapters own missing-session guidance, source validation/logging, fork preparation,
  launch arguments, and forwarded environment. Shared metadata checks stay in `agents.py`;
  tab creation, readiness, focus, and cleanup stay in `workflow.py`. Validation must not
  create a fork; only preparation may save an OpenCode fork, before tab creation.
- Preserve the existing Claude/Codex workflow and cleanup. Do not fold unrelated review fixes
  into this feature.
- Target the ordinary shared background service and herdr server environment. Custom source
  `--server`/`--standalone`, private-service defaults, and shell-only overrides are unsupported
  and not discovered. Do not put credentials or inline configuration in logged tab arguments.
- Validate the CLI/server major version and read the source's session location before either
  tab or popup creation. Use that location as the new tab's working directory.
- The current implementation uses OpenCode's V2 API and rejects incompatible API generations.
  This guard is not a permanent support promise for a particular major version, and it does
  not look up the latest release online. Exact versions belong in contract notes and tests;
  public descriptions and errors use the general latest-releases policy for every agent.
- Save the OpenCode fork before creating the tab; name it through the new session's title API. Never retry mutations or automatically delete saved forks. Log the new ID before naming or tab creation so subsequent failures remain recoverable. When naming, tab creation, or startup fails after saving, the error notification names the fork and its `opencode --session <fork-id>` resume command. A timeout may leave a saved fork without a known ID; document inspection before retrying.
- Update user documentation, the manifest version, changelog, and repository guidance together.

## Implementation and verification

- [x] Verify fork/get/update responses, CLI output, location, server selection, and integration.
- [x] Implement compatibility validation, fork creation, launch, environment handling, and errors.
- [x] Cover named/unnamed forks, incompatible API rejection, invalid/missing/conflicting session metadata,
  malformed responses, command failures/timeouts, and existing-agent regressions with mocks.
- [x] Document supported connection scope, requirements, naming, and failure behavior.
- [x] Bump version to 0.6.0 and update changelog, research, and agent guidance.
- [x] State the latest-releases support policy consistently in public descriptions and errors.
- [x] Refactor agent-specific behavior into registered adapter modules without behavior changes.
- [x] Cover adapter dispatch, validation/preparation separation, and existing-agent regressions.
- [x] Group agent contract notes under parallel Claude Code, Codex, and OpenCode subsections.
- [x] Run `make check` and review the adapter refactor and documentation changes.
- [x] Show the saved fork's resume command in errors after naming, tab creation, or startup fails.
- [x] With the user, smoke-test an unnamed OpenCode fork and verify distinct session identity. The action succeeded, the fork registered a different session ID, the source retained its ID, and the user confirmed automatic focus and conversation history.
- [x] With the user, smoke-test a named fork, source independence, and attention navigation.
  - [x] Named fork succeeded; the herdr tab label and saved OpenCode session title match the requested name, and the new pane reports the new session ID.
  - [x] User confirmed fork/source independence.
  - [x] User confirmed that `attention-next` and `attention-prev` work correctly with the OpenCode source and forks.
