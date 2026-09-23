#!/usr/bin/env python3
"""Validate herdr-plugin.toml before herdr gets a chance to reject it.

`herdr plugin link .` is the authoritative validator, but it needs a running
herdr and it only reports the first problem. This checks the rules from the
plugin docs offline, plus one herdr cannot know: that every declared id has a
module behind it, so a typo fails here instead of at keypress time.

    python3 tests/check_manifest.py [path]

Uses tomllib (Python 3.11+); the plugin itself stays 3.9-compatible.
"""
import os
import re
import sys

try:
    import tomllib
except ImportError:  # pragma: no cover - only on Python < 3.11
    tomllib = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLUGIN_ID_RE = re.compile(r"^[A-Za-z0-9.:_-]{1,120}$")
LOCAL_ID_RE = re.compile(r"^[A-Za-z0-9:_-]+$")  # no dots: qualified ids stay splittable
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+")
PLATFORMS = {"linux", "macos", "windows"}
PLACEMENTS = {"overlay", "popup", "split", "tab", "zoomed"}

REQUIRED = ("id", "name", "version", "min_herdr_version")

#: manifest section -> package directory holding one module per id
MODULE_DIRS = {"actions": "actions", "panes": "panes"}


def check(manifest, root=ROOT):
    """Validate a parsed manifest and its entrypoint files without live herdr.

    Args:
        manifest (dict): Parsed TOML manifest, including any deliberately invalid
            field values used in tests.
        root (str): Plugin root for checking module paths; defaults to this checkout.

    Returns:
        list[str]: Validation problems; an empty list means the manifest passed.
    """
    problems = []

    def bad(message):
        """Append one diagnostic to the enclosing validation result.

        Args:
            message (str): Problem description to report to the developer.
        """
        problems.append(message)

    for key in REQUIRED:
        value = manifest.get(key)
        if not isinstance(value, str) or not value.strip():
            bad("missing or empty required key: %s" % key)

    plugin_id = manifest.get("id")
    if isinstance(plugin_id, str) and plugin_id:
        if not PLUGIN_ID_RE.match(plugin_id):
            bad("id %r: allowed are ASCII letters, digits, dot, colon, underscore, hyphen (max 120)"
                % plugin_id)
        if plugin_id != plugin_id.lower():
            # herdr percent-escapes every byte outside [a-z0-9._-] in the
            # config and state directory names, so `My.Plugin` becomes
            # `%4Dy.%50lugin` on disk.
            bad("id %r should be lowercase, or the config/state dirs get %%XX escapes" % plugin_id)

    version = manifest.get("min_herdr_version")
    if isinstance(version, str) and not SEMVER_RE.match(version or ""):
        bad("min_herdr_version %r is not a semantic version (a value above the running herdr is a "
            "hard load failure)" % version)

    platforms = manifest.get("platforms")
    if platforms is None:
        bad("no platforms declared (link warns: 'platform support unknown')")
    elif not isinstance(platforms, list) or not set(platforms) <= PLATFORMS:
        bad("platforms must be a subset of %s, got %r" % (sorted(PLATFORMS), platforms))

    for section in ("actions", "panes", "link_handlers", "events", "startup", "build"):
        entries = manifest.get(section, [])
        if not isinstance(entries, list):
            bad("%s must be an array of tables" % section)
            continue
        problems.extend(check_section(section, entries, root))

    problems.extend(check_link_handlers(manifest))
    return problems


def check_section(section, entries, root):
    """Validate IDs, commands, and section-specific properties.

    Args:
        section (str): Manifest table-array name, such as "actions" or "panes".
        entries (list[dict]): Parsed entries belonging to that section.
        root (str): Plugin directory for module existence checks.

    Returns:
        list[str]: Diagnostics for invalid or duplicate entries.
    """
    problems = []
    seen = set()
    for index, entry in enumerate(entries):
        where = "%s[%d]" % (section, index)

        if section in ("actions", "panes", "link_handlers"):
            entry_id = entry.get("id")
            if not isinstance(entry_id, str) or not LOCAL_ID_RE.match(entry_id or ""):
                problems.append("%s: id %r must be letters, digits, colon, underscore or hyphen "
                                "(no dots)" % (where, entry_id))
            elif entry_id in seen:
                problems.append("%s: duplicate id %r in %s" % (where, entry_id, section))
            else:
                seen.add(entry_id)
                problems.extend(check_module(section, entry_id, entry, root))

            if not entry.get("title"):
                problems.append("%s: title is required" % where)

        if section != "link_handlers":
            problems.extend(check_command(where, entry.get("command")))

        if section == "panes":
            problems.extend(check_pane(where, entry))

    return problems


