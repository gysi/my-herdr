"""Popup: ask for the forked tab's name, then have herdr run the fork.

The fork itself does not run here. A popup stays on screen until its process
exits, and `agent start` waits for Claude to replay the whole session, so a
popup that forked in place would sit over the new tab for that entire wait.

Instead the popup leaves the name and the source pane as a request (see
`fork_request`) and invokes the ordinary `fork-tab` action. `plugin action
invoke` returns as soon as herdr has started the action, so the popup closes at
once and the new tab is visible while Claude comes up. The fork is then an
action like any other: herdr launches it, logs it, and gives it the action
environment.

Claude is started by `agent start` in the new tab's own pane, never in this
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

HEADER = "Fork this Claude session into a new tab\n"
HINT = "Enter: fork   Esc: cancel   (no name: herdr's default)\n\n"
LABEL = "Tab name: "


def main(args):
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
    """Leave the request and have herdr start `fork-tab` to take it."""
    fork_request.save(ctx.state_dir, pane_id, name)
    try:
        herdr.run_json("plugin", "action", "invoke", "%s.%s" % (ctx.plugin_id, FORK_ACTION))
    except MyHerdrError:
        # Nothing will take it now, and a later plain fork-tab must not.
        fork_request.drop(ctx.state_dir)
        raise
