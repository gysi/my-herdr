"""OpenCode V2 CLI/API validation, independent forks, and dispatcher integration."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from myherdr.forking import opencode, workflow
from myherdr.shared import herdr
from myherdr.shared.errors import MyHerdrError
from tests import support
from .test_tab import TAB_CREATED, agent_get

SOURCE = "ses_source"
FORK = "ses_fork"
DIRECTORY = "/home/user/opencode-project"
NAME = "it's \"$HOME\" -- & moreé"


def output(value):
    """Build a raw OpenCode JSON response, without a herdr result envelope.

    Args:
        value (object): JSON-serializable API response to encode on stdout.

    Returns:
        subprocess.CompletedProcess: Successful process result with JSON stdout.
    """
    return support.completed(stdout=json.dumps(value))


class CliTest(unittest.TestCase):
    def test_command_errors_are_actionable_and_do_not_leak_private_output(self):
        for error in (FileNotFoundError("missing binary"), PermissionError("not executable"),
                      subprocess.TimeoutExpired("opencode", 30)):
            with self.subTest(error=type(error).__name__):
                with mock.patch("subprocess.run", side_effect=error) as spawn:
                    with self.assertRaises(MyHerdrError):
                        opencode.run("--version")
                spawn.assert_called_once()
        proc = support.completed(stdout="private session content", stderr="private password",
                                 returncode=1)
        with mock.patch("subprocess.run", return_value=proc):
            with self.assertRaises(MyHerdrError) as caught:
                opencode.api("post", "/api/session/ses_source/fork", {})
        self.assertIn("shared service", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))

    def test_json_shapes_and_empty_204_are_not_confused_with_herdr_envelopes(self):
        for text in ("not json", "[]", "null", '"text"', "1"):
            with self.subTest(text=text):
                with mock.patch.object(opencode, "run", return_value=support.completed(stdout=text)):
                    with self.assertRaises(MyHerdrError):
                        opencode.api("get", "/api/info")
        with mock.patch.object(opencode, "run", return_value=support.completed()):
            self.assertIsNone(opencode.api("patch", "/api/session/ses_fork", {"title": NAME}))

    def test_session_ids_are_encoded_as_one_path_component(self):
        self.assertEqual(opencode.session_path("ses_a/b ?#%"),
                         "/api/session/ses_a%2Fb%20%3F%23%25")


class ValidationTest(unittest.TestCase):
    def test_v2_prerelease_stable_and_newer_versions_are_accepted(self):
        for version in ("2.0.0-beta.19242", "opencode v2.0.32\n", "v2.1.0+build", "3.0.0",
                        "2.0.0-beta.19242+build"):
            opencode.require_supported_version(version)

    def test_v1_and_unverifiable_versions_are_rejected(self):
        for version in ("1.18.29", "opencode v1.99.0", "dev", "2", "2.0", "", None, 2,
                        "unexpected 2.0.0 output"):
            with self.subTest(version=version):
                with self.assertRaisesRegex(MyHerdrError, "latest release"):
                    opencode.require_supported_version(version)

    def test_validation_checks_both_versions_and_reads_the_exact_source(self):
        recorder = support.Recorder(support.completed(stdout="opencode v2.0.32"),
                                    output({"version": "2.0.32"}),
                                    output({"data": {"id": SOURCE,
                                                     "location": {"directory": DIRECTORY}}}))
        with mock.patch.object(opencode, "run", recorder):
            self.assertEqual(opencode.validate(SOURCE), DIRECTORY)
        self.assertEqual(recorder.calls, [["--version"], ["api", "get", "/api/info"],
                                         ["api", "get", "/api/session/ses_source"]])

    def test_legacy_cli_never_contacts_the_service(self):
        with mock.patch.object(opencode, "run", return_value=support.completed(stdout="1.18.29")) as run:
            with self.assertRaises(MyHerdrError):
                opencode.validate(SOURCE)
        run.assert_called_once_with("--version", timeout=10.0)

    def test_legacy_server_is_rejected_before_session_access(self):
        recorder = support.Recorder(support.completed(stdout="2.0.32"),
                                    output({"version": "1.18.29"}))
        with mock.patch.object(opencode, "run", recorder):
            with self.assertRaises(MyHerdrError):
                opencode.validate(SOURCE)
        self.assertEqual(len(recorder.calls), 2)

    def test_invalid_source_ids_and_locations_fail_closed(self):
        sessions = [None, [], {}, {"id": "ses_other"}, {"id": SOURCE},
                    {"id": SOURCE, "location": []}]
        sessions += [{"id": SOURCE, "location": {"directory": directory}}
                     for directory in (None, "", "relative/project", 1)]
        for session in sessions:
            with self.subTest(session=session):
                with mock.patch.object(opencode, "run", return_value=support.completed(stdout="2.0.32")), \
                     mock.patch.object(opencode, "api", side_effect=[{"version": "2.0.32"},
                                                                    {"data": session}]):
                    with self.assertRaises(MyHerdrError):
                        opencode.validate(SOURCE)


class ForkTest(unittest.TestCase):
    def test_fork_uses_empty_body_and_names_only_the_new_session(self):
        for name in (None, "", NAME):
            with self.subTest(name=name):
                with mock.patch.object(opencode, "api", side_effect=[{"data": {"id": FORK}}, None]) as api, \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(opencode.fork_session(SOURCE, name), FORK)
                expected = [mock.call("post", "/api/session/ses_source/fork", {})]
                if name:
                    expected += [mock.call("patch", "/api/session/ses_fork", {"title": name})]
                self.assertEqual(api.call_args_list, expected)

    def test_missing_or_source_fork_id_is_never_launched_or_renamed(self):
        for response in (None, {}, {"data": []}, {"data": {}}, {"data": {"id": SOURCE}},
                         {"data": {"id": "  "}}, {"data": {"id": 7}}):
            with self.subTest(response=response):
                with mock.patch.object(opencode, "api", return_value=response) as api:
                    with self.assertRaisesRegex(MyHerdrError, "distinct fork"):
                        opencode.fork_session(SOURCE, NAME)
                api.assert_called_once()

    def test_naming_failure_keeps_and_reports_the_saved_fork_without_deletion(self):
        log = io.StringIO()
        with mock.patch.object(opencode, "api", side_effect=[{"data": {"id": FORK}},
                                                            MyHerdrError("failed")]) as api, \
             contextlib.redirect_stdout(log):
            with self.assertRaisesRegex(MyHerdrError, "ses_fork was saved"):
                opencode.fork_session(SOURCE, NAME)
        self.assertIn(FORK, log.getvalue())
        self.assertEqual(api.call_count, 2)
        self.assertFalse(any(call.args[0] == "delete" for call in api.call_args_list))

    def test_workflow_creates_fork_before_tab_and_never_resumes_source(self):
        events = []
        source = json.loads(agent_get("opencode").stdout)["result"]["agent"]
        source["agent_session"]["value"] = SOURCE
        source["opencode_directory"] = DIRECTORY

        def create_fork(session_id, name):
            """Record API fork creation and return the new ID.

            Args:
                session_id (str): Source ID expected from the validated record.
                name (str or None): Requested title forwarded by the workflow.

            Returns:
                str: Synthetic new fork session ID.
            """
            events.append(("fork", session_id, name))
            return FORK

        def respond(*args, **kwargs):
            """Record herdr mutations and return controlled responses.

            Args:
                *args (str): herdr command arguments to record.
                **kwargs (object): Wrapper timeout options, accepted and ignored.

            Returns:
                dict: New tab metadata for creation, otherwise an empty success.
            """
            events.append(args)
            return TAB_CREATED if args[:2] == ("tab", "create") else {}

        with mock.patch.object(workflow.agents, "forkable_agent", return_value=source), \
             mock.patch.object(opencode, "fork_session", side_effect=create_fork), \
             mock.patch.object(herdr, "run_json", side_effect=respond), \
             mock.patch.object(herdr, "wait_shell_ready", return_value=True):
            workflow.fork_into_new_tab("w1:p3", NAME)
        self.assertEqual(events[0], ("fork", SOURCE, NAME))
        self.assertEqual(events[1], ("tab", "create", "--workspace", "w1", "--cwd", DIRECTORY,
                                     "--label", NAME, "--focus"))
        self.assertEqual(events[2][-3:], ("--", "--session", FORK))


class OpenCodeEndToEndTest(support.EndToEndCase):
    def invoke(self, *args, **kwargs):
        """Run the dispatcher using mock OpenCode and its default source pane.

        Args:
            *args (str): Dispatcher arguments, including actions/popup entrypoints.
            **kwargs (object): Options passed to EndToEndCase.invoke, including
                isolated environment overrides and simulated popup stdin.

        Returns:
            subprocess.CompletedProcess: Dispatcher exit status and captured output.
        """
        env = {"HERDR_PANE_ID": "w1:p3"}
        env.update(kwargs.pop("env", {}))
        return super().invoke(*args, env=env, **kwargs)

    def opencode_calls(self):
        """Read the argv lists recorded by the mock OpenCode CLI.

        Returns:
            list[list[str]]: One argv list per OpenCode call in call order, or an
            empty list when OpenCode was never called.
        """
        path = Path(self.tmp, "opencode.log")
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def assert_launch(self):
        """Assert a single OpenCode launch resumes only the new fork and clears its alias.

        Raises:
            AssertionError: The launch argv or alias cleanup differs from the contract.
        """
        launches = [call for call in self.herdr_calls() if call[:2] == ["agent", "start"]]
        self.assertEqual(len(launches), 1)
        self.assertEqual(launches[0][:2] + launches[0][3:], [
            "agent", "start", "--kind", "opencode", "--pane", "w1:p9", "--timeout", "60000",
            "--", "--session", FORK])
        self.assertEqual(self.herdr_calls()[-1], ["agent", "rename", "w1:p9", "--clear"])

    def test_direct_fork_uses_v2_api_and_authoritative_session_directory(self):
        self.claude_store("another-session")
        result = self.invoke("fork-tab", env={"OPENCODE_PASSWORD": "secret"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.opencode_calls(), [["--version"], ["api", "get", "/api/info"],
                         ["api", "get", "/api/session/ses_source"],
                         ["api", "post", "/api/session/ses_source/fork", "--data", "{}"]])
        self.assertEqual(self.herdr_calls()[1], ["tab", "create", "--workspace", "w1", "--cwd",
                                               DIRECTORY, "--focus"])
        self.assert_launch()
        self.assertIn("saved OpenCode session " + FORK, result.stdout)
        self.assertNotIn("secret", result.stdout + result.stderr + repr(self.herdr_calls()))

    def test_named_popup_revalidates_source_and_names_only_new_fork(self):
        result = self.invoke("fork-tab-ask")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.opencode_calls()), 3)
        self.assertEqual(self.herdr_calls()[-1], [
            "plugin", "pane", "open", "--plugin", "my-herdr", "--entrypoint", "fork-prompt",
            "--env", "MH_SOURCE_PANE=w1:p3"])
        result = self.invoke("pane", "fork-prompt", stdin=NAME + "\n", env={
            "HERDR_PANE_ID": None, "MH_SOURCE_PANE": "w1:p3"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.opencode_calls()), 3, "popup must not do slow/API work")
        result = self.invoke("fork-tab", env={"HERDR_PANE_ID": "w1:p1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.herdr_calls()[3], ["agent", "get", "w1:p3"])
        self.assertEqual(self.opencode_calls()[3:6], self.opencode_calls()[:3])
        self.assertEqual(self.opencode_calls()[-1], [
            "api", "patch", "/api/session/ses_fork", "--data", json.dumps({"title": NAME})])
        self.assertIn("--label", self.herdr_calls()[4])
        self.assertEqual(self.herdr_calls()[4][-3:], ["--label", NAME, "--focus"])
        self.assert_launch()

    def test_popup_cancellation_never_calls_fork_api(self):
        result = self.invoke("fork-tab-ask")
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.opencode_calls()
        result = self.invoke("pane", "fork-prompt", stdin="", env={
            "HERDR_PANE_ID": None, "MH_SOURCE_PANE": "w1:p3"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.opencode_calls(), before)
        self.assertFalse(Path(self.tmp, "fork-request.json").exists())

    def test_session_switch_while_naming_forks_the_current_reported_session(self):
        result = self.invoke("fork-tab-ask")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.invoke("pane", "fork-prompt", stdin=NAME + "\n", env={
            "HERDR_PANE_ID": None, "MH_SOURCE_PANE": "w1:p3"})
        self.assertEqual(result.returncode, 0, result.stderr)
        fixtures = Path(self.tmp, "fixtures")
        fixtures.mkdir()
        source = json.loads(Path(support.FIXTURES, "agent_get_w1_p3.json").read_text())
        source["result"]["agent"]["agent_session"]["value"] = "ses_selected_later"
        Path(fixtures, "agent_get_w1_p3.json").write_text(json.dumps(source))
        # Other herdr responses use the standard fixtures; only the source read changes.
        for name in ("tab_create.json", "pane_process_info.json"):
            fixture = Path(support.FIXTURES, name)
            Path(fixtures, name).write_text(fixture.read_text())
        result = self.invoke("fork-tab", env={"HERDR_PANE_ID": "w1:p1",
                                              "HERDR_MOCK_DIR": str(fixtures)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["api", "post", "/api/session/ses_selected_later/fork", "--data", "{}"],
                      self.opencode_calls())
        self.assertFalse(any(call[:3] == ["api", "post", "/api/session/ses_source/fork"]
                             for call in self.opencode_calls()))
        self.assert_launch()

    def test_empty_popup_name_keeps_default_tab_and_session_naming(self):
        result = self.invoke("pane", "fork-prompt", stdin="\n", env={"MH_SOURCE_PANE": "w1:p3"})
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.invoke("fork-tab")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(call[:2] == ["api", "patch"] for call in self.opencode_calls()))
        self.assertFalse(any("--label" in call for call in self.herdr_calls()))
        self.assert_launch()

    def test_v1_cli_and_v1_server_are_refused_before_popup_or_tab(self):
        for key in ("OPENCODE_MOCK_VERSION", "OPENCODE_MOCK_SERVER_VERSION"):
            for action in ("fork-tab", "fork-tab-ask"):
                with self.subTest(key=key, action=action):
                    result = self.invoke(action, env={key: "1.18.29"})
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("latest release", result.stderr)
        self.assertFalse(any(call[:2] in (["tab", "create"], ["plugin", "pane"])
                             for call in self.herdr_calls()))
        self.assertFalse(any(call[:2] == ["api", "post"] for call in self.opencode_calls()))

    def test_source_lookup_failures_are_toasted_before_any_ui(self):
        for failure in ("api get /api/info", "api get /api/session/ses_source"):
            result = self.invoke("fork-tab-ask", env={"OPENCODE_MOCK_FAIL": failure})
            self.assertEqual(result.returncode, 1)
            self.assertIn("shared service", result.stderr)
            self.assertNotIn("private failure text", result.stderr)
            self.assertEqual(self.herdr_calls()[-1][:2], ["notification", "show"])
        self.assertFalse(any(call[:2] == ["plugin", "pane"] for call in self.herdr_calls()))

    def test_failed_fork_is_not_retried_and_never_creates_tab(self):
        result = self.invoke("fork-tab", env={"OPENCODE_MOCK_FAIL": "api post"})
        self.assertEqual(result.returncode, 1)
        self.assertEqual(sum(call[:2] == ["api", "post"] for call in self.opencode_calls()), 1)
        self.assertFalse(any(call[:2] == ["tab", "create"] for call in self.herdr_calls()))

    def test_malformed_api_response_or_source_id_as_fork_never_launches(self):
        for response in ("not json", "[]", "null", "", '{"data":{"id":"ses_source"}}'):
            result = self.invoke("fork-tab", env={"OPENCODE_MOCK_MATCH": "api post",
                                                  "OPENCODE_MOCK_RESPONSE": response})
            self.assertEqual(result.returncode, 1, response)
        self.assertFalse(any(call[:2] == ["agent", "start"] for call in self.herdr_calls()))
        self.assertFalse(any(call[:2] == ["tab", "create"] for call in self.herdr_calls()))

    def test_failed_start_closes_tab_and_preserves_saved_fork(self):
        result = self.invoke("fork-tab", env={"HERDR_MOCK_FAIL": "agent start:startup_failed:failed"})
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.herdr_calls()[-3:-1], [["tab", "close", "w1:t9"],
                                                   ["agent", "focus", "w1:p3"]])
        self.assert_resume_hint_toasted()
        self.assertFalse(any(call[:2] == ["api", "delete"] for call in self.opencode_calls()))

    def test_failed_naming_reports_saved_fork_without_tab_or_retry(self):
        result = self.invoke("pane", "fork-prompt", stdin=NAME + "\n", env={"MH_SOURCE_PANE": "w1:p3"})
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.invoke("fork-tab", env={"OPENCODE_MOCK_FAIL": "api patch"})
        self.assertEqual(result.returncode, 1)
        self.assert_resume_hint_toasted()
        self.assertEqual(sum(call[:2] == ["api", "patch"] for call in self.opencode_calls()), 1)
        self.assertFalse(any(call[:2] == ["tab", "create"] for call in self.herdr_calls()))
        self.assertFalse(any(call[:2] == ["api", "delete"] for call in self.opencode_calls()))

    def test_failed_tab_creation_keeps_saved_fork_without_closing_other_tabs(self):
        result = self.invoke("fork-tab", env={"HERDR_MOCK_FAIL": "tab create:creation_failed:failed"})
        self.assertEqual(result.returncode, 1)
        self.assert_resume_hint_toasted()
        self.assertFalse(any(call[:2] == ["tab", "close"] for call in self.herdr_calls()))
        self.assertFalse(any(call[:2] == ["api", "delete"] for call in self.opencode_calls()))

    def assert_resume_hint_toasted(self):
        """Assert the failure toast names the saved fork and how to resume it.

        Raises:
            AssertionError: The last herdr call is not a notification containing
                the resume command for the saved fork.
        """
        toast = self.herdr_calls()[-1]
        self.assertEqual(toast[:2], ["notification", "show"])
        self.assertTrue(any("opencode --session %s" % FORK in arg for arg in toast), toast)
