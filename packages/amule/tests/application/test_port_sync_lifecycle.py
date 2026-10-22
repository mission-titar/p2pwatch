"""Port-sync's loop: amuled is never left down, and the port is written only while it is down."""

import dataclasses
from collections.abc import Callable
from datetime import timedelta

import pytest

from p2pwatch_amule.application.port_sync_lifecycle import PortSyncLifecycle
from p2pwatch_amule.domain.conf import with_listen_port
from p2pwatch_amule.domain.settings import PortSyncSettings
from tests.fakes.adapters.driven.fake_amule_conf_store import FakeAmuleConfStore
from tests.fakes.adapters.driven.fake_forwarded_port_reader import FakeForwardedPortReader
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_monotonic_clock import FakeMonotonicClock
from tests.fakes.adapters.driven.fake_service_supervisor import FakeServiceSupervisor

DOWN = "stop amuled"
UP = "start amuled"
READ = "read amule.conf"
WRITE = "write amule.conf as 1000:1001"
SETTINGS = PortSyncSettings(
    gluetun_control_url="http://localhost:8000",
    poll_interval=timedelta(seconds=60),
    restart_min_interval=timedelta(seconds=300),
    puid=1000,
    pgid=1001,
)
CONF = "[eMule]\nPort=4662\nUDPPort=4672\nMaxUpload=42\n\n[AmuleApi]\nEnabled=1\n\n"


class _Stop(Exception):
    pass


class Node:
    """amule.conf and the supervisor recording into one action list, gluetun's port, a clock, a
    logger."""

    def __init__(self) -> None:
        self.actions: list[str] = []
        self.amule_conf = FakeAmuleConfStore(self.actions)
        self.amule_conf.conf = CONF
        self.forwarded_port_reader = FakeForwardedPortReader()
        self.service_supervisor = FakeServiceSupervisor(self.actions)
        self.between_rounds: Callable[[], None] = lambda: None
        self.monotonic_clock = FakeMonotonicClock()
        self.logger = FakeLogger()

    @property
    def conf(self) -> str | None:
        return self.amule_conf.conf

    def move_the_forwarded_port(self) -> None:
        # The first restart wrote 51820; gluetun moving again must wait for the window.
        self.forwarded_port_reader.forwarded_port = 51821

    def run_loop(self, port_sync_settings: PortSyncSettings = SETTINGS, rounds: int = 1) -> None:
        """Runs the loop until its ``rounds``-th sleep."""

        def stop_after_the_last_round() -> None:
            if len(self.monotonic_clock.sleeps) == rounds:
                raise _Stop
            self.between_rounds()

        self.monotonic_clock.on_sleep = stop_after_the_last_round
        with pytest.raises(_Stop):
            PortSyncLifecycle(
                port_sync_settings=port_sync_settings,
                forwarded_port_reader=self.forwarded_port_reader,
                amule_conf_reader=self.amule_conf,
                amule_conf_writer=self.amule_conf,
                service_supervisor=self.service_supervisor,
                monotonic_clock=self.monotonic_clock,
                logger=self.logger,
            ).run()


@pytest.fixture
def node() -> Node:
    return Node()


def test_a_new_port_stops_amuled_writes_both_ports_and_starts_it(node: Node) -> None:
    node.run_loop()
    assert node.actions == [UP, READ, DOWN, READ, WRITE, UP]
    assert node.conf == with_listen_port(CONF, 51820)
    assert node.logger.lines == [
        LoggedLine("info", "gluetun forwards 51820, amuled listens on 4662: restarting amuled"),
        LoggedLine("info", "amule.conf now sets Port and UDPPort to 51820"),
    ]


def test_the_write_keeps_what_amuled_flushed_on_exit(node: Node) -> None:
    def flush() -> None:
        node.amule_conf.conf = CONF.replace("MaxUpload=42", "MaxUpload=42\nNick=flushed")

    node.service_supervisor.on_stop_amuled = flush
    node.run_loop()
    assert node.conf == with_listen_port(
        CONF.replace("MaxUpload=42", "MaxUpload=42\nNick=flushed"), 51820
    )


def test_a_down_wait_that_fails_writes_nothing_and_still_starts_amuled(node: Node) -> None:
    node.service_supervisor.is_amuled_stopped = False
    node.run_loop()
    assert node.actions == [UP, READ, DOWN, UP]
    assert node.conf == CONF
    assert node.logger.lines[1:] == []


@pytest.mark.parametrize("conf", ["[eMule]\nPort=4662\n", None])
def test_a_write_that_raises_still_starts_amuled_and_is_logged(
    node: Node, conf: str | None
) -> None:
    def flush() -> None:
        node.amule_conf.conf = conf

    node.amule_conf.write_error = OSError("No space left on device")
    node.service_supervisor.on_stop_amuled = flush
    node.run_loop()
    assert node.actions == [UP, READ, DOWN, READ, UP]
    reason = "No space left on device" if conf else "amule.conf does not exist"
    assert node.logger.lines[1:] == [LoggedLine("error", f"amule.conf was not written ({reason})")]


def test_the_same_port_asks_the_supervisor_nothing(node: Node) -> None:
    node.forwarded_port_reader.forwarded_port = 4662
    node.run_loop()
    assert node.actions == [UP, READ]


def test_no_forwarded_port_asks_the_supervisor_nothing(node: Node) -> None:
    node.forwarded_port_reader.forwarded_port = None
    node.run_loop()
    assert node.actions == [UP]


def test_a_restart_within_the_window_asks_the_supervisor_nothing(node: Node) -> None:
    node.between_rounds = node.move_the_forwarded_port
    node.run_loop(dataclasses.replace(SETTINGS, poll_interval=timedelta(seconds=299)), rounds=2)
    assert node.actions == [UP, READ, DOWN, READ, WRITE, UP, READ]


def test_a_restart_once_the_window_is_over_goes_ahead(node: Node) -> None:
    node.between_rounds = node.move_the_forwarded_port
    node.run_loop(dataclasses.replace(SETTINGS, poll_interval=timedelta(seconds=300)), rounds=2)
    restart = [READ, DOWN, READ, WRITE, UP]
    assert node.actions == [UP, *restart, *restart]


def test_the_start_sends_up_before_the_first_round_then_polls_every_60s(node: Node) -> None:
    node.forwarded_port_reader.forwarded_port = 4662
    node.forwarded_port_reader.on_read = lambda: node.actions.append("read forwarded port")
    node.run_loop(rounds=2)
    gluetun = "read forwarded port"
    assert node.actions == [UP, gluetun, READ, gluetun, READ]
    assert node.monotonic_clock.sleeps == [timedelta(seconds=60), timedelta(seconds=60)]


def test_the_poll_interval_is_the_settings(node: Node) -> None:
    node.forwarded_port_reader.forwarded_port = 4662
    node.run_loop(dataclasses.replace(SETTINGS, poll_interval=timedelta(seconds=5)))
    assert node.monotonic_clock.sleeps == [timedelta(seconds=5)]


@pytest.mark.parametrize("conf", ["[eMule]\nPort=4662x\n", "Port=4662\n", None])
def test_an_unreadable_amule_conf_asks_the_supervisor_nothing_and_is_logged(
    node: Node, conf: str | None
) -> None:
    node.amule_conf.conf = conf
    node.run_loop()
    assert node.actions == [UP, READ]
    assert [line.level for line in node.logger.lines] == ["error"]
    assert node.logger.lines[0].message.startswith(
        "amule.conf's port is unreadable, amuled left as is ("
    )
