# herdr plugin authoring: reference notes from the official docs

> **Reference snapshot, not a maintained document.** It was written while building this plugin
> against **herdr 0.9.1** and is not updated in step with herdr releases. It exists so that work on
> this plugin does not have to re-derive the plugin contract. **herdr's own documentation and the
> live `herdr` CLI always win**; when they disagree with this file, fix the file.

The herdr plugin contract as `my-herdr` relies on it. Everything here describes **herdr 0.9.1**
(protocol 22), the current stable release and the version this plugin targets.

- **[docs]** or an unmarked quote: from the official documentation pages linked below.
- **[src]**: read from the herdr source, at the paths listed below.
- **[local]**: checked against an installed herdr CLI. Nothing was installed, linked, configured, or created while checking.

## Source URLs

| Short name | URL |
| --- | --- |
| index | https://herdr.dev/llms.txt |
| plugins | https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/docs/next/website/src/content/docs/plugins.mdx |
| configuration | https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/docs/next/website/src/content/docs/configuration.mdx |
| config-reference | https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/docs/next/website/src/data/config-reference.json |
| keyboard | https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/docs/next/website/src/content/docs/keyboard.mdx |
| marketplace | https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/docs/next/website/src/content/docs/marketplace.mdx |
| cli-reference | https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/docs/next/website/src/content/docs/cli-reference.mdx |
| socket-api | https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/docs/next/website/src/content/docs/socket-api.mdx |
| agent-automation | https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/docs/next/website/src/content/docs/agent-automation.mdx |
| integrations | https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/docs/next/website/src/content/docs/integrations.mdx |
| changelog | https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/CHANGELOG.md |
| example plugins | https://github.com/ogulcancelik/herdr-plugin-examples (not official; "provided as-is and are not actively maintained") |
| source | `https://raw.githubusercontent.com/herdrdev/herdr/v0.9.1/src/app/api/plugins/{mod,runtime,env,context,manifest,panes}.rs`, `src/cli/plugin.rs`, `src/cli/pane.rs`, `src/app/popup.rs`, `src/app/custom_commands.rs`, `src/config/keybinds.rs`, `src/plugin_paths.rs`, `src/api/schema/events.rs` |


---

## 1. What a plugin is

From the plugins page, verbatim:

> A plugin is a directory with a `herdr-plugin.toml` manifest and commands Herdr can launch. Herdr validates the manifest, injects runtime context, starts the declared commands, and records logs. The commands call back into Herdr through the CLI or socket when they need to do more work.

> There is no separate plugin SDK or restricted command set. The entire Herdr CLI is the plugin API. Every command in the CLI reference is available to a plugin, and a plugin can run anything you can run yourself as `herdr ...`. Most plugins should call Herdr through `HERDR_BIN_PATH`, which points at the running Herdr binary.

> Runtime action registration and native non-terminal plugin UI are not part of plugin v1. Actions, event hooks, panes, and link handlers are all declared in the manifest.

This means:

- **No UI widgets.** There are no dialogs, text inputs, or menus. The only UI a plugin gets is a terminal: a popup, overlay, split, tab, or zoomed pane running a command.
- **No storage API.** "There is no Herdr-managed plugin storage API in v1. Plugins that need durable state should own their files or database."

---

## 2. Manifest (`herdr-plugin.toml`)

### 2.1 Full official example (verbatim, plugins page)

```toml
id = "example.layout"
name = "Layout"
version = "0.1.0"
min_herdr_version = "0.7.0"
description = "Apply project layouts"
platforms = ["linux", "macos", "windows"]

[[build]]
command = ["npm", "ci"]

[[build]]
command = ["npm", "run", "build"]
platforms = ["linux", "macos"]

[[startup]]
command = ["node", "dist/restore.js"]

[[actions]]
id = "apply"
title = "Apply layout"
contexts = ["workspace"]
command = ["node", "dist/apply.js"]

[[events]]
on = "worktree.created"
command = ["herdr", "workspace", "list"]

[[panes]]
id = "board"
title = "Project board"
placement = "overlay"
command = ["herdr-board"]

[[link_handlers]]
id = "github-issue"
title = "Open GitHub issue"
pattern = "^https://github\\.com/[^/]+/[^/]+/(issues|pull)/[0-9]+$"
action = "apply"
```

Popup pane example (verbatim, plugins page):

```toml
[[panes]]
id = "picker"
title = "Picker"
platforms = ["linux", "macos"]
placement = "popup"
width = "80%"
height = 20
command = ["sh", "picker.sh"]
```

A real Bash example from the examples repo (`github-link-preview/herdr-plugin.toml`). Note that its action has no `contexts`:

```toml
id = "examples.github-link-preview"
name = "GitHub Link Preview"
version = "0.1.0"
min_herdr_version = "0.7.0"
description = "Open clicked GitHub issue and PR links in a Herdr side pane."
platforms = ["linux", "macos"]

[[actions]]
id = "open"
title = "Open GitHub link preview"
command = ["bash", "open.sh"]

[[panes]]
id = "preview"
title = "GitHub preview"
placement = "split"
command = ["bash", "preview.sh"]

[[link_handlers]]
id = "github-issue-or-pr"
title = "Preview GitHub issue or PR"
pattern = "^https://github\\.com/[^/]+/[^/]+/(issues|pull)/[0-9]+/?$"
action = "open"
```

### 2.2 All fields

Field lists come from the docs plus the manifest deserializer **[src `manifest.rs`]**. TOML keys that the deserializer does not know are silently ignored; there is no `deny_unknown_fields`.

#### Top-level fields

| Key | Required | Notes |
| --- | --- | --- |
| `id` | yes | Plugin id. ASCII letters, digits, `.`, `:`, `_`, `-`. At most 120 chars **[src]**. |
| `name` | yes | Must not be empty after trim. |
| `version` | yes | Must not be empty after trim. The docs do not require semver. |
| `min_herdr_version` | yes | Must be a semantic version. Link or install fails when it is missing, invalid, or newer than the running binary (`plugin_requires_newer_herdr`). |
| `description` | no | |
| `platforms` | no, but recommended | `"linux"`, `"macos"`, `"windows"`. If omitted, link still succeeds but adds the warning `"manifest does not declare platforms; platform support unknown"`. |
| `[[build]]` | no | `command` (argv), optional `platforms`. |
| `[[startup]]` | no | `command`, optional `platforms`. |
| `[[actions]]` | no | See below. |
| `[[events]]` | no | See below. |
| `[[panes]]` | no | See below. |
| `[[link_handlers]]` | no | See below. |

#### `[[actions]]`

| Key | Required | Notes |
| --- | --- | --- |
| `id` | yes | Local id: letters, digits, `:`, `_`, `-`. **No dots.** Unique within the plugin. |
| `title` | yes | |
| `command` | yes | Non-empty argv array; every element must be non-empty. |
| `description` | no | Undocumented in prose, present in the schema. |
| `contexts` | no | Enum `global`, `workspace`, `tab`, `pane`, `selection` **[schema]**. Only metadata: there is no enforcement in the invoke path **[src]**. |
| `platforms` | no | Overrides the top-level list. |

#### `[[events]]`

| Key | Required | Notes |
| --- | --- | --- |
| `on` | yes | Event name, for example `"pane.agent_status_changed"`. Unknown names do not block linking but add the warning `"unknown event '...'"`. |
| `command` | yes | |
| `platforms` | no | |

#### `[[panes]]`

| Key | Required | Notes |
| --- | --- | --- |
| `id` | yes | Same rules as action ids (no dots). |
| `title` | yes | Becomes the pane's label. |
| `command` | yes | |
| `placement` | no | `overlay` (default), `popup`, `split`, `tab`, `zoomed`. |
| `width`, `height` | no | **Only valid with `placement = "popup"`.** Otherwise the link fails with `invalid_plugin_pane_size`. Value is an integer (cells, including the border) or a string `"1%"`..`"100%"`. |
| `description` | no | |
| `platforms` | no | |

#### `[[link_handlers]]`

| Key | Required | Notes |
| --- | --- | --- |
| `id` | yes | Local id. |
| `title` | yes | |
| `pattern` | yes | Rust regex matched against the clicked URL. |
| `action` | yes | Must name an action in the same plugin, else `invalid_plugin_link_handler_action`. |
| `platforms` | no | |

### 2.3 Id rules (verbatim)

> Top-level `id`, `name`, `version`, and `min_herdr_version` are required. [...] Plugin ids may use ASCII letters, digits, dot, colon, underscore, and hyphen.

