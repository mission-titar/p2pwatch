"""``WakeSubject``: what a ``Waker`` wakes, one member per loop that waits on a wake."""

from enum import Enum, auto


class WakeSubject(Enum):
    """The loop a ``wake`` resumes."""

    DOWNLOAD = auto()
