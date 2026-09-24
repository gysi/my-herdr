"""Dispatcher routing and the one place MyHerdrError is turned into feedback."""
import io
import sys
import unittest
from unittest import mock

from myherdr import cli
from myherdr.shared import herdr
from myherdr.shared.errors import MyHerdrError


class CapturedStreams(object):
    """Collects stdout/stderr so a failing dispatch does not spam the test run."""

    def __enter__(self):
        """Replace stdout/stderr with text buffers and return this capture object."""
        self.out, self.err = io.StringIO(), io.StringIO()
        self._saved = (sys.stdout, sys.stderr)
        sys.stdout, sys.stderr = self.out, self.err
        return self

    def __exit__(self, *exc):
        """Restore the original streams without suppressing exceptions.

        Args:
            *exc: Exception type, value, and traceback supplied by the with statement.

        Returns:
            False, allowing any exception to propagate.
        """
        sys.stdout, sys.stderr = self._saved
        return False


class RoutingTest(unittest.TestCase):
    def test_routes_an_action_to_its_module(self):
        module = mock.Mock(main=mock.Mock(return_value=0))
        with mock.patch("importlib.import_module", return_value=module) as imported:
            with CapturedStreams():
                self.assertEqual(cli.main(["ping", "--extra"]), 0)
        imported.assert_called_once_with("myherdr.diagnostics.ping")
        module.main.assert_called_once_with(["--extra"])

    def test_routes_a_pane_entrypoint(self):
        module = mock.Mock(main=mock.Mock(return_value=0))
        with mock.patch("importlib.import_module", return_value=module) as imported:
            with CapturedStreams():
                cli.main(["pane", "fork-prompt"])
        imported.assert_called_once_with("myherdr.forking.popup")

    def test_public_id_routes_to_its_feature_module(self):
        # The public ID is independent of the implementation module name.
        module = mock.Mock(main=mock.Mock(return_value=0))
        with mock.patch("importlib.import_module", return_value=module) as imported:
            with CapturedStreams():
                cli.main(["attention-next"])
        imported.assert_called_once_with("myherdr.attention.next")

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
            """Simulate a dependency import failure inside an action module.

            Args:
                name: Requested module name; ignored by this stub.

            Raises:
                ImportError: Always, naming the missing dependency.
            """
            raise ImportError("No module named 'nonexistent_dependency'",
                              name="nonexistent_dependency")

        with mock.patch("importlib.import_module", explode):
            with self.assertRaises(ImportError):
                cli.main(["ping"])

    def test_unknown_entrypoints_do_not_attempt_import(self):
        for argv in (["nope"], ["pane", "nope"], ["pane", "ping"], ["fork-prompt"]):
            with self.subTest(argv=argv), mock.patch("importlib.import_module") as imported:
                with CapturedStreams():
                    self.assertEqual(cli.main(argv), cli.EXIT_USAGE)
                imported.assert_not_called()

    def test_missing_registered_module_is_not_hidden(self):
        with mock.patch("importlib.import_module", side_effect=ModuleNotFoundError(
                "missing registered target", name="myherdr.diagnostics.ping")):
            with self.assertRaises(ModuleNotFoundError):
                cli.main(["ping"])


class ErrorReportingTest(unittest.TestCase):
    def failing_module(self, message="it broke"):
        """Build an action module that raises a user-facing error.

        Args:
            message: Error text raised by the entrypoint; defaults to "it broke".

        Returns:
            Mock module exposing a main(args) entrypoint.
        """
        def main(args):
            """Raise the configured action error.

            Args:
                args: Dispatcher argument list; ignored by this stub.

            Raises:
                MyHerdrError: Always, with the configured message.
            """
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
                        self.assertEqual(cli.main(["pane", "fork-prompt"]), cli.EXIT_ERROR)
        notify.assert_not_called()
        self.assertIn("press Enter", streams.err.getvalue())
        self.assertEqual(stdin.read(), "", "must consume the keypress")

    def test_cancelling_a_popup_is_not_a_failure(self):
        # Ctrl-C / Ctrl-D in a prompt means "never mind", not an error.
        def cancel(args):
            """Simulate cancellation of a popup.

            Args:
                args: Dispatcher argument list; ignored by this stub.

            Raises:
                KeyboardInterrupt: Always, simulating Ctrl-C.
            """
            raise KeyboardInterrupt()

        with mock.patch("importlib.import_module", return_value=mock.Mock(main=cancel)):
            with CapturedStreams():
                self.assertEqual(cli.main(["pane", "fork-prompt"]), cli.EXIT_OK)

    def test_interrupting_an_action_reports_the_signal(self):
        def cancel(args):
            """Simulate interruption of an action.

            Args:
                args: Dispatcher argument list; ignored by this stub.

            Raises:
                KeyboardInterrupt: Always, simulating Ctrl-C.
            """
            raise KeyboardInterrupt()

        with mock.patch("importlib.import_module", return_value=mock.Mock(main=cancel)):
            with CapturedStreams():
                self.assertEqual(cli.main(["ping"]), cli.EXIT_INTERRUPTED)


class AvailableTest(unittest.TestCase):
    def test_lists_registered_manifest_ids(self):
        self.assertIn("ping", cli.available("actions"))
        self.assertNotIn("__init__", cli.available("actions"))

    def test_unknown_registry_section_is_empty(self):
        self.assertEqual(cli.available("nothing-here"), [])


if __name__ == "__main__":
    unittest.main()
