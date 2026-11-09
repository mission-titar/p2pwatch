"""A first signal requests the shutdown, a second exits; while the start holds the event loop, a
flag says it at once; on exit, the signals are given back."""

import asyncio
import signal

import pytest

from p2pwatch.adapters.driving.process.posix_process import PosixProcess
from tests.fakes.application.use_cases.fake_shutdown_requester import FakeShutdownRequester

_REQUESTED = (
    "Shutdown requested: finishing in-flight searches, clean close… (Ctrl-C again to force)"
)


async def _let_the_loop_run() -> None:
    """Returns once the loop has run the callbacks scheduled before this call."""
    loop = asyncio.get_running_loop()
    ran = loop.create_future()
    loop.call_soon(ran.set_result, None)
    await ran


@pytest.mark.asyncio
@pytest.mark.parametrize("signal_number", [signal.SIGINT, signal.SIGTERM])
async def test_a_first_signal_requests_the_shutdown_and_says_how_to_force(
    *, signal_number: signal.Signals, capsys: pytest.CaptureFixture[str]
) -> None:
    shutdown_requester = FakeShutdownRequester()

    async with PosixProcess(shutdown_requester):
        signal.raise_signal(signal_number)
        await asyncio.wait_for(shutdown_requester.requested.wait(), 1.0)

    assert capsys.readouterr().err == f"{_REQUESTED}\n"


@pytest.mark.asyncio
async def test_a_signal_while_the_start_holds_the_loop_is_seen_at_once_by_its_flag() -> None:
    shutdown_requester = FakeShutdownRequester()

    async with PosixProcess(shutdown_requester) as process:
        assert not process.is_shutdown_requested()
        signal.raise_signal(signal.SIGTERM)
        requested_at_once = process.is_shutdown_requested()

    assert requested_at_once
    assert shutdown_requester.calls == ["request_shutdown"]


@pytest.mark.asyncio
async def test_once_the_loop_runs_a_signal_is_handled_by_the_loop_never_mid_bytecode() -> None:
    shutdown_requester = FakeShutdownRequester()

    async with PosixProcess(shutdown_requester) as process:
        await _let_the_loop_run()
        signal.raise_signal(signal.SIGTERM)
        requested_before_the_loop_ran = process.is_shutdown_requested()
        await asyncio.wait_for(shutdown_requester.requested.wait(), 1.0)

    assert not requested_before_the_loop_ran
    assert process.is_shutdown_requested()


@pytest.mark.parametrize("loop_ran", [False, True], ids=["holding-the-loop", "on-the-loop"])
def test_a_second_signal_forces_the_exit(
    *, loop_ran: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    async def signal_twice() -> None:
        shutdown_requester = FakeShutdownRequester()
        async with PosixProcess(shutdown_requester):
            if loop_ran:
                await _let_the_loop_run()
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
@pytest.mark.parametrize("loop_ran", [False, True], ids=["holding-the-loop", "on-the-loop"])
async def test_on_exit_the_signals_get_their_default_handlers_back(*, loop_ran: bool) -> None:
    async with PosixProcess(FakeShutdownRequester()):
        if loop_ran:
            await _let_the_loop_run()
        assert signal.getsignal(signal.SIGINT) is not signal.default_int_handler
        assert signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL

    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
