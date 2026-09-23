"""Hand a tab name from the `fork-prompt` popup to the `fork-tab` action.

The popup does not fork. It asks for the name, leaves a request here, and has
herdr run `fork-tab` like any other action, so the fork gets the plugin log,
the action environment and herdr's bookkeeping. The file exists only because a
herdr action takes no parameters: `plugin action invoke` has no way to pass
one, and the socket API's invocation context has fixed fields.

A request is one file in the plugin state directory, used at most once:

- the popup writes it immediately before invoking the action, and deletes it
  again if the invoke fails, so a request is never left behind on purpose;
- the action claims it by renaming it away before reading it, so two runs
  cannot both take the same request;
- a request older than REQUEST_TTL is ignored, so one left behind anyway (a
  popup killed between writing and invoking) cannot name a later, unrelated
  `fork-tab`. The invoke follows the write within milliseconds; the margin is
  for a loaded machine.

The request carries the source pane too, rather than trusting the invoked
action to see the pane under the popup as focused.
"""
import json
import os
import time

from .errors import MyHerdrError

FILE_NAME = "fork-request.json"

#: Seconds a request stays valid after it was written.
REQUEST_TTL = 10.0


def save(state_dir, pane_id, name=None, now=None):
    """Leave a request for the next `fork-tab`. Raises MyHerdrError if it cannot.

    Written to a temporary name and renamed into place, so the action never
    reads a half-written file.

    Args:
        state_dir (str): Existing plugin state directory for the request file.
        pane_id (str): Source pane to re-read and fork when the action runs.
        name (str or None): Requested tab label; None requests default naming.
        now (float or None): Write timestamp in Unix seconds. None uses
            time.time(); tests can provide a deterministic clock value.

    Raises:
        MyHerdrError: The state directory is missing or the file cannot be saved.
    """
    if not state_dir:
        raise MyHerdrError("no plugin state directory to hand the tab name over in")
    path = os.path.join(state_dir, FILE_NAME)
    partial = "%s.%d.tmp" % (path, os.getpid())
    request = {"pane_id": pane_id, "name": name,
               "written_at": time.time() if now is None else now}
    try:
        with open(partial, "w") as handle:
            json.dump(request, handle)
        os.replace(partial, path)
    except (IOError, OSError) as exc:
        _remove(partial)
        raise MyHerdrError("could not hand the tab name over: %s" % exc)


def take(state_dir, now=None):
    """Claim the pending request: `{"pane_id", "name"}`, or None if there is none.

    None as well for a request that is stale, unreadable or malformed: the
    caller then forks the focused pane unnamed, which is what `fork-tab` does
    when nobody asked for a name.

    Args:
        state_dir (str or None): Directory holding the request; None or an empty
            string means there is no request to claim.
        now (float or None): Current Unix time for expiry checks. None uses
            time.time(); requests older than REQUEST_TTL are discarded.

    Returns:
        dict or None: ``pane_id`` (str) and ``name`` (str or None) from a valid
            request, or None if unavailable or invalid. The claimed file is
            removed even when its contents cannot be used.
    """
    if not state_dir:
        return None
    path = os.path.join(state_dir, FILE_NAME)
    claimed = "%s.%d.claimed" % (path, os.getpid())
    try:
        os.rename(path, claimed)
    except OSError:
        return None  # no request, or another run claimed it first

    try:
        with open(claimed) as handle:
            request = json.load(handle)
    except (IOError, OSError, ValueError):
        return None
    finally:
        _remove(claimed)

    if not isinstance(request, dict):
        return None
    written_at = request.get("written_at")
    now = time.time() if now is None else now
    # A clock stepping backwards makes the age negative; a second of slack
    # covers that without accepting a request from the future.
    if not isinstance(written_at, (int, float)) or not -1.0 <= now - written_at <= REQUEST_TTL:
        return None
    pane_id = request.get("pane_id")
    if not isinstance(pane_id, str) or not pane_id:
        return None
    name = request.get("name")
    return {"pane_id": pane_id, "name": name if isinstance(name, str) and name else None}


def drop(state_dir):
    """Withdraw a pending request, ignoring filesystem errors.

    Args:
        state_dir (str or None): Plugin state directory. None or an empty
            string leaves the filesystem untouched.
    """
    if state_dir:
        _remove(os.path.join(state_dir, FILE_NAME))


def _remove(path):
    """Remove a temporary or pending file, ignoring filesystem errors.

    Args:
        path (str): File path to unlink, which may already be absent.
    """
    try:
        os.remove(path)
    except OSError:
        pass
