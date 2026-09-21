"""Fork the Claude Code session of a pane into a new tab.

The fork starts with the full conversation of the original and is otherwise
independent: the source session keeps running and is not touched.

The routine lives here rather than in the action module so that the fork is
one piece of code however it is reached: bound to a key directly, or through
the popup that asks for a tab name first.

Why `agent start` rather than typing a command into the new pane: it waits for
the shell to be ready and for Claude to actually come up, and it fails loudly
instead of leaving a half-typed command line behind. It costs a throwaway agent
name, which is cleared again once the agent is up.

The new tab is focused as soon as it exists, not once the fork is up. Waiting
would leave you staring at the old pane for as long as Claude takes to replay
the session, unable to do anything useful in it, which reads as lag; watching
the fork boot reads as progress. Focus is not gated on readiness — herdr
focuses an ordinary new tab before its shell has started too. The cost is that
a fork that fails has to put focus back, which `abandon()` does.
"""
import glob
import os

from . import herdr
from .errors import MyHerdrError

#: `agent start` waits for Claude to be ready for input. The CLI default is
#: 30000 ms, which a cold start with a large session to replay can exceed.
START_TIMEOUT_MS = 60000

#: Room for herdr's own wait plus the round trip, so the CLI's timeout is the
#: one that fires and reports properly, not the subprocess kill.
START_TIMEOUT = START_TIMEOUT_MS / 1000.0 + 15.0

#: A new tab's shell needs a moment before `agent start` will accept the pane.
SHELL_TIMEOUT = 10.0

#: Not inherited by the new tab's shell, because herdr's server environment is
#: what plugin commands and new panes get, not the shell the source agent was
#: started from. Forwarded explicitly so a fork of a session in an alternate
#: Claude config lands in the same config.
FORWARDED_ENV = ("CLAUDE_CONFIG_DIR",)


def fork_into_new_tab(pane_id, name=None, env=None):
    """Fork the Claude session running in `pane_id` into a new tab.

    `name` labels the tab and names the forked session; without one the tab
    keeps herdr's generic name, so tab-renaming plugins and Claude's own title
    can take it over.

    Returns the new tab and pane ids. Raises MyHerdrError for anything that
    stops the fork, having closed the new tab again if it got that far.
    """
    agent = claude_agent(pane_id, env)
    session_id = agent["agent_session"]["value"]
    cwd = agent.get("foreground_cwd") or agent.get("cwd")
    workspace_id = agent.get("workspace_id") or pane_id.split(":")[0]

    created = herdr.run_json(*tab_create_args(workspace_id, cwd, name, env))
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
            *agent_start_args(new_pane, session_id, name), timeout=START_TIMEOUT)
    except BaseException:
        # Including the interrupt: a tab holding a fork that never started is
        # worse than no tab, and nobody asked for an empty shell.
        abandon(tab_id, pane_id)
        raise

    # The throwaway name was only needed because `agent start` requires one;
    # left in place it would show up as the agent's alias from here on.
    herdr.try_json("agent", "rename", new_pane, "--clear")
    return {"tab_id": tab_id, "pane_id": new_pane}


def claude_agent(pane_id, env=None):
    """The agent running in `pane_id`, once it is established it can be forked.

    Raises rather than returning None: every caller needs a session id, and
    each way of not having a usable one needs its own explanation.
    """
    result = herdr.try_json("agent", "get", pane_id)
    agent = (result or {}).get("agent") or {}
    kind = agent.get("agent")
    if not kind:
        raise MyHerdrError("no agent is running in %s" % pane_id)
    if kind != "claude":
        raise MyHerdrError(
            "fork-tab only works on Claude Code panes; %s runs %s" % (pane_id, kind))

    session = agent.get("agent_session") or {}
    if session.get("kind") != "id" or not session.get("value"):
        # herdr learns the id from the Claude hook when Claude starts in the
        # pane. That never happens for Claude's background-sessions view
        # (`claude agents`): the session runs in Claude's daemon, detached from
        # any pane. Otherwise it is a missing integration, or a session that
        # started before it was installed.
        raise MyHerdrError(
            "herdr does not know this Claude session's id, so there is nothing to fork. "
            "Start the session in this pane with `claude --resume <id>`, not through "
            "Claude's background-sessions view, and make sure `herdr integration install "
            "claude` has been run.")

    saved = conversation_saved(session["value"], env)
    # One line per fork in the plugin log: which pane, which id herdr holds,
    # and whether Claude has that conversation. When herdr's id is stale (see
    # README), this is the line that shows it, without hunting for processes.
    print("fork: %s runs claude session %s (saved conversation: %s, in %s)" % (
        pane_id, session["value"], {True: "yes", False: "no", None: "cannot tell"}[saved],
        os.path.join(claude_config_dir(env), "projects")))
    if saved is False:
        # `--resume` would find nothing: Claude exits at once, but `agent
        # start` only gives up at its timeout, so this saves a minute in a
        # tab that shows nothing but Claude's error.
        raise MyHerdrError(
            "Claude has no saved conversation for this session yet, so there is nothing to "
            "fork. Send it a message first. If it already has some, restart Claude in this "
            "pane: herdr may still hold the id it had before a resume.")
    return agent


