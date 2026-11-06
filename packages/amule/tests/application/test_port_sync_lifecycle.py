"""Port-sync's loop: amuled's port read and set live through amuleapi, retried at the next poll
while amuleapi is not ready or rejects it."""

import dataclasses
from datetime import timedelta
from typing import Protocol

import pytest

from p2pwatch_amule.application.port_sync_lifecycle import PortSyncLifecycle
from p2pwatch_amule.domain.listen_port_error import (
    ApiNotReadyError,
    ListenPortError,
    ListenPortRejectedError,
)
from p2pwatch_amule.domain.settings import PortSyncSettings
from tests.fakes.adapters.driven.fake_forwarded_port_client import FakeForwardedPortClient
from tests.fakes.adapters.driven.fake_listen_port_client import FakeListenPortClient
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_monotonic_clock import FakeMonotonicClock

READ = "read listen port"
SET = "set listen port 51820"
REFUSAL = ListenPortRejectedError("PATCH /api/v1/preferences: 400 b'amuled_rejected'")
NOT_READY = ApiNotReadyError("POST /api/v1/auth/login: <urlopen error [Errno 111] refused>")
SETTINGS = PortSyncSettings(
    gluetun_control_url="http://localhost:8000",
    poll_interval=timedelta(seconds=60),
    api_password="s3cret",
)


class _Stop(Exception):
    pass


class RoundCallback(Protocol):
    def __call__(self) -> None: ...


class Node:
    """amuleapi recording into an action list, gluetun's port, a clock, a logger."""

    def __init__(self) -> None:
        self.actions: list[str] = []
        self.forwarded_port_client = FakeForwardedPortClient()
        self.listen_port_client = FakeListenPortClient(self.actions)
        self.between_rounds: RoundCallback = lambda: None
        self.monotonic_clock = FakeMonotonicClock()
        self.logger = FakeLogger()

    def run_loop(
        self,
        port_sync_settings: PortSyncSettings = SETTINGS,
        *,
        rounds: int = 1,
        raises: type[Exception] = _Stop,
    ) -> None:
        """Runs the loop until its ``rounds``-th sleep, or until it ``raises``."""

        def stop_after_the_last_round() -> None:
            if len(self.monotonic_clock.sleeps) == rounds:
                raise _Stop
            self.between_rounds()

        self.monotonic_clock.on_sleep = stop_after_the_last_round
        with pytest.raises(raises):
            PortSyncLifecycle(
                port_sync_settings=port_sync_settings,
                forwarded_port_client=self.forwarded_port_client,
                listen_port_client=self.listen_port_client,
                monotonic_clock=self.monotonic_clock,
                logger=self.logger,
            ).run()


@pytest.fixture
def node() -> Node:
    return Node()


def test_a_new_port_is_set_live_and_amuled_left_running(node: Node) -> None:
    node.run_loop()
    assert node.actions == [READ, SET]
    assert node.listen_port_client.listen_port == 51820
    assert node.logger.lines == [
        LoggedLine(
            level="info", message="gluetun forwards 51820, amuled listened on 4662: set live"
        )
    ]


def test_a_rejected_port_is_logged_amuled_left_on_its_port_and_retried_at_the_next_poll(
    node: Node,
) -> None:
    node.listen_port_client.set_error = REFUSAL
    node.run_loop(rounds=2)
    assert node.actions == [READ, SET, READ, SET]
    assert node.listen_port_client.listen_port == 4662
    rejected = LoggedLine(
        level="error",
        message="amuleapi rejected 51820, amuled stays on 4662 "
        "(PATCH /api/v1/preferences: 400 b'amuled_rejected')",
    )
    assert node.logger.lines == [rejected, rejected]


def test_amuleapi_not_ready_at_the_first_round_is_logged_and_retried_at_the_next_poll(
    node: Node,
) -> None:
    def ready() -> None:
        node.listen_port_client.set_error = None

    node.listen_port_client.set_error = NOT_READY
    node.between_rounds = ready
    node.run_loop(rounds=2)
    assert node.actions == [READ, SET, READ, SET]
    assert node.logger.lines[0] == LoggedLine(
        level="info",
        message="amuleapi is not ready, 51820 waits for the next poll "
        "(POST /api/v1/auth/login: <urlopen error [Errno 111] refused>)",
    )


def test_a_port_set_live_is_read_back_at_the_next_poll_and_not_set_again(node: Node) -> None:
    node.run_loop(rounds=2)
    assert node.actions == [READ, SET, READ]


def test_amuleapi_not_ready_for_the_read_is_logged_and_retried_at_the_next_poll(
    node: Node,
) -> None:
    def ready() -> None:
        node.listen_port_client.read_error = None

    node.listen_port_client.read_error = NOT_READY
    node.between_rounds = ready
    node.run_loop(rounds=2)
    assert node.actions == [READ, READ, SET]
    assert node.logger.lines[0] == LoggedLine(
        level="info",
        message="amuleapi is not ready, 51820 waits for the next poll "
        "(POST /api/v1/auth/login: <urlopen error [Errno 111] refused>)",
    )


def test_another_failure_of_the_read_ends_the_loop(node: Node) -> None:
    node.listen_port_client.read_error = ListenPortError("GET /api/v1/preferences: 500 b''")
    node.run_loop(raises=ListenPortError)
    assert node.actions == [READ]
    assert node.logger.lines == []


def test_another_failure_of_amuleapi_ends_the_loop(node: Node) -> None:
    node.listen_port_client.set_error = ListenPortError("PATCH /api/v1/preferences: 500 b''")
    node.run_loop(raises=ListenPortError)
    assert node.actions == [READ, SET]
    assert node.logger.lines == []


def test_the_same_port_asks_amuleapi_nothing(node: Node) -> None:
    node.forwarded_port_client.forwarded_port = 4662
    node.run_loop()
    assert node.actions == [READ]


def test_no_forwarded_port_asks_amuleapi_nothing(node: Node) -> None:
    node.forwarded_port_client.forwarded_port = None
    node.run_loop()
    assert node.actions == []


def test_the_loop_polls_every_60s(node: Node) -> None:
    node.forwarded_port_client.forwarded_port = 4662
    node.forwarded_port_client.on_read = lambda: node.actions.append("read forwarded port")
    node.run_loop(rounds=2)
    gluetun = "read forwarded port"
    assert node.actions == [gluetun, READ, gluetun, READ]
    assert node.monotonic_clock.sleeps == [timedelta(seconds=60), timedelta(seconds=60)]


def test_the_poll_interval_is_the_settings(node: Node) -> None:
    node.forwarded_port_client.forwarded_port = 4662
    node.run_loop(dataclasses.replace(SETTINGS, poll_interval=timedelta(seconds=5)))
    assert node.monotonic_clock.sleeps == [timedelta(seconds=5)]
