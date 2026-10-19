"""TDD tests for the read-only SQL console's ``/console`` + ``/console.csv`` routes (spec §11),
built with the shared webui fixtures + a no-op control."""

from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette

from catalog_matching.domain.config import MatcherConfig
from catalog_matching.domain.models import TargetSegment
from catalog_matching.domain.validation import parse_matcher_config, parse_targets
from p2pwatch.adapters.driving.webui.app import build_app
from p2pwatch.domain.node_state import NodeState
from p2pwatch.ports.driven.clock import MonotonicClock
from p2pwatch.ports.driving.crawl_summarizer import CrawlSummary
from p2pwatch.ports.driving.file_lister import FileListing
from p2pwatch.ports.driving.node_describer import NodeDescription
from p2pwatch_testing.application.fakes import (
    FakeCrawlControls,
    FakeCrawlSummarizer,
    FakeFileLister,
    FakeNodeDescriber,
    FakeTime,
    TickingMonotonicClock,
)
from p2pwatch_testing.catalog_rows import insert_file

pytestmark = pytest.mark.usefixtures("close_test_connections")

_HASH_A = "a" * 32
# A few hundredths of a second of real time, past a 5 s budget on a TickingMonotonicClock.
_PAST_BUDGET_SQL = (
    "WITH RECURSIVE r(i) AS (SELECT 0 UNION ALL SELECT i + 1 FROM r WHERE i < 100000)"
    " SELECT count(*) FROM r"
)

# ---------------------------------------------------------------------------
# Route fixtures
# ---------------------------------------------------------------------------


def _targets() -> tuple[TargetSegment, ...]:
    return parse_targets(
        yaml.safe_load(
            """\
episodes:
  - season: 2
    seasonal_number: 11
    absolute_number: 62
    segments:
      - letter: a
        title: "La Grenouille Cosmique"
"""
        )
    )


def _matcher() -> MatcherConfig:
    return parse_matcher_config(
        yaml.safe_load(
            """\
tokens:
  keroro:
    keyword: keroro
rules:
  - name: catalog
    tier: catalog
    scope: unattributed
    any:
      - keroro
"""
        )
    )


def _build(catalog_db: Path, local_db: Path, monotonic_clock: MonotonicClock) -> Starlette:
    matcher_config = _matcher()
    targets = _targets()
    import p2pwatch.adapters.driving.webui

    templates_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent / "templates"
    static_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent / "static"
    controls = FakeCrawlControls()  # the console routes never call them
    node_state = NodeState(node_id=None, created_at=None, downloads=(), backoff_state_by_key={})
    return build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        crawl_pauser=controls,
        crawl_resumer=controls,
        shutdown_requester=controls,
        crawl_summarizer=FakeCrawlSummarizer(CrawlSummary((), False, node_state, ())),
        node_describer=FakeNodeDescriber(NodeDescription(node_state)),
        file_lister=FakeFileLister(FileListing((), False, 0, 0, {})),
        amule_url="http://localhost:4711",
        wall_clock=FakeTime().wall,
        monotonic_clock=monotonic_clock,
        source_period_gap=timedelta(seconds=90),
    )


@pytest.fixture
def console_app(catalog_db: Path, local_db: Path) -> Starlette:
    """App wired against real (schema-only) DBs, plus one catalog file + one backoff row so
    both DBs return something readable through the console."""
    import sqlite3

    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, _HASH_A, 10)
    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO backoff_states VALUES ('seeded-client', NULL, 1, 0, 1.0)")
        conn.commit()
    return _build(catalog_db, local_db, FakeTime().monotonic)


# ---------------------------------------------------------------------------
# GET /console
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_console_renders_empty_form(console_app: Starlette) -> None:
    """GET /console -> 200 with the form (textarea, Run, Download CSV, db selector), no result."""
    async with AsyncClient(
        transport=ASGITransport(app=console_app), base_url="http://test"
    ) as client:
        resp = await client.get("/console")
    assert resp.status_code == 200
    assert 'name="sql"' in resp.text
    assert 'name="db"' in resp.text
    assert ">Run<" in resp.text
    assert "Download CSV" in resp.text
    assert 'formaction="/console.csv"' in resp.text
    assert 'class="console-error"' not in resp.text
    assert 'class="console-table"' not in resp.text


@pytest.mark.asyncio
async def test_get_console_defaults_to_catalog_selected(console_app: Starlette) -> None:
    """GET /console selects the catalog DB by default."""
    async with AsyncClient(
        transport=ASGITransport(app=console_app), base_url="http://test"
    ) as client:
        resp = await client.get("/console")
    assert resp.status_code == 200
    assert '<option value="catalog" selected>' in resp.text


