import asyncio

from p2pwatch.application.ports.driven.waker import Waker


class FakeWaker(Waker):
    """Waker that RECORDS woken and waited subjects (the test inspects/awaits)."""

    def __init__(self) -> None:
        self.woken_subjects: list[str] = []
        self.waited_subjects: list[str] = []
        self._events: dict[str, asyncio.Event] = {}

    def wake(self, subject: str) -> None:
        self.woken_subjects.append(subject)
        self._events.setdefault(subject, asyncio.Event()).set()

    async def wait(self, subject: str) -> None:
        self.waited_subjects.append(subject)
        event = self._events.setdefault(subject, asyncio.Event())
        await event.wait()
        event.clear()
