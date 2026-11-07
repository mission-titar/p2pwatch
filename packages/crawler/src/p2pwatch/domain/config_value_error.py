"""The error a config value raises in a parse that does not know its file."""


class ConfigValueError(Exception):
    """A value of a config file is refused: ``key`` is the key path it names, ``None`` for none."""

    def __init__(self, key: str | None, *, message: str) -> None:
        super().__init__(message if key is None else f"{key}: {message}")
        self.key = key
        self.message = message
