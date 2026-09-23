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
        """Read invocation variables and parse the optional context JSON.

        Args:
            env (Mapping[str, str] or None): Environment to read. None uses
                os.environ; an empty mapping describes no herdr invocation.
        """
        self.env = os.environ if env is None else env
        self.raw = self._parse(self.env.get("HERDR_PLUGIN_CONTEXT_JSON"))

    @staticmethod
    def _parse(blob):
        """Parse a context object without failing on absent or malformed JSON.

        Args:
            blob (str or None): HERDR_PLUGIN_CONTEXT_JSON contents, if present.

        Returns:
            dict: Parsed object, or an empty dict for missing or invalid input.
        """
        if not blob:
            return {}
        try:
            value = json.loads(blob)
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}

    def get(self, key, default=None):
        """Read one context field, treating JSON null as missing.

        Args:
            key (str): Field name in the parsed invocation context.
            default (object): Value for missing or null fields, default None.

        Returns:
            object: The field's value, or the supplied default.
        """
        value = self.raw.get(key)
        return default if value is None else value

    # -- identity of the invocation ---------------------------------------

    @property
    def is_herdr(self):
        """Return a bool indicating whether HERDR_ENV marks a herdr invocation."""
        return self.env.get(ENV_MARKER) == "1"

    @property
    def plugin_id(self):
        """Return the plugin ID as a str, defaulting to "my-herdr"."""
        return self.env.get("HERDR_PLUGIN_ID") or "my-herdr"

    @property
    def action_id(self):
        """Return the invoked action ID as a str, or None outside an action."""
        return self.env.get("HERDR_PLUGIN_ACTION_ID")

    @property
    def entrypoint_id(self):
        """Return the pane entrypoint ID as a str, or None outside a plugin pane."""
        return self.env.get("HERDR_PLUGIN_ENTRYPOINT_ID")

    @property
    def invocation_source(self):
        """Return the context's invocation source as a str, or None if absent."""
        return self.get("invocation_source")

    @property
    def plugin_root(self):
        """Return the plugin checkout path as a str, or None when not supplied."""
        return self.env.get("HERDR_PLUGIN_ROOT")

    @property
    def state_dir(self):
        """Return the plugin state path as a str, or None; herdr creates it."""
        return self.env.get("HERDR_PLUGIN_STATE_DIR")

    @property
    def config_dir(self):
        """Return the plugin configuration path as a str, or None if absent."""
        return self.env.get("HERDR_PLUGIN_CONFIG_DIR")

    # -- what was focused --------------------------------------------------

    @property
    def pane_id(self):
        """The pane the action was invoked from, without asking the server.

        A popup gets no HERDR_PANE_ID, so the context JSON is the fallback
        there; callers that need certainty use herdr.focused_pane(), which can
        also ask the server.

        Returns:
            str or None: Source pane ID, preferring HERDR_PANE_ID over JSON.
        """
        return self.env.get("HERDR_PANE_ID") or self.get("focused_pane_id")

    @property
    def tab_id(self):
        """Return the source tab ID as a str, preferring env over JSON, or None."""
        return self.env.get("HERDR_TAB_ID") or self.get("tab_id")

    @property
    def tab_label(self):
        """Return the source tab's label as a str, or None if absent."""
        return self.get("tab_label")

    @property
    def workspace_id(self):
        """Return the workspace ID as a str, preferring env over JSON, or None."""
        return self.env.get("HERDR_WORKSPACE_ID") or self.get("workspace_id")

    @property
    def pane_cwd(self):
        """Return pane cwd, then workspace cwd, as a str; None if both are absent."""
        return self.get("focused_pane_cwd") or self.get("workspace_cwd")

    @property
    def pane_agent(self):
        """Return the focused pane's detected agent kind as a str, or None."""
        return self.get("focused_pane_agent")

    @property
    def pane_status(self):
        """Return the focused pane's agent status as a str, or None if absent."""
        return self.get("focused_pane_status")

    def herdr_env(self):
        """Return HERDR_* variables as sorted (name, value) pairs of strings."""
        return sorted((k, v) for k, v in self.env.items() if k.startswith("HERDR_"))
