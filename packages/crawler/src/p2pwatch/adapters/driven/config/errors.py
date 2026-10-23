"""Shared config error (fail-fast §5/§14), isolated to break an import cycle."""


class ConfigError(Exception):
    """Invalid config → refuse to start; ``key`` is the key path it names, ``None`` for none."""

    def __init__(self, key: str | None, message: str) -> None:
        super().__init__(message if key is None else f"{key}: {message}")
        self.key = key
        self.message = message
