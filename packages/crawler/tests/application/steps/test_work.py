"""A work waits before each of its turns, the first one included, and lets other tasks run after
each turn."""

import asyncio

import pytest

from p2pwatch.application.steps.work import Work


class _LastTurnError(Exception):
    """Raised by the last turn, so a test's run ends."""


class _CountedWork(Work):
    """Notes each wait and each turn, neither of which suspends; its last turn raises."""

    def __init__(self, *, turns: int) -> None:
        self.calls: list[str] = []
        self._turns_left = turns

    async def wait_for_next_turn(self) -> None:
        self.calls.append("wait")

    async def run_once(self) -> None:
        self.calls.append("turn")
        self._turns_left -= 1
        if self._turns_left == 0:
            raise _LastTurnError


@pytest.mark.asyncio
async def test_each_turn_comes_after_its_wait_and_an_exception_in_a_turn_ends_the_run() -> None:
    work = _CountedWork(turns=2)

    with pytest.raises(_LastTurnError):
        await work.run()

    assert work.calls == ["wait", "turn", "wait", "turn"]


@pytest.mark.asyncio
async def test_a_turn_that_never_suspends_still_lets_other_tasks_run_after_it() -> None:
    work = _CountedWork(turns=3)
    run = asyncio.create_task(work.run())

    await asyncio.sleep(0)  # noqa: TID251

    assert work.calls == ["wait", "turn"]
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
