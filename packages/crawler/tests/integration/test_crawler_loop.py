"""Lightweight end-to-end: the REAL crawl loop against a REAL amuled (spec §8).

Dedicated run: uv run pytest -m orchestration_integration --no-cov
Validates that a real ``CrawlerApp`` built from YAML files (real ``AmuleApiClient`` + real SQLite
DBs) runs ONE full search task against the provided ``amuled`` then stops CLEANLY on a SIGTERM. The
results may be empty (no guaranteed eD2k network access): it is the LOOP (startup, search,
cataloging, bounded shutdown) that is validated, not the richness of the results.
"""

import asyncio
import logging
import signal
from pathlib import Path

import pytest

from p2pwatch.composition.app import CrawlerApp
from tests.integration.conftest import ApiEndpoint

pytestmark = pytest.mark.orchestration_integration

_DEPLOY = Path(__file__).resolve().parents[4] / "deploy"
# One keyword: a Kad search lasts 45 s at most, so one returns within a minute.
_CONFIG = """\
shutdown_deadline_seconds: 30.0
search:
  keywords: [titar]
  backoff: {{base_seconds: 2.0, cap_seconds: 60.0, factor: 2.0, jitter_ratio: 0.3}}
amule_api_password: ${{AMULE_API_PASSWORD}}
catalog_db_path: {data}/catalog.db
local_db_path: {data}/local.db
webui:
  enabled: false
"""
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
async def test_real_loop_runs_one_search_and_stops(
    amuled: ApiEndpoint, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config_path = tmp_path / "crawler.yml"
    config_path.write_text(_CONFIG.format(data=tmp_path), encoding="utf-8")
    app = CrawlerApp(
        webui_address=("127.0.0.1", 0),
        amule_api_address=(amuled.host, amuled.port),
        env={"AMULE_API_PASSWORD": amuled.password},
    )
    handler = _SearchRecordedHandler()
    search_worker_logger = logging.getLogger(_SEARCH_WORKER_LOGGER)
    search_worker_logger.addHandler(handler)
    level = search_worker_logger.level
    search_worker_logger.setLevel(logging.INFO)
    default_sigterm = signal.getsignal(signal.SIGTERM)
    try:
        # caplog restores the root level the config sets.
        with caplog.at_level(logging.INFO):
            run = asyncio.create_task(
                app.crawl(
                    config_path=config_path,
                    targets_path=_DEPLOY / "targets.yml",
                    matcher_path=_DEPLOY / "matcher.yml",
                )
            )
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
