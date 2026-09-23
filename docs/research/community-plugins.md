# Community herdr plugins: how they are built

> **Reference snapshot, not a maintained document.** A survey of other people's plugins as they
> looked while this one was being built. The repositories move on; treat every claim about them as
> "was true once", and check the repository itself before relying on it.

Research note from building **my-herdr**, a herdr plugin with no build step. It was first planned in Bash + jq and is written in Python (see the note at the top of §4).

- Checked against herdr **0.9.1**. The recommendations assume no extra tools: `fzf`, `shellcheck`, `bats` and `gum` are not required.
- Sources: shallow clones of the repos in §1, the official docs at https://herdr.dev/docs/plugins/ and https://herdr.dev/docs/marketplace/, and `herdr <cmd> --help` on 0.9.0.
- License: every repo quoted below is **MIT** unless noted. Two repos have **no LICENSE** (`ogulcancelik/herdr-plugin-examples`, `third774/herdr-last-workspace`), so describe what they do but don't copy their code. Keep attribution when copying MIT snippets (a `# Adapted from <repo>/<path> (MIT)` comment is enough).

---

## 0. TL;DR for the implementer

1. **Actions run headless.** They have no TTY and run detached, with cwd = plugin root. Anything interactive (fzf, `read`) has to run in a **plugin pane**, usually `placement = "popup"`, which the action opens with `herdr plugin pane open --entrypoint X --env K=V ...`. Every picker/prompt plugin studied uses this two-stage pattern: drovr, command-palette, catchup, herdr-plus, agent-handoff and plugin-manager.
2. **Getting the focused pane.** Use `HERDR_PANE_ID`, then fall back to `HERDR_PLUGIN_CONTEXT_JSON.focused_pane_id`, then `herdr pane current`. Get the Claude session id from `herdr agent get <pane>` (or `pane get`) at `.result.agent.agent_session.value`, where `kind == "id"`. This needs `herdr integration install claude`.
3. **Forking.** The cleanest recipe is t4t5/herdr-forkr: `herdr tab create --workspace W --cwd C --focus`, then wait until the new pane's shell is idle, then `herdr agent start <unique-name> --kind claude --pane P --timeout 60000 -- --resume <id> --fork-session`. herdr then tracks the fork as a normal agent.
4. **Moving a pane to a new tab.** Use one call: `herdr pane move <pane> --new-tab --workspace <ws> [--label NAME] --no-focus`, then focus `.result.move_result.pane.tab_id`. Pattern from drovr.
5. **Errors.** Stdout and stderr only reach `herdr plugin log list --plugin <id>`. Show failures with `herdr notification show "<title>" --body "<msg>"`. In popups, wait for Enter before exiting so the message stays visible.
6. **Keybindings are not declared in the manifest.** Document `[[keys.command]] type = "plugin_action"` blocks for `~/.config/herdr/config.toml` in the README.
7. **Tests.** No studied Bash plugin uses bats. They all use a hand-rolled harness plus a **fake `herdr` script** that logs argv and serves JSON fixtures, with `HERDR_BIN_PATH` pointed at it. Add `bash -n` and `shellcheck -x`.

---

## 1. Landscape and popularity

