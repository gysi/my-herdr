"""Move the focused pane into a tab of its own, taking its process with it.

For the moment a split has outgrown its share of the screen: the agent running
in it keeps running, and lands in a full-width tab.

The tab keeps herdr's generic name. A label is deliberately not set: a
plugin-set label looks like a manual rename to the tab-renaming plugins, which
then leave it alone forever.

If the pane is already alone in its tab there is nothing to do, and herdr would
otherwise destroy the old tab and build a new one for the same single pane —
visible churn in the tab bar for no result. That case is detected up front and
reported instead.
"""
from .. import herdr
from ..context import Context


def main(args):
    ctx = Context()
    pane_id = herdr.focused_pane(ctx)

    if is_alone(pane_id, ctx):
        herdr.notify("This pane is already alone in its tab.")
        print("pane-to-tab: %s is already alone in its tab" % pane_id)
        return 0

    result = herdr.run_json(
        "pane", "move", pane_id, "--new-tab", "--workspace", workspace_of(pane_id, ctx),
        "--focus")
    move = result.get("move_result") or {}
    if not move.get("changed"):
        # A zoomed source or target tab makes the move a silent no-op rather
        # than an error, so the answer has to be read, not assumed.
        reason = move.get("reason") or "unknown"
        herdr.notify("Could not move the pane (%s)." % reason)
        print("pane-to-tab: %s not moved (reason: %s)" % (pane_id, reason))
        return 0

    # A cross-workspace move renames the pane; always report what came back.
    moved = move.get("pane") or {}
    print("pane-to-tab: moved %s to tab %s (now %s)" % (
        move.get("previous_pane_id") or pane_id,
        (move.get("created_tab") or {}).get("tab_id") or "?",
        moved.get("pane_id") or pane_id))
    return 0


def is_alone(pane_id, ctx):
    """True when `pane_id`'s tab holds nothing else.

    Best effort: when the tab cannot be identified, say no and let the move
    proceed. A pointless move is a smaller failure than refusing a valid one.
    """
    tab_id = tab_of(pane_id, ctx)
    if not tab_id:
        return False
    for tab in tabs(ctx):
        if tab.get("tab_id") == tab_id:
            return tab.get("pane_count") == 1
    return False


def tabs(ctx):
    """Every tab in this workspace, or an empty list if herdr will not say."""
    workspace_id = ctx.workspace_id
    args = ["tab", "list"]
    if workspace_id:
        args += ["--workspace", workspace_id]
    return (herdr.try_json(*args) or {}).get("tabs") or []


def tab_of(pane_id, ctx):
    """The tab holding `pane_id`: from the context if it describes that pane."""
    if ctx.pane_id == pane_id and ctx.tab_id:
        return ctx.tab_id
    return pane_info(pane_id).get("tab_id")


def workspace_of(pane_id, ctx):
    """The workspace to create the tab in.

    Passing it explicitly keeps the new tab where the pane already lives,
    rather than wherever the server considers current.
    """
    if ctx.pane_id == pane_id and ctx.workspace_id:
        return ctx.workspace_id
    return pane_info(pane_id).get("workspace_id") or pane_id.split(":")[0]


def pane_info(pane_id):
    """One pane as herdr sees it, or an empty dict. `pane get` takes a positional id."""
    return (herdr.try_json("pane", "get", pane_id) or {}).get("pane") or {}
