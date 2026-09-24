"""Focus the previous sidebar row without urgency interruptions."""
from .navigation import navigate


def main(args):
    """Focus the previous agent and save navigation state after success.

    Args:
        args (list[str]): Dispatcher arguments; unused by this headless action.

    Returns:
        int: 0 after focusing or notifying that no other agent exists.

    Raises:
        MyHerdrError: herdr cannot list agents or focus the selected target.
    """
    return navigate(-1)
