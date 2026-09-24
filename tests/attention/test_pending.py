"""Pending attention survives unrelated visits and sidebar navigation."""
import json
from pathlib import Path
import unittest

from myherdr.attention import navigation
from tests import support
from .test_next import agent, listing


class ReconciliationTest(unittest.TestCase):
    def test_stale_visits_are_pruned_without_mutating_saved_state(self):
        cursor = {"visited": {"w1:p1": ["blocked", 1], "w1:p2": ["done", 2],
                              "w1:p3": ["done", 3], "w1:p4": ["done", 4],
                              "w1:p5": ["blocked", 5], "w1:p6": ["done", 6]}}
        before = json.dumps(cursor)
        agents = [agent("w1:p1", "blocked", 1), agent("w1:p2", "idle", 2),
                  agent("w1:p3", "working", 3), agent("w1:p5", "done", 5),
                  agent("w1:p6", "done", 7)]
        self.assertEqual(navigation.visited_states(agents, cursor),
                         {"w1:p1": ["blocked", 1]})
        self.assertEqual([a["pane_id"] for a in navigation.pending_agents(agents, None, cursor)],
                         ["w1:p5", "w1:p6"])
        self.assertEqual(json.dumps(cursor), before)

    def test_new_state_only_here_does_not_revisit_an_old_blocker(self):
        agents = [agent("w1:p1", "done", 30), agent("w1:p2"),
                  agent("w1:p3", "blocked", 1)]
        cursor = {"visited": {"w1:p1": ["done", 10], "w1:p3": ["blocked", 1]}}
        self.assertEqual(navigation.choose(agents, "w1:p1", cursor)["pane_id"], "w1:p2")

    def test_other_clients_focus_flags_do_not_acknowledge_pending_work(self):
        agents = [agent("w1:p1"), agent("w1:p2"), agent("w2:p1", "done", 1, focused=True)]
        self.assertEqual(navigation.choose(agents, "w1:p1", {})["pane_id"], "w2:p1")


