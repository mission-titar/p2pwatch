"""The read-only SQL console's routes, ``/console`` and ``/console.csv`` (spec §11), on a fake of
``ConsoleQueryRunner``: what the form asks it, and how its outcome renders."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient, Response
from starlette.applications import Starlette

from catalog_matching.domain.models import TargetSegment
from catalog_matching.domain.validation import parse_targets
from p2pwatch.adapters.driving.webui.app import build_app
from p2pwatch.domain.console_query import ConsoleDatabase, QueryAnswer, QueryFailure
from p2pwatch.domain.node_state import NodeState
from p2pwatch.ports.driving.console_query_runner import ConsoleQueryOutcome
from p2pwatch.ports.driving.crawl_summarizer import CrawlSummary
from p2pwatch.ports.driving.file_lister import FileListing
from p2pwatch.ports.driving.node_describer import NodeDescription
from p2pwatch.ports.driving.source_lister import SourceListing
from tests.fakes.application.fakes import (
    FakeConsoleQueryRunner,
    FakeCrawlControls,
    FakeCrawlSummarizer,
    FakeFileDescriber,
    FakeFileLister,
    FakeNodeDescriber,
    FakeSourceDescriber,
    FakeSourceLister,
    FakeSourceNameDescriber,
    RunConsoleQueryCall,
)

_HASH_A = "a" * 32
_SQL = "SELECT native_id FROM files"
_ANSWER = QueryAnswer(("native_id",), ((_HASH_A,),), timedelta(milliseconds=3), truncated=False)
_OUTCOME = ConsoleQueryOutcome(_ANSWER, row_cap=1000)
_UNKNOWN_DB = "Unknown database. Choose catalog.db or local.db."

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


def _build(console_query_runner: FakeConsoleQueryRunner) -> Starlette:
    import p2pwatch.adapters.driving.webui

    templates_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent / "templates"
    static_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent / "static"
    controls = FakeCrawlControls()  # the console routes never call them
    node_state = NodeState(node_id=None, created_at=None, downloads=(), backoff_state_by_key={})
    return build_app(
        target_segments=_targets(),
        templates_dir=templates_dir,
        static_dir=static_dir,
        crawl_pauser=controls,
        crawl_resumer=controls,
        shutdown_requester=controls,
        crawl_summarizer=FakeCrawlSummarizer(CrawlSummary((), False, node_state, ())),
        node_describer=FakeNodeDescriber(NodeDescription(node_state)),
        file_lister=FakeFileLister(FileListing((), False, 0, 0, {})),
        file_describer=FakeFileDescriber(None),
        source_lister=FakeSourceLister(SourceListing((), has_next_page=False, source_count=0)),
        source_describer=FakeSourceDescriber(None),
        source_name_describer=FakeSourceNameDescriber(None),
        console_query_runner=console_query_runner,
        amule_url="http://localhost:4711",
    )


async def _get(path: str) -> Response:
    app = _build(FakeConsoleQueryRunner(_OUTCOME))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path)


async def _post(
    path: str, form: dict[str, str], outcome: ConsoleQueryOutcome = _OUTCOME
) -> tuple[Response, list[RunConsoleQueryCall]]:
    """The response to ``form`` posted to ``path``, the runner answering ``outcome``, and the
    runner's calls."""
    console_query_runner = FakeConsoleQueryRunner(outcome)
    app = _build(console_query_runner)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, data=form)
    return response, console_query_runner.calls


# ---------------------------------------------------------------------------
# GET /console
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_console_renders_empty_form() -> None:
    """GET /console -> 200 with the form (textarea, Run, Download CSV, db selector), no answer."""
    resp = await _get("/console")
    assert resp.status_code == 200
    assert 'name="sql"' in resp.text
    assert 'name="db"' in resp.text
    assert ">Run<" in resp.text
    assert "Download CSV" in resp.text
    assert 'formaction="/console.csv"' in resp.text
    assert 'class="console-error"' not in resp.text
    assert 'class="console-table"' not in resp.text


@pytest.mark.asyncio
async def test_get_console_defaults_to_catalog_selected() -> None:
    """GET /console selects the catalog DB by default."""
    resp = await _get("/console")
    assert resp.status_code == 200
    assert '<option value="catalog" selected>' in resp.text
    assert '<option value="local" >' in resp.text


@pytest.mark.asyncio
async def test_console_nav_entry_links_from_elsewhere_and_is_active_on_console() -> None:
    """The base nav carries a Console entry: a link (href="/console") from any other page, and
    the active non-link on /console itself, where that href is gone by construction."""
    elsewhere = await _get("/")
    on_console = await _get("/console")
    assert elsewhere.status_code == 200
    assert '<a href="/console">Console</a>' in elsewhere.text
    assert on_console.status_code == 200
    assert '<span aria-current="page">Console</span>' in on_console.text
    assert '<a href="/console">Console</a>' not in on_console.text


