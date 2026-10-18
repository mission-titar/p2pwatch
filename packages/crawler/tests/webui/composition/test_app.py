"""TDD tests for the Starlette application (composition/app.py, Task 11)."""

import re
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from jinja2 import Environment, FileSystemLoader, UndefinedError, meta
from starlette.applications import Starlette
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from catalog_matching.domain.config import MatcherConfig
from catalog_matching.domain.models import TargetSegment
from catalog_matching.domain.validation import parse_matcher_config, parse_targets
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import SourceKey
from p2pwatch.ports.client_status import ChannelStatus, ClientStatus, StatusReading
from p2pwatch.webui.adapters.catalog_read import PAGE_SIZE
from p2pwatch.webui.composition.app import (
    _normalize_direction,
    _normalize_sort,
    _resolve_target_display,
    _search_bar,
    _sort_headers,
    _tier_facets,
    _to_display_rows,
    build_app,
)
from p2pwatch.webui.domain.views import (
    DecisionCell,
    FileDecision,
    FileRow,
    HiddenInput,
)
from p2pwatch_testing.application.fakes import FakeTime
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


class _Readings:
    """The status board as the webui reads it: fixed readings, all current or all out of date."""

    def __init__(self, readings: dict[str, StatusReading | None], *, current: bool = True) -> None:
        self._readings = readings
        self._current = current

    def readings(self) -> Mapping[str, StatusReading | None]:
        return self._readings

    def is_current(self, client_name: str) -> bool:
        return self._current


_NO_STATUS = _Readings({})


def _detail_url(ed2k_hash: str) -> str:
    return f"/files/{file_id(ed2k_hash).hex()}"


def _query(since: datetime, until: datetime, **kept: str) -> str:
    """An interval's query string, in the webui's time format."""
    ends = {"from": f"{since:%Y-%m-%d %H:%M:%S}Z", "to": f"{until:%Y-%m-%d %H:%M:%S}Z"}
    return urlencode({**kept, **ends})


def _href(path: str, since: datetime, until: datetime, **kept: str) -> str:
    """An interval's link as the page escapes it."""
    return f'href="{path}?{_query(since, until, **kept)}"'.replace("&", "&amp;")


class _RecordingControl:
    """Records runtime-control intents (phase P6a). Satisfies ``CrawlerControl`` structurally;
    the throwaway instances passed to the read-path fixtures are never invoked, while the
    controls-route tests inspect ``calls``."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.paused = False

    def is_paused(self) -> bool:
        return self.paused

    def pause(self) -> None:
        self.calls.append("pause")

    def resume(self) -> None:
        self.calls.append("resume")

    def request_shutdown(self) -> None:
        self.calls.append("request_shutdown")


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

    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-test-001"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()

    matcher_config = _matcher()
    targets = _targets()

    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"

    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.fixture
def app_no_decision(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """File without a match decision (decision=None branch)."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 100_000_000)
        insert_observation(
            conn,
            TEST_HASH,
            "keroro_s2e62a_vf.avi",
            size_bytes=100_000_000,
            source_count=5,
        )
        # No decision

    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-no-dec"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()

    matcher_config = _matcher()
    targets = _targets()

    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"

    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.fixture
