"""pane-to-tab: the argv sent, and the answers that mean "nothing happened"."""
import json
import unittest
from unittest import mock

from tests import support  # noqa: F401

from myherdr.shared import herdr
from myherdr.pane_to_tab import action as pane_to_tab
from myherdr.shared.errors import MyHerdrError

CONTEXT = {
    "workspace_id": "w1",
    "tab_id": "w1:t1",
    "focused_pane_id": "w1:p1",
    "invocation_source": "keybinding",
}


def tab(tab_id, pane_count, workspace="w1"):
    """Build a tab-list entry for move tests.

    Args:
        tab_id: String ID of the tab being described.
        pane_count: Number of panes in that tab.
        workspace: Owning workspace ID string; defaults to w1.

    Returns:
        Tab dictionary including its location, pane count, and display metadata.
    """
    return {"tab_id": tab_id, "pane_count": pane_count, "workspace_id": workspace,
            "label": "work", "number": 1, "focused": True, "agent_status": "idle"}


def moved(changed=True, reason=None, pane="w1:p1", tab_id="w1:t9"):
    """Build a successful CLI response describing a pane-move outcome.

    Args:
        changed: Whether the move changed the layout; defaults to True.
        reason: No-op reason string, or None when no reason is supplied.
        pane: Resulting pane ID string; defaults to w1:p1.
        tab_id: Created tab ID string; defaults to w1:t9.

    Returns:
        Completed subprocess result containing a JSON move_result envelope.
    """
    result = {"move_result": {
        "changed": changed,
        "reason": reason,
        "previous_pane_id": "w1:p1",
        "pane": {"pane_id": pane},
        "created_tab": {"tab_id": tab_id},
    }}
    return support.ok(result)


