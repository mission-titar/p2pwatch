"""``Severity``: how much a fact matters, the level its log line takes."""

from enum import Enum, auto


class Severity(Enum):
    """DOMAIN severity of a fact (translated to a ``logging`` level by the adapter)."""

    DEBUG = auto()
    INFO = auto()
    SUCCESS = auto()
    WARNING = auto()
