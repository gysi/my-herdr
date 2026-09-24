"""Bidirectional navigation, sidebar sorting, and shared persisted state."""
import json
import os
from pathlib import Path
import unittest

from tests import support
from myherdr.attention import navigation as attention
from .test_next import agent, listing


class NavigationTest(unittest.TestCase):
    def test_priority_order_and_ties(self):
        agents = listing(agent("w1:p1", "idle", 999), agent("w2:p1", "blocked", 3),
                         agent("w1:p9", "blocked", 3), agent("w1:p2", "blocked", 2),
                         agent("w1:p3", "done", 99), agent("w1:p4", "working", 999),
                         agent("w1:p5", "unknown", 999))
        self.assertEqual([a["pane_id"] for a in attention.ring(agents, "priority")],
                         ["w2:p1", "w1:p9", "w1:p2", "w1:p3", "w1:p4", "w1:p1", "w1:p5"])
        # Urgency still picks oldest, independent of sidebar order.
        self.assertEqual(attention.choose(attention.ring(agents, "priority"), None, {})["pane_id"],
                         "w1:p2")

    def test_urgency_tie_breaking_still_uses_natural_ids(self):
        agents = attention.ring(listing(agent("w1:p10", "blocked", 3),
                                       agent("w1:p2", "blocked", 3)))
        self.assertEqual(attention.choose(agents, None, {})["pane_id"], "w1:p2")

    def test_reverse_wrap_and_manual_focus_override(self):
        agents = attention.ring(listing(agent("w1:p1"), agent("w1:p2"), agent("w1:p3")))
        for direction, expected in [(1, "w1:p2"), (-1, "w1:p3")]:
            self.assertEqual(attention.choose(agents, "w1:p1", {"pane_id": "w1:p2"},
                                              direction)["pane_id"], expected)

    def test_reverse_ignores_new_waiting_agents(self):
        for status in ("blocked", "done"):
            agents = attention.ring(listing(agent("w1:p1", status, 3),
                                           agent("w1:p2"), agent("w1:p3")))
            self.assertEqual(attention.choose(agents, "w1:p3", {}, -1)["pane_id"], "w1:p2")

    def test_reverse_ignores_new_episode_in_known_pane(self):
        agents = attention.ring(listing(agent("w1:p1", "done", 20),
                                       agent("w1:p2"), agent("w1:p3")))
        cursor = {"pane_id": "w1:p1", "visited": {"w1:p1": ["done", 10]}}
        self.assertEqual(attention.choose(agents, "w1:p3", cursor, -1)["pane_id"], "w1:p2")

    def test_unanchored_reverse_and_saved_anchor_outside_list(self):
        agents = attention.ring(listing(agent("w1:p1"), agent("w1:p2"), agent("w1:p3")))
        for cursor, expected in [({}, "w1:p3"), ({"pane_id": "gone"}, "w1:p3"),
                                 ({"pane_id": "w1:p3"}, "w1:p2")]:
            self.assertEqual(attention.choose(agents, "shell", cursor, -1)["pane_id"], expected)
        self.assertIsNone(attention.choose([], None, {}, -1))
        self.assertIsNone(attention.choose([agent("w1:p1")], "w1:p1", {}, -1))

    def test_reverse_reaches_every_agent(self):
        agents = attention.ring(listing(agent("w1:p1"), agent("w1:p2"), agent("w1:p3")))
        here, seen = "w1:p1", []
        for _ in range(6):
            here = attention.choose(agents, here, {}, -1)["pane_id"]
            seen.append(here)
        self.assertEqual(seen, ["w1:p3", "w1:p2", "w1:p1"] * 2)


