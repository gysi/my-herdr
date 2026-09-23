"""Read local herdr 0.9.1 sidebar preferences without changing user settings.

The preference filename is an internal herdr contract; see the research note.
The config reader extracts one scalar, not arbitrary TOML. Strings are tokenized
as units so unrelated multiline strings cannot impersonate a [ui] section.
"""
import json
import os
import re
import sys
import tempfile


_MODES = {"spaces": "spaces", "workspaces": "spaces", "priority": "priority"}
_TOKENS = re.compile(
    r'"""(?:\\.|(?!""").)*"""|\x27\x27\x27.*?\x27\x27\x27'
    r'|"(?:\\.|[^"\\\n])*"|\x27[^\x27\n]*\x27'
    r'|#[^\n]*|\n|[^\S\n]+|[A-Za-z0-9_-]+|.', re.DOTALL)


def preference_path(env):
    """Locate this local session's saved sidebar settings.

    Args:
        env (Mapping[str, str]): Invocation environment, including the API socket
            in HERDR_SOCKET_PATH. Its filename stem determines the client socket.

    Returns:
        str or None: Session-specific JSON path, or None without a socket path.
    """
    socket = env.get("HERDR_SOCKET_PATH")
    if not socket:
        return None
    # Client preferences hash the binary client socket, not the JSON API socket
    # supplied to plugins. See src/server/socket_paths.rs in herdr 0.9.1.
    parent, filename = os.path.split(socket)
    stem = os.path.splitext(filename)[0] or "herdr"
    socket = os.path.join(parent, stem + "-client.sock")
    digest = 0xcbf29ce484222325
    for byte in socket.encode("utf-8", errors="replace"):
        digest = ((digest ^ byte) * 0x100000001b3) & 0xffffffffffffffff
    root = _directory(env, "XDG_STATE_HOME", ".local/state", "herdr-state")
    return os.path.join(root, "client-shell", "local-%016x.json" % digest)


def sort_mode(env):
    """Read saved sort, configured sort, then the grouped default, in that order.

    Args:
        env (Mapping[str, str]): Invocation environment for socket, HOME, XDG paths,
            and optional HERDR_CONFIG_PATH. Never reads another session's preferences.

    Returns:
        str: "spaces" or "priority". Invalid settings are logged to stderr;
            missing or unreadable files fall through to the next source.
    """
    path = preference_path(env)
    if path:
        try:
            with open(path, encoding="utf-8") as handle:
                preferences = json.load(handle)
            if not isinstance(preferences, dict):
                raise ValueError("expected an object")
            value = preferences.get("agent_panel_sort")
            if value is not None:
                if isinstance(value, str) and value in _MODES:
                    return _MODES[value]
                _diagnostic("unsupported saved agent_panel_sort")
        except (ValueError, UnicodeError):
            _diagnostic("malformed sidebar preferences")
        except OSError:
            pass
    path = env.get("HERDR_CONFIG_PATH") or os.path.join(
        _directory(env, "XDG_CONFIG_HOME", ".config", "herdr"), "config.toml")
    try:
        with open(path, encoding="utf-8-sig") as handle:
            return config_sort(handle.read()) or "spaces"
    except UnicodeError:
        _diagnostic("malformed sidebar configuration")
    except OSError:
        pass
    return "spaces"


def config_sort(text):
    """Extract the sidebar sort scalar from conventional herdr TOML configuration.

    Args:
        text (str): Configuration contents. Supports [ui] with agent_panel_sort,
            or a root ui.agent_panel_sort assignment, single/double quoted keys
            and values, comments, and unrelated multiline strings.

    Returns:
        str or None: Normalized sort mode, or None when absent or unsupported.
            This is not a general TOML validator; unsupported target values log.
    """
    section = []
    statement = []
    found = None
    for token in _TOKENS.findall(text) + ["\n"]:
        if token.startswith("#") or (token.isspace() and token != "\n"):
            continue
        if token != "\n":
            statement.append(token)
            continue
        parts, statement = statement, []
        if not parts:
            continue
        if parts[0] == "[":
            section = [_unquote(part) for part in parts[1:-1]]
            continue
        if "=" not in parts:
            continue
        equals = parts.index("=")
        key = [_unquote(part) for part in parts[:equals]]
        if not ((section == ["ui"] and key == ["agent_panel_sort"])
                or (not section and key == ["ui", ".", "agent_panel_sort"])):
            continue
        values = parts[equals + 1:]
        value = _unquote(values[0]) if len(values) == 1 else None
        if (len(values) != 1 or not values[0].startswith(("'", '"'))
                or value not in _MODES):
            _diagnostic("unsupported configured agent_panel_sort")
            return None
        if found is not None:
            _diagnostic("duplicate configured agent_panel_sort")
            return None
        found = _MODES[value]
    return found


def _unquote(token):
    """Decode a simple TOML key or string used by the scalar reader.

    Args:
        token (str): A bare key or a quoted string token.

    Returns:
        str or None: Decoded value, or None for unsupported string syntax.
    """
    if token.startswith("'"):
        return token[1:-1] if not token.startswith("'''") else None
    if token.startswith('"'):
        try:
            return json.loads(token)
        except ValueError:
            return None
    return token


def _directory(env, xdg_key, home_suffix, temporary_name):
    """Resolve a herdr directory using its non-Windows path rules.

    Args:
        env (Mapping[str, str]): Environment to inspect, without implicit HOME lookup.
        xdg_key (str): XDG_CONFIG_HOME or XDG_STATE_HOME.
        home_suffix (str): Relative directory under HOME when XDG is absent.
        temporary_name (str): Directory under the temporary root when HOME is absent.

    Returns:
        str: herdr-specific directory for Linux or macOS.
    """
    if xdg_key in env:
        return os.path.join(env[xdg_key], "herdr")
    if "HOME" in env:
        return os.path.join(env["HOME"], home_suffix, "herdr")
    return os.path.join(tempfile.gettempdir(), temporary_name)


def _diagnostic(message):
    """Write a nonfatal preference diagnostic to the plugin log.

    Args:
        message (str): Description without private configuration contents.
    """
    print("attention: %s; falling back to configuration/defaults" % message, file=sys.stderr)
