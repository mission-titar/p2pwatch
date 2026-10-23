"""``FakeTime``: the clock step the monotonic clock's tests rely on; ``FakeLogger``: its lines;
``FakeDecisionReader`` and ``FakeObservationReader``: the reads the download loop never makes;
``FakeNoSetStateTrackedDownloadStore``: the state change a cycle never makes;
``FakeSourcePointStore``: the latest point the step never reads."""

from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import SourceReading
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_no_set_state_tracked_download_store import (
    FakeNoSetStateTrackedDownloadStore,
)
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_source_point_store import FakeSourcePointStore
from tests.fakes.adapters.driven.fake_time import FakeTime

_T0 = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)


def test_a_wall_clock_step_leaves_the_monotonic_clock() -> None:
    fake_time = FakeTime()
    wall_before, monotonic_before = fake_time.wall.now(), fake_time.monotonic.now()

    fake_time.step_wall(timedelta(hours=-1))

    assert fake_time.wall.now() == wall_before - timedelta(hours=1)
    assert fake_time.monotonic.now() == monotonic_before


@pytest.mark.asyncio
async def test_a_monotonic_sleep_records_its_duration_and_moves_both_clocks() -> None:
    fake_time = FakeTime()
    wall_before, monotonic_before = fake_time.wall.now(), fake_time.monotonic.now()

    await fake_time.monotonic.sleep(timedelta(seconds=60))

    assert fake_time.sleeps == [timedelta(seconds=60)]
    assert fake_time.wall.now() == wall_before + timedelta(seconds=60)
    assert fake_time.monotonic.now() == monotonic_before + timedelta(seconds=60)


def test_a_logged_line_keeps_its_level_and_its_formatted_message() -> None:
    logger = FakeLogger()

    logger.info("searched '%s'", "keroro")
    logger.warning("backoff %.1fs", 2.0)
    logger.error("100% lost")

    assert logger.lines == [
        LoggedLine("info", "searched 'keroro'"),
        LoggedLine("warning", "backoff 2.0s"),
        LoggedLine("error", "100% lost"),  # no argument: kept as written, as logging does
    ]


def test_the_catalog_reads_refuse_what_the_download_loop_never_reads() -> None:
    file = FileKey(Network.ED2K, "a" * 32)

    with pytest.raises(AssertionError, match="decisions"):
        FakeDecisionReader().read_latest_decisions(file)
    with pytest.raises(AssertionError, match="filenames"):
        FakeObservationReader().read_known_filenames(file)


def test_the_store_refuses_the_state_change_a_cycle_never_makes() -> None:
    with pytest.raises(AssertionError, match="set_state"):
        FakeNoSetStateTrackedDownloadStore().set_state(
            FileKey(Network.ED2K, "a" * 32), DownloadState.FAILED
        )


def test_the_source_point_store_refuses_the_latest_point_the_step_never_reads() -> None:
    file = FileKey(Network.ED2K, "a" * 32)
    reading = SourceReading(None, "peer", None, None, None, None, (), 0)
    with pytest.raises(AssertionError, match="latest point"):
        FakeSourcePointStore().read_latest_point(file, reading, _T0, _T0, "n1")
