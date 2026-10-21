"""Port-sync's loop: amuled is never left down, and the port is written only while it is down."""

import dataclasses
import os
import subprocess
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from p2pwatch_amule.adapters.driving import port_sync
from p2pwatch_amule.domain.conf import tcp_listen_port, with_listen_port
from p2pwatch_amule.domain.monotonic_instant import MonotonicInstant
from p2pwatch_amule.domain.settings import PortSyncSettings
from tests.fakes import FakeForwardedPortReader, FakeLogger, FakeMonotonicClock, LoggedLine

AMULED_SERVICE_DIRECTORY = "/run/service/amuled"
DOWN = ["s6-svc", "-wD", "-T", "60000", "-d", AMULED_SERVICE_DIRECTORY]
UP = ["s6-svc", "-u", AMULED_SERVICE_DIRECTORY]
SETTINGS = PortSyncSettings(
    gluetun_control_url="http://localhost:8000",
    poll_interval=timedelta(seconds=60),
    restart_min_interval=timedelta(seconds=300),
)
CONF = "[eMule]\nPort=4662\nUDPPort=4672\nMaxUpload=42\n\n[AmuleApi]\nEnabled=1\n\n"


def instant_at(seconds: int) -> MonotonicInstant:
    return MonotonicInstant(seconds * 1_000_000_000)


