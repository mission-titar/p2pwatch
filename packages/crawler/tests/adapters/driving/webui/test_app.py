"""TDD tests for the Starlette application (adapters/driving/webui/app.py, Task 11)."""

import re
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest
import yaml
from httpx import ASGITransport, AsyncClient, Response
from jinja2 import Environment, FileSystemLoader, UndefinedError, meta
from starlette.applications import Starlette
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from catalog_matching.domain.config import MatcherConfig
from catalog_matching.domain.engine import DecisionRecord, Explanation
from catalog_matching.domain.models import TargetSegment
from catalog_matching.domain.validation import parse_matcher_config, parse_targets
from p2pwatch.adapters.driven.persistence_sqlite.catalog_read import (
    PAGE_SIZE,
    SqliteCatalogFileReader,
    SqliteSourceReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.reader import ReaderProvider
from p2pwatch.adapters.driving.webui.app import (
    _normalize_direction,
    _normalize_sort,
    _resolve_target_display,
    _search_bar,
    _sort_headers,
    _tier_facets,
    _to_display_rows,
    build_app,
)
from p2pwatch.adapters.driving.webui.views import DecisionCell, HiddenInput
from p2pwatch.application.describe_file import DescribeFile
from p2pwatch.application.matching_read import MatchingExplainer
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.coverage import TargetCoverage
from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.file_history import DatedDecision, FileHistory
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.interval import Interval
from p2pwatch.domain.node_state import NodeState, TrackedDownload
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from p2pwatch.domain.source import SourceKey
from p2pwatch.domain.status_reading import ChannelStatus, ClientStatus, StatusReading
from p2pwatch.ports.driving.crawl_summarizer import ClientSummary, CrawlSummary
from p2pwatch.ports.driving.file_describer import FileDescription
from p2pwatch.ports.driving.file_lister import FileListing
from p2pwatch.ports.driving.node_describer import NodeDescription
from p2pwatch_testing.application.fakes import (
    DescribeFileCall,
    FakeCrawlControls,
    FakeCrawlSummarizer,
    FakeFileDescriber,
    FakeFileLister,
    FakeNodeDescriber,
    FakeTime,
    ListFilesCall,
)
from p2pwatch_testing.catalog_rows import (
    SEEN_AT,
    file_id,
    insert_decision,
    insert_file,
    insert_observation,
    insert_source,
    insert_source_point,
    insert_source_variant,
    source_id,
)

pytestmark = pytest.mark.usefixtures("close_test_connections")

# ---------------------------------------------------------------------------
# Parsed-config helpers (since P4a build_app takes already-parsed config)
# ---------------------------------------------------------------------------

TEST_HASH = "aabbccdd00112233aabbccdd00112233"
_AMULE_URL = "http://localhost:4711"
# Wednesday 2026-10-14 20:00 UTC: the period tables read the 7 days before it.
_FAKE_TIME = FakeTime(datetime(2026, 10, 14, 20, 0, tzinfo=UTC))
_WALL_CLOCK = _FAKE_TIME.wall
_MONOTONIC_CLOCK = _FAKE_TIME.monotonic
_GAP = timedelta(seconds=90)


# The read-path fixtures never call the controls, and read the crawl as running.
_NO_CONTROLS = FakeCrawlControls()
_NODE_STATE = NodeState(
    node_id="node-test-001",
    created_at=datetime(2024, 1, 1, tzinfo=UTC),
    downloads=(),
    backoff_state_by_key={},
)
_CRAWL_SUMMARY = CrawlSummary(
    client_summaries=(),
    is_paused=False,
    node_state=_NODE_STATE,
    target_coverages=(TargetCoverage("062A", status="none", best_tier=None, file_count=0),),
)
_SUMMARIZER = FakeCrawlSummarizer(_CRAWL_SUMMARY)
_DESCRIBER = FakeNodeDescriber(NodeDescription(_NODE_STATE))
_NO_FILE_LISTER = FakeFileLister(FileListing((), False, 0, 0, {}))
# What /files asks for with no parameter.
_DEFAULT_CALL = ListFilesCall(
    target_id=None,
    tier=None,
    search_text=None,
    matched_only=True,
    sort=CatalogEntrySort.LAST_SEEN,
    direction=SortDirection.DESC,
    page=1,
)
_NO_FILE_DESCRIBER = FakeFileDescriber(None)
# The pages on fakes read their use case only: opening this path would fail.
_NO_DB = Path("/nonexistent/p2pwatch.db")
_FILE = FileKey(Network.ED2K, TEST_HASH)
_OBSERVATION = FileObservation(
    ReportedFile(_FILE, "keroro_s2e62a_vf.avi", 100_000_000, 5, "keroro"),
    datetime.fromisoformat(SEEN_AT),
)
_DECISION = DatedDecision(
    DecisionRecord("062A", "catalog", "catalog"), datetime.fromisoformat(SEEN_AT), "n1"
)
_WEEK = Interval(_WALL_CLOCK.now() - timedelta(days=7), _WALL_CLOCK.now())
# One file seen once under one name, decided on 062A, with no source and no explanation.
_FILE_DESCRIPTION = FileDescription(
    FileHistory(_FILE, 100_000_000, (_OBSERVATION,), _OBSERVATION, (_DECISION,), ()),
    sharing_periods=(),
    explanation=None,
    interval=_WEEK,
    now=_WALL_CLOCK.now(),
)


def _file_describer(
    catalog_db: Path, matcher_config: MatcherConfig, target_segments: tuple[TargetSegment, ...]
) -> DescribeFile:
    """The file page's use case over the fixture catalog, until its route tests run on a fake."""
    reader_provider = ReaderProvider(catalog_db)
    return DescribeFile(
        catalog_file_reader=SqliteCatalogFileReader(reader_provider),
        source_reader=SqliteSourceReader(reader_provider),
        explainer=MatchingExplainer(matcher_config=matcher_config, targets=target_segments),
        wall_clock=_WALL_CLOCK,
        source_period_gap=_GAP,
    )


def _app_on_fakes(
    *,
    crawl_summary: CrawlSummary = _CRAWL_SUMMARY,
    node_state: NodeState = _NODE_STATE,
    file_lister: FakeFileLister = _NO_FILE_LISTER,
    file_describer: FakeFileDescriber = _NO_FILE_DESCRIBER,
    target_segments: tuple[TargetSegment, ...] | None = None,
    controls: FakeCrawlControls = _NO_CONTROLS,
    amule_url: str = _AMULE_URL,
) -> Starlette:
    import p2pwatch.adapters.driving.webui

    webui_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent
    return build_app(
        catalog_db_path=_NO_DB,
        local_db_path=_NO_DB,
        target_segments=_targets() if target_segments is None else target_segments,
        templates_dir=webui_dir / "templates",
        static_dir=webui_dir / "static",
        crawl_pauser=controls,
        crawl_resumer=controls,
        shutdown_requester=controls,
        crawl_summarizer=FakeCrawlSummarizer(crawl_summary),
        node_describer=FakeNodeDescriber(NodeDescription(node_state)),
        file_lister=file_lister,
        file_describer=file_describer,
        amule_url=amule_url,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )


async def _page(app: Starlette, url: str) -> str:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(url)
    assert resp.status_code == 200
    return resp.text


def _listing(*catalog_entries: CatalogEntry) -> FileListing:
    return FileListing(catalog_entries, False, 0, 0, {})


def _one_file(*decisions: DecisionRecord) -> FileListing:
    return _listing(_catalog_entry(decisions=decisions))


async def _files_page(
    url: str,
    file_listing: FileListing | None = None,
    target_segments: tuple[TargetSegment, ...] | None = None,
) -> tuple[str, ListFilesCall]:
    """The page rendered from ``file_listing`` (one catalog-tier file by default), and its call."""
    if file_listing is None:
        file_listing = _one_file(_decision("062A", "catalog"))
    file_lister = FakeFileLister(file_listing)
    app = _app_on_fakes(file_lister=file_lister, target_segments=target_segments)
    text = await _page(app, url)
    (call,) = file_lister.calls
    return text, call


def _detail_url(ed2k_hash: str) -> str:
    return f"/files/{file_id(ed2k_hash).hex()}"


async def _file_response(
    url: str, file_description: FileDescription | None = _FILE_DESCRIPTION
) -> tuple[Response, list[DescribeFileCall]]:
    """The file page's response, rendered from ``file_description``, and its calls."""
    file_describer = FakeFileDescriber(file_description)
    app = _app_on_fakes(file_describer=file_describer)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(url)
    return response, file_describer.calls


def _query(since: datetime, until: datetime, **kept: str) -> str:
    """An interval's query string, in the webui's time format."""
    ends = {"from": f"{since:%Y-%m-%d %H:%M:%S}Z", "to": f"{until:%Y-%m-%d %H:%M:%S}Z"}
    return urlencode({**kept, **ends})


def _href(path: str, since: datetime, until: datetime, **kept: str) -> str:
    """An interval's link as the page escapes it."""
    return f'href="{path}?{_query(since, until, **kept)}"'.replace("&", "&amp;")


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


# ---------------------------------------------------------------------------
# Fixture: app with data
# ---------------------------------------------------------------------------


@pytest.fixture
def populated_app(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """Insert test data and build the Starlette app."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 100_000_000)
        insert_observation(
            conn,
            TEST_HASH,
            "keroro_s2e62a_vf.avi",
            size_bytes=100_000_000,
            source_count=5,
        )
        insert_decision(conn, TEST_HASH, "062A", "catalog", rule_name="catalog")

    matcher_config = _matcher()
    targets = _targets()

    import p2pwatch.adapters.driving.webui

    templates_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent / "templates"
    static_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent / "static"

    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        crawl_pauser=_NO_CONTROLS,
        crawl_resumer=_NO_CONTROLS,
        shutdown_requester=_NO_CONTROLS,
        crawl_summarizer=_SUMMARIZER,
        node_describer=_DESCRIBER,
        file_lister=_NO_FILE_LISTER,
        file_describer=_file_describer(catalog_db, matcher_config, targets),
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.fixture
def app_no_observations(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """File without observations (last_obs=None branch → link='')."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 100_000_000)
        # No observations

    matcher_config = _matcher()
    targets = _targets()

    import p2pwatch.adapters.driving.webui

    templates_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent / "templates"
    static_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent / "static"

    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        crawl_pauser=_NO_CONTROLS,
        crawl_resumer=_NO_CONTROLS,
        shutdown_requester=_NO_CONTROLS,
        crawl_summarizer=_SUMMARIZER,
        node_describer=_DESCRIBER,
        file_lister=_NO_FILE_LISTER,
        file_describer=_file_describer(catalog_db, matcher_config, targets),
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_200(populated_app: tuple[Starlette, str]) -> None:
    """/health → 200 {"status": "ok"}."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def _coverage_cells(coverage: TargetCoverage) -> list[str]:
    summary = replace(_CRAWL_SUMMARY, target_coverages=(coverage,))
    text = await _page(_app_on_fakes(crawl_summary=summary), "/")
    return re.findall(r"<td>(.*?)</td>", text[text.index("<h2>Target coverage</h2>") :])


@pytest.mark.asyncio
async def test_dashboard_shows_each_target_coverage_with_its_title() -> None:
    coverage = TargetCoverage("062A", status="found", best_tier="download", file_count=2)
    assert await _coverage_cells(coverage) == [
        '<a href="/targets/062A">062A</a>',
        *("La Grenouille Cosmique", "found", "download", "2"),
    ]


@pytest.mark.asyncio
async def test_dashboard_shows_a_target_without_a_best_tier_as_a_dot() -> None:
    coverage = TargetCoverage("062A", status="none", best_tier=None, file_count=0)
    assert (await _coverage_cells(coverage))[2:] == ["none", "·", "0"]


@pytest.mark.asyncio
async def test_files_asks_for_the_first_page_of_matched_files_by_last_seen() -> None:
    text, call = await _files_page("/files")
    assert call == _DEFAULT_CALL
    assert TEST_HASH[:8] in text


@pytest.mark.asyncio
async def test_files_default_summarizes_the_matched_files_and_offers_all() -> None:
    listing = replace(_listing(), matched_file_count=3, total_file_count=1234)
    text, _ = await _files_page("/files", listing)
    assert "Showing matched files only: 3 of 1,234 catalogued." in text
    assert 'href="/files?show_unmatched=1">Show all catalogued files' in text


@pytest.mark.asyncio
async def test_files_toggle_preserves_active_filter() -> None:
    """The matched→all toggle must carry the active search (spec §5: filters preserved)."""
    text, call = await _files_page("/files?search=keroro")
    assert call == replace(_DEFAULT_CALL, search_text="keroro")
    # Jinja2 autoescapes "&" to "&amp;" inside the href attribute.
    assert 'href="/files?search=keroro&amp;show_unmatched=1">Show all catalogued files' in text


@pytest.mark.parametrize(
    ("key", "old_key", "filtered_call"),
    [
        ("search", "q", replace(_DEFAULT_CALL, search_text="001A")),
        ("target_id", "target", replace(_DEFAULT_CALL, target_id="001A")),
    ],
)
@pytest.mark.asyncio
async def test_files_filters_on_its_query_key_and_ignores_the_4x_one(
    key: str, old_key: str, filtered_call: ListFilesCall
) -> None:
    _, filtered = await _files_page(f"/files?{key}=001A")
    _, unfiltered = await _files_page(f"/files?{old_key}=001A")
    assert filtered == filtered_call
    assert unfiltered == _DEFAULT_CALL


@pytest.mark.asyncio
async def test_files_show_unmatched_reveals_and_toggles_back() -> None:
    """/files?show_unmatched=1 asks for the whole catalogue; toggle points back to matched-only."""
    listing = replace(_listing(), matched_file_count=0, total_file_count=1)
    text, call = await _files_page("/files?show_unmatched=1", listing)
    assert call == replace(_DEFAULT_CALL, matched_only=False)
    assert "Showing all catalogued files: 1 catalogued (0 matched)." in text
    assert 'href="/files">Matched only' in text  # toggle drops the param → bare /files


def _history(**changes: Any) -> FileHistory:
    return replace(_FILE_DESCRIPTION.file_history, **changes)


async def _file_page(file_description: FileDescription = _FILE_DESCRIPTION) -> str:
    """The file page rendered from ``file_description``, with no space between tags."""
    response, _ = await _file_response(_detail_url(TEST_HASH), file_description)
    assert response.status_code == 200
    return re.sub(r">\s+<", "><", response.text)


@pytest.mark.asyncio
async def test_file_page_shows_the_network_the_native_id_and_the_ed2k_link() -> None:
    page = await _file_page()
    link = f"ed2k://|file|keroro_s2e62a_vf.avi|100000000|{TEST_HASH}|/"
    assert "<dt>Network</dt><dd>ed2k</dd>" in page
    assert f"<dt>Native ID</dt><dd>{TEST_HASH}</dd>" in page
    assert f'<dt>eD2k link</dt><dd><a href="{link}">{link}</a></dd>' in page
    assert "eD2k hash" not in page
    assert "AICH" not in page


@pytest.mark.asyncio
async def test_file_page_shows_each_decision_with_its_rule_tier_and_instant() -> None:
    decisions = tuple(
        DatedDecision(DecisionRecord(target_id, "numero_nu_confirmed", "download"), at, "n1")
        for target_id, at in (("072A", _OBSERVATION.observed_at), ("072B", _WALL_CLOCK.now()))
    )
    page = await _file_page(replace(_FILE_DESCRIPTION, file_history=_history(decisions=decisions)))
    for target_id, decided_at in (("072A", SEEN_AT), ("072B", "2026-10-14T20:00:00.000000+00:00")):
        terms = ("Target", target_id), ("Rule", "numero_nu_confirmed"), ("Tier", "download")
        cells = "".join(f"<dt>{term}</dt><dd>{value}</dd>" for term, value in terms)
        assert f"<dl>{cells}<dt>Decided at</dt><dd>{decided_at}</dd></dl>" in page
    assert "No matching decision." not in page


@pytest.mark.parametrize(
    ("query", "requested_since", "requested_until"),
    [
        ("", None, None),
        (
            "from=2026-10-14+19%3A00%3A00Z&to=2026-10-14+20%3A00%3A00Z",
            datetime(2026, 10, 14, 19, tzinfo=UTC),
            datetime(2026, 10, 14, 20, tzinfo=UTC),
        ),
        (
            "from=2026-10-08T00%3A00%3A00&to=2026-10-11T00%3A00%3A00",
            datetime(2026, 10, 8, tzinfo=UTC),
            datetime(2026, 10, 11, tzinfo=UTC),
        ),
        (
            "from=2026-10-11+00%3A00%3A00Z&to=2026-10-08+00%3A00%3A00Z",
            datetime(2026, 10, 11, tzinfo=UTC),
            datetime(2026, 10, 8, tzinfo=UTC),
        ),
        ("from=yesterday&to=2026-10-11+00%3A00%3A00Z", None, datetime(2026, 10, 11, tzinfo=UTC)),
    ],
    ids=["none", "preset", "custom", "inverted", "malformed"],
)
@pytest.mark.asyncio
async def test_file_page_asks_for_its_file_over_the_ends_its_query_names(
    query: str, requested_since: datetime | None, requested_until: datetime | None
) -> None:
    # The use case resolves the interval: an inverted or a malformed end reaches it as read.
    response, calls = await _file_response(f"{_detail_url(TEST_HASH)}?{query}")
    assert response.status_code == 200
    assert calls == [DescribeFileCall(file_id(TEST_HASH), requested_since, requested_until)]


@pytest.mark.asyncio
async def test_file_page_of_a_file_the_catalog_does_not_hold_is_a_styled_404() -> None:
    # The ed2k hash is a well-formed id, but not a file's.
    response, calls = await _file_response(f"/files/{TEST_HASH}", None)
    assert response.status_code == 404
    assert "not found" in response.text.lower()
    assert calls == [DescribeFileCall(bytes.fromhex(TEST_HASH), None, None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed",
    ["zz", file_id(TEST_HASH).hex().upper(), file_id(TEST_HASH).hex()[:31], " " * 32],
)
async def test_file_page_of_a_malformed_file_id_is_a_404_that_asks_for_nothing(
    malformed: str,
) -> None:
    response, calls = await _file_response(f"/files/{malformed}")
    assert response.status_code == 404
    assert "not found" in response.text.lower()
    assert calls == []


@pytest.mark.asyncio
async def test_files_list_links_each_file_to_its_file_id() -> None:
    text, _ = await _files_page("/files")
    assert f'<a href="{_detail_url(TEST_HASH)}">{TEST_HASH[:8]}…</a>' in text


@pytest.mark.asyncio
async def test_file_page_shows_the_explanation_its_use_case_gives() -> None:
    explanation = Explanation(
        target_id="072B",
        rules_fired=("title_review",),
        tokens_matched=("ita", "keroro", "title_hit"),
        coverage_values=(("title_hit", 2 / 3),),
        vetoes_fired=("ita",),
    )
    page = await _file_page(replace(_FILE_DESCRIPTION, explanation=explanation))
    assert (
        "<p>Evaluated against the current configuration</p><p>Target: 072B</p>"
        "<p>Rules fired:</p><ul><li>title_review</li></ul>"
        "<p>Matched tokens:</p><ul><li>ita</li><li>keroro</li><li>title_hit</li></ul>"
        "<p>Coverage values:</p><ul><li>title_hit: 0.67</li></ul>"
        "<p>Vetoes fired:</p><ul><li>ita</li></ul>"
    ) in page
    assert "No explanation available." not in page


@pytest.mark.asyncio
async def test_file_detail_timeline_shows_each_observation_as_one_plain_line(
    populated_app: tuple[Starlette, str],
) -> None:
    app, hash_ = populated_app
    day = _query(datetime(2026, 6, 22, tzinfo=UTC), datetime(2026, 6, 23, tzinfo=UTC))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"{_detail_url(hash_)}?{day}")
    cells = ("keroro_s2e62a_vf.avi", "100000000", "5", "keroro", SEEN_AT)
    line = "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"
    assert line in re.sub(r">\s+<", "><", resp.text)
    assert "Times seen" not in resp.text


_USER = "1f2e" * 8
# Tuesday 2026-10-13 20:00:00 UTC, in microseconds since the Unix epoch.
_TUESDAY_8PM = 1_791_921_600_000_000


def _row(*cells: str) -> str:
    return "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"


@pytest.mark.asyncio
async def test_file_detail_shows_its_source_history_newest_first(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    with sqlite3.connect(catalog_db) as conn:
        insert_source(conn, _USER)
        queued = insert_source_variant(
            conn,
            hash_,
            _USER,
            contact_point="198.51.100.7:4661",
            connectable=False,
            node_id="n2",
        )
        sending = insert_source_variant(conn, hash_, _USER, role="sending", node_id="n1")
        for at in (30, 60):
            insert_source_point(conn, queued, _TUESDAY_8PM + at * 1_000_000)
        for step in range(129):  # every 80 s, 10 MB in 10,240 s
            at, counter = _TUESDAY_8PM + (90 + 80 * step) * 1_000_000, step * 81_920
            insert_source_point(conn, sending, at, session_received_bytes=counter)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    page = re.sub(r">\s+<", "><", resp.text)
    name = '<a href="/sources/name?source_name=AnimuseeFMR">AnimuseeFMR</a>'
    source = f'<a href="/sources/{SourceKey(Network.ED2K, _USER).source_id.hex()}">1f2e1f2e…</a>'
    sending_line = _row(
        name, source, "sending", "unknown", "unknown",
        "2026-10-13 20:01:30Z", "2026-10-13 22:52:10Z", "10 MB", "1 KB/s", "n1",
    )  # fmt: skip
    queued_line = _row(
        name, source, "queued", "198.51.100.7:4661", "no",
        "2026-10-13 20:00:30Z", "2026-10-13 20:01:00Z", "", "", "n2",
    )  # fmt: skip
    assert "<h2>Source history</h2>" in page
    assert "<th>Connectable</th>" in page
    assert page.index("<h2>Observations</h2>") < page.index("<h2>Source history</h2>")
    assert 0 < page.index(sending_line) < page.index(queued_line)


@pytest.mark.asyncio
async def test_file_detail_links_only_the_name_or_the_hash_a_period_has(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    with sqlite3.connect(catalog_db) as conn:
        insert_source(conn, _USER)
        unnamed = insert_source_variant(conn, hash_, _USER, name=None, connectable=True)
        hashless = insert_source_variant(conn, hash_, None, name="http://emule-project.net")
        insert_source_point(conn, unnamed, _TUESDAY_8PM)
        insert_source_point(conn, hashless, _TUESDAY_8PM)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    page = re.sub(r">\s+<", "><", resp.text)
    source = f'<a href="/sources/{SourceKey(Network.ED2K, _USER).source_id.hex()}">1f2e1f2e…</a>'
    name = '<a href="/sources/name?source_name=http%3A%2F%2Femule-project.net">http://emule-project.net</a>'
    stamp = "2026-10-13 20:00:00Z"
    assert _row("unknown", source, "queued", "unknown", "yes", stamp, stamp, "", "", "n1") in page
    assert _row(name, "unknown", "queued", "unknown", "unknown", stamp, stamp, "", "", "n1") in page


@pytest.mark.asyncio
async def test_file_detail_shows_no_source_older_than_7_days(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    with sqlite3.connect(catalog_db) as conn:
        insert_source(conn, _USER)
        week_before = (_WALL_CLOCK.now() - timedelta(days=7, microseconds=1)).timestamp()
        insert_source_point(
            conn, insert_source_variant(conn, hash_, _USER), int(week_before * 1_000_000)
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert '<td colspan="10">No source read in this interval.</td>' in resp.text


# ---------------------------------------------------------------------------
# The sources list (stage 4 spec, D13)
# ---------------------------------------------------------------------------

_OTHER = "9c0d" * 8


def _seed_two_sources(catalog_db: Path, ed2k_hash: str) -> None:
    with sqlite3.connect(catalog_db) as conn:
        for user, name in ((_USER, "AnimuseeFMR"), (_OTHER, "Shinobu")):
            insert_source(conn, user)
            variant = insert_source_variant(conn, ed2k_hash, user, name=name)
            for at in (_TUESDAY_8PM, _TUESDAY_8PM + 30_000_000):
                insert_source_point(conn, variant, at)


async def _sources_page(app: Starlette, url: str) -> str:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(url)
    assert resp.status_code == 200
    return re.sub(r">\s+<", "><", resp.text)


@pytest.mark.asyncio
async def test_sources_lists_each_source_with_its_links_last_seen_and_files(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    _seed_two_sources(catalog_db, hash_)
    page = await _sources_page(app, "/sources")
    name = '<a href="/sources/name?source_name=AnimuseeFMR">AnimuseeFMR</a>'
    source = f'<a href="/sources/{SourceKey(Network.ED2K, _USER).source_id.hex()}">1f2e1f2e…</a>'
    assert _row(name, source, "2026-10-13 20:00:30Z", "1") in page
    assert "Sources recorded: 2." in page
    assert (
        '<input type="search" name="search" value="" placeholder="Search name or user hash">'
        in page
    )


@pytest.mark.asyncio
async def test_sources_search_keeps_its_query_and_counts_its_matches(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    _seed_two_sources(catalog_db, hash_)
    page = await _sources_page(app, "/sources?search=+shinob+")
    assert "Shinobu</a>" in page
    assert "AnimuseeFMR" not in page
    assert "Sources matching the search: 1." in page
    assert 'name="search" value="shinob"' in page


@pytest.mark.asyncio
async def test_sources_ignore_the_4x_search_key(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    _seed_two_sources(catalog_db, hash_)
    page = await _sources_page(app, "/sources?q=shinob")
    assert "AnimuseeFMR</a>" in page
    assert "Sources recorded: 2." in page


@pytest.mark.asyncio
async def test_sources_without_a_source_says_so(populated_app: tuple[Starlette, str]) -> None:
    app, _ = populated_app
    page = await _sources_page(app, "/sources?page=nope")
    assert '<td colspan="4">No source found.</td>' in page
    assert "<span>Page 1</span>" in page


@pytest.mark.asyncio
async def test_sources_pages_keep_the_search(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    with sqlite3.connect(catalog_db) as conn:
        for n in range(PAGE_SIZE + 1):
            insert_source(conn, f"{n:032x}")
            insert_source_point(conn, insert_source_variant(conn, hash_, f"{n:032x}"), n)
    first = await _sources_page(app, "/sources?search=FMR")
    second = await _sources_page(app, "/sources?search=FMR&page=2")
    assert 'href="/sources?search=FMR&amp;page=2"' in first
    assert 'href="/sources?search=FMR&amp;page=1"' in second
    assert second.count("<tr><td>") == 1


# ---------------------------------------------------------------------------
# The page of a source and the page of a name (stage 4 spec, D13)
# ---------------------------------------------------------------------------

_THIRD = "5a6b" * 8
_USER_PAGE = f"/sources/{source_id(_USER).hex()}"


def _hash_link(user: str) -> str:
    return f'<a href="/sources/{source_id(user).hex()}">{user[:8]}…</a>'


@pytest.mark.asyncio
async def test_source_page_shows_its_hash_its_names_and_its_periods(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    _seed_two_sources(catalog_db, hash_)
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, "c" * 32)
        unseen = insert_source_variant(conn, "c" * 32, _USER, role="standby")
        insert_source_point(conn, unseen, _TUESDAY_8PM)
    page = await _sources_page(app, _USER_PAGE)
    name = '<a href="/sources/name?source_name=AnimuseeFMR">AnimuseeFMR</a>'
    file = f'<a href="/files/{file_id(hash_).hex()}">keroro_s2e62a_vf.avi</a>'
    unseen_file = f'<a href="/files/{file_id("c" * 32).hex()}">cccccccc…</a>'
    first, last = "2026-10-13 20:00:00Z", "2026-10-13 20:00:30Z"
    assert f"<dd>{_USER}</dd>" in page
    assert "<th>Connectable</th>" in page
    assert _row(name, last, "2") in page
    assert _row(file, name, "queued", "unknown", "unknown", first, last, "", "", "n1") in page
    unseen_line = _row(
        unseen_file, name, "standby", "unknown", "unknown", first, first, "", "", "n1"
    )
    assert unseen_line in page
    assert "Shinobu" not in page


@pytest.mark.asyncio
async def test_a_source_without_a_name_reads_unknown_unlinked_on_the_list_and_its_page(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    with sqlite3.connect(catalog_db) as conn:
        insert_source(conn, _USER)
        unnamed = insert_source_variant(conn, hash_, _USER, name=None)
        insert_source_point(conn, unnamed, _TUESDAY_8PM)
    source = f'<a href="/sources/{SourceKey(Network.ED2K, _USER).source_id.hex()}">1f2e1f2e…</a>'
    file = f'<a href="/files/{file_id(hash_).hex()}">keroro_s2e62a_vf.avi</a>'
    stamp = "2026-10-13 20:00:00Z"
    assert _row("unknown", source, stamp, "1") in await _sources_page(app, "/sources")
    period = _row(file, "unknown", "queued", "unknown", "unknown", stamp, stamp, "", "", "n1")
    assert period in await _sources_page(app, _USER_PAGE)


@pytest.mark.asyncio
async def test_name_page_lists_the_hashes_that_carried_it_and_nothing_further(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    _seed_two_sources(catalog_db, hash_)
    unseen = "c" * 32
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, unseen)
        insert_source(conn, _THIRD)
        for user, name, on in (
            (_OTHER, "AnimuseeFMR", hash_),
            (_THIRD, "Shinobu", hash_),
            (None, "AnimuseeFMR", unseen),
        ):
            variant = insert_source_variant(conn, on, user, name=name, role="standby")
            insert_source_point(conn, variant, _TUESDAY_8PM)
    page = await _sources_page(app, "/sources/name?source_name=AnimuseeFMR")
    file = f'<a href="/files/{file_id(unseen).hex()}">cccccccc…</a>'
    stamp = "2026-10-13 20:00:00Z"
    assert "<dd>AnimuseeFMR</dd>" in page
    assert "<th>Connectable</th>" in page
    assert _row(_hash_link(_USER), "2026-10-13 20:00:30Z", "1") in page
    assert _row(_hash_link(_OTHER), stamp, "1") in page
    assert _THIRD[:8] not in page
    assert _row(file, "standby", "unknown", "unknown", stamp, stamp, "", "", "n1") in page


@pytest.mark.parametrize(
    "url",
    [
        "/sources/zz",
        f"/sources/{'0' * 32}",
        "/sources/name",
        "/sources/name?source_name=nobody",
        "/sources/name?name=AnimuseeFMR",  # 4.x's key
    ],
)
@pytest.mark.asyncio
async def test_source_and_name_pages_of_what_was_never_recorded_return_404(
    populated_app: tuple[Starlette, str], catalog_db: Path, url: str
) -> None:
    app, hash_ = populated_app
    _seed_two_sources(catalog_db, hash_)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(url)
    assert resp.status_code == 404


@pytest.mark.parametrize(
    ("user", "url", "lists"),
    [(None, "/sources/name?source_name=AnimuseeFMR&", 0), (_USER, f"{_USER_PAGE}?", 1)],
    ids=["name", "source"],
)
@pytest.mark.asyncio
async def test_source_and_name_pages_show_every_period_of_the_window_on_one_page(
    populated_app: tuple[Starlette, str], catalog_db: Path, user: str | None, url: str, lists: int
) -> None:
    # The page parameter moves the names or the hashes only (source points spec, D6).
    app, hash_ = populated_app
    with sqlite3.connect(catalog_db) as conn:
        if user is not None:
            insert_source(conn, user)
        variant = insert_source_variant(conn, hash_, user)
        for n in range(PAGE_SIZE + 1):  # one period each, past the gap
            insert_source_point(conn, variant, _TUESDAY_8PM + n * 100_000_000)
    first, second = await _sources_page(app, url), await _sources_page(app, f"{url}page=2")
    assert first.count("<tr><td>") == PAGE_SIZE + 1 + lists
    assert second.count("<tr><td>") == PAGE_SIZE + 1
    assert "page=2" not in first


@pytest.mark.asyncio
async def test_file_page_without_a_decision_says_so() -> None:
    page = await _file_page(replace(_FILE_DESCRIPTION, file_history=_history(decisions=())))
    assert "<p>No matching decision.</p>" in page
    assert "<p>No explanation available.</p>" in page
    assert "ed2k://" in page


@pytest.mark.asyncio
async def test_file_page_with_a_decision_but_no_explanation_says_so() -> None:
    # The explainer has none for a target the current config does not know.
    unknown = replace(_DECISION, decision=DecisionRecord("S9E999Z", "catalog", "catalog"))
    page = await _file_page(replace(_FILE_DESCRIPTION, file_history=_history(decisions=(unknown,))))
    assert "<dt>Target</dt><dd>S9E999Z</dd>" in page
    assert "<p>No explanation available.</p>" in page


@pytest.mark.asyncio
async def test_target_page_asks_for_every_file_of_its_target_on_one_page() -> None:
    """/targets/{target_id}: a shortcut to /files filtered on it, matched or not."""
    _, call = await _files_page("/targets/062A?page=2&sort=size&tier=notify")
    assert call == replace(_DEFAULT_CALL, target_id="062A", matched_only=False)


@pytest.mark.asyncio
async def test_target_page_has_no_summary_line() -> None:
    """/targets/{id} shares files.html, but the matched/all summary is meaningless on a
    target-scoped page: the summary line and its toggle must not render there."""
    text, _ = await _files_page("/targets/062A")
    assert "files-summary" not in text
    assert "Showing matched files only" not in text
    assert "Show all catalogued files" not in text


@pytest.mark.asyncio
async def test_node_page_shows_the_node_id() -> None:
    assert "<dd>node-test-001</dd>" in await _page(_app_on_fakes(), "/node")


@pytest.mark.asyncio
async def test_files_non_numeric_page_defaults_to_1() -> None:
    _, call = await _files_page("/files?page=abc")
    assert call == _DEFAULT_CALL


@pytest.mark.asyncio
async def test_file_detail_no_observations_returns_200(
    app_no_observations: tuple[Starlette, str],
) -> None:
    """/files/{file_id} without observations → 200; no ed2k link, empty branch rendered."""
    app, hash_ = app_no_observations
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert resp.status_code == 200
    assert "ed2k://" not in resp.text
    assert "No observation in this interval." in resp.text


@pytest.mark.asyncio
async def test_base_nav_uses_singular_node_href(
    populated_app: tuple[Starlette, str],
) -> None:
    """The base nav contains href="/node" (singular) and NOT href="/nodes"."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert 'href="/node"' in resp.text
    assert 'href="/nodes"' not in resp.text


_DOWNLOAD = TrackedDownload(
    file=FileKey(Network.ED2K, TEST_HASH),
    target_id="062A",
    state=DownloadState.DOWNLOADING,
    queued_at=datetime(2026, 10, 10, tzinfo=UTC),
    completed_at=None,
    last_progress_at=None,
    waiting_reason=None,
    failure_reason=None,
)


async def _node_page(node_state: NodeState) -> str:
    return await _page(_app_on_fakes(node_state=node_state), "/node")


@pytest.mark.asyncio
async def test_node_page_shows_each_backoff_and_its_planned_retry_in_utc() -> None:
    started_at = datetime(2026, 6, 12, 10, tzinfo=UTC)
    backoff_state_by_key = {
        BackoffKey("amuled", None): BackoffState(3, started_at, timedelta(seconds=120)),
        BackoffKey("amuled", "kad"): BackoffState(1, started_at, timedelta(seconds=2.5)),
    }
    before = await _node_page(_NODE_STATE)
    after = await _node_page(replace(_NODE_STATE, backoff_state_by_key=backoff_state_by_key))
    assert "No backoff." in before
    cells = re.findall(r"<td>([^<]*)</td>", after)
    assert cells == [
        *("amuled", "whole client", "3", "2026-06-12T10:02:00.000000+00:00"),
        *("amuled", "kad", "1", "2026-06-12T10:00:02.500000+00:00"),
    ]


@pytest.mark.asyncio
async def test_node_page_names_a_download_by_its_native_id() -> None:
    text = await _node_page(replace(_NODE_STATE, downloads=(_DOWNLOAD,)))
    assert f"<td>{TEST_HASH}</td>" in text


@pytest.mark.asyncio
async def test_node_page_shows_a_downloads_lifecycle() -> None:
    download = replace(
        _DOWNLOAD,
        state=DownloadState.FAILED,
        last_progress_at=datetime(2026, 10, 11, tzinfo=UTC),
        waiting_reason="local_processing",
        failure_reason="error",
    )
    text = await _node_page(replace(_NODE_STATE, downloads=(download,)))
    assert "<td>2026-10-11T00:00:00.000000+00:00</td>" in text
    assert "<td>local_processing</td>" in text
    assert "<td>error</td>" in text
    assert "None" not in text  # an unknown value shows blank


@pytest.mark.parametrize(
    "template",
    ["{{ missing }}", "{% for item in nav_items %}{{ item.missing }}{% endfor %}"],
    ids=["missing-name", "missing-attribute"],
)
@pytest.mark.asyncio
async def test_a_template_reading_what_its_context_lacks_raises(
    template: str, catalog_db: Path, local_db: Path, tmp_path: Path
) -> None:
    """A renamed context key or field fails the render instead of printing an empty string."""
    import p2pwatch.adapters.driving.webui

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "404.html").write_text(template, encoding="utf-8")
    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        target_segments=_targets(),
        templates_dir=templates_dir,
        static_dir=Path(p2pwatch.adapters.driving.webui.__file__).parent / "static",
        crawl_pauser=_NO_CONTROLS,
        crawl_resumer=_NO_CONTROLS,
        shutdown_requester=_NO_CONTROLS,
        crawl_summarizer=_SUMMARIZER,
        node_describer=_DESCRIBER,
        file_lister=_NO_FILE_LISTER,
        file_describer=_file_describer(catalog_db, _matcher(), _targets()),
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with pytest.raises(UndefinedError):
            await client.get("/sources/not-a-hex-id")


class _TemplateRecorder:
    """The app, each template response asked for its template and context through ASGI's debug
    extension, which Starlette answers and httpx's transport does not request."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self.rendered: list[dict[str, Any]] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def record(message: Message) -> None:
            if message["type"] == "http.response.debug":
                self.rendered.append(message["info"])
            else:
                await send(message)

        await self._app({**scope, "extensions": {"http.response.debug": {}}}, receive, record)


def _template_reads(loader: FileSystemLoader, name: str) -> set[str]:
    """The context names a template reads, with those of the templates it extends or includes."""
    env = Environment(loader=loader)
    tree = env.parse(loader.get_source(env, name)[0])
    reads = set(meta.find_undeclared_variables(tree))
    for parent in meta.find_referenced_templates(tree):
        reads |= _template_reads(loader, str(parent))
    return reads


@pytest.mark.parametrize(
    "url",
    [
        "/",
        "/files",
        "/files/{file_id}",
        "/files/not-a-hex-id",
        "/sources",
        _USER_PAGE,
        "/sources/name?source_name=AnimuseeFMR",
        "/targets/062A",
        "/node",
        "/console",
    ],
)
@pytest.mark.asyncio
async def test_each_page_passes_its_template_only_what_it_reads(
    populated_app: tuple[Starlette, str], catalog_db: Path, url: str
) -> None:
    """A context key no template reads is a stale name, which strict templates cannot see."""
    import p2pwatch.adapters.driving.webui

    app, hash_ = populated_app
    _seed_two_sources(catalog_db, hash_)
    recorder = _TemplateRecorder(app)
    async with AsyncClient(transport=ASGITransport(app=recorder), base_url="http://test") as client:
        await client.get(url.format(file_id=file_id(hash_).hex()))
    (rendered,) = recorder.rendered
    loader = FileSystemLoader(Path(p2pwatch.adapters.driving.webui.__file__).parent / "templates")
    passed = set(rendered["context"]) - {"request"}
    assert passed == _template_reads(loader, rendered["template"].name)


@pytest.fixture
def app_with_hostile_filename(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """File whose name contains a ``|`` (eD2k link separator). A webui-security#0
    regression: without percent-encoding, the ``|`` in the name shifts size/hash and the
    link points elsewhere."""
    hostile = "weird|name.avi"
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 100_000_000)
        insert_observation(conn, TEST_HASH, hostile, size_bytes=100_000_000)
    matcher_config = _matcher()
    targets = _targets()
    import p2pwatch.adapters.driving.webui

    templates_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent / "templates"
    static_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent / "static"
    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        crawl_pauser=_NO_CONTROLS,
        crawl_resumer=_NO_CONTROLS,
        shutdown_requester=_NO_CONTROLS,
        crawl_summarizer=_SUMMARIZER,
        node_describer=_DESCRIBER,
        file_lister=_NO_FILE_LISTER,
        file_describer=_file_describer(catalog_db, matcher_config, targets),
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.mark.asyncio
async def test_empty_filter_param_does_not_silently_zero_results() -> None:
    # webui-security#0 regression (filters): ``?target_id=`` (empty, common with a <select>
    # that has an empty option) must be treated as "no filter", not as ``target_id = ''`` which
    # matches 0 results with no message.
    _, call = await _files_page("/files?target_id=&tier=&search=")
    assert call == _DEFAULT_CALL


@pytest.mark.asyncio
async def test_page_zero_is_clamped_to_first_page() -> None:
    # webui-security#2 regression: ``?page=0`` → OFFSET=-50 (SQLite returned page 1 by
    # luck). Now ``max(1, page)`` clamps.
    text, call = await _files_page("/files?page=0")
    assert call == _DEFAULT_CALL
    assert "<span>Page 1</span>" in text


@pytest.mark.asyncio
async def test_security_headers_are_set_on_every_response(
    populated_app: tuple[Starlette, str],
) -> None:
    # webui-security#3: CSP + X-Content-Type-Options + Referrer-Policy set by middleware.
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert resp.headers["Content-Security-Policy"] == "default-src 'self'"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.asyncio
async def test_files_page_shows_pagination_navigation() -> None:
    # webui-security#1: a "Next →" link when the listing has a next page.
    first, _ = await _files_page("/files?search=x", replace(_listing(), has_next_page=True))
    second, call = await _files_page("/files?search=x&page=2")
    assert call == replace(_DEFAULT_CALL, search_text="x", page=2)
    assert '<a href="/files?search=x&amp;page=2">Next →</a>' in first
    assert "Previous" not in first
    assert '<a href="/files?search=x&amp;page=1">← Previous</a>' in second
    assert "Next" not in second


@pytest.mark.asyncio
async def test_hostile_filename_is_escaped_in_ed2k_link(
    app_with_hostile_filename: tuple[Starlette, str],
) -> None:
    # webui-security#0 regression: a hostile ``|`` in the name must be percent-encoded
    # (%7C). Without this escaping, the link would have 6 ``|`` (instead of 5 structural
    # separators) and size/hash would be shifted → unusable file / pointing elsewhere.
    app, hash_ = app_with_hostile_filename
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert resp.status_code == 200
    # The link in the response must contain %7C (and NOT a raw ``|`` in the middle of the name).
    assert "%7C" in resp.text
    # We extract the first occurrence of ``ed2k://`` up to the next whitespace/`"` to
    # verify it has EXACTLY 5 ``|`` (the 5 structural separators of the canonical link).
    start = resp.text.index("ed2k://")
    end = start
    while end < len(resp.text) and resp.text[end] not in ('"', "<", " ", "\n"):
        end += 1
    link = resp.text[start:end]
    assert link.count("|") == 5


# ---------------------------------------------------------------------------
# Unit tests · _resolve_target_display / _to_display_rows (Task 3 resolution rule)
# ---------------------------------------------------------------------------

_SEGMENT_062A = TargetSegment(
    season=2, seasonal_number=11, absolute_number=62, letter="a", title="La Grenouille Cosmique"
)
_SEGMENT_062B = TargetSegment(
    season=2, seasonal_number=11, absolute_number=62, letter="b", title="Duel Contre Giroro"
)
_SEGMENT_BY_ID = {_SEGMENT_062A.target_id: _SEGMENT_062A}
_SEGMENTS_AB = {s.target_id: s for s in (_SEGMENT_062A, _SEGMENT_062B)}


def _catalog_entry(
    *,
    decisions: tuple[DecisionRecord, ...],
    observed_at: datetime = datetime(2024, 1, 1, tzinfo=UTC),
) -> CatalogEntry:
    reported_file = ReportedFile(FileKey(Network.ED2K, TEST_HASH), "f.avi", 1024, 1, "keroro")
    return CatalogEntry(
        file=reported_file.file,
        size_bytes=1024,
        latest_observation=FileObservation(reported_file, observed_at),
        decisions=decisions,
    )


def _decision(target_id: str, tier: str) -> DecisionRecord:
    return DecisionRecord(target_id, "rule", tier)


def test_resolve_target_display_empty_decisions_is_empty_list() -> None:
    assert _resolve_target_display(_catalog_entry(decisions=()), _SEGMENT_BY_ID) == []


def test_resolve_target_display_catalog_decision_is_unidentified() -> None:
    entry = _catalog_entry(decisions=(_decision(target_id="062A", tier="catalog"),))
    assert _resolve_target_display(entry, _SEGMENT_BY_ID) == [("unidentified", "·")]


def test_resolve_target_display_resolvable_id_joins_seasonal_locator_and_title() -> None:
    entry = _catalog_entry(decisions=(_decision(target_id="062A", tier="download"),))
    assert _resolve_target_display(entry, _SEGMENT_BY_ID) == [
        ("062A / S02E11A", "La Grenouille Cosmique")
    ]


def test_resolve_target_display_unknown_id_falls_back_to_raw_id() -> None:
    entry = _catalog_entry(decisions=(_decision(target_id="999Z", tier="download"),))
    assert _resolve_target_display(entry, _SEGMENT_BY_ID) == [("999Z", "·")]


def test_resolve_target_display_two_segments_returns_a_pair_each() -> None:
    entry = _catalog_entry(decisions=(_decision("062A", "download"), _decision("062B", "download")))
    assert _resolve_target_display(entry, _SEGMENTS_AB) == [
        ("062A / S02E11A", "La Grenouille Cosmique"),
        ("062B / S02E11B", "Duel Contre Giroro"),
    ]


def test_to_display_rows_empty_decisions_all_dashes() -> None:
    [display] = _to_display_rows([_catalog_entry(decisions=())], _SEGMENTS_AB)
    assert display.decisions_display == ()
    assert display.tier_display == "·"


def test_to_display_rows_two_segments_aggregate_cells_shared_tier() -> None:
    entry = _catalog_entry(decisions=(_decision("062A", "download"), _decision("062B", "download")))
    [display] = _to_display_rows([entry], _SEGMENTS_AB)
    assert display.decisions_display == (
        DecisionCell(target="062A / S02E11A", title="La Grenouille Cosmique"),
        DecisionCell(target="062B / S02E11B", title="Duel Contre Giroro"),
    )
    assert display.tier_display == "download"


def test_to_display_rows_two_segments_differing_tiers_lists_per_target() -> None:
    entry = _catalog_entry(decisions=(_decision("062A", "download"), _decision("062B", "notify")))
    [display] = _to_display_rows([entry], _SEGMENTS_AB)
    assert display.tier_display == "062A: download · 062B: notify"


def test_to_display_rows_computes_size_and_last_seen_display() -> None:
    entry = _catalog_entry(
        decisions=(), observed_at=datetime(2026, 7, 3, 23, 45, 24, 104990, tzinfo=UTC)
    )
    [display] = _to_display_rows([entry], _SEGMENTS_AB)
    assert display.size_display == "1 KB"
    assert display.last_seen_display == "2026-07-03 23:45Z"


def test_to_display_rows_shows_a_file_never_seen_with_unknown_sources() -> None:
    entry = replace(_catalog_entry(decisions=()), latest_observation=None)
    [display] = _to_display_rows([entry], _SEGMENTS_AB)
    assert (display.filename, display.sources_display, display.last_seen_display) == (
        "",
        "unknown",
        "",
    )


# ---------------------------------------------------------------------------
# HTTP-level tests · the resolution rule end-to-end through both routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_files_catalog_tier_shows_unidentified() -> None:
    """A tier=catalog decision → the /files list must show "unidentified", not the resolved
    id/title."""
    text, _ = await _files_page("/files", _one_file(_decision("062A", "catalog")))
    assert TEST_HASH[:8] in text
    # Scoped to the table cell (not the static tier legend, which also mentions the word).
    assert '<div class="cell-line">unidentified</div>' in text
    assert "La Grenouille Cosmique" not in text


@pytest.mark.asyncio
async def test_files_resolvable_target_shows_seasonal_locator_and_title() -> None:
    text, _ = await _files_page("/files", _one_file(_decision("062A", "download")))
    assert "062A / S02E11A" in text
    assert "La Grenouille Cosmique" in text


@pytest.mark.asyncio
async def test_files_table_is_scroll_wrapped_and_name_has_full_title() -> None:
    """The table is wrapped for horizontal scroll on narrow desktop widths, and the (possibly
    truncated) filename keeps its full text in a title= tooltip."""
    text, _ = await _files_page("/files")
    assert '<div class="files-scroll">' in text
    assert 'class="cell-name" title="f.avi"' in text


@pytest.mark.asyncio
async def test_files_unknown_target_shows_raw_id_and_dash_title() -> None:
    text, _ = await _files_page("/files", _one_file(_decision("999Z", "download")))
    assert "999Z" in text
    # The static tier legend also mentions the word "unidentified": scope to the cell.
    assert '<div class="cell-line">unidentified</div>' not in text
    assert "La Grenouille Cosmique" not in text


@pytest.mark.asyncio
async def test_files_no_decision_shows_dashes() -> None:
    """No decision at all → target and title both render as "·" cells, never an
    "unidentified" cell value."""
    text, _ = await _files_page("/files?show_unmatched=1", _one_file())
    assert TEST_HASH[:8] in text
    # The Target header tooltip also mentions "unidentified": scope to the cell so we
    # assert on the row value, not the static legend text.
    assert '<div class="cell-line">unidentified</div>' not in text
    assert "La Grenouille Cosmique" not in text


@pytest.mark.asyncio
async def test_files_tier_header_has_tooltip_and_no_legacy_legend() -> None:
    """The tier meanings now live in a "?" header tooltip on the Tier column, replacing the
    old free-standing <p class="tier-legend"> block."""
    text, _ = await _files_page("/files")
    # The legacy legend block is gone.
    assert 'class="tier-legend"' not in text
    assert "Tier legend" not in text
    # A focusable "?" trigger describes a tooltip that enumerates the three tiers.
    assert 'aria-describedby="tip-tier"' in text
    assert 'id="tip-tier"' in text
    assert 'role="tooltip"' in text
    assert "automatically queued for download" in text
    assert "flagged for manual review" in text


@pytest.mark.asyncio
async def test_files_nonobvious_columns_have_header_tooltips() -> None:
    """The other non-obvious columns (Target, Sources) also carry a "?" header tooltip
    explaining their values."""
    text, _ = await _files_page("/files")
    assert 'id="tip-target"' in text
    assert 'id="tip-sources"' in text
    # A distinctive phrase from each of the two tooltips.
    assert "the episode this file is matched to" in text  # target
    assert "peers" in text  # sources


@pytest.mark.asyncio
async def test_target_page_resolves_title_via_segment_mapping() -> None:
    """/targets/{id} shares _to_display_rows with /files: confirm handle_target ALSO
    threads the segment_by_id mapping (both call sites, per the brief)."""
    text, _ = await _files_page("/targets/062A", _one_file(_decision("062A", "download")))
    assert "062A / S02E11A" in text
    assert "La Grenouille Cosmique" in text


# ---------------------------------------------------------------------------
# Whole-episode end-to-end (Task 4, the multi-target headline behavior):
# one recovered whole-episode file resolves BOTH lost segments, renders as
# ONE <tr> with an aggregated Target/Title/Tier cell, and appears under EACH
# of its targets.
# ---------------------------------------------------------------------------


def _targets_ab() -> tuple[TargetSegment, ...]:
    return parse_targets(
        yaml.safe_load(
            """\
episodes:
  - season: 3
    seasonal_number: 6
    absolute_number: 72
    segments:
      - letter: a
        title: "Le Defi"
      - letter: b
        title: "Duel Contre Giroro"
"""
        )
    )


@pytest.mark.asyncio
async def test_files_whole_episode_renders_one_row_with_aggregated_targets() -> None:
    listing = _one_file(_decision("072A", "download"), _decision("072B", "download"))
    text, _ = await _files_page("/files", listing, _targets_ab())
    assert text.count(TEST_HASH[:8]) == 1
    assert '<div class="cell-line">072A / S03E06A</div>' in text
    assert '<div class="cell-line">072B / S03E06B</div>' in text
    assert '<div class="cell-line cell-title" title="Le Defi">Le Defi</div>' in text
    assert (
        '<div class="cell-line cell-title" title="Duel Contre Giroro">Duel Contre Giroro</div>'
        in text
    )
    assert "<td>download</td>" in text


# ---------------------------------------------------------------------------
# Dashboard controls and client status (stage 2 D20): each POST dispatches one intent and
# redirects (PRG) to the dashboard, whose ?done banner maps a known code to a message.
# ---------------------------------------------------------------------------


@pytest.fixture
def controls_app() -> tuple[Starlette, FakeCrawlControls]:
    """App wired with fake controls, for the runtime-control route tests."""
    controls = FakeCrawlControls()
    return _app_on_fakes(controls=controls), controls


@pytest.mark.asyncio
async def test_dashboard_renders_the_three_action_forms_and_the_running_crawl(
    controls_app: tuple[Starlette, FakeCrawlControls],
) -> None:
    app, _ = controls_app
    text = await _page(app, "/")
    assert 'action="/controls/pause"' in text
    assert 'action="/controls/resume"' in text
    assert 'action="/controls/restart"' in text
    assert "The crawl is running." in text


@pytest.mark.asyncio
async def test_dashboard_shows_a_paused_crawl() -> None:
    app = _app_on_fakes(crawl_summary=replace(_CRAWL_SUMMARY, is_paused=True))
    assert "The crawl is paused." in await _page(app, "/")


@pytest.mark.asyncio
async def test_the_controls_page_and_its_nav_entry_are_gone(
    controls_app: tuple[Starlette, FakeCrawlControls],
) -> None:
    app, _ = controls_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        page = await client.get("/controls")
        dashboard = await client.get("/")
    assert page.status_code == 404
    assert 'href="/controls"' not in dashboard.text


@pytest.mark.asyncio
async def test_dashboard_without_done_shows_no_banner(
    controls_app: tuple[Starlette, FakeCrawlControls],
) -> None:
    app, _ = controls_app
    assert "control-banner" not in await _page(app, "/")


@pytest.mark.asyncio
async def test_dashboard_unknown_done_shows_no_banner(
    controls_app: tuple[Starlette, FakeCrawlControls],
) -> None:
    app, _ = controls_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/?done=bogus")
    assert resp.status_code == 200
    assert "control-banner" not in resp.text


@pytest.mark.asyncio
async def test_there_is_no_force_cycle_control(
    controls_app: tuple[Starlette, FakeCrawlControls],
) -> None:
    app, controls = controls_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/controls/force-cycle")
    assert resp.status_code == 404
    assert controls.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "call", "done"),
    [
        ("pause", "pause_crawl", "paused"),
        ("resume", "resume_crawl", "resumed"),
        ("restart", "request_shutdown", "restarted"),
    ],
)
async def test_each_control_dispatches_and_redirects_to_the_dashboard(
    controls_app: tuple[Starlette, FakeCrawlControls], action: str, call: str, done: str
) -> None:
    app, controls = controls_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/controls/{action}")
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/?done={done}"
    assert controls.calls == [call]


@pytest.mark.parametrize(
    ("action", "banner"),
    [
        (
            "pause",
            "Crawl paused. Searches in flight or already waiting their network slot still run, "
            "then the crawler idles.",
        ),
        ("resume", "Crawl resumed."),
        ("restart", "Restart requested. The service goes offline briefly, then returns."),
    ],
)
@pytest.mark.asyncio
async def test_each_control_followed_lands_on_its_dashboard_banner(
    controls_app: tuple[Starlette, FakeCrawlControls], action: str, banner: str
) -> None:
    app, controls = controls_app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=True
    ) as client:
        resp = await client.post(f"/controls/{action}")
    assert resp.status_code == 200
    assert f'<p class="control-banner" role="status">{banner}</p>' in resp.text
    assert len(controls.calls) == 1


_CHANNELS = (ChannelStatus("ed2k", True, False), ChannelStatus("x", False, None))


async def _clients_section(reading: StatusReading | None, *, is_fresh: bool = True) -> str:
    client_summary = ClientSummary("amuled", reading, is_fresh=is_fresh)
    summary = replace(_CRAWL_SUMMARY, client_summaries=(client_summary,))
    text = await _page(_app_on_fakes(crawl_summary=summary), "/")
    return text[text.index("<h2>Clients</h2>") : text.index("<h2>Crawl</h2>")]


def _read_now(status: ClientStatus | None) -> StatusReading:
    return StatusReading(FakeTime().wall.now(), status)


@pytest.mark.asyncio
async def test_dashboard_shows_each_client_and_channel_of_a_current_reading() -> None:
    section = await _clients_section(_read_now(ClientStatus("2.3.3", _CHANNELS)))
    assert "<h3>amuled</h3>" in section
    assert "<th>Connected</th>" in section
    assert "<dd>2.3.3</dd>" in section
    assert "<dt>API reachable</dt><dd>yes</dd>" in section
    assert "<dd>Read at 2026-06-12 00:00Z.</dd>" in section
    assert "<td>ed2k</td><td>yes</td><td>no</td>" in section
    assert "<td>x</td><td>no</td><td>unknown</td>" in section


@pytest.mark.asyncio
async def test_dashboard_shows_an_unknown_version() -> None:
    section = await _clients_section(_read_now(ClientStatus(None, ())))
    assert "<dt>Version</dt><dd>unknown</dd>" in section
    assert "No current channel reading." in section


@pytest.mark.asyncio
async def test_dashboard_shows_an_unreachable_client() -> None:
    section = await _clients_section(_read_now(None))
    assert "<dt>API reachable</dt><dd>no</dd>" in section
    assert "No current channel reading." in section


@pytest.mark.asyncio
async def test_dashboard_never_shows_a_stale_reading_as_current() -> None:
    section = await _clients_section(_read_now(ClientStatus("2.3.3", _CHANNELS)), is_fresh=False)
    assert "<dd>Out of date: last reading at 2026-06-12 00:00Z.</dd>" in section
    assert "2.3.3" not in section
    assert "<dt>API reachable</dt><dd>unknown</dd>" in section
    assert "<td>ed2k</td>" not in section


@pytest.mark.asyncio
async def test_dashboard_shows_a_client_not_read_yet() -> None:
    section = await _clients_section(None, is_fresh=False)
    assert "<h3>amuled</h3>" in section
    assert "<dd>No reading yet.</dd>" in section
    assert "<dt>API reachable</dt><dd>unknown</dd>" in section


# ---------------------------------------------------------------------------
# Bidirectional column sorting (Task 3): normalizers + header builder (direct)
# and the sortable <thead> end-to-end.
# ---------------------------------------------------------------------------


def test_normalize_sort_valid_unknown_missing() -> None:
    assert _normalize_sort("size") is CatalogEntrySort.SIZE
    assert _normalize_sort("bogus") is CatalogEntrySort.LAST_SEEN
    assert _normalize_sort("size; drop table files") is CatalogEntrySort.LAST_SEEN
    assert _normalize_sort(None) is CatalogEntrySort.LAST_SEEN


def test_normalize_dir_valid_unknown_missing() -> None:
    assert _normalize_direction("asc") is SortDirection.ASC
    assert _normalize_direction("bogus") is SortDirection.DESC
    assert _normalize_direction(None) is SortDirection.DESC


def test_sort_headers_default_state_no_filters() -> None:
    headers = _sort_headers(active_sort="last_seen", active_direction="desc", kept_params={})
    # active column: last_seen, showing desc; its link flips to asc. sort=last_seen is the
    # DEFAULT sort so it is OMITTED from the URL (the omit-defaults invariant); only direction=asc
    # shows.
    assert headers.last_seen.indicator == "desc"
    assert headers.last_seen.url == "/files?direction=asc"
    # inactive columns: no indicator, per-column default direction, sort/dir omitted when default
    assert headers.name.indicator == ""
    assert headers.name.url == "/files?sort=name&direction=asc"  # Name default dir is asc
    assert headers.size.url == "/files?sort=size"  # Size default dir desc == DEFAULT_DIR -> omitted
    assert headers.tier.url == "/files?sort=tier"


def test_sort_headers_active_column_flips_and_preserves_filters() -> None:
    headers = _sort_headers(
        active_sort="size",
        active_direction="asc",
        kept_params={"search": "keroro", "tier": "notify"},
    )
    # active column size, currently asc -> indicator asc, link flips to desc (== default -> omitted)
    assert headers.size.indicator == "asc"
    assert headers.size.url == "/files?search=keroro&tier=notify&sort=size"
    # an inactive column keeps the filters and sets its own sort + default dir
    assert headers.name.indicator == ""
    assert headers.name.url == "/files?search=keroro&tier=notify&sort=name&direction=asc"


@pytest.mark.asyncio
async def test_files_sort_by_size_renders_the_rows_in_the_order_listed() -> None:
    first, second = (
        replace(_catalog_entry(decisions=()), file=FileKey(Network.ED2K, h * 32)) for h in "ca"
    )
    text, call = await _files_page("/files?sort=size&direction=asc", _listing(first, second))
    _, old_key = await _files_page("/files?sort=size&dir=asc")
    assert call == replace(_DEFAULT_CALL, sort=CatalogEntrySort.SIZE, direction=SortDirection.ASC)
    assert 0 < text.index("cccccccc") < text.index("aaaaaaaa")
    # 4.x's ``dir`` is ignored: the default direction
    assert old_key == replace(_DEFAULT_CALL, sort=CatalogEntrySort.SIZE)


@pytest.mark.asyncio
async def test_files_renders_sortable_header_link() -> None:
    text, _ = await _files_page("/files")
    # the Name header is a sort link with a data-sort attribute (default state -> not active)
    assert 'href="/files?sort=name&amp;direction=asc"' in text
    assert 'data-sort="desc"' in text  # last_seen is the active default column


@pytest.mark.asyncio
async def test_target_page_headers_are_plain_text() -> None:
    text, _ = await _files_page("/targets/062A")
    # no sort links on a target page (headers tuple is empty -> the {% else %} plain label renders)
    assert "?sort=" not in text


@pytest.mark.asyncio
async def test_sort_header_links_preserve_target_and_tier_filters() -> None:
    """An active target + tier filter is carried into every sort-header link (the ordered
    ``filters`` dict is threaded into each header URL, then sort/dir override for that column)."""
    text, call = await _files_page("/files?target_id=062A&tier=download")
    assert call == replace(_DEFAULT_CALL, target_id="062A", tier="download")
    # the Name header keeps both filters (autoescaped & -> &amp;) then adds its own sort + dir
    assert "target_id=062A&amp;tier=download&amp;sort=name&amp;direction=asc" in text


# ---------------------------------------------------------------------------
# Filename search + tier facet (Task 4): the two builders (direct) and the
# rendered search form + facet chips end-to-end.
# ---------------------------------------------------------------------------


def test_tier_facets_all_reset_and_masks_catalog() -> None:
    facets = _tier_facets(
        file_count_by_tier={"download": 1, "notify": 2, "catalog": 5},
        active_tier=None,
        kept_params={},
    )
    assert facets[0].label == "all"
    assert facets[0].selected_flag == "1"  # no tier active → all selected
    assert facets[0].url == "/files"
    labels = [f.label for f in facets[1:]]
    assert labels == ["download", "notify", "unidentified"]  # fixed order, catalog masked
    assert facets[1].count_display == "(1)"
    assert facets[1].url == "/files?tier=download"


def test_tier_facets_selected_and_preserves_base() -> None:
    facets = _tier_facets(
        file_count_by_tier={"download": 1, "notify": 2},
        active_tier="notify",
        kept_params={"search": "keroro", "sort": "size"},
    )
    notify = next(f for f in facets if f.label == "notify")
    assert notify.selected_flag == "1"
    assert notify.url == "/files?search=keroro&sort=size&tier=notify"
    assert facets[0].url == "/files?search=keroro&sort=size"  # all-reset keeps base, drops tier


def test_tier_facets_only_present_tiers_appear() -> None:
    facets = _tier_facets(file_count_by_tier={"notify": 3}, active_tier=None, kept_params={})
    assert [f.label for f in facets] == ["all", "notify"]


def test_search_bar_prefill_and_hidden_excludes_q() -> None:
    bar = _search_bar(search_text="keroro", kept_params={"tier": "notify", "sort": "size"})
    assert bar.query == "keroro"
    assert bar.hidden == (
        HiddenInput(name="tier", value="notify"),
        HiddenInput(name="sort", value="size"),
    )


def test_search_bar_no_query_is_empty_string() -> None:
    bar = _search_bar(search_text=None, kept_params={})
    assert bar.query == ""
    assert bar.hidden == ()


@pytest.mark.asyncio
async def test_files_renders_search_prefill_and_facet() -> None:
    listing = replace(_listing(), file_count_by_tier={"catalog": 1})
    text, call = await _files_page("/files?search=keroro&show_unmatched=1", listing)
    assert call == replace(_DEFAULT_CALL, search_text="keroro", matched_only=False)
    assert 'name="search"' in text
    assert 'value="keroro"' in text  # prefill
    assert 'name="show_unmatched"' in text  # carried as a hidden input
    # one catalog-tier file → the facet shows "unidentified (1)"
    assert (
        '<a href="/files?search=keroro&amp;show_unmatched=1&amp;tier=catalog" data-selected="">'
        "unidentified (1)</a>"
    ) in text


@pytest.mark.asyncio
async def test_files_filter_bar_wraps_facets_then_search() -> None:
    """The facet chips and the search form share one .filter-bar row, chips first.

    The order is the layout contract: the row is a flex line and the form is pushed right by
    `margin-left: auto`, which only lands the form on the right if it is the LAST child.
    """
    text, _ = await _files_page("/files")
    row = re.search(r'<div class="filter-bar">(.*?)</div>', text, re.DOTALL)
    assert row is not None  # the wrapper is a div now, no longer the form itself
    inner = row.group(1)
    facet_at = inner.find('<nav class="tier-facet"')
    form_at = inner.find('<form class="files-search"')
    assert facet_at != -1  # the chips live inside the row
    assert form_at != -1  # the form lives inside the row, and carries files-search
    assert facet_at < form_at  # chips left, search right
    assert 'role="search"' in inner  # the form stays a landmark after the reclassing


@pytest.mark.asyncio
async def test_target_page_has_no_filter_bar() -> None:
    text, _ = await _files_page("/targets/062A")
    assert 'name="search"' not in text  # no search form on a target page
    assert "tier-facet" not in text  # no facet on a target page
    assert "filter-bar" not in text  # the wrapper itself renders nothing either
    assert "files-search" not in text


# ---------------------------------------------------------------------------
# Top nav: active state + the page titles it replaces
# ---------------------------------------------------------------------------

# The nav destinations, in render order: (path, label). Mirrors the table wired in
# adapters/driving/webui/app.py; a test that drifts from it fails on the label or the href.
_NAV_ENTRIES: tuple[tuple[str, str], ...] = (
    ("/", "Dashboard"),
    ("/files", "Files"),
    ("/sources", "Sources"),
    ("/node", "Node"),
    ("/console", "Console"),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "label"), _NAV_ENTRIES)
async def test_nav_marks_only_the_current_page_entry_as_active(
    populated_app: tuple[Starlette, str], path: str, label: str
) -> None:
    """On each nav destination: its own entry is a non-link marked aria-current="page" (the CSS
    hook that bolds it), its nav link is gone, every other entry stays a link, and exactly one
    entry is active."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(path)
    assert resp.status_code == 200
    assert f'<span aria-current="page">{label}</span>' in resp.text
    assert f'<a href="{path}">{label}</a>' not in resp.text
    for other_path, other_label in _NAV_ENTRIES:
        if other_path == path:
            continue
        assert f'<a href="{other_path}">{other_label}</a>' in resp.text
    assert resp.text.count('aria-current="page"') == 1


@pytest.mark.asyncio
async def test_nav_links_to_the_amule_web_ui(populated_app: tuple[Starlette, str]) -> None:
    """The container publishes two web surfaces (design §9): the nav carries a link to amuleweb
    so the operator can reach it from here. It is an EXTERNAL entry, so it never goes active."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert f'<a href="{_AMULE_URL}">aMule</a>' in resp.text
    assert resp.text.count('aria-current="page"') == 1  # still only the current page


@pytest.mark.asyncio
async def test_nav_amule_link_uses_the_configured_base() -> None:
    """The base is configurable so the link survives a reverse proxy in front of 8080: p2pwatch
    cannot infer from the request how amuleweb is reachable from the operator's browser."""
    app = _app_on_fakes(amule_url="https://mule.example.org/amule")
    assert '<a href="https://mule.example.org/amule">aMule</a>' in await _page(app, "/")


@pytest.mark.asyncio
async def test_nav_on_a_non_nav_path_renders_every_entry_as_a_link(
    populated_app: tuple[Starlette, str],
) -> None:
    """A page that is NOT a nav destination (here /files/{file_id}, the file detail) leaves every
    entry a link and marks none active: the active entry is an EXACT path match, not a prefix."""
    app, hash_ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert resp.status_code == 200
    for path, label in _NAV_ENTRIES:
        assert f'<a href="{path}">{label}</a>' in resp.text
    assert "aria-current" not in resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [path for path, _ in _NAV_ENTRIES])
