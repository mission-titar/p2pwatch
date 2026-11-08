class BrokenInputError(Exception):
    """A config file a check cannot read: ``reason`` why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
