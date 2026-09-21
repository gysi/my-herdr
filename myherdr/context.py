"""The invocation context: HERDR_* environment plus HERDR_PLUGIN_CONTEXT_JSON.

herdr injects a JSON blob describing what was focused when the action was
invoked, plus a handful of plain variables. Every field is nullable, the JSON
can be absent (running the dispatcher by hand) and it can be malformed, so
nothing here raises: missing values come back as None and the caller decides
whether that is fatal.
"""
import json
import os

# Set on every runtime command; used to tell a real herdr invocation from a
# hand-run one.
ENV_MARKER = "HERDR_ENV"


class Context(object):
    """Read-only view of one invocation. Never touches the herdr CLI."""

    def __init__(self, env=None):
        self.env = os.environ if env is None else env
        self.raw = self._parse(self.env.get("HERDR_PLUGIN_CONTEXT_JSON"))

    @staticmethod
    def _parse(blob):
        if not blob:
            return {}
        try:
            value = json.loads(blob)
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    def get(self, key, default=None):
        """One field of the context JSON, with null treated as missing."""
        value = self.raw.get(key)
        return default if value is None else value

    # -- identity of the invocation ---------------------------------------

    @property
    def is_herdr(self):
        return self.env.get(ENV_MARKER) == "1"

    @property
    def plugin_id(self):
        return self.env.get("HERDR_PLUGIN_ID") or "my-herdr"

    @property
    def action_id(self):
        return self.env.get("HERDR_PLUGIN_ACTION_ID")

    @property
    def entrypoint_id(self):
        return self.env.get("HERDR_PLUGIN_ENTRYPOINT_ID")

    @property
    def invocation_source(self):
        return self.get("invocation_source")

    @property
    def plugin_root(self):
        return self.env.get("HERDR_PLUGIN_ROOT")

    @property
    def state_dir(self):
        """Durable per-plugin state. herdr creates it; the plugin owns it."""
        return self.env.get("HERDR_PLUGIN_STATE_DIR")

    @property
    def config_dir(self):
        return self.env.get("HERDR_PLUGIN_CONFIG_DIR")

    # -- what was focused --------------------------------------------------

    @property
    def pane_id(self):
        """The pane the action was invoked from, without asking the server.

        A popup gets no HERDR_PANE_ID, so the context JSON is the fallback
        there; callers that need certainty use herdr.focused_pane(), which can
        also ask the server.
        """
        return self.env.get("HERDR_PANE_ID") or self.get("focused_pane_id")

    @property
    def tab_id(self):
        return self.env.get("HERDR_TAB_ID") or self.get("tab_id")

    @property
    def tab_label(self):
        return self.get("tab_label")

    @property
    def workspace_id(self):
        return self.env.get("HERDR_WORKSPACE_ID") or self.get("workspace_id")

    @property
    def pane_cwd(self):
        return self.get("focused_pane_cwd") or self.get("workspace_cwd")

    @property
    def pane_agent(self):
        return self.get("focused_pane_agent")

    @property
    def pane_status(self):
        return self.get("focused_pane_status")

    def herdr_env(self):
        """Every HERDR_* variable, sorted. For the ping action and debugging."""
        return sorted((k, v) for k, v in self.env.items() if k.startswith("HERDR_"))
