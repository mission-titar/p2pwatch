import asyncio

from p2pwatch.application.ports.driven.waker import Waker
from p2pwatch.domain.wake_subject import WakeSubject


class FakeWaker(Waker):
    """Waker that RECORDS woken and waited subjects (the test inspects/awaits)."""

    def __init__(self) -> None:
        self.woken_subjects: list[WakeSubject] = []
        self.waited_subjects: list[WakeSubject] = []
        self._events: dict[WakeSubject, asyncio.Event] = {}

    def wake(self, subject: WakeSubject) -> None:
        self.woken_subjects.append(subject)
        self._events.setdefault(subject, asyncio.Event()).set()

    async def wait(self, subject: WakeSubject) -> None:
        self.waited_subjects.append(subject)
        event = self._events.setdefault(subject, asyncio.Event())
        await event.wait()
        event.clear()
