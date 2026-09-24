"""fork-tab-ask: the action that opens the popup, and the popup that names the fork."""
import io
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from tests import support  # noqa: F401

from myherdr import cli
from myherdr.forking import request as fork_request, line_editor as prompt
from myherdr.shared import herdr
from myherdr.forking import tab as fork_tab, tab_ask as fork_tab_ask
from myherdr.shared.errors import MyHerdrError
from myherdr.forking import popup as fork_prompt

CONTEXT = {
    "workspace_id": "w1",
    "tab_id": "w1:t1",
    "focused_pane_id": "w1:p1",
    "invocation_source": "keybinding",
}

ENV = {
    "HOME": support.NO_HOME,
    "HERDR_PANE_ID": "w1:p1",
    "HERDR_TAB_ID": "w1:t1",
    "HERDR_WORKSPACE_ID": "w1",
    "HERDR_PLUGIN_ID": "my-herdr",
    "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
}

AGENT = {
    "agent": "claude",
    "agent_session": {"kind": "id", "value": "11111111-2222-3333-4444-555555555555"},
    "cwd": "/home/user/project",
    "pane_id": "w1:p1",
    "workspace_id": "w1",
}


def agent_get(**overrides):
    """Build an agent-info CLI response from the popup's default source pane.

    Args:
        **overrides: Agent fields to replace, including deliberately invalid values.

    Returns:
        Completed subprocess result containing a JSON agent_info envelope.
    """
    return support.ok({"agent": dict(AGENT, **overrides), "type": "agent_info"})


class ActionTest(unittest.TestCase):
    def run_action(self, *answers):
        """Run fork-tab-ask with an isolated environment and mocked CLI responses.

        Args:
            *answers: Completed subprocess results to replay in call order.

        Returns:
            Recorder containing CLI calls; self.exit_code holds the action's result.

        Raises:
            MyHerdrError: Source validation or popup opening fails.
        """
        recorder = support.Recorder(*answers)
        with mock.patch.dict("os.environ", ENV, clear=True):
            with mock.patch.object(herdr, "run", recorder):
                self.exit_code = fork_tab_ask.main([])
        return recorder

    def test_checks_the_pane_then_opens_the_popup_with_the_source_pane(self):
        recorder = self.run_action(agent_get(), support.ok({"type": "ok"}))
        self.assertEqual(self.exit_code, 0)
        self.assertEqual(recorder.commands, [
            "agent get w1:p1",
            "plugin pane open --plugin my-herdr --entrypoint fork-prompt "
            "--env MH_SOURCE_PANE=w1:p1",
        ])

    def test_codex_uses_the_same_popup_and_only_passes_the_pane(self):
        recorder = self.run_action(agent_get(agent="codex"), support.ok({"type": "ok"}))
        self.assertEqual(self.exit_code, 0)
        self.assertEqual(recorder.calls, [
            ["agent", "get", "w1:p1"],
            ["plugin", "pane", "open", "--plugin", "my-herdr", "--entrypoint", "fork-prompt",
             "--env", "MH_SOURCE_PANE=w1:p1"],
        ])

    def test_a_pane_that_cannot_be_forked_never_opens_the_popup(self):
        # Refuse before anything is typed, not after.
        for answer in (agent_get(agent="gemini"), agent_get(agent_session={}),
                       support.failure("agent_not_found")):
            recorder = support.Recorder(answer)
            with self.assertRaises(MyHerdrError):
                with mock.patch.dict("os.environ", ENV, clear=True):
                    with mock.patch.object(herdr, "run", recorder):
                        fork_tab_ask.main([])
            self.assertEqual(recorder.commands, ["agent get w1:p1"])

    def test_an_unsaved_conversation_never_opens_the_popup(self):
        # Asking for a name for a fork that cannot happen wastes the typing.
        import shutil
        import tempfile
        home = tempfile.mkdtemp(prefix="my-herdr-test-")
        self.addCleanup(shutil.rmtree, home, True)
        os.makedirs(os.path.join(home, ".claude", "projects", "-home-user-project"))
        recorder = support.Recorder(agent_get())
        with self.assertRaises(MyHerdrError):
            with mock.patch.dict("os.environ", dict(ENV, HOME=home), clear=True):
                with mock.patch.object(herdr, "run", recorder):
                    fork_tab_ask.main([])
        self.assertEqual(recorder.commands, ["agent get w1:p1"])

    def test_a_busy_popup_slot_is_reported(self):
        # Only one popup at a time; herdr answers ui_busy.
        with self.assertRaises(MyHerdrError):
            self.run_action(agent_get(), support.failure("ui_busy", "a popup pane is already open"))


