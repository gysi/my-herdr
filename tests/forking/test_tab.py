"""fork-tab: the argv sent, and what happens when the fork does not come up."""
import json
import unittest
from unittest import mock

from tests import support  # noqa: F401

from myherdr.forking import workflow as fork
from myherdr.shared import herdr
from myherdr.forking import tab as fork_tab
from myherdr.shared.errors import MyHerdrError

CONTEXT = {
    "workspace_id": "w1",
    "tab_id": "w1:t1",
    "focused_pane_id": "w1:p1",
    "invocation_source": "keybinding",
}

#: What `agent get` says about a forkable pane.
AGENT = {
    "agent": "claude",
    "agent_session": {"agent": "claude", "kind": "id", "source": "herdr:claude",
                      "value": "11111111-2222-3333-4444-555555555555"},
    "agent_status": "idle",
    "cwd": "/home/user/project",
    "foreground_cwd": "/home/user/project",
    "pane_id": "w1:p1",
    "tab_id": "w1:t1",
    "workspace_id": "w1",
}

TAB_CREATED = {
    "tab": {"tab_id": "w1:t9", "workspace_id": "w1", "label": "", "pane_count": 1},
    "root_pane": {"pane_id": "w1:p9", "tab_id": "w1:t9", "workspace_id": "w1"},
    "type": "tab_created",
}

SID = AGENT["agent_session"]["value"]


def agent_get(kind="claude", **overrides):
    """Build an agent-info CLI response from the default forkable pane.

    Args:
        kind: Agent kind string used for pane and session metadata; defaults to claude.
        **overrides: Agent fields to replace after setting the kind and session metadata.

    Returns:
        Completed subprocess result containing a JSON agent_info envelope.
    """
    agent = dict(AGENT, agent=kind,
                 agent_session=dict(AGENT["agent_session"], agent=kind, source="herdr:" + kind))
    agent.update(overrides)
    return support.ok({"agent": agent, "type": "agent_info"})