def app_retracted_decision(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """File whose LATEST decision for target 062A is a per-target retraction sentinel
    (``target_id="062A", rule_name="", tier="retracted"``): must be treated exactly like
    ``app_no_decision`` (unmatched), never like a real decision."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 100_000_000)
        insert_observation(
            conn,
            TEST_HASH,
            "keroro_s2e62a_vf.avi",
            size_bytes=100_000_000,
            source_count=5,
        )
        # First a real decision (was matched)...
        insert_decision(conn, TEST_HASH, "062A", "download", rule_name="high_confidence")
        # ...then the per-target retraction sentinel, now the LATEST row for 062A.
        insert_decision(
            conn,
            TEST_HASH,
            "062A",
            "retracted",
            rule_name="",
            decided_at="2026-06-23T10:00:00.000000+00:00",
        )

    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-retracted"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()

    matcher_config = _matcher()
    targets = _targets()

    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"

    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
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

    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-no-obs"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()

    matcher_config = _matcher()
    targets = _targets()

    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"

    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.fixture
def app_unknown_target(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """File with a decision for a target_id unknown to the current config."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 100_000_000)
        insert_observation(
            conn,
            TEST_HASH,
            "keroro_s2e62a_vf.avi",
            size_bytes=100_000_000,
            source_count=5,
        )
        # target_id unknown to the current YAML config
        insert_decision(conn, TEST_HASH, "S9E999Z", "catalog", rule_name="catalog")

    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-unk"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()

    matcher_config = _matcher()
    targets = _targets()

    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"

    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.fixture
def app_download_tier_known_target(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """A non-catalog decision (tier=download) on a target_id resolvable in the current
    targets.yaml. Task 3 resolution rule: the "resolvable id" case."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 100_000_000)
        insert_observation(
            conn,
            TEST_HASH,
            "keroro_s2e62a_vf.avi",
            size_bytes=100_000_000,
            source_count=5,
        )
        insert_decision(conn, TEST_HASH, "062A", "download", rule_name="high_confidence")

    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-dl"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()

    matcher_config = _matcher()
    targets = _targets()

    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"

    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.fixture
def app_download_tier_unknown_target(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """A non-catalog decision (tier=download) on a target_id NOT in the current
    targets.yaml. Task 3 resolution rule: the "unknown id" case."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 100_000_000)
        insert_observation(
            conn,
            TEST_HASH,
            "keroro_s9e999z_vf.avi",
            size_bytes=100_000_000,
            source_count=5,
        )
        insert_decision(conn, TEST_HASH, "999Z", "download", rule_name="high_confidence")

    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-dl-unk"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()

    matcher_config = _matcher()
    targets = _targets()

    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"

    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
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


@pytest.mark.asyncio
async def test_dashboard_returns_200_with_target_id(
    populated_app: tuple[Starlette, str],
) -> None:
    """/ → 200 + contains 062A in the page."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "062A" in resp.text


@pytest.mark.asyncio
async def test_dashboard_excludes_catalog_tier_from_coverage(
    populated_app: tuple[Starlette, str],
) -> None:
    """The only decision in ``populated_app`` is the ``keroro_large`` catch-all (tier=catalog)
    on 062A. It must NOT count as coverage: the 062A row reads none / "·" / 0, never the
    polluted partial / catalog / 1 the catch-all tie-break would otherwise produce."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "<td>none</td>" in resp.text
    assert "<td>0</td>" in resp.text
    assert "<td>partial</td>" not in resp.text
    assert "<td>catalog</td>" not in resp.text


@pytest.mark.asyncio
async def test_files_returns_200_with_file_row(
    populated_app: tuple[Starlette, str],
) -> None:
    """/files → 200 + contains the inserted file's hash."""
    app, hash_ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert resp.status_code == 200
    assert hash_[:8] in resp.text


@pytest.mark.asyncio
async def test_files_default_hides_unmatched(
    app_no_decision: tuple[Starlette, str],
) -> None:
    """/files defaults to matched-only → an unmatched file is hidden."""
    app, hash_ = app_no_decision
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert resp.status_code == 200
    assert hash_[:8] not in resp.text
    assert "Showing matched files only: 0 of 1 catalogued." in resp.text
    assert "Show all catalogued files" in resp.text
    assert "show_unmatched=1" in resp.text


@pytest.mark.asyncio
async def test_files_default_hides_retracted(
    app_retracted_decision: tuple[Starlette, str],
) -> None:
    """A retracted latest decision is treated exactly like no decision: the matched-only
    default (/files) hides it and counts it as unmatched in the summary."""
    app, hash_ = app_retracted_decision
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert resp.status_code == 200
    assert hash_[:8] not in resp.text
    assert "Showing matched files only: 0 of 1 catalogued." in resp.text


@pytest.mark.asyncio
async def test_files_retracted_shows_as_unmatched_in_all_view(
    app_retracted_decision: tuple[Starlette, str],
) -> None:
    """The all-view (show_unmatched=1) renders a retracted file as an unmatched row: "·"
    cells, never "<td>unidentified</td>", never a tier badge (e.g. never the literal
    "retracted" string in a cell)."""
    app, hash_ = app_retracted_decision
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files?show_unmatched=1")
    assert resp.status_code == 200
    assert hash_[:8] in resp.text
    assert "<td>unidentified</td>" not in resp.text
    assert "<td>retracted</td>" not in resp.text
    assert "La Grenouille Cosmique" not in resp.text


@pytest.mark.asyncio
async def test_files_toggle_preserves_active_filter(
    populated_app: tuple[Starlette, str],
) -> None:
    """The matched→all toggle must carry the active q filter (spec §5: filters preserved)."""
    app, hash_ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files?search=keroro")
    assert resp.status_code == 200
    assert hash_[:8] in resp.text  # the matched file still shows under the q filter
    # Jinja2 autoescapes "&" to "&amp;" inside the href attribute.
    assert 'href="/files?search=keroro&amp;show_unmatched=1">Show all catalogued files' in resp.text


@pytest.mark.parametrize(("key", "old_key"), [("search", "q"), ("target_id", "target")])
@pytest.mark.asyncio
async def test_files_filters_on_its_query_key_and_ignores_the_4x_one(
    populated_app: tuple[Starlette, str], key: str, old_key: str
) -> None:
    app, hash_ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        filtered = await client.get(f"/files?{key}=001A")
        unfiltered = await client.get(f"/files?{old_key}=001A")
    assert hash_[:8] not in filtered.text
    assert hash_[:8] in unfiltered.text


@pytest.mark.asyncio
async def test_files_show_unmatched_reveals_and_toggles_back(
    app_no_decision: tuple[Starlette, str],
) -> None:
    """/files?show_unmatched=1 reveals the whole catalogue; toggle points back to matched-only."""
    app, hash_ = app_no_decision
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files?show_unmatched=1")
    assert resp.status_code == 200
    assert hash_[:8] in resp.text
    assert "Showing all catalogued files: 1 catalogued (0 matched)." in resp.text
    assert "Matched only" in resp.text
    assert 'href="/files">Matched only' in resp.text  # toggle drops the param → bare /files


@pytest.mark.asyncio
async def test_file_detail_with_decision_returns_200(
    populated_app: tuple[Starlette, str],
) -> None:
    """/files/{file_id} with a decision → 200, contains the ed2k link + explanation info."""
    app, hash_ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert resp.status_code == 200
    assert "ed2k://" in resp.text
    assert "062A" in resp.text
    assert "AICH" not in resp.text


@pytest.mark.asyncio
async def test_file_detail_shows_the_network_and_the_native_id(
    populated_app: tuple[Starlette, str],
) -> None:
    app, hash_ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    page = re.sub(r">\s+<", "><", resp.text)
    assert "<dt>Network</dt><dd>ed2k</dd>" in page
    assert f"<dt>Native ID</dt><dd>{hash_}</dd>" in page
    assert "eD2k hash" not in page


@pytest.mark.asyncio
async def test_file_detail_by_the_ed2k_hash_returns_404(
    populated_app: tuple[Starlette, str],
) -> None:
    app, hash_ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/files/{hash_}")
    assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed",
    ["zz", file_id(TEST_HASH).hex().upper(), file_id(TEST_HASH).hex()[:31], " " * 32],
)
async def test_file_detail_malformed_file_id_returns_404(
    populated_app: tuple[Starlette, str], malformed: str
) -> None:
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/files/{malformed}")
    assert resp.status_code == 404
    assert "not found" in resp.text.lower()


@pytest.mark.asyncio
async def test_files_list_links_each_file_to_its_file_id(
    populated_app: tuple[Starlette, str],
) -> None:
    app, hash_ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert f'<a href="{_detail_url(hash_)}">{hash_[:8]}…</a>' in resp.text


@pytest.fixture
def app_vetoed_alias(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """One file seen under a clean name and a foreign alias, with a veto on the alias."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 100_000_000)
        insert_observation(conn, TEST_HASH, "keroro_s2e62a_vf.avi")
        insert_observation(
            conn, TEST_HASH, "keroro ITA.avi", observed_at="2026-06-23T10:00:00.000000+00:00"
        )
        insert_decision(conn, TEST_HASH, "062A", "catalog", rule_name="catalog")
    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-veto"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()
    matcher_config = parse_matcher_config(
        {
            "tokens": {
                "keroro": {"keyword": "keroro"},
                "vf": {"regex": "vf"},
                "ita": {"regex": r"\bITA\b"},
            },
            "vetoes": ["ita"],
            "rules": [
                {
                    "name": "catalog",
                    "tier": "catalog",
                    "scope": "unattributed",
                    "all": ["keroro", "vf"],
                }
            ],
        }
    )

    import p2pwatch.webui

    webui_dir = Path(p2pwatch.webui.__file__).parent / "adapters"
    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=_targets(),
        templates_dir=webui_dir / "templates",
        static_dir=webui_dir / "static",
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.mark.asyncio
async def test_file_detail_explains_over_every_name_and_lists_the_vetoes_fired(
    app_vetoed_alias: tuple[Starlette, str],
) -> None:
    app, hash_ = app_vetoed_alias
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert resp.status_code == 200
    assert "Vetoes fired:" in resp.text
    assert "<li>ita</li>" in resp.text  # fired by the ITA alias only
    assert "<li>catalog</li>" in resp.text  # fired by the VF name only


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
async def test_file_detail_without_decision_returns_200(
    app_no_decision: tuple[Starlette, str],
) -> None:
    """/files/{file_id} without a decision → 200, empty branches rendered."""
    app, hash_ = app_no_decision
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert resp.status_code == 200
    assert "ed2k://" in resp.text
    assert "No matching decision." in resp.text
    assert "No explanation available." in resp.text


@pytest.mark.asyncio
async def test_file_detail_retracted_shows_no_decision(
    app_retracted_decision: tuple[Starlette, str],
) -> None:
    """/files/{file_id} whose LATEST decision is a retraction renders exactly like a file with
    no decision at all: "No matching decision.", never a tier/target/rule badge, and never
    the literal "retracted" string anywhere in the page."""
    app, hash_ = app_retracted_decision
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert resp.status_code == 200
    assert "No matching decision." in resp.text
    assert "No explanation available." in resp.text
    assert "retracted" not in resp.text
    assert "062A" not in resp.text  # the earlier, pre-retraction decision must not leak through


@pytest.mark.asyncio
async def test_file_detail_explanation_none_unknown_target(
    app_unknown_target: tuple[Starlette, str],
) -> None:
    """/files/{file_id} with a target_id unknown to the config → 200 (explanation=None)."""
    app, hash_ = app_unknown_target
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert resp.status_code == 200
    assert "ed2k://" in resp.text


@pytest.mark.asyncio
async def test_file_detail_unknown_hash_returns_404(
    populated_app: tuple[Starlette, str],
) -> None:
    """/files/{file_id} nonexistent (32 hex) → 404."""
    app, _ = populated_app
    unknown = "00000000000000000000000000000000"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/files/{unknown}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_targets_shortcut_returns_200(
    populated_app: tuple[Starlette, str],
) -> None:
    """/targets/{target_id} → 200 (shortcut to filtered /files)."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/targets/062A")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_target_page_has_no_summary_line(
    populated_app: tuple[Starlette, str],
) -> None:
    """/targets/{id} shares files.html, but the matched/all summary is meaningless on a
    target-scoped page: the summary line and its toggle must not render there."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/targets/062A")
    assert resp.status_code == 200
    assert "files-summary" not in resp.text
    assert "Showing matched files only" not in resp.text
    assert "Show all catalogued files" not in resp.text


@pytest.mark.asyncio
async def test_node_returns_200_with_node_info(
    populated_app: tuple[Starlette, str],
) -> None:
    """/node → 200 + contains the node id."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/node")
    assert resp.status_code == 200
    assert "node-test-001" in resp.text


