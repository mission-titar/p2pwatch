"""Lot 4 inventory: extra probes of today's behaviour. A pass proves the current behaviour."""

import asyncio
import errno
import os
import signal
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.adapters.driven.asyncio_run_state_store import AsyncioRunStateStore
from p2pwatch.adapters.driven.persistence_sqlite.errors import MigrationError
from p2pwatch.adapters.driving.process.posix_process import PosixProcess
from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.catalog_reevaluator import CatalogReevaluator
from p2pwatch.application.steps.search_worker import SearchTask, SearchWorker
from p2pwatch.application.use_cases.request_shutdown import RequestShutdown
from p2pwatch.domain.client_errors import ClientAuthError
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword, NodeId
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.adapters.driving.cli.test_argparse_command_line import _command_line
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_policy_fingerprint_store import FakePolicyFingerprintStore
from tests.fakes.adapters.driven.fake_search_client import FakeSearchClient, make_search_failed
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.composition.fake_crawler_runner import FakeCrawlerRunner
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

_POLICY = BackoffPolicy(base_seconds=2.0, cap_seconds=300.0, factor=2.0, jitter_ratio=0.0)
_FILES = 50


def _observation(index: int) -> FileObservation:
    return FileObservation(
        reported_file=ReportedFile(
            file=FileKey(network=Network.ED2K, native_id=f"{index:032x}"),
            filename="a.avi",
            size_bytes=1,
            source_count=1,
            keyword=Keyword("keroro"),
        ),
        observed_at=datetime(2026, 11, 1, tzinfo=UTC),
        node_id=NodeId("n1"),
    )


class _SigtermAtFirstFileScan:
    def read_file_count(self) -> int:
        return _FILES

    def iter_latest_observations(self) -> Iterator[FileObservation]:
        for index in range(_FILES):
            if index == 0:
                os.kill(os.getpid(), signal.SIGTERM)
            yield _observation(index)


class _RecordingJudge:
    def __init__(self, run_state: AsyncioRunStateStore, *, yields: bool) -> None:
        self._run_state = run_state
        self._yields = yields
        self.seen: list[bool] = []

    async def rejudge(self, *args: object, **kwargs: object) -> int:
        self.seen.append(self._run_state.is_shutdown_requested())
        if self._yields:
            await asyncio.sleep(0)  # noqa: TID251
        return 0


async def _reevaluate_under_sigterm(*, yields: bool) -> tuple[list[bool], bool, object]:
    run_state = AsyncioRunStateStore(loop=asyncio.get_running_loop())
    judge = _RecordingJudge(run_state, yields=yields)
    fingerprints = FakePolicyFingerprintStore(stored_fingerprint="old")
    reevaluator = CatalogReevaluator(
        policy_fingerprint="new",
        policy_fingerprint_reader=fingerprints,
        policy_fingerprint_writer=fingerprints,
        file_judge=judge,  # type: ignore[arg-type]
        catalog_scan_reader=_SigtermAtFirstFileScan(),  # type: ignore[arg-type]
        progress_every_files=1000,
        logger=FakeLogger(),
    )
    async with PosixProcess(RequestShutdown(run_state)):
        await reevaluator.reevaluate_if_policy_changed(NodeId("n1"))
        for _ in range(5):
            await asyncio.sleep(0)  # noqa: TID251
        requested_after = run_state.is_shutdown_requested()
    return judge.seen, requested_after, fingerprints.read_policy_fingerprint()


@pytest.mark.asyncio
async def test_sigterm_during_a_reevaluation_that_never_yields_is_seen_only_after_the_pass() -> None:
    seen, requested_after, fingerprint = await _reevaluate_under_sigterm(yields=False)
    print(f"no yield: {len(seen)} files judged, requested seen at any file: {any(seen)}")
    assert len(seen) == _FILES and not any(seen)
    assert requested_after and fingerprint == "new"


@pytest.mark.asyncio
async def test_sigterm_during_a_reevaluation_that_yields_is_seen_but_the_pass_runs_on() -> None:
    seen, requested_after, fingerprint = await _reevaluate_under_sigterm(yields=True)
    first = seen.index(True)
    print(f"yielding: requested seen from file {first}, pass ran {len(seen)}/{_FILES} files")
    assert 0 < first < _FILES and len(seen) == _FILES
    assert requested_after and fingerprint == "new"


@pytest.mark.asyncio
async def test_a_persisted_1024_attempts_overflows_at_the_first_failure_after_a_restart() -> None:
    fake_time = FakeTime()
    key = BackoffKey(client_name=ClientName("amuled"), channel=Channel("ed2k"))
    store = FakeBackoffStateStore()
    store.set_backoff_states(
        {
            key: BackoffState(
                attempts=1024, started_at=fake_time.wall.now() - timedelta(hours=1),
                delay=timedelta(seconds=300),
            )
        }
    )
    registry = BackoffRegistry(
        _POLICY,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        jitter_generator=FakeJitterGenerator(),
        backoff_state_reader=store,
    )
    registry.resume_waits()
    worker = SearchWorker(
        client_name=ClientName("amuled"),
        client=FakeSearchClient(search_failures=[make_search_failed()]),
        backoff=registry,
        cataloguer=None,  # type: ignore[arg-type]
        observability_dispatcher=ObservabilityOverFakes().dispatcher,
        logger=FakeLogger(),
    )
    with pytest.raises(OverflowError):
        await worker.run_task(
            SearchTask(keyword=Keyword("keroro"), channel=Channel("ed2k")), node_id=NodeId("n1")
        )
    assert registry.snapshot()[key].attempts == 1024


def test_crawl_reports_any_timeout_error_as_the_deadline_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for failure in (TimeoutError("an amuleapi bug"), OSError(errno.ETIMEDOUT, "statvfs on NFS")):
        assert _command_line(FakeCrawlerRunner(failure)).run(["crawl"]) == 0
        assert "Shutdown deadline elapsed" in capsys.readouterr().err


@pytest.mark.parametrize(
    "failure",
    [
        ExceptionGroup("loops", [TimeoutError("a loop")]),
        ExceptionGroup("loops", [RuntimeError("a loop bug")]),
        ClientAuthError("amuleapi refused the admin password"),
        MigrationError("database newer than the code"),
        RuntimeError("startup bug"),
    ],
    ids=["group-timeout", "group-bug", "auth", "migration", "bare-bug"],
)
def test_crawl_lets_everything_else_escape_the_command_line(failure: Exception) -> None:
    with pytest.raises(type(failure)):
        _command_line(FakeCrawlerRunner(failure)).run(["crawl"])
