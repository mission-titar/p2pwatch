"""Port-sync's loop: amuled is never left down, and the port is written only while it is down."""

import dataclasses
from collections.abc import Callable
from datetime import timedelta

import pytest

from p2pwatch_amule.adapters.driving import port_sync
from p2pwatch_amule.domain.conf import tcp_listen_port, with_listen_port
from p2pwatch_amule.domain.settings import PortSyncSettings
from tests.fakes import (
    FakeAmuleConf,
    FakeForwardedPortReader,
    FakeLogger,
    FakeMonotonicClock,
    FakeServiceSupervisor,
    LoggedLine,
)

DOWN = "stop amuled"
UP = "start amuled"
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
    """amule.conf, gluetun's port, a fake s6 recording its actions, a clock, a logger."""

    def __init__(self) -> None:
        self.amule_conf = FakeAmuleConf()
        self.amule_conf.conf = CONF
        self.forwarded_port_reader = FakeForwardedPortReader()
        self.service_supervisor = FakeServiceSupervisor()
        self.commands = self.service_supervisor.actions
        self.between_rounds: Callable[[], None] = lambda: None
        self.monotonic_clock = FakeMonotonicClock()
        self.logger = FakeLogger()

    @property
    def conf(self) -> str | None:
        return self.amule_conf.conf

    def move_the_forwarded_port(self) -> None:
        # The first restart wrote 51820; gluetun moving again must wait for the window.
        self.forwarded_port_reader.forwarded_port = 51821

    def main(self, port_sync_settings: PortSyncSettings = SETTINGS, rounds: int = 1) -> None:
        """Runs the loop until its ``rounds``-th sleep."""

        def stop_after_the_last_round() -> None:
            if len(self.monotonic_clock.sleeps) == rounds:
                raise _Stop
            self.between_rounds()

        self.monotonic_clock.on_sleep = stop_after_the_last_round
        with pytest.raises(_Stop):
            port_sync.main(
                port_sync_settings,
                forwarded_port_reader=self.forwarded_port_reader,
                amule_conf_reader=self.amule_conf,
                amule_conf_writer=self.amule_conf,
                service_supervisor=self.service_supervisor,
                monotonic_clock=self.monotonic_clock,
                logger=self.logger,
            )


@pytest.fixture
def node() -> Node:
    return Node()


def test_a_new_port_stops_amuled_writes_both_ports_and_starts_it(node: Node) -> None:
    node.main()
    assert node.commands == [UP, DOWN, UP]
    assert node.conf == with_listen_port(CONF, 51820)
    assert node.logger.lines == [
        LoggedLine("info", "gluetun forwards 51820, amuled listens on 4662: restarting amuled"),
        LoggedLine("info", "amule.conf now sets Port and UDPPort to 51820"),
    ]


def test_the_file_is_written_only_once_amuled_is_down(node: Node) -> None:
    ports_seen_at_down: list[int] = []

    def read_the_port() -> None:
        assert node.conf is not None
        ports_seen_at_down.append(tcp_listen_port(node.conf))

    node.service_supervisor.on_stop_amuled = read_the_port
    node.main()
    assert ports_seen_at_down == [4662]


def test_the_write_keeps_what_amuled_flushed_on_exit(node: Node) -> None:
    def flush() -> None:
        node.amule_conf.conf = CONF.replace("MaxUpload=42", "MaxUpload=42\nNick=flushed")

    node.service_supervisor.on_stop_amuled = flush
    node.main()
    assert node.conf == with_listen_port(
        CONF.replace("MaxUpload=42", "MaxUpload=42\nNick=flushed"), 51820
    )


def test_the_written_file_is_owned_by_puid_and_pgid(node: Node) -> None:
    node.main()
    assert node.amule_conf.owners == [(1000, 1001)]


def test_a_down_wait_that_fails_writes_nothing_and_still_starts_amuled(node: Node) -> None:
    node.service_supervisor.is_amuled_stopped = False
    node.main()
    assert node.commands == [UP, DOWN, UP]
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
    node.main()
    assert node.commands == [UP, DOWN, UP]
    reason = "No space left on device" if conf else "amule.conf does not exist"
    assert node.logger.lines[1:] == [LoggedLine("error", f"amule.conf was not written ({reason})")]


def test_the_same_port_calls_no_s6_command(node: Node) -> None:
    node.forwarded_port_reader.forwarded_port = 4662
    node.main()
    assert node.commands == [UP]


def test_no_forwarded_port_calls_no_s6_command(node: Node) -> None:
    node.forwarded_port_reader.forwarded_port = None
    node.main()
    assert node.commands == [UP]


def test_a_restart_within_the_window_calls_no_s6_command(node: Node) -> None:
    node.between_rounds = node.move_the_forwarded_port
    node.main(dataclasses.replace(SETTINGS, poll_interval=timedelta(seconds=299)), rounds=2)
    assert node.commands == [UP, DOWN, UP]


def test_a_restart_once_the_window_is_over_goes_ahead(node: Node) -> None:
    node.between_rounds = node.move_the_forwarded_port
    node.main(dataclasses.replace(SETTINGS, poll_interval=timedelta(seconds=300)), rounds=2)
    assert node.commands == [UP, DOWN, UP, DOWN, UP]


def test_the_start_sends_up_before_the_first_round_then_polls_every_60s(node: Node) -> None:
    node.forwarded_port_reader.forwarded_port = 4662
    node.forwarded_port_reader.on_read = lambda: node.commands.append("read forwarded port")
    node.main(rounds=2)
    gluetun = "read forwarded port"
    assert node.commands == [UP, gluetun, gluetun]
    assert node.monotonic_clock.sleeps == [timedelta(seconds=60), timedelta(seconds=60)]


def test_the_poll_interval_is_the_settings(node: Node) -> None:
    node.forwarded_port_reader.forwarded_port = 4662
    node.main(dataclasses.replace(SETTINGS, poll_interval=timedelta(seconds=5)))
    assert node.monotonic_clock.sleeps == [timedelta(seconds=5)]


@pytest.mark.parametrize("conf", ["[eMule]\nPort=4662x\n", "Port=4662\n", None])
def test_an_unreadable_amule_conf_calls_no_s6_command_and_is_logged(
    node: Node, conf: str | None
) -> None:
    node.amule_conf.conf = conf
    node.main()
    assert node.commands == [UP]
    assert [line.level for line in node.logger.lines] == ["error"]
    assert node.logger.lines[0].message.startswith(
        "amule.conf's port is unreadable, amuled left as is ("
    )
