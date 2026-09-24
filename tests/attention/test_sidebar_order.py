"""Local sidebar preference and configuration discovery, without live herdr."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from myherdr.attention import sidebar_order


class SortModeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"HOME": self.tmp.name, "HERDR_SOCKET_PATH": "/run/herdr/test.sock"}
        self.config = Path(self.tmp.name, ".config/herdr/config.toml")
        self.config.parent.mkdir(parents=True)
        self.preferences = Path(sidebar_order.preference_path(self.env))
        self.preferences.parent.mkdir(parents=True)

    def test_default_and_configured_sort(self):
        self.assertEqual(sidebar_order.sort_mode(self.env), "spaces")
        self.config.write_text('[ui]\nagent_panel_sort = "priority"\n')
        self.assertEqual(sidebar_order.sort_mode(self.env), "priority")

    def test_preferences_override_config_and_are_reread(self):
        self.config.write_text('[ui]\nagent_panel_sort = "priority"\n')
        for saved, expected in [("spaces", "spaces"), ("priority", "priority"),
                                ("workspaces", "spaces"), (None, "priority")]:
            self.preferences.write_text(json.dumps({"agent_panel_sort": saved}))
            self.assertEqual(sidebar_order.sort_mode(self.env), expected)

    def test_other_session_preferences_are_not_used(self):
        self.preferences.write_text('{"agent_panel_sort":"priority"}')
        other = dict(self.env, HERDR_SOCKET_PATH="/run/herdr/another.sock")
        self.assertNotEqual(sidebar_order.preference_path(other), str(self.preferences))
        self.assertEqual(sidebar_order.sort_mode(other), "spaces")

    def test_xdg_paths_and_explicit_config_path(self):
        env = dict(self.env, XDG_STATE_HOME=os.path.join(self.tmp.name, "state"),
                   XDG_CONFIG_HOME=os.path.join(self.tmp.name, "config"))
        self.assertTrue(sidebar_order.preference_path(env).startswith(env["XDG_STATE_HOME"]))
        config = Path(env["XDG_CONFIG_HOME"], "herdr/config.toml")
        config.parent.mkdir(parents=True)
        config.write_text('[ui]\nagent_panel_sort = "priority"')
        self.assertEqual(sidebar_order.sort_mode(env), "priority")
        self.config.write_text('[ui]\nagent_panel_sort = "spaces"')
        env["HERDR_CONFIG_PATH"] = str(self.config)
        self.assertEqual(sidebar_order.sort_mode(env), "spaces")

    def test_hash_uses_derived_client_socket(self):
        # Fixed vectors hash /run/herdr/test-client.sock etc., not the API path.
        for api_socket, filename in [
            ("/run/herdr/test.sock", "local-39bad257cb5e1da8.json"),
            ("/tmp/custom-api", "local-00c549280c3876f8.json"),
            ("/tmp/test.herdr.sock", "local-8aa423d3c8d817c9.json"),
        ]:
            env = dict(self.env, HERDR_SOCKET_PATH=api_socket)
            self.assertEqual(Path(sidebar_order.preference_path(env)).name, filename)
        self.assertIsNone(sidebar_order.preference_path({}))

    def test_reads_priority_from_herdr_client_preference_filename(self):
        # Do not build the fixture path through the function being tested.
        path = Path(self.tmp.name, ".local/state/herdr/client-shell",
                    "local-39bad257cb5e1da8.json")
        path.write_text('{"agent_panel_sort":"priority"}')
        self.assertEqual(sidebar_order.sort_mode(self.env), "priority")

    def test_malformed_preferences_fall_back_with_diagnostic(self):
        self.config.write_text('[ui]\nagent_panel_sort = "priority"')
        for contents in ('{broken', '[]', '{"agent_panel_sort":[]}',
                         '{"agent_panel_sort":"unsupported"}'):
            self.preferences.write_text(contents)
            log = io.StringIO()
            with contextlib.redirect_stderr(log):
                self.assertEqual(sidebar_order.sort_mode(self.env), "priority")
            self.assertIn("attention:", log.getvalue())

    def test_unreadable_files_are_nonfatal(self):
        with mock.patch("builtins.open", side_effect=PermissionError):
            self.assertEqual(sidebar_order.sort_mode(self.env), "spaces")

    def test_no_socket_still_reads_configuration(self):
        self.config.write_text('[ui]\nagent_panel_sort = "priority"')
        self.assertEqual(sidebar_order.sort_mode({"HOME": self.tmp.name}), "priority")


class ConfigScalarTest(unittest.TestCase):
    def test_quotes_comments_and_dotted_key(self):
        for text in ('[ui]\nagent_panel_sort = "priority" # comment',
                     "['ui']\n'agent_panel_sort' = 'priority'",
                     'ui.agent_panel_sort = "priority"',
                     '"ui"."agent_panel_sort" = "priority"'):
            self.assertEqual(sidebar_order.config_sort(text), "priority", text)

    def test_unrelated_sections_and_multiline_strings_are_ignored(self):
        for quotes in ('"""', "'''"):
            text = ('[other]\ntext = ' + quotes + '\n[ui]\n'
                    'agent_panel_sort = "priority"\n' + quotes + '\n'
                    '[ui.sidebar]\nagent_panel_sort = "priority"\n'
                    '[ui]\nagent_panel_sort = "workspaces"\n'
                    '[[keys.command]]\ncommand = "# [ui]"\n')
            self.assertEqual(sidebar_order.config_sort(text), "spaces")

    def test_invalid_and_duplicate_values_log_and_fall_back(self):
        for value in ('123', 'priority', '"other"', '["priority"]',
                      '"priority"\nagent_panel_sort = "spaces"'):
            with contextlib.redirect_stderr(io.StringIO()) as log:
                self.assertIsNone(sidebar_order.config_sort('[ui]\nagent_panel_sort = ' + value))
            self.assertIn("configured agent_panel_sort", log.getvalue())