class ForkTest(unittest.TestCase):
    """The routine itself, with the shell-readiness poll stubbed out.

    `wait_shell_ready` has its own tests in test_herdr.py; leaving it in here
    would bury the argv sequence under process-info polls.
    """

    def setUp(self):
        self.env = {
            "HOME": support.NO_HOME,
            "HERDR_PANE_ID": "w1:p1",
            "HERDR_TAB_ID": "w1:t1",
            "HERDR_WORKSPACE_ID": "w1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
        }

    def run_fork(self, *answers, **kwargs):
        """Run fork-tab with mocked CLI responses and shell readiness.

        Args:
            *answers: Completed subprocess results to replay in call order.
            **kwargs: Optional ready boolean (default True) for the readiness poll and
                env dictionary overriding the isolated environment. None env values
                remove variables. Other keys are ignored.

        Returns:
            Recorder containing CLI calls; self.exit_code holds the action's result.

        Raises:
            MyHerdrError: Validation, tab creation, readiness, or agent startup fails.
        """
        recorder = support.Recorder(*answers)
        ready = kwargs.pop("ready", True)
        env = dict(self.env)
        for key, value in kwargs.pop("env", {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        with mock.patch.dict("os.environ", env, clear=True):
            with mock.patch.object(herdr, "run", recorder):
                with mock.patch.object(herdr, "wait_shell_ready", return_value=ready):
                    self.exit_code = fork_tab.main([])
        return recorder

    def test_the_whole_sequence_for_a_forkable_pane(self):
        recorder = self.run_fork(agent_get(), support.ok(TAB_CREATED), support.ok({}))
        self.assertEqual(self.exit_code, 0)
        self.assertEqual(recorder.commands, [
            "agent get w1:p1",
            "tab create --workspace w1 --cwd /home/user/project --focus",
            "agent start %s --kind claude --pane w1:p9 --timeout 60000 "
            "-- --resume %s --fork-session" % (fork.temp_agent_name(), SID),
            "agent rename w1:p9 --clear",
        ])

    def test_the_new_tab_is_focused_immediately_not_once_the_fork_is_up(self):
        # Waiting would show the old pane for as long as Claude takes to
        # replay the session, which reads as lag. Focus is not gated on
        # readiness; only `agent start` cares whether the shell is idle.
        recorder = self.run_fork(agent_get(), support.ok(TAB_CREATED), support.ok({}))
        self.assertIn("--focus", recorder.calls[1])
        self.assertNotIn("--no-focus", recorder.calls[1])
        self.assertNotIn("tab focus w1:t9", recorder.commands)

    def test_no_name_means_no_label_and_no_session_name(self):
        # An unnamed tab keeps herdr's generic name, so tab-renaming plugins
        # and Claude's own title still manage it.
        recorder = self.run_fork(agent_get(), support.ok(TAB_CREATED), support.ok({}))
        self.assertNotIn("--label", recorder.calls[1])
        self.assertNotIn("-n", recorder.calls[2])

    def test_the_forks_directory_is_the_agents_foreground_directory(self):
        # Claude keys sessions by project directory: start the fork elsewhere
        # and `--resume` finds nothing.
        recorder = self.run_fork(
            agent_get(foreground_cwd="/home/user/project/sub"),
            support.ok(TAB_CREATED), support.ok({}))
        self.assertIn("--cwd", recorder.calls[1])
        self.assertEqual(recorder.calls[1][recorder.calls[1].index("--cwd") + 1],
                         "/home/user/project/sub")

    def test_the_pane_cwd_is_used_when_there_is_no_foreground_cwd(self):
        recorder = self.run_fork(
            agent_get(foreground_cwd=None), support.ok(TAB_CREATED), support.ok({}))
        self.assertIn("/home/user/project", recorder.calls[1])

    def test_the_tab_lands_in_the_source_panes_workspace(self):
        recorder = self.run_fork(
            agent_get(workspace_id="w3"), support.ok(TAB_CREATED), support.ok({}))
        self.assertEqual(recorder.calls[1][:4], ["tab", "create", "--workspace", "w3"])

    def test_codex_named_and_unnamed_forks_use_exact_argv_and_only_codex_environment(self):
        for name in (None, "", "it's \"$HOME\" -- & moreé"):
            for foreground_cwd in (None, "/home/user/project/sub dir"):
                with self.subTest(name=name, cwd=foreground_cwd):
                    recorder = support.Recorder(
                        agent_get("codex", foreground_cwd=foreground_cwd, workspace_id="w3"),
                        support.ok(TAB_CREATED), support.ok({}))
                    with mock.patch.object(herdr, "run", recorder):
                        with mock.patch.object(herdr, "wait_shell_ready", return_value=True):
                            result = fork.fork_into_new_tab("w1:p1", name, env={
                                "CODEX_HOME": "/home/user/codex alt",
                                "CLAUDE_CONFIG_DIR": "/home/user/claude-alt",
                            })
                    label = ["--label", name] if name else []
                    self.assertEqual(recorder.calls, [
                        ["agent", "get", "w1:p1"],
                        ["tab", "create", "--workspace", "w3", "--cwd",
                         foreground_cwd or AGENT["cwd"]] + label +
                        ["--env", "CODEX_HOME=/home/user/codex alt", "--focus"],
                        ["agent", "start", fork.temp_agent_name(), "--kind", "codex",
                         "--pane", "w1:p9", "--timeout", "60000", "--", "fork", SID],
                        ["agent", "rename", "w1:p9", "--clear"],
                    ])
                    self.assertEqual(result, {"tab_id": "w1:t9", "pane_id": "w1:p9"})

    # -- refusals ---------------------------------------------------------

    def test_a_pane_without_an_agent_is_refused_before_anything_is_created(self):
        recorder = support.Recorder(support.failure("agent_not_found"))
        with self.assertRaises(MyHerdrError) as caught:
            with mock.patch.dict("os.environ", self.env, clear=True):
                with mock.patch.object(herdr, "run", recorder):
                    fork_tab.main([])
        self.assertIn("no agent", str(caught.exception))
        self.assertEqual(recorder.commands, ["agent get w1:p1"])

    def test_an_unsupported_agent_says_so(self):
        recorder = support.Recorder(agent_get(agent="gemini"))
        with self.assertRaises(MyHerdrError) as caught:
            with mock.patch.dict("os.environ", self.env, clear=True):
                with mock.patch.object(herdr, "run", recorder):
                    fork_tab.main([])
        self.assertIn("gemini", str(caught.exception))
        self.assertEqual(len(recorder.commands), 1)

    def test_a_missing_session_id_points_at_the_claude_integration(self):
        # Without the hook herdr never learns the session id, and there is
        # nothing to resume.
        for session in ({}, {"kind": "path", "value": "/tmp/x"}, {"kind": "id", "value": ""}):
            recorder = support.Recorder(agent_get(agent_session=session))
            with self.assertRaises(MyHerdrError) as caught:
                with mock.patch.dict("os.environ", self.env, clear=True):
                    with mock.patch.object(herdr, "run", recorder):
                        fork_tab.main([])
            self.assertIn("herdr integration install claude", str(caught.exception))
            self.assertEqual(len(recorder.commands), 1)

    # -- cleanup ----------------------------------------------------------

    def test_the_tab_is_closed_when_the_agent_does_not_come_up(self):
        for kind in ("claude", "codex"):
            with self.subTest(kind=kind):
                recorder = support.Recorder(
                    agent_get(kind), support.ok(TAB_CREATED),
                    support.failure("agent_start_failed", "%s never appeared" % kind))
                with self.assertRaises(MyHerdrError) as caught:
                    with mock.patch.dict("os.environ", self.env, clear=True):
                        with mock.patch.object(herdr, "run", recorder):
                            with mock.patch.object(herdr, "wait_shell_ready", return_value=True):
                                fork_tab.main([])
                self.assertIn("%s never appeared" % kind, str(caught.exception))
                # The tab goes, and focus comes back to where the key was pressed:
                # closing the focused tab would otherwise drop us on a random one.
                self.assertEqual(recorder.commands[-2:],
                                 ["tab close w1:t9", "agent focus w1:p1"])
                self.assertNotIn("agent rename w1:p9 --clear", recorder.commands)

    def test_a_shell_that_never_settles_closes_the_tab_without_starting_anything(self):
        for kind in ("claude", "codex"):
            with self.subTest(kind=kind):
                recorder = support.Recorder(agent_get(kind), support.ok(TAB_CREATED))
                with self.assertRaises(MyHerdrError) as caught:
                    with mock.patch.dict("os.environ", self.env, clear=True):
                        with mock.patch.object(herdr, "run", recorder):
                            with mock.patch.object(herdr, "wait_shell_ready", return_value=False):
                                fork_tab.main([])
                self.assertIn("did not reach a prompt", str(caught.exception))
                self.assertEqual(recorder.commands, [
                    "agent get w1:p1",
                    "tab create --workspace w1 --cwd /home/user/project --focus",
                    "tab close w1:t9",
                    "agent focus w1:p1",
                ])

    def test_a_tab_created_without_a_pane_is_closed_again(self):
        recorder = support.Recorder(
            agent_get(), support.ok({"tab": {"tab_id": "w1:t9"}}))
        with self.assertRaises(MyHerdrError):
            with mock.patch.dict("os.environ", self.env, clear=True):
                with mock.patch.object(herdr, "run", recorder):
                    fork_tab.main([])
        self.assertEqual(recorder.commands[-2:],
                         ["tab close w1:t9", "agent focus w1:p1"])

    def test_an_interrupt_mid_start_still_closes_the_tab(self):
        calls = []

        def run(*args, **kwargs):
            """Record CLI calls and simulate interruption during agent startup.

            Args:
                *args: CLI arguments to record and match against fixture responses.
                **kwargs: Wrapper options accepted for compatibility and ignored.

            Returns:
                Completed subprocess result for agent lookup, tab creation, or cleanup.

            Raises:
                KeyboardInterrupt: The command starts an agent.
            """
            calls.append([str(a) for a in args])
            if args[:2] == ("agent", "start"):
                raise KeyboardInterrupt
            return {"agent get": agent_get(),
                    "tab create": support.ok(TAB_CREATED)}.get(
                        " ".join(str(a) for a in args[:2]), support.ok({}))

        with self.assertRaises(KeyboardInterrupt):
            with mock.patch.dict("os.environ", self.env, clear=True):
                with mock.patch.object(herdr, "run", run):
                    with mock.patch.object(herdr, "wait_shell_ready", return_value=True):
                        fork_tab.main([])
        self.assertEqual([" ".join(c) for c in calls][-2:],
                         ["tab close w1:t9", "agent focus w1:p1"])


class ArgumentTest(unittest.TestCase):
    """A named fork, as the fork-prompt popup requests it."""

    def test_a_name_labels_the_tab_and_names_the_session(self):
        self.assertEqual(
            fork.tab_create_args("w1", "/p", "spike", env={}),
            ["tab", "create", "--workspace", "w1", "--cwd", "/p", "--label", "spike",
             "--focus"])
        self.assertEqual(
            fork.agent_start_args("w1:p9", SID, "spike"),
            ["agent", "start", fork.temp_agent_name(), "--kind", "claude", "--pane", "w1:p9",
             "--timeout", "60000", "--", "--resume", SID, "--fork-session", "-n", "spike"])

    def test_a_name_is_one_argument_however_it_is_written(self):
        # argv lists mean no shell is involved, so quotes, `$` and spaces
        # travel as themselves. Asserted rather than assumed.
        name = "it's \"$HOME\" & more"
        args = fork.agent_start_args("w1:p9", SID, name)
        self.assertEqual(args[-2:], ["-n", name])

    def test_claude_config_dir_is_forwarded_when_set(self):
        # Plugin commands inherit herdr's server environment, not the shell the
        # source agent was launched from, so it has to be passed explicitly.
        args = fork.tab_create_args("w1", "/p", env={"CLAUDE_CONFIG_DIR": "/home/user/.claude-alt"})
        self.assertIn("--env", args)
        self.assertEqual(args[args.index("--env") + 1], "CLAUDE_CONFIG_DIR=/home/user/.claude-alt")

    def test_nothing_is_forwarded_when_nothing_is_set(self):
        self.assertNotIn("--env", fork.tab_create_args("w1", "/p", env={"PATH": "/usr/bin"}))
        self.assertNotIn("--env", fork.tab_create_args("w1", "/p", env={"CLAUDE_CONFIG_DIR": ""}))

    def test_the_temporary_agent_name_matches_herdrs_rule(self):
        self.assertRegex(fork.temp_agent_name(), r"^[a-z][a-z0-9_-]{0,31}$")

    def test_abandoning_nothing_does_nothing(self):
        with mock.patch.object(herdr, "run") as run:
            fork.abandon(None, None)
        run.assert_not_called()


class EndToEndTest(support.EndToEndCase):
    def test_forks_the_pane_and_reports_the_new_tab(self):
        result = self.invoke("fork-tab", env={
            "HERDR_PANE_ID": "w1:p1",
            "HERDR_TAB_ID": "w1:t1",
            "HERDR_WORKSPACE_ID": "w1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
            "CLAUDE_CONFIG_DIR": None,
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.herdr_commands()
        self.assertEqual(commands[0], "agent get w1:p1")
        self.assertEqual(commands[1],
                         "tab create --workspace w1 --cwd /home/user/project --focus")
        # The fixtures' new pane is w1:p9, and its shell is idle, so the real
        # readiness poll runs here rather than being stubbed.
        self.assertEqual(commands[2], "pane process-info --pane w1:p9")
        self.assertTrue(commands[3].startswith("agent start "))
        self.assertIn("--resume %s --fork-session" % SID, commands[3])
        self.assertEqual(commands[-1], "agent rename w1:p9 --clear")
        self.assertIn("w1:t9", result.stdout)

    def test_a_fork_that_will_not_start_is_toasted_and_the_tab_closed(self):
        result = self.invoke("fork-tab", env={
            "HERDR_PANE_ID": "w1:p1",
            "HERDR_WORKSPACE_ID": "w1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
            "HERDR_MOCK_FAIL": "agent start:agent_start_failed:claude did not start",
        })
        self.assertEqual(result.returncode, 1)
        self.assertIn("claude did not start", result.stderr)
        commands = self.herdr_commands()
        self.assertIn("tab close w1:t9", commands)
        self.assertIn("agent focus w1:p1", commands)
        self.assertTrue(commands[-1].startswith("notification show"))

    def test_a_pane_without_a_claude_session_never_creates_a_tab(self):
        result = self.invoke("fork-tab", env={
            "HERDR_PANE_ID": "w1:p1",
            "HERDR_WORKSPACE_ID": "w1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
            "HERDR_MOCK_FAIL": "agent get:agent_not_found:no agent here",
        })
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("tab create", " ".join(self.herdr_commands()))
        self.assertIn("no agent", result.stderr)

    def test_a_saved_conversation_is_forked(self):
        self.claude_store(SID)
        result = self.invoke("fork-tab", env={
            "HERDR_PANE_ID": "w1:p1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
            "CLAUDE_CONFIG_DIR": None,
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("agent rename w1:p9 --clear", self.herdr_commands())
        # The plugin log names the pane and the id herdr holds for it.
        self.assertIn("fork: w1:p1 runs claude session %s (saved conversation: yes" % SID,
                      result.stdout)

    def test_an_unsaved_conversation_is_refused_at_once_without_a_tab(self):
        self.claude_store("another-session")
        result = self.invoke("fork-tab", env={
            "HERDR_PANE_ID": "w1:p1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
            "CLAUDE_CONFIG_DIR": None,
        })
        self.assertEqual(result.returncode, 1)
        self.assertIn("no saved conversation", result.stderr)
        self.assertIn("fork: w1:p1 runs claude session %s (saved conversation: no" % SID,
                      result.stdout)
        commands = self.herdr_commands()
        self.assertNotIn("tab create", " ".join(commands))
        self.assertTrue(commands[-1].startswith("notification show"))

    def test_claude_config_dir_reaches_the_new_tab(self):
        result = self.invoke("fork-tab", env={
            "HERDR_PANE_ID": "w1:p1",
            "HERDR_WORKSPACE_ID": "w1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
            "CLAUDE_CONFIG_DIR": "/home/user/.claude-alt",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--env CLAUDE_CONFIG_DIR=/home/user/.claude-alt", self.herdr_commands()[1])


if __name__ == "__main__":
    unittest.main()
