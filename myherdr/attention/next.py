"""Focus an urgent agent, otherwise the next sidebar row."""
from .navigation import navigate


def main(args):
    """Focus the next agent and save navigation state after success.

    Args:
        args (list[str]): Dispatcher arguments; unused by this headless action.

    Returns:
        int: 0 after focusing or notifying that no other agent exists.

    Raises:
        MyHerdrError: herdr cannot list agents or focus the selected target.
    """
    return navigate(1)