async def test_nav_pages_render_no_page_title(
    populated_app: tuple[Starlette, str], path: str
) -> None:
    """The nav destinations carry no <h1>: the title duplicated the nav, whose bold current
    entry now names the page. Their <h2> section headings stay."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(path)
    assert resp.status_code == 200
    assert "<h1>" not in resp.text


@pytest.mark.asyncio
async def test_target_page_renders_its_own_heading() -> None:
    """/targets/{id} reuses files.html but is NOT a nav destination, so nothing else would name
    it: it passes its own heading in the ``headings`` tuple (files.html itself renders none)."""
    text, _ = await _files_page("/targets/062A")
    assert "<h1>Files for target 062A</h1>" in text


# ---------------------------------------------------------------------------
# The interval selector (source points spec, D6)
# ---------------------------------------------------------------------------

_SECOND = timedelta(seconds=1)
_OCT_8, _OCT_11 = datetime(2026, 10, 8, tzinfo=UTC), datetime(2026, 10, 11, tzinfo=UTC)
_EDGES = "<p>Periods are cut at the interval's edges.</p>"


def _micros(moment: datetime) -> int:
    return (moment - datetime(1970, 1, 1, tzinfo=UTC)) // timedelta(microseconds=1)


def _seed_points(catalog_db: Path, ed2k_hash: str, *moments: datetime) -> None:
    """One source's points on the file, one variant, and an observation named after each."""
    with sqlite3.connect(catalog_db) as conn:
        insert_source(conn, _USER)
        variant = insert_source_variant(conn, ed2k_hash, _USER)
        for n, moment in enumerate(moments):
            insert_source_point(conn, variant, _micros(moment))
            insert_observation(conn, ed2k_hash, f"{n}.avi", observed_at=moment.isoformat())


