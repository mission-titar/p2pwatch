"""The loops run until the stop, whoever asks for it; the bound is armed before they unwind."""

import asyncio

import pytest

from p2pwatch.application.supervise_loops import supervise_loops


class _BlockedLoop:
    """A loop that never ends on its own, and records its cancellation."""

    def __init__(self, name: str, events: list[str]) -> None:
        self._name = name
        self._events = events
        self.started = asyncio.Event()

    async def run(self) -> None:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self._events.append(f"{self._name} cancelled")
            raise


async def _fails() -> None:
    raise ValueError("a worker crashed")


@pytest.mark.asyncio
async def test_a_stop_without_a_signal_arms_the_bound_before_cancelling_every_loop() -> None:
    events: list[str] = []
    shutdown = asyncio.Event()
    search, status = _BlockedLoop("search", events), _BlockedLoop("status", events)
    supervision = asyncio.create_task(
        supervise_loops(
            [search.run, status.run],
            shutdown=shutdown,
            arm_shutdown_bound=lambda: events.append("armed"),
        )
    )
    await search.started.wait()
    await status.started.wait()

    shutdown.set()  # as the webui's restart button does: no signal involved
    await asyncio.wait_for(supervision, 1.0)

    assert events[0] == "armed"
    assert sorted(events[1:]) == ["search cancelled", "status cancelled"]


@pytest.mark.asyncio
async def test_a_loop_that_ends_neither_stops_the_others_nor_arms_the_bound() -> None:
    events: list[str] = []
    shutdown = asyncio.Event()
    status = _BlockedLoop("status", events)
    ended = asyncio.Event()

    async def end_at_once() -> None:
        ended.set()

    supervision = asyncio.create_task(
        supervise_loops(
            [end_at_once, status.run],
            shutdown=shutdown,
            arm_shutdown_bound=lambda: events.append("armed"),
        )
    )
    await ended.wait()
    await status.started.wait()

    assert not supervision.done()
    assert events == []
    shutdown.set()
    await asyncio.wait_for(supervision, 1.0)
    assert events == ["armed", "status cancelled"]


@pytest.mark.asyncio
async def test_a_failing_loop_escapes_as_an_exception_group_without_arming_the_bound() -> None:
    events: list[str] = []
    status = _BlockedLoop("status", events)

    with pytest.RaisesGroup(pytest.RaisesExc(ValueError, match="a worker crashed")):
        await supervise_loops(
            [status.run, _fails],
            shutdown=asyncio.Event(),
            arm_shutdown_bound=lambda: events.append("armed"),
        )

    assert events == ["status cancelled"]
