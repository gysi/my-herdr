"""Agent-specific session validation and fork arguments."""
import io
import os
import unittest
from unittest import mock

import support
from myherdr import fork_agents, herdr
from myherdr.actions import fork_tab, fork_tab_ask
from myherdr.errors import MyHerdrError
from test_fork_tab import AGENT, SID, agent_get


class ValidationTest(unittest.TestCase):
    def test_both_actions_refuse_unusable_sessions_before_opening_any_ui(self):
        invalid = [None, {}, [], "bad", {"kind": "path", "value": "/tmp/session"}]
        invalid += [{"kind": "id", "value": value}
                    for value in (None, "", "  ", 1, True, [], {})]
        for kind in ("claude", "codex"):
            for session in invalid:
                for action in (fork_tab, fork_tab_ask):
                    with self.subTest(kind=kind, session=session, action=action.__name__):
                        recorder = support.Recorder(agent_get(kind, agent_session=session))
                        with mock.patch.dict(os.environ, {"HERDR_PANE_ID": "w1:p1"}, clear=True):
                            with mock.patch.object(herdr, "run", recorder):
                                with self.assertRaises(MyHerdrError) as caught:
                                    action.main([])
                        self.assertIn("herdr integration install " + kind, str(caught.exception))
                        self.assertIn("this pane", str(caught.exception))
                        self.assertEqual(recorder.calls, [["agent", "get", "w1:p1"]])

    def test_conflicting_session_agent_is_refused_by_both_actions(self):
        for kind, other in (("claude", "codex"), ("codex", "claude")):
            for action in (fork_tab, fork_tab_ask):
                with self.subTest(kind=kind, action=action.__name__):
                    session = dict(AGENT["agent_session"], agent=other)
                    recorder = support.Recorder(agent_get(kind, agent_session=session))
                    with mock.patch.dict(os.environ, {"HERDR_PANE_ID": "w1:p1"}, clear=True):
                        with mock.patch.object(herdr, "run", recorder):
                            with self.assertRaises(MyHerdrError) as caught:
                                action.main([])
                    self.assertIn("reports a %s session for the %s pane" % (other, kind),
                                  str(caught.exception))
                    self.assertEqual(recorder.calls, [["agent", "get", "w1:p1"]])

    def test_optional_agent_metadata_is_not_required(self):
        for kind in ("claude", "codex"):
            for extra in ({}, {"agent": None}, {"agent": kind}):
                with self.subTest(kind=kind, extra=extra):
                    session = dict(kind="id", value=SID, **extra)
                    with mock.patch.object(herdr, "run", support.Recorder(
                            agent_get(kind, agent_session=session))):
                        agent = fork_agents.forkable_agent("w1:p1", env={"HOME": support.NO_HOME})
                    self.assertEqual(agent["agent"], kind)

    def test_codex_never_checks_claude_storage_or_claims_to_have_checked_its_own(self):
        output = io.StringIO()
        with mock.patch.object(herdr, "run", support.Recorder(agent_get("codex"))):
            with mock.patch.object(fork_agents, "conversation_saved") as saved:
                with mock.patch.object(fork_agents, "claude_config_dir") as config:
                    with mock.patch("sys.stdout", output):
                        fork_agents.forkable_agent("w1:p1")
        saved.assert_not_called()
        config.assert_not_called()
        self.assertEqual(output.getvalue(), "fork: w1:p1 runs codex session %s\n" % SID)


