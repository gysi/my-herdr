"""Shared attention navigation in the local herdr sidebar's current order.

Forward urgency uses oldest blocked/done agents, independently of sidebar sort.
Normal navigation starts from the invoking pane, or the shared saved position
when invoked outside the agent list. Both directions skip the invoking pane.
"""
import json
import os
import re

from . import herdr
from .context import Context
from .sidebar_order import sort_mode

#: Statuses that cut into the ring, in the order they are offered. `blocked` is
#: someone actively waiting on an answer; `done` is work finished but unread.
WAITING = ("blocked", "done")

CURSOR_FILE = "attention-next.json"


def navigate(direction=1):
    """Focus an agent in the requested direction and persist successful navigation.

    Args:
        direction (int): 1 for next with urgency, -1 for previous without urgency.

    Returns:
        int: 0 after focusing an agent or reporting that there is no other agent.

    Raises:
        MyHerdrError: herdr cannot list agents or focus the chosen pane. A failed
            focus does not advance the persisted cursor.
    """
    ctx = Context()
    here = ctx.pane_id
    action = "attention-next" if direction == 1 else "attention-prev"
    mode = sort_mode(ctx.env)
    agents = ring(herdr.run_json("agent", "list"), mode)
    if not any(item["pane_id"] != here for item in agents):
        # No agents, or only this pane. The action has no TTY, so silence would
        # look like a broken keybinding — though the toast is itself invisible
        # when ui.toast.delivery is off.
        herdr.notify("No other agent to jump to.")
        print("%s: no other agent" % action)
        return 0

    path = cursor_path(ctx)
    target = choose(agents, here, read_cursor(path), direction)
    herdr.run_json("agent", "focus", target["pane_id"])
    # Only now: an anchor pointing at a pane we failed to reach would make the
    # next press start from the wrong place.
    write_cursor(path, target["pane_id"], agents)

    print("%s: focused %s (%s, %s, seq %s) of %d agents, %d waiting; sort=%s" % (
        action, target["pane_id"], target.get("agent") or "?", target.get("agent_status"),
        target.get("state_change_seq"), len(agents), len(waiting_ids(agents)), mode))
    return 0


def ring(result, mode="spaces"):
    """Order valid agents as grouped or priority sidebar rows.

    Args:
        result (dict or None): Parsed result of herdr agent list, with an
            optional ``agents`` list. None represents an unavailable response.
        mode (str): "spaces" preserves API layout order; "priority" sorts by
            status and newest state change, preserving layout order for ties.

    Returns:
        list[dict]: Usable agent records in sidebar order.
    """
    agents = result.get("agents") if isinstance(result, dict) else None
    if not isinstance(agents, list):
        return []
    found = [item for item in agents if isinstance(item, dict)
             and isinstance(item.get("pane_id"), str) and item["pane_id"]]
    if mode == "priority":
        ranks = {"blocked": 4, "done": 3, "working": 2, "idle": 1}
        found.sort(key=lambda item: (-ranks.get(item.get("agent_status"), 0), -_seq(item)))
    return found


def choose(agents, here, cursor, direction=1):
    """The agent this press should go to.

    `agents` is the whole ring, including `here`; only the returned target is
    guaranteed to be some other pane.

    Args:
        agents (list[dict]): Complete sidebar order from ring().
        here (str or None): Invoking pane ID; anchors navigation and is excluded
            as a target. None uses the saved cursor when available.
        cursor (dict): Previous ``pane_id`` anchor and ``waiting`` ID list;
            an empty dict starts a fresh walk.
        direction (int): 1 walks down with urgency; -1 walks up without urgency.

    Returns:
        dict or None: Forward urgency target, otherwise the adjacent eligible agent;
            None when no pane other than here exists.
    """
    if direction == 1 and set(waiting_ids(agents)) - set(cursor.get("waiting") or []):
        # Somebody started waiting since the last press. That is news, and news
        # interrupts the walk.
        urgent = most_urgent(agents, here)
        if urgent is not None:
            return urgent
    pane_ids = [item["pane_id"] for item in agents]
    anchor = here if here in pane_ids else cursor.get("pane_id")
    return next_after(agents, anchor, here, direction)


def most_urgent(agents, here):
    """Choose a waiting agent by status, age, then position.

    Args:
        agents (list[dict]): Agent records containing pane IDs and optional status.
        here (str or None): Invoking pane ID to exclude, or None if unknown.

    Returns:
        dict or None: Oldest blocked agent, otherwise oldest done agent;
            None if no other agent is waiting.
    """
    waiting = [
        item for item in agents
        if item.get("agent_status") in WAITING and item["pane_id"] != here
    ]
    if not waiting:
        return None
    return min(waiting, key=lambda item: (
        WAITING.index(item["agent_status"]), _seq(item), _place(item)))