class PendingActionTest(support.EndToEndCase):
    def setUp(self):
        """Create isolated mock snapshots, configuration, and navigation state."""
        super().setUp()
        self.fixtures = Path(self.tmp, "fixtures")
        self.fixtures.mkdir()
        self.config = Path(self.tmp, "config.toml")
        self.cursor = Path(self.tmp, navigation.CURSOR_FILE)

    def jump(self, agents, here, action="attention-next", mode="spaces", **env):
        """Invoke the dispatcher against a snapshot and return its output.

        Args:
            agents (list[dict]): Mock agent records for this invocation.
            here (str): Invoking pane ID, including non-agent source panes.
            action (str): Navigation action, defaulting to attention-next.
            mode (str): Sidebar sort mode, defaulting to grouped spaces.
            **env (str): Additional isolated environment overrides.

        Returns:
            subprocess.CompletedProcess: Dispatcher output and exit status.
        """
        (self.fixtures / "agent_list.json").write_text(json.dumps({"result": listing(*agents)}))
        self.config.write_text('[ui]\nagent_panel_sort = "%s"\n' % mode)
        return self.invoke(action, env={"HERDR_MOCK_DIR": str(self.fixtures),
                                       "HERDR_CONFIG_PATH": str(self.config),
                                       "HERDR_PANE_ID": here, **env})

    def test_each_pending_state_is_visited_before_sidebar_cycling(self):
        for mode in ("spaces", "priority"):
            for statuses in (("done", "done"), ("blocked", "done"), ("blocked", "blocked")):
                with self.subTest(mode=mode, statuses=statuses):
                    self.cursor.unlink(missing_ok=True)
                    agents = [agent("w1:p1", statuses[0], 10), agent("w1:p2"),
                              agent("w2:p1", statuses[1], 20), agent("w2:p2")]
                    here = "w2:p2"
                    for expected in ("w1:p1", "w2:p1"):
                        result = self.jump(agents, here, mode=mode)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(self.herdr_commands()[-1], "agent focus " + expected)
                        self.assertIn("reason=urgent", result.stdout)
                        here = expected
                    # Persistent blockers/done snapshots must not trap cycling.
                    seen = set()
                    for _ in agents:
                        result = self.jump(agents, here, mode=mode)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn("reason=sidebar; pending={}", result.stdout)
                        here = self.herdr_commands()[-1].split()[-1]
                        seen.add(here)
                    self.assertEqual(seen, {a["pane_id"] for a in agents})

    def test_previous_elsewhere_preserves_pending_done_and_logs_why(self):
        agents = [agent("w1:p1", "done", 10), agent("w1:p2"), agent("w1:p3")]
        result = self.jump(agents, "w1:p3", "attention-prev")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_commands()[-1], "agent focus w1:p2")
        self.assertIn('source=w1:p3; reason=sidebar; pending={"w1:p1": ["done", 10]}',
                      result.stdout)
        self.assertEqual(json.loads(self.cursor.read_text())["visited"], {})
        result = self.jump(agents, "w1:p2")
        self.assertEqual(self.herdr_commands()[-1], "agent focus w1:p1")
        self.assertIn('source=w1:p2; reason=urgent; pending={"w1:p1": ["done", 10]}',
                      result.stdout)

    def test_previous_acknowledges_only_source_and_destination(self):
        agents = [agent("w1:p1", "blocked", 10), agent("w1:p2", "blocked", 20),
                  agent("w1:p3", "done", 30), agent("w1:p4")]
        result = self.jump(agents, "w1:p2", "attention-prev")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_commands()[-1], "agent focus w1:p1")
        self.assertEqual(json.loads(self.cursor.read_text())["visited"],
                         {"w1:p1": ["blocked", 10], "w1:p2": ["blocked", 20]})
        self.jump(agents, "w1:p1")
        self.assertEqual(self.herdr_commands()[-1], "agent focus w1:p3")

    def test_pending_work_that_stops_waiting_does_not_interrupt(self):
        for status in ("idle", "working", None):
            with self.subTest(status=status):
                self.cursor.unlink(missing_ok=True)
                agents = [agent("w1:p1", "blocked", 10), agent("w1:p2"),
                          agent("w1:p3", "done", 20)]
                self.jump(agents, "w1:p2")
                if status is None:
                    agents.pop()
                else:
                    agents[2]["agent_status"] = status
                result = self.jump(agents, "w1:p1")
                self.assertEqual(self.herdr_commands()[-1], "agent focus w1:p2")
                self.assertIn("reason=sidebar; pending={}", result.stdout)

    def test_list_and_focus_failures_preserve_visits_and_allow_retry(self):
        for action in ("attention-next", "attention-prev"):
            for failure in ("agent list", "agent focus"):
                with self.subTest(action=action, failure=failure):
                    original = json.dumps({"version": 2, "pane_id": "w1:p3",
                                           "visited": {"w1:p3": ["blocked", 5]}})
                    self.cursor.write_text(original)
                    agents = [agent("w1:p1", "done", 10), agent("w1:p2"),
                              agent("w1:p3", "blocked", 5)]
                    result = self.jump(agents, "w1:p2", action,
                                       HERDR_MOCK_FAIL=failure + ":server_error:failed")
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(self.cursor.read_text(), original)
                    result = self.jump(agents, "w1:p2")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.herdr_commands()[-1], "agent focus w1:p1")

    def test_no_other_agent_leaves_state_unchanged(self):
        self.cursor.write_text('{"pane_id":"w1:p1","waiting":[]}')
        original = self.cursor.read_text()
        for action in ("attention-next", "attention-prev"):
            result = self.jump([agent("w1:p1", "done", 10)], "w1:p1", action)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("no other agent", result.stdout)
            self.assertEqual(self.cursor.read_text(), original)
