"""The invocation context. Every field is nullable, so nothing here may raise."""
import json
import unittest

import support  # noqa: F401  (puts the plugin root on sys.path)

from myherdr.context import Context

# The shape herdr injects, trimmed to the fields the plugin reads.
CONTEXT = {
    "workspace_id": "w1",
    "workspace_label": "project",
    "workspace_cwd": "/home/user/project",
    "tab_id": "w1:t1",
    "tab_label": "api",
    "focused_pane_id": "w1:p1",
    "focused_pane_cwd": "/home/user/project/api",
    "focused_pane_agent": "claude",
    "focused_pane_status": "blocked",
    "invocation_source": "keybinding",
}


def env(**overrides):
    """Build a plugin environment with the default invocation context.

    Args:
        **overrides: Environment values to replace; None removes a variable.

    Returns:
        Dictionary of environment variable names and string values.
    """
    base = {
        "HERDR_ENV": "1",
        "HERDR_PLUGIN_ID": "my-herdr",
        "HERDR_PLUGIN_CONTEXT_JSON": json.dumps(CONTEXT),
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


class ContextTest(unittest.TestCase):
    def test_reads_the_context_json(self):
        ctx = Context(env())
        self.assertEqual(ctx.pane_id, "w1:p1")
        self.assertEqual(ctx.tab_label, "api")
        self.assertEqual(ctx.pane_agent, "claude")
        self.assertEqual(ctx.invocation_source, "keybinding")

    def test_env_wins_over_context_for_the_pane(self):
        # HERDR_PANE_ID is the pane that had focus at keypress time; the
        # context is rebuilt later and can disagree.
        ctx = Context(env(HERDR_PANE_ID="w2:p5"))
        self.assertEqual(ctx.pane_id, "w2:p5")

    def test_popup_falls_back_to_the_context(self):
        # A popup deliberately gets no HERDR_PANE_ID, so the underlying tiled
        # pane has to come from the context JSON.
        ctx = Context(env(HERDR_PANE_ID=None, HERDR_PLUGIN_ENTRYPOINT_ID="fork-prompt"))
        self.assertEqual(ctx.pane_id, "w1:p1")
        self.assertEqual(ctx.entrypoint_id, "fork-prompt")

    def test_pane_cwd_falls_back_to_the_workspace(self):
        context = dict(CONTEXT, focused_pane_cwd=None)
        ctx = Context(env(HERDR_PLUGIN_CONTEXT_JSON=json.dumps(context)))
        self.assertEqual(ctx.pane_cwd, "/home/user/project")

    def test_null_fields_read_as_missing(self):
        context = dict(CONTEXT, tab_label=None)
        ctx = Context(env(HERDR_PLUGIN_CONTEXT_JSON=json.dumps(context)))
        self.assertIsNone(ctx.tab_label)
        self.assertEqual(ctx.get("tab_label", "fallback"), "fallback")

    def test_malformed_json_is_empty_not_fatal(self):
        ctx = Context(env(HERDR_PLUGIN_CONTEXT_JSON="{not json"))
        self.assertEqual(ctx.raw, {})
        self.assertIsNone(ctx.pane_id)

    def test_non_object_json_is_empty(self):
        ctx = Context(env(HERDR_PLUGIN_CONTEXT_JSON="[1, 2, 3]"))
        self.assertEqual(ctx.raw, {})

    def test_missing_context_is_empty(self):
        ctx = Context({})
        self.assertEqual(ctx.raw, {})
        self.assertFalse(ctx.is_herdr)
        self.assertEqual(ctx.plugin_id, "my-herdr")

    def test_herdr_env_listing_is_sorted_and_filtered(self):
        ctx = Context({"HERDR_PANE_ID": "w1:p1", "PATH": "/usr/bin", "HERDR_ENV": "1"})
        self.assertEqual(ctx.herdr_env(), [("HERDR_ENV", "1"), ("HERDR_PANE_ID", "w1:p1")])


if __name__ == "__main__":
    unittest.main()
