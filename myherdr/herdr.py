"""The only place that talks to the herdr CLI.

Everything goes through `run()`, which takes an argv list, so there is no shell
and nothing needs quoting, and so tests can replace one function to fake the
whole CLI.

Response shapes (verified against the herdr CLI):
    success  stdout {"id":"cli:pane:get","result":{...,"type":"pane_info"}}   exit 0
    failure  stderr {"error":{"code":"pane_not_found","message":"..."}}       exit 1
    usage    stderr plain text usage block                                    exit 2
"""
import json
import os
import subprocess
import time

from .errors import MyHerdrError

#: Plenty for a local socket round trip; `agent start` passes its own.
DEFAULT_TIMEOUT = 30.0

#: herdr caps notification text; longer values are rejected, so truncate.
TITLE_MAX = 80
BODY_MAX = 240

_SHELLS = frozenset(("zsh", "bash", "fish", "sh", "dash", "ksh", "nu"))


def bin_path():
    """Return HERDR_BIN_PATH as a str, falling back to the PATH command "herdr"."""
    return os.environ.get("HERDR_BIN_PATH") or "herdr"


def run(*args, **kwargs):
    """Run one herdr command and return the finished process.

    This is the seam the tests patch, so it stays dumb: no parsing, no raising
    for a non-zero exit. Only a herdr that cannot be started at all, or one
    that hangs, becomes a MyHerdrError here.

    Args:
        *args (object): herdr command and arguments, excluding its executable.
            Each value is converted to str and passed without shell expansion.
        **kwargs (object): Optional ``timeout`` in seconds (default 30) and
            ``stdin`` text (default None). No other keywords are accepted.

    Returns:
        subprocess.CompletedProcess: Exit status and captured stdout/stderr
            as text, including when the command exits unsuccessfully.

    Raises:
        MyHerdrError: The executable cannot be started or the timeout expires.
        TypeError: An unknown keyword argument is supplied.
    """
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    stdin = kwargs.pop("stdin", None)
    if kwargs:
        raise TypeError("unexpected keyword arguments: %s" % ", ".join(sorted(kwargs)))

    argv = [bin_path()] + [str(a) for a in args]
    try:
        return subprocess.run(
            argv,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,  # 3.9-compatible spelling of text=True
            timeout=timeout,
        )
    except OSError as exc:
        # Missing, not executable, wrong architecture: all the same story for
        # the user, and all worth a clearer message than a raw traceback.
        raise MyHerdrError(
            "cannot run the herdr CLI at %r: %s (set HERDR_BIN_PATH)" % (argv[0], exc))
    except subprocess.TimeoutExpired:
        raise MyHerdrError(
            "herdr %s timed out after %ss" % (" ".join(argv[1:]), timeout))


def run_json(*args, **kwargs):
    """Run a herdr command and return its `result` object.

    Args:
        *args (object): herdr command and arguments, excluding the executable.
        **kwargs (object): Optional ``timeout`` seconds and ``stdin`` text,
            forwarded to run(). Defaults are 30 seconds and no input.

    Returns:
        dict: The JSON response's ``result`` object.

    Raises:
        MyHerdrError: Execution failed, herdr returned an error, or its output
            lacks a valid result object. herdr error codes are preserved.
        TypeError: An unsupported keyword is passed to run().
    """
    proc = run(*args, **kwargs)
    if proc.returncode != 0:
        message, code = _error_of(proc, args)
        raise MyHerdrError(message, code=code)
    return _result_of(proc, args)


def try_json(*args, **kwargs):
    """Like run_json(), but returns None instead of raising.

    For reads where "no answer" is an acceptable outcome, so a degraded herdr
    does not turn a best-effort lookup into a failed action.

    Args:
        *args (object): herdr command and arguments, excluding the executable.
        **kwargs (object): Optional ``timeout`` seconds and ``stdin`` text,
            forwarded to run_json(). Defaults are 30 seconds and no input.

    Returns:
        dict or None: Parsed result, or None on MyHerdrError.

    Raises:
        TypeError: An unsupported keyword is passed to run().
    """
    try:
        return run_json(*args, **kwargs)
    except MyHerdrError:
        return None


def _result_of(proc, args):
    """Extract the result object from a completed herdr command.

    Args:
        proc (subprocess.CompletedProcess): Successful process with text stdout.
        args (Sequence[object]): Command arguments used in error messages.

    Returns:
        dict: The response's ``result`` object.

    Raises:
        MyHerdrError: stdout is invalid JSON or contains no result object.
    """
    try:
        envelope = json.loads(proc.stdout)
    except ValueError:
        raise MyHerdrError(
            "herdr %s returned unparsable output: %s"
            % (" ".join(str(a) for a in args), _clip(proc.stdout, 200)))
    result = envelope.get("result") if isinstance(envelope, dict) else None
    if not isinstance(result, dict):
        raise MyHerdrError(
            "herdr %s returned no result object" % " ".join(str(a) for a in args))
    return result


