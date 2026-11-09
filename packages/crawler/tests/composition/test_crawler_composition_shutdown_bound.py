"""The composition's shutdown bound: armed, its firing is the shutdown deadline, and only it."""

import asyncio

import pytest

from p2pwatch.composition.crawler_composition import shutdown_bound
from p2pwatch.domain.shutdown_deadline_error import ShutdownDeadlineError

# Far beyond the bound's own deadline: only a bound that never fires reaches it.
_WAIT_SECONDS = 5.0


@pytest.mark.asyncio
async def test_a_timeout_error_of_its_body_passes_through_as_it_is() -> None:
    with pytest.raises(TimeoutError, match="an amuleapi bug"):
        async with shutdown_bound(deadline_seconds=_WAIT_SECONDS):
            raise TimeoutError("an amuleapi bug")


@pytest.mark.asyncio
async def test_once_armed_its_deadline_cuts_the_body_as_a_shutdown_deadline_error() -> None:
    async with asyncio.timeout(_WAIT_SECONDS):
        with pytest.raises(ShutdownDeadlineError, match=r"cut after 0\.01 s"):
            async with shutdown_bound(deadline_seconds=0.01) as arm_shutdown_bound:
                arm_shutdown_bound()
                await asyncio.Event().wait()
