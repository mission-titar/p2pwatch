import asyncio

import pytest

from p2pwatch.adapters.driven.asyncio_waker import AsyncioWaker
from p2pwatch.domain.wake_subject import WakeSubject


@pytest.mark.asyncio
async def test_signal_wakes_a_waiter() -> None:
    hub = AsyncioWaker()
    waiter = asyncio.create_task(hub.wait(WakeSubject.DOWNLOAD))
    await asyncio.sleep(0)
    assert not waiter.done()
    hub.wake(WakeSubject.DOWNLOAD)
    await asyncio.wait_for(waiter, timeout=1.0)
    assert waiter.done()


@pytest.mark.asyncio
async def test_signal_before_wait_is_not_lost() -> None:
    # A wake WITHOUT a waiter leaves the event armed: the next wait returns immediately.
    hub = AsyncioWaker()
    hub.wake(WakeSubject.DOWNLOAD)
    await asyncio.wait_for(hub.wait(WakeSubject.DOWNLOAD), timeout=1.0)


@pytest.mark.asyncio
async def test_wait_rearms_for_the_next_signal() -> None:
    hub = AsyncioWaker()
    hub.wake(WakeSubject.DOWNLOAD)
    await asyncio.wait_for(hub.wait(WakeSubject.DOWNLOAD), timeout=1.0)
    # Sleeps again: no signal pending anymore → the next wait does not resolve on its own.
    second = asyncio.create_task(hub.wait(WakeSubject.DOWNLOAD))
    await asyncio.sleep(0)
    assert not second.done()
    hub.wake(WakeSubject.DOWNLOAD)
    await asyncio.wait_for(second, timeout=1.0)
