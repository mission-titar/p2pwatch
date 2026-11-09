"""The composition's resource stack: on exit, all it holds is closed within its bound, the first
error kept."""

import asyncio

import pytest

from p2pwatch.composition.crawler_composition import resource_stack

# Far beyond the stack's own bound: only a close it does not cut reaches it.
_WAIT_SECONDS = 5.0


@pytest.mark.asyncio
@pytest.mark.parametrize("close_failure", [OSError("close failed"), asyncio.CancelledError()])
async def test_on_exit_it_closes_all_it_holds_and_lets_only_the_first_error_through(
    close_failure: BaseException,
) -> None:
    closed: list[str] = []

    async def fail_to_close() -> None:
        closed.append("client")
        raise close_failure

    with pytest.raises(ValueError, match="setup failed"):
        async with resource_stack(close_timeout_seconds=_WAIT_SECONDS) as resources:
            resources.callback(closed.append, "catalog")
            resources.push_async_callback(fail_to_close)
            raise ValueError("setup failed")

    assert closed == ["client", "catalog"]


@pytest.mark.asyncio
async def test_a_close_that_never_returns_is_cut_at_its_bound() -> None:
    async def never_close() -> None:
        await asyncio.Event().wait()

    async def hold_then_leave() -> None:
        async with resource_stack(close_timeout_seconds=0.01) as resources:
            resources.push_async_callback(never_close)

    leaving = asyncio.create_task(hold_then_leave())
    done, _ = await asyncio.wait({leaving}, timeout=_WAIT_SECONDS)
    leaving.cancel()

    assert leaving in done
    assert leaving.exception() is None
