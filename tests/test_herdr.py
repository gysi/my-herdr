"""The herdr CLI wrapper: envelope parsing, error mapping, helpers."""
import subprocess
import unittest
from unittest import mock

import support  # noqa: F401  (puts the plugin root on sys.path)

from myherdr import herdr
from myherdr.errors import MyHerdrError


class BinPathTest(unittest.TestCase):
    def test_prefers_the_injected_binary(self):
        # herdr injects the path of the *running* server binary, which is not
        # necessarily the herdr on PATH.
        with mock.patch.dict("os.environ", {"HERDR_BIN_PATH": "/opt/herdr/bin/herdr"}):
            self.assertEqual(herdr.bin_path(), "/opt/herdr/bin/herdr")

    def test_falls_back_to_path_lookup(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(herdr.bin_path(), "herdr")


class RunTest(unittest.TestCase):
    """The subprocess layer itself, below the seam the other tests patch."""

    def test_builds_argv_without_a_shell(self):
        with mock.patch("subprocess.run", return_value=support.completed()) as spawned:
            with mock.patch.dict("os.environ", {"HERDR_BIN_PATH": "/opt/herdr"}):
                herdr.run("tab", "create", "--label", "a b")
        self.assertEqual(spawned.call_args[0][0],
                         ["/opt/herdr", "tab", "create", "--label", "a b"])

    def test_an_unusable_binary_is_a_clear_error(self):
        # Missing, or present but not executable: both land here.
        for exc in (FileNotFoundError(2, "No such file"), PermissionError(13, "Permission denied")):
            with mock.patch("subprocess.run", side_effect=exc):
                with self.assertRaises(MyHerdrError) as caught:
                    herdr.run("agent", "list")
            self.assertIn("HERDR_BIN_PATH", str(caught.exception))

    def test_a_hung_call_becomes_an_error_not_a_hang(self):
        # A plugin action has no timeout of its own: it would hold a
        # concurrency slot forever.
        with mock.patch("subprocess.run",
                        side_effect=subprocess.TimeoutExpired("herdr", 30)):
            with self.assertRaises(MyHerdrError) as caught:
                herdr.run("agent", "start", "x")
        self.assertIn("timed out", str(caught.exception))

    def test_rejects_unknown_keywords(self):
        with self.assertRaises(TypeError):
            herdr.run("agent", "list", verbose=True)


class RunJsonTest(unittest.TestCase):
    def test_returns_the_result_object(self):
        recorder = support.Recorder(support.ok({"pane": {"pane_id": "w1:p1"}}))
        with mock.patch.object(herdr, "run", recorder):
            result = herdr.run_json("pane", "current")
        self.assertEqual(result, {"pane": {"pane_id": "w1:p1"}})
        self.assertEqual(recorder.commands, ["pane current"])

    def test_passes_arguments_as_separate_argv_items(self):
        # The whole point of argv lists: a label with spaces and quotes must
        # survive without any shell quoting.
        recorder = support.Recorder(support.ok({}))
        with mock.patch.object(herdr, "run", recorder):
            herdr.run_json("tab", "create", "--label", 'a "b" $c')
        self.assertEqual(recorder.calls[0][-1], 'a "b" $c')

    def test_raises_with_the_cli_message_and_code(self):
        recorder = support.Recorder(support.failure("pane_not_found", "pane w9:p9 not found"))
        with mock.patch.object(herdr, "run", recorder):
            with self.assertRaises(MyHerdrError) as caught:
                herdr.run_json("pane", "get", "w9:p9")
        self.assertEqual(str(caught.exception), "pane w9:p9 not found")
        self.assertEqual(caught.exception.code, "pane_not_found")

    def test_usage_errors_are_not_json(self):
        # herdr exits 2 with a plain usage block; the message must still be useful.
        recorder = support.Recorder(support.completed(
            stderr="usage: herdr pane move <pane_id> --tab <tab_id>", returncode=2))
        with mock.patch.object(herdr, "run", recorder):
            with self.assertRaises(MyHerdrError) as caught:
                herdr.run_json("pane", "move", "--bogus")
        self.assertIn("exit 2", str(caught.exception))
        self.assertIn("usage: herdr pane move", str(caught.exception))
        self.assertIsNone(caught.exception.code)

    def test_unparsable_output_is_an_error_not_a_crash(self):
        recorder = support.Recorder(support.completed(stdout="not json at all"))
        with mock.patch.object(herdr, "run", recorder):
            with self.assertRaises(MyHerdrError) as caught:
                herdr.run_json("agent", "list")
        self.assertIn("unparsable", str(caught.exception))

    def test_envelope_without_result_is_an_error(self):
        recorder = support.Recorder(support.completed(stdout='{"id":"cli:x"}'))
        with mock.patch.object(herdr, "run", recorder):
            with self.assertRaises(MyHerdrError):
                herdr.run_json("agent", "list")


class TryJsonTest(unittest.TestCase):
    def test_swallows_failures(self):
        recorder = support.Recorder(support.failure("not_found"))
        with mock.patch.object(herdr, "run", recorder):
            self.assertIsNone(herdr.try_json("pane", "current"))


class NotifyTest(unittest.TestCase):
    def test_sends_a_toast(self):
        recorder = support.Recorder(support.ok({"type": "notification_show"}))
        with mock.patch.object(herdr, "run", recorder):
            herdr.notify("something broke", sound="request")
        self.assertEqual(
            recorder.calls[0],
            ["notification", "show", "my-herdr", "--body", "something broke",
             "--sound", "request"])

    def test_truncates_to_herdr_limits(self):
        recorder = support.Recorder(support.ok({}))
        with mock.patch.object(herdr, "run", recorder):
            herdr.notify("x" * 500)
        body = recorder.calls[0][recorder.calls[0].index("--body") + 1]
        self.assertLessEqual(len(body), herdr.BODY_MAX)

    def test_a_failing_toast_never_raises(self):
        # notify() reports other failures; it must not become one itself.
        def explode(*args, **kwargs):
            """Simulate a failure while delivering a notification.

            Args:
                *args: CLI arguments accepted for compatibility and ignored.
                **kwargs: Wrapper options accepted for compatibility and ignored.

            Raises:
                MyHerdrError: Always, simulating an unavailable herdr executable.
            """
            raise MyHerdrError("herdr CLI not found")

        with mock.patch.object(herdr, "run", explode):
            herdr.notify("still fine")


class FocusedPaneTest(unittest.TestCase):
    def test_prefers_the_context(self):
        class Ctx(object):
            pane_id = "w1:p7"

        recorder = support.Recorder(support.ok({}))
        with mock.patch.object(herdr, "run", recorder):
            self.assertEqual(herdr.focused_pane(Ctx()), "w1:p7")
        self.assertEqual(recorder.calls, [], "must not ask the server when it already knows")

    def test_asks_the_server_when_the_context_is_empty(self):
        class Ctx(object):
            pane_id = None

        recorder = support.Recorder(support.ok({"pane": {"pane_id": "w1:p3"}}))
        with mock.patch.object(herdr, "run", recorder):
            self.assertEqual(herdr.focused_pane(Ctx()), "w1:p3")
        self.assertEqual(recorder.commands, ["pane current"])

    def test_raises_when_nothing_is_focused(self):
        recorder = support.Recorder(support.ok({}))
        with mock.patch.object(herdr, "run", recorder):
            with self.assertRaises(MyHerdrError):
                herdr.focused_pane(None)


def process_info(foreground, shell_pid=100):
    """Build a successful process-info response for shell readiness tests.

    Args:
        foreground: List of foreground process dictionaries with pid and name fields.
        shell_pid: Integer PID identifying the pane's shell; defaults to 100.

    Returns:
        Completed subprocess result with a JSON process_info envelope on stdout.
    """
    return support.ok({"process_info": {
        "foreground_processes": foreground, "shell_pid": shell_pid}})


class WaitShellReadyTest(unittest.TestCase):
    def test_ready_when_only_the_shell_runs(self):
        recorder = support.Recorder(process_info([{"pid": 100, "name": "bash"}]))
        with mock.patch.object(herdr, "run", recorder):
            self.assertTrue(herdr.wait_shell_ready("w1:p9", sleep=lambda _: None))

    def test_ready_when_the_shell_is_named_but_has_another_pid(self):
        # A login shell may not be the recorded shell_pid; the name settles it.
        recorder = support.Recorder(process_info([{"pid": 222, "name": "zsh"}]))
        with mock.patch.object(herdr, "run", recorder):
            self.assertTrue(herdr.wait_shell_ready("w1:p9", sleep=lambda _: None))

    def test_not_ready_while_a_command_runs(self):
        # `agent start` would fail here, so we must keep waiting.
        recorder = support.Recorder(process_info([{"pid": 500, "name": "npm"}]))
        with mock.patch.object(herdr, "run", recorder):
            self.assertFalse(
                herdr.wait_shell_ready("w1:p9", timeout=0.0, sleep=lambda _: None))

    def test_becomes_ready_after_polling(self):
        recorder = support.Recorder(
            process_info([{"pid": 500, "name": "npm"}]),
            process_info([{"pid": 100, "name": "bash"}]))
        with mock.patch.object(herdr, "run", recorder):
            self.assertTrue(herdr.wait_shell_ready("w1:p9", sleep=lambda _: None))
        self.assertEqual(len(recorder.calls), 2)

    def test_a_degraded_server_is_not_ready(self):
        recorder = support.Recorder(support.failure("pane_not_found"))
        with mock.patch.object(herdr, "run", recorder):
            self.assertFalse(
                herdr.wait_shell_ready("w1:p9", timeout=0.0, sleep=lambda _: None))


if __name__ == "__main__":
    unittest.main()