def conversation_saved(session_id, env=None):
    """Whether Claude has the conversation `--resume <session_id>` would load.

    True or False from Claude's own store: `<config>/projects/<dir>/<id>.jsonl`.
    None when there is no store to look in, and the caller must not refuse
    on a guess. The config directory is the one the fork will use, resolved
    the same way, so the check cannot rule out a session the fork would find.
    """
    projects = os.path.join(claude_config_dir(env), "projects")
    if not os.path.isdir(projects):
        return None
    pattern = os.path.join(glob.escape(projects), "*", glob.escape(session_id) + ".jsonl")
    return bool(glob.glob(pattern))


def claude_config_dir(env=None):
    """Claude's config directory: CLAUDE_CONFIG_DIR, else ~/.claude."""
    env = os.environ if env is None else env
    configured = env.get("CLAUDE_CONFIG_DIR")
    if configured:
        return os.path.expanduser(configured)
    home = env.get("HOME") or os.path.expanduser("~")
    return os.path.join(home, ".claude")


def tab_create_args(workspace_id, cwd, name=None, env=None):
    """`tab create` for the fork's tab: same workspace, same directory.

    The directory matters beyond convenience: Claude keys its sessions by
    project directory, so a fork started elsewhere would not find the session.
    """
    args = ["tab", "create", "--workspace", workspace_id]
    if cwd:
        args += ["--cwd", cwd]
    if name:
        args += ["--label", name]
    for key, value in sorted(forwarded_env(env).items()):
        args += ["--env", "%s=%s" % (key, value)]
    args.append("--focus")
    return args


def agent_start_args(pane_id, session_id, name=None):
    """`agent start` for the fork.

    `--fork-session` makes Claude branch the resumed session instead of
    continuing it, which is what leaves the original untouched. Everything
    after `--` goes to Claude as an argv list, so a name with spaces or quotes
    needs no quoting anywhere.
    """
    args = ["agent", "start", temp_agent_name(), "--kind", "claude",
            "--pane", pane_id, "--timeout", str(START_TIMEOUT_MS),
            "--", "--resume", session_id, "--fork-session"]
    if name:
        args += ["-n", name]
    return args


def temp_agent_name():
    """A name for `agent start`, cleared again as soon as the agent is up.

    herdr requires `[a-z][a-z0-9_-]{0,31}` and uniqueness among live agents;
    the pid keeps concurrent invocations apart and stays well inside 32 chars.
    """
    return "mh-fork-%d" % os.getpid()


def forwarded_env(env=None):
    """The variables worth carrying into the fork's shell, if they are set."""
    env = os.environ if env is None else env
    return {key: env[key] for key in FORWARDED_ENV if env.get(key)}


def abandon(tab_id, source_pane_id):
    """Undo a fork that did not come up: close its tab, go back where we were.

    Both steps are best effort, because they run while an error is already on
    its way out and must not replace it with their own. Closing the focused tab
    leaves herdr to pick the next one, which is rarely where the key was
    pressed, so the source pane is focused explicitly rather than left to luck.
    """
    if tab_id:
        herdr.try_json("tab", "close", tab_id)
    if source_pane_id:
        herdr.try_json("agent", "focus", source_pane_id)