> Action ids, pane ids, and link handler ids are local ids inside the plugin. They may use ASCII letters, digits, colon, underscore, and hyphen, but not dots. Each id type must be unique inside a plugin. Herdr qualifies action ids as `plugin.id.action` when it needs a globally unique name.

> Local action ids cannot contain dots, so qualified ids remain unambiguous even when plugin ids contain dots. (cli-reference)

**Gotcha [src `plugin_paths.rs`]: use lowercase plugin ids.** The per-plugin config and state directory names escape every byte that is not `[a-z0-9._-]` as `%XX`. An id like `My.Plugin` therefore gets a directory like `%4Dy.%50lugin`. For example, `my-herdr` or `owner.my-herdr` produce clean paths.

### 2.4 Commands are argv, not shell (verbatim)

> `command` values are argv arrays. Herdr does not run them through a shell, so there is no shell expansion unless your command starts a shell itself.

Relative plugin commands resolve from the plugin root, and command arrays preserve whitespace-only arguments. So `command = ["bash", "bin/fork-tab.sh"]` works, and so does `command = ["./bin/fork-tab.sh"]` if the file is executable.

### 2.5 Build commands (verbatim)

> Build commands run during GitHub `plugin install` after confirmation and before Herdr registers the plugin. If a build command fails, install aborts and the plugin is not registered. `plugin link` does not run build commands; local authors build their working tree themselves. Build commands may generate files, but changing `herdr-plugin.toml` after the install preview aborts install.

> Build commands are plain argv commands too, but they do not receive runtime plugin context or Herdr socket env.

`my-herdr` has no build step, so leave out `[[build]]` entirely.

### 2.6 Startup hooks (verbatim)

> `[[startup]]` commands run once for each enabled plugin after Herdr restores the session and its API socket is ready. They run again when a new server takes over during live handoff, but not when a client attaches, config reloads, or a plugin is linked or enabled. [...] A startup failure does not stop the server.

> Startup hooks receive the normal runtime plugin environment and `HERDR_PLUGIN_EVENT=startup`.

### 2.7 Event hooks

From the socket API page: "Event hooks run for enabled installed plugins when Herdr emits a matching event name such as `worktree.created`."

**[src `events.rs` `PLUGIN_HOOK_EVENT_KINDS`]** lists the event names that can trigger hooks:

- **Workspace:** `workspace.created`, `workspace.updated`, `workspace.closed`, `workspace.renamed`, `workspace.moved`, `workspace.reordered`, `workspace.focused`
- **Worktree:** `worktree.created`, `worktree.opened`, `worktree.removed`
- **Tab:** `tab.created`, `tab.closed`, `tab.renamed`, `tab.moved`, `tab.focused`
- **Pane:** `pane.created`, `pane.closed`, `pane.focused`, `pane.moved`, `pane.exited`, `pane.agent_detected`, `pane.agent_status_changed`

Some events can be subscribed to over the socket but do **not** fire hooks: `workspace.metadata_updated`, `pane.updated`, `pane.output_changed`/`pane.output_matched`, `pane.scroll_changed`, and `layout.updated`. The docs confirm this for one of them: "`workspace.metadata_updated` reports token changes and TTL expiry without invoking plugin event hooks."

Hook processes receive `HERDR_PLUGIN_EVENT=<name>` and `HERDR_PLUGIN_EVENT_JSON=<event envelope JSON>`.

### 2.8 Link handlers (verbatim)

> Use `[[link_handlers]]` to route modified clicks on matching terminal URLs to a plugin action instead of opening the URL in the browser. The modified-click modifier is Control on every platform, including macOS [...]. `pattern` is a Rust regular expression matched against the clicked URL, and `action` must name an action declared by the same plugin. Link handler actions receive `invocation_source = "link_click"`, `clicked_url`, and `link_handler_id` in `HERDR_PLUGIN_CONTEXT_JSON`; shell plugins can also read `HERDR_PLUGIN_CLICKED_URL` and `HERDR_PLUGIN_LINK_HANDLER_ID`. Handlers are checked in manifest order inside each plugin.

Link handlers also receive matching OSC 8 `file://` clicks.

### 2.9 Suggested manifest skeleton for `my-herdr`

This is my own composition from the rules above, not an official example.

```toml
id = "my-herdr"                     # lowercase: clean config/state dir names
name = "my-herdr"
version = "0.1.0"
min_herdr_version = "0.9.1"         # a value above the running herdr is a hard load failure
description = "Personal herdr helpers: fork Claude session into tab, pane to tab"
platforms = ["linux", "macos"]

[[actions]]
id = "fork-tab"
title = "Fork Claude session into new tab"
contexts = ["pane"]
command = ["bash", "bin/fork-tab.sh"]

[[actions]]
id = "pane-to-tab"
title = "Move focused pane to new tab"
contexts = ["pane"]
command = ["bash", "bin/pane-to-tab.sh"]

# Interactive name/prompt input: a terminal popup opened by the action (see section 5)
[[panes]]
id = "fork-tab-prompt"
title = "Fork Claude session"
placement = "popup"
width = "70%"
height = 12
command = ["bash", "bin/fork-tab-prompt.sh"]
```

---

## 3. How an action runs

### 3.1 Process, working directory, stdio **[src `runtime.rs`] + docs**

- **Working directory.** From the plugins page: "Runtime commands run with the plugin directory as their working directory." That is `HERDR_PLUGIN_ROOT`, not the focused pane's cwd. Read the pane cwd from the context JSON (`focused_pane_cwd`) or from `herdr pane get`.
- **Spawn.** The action is spawned **asynchronously on a background thread by the server**. `plugin action invoke` (and the keybinding) returns as soon as the process has started. The response carries a log record with `status: "running"`.
- **No TTY.** stdout and stderr are piped and captured. **An action cannot prompt the user**; use a popup or overlay pane instead (section 5).
- **Output cap.** stdout and stderr are each capped at **64 KiB**. Anything beyond that is replaced by `\n[herdr truncated plugin output after 65536 bytes]`.
- **No timeout.** There is none in the source and none documented. A hung action stays `running` forever and holds a concurrency slot.
- **Concurrency.** At most **32 plugin commands in flight** at once, counted across all plugins. Above that, the invoke fails with `plugin_command_limit_reached`.
- **Log retention.** The server keeps the last **200** command log records **in memory**. `plugin log list` defaults to `--limit 50` and clamps to 1..200. Logs do not survive a server restart; I saw no persistence.
- **Exit codes.** The exit code is recorded as `exit_code`. `status` is `running`, `succeeded`, or `failed`. If the spawn fails, `error` is set and `exit_code` is null. Herdr does not show a notification when an action fails; you only see it in `herdr plugin log list`. For user-visible feedback, call `"$HERDR_BIN_PATH" notification show "..."` yourself.

### 3.2 Environment variables

Verbatim from the plugins page:

> Runtime commands run with the plugin directory as their working directory. Herdr injects `HERDR_SOCKET_PATH`, `HERDR_BIN_PATH`, `HERDR_ENV=1`, `HERDR_PLUGIN_ID`, `HERDR_PLUGIN_ROOT`, `HERDR_PLUGIN_CONFIG_DIR`, `HERDR_PLUGIN_STATE_DIR`, `HERDR_PLUGIN_CONTEXT_JSON`, and any available `HERDR_WORKSPACE_ID`, `HERDR_TAB_ID`, and `HERDR_PANE_ID`. Action commands also receive `HERDR_PLUGIN_ACTION_ID`; startup and event hooks receive `HERDR_PLUGIN_EVENT` (`startup` for startup hooks), event hooks additionally receive `HERDR_PLUGIN_EVENT_JSON`, and pane commands receive `HERDR_PLUGIN_ENTRYPOINT_ID`.

