"""The composition's resource stack: on exit, all it holds is closed, the first error kept."""

import asyncio

import pytest

from p2pwatch.composition.crawler_composition import resource_stack


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
        async with resource_stack() as resources:
            resources.callback(closed.append, "catalog")
            resources.push_async_callback(fail_to_close)
            raise ValueError("setup failed")

    assert closed == ["client", "catalog"]

