"""``Waker`` port: wakes the in-process loops waiting on a subject (spec orchestration §3).

Coupling by data + wake (spec §3): the loop persists the decision (append-only = free
reliability, a missing consumer replays from the table) THEN ``wake``s the subject, resuming an
in-process consumer immediately. Fallback polling stays the net; a lost wake is harmless.
"""

from abc import ABC, abstractmethod

from p2pwatch.domain.wake_subject import WakeSubject


class Waker(ABC):
    """Wakes every ``wait`` on the subject a ``wake`` names."""

    @abstractmethod
    def wake(self, subject: WakeSubject) -> None:
        """Wakes the subject's waiters; synchronous, called post-commit, never blocks."""

    @abstractmethod
    async def wait(self, subject: WakeSubject) -> None:
        """Returns once the subject is woken."""
