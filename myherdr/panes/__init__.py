"""Pane entrypoints. One module per `[[panes]]` id, each with `main(args)`.

Unlike actions these have a TTY, so they may prompt. A popup has no pane id of
its own: whatever it needs to act on is passed in with `--env`.
"""