@pytest.mark.asyncio
async def test_files_non_numeric_page_defaults_to_1(
    populated_app: tuple[Starlette, str],
) -> None:
    """/files?page=abc → 200 (non-numeric page → default 1)."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files?page=abc")
    assert resp.status_code == 200


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


@pytest.mark.asyncio
async def test_node_page_shows_each_backoff_and_its_planned_retry_in_utc(
    populated_app: tuple[Starlette, str], local_db: Path
) -> None:
    app, _ = populated_app
    started_at_micros = 1_781_258_400_000_000  # 2026-06-12T10:00:00Z
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = await client.get("/node")
        with sqlite3.connect(local_db) as conn:
            conn.executemany(
                "INSERT INTO backoff_states VALUES (?, ?, ?, ?, ?)",
                [
                    ("amuled", None, 3, started_at_micros, 120.0),
                    ("amuled", "kad", 1, started_at_micros, 2.5),
                ],
            )
        after = await client.get("/node")
    assert "No backoff." in before.text
    cells = re.findall(r"<td>([^<]*)</td>", after.text)
    assert cells == [
        *("amuled", "whole client", "3", "2026-06-12T10:02:00.000000+00:00"),
        *("amuled", "kad", "1", "2026-06-12T10:00:02.500000+00:00"),
    ]


@pytest.mark.asyncio
async def test_node_page_names_a_download_by_its_native_id(
    populated_app: tuple[Starlette, str], local_db: Path
) -> None:
    app, hash_ = populated_app
    with sqlite3.connect(local_db) as conn:
        conn.execute(
            "INSERT INTO downloads (file_id, network, native_id, target_id, state, queued_at)"
            " VALUES (?, 'ed2k', ?, '062A', 'downloading', '2026-10-10')",
            (file_id(hash_), hash_),
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/node")
    assert f"<td>{hash_}</td>" in resp.text


@pytest.mark.asyncio
async def test_node_page_shows_a_downloads_lifecycle(
    populated_app: tuple[Starlette, str], local_db: Path
) -> None:
    app, hash_ = populated_app
    with sqlite3.connect(local_db) as conn:
        conn.execute(
            "INSERT INTO downloads (file_id, network, native_id, target_id, state, queued_at,"
            " last_progress_at, waiting_reason, failure_reason) VALUES"
            " (?, 'ed2k', ?, '062A', 'failed', '2026-10-10', '2026-10-11', 'local_processing',"
            " 'error')",
            (file_id(hash_), hash_),
        )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/node")
    assert "<td>2026-10-11</td>" in resp.text
    assert "<td>local_processing</td>" in resp.text
    assert "<td>error</td>" in resp.text
    assert "None" not in resp.text  # an unknown value shows blank


@pytest.fixture
def app_with_media_obs(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """File with an observation having non-null duration_seconds and bitrate_kbps."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 100_000_000)
        insert_observation(
            conn,
            TEST_HASH,
            "keroro_s2e62a_vf.avi",
            size_bytes=100_000_000,
            source_count=5,
            duration_seconds=1320,
            bitrate_kbps=192,
        )
        insert_decision(conn, TEST_HASH, "062A", "catalog", rule_name="catalog")

    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-media"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()

    matcher_config = _matcher()
    targets = _targets()

    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"

    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.mark.asyncio
