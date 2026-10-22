"""A first signal requests the shutdown, a second exits; on exit, what it holds is closed."""

import asyncio
import signal

import pytest

from p2pwatch.adapters.driving.process.posix_process import PosixProcess
from tests.fakes.application.use_cases.fake_shutdown_requester import FakeShutdownRequester

_REQUESTED = (
    "Shutdown requested: finishing in-flight searches, clean close… (Ctrl-C again to force)"
)


@pytest.mark.asyncio
@pytest.mark.parametrize("signal_number", [signal.SIGINT, signal.SIGTERM])
async def test_a_first_signal_requests_the_shutdown_and_says_how_to_force(
    signal_number: signal.Signals, capsys: pytest.CaptureFixture[str]
) -> None:
    shutdown_requester = FakeShutdownRequester()

    async with PosixProcess(shutdown_requester):
        signal.raise_signal(signal_number)
        await asyncio.wait_for(shutdown_requester.requested.wait(), 1.0)

    assert capsys.readouterr().err == f"{_REQUESTED}\n"


def test_a_second_signal_forces_the_exit(capsys: pytest.CaptureFixture[str]) -> None:
    async def signal_twice() -> None:
        shutdown_requester = FakeShutdownRequester()
        async with PosixProcess(shutdown_requester):
            signal.raise_signal(signal.SIGTERM)
            await shutdown_requester.requested.wait()
            signal.raise_signal(signal.SIGINT)
            await asyncio.wait_for(asyncio.Event().wait(), 1.0)  # only the forced exit ends it

    # The exit escapes the event loop itself, so it is caught around ``asyncio.run``.
    with pytest.raises(SystemExit) as raised:
        asyncio.run(signal_twice())

    assert raised.value.code == 1
    assert capsys.readouterr().err == f"{_REQUESTED}\nForced shutdown.\n"


@pytest.mark.asyncio
async def test_on_exit_the_signals_get_their_default_handlers_back() -> None:
    async with PosixProcess(FakeShutdownRequester()):
        assert signal.getsignal(signal.SIGINT) is not signal.default_int_handler
        assert signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL

    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL


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
        async with PosixProcess(FakeShutdownRequester()) as resources:
            resources.callback(closed.append, "catalog")
            resources.push_async_callback(fail_to_close)
            raise ValueError("setup failed")

    assert closed == ["client", "catalog"]
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
