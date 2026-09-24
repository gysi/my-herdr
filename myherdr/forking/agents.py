"""Session validation, CLI arguments and environment for Claude and Codex forks."""
import glob
import os

from ..shared import herdr
from ..shared.errors import MyHerdrError


def forkable_agent(pane_id, env=None):
    """Read and validate the source agent before opening a tab or popup.

    Logs the pane, agent kind, and session ID. Claude's saved conversation is
    checked when its store is available; Codex validates its own storage later.

    Args:
        pane_id (str): Source herdr pane ID whose current session will be forked.
        env (Mapping[str, str] or None): Environment used to locate Claude's
            store. None uses os.environ. Codex does not use this parameter.

    Returns:
        dict: herdr's agent record with a supported ``agent`` kind and a
            nonempty string ``agent_session.value`` of kind ``id``.

    Raises:
        MyHerdrError: No supported agent or usable session was found, session
            metadata conflicts, or Claude's store lacks the conversation.
    """
    result = herdr.try_json("agent", "get", pane_id)
    agent = (result or {}).get("agent")
    if not isinstance(agent, dict) or not agent.get("agent"):
        raise MyHerdrError("no agent is running in %s" % pane_id)
    kind = agent["agent"]
    if kind not in ("claude", "codex"):
        raise MyHerdrError(
            "fork-tab only works on Claude Code or Codex panes; %s runs %s" % (pane_id, kind))

    session = agent.get("agent_session")
    if not isinstance(session, dict):
        session = {}
    if session.get("agent") not in (None, kind):
        raise MyHerdrError(
            "herdr reports a %s session for the %s pane %s; "
            "start or resume the %s session in this pane before forking"
            % (session["agent"], kind, pane_id, kind))
    session_id = session.get("value")
    if (session.get("kind") != "id" or not isinstance(session_id, str)
            or not session_id.strip()):
        if kind == "claude":
            raise MyHerdrError(
                "herdr does not know this Claude session's id, so there is nothing to fork. "
                "Start the session in this pane with `claude --resume <id>`, not through "
                "Claude's background-sessions view, and make sure `herdr integration install "
                "claude` has been run.")
        raise MyHerdrError(
            "herdr does not know this Codex session's id, so there is nothing to fork. "
            "Start or resume the session in this pane with `codex` or `codex resume <id>`, "
            "and make sure `herdr integration install codex` has been run.")

    if kind == "claude":
        saved = conversation_saved(session_id, env)
        print("fork: %s runs claude session %s (saved conversation: %s, in %s)" % (
            pane_id, session_id, {True: "yes", False: "no", None: "cannot tell"}[saved],
            os.path.join(claude_config_dir(env), "projects")))
        if saved is False:
            # Avoid waiting through startup for a conversation Claude cannot load.
            raise MyHerdrError(
                "Claude has no saved conversation for this session yet, so there is nothing to "
                "fork. Send it a message first. If it already has some, restart Claude in this "
                "pane: herdr may still hold the id it had before a resume.")
    else:
        # Codex loads and validates its own saved conversation at startup.
        print("fork: %s runs codex session %s" % (pane_id, session_id))
    return agent


def fork_args(kind, session_id, name=None):
    """Build the agent-specific arguments passed after herdr's ``--``.

    Args:
        kind (str): Supported agent kind, "claude" or "codex".
        session_id (str): Validated source session ID understood by the agent.
        name (str or None): Optional saved-session name for Claude. None or an
            empty string omits it. Codex ignores it because naming is tab-only.

    Returns:
        list[str]: Agent argv preserving each value as a separate argument.

    Raises:
        MyHerdrError: The agent kind is unsupported.
    """
    if kind == "codex":
        return ["fork", session_id]
    if kind == "claude":
        args = ["--resume", session_id, "--fork-session"]
        if name:
            args += ["-n", name]
        return args
    raise MyHerdrError("cannot fork unsupported agent %s" % kind)


def forwarded_env(kind, env=None):
    """Forward the agent's store override from the action environment only.

    herdr supplies its server environment; shell-only overrides in the source
    pane are not discovered by the plugin.

    Args:
        kind (str): Supported agent kind, "claude" or "codex".
        env (Mapping[str, str] or None): Environment to read; None uses
            os.environ. An empty mapping forwards nothing.

    Returns:
        dict[str, str]: CLAUDE_CONFIG_DIR for Claude or CODEX_HOME for Codex,
            when nonempty in env; otherwise an empty dict.

    Raises:
        MyHerdrError: The agent kind is unsupported.
    """
    env = os.environ if env is None else env
    if kind == "claude":
        key = "CLAUDE_CONFIG_DIR"
    elif kind == "codex":
        key = "CODEX_HOME"
    else:
        raise MyHerdrError("cannot fork unsupported agent %s" % kind)
    return {key: env[key]} if env.get(key) else {}


def conversation_saved(session_id, env=None):
    """Whether Claude has the conversation `--resume <session_id>` would load.

    Args:
        session_id (str): Claude session ID to look for under
            ``<config>/projects/*/<id>.jsonl``. Glob characters are literal.
        env (Mapping[str, str] or None): Environment used to resolve Claude's
            configuration directory. None uses os.environ.

    Returns:
        bool or None: True if a matching transcript exists, False if the
            projects directory exists but has no match, or None if that
            directory is unavailable. Callers must not refuse on None.
    """
    projects = os.path.join(claude_config_dir(env), "projects")
    if not os.path.isdir(projects):
        return None
    pattern = os.path.join(glob.escape(projects), "*", glob.escape(session_id) + ".jsonl")
    return bool(glob.glob(pattern))


def claude_config_dir(env=None):
    """Resolve the configuration directory used for Claude's transcript check.

    Args:
        env (Mapping[str, str] or None): Environment containing optional
            CLAUDE_CONFIG_DIR and HOME values. None uses os.environ.

    Returns:
        str: Nonempty CLAUDE_CONFIG_DIR with a leading tilde expanded, otherwise
            ``<HOME>/.claude``. Missing HOME falls back to os.path.expanduser.
            Tilde expansion uses the process environment, not the supplied env.
    """
    env = os.environ if env is None else env
    configured = env.get("CLAUDE_CONFIG_DIR")
    if configured:
        return os.path.expanduser(configured)
    home = env.get("HOME") or os.path.expanduser("~")
    return os.path.join(home, ".claude")