class PopupTest(unittest.TestCase):
    """The popup's own logic, with the prompt stubbed and herdr recorded."""

    def setUp(self):
        self.state = tempfile.mkdtemp(prefix="my-herdr-test-")
        self.addCleanup(shutil.rmtree, self.state, True)

    def run_popup(self, answer, env=None, *answers):
        """Run the popup with a simulated answer and record its action invocation.

        Args:
            answer: Tab-name string, an empty string for no name, or None to cancel.
            env: Dictionary of string environment overrides; None uses popup defaults.
            *answers: Completed CLI results to replay; omitted answers default to success.

        Returns:
            Recorder containing CLI calls; self.exit_code holds the popup's result.

        Raises:
            MyHerdrError: Saving the request or invoking fork-tab fails.
        """
        recorder = support.Recorder(*(answers or (support.ok({"type": "ok"}),)))
        env = dict({"MH_SOURCE_PANE": "w1:p1", "HERDR_PLUGIN_CONTEXT_JSON": "{}",
                    "HERDR_PLUGIN_ID": "my-herdr", "HERDR_PLUGIN_STATE_DIR": self.state},
                   **(env or {}))
        with mock.patch.dict("os.environ", env, clear=True):
            with mock.patch.object(prompt, "ask", return_value=answer):
                with mock.patch.object(herdr, "run", recorder):
                    with mock.patch("sys.stdout", io.StringIO()):
                        self.exit_code = fork_prompt.main([])
        return recorder

    def pending(self):
        """Consume and return the pending pane_id/name request dict, or None."""
        return fork_request.take(self.state)

    def test_a_name_is_left_for_fork_tab_which_herdr_then_runs(self):
        recorder = self.run_popup("spike")
        self.assertEqual(self.exit_code, 0)
        self.assertEqual(recorder.commands, ["plugin action invoke my-herdr.fork-tab"])
        self.assertEqual(self.pending(), {"pane_id": "w1:p1", "name": "spike"})

    def test_the_popup_starts_no_process_of_its_own(self):
        # herdr launches the fork; nothing may run outside its view.
        with mock.patch("subprocess.Popen") as popen:
            self.run_popup("spike")
        popen.assert_not_called()

    def test_an_empty_name_still_requests_an_unnamed_fork_of_the_source_pane(self):
        self.run_popup("")
        self.assertEqual(self.pending(), {"pane_id": "w1:p1", "name": None})

    def test_surrounding_whitespace_is_not_part_of_the_name(self):
        self.run_popup("  spike  ")
        self.assertEqual(self.pending()["name"], "spike")
        self.run_popup("   ")
        self.assertIsNone(self.pending()["name"])

    def test_a_name_with_quotes_dollars_and_dashes_survives_the_hand_off(self):
        name = "it's \"$HOME\" -- & more\u00e9"
        self.run_popup(name)
        self.assertEqual(self.pending()["name"], name)

    def test_cancel_requests_nothing(self):
        recorder = self.run_popup(None)
        self.assertEqual(self.exit_code, 0)
        self.assertEqual(recorder.commands, [])
        self.assertIsNone(self.pending())

    def test_a_failed_invoke_withdraws_the_request(self):
        # Otherwise the next plain fork-tab could pick up this name.
        with self.assertRaises(MyHerdrError):
            self.run_popup("spike", None, support.failure("plugin_not_found"))
        self.assertEqual(os.listdir(self.state), [])

    def test_the_source_pane_falls_back_to_the_context(self):
        self.run_popup("x", {
            "MH_SOURCE_PANE": "",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps({"focused_pane_id": "w2:p4"}),
        })
        self.assertEqual(self.pending()["pane_id"], "w2:p4")

    def test_no_source_pane_at_all_is_an_error(self):
        with self.assertRaises(MyHerdrError):
            self.run_popup("x", {"MH_SOURCE_PANE": ""})

    def test_no_state_directory_is_an_error_before_anything_is_invoked(self):
        # Invoking anyway would fork the right pane but silently drop the name.
        with mock.patch.object(herdr, "run") as run:
            with self.assertRaises(MyHerdrError):
                with mock.patch.dict("os.environ", {"MH_SOURCE_PANE": "w1:p1"}, clear=True):
                    with mock.patch.object(prompt, "ask", return_value="x"):
                        with mock.patch("sys.stdout", io.StringIO()):
                            fork_prompt.main([])
        run.assert_not_called()

    def test_the_popup_errors_wait_for_enter(self):
        # A popup vanishes when its process exits, so an error must hold it.
        err = io.StringIO()
        with mock.patch.dict("os.environ", {"HERDR_PLUGIN_CONTEXT_JSON": "{}"}, clear=True):
            with mock.patch("sys.stdin", io.StringIO("\n")), mock.patch("sys.stderr", err):
                with mock.patch("sys.stdout", io.StringIO()):
                    self.assertEqual(cli.main(["pane", "fork-prompt"]), cli.EXIT_ERROR)
        self.assertIn("press Enter", err.getvalue())