| Variable | Action | Plugin pane (split/tab/overlay/zoomed) | Plugin **popup** pane | Notes |
| --- | --- | --- | --- | --- |
| `HERDR_BIN_PATH` | yes | yes | yes | `current_exe()` of the server, for example a Homebrew path like `.../Cellar/herdr/0.9.1/bin/herdr`. |
| `HERDR_SOCKET_PATH` | yes | yes | yes | Default `~/.config/herdr/herdr.sock`. |
| `HERDR_ENV` | `1` | `1` | `1` | |
| `HERDR_PLUGIN_ID` | yes | yes | yes | |
| `HERDR_PLUGIN_ROOT` | yes | yes | yes | Linked dir, or managed checkout for GitHub installs. |
| `HERDR_PLUGIN_CONFIG_DIR` | yes | yes | yes | `~/.config/herdr/plugins/config/<id>` **[src]** |
| `HERDR_PLUGIN_STATE_DIR` | yes | yes | yes | `~/.local/state/herdr/plugins/<id>` (`$XDG_STATE_HOME/herdr/...` if set) **[src]** |
| `HERDR_PLUGIN_CONTEXT_JSON` | yes | yes | yes | See 3.3. |
| `HERDR_PLUGIN_ACTION_ID` | yes (local id, for example `fork-tab`) | no | no | |
| `HERDR_PLUGIN_ENTRYPOINT_ID` | no | yes | yes | |
| `HERDR_WORKSPACE_ID` / `HERDR_TAB_ID` / `HERDR_PANE_ID` | from context: **`HERDR_PANE_ID` = the focused pane** at invoke time | the new pane's own ids (normal pane env) | **not set** ("does not export `HERDR_PANE_ID`") | |
| `HERDR_PLUGIN_CLICKED_URL`, `HERDR_PLUGIN_LINK_HANDLER_ID` | link-click only | no | no | |
| `HERDR_PLUGIN_EVENT`, `HERDR_PLUGIN_EVENT_JSON` | hooks only | no | no | |

Further details:

- **Config and state dirs.** From the plugins page: "Herdr creates those directories [...] but it does not validate, sync, or delete their contents. The plugin owns the file format and lifecycle." Also: "Do not store user credentials or durable state there [plugin root], because GitHub-installed plugin roots are managed source checkouts."
- **Protected variables.** From the CLI reference: "`--env KEY=VALUE` can be repeated on process-launching commands. It applies to the newly launched process only. Herdr-managed variables such as `HERDR_SOCKET_PATH`, `HERDR_BIN_PATH`, `HERDR_ENV`, `HERDR_WORKSPACE_ID`, `HERDR_TAB_ID`, `HERDR_PANE_ID`, `HERDR_PLUGIN_ID`, `HERDR_PLUGIN_ROOT`, `HERDR_PLUGIN_CONFIG_DIR`, `HERDR_PLUGIN_STATE_DIR`, `HERDR_PLUGIN_ENTRYPOINT_ID`, and `HERDR_PLUGIN_CONTEXT_JSON` stay authoritative when they conflict with caller-provided env."
- **Custom commands get different names.** `[[keys.command]]` with `type = shell|pane|popup` (not plugin actions) gets a different set: `HERDR_SOCKET_PATH`, `HERDR_BIN_PATH`, `HERDR_ACTIVE_WORKSPACE_ID`, `HERDR_ACTIVE_TAB_ID`, `HERDR_ACTIVE_PANE_ID`, `HERDR_ACTIVE_PANE_CWD` (configuration page). Do not mix up `HERDR_ACTIVE_PANE_ID` with the plugin's `HERDR_PANE_ID`.

### 3.3 `HERDR_PLUGIN_CONTEXT_JSON` shape

Schema `PluginInvocationContext` **[local `herdr api schema --json`]**. All fields are nullable:

```json
{
  "workspace_id": "w1",
  "workspace_label": "...",
  "workspace_cwd": "/path",          // focused pane cwd, else workspace default cwd
  "worktree": { ... } | null,
  "tab_id": "w1:t6",
  "tab_label": "...",
  "focused_pane_id": "w1:pC",
  "focused_pane_cwd": "/path",
  "focused_pane_agent": "claude",    // agent label if detected
  "focused_pane_status": "idle|working|blocked|done|unknown",
  "selected_text": "..." | null,     // keybinding invocations: the client's mouse selection, if any
  "invocation_source": "keybinding" | "api" | "link_click" | "startup",
  "correlation_id": "...",
  "clicked_url": null,
  "link_handler_id": null
}
```

Some details **[src]**:

- **Keybinding invocations** set `invocation_source = "keybinding"`. The server first focuses the invoking client's target workspace, tab, and pane, then builds the context from the active focused pane. So `HERDR_PANE_ID` is the pane that had focus when the key was pressed.
- **CLI invocations** (`herdr plugin action invoke`) use **`"cli"`**, not `"api"` as the schema comment above suggests **[local]**, and they get the *server's* active focused pane. Callers may pass their own `context` over the raw socket.

**Real context from a live CLI invocation [local, `my-herdr.ping`]**, ids and paths replaced with placeholders:

```json
{
  "correlation_id": "cli:plugin",
  "focused_pane_cwd": "/home/user/my-herdr",
  "focused_pane_id": "w3:p4",
  "focused_pane_status": "unknown",
  "invocation_source": "cli",
  "tab_id": "w3:t4",
  "tab_label": "some tab",
  "workspace_cwd": "/home/user/my-herdr",
  "workspace_id": "w3",
  "workspace_label": "my-herdr"
}
```

