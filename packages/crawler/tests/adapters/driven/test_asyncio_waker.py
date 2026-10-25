import asyncio

import pytest

from p2pwatch.adapters.driven.asyncio_waker import AsyncioWaker
from p2pwatch.domain.wake_subject import WakeSubject
from tests.contracts.application.ports.driven.waker_contract import WakerContract


class TestAsyncioWaker(WakerContract):
    @pytest.fixture
    def waker(self) -> AsyncioWaker:
        return AsyncioWaker()


@pytest.mark.asyncio
async def test_a_wake_with_no_waiter_is_kept_for_the_next_wait() -> None:
    waker = AsyncioWaker()
    waker.wake(WakeSubject.DOWNLOAD)
    await asyncio.wait_for(waker.wait(WakeSubject.DOWNLOAD), timeout=1.0)


@pytest.mark.asyncio
async def test_a_wait_consumes_the_kept_wake() -> None:
    waker = AsyncioWaker()
    waker.wake(WakeSubject.DOWNLOAD)
    await asyncio.wait_for(waker.wait(WakeSubject.DOWNLOAD), timeout=1.0)
    # Sleeps again: no wake kept anymore, so the next wait does not return on its own.
    second = asyncio.create_task(waker.wait(WakeSubject.DOWNLOAD))
    await asyncio.sleep(0)
    assert not second.done()
    waker.wake(WakeSubject.DOWNLOAD)
    await asyncio.wait_for(second, timeout=1.0)
