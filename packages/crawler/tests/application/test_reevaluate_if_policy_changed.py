"""Tests for the startup re-evaluation gate ``reevaluate_if_policy_changed`` (spec §7.1, Task 6).

A fake local-state repo (``LocalStateRepository``'s two fingerprint methods) + a plain async
callable standing in for ``reevaluate_catalog``. No real SQLite/engine needed: the gate is pure
orchestration over the port + the injected callable.
"""

import pytest

from p2pwatch.application.reevaluate_catalog import ReevaluationSummary
from p2pwatch.application.reevaluate_if_policy_changed import reevaluate_if_policy_changed
from p2pwatch_testing.application.fakes import FakeLogger, LoggedLine

_SUMMARY = ReevaluationSummary(files_evaluated=3, rows_written=1)


class FakeLocalRepo:
    """``LocalStateRepository`` stub: keeps the fingerprint it is given."""

    def __init__(self, *, stored_policy: str | None) -> None:
        self._stored_policy = stored_policy
        self.set_calls: list[str] = []

    def reevaluated_policy_fingerprint(self) -> str | None:
        return self._stored_policy

    def set_reevaluated_policy_fingerprint(self, fingerprint: str) -> None:
        self.set_calls.append(fingerprint)
        self._stored_policy = fingerprint


@pytest.mark.asyncio
async def test_marker_matches_fingerprint_skips_backfill() -> None:
    local_repo = FakeLocalRepo(stored_policy="abc")
    logger = FakeLogger()
    calls = 0

    async def reevaluate() -> ReevaluationSummary:
        nonlocal calls
        calls += 1
        return _SUMMARY

    await reevaluate_if_policy_changed(
        fingerprint="abc", local_repo=local_repo, reevaluate=reevaluate, logger=logger
    )
    assert logger.lines == [LoggedLine("info", "policy unchanged: catalogue re-evaluation skipped")]
    assert calls == 0
    assert local_repo.set_calls == []


@pytest.mark.asyncio
async def test_marker_absent_runs_backfill_then_stores_fingerprint() -> None:
    local_repo = FakeLocalRepo(stored_policy=None)
    logger = FakeLogger()
    calls = 0

    async def reevaluate() -> ReevaluationSummary:
        nonlocal calls
        calls += 1
        return _SUMMARY

    await reevaluate_if_policy_changed(
        fingerprint="abc", local_repo=local_repo, reevaluate=reevaluate, logger=logger
    )
    assert logger.lines == [LoggedLine("info", "catalogue re-evaluated: 3 files, 1 rows written")]
    assert calls == 1
    assert local_repo.set_calls == ["abc"]


@pytest.mark.asyncio
async def test_marker_differs_from_fingerprint_runs_backfill() -> None:
    local_repo = FakeLocalRepo(stored_policy="old-fingerprint")
    calls = 0

    async def reevaluate() -> ReevaluationSummary:
        nonlocal calls
        calls += 1
        return _SUMMARY

    await reevaluate_if_policy_changed(
        fingerprint="new-fingerprint",
        local_repo=local_repo,
        reevaluate=reevaluate,
        logger=FakeLogger(),
    )
    assert calls == 1
    assert local_repo.set_calls == ["new-fingerprint"]


@pytest.mark.asyncio
async def test_run_backfill_raising_propagates_and_marker_not_set() -> None:
    local_repo = FakeLocalRepo(stored_policy=None)

    async def boom() -> ReevaluationSummary:
        raise RuntimeError("re-evaluation exploded")

    with pytest.raises(RuntimeError, match="re-evaluation exploded"):
        await reevaluate_if_policy_changed(
            fingerprint="abc", local_repo=local_repo, reevaluate=boom, logger=FakeLogger()
        )
    assert local_repo.set_calls == []
