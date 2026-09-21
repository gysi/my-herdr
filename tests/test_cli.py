"""Dispatcher routing and the one place MyHerdrError is turned into feedback."""
import io
import sys
import unittest
from unittest import mock

import support  # noqa: F401  (puts the plugin root on sys.path)

from myherdr import cli, herdr
from myherdr.errors import MyHerdrError


class CapturedStreams(object):
    """Collects stdout/stderr so a failing dispatch does not spam the test run."""

    def __enter__(self):
        self.out, self.err = io.StringIO(), io.StringIO()
        self._saved = (sys.stdout, sys.stderr)
        sys.stdout, sys.stderr = self.out, self.err
        return self

    def __exit__(self, *exc):
        sys.stdout, sys.stderr = self._saved
        return False


class RoutingTest(unittest.TestCase):
    def test_routes_an_action_to_its_module(self):
        module = mock.Mock(main=mock.Mock(return_value=0))
        with mock.patch("importlib.import_module", return_value=module) as imported:
            with CapturedStreams():
                self.assertEqual(cli.main(["ping", "--extra"]), 0)
        imported.assert_called_once_with("myherdr.actions.ping")
        module.main.assert_called_once_with(["--extra"])

    def test_routes_a_pane_entrypoint(self):
        module = mock.Mock(main=mock.Mock(return_value=0))
        with mock.patch("importlib.import_module", return_value=module) as imported:
            with CapturedStreams():
                cli.main(["pane", "fork-prompt"])
        imported.assert_called_once_with("myherdr.panes.fork_prompt")

    def test_dashes_in_ids_map_to_underscores_in_modules(self):
        # Manifest ids may not contain dots and conventionally use dashes;
        # module names cannot.
        module = mock.Mock(main=mock.Mock(return_value=0))
        with mock.patch("importlib.import_module", return_value=module) as imported:
            with CapturedStreams():
                cli.main(["attention-next"])
        imported.assert_called_once_with("myherdr.actions.attention_next")

    def test_a_module_returning_none_still_exits_zero(self):
        module = mock.Mock(main=mock.Mock(return_value=None))
        with mock.patch("importlib.import_module", return_value=module):
            with CapturedStreams():
                self.assertEqual(cli.main(["ping"]), 0)

    def test_unknown_action_is_a_usage_error(self):
        with CapturedStreams() as streams:
            self.assertEqual(cli.main(["nope"]), cli.EXIT_USAGE)
        self.assertIn("unknown action 'nope'", streams.err.getvalue())
        self.assertIn("ping", streams.err.getvalue(), "should list what is available")

    def test_pane_without_an_entrypoint_is_a_usage_error(self):
        with CapturedStreams():
            self.assertEqual(cli.main(["pane"]), cli.EXIT_USAGE)

    def test_no_arguments_is_a_usage_error(self):
        with CapturedStreams():
            self.assertEqual(cli.main([]), cli.EXIT_USAGE)

    def test_help_exits_zero(self):
        with CapturedStreams() as streams:
            self.assertEqual(cli.main(["--help"]), cli.EXIT_OK)
        self.assertIn("usage:", streams.out.getvalue())

    def test_rejects_ids_that_are_not_ids(self):
        # Without this, a crafted id could import an unrelated module.
        for bad in ["../secrets", "os.path", "myherdr.herdr", "-x", ""]:
            with CapturedStreams():
                self.assertEqual(cli.main([bad]), cli.EXIT_USAGE, bad)

    def test_an_import_error_inside_the_module_is_not_hidden(self):
        # A broken import in an action is a bug worth a traceback, not a
        # misleading "unknown action".
        def explode(name):
            raise ImportError("No module named 'nonexistent_dependency'",
                              name="nonexistent_dependency")

        with mock.patch("importlib.import_module", explode):
            with self.assertRaises(ImportError):
                cli.main(["ping"])


class ErrorReportingTest(unittest.TestCase):
    def failing_module(self, message="it broke"):
        def main(args):
            raise MyHerdrError(message)

        return mock.Mock(main=main)

    def test_an_action_error_toasts_and_exits_one(self):
        # An action has no TTY and its stderr only reaches the plugin log, so a
        # toast is the only thing the user will actually see.
        with mock.patch("importlib.import_module", return_value=self.failing_module()):
            with mock.patch.object(herdr, "notify") as notify:
                with CapturedStreams() as streams:
                    self.assertEqual(cli.main(["ping"]), cli.EXIT_ERROR)
        notify.assert_called_once()
        self.assertEqual(notify.call_args[0][0], "it broke")
        self.assertEqual(notify.call_args[1].get("sound"), "request")
        self.assertIn("it broke", streams.err.getvalue())

    def test_a_pane_error_waits_for_enter_instead_of_toasting(self):
        # The popup closes the instant this process exits, so the message has
        # to be held on screen.
        with mock.patch("importlib.import_module", return_value=self.failing_module()):
            with mock.patch.object(herdr, "notify") as notify:
                with mock.patch.object(sys, "stdin", io.StringIO("\n")) as stdin:
                    with CapturedStreams() as streams:
                        self.assertEqual(cli.main(["pane", "prompt"]), cli.EXIT_ERROR)
        notify.assert_not_called()
        self.assertIn("press Enter", streams.err.getvalue())
        self.assertEqual(stdin.read(), "", "must consume the keypress")

    def test_cancelling_a_popup_is_not_a_failure(self):
        # Ctrl-C / Ctrl-D in a prompt means "never mind", not an error.
        def cancel(args):
            raise KeyboardInterrupt()

        with mock.patch("importlib.import_module", return_value=mock.Mock(main=cancel)):
            with CapturedStreams():
                self.assertEqual(cli.main(["pane", "prompt"]), cli.EXIT_OK)

    def test_interrupting_an_action_reports_the_signal(self):
        def cancel(args):
            raise KeyboardInterrupt()

        with mock.patch("importlib.import_module", return_value=mock.Mock(main=cancel)):
            with CapturedStreams():
                self.assertEqual(cli.main(["ping"]), cli.EXIT_INTERRUPTED)


class AvailableTest(unittest.TestCase):
    def test_lists_real_modules_as_manifest_ids(self):
        self.assertIn("ping", cli.available("actions"))
        self.assertNotIn("__init__", cli.available("actions"))

    def test_missing_directory_is_empty(self):
        self.assertEqual(cli.available("nothing-here"), [])


if __name__ == "__main__":
    unittest.main()
