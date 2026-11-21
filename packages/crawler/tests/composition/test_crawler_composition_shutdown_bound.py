"""The composition's shutdown bound: armed, its firing is the shutdown deadline, and only it; the
close runs within it once its body has ended, and a restart keeps its error whatever it cuts."""

import asyncio

import pytest

from p2pwatch.composition.crawler_composition import shutdown_bound
from p2pwatch.domain.crawler_function import CrawlerFunction
from p2pwatch.domain.crawler_restart_error import CrawlerRestartError
from p2pwatch.domain.shutdown_deadline_error import ShutdownDeadlineError

# Far beyond the bound's own deadline: only a bound that never fires reaches it.
_WAIT_SECONDS = 5.0
_RESTART = CrawlerRestartError(CrawlerFunction.CRAWL, rebuilds=3)


class _Close:
    """Notes when it starts, then ends at once, or never once told to hang."""

    def __init__(self, *, hangs: bool = False) -> None:
        self.started = 0
        self._hangs = hangs

    async def __call__(self) -> None:
        self.started += 1
        if self._hangs:
            await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_a_timeout_error_of_its_body_passes_through_as_it_is() -> None:
    with pytest.raises(TimeoutError, match="an amuleapi bug"):
        async with shutdown_bound(deadline_seconds=_WAIT_SECONDS, close=_Close()):
            raise TimeoutError("an amuleapi bug")


@pytest.mark.asyncio
async def test_once_armed_its_deadline_cuts_the_body_as_a_shutdown_deadline_error() -> None:
    close = _Close()
    async with asyncio.timeout(_WAIT_SECONDS):
        with pytest.raises(ShutdownDeadlineError, match=r"cut after 0\.01 s"):
            async with shutdown_bound(deadline_seconds=0.01, close=close) as arm_shutdown_bound:
                arm_shutdown_bound()
                await asyncio.Event().wait()

    # What is left is the resource stack's to close, within its own bound.
    assert close.started == 0


@pytest.mark.asyncio
async def test_its_close_runs_within_it_once_its_body_has_ended() -> None:
    close = _Close()

    async with shutdown_bound(deadline_seconds=_WAIT_SECONDS, close=close):
        pass

    assert close.started == 1


@pytest.mark.asyncio
async def test_a_restart_has_its_close_run_within_it_then_raises_its_error() -> None:
    close = _Close()

    with pytest.raises(CrawlerRestartError):
        async with shutdown_bound(deadline_seconds=_WAIT_SECONDS, close=close):
            raise _RESTART

    assert close.started == 1


@pytest.mark.asyncio
async def test_a_restart_whose_drain_its_deadline_cut_keeps_its_error_leaving_the_close() -> None:
    close = _Close()

    async with asyncio.timeout(_WAIT_SECONDS):
        with pytest.raises(CrawlerRestartError):
            async with shutdown_bound(deadline_seconds=0.01, close=close) as arm_shutdown_bound:
                arm_shutdown_bound()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:  # as the lifecycle's drain, cut
                    raise _RESTART from None

    assert close.started == 0


@pytest.mark.asyncio
async def test_a_restart_whose_close_its_deadline_cut_keeps_its_error() -> None:
    close = _Close(hangs=True)

    async with asyncio.timeout(_WAIT_SECONDS):
        with pytest.raises((CrawlerRestartError, ShutdownDeadlineError)) as raised:
            async with shutdown_bound(deadline_seconds=0.01, close=close) as arm_shutdown_bound:
                arm_shutdown_bound()
                raise _RESTART

    assert (close.started, raised.value) == (1, _RESTART)
