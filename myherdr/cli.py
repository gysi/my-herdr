"""Dispatcher: maps `my-herdr <action>` / `my-herdr pane <entrypoint>` to a module.

Every action is `myherdr/actions/<id>.py` with a `main(args)`; every pane
entrypoint is `myherdr/panes/<id>.py` with the same shape. Adding one means
adding a module and an `[[actions]]` block, nothing here.

This is also where MyHerdrError stops. How it is reported depends on where the
code runs: a headless action has no TTY and its output only reaches
`herdr plugin log list`, so it toasts; a pane has a user in front of it and
must not vanish before they read the message.
"""
import importlib
import os
import re
import sys

from . import herdr
from .context import Context
from .errors import MyHerdrError

USAGE = """usage: my-herdr <action> [args...]
       my-herdr pane <entrypoint> [args...]"""

#: Same charset herdr allows for action and pane ids (no dots), so a manifest
#: id maps to exactly one module and nothing else can be imported.
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        print()
        print("actions:     %s" % (", ".join(available("actions")) or "(none)"))
        print("entrypoints: %s" % (", ".join(available("panes")) or "(none)"))
        return EXIT_OK if argv else EXIT_USAGE

    if argv[0] == "pane":
        if len(argv) < 2:
            return usage_error("my-herdr pane needs an entrypoint id")
        return dispatch("panes", argv[1], argv[2:], interactive=True)

    return dispatch("actions", argv[0], argv[1:], interactive=False)


def dispatch(kind, name, args, interactive):
    if not ID_RE.match(name):
        return usage_error("invalid %s id: %r" % (kind[:-1], name))

    try:
        module = importlib.import_module("myherdr.%s.%s" % (kind, name.replace("-", "_")))
    except ImportError as exc:
        # An ImportError from inside the module itself is a real bug and must
        # not be reported as "unknown action".
        if getattr(exc, "name", None) != "myherdr.%s.%s" % (kind, name.replace("-", "_")):
            raise
        return usage_error(
            "unknown %s %r (available: %s)"
            % (kind[:-1], name, ", ".join(available(kind)) or "none"))

    try:
        return module.main(args) or EXIT_OK
    except MyHerdrError as exc:
        return report(exc, interactive)
    except (KeyboardInterrupt, EOFError):
        # In a popup this is the user pressing Ctrl-C/Ctrl-D to cancel, which
        # is a normal outcome, not a failure.
        return EXIT_OK if interactive else EXIT_INTERRUPTED


def report(exc, interactive):
    prefix = Context().plugin_id
    sys.stderr.write("%s: %s\n" % (prefix, exc))
    if interactive:
        # The popup closes the moment this process exits, so hold it open.
        # A blocking read only: `read` with a timeout gets EOF immediately in a
        # herdr popup when idle.
        sys.stderr.write("[press Enter to close]")
        sys.stderr.flush()
        try:
            sys.stdin.readline()
        except (KeyboardInterrupt, EOFError):
            pass
    else:
        herdr.notify(str(exc), sound="request")
    return EXIT_ERROR


def usage_error(message):
    sys.stderr.write("my-herdr: %s\n%s\n" % (message, USAGE))
    return EXIT_USAGE


def available(kind):
    """Module names under myherdr/<kind>/, as manifest ids (underscores back to dashes)."""
    directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), kind)
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    return sorted(
        n[:-3].replace("_", "-")
        for n in names
        if n.endswith(".py") and not n.startswith("_")
    )
