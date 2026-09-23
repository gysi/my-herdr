"""Runs bin/my-herdr as a real process against the fake herdr CLI.

What only this level can catch: the shebang and sys.path wiring, the exit codes
herdr records in the plugin log, and the exact argv a real herdr would receive.
"""
import json
import os
import unittest

import support

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


class DispatcherTest(support.EndToEndCase):
    def test_unknown_action_exits_two(self):
        result = self.invoke("does-not-exist")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown action", result.stderr)

    def test_help_lists_the_actions(self):
        result = self.invoke("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("ping", result.stdout)

    def test_runs_from_any_working_directory(self):
        # A pane opened with --cwd does not start in the plugin root, so the
        # dispatcher must locate the package relative to itself.
        result = self.invoke("ping", cwd=os.path.dirname(support.ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)


class MockTest(support.EndToEndCase):
    """The fake herdr itself, so a broken mock cannot fake a passing suite."""

    def herdr(self, *args, **env):
        """Run the mock CLI with convenient positional arguments.

        Args:
            *args: String CLI arguments after the executable name.
            **env: String environment overrides, such as HERDR_MOCK_FAIL.

        Returns:
            Completed subprocess result with captured text output.
        """
        return self.invoke_mock(args, env)

    def invoke_mock(self, args, env):
        """Run the mock CLI using this test's fixture directory and call log.

        Args:
            args: Sequence of string CLI arguments after the executable name.
            env: Dictionary of string overrides for the subprocess environment.

        Returns:
            Completed subprocess result with stdout, stderr, and exit status.

        Raises:
            OSError: The subprocess cannot be started.
            subprocess.TimeoutExpired: The mock exceeds the 30-second timeout.
        """
        import subprocess
        import sys
        environ = dict(os.environ, HERDR_MOCK_LOG=self.log, HERDR_MOCK_DIR=support.FIXTURES)
        environ.update(env)
        return subprocess.run([sys.executable, support.MOCK] + list(args),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, env=environ, timeout=30)

    def test_serves_a_fixture(self):
        result = self.herdr("pane", "current")
        self.assertEqual(json.loads(result.stdout)["result"]["pane"]["pane_id"], "w1:p1")

    def test_logs_every_argument(self):
        self.herdr("tab", "create", "--label", "a b")
        self.assertEqual(self.herdr_calls(), [["tab", "create", "--label", "a b"]])

    def test_mutations_answer_ok_without_a_fixture(self):
        result = self.herdr("agent", "focus", "w1:p2")
        self.assertEqual(json.loads(result.stdout)["result"], {"type": "ok"})

    def test_reads_without_a_fixture_answer_empty(self):
        result = self.herdr("workspace", "list")
        self.assertEqual(json.loads(result.stdout)["result"], {})

    def test_failures_look_like_herdr_failures(self):
        result = self.herdr("agent", "get", "w1:p1",
                            HERDR_MOCK_FAIL="agent get:agent_not_found:no agent")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["error"]["code"], "agent_not_found")
        self.assertEqual(result.stdout, "", "errors belong on stderr, like the real CLI")

    def test_failures_only_match_their_own_command(self):
        result = self.herdr("pane", "current", HERDR_MOCK_FAIL="agent get:agent_not_found")
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