class ForkTabRequestTest(unittest.TestCase):
    """fork-tab with and without a request waiting for it."""

    def setUp(self):
        self.state = tempfile.mkdtemp(prefix="my-herdr-test-")
        self.addCleanup(shutil.rmtree, self.state, True)
        self.env = dict(ENV, HERDR_PLUGIN_STATE_DIR=self.state)

    def run_fork_tab(self):
        """Run fork-tab against the test request store and return its mocked fork call."""
        with mock.patch.dict("os.environ", self.env, clear=True):
            with mock.patch.object(fork_tab.workflow, "fork_into_new_tab",
                                   return_value={"tab_id": "w1:t9", "pane_id": "w1:p9"}) as run:
                with mock.patch("sys.stdout", io.StringIO()):
                    fork_tab.main([])
        return run

    def test_a_request_decides_the_pane_and_the_name(self):
        fork_request.save(self.state, "w2:p4", "spike")
        self.run_fork_tab().assert_called_once_with("w2:p4", name="spike")

    def test_without_a_request_it_forks_the_focused_pane_unnamed(self):
        self.run_fork_tab().assert_called_once_with("w1:p1", name=None)

    def test_a_request_is_used_once(self):
        fork_request.save(self.state, "w2:p4", "spike")
        self.run_fork_tab()
        self.run_fork_tab().assert_called_once_with("w1:p1", name=None)

    def test_a_stale_request_is_ignored(self):
        fork_request.save(self.state, "w2:p4", "spike",
                          now=time.time() - fork_request.REQUEST_TTL - 1)
        self.run_fork_tab().assert_called_once_with("w1:p1", name=None)
        self.assertEqual(os.listdir(self.state), [])


class EndToEndTest(support.EndToEndCase):
    def test_the_action_opens_the_popup(self):
        result = self.invoke("fork-tab-ask", env=ENV)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_commands(), [
            "agent get w1:p1",
            "plugin pane open --plugin my-herdr --entrypoint fork-prompt "
            "--env MH_SOURCE_PANE=w1:p1",
        ])

    def test_the_popup_leaves_a_request_and_invokes_fork_tab(self):
        # Popups get no HERDR_PANE_ID. The fake herdr does not run the action
        # it is asked to invoke; the next test plays herdr's part.
        result = self.invoke("pane", "fork-prompt", stdin="spike\n", env={
            "MH_SOURCE_PANE": "w1:p1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
            "HERDR_PLUGIN_ENTRYPOINT_ID": "fork-prompt",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_commands(), ["plugin action invoke my-herdr.fork-tab"])
        with open(os.path.join(self.tmp, fork_request.FILE_NAME)) as handle:
            request = json.load(handle)
        self.assertEqual((request["pane_id"], request["name"]), ("w1:p1", "spike"))

    def test_fork_tab_takes_the_request_as_herdr_would_run_it(self):
        fork_request.save(self.tmp, "w1:p1", "spike")
        result = self.invoke("fork-tab", env=dict(ENV, CLAUDE_CONFIG_DIR=None))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("named 'spike'", result.stdout)
        commands = self.herdr_commands()
        self.assertIn("tab create --workspace w1 --cwd /home/user/project --label spike --focus",
                      commands)
        self.assertTrue(any(c.endswith("--fork-session -n spike") for c in commands), commands)
        self.assertEqual(commands[-1], "agent rename w1:p9 --clear")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, fork_request.FILE_NAME)))

    def test_cancelling_the_popup_touches_nothing(self):
        result = self.invoke("pane", "fork-prompt", stdin="", env={
            "MH_SOURCE_PANE": "w1:p1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_commands(), [])
        self.assertEqual([f for f in os.listdir(self.tmp) if f.startswith("fork-")], [])


if __name__ == "__main__":
    unittest.main()