async def test_file_detail_with_media_fields_returns_200(
    app_with_media_obs: tuple[Starlette, str],
) -> None:
    """/files/{file_id} with duration_seconds + bitrate_kbps → 200, explanation computed."""
    app, hash_ = app_with_media_obs
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert resp.status_code == 200
    assert "062A" in resp.text


@pytest.mark.asyncio
async def test_file_detail_unknown_hash_returns_styled_404(
    populated_app: tuple[Starlette, str],
) -> None:
    """/files/{file_id} nonexistent → 404 with the styled HTML template (contains 'not found')."""
    app, _ = populated_app
    unknown = "00000000000000000000000000000000"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/files/{unknown}")
    assert resp.status_code == 404
    assert "not found" in resp.text.lower()


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
    import p2pwatch.webui

    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "404.html").write_text(template, encoding="utf-8")
    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=_matcher(),
        target_segments=_targets(),
        templates_dir=templates_dir,
        static_dir=Path(p2pwatch.webui.__file__).parent / "adapters" / "static",
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
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
    import p2pwatch.webui

    app, hash_ = populated_app
    _seed_two_sources(catalog_db, hash_)
    recorder = _TemplateRecorder(app)
    async with AsyncClient(transport=ASGITransport(app=recorder), base_url="http://test") as client:
        await client.get(url.format(file_id=file_id(hash_).hex()))
    (rendered,) = recorder.rendered
    loader = FileSystemLoader(Path(p2pwatch.webui.__file__).parent / "adapters" / "templates")
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
    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-hostile"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()
    matcher_config = _matcher()
    targets = _targets()
    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"
    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.mark.asyncio
async def test_empty_filter_param_does_not_silently_zero_results(
    populated_app: tuple[Starlette, str],
) -> None:
    # webui-security#0 regression (filters): ``?target_id=`` (empty, common with a <select>
    # that has an empty option) must be treated as "no filter", not as ``target_id = ''`` which
    # matches 0 results with no message.
    app, hash_ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files?target_id=&tier=&search=")
    assert resp.status_code == 200
    assert hash_[:8] in resp.text  # the inserted file is rendered despite the empty filters


@pytest.mark.asyncio
async def test_page_zero_is_clamped_to_first_page(
    populated_app: tuple[Starlette, str],
) -> None:
    # webui-security#2 regression: ``?page=0`` → OFFSET=-50 (SQLite returned page 1 by
    # luck). Now ``max(1, page)`` clamps.
    app, hash_ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files?page=0")
    assert resp.status_code == 200
    assert hash_[:8] in resp.text
    assert "Page 1" in resp.text


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
async def test_files_page_shows_pagination_navigation(catalog_db: Path, local_db: Path) -> None:
    # webui-security#1: the page lists 50 files max; when it is FULL, a "Next →" link
    # must be rendered (heuristic: we don't have the total count).
    with sqlite3.connect(catalog_db) as conn:
        for i in range(50):
            ed2k = f"{i:032d}"
            insert_file(conn, ed2k)
            insert_observation(conn, ed2k, f"file-{i}.bin")
            insert_decision(conn, ed2k, "062A", "catalog", rule_name="catalog")
    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-paged"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()
    matcher_config = _matcher()
    targets = _targets()
    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"
    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp1 = await client.get("/files")
        resp2 = await client.get("/files?page=2")
    # page 1: full page → "Next" present, "Previous" absent.
    assert "Next" in resp1.text
    assert "Previous" not in resp1.text
    # page 2: not full (0 files) → "Previous" present, "Next" absent.
    assert "Previous" in resp2.text
    assert "Next" not in resp2.text


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


def _file_row(*, decisions: tuple[FileDecision, ...]) -> FileRow:
    return FileRow(
        file=FileKey(Network.ED2K, TEST_HASH),
        size_bytes=1024,
        filename="f.avi",
        source_count=1,
        last_seen="2024-01-01T00:00:00",
        decisions=decisions,
    )


def test_resolve_target_display_empty_decisions_is_empty_list() -> None:
    assert _resolve_target_display(_file_row(decisions=()), _SEGMENT_BY_ID) == []


def test_resolve_target_display_catalog_decision_is_unidentified() -> None:
    row = _file_row(decisions=(FileDecision(target_id="062A", tier="catalog"),))
    assert _resolve_target_display(row, _SEGMENT_BY_ID) == [("unidentified", "·")]


def test_resolve_target_display_resolvable_id_joins_seasonal_locator_and_title() -> None:
    row = _file_row(decisions=(FileDecision(target_id="062A", tier="download"),))
    assert _resolve_target_display(row, _SEGMENT_BY_ID) == [
        ("062A / S02E11A", "La Grenouille Cosmique")
    ]


def test_resolve_target_display_unknown_id_falls_back_to_raw_id() -> None:
    row = _file_row(decisions=(FileDecision(target_id="999Z", tier="download"),))
    assert _resolve_target_display(row, _SEGMENT_BY_ID) == [("999Z", "·")]


