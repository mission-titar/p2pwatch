"""The real assembly, run against the amuleapi fake on a loopback socket: what no unit test sees."""

import asyncio
import gc
import json
import logging
import re
import signal
import socket
import threading
import warnings
from datetime import timedelta
from http.server import ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog, open_local
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_backoff_state_store import (
    SqliteBackoffStateStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_tracked_download_store import (
    SqliteTrackedDownloadStore,
)
from p2pwatch.adapters.driven.system_wall_clock import SystemWallClock
from p2pwatch.composition.crawler_composition import CrawlerComposition
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.fakes.fake_amule_api import PASSWORD, FakeAmuleApi
from tests.fakes.fake_amule_api_server import FakeAmuleApiServer
from tests.fakes.fake_notification_sink import FakeNotificationSink
from tests.support.catalog_rows import (
    decision_node_ids,
    insert_file,
    insert_observation,
    observation_node_ids,
    source_variant_node_ids,
)

_DEPLOY = Path(__file__).resolve().parents[4] / "deploy"
_MATCHER = _DEPLOY / "matcher.yml"
_SHIPPED_TARGETS = _DEPLOY / "targets.yml"
_TARGET_062A = """\
episodes:
  - season: 2
    seasonal_number: 11
    absolute_number: 62
    segments:
      - { letter: A, title: "Les demoiselles cambrioleuses" }
"""
_HASH = "0123456789abcdef0123456789abcdef"
_RESULT = {
    "hash": _HASH,
    "name": "Keroro N°062A Les demoiselles cambrioleuses.avi",
    "size_bytes": 367_001_600,
    "sources": {"total": 3},
}
_LOGIN = ("POST", "/api/v1/auth/login")
# A million recursion steps: tens of milliseconds at least, far below the console's budget.
_COUNTING_QUERY = (
    "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r WHERE x < 1000000)"
    " SELECT count(*) FROM r"
)
_CONSOLE_ELAPSED = re.compile(r"1 rows in (\d+) ms")
_WEBUI_SERVING = re.compile(r"^webui serving on (.+):(\d+) \(own thread\)$")
# Far beyond what the fake takes to see each step: only a broken assembly ever reaches it.
_WAIT_SECONDS = 10.0


def _config(tmp_path: Path, **sections: object) -> dict[str, Any]:
    """An observer's ``crawler.yml``, one ed2k keyword, ``sections`` replacing its own."""
    return {
        "shutdown_deadline_seconds": _WAIT_SECONDS,
        "search": {
            "keywords": ["keroro"],
            "backoff": {
                "base_seconds": 2.0,
                "cap_seconds": 60.0,
                "factor": 2.0,
                "jitter_ratio": 0.0,
            },
        },
        "amule_api_password": "${AMULE_API_PASSWORD}",
        "catalog_db_path": str(tmp_path / "catalog.db"),
        "local_db_path": str(tmp_path / "local.db"),
        "observability": {"log_level": "INFO"},
    } | sections


def _write(path: Path, config: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


def _crawl(
    server: FakeAmuleApiServer,
    config_path: Path,
    targets_path: Path = _SHIPPED_TARGETS,
    root_logger: logging.Logger | None = None,
) -> asyncio.Task[None]:
    crawler_composition = CrawlerComposition(
        webui_address=("127.0.0.1", 0),
        amule_api_address=(server.host, server.port),
        env={"AMULE_API_PASSWORD": PASSWORD},
        root_logger=root_logger or logging.Logger("root"),
    )
    return asyncio.create_task(
        crawler_composition.run_crawler(
            config_path=config_path, targets_path=targets_path, matcher_path=_MATCHER
        )
    )


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


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


def _send_sigterm(default_handler: object) -> None:
    """Only once the run handles SIGTERM: a missing handler then fails instead of killing pytest."""
    assert signal.getsignal(signal.SIGTERM) is not default_handler
    signal.raise_signal(signal.SIGTERM)


def _searches_read(api: FakeAmuleApi) -> int:
    """How many searches had their result rows read, past the zero-row progress reads."""
    paths = {
        request.url.path
        for request in api.requests
        if request.url.path.endswith("/results") and request.url.params.get("limit") != "0"
    }
    return len(paths)


def _has_logged_out(api: FakeAmuleApi) -> bool:
    return any(request.url.path == "/api/v1/auth/logout" for request in api.requests)


def _has_read_the_status(api: FakeAmuleApi) -> bool:
    return any(request.url.path == "/api/v1/status" for request in api.requests)


async def _crawl_until_a_search_is_read(config_path: Path, targets_path: Path) -> None:
    default_sigterm = signal.getsignal(signal.SIGTERM)
    with FakeAmuleApiServer(FakeAmuleApi()) as server:
        run = _crawl(server, config_path, targets_path)
        assert await asyncio.to_thread(
            server.wait_for, lambda seen: _searches_read(seen) >= 1, _WAIT_SECONDS
        )
        _send_sigterm(default_sigterm)
        await asyncio.wait_for(run, _WAIT_SECONDS)


@pytest.mark.asyncio
async def test_full_mode_catalogues_queues_serves_the_webui_and_metrics_and_stops_on_restart(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    metrics_port = _free_port()
    download = {
        "enabled": True,
        "poll_interval_seconds": 30.0,
        "min_free_bytes": 1,
        "lost_after_seconds": 86400,
        "output_dir": str(tmp_path),
        "reappeared_after_seconds": 43200,
        "sources_interval_seconds": 300,
    }
    config_path = _write(
        tmp_path / "crawler.yml",
        _config(
            tmp_path,
            node_id="wired-node",
            observability={"log_level": "INFO", "metrics": {"enabled": True, "port": metrics_port}},
            download=download,
        ),
    )
    targets_path = tmp_path / "targets.yml"
    targets_path.write_text(_TARGET_062A, encoding="utf-8")
    api = FakeAmuleApi(results=[_RESULT])

    with FakeAmuleApiServer(api) as server, caplog.at_level(logging.INFO):
        run = _crawl(server, config_path, targets_path)
        assert await asyncio.to_thread(
            server.wait_for, lambda seen: bool(seen.added_links), _WAIT_SECONDS
        )
        host, port = _webui_bound_address(caplog.messages)
        async with httpx.AsyncClient() as http:
            metrics = await http.get(f"http://127.0.0.1:{metrics_port}/metrics")
            catalog_query, local_query = [  # each table lives in one database only
                await http.post(f"http://{host}:{port}/console.csv", data=form)
                for form in (
                    {"sql": "SELECT native_id FROM files", "db": "catalog"},
                    {"sql": "SELECT native_id FROM downloads", "db": "local"},
                )
            ]
            dashboard, files, node = [
                await http.get(f"http://{host}:{port}{path}") for path in ("/", "/files", "/node")
            ]
            timed_query = await http.post(
                f"http://{host}:{port}/console", data={"sql": _COUNTING_QUERY, "db": "catalog"}
            )
            restart = await http.post(f"http://{host}:{port}/controls/restart")
        await asyncio.wait_for(run, _WAIT_SECONDS)

    named_messages = [(record.name, record.getMessage()) for record in caplog.records]
    assert (  # each logs under its module's name, which an operator's filters read
        "p2pwatch.composition.crawler_composition",
        f"p2pwatch version {version('p2pwatch')}",
    ) in named_messages
    assert any(
        name == "p2pwatch.application.steps.search_worker" and "verdict(s) changed" in message
        for name, message in named_messages
    )
    assert (
        "p2pwatch.application.crawler_lifecycle",
        "crawler started: node_id=wired-node",
    ) in named_messages
    assert (
        "p2pwatch.application.steps.catalog_reevaluator",
        "catalogue re-evaluated: 0 files, 0 rows written",
    ) in named_messages
    assert (
        "p2pwatch.application.steps.download_decider",
        f"candidate file={_HASH} queued for download",
    ) in named_messages
    assert "🟢 node online (download on)" in caplog.messages
    assert api.logins == 1  # one session per node: it searches, reads the status and downloads
    assert len(api.added_links) == 1 and _HASH in api.added_links[0].lower()
    catalog = open_catalog(tmp_path / "catalog.db")
    assert observation_node_ids(catalog) == {"wired-node"}
    assert decision_node_ids(catalog) == {"wired-node"}
    catalog.close()
    assert (host, port != 8080) == ("127.0.0.1", True)
    assert "p2pwatch_observations_total{" in metrics.text
    assert (catalog_query.status_code, local_query.status_code) == (200, 200)
    assert _HASH in catalog_query.text and _HASH in local_query.text
    assert '<a href="/targets/062A">062A</a>' in dashboard.text  # catalog.db's coverage
    assert f"<dd>{api.version['daemon_version']}</dd>" in dashboard.text  # the status reading store
    assert 'title="Keroro N°062A Les demoiselles cambrioleuses.avi"' in files.text
    assert f"<td>{_HASH}</td>" in node.text  # local.db's tracked download
    elapsed = _CONSOLE_ELAPSED.search(timed_query.text)
    assert elapsed is not None and int(elapsed.group(1)) > 0  # timed on the app's monotonic clock
    assert restart.status_code == 303
    assert not any(thread.name == "webui" for thread in threading.enumerate())
    with warnings.catch_warnings(record=True) as caught:  # the webui's readers left unclosed
        warnings.simplefilter("always")
        gc.collect()
    assert [str(warning.message) for warning in caught] == []


def _has_read_the_sources_then_listed_again(api: FakeAmuleApi) -> bool:
    """The next cycle's listing: the cycle that read the sources has written them."""
    paths = [request.url.path for request in api.requests]
    sources = f"/api/v1/downloads/{_HASH}/clients"
    return sources in paths and "/api/v1/downloads" in paths[paths.index(sources) :]


@pytest.mark.asyncio
async def test_the_download_loop_records_a_tracked_downloads_sources_under_the_nodes_id(
    tmp_path: Path,
) -> None:
    catalog = open_catalog(tmp_path / "catalog.db")
    insert_file(catalog, _HASH)
    catalog.close()
    local = open_local(tmp_path / "local.db")
    SqliteTrackedDownloadStore(local).record_queued(
        FileKey(Network.ED2K, _HASH), "062A", 10, SystemWallClock().now()
    )
    local.close()
    download = {
        "enabled": True,
        "poll_interval_seconds": 0.05,
        "min_free_bytes": 1,
        "lost_after_seconds": 86400,
        "output_dir": str(tmp_path),
        "reappeared_after_seconds": 43200,
    }
    config_path = _write(
        tmp_path / "crawler.yml", _config(tmp_path, node_id="wired-node", download=download)
    )
    listed = {"hash": _HASH, "size_bytes": 10, "completed_bytes": 4, "status": "downloading"}
    source = {"ecid": 1, "name": "peer", "user_hash": "1f" * 16, "role": "downloading_from"}
    api = FakeAmuleApi(downloads=[listed], clients={_HASH: [source]})
    default_sigterm = signal.getsignal(signal.SIGTERM)

    with FakeAmuleApiServer(api) as server:
        run = _crawl(server, config_path)
        assert await asyncio.to_thread(
            server.wait_for, _has_read_the_sources_then_listed_again, _WAIT_SECONDS
        )
        _send_sigterm(default_sigterm)
        await asyncio.wait_for(run, _WAIT_SECONDS)

    catalog = open_catalog(tmp_path / "catalog.db")
    assert source_variant_node_ids(catalog) == {"wired-node"}
    catalog.close()


@pytest.mark.asyncio
async def test_the_nodes_notifications_carry_its_id_in_their_username_and_title(
    tmp_path: Path,
) -> None:
    sink = ThreadingHTTPServer(("127.0.0.1", 0), FakeNotificationSink)
    FakeNotificationSink.received = []
    threading.Thread(target=sink.serve_forever, daemon=True).start()
    notification = {"url": f"json://127.0.0.1:{sink.server_port}/", "audience": "operations"}
    observability = {"log_level": "INFO", "notifications": [notification]}
    config_path = _write(
        tmp_path / "crawler.yml",
        _config(tmp_path, node_id="wired-node", observability=observability),
    )
    default_sigterm = signal.getsignal(signal.SIGTERM)

    with FakeAmuleApiServer(FakeAmuleApi()) as server:
        run = _crawl(server, config_path)
        assert await asyncio.to_thread(
            server.wait_for, lambda seen: _searches_read(seen) >= 1, _WAIT_SECONDS
        )
        _send_sigterm(default_sigterm)
        await asyncio.wait_for(run, _WAIT_SECONDS)
    sink.shutdown()
    sink.server_close()

    assert ("p2pwatch - wired-node", "[wired-node]") in FakeNotificationSink.received


@pytest.mark.asyncio
async def test_observer_mode_crawls_its_config_files_with_one_ed2k_search_until_a_sigterm(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Both keywords' ed2k searches share one client, which spaces their starts by a minute: two
    # clients would start both at once and break the network's pacing.
    config_path = _write(
        tmp_path / "crawler.yml",
        _config(
            tmp_path,
            search=_config(tmp_path)["search"] | {"keywords": ["keroro", "titar"]},
            observability={"log_level": "DEBUG"},
        ),
    )
    api = FakeAmuleApi()
    default_sigterm = signal.getsignal(signal.SIGTERM)
    root_logger = logging.Logger("root")

    with FakeAmuleApiServer(api) as server, caplog.at_level(logging.INFO):
        run = _crawl(server, config_path, root_logger=root_logger)
        # The first ed2k search and both Kad ones, each read to its end.
        assert await asyncio.to_thread(
            server.wait_for, lambda seen: _searches_read(seen) >= 3, _WAIT_SECONDS
        )
        _send_sigterm(default_sigterm)
        await asyncio.wait_for(run, _WAIT_SECONDS)

    assert _search_types(api).count("global") == 1
    assert root_logger.level == logging.DEBUG
    assert "🟢 node online (download off)" in caplog.messages
    assert api.logins == 1
    assert _webui_bound_address(caplog.messages)[0] == "127.0.0.1"  # served in crawl-only too


# The cut close may leave the client's sockets open, as the process exit closes them in production.
@pytest.mark.filterwarnings("ignore:unclosed:ResourceWarning")
def test_the_shutdown_deadline_spares_the_run_then_cuts_a_logout_amuled_never_answers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    deadline_seconds = 0.2
    config_path = _write(
        tmp_path / "crawler.yml", _config(tmp_path, shutdown_deadline_seconds=deadline_seconds)
    )
    api = FakeAmuleApi()
    released = threading.Event()

    def stalled_logout(request: httpx.Request) -> httpx.Response:
        released.wait(_WAIT_SECONDS)
        return httpx.Response(204)

    api.overrides[("POST", "/api/v1/auth/logout")] = stalled_logout
    default_sigterm = signal.getsignal(signal.SIGTERM)

    async def stop_during_the_logout() -> tuple[bool, bool, float]:
        loop = asyncio.get_running_loop()
        with FakeAmuleApiServer(api) as server:
            run = _crawl(server, config_path)
            assert await asyncio.to_thread(
                server.wait_for, lambda seen: _searches_read(seen) >= 1, _WAIT_SECONDS
            )
            # Only time shows an absence: armed from the start, the deadline would end the run.
            await asyncio.sleep(2 * deadline_seconds)
            logged_out_before_the_stop = _has_logged_out(api)
            _send_sigterm(default_sigterm)
            stopped_at = loop.time()
            await asyncio.wait({run}, timeout=2 * _WAIT_SECONDS)
            elapsed = loop.time() - stopped_at
            released.set()
        return logged_out_before_the_stop, isinstance(run.exception(), TimeoutError), elapsed

    with caplog.at_level(logging.INFO):
        logged_out_before_the_stop, timed_out, elapsed = asyncio.run(stop_during_the_logout())
        gc.collect()  # collected here, where the leak is tolerated, not in a later test

    assert not logged_out_before_the_stop
    # Unbounded, the close would wait out the client's own 10 s timeout, then return.
    assert timed_out
    assert elapsed < _WAIT_SECONDS / 2


@pytest.mark.asyncio
async def test_a_backoff_the_previous_run_saved_holds_the_ed2k_search(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    local = open_local(tmp_path / "local.db")
    SqliteBackoffStateStore(local).set_backoff_states(
        {BackoffKey("amuled", "ed2k"): BackoffState(1, SystemWallClock().now(), timedelta(hours=1))}
    )
    local.close()
    config_path = _write(tmp_path / "crawler.yml", _config(tmp_path))
    api = FakeAmuleApi()
    default_sigterm = signal.getsignal(signal.SIGTERM)

    with FakeAmuleApiServer(api) as server, caplog.at_level(logging.INFO):
        run = _crawl(server, config_path)
        # Unheld, the ed2k start goes out with Kad's, well before Kad's search is read to its end.
        assert await asyncio.to_thread(
            server.wait_for, lambda seen: _searches_read(seen) >= 1, _WAIT_SECONDS
        )
        _send_sigterm(default_sigterm)
        await asyncio.wait_for(run, _WAIT_SECONDS)

    assert _search_types(api) == ["kad"]


@pytest.mark.asyncio
async def test_a_pause_from_the_webui_holds_the_searches_until_its_resume(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config_path = _write(tmp_path / "crawler.yml", _config(tmp_path))
    api = FakeAmuleApi()
    login_arrived = threading.Event()
    paused = threading.Event()

    def login_once_paused(request: httpx.Request) -> httpx.Response:
        # Held until the test has paused, so the loops start paused; then answered as usual.
        login_arrived.set()
        paused.wait(_WAIT_SECONDS)
        del api.overrides[_LOGIN]
        return api.handle(request)

    api.overrides[_LOGIN] = login_once_paused

    with FakeAmuleApiServer(api) as server, caplog.at_level(logging.INFO):
        run = _crawl(server, config_path)
        assert await asyncio.to_thread(login_arrived.wait, _WAIT_SECONDS)
        host, port = _webui_bound_address(caplog.messages)
        async with httpx.AsyncClient(base_url=f"http://{host}:{port}") as webui:
            await webui.post("/controls/pause")
            paused.set()
            # The status loop reads on while paused; only time shows that no search starts.
            assert await asyncio.to_thread(server.wait_for, _has_read_the_status, _WAIT_SECONDS)
            await asyncio.sleep(0.5)
            searches_while_paused = _search_types(api)
            await webui.post("/controls/resume")
            assert await asyncio.to_thread(
                server.wait_for, lambda seen: _searches_read(seen) >= 1, _WAIT_SECONDS
            )
            await webui.post("/controls/restart")
        await asyncio.wait_for(run, _WAIT_SECONDS)

    assert searches_while_paused == []


@pytest.mark.asyncio
async def test_a_restart_re_evaluates_the_catalogue_only_once_a_policy_file_changed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config_path = _write(tmp_path / "crawler.yml", _config(tmp_path))
    targets_path = tmp_path / "targets.yml"
    targets_path.write_text(_TARGET_062A, encoding="utf-8")

    with caplog.at_level(logging.INFO):
        await _crawl_until_a_search_is_read(config_path, targets_path)
        await _crawl_until_a_search_is_read(config_path, targets_path)
        targets_path.write_text(f"{_TARGET_062A}# edited\n", encoding="utf-8")
        await _crawl_until_a_search_is_read(config_path, targets_path)

    reevaluations = [
        message
        for message in caplog.messages
        if message.startswith(("catalogue re-evaluated", "policy unchanged"))
    ]
    assert reevaluations == [
        "catalogue re-evaluated: 0 files, 0 rows written",
        "policy unchanged: catalogue re-evaluation skipped",
        "catalogue re-evaluated: 0 files, 0 rows written",
    ]


@pytest.mark.asyncio
async def test_a_re_evaluation_logs_its_progress_under_its_module_s_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    catalog = open_catalog(tmp_path / "catalog.db")
    for index in range(200):  # the composition's progress interval
        native_id = f"{index:032x}"
        insert_file(catalog, native_id)
        insert_observation(catalog, native_id, f"unrelated_{index}.avi")
    catalog.close()
    config_path = _write(tmp_path / "crawler.yml", _config(tmp_path))
    targets_path = tmp_path / "targets.yml"
    targets_path.write_text(_TARGET_062A, encoding="utf-8")

    with caplog.at_level(logging.INFO):
        await _crawl_until_a_search_is_read(config_path, targets_path)

    assert (
        "p2pwatch.application.steps.catalog_reevaluator",
        "catalogue re-evaluation: 200/200 files, 0 rows written",
    ) in [(record.name, record.getMessage()) for record in caplog.records]
