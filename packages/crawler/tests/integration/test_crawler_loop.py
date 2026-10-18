"""Lightweight end-to-end: the REAL crawl loop against a REAL amuled (spec §8).

Dedicated run: uv run pytest -m orchestration_integration --no-cov
Validates that a real ``CrawlerApp`` (real ``AmuleApiClient`` + real SQLite DBs) runs
ONE full search task against the provided ``amuled`` then stops CLEANLY on a SIGTERM. The
results may be empty (no guaranteed eD2k network access): it is the LOOP (startup, search,
cataloging, bounded shutdown) that is validated, not the richness of the results.
"""

import asyncio
import logging
import signal
from pathlib import Path

import pytest

from catalog_matching.models import TargetSegment
from catalog_matching.validation import parse_matcher_config
from p2pwatch.adapters.config.crawler_config import (
    BackoffConfig,
    CrawlerConfig,
    SearchConfig,
    WebuiConfig,
)
from p2pwatch.adapters.config.yaml_loader import load_yaml
from p2pwatch.adapters.monotonic_clock_asyncio import AsyncioMonotonicClock
from p2pwatch.adapters.rng_random import SeededRng
from p2pwatch.adapters.wake_hub_asyncio import AsyncioWakeHub
from p2pwatch.adapters.wall_clock_system import SystemWallClock
from p2pwatch.composition.app import CrawlerApp
from tests.integration.conftest import ApiEndpoint

pytestmark = pytest.mark.orchestration_integration

_MATCHER = Path(__file__).resolve().parents[4] / "deploy" / "matcher.yml"
_TARGETS = (
    TargetSegment(
        season=2,
        seasonal_number=11,
        absolute_number=62,
        letter="A",
        title="Les demoiselles cambrioleuses",
    ),
)
_SEARCH_WORKER_LOGGER = "p2pwatch.application.search_worker"


class _SearchRecordedHandler(logging.Handler):
    """Sets ``recorded`` on the line a search logs once it returned and was recorded.

    A refused search does not count: a daemon off eD2k refuses every ed2k search at once, and
    logs a warning instead."""

    def __init__(self) -> None:
        super().__init__()
        self.recorded = asyncio.Event()

    def emit(self, record: logging.LogRecord) -> None:
        if "verdict(s) changed" in record.getMessage():
            self.recorded.set()


@pytest.mark.asyncio
async def test_real_loop_runs_one_search_and_stops(amuled: ApiEndpoint, tmp_path: Path) -> None:
    matcher_config = parse_matcher_config(load_yaml(_MATCHER))
    crawler_config = CrawlerConfig(
        # One keyword: a Kad search lasts 45 s at most, so one returns within a minute.
        search=SearchConfig(
            keywords=("titar",),
            backoff=BackoffConfig(base_seconds=2.0, cap_seconds=60.0, factor=2.0, jitter_ratio=0.3),
        ),
        shutdown_deadline_seconds=30.0,
        amule_api_password=amuled.password,
        catalog_db_path=str(tmp_path / "catalog.db"),
        local_db_path=str(tmp_path / "local.db"),
        node_id=None,
        webui=WebuiConfig(enabled=False),
    )
    app = CrawlerApp(
        crawler_config=crawler_config,
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=SystemWallClock(),
        monotonic_clock=AsyncioMonotonicClock(),
        rng=SeededRng(),
        wake_hub=AsyncioWakeHub(),
        policy_fingerprint="test-policy-fingerprint",
        webui_address=("127.0.0.1", 0),
        amule_api_address=(amuled.host, amuled.port),
    )
    handler = _SearchRecordedHandler()
    search_worker_logger = logging.getLogger(_SEARCH_WORKER_LOGGER)
    search_worker_logger.addHandler(handler)
    level = search_worker_logger.level
    search_worker_logger.setLevel(logging.INFO)
    default_sigterm = signal.getsignal(signal.SIGTERM)
    try:
        run = asyncio.create_task(app.run())
        # Without this wait, the test passed before any search even returned.
        await asyncio.wait_for(handler.recorded.wait(), timeout=150.0)
        assert signal.getsignal(signal.SIGTERM) is not default_sigterm
        signal.raise_signal(signal.SIGTERM)
        await asyncio.wait_for(run, timeout=30.0)
    finally:
        search_worker_logger.setLevel(level)
        search_worker_logger.removeHandler(handler)
    assert (tmp_path / "catalog.db").exists()
    assert (tmp_path / "local.db").exists()
