"""Tests for the startup re-evaluation gate ``reevaluate_if_policy_changed`` (spec §7.1, Task 6).

A fake local-state repo (full ``LocalStateRepository`` structural satisfaction: only
``reevaluated_policy_fingerprint``/``set_reevaluated_policy_fingerprint`` are exercised here,
the rest are unused stubs) + a plain async callable standing in for ``reevaluate_catalog``. No real
SQLite/engine needed: the gate is pure orchestration over the port + the injected callable.
"""

import logging
from datetime import datetime

import pytest

from p2pwatch.application.reevaluate_catalog import ReevaluationSummary
from p2pwatch.application.reevaluate_if_policy_changed import reevaluate_if_policy_changed

_SUMMARY = ReevaluationSummary(files_evaluated=3, rows_written=1)
_LOGGER = "p2pwatch.application.reevaluate_if_policy_changed"


def _messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == _LOGGER]


class FakeLocalRepo:
    """Full ``LocalStateRepository`` stub: only the fingerprint methods matter here."""

    def __init__(self, *, stored_policy: str | None) -> None:
        self._stored_policy = stored_policy
        self.set_calls: list[str] = []

    def get_or_create_node_id(self, created_at: datetime) -> str:
        return "node"

    def reevaluated_policy_fingerprint(self) -> str | None:
        return self._stored_policy

    def set_reevaluated_policy_fingerprint(self, fingerprint: str) -> None:
        self.set_calls.append(fingerprint)
        self._stored_policy = fingerprint


@pytest.mark.asyncio
async def test_marker_matches_fingerprint_skips_backfill(caplog: pytest.LogCaptureFixture) -> None:
    local_repo = FakeLocalRepo(stored_policy="abc")
    calls = 0

    async def reevaluate() -> ReevaluationSummary:
        nonlocal calls
        calls += 1
        return _SUMMARY

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        await reevaluate_if_policy_changed(
            fingerprint="abc", local_repo=local_repo, reevaluate=reevaluate
        )
    assert _messages(caplog) == ["policy unchanged: catalogue re-evaluation skipped"]
    assert calls == 0
    assert local_repo.set_calls == []


@pytest.mark.asyncio
async def test_marker_absent_runs_backfill_then_stores_fingerprint(
    caplog: pytest.LogCaptureFixture,
) -> None:
    local_repo = FakeLocalRepo(stored_policy=None)
    calls = 0

    async def reevaluate() -> ReevaluationSummary:
        nonlocal calls
        calls += 1
        return _SUMMARY

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        await reevaluate_if_policy_changed(
            fingerprint="abc", local_repo=local_repo, reevaluate=reevaluate
        )
    assert _messages(caplog) == ["catalogue re-evaluated: 3 files, 1 rows written"]
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
        fingerprint="new-fingerprint", local_repo=local_repo, reevaluate=reevaluate
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
            fingerprint="abc", local_repo=local_repo, reevaluate=boom
        )
    assert local_repo.set_calls == []