class ArgumentTest(unittest.TestCase):
    def test_claude_arguments_and_codex_arguments_with_or_without_name(self):
        for name in (None, "", "it's \"$HOME\" -- & moreé"):
            with self.subTest(name=name):
                self.assertEqual(fork_agents.fork_args("codex", SID, name), ["fork", SID])
                self.assertEqual(fork_agents.fork_args("claude", SID, name),
                                 ["--resume", SID, "--fork-session"] +
                                 (["-n", name] if name else []))

    def test_only_the_matching_agents_store_is_forwarded(self):
        env = {"CLAUDE_CONFIG_DIR": "/claude alt", "CODEX_HOME": "/codex alt", "PATH": "/bin"}
        for kind, key in (("claude", "CLAUDE_CONFIG_DIR"), ("codex", "CODEX_HOME")):
            with self.subTest(kind=kind):
                self.assertEqual(fork_agents.forwarded_env(kind, env), {key: env[key]})
                with mock.patch.dict(os.environ, env, clear=True):
                    self.assertEqual(fork_agents.forwarded_env(kind), {key: env[key]})
                self.assertEqual(fork_agents.forwarded_env(kind, {}), {})
                self.assertEqual(fork_agents.forwarded_env(kind, {key: ""}), {})

    def test_unknown_agent_is_never_launched_as_claude(self):
        with self.assertRaises(MyHerdrError):
            fork_agents.fork_args("gemini", SID)
        with self.assertRaises(MyHerdrError):
            fork_agents.forwarded_env("gemini", {})


class SavedConversationTest(unittest.TestCase):
    """The check that the session has something for `--resume` to load."""

    def setUp(self):
        import shutil
        import tempfile
        self.home = tempfile.mkdtemp(prefix="my-herdr-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.projects = os.path.join(self.home, ".claude", "projects")

    def save(self, session_id, root=None):
        """Create an empty transcript file in a synthetic Claude project directory.

        Args:
            session_id: String session ID used as the transcript filename stem.
            root: Projects directory path; None or an empty string uses self.projects.

        Raises:
            OSError: The directory or transcript file cannot be created.
        """
        project = os.path.join(root or self.projects, "-home-user-project")
        if not os.path.isdir(project):
            os.makedirs(project)
        open(os.path.join(project, session_id + ".jsonl"), "w").close()

    def test_a_saved_conversation_is_found_in_any_project(self):
        self.save(SID)
        self.assertIs(fork_agents.conversation_saved(SID, {"HOME": self.home}), True)

    def test_an_unsaved_one_is_not(self):
        # A session forked before its first message, or an id herdr kept
        # from before a resume: Claude has nothing under that name.
        self.save("another-session")
        self.assertIs(fork_agents.conversation_saved(SID, {"HOME": self.home}), False)

    def test_no_store_at_all_means_cannot_tell(self):
        # Refusing on a guess could block a fork that would have worked.
        self.assertIsNone(fork_agents.conversation_saved(SID, {"HOME": self.home}))

    def test_claude_config_dir_is_where_it_looks(self):
        # The same directory the fork's `claude --resume` will read.
        alt = os.path.join(self.home, "alt")
        self.save(SID, os.path.join(alt, "projects"))
        self.assertIs(fork_agents.conversation_saved(
            SID, {"HOME": self.home, "CLAUDE_CONFIG_DIR": alt}), True)
        os.makedirs(self.projects)
        self.assertIs(fork_agents.conversation_saved(SID, {"HOME": self.home}), False)

    def test_glob_characters_in_an_id_match_only_themselves(self):
        self.save("abc")
        self.assertIs(fork_agents.conversation_saved("*", {"HOME": self.home}), False)
        self.assertIs(fork_agents.conversation_saved("[a]bc", {"HOME": self.home}), False)

    def test_an_unsaved_session_is_refused_before_any_tab_exists(self):
        self.save("another-session")
        recorder = support.Recorder(agent_get())
        with self.assertRaises(MyHerdrError) as caught:
            with mock.patch.dict("os.environ", {"HOME": self.home, "HERDR_PANE_ID": "w1:p1"},
                                 clear=True):
                with mock.patch.object(herdr, "run", recorder):
                    fork_tab.main([])
        self.assertIn("no saved conversation", str(caught.exception))
        self.assertEqual(recorder.commands, ["agent get w1:p1"])


if __name__ == "__main__":
    unittest.main()
