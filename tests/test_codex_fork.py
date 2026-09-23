"""Codex forks through the dispatcher, popup handoff and mock herdr CLI."""
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest import mock

import support
from myherdr import fork_request

SID = "11111111-2222-3333-4444-555555555555"
NEW_SID = "66666666-7777-8888-9999-000000000000"


class CodexEndToEndTest(support.EndToEndCase):
    def invoke(self, *args, **kwargs):
        """Invoke the dispatcher using the Codex pane as its default source.

        Args:
            *args: String dispatcher arguments, such as fork-tab or pane fork-prompt.
            **kwargs: Options forwarded to EndToEndCase.invoke, including env overrides
                (None values remove variables), stdin text, and subprocess options.

        Returns:
            Completed subprocess result with captured text output and exit status.
        """
        env = {"HERDR_PANE_ID": "w1:p2"}
        env.update(kwargs.pop("env", {}))
        return super().invoke(*args, env=env, **kwargs)

    def assert_launch(self, session_id=SID):
        """Verify a single Codex fork launch followed by clearing its temporary alias.

        Args:
            session_id: Expected source session ID string; defaults to the fixture's ID.

        Raises:
            AssertionError: The call count, launch arguments, or alias cleanup differ.
        """
        launches = [call for call in self.herdr_calls() if call[:2] == ["agent", "start"]]
        self.assertEqual(len(launches), 1)
        launch = launches[0]
        self.assertRegex(launch[2], r"^mh-fork-[0-9]+$")
        self.assertEqual(launch[:2] + launch[3:], [
            "agent", "start", "--kind", "codex", "--pane", "w1:p9",
            "--timeout", "60000", "--", "fork", session_id,
        ])
        self.assertEqual(self.herdr_calls()[-1], ["agent", "rename", "w1:p9", "--clear"])

    def test_direct_fork_ignores_claude_store_and_inherited_config_overrides(self):
        # An empty Claude store would reject the same ID for a Claude pane.
        self.claude_store("another-session")
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/unexpected/claude",
                                          "CODEX_HOME": "/unexpected/codex"}):
            result = self.invoke("fork-tab")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_calls()[:3], [
            ["agent", "get", "w1:p2"],
            ["tab", "create", "--workspace", "w1", "--cwd", "/home/user/project", "--focus"],
            ["pane", "process-info", "--pane", "w1:p9"],
        ])
        self.assert_launch()
        self.assertIn("fork: w1:p2 runs codex session " + SID, result.stdout)
        self.assertNotIn("saved conversation", result.stdout)
        self.assertIn("w1:t9", result.stdout)

    def test_codex_home_reaches_the_tab_without_claude_config(self):
        result = self.invoke("fork-tab", env={
            "CODEX_HOME": "/home/user/codex alt",
            "CLAUDE_CONFIG_DIR": "/home/user/claude-alt",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_calls()[1], [
            "tab", "create", "--workspace", "w1", "--cwd", "/home/user/project",
            "--env", "CODEX_HOME=/home/user/codex alt", "--focus",
        ])
        self.assert_launch()

    def test_named_popup_handoff_rereads_the_agent_and_session(self):
        # Start with Claude; the source switches to Codex while the popup is open.
        result = self.invoke("fork-tab-ask", env={"HERDR_PANE_ID": "w1:p1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        name = "it's \"$HOME\" -- & moreé"
        result = self.invoke("pane", "fork-prompt", stdin=name + "\n", env={
            "HERDR_PANE_ID": None, "MH_SOURCE_PANE": "w1:p1",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Fork this session into a new tab.", result.stdout)
        request_path = Path(self.tmp, fork_request.FILE_NAME)
        request = json.loads(request_path.read_text())
        self.assertEqual(set(request), {"pane_id", "name", "written_at"})
        self.assertEqual(request["name"], name)
        self.assertFalse(any(call[:2] == ["agent", "start"] for call in self.herdr_calls()))
        fixtures = Path(self.tmp, "fixtures")
        shutil.copytree(support.FIXTURES, fixtures)
        agent = json.loads(Path(fixtures, "agent_get_w1_p2.json").read_text())
        agent["result"]["agent"]["pane_id"] = "w1:p1"
        agent["result"]["agent"]["agent_session"]["value"] = NEW_SID
        Path(fixtures, "agent_get.json").write_text(json.dumps(agent))
        # Focus has moved; the request still names the original pane.
        result = self.invoke("fork-tab", env={"HERDR_MOCK_DIR": str(fixtures)})
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.herdr_calls()
        self.assertEqual(calls[2], ["plugin", "action", "invoke", "my-herdr.fork-tab"])
        self.assertEqual(calls[3], ["agent", "get", "w1:p1"])
        self.assertEqual(calls[4], [
            "tab", "create", "--workspace", "w1", "--cwd", "/home/user/project",
            "--label", name, "--focus",
        ])
        self.assert_launch(NEW_SID)
        self.assertFalse(request_path.exists())

    def test_codex_popup_with_empty_name_still_forks(self):
        result = self.invoke("fork-tab-ask")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_calls()[1], [
            "plugin", "pane", "open", "--plugin", "my-herdr", "--entrypoint", "fork-prompt",
            "--env", "MH_SOURCE_PANE=w1:p2",
        ])
        result = self.invoke("pane", "fork-prompt", stdin="\n", env={
            "HERDR_PANE_ID": None, "MH_SOURCE_PANE": "w1:p2",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.invoke("fork-tab")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("--label", self.herdr_calls()[4])
        self.assert_launch()
        self.assertFalse(Path(self.tmp, fork_request.FILE_NAME).exists())

    def test_codex_popup_cancellation_never_dispatches_a_fork(self):
        result = self.invoke("fork-tab-ask")
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.herdr_calls()
        result = self.invoke("pane", "fork-prompt", stdin="", env={
            "HERDR_PANE_ID": None, "MH_SOURCE_PANE": "w1:p2",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_calls(), before)
        self.assertFalse(Path(self.tmp, fork_request.FILE_NAME).exists())

    def test_failed_codex_start_closes_tab_restores_focus_and_toasts(self):
        result = self.invoke("fork-tab", env={
            "HERDR_MOCK_FAIL": "agent start:agent_not_ready:codex startup timed out",
        })
        self.assertEqual(result.returncode, 1)
        self.assertIn("codex startup timed out", result.stderr)
        calls = self.herdr_calls()
        self.assertEqual(calls[-3:-1], [
            ["tab", "close", "w1:t9"], ["agent", "focus", "w1:p2"],
        ])
        self.assertEqual(calls[-1][:2], ["notification", "show"])
        self.assertFalse(any(call[:2] == ["agent", "rename"] for call in calls))


if __name__ == "__main__":
    unittest.main()