# ---------------------------------------------------------------------------
# POST /console
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("database", list(ConsoleDatabase))
@pytest.mark.asyncio
async def test_post_console_runs_the_sql_on_the_chosen_database(database: ConsoleDatabase) -> None:
    """The query runs on the database the form names, which stays selected, its SQL echoed."""
    resp, calls = await _post("/console", {"sql": _SQL, "db": database})
    assert resp.status_code == 200
    assert calls == [RunConsoleQueryCall(database, _SQL)]
    assert f'<option value="{database}" selected>' in resp.text
    assert f">{_SQL}</textarea>" in resp.text


@pytest.mark.asyncio
async def test_post_console_renders_the_answer() -> None:
    """An answer renders its count, its time in milliseconds, its columns and its cells."""
    resp, _ = await _post("/console", {"sql": _SQL, "db": "catalog"})
    assert resp.status_code == 200
    assert '<p class="console-meta">1 rows in 3 ms</p>' in resp.text
    assert "<th>native_id</th>" in resp.text
    assert f"<td>{_HASH_A}</td>" in resp.text
    assert 'class="console-table"' in resp.text
    assert 'class="console-truncated"' not in resp.text
    assert 'class="console-error"' not in resp.text


@pytest.mark.asyncio
async def test_post_console_answer_without_rows_says_so() -> None:
    answer = replace(_ANSWER, rows=())
    resp, _ = await _post(
        "/console", {"sql": _SQL, "db": "catalog"}, replace(_OUTCOME, query_answer=answer)
    )
    assert '<p class="console-meta">0 rows in 3 ms</p>' in resp.text
    assert "<tr><td>No rows.</td></tr>" in resp.text


@pytest.mark.asyncio
async def test_post_console_bogus_db_shows_error_no_query() -> None:
    """POST db=bogus -> 200 with an error banner, no query run (no query answer table)."""
    resp, calls = await _post("/console", {"sql": _SQL, "db": "bogus"})
    assert resp.status_code == 200
    assert f'<p class="console-error" role="alert">{_UNKNOWN_DB}</p>' in resp.text
    assert 'class="console-table"' not in resp.text
    assert " selected>" not in resp.text
    assert calls == []


@pytest.mark.asyncio
async def test_post_console_query_failure_shows_error_banner() -> None:
    """A failed query renders its message in the error banner, still HTTP 200."""
    outcome = replace(_OUTCOME, query_answer=QueryFailure("SQL error: near FROM"))
    resp, _ = await _post("/console", {"sql": "SELECT FROM", "db": "catalog"}, outcome)
    assert resp.status_code == 200
    assert '<p class="console-error" role="alert">SQL error: near FROM</p>' in resp.text
    assert 'class="console-table"' not in resp.text


@pytest.mark.asyncio
async def test_post_console_truncation_banner_names_the_row_cap() -> None:
    """A truncated answer renders the banner with the cap the outcome carries."""
    outcome = ConsoleQueryOutcome(replace(_ANSWER, truncated=True), row_cap=1000)
    resp, _ = await _post("/console", {"sql": _SQL, "db": "catalog"}, outcome)
    assert resp.status_code == 200
    assert (
        '<p class="console-truncated" role="status">Results truncated to the first 1,000 rows.</p>'
        in resp.text
    )


# ---------------------------------------------------------------------------
# POST /console.csv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_console_csv_valid_select() -> None:
    """POST a valid SELECT to /console.csv -> text/csv attachment with the CSV body."""
    resp, calls = await _post("/console.csv", {"sql": _SQL, "db": "local"})
    assert resp.status_code == 200
    assert calls == [RunConsoleQueryCall(ConsoleDatabase.LOCAL, _SQL)]
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"] == 'attachment; filename="query.csv"'
    assert resp.text == f"native_id\r\n{_HASH_A}\r\n"


@pytest.mark.asyncio
async def test_post_console_csv_bad_db_returns_400() -> None:
    """POST /console.csv with an unknown db -> 400 plain text with the error, no query run."""
    resp, calls = await _post("/console.csv", {"sql": _SQL, "db": "bogus"})
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.text == _UNKNOWN_DB
    assert calls == []


@pytest.mark.asyncio
async def test_post_console_csv_query_failure_returns_400() -> None:
    """POST /console.csv with a failed query -> 400 plain text with its message."""
    outcome = replace(_OUTCOME, query_answer=QueryFailure("SQL error: near FROM"))
    resp, _ = await _post("/console.csv", {"sql": "SELECT FROM", "db": "catalog"}, outcome)
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.text == "SQL error: near FROM"