def test_resolve_target_display_two_segments_returns_a_pair_each() -> None:
    row = _file_row(decisions=(FileDecision("062A", "download"), FileDecision("062B", "download")))
    assert _resolve_target_display(row, _SEGMENTS_AB) == [
        ("062A / S02E11A", "La Grenouille Cosmique"),
        ("062B / S02E11B", "Duel Contre Giroro"),
    ]


def test_to_display_rows_empty_decisions_all_dashes() -> None:
    [display] = _to_display_rows([_file_row(decisions=())], _SEGMENTS_AB)
    assert display.decisions_display == ()
    assert display.tier_display == "·"


def test_to_display_rows_two_segments_aggregate_cells_shared_tier() -> None:
    row = _file_row(decisions=(FileDecision("062A", "download"), FileDecision("062B", "download")))
    [display] = _to_display_rows([row], _SEGMENTS_AB)
    assert display.decisions_display == (
        DecisionCell(target="062A / S02E11A", title="La Grenouille Cosmique"),
        DecisionCell(target="062B / S02E11B", title="Duel Contre Giroro"),
    )
    assert display.tier_display == "download"


def test_to_display_rows_two_segments_differing_tiers_lists_per_target() -> None:
    row = _file_row(decisions=(FileDecision("062A", "download"), FileDecision("062B", "notify")))
    [display] = _to_display_rows([row], _SEGMENTS_AB)
    assert display.tier_display == "062A: download · 062B: notify"


def test_to_display_rows_computes_size_and_last_seen_display() -> None:
    row = FileRow(
        file=FileKey(Network.ED2K, TEST_HASH),
        size_bytes=1024,
        filename="f.avi",
        source_count=1,
        last_seen="2026-07-03T23:45:24.104990+00:00",
        decisions=(),
    )
    [display] = _to_display_rows([row], _SEGMENTS_AB)
    assert display.size_display == "1 KB"
    assert display.last_seen_display == "2026-07-03 23:45Z"


# ---------------------------------------------------------------------------
# HTTP-level tests · the resolution rule end-to-end through both routes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_files_catalog_tier_shows_unidentified(
    populated_app: tuple[Starlette, str],
) -> None:
    """populated_app's decision is tier=catalog → the /files list must show "unidentified",
    not the resolved id/title."""
    app, hash_ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert resp.status_code == 200
    assert hash_[:8] in resp.text
    # Scoped to the table cell (not the static tier legend, which also mentions the word).
    assert '<div class="cell-line">unidentified</div>' in resp.text
    assert "La Grenouille Cosmique" not in resp.text


@pytest.mark.asyncio
async def test_files_resolvable_target_shows_seasonal_locator_and_title(
    app_download_tier_known_target: tuple[Starlette, str],
) -> None:
    app, _ = app_download_tier_known_target
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert resp.status_code == 200
    assert "062A / S02E11A" in resp.text
    assert "La Grenouille Cosmique" in resp.text


@pytest.mark.asyncio
async def test_files_table_is_scroll_wrapped_and_name_has_full_title(
    app_download_tier_known_target: tuple[Starlette, str],
) -> None:
    """The table is wrapped for horizontal scroll on narrow desktop widths, and the (possibly
    truncated) filename keeps its full text in a title= tooltip."""
    app, _ = app_download_tier_known_target
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert resp.status_code == 200
    assert '<div class="files-scroll">' in resp.text
    assert 'class="cell-name" title="keroro_s2e62a_vf.avi"' in resp.text


@pytest.mark.asyncio
async def test_files_unknown_target_shows_raw_id_and_dash_title(
    app_download_tier_unknown_target: tuple[Starlette, str],
) -> None:
    app, _ = app_download_tier_unknown_target
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert resp.status_code == 200
    assert "999Z" in resp.text
    # The static tier legend also mentions the word "unidentified": scope to the cell.
    assert '<div class="cell-line">unidentified</div>' not in resp.text
    assert "La Grenouille Cosmique" not in resp.text


@pytest.mark.asyncio
async def test_files_no_decision_shows_dashes(
    app_no_decision: tuple[Starlette, str],
) -> None:
    """No decision at all → target and title both render as "·" cells, never an
    "unidentified" cell value. The row is only visible with show_unmatched (the
    matched-only default hides it, cf. test_files_default_hides_unmatched)."""
    app, hash_ = app_no_decision
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files?show_unmatched=1")
    assert resp.status_code == 200
    assert hash_[:8] in resp.text
    # The Target header tooltip also mentions "unidentified": scope to the cell so we
    # assert on the row value, not the static legend text.
    assert '<div class="cell-line">unidentified</div>' not in resp.text
    assert "La Grenouille Cosmique" not in resp.text


