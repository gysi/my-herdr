"""Popup: ask for the forked tab's name, then have herdr run the fork.

The fork itself does not run here. A popup stays on screen until its process
exits, and `agent start` waits for the agent to replay the whole session, so a
popup that forked in place would sit over the new tab for that entire wait.

Instead the popup leaves the name and the source pane as a request (see
`fork_request`) and invokes the ordinary `fork-tab` action. `plugin action
invoke` returns as soon as herdr has started the action, so the popup closes at
once and the new tab is visible while the agent comes up. The fork is then an
action like any other: herdr launches it, logs it, and gives it the action
environment.

The agent is started by `agent start` in the new tab's own pane, never in this
popup, so the fork has a HERDR_PANE_ID and registers its session id.
"""
import os
import sys

from .. import fork_request, herdr, prompt
from ..actions.fork_tab_ask import SOURCE_ENV
from ..context import Context
from ..errors import MyHerdrError

#: The action that does the forking, unqualified.
FORK_ACTION = "fork-tab"

HEADER = "Fork this session into a new tab.\n"
HINT = "Enter: fork   Esc: cancel   (no name: herdr's default)\n\n"
LABEL = "Tab name: "


def main(args):
    """Ask for a tab label and dispatch the fork, or close on cancellation.

    Args:
        args (list[str]): Dispatcher arguments; unused by this popup entrypoint.

    Returns:
        int: 0 after requesting the fork or cancelling without creating a request.

    Raises:
        MyHerdrError: The source pane is missing, the request cannot be saved,
            or herdr refuses the action invocation.
    """
    ctx = Context()
    pane_id = os.environ.get(SOURCE_ENV) or ctx.pane_id
    if not pane_id:
        raise MyHerdrError("no source pane was passed to the popup")

    sys.stdout.write(HEADER + HINT)
    name = prompt.ask(LABEL)
    if name is None:
        return 0  # cancelled: nothing was created, nothing to report

    request_fork(ctx, pane_id, name.strip() or None)
    return 0


def request_fork(ctx, pane_id, name):
    """Save the request and have herdr start fork-tab to claim it.

    Args:
        ctx (Context): Invocation context providing the plugin ID and state path.
        pane_id (str): Source pane whose current session the action will re-read.
        name (str or None): Requested tab label, or None for default naming.

    Raises:
        MyHerdrError: Saving or dispatch fails. A failed dispatch withdraws
            the request so a later fork does not accidentally consume it.
    """
    fork_request.save(ctx.state_dir, pane_id, name)
    try:
        herdr.run_json("plugin", "action", "invoke", "%s.%s" % (ctx.plugin_id, FORK_ACTION))
    except MyHerdrError:
        # Nothing will take it now, and a later plain fork-tab must not.
        fork_request.drop(ctx.state_dir)
        raise