def _error_of(proc, args):
    """Turn a failed CLI run into (message, code).

    Usage errors (exit 2) are not JSON, so fall back to the raw stderr text.

    Args:
        proc (subprocess.CompletedProcess): Failed process with text output.
        args (Sequence[object]): Command arguments used in fallback diagnostics.

    Returns:
        tuple[str, str or None]: User-facing message and herdr error code;
            the code is None for an unstructured error.
    """
    try:
        envelope = json.loads(proc.stderr)
        error = envelope["error"]
        return error.get("message") or "herdr failed", error.get("code")
    except (ValueError, KeyError, TypeError):
        text = _clip((proc.stderr or proc.stdout or "").strip(), 300)
        return (
            "herdr %s failed (exit %s)%s"
            % (" ".join(str(a) for a in args), proc.returncode,
               ": " + text if text else ""),
            None,
        )


def _clip(text, limit):
    """Shorten to at most `limit` characters, ellipsis included.

    herdr rejects a title over 80 or a body over 240 characters, so the marker
    has to fit inside the budget rather than be added on top of it.

    Args:
        text (str or None): Text to trim; None is treated as an empty string.
        limit (int): Positive maximum character count, including the ellipsis.

    Returns:
        str: Stripped text, shortened with an ellipsis when necessary.
    """
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit - 1] + "…"


# -- convenience calls used by more than one action -----------------------


def notify(body, title="my-herdr", sound="none"):
    """Best-effort toast.

    A plugin action's stdout is invisible unless someone runs `herdr plugin log
    list`, so failures have to be toasted. A failing toast must never mask the
    error it is reporting, hence no raising.

    Args:
        body (str): Notification message, trimmed to herdr's 240-character limit.
        title (str): Notification heading, default "my-herdr", capped at 80 chars.
        sound (str): herdr sound name: "none" (default), "done", or "request".
    """
    try:
        run("notification", "show", _clip(title, TITLE_MAX),
            "--body", _clip(body, BODY_MAX), "--sound", sound, timeout=5.0)
    except MyHerdrError:
        pass


def focused_pane(ctx=None):
    """The pane an action was invoked from.

    Env first (herdr sets HERDR_PANE_ID to the pane that had focus when the key
    was pressed), then the context JSON (popups get no HERDR_PANE_ID), then the
    server as a last resort.

    Args:
        ctx (Context or None): Invocation context to prefer; None queries herdr
            directly instead of reading an invocation context.

    Returns:
        str: Focused pane ID, such as ``w1:p1``.

    Raises:
        MyHerdrError: Neither the supplied context nor herdr provides a pane ID.
    """
    if ctx is not None and ctx.pane_id:
        return ctx.pane_id
    result = try_json("pane", "current")
    pane = (result or {}).get("pane") or {}
    pane_id = pane.get("pane_id")
    if not pane_id:
        raise MyHerdrError("no focused pane")
    return pane_id


def wait_shell_ready(pane_id, timeout=10.0, interval=0.2, sleep=time.sleep):
    """Block until `pane_id` is back at its interactive shell prompt.

    `agent start` refuses a pane that has a foreground command, and a freshly
    created tab is still starting its shell. Adapted from t4t5/herdr-forkr
    (MIT), which polls `pane process-info` the same way.

    Args:
        pane_id (str): Destination pane whose foreground process is checked.
        timeout (float): Polling deadline in seconds, default 10. A CLI call
            already in progress may run beyond this deadline.
        interval (float): Seconds to wait between unsuccessful polls, default 0.2.
        sleep (Callable[[float], object]): Delay function, default time.sleep;
            tests can inject one that advances a fake clock.

    Returns:
        bool: True once the foreground process is the shell, False on timeout.
    """
    deadline = time.monotonic() + timeout
    while True:
        if _shell_is_idle(pane_id):
            return True
        if time.monotonic() >= deadline:
            return False
        sleep(interval)


def _shell_is_idle(pane_id):
    """Check whether one foreground process appears to be the pane's shell.

    Args:
        pane_id (str): herdr pane ID to query with pane process-info.

    Returns:
        bool: True for a sole shell process; False for busy or unreadable panes.
    """
    result = try_json("pane", "process-info", "--pane", pane_id, timeout=5.0)
    info = (result or {}).get("process_info") or {}
    foreground = info.get("foreground_processes") or []
    if len(foreground) != 1:
        return False
    only = foreground[0]
    return only.get("pid") == info.get("shell_pid") or only.get("name") in _SHELLS