@pytest.mark.asyncio
async def test_files_tier_header_has_tooltip_and_no_legacy_legend(
    populated_app: tuple[Starlette, str],
) -> None:
    """The tier meanings now live in a "?" header tooltip on the Tier column, replacing the
    old free-standing <p class="tier-legend"> block."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert resp.status_code == 200
    # The legacy legend block is gone.
    assert 'class="tier-legend"' not in resp.text
    assert "Tier legend" not in resp.text
    # A focusable "?" trigger describes a tooltip that enumerates the three tiers.
    assert 'aria-describedby="tip-tier"' in resp.text
    assert 'id="tip-tier"' in resp.text
    assert 'role="tooltip"' in resp.text
    assert "automatically queued for download" in resp.text
    assert "flagged for manual review" in resp.text


@pytest.mark.asyncio
async def test_files_nonobvious_columns_have_header_tooltips(
    populated_app: tuple[Starlette, str],
) -> None:
    """The other non-obvious columns (Target, Sources) also carry a "?" header tooltip
    explaining their values."""
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert resp.status_code == 200
    assert 'id="tip-target"' in resp.text
    assert 'id="tip-sources"' in resp.text
    # A distinctive phrase from each of the two tooltips.
    assert "the episode this file is matched to" in resp.text  # target
    assert "peers" in resp.text  # sources


@pytest.mark.asyncio
async def test_target_page_resolves_title_via_segment_mapping(
    app_download_tier_known_target: tuple[Starlette, str],
) -> None:
    """/targets/{id} shares _to_display_rows with /files: confirm handle_target ALSO
    threads the segment_by_id mapping (both call sites, per the brief)."""
    app, _ = app_download_tier_known_target
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/targets/062A")
    assert resp.status_code == 200
    assert "062A / S02E11A" in resp.text
    assert "La Grenouille Cosmique" in resp.text


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


@pytest.fixture
def app_whole_episode(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """One file matched to BOTH 072A and 072B (two current decisions, tier download) against a
    two-segment targets.yaml: the core multi-target end-to-end fixture (spec §9)."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 170_000_000)
        insert_observation(
            conn, TEST_HASH, "keroro_072_vf.avi", size_bytes=170_000_000, source_count=7
        )
        insert_decision(conn, TEST_HASH, "072A", "download", rule_name="numero_nu_confirmed")
        insert_decision(conn, TEST_HASH, "072B", "download", rule_name="numero_nu_confirmed")

    with sqlite3.connect(local_db) as conn:
        conn.execute("INSERT INTO node_runtime VALUES (?, ?)", ("node_id", "node-whole"))
        conn.execute(
            "INSERT INTO node_runtime VALUES (?, ?)", ("created_at", "2024-01-01T00:00:00")
        )
        conn.commit()

    matcher_config = _matcher()
    targets = _targets_ab()

    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"
    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=targets,
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.mark.asyncio
async def test_files_whole_episode_renders_one_row_with_aggregated_targets(
    app_whole_episode: tuple[Starlette, str],
) -> None:
    app, hash_ = app_whole_episode
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    assert resp.status_code == 200
    assert hash_[:8] in resp.text
    assert '<div class="cell-line">072A / S03E06A</div>' in resp.text
    assert '<div class="cell-line">072B / S03E06B</div>' in resp.text
    assert '<div class="cell-line cell-title" title="Le Defi">Le Defi</div>' in resp.text
    assert (
        '<div class="cell-line cell-title" title="Duel Contre Giroro">Duel Contre Giroro</div>'
        in resp.text
    )
    assert "<td>download</td>" in resp.text


@pytest.mark.asyncio
async def test_whole_episode_appears_under_each_target(
    app_whole_episode: tuple[Starlette, str],
) -> None:
    app, hash_ = app_whole_episode
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp_a = await client.get("/targets/072A")
        resp_b = await client.get("/targets/072B")
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    assert hash_[:8] in resp_a.text
    assert hash_[:8] in resp_b.text


@pytest.mark.asyncio
async def test_file_detail_whole_episode_shows_both_targets(
    app_whole_episode: tuple[Starlette, str],
) -> None:
    app, hash_ = app_whole_episode
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert resp.status_code == 200
    assert "072A" in resp.text
    assert "072B" in resp.text