- **Missing values are left out, not sent as `null`.** Here the focused pane was a plain shell, so `focused_pane_agent`, `worktree`, `selected_text`, `clicked_url` and `link_handler_id` were simply absent. Read every field as optional.
- A pane without an agent reports `focused_pane_status: "unknown"`, not `"idle"`.
- `HERDR_PANE_ID`, `HERDR_TAB_ID` and `HERDR_WORKSPACE_ID` matched `focused_pane_id`, `tab_id` and `workspace_id`. `HERDR_PLUGIN_ACTION_ID` was the local id (`ping`); there was no `HERDR_PLUGIN_ENTRYPOINT_ID`, as expected for an action.
- The action ran with **cwd = plugin root** and finished in about 40 ms.
- **`python3` is resolved from the herdr server's PATH, not from your shell's.** Plugin commands are spawned by the server without a shell, so they inherit whatever environment the server was started with. In the observed setup the server ran as a systemd user service (the unit Homebrew's `brew services` generates), whose PATH has no Homebrew directories, so plugins got the system `/usr/bin/python3` (3.10) while interactive shells resolved a newer Homebrew Python. Plugin code must therefore not assume the interpreter it is tested with: the 3.9+ rule is a live constraint, and `tomllib` (3.11+) must stay out of plugin code.
- A keybinding invocation (`"keybinding"`) has not been captured yet; do that when the first key is bound.
- **Popups** get the context of the tiled pane under the popup. From the socket API page: "leaves plugin focus context on the underlying tiled pane."

Reading it in Bash:

```bash
ctx="${HERDR_PLUGIN_CONTEXT_JSON:-{}}"
pane_id="${HERDR_PANE_ID:-$(jq -r '.focused_pane_id // empty' <<<"$ctx")}"
pane_cwd="$(jq -r '.focused_pane_cwd // .workspace_cwd // empty' <<<"$ctx")"
herdr="${HERDR_BIN_PATH:-herdr}"
```

### 3.4 Logging

```bash
herdr plugin log list [--plugin ID] [--limit N]
# alias: herdr plugin logs list
```

Output is `{"id":"cli:plugin","result":{"logs":[ ... ],"type":"plugin_log_list"}}`. **[local]** With nothing run yet it returns `{"logs":[],"type":"plugin_log_list"}`. Each log record has this shape (schema `PluginCommandLogInfo`):

```json
{
  "log_id": "plugin-log-7",
  "plugin_id": "my-herdr",
  "action_id": "fork-tab",        // or null
  "event": null,                  // or event name / "startup"
  "command": ["bash", "bin/fork-tab.sh"],
  "status": "running|succeeded|failed",
  "started_unix_ms": 1789000000000,
  "finished_unix_ms": 1789000000123,
  "exit_code": 0,
  "stdout": "...",                // capped 64 KiB
  "stderr": "...",
  "error": null                   // spawn/wait error text
}
```

Herdr's own logs are `~/.config/herdr/herdr-server.log` and `herdr-client.log`. Set `HERDR_LOG=herdr=debug` for more detail.

---

## 4. `plugin action` commands and JSON

```bash
herdr plugin action list [--plugin ID]
herdr plugin action invoke <action_id> [--plugin ID]
```

Verbatim from the CLI reference:

> `plugin action invoke` starts the manifest command for an installed, enabled, platform-compatible plugin action and prints the started command log record in the JSON response. Use the qualified action id (`plugin.id.action`) when more than one plugin uses the same action id.

**An action takes no parameters [local, `herdr api schema --json`].** The CLI has no option besides `--plugin`, and `PluginActionInvokeParams` is `action_id`, `plugin_id` and an optional `context`. That `context` is a `PluginInvocationContext` with fixed fields (`focused_pane_id`, `selected_text`, `tab_id`, `correlation_id`, …) and no room for custom data. Anything an invoker needs to hand over has to go through a file, for example in the plugin state directory. `my-herdr` does that for the popup that names a fork.

The response type is `plugin_action_invoked`, with fields `action`, `context`, and `log`:

```json
{"id":"cli:plugin","result":{"type":"plugin_action_invoked",
  "action":{"plugin_id":"...","action_id":"...","title":"...","command":[...],"contexts":[...],"platforms":[...]},
  "context":{ ...PluginInvocationContext... },
  "log":{ ...PluginCommandLogInfo with status "running"... }}}
```

Error codes include `plugin_action_not_found`, `plugin_disabled`, `platform_unsupported`, and `plugin_command_limit_reached`. **[local]** Errors print JSON to **stderr** and exit **1**, for example `{"error":{"code":"plugin_action_not_found","message":"plugin action not found"},"id":"cli:plugin"}`. CLI usage errors exit **2**.

The raw socket request (socket API page):

```json
{"id":"req_plugin_invoke","method":"plugin.action.invoke","params":{"action_id":"example.worktree-bootstrap.bootstrap","context":{"invocation_source":"keybinding"}}}
```

Both the keybinding path and the API path reload `plugins.json` before resolving the action **[src]**. Edits to the scripts take effect on the next invocation with no relink. **Edits to `herdr-plugin.toml`** are re-read from the manifest path when the registry reloads; the socket API page says "On startup, Herdr re-reads each manifest from its original path". To be safe after changing the manifest, run `herdr plugin link <path>` again. It overwrites the entry with the same id.

---

## 5. Interactive input from a keybinding-triggered action

**Summary.** herdr has **no prompt or dialog API** for plugins ("native non-terminal plugin UI are not part of plugin v1"). Because actions have no TTY, the documented way to ask the user something is a **terminal pane**. The best fit is a **popup** that runs a script which reads input with `read`.

### 5.1 Popup plugin panes (verbatim, plugins page)

> `placement = "popup"` opens a session-modal terminal popup without changing the tiled layout. It accepts optional `width` and `height` fields in the manifest or open request; omit them for the default half-size popup, use numbers for outer terminal-cell dimensions, or use strings like `"80%"` for a percentage of the terminal area. It receives all terminal input, including Escape, and closes when the command exits or a `popup.close` request is sent. Dimensions smaller than the popup minimum are clamped.

> A popup is a singleton session resource rather than a Herdr pane: it has no pane ID, does not change plugin focus context, emits no pane lifecycle events, and does not participate in pane, layout, persistence, or agent APIs. Its process does not receive `HERDR_PANE_ID`; the underlying tiled pane remains available through `HERDR_PLUGIN_CONTEXT_JSON`. Opening a popup returns `ui_busy` while Settings, Copy mode, or another Herdr modal is active, and `plugin.pane.open` returns an `ok` result after launch.

Other placements (verbatim):

> Manifest pane `placement` defaults to `overlay`, which opens a temporary zoomed overlay over the active pane and restores the previous focus and zoom when it closes. A `plugin.pane.open` request can override the manifest placement with `overlay`, `popup`, `split`, `tab`, or `zoomed`.

> Split, tab, zoomed, and overlay plugin panes are normal Herdr panes after they open.

### 5.2 Opening a plugin pane

```bash
herdr plugin pane open --plugin ID --entrypoint ID [--placement overlay|popup|split|tab|zoomed] [--width SIZE] [--height SIZE] [--workspace ID] [--target-pane PANE] [--direction right|down] [--cwd PATH] [--env KEY=VALUE] [--focus|--no-focus]
herdr plugin pane focus <pane_id>
herdr plugin pane close <pane_id>
```

Raw socket request:

```json
{"id":"req_plugin_pane","method":"plugin.pane.open","params":{"plugin_id":"example.board","entrypoint":"board","placement":"zoomed","target_pane_id":"w1:p1","env":{"HERDR_ROLE":"board"},"focus":true}}
```

Responses:

- **Popup:** `{"result":{"type":"ok"}}`.
- **Other placements:** `{"result":{"type":"plugin_pane_opened","plugin_pane":{"plugin_id":"...","entrypoint":"...","pane":{...PaneInfo...}}}}`.

Validation rules and defaults **[src `plugins/mod.rs`, `panes.rs`]**:

- `--width` and `--height` are rejected (`invalid_params`) unless the effective placement is `popup`.
- Overlay and popup reject `--workspace`, `--target-pane`, and `--direction`: "overlay and popup plugin panes target the active pane".
- Split and zoomed reject `--workspace`.
- Tab rejects `--target-pane` and `--direction`.
- If a popup is already open, opening another returns `ui_busy` ("a popup pane is already open").
- The pane's cwd defaults to **`HERDR_PLUGIN_ROOT`** unless `--cwd` is given.
- `--env` values go to the popup process, except for the protected `HERDR_*` names. **Use this to pass the source pane id into the popup.**

**The CLI help is stale [local].** `herdr plugin pane open --help` lists `--placement` values `overlay, split, tab, zoomed` and shows no `--width` or `--height`. The actual argument parser in `src/cli/plugin.rs` accepts `popup` (and `fullscreen` as an alias for `zoomed`) plus `--width` and `--height`. I verified this: `herdr plugin pane open --plugin zz.nonexistent --entrypoint x --placement popup --width 80% --height 20` gets past parsing and returns `plugin_not_found`, while `--placement bogus` fails with `invalid pane placement: bogus` and exit 2. The API schema also lists `popup`. To avoid depending on the flag at all, declare `placement = "popup"` in the manifest and leave out `--placement`.

**Closing a popup.** It closes when its command exits. There is **no `herdr popup` CLI command** **[local]**. The only other way is the raw socket method `popup.close` (returns `popup_not_open` if none is open):

```json
{"id":"1","method":"popup.close","params":{}}
```

### 5.3 Recommended pattern for `fork-tab` with a name prompt

This is my design, not an official recipe. It is built from the documented pieces.

1. The keybinding runs `[[keys.command]] type = "plugin_action"` with `command = "my-herdr.fork-tab"`.
2. `bin/fork-tab.sh` (no TTY) does the preparation:
   - reads `HERDR_PANE_ID` (the focused pane);
   - runs `"$HERDR_BIN_PATH" agent get "$HERDR_PANE_ID"` and extracts `.result.agent.agent_session.value`;
   - checks that `.result.agent.agent == "claude"` and that the session kind is `id`;
   - if the check fails, runs `notification show` and exits;
   - otherwise opens the popup and exits right away (the popup keeps living):

   ```bash
   exec "$HERDR_BIN_PATH" plugin pane open --plugin my-herdr --entrypoint fork-tab-prompt \
     --env "MYH_SRC_PANE=$HERDR_PANE_ID" --env "MYH_SESSION_ID=$sid" --env "MYH_CWD=$cwd"
   ```

3. `bin/fork-tab-prompt.sh` runs inside the popup with a real TTY:
   - `read -r -e -p "Tab name: " name`, then optionally `read -r -e -p "Prompt (optional): " prompt`;
   - `tab create`, then `pane run` (or `agent start`, see 7.4);
   - exits, which closes the popup. On error, print the message and `read -r _` so the user can see it before the popup closes. The official example `github-link-preview/preview.sh` does this with `trap finish EXIT`.
   - Esc is delivered to the popup process, so the script must treat an empty read or Ctrl-C/Ctrl-D as cancel.

Alternative that skips the action and plugin env: a plain `[[keys.command]] type = "popup"` whose `command` runs the script directly. It gets `HERDR_ACTIVE_PANE_ID` and similar. That works too, but lives outside the plugin system: no plugin logs, no plugin env, and the command string runs through `/bin/sh -c`.

---

## 6. Keybindings

### 6.1 Binding a plugin action (verbatim)

```toml
[[keys.command]]
key = "prefix+l"
type = "plugin_action"
command = "example.layout.apply"
description = "apply layout"
```

From the configuration page:

> `type = "plugin_action"` invokes an installed plugin action id. Use the qualified id when action ids are not globally unique:

> `description` is optional. When set, it appears in the keybind help panel (opened with `prefix+?`) instead of the default `'custom command'` label.

`[[keys.command]]` fields **[src `config/keybinds.rs`]**:

| Key | Notes |
| --- | --- |
| `key` | A string or an array of strings, same syntax as `[keys]` entries. |
| `command` | String. Must not be empty, or the binding is disabled with a diagnostic. |
| `type` | `"shell"` (default), `"pane"`, `"popup"`, `"plugin_action"`. |
| `description` | Optional. |
| `width`, `height` | Popup only. On other types they are ignored with a diagnostic. |

The four `type` values (configuration page):

- `popup`: session-modal popup; the command runs via `/bin/sh -c`.
- `pane`: "opens a temporary zoomed pane and closes it when the command exits".
- `shell`: "runs detached in the background"; `/bin/sh -lc`, stdio goes to `/dev/null`.
- `plugin_action`: invokes the action; the `command` string is the action id.

Popup custom command example (verbatim):

```toml
[[keys.command]]
key = "prefix+alt+g"
type = "popup"
command = "lazygit"
description = "run lazygit"
width = "80%"
height = "80%"
```

### 6.2 Key syntax (verbatim, configuration page)

> Herdr has a prefix mode similar to tmux. The default prefix is `ctrl+b`. Keybinding strings are explicit: `prefix+n` means press the configured prefix and then `n`; `ctrl+alt+n` is a direct terminal-mode shortcut.

> Key strings accept plain keys, modifier combinations such as `ctrl+a`, `shift+n`, `alt+1`, `cmd+k`, and special keys such as `enter`, `tab`, `esc`, `left`, `right`, `up`, and `down`. Named punctuation such as `minus`, `comma`, `ampersand`, `plus`, and `backtick` is also accepted. Plain direct printable keys such as `n` are unsafe because they intercept typing; use `prefix+n` unless you intentionally want a direct binding.

> A binding may also be an array when one action needs multiple shortcuts: `next_tab = ["prefix+n", "ctrl+alt+]"]`

The prefix itself is set with `[keys] prefix = "ctrl+b"`. Examples in the reference: `"ctrl+b"`, `"f12"`, `"esc"`.

Pressing the prefix twice sends a literal prefix key, so `prefix+<prefix key>` is reserved and disabled **[src]**.

### 6.3 Conflict resolution **[src `config/keybinds.rs`, with its unit tests]**

Bindings are registered in two passes: **user first** (explicit `[keys]` entries, then `[[keys.command]]` in file order), **then defaults**.

- **A `[[keys.command]]` key equal to a default binding you did not override:** the command wins and the default binding is **silently dropped**.
- **A `[[keys.command]]` key equal to a key you set explicitly under `[keys]`:** the command is disabled with the diagnostic `"<key>: kept keys.<field>, disabled keys.command[N].key"`.
- **Two `[[keys.command]]` entries with the same key:** the later one is disabled.
- **A direct unmodified printable key** (for example `key = "f"` without `prefix+`): disabled as an "unsafe direct keybinding".
- Run `herdr config check` (read-only; prints `config: ok` or diagnostics) to see these. The `prefix+?` help panel shows the active bindings.

### 6.4 Default keybindings (config reference `keys.*`, matching `--default-config`)

**Prefix-mode defaults:**

| Key | Action |
| --- | --- |
| `prefix+?` | help |
| `prefix+s` | settings |
| `prefix+q` | detach |
| `prefix+shift+r` | reload_config |
| `prefix+o` | open_notification_target |
| `prefix+w` | workspace_picker |
| `prefix+g` | goto |
| `prefix+shift+n` | new_workspace |
| `prefix+shift+g` | new_worktree |
| `prefix+shift+w` | rename_workspace |
| `prefix+shift+d` | close_workspace |
| `prefix+c` | new_tab |
| `prefix+shift+t` | rename_tab |
| `prefix+p` | previous_tab |
| `prefix+n` | next_tab |
| `prefix+1..9` | switch_tab |
| `prefix+shift+x` | close_tab |
| `prefix+shift+p` | rename_pane |
| `prefix+e` | edit_scrollback |
| `prefix+[` | copy_mode |
| `prefix+h/j/k/l` | focus_pane_left/down/up/right |
| `prefix+shift+h/j/k/l` | swap_pane_left/down/up/right |
| `prefix+tab` | cycle_pane_next |
| `prefix+shift+tab` | cycle_pane_previous |
| `prefix+v` | split_vertical |
| `prefix+minus` | split_horizontal |
| `prefix+x` | close_pane |
| `prefix+z` | zoom |
| `prefix+r` | resize_mode |
| `prefix+b` | toggle_sidebar |

**Other defaults:**

- Navigate mode only: `up`/`down` (workspace), `h/j/k/l` (pane). Esc, Enter, Tab, Shift+Tab, and unmodified `1..9` are reserved there.
- `ctrl+v`: `remote_image_paste`, only active in `herdr --remote`.

**Unset by default:** `open_worktree`, `remove_worktree`, `previous_workspace`, `next_workspace`, `previous_agent`, `next_agent`, `focus_agent`, `move_tab_previous`, `move_tab_next`, `switch_workspace`, `last_pane`, `resize_pane_*`, `keys.indexed.*`.

**Free prefix keys** (lowercase letters not used by defaults): `prefix+a`, `prefix+d`, `prefix+f`, `prefix+i`, `prefix+m`, `prefix+t`, `prefix+u`, `prefix+y`. All `prefix+shift+<letter>` combinations are free except H J K L N G W D T X P R. `prefix+alt+*` is completely unused by defaults; the docs use `prefix+alt+g` and `prefix+alt+1..9` as examples.

**Direct (prefix-free) chords.** Verbatim advice from the keyboard page: "One modifier family is almost untouched everywhere: `ctrl+alt`." Avoid these:

| Chord | Owned by |
| --- | --- |
| `ctrl+alt+arrows` | GNOME workspace switching, Ghostty and Konsole defaults |
| `ctrl+alt+t` | "Launch terminal" on Ubuntu and Fedora |
| `ctrl+alt+l` / `ctrl+alt+a` | KDE lock screen / attention window |
| `ctrl+alt+s` / `ctrl+alt+u` | Konsole |
| `ctrl+alt+f1..f12` | Linux virtual console switching |

### 6.5 Reloading config (verbatim, configuration page)

> Reload a running server after editing `config.toml`:
>
> `herdr server reload-config`
>
> You can also open the global menu in Herdr and choose `reload config`.
>
> Reload applies most UI settings without restarting panes. Startup-only settings still need a restart.

> Themes, sidebar layouts, copy behavior, and other presentation settings come from the client's local config [...]. Pane defaults, worktrees, integrations, and custom commands belong to the server where the panes run. The UI's `reload config` action reloads both the client's local settings and the selected server's config. Local keybindings reload too; `--remote-keybindings server` instead uses the selected server's keybindings.

Config file: `~/.config/herdr/config.toml` (or `$HERDR_CONFIG_PATH`).

**Recommendation.** Keybindings are client-side while custom commands are server-side, so use the in-app reload (`prefix+shift+r`, or "reload config" in the global menu) after editing. It reloads both sides. `herdr server reload-config` is the scriptable way to reload the server. Then confirm in `prefix+?`. On a stale command manifest the server answers `command_not_found`: "custom command manifest is stale; reload configuration" **[src]**. Also available: `herdr config reset-keys` backs up the config and removes `[keys]` and `[[keys.command]]`. Do not run it.

---

## 7. Install, link, enable

### 7.1 Local development (verbatim command list, plugins page)

```bash
herdr plugin link /path/to/plugin
herdr plugin config-dir example.layout
herdr plugin action list --plugin example.layout
herdr plugin action invoke example.layout.apply
herdr plugin pane open --plugin example.layout --entrypoint board
herdr plugin log list --plugin example.layout
```

CLI synopsis (CLI reference, confirmed by **[local]** `--help`):

```bash
herdr plugin install <owner>/<repo>[/subdir...] [--ref REF] [--yes]   # -y alias
herdr plugin list [--plugin ID] [--json]
herdr plugin uninstall <plugin_id|owner/repo[/subdir...]>
herdr plugin enable <plugin_id>
herdr plugin disable <plugin_id>
herdr plugin link <path> [--disabled]        # local also shows --enabled
herdr plugin unlink <plugin_id>
herdr plugin config-dir <plugin_id>
herdr plugin action list [--plugin ID]
herdr plugin action invoke <action_id> [--plugin ID]
herdr plugin log list [--plugin ID] [--limit N]
herdr plugin pane open|focus|close ...
```

Key facts, verbatim:

> `plugin link` accepts a plugin directory containing `herdr-plugin.toml` or a direct manifest path. Use it while authoring or testing a plugin from a local checkout. `plugin unlink` unregisters the plugin and leaves files alone.

> Installed and linked plugins, including their enabled state, are global to the current user and available in every Herdr session. Both `plugin install` and `plugin link` can register plugins while no Herdr server is running.

> Herdr writes a `plugins.json` registry file alongside `session.json` on `plugin.link`, `plugin.unlink`, `plugin.enable`, and `plugin.disable`. [...] On startup, Herdr re-reads each manifest from its original path; if the file is missing or unparseable, the entry is kept with a `warnings` field so `plugin.list` surfaces it.

> `plugin install` and `plugin link` create the plugin's config and state directories, and `plugin config-dir <id>` prints the config directory

Notes:

- **Link state.** Link stores the **canonicalized manifest path**, and the plugin root is the directory that contains it **[src]**. A newly linked plugin is enabled unless `--disabled` is given.
- **Empty registry [local].** With no plugins registered, `herdr plugin list --json` returns `{"id":"cli:plugin","result":{"plugins":[],"type":"plugin_list"}}`.
- **Registry location.** `plugins.json` sits next to `session.json` in `~/.config/herdr/`.
- **Remote machines.** Plugin link paths must be absolute when routed with `--machine`.

### 7.2 Installing from GitHub (verbatim)

> `plugin install` accepts GitHub shorthand only, such as `owner/repo/subdir`. It clones with `git`, shows a preview in interactive terminals, runs supported build commands, then stores the checkout under Herdr-managed plugin data and registers it. Use `--yes` for noninteractive installs. Reinstalling a GitHub-managed plugin replaces that managed checkout. [...] Installing over a locally linked plugin is refused; unlink or uninstall the local plugin first.

> `plugin uninstall <id-or-source>` unregisters the plugin. For GitHub-managed installs it also removes the managed checkout, and it accepts either the plugin id or the same `owner/repo[/subdir...]` shorthand used by install. [...] There is no separate `plugin update` in v1; reinstall from GitHub to refresh a managed plugin.

- **Managed checkout location [src]:** `~/.config/herdr/plugins/github/<component>`.
- **Source metadata.** `plugin list --json` shows `source`: `{kind:"github", owner, repo, subdir, requested_ref, resolved_commit, managed_path, installed_unix_ms}`. For linked plugins it is `{kind:"local"}`.
- **Update flow:** run `herdr plugin install owner/repo[/subdir] [--ref REF] --yes` again. For the local dev flow, edit files in place; relink only if the manifest changed.

### 7.3 What a repo needs

**To be installable** (marketplace page, verbatim):

> The command works with a public GitHub repository that has a `herdr-plugin.toml` manifest at its root or in a subdirectory.

The manifest must satisfy all the validation in section 2. `min_herdr_version` must not be newer than the installer's herdr.

**To be listed in the marketplace** (verbatim):

> Add the GitHub topic `herdr-plugin` to a public repository and put one or more `herdr-plugin.toml` manifests with parseable required metadata on its default branch. Manifests may be at the root or in subdirectories. The marketplace uses one card per repository and lists each valid manifest as a separately installable plugin. The index refreshes automatically every 30 minutes and rescans repositories when their default-branch head changes.

> The index records the manifest path, `id`, `name`, `version`, `platforms`, and `min_herdr_version` together with the exact default-branch commit. Forks, archived repositories, repositories without a valid plugin manifest, and malformed manifest metadata are excluded.

> Discovery is automatic and unreviewed. A listing means a repository tagged itself, not that Herdr vetted it

Browse the marketplace at https://herdr.dev/plugins/.

**Note for `my-herdr`:** the repo root is the plugin, so `herdr-plugin.toml` goes at the repo root. Install with `herdr plugin install <owner>/my-herdr`. A **fork** is excluded from the marketplace, and a private repo cannot be listed.

### 7.4 Agent-related commands useful for `fork-tab`

```bash
herdr agent get <target>        # target = unique live agent name or pane id
herdr agent list
herdr agent start <name> --kind KIND --pane ID [--timeout MS] [-- <agent-args...>]
```

`agent_session` (verbatim, socket API page):

> `pane.get`, `pane.list`, `agent.get`, and `agent.list` expose a read-only `agent_session` object when Herdr has a stored native session reference [...] If no native session reference is stored, the field is omitted.

For Claude this requires `herdr integration install claude`. From the integrations page: "The hook reports Claude Code session identity to the local Herdr socket on session start. Claude Code state comes from Herdr's screen manifest detection."

**The hook is versioned independently of herdr [local].** herdr 0.9.1 installs **v10**, whose Claude-settings registration matches the `SessionStart` sources `^(startup|resume|clear|compact|fork)$`. `fork` is in that list, so a forked session reports its **new** id when it starts.

**Upgrading herdr does not upgrade the hook.** `herdr integration status` reports `claude: outdated (vN < vM)` until `herdr integration install claude` is run again. A plugin should not depend on which hook version is installed.

**The hook's own preconditions matter for fork-tab [local, read from the installed script].** It exits silently (status 0, no report) unless all of these hold in Claude's own process environment:

```sh
[ "${HERDR_ENV:-}" = "1" ] || exit 0
[ -n "${HERDR_SOCKET_PATH:-}" ] || exit 0
[ -n "${HERDR_PANE_ID:-}" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
```

So a Claude started **inside a popup would never register a session**, because popups get no `HERDR_PANE_ID` (§3.2). That is the concrete mechanism behind the "never launch the agent in the popup" pitfall: the fork would run, but herdr would never learn its session id, and forking *that* fork later would be impossible. It also means the hook needs `python3` on PATH, the same interpreter this plugin needs.

**[local]** Actual output of `herdr agent get w1:pC` (a pane running Claude; session id and paths replaced with placeholders):

```json
{"id":"cli:agent:get","result":{"agent":{"agent":"claude","agent_session":{"agent":"claude","kind":"id","source":"herdr:claude","value":"00000000-0000-0000-0000-000000000000"},"agent_status":"blocked","cwd":"/home/user/project","focused":true,"foreground_cwd":"/home/user/project","pane_id":"w1:pC","revision":2,"state_change_seq":445,"tab_id":"w1:t6","terminal_id":"term_65ba9c0d4fe41c","terminal_title":"◐ pane-test","terminal_title_stripped":"pane-test","workspace_id":"w1"},"type":"agent_info"}}
```

So `jq -r '.result.agent.agent_session.value'` gives the Claude session id. `kind` is `"id"` or `"path"`, depending on the agent. For a pane with no detected agent, `agent get <pane>` returns an error; handle a non-zero exit.

**GOTCHA [local]: the id can lag behind the conversation on screen.** When Claude Code resumes a
conversation it carries it into a **new** session id and leaves a `{"type": "continued-in",
"continuedInSessionId": ...}` record at the end of the old transcript
(`~/.claude/projects/<cwd-slug>/<id>.jsonl`). herdr keeps the old id until the hook reports the new
one, so for a while after a pane is resumed or restored, `agent_session.value` names a transcript that
stops before the latest turns. Separately, `claude --resume <id>` on a session still open in another
process can load a **discarded branch** left by a rewind: the transcript keeps both branches, and
Claude (2.1.278) has no flag to resume at a given message. A fork is only as current as those two
allow.

**`agent start` as an alternative to `pane run`** (CLI reference, verbatim):

> `agent start` activates an existing available shell pane: the pane's interactive shell must own the foreground, with no foreground command, editor, or agent running. [...] Names are unique among live agents and must match `[a-z][a-z0-9_-]{0,31}`. The kind selects Herdr's canonical interactive executable, while arguments after `--` are passed to that executable.

> A successful start returns only after the expected agent owns the same terminal and is ready for interactive input. [...] The default startup timeout is 30000 milliseconds

For example:

```bash
herdr agent start <name> --kind claude --pane "$new_pane" -- --resume "$sid" --fork-session -n "$label"
```

This waits for the new shell to be ready, which `pane run` does not. The catch is the herdr agent-name regex and uniqueness requirement. Whether `--kind claude` launches `claude` from PATH exactly as the user's shell would is not documented.

---

## 8. Trust and security model (verbatim)

From the plugins page, "Trust and security":

> A plugin is ordinary code that runs on your machine. Its build and runtime commands run as your user, inherit your environment, and can call the full Herdr CLI. Treat a plugin like any extension you add to an editor, shell, or coding agent.

> Install or link plugins only from authors and repositories you trust. Before installing or linking one, skim the `herdr-plugin.toml` manifest and the scripts or binaries it runs. `herdr plugin install` shows a preview of the source and the commands it will run in interactive terminals, so you can review before confirming. Use `--yes` for sources you already trust, and pin `--ref` when you want a specific revision.

> Herdr validates the manifest and keeps each plugin's config and state in its own directory, but it does not review or sandbox plugin code. Third-party plugins come from their authors, not Herdr; you are responsible for deciding whether to run them.

From the startup hooks section: "The install preview lists every startup command so users can review code that will run automatically."

From the marketplace page: "The index covers public GitHub repositories; it is not a reviewed catalog." Also: "Discovery is automatic and unreviewed. A listing means a repository tagged itself, not that Herdr vetted it, so the trust guidance applies before you install anything."

There are **no permission scopes and no sandbox**. A plugin has full CLI and socket access.

---

## 9. CLI and socket reference for the planned actions

All IDs are opaque: workspace `w1`, tab `w1:t1`, pane `w1:p1`. From the herdr skill: "Closed tab and pane IDs are not reused." Always read IDs from JSON responses.

### 9.1 `tab create`

```bash
herdr tab create [--workspace <workspace_id>] [--cwd PATH] [--label TEXT] [--env KEY=VALUE] [--focus] [--no-focus]
```

> A tab is another terminal layout inside a workspace. Without `--workspace`, `tab create` uses the active workspace and fails if none exists. Its JSON response exposes `.result.tab.tab_id` and `.result.root_pane.pane_id`.

> Workspace and tab creation, and pane splitting, leave focus unchanged by default. `--focus` selects the new layout [...] Each `--env KEY=VALUE` adds or replaces that variable in the new root shell.

- **Response type** `tab_created` with `tab` (TabInfo) and `root_pane` (PaneInfo).
- **TabInfo fields:** `tab_id`, `workspace_id`, `number`, `label`, `focused`, `pane_count`, `agent_status`.
- **[local]** `tab list` item: `{"agent_status":"blocked","focused":true,"label":"api","number":6,"pane_count":2,"tab_id":"w1:t6","workspace_id":"w1"}`.
- **Tip:** pass `--workspace "$HERDR_WORKSPACE_ID"` so the tab lands in the source pane's workspace, even if another client is looking at a different one.

### 9.2 `pane move`

```bash
herdr pane move <pane_id> --tab <tab_id> --split right|down [--target-pane ID] [--ratio FLOAT] [--focus|--no-focus]
herdr pane move <pane_id> --new-tab [--workspace ID] [--label TEXT] [--focus|--no-focus]
herdr pane move <pane_id> --new-workspace [--label TEXT] [--tab-label TEXT] [--focus|--no-focus]
```

> **GOTCHA [src `cli/pane.rs`]: `--new-tab` takes `--label`, not `--tab-label`.** `--tab-label` is only valid with `--new-workspace`. `herdr pane move <pane> --new-tab --tab-label foo` fails with the usage error and **exit 2**. The planned command must be:
>
> ```bash
> herdr pane move "$HERDR_PANE_ID" --new-tab --label "$name" --focus
> ```
>
> The CLI's default is `focus = true` for `pane move`, unlike the create commands.

Verbatim from the CLI reference:

> After `pane move`, use `.result.move_result.pane.pane_id` for later commands. A cross-workspace move changes the workspace-qualified pane ID; the prior value remains at `.result.move_result.previous_pane_id`. The running process keeps its launch-time `HERDR_PANE_ID`, `HERDR_TAB_ID`, and `HERDR_WORKSPACE_ID`; Herdr retains the old pane ID as an alias for that terminal, so pane commands using `--current` still resolve it. A live agent name follows the terminal and continues to resolve after the move.

Raw form and semantics (socket API page):

```json
{"id":"req_move_new_tab","method":"pane.move","params":{"pane_id":"w1:p2","destination":{"type":"new_tab","workspace_id":"w1","label":"logs"},"focus":true}}
```

> Moves involving a zoomed source or target tab return `changed: false` with `reason: "zoomed_tab"`.

> The response is `type: "pane_move"` with `changed`, optional `reason`, `previous_pane_id`, `previous_workspace_id`, `previous_tab_id`, the moved `pane`, optional `source_layout`, `target_layout`, optional created workspace or tab records, optional closed workspace or tab ids, and `focused_pane_id`.

- **CLI wrapper:** the fields sit under `.result.move_result`. Schema `PaneMoveResult`: `changed`, `reason` (`same_tab`|`zoomed_tab`|null), `previous_pane_id`, `previous_workspace_id`, `previous_tab_id`, `pane` (PaneInfo), `source_layout?`, `target_layout`, `created_tab?` (TabInfo), `created_workspace?`, `closed_tab_id?`, `closed_workspace_id?`, `focused_pane_id`.
- **Check `changed`**, because a zoomed tab makes the move a no-op rather than an error. If the pane was the only one in its tab, expect `closed_tab_id` to be set.
- **`--focus` moves attached clients** to the moved pane, so no extra `tab focus` is needed.

### 9.3 `pane run`

```bash
herdr pane run <pane_id> <command>
```

> `pane run` honors live bracketed-paste mode and submits text plus Enter atomically. Prefer it over `send-text` plus `send-keys Enter` for commands

**[src]** The CLI joins all remaining arguments with single spaces and **types the text into the pane's shell**. Consequences:

- **Shell-quote everything** yourself, for example `printf -v cmd 'claude --resume %q --fork-session -n %q %q' "$sid" "$name" "$prompt"`.
- A prompt that contains newlines is pasted into the shell, so avoid newlines or pass the prompt differently.
- On success the output is `{"result":{"type":"ok"}}`-style.
- **Readiness race:** a freshly created tab's shell may not be ready yet. Input is buffered by the PTY, which usually works, but `agent start` (7.4) explicitly waits for the shell to be ready.

### 9.4 `pane split`

```bash
herdr pane split [<pane_id>|--pane ID|--current] --direction right|down [--ratio FLOAT] [--cwd PATH] [--env KEY=VALUE] [--right-click herdr|pane] [--focus] [--no-focus]
```

- The response exposes the new pane as `.result.pane.pane_id`.
- An omitted target "splits the calling pane when `HERDR_PANE_ID` is available, otherwise the focused pane", and `--current` errors without `HERDR_PANE_ID`. **Always pass an explicit pane id** rather than relying on that.

### 9.5 `pane rename`, `tab rename`

```bash
herdr pane rename <pane_id> <label>|--clear      # local: [LABEL]... (multiple words joined)
herdr tab rename <tab_id> <label>
herdr agent rename <target> <name>|--clear       # agent alias, regex [a-z][a-z0-9_-]{0,31}
```

### 9.6 `pane current`, `pane get`

```bash
herdr pane current [--pane ID|--current]
herdr pane get <pane_id>
```

**GOTCHA [local]:** `pane get` takes the id **positionally**, while its neighbours `pane current` and
`pane process-info` take `--pane ID`. `herdr pane get --pane w1:p1` is a usage error and exits 2.

`pane.current` (verbatim): "returns a single `PaneInfo`. When `caller_pane_id` is present, Herdr returns that pane. When it is omitted, Herdr returns the active focused pane." They "resolve the calling pane instead of another client's focused pane".

**[local]** The response `type` is **`pane_current`**, not `pane_info`:

```json
{"id":"cli:pane:current","result":{"pane":{"agent":"claude","agent_session":{"agent":"claude","kind":"id","source":"herdr:claude","value":"00000000-..."},"agent_status":"blocked","cwd":"/home/user/project","focused":true,"foreground_cwd":"/home/user/project","label":"pane-test","pane_id":"w1:pC","revision":2,"scroll":{"max_offset_from_bottom":0,"offset_from_bottom":0,"viewport_rows":50},"tab_id":"w1:t6","terminal_id":"term_65ba9c0d4fe41c","terminal_title":"◐ pane-test","terminal_title_stripped":"pane-test","workspace_id":"w1"},"type":"pane_current"}}
```

**PaneInfo fields:**

- **Always present:** `pane_id`, `terminal_id`, `workspace_id`, `tab_id`, `focused`, `agent_status`, `revision`.
- **Optional:** `agent`, `agent_session`, `cwd`, `foreground_cwd`, `label`, `title`, `display_agent`, `state_labels`, `tokens`, `scroll`, `terminal_title`, `terminal_title_stripped`.
- **AgentInfo** adds `name`, `interactive_ready`, `launch_pending`, `screen_detection_skipped`, `state_change_seq`.

Pane `cwd` vs `foreground_cwd` (verbatim): "`foreground_cwd` when Herdr can resolve the cwd of the foreground process controlling the pane. The `cwd` field remains the pane/workspace cwd used for labels and follow-cwd behavior." For forking Claude, prefer `foreground_cwd // cwd` as `--cwd` of the new tab: Claude sessions are keyed by project directory.

### 9.7 `agent list`

**[local]** `.result.type == "agent_list"`. `.result.agents[]` items have the keys `agent`, `agent_session`, `agent_status`, `cwd`, `focused`, `foreground_cwd`, `pane_id`, `revision`, `state_change_seq`, `tab_id`, `terminal_id`, `terminal_title`, `terminal_title_stripped`, `workspace_id`.

`agent list` takes **no options** (`herdr agent list --help` shows none), so filtering by workspace or status happens in the client.

#### `agent_status` lifecycle **[local, measured]**

`AgentStatus` (from `herdr api schema --json`) is `idle | working | blocked | done | unknown`. There is **no seen-related field** anywhere in `AgentInfo`: `done` versus `idle` *is* the seen signal.

Measured with a read-only poller (`agent list` every 250 ms for one hour, logging transitions):

- `done` **is reachable and durable**. An agent that finished while its pane was not being looked at went `working -> done (focused=false)` and **stayed `done` for the remaining ~24 minutes** of the run. It is not a transient blip, and it does not decay on a timer.
- An agent that finishes while its pane **is** being looked at never shows `done` at all: it goes straight `working -> idle` (observed with `focused=true`). An earlier spot check that showed finished agents as `idle` was this case, not evidence that `done` is unreachable.
- `blocked` behaves the same way in reverse: focusing a blocked agent does **not** clear it, because it is still waiting for input.

Consequence for "jump to the agent that needs me": a plain `agent list` poll at keypress time is enough, and **no event hook is needed** to catch finished-but-unread agents.

The matching event, `pane.agent_status_changed`, carries `pane_id`, `workspace_id`, `agent_status`, `agent`, `title` and `state_labels` — but **no `tab_id`**, so an event-driven queue would have to resolve the tab itself.

### 9.8 Notifications (useful for feedback from a TTY-less action)

```bash
herdr notification show <title> [--body TEXT] [--position top-left|top-right|bottom-left|bottom-right] [--sound none|done|request]
```

Response: `{"type":"notification_show","shown":true,"reason":"shown"}`. `reason` is one of `shown`, `disabled`, `rate_limited`, `no_foreground_client`, `busy`. The title is capped at 80 chars and the body at 240.

### 9.9 Socket transport

> Herdr uses newline-delimited JSON over a local socket. On Unix, that socket is a Unix domain socket.

Request and response shapes:

```json
{"id":"req_1","method":"ping","params":{}}
{"id":"req_1","result":{"type":"pong"}}
{"id":"req_1","error":{"code":"not_found","message":"pane not found"}}
```

- **Socket path:** `~/.config/herdr/herdr.sock` for the default session; `~/.config/herdr/sessions/<name>/herdr.sock` for named sessions.
- **Protocol tolerance:** "JSON API clients should ignore unknown fields and handle unsupported methods as normal errors."
- **Schema dump:** `herdr api schema --json` (or `--output FILE`) prints the full JSON Schema for the installed binary. That is the authoritative source for field names.

---

## 10. Other env vars and paths

| Item | Value |
| --- | --- |
| Config | `~/.config/herdr/config.toml`, override `HERDR_CONFIG_PATH` |
| Session selection | `HERDR_SESSION=<name>` or `--session <name>` |
| Socket override | `HERDR_SOCKET_PATH` |
| Pane process env | `HERDR_ENV=1`, `HERDR_PANE_ID`, `HERDR_TAB_ID`, `HERDR_WORKSPACE_ID` |
| Plugin registry | `~/.config/herdr/plugins.json` (next to `session.json`) |
| Plugin config dir | `~/.config/herdr/plugins/config/<id>` **[src]**; `herdr plugin config-dir <id>` prints and creates it |
| Plugin state dir | `~/.local/state/herdr/plugins/<id>` **[src]** |
| GitHub managed checkout | `~/.config/herdr/plugins/github/<component>` **[src]** |
| Logs | `~/.config/herdr/herdr-server.log`, `herdr-client.log`; `HERDR_LOG=herdr=debug` |

---

## 11. Custom commands vs plugin actions

| | `[[keys.command]]` `shell` | `popup` | `pane` | `plugin_action` |
| --- | --- | --- | --- | --- |
| Runs via | `/bin/sh -lc`, detached | `/bin/sh -c` in popup TTY | `/bin/sh -c` in temporary zoomed pane | Manifest argv, no shell |
| cwd | Focused pane cwd | Focused pane cwd | Focused pane cwd | Plugin root |
| Env | `HERDR_ACTIVE_*` + socket + bin | Same | Same | `HERDR_PLUGIN_*` + `HERDR_PANE_ID` etc. |
| TTY / interactive | no | **yes** | **yes** | no |
| Logged | no (stdio to /dev/null) | no | no | **yes** (`plugin log list`) |

---

## 12. Gotchas and surprises

1. **`pane move --new-tab` uses `--label`.** `--tab-label` there is a usage error (exit 2). `--tab-label` only exists for `--new-workspace`.
2. **The `--help` output is stale.** `herdr plugin pane open --help` hides `popup`, `--width`, and `--height`, but the parser accepts them. Declaring `placement = "popup"` in the manifest avoids the question.
3. **Actions have no TTY** and run async with stdout/stderr captured (64 KiB cap). Interactive input needs a popup or overlay plugin pane. No dialog API exists.
4. **Action cwd is the plugin root**, not the focused pane's cwd. Plugin pane cwd also defaults to the plugin root. Use `--cwd` or read cwd from the context.
5. **Popups have no `HERDR_PANE_ID`** and are not panes: no pane events, and `--current` does not work inside them. Pass the source pane id with `--env` from the action, or read `focused_pane_id` from `HERDR_PLUGIN_CONTEXT_JSON`.
6. **Only one popup at a time.** Opening another returns `ui_busy`, and so does opening while Settings or Copy mode is active.
7. **There is no `herdr popup close` CLI.** The popup closes when its process exits, or via the raw socket method `popup.close`.
8. **No action timeout. The concurrency cap is 32** across all plugins. Logs are in memory only and limited to 200.
9. **Keybinding precedence.** A `[[keys.command]]` binding silently overrides a same-key default binding, but is itself disabled if it collides with a key you set explicitly under `[keys]`. Use `herdr config check` to see diagnostics.
10. **Keep plugin ids lowercase**, or the config and state dir names get `%XX` escapes.
11. **Unknown manifest keys are silently ignored.** Typos such as `contxts` will not error. `contexts` is not enforced anyway.
12. **Event hook names are validated only with a warning.** A typo'd `on` value never fires; check the `warnings` field in `plugin list --json`.
13. **`pane run` types a shell command line.** It joins argv with spaces, so quote with `printf %q`. It does not wait for the shell to be ready; `agent start` does.
14. **`pane move` can silently no-op** (`changed:false`, `reason:"zoomed_tab"` or `"same_tab"`). Check `.result.move_result.changed`.
15. **After a cross-workspace move the pane id changes.** A new-tab move within the same workspace keeps the workspace prefix; still, always use `.result.move_result.pane.pane_id`.
16. **`agent_session` is only present after `herdr integration install claude`** has installed the SessionStart hook, and only once Claude has started or resumed inside that pane. It is omitted otherwise. Make fork-tab fail gracefully with a `notification show`.
17. **`pane current` returns `type: "pane_current"`**, not `pane_info` as the generic docs example suggests.
18. **CLI errors go to stderr as JSON with exit code 1.** Usage errors exit 2. `set -e` scripts should capture stderr for the user-facing message.
19. **Relinking.** Scripts are read fresh on every run, and the registry is reloaded on every invoke. After editing `herdr-plugin.toml`, run `herdr plugin link <dir>` again to refresh the stored manifest.
20. **There is no `herdr plugin update`.** Reinstall from GitHub. Installing over a locally linked plugin with the same id is refused; `unlink` first.
21. **`agent_status = "done"` only exists while nobody has looked.** It is durable (measured: >24 minutes) for an unseen agent, but an agent that finishes in a pane you are watching goes straight to `idle` and never passes through `done`. There is no seen field to read instead. See §9.7.
22. **The claude integration hook needs `HERDR_PANE_ID`.** Without it (a popup has none) the hook exits silently and herdr never learns the session id, even though Claude itself starts fine. See §7.4.
23. **`pane get` takes its id positionally**, unlike `pane current` and `pane process-info`, which take `--pane ID`. `pane get --pane w1:p1` exits 2. See §9.6.
24. **`agent_session.value` can be stale or resume a discarded branch.** After a Claude resume the
    conversation moves to a new id that herdr learns late, and a rewind leaves a branch that
    `--resume` may pick. See §7.4.
25. **llms-full.txt inconsistency.** `https://herdr.dev/llms-full.txt` has an older landing-page blurb ("tag your repo to be listed when the marketplace launches"). The versioned `marketplace.mdx` says the marketplace is live at herdr.dev/plugins.

