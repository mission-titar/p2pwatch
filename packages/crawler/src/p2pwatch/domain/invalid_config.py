"""The one error an invalid config raises, whichever file or check refused it."""


class InvalidConfigError(Exception):
    """A config file does not load or does not parse: the crawler refuses to start."""
