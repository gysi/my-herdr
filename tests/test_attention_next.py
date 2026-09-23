"""attention-next: who is picked, in what order, and how the walk moves on."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import support  # noqa: F401  (puts the plugin root on sys.path)

from myherdr import attention as attention_next, herdr
from myherdr.actions import attention_next as next_action
from myherdr.context import Context
from myherdr.errors import MyHerdrError


def agent(pane_id, status="idle", seq=0, tab=None, **extra):
    """Build an agent entry for attention-selection tests.

    Args:
        pane_id: String pane identifier; its prefix supplies the workspace ID.
        status: Agent status string; defaults to idle.
        seq: State-change sequence number; defaults to zero, the oldest priority.
        tab: String tab ID; None or an empty string selects the workspace's first tab.
        **extra: Agent fields to add or override, including deliberately invalid values.

    Returns:
        Dictionary shaped like an entry in an agent-list response.
    """
    workspace = pane_id.split(":")[0]
    item = {
        "pane_id": pane_id,
        "agent_status": status,
        "state_change_seq": seq,
        "agent": "claude",
        "workspace_id": workspace,
        "tab_id": tab or "%s:t1" % workspace,
    }
    item.update(extra)
    return item


def listing(*agents):
    """Wrap agent entries in an agent-list result.

    Args:
        *agents: Agent dictionaries or malformed entries for robustness tests.

    Returns:
        Dictionary with agents and type fields, without a CLI response envelope.
    """
    return {"agents": list(agents), "type": "agent_list"}


class RingTest(unittest.TestCase):
    """The walk order: position only, never status."""

    def ids(self, result):
        """Extract pane IDs in the action's traversal order.

        Args:
            result: Agent-list result dictionary, or malformed input under test.

        Returns:
            List of pane ID strings in ring order.
        """
        return [a["pane_id"] for a in attention_next.ring(result)]

    def test_grouped_preserves_api_workspace_tab_and_layout_order(self):
        result = listing(
            agent("w2:p1", tab="w2:t1"), agent("w1:p9", tab="w1:t2"),
            agent("w1:p2", tab="w1:t1"))
        self.assertEqual(self.ids(result), ["w2:p1", "w1:p9", "w1:p2"])

    def test_grouped_does_not_sort_pane_ids(self):
        result = listing(agent("w1:p10"), agent("w1:p2"), agent("w1:p1"))
        self.assertEqual(self.ids(result), ["w1:p10", "w1:p2", "w1:p1"])

    def test_status_does_not_move_an_agent_in_the_ring(self):
        # The ring has to stay put as agents work and finish, or the walk would
        # reshuffle underfoot between presses.
        quiet = self.ids(listing(agent("w1:p1"), agent("w1:p2"), agent("w1:p3")))
        busy = self.ids(listing(agent("w1:p1", "done", seq=9),
                                agent("w1:p2", "blocked", seq=5), agent("w1:p3", "working")))
        self.assertEqual(quiet, busy)

    def test_agents_of_any_kind_are_in_the_ring(self):
        self.assertEqual(self.ids(listing(agent("w1:p1", agent="codex"))), ["w1:p1"])

    def test_a_degraded_server_means_an_empty_ring(self):
        for result in ({}, None, {"agents": None}, {"agents": "nope"}, listing()):
            self.assertEqual(self.ids(result), [], repr(result))

    def test_unusable_entries_are_ignored_not_fatal(self):
        result = listing("not a dict", {"agent_status": "blocked"}, agent("w1:p1"))
        self.assertEqual(self.ids(result), ["w1:p1"])

    def test_an_agent_with_no_place_still_sorts(self):
        result = listing({"pane_id": "w1:p1", "agent_status": "idle"}, agent("w1:p2"))
        self.assertEqual(sorted(self.ids(result)), ["w1:p1", "w1:p2"])


class UrgencyTest(unittest.TestCase):
    def urgent(self, result, here=None):
        """Find the pane with the highest attention priority.

        Args:
            result: Agent-list result dictionary to order and inspect.
            here: Current pane ID to exclude; None excludes no pane.

        Returns:
            Selected pane ID string, or None when no agent needs attention.
        """
        found = attention_next.most_urgent(attention_next.ring(result), here)
        return found["pane_id"] if found else None

    def test_blocked_comes_before_done(self):
        # Someone waiting on an answer outranks output nobody has read yet,
        # even when the finished agent has been waiting longer.
        result = listing(agent("w1:p1", "done", seq=10), agent("w1:p2", "blocked", seq=99))
        self.assertEqual(self.urgent(result), "w1:p2")

    def test_oldest_waiting_first(self):
        result = listing(agent("w1:p1", "blocked", seq=300), agent("w1:p2", "blocked", seq=100))
        self.assertEqual(self.urgent(result), "w1:p2")

    def test_idle_and_working_agents_are_never_urgent(self):
        result = listing(agent("w1:p1", "idle"), agent("w1:p2", "working"),
                         agent("w1:p3", "unknown"))
        self.assertIsNone(self.urgent(result))

    def test_the_current_pane_is_not_urgent(self):
        # You are already looking at it.
        result = listing(agent("w1:p1", "blocked", seq=1), agent("w1:p2", "blocked", seq=2))
        self.assertEqual(self.urgent(result, here="w1:p1"), "w1:p2")

    def test_other_workspaces_count(self):
        result = listing(agent("w1:p1", "blocked", seq=2), agent("w9:p1", "blocked", seq=1))
        self.assertEqual(self.urgent(result), "w9:p1")

    def test_an_unusable_sequence_sorts_as_oldest(self):
        result = listing(agent("w1:p1", "blocked", seq="?"), agent("w1:p2", "blocked", seq=5))
        self.assertEqual(self.urgent(result), "w1:p1")


class WalkTest(unittest.TestCase):
    """Pressing again moves on, and can reach every agent."""

    def setUp(self):
        self.agents = attention_next.ring(
            listing(agent("w1:p1"), agent("w1:p2"), agent("w1:p3")))

    def choose(self, here, cursor, agents=None):
        """Select a pane using the current position and saved traversal state.

        Args:
            here: Current pane ID string.
            cursor: Saved cursor dictionary; an empty dictionary starts a new walk.
            agents: Ordered agent list; None or an empty list uses the default fixture.

        Returns:
            Selected pane ID string.
        """
        return attention_next.choose(agents or self.agents, here, cursor)["pane_id"]

    def test_the_first_press_starts_at_the_top_of_the_ring(self):
        self.assertEqual(self.choose("w9:p9", {}), "w1:p1")

    def test_the_walk_advances(self):
        self.assertEqual(self.choose("w1:p1", {"pane_id": "w1:p1", "waiting": []}), "w1:p2")

    def test_the_walk_wraps(self):
        self.assertEqual(self.choose("w1:p3", {"pane_id": "w1:p3", "waiting": []}), "w1:p1")

    def test_the_walk_reaches_every_agent(self):
        # The regression test for the ping-pong bug: anchored in the filtered
        # list, this cycled between two agents and never reached the third.
        here, cursor, seen = "w1:p1", {"pane_id": "w1:p1", "waiting": []}, []
        for _ in range(6):
            target = attention_next.choose(self.agents, here, cursor)
            seen.append(target["pane_id"])
            here = target["pane_id"]
            cursor = {"pane_id": here, "waiting": attention_next.waiting_ids(self.agents)}
        self.assertEqual(seen, ["w1:p2", "w1:p3", "w1:p1", "w1:p2", "w1:p3", "w1:p1"])

    def test_a_blocked_agent_does_not_trap_the_walk(self):
        # One blocked agent and two finished ones, the live setup that exposed
        # the bug: the walk must still reach all three.
        agents = attention_next.ring(
            listing(agent("w1:p1", "blocked", seq=9), agent("w1:p2"), agent("w1:p3")))
        waiting = attention_next.waiting_ids(agents)
        here, cursor, seen = "w1:p1", {"pane_id": "w1:p1", "waiting": waiting}, []
        for _ in range(4):
            target = attention_next.choose(agents, here, cursor)
            seen.append(target["pane_id"])
            here = target["pane_id"]
            cursor = {"pane_id": here, "waiting": waiting}
        self.assertEqual(seen, ["w1:p2", "w1:p3", "w1:p1", "w1:p2"])

    def test_a_vanished_anchor_restarts_the_walk(self):
        self.assertEqual(self.choose("w9:p9", {"pane_id": "w1:p9", "waiting": []}), "w1:p1")

    def test_the_current_pane_is_never_the_target(self):
        self.assertEqual(self.choose("w1:p2", {"pane_id": "w1:p1", "waiting": []}), "w1:p3")

    def test_a_single_other_agent_is_always_the_target(self):
        agents = attention_next.ring(listing(agent("w1:p1"), agent("w1:p2")))
        self.assertEqual(self.choose("w1:p1", {"pane_id": "w1:p1", "waiting": []}, agents),
                         "w1:p2")

    def test_a_newly_waiting_agent_cuts_in(self):
        agents = attention_next.ring(
            listing(agent("w1:p1"), agent("w1:p2"), agent("w1:p3", "blocked", seq=4)))
        # Mid-walk at p1, and p3 blocks: the next press goes to p3, not p2.
        self.assertEqual(self.choose("w1:p1", {"pane_id": "w1:p1", "waiting": []}, agents),
                         "w1:p3")

    def test_a_still_waiting_agent_is_not_news_twice(self):
        # p3 stays blocked, so pressing again walks on. This is what lets the
        # key reach an idle agent while p3 keeps waiting.
        agents = attention_next.ring(
            listing(agent("w1:p1"), agent("w1:p2"), agent("w1:p3", "blocked", seq=4)))
        cursor = {"pane_id": "w1:p3", "waiting": ["w1:p3"]}
        self.assertEqual(self.choose("w1:p3", cursor, agents), "w1:p1")

    def test_an_agent_that_stops_waiting_does_not_restart_the_walk(self):
        # You answered p3 and carried on; the walk keeps its place.
        cursor = {"pane_id": "w1:p1", "waiting": ["w1:p3"]}
        self.assertEqual(self.choose("w1:p1", cursor), "w1:p2")

    def test_news_about_the_current_pane_does_not_derail_the_walk(self):
        # The pane you are in just blocked. You can see it; keep walking.
        agents = attention_next.ring(
            listing(agent("w1:p1", "blocked", seq=4), agent("w1:p2"), agent("w1:p3")))
        self.assertEqual(self.choose("w1:p1", {"pane_id": "w1:p1", "waiting": []}, agents),
                         "w1:p2")

    def test_waiting_ids_cover_the_whole_ring(self):
        # Including the current pane: otherwise walking onto a blocked agent
        # would make it look like it stopped and then started waiting again.
        agents = attention_next.ring(listing(agent("w1:p1", "blocked"), agent("w1:p2")))
        self.assertEqual(attention_next.waiting_ids(agents), ["w1:p1"])


class CursorFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="my-herdr-cursor-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "cursor.json")

    def test_round_trip(self):
        agents = [agent("w1:p1", "blocked"), agent("w1:p2")]
        attention_next.write_cursor(self.path, "w1:p2", agents)
        self.assertEqual(attention_next.read_cursor(self.path),
                         {"pane_id": "w1:p2", "waiting": ["w1:p1"]})

    def test_a_missing_or_broken_cursor_is_not_an_error(self):
        self.assertEqual(attention_next.read_cursor(self.path), {})
        for junk in ("{not json", "[1, 2]"):
            with open(self.path, "w") as handle:
                handle.write(junk)
            self.assertEqual(attention_next.read_cursor(self.path), {})

    def test_an_unwritable_cursor_does_not_fail_the_jump(self):
        unwritable = os.path.join(self.tmp, "no-such-dir", "cursor.json")
        attention_next.write_cursor(unwritable, "w1:p1", [agent("w1:p1")])

    def test_no_state_dir_means_no_cursor(self):
        # Without persisted state, the invoking pane can still anchor navigation.
        self.assertIsNone(attention_next.cursor_path(Context(env={})))
        self.assertEqual(attention_next.read_cursor(None), {})
        attention_next.write_cursor(None, "w1:p1", [])


class ActionTest(unittest.TestCase):
    """main(), with the herdr CLI faked at the run() seam."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="my-herdr-action-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = {"HERDR_PANE_ID": "w1:p9", "HERDR_PLUGIN_STATE_DIR": self.tmp,
                    "HOME": os.path.join(self.tmp, "home")}

    def run_action(self, *answers, **kwargs):
        """Run attention-next with mocked CLI responses and record its exit code.

        Args:
            *answers: Completed subprocess results to replay in call order.
            **kwargs: Optional env dictionary overriding the isolated action environment;
                values of None remove variables. Other keys are ignored.

        Returns:
            Recorder containing the CLI calls; self.exit_code holds the action's result.

        Raises:
            MyHerdrError: The action encounters an unrecoverable CLI failure.
        """
        recorder = support.Recorder(*answers)
        env = dict(self.env)
        for key, value in kwargs.pop("env", {}).items():
            # None removes a variable, so a test can run without one herdr
            # would normally set.
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        with mock.patch.dict("os.environ", env, clear=True):
            with mock.patch.object(herdr, "run", recorder):
                self.exit_code = next_action.main([])
        return recorder

    def focused(self, recorder):
        """Assert that the final CLI command focuses an agent and extract its pane.

        Args:
            recorder: Recorder containing calls from an action invocation.

        Returns:
            Focused pane ID string.

        Raises:
            AssertionError: The final command is not an agent-focus command.
        """
        self.assertTrue(recorder.commands[-1].startswith("agent focus "))
        return recorder.commands[-1].split()[-1]

    def test_focuses_the_agent_that_is_waiting(self):
        recorder = self.run_action(support.ok(listing(
            agent("w1:p1"), agent("w1:p2", "blocked", seq=2))))
        self.assertEqual(self.exit_code, 0)
        self.assertEqual(recorder.commands, ["agent list", "agent focus w1:p2"])

    def test_walks_the_whole_ring_as_focus_follows_along(self):
        # The live failure: each press lands somewhere, which becomes the pane
        # the next press is invoked from. Every agent must still be reachable.
        agents = listing(agent("w1:p1"), agent("w1:p2"), agent("w1:p3"))
        here, seen = "w1:p1", []
        for _ in range(4):
            here = self.focused(self.run_action(support.ok(agents),
                                                env={"HERDR_PANE_ID": here}))
            seen.append(here)
        self.assertEqual(seen, ["w1:p2", "w1:p3", "w1:p1", "w1:p2"])

    def test_a_blocked_agent_does_not_trap_the_walk(self):
        # One blocked, two finished and read: your three-agent session.
        agents = listing(agent("w1:p1", "blocked", seq=9), agent("w1:p2"), agent("w1:p3"))
        here, seen = "w1:p9", []
        for _ in range(4):
            here = self.focused(self.run_action(support.ok(agents),
                                                env={"HERDR_PANE_ID": here}))
            seen.append(here)
        # Blocked first because it is news, then the ring, reaching all three.
        self.assertEqual(seen, ["w1:p1", "w1:p2", "w1:p3", "w1:p1"])

    def test_a_new_blocker_interrupts_the_walk(self):
        quiet = listing(agent("w1:p1"), agent("w1:p2"), agent("w1:p3"))
        self.run_action(support.ok(quiet))  # lands on p1
        busy = listing(agent("w1:p1"), agent("w1:p2"), agent("w1:p3", "blocked", seq=9))
        self.assertEqual(self.focused(self.run_action(support.ok(busy))), "w1:p3")

    def test_no_other_agent_toasts_instead_of_failing(self):
        # Headless: without the toast the keypress would look broken.
        recorder = self.run_action(support.ok(listing(agent("w1:p9"))))
        self.assertEqual(self.exit_code, 0)
        self.assertEqual(len(recorder.commands), 2)  # the listing, then the toast
        self.assertTrue(recorder.commands[1].startswith("notification show"))
        self.assertIn("No other agent", " ".join(recorder.calls[1]))

    def test_the_invoking_pane_is_skipped_via_the_environment(self):
        recorder = self.run_action(
            support.ok(listing(agent("w1:p9", "blocked", seq=1),
                               agent("w1:p2", "blocked", seq=2))))
        self.assertEqual(self.focused(recorder), "w1:p2")

    def test_falls_back_to_the_context_when_there_is_no_pane_variable(self):
        # `plugin action invoke` from the CLI sets no HERDR_PANE_ID.
        recorder = self.run_action(
            support.ok(listing(agent("w1:p1", "blocked", seq=1),
                               agent("w1:p2", "blocked", seq=2))),
            env={"HERDR_PANE_ID": None,
                 "HERDR_PLUGIN_CONTEXT_JSON": json.dumps({"focused_pane_id": "w1:p1"})})
        self.assertEqual(self.focused(recorder), "w1:p2")

    def test_a_failing_list_is_reported_not_swallowed(self):
        with self.assertRaises(MyHerdrError):
            self.run_action(support.failure("server_error", "socket closed"))

    def test_a_failed_focus_leaves_the_cursor_alone(self):
        # Otherwise the next press would start from a pane we never reached.
        agents = listing(agent("w1:p1"), agent("w1:p2"))
        with self.assertRaises(MyHerdrError):
            self.run_action(support.ok(agents), support.failure("pane_not_found"))
        self.assertEqual(self.focused(self.run_action(support.ok(agents))), "w1:p1")


