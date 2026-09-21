"""One key to reach any agent: whoever needs you, otherwise the next one along.

Two jobs in one action, because they are the same question asked twice. If some
agent needs you, go there. If nobody does, walk to the next one, so this key
alone is enough to reach every agent without a second binding.

Two orderings, kept deliberately separate:

* The **ring** is every agent by position — workspace, then tab, then pane. It
  never depends on status, so it does not reshuffle underfoot as agents work and
  finish. Repeated presses walk the ring and wrap.
* **Urgency** decides when to leave the ring: `blocked` before `done`, oldest
  state change first.

An agent that has *newly* started waiting since the last press cuts in and gets
that press. One that merely keeps waiting does not, so a persistently blocked
agent cannot trap the key and make every other agent unreachable. One that stops
waiting does not disturb the walk either, so you can answer an agent and carry
on where you were.

The pane you pressed the key in is never the target. That pane is usually the
one the *previous* press jumped to, which is why the walk is anchored in the
full agent ring and not in the filtered candidate list: the anchor has to stay
findable even once it is excluded as the current pane. Anchoring in the filtered
list makes the position lookup fail every time, restarting the walk at the front
and trapping it between the first two agents.

The anchor and the set of waiting agents it was decided against live in a cursor
file in $HERDR_PLUGIN_STATE_DIR.
"""
import json
import os
import re

from .. import herdr
from ..context import Context

#: Statuses that cut into the ring, in the order they are offered. `blocked` is
#: someone actively waiting on an answer; `done` is work finished but unread.
WAITING = ("blocked", "done")

CURSOR_FILE = "attention-next.json"


def main(args):
    ctx = Context()
    here = ctx.pane_id
    agents = ring(herdr.run_json("agent", "list"))
    if not any(item["pane_id"] != here for item in agents):
        # No agents, or only this pane. The action has no TTY, so silence would
        # look like a broken keybinding — though the toast is itself invisible
        # when ui.toast.delivery is off.
        herdr.notify("No other agent to jump to.")
        print("attention-next: no other agent")
        return 0

    path = cursor_path(ctx)
    target = choose(agents, here, read_cursor(path))
    herdr.run_json("agent", "focus", target["pane_id"])
    # Only now: an anchor pointing at a pane we failed to reach would make the
    # next press start from the wrong place.
    write_cursor(path, target["pane_id"], agents)

    print("attention-next: focused %s (%s, %s, seq %s) of %d agents, %d waiting" % (
        target["pane_id"], target.get("agent") or "?", target.get("agent_status"),
        target.get("state_change_seq"), len(agents), len(waiting_ids(agents))))
    return 0


def ring(result):
    """Every agent, in the stable order the walk follows.

    Position only: a status-dependent order would rearrange the ring whenever an
    agent started or stopped working. Defensive about the shape, because a
    degraded server answering `{}` should mean "nowhere to go", not a traceback
    in the plugin log.
    """
    agents = (result or {}).get("agents")
    if not isinstance(agents, list):
        return []
    found = [item for item in agents if isinstance(item, dict) and item.get("pane_id")]
    found.sort(key=_place)
    return found


def choose(agents, here, cursor):
    """The agent this press should go to.

    `agents` is the whole ring, including `here`; only the returned target is
    guaranteed to be some other pane.
    """
    if set(waiting_ids(agents)) - set(cursor.get("waiting") or []):
        # Somebody started waiting since the last press. That is news, and news
        # interrupts the walk.
        urgent = most_urgent(agents, here)
        if urgent is not None:
            return urgent
    return next_after(agents, cursor.get("pane_id"), here)


def most_urgent(agents, here):
    """The agent that has been waiting longest, or None if nobody else is."""
    waiting = [
        item for item in agents
        if item.get("agent_status") in WAITING and item["pane_id"] != here
    ]
    if not waiting:
        return None
    return min(waiting, key=lambda item: (
        WAITING.index(item["agent_status"]), _seq(item), _place(item)))


def next_after(agents, anchor, here):
    """The first agent after `anchor` in the ring that is not `here`, wrapping.

    An anchor that has vanished — or none at all, on the first press — starts
    the walk at the top of the ring.
    """
    pane_ids = [item["pane_id"] for item in agents]
    start = pane_ids.index(anchor) + 1 if anchor in pane_ids else 0
    for offset in range(len(agents)):
        item = agents[(start + offset) % len(agents)]
        if item["pane_id"] != here:
            return item
    return None


def waiting_ids(agents):
    """The pane ids that want attention, sorted.

    Computed over the whole ring, including the current pane, so that walking
    onto a blocked agent does not make it look like it stopped waiting and then
    started again on the way back.
    """
    return sorted(
        item["pane_id"] for item in agents if item.get("agent_status") in WAITING)


def _seq(item):
    """`state_change_seq` as a number; anything unusable sorts as oldest."""
    try:
        return int(item.get("state_change_seq"))
    except (TypeError, ValueError):
        return 0


def _place(item):
    """Where the agent sits: workspace, then tab, then pane."""
    return (_natural(item.get("workspace_id")), _natural(item.get("tab_id")),
            _natural(item.get("pane_id")))


def _natural(value):
    """Sort key where digit runs compare as numbers, so `p10` follows `p2`.

    Each part becomes a (number, text) pair so the parts stay comparable with
    each other whichever kind they are.
    """
    return tuple(
        (int(part), "") if part.isdigit() else (-1, part)
        for part in re.split(r"(\d+)", value or "")
    )


def cursor_path(ctx):
    """Where the cursor lives, or None when herdr gave us no state directory."""
    return os.path.join(ctx.state_dir, CURSOR_FILE) if ctx.state_dir else None


def read_cursor(path):
    """The last jump, or an empty dict. Never raises: the cursor is a convenience."""
    if not path:
        return {}
    try:
        with open(path) as handle:
            cursor = json.load(handle)
    except (IOError, OSError, ValueError):
        return {}
    return cursor if isinstance(cursor, dict) else {}


def write_cursor(path, pane_id, agents):
    """Record where we landed and who was waiting at the time. Failure is silent."""
    if not path:
        return
    try:
        with open(path, "w") as handle:
            json.dump({"pane_id": pane_id, "waiting": waiting_ids(agents)}, handle)
    except (IOError, OSError):
        # Losing the cursor costs one misplaced jump, nothing more; failing the
        # action over it would cost the jump itself.
        pass
