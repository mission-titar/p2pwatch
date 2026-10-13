import asyncio

import pytest

from p2pwatch.adapters.wake_hub_asyncio import AsyncioWakeHub


@pytest.mark.asyncio
async def test_signal_wakes_a_waiter() -> None:
    hub = AsyncioWakeHub()
    waiter = asyncio.create_task(hub.wait("062A"))
    await asyncio.sleep(0)
    assert not waiter.done()
    hub.wake("062A")
    await asyncio.wait_for(waiter, timeout=1.0)
    assert waiter.done()


@pytest.mark.asyncio
async def test_signal_before_wait_is_not_lost() -> None:
    # A wake WITHOUT a waiter leaves the event armed: the next wait returns immediately.
    hub = AsyncioWakeHub()
    hub.wake("062A")
    await asyncio.wait_for(hub.wait("062A"), timeout=1.0)  # ne bloque pas


@pytest.mark.asyncio
async def test_wait_rearms_for_the_next_signal() -> None:
    hub = AsyncioWakeHub()
    hub.wake("h")
    await asyncio.wait_for(hub.wait("h"), timeout=1.0)
    # Sleeps again: no signal pending anymore → the next wait does not resolve on its own.
    second = asyncio.create_task(hub.wait("h"))
    await asyncio.sleep(0)
    assert not second.done()
    hub.wake("h")
    await asyncio.wait_for(second, timeout=1.0)


@pytest.mark.asyncio
async def test_subjects_are_independent() -> None:
    hub = AsyncioWakeHub()
    waiter_a = asyncio.create_task(hub.wait("a"))
    await asyncio.sleep(0)
    hub.wake("b")  # other subject: does not wake a
    await asyncio.sleep(0)
    assert not waiter_a.done()
    hub.wake("a")
    await asyncio.wait_for(waiter_a, timeout=1.0)