def next_after(agents, anchor, here, direction=1):
    """Find an eligible neighbor of the anchor in the requested direction, wrapping.

    An anchor that has vanished — or none at all, on the first press — starts
    the walk at the top for next, or the bottom for previous.

    Args:
        agents (list[dict]): Complete ring in current sidebar order.
        anchor (str or None): Invoking or saved pane ID, or None when unanchored.
        here (str or None): Invoking pane ID, which must never be returned.
        direction (int): 1 walks down; -1 walks up.

    Returns:
        dict or None: First eligible record after the anchor, wrapping once;
            None if every record is excluded or the ring is empty.
    """
    pane_ids = [item["pane_id"] for item in agents]
    start = (pane_ids.index(anchor) + direction if anchor in pane_ids
             else (0 if direction == 1 else len(agents) - 1))
    for offset in range(len(agents)):
        item = agents[(start + direction * offset) % len(agents)]
        if item["pane_id"] != here:
            return item
    return None


def waiting_ids(agents):
    """The pane ids that want attention, sorted.

    Computed over the whole ring, including the current pane, so that walking
    onto a blocked agent does not make it look like it stopped waiting and then
    started again on the way back.

    Args:
        agents (list[dict]): Complete agent ring, including the invoking pane.

    Returns:
        list[str]: Sorted pane IDs whose status is blocked or done.
    """
    return sorted(
        item["pane_id"] for item in agents if item.get("agent_status") in WAITING)


def _seq(item):
    """Read an agent's state-change sequence for age ordering.

    Args:
        item (dict): Agent record with an optional ``state_change_seq`` field.

    Returns:
        int: Sequence value, or 0 for missing/unusable values so they sort oldest.
    """
    try:
        return int(item.get("state_change_seq"))
    except (TypeError, ValueError):
        return 0


def _place(item):
    """Build a position key for an agent.

    Args:
        item (dict): Agent record with workspace, tab, and pane IDs.

    Returns:
        tuple: Natural-sort keys for workspace, tab, and pane, in that order.
    """
    return (_natural(item.get("workspace_id")), _natural(item.get("tab_id")),
            _natural(item.get("pane_id")))


def _natural(value):
    """Sort key where digit runs compare as numbers, so `p10` follows `p2`.

    Each part becomes a (number, text) pair so the parts stay comparable with
    each other whichever kind they are.

    Args:
        value (str or None): herdr ID to split into text and numeric runs;
            None is treated as an empty string.

    Returns:
        tuple[tuple[int, str]]: Comparable key with numeric runs ordered as ints.
    """
    return tuple(
        (int(part), "") if part.isdigit() else (-1, part)
        for part in re.split(r"(\d+)", value or "")
    )


def cursor_path(ctx):
    """Resolve the attention cursor's storage path.

    Args:
        ctx (Context): Invocation context providing the plugin state directory.

    Returns:
        str or None: Cursor file path, or None when no state directory is supplied.
    """
    return os.path.join(ctx.state_dir, CURSOR_FILE) if ctx.state_dir else None


def read_cursor(path):
    """Read the last jump, tolerating unavailable or malformed cursor files.

    Args:
        path (str or None): Cursor file path. None or an empty string skips reading.

    Returns:
        dict: Stored ``pane_id`` and ``waiting`` fields, or an empty dict when
            the file cannot be read as a JSON object.
    """
    if not path:
        return {}
    try:
        with open(path) as handle:
            cursor = json.load(handle)
    except (IOError, OSError, ValueError):
        return {}
    if not isinstance(cursor, dict):
        return {}
    waiting = cursor.get("waiting")
    return {
        "pane_id": cursor.get("pane_id") if isinstance(cursor.get("pane_id"), str) else None,
        "waiting": [pane for pane in waiting if isinstance(pane, str)]
        if isinstance(waiting, list) else [],
    }


def write_cursor(path, pane_id, agents):
    """Record the successful jump and waiting agents, ignoring filesystem errors.

    Args:
        path (str or None): Cursor file path; None or an empty string skips writing.
        pane_id (str): Pane that herdr successfully focused.
        agents (list[dict]): Complete agent ring used to record waiting pane IDs.
    """
    if not path:
        return
    try:
        with open(path, "w") as handle:
            json.dump({"pane_id": pane_id, "waiting": waiting_ids(agents)}, handle)
    except (IOError, OSError):
        # Losing the cursor costs one misplaced jump, nothing more; failing the
        # action over it would cost the jump itself.
        pass