class EndToEndTest(support.EndToEndCase):
    def test_jumps_to_the_blocked_agent_in_the_fixture(self):
        # Fixture: blocked w1:p2 (seq 300), done w2:p1 (seq 200), idle w1:p1, working w2:p2.
        result = self.invoke("attention-next", env={"HERDR_PANE_ID": "w1:p1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_commands(), ["agent list", "agent focus w1:p2"])
        self.assertIn("w1:p2", result.stdout)

    def test_pressing_again_walks_the_ring(self):
        # The cursor lives in HERDR_PLUGIN_STATE_DIR, which survives the process.
        # Focus follows the action, so each press is invoked from the last target.
        here, seen = "w1:p1", []
        for _ in range(4):
            result = self.invoke("attention-next", env={"HERDR_PANE_ID": here})
            self.assertEqual(result.returncode, 0, result.stderr)
            here = self.herdr_commands()[-1].split()[-1]
            seen.append(here)
        # Blocked first, then round the ring: every agent is reachable.
        self.assertEqual(seen, ["w1:p2", "w2:p1", "w2:p2", "w1:p1"])

    def test_a_session_with_one_agent_only_toasts(self):
        fixtures = os.path.join(self.tmp, "fixtures")
        os.makedirs(fixtures)
        with open(os.path.join(fixtures, "agent_list.json"), "w") as handle:
            json.dump({"id": "cli:agent:list", "result": listing(agent("w1:p1"))}, handle)
        result = self.invoke("attention-next", env={
            "HERDR_MOCK_DIR": fixtures, "HERDR_PANE_ID": "w1:p1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.herdr_commands()), 2)
        self.assertTrue(self.herdr_commands()[1].startswith("notification show"))

    def test_a_broken_server_toasts_the_error_and_fails(self):
        result = self.invoke("attention-next", env={
            "HERDR_MOCK_FAIL": "agent list:server_error:socket closed"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("socket closed", result.stderr)
        self.assertTrue(self.herdr_commands()[-1].startswith("notification show"))


if __name__ == "__main__":
    unittest.main()
