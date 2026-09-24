"""Fork the Claude Code or Codex session of a pane into a new tab.

The fork starts with the full conversation of the original and is otherwise
independent: the source session keeps running and is not touched.

The routine lives here rather than in the action module so that the fork is
one piece of code however it is reached: bound to a key directly, or through
the popup that asks for a tab name first.

Why `agent start` rather than typing a command into the new pane: it waits for
the shell to be ready and for the agent to actually come up, and it fails loudly
instead of leaving a half-typed command line behind. It costs a throwaway agent
name, which is cleared again once the agent is up.

The new tab is focused as soon as it exists, not once the fork is up. Waiting
would leave you staring at the old pane for as long as the agent takes to replay
the session, unable to do anything useful in it, which reads as lag; watching
the fork boot reads as progress. Focus is not gated on readiness — herdr
focuses an ordinary new tab before its shell has started too. The cost is that
a fork that fails has to put focus back, which `abandon()` does.
"""
import os

from . import agents
from ..shared import herdr
from ..shared.errors import MyHerdrError

#: `agent start` waits for the agent to be ready for input. The CLI default is
#: 30000 ms, which a cold start with a large session to replay can exceed.
START_TIMEOUT_MS = 60000

#: Room for herdr's own wait plus the round trip, so the CLI's timeout is the
#: one that fires and reports properly, not the subprocess kill.
START_TIMEOUT = START_TIMEOUT_MS / 1000.0 + 15.0

#: A new tab's shell needs a moment before `agent start` will accept the pane.
SHELL_TIMEOUT = 10.0


def fork_into_new_tab(pane_id, name=None, env=None):
    """Fork a pane's Claude Code or Codex session into a new, focused tab.

    Args:
        pane_id (str): Source herdr pane ID, such as ``w1:p1``. Its current
            agent supplies the session ID, workspace, and working directory.
        name (str or None): Optional tab label, also used as the saved session
            name for Claude. None or an empty string keeps default naming.
        env (Mapping[str, str] or None): Environment used to resolve Claude's
            store and select configuration variables to forward to the tab.
            None uses os.environ; an empty mapping supplies no overrides.
            This does not replace the environment of herdr subprocesses.

    Returns:
        dict: ``tab_id`` (str or None) and ``pane_id`` (str) for the new tab
            and pane. The tab ID is None if herdr did not report one.

    Raises:
        MyHerdrError: Source validation, tab creation, shell readiness, or
            agent startup failed. After creation, cleanup attempts to close
            the new tab and restore source focus before propagating errors.
    """
    agent = agents.forkable_agent(pane_id, env)
    kind = agent["agent"]
    session_id = agent["agent_session"]["value"]
    cwd = agent.get("foreground_cwd") or agent.get("cwd")
    workspace_id = agent.get("workspace_id") or pane_id.split(":")[0]

    created = herdr.run_json(*tab_create_args(workspace_id, cwd, name, env, kind=kind))
    tab_id = (created.get("tab") or {}).get("tab_id")
    new_pane = (created.get("root_pane") or {}).get("pane_id")
    if not new_pane:
        abandon(tab_id, pane_id)
        raise MyHerdrError("herdr created a tab but reported no pane to start the fork in")

    try:
        if not herdr.wait_shell_ready(new_pane, timeout=SHELL_TIMEOUT):
            raise MyHerdrError(
                "the new tab's shell did not reach a prompt within %gs" % SHELL_TIMEOUT)
        herdr.run_json(
            *agent_start_args(new_pane, session_id, name, kind=kind), timeout=START_TIMEOUT)
    except BaseException:
        # Including the interrupt: a tab holding a fork that never started is
        # worse than no tab, and nobody asked for an empty shell.
        abandon(tab_id, pane_id)
        raise

    # The throwaway name was only needed because `agent start` requires one;
    # left in place it would show up as the agent's alias from here on.
    herdr.try_json("agent", "rename", new_pane, "--clear")
    return {"tab_id": tab_id, "pane_id": new_pane}


def tab_create_args(workspace_id, cwd, name=None, env=None, kind="claude"):
    """Build arguments to create and focus the fork's tab.

    Args:
        workspace_id (str): Source workspace ID in which to create the tab.
        cwd (str or None): Source agent's working directory. None or an empty
            string omits --cwd and lets herdr choose its default directory.
        name (str or None): Optional tab label; None or an empty string omits it.
        env (Mapping[str, str] or None): Environment from which to select the
            agent's configuration override. None uses os.environ.
        kind (str): Agent kind, "claude" (default) or "codex", which selects
            CLAUDE_CONFIG_DIR or CODEX_HOME for forwarding.

    Returns:
        list[str]: herdr arguments, excluding the executable, with --focus.

    Raises:
        MyHerdrError: The agent kind is unsupported.
    """
    args = ["tab", "create", "--workspace", workspace_id]
    if cwd:
        args += ["--cwd", cwd]
    if name:
        args += ["--label", name]
    for key, value in sorted(agents.forwarded_env(kind, env).items()):
        args += ["--env", "%s=%s" % (key, value)]
    args.append("--focus")
    return args


def agent_start_args(pane_id, session_id, name=None, kind="claude"):
    """Build arguments to start the fork through herdr without shell quoting.

    Args:
        pane_id (str): Destination pane ID; its shell must be ready at launch.
        session_id (str): Source agent's native session ID to fork.
        name (str or None): Optional saved-session name for Claude. None or an
            empty string omits it; Codex ignores it.
        kind (str): Agent kind, "claude" (default) or "codex".

    Returns:
        list[str]: herdr arguments, excluding the executable, including a
            temporary agent name, startup timeout, and agent-specific argv.

    Raises:
        MyHerdrError: The agent kind is unsupported.
    """
    return ["agent", "start", temp_agent_name(), "--kind", kind,
            "--pane", pane_id, "--timeout", str(START_TIMEOUT_MS),
            "--"] + agents.fork_args(kind, session_id, name)


def temp_agent_name():
    """A name for `agent start`, cleared again as soon as the agent is up.

    herdr requires `[a-z][a-z0-9_-]{0,31}` and uniqueness among live agents;
    the pid keeps concurrent invocations apart and stays well inside 32 chars.

    Returns:
        str: ``mh-fork-<pid>`` for this action process.
    """
    return "mh-fork-%d" % os.getpid()


def abandon(tab_id, source_pane_id):
    """Undo a fork that did not come up: close its tab, go back where we were.

    Both steps are best effort, because they run while an error is already on
    its way out and must not replace it with their own. Closing the focused tab
    leaves herdr to pick the next one, which is rarely where the key was
    pressed, so the source pane is focused explicitly rather than left to luck.

    Args:
        tab_id (str or None): New tab to close; None or an empty string skips
            closing when its ID is unavailable.
        source_pane_id (str or None): Original pane to focus; None or an empty
            string skips focus restoration.
    """
    if tab_id:
        herdr.try_json("tab", "close", tab_id)
    if source_pane_id:
        herdr.try_json("agent", "focus", source_pane_id)
