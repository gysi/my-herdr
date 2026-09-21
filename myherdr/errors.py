"""The one exception type the plugin raises on purpose."""


class MyHerdrError(Exception):
    """A failure with a message meant for the user.

    `code` carries herdr's own error code (``agent_not_ready``, ``ui_busy``, …)
    when the failure came from the CLI, so callers can react to specific ones
    without matching on message text.
    """

    def __init__(self, message, code=None):
        super().__init__(message)
        self.message = message
        self.code = code

    def __str__(self):
        return self.message
