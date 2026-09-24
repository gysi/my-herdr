"""Diagnostic action through the real dispatcher and mock CLI."""
import json

from tests import support

CONTEXT = {
    "workspace_id": "w1",
    "tab_id": "w1:t1",
    "tab_label": "api",
    "focused_pane_id": "w1:p1",
    "focused_pane_cwd": "/home/user/project",
    "focused_pane_agent": "claude",
    "invocation_source": "keybinding",
}


class PingTest(support.EndToEndCase):
    def test_reports_the_environment_and_context(self):
        result = self.invoke("ping", env={
            "HERDR_PANE_ID": "w1:p1",
            "HERDR_TAB_ID": "w1:t1",
            "HERDR_WORKSPACE_ID": "w1",
            "HERDR_PLUGIN_ACTION_ID": "ping",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HERDR_PANE_ID", result.stdout)
        self.assertIn("w1:p1", result.stdout)
        self.assertIn("keybinding", result.stdout)
        # The context JSON is echoed in full, not just listed as a variable.
        self.assertIn('"focused_pane_agent": "claude"', result.stdout)

    def test_talks_to_herdr_through_the_injected_binary(self):
        self.invoke("ping", env={"HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT)})
        self.assertEqual(self.herdr_commands(), ["pane current"])

    def test_survives_a_herdr_that_is_failing(self):
        # ping is a diagnostic: it must still print what it knows when the
        # server refuses to answer.
        result = self.invoke("ping", env={
            "HERDR_MOCK_FAIL": "pane current:server_error:socket closed",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("unavailable", result.stdout)

    def test_survives_a_missing_context(self):
        result = self.invoke("ping")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not running under herdr", result.stdout)

    def test_survives_a_malformed_context(self):
        result = self.invoke("ping", env={"HERDR_PLUGIN_CONTEXT_JSON": "{broken"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("unparsable", result.stdout)


