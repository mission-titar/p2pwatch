"""The real assembly, run against the amuleapi fake on a loopback socket: what no unit test sees."""

import asyncio
import json
import logging
import re
import signal
import socket
import threading
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from catalog_matching.config import MatcherConfig
from catalog_matching.models import TargetSegment
from catalog_matching.validation import parse_matcher_config
from p2pwatch.adapters.config.crawler_config import (
    BackoffConfig,
    CrawlerConfig,
    DownloadConfig,
    MetricsConfig,
    ObservabilityConfig,
    SearchConfig,
    WebuiConfig,
)
from p2pwatch.adapters.config.yaml_loader import load_yaml
from p2pwatch.adapters.monotonic_clock_asyncio import AsyncioMonotonicClock
from p2pwatch.adapters.persistence_sqlite.connection import open_catalog
from p2pwatch.adapters.rng_random import SeededRng
from p2pwatch.adapters.wake_hub_asyncio import AsyncioWakeHub
from p2pwatch.adapters.wall_clock_system import SystemWallClock
from p2pwatch.composition.app import CrawlerApp
from p2pwatch_testing.adapters.mule_api.api_fakes import (
    PASSWORD,
    FakeAmuleApi,
    FakeAmuleApiServer,
)
from p2pwatch_testing.catalog_rows import observation_node_ids

_TARGETS = (
    TargetSegment(
        season=2,
        seasonal_number=11,
        absolute_number=62,
        letter="A",
        title="Les demoiselles cambrioleuses",
    ),
)
_MATCHER = Path(__file__).resolve().parents[4] / "deploy" / "matcher.yml"
_HASH = "0123456789abcdef0123456789abcdef"
_RESULT = {
    "hash": _HASH,
    "name": "Keroro N°062A Les demoiselles cambrioleuses.avi",
    "size_bytes": 367_001_600,
    "sources": {"total": 3},
}
_WEBUI_OFF = WebuiConfig(enabled=False)
_WEBUI_SERVING = re.compile(r"^webui serving on (.+):(\d+) \(own thread\)$")
# Far beyond what the fake takes to see each step: only a broken assembly ever reaches it.
_WAIT_SECONDS = 10.0


@pytest.fixture
def matcher_config() -> MatcherConfig:
    return parse_matcher_config(load_yaml(_MATCHER))


def _crawler_config(
    tmp_path: Path,
    *,
    keywords: tuple[str, ...],
    node_id: str | None = None,
    metrics_port: int | None = None,
    download: DownloadConfig | None = None,
    webui: WebuiConfig = _WEBUI_OFF,
) -> CrawlerConfig:
    metrics = None if metrics_port is None else MetricsConfig(enabled=True, port=metrics_port)
    return CrawlerConfig(
        search=SearchConfig(
            keywords=keywords,
            backoff=BackoffConfig(base_seconds=2.0, cap_seconds=60.0, factor=2.0, jitter_ratio=0.0),
        ),
        shutdown_deadline_seconds=_WAIT_SECONDS,
        amule_api_password=PASSWORD,
        catalog_db_path=str(tmp_path / "catalog.db"),
        local_db_path=str(tmp_path / "local.db"),
        node_id=node_id,
        observability=ObservabilityConfig(
            log_level="INFO", metrics=metrics, notification_timeout_seconds=5.0, notifications=()
        ),
        download=download,
        webui=webui,
    )


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


def _app(
    crawler_config: CrawlerConfig,
    matcher_config: MatcherConfig,
    server: FakeAmuleApiServer,
) -> CrawlerApp:
    return CrawlerApp(
        crawler_config=crawler_config,
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=SystemWallClock(),
        monotonic_clock=AsyncioMonotonicClock(),
        rng=SeededRng(),
        wake_hub=AsyncioWakeHub(),
        policy_fingerprint="wiring-policy-fingerprint",
        webui_address=("127.0.0.1", 0),
        amule_api_address=(server.host, server.port),
    )