class ActionTest(support.EndToEndCase):
    def test_next_prev_next_share_position_and_preserve_pending_answer(self):
        here = "w1:p1"
        for action, expected in [("attention-next", "w1:p2"),
                                 ("attention-prev", "w1:p1"),
                                 ("attention-next", "w2:p1")]:
            result = self.invoke(action, env={"HERDR_PANE_ID": here})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.herdr_commands()[-1], "agent focus " + expected)
            cursor = json.loads(Path(self.tmp, attention.CURSOR_FILE).read_text())
            self.assertEqual(cursor["pane_id"], expected)
            here = expected

    def test_sort_toggle_changes_next_and_previous_targets(self):
        env = {"HERDR_SOCKET_PATH": "/run/herdr/test.sock",
               "XDG_STATE_HOME": os.path.join(self.tmp, "state"), "HERDR_PANE_ID": "w1:p2"}
        fixtures = Path(self.tmp, "fixtures")
        fixtures.mkdir()
        agents = listing(agent("w1:p1"), agent("w1:p2", "working"),
                         agent("w1:p3", "blocked"), agent("w1:p4", "done"))
        (fixtures / "agent_list.json").write_text(json.dumps({"result": agents}))
        env["HERDR_MOCK_DIR"] = str(fixtures)
        # Match herdr's client-socket filename without using preference_path,
        # which would hide API/client-socket confusion in the fixture itself.
        path = Path(env["XDG_STATE_HOME"], "herdr/client-shell/local-39bad257cb5e1da8.json")
        path.parent.mkdir(parents=True)
        # Both waiting states have already been visited, so next cycles normally.
        attention.write_cursor(os.path.join(self.tmp, attention.CURSOR_FILE), "w1:p2",
                               {"w1:p3": ["blocked", 0], "w1:p4": ["done", 0]})
        for mode, action, expected in [("spaces", "attention-next", "w1:p3"),
                                       ("priority", "attention-next", "w1:p1"),
                                       ("priority", "attention-prev", "w1:p4"),
                                       ("spaces", "attention-prev", "w1:p1")]:
            path.write_text(json.dumps({"agent_panel_sort": mode}))
            result = self.invoke(action, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.herdr_commands()[-1], "agent focus " + expected)
            self.assertIn("sort=" + mode, result.stdout)

    def test_previous_without_writable_state_uses_invoking_pane(self):
        result = self.invoke("attention-prev", env={"HERDR_PANE_ID": "w1:p2",
                             "HERDR_PLUGIN_STATE_DIR": os.path.join(self.tmp, "missing")})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_commands()[-1], "agent focus w1:p1")

    def test_previous_context_fallback(self):
        result = self.invoke("attention-prev", env={"HERDR_PANE_ID": None,
                             "HERDR_PLUGIN_CONTEXT_JSON": '{"focused_pane_id":"w1:p2"}'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_commands()[-1], "agent focus w1:p1")

    def test_empty_and_current_only_lists_notify(self):
        fixtures = Path(self.tmp, "fixtures")
        fixtures.mkdir()
        for agents in ([], [agent("w1:p1")]):
            (fixtures / "agent_list.json").write_text(json.dumps({"result": listing(*agents)}))
            result = self.invoke("attention-prev", env={"HERDR_PANE_ID": "w1:p1",
                                 "HERDR_MOCK_DIR": str(fixtures)})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(self.herdr_commands()[-1].startswith("notification show"))
            self.assertNotIn("agent focus", "\n".join(self.herdr_commands()))

    def test_previous_failure_does_not_replace_cursor(self):
        path = Path(self.tmp, attention.CURSOR_FILE)
        original = '{"pane_id":"w1:p2","waiting":[]}'
        path.write_text(original)
        result = self.invoke("attention-prev", env={"HERDR_PANE_ID": "w1:p2",
                             "HERDR_MOCK_FAIL": "agent focus:pane_not_found:gone"})
        self.assertEqual(result.returncode, 1)
        self.assertEqual(path.read_text(), original)
        self.assertTrue(self.herdr_commands()[-1].startswith("notification show"))

    def test_corrupt_cursor_fields_do_not_crash_navigation(self):
        Path(self.tmp, attention.CURSOR_FILE).write_text('{"pane_id":[],"waiting":[{}]}')
        for action in ("attention-next", "attention-prev"):
            result = self.invoke(action, env={"HERDR_PANE_ID": "w1:p1"})
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_previous_list_failure_toasts(self):
        result = self.invoke("attention-prev", env={
            "HERDR_MOCK_FAIL": "agent list:server_error:socket closed"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("socket closed", result.stderr)
        self.assertTrue(self.herdr_commands()[-1].startswith("notification show"))