@pytest.mark.asyncio
async def test_an_interval_of_3_days_shows_those_days_only_and_moves_by_3_days(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    _seed_points(catalog_db, hash_, _OCT_8 - _SECOND, _OCT_8, _OCT_11 - _SECOND, _OCT_11)
    path = _detail_url(hash_)
    page = await _sources_page(app, f"{path}?{_query(_OCT_8, _OCT_11)}")
    assert [f"<td>{n}.avi</td>" in page for n in range(4)] == [False, True, True, False]
    cells = ("2026-10-07 23:59:59Z", "2026-10-08 00:00:00Z", "2026-10-10 23:59:59Z")
    assert [f"<td>{cell}</td>" in page for cell in cells] == [False, True, True]
    assert "<td>2026-10-11 00:00:00Z</td>" not in page
    days = timedelta(days=3)
    assert f"<a {_href(path, _OCT_8 - days, _OCT_8)}>← Previous</a>" in page
    assert f"<a {_href(path, _OCT_11, _OCT_11 + days)}>Next →</a>" in page
    assert "Showing 2026-10-08 00:00:00Z to 2026-10-11 00:00:00Z." in page
    assert _EDGES in page


@pytest.mark.asyncio
async def test_an_interval_of_30_days_shows_the_7_ending_at_its_to_and_says_so(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    week_before = _OCT_11 - timedelta(days=7)
    _seed_points(catalog_db, hash_, week_before - _SECOND, week_before)
    month = _query(_OCT_11 - timedelta(days=30), _OCT_11)
    page = await _sources_page(app, f"{_detail_url(hash_)}?{month}")
    notice = "The interval requested is longer than 7 days: showing the 7 days ending at its end."
    assert f"<p>{notice}</p>" in page
    assert '<input type="datetime-local" name="from" step="1" value="2026-10-04T00:00:00">' in page
    assert '<input type="datetime-local" name="to" step="1" value="2026-10-11T00:00:00">' in page
    assert ["<td>0.avi</td>" in page, "<td>1.avi</td>" in page] == [False, True]


@pytest.mark.asyncio
async def test_no_parameter_shows_the_last_7_days_and_no_next(
    populated_app: tuple[Starlette, str],
) -> None:
    app, hash_ = populated_app
    path = _detail_url(hash_)
    page = await _sources_page(app, path)
    now = _WALL_CLOCK.now()
    assert "Showing 2026-10-07 20:00:00Z to 2026-10-14 20:00:00Z." in page
    assert f"<a {_href(path, now - timedelta(days=14), now - timedelta(days=7))}>" in page
    assert "Next →" not in page
    assert "longer than 7 days" not in page


@pytest.mark.asyncio
async def test_the_presets_end_now(populated_app: tuple[Starlette, str]) -> None:
    app, hash_ = populated_app
    path = _detail_url(hash_)
    page = await _sources_page(app, f"{path}?{_query(_OCT_8, _OCT_11)}")
    now, hours = _WALL_CLOCK.now(), {"hour": 1, "6 hours": 6, "24 hours": 24, "7 days": 168}
    for label, span in hours.items():
        assert f"<a {_href(path, now - timedelta(hours=span), now)}>Last {label}</a>" in page


@pytest.mark.asyncio
async def test_a_period_crossing_from_starts_at_its_first_point_inside(
    populated_app: tuple[Starlette, str], catalog_db: Path
) -> None:
    app, hash_ = populated_app
    _seed_points(catalog_db, hash_, *(_OCT_8 + n * 30 * _SECOND for n in (-1, 1, 2)))
    page = await _sources_page(app, f"{_detail_url(hash_)}?{_query(_OCT_8, _OCT_11)}")
    period = ("queued", "unknown", "unknown", "2026-10-08 00:00:30Z", "2026-10-08 00:01:00Z")
    assert "".join(f"<td>{cell}</td>" for cell in period) in page


@pytest.mark.parametrize(
    ("path", "kept"),
    [(_USER_PAGE, {}), ("/sources/name", {"source_name": "AnimuseeFMR"})],
    ids=["source", "name"],
)
@pytest.mark.asyncio
async def test_the_source_and_name_pages_keep_their_parameters_and_their_interval(
    populated_app: tuple[Starlette, str], catalog_db: Path, path: str, kept: dict[str, str]
) -> None:
    app, hash_ = populated_app
    _seed_points(catalog_db, hash_, _OCT_8)
    with sqlite3.connect(catalog_db) as conn:
        insert_source_point(conn, insert_source_variant(conn, hash_, None), _micros(_OCT_8))
    on_page_2 = {**kept, "page": "2"}
    page = await _sources_page(app, f"{path}?{_query(_OCT_8, _OCT_11, **on_page_2)}")
    hidden = "".join(
        f'<input type="hidden" name="{name}" value="{value}">' for name, value in on_page_2.items()
    )
    assert f'<form method="get">{hidden}<label>' in page
    previous_interval = _href(path, _OCT_8 - timedelta(days=3), _OCT_8, **on_page_2)
    assert f"<a {previous_interval}>← Previous</a>" in page
    first_page = _href(path, _OCT_8, _OCT_11, **kept).removesuffix('"') + '&amp;page=1"'
    assert f"<a {first_page}>← Previous</a>" in page
    assert "<td>2026-10-08 00:00:00Z</td>" in page
    assert _EDGES in page
