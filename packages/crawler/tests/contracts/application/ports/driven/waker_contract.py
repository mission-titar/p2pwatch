"""The promise of the ``Waker`` port."""

import asyncio
from abc import ABC, abstractmethod

import pytest

from p2pwatch.application.ports.driven.waker import Waker
from p2pwatch.domain.wake_subject import WakeSubject


class WakerContract(ABC):
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    @abstractmethod
    def waker(self) -> Waker:
        """A waker no call has woken yet, waited on the test's running loop."""

    async def test_a_wait_returns_once_its_subject_is_woken(self, waker: Waker) -> None:
        waiting = asyncio.create_task(waker.wait(WakeSubject.DOWNLOAD))
        await asyncio.sleep(0)  # noqa: TID251
        assert not waiting.done()

        waker.wake(WakeSubject.DOWNLOAD)

        await asyncio.wait_for(waiting, 1.0)

    async def test_a_wake_wakes_every_wait_on_its_subject(self, waker: Waker) -> None:
        waitings = [asyncio.create_task(waker.wait(WakeSubject.DOWNLOAD)) for _ in range(2)]
        await asyncio.sleep(0)  # noqa: TID251

        waker.wake(WakeSubject.DOWNLOAD)

        await asyncio.wait_for(asyncio.gather(*waitings), 1.0)
