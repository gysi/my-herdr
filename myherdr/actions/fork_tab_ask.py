"""Ask for a tab name, then fork this pane's Claude Code or Codex session into a new tab.

The same fork as `fork-tab`, with a name, the way herdr's own new-tab asks for
one. An action has no terminal, so the asking happens in the `fork-prompt`
popup; this only decides whether there is anything to ask about.

The pane is checked before the popup opens: a pane that cannot be forked is
reported straight away, instead of after the user has typed a name for it.
"""
from .. import fork_agents, herdr
from ..context import Context

ENTRYPOINT = "fork-prompt"

#: Carries the source pane into the popup, which gets no HERDR_PANE_ID of its own.
SOURCE_ENV = "MH_SOURCE_PANE"


def main(args):
    """Validate the focused session and open the naming popup.

    Args:
        args (list[str]): Dispatcher arguments; unused by this headless action.

    Returns:
        int: 0 once herdr has opened the popup with the source pane ID.

    Raises:
        MyHerdrError: No forkable session is available or the popup cannot open.
    """
    ctx = Context()
    pane_id = herdr.focused_pane(ctx)
    fork_agents.forkable_agent(pane_id)

    herdr.run_json(
        "plugin", "pane", "open", "--plugin", ctx.plugin_id, "--entrypoint", ENTRYPOINT,
        "--env", "%s=%s" % (SOURCE_ENV, pane_id))
    print("fork-tab-ask: asking for a name to fork %s" % pane_id)
    return 0
