"""``StdlibLogger``: the ``Logger`` port over a named ``logging.Logger``."""

import logging

from p2pwatch.application.ports.driven.logger import Logger

# The caller of debug() or info(), not this module, is the record's location.
_CALLER = 2


class StdlibLogger(Logger):
    """Writes to ``logging.getLogger(name)``, so the operator's filters on that name apply."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def debug(self, message: str, *args: object) -> None:
        self._logger.debug(message, *args, stacklevel=_CALLER)

    def info(self, message: str, *args: object) -> None:
        self._logger.info(message, *args, stacklevel=_CALLER)

    def warning(self, message: str, *args: object) -> None:
        self._logger.warning(message, *args, stacklevel=_CALLER)

    def error(self, message: str, *args: object) -> None:
        self._logger.error(message, *args, stacklevel=_CALLER)