class Node:
    """amule.conf under tmp_path, gluetun's port, a fake s6 recording its commands, a clock, a
    logger."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.conf = tmp_path / "amule.conf"
        self.conf.write_text(CONF)
        self.forwarded_port_reader = FakeForwardedPortReader()
        self.commands: list[list[str]] = []
        self.down_exit = 0
        self.on_down: Callable[[], None] = lambda: None
        self.monotonic_clock = FakeMonotonicClock()
        self.logger = FakeLogger()
        monkeypatch.setattr(subprocess, "run", self._run)

    def sync_once(
        self, latest_restart: MonotonicInstant | None, now: MonotonicInstant
    ) -> MonotonicInstant | None:
        return port_sync.sync_listen_port_once(
            SETTINGS,
            latest_restart,
            now,
            amule_conf_path=self.conf,
            amuled_service_directory=Path(AMULED_SERVICE_DIRECTORY),
            forwarded_port_reader=self.forwarded_port_reader,
            logger=self.logger,
        )

    def main(self, port_sync_settings: PortSyncSettings = SETTINGS) -> None:
        port_sync.main(
            port_sync_settings,
            amule_conf_path=self.conf,
            amuled_service_directory=Path(AMULED_SERVICE_DIRECTORY),
            monotonic_clock=self.monotonic_clock,
            forwarded_port_reader=self.forwarded_port_reader,
            logger=self.logger,
        )

    def _run(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(argv)
        if argv == DOWN:
            self.on_down()
            return subprocess.CompletedProcess(argv, self.down_exit, "", "timed out")
        return subprocess.CompletedProcess(argv, 0, "", "")


@pytest.fixture
def node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Node:
    return Node(tmp_path, monkeypatch)


def test_a_new_port_stops_amuled_writes_both_ports_and_starts_it(node: Node) -> None:
    assert node.sync_once(None, now=instant_at(1000)) == instant_at(1000)
    assert node.commands == [DOWN, UP]
    assert node.conf.read_text() == with_listen_port(CONF, 51820)
    assert tcp_listen_port(node.conf.read_text()) == 51820
    assert node.logger.lines == [
        LoggedLine("info", "gluetun forwards 51820, amuled listens on 4662: restarting amuled"),
        LoggedLine("info", "amule.conf now sets Port and UDPPort to 51820"),
    ]


def test_the_file_is_written_only_once_amuled_is_down(node: Node) -> None:
    ports_seen_at_down: list[int] = []
    node.on_down = lambda: ports_seen_at_down.append(tcp_listen_port(node.conf.read_text()))
    node.sync_once(None, now=instant_at(1000))
    assert ports_seen_at_down == [4662]


def test_the_write_keeps_what_amuled_flushed_on_exit(node: Node) -> None:
    def flush() -> None:
        node.conf.write_text(CONF.replace("MaxUpload=42", "MaxUpload=42\nNick=flushed"))

    node.on_down = flush
    node.sync_once(None, now=instant_at(1000))
    assert node.conf.read_text() == with_listen_port(
        CONF.replace("MaxUpload=42", "MaxUpload=42\nNick=flushed"), 51820
    )


def test_the_written_file_stays_private_to_its_owner(node: Node) -> None:
    node.sync_once(None, now=instant_at(1000))
    assert node.conf.stat().st_mode & 0o777 == 0o600


def test_a_down_wait_that_fails_writes_nothing_and_still_starts_amuled(node: Node) -> None:
    node.down_exit = 99
    assert node.sync_once(None, now=instant_at(1000)) == instant_at(1000)
    assert node.commands == [DOWN, UP]
    assert node.conf.read_text() == CONF
    assert node.logger.lines[1:] == [
        LoggedLine("error", "s6-svc -wD -T 60000 -d exited 99: timed out")
    ]


def test_a_write_that_raises_still_starts_amuled_and_is_logged(
    node: Node, monkeypatch: pytest.MonkeyPatch
) -> None:
    def replace(source: str, destination: str) -> None:
        raise OSError("No space left on device")

    monkeypatch.setattr(os, "replace", replace)
    assert node.sync_once(None, now=instant_at(1000)) == instant_at(1000)
    assert node.commands == [DOWN, UP]
    assert node.conf.read_text() == CONF
    assert node.logger.lines[1:] == [
        LoggedLine("error", "amule.conf was not written (No space left on device)")
    ]


def test_the_same_port_calls_no_s6_command(node: Node) -> None:
    node.forwarded_port_reader.forwarded_port = 4662
    assert node.sync_once(instant_at(5), now=instant_at(1000)) == instant_at(5)
    assert node.commands == []


def test_no_forwarded_port_calls_no_s6_command(node: Node) -> None:
    node.forwarded_port_reader.forwarded_port = None
    assert node.sync_once(None, now=instant_at(1000)) is None
    assert node.commands == []


def test_a_restart_within_the_window_calls_no_s6_command(node: Node) -> None:
    assert node.sync_once(instant_at(1000), now=instant_at(1299)) == instant_at(1000)
    assert node.commands == []


def test_a_restart_once_the_window_is_over_goes_ahead(node: Node) -> None:
    assert node.sync_once(instant_at(1000), now=instant_at(1300)) == instant_at(1300)
    assert node.commands == [DOWN, UP]


class _Stop(Exception):
    pass


def test_the_start_sends_up_before_the_first_round_then_polls_every_60s(node: Node) -> None:
    def stop_at_the_second_sleep() -> None:
        if len(node.monotonic_clock.sleeps) == 2:
            raise _Stop

    node.forwarded_port_reader.forwarded_port = 4662
    node.forwarded_port_reader.on_read = lambda: node.commands.append(["read forwarded port"])
    node.monotonic_clock.on_sleep = stop_at_the_second_sleep
    with pytest.raises(_Stop):
        node.main()
    gluetun = ["read forwarded port"]
    assert node.commands == [UP, gluetun, gluetun]
    assert node.monotonic_clock.sleeps == [timedelta(seconds=60), timedelta(seconds=60)]


def test_the_poll_interval_is_the_settings(node: Node) -> None:
    def stop() -> None:
        raise _Stop

    node.forwarded_port_reader.forwarded_port = 4662
    node.monotonic_clock.on_sleep = stop
    with pytest.raises(_Stop):
        node.main(dataclasses.replace(SETTINGS, poll_interval=timedelta(seconds=5)))
    assert node.monotonic_clock.sleeps == [timedelta(seconds=5)]


def test_the_restart_time_carries_from_one_round_to_the_next(node: Node) -> None:
    def move_the_port_then_stop_at_the_second_sleep() -> None:
        # The first restart wrote 51820; gluetun moving again 60 s later must wait for the window.
        node.forwarded_port_reader.forwarded_port = 51821
        if len(node.monotonic_clock.sleeps) == 2:
            raise _Stop

    node.monotonic_clock.on_sleep = move_the_port_then_stop_at_the_second_sleep
    with pytest.raises(_Stop):
        node.main()
    assert node.commands == [UP, DOWN, UP]


@pytest.mark.parametrize("conf", ["[eMule]\nPort=4662x\n", "Port=4662\n", None])
def test_an_unreadable_amule_conf_calls_no_s6_command_and_is_logged(
    node: Node, conf: str | None
) -> None:
    if conf is None:
        node.conf.unlink()
    else:
        node.conf.write_text(conf)
    assert node.sync_once(instant_at(5), now=instant_at(1000)) == instant_at(5)
    assert node.commands == []
    assert [line.level for line in node.logger.lines] == ["error"]
    assert node.logger.lines[0].message.startswith(
        "amule.conf's port is unreadable, amuled left as is ("
    )