@pytest.mark.asyncio
async def test_console_nav_entry_links_from_elsewhere_and_is_active_on_console(
    console_app: Starlette,
) -> None:
    """The base nav carries a Console entry: a link (href="/console") from any other page, and
    the active non-link on /console itself, where that href is gone by construction."""
    async with AsyncClient(
        transport=ASGITransport(app=console_app), base_url="http://test"
    ) as client:
        elsewhere = await client.get("/")
        on_console = await client.get("/console")
    assert elsewhere.status_code == 200
    assert '<a href="/console">Console</a>' in elsewhere.text
    assert on_console.status_code == 200
    assert '<span aria-current="page">Console</span>' in on_console.text
    assert '<a href="/console">Console</a>' not in on_console.text


# ---------------------------------------------------------------------------
# POST /console
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_console_valid_select_renders_result(console_app: Starlette) -> None:
    """POST a valid SELECT -> 200, result table with the value, SQL echoed, db still selected."""
    async with AsyncClient(
        transport=ASGITransport(app=console_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/console", data={"sql": "SELECT native_id FROM files", "db": "catalog"}
        )
    assert resp.status_code == 200
    assert _HASH_A in resp.text  # the row value rendered
    assert "SELECT native_id FROM files" in resp.text  # SQL echoed into the textarea
    assert '<option value="catalog" selected>' in resp.text
    assert 'class="console-table"' in resp.text


@pytest.mark.asyncio
async def test_post_console_bogus_db_shows_error_no_query(console_app: Starlette) -> None:
    """POST db=bogus -> 200 with an error banner, no query run (no result table)."""
    async with AsyncClient(
        transport=ASGITransport(app=console_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/console", data={"sql": "SELECT native_id FROM files", "db": "bogus"}
        )
    assert resp.status_code == 200
    assert 'class="console-error"' in resp.text
    assert 'class="console-table"' not in resp.text
    assert _HASH_A not in resp.text


@pytest.mark.asyncio
async def test_post_console_local_db_is_queried(console_app: Starlette) -> None:
    """POST db=local reads local.db (the seeded backoff_states row comes back)."""
    async with AsyncClient(
        transport=ASGITransport(app=console_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/console", data={"sql": "SELECT client_name FROM backoff_states", "db": "local"}
        )
    assert resp.status_code == 200
    assert "seeded-client" in resp.text
    assert '<option value="local" selected>' in resp.text


@pytest.mark.asyncio
async def test_post_console_query_error_shows_error_banner(console_app: Starlette) -> None:
    """A SQL error POSTed to /console renders in the error banner, still HTTP 200."""
    async with AsyncClient(
        transport=ASGITransport(app=console_app), base_url="http://test"
    ) as client:
        resp = await client.post("/console", data={"sql": "SELECT FROM", "db": "catalog"})
    assert resp.status_code == 200
    assert 'class="console-error"' in resp.text
    assert 'class="console-table"' not in resp.text


@pytest.mark.asyncio
async def test_post_console_measures_its_budget_on_the_apps_monotonic_clock(
    catalog_db: Path, local_db: Path
) -> None:
    app = _build(catalog_db, local_db, TickingMonotonicClock(FakeTime()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/console", data={"sql": _PAST_BUDGET_SQL, "db": "catalog"})
    assert resp.status_code == 200
    assert "time limit" in resp.text


@pytest.mark.asyncio
async def test_post_console_truncation_banner(console_app: Starlette) -> None:
    """A result over the row cap renders the truncation banner (multi-target end to end via a
    tiny generated set only needs the cap, so we rely on the default cap being small enough)."""
    async with AsyncClient(
        transport=ASGITransport(app=console_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/console",
            data={
                "sql": "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r"
                " WHERE x < 2000) SELECT x FROM r",
                "db": "catalog",
            },
        )
    assert resp.status_code == 200
    assert 'class="console-truncated"' in resp.text


# ---------------------------------------------------------------------------
# POST /console.csv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_console_csv_valid_select(console_app: Starlette) -> None:
    """POST a valid SELECT to /console.csv -> text/csv attachment with the CSV body."""
    async with AsyncClient(
        transport=ASGITransport(app=console_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/console.csv", data={"sql": "SELECT native_id FROM files", "db": "catalog"}
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert "query.csv" in resp.headers["content-disposition"]
    assert "native_id" in resp.text  # header row
    assert _HASH_A in resp.text  # data row


@pytest.mark.asyncio
async def test_post_console_csv_bad_db_returns_400(console_app: Starlette) -> None:
    """POST /console.csv with an unknown db -> 400 plain text with the error."""
    async with AsyncClient(
        transport=ASGITransport(app=console_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/console.csv", data={"sql": "SELECT native_id FROM files", "db": "bogus"}
        )
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.text != ""


@pytest.mark.asyncio
async def test_post_console_csv_query_error_returns_400(console_app: Starlette) -> None:
    """POST /console.csv with a SQL error -> 400 plain text with the error message."""
    async with AsyncClient(
        transport=ASGITransport(app=console_app), base_url="http://test"
    ) as client:
        resp = await client.post("/console.csv", data={"sql": "SELECT FROM", "db": "catalog"})
    assert resp.status_code == 400
    assert "syntax" in resp.text.lower()
