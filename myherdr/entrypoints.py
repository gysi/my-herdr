"""Public action and pane IDs mapped to lazily imported feature modules.

Each target exposes main(args). Keep this registry aligned with the manifest;
the offline manifest check verifies both directions. Importing this module
must not import feature implementations.
"""

ENTRYPOINTS = {
    "actions": {
        "attention-next": "myherdr.attention.next",
        "attention-prev": "myherdr.attention.previous",
        "fork-tab": "myherdr.forking.tab",
        "fork-tab-ask": "myherdr.forking.tab_ask",
        "pane-to-tab": "myherdr.pane_to_tab.action",
        "ping": "myherdr.diagnostics.ping",
    },
    "panes": {
        "fork-prompt": "myherdr.forking.popup",
    },
}