def check_command(where, command):
    """Check that a manifest command is a nonempty string argv list.

    Args:
        where (str): Entry location to include in diagnostics, such as "actions[0]".
        command (object): Command value, which may be absent or malformed.

    Returns:
        list[str]: Command diagnostics, or an empty list for a valid argv array.
    """
    # herdr runs these without a shell, so an empty element would become an
    # empty argv entry rather than disappearing.
    if not isinstance(command, list) or not command:
        return ["%s: command must be a non-empty argv array, got %r" % (where, command)]
    if not all(isinstance(part, str) and part for part in command):
        return ["%s: every command element must be a non-empty string: %r" % (where, command)]
    return []


def check_pane(where, entry):
    """Validate a pane's placement and popup-only dimensions.

    Args:
        where (str): Manifest entry location for diagnostics.
        entry (dict): Pane declaration; missing placement defaults to overlay.

    Returns:
        list[str]: Placement and dimension diagnostics, possibly empty.
    """
    problems = []
    placement = entry.get("placement", "overlay")
    if placement not in PLACEMENTS:
        problems.append("%s: placement %r must be one of %s"
                        % (where, placement, sorted(PLACEMENTS)))
    if placement != "popup" and ("width" in entry or "height" in entry):
        # herdr fails the link with invalid_plugin_pane_size.
        problems.append("%s: width/height are only valid with placement = \"popup\"" % where)
    return problems


def check_module(section, entry_id, entry, root):
    """Check that an action or pane declaration routes to an existing module.

    Args:
        section (str): Manifest section; only actions and panes have modules.
        entry_id (str): Validated local ID, with dashes mapped to module underscores.
        entry (dict): Declaration whose command must mention its own ID.
        root (str): Plugin checkout directory to inspect.

    Returns:
        list[str]: Routing diagnostics; empty for valid or non-module sections.
    """
    directory = MODULE_DIRS.get(section)
    if directory is None:
        return []

    module = entry_id.replace("-", "_") + ".py"
    path = os.path.join(root, "myherdr", directory, module)
    if not os.path.exists(path):
        return ["%s %r: expected myherdr/%s/%s" % (section[:-1], entry_id, directory, module)]

    # The dispatcher picks the module from the argument, not from the id, so a
    # mismatch would run the wrong code.
    command = entry.get("command") or []
    if not any(entry_id in str(part) for part in command):
        return ["%s %r: command %r never mentions the id, so the dispatcher would route elsewhere"
                % (section[:-1], entry_id, command)]
    return []


def check_link_handlers(manifest):
    """Check that link handlers have patterns and refer to declared actions.

    Args:
        manifest (dict): Parsed manifest with action and link-handler arrays.

    Returns:
        list[str]: Missing-pattern or unknown-action diagnostics.
    """
    actions = {a.get("id") for a in manifest.get("actions", []) if isinstance(a, dict)}
    problems = []
    for index, handler in enumerate(manifest.get("link_handlers", [])):
        target = handler.get("action")
        if target not in actions:
            problems.append("link_handlers[%d]: action %r is not declared by this plugin"
                            % (index, target))
        if not handler.get("pattern"):
            problems.append("link_handlers[%d]: pattern is required" % index)
    return problems


def main(argv):
    """Read a manifest and print offline validation results.

    Args:
        argv (list[str]): Optional manifest path; empty uses this checkout's manifest.

    Returns:
        int: 0 for a valid manifest or an explicit skip without tomllib;
            1 for unreadable, malformed, or invalid manifests.
    """
    if tomllib is None:
        print("check_manifest: needs Python 3.11+ for tomllib, skipping")
        return 0

    path = argv[0] if argv else os.path.join(ROOT, "herdr-plugin.toml")
    root = os.path.dirname(os.path.abspath(path))
    try:
        with open(path, "rb") as handle:
            manifest = tomllib.load(handle)
    except (IOError, OSError) as exc:
        print("check_manifest: cannot read %s: %s" % (path, exc), file=sys.stderr)
        return 1
    except tomllib.TOMLDecodeError as exc:
        print("check_manifest: %s is not valid TOML: %s" % (path, exc), file=sys.stderr)
        return 1

    problems = check(manifest, root)
    for problem in problems:
        print("check_manifest: %s" % problem, file=sys.stderr)
    if problems:
        return 1
    print("manifest ok: %s (%d actions, %d panes)"
          % (manifest["id"], len(manifest.get("actions", [])), len(manifest.get("panes", []))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
