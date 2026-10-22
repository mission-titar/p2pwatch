"""Tests for the startup re-evaluation gate ``reevaluate_if_policy_changed`` (spec §7.1, Task 6).

A fake fingerprint store (both policy fingerprint ports) + a plain async
callable standing in for ``reevaluate_catalog``. No real SQLite/engine needed: the gate is pure
orchestration over the port + the injected callable.
"""

import pytest

from p2pwatch.application.reevaluate_catalog import ReevaluationSummary
from p2pwatch.application.reevaluate_if_policy_changed import reevaluate_if_policy_changed
from tests.fakes.application.fakes import FakeLogger, FakePolicyFingerprintStore, LoggedLine

_SUMMARY = ReevaluationSummary(files_evaluated=3, rows_written=1)


@pytest.mark.asyncio
async def test_marker_matches_fingerprint_skips_backfill() -> None:
    fingerprints = FakePolicyFingerprintStore(stored_fingerprint="abc")
    logger = FakeLogger()
    calls = 0

    async def reevaluate() -> ReevaluationSummary:
        nonlocal calls
        calls += 1
        return _SUMMARY

    await reevaluate_if_policy_changed(
        fingerprint="abc",
        policy_fingerprint_reader=fingerprints,
        policy_fingerprint_writer=fingerprints,
        reevaluate=reevaluate,
        logger=logger,
    )
    assert logger.lines == [LoggedLine("info", "policy unchanged: catalogue re-evaluation skipped")]
    assert calls == 0
    assert fingerprints.set_calls == []


@pytest.mark.asyncio
async def test_marker_absent_runs_backfill_then_stores_fingerprint() -> None:
    fingerprints = FakePolicyFingerprintStore(stored_fingerprint=None)
    logger = FakeLogger()
    calls = 0

    async def reevaluate() -> ReevaluationSummary:
        nonlocal calls
        calls += 1
        return _SUMMARY

    await reevaluate_if_policy_changed(
        fingerprint="abc",
        policy_fingerprint_reader=fingerprints,
        policy_fingerprint_writer=fingerprints,
        reevaluate=reevaluate,
        logger=logger,
    )
    assert logger.lines == [LoggedLine("info", "catalogue re-evaluated: 3 files, 1 rows written")]
    assert calls == 1
    assert fingerprints.set_calls == ["abc"]


@pytest.mark.asyncio
async def test_marker_differs_from_fingerprint_runs_backfill() -> None:
    fingerprints = FakePolicyFingerprintStore(stored_fingerprint="old-fingerprint")
    calls = 0

    async def reevaluate() -> ReevaluationSummary:
        nonlocal calls
        calls += 1
        return _SUMMARY

    await reevaluate_if_policy_changed(
        fingerprint="new-fingerprint",
        policy_fingerprint_reader=fingerprints,
        policy_fingerprint_writer=fingerprints,
        reevaluate=reevaluate,
        logger=FakeLogger(),
    )
    assert calls == 1
    assert fingerprints.set_calls == ["new-fingerprint"]


@pytest.mark.asyncio
async def test_run_backfill_raising_propagates_and_marker_not_set() -> None:
    fingerprints = FakePolicyFingerprintStore(stored_fingerprint=None)

    async def boom() -> ReevaluationSummary:
        raise RuntimeError("re-evaluation exploded")

    with pytest.raises(RuntimeError, match="re-evaluation exploded"):
        await reevaluate_if_policy_changed(
            fingerprint="abc",
            policy_fingerprint_reader=fingerprints,
            policy_fingerprint_writer=fingerprints,
            reevaluate=boom,
            logger=FakeLogger(),
        )
    assert fingerprints.set_calls == []