class ActionTest(unittest.TestCase):
    def setUp(self):
        self.env = {
            "HERDR_PANE_ID": "w1:p1",
            "HERDR_TAB_ID": "w1:t1",
            "HERDR_WORKSPACE_ID": "w1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
        }

    def run_action(self, *answers, **kwargs):
        """Run pane-to-tab with mocked CLI responses and record its exit code.

        Args:
            *answers: Completed subprocess results to replay in call order.
            **kwargs: Optional env dictionary overriding the isolated action environment;
                values of None remove variables. Other keys are ignored.

        Returns:
            Recorder containing the CLI calls; self.exit_code holds the action's result.

        Raises:
            MyHerdrError: The action cannot resolve or move the source pane.
        """
        recorder = support.Recorder(*answers)
        env = dict(self.env)
        for key, value in kwargs.pop("env", {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        with mock.patch.dict("os.environ", env, clear=True):
            with mock.patch.object(herdr, "run", recorder):
                self.exit_code = pane_to_tab.main([])
        return recorder

    def test_moves_the_pane_into_a_new_tab_in_its_own_workspace(self):
        recorder = self.run_action(support.ok({"tabs": [tab("w1:t1", 2)]}), moved())
        self.assertEqual(self.exit_code, 0)
        self.assertEqual(recorder.commands, [
            "tab list --workspace w1",
            "pane move w1:p1 --new-tab --workspace w1 --focus",
        ])

    def test_no_label_is_sent(self):
        # A plugin-set label looks like a manual rename to tab-renaming
        # plugins, which then never touch it again.
        recorder = self.run_action(support.ok({"tabs": [tab("w1:t1", 2)]}), moved())
        self.assertNotIn("--label", recorder.calls[-1])

    def test_a_pane_alone_in_its_tab_is_left_alone(self):
        # herdr would close the tab and build a new one for the same single
        # pane: churn in the tab bar with nothing to show for it.
        recorder = self.run_action(support.ok({"tabs": [tab("w1:t1", 1)]}))
        self.assertEqual(self.exit_code, 0)
        self.assertEqual(len(recorder.commands), 2)
        self.assertEqual(recorder.commands[0], "tab list --workspace w1")
        self.assertTrue(recorder.commands[1].startswith("notification show"))
        self.assertIn("already alone", " ".join(recorder.calls[1]))

    def test_a_silent_no_op_is_reported(self):
        # A zoomed tab makes the move a no-op rather than an error, so the
        # answer has to be read instead of assumed.
        recorder = self.run_action(
            support.ok({"tabs": [tab("w1:t1", 2)]}),
            moved(changed=False, reason="zoomed_tab"))
        self.assertEqual(self.exit_code, 0)
        self.assertTrue(recorder.commands[-1].startswith("notification show"))
        self.assertIn("zoomed_tab", " ".join(recorder.calls[-1]))

    def test_a_no_op_without_a_reason_still_reports(self):
        recorder = self.run_action(
            support.ok({"tabs": [tab("w1:t1", 2)]}), moved(changed=False))
        self.assertTrue(recorder.commands[-1].startswith("notification show"))

    def test_a_failed_move_is_reported_not_swallowed(self):
        with self.assertRaises(MyHerdrError):
            self.run_action(support.ok({"tabs": [tab("w1:t1", 2)]}),
                            support.failure("pane_not_found"))

    def test_an_unlistable_tab_does_not_block_the_move(self):
        # Better a pointless move than refusing a valid one.
        recorder = self.run_action(support.failure("server_error"), moved())
        self.assertEqual(self.exit_code, 0)
        self.assertEqual(recorder.commands[-1],
                         "pane move w1:p1 --new-tab --workspace w1 --focus")

    def test_an_unknown_tab_does_not_block_the_move(self):
        recorder = self.run_action(support.ok({"tabs": [tab("w9:t9", 1, "w9")]}), moved())
        self.assertEqual(recorder.commands[-1],
                         "pane move w1:p1 --new-tab --workspace w1 --focus")

    def test_the_pane_is_resolved_when_the_environment_is_bare(self):
        # `plugin action invoke` from the CLI sets no HERDR_PANE_ID; the
        # context still names the focused pane.
        recorder = self.run_action(
            support.ok({"tabs": [tab("w1:t1", 2)]}), moved(),
            env={"HERDR_PANE_ID": None, "HERDR_TAB_ID": None})
        self.assertEqual(recorder.commands[-1],
                         "pane move w1:p1 --new-tab --workspace w1 --focus")

    def test_no_pane_at_all_is_an_error(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(herdr, "run", support.Recorder(support.ok({}))):
                with self.assertRaises(MyHerdrError):
                    pane_to_tab.main([])


class LookupTest(unittest.TestCase):
    """Falling back to the server when the context describes another pane."""

    def test_the_tab_comes_from_the_server_for_a_foreign_pane(self):
        recorder = support.Recorder(support.ok({"pane": {"tab_id": "w2:t3"}}))
        with mock.patch.dict("os.environ", {"HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT)}):
            with mock.patch.object(herdr, "run", recorder):
                from myherdr.shared.context import Context
                self.assertEqual(pane_to_tab.tab_of("w2:p7", Context()), "w2:t3")
        # `pane get` takes a positional id, not --pane.
        self.assertEqual(recorder.commands, ["pane get w2:p7"])

    def test_the_workspace_falls_back_to_the_pane_id_prefix(self):
        recorder = support.Recorder(support.failure("pane_not_found"))
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(herdr, "run", recorder):
                from myherdr.shared.context import Context
                self.assertEqual(pane_to_tab.workspace_of("w4:p2", Context()), "w4")


class EndToEndTest(support.EndToEndCase):
    def test_moves_the_pane_and_reports_the_new_tab(self):
        result = self.invoke("pane-to-tab", env={
            "HERDR_PANE_ID": "w1:p1",
            "HERDR_TAB_ID": "w1:t1",
            "HERDR_WORKSPACE_ID": "w1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        # Fixtures put w1:p1 in a two-pane tab, so the move goes ahead.
        self.assertEqual(self.herdr_commands(), [
            "tab list --workspace w1",
            "pane move w1:p1 --new-tab --workspace w1 --focus",
        ])
        self.assertIn("w1:t9", result.stdout)

    def test_a_pane_alone_in_its_tab_never_reaches_the_move(self):
        result = self.invoke("pane-to-tab", env={
            "HERDR_PANE_ID": "w1:p2",
            "HERDR_TAB_ID": "w1:t2",
            "HERDR_WORKSPACE_ID": "w1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(
                dict(CONTEXT, focused_pane_id="w1:p2", tab_id="w1:t2")),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("pane move", " ".join(self.herdr_commands()))
        self.assertIn("already alone", result.stdout)

    def test_a_broken_server_toasts_the_error_and_fails(self):
        result = self.invoke("pane-to-tab", env={
            "HERDR_PANE_ID": "w1:p1",
            "HERDR_WORKSPACE_ID": "w1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
            "HERDR_MOCK_FAIL": "pane move:invalid_pane:no such pane",
        })
        self.assertEqual(result.returncode, 1)
        self.assertIn("no such pane", result.stderr)
        self.assertTrue(self.herdr_commands()[-1].startswith("notification show"))


if __name__ == "__main__":
    unittest.main()
