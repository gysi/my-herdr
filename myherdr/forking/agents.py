"""Agent adapter registry, shared session validation, and fork delegation."""

from . import claude, codex, opencode
from ..shared import herdr
from ..shared.errors import MyHerdrError


#: Agent modules implement the same five functions without a class hierarchy.
ADAPTERS = {"claude": claude, "codex": codex, "opencode": opencode}


def get_adapter(kind):
    """Select the registered module that owns an agent's fork behavior.

    Args:
        kind (str): Canonical agent kind reported by herdr.

    Returns:
        module: Adapter implementing missing_session_message, validate_source,
        prepare_fork, fork_args, and forwarded_env.

    Raises:
        MyHerdrError: The agent kind has no registered fork adapter.
    """
    adapter = ADAPTERS.get(kind) if isinstance(kind, str) else None
    if adapter is None:
        raise MyHerdrError("cannot fork unsupported agent %s" % kind)
    return adapter


def forkable_agent(pane_id, env=None):
    """Read and validate the source agent before opening a tab or popup.

    Logs the pane, agent kind, and session ID. Claude's saved conversation is
    checked when its store is available; Codex validates its own storage later.
    OpenCode verifies its CLI/server compatibility and source session through its API.

    Args:
        pane_id (str): Source herdr pane ID whose current session will be forked.
        env (Mapping[str, str] or None): Environment used to locate Claude's
            store. None uses os.environ. Codex/OpenCode do not use this parameter.

    Returns:
        dict: herdr's agent record with a supported ``agent`` kind and a
            nonempty string ``agent_session.value`` of kind ``id``. OpenCode
            adds ``opencode_directory`` from its authoritative session location.

    Raises:
        MyHerdrError: No supported agent or usable session was found, session
            metadata conflicts, Claude's store lacks the conversation, or
            OpenCode compatibility validation fails.
    """
    result = herdr.try_json("agent", "get", pane_id)
    agent = (result or {}).get("agent")
    if not isinstance(agent, dict) or not agent.get("agent"):
        raise MyHerdrError("no agent is running in %s" % pane_id)
    kind = agent["agent"]
    adapter = ADAPTERS.get(kind) if isinstance(kind, str) else None
    if adapter is None:
        raise MyHerdrError(
            "fork-tab only works on Claude Code, Codex or OpenCode panes; %s runs %s"
            % (pane_id, kind))

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
        raise MyHerdrError(adapter.missing_session_message())

    return adapter.validate_source(pane_id, agent, env)


def prepare_fork(agent, name=None):
    """Delegate preparation after source validation and before tab creation.

    Args:
        agent (dict): Source record returned by forkable_agent, including adapter
            validation metadata such as OpenCode's authoritative directory.
        name (str or None): Optional fork name; None or empty keeps default naming.

    Returns:
        dict: ``session_id`` (str) to launch and ``cwd`` (str or None) for the tab.
        An optional ``recovery`` (str) is appended to later startup errors.
        OpenCode saves its fork here; Claude/Codex defer creation to CLI startup.

    Raises:
        MyHerdrError: The kind is unsupported or agent-specific preparation fails.
            Saved OpenCode forks are retained and mutations are never retried.
    """
    return get_adapter(agent["agent"]).prepare_fork(agent, name)


def fork_args(kind, session_id, name=None):
    """Build the agent-specific arguments passed after herdr's ``--``.

    Args:
        kind (str): Supported agent kind: "claude", "codex", or "opencode".
        session_id (str): Source ID for Claude/Codex; already-created fork ID
            for OpenCode, whose fork is created through its API beforehand.
        name (str or None): Optional saved-session name for Claude. None or an
            empty string omits it. Codex ignores it; OpenCode is named via its API.

    Returns:
        list[str]: Agent argv preserving each value as a separate argument.

    Raises:
        MyHerdrError: The agent kind is unsupported.
    """
    return get_adapter(kind).fork_args(session_id, name)


def forwarded_env(kind, env=None):
    """Forward the agent's store override from the action environment only.

    herdr supplies its server environment; shell-only overrides in the source
    pane are not discovered by the plugin.

    Args:
        kind (str): Supported agent kind: "claude", "codex", or "opencode".
        env (Mapping[str, str] or None): Environment to read; None uses
            os.environ. An empty mapping forwards nothing.

    Returns:
        dict[str, str]: CLAUDE_CONFIG_DIR for Claude or CODEX_HOME for Codex,
            when nonempty in env; otherwise an empty dict. OpenCode uses its
            shared service and the inherited herdr server environment, with
            no extra variables placed in logged --env arguments.

    Raises:
        MyHerdrError: The agent kind is unsupported.
    """
    return get_adapter(kind).forwarded_env(env)
