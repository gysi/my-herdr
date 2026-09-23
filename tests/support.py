"""Shared test helpers.

Importing this puts the plugin root on sys.path, because `unittest discover -s
tests` only adds `tests/` itself. Every test module imports it first.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
MOCK = os.path.join(TESTS, "mocks", "herdr")
FIXTURES = os.path.join(TESTS, "fixtures")
DISPATCHER = os.path.join(ROOT, "bin", "my-herdr")

#: A HOME with nothing in it, so no test reads the real ~/.claude of whoever
#: runs the suite. Unit tests put it in the environment they patch in.
NO_HOME = os.path.join(TESTS, "no-such-home")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def completed(stdout="", stderr="", returncode=0):
    """Build a process result for mocking myherdr.herdr.run().

    Args:
        stdout (str): Captured standard output, empty by default.
        stderr (str): Captured standard error, empty by default.
        returncode (int): Process exit code, default 0 for success.

    Returns:
        subprocess.CompletedProcess: Fake herdr result with the supplied output.
    """
    return subprocess.CompletedProcess(
        args=["herdr"], returncode=returncode, stdout=stdout, stderr=stderr)


def ok(result):
    """Build a successful herdr response with JSON on stdout.

    Args:
        result (dict): Payload to place inside the response's ``result`` field.

    Returns:
        subprocess.CompletedProcess: Exit 0 with the encoded success envelope.
    """
    return completed(stdout=json.dumps({"id": "cli:test", "result": result}))


def failure(code, message="boom"):
    """Build a failed herdr response with JSON on stderr.

    Args:
        code (str): Structured herdr error code to simulate.
        message (str): User-facing error text, default "boom".

    Returns:
        subprocess.CompletedProcess: Exit 1 with the encoded error envelope.
    """
    return completed(
        stderr=json.dumps({"error": {"code": code, "message": message}, "id": "cli:test"}),
        returncode=1)


class Recorder(object):
    """Replacement for myherdr.herdr.run that records argv and replays answers.

    Answers are consumed in order; when they run out the last one repeats, so a
    test that only cares about the first call stays short.
    """

    def __init__(self, *answers):
        """Set up ordered fake responses and an empty command log.

        Args:
            *answers (subprocess.CompletedProcess): Responses to replay; the
                final one repeats. No answers defaults to an empty success.
        """
        self.answers = list(answers) or [ok({})]
        self.calls = []

    def __call__(self, *args, **kwargs):
        """Record one CLI call and return its configured response.

        Args:
            *args (object): CLI arguments, converted to strings for recording.
            **kwargs (object): run() options accepted for compatibility and ignored.

        Returns:
            subprocess.CompletedProcess: Next answer, or the repeated final answer.
        """
        self.calls.append([str(a) for a in args])
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    @property
    def commands(self):
        """Return recorded calls as a list of space-joined command strings."""
        return [" ".join(call) for call in self.calls]


class EndToEndCase(unittest.TestCase):
    """Runs bin/my-herdr as a real process against the fake herdr CLI.

    Covers what in-process tests cannot: the shebang, sys.path setup, exit
    codes, and the exact argv that would reach a real herdr.
    """

    def setUp(self):
        """Create a temporary state directory and mock log, with automatic cleanup."""
        self.tmp = tempfile.mkdtemp(prefix="my-herdr-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = os.path.join(self.tmp, "herdr.log")

    def invoke(self, *args, **kwargs):
        """Run the dispatcher against mock herdr in an isolated test environment.

        Args:
            *args (object): Dispatcher arguments, converted to strings.
            **kwargs (object): Optional ``env`` mapping of overrides (None values
                remove variables) and ``stdin`` text (default empty). Remaining
                options, such as ``cwd``, are forwarded to subprocess.run().

        Returns:
            subprocess.CompletedProcess: Dispatcher exit status and captured text.

        Raises:
            subprocess.TimeoutExpired: The test process exceeds 30 seconds.
            OSError: The dispatcher cannot be started.
        """
        env = dict(os.environ)
        # Inherited herdr variables would leak a live session into the test
        # (for example when the suite runs inside a herdr pane), so start clean.
        # Agent config and popup variables must not read a developer's stores either.
        for key in list(env):
            if key.startswith(("HERDR_", "MH_")) or key in ("CODEX_HOME", "CLAUDE_CONFIG_DIR"):
                del env[key]
        env.update({
            "HERDR_BIN_PATH": MOCK,
            "HERDR_MOCK_LOG": self.log,
            "HERDR_MOCK_DIR": FIXTURES,
            "HERDR_ENV": "1",
            "HERDR_PLUGIN_ID": "my-herdr",
            "HERDR_PLUGIN_ROOT": ROOT,
            "HERDR_PLUGIN_STATE_DIR": self.tmp,
            # A fresh home per test: nothing of the developer's leaks in, and a
            # test can build a Claude store under it (see claude_store()).
            "HOME": os.path.join(self.tmp, "home"),
            "XDG_CONFIG_HOME": os.path.join(self.tmp, "config"),
            "XDG_STATE_HOME": os.path.join(self.tmp, "state"),
        })
        # A value of None removes the variable, so a test can assert on what
        # happens without one even if the developer's own shell exports it.
        for key, value in kwargs.pop("env", {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return subprocess.run(
            [sys.executable, DISPATCHER] + [str(a) for a in args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, env=env, timeout=30,
            input=kwargs.pop("stdin", ""), **kwargs)

    def claude_store(self, *session_ids):
        """Create a Claude store under the test HOME with empty transcript files.

        Args:
            *session_ids (str): IDs to save. No IDs creates an empty project store.

        Raises:
            OSError: The project directory exists already or files cannot be created.
        """
        project = os.path.join(self.tmp, "home", ".claude", "projects", "-home-user-project")
        os.makedirs(project)
        for session_id in session_ids:
            open(os.path.join(project, session_id + ".jsonl"), "w").close()

    def herdr_calls(self):
        """Return recorded mock calls as list[list[str]], or [] if no log exists."""
        try:
            with open(self.log) as handle:
                return [json.loads(line) for line in handle if line.strip()]
        except IOError:
            return []

    def herdr_commands(self):
        """Return mock calls as space-joined strings for readable assertions."""
        return [" ".join(call) for call in self.herdr_calls()]
