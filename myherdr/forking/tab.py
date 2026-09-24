"""Fork this pane's Claude Code or Codex session into a new tab.

For the moment you want to try something without losing where you are: the new
tab starts from the same conversation, and the session you forked from carries
on untouched.

Bound to a key, the source is the focused pane and no name is set, so the tab
keeps herdr's generic name and whatever renames your tabs — a tab-renaming
plugin, or the agent's own title — stays in charge of it.

The `fork-prompt` popup runs this same action after asking for a name. It
passes the name, and the pane it asked about, through a request in the state
directory (see `request.py`), because herdr actions take no arguments.
"""
from . import request, workflow
from ..shared import herdr
from ..shared.context import Context


def main(args):
    """Fork the requested source pane or the currently focused pane.

    Args:
        args (list[str]): Dispatcher arguments; unused because herdr actions
            take no runtime parameters. Named forks use the request file.

    Returns:
        int: 0 after the new tab and pane have been reported to the plugin log.

    Raises:
        MyHerdrError: No source pane is available, validation fails, or the fork
            cannot start. The dispatcher logs and notifies the user.
    """
    ctx = Context()
    pending = request.take(ctx.state_dir)
    if pending:
        pane_id, name = pending["pane_id"], pending["name"]
    else:
        pane_id, name = herdr.focused_pane(ctx), None

    forked = workflow.fork_into_new_tab(pane_id, name=name)

    print("fork-tab: forked %s into tab %s (pane %s)%s"
          % (pane_id, forked["tab_id"] or "?", forked["pane_id"],
             " named %r" % name if name else ""))
    return 0