def _webui_bound_address(messages: list[str]) -> tuple[str, int]:
    matches = [match for match in map(_WEBUI_SERVING.match, messages) if match is not None]
    assert len(matches) == 1, messages
    return matches[0].group(1), int(matches[0].group(2))


def _search_types(api: FakeAmuleApi) -> list[str]:
    """The type of every ``POST /search`` the fake saw, in order."""
    return [
        json.loads(request.content)["type"]
        for request in api.requests
        if request.method == "POST" and request.url.path == "/api/v1/search"
    ]


def _searches_read(api: FakeAmuleApi) -> int:
    """How many searches had their result rows read, past the zero-row progress reads."""
    paths = {
        request.url.path
        for request in api.requests
        if request.url.path.endswith("/results") and request.url.params.get("limit") != "0"
    }
    return len(paths)


@pytest.mark.asyncio
async def test_full_mode_catalogues_queues_serves_the_webui_and_metrics_and_stops_on_restart(
    tmp_path: Path, matcher_config: MatcherConfig, caplog: pytest.LogCaptureFixture
) -> None:
    download = DownloadConfig(
        poll_interval_seconds=30.0,
        min_free_bytes=1,
        lost_after=timedelta(hours=24),
        output_dir=str(tmp_path),
        reappeared_after=timedelta(hours=12),
        sources_interval=timedelta(minutes=5),
    )
    metrics_port = _free_port()
    crawler_config = _crawler_config(
        tmp_path,
        keywords=("keroro",),
        node_id="wired-node",
        metrics_port=metrics_port,
        download=download,
        webui=WebuiConfig(enabled=True),
    )
    api = FakeAmuleApi(results=[_RESULT])

    with FakeAmuleApiServer(api) as server, caplog.at_level(logging.INFO):
        run = asyncio.create_task(_app(crawler_config, matcher_config, server).run())
        assert await asyncio.to_thread(
            server.wait_for, lambda seen: bool(seen.added_links), _WAIT_SECONDS
        )
        host, port = _webui_bound_address(caplog.messages)
        async with httpx.AsyncClient() as http:
            metrics = await http.get(f"http://127.0.0.1:{metrics_port}/metrics")
            restart = await http.post(f"http://{host}:{port}/controls/restart")
        await asyncio.wait_for(run, _WAIT_SECONDS)

    assert api.logins > 0
    assert len(api.added_links) == 1 and _HASH in api.added_links[0].lower()
    catalog = open_catalog(tmp_path / "catalog.db")
    assert observation_node_ids(catalog) == {"wired-node"}
    catalog.close()
    assert (host, port != 8080) == ("127.0.0.1", True)
    assert "p2pwatch_observations_total{" in metrics.text
    assert restart.status_code == 303
    assert not any(thread.name == "webui" for thread in threading.enumerate())


@pytest.mark.asyncio
async def test_observer_mode_starts_one_ed2k_search_of_two_keywords_until_a_sigterm(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    # Both keywords' ed2k searches share one client, which spaces their starts by a minute: two
    # clients would start both at once and break the network's pacing.
    crawler_config = _crawler_config(tmp_path, keywords=("keroro", "titar"))
    api = FakeAmuleApi()
    default_sigterm = signal.getsignal(signal.SIGTERM)

    with FakeAmuleApiServer(api) as server:
        run = asyncio.create_task(_app(crawler_config, matcher_config, server).run())
        # The first ed2k search and both Kad ones, each read to its end.
        assert await asyncio.to_thread(
            server.wait_for, lambda seen: _searches_read(seen) >= 3, _WAIT_SECONDS
        )
        assert signal.getsignal(signal.SIGTERM) is not default_sigterm
        signal.raise_signal(signal.SIGTERM)
        await asyncio.wait_for(run, _WAIT_SECONDS)

    assert _search_types(api).count("global") == 1
