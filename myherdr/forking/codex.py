"""Codex fork adapter; Codex validates its own saved conversation at startup."""
import os


def missing_session_message():
    """Describe how to register a forkable Codex session with herdr.

    Returns:
        str: Recovery guidance for a missing or unusable native session ID.
    """
    return (
        "herdr does not know this Codex session's id, so there is nothing to fork. "
        "Start or resume the session in this pane with `codex` or `codex resume <id>`, "
        "and make sure `herdr integration install codex` has been run.")


def validate_source(pane_id, agent, env=None):
    """Log the identified source without inspecting Codex's conversation store.

    Args:
        pane_id (str): Source herdr pane ID included in the plugin log.
        agent (dict): Agent record whose native session ID passed shared validation.
        env (Mapping[str, str] or None): Action environment, accepted for the common
            adapter interface but unused. Codex validates its storage at startup.

    Returns:
        dict: The unchanged source agent record. No fork is created here.
    """
    print("fork: %s runs codex session %s" % (pane_id, agent["agent_session"]["value"]))
    return agent


def prepare_fork(agent, name=None):
    """Select the source ID and directory for a fork created at CLI startup.

    Args:
        agent (dict): Validated source agent record with its session and pane directories.
        name (str or None): Optional tab label; None or empty keeps default naming.
            Codex session naming is unsupported, so this adapter ignores the value.

    Returns:
        dict: ``session_id`` is the source native ID; ``cwd`` is foreground_cwd,
        falling back to cwd or None. No session is created or modified here.
    """
    return {"session_id": agent["agent_session"]["value"],
            "cwd": agent.get("foreground_cwd") or agent.get("cwd")}


def fork_args(session_id, name=None):
    """Build Codex arguments that fork and validate its saved conversation.

    Args:
        session_id (str): Validated source native session ID to copy at startup.
        name (str or None): Optional tab label, unused because Codex has no
            session-name flag. None or empty keeps default tab naming.

    Returns:
        list[str]: CLI arguments preserving the session ID as one value.
    """
    return ["fork", session_id]


def forwarded_env(env=None):
    """Select Codex's store override from the action environment.

    Args:
        env (Mapping[str, str] or None): Environment inherited from the herdr server.
            None uses os.environ; an empty mapping forwards nothing. Source-shell
            overrides are not discovered.

    Returns:
        dict[str, str]: Nonempty CODEX_HOME only, or an empty dictionary.
    """
    env = os.environ if env is None else env
    return {"CODEX_HOME": env["CODEX_HOME"]} if env.get("CODEX_HOME") else {}
