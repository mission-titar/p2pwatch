"""A work waits before each of its turns, the first included, and yields after each one."""

import asyncio

import pytest

from p2pwatch.application.steps.work import Work


class _Ended(Exception):
    """Ends a recorded run at its last turn."""


class _RecordedWork(Work):
    """Records its waits and turns, neither suspending, and raises at its last turn."""

    def __init__(self, *, turns: int) -> None:
        self.events: list[str] = []
        self._turns_left = turns

    async def wait_for_next_turn(self) -> None:
        self.events.append("wait")

    async def run_once(self) -> None:
        self.events.append("turn")
        self._turns_left -= 1
        if self._turns_left == 0:
            raise _Ended


@pytest.mark.asyncio
async def test_each_turn_follows_its_wait_and_a_turn_s_error_ends_the_run() -> None:
    work = _RecordedWork(turns=2)

    with pytest.raises(_Ended):
        await work.run()

    assert work.events == ["wait", "turn", "wait", "turn"]


@pytest.mark.asyncio
async def test_a_turn_that_never_suspends_yields_the_loop_after_it() -> None:
    work = _RecordedWork(turns=3)
    run = asyncio.create_task(work.run())

    await asyncio.sleep(0)  # noqa: TID251

    assert work.events == ["wait", "turn"]
    assert not run.done()
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
