"""The one error an invalid config raises, whichever file or check refused it."""


class InvalidConfigError(Exception):
    """A config file does not load or does not parse: the crawler refuses to start; ``key`` is
    the key path it names, ``None`` for none."""

    def __init__(self, key: str | None, message: str) -> None:
        super().__init__(message if key is None else f"{key}: {message}")
        self.key = key
        self.message = message
