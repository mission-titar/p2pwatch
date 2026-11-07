from pathlib import PurePath


class BrokenInputError(Exception):
    """A config file a check cannot read: ``reason`` why, its message naming the file first."""

    def __init__(self, path: PurePath, *, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.reason = reason