The marketplace (https://herdr.dev/plugins/) indexes public repos with the `herdr-plugin` topic (around 1,200 at the time of writing). The most-starred ones (terminal-browser 3k, terminal-code 2k, crabbox 1.4k, collie 1k, zoetrope 0.9k) are **standalone apps** that carry the topic, not typical plugins. The actual plugins studied here:

| Repo | ★ | Runtime | Build step | Relevance |
|---|---|---|---|---|
| cloudmanic/herdr-plus | 318 | Go binary | `[[build]]` sh/go | Multi-tool plugin structure |
| kryptamine/herdr-auto-title | 156 | Go | `go build` | `[[startup]]` long-running process, release-please |
| thanhdat77/herdr-navigator | 154 | Rust | `cargo build` | overlay picker + side pane |
| qu8n/herdr-automatic-rename | 86 | **Bash + jq** | none | Largest Bash plugin: events, tests, shellcheck CI, releases |
| robbyrussell/herdr-ohmyzsh | 70 | zsh | `[[build]]` zsh link | Shell plugin, mock herdr tests, CI |
| JanTvrdik/herdr-command-palette | 38 | **Bash + jq + fzf** | none | Minimal action → overlay → fzf |
| speardragon/herdr-plugin-manager | 36 | **Bash** (+python3) | none | Popup TUI in bash, line-input helper, tests |
| Crokily/herdr-lazygit | 33 | Bash + python | downloads runtime | pane-cwd pitfall notes |
| speardragon/herdr-yazi | 28 | Bash one-liners in manifest | build = dependency check | Tiny manifest-only plugin |
| Tyru5/herdr-floax | 25 | Rust + Bash toggle | `cargo build` | Toggle pattern, keybinding installer |
| AVGVSTVS96/herdr-drovr | 18 | Node ≥23 (TS type stripping) | none | **Moves panes/tabs**, popup + fzf |
| sanirudh17/herdr-agent-handoff | 17 | Node | none | Popup pickers, `setup-keys` action |
| wilbeibi/herdr-catchup | 9 | **Bash** (sed, no jq) | none | Session id lookup, popup/split, config.env |
| calebcauthon/herdr-agent-copy-paste-fork | 2 | **Bash + jq** | none | Fork via plugin pane + `--env`, tests |
| dmangla3/herdr-fork-from-message | 2 | Python 3.10+ | none | Very defensive fork, cleanup on failure, CI |
| t4t5/herdr-forkr | 1 | **POSIX sh + jq** | none | **Best minimal fork recipe** (132 lines) |

Also useful: `ogulcancelik/herdr-plugin-examples` (the official cookbook, no license), which has subdirectory plugins including a Bash link handler (`github-link-preview`).

---

## 2. Official contract (herdr docs, "Latest 0.9.1")

Summary of https://herdr.dev/docs/plugins/:

- **Required top-level keys:** `id`, `name`, `version`, `min_herdr_version`. `description` is optional. Also set `platforms`, because local plugins without it link with a warning.
- **Plugin id** charset: ASCII letters, digits, `.` `:` `_` `-`. **Action, pane and link-handler ids** use the same set **without dots**, and each must be unique within its kind. Actions are qualified as `<plugin.id>.<action-id>`.
- **`command` is an argv array with no shell.** For expansion, wrap it in `["bash", "-c", "..."]`.
- **Sections:** `[[build]]` runs only on `plugin install` from GitHub, not on `link`, and gets no runtime env. `[[startup]]` is one-shot after the session restores. Also available: `[[actions]]` (`id`, `title`, `description`, `contexts`, `command`, `platforms`), `[[events]]` (`on = "tab.created"` etc.), `[[panes]]` (`id`, `title`, `placement`, `width`, `height`, `command`) and `[[link_handlers]]`.
- **Runtime env:** `HERDR_SOCKET_PATH`, `HERDR_BIN_PATH`, `HERDR_ENV=1`, `HERDR_PLUGIN_ID`, `HERDR_PLUGIN_ROOT`, `HERDR_PLUGIN_CONFIG_DIR`, `HERDR_PLUGIN_STATE_DIR` and `HERDR_PLUGIN_CONTEXT_JSON` are always set. `HERDR_WORKSPACE_ID`, `HERDR_TAB_ID` and `HERDR_PANE_ID` are set when available. Actions also get `HERDR_PLUGIN_ACTION_ID`. Events get `HERDR_PLUGIN_EVENT` and `HERDR_PLUGIN_EVENT_JSON`. Panes get `HERDR_PLUGIN_ENTRYPOINT_ID`. Link handlers get `HERDR_PLUGIN_CLICKED_URL` and `HERDR_PLUGIN_LINK_HANDLER_ID`.
- **Runtime commands run with cwd = plugin dir.** Don't store state in `HERDR_PLUGIN_ROOT`, because GitHub installs are managed checkouts. Use `HERDR_PLUGIN_CONFIG_DIR` for user config and `HERDR_PLUGIN_STATE_DIR` for runtime state.
- **Pane placements:** the default is `overlay` (temporary zoomed view that restores focus). Others are `popup` (session-modal, `width`/`height` as cells or `"80%"`), `split`, `tab` and `zoomed`. A popup **is not a pane**: it has no `HERDR_PANE_ID` and is not visible to the pane or agent APIs, but the underlying pane is still in `HERDR_PLUGIN_CONTEXT_JSON`. Opening a popup returns `ui_busy` while another herdr modal is open.
- **Keybindings** go in the user's config:
  ```toml
  [[keys.command]]
  key = "prefix+l"
  type = "plugin_action"
  command = "example.layout.apply"
  description = "apply layout"
  ```
- **Dev loop:** `herdr plugin link .`, `herdr plugin action list --plugin ID`, `herdr plugin action invoke ID.action`, `herdr plugin pane open --plugin ID --entrypoint X`, `herdr plugin log list --plugin ID`, `herdr plugin config-dir ID`. There is no `plugin update` in v1: reinstall instead.
- **`min_herdr_version`:** herdr refuses to link or install when this is newer than the running binary. qu8n notes it is also re-checked on every event dispatch (`plugin_requires_newer_herdr`).

**Marketplace listing** (https://herdr.dev/docs/marketplace/):

- The repo must be **public**, tagged with the **`herdr-plugin`** topic, and have at least one `herdr-plugin.toml` with parseable required metadata on the **default branch**, at the root or in subdirectories. There is one card per repo.
- The index refreshes every 30 minutes and rescans when the default-branch HEAD changes.
- Forks, archived repos and malformed manifests are excluded. The card shows repo description, stars, language, last push, and each manifest's name and version.
- Installing uses `herdr plugin install owner/repo[/subdir]`.

`HERDR_PLUGIN_CONTEXT_JSON` fields seen in code (herdr-plus `context_test.go`, catchup, fork-from-message): `workspace_id`, `workspace_label`, `workspace_cwd`, `tab_id`, `tab_label`, `focused_pane_id`, `focused_pane_cwd`, `focused_pane_agent`, plus `invocation_source`, `clicked_url` and `link_handler_id` for link clicks. Example from herdr-plus tests:

```json
{"workspace_id":"w3","workspace_label":"herdr-plus","workspace_cwd":"/ws","tab_id":"w3:t1","tab_label":"shell","focused_pane_id":"w3:p2","focused_pane_cwd":"/Users/spicer/code","focused_pane_agent":"claude"}
```

---

## 3. Per-repo findings

### 3.1 AVGVSTVS96/herdr-drovr (moves panes/tabs): most relevant for "move pane"

- **Manifest** (verbatim):
  ```toml
  id = "drovr"
  name = "drovr"
  version = "0.4.8"
  min_herdr_version = "0.7.4"
  description = "Drive your herd: move the focused tab or pane, live agents included, anywhere with an fzf picker."
  platforms = ["linux", "macos"]

  # Headless; invoked by keybindings (see README).
  [[actions]]
  id = "move-tab"
  title = "Move tab to workspace…"
  contexts = ["tab"]
  command = ["node", "--import", "./compile-cache.js", "open-picker.ts", "tab"]

  [[actions]]
  id = "move-pane"
  title = "Move pane to tab…"
  contexts = ["pane"]
  command = ["node", "--import", "./compile-cache.js", "open-picker.ts", "pane"]

  # Keep direct opens consistent with the action-launched picker.
  [[panes]]
  id = "picker"
  title = "drovr"
  placement = "popup"
  width = 64
  height = 28
  command = ["node", "--import", "./compile-cache.js", "pick-and-move.ts"]
  ```
- **Layout:** flat. `open-picker.ts` is the headless action and `pick-and-move.ts` runs in the popup. There is also `test.ts`, and `package.json` holds dev-only typescript. It needs Node ≥23 for native type stripping, so there is no build step.
- **Context:** `HERDR_BIN_PATH || "herdr"`, `HERDR_PLUGIN_ID || "drovr"`, `HERDR_PANE_ID`, falling back to `herdr pane list` → `.result.panes[] | select(.focused)`.
- **Handoff to popup:** `herdr plugin pane open --plugin drovr --entrypoint picker --width 64 --height 28 --env DROVR_MODE=pane --env DROVR_PANE=<id>`.
- **Input:** fzf runs **inside the popup** (it draws on `/dev/tty`, with candidates on stdin). It uses `--print-query` so typed text becomes the new tab name, `--expect alt-d` for split-down, `--disabled` with a `change:reload(...)` search script, and a `ctrl-t` toggle for cross-workspace scope. Styling uses ANSI palette numbers only, so the popup inherits the herdr theme.
- **The actual move calls:**
  - Pane into an existing tab: `pane move <pane> --tab <tab_id> --split right|down --no-focus`
  - Pane into a **new tab**: `pane move <pane> --new-tab --workspace <src_ws> [--label <name>] --no-focus`
  - Pane into a new workspace: `pane move <pane> --new-workspace [--label <name>] --no-focus`
  - Tab move: rebuild the layout tree from `pane layout --pane X` rects, then one `pane move --new-tab/--new-workspace` for the anchor and one `pane move --tab T --split DIR --target-pane P --ratio R` per split.
  - Check `.result.move_result.changed`. Then `workspace focus <ws>` and `tab focus <tab>` from `.result.move_result.pane`, treating focus as best effort.
- **Robustness:** re-validates that the source pane is still in the same tab after the picker closes, because other agents may have changed the layout. The README says: "If a move leaves the source tab or workspace empty, herdr closes it."
- **Errors:** `keepPickerOpenUntilEnter(msg)` prints and blocks on stdin so the popup doesn't vanish. fzf exit 1 or 130 is treated as a silent cancel.
- **README sections:** Features, Requirements, Install (with the keybinding TOML), Usage (key table), How it works, Development, License.
- **Suggested keys:** `prefix+M` → `drovr.move-tab`, `prefix+m` → `drovr.move-pane`.
- **Tests:** `npm test` runs `tsc --noEmit` and then `node test.ts`, which is pure-function tests (layout tree, picker parsing). No CI workflow. Version in manifest and package.json. MIT.

### 3.2 t4t5/herdr-forkr: best minimal fork recipe (POSIX sh + jq)

- **Manifest** (key parts):
  ```toml
  id = "forkr"
  name = "forkr"
  version = "0.1.0"
  min_herdr_version = "0.8.0"
  description = "Fork the focused agent's conversation into a new tab, split, or workspace and keep the original running. Claude Code, Codex, Pi, OpenCode."
  platforms = ["linux", "macos"]

  # Headless actions: bind them to keys (see README) or use the pane menu.
  [[actions]]
  id = "tab"
  title = "Fork conversation into a new tab"
  description = "Copy the focused pane's agent conversation into a new tab in this workspace"
  contexts = ["pane"]
  command = ["sh", "forkr.sh", "--tab"]
  # ... "split" (--split right), "split-down" (--split down), "workspace" (--workspace)
  ```
- **Layout:** one script, `forkr.sh`, plus README and LICENSE. Several actions share one script and differ only in argv flags. Headless, with no panes.
- **Session id:** `herdr agent get <pane>` → `.result.agent.{agent, pane_id, workspace_id, foreground_cwd, cwd, agent_session.kind, agent_session.value}`. If there is no session, the error tells the user to run `herdr integration install <kind>`.
- **Launch:** create the destination (`tab create` / `pane split` / `workspace create`, reading `.result.root_pane.pane_id` or `.result.pane.pane_id`), then **poll `pane process-info` until the only foreground process is the shell**, then `herdr agent start "forkr-$$" --kind claude --pane P --timeout 60000 -- --resume ID --fork-session`, then `agent rename P --clear` so the sidebar shows the agent's own title. `agent_not_ready` is tolerated, because a trust or hook prompt still leaves a usable pane.
- **Errors:** `notify()` and `fail()` both send a herdr toast and print to stderr, because "plugin actions run detached". `-h` prints the header comment as help. Also usable as a plain script (`sh forkr.sh --tab [pane-id]`).
- **README:** intro with agent → command table; How it works (4 numbered steps); Requirements; Install (`herdr plugin install` or `link`); Bind keys; Actions table; From a script; Notes (caveats); Related plugins; Development (`link`, `action list`, `log list`, `sh -n`); License.
- **Suggested keys:** `prefix+f` → `forkr.tab`, `prefix+shift+f` → `forkr.split`.
- **Tests/CI:** none. MIT.

Verbatim code worth copying (t4t5/herdr-forkr `forkr.sh`, MIT):

```sh
herdr=${HERDR_BIN_PATH:-herdr}

notify() {
  "$herdr" notification show "forkr" --body "$1" --sound "${2:-none}" >/dev/null 2>&1
}

fail() {
  notify "$1" request
  printf 'forkr: %s\n' "$1" >&2
  exit 1
}
```

```sh
# Target: explicit argument, else the pane herdr says is focused.
if [ -z "$target" ] && [ -n "${HERDR_PLUGIN_CONTEXT_JSON:-}" ]; then
  target=$(printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -r '.focused_pane_id // empty')
fi
[ -n "$target" ] || target=${HERDR_PANE_ID:-}
[ -n "$target" ] || target=$("$herdr" pane current 2>/dev/null | jq -r '.result.pane.pane_id // empty')
[ -n "$target" ] || fail "no focused pane"

info=$("$herdr" agent get "$target" 2>/dev/null) || fail "no agent running in $target"
field() { printf '%s' "$info" | jq -r ".result.agent.$1 // empty"; }
```

```sh
# A brand-new pane may still be starting its shell, and agent start refuses
# a pane that is not at an interactive prompt. Wait (up to 10s) until the
# only foreground process is the shell itself.
i=0
while [ $i -lt 50 ]; do
  ready=$("$herdr" pane process-info --pane "$new_pane" 2>/dev/null | jq -r '
    .result.process_info
    | if (.foreground_processes | length) == 1
         and (.foreground_processes[0].pid == .shell_pid
              or (.foreground_processes[0].name | test("^(zsh|bash|fish|sh|dash|ksh|nu)$")))
      then "yes" else "no" end' 2>/dev/null)
  [ "$ready" = yes ] && break
  i=$((i + 1))
  sleep 0.2
done

# agent start needs a unique name; clear it afterwards so the sidebar keeps
# the agent's own title. A blocked startup (trust prompt, hook approval)
# still leaves a usable pane, so only other failures are reported.
err=$("$herdr" agent start "forkr-$$" --kind "$kind" --pane "$new_pane" --timeout 60000 -- "$@" 2>&1 >/dev/null)
status=$?
"$herdr" agent rename "$new_pane" --clear >/dev/null 2>&1
if [ $status -ne 0 ] && ! printf '%s' "$err" | grep -q agent_not_ready; then
  fail "$kind did not start in $new_pane: $err"
fi
```

### 3.3 calebcauthon/herdr-agent-copy-paste-fork (Bash + jq, with tests)

- **Manifest:** `id = "herdr-plugins.fork"`, `version = "0.3.0"`, `min_herdr_version = "0.7.5"`, `platforms = ["linux","macos"]`. Actions: `fork` (`["bash","scripts/fork.sh","--placement","tab"]`), `fork-split` (`--placement split --direction right`), `copy` and `paste`, each with `contexts = ["pane","workspace"]`. There is one pane, `session` (`placement = "tab"`, `["bash","scripts/launch.sh"]`), and the placement is overridden per open.
- **Layout:** `scripts/common.sh` is a sourced helper library, with one script per action in `scripts/`, plus `tests/run.sh`.
- **Session id:** `herdr pane get <pane>`, then a jq recursive search `[.. | objects | .agent_session? // empty | select(type=="object")][0]` so it tolerates schema nesting. It uses `.value`, `.agent` and `foreground_cwd`.
- **Launch:** unlike forkr, it opens a **plugin pane** (`plugin pane open --entrypoint session --env HERDR_FORK_AGENT=... --env HERDR_FORK_VALUE=... --env HERDR_FORK_CWD=... <placement flags>`). `launch.sh` then `cd`s and runs `claude --resume V --fork-session` under a Python PTY recorder. When claude exits it falls back to a login shell (`exec "$SHELL" -i -l`) so the tab doesn't close. forkr's README notes the tradeoff: a wrapper process means herdr doesn't see a plain agent pane in the same way.
- **Copy/paste:** writes `{agent,value,cwd}` to `$HERDR_PLUGIN_STATE_DIR/clipboard.json` (mode 0600). `paste` runs `herdr pane run <pane> "<cmd>"`, which submits text plus Enter.
- **Errors:** stderr message plus `notify` (a best-effort toast). Opt-in debug with `HERDR_FORK_DEBUG=1`, which appends to `$TMPDIR/herdr-fork-debug.log`.
- **Tests:** `tests/run.sh` builds stub `herdr`, `claude` and `codex` executables in `tests/.tmp/bin`. The stub `claude` records argv and PWD; the stub `herdr` serves `pane get` JSON and records `plugin pane open` argv. It asserts the argv. The README Development section: `bash tests/run.sh`, `bash -n scripts/*.sh`, `shellcheck -x scripts/*.sh tests/run.sh`. No CI.
- **README** is very complete: Requirements, Install, Bind your key, What it declares (table), How it works, Configuration and state, Failure behavior, Notes and caveats, Development, Logs and cleanup, Security summary.
- **Suggested keys:** `prefix+f`, `prefix+shift+f`, `prefix+c`, `prefix+v`. It warns that **`prefix+c` is herdr's default `new_tab`**.
- **Inconsistency:** a `fork.sh` comment says it deliberately does NOT pass `--cwd`, because a relative pane command would break, but the README says it does. The lesson: pane commands should use `$HERDR_PLUGIN_ROOT` so `--cwd` is safe (see §5).

Verbatim (calebcauthon `scripts/common.sh`, MIT):

```bash
# Resolve the pane the action was invoked from. Prefer the explicit env var,
# then fall back to the several shapes the context JSON can take.
resolve_pane_id() {
  local pane ctx
  pane="$(printf '%s' "${HERDR_PANE_ID:-}" | tr -d '[:space:]')"
  if [ -n "$pane" ]; then
    printf '%s' "$pane"
    return 0
  fi

  ctx="${HERDR_PLUGIN_CONTEXT_JSON:-}"
  if [ -n "$ctx" ] && have_jq; then
    pane="$(printf '%s' "$ctx" | jq -r '
      .focused_pane_id
      // .pane_id
      // .focused_pane.pane_id
      // .pane.pane_id
      // .context.pane_id
      // empty' 2>/dev/null || true)"
    pane="$(printf '%s' "$pane" | tr -d '[:space:]')"
    if [ -n "$pane" ]; then
      printf '%s' "$pane"
      return 0
    fi
  fi

  return 1
}

# Durable location for the fork clipboard. copy.sh writes it; paste.sh reads it.
# Herdr supplies HERDR_PLUGIN_STATE_DIR at runtime; fall back for local tests.
state_dir() {
  printf '%s' "${HERDR_PLUGIN_STATE_DIR:-${TMPDIR:-/tmp}/herdr-fork-state}"
}
```

The action script header pattern (`scripts/fork.sh`):

```bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
. "$here/common.sh"
```

### 3.4 dmangla3/herdr-fork-from-message (Python, most defensive)

- **Manifest:** `id = "dmangla3.fork-from-message"`, `version = "0.3.0"`, `min_herdr_version = "0.8.0"`. Actions: `fork` (tab), `fork-pane` and `fork-workspace`, all `contexts = ["pane"]` and `["python3","scripts/fork_from_message.py","--destination",...]`.
- **Session id:** `herdr pane get <focused_pane_id>`. It **validates trust**: `agent_session.agent == kind`, `kind == "id"`, `source == "herdr:<kind>"`, and a canonical UUID value. It also checks that the pane and workspace still match the context (the focus may have moved).
- **Launch:** `tab create --workspace W --cwd C --label "Fork · <tab_label>" [--env CLAUDE_CONFIG_DIR=...] --no-focus`. It **forwards `CLAUDE_CONFIG_DIR` / `CODEX_HOME`** into the new tab (useful when running multiple Claude accounts). Then `agent start <kind>_fork_<uuid12> --kind claude --pane P --timeout 45000 -- --resume ID --fork-session`, retrying on `agent_pane_busy` for up to 8 seconds. Then `agent read P --source detection --lines 40` to detect blocked startup, then `agent send-keys P esc esc` to open Claude's rewind picker, and finally `tab focus`.
- **Cleanup:** if anything fails after creating the tab, it runs `tab close <id>` so no half-done tab is left behind.
- **Errors:** a `ForkError` with an actionable message, then `notification show "<title> failed" --body "<msg> Logs: herdr plugin log list --plugin <id> --limit 5" --sound request`. Refuses to run unless `HERDR_ENV == "1"`. Prints a JSON result on success.
- **Tests/CI:** `scripts/check.sh` (unittest plus compile check). GitHub Actions matrix: ubuntu with py3.10/3.14 and macOS py3.14, `permissions: contents: read`, `timeout-minutes: 5`. Also has CHANGELOG, CONTRIBUTING and SECURITY. The README has a CI badge and a dependency version table.

### 3.5 wilbeibi/herdr-catchup (Bash, no jq)

- **Manifest** (key parts): `id = "wilbeibi.catchup"`, `min_herdr_version = "0.7.5"` (with a comment explaining which API needs it). Actions `summary`, `fork`, `handoff`, `send` and `ask` all use `["bash","bin/run.sh","<mode>"]` with `contexts = ["pane","workspace"]`. There is a matching `[[panes]]` per mode:
  ```toml
  [[panes]]
  id = "send"
  title = "catchup: send"
  placement = "popup"
  width = "70%"
  height = 20
  command = ["bash", "-c", "exec bash \"$HERDR_PLUGIN_ROOT/bin/run.sh\" --in-pane send"]

  # fork and handoff launch an agent, and an agent must be a real pane: a popup
  # has no pane id and stays outside every pane and agent API, so herdr would
  # never see the agent that was just started.
  [[panes]]
  id = "fork"
  title = "catchup: fork"
  placement = "split"
  command = ["bash", "-c", "exec bash \"$HERDR_PLUGIN_ROOT/bin/run.sh\" --in-pane fork"]
  ```
- **Single dispatcher script with roles:** `run.sh <mode>` is the headless action, `run.sh --in-pane <mode>` runs inside the pane, and `run.sh worktree-created` is the event hook.
- **Context:** `: "${HERDR_BIN_PATH:?...}"`. Reads `focused_pane_cwd` (then `workspace_cwd`), `focused_pane_id` and `focused_pane_agent` from context JSON using `sed` (deliberately avoids a jq dependency). Session id comes from `herdr agent get`.
- **Passing data:** always per-pane via `--env`, never through shared files, with the comment "a shared file would be a race between two herdr sessions".
- **Interactive input:** Bash `select` menus inside popup/split panes (`PS3="agent> "`). `hold_open` does `printf '\n[press Enter to close]'; read -r`.
- **Placement quirks** (documented in code):
  - `--target-pane` is only accepted for split/zoomed. herdr rejects it for overlay and popup.
  - To get the popup, **pass no `--placement`**, because "the CLI's `--placement` does not accept it, and the manifest is the authority when the request is silent". herdr 0.9.0 `plugin pane open --help` indeed lists only `overlay, split, tab, zoomed`.
- **Config:** `$HERDR_PLUGIN_CONFIG_DIR/config.env` with `key = value` lines, parsed with `sed`. Every key is optional, and herdr creates the directory.
- **README:** one-line install first, Actions table, Configuration, Agent support table, How it works, Limits and non-goals, Alternatives table, Local development, Ideas, License. It notes: "No pane at all? The failure happened before the pane existed. It's in `herdr plugin log list`." It also notes that **herdr plugin actions take no parameters**, so per-variant behaviour needs separate action ids or config.
- **Suggested keys:** `prefix+c` summary, `prefix+f` fork, `prefix+h` handoff, `prefix+r` ask. No tests or CI.

Verbatim `cfg()` (wilbeibi/herdr-catchup `bin/run.sh`, MIT):

```bash
cfg() {
  local dir="${HERDR_PLUGIN_CONFIG_DIR:-}"
  [ -n "$dir" ] && [ -f "$dir/config.env" ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*\([^#]*\).*/\1/p" "$dir/config.env" \
    | sed -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/" \
    | tail -n1
}
```

### 3.6 cloudmanic/herdr-plus: multi-tool plugin structure (Go)

- **Manifest:** a long commented header. `id = "cloudmanic.herdr-plus"`, `version = "0.1.24"` ("Kept in sync with internal/version/version.go by .github/workflows/release.yml"), `min_herdr_version = "0.7.0"`, `platforms = ["linux","macos","windows"]`. `[[build]]` runs `sh scripts/build.sh`, which uses local Go or downloads a release binary.
- Each tool is a **subcommand of one binary**: `projects`, `projects-ui`, `quick-actions`, `quick-actions-ui`, `ping`, `on-worktree`. Every **action X has a companion pane X-ui/picker**: the action opens it via `plugin pane open --placement <cfg> --env HERDR_PLUS_CTX=<base64 json>`.
- Has a **`ping` smoke-test action**: "talks to herdr over the socket and prints the focused pane/workspace. Its output is captured in `herdr plugin log list`". A cheap first action worth copying.
- `[[events]]` on `worktree.created` and `worktree.opened` both route to one idempotent handler.
- Config lives in `~/.config/herdr-plus/...` and in the plugin config dir, with per-picker placement overridable (`[quick_actions] placement = "split"`), and falls back on invalid values.
- Quick-action types: `command`, `select` (second fuzzy list) and `form` (typed value → `{{.Value}}`). This is the herdr-plus equivalent of "ask for input". Context is exported to commands as `HERDR_PLUS_*` env vars.
- **Tests/CI:** Go unit tests including **`manifest_test.go`, which parses `herdr-plugin.toml`** and asserts platform coverage. `test.yml` runs build, vet and `go test -race` on ubuntu and macOS. Also `release.yml` with goreleaser, a Homebrew formula in-repo, and `site.yml`.
- **README:** Install, Configuration, one section per tool (Projects, Quick Actions, Worktree auto-layout), Binding a key (`prefix+up` / `prefix+down`), Building.

### 3.7 robbyrussell/herdr-ohmyzsh (shell-based)

- **Manifest** (verbatim):
  ```toml
  id = "ohmyzsh.shell"
  name = "Oh My Zsh"
  version = "0.1.0"
  min_herdr_version = "0.8.0"
  description = "Know when the slow command finished, reload Oh My Zsh in every idle pane with one key, and short names for splits, tabs, agents and worktrees"
  platforms = ["macos", "linux"]

  # Links this checkout into $ZSH_CUSTOM/plugins/herdr so `plugins=(... herdr)`
  # picks it up. Prints instructions instead of failing when Oh My Zsh is absent.
  [[build]]
  command = ["zsh", "bin/install-zsh-plugin"]

  [[actions]]
  id = "reload-all"
  title = "Reload Oh My Zsh in idle panes"
  contexts = ["workspace"]
  command = ["zsh", "bin/reload-all"]

  [[actions]]
  id = "install"
  title = "Link the zsh plugin into Oh My Zsh"
  contexts = ["workspace"]
  command = ["zsh", "bin/install-zsh-plugin"]
  ```
- **Layout:** `bin/<action>` executables without extensions, `herdr.plugin.zsh` (the shell-side part), `tests/{lib.zsh,run.zsh,test_*.zsh,mocks/herdr}`.
- `reload-all` iterates `pane list`, skips panes with an agent, uses `pane process-info` to confirm only the shell is in the foreground, runs `pane run <id> "omz reload"`, and ends with a summary toast. It has a `--dry-run` flag and parses JSON with zsh regex, not jq.
- **Tests:** fake `herdr` (below) and zsh assertion helpers `check`, `check_match`, `check_contains`, `check_lacks`.
- **CI** `tests` workflow: ubuntu and macOS, install zsh, `zsh -n` / `bash -n` syntax check, run tests.

Verbatim mock (robbyrussell/herdr-ohmyzsh `tests/mocks/herdr`, MIT). This is the template for our own:

```bash
#!/usr/bin/env bash
# Fake `herdr` CLI for the test suite.
#
# Every invocation is appended, space-joined, to $HERDR_MOCK_LOG so tests can
# assert exactly which calls the plugin made. Read-only queries are answered
# from fixture files in $HERDR_MOCK_DIR; a missing fixture yields a valid but
# empty response, the same way a real herdr degrades.
dir="${HERDR_MOCK_DIR:?HERDR_MOCK_DIR unset}"
log="${HERDR_MOCK_LOG:?HERDR_MOCK_LOG unset}"
printf '%s\n' "$*" >>"$log"

serve() { cat "$dir/$1" 2>/dev/null || printf '%s\n' "$2"; }
mutate() { [ "${HERDR_MOCK_FAIL:-0}" = 1 ] && exit 1; printf '{"result":{}}\n'; }

case "${1:-} ${2:-}" in
  "--version "|"-V ")   printf 'herdr %s\n' "${HERDR_MOCK_VERSION:-0.8.0}" ;;
  "pane list")          serve panes.json '{"result":{"panes":[]}}' ;;
  "pane get")           serve "pane_${3//:/-}.json" '{"result":{"pane":{}}}' ;;
  "pane current")       serve current.json '{"result":{"pane":{"focused":false}}}' ;;
  "pane split")         serve split.json '{"result":{"pane":{"pane_id":"w1:p9"}}}' ;;
  "pane process-info")
    shift 2; id=""
    while [ $# -gt 0 ]; do
      case "$1" in --pane) id="$2"; shift 2 ;; *) shift ;; esac
    done
    serve "procinfo_${id//:/-}.json" '{"result":{"process_info":{}}}' ;;
  "pane run"|"pane report-agent"|"pane release-agent"|"notification show"|"agent start"|"tab create"|"worktree create")
    mutate ;;
  *) printf '{"result":{}}\n' ;;
esac
```

(Excerpt; the `completion zsh` line is omitted.)

### 3.8 speardragon/herdr-plugin-manager (bash popup TUI)

- **Manifest** (verbatim):
  ```toml
  id = "ray.plugin-manager"
  name = "Plugin Manager"
  version = "0.4.0"
  min_herdr_version = "0.7.4"
  description = "Manage herdr plugins from a popup: list, install, update, enable/disable, uninstall, browse the marketplace, open repo in browser, edit plugins.json"
  platforms = ["macos", "linux"]

  [[panes]]
  id = "manager"
  title = "Plugin Manager"
  placement = "popup"
  width = 82
  height = 28
  command = ["bash", "-c", "exec bash \"$HERDR_PLUGIN_ROOT/bin/manager.sh\""]

  [[actions]]
  id = "open"
  title = "Open plugin manager"
  contexts = ["workspace"]
  command = ["bash", "-c", "exec \"${HERDR_BIN_PATH:-herdr}\" plugin pane open --plugin ray.plugin-manager --entrypoint manager --placement popup --focus"]
  ```
  The action is a **one-liner in the manifest**, with no script. It passes `--placement popup`, which contradicts catchup's note; see pitfalls.
- **Popup input lessons** (from `manager.sh` header):
  - "The herdr popup's stdin returns EOF from a timed read (`read -t`) when idle instead of blocking, so the main input read MUST be blocking."
  - Targets bash 3.2 (macOS). Uses `tput` for colours, `trap cleanup EXIT` to restore the cursor, and `HERDR_PM_DRY_RUN=1` to print mutating commands instead of running them.
  - `invoke_after_close.sh`: invoking another plugin action **from inside a popup fails for anything that opens UI** (`ui_busy` / "popup already open"). So it spawns a detached helper that waits for the popup pid to die, then invokes with retries.
  - herdr kills the pane's whole **process group** when the popup dies, so helpers that must survive need their own session (`perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV'`).
- **Tests:** `tests/run.sh` runs `tests/cases/*.sh` with stubs for `git`, `curl` and `herdr` in `tests/lib/stubs`, and fixtures, with no network. CI matrix: **bash 3.2 on macOS (`/bin/bash`) and bash 5 on Linux**, syntax check plus tests, plus a **PR job warning when `bin/` or the manifest changed without a `version` bump**.
- **README:** badges (herdr version, platform, deps), screenshot, Quick start with keybinding (recommends `prefix+p`), a keys table, English plus Korean. Has CHANGELOG, issue and PR templates.

Verbatim line-input helper (speardragon/herdr-plugin-manager `bin/manager.sh`, MIT). It is useful if we want an Esc-cancellable prompt in a popup; otherwise plain `read -r -p` is enough:

```bash
prompt_line() {
  local prompt="$1" buf="" k rest saved
  PROMPT_CANCELLED=0
  printf '\033[?25h%s' "$prompt"
  while true; do
    IFS= read -rsn1 k || { PROMPT_CANCELLED=1; break; }
    if [ -z "$k" ]; then
      break  # Enter
    elif [ "$k" = $'\e' ]; then
      rest=''
      if saved="$(stty -g 2>/dev/null)" && [ -n "$saved" ]; then
        stty -icanon -echo min 0 time 1 2>/dev/null
        rest="$(dd bs=6 count=1 2>/dev/null)"
        stty "$saved" 2>/dev/null
      else
        IFS= read -rsn1 -t 1 rest || true
      fi
      [ -z "$rest" ] && { PROMPT_CANCELLED=1; break; }
    elif [ "$k" = $'\x03' ]; then
      PROMPT_CANCELLED=1
      break
    elif [ "$k" = $'\x7f' ] || [ "$k" = $'\b' ]; then
      if [ -n "$buf" ]; then
        buf="${buf%?}"
        printf '\b \b'
      fi
    else
      buf+="$k"
      printf '%s' "$k"
    fi
  done
  printf '\033[?25l'
  REPLY="$buf"
}
```

Version-bump warning job (same repo, `.github/workflows/tests.yml`, MIT). The paths are adapted in §4.8.

```yaml
      - name: Warn when shipped files change without a version bump
        run: |
          base="origin/${{ github.base_ref }}"
          git fetch origin "${{ github.base_ref }}" --depth=1 --quiet
          changed="$(git diff --name-only "$base"...HEAD -- bin herdr-plugin.toml)"
          if [ -z "$changed" ]; then echo "no shipped files changed"; exit 0; fi
          version_of() { git show "$1":herdr-plugin.toml | sed -nE 's/^version = "(.*)"/\1/p'; }
          before="$(version_of "$base")"; after="$(version_of HEAD)"
          if [ "$before" = "$after" ]; then
            echo "::warning title=No version bump::bin/ changed but herdr-plugin.toml is still $after — bump it before or at merge."
          else
            echo "version $before -> $after"
          fi
```

### 3.9 JanTvrdik/herdr-command-palette (Bash + jq + fzf, ~140 lines)

- **Manifest:** `id = "jt.command-palette"`, action `open` (`contexts = ["workspace"]`, `["bash","open.sh"]`), and pane `palette` (`placement = "overlay"`, `["bash","-c","exec \"$HERDR_PLUGIN_ROOT/palette.sh\""]`). The manifest comments say: "its command is run by the herdr server WITHOUT a TTY, so it cannot run fzf itself", and "herdr 0.7 does NOT bind keys declared in a plugin manifest".
- **`open.sh`** forwards the origin cwd with `--cwd` so actions invoked from the overlay resolve the right repo. The overlay becomes the focused pane, which would otherwise change context.
- **`palette.sh`:** `herdr plugin action list | jq ... @tsv | fzf --with-nth=2`, then `plugin action invoke <id>`. Because **invoke is fire-and-forget** (exit 0 only means dispatched), it polls `plugin log list --plugin P` for the returned `log_id` until `succeeded` or `failed`, and shows stderr on failure.
- **Errors:** `die()` prints and waits for a key so the overlay doesn't vanish.
- **README:** short. Requirements, Install, Bind a key (`prefix+p`), How it works (4 steps), License. No tests or CI.

Verbatim (JanTvrdik/herdr-command-palette `palette.sh`, MIT):

```bash
# Brief pause + message helper so failures don't vanish when the overlay closes.
die() {
  printf '%s\n' "$*" >&2
  printf 'Press any key to close…' >&2
  read -r -n1 _ 2>/dev/null || sleep 2
  exit 1
}
```

### 3.10 thanhdat77/herdr-navigator (Rust)

- **Manifest:** `[[build]] cargo build --release`. Actions `open`, `open-side` and `jump-back` (`contexts = ["workspace","global"]`) run `./target/release/herdr-navigator <sub>`. Panes: `picker` (overlay) and `picker-side` (split, "Title must stay in sync with SIDE_PANE_LABEL"). The toggle finds its own pane by label.
- **Releases:** SemVer tags. `RELEASE.md` says to bump `Cargo.toml` **and** `herdr-plugin.toml` together, move CHANGELOG `Unreleased`, then tag `v*`; CI builds archives. Also AGENTS.md, CONTRIBUTING, SECURITY and `examples/plugin-integration/herdr-keybinding.toml`.

### 3.11 Event-hook plugins: kryptamine/herdr-auto-title, qu8n/herdr-automatic-rename

**kryptamine/herdr-auto-title** (Go):

- **Manifest:** `id = "herdr.auto-title"`, `min_herdr_version = "0.8.2"`, per-platform `[[build]] go build` and `[[startup]] ./herdr-auto-title`. It uses a **process started from `[[startup]]` that stays alive and polls** rather than `[[events]]`.
- Uses **release-please** (`googleapis/release-please-action@v4`), golangci, CODEOWNERS, issue templates, architecture docs (`docs/architecture/herdr-socket-api.md`), and a `CLAUDE.md` / `AGENTS.md` for coding agents.

**qu8n/herdr-automatic-rename** (Bash 3.2 + jq, ~5k lines), the reference for a *serious* Bash plugin:

- **Manifest:** `version = "0.11.1"`. `min_herdr_version = "0.7.1"` is **deliberately low**, with this comment:
  ```toml
  # min_herdr_version stays at 0.7.1 deliberately. A requirement above the running
  # herdr is a HARD load failure (plugin_requires_newer_herdr), re-checked on every
  # event dispatch, whereas an event name an older herdr does not know is only an
  # install-preview warning. Newer-herdr features are therefore version-gated at
  # runtime instead (see ar_agent_prefix_ok) and newer events are simply declared
  # below.
  ```
  Every event runs `["bash", "automatic-rename.sh", "<event.name>"]`, with one idempotent reconcile. Actions `reset`, **`doctor`** ("explain this tab's name") and `clear` use `contexts = ["global"]`, and the manifest comment shows `herdr plugin action invoke herdr-automatic-rename.reset`.
- **Findings:**
  - `tab.closed` is not delivered for the interactive close keybinding (as of 0.8.0), only `pane.closed`.
  - `layout.updated` is socket-only and not delivered to plugins.
  - Shell-invoked runs (preexec hooks) don't get `HERDR_PLUGIN_*` vars, so it uses fixed XDG paths, keyed per herdr session from `HERDR_SOCKET_PATH`.
- **Layout:** the main script plus sourced modules (`naming.sh`, `git.sh`, `icons.sh`, `transcript.sh`), `config.example.sh`, `install.sh`, `shell/hook.{bash,zsh,fish}`, and `tests/{lib.sh,run.sh,test_*.sh,mocks/herdr}`. `AR_ROOT="${HERDR_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)}"` works whether the script is run by herdr, executed directly, or sourced by tests.
- **Tooling:**
  - `Makefile` targets `test`, `lint-sh` (shellcheck **pinned 0.11.0 plus sha256**), `lint-md` (markdownlint), `syntax` (`bash -n` on every file, including the extensionless mock) and `hooks` (pre-commit/prek).
  - CI: tests on ubuntu and macOS (bash 3.2), a separate shellcheck job, and markdown lint. Actions pinned by SHA; `permissions: contents: read`.
  - `release.yml` on `v*` tags extracts the `## [x.y.z]` section of CHANGELOG.md as release notes.
- **Tests:** a no-bats, TAP-ish `tests/lib.sh` (`check`, `check_rc`, `check_contains`, `check_absent`, `t_summary`), with `run.sh` running files in parallel, each sandboxed with mktemp.
- **README:** Quick start (Requirements, Install or update, shell hook), Recommended herdr configs, Configuration (optional), Actions, Uninstall, Caveats, Contributing, License.

### 3.12 Tyru5/herdr-floax (floating popup, Rust + Bash toggle)

- **Manifest:** a long header explaining design and limitations. `[[build]] cargo build --release`. Pane `floating` (`placement = "split"`, `title = "⌂ floax"`) and action `toggle` (`["bash","scripts/toggle-floating.sh"]`, **no `contexts`**).
- **Toggle logic** in Bash + jq. Find its pane via `pane list --workspace $HERDR_WORKSPACE_ID | select(.label == "⌂ floax")`:
  - If none, `plugin pane open --placement split --target-pane $HERDR_PANE_ID --env ...` and then `pane zoom <id> --on`.
  - If focused, `plugin pane close`.
  - Otherwise, `pane zoom --on`.
  - Reads the new pane id from `.result.plugin_pane.pane.pane_id`.
- **Claimed pitfalls (herdr 0.7.1 era):** overlay/zoomed panes are "torn down the instant the invoking keybinding action completes", and `plugin pane open --cwd` "makes the pane exit immediately". Both conflict with other plugins that use overlay plus `--cwd` fine (command-palette, catchup). The likely real cause is relative pane commands breaking under `--cwd` (§5). Treat these as version-specific and verify.
- **`scripts/install-keybinding.sh`:** an idempotent append of a `[[keys.command]]` block to `config.toml`, guarded by a marker comment (`# herdr-floax:keybind`). agent-handoff does the same as a `setup-keys` **action** that strips and replaces its own blocks and refuses on key conflicts unless `--force`.
- The README shows how to find the install root: `herdr plugin list --plugin herdr-floax --json | jq -r '.result.plugins[0].plugin_root'`.

### 3.13 Also looked at

- **sanirudh17/herdr-agent-handoff** (Node):
  - Popup panes use `width = "70%"`, `height = "60%"`.
  - Pane command uses `node -e 'require(path.join(process.env.HERDR_PLUGIN_ROOT, ...))'` because of the Windows `\\?\` cwd.
  - Has a `setup-keys` action that edits config.toml with a marker, and a CI `test.yml`.
  - Focused handoff has the *source* agent write a summary file (via `agent prompt`) and polls for it.
- **speardragon/herdr-yazi:** a manifest-only plugin whose actions are `bash -c` one-liners. `[[build]]` is only a dependency check that prints install instructions and exits 1.
- **Crokily/herdr-lazygit:** the manifest comment says "herdr spawns the pane command with cwd = the launcher's --cwd, NOT the plugin root — a bare relative "scripts/…" path fails". It uses `bash -c 'exec bash "$HERDR_PLUGIN_ROOT/scripts/run-lazygit.sh"'`, and its `DESIGN.md` says "A failed mutation is never retried automatically: a timeout may mean the server already applied it."
- **ogulcancelik/herdr-plugin-examples** (official cookbook, no license): a repo with multiple plugins in subdirectories. `github-link-preview` = `[[link_handlers]]` → action `open.sh` → `plugin pane open --placement split --env GITHUB_URL=...`, and its `preview.sh` uses `trap finish EXIT` (press Enter to close).

---

## 4. Recommendations for my-herdr (Bash + jq, no build)

> **The design sketch this plugin started from, not a description of it.** `my-herdr` is built, in
> **Python 3, standard library only**; the code, [README](../../README.md), and
> [AGENTS.md](../../AGENTS.md) describe the current implementation and contributor rules. The
> [documentation index](../README.md) links to active plans and the historical initial plan.
> The Bash below still names the planned ids (`fork-claude-tab`, `move-pane-new-tab`), which
> shipped as `fork-tab`, `fork-tab-ask` and `pane-to-tab`. What remains useful here is the survey of
> patterns: the herdr call sequences, the helper ideas, and the pitfalls. The project has no CI and
> no linter, so §4.8's workflow does not apply; its fake-herdr and manifest-check ideas were ported.

### 4.1 Manifest skeleton

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

### 4.2 Repo layout

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

### 4.3 Shared helper library (`lib/common.sh`), a synthesis of the plugins above

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

wait_shell_ready() {                                # adapted from t4t5/herdr-forkr (MIT)
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

### 4.4 Action recipes

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

**Fork Claude into a new tab.** The studied plugins (forkr, fork-from-message) share one sequence,
which `my-herdr` implements in `myherdr/fork.py`: `agent get` → require `agent == "claude"` and
`agent_session.kind == "id"` → `tab create --workspace --cwd` (cwd = `foreground_cwd // cwd`, and
`--env CLAUDE_CONFIG_DIR=…` if set) → wait for the new shell → `agent start <tmp-name> --kind claude
--pane <new> -- --resume <sid> --fork-session [-n <name>]` → `agent rename <new> --clear`, closing
the tab if the start fails. The rationale is recorded in the
[initial development plan](../plans/initial-development.md) (Phases 5 and 6): no invented
`fork: …` label, the tab focused on creation, the saved conversation
checked before any tab exists, and background Claude sessions refused (`official-docs.md` §7.4).

**Asking for input first** (two-stage: action → popup). The action validates headless, so errors
surface as toasts, then opens the popup with `plugin pane open --entrypoint … --env …`; omit
`--placement` so the manifest's `popup` applies (catchup), and don't pass `--target-pane` for a
popup, herdr rejects it. On Esc or empty input, exit 0 silently (drovr treats cancel as success); on
error, keep the popup readable until Enter. **Don't do slow work in the popup**: it stays on screen
until its process exits. drovr does its moves from the popup because a move is instant; a fork
waits for Claude. Invoking another action from the popup works for actions that open no UI (that is
how `fork-tab-ask` hands off to `fork-tab`), but one that opens UI gets `ui_busy` (plugin-manager).

Seeding a fork with a first message is possible either as Claude's positional prompt argument or,
more robustly, with `agent prompt <TARGET> <TEXT> [--wait]` once `agent start` has returned (it
rejects with `agent_blocked` while a dialog is open). `my-herdr` asks for a name only.

**`ping` action** (herdr-plus idea): print `env | grep ^HERDR_` and `$HERDR_PLUGIN_CONTEXT_JSON | jq .` to stdout, then check with `herdr plugin log list --plugin my-herdr`. It is a cheap way to discover the real context shape on the installed herdr.

### 4.5 Keybindings (README section)

`my-herdr` suggests no keys (see [AGENTS.md](../../AGENTS.md)); its README documents the
`[[keys.command]]` mechanism with placeholder keys. Keybindings are client-side: reload them with the
in-app reload (`prefix+shift+r`), not `herdr server reload-config` (`official-docs.md`).

- Keys other plugins suggest (possible conflicts if you install them): `prefix+f` (forkr, catchup, floax), `prefix+m` / `prefix+M` (drovr), `prefix+p` (command-palette, plugin-manager), `prefix+a` (agent-handoff), `prefix+c` (catchup, calebcauthon).
- **`prefix+c` is herdr's default `new_tab`**.
- Check `herdr config` or the herdr keyboard docs before choosing. Don't auto-edit config.toml by default; if ever wanted, use a marker-guarded, idempotent `setup-keys` action (floax/agent-handoff pattern).

### 4.6 README sections (consensus of the best READMEs)

1. Title plus a one-paragraph what/why (and a table of actions, or agent → command).
2. **Requirements:** herdr ≥ X, `jq`, `claude` on PATH, `herdr integration install claude` (verify with `herdr integration status`).
3. **Install:** `herdr plugin install <owner>/my-herdr`, or `herdr plugin link /path/to/my-herdr` for local development.
4. **Keybindings:** TOML blocks plus the in-app reload (`prefix+shift+r`); several of the studied
   READMEs say `herdr server reload-config`, which does not reload keybindings.
5. **Actions:** table of qualified id → behaviour. Include manual invocation: `herdr plugin action invoke my-herdr.<id>`.
6. **How it works:** numbered steps, naming the herdr CLI calls.
7. **Configuration and state:** what goes in `$HERDR_PLUGIN_CONFIG_DIR` / `$HERDR_PLUGIN_STATE_DIR`, or "none".
8. **Failure behaviour and logs:** toasts, `herdr plugin log list --plugin my-herdr`.
9. **Notes and caveats:** the fork is a snapshot of the on-disk transcript, and "allow for this session" grants don't carry over (forkr).
10. **Development:** link, test, lint.
11. License.

### 4.7 Marketplace and versioning checklist

- Public repo, GitHub topic `herdr-plugin` (also useful: `herdr`, `claude-code`), `herdr-plugin.toml` at the root on the default branch, all required keys present and parseable. Don't make it a fork or archive it, or it won't be listed.
- Bump `version` in the manifest on every shipped change; the card shows it. Use SemVer, tag `vX.Y.Z`, and optionally auto-create a GitHub release from the CHANGELOG section (qu8n `release.yml`).
- Users update by re-running `herdr plugin install owner/repo`; there is no `update` command.
- A LICENSE file (MIT is universal among studied plugins).

### 4.8 Testing approach

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

---

## 5. Pitfalls observed

1. **Actions have no TTY.** fzf, `read` and `select` must run in a plugin pane (popup/overlay/split). Every picker plugin works around this.
2. **Relative paths in pane commands break with `--cwd`.** Action cwd is the plugin root, but a pane opened with `--cwd X` starts in X. Use `["bash","-c","exec bash \"$HERDR_PLUGIN_ROOT/…\""]` (lazygit, catchup, command-palette, plugin-manager). This probably explains floax's "`--cwd` makes the pane exit" and calebcauthon avoiding `--cwd`.
3. **Popups have no pane id.** Inside a popup `HERDR_PANE_ID` is unset, and popups are outside the pane and agent APIs. **Never launch the forked agent inside the popup itself**; create a real tab and run `agent start` there (catchup comment). Pass the source pane to the popup with `--env`.
4. **Popup placement via CLI is uncertain.** `plugin pane open --help` lists `--placement overlay|split|tab|zoomed` only, and catchup says popup must come from the manifest (omit `--placement`). But plugin-manager passes `--placement popup` and drovr passes `--width/--height`, which don't appear in help. Declare the pane `placement = "popup"` in the manifest and omit `--placement`; verify the other flags on 0.9.0 if needed.
5. **`--target-pane` is rejected for overlay and popup** (catchup).
6. **`read -t` in popups returns EOF immediately when idle** (plugin-manager). Use blocking reads.
7. **Invoking a UI-opening action from inside a popup returns `ui_busy`** (plugin-manager). Also, opening a popup while Settings, Copy mode or another modal is active returns `ui_busy` (docs).
8. **herdr kills the popup's whole process group on close.** Background helpers need `setsid` (plugin-manager).
9. **Errors disappear.** Action output only reaches `herdr plugin log list`. Always toast failures, and in panes wait for Enter (drovr, command-palette, catchup, examples).
10. **`plugin action invoke` is fire-and-forget.** Exit 0 means dispatched, not succeeded. Poll `plugin log list` for the `log_id` if you need the result (command-palette).
11. **`agent start` requires the pane to be at an idle shell prompt.** Wait with `pane process-info` (forkr) or retry on `agent_pane_busy` (fork-from-message). It needs a **unique agent name**, so clear it afterwards with `agent rename --clear`. `agent_not_ready` after a trust or hook dialog is not fatal.
12. **No session id without the integration.** `agent_session` only exists if `herdr integration install claude` was run and Claude was restarted after that. Say so in the error.
13. **Focus can change between keypress and execution.** Re-validate that the pane still has the expected tab or workspace before mutating (drovr, fork-from-message).
14. **Moving the last pane of a tab closes that tab** (drovr).
15. **`min_herdr_version` too high is a hard load failure.** Gate newer features at runtime instead (qu8n).
16. **Events are incomplete.** No `tab.closed` for the keyboard close as of 0.8.0, and `layout.updated` isn't delivered to plugins (qu8n). Not relevant now, but matters for future event-driven actions.
17. **Plugin ids with dots make qualified ids ambiguous to split** (`jt.command-palette.open`). Use a dot-free id like `my-herdr`, or always get the plugin id from API fields, not by splitting.
18. **Don't store state in `HERDR_PLUGIN_ROOT`**, because install replaces the checkout. Use `HERDR_PLUGIN_STATE_DIR` and `HERDR_PLUGIN_CONFIG_DIR`. Scripts run outside herdr (shell hooks) don't get these vars (qu8n).
19. **Pass per-invocation data via `--env`, not shared temp files**, which race across simultaneous invocations and sessions (catchup, calebcauthon).
20. **Forward `CLAUDE_CONFIG_DIR`** to the new tab if you use multiple Claude config dirs, or the fork may resume against the wrong account and store (fork-from-message).
21. **A failed mutation may already have been applied** (for example after a timeout), so don't auto-retry blindly (lazygit DESIGN.md).
22. **`[[build]]` does not run on `plugin link`**, and build commands get no runtime env. Not relevant for a no-build Bash plugin, but don't rely on build for setup.
