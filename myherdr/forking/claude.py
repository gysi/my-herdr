"""Claude Code fork adapter and saved-conversation lookup."""
import glob
import os

from ..shared.errors import MyHerdrError


def missing_session_message():
    """Describe how to register a forkable Claude session with herdr.

    Returns:
        str: Recovery guidance for a missing or unusable native session ID.
    """
    return (
        "herdr does not know this Claude session's id, so there is nothing to fork. "
        "Start the session in this pane with `claude --resume <id>`, not through "
        "Claude's background-sessions view, and make sure `herdr integration install "
        "claude` has been run.")


def validate_source(pane_id, agent, env=None):
    """Check and log the source conversation without creating a fork.

    Args:
        pane_id (str): Source herdr pane ID included in the plugin log.
        agent (dict): Agent record whose native session ID passed shared validation.
        env (Mapping[str, str] or None): Environment used to locate Claude's store.
            None uses os.environ; an empty mapping uses the default home fallback.

    Returns:
        dict: The unchanged source agent record when its conversation exists or
        the store cannot be inspected.

    Raises:
        MyHerdrError: The available store contains no saved source conversation.
    """
    session_id = agent["agent_session"]["value"]
    saved = conversation_saved(session_id, env)
    print("fork: %s runs claude session %s (saved conversation: %s, in %s)" % (
        pane_id, session_id, {True: "yes", False: "no", None: "cannot tell"}[saved],
        os.path.join(claude_config_dir(env), "projects")))
    if saved is False:
        raise MyHerdrError(
            "Claude has no saved conversation for this session yet, so there is nothing to "
            "fork. Send it a message first. If it already has some, restart Claude in this "
            "pane: herdr may still hold the id it had before a resume.")
    return agent


def prepare_fork(agent, name=None):
    """Select the source ID and directory for a fork created at CLI startup.

    Args:
        agent (dict): Validated source agent record with its session and pane directories.
        name (str or None): Optional fork name, applied later in launch arguments.
            None or an empty string keeps default naming; unused at this stage.

    Returns:
        dict: ``session_id`` is the source native ID; ``cwd`` is foreground_cwd,
        falling back to cwd or None. No session is created or modified here.
    """
    return {"session_id": agent["agent_session"]["value"],
            "cwd": agent.get("foreground_cwd") or agent.get("cwd")}


def fork_args(session_id, name=None):
    """Build Claude arguments that resume and fork the source conversation.

    Args:
        session_id (str): Validated source native session ID to copy at startup.
        name (str or None): Optional saved-session name; None or empty omits -n.

    Returns:
        list[str]: CLI arguments preserving the session ID and name as single values.
    """
    args = ["--resume", session_id, "--fork-session"]
    if name:
        args += ["-n", name]
    return args


def forwarded_env(env=None):
    """Select Claude's configuration override from the action environment.

    Args:
        env (Mapping[str, str] or None): Environment inherited from the herdr server.
            None uses os.environ; an empty mapping forwards nothing. Source-shell
            overrides are not discovered.

    Returns:
        dict[str, str]: Nonempty CLAUDE_CONFIG_DIR only, or an empty dictionary.
    """
    env = os.environ if env is None else env
    return {"CLAUDE_CONFIG_DIR": env["CLAUDE_CONFIG_DIR"]} if env.get("CLAUDE_CONFIG_DIR") else {}


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
