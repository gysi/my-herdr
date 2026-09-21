"""Smoke test: dump the runtime environment to the plugin log.

    herdr plugin action invoke my-herdr.ping
    herdr plugin log list --plugin my-herdr --limit 1

Answers "is the plugin wired up, and what does herdr actually pass me here?"
without changing anything. Read-only: the one herdr call is `pane current`, and
it is best-effort.
"""
import json
import os
import sys

from .. import herdr
from ..context import Context


def main(args):
    ctx = Context()
    out = sys.stdout

    out.write("my-herdr ping\n")
    out.write("  argv        : %r\n" % (args,))
    out.write("  python      : %s\n" % sys.version.split()[0])
    out.write("  executable  : %s\n" % sys.executable)
    out.write("  cwd         : %s\n" % os.getcwd())
    out.write("  herdr bin   : %s\n" % herdr.bin_path())
    out.write("  invoked by  : %s\n" % (ctx.invocation_source or "?"))

    out.write("\nHERDR_* environment:\n")
    for key, value in ctx.herdr_env():
        # The context JSON is printed in full below; keep the listing readable.
        if key == "HERDR_PLUGIN_CONTEXT_JSON":
            value = "<%d bytes, see below>" % len(value)
        out.write("  %-28s %s\n" % (key, value))

    out.write("\nHERDR_PLUGIN_CONTEXT_JSON:\n")
    if ctx.raw:
        out.write(json.dumps(ctx.raw, indent=2, sort_keys=True) + "\n")
    elif ctx.env.get("HERDR_PLUGIN_CONTEXT_JSON"):
        out.write("  (unparsable: %r)\n" % ctx.env["HERDR_PLUGIN_CONTEXT_JSON"][:200])
    else:
        out.write("  (not set — not running under herdr?)\n")

    out.write("\nresolved:\n")
    out.write("  pane_id     : %s\n" % (ctx.pane_id or "-"))
    out.write("  tab_id      : %s\n" % (ctx.tab_id or "-"))
    out.write("  workspace_id: %s\n" % (ctx.workspace_id or "-"))
    out.write("  pane_cwd    : %s\n" % (ctx.pane_cwd or "-"))

    # Proves the CLI wrapper can reach the server from inside a plugin process.
    current = herdr.try_json("pane", "current")
    pane = (current or {}).get("pane") or {}
    out.write("  pane current: %s (agent=%s status=%s)\n" % (
        pane.get("pane_id") or "unavailable",
        pane.get("agent") or "-",
        pane.get("agent_status") or "-"))
    return 0
