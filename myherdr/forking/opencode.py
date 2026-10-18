"""OpenCode fork adapter and session access through its service-aware CLI.

Only the normal shared-service connection is supported. No database access,
transcript copying, legacy fallback, or direct HTTP authentication is needed.
"""
import json
import os
import re
import subprocess
from urllib.parse import quote

from ..shared.errors import MyHerdrError

_VERSION = re.compile(
    r"^(?:opencode\s+)?v?(\d+)\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def missing_session_message():
    """Describe how to register a forkable OpenCode session with herdr.

    Returns:
        str: Recovery guidance for a missing or unusable native session ID.
    """
    return (
        "herdr does not know this OpenCode session's id, so there is nothing to fork. "
        "Run `herdr integration install opencode`, restart the OpenCode TUI in "
        "this pane, and select the source session. Mini/headless clients are unsupported.")


def validate_source(pane_id, agent, env=None):
    """Verify and log the source through the API without creating a fork.

    Args:
        pane_id (str): Source herdr pane ID included in the plugin log.
        agent (dict): Agent record whose native session ID passed shared validation.
        env (Mapping[str, str] or None): Action environment, accepted for the common
            adapter interface but unused. CLI subprocesses inherit the process
            environment for shared-service discovery and authentication.

    Returns:
        dict: Copy of the source agent record with ``opencode_directory`` set to
        its API-reported absolute session directory.

    Raises:
        MyHerdrError: CLI/server compatibility or source-session validation fails.
    """
    session_id = agent["agent_session"]["value"]
    validated = dict(agent, opencode_directory=validate(session_id))
    print("fork: %s runs opencode session %s" % (pane_id, session_id))
    return validated


def prepare_fork(agent, name=None):
    """Save the fork before tab creation, using the validated source directory.

    Args:
        agent (dict): Validated source agent record with its native session ID
            and authoritative ``opencode_directory``.
        name (str or None): Optional saved-fork title; None or empty preserves
            OpenCode's automatic title.

    Returns:
        dict: ``session_id`` is the newly saved fork's ID; ``cwd`` is the source
        session's API-reported directory, not either pane directory; ``recovery``
        tells the user how to resume the saved fork if tab startup fails.

    Raises:
        MyHerdrError: Fork creation or naming fails. Saved forks are logged and
            retained on subsequent failure; mutations are never retried.
    """
    cwd = agent["opencode_directory"]
    fork_id = fork_session(agent["agent_session"]["value"], name)
    return {"session_id": fork_id, "cwd": cwd, "recovery": recovery_note(fork_id)}


def recovery_note(fork_id):
    """Tell the user how to resume a saved fork that has no working tab.

    Args:
        fork_id (str): ID of the saved OpenCode fork.

    Returns:
        str: One sentence naming the fork and the command that resumes it.
    """
    return "OpenCode fork %s was saved; resume it with `opencode --session %s`" % (
        fork_id, fork_id)


def fork_args(session_id, name=None):
    """Build OpenCode arguments that launch an already-created fork.

    Args:
        session_id (str): Newly saved fork ID, never the source session ID.
        name (str or None): Optional fork title, already applied through the API.
            None or empty keeps default naming; unused at CLI startup.

    Returns:
        list[str]: CLI arguments preserving the fork ID as one value.
    """
    return ["--session", session_id]


def forwarded_env(env=None):
    """Keep OpenCode discovery credentials out of logged tab environment arguments.

    Args:
        env (Mapping[str, str] or None): Action environment, accepted for the common
            adapter interface but unused, including when None. OpenCode relies
            on the inherited herdr server environment and shared service.

    Returns:
        dict: Empty dictionary; no extra variables are forwarded in tab argv.
    """
    return {}


def run(*args, timeout=30.0):
    """Run OpenCode without a shell, capturing output and bounding execution.

    Args:
        *args (str): OpenCode arguments, excluding the executable resolved from PATH.
        timeout (float): Maximum subprocess duration in seconds, default 30.

    Returns:
        subprocess.CompletedProcess: Successful command with text stdout/stderr.

    Raises:
        MyHerdrError: The executable is missing, fails, or exceeds the timeout.
            Failure messages omit command output, which can contain private data.
    """
    try:
        proc = subprocess.run(["opencode"] + list(args), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True,
                              timeout=timeout)
    except OSError as exc:
        raise MyHerdrError("cannot run OpenCode from the herdr server's PATH: %s" % exc)
    except subprocess.TimeoutExpired:
        raise MyHerdrError("OpenCode command timed out after %gs; it was not retried" % timeout)
    except UnicodeError:
        raise MyHerdrError("OpenCode returned invalid text output")
    if proc.returncode:
        raise MyHerdrError(
            "OpenCode command failed (exit %s); check the shared service, session ID, "
            "and authentication in the herdr server environment" % proc.returncode)
    return proc


def api(method, path, body=None):
    """Call the V2 API using OpenCode's own discovery and authentication.

    Args:
        method (str): HTTP method understood by opencode api.
        path (str): Absolute API path, with any session ID URL-encoded.
        body (dict or None): JSON request payload; None omits --data.

    Returns:
        dict or None: Raw JSON object, or None for a successful empty response.

    Raises:
        MyHerdrError: Execution fails or nonempty output is not a JSON object.
            Mutations are never retried, including after ambiguous timeouts.
    """
    args = ["api", method, path]
    if body is not None:
        args += ["--data", json.dumps(body)]
    proc = run(*args)
    if not proc.stdout.strip():
        return None
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        raise MyHerdrError("OpenCode returned invalid JSON")
    if not isinstance(result, dict):
        raise MyHerdrError("OpenCode returned no response object")
    return result


def require_supported_version(version):
    """Reject legacy or unidentifiable OpenCode versions before mutations.

    Args:
        version (str or None): CLI version output or server's version field.
            Stable and prerelease versions with major >= 2 pass this API-generation
            guard; it does not check release freshness or define the support policy.

    Raises:
        MyHerdrError: The version is missing, unrecognized, or incompatible with
            the session API used by this implementation.
    """
    match = _VERSION.fullmatch(version.strip()) if isinstance(version, str) else None
    if not match or int(match.group(1)) < 2:
        raise MyHerdrError("OpenCode CLI/server compatibility could not be verified; "
                           "update the OpenCode CLI and shared service to the latest release")


def session_path(session_id):
    """Build a session endpoint without interpreting the ID as a URL path.

    Args:
        session_id (str): Native OpenCode session ID to address literally.

    Returns:
        str: Absolute V2 session API path with the ID percent-encoded.
    """
    return "/api/session/" + quote(session_id, safe="")


def validate(session_id):
    """Verify CLI/server compatibility and find the source session's location.

    Args:
        session_id (str): Native session ID reported for the source herdr pane.

    Returns:
        str: Absolute directory owned by the source OpenCode session, used for
            the new tab rather than the plugin root or a stale foreground cwd.

    Raises:
        MyHerdrError: The CLI/server is incompatible, the source cannot be read from
            the shared service, or its ID/location response is invalid.
    """
    require_supported_version(run("--version", timeout=10.0).stdout)
    info = api("get", "/api/info")
    require_supported_version((info or {}).get("version"))
    response = api("get", session_path(session_id))
    session = (response or {}).get("data")
    if not isinstance(session, dict) or session.get("id") != session_id:
        raise MyHerdrError("OpenCode did not return the requested source session")
    location = session.get("location")
    directory = location.get("directory") if isinstance(location, dict) else None
    if not isinstance(directory, str) or not os.path.isabs(directory):
        raise MyHerdrError("OpenCode reported no absolute directory for the source session")
    return directory


def fork_session(session_id, name=None):
    """Save an independent fork and optionally name only that new session.

    Args:
        session_id (str): Validated source session ID; never resumed as the fork.
        name (str or None): Optional title for the fork. None or empty preserves
            OpenCode's automatic fork title.

    Returns:
        str: Newly saved fork's ID, distinct from the source ID.

    Raises:
        MyHerdrError: Fork creation/naming fails or the response lacks a distinct
            ID. A successfully created fork is logged and kept even on failure;
            no session deletion is attempted, and mutations are never retried.
    """
    response = api("post", session_path(session_id) + "/fork", {})
    session = (response or {}).get("data")
    fork_id = session.get("id") if isinstance(session, dict) else None
    if not isinstance(fork_id, str) or not fork_id.strip() or fork_id == session_id:
        raise MyHerdrError("OpenCode did not return a distinct fork session ID; "
                           "creation was not retried")
    print("fork: saved OpenCode session %s from %s (kept if tab startup fails)" % (
        fork_id, session_id), flush=True)
    if name:
        try:
            api("patch", session_path(fork_id), {"title": name})
        except MyHerdrError as exc:
            raise MyHerdrError("could not name the OpenCode fork: %s. %s" % (
                str(exc).rstrip("."), recovery_note(fork_id)))
    return fork_id