@pytest.fixture
def app_title_coverage(catalog_db: Path, local_db: Path) -> tuple[Starlette, str]:
    """One file whose name covers two of its target's three title words, decided on that."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, TEST_HASH, 100_000_000)
        insert_observation(conn, TEST_HASH, "keroro_duel_giroro_vf.avi")
        insert_decision(conn, TEST_HASH, "072B", "notify", rule_name="title_review")
    matcher_config = parse_matcher_config(
        {
            "tokens": {
                "keroro": {"keyword": "keroro"},
                "title_hit": {"coverage": "title", "min_coverage": 0.6},
            },
            "rules": [
                {
                    "name": "title_review",
                    "tier": "notify",
                    "scope": "segment",
                    "all": ["keroro", "title_hit"],
                }
            ],
        }
    )

    import p2pwatch.webui

    webui_dir = Path(p2pwatch.webui.__file__).parent / "adapters"
    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=matcher_config,
        target_segments=_targets_ab(),
        templates_dir=webui_dir / "templates",
        static_dir=webui_dir / "static",
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, TEST_HASH


@pytest.mark.asyncio
async def test_file_detail_shows_each_coverage_value_to_two_decimals(
    app_title_coverage: tuple[Starlette, str],
) -> None:
    app, hash_ = app_title_coverage
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(_detail_url(hash_))
    assert resp.status_code == 200
    assert "<li>title_hit</li>" in resp.text  # fired: 0.67 reaches min_coverage
    assert "Coverage values:" in resp.text
    assert "<li>title_hit: 0.67</li>" in resp.text  # "duel" and "giroro" of "Duel Contre Giroro"


# ---------------------------------------------------------------------------
# Dashboard controls and client status (stage 2 D20): each POST dispatches one intent and
# redirects (PRG) to the dashboard, whose ?done banner maps a known code to a message.
# ---------------------------------------------------------------------------


def _dashboard_app(
    catalog_db: Path, local_db: Path, control: _RecordingControl, status: _Readings
) -> Starlette:
    import p2pwatch.webui

    webui_dir = Path(p2pwatch.webui.__file__).parent
    return build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=_matcher(),
        target_segments=_targets(),
        templates_dir=webui_dir / "adapters" / "templates",
        static_dir=webui_dir / "adapters" / "static",
        control=control,
        status_readings=status,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )


@pytest.fixture
def controls_app(catalog_db: Path, local_db: Path) -> tuple[Starlette, _RecordingControl]:
    """App wired with a recording control, for the runtime-control route tests."""
    control = _RecordingControl()
    return _dashboard_app(catalog_db, local_db, control, _NO_STATUS), control


async def _dashboard(app: Starlette) -> str:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    return resp.text


@pytest.mark.asyncio
async def test_dashboard_renders_the_three_action_forms_and_the_running_crawl(
    controls_app: tuple[Starlette, _RecordingControl],
) -> None:
    app, _ = controls_app
    text = await _dashboard(app)
    assert 'action="/controls/pause"' in text
    assert 'action="/controls/resume"' in text
    assert 'action="/controls/restart"' in text
    assert "The crawl is running." in text


@pytest.mark.asyncio
async def test_dashboard_shows_a_paused_crawl(
    controls_app: tuple[Starlette, _RecordingControl],
) -> None:
    app, control = controls_app
    control.paused = True
    assert "The crawl is paused." in await _dashboard(app)


@pytest.mark.asyncio
async def test_the_controls_page_and_its_nav_entry_are_gone(
    controls_app: tuple[Starlette, _RecordingControl],
) -> None:
    app, _ = controls_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        page = await client.get("/controls")
        dashboard = await client.get("/")
    assert page.status_code == 404
    assert 'href="/controls"' not in dashboard.text


@pytest.mark.asyncio
async def test_dashboard_without_done_shows_no_banner(
    controls_app: tuple[Starlette, _RecordingControl],
) -> None:
    app, _ = controls_app
    assert "control-banner" not in await _dashboard(app)


@pytest.mark.asyncio
async def test_dashboard_unknown_done_shows_no_banner(
    controls_app: tuple[Starlette, _RecordingControl],
) -> None:
    app, _ = controls_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/?done=bogus")
    assert resp.status_code == 200
    assert "control-banner" not in resp.text


@pytest.mark.asyncio
async def test_there_is_no_force_cycle_control(
    controls_app: tuple[Starlette, _RecordingControl],
) -> None:
    app, control = controls_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/controls/force-cycle")
    assert resp.status_code == 404
    assert control.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "call", "done"),
    [
        ("pause", "pause", "paused"),
        ("resume", "resume", "resumed"),
        ("restart", "request_shutdown", "restarted"),
    ],
)
async def test_each_control_dispatches_and_redirects_to_the_dashboard(
    controls_app: tuple[Starlette, _RecordingControl], action: str, call: str, done: str
) -> None:
    app, control = controls_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(f"/controls/{action}")
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/?done={done}"
    assert control.calls == [call]


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
    controls_app: tuple[Starlette, _RecordingControl], action: str, banner: str
) -> None:
    app, control = controls_app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=True
    ) as client:
        resp = await client.post(f"/controls/{action}")
    assert resp.status_code == 200
    assert f'<p class="control-banner" role="status">{banner}</p>' in resp.text
    assert len(control.calls) == 1


_CHANNELS = (ChannelStatus("ed2k", True, False), ChannelStatus("x", False, None))


async def _clients_section(
    catalog_db: Path, local_db: Path, reading: StatusReading | None, *, current: bool = True
) -> str:
    status = _Readings({"amuled": reading}, current=current)
    text = await _dashboard(_dashboard_app(catalog_db, local_db, _RecordingControl(), status))
    return text[text.index("<h2>Clients</h2>") : text.index("<h2>Crawl</h2>")]


def _read_now(status: ClientStatus | None) -> StatusReading:
    return StatusReading(FakeTime().wall.now(), status)


@pytest.mark.asyncio
async def test_dashboard_shows_each_client_and_channel_of_a_current_reading(
    catalog_db: Path, local_db: Path
) -> None:
    section = await _clients_section(
        catalog_db, local_db, _read_now(ClientStatus("2.3.3", _CHANNELS))
    )
    assert "<h3>amuled</h3>" in section
    assert "<th>Connected</th>" in section
    assert "<dd>2.3.3</dd>" in section
    assert "<dt>API reachable</dt><dd>yes</dd>" in section
    assert "<dd>Read at 2026-06-12 00:00Z.</dd>" in section
    assert "<td>ed2k</td><td>yes</td><td>no</td>" in section
    assert "<td>x</td><td>no</td><td>unknown</td>" in section


@pytest.mark.asyncio
async def test_dashboard_shows_an_unknown_version(catalog_db: Path, local_db: Path) -> None:
    section = await _clients_section(catalog_db, local_db, _read_now(ClientStatus(None, ())))
    assert "<dt>Version</dt><dd>unknown</dd>" in section
    assert "No current channel reading." in section


@pytest.mark.asyncio
async def test_dashboard_shows_an_unreachable_client(catalog_db: Path, local_db: Path) -> None:
    section = await _clients_section(catalog_db, local_db, _read_now(None))
    assert "<dt>API reachable</dt><dd>no</dd>" in section
    assert "No current channel reading." in section


@pytest.mark.asyncio
async def test_dashboard_never_shows_an_old_reading_as_current(
    catalog_db: Path, local_db: Path
) -> None:
    section = await _clients_section(
        catalog_db, local_db, _read_now(ClientStatus("2.3.3", _CHANNELS)), current=False
    )
    assert "<dd>Out of date: last reading at 2026-06-12 00:00Z.</dd>" in section
    assert "2.3.3" not in section
    assert "<dt>API reachable</dt><dd>unknown</dd>" in section
    assert "<td>ed2k</td>" not in section


@pytest.mark.asyncio
async def test_dashboard_shows_a_client_not_read_yet(catalog_db: Path, local_db: Path) -> None:
    section = await _clients_section(catalog_db, local_db, None)
    assert "<h3>amuled</h3>" in section
    assert "<dd>No reading yet.</dd>" in section
    assert "<dt>API reachable</dt><dd>unknown</dd>" in section


# ---------------------------------------------------------------------------
# Bidirectional column sorting (Task 3): normalizers + header builder (direct)
# and the sortable <thead> end-to-end.
# ---------------------------------------------------------------------------


def test_normalize_sort_valid_unknown_missing() -> None:
    assert _normalize_sort("size") == "size"
    assert _normalize_sort("bogus") == "last_seen"
    assert _normalize_sort(None) == "last_seen"


def test_normalize_dir_valid_unknown_missing() -> None:
    assert _normalize_direction("asc") == "asc"
    assert _normalize_direction("bogus") == "desc"
    assert _normalize_direction(None) == "desc"


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


@pytest.fixture
def sortable_app(catalog_db: Path, local_db: Path) -> tuple[Starlette, list[str]]:
    """App over three matched files with distinct sizes (300/200/100), for the sort-order test.
    Returns (app, hashes-in-descending-size-order)."""
    big, mid, small = "a" * 32, "b" * 32, "c" * 32
    with sqlite3.connect(catalog_db) as conn:
        for h, size, name in ((big, 300, "x.avi"), (mid, 200, "y.avi"), (small, 100, "z.avi")):
            insert_file(conn, h, size)
            insert_observation(conn, h, name, size_bytes=size)
            insert_decision(conn, h, "062A", "download")
    import p2pwatch.webui

    templates_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "templates"
    static_dir = Path(p2pwatch.webui.__file__).parent / "adapters" / "static"
    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=_matcher(),
        target_segments=_targets(),
        templates_dir=templates_dir,
        static_dir=static_dir,
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url=_AMULE_URL,
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    return app, [big, mid, small]


@pytest.mark.asyncio
async def test_files_sort_by_size_orders_rows(sortable_app: tuple[Starlette, list[str]]) -> None:
    app, ordered_desc = sortable_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files?sort=size&direction=asc")
        old_key = await client.get("/files?sort=size&dir=asc")
    assert resp.status_code == 200
    # smallest first: the three short-hashes appear in ascending-size order in the body
    positions = [resp.text.index(h[:8]) for h in reversed(ordered_desc)]
    assert positions == sorted(positions)
    # 4.x's ``dir`` is ignored: the default direction, largest first
    positions = [old_key.text.index(h[:8]) for h in ordered_desc]
    assert positions == sorted(positions)


@pytest.mark.asyncio
async def test_files_renders_sortable_header_link(populated_app: tuple[Starlette, str]) -> None:
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    # the Name header is a sort link with a data-sort attribute (default state -> not active)
    assert 'href="/files?sort=name&amp;direction=asc"' in resp.text
    assert 'data-sort="desc"' in resp.text  # last_seen is the active default column


@pytest.mark.asyncio
async def test_target_page_headers_are_plain_text(
    app_download_tier_known_target: tuple[Starlette, str],
) -> None:
    app, _ = app_download_tier_known_target
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/targets/062A")
    assert resp.status_code == 200
    # no sort links on a target page (headers tuple is empty -> the {% else %} plain label renders)
    assert "?sort=" not in resp.text


@pytest.mark.asyncio
async def test_sort_header_links_preserve_target_and_tier_filters(
    app_download_tier_known_target: tuple[Starlette, str],
) -> None:
    """An active target + tier filter is carried into every sort-header link (the ordered
    ``filters`` dict is threaded into each header URL, then sort/dir override for that column)."""
    app, _ = app_download_tier_known_target
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files?target_id=062A&tier=download")
    assert resp.status_code == 200
    # the Name header keeps both filters (autoescaped & -> &amp;) then adds its own sort + dir
    assert "target_id=062A&amp;tier=download&amp;sort=name&amp;direction=asc" in resp.text


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
async def test_files_renders_search_prefill_and_facet(
    populated_app: tuple[Starlette, str],
) -> None:
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files?search=keroro&show_unmatched=1")
    assert 'name="search"' in resp.text
    assert 'value="keroro"' in resp.text  # prefill
    assert 'name="show_unmatched"' in resp.text  # carried as a hidden input
    # populated_app's single file is a catalog-tier decision → facet shows "unidentified (1)"
    assert "unidentified" in resp.text
    assert 'href="/files?search=keroro&amp;show_unmatched=1&amp;tier=catalog"' in resp.text


@pytest.mark.asyncio
async def test_files_filter_bar_wraps_facets_then_search(
    populated_app: tuple[Starlette, str],
) -> None:
    """The facet chips and the search form share one .filter-bar row, chips first.

    The order is the layout contract: the row is a flex line and the form is pushed right by
    `margin-left: auto`, which only lands the form on the right if it is the LAST child.
    """
    app, _ = populated_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/files")
    row = re.search(r'<div class="filter-bar">(.*?)</div>', resp.text, re.DOTALL)
    assert row is not None  # the wrapper is a div now, no longer the form itself
    inner = row.group(1)
    facet_at = inner.find('<nav class="tier-facet"')
    form_at = inner.find('<form class="files-search"')
    assert facet_at != -1  # the chips live inside the row
    assert form_at != -1  # the form lives inside the row, and carries files-search
    assert facet_at < form_at  # chips left, search right
    assert 'role="search"' in inner  # the form stays a landmark after the reclassing


@pytest.mark.asyncio
async def test_target_page_has_no_filter_bar(
    app_download_tier_known_target: tuple[Starlette, str],
) -> None:
    app, _ = app_download_tier_known_target
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/targets/062A")
    assert 'name="search"' not in resp.text  # no search form on a target page
    assert "tier-facet" not in resp.text  # no facet on a target page
    assert "filter-bar" not in resp.text  # the wrapper itself renders nothing either
    assert "files-search" not in resp.text


# ---------------------------------------------------------------------------
# Top nav: active state + the page titles it replaces
# ---------------------------------------------------------------------------

# The nav destinations, in render order: (path, label). Mirrors the table wired in
# composition.app; a test that drifts from it fails on the label or the href.
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
async def test_nav_amule_link_uses_the_configured_base(catalog_db: Path, local_db: Path) -> None:
    """The base is configurable so the link survives a reverse proxy in front of 8080: p2pwatch
    cannot infer from the request how amuleweb is reachable from the operator's browser."""
    import p2pwatch.webui

    webui_dir = Path(p2pwatch.webui.__file__).parent
    app = build_app(
        catalog_db_path=catalog_db,
        local_db_path=local_db,
        matcher_config=_matcher(),
        target_segments=_targets(),
        templates_dir=webui_dir / "adapters" / "templates",
        static_dir=webui_dir / "adapters" / "static",
        control=_RecordingControl(),
        status_readings=_NO_STATUS,
        amule_url="https://mule.example.org/amule",
        wall_clock=_WALL_CLOCK,
        monotonic_clock=_MONOTONIC_CLOCK,
        source_period_gap=_GAP,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
    assert '<a href="https://mule.example.org/amule">aMule</a>' in resp.text


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
async def test_target_page_renders_its_own_heading(
    app_download_tier_known_target: tuple[Starlette, str],
) -> None:
    """/targets/{id} reuses files.html but is NOT a nav destination, so nothing else would name
    it: it passes its own heading in the ``headings`` tuple (files.html itself renders none)."""
    app, _ = app_download_tier_known_target
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/targets/062A")
    assert resp.status_code == 200
    assert "<h1>Files for target 062A</h1>" in resp.text


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
