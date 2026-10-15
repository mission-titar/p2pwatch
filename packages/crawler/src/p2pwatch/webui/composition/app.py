"""Starlette application factory (webui spec, Task 11).

``build_app`` wires the adapters (SQLite, YAML, templates) and registers all
routes. The handlers are closures capturing the dependencies: no ``app.state``.
"""

import csv
import io
import re
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, assert_never
from urllib.parse import parse_qs, urlencode

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.types import ASGIApp

from catalog_matching.config import MatcherConfig
from catalog_matching.ed2k_link import build_ed2k_link
from catalog_matching.models import TargetSegment
from p2pwatch.adapters.persistence_sqlite.reader import ReaderProvider
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.observation import Sighting
from p2pwatch.domain.source import SourceKey
from p2pwatch.ports.client_status import StatusReadings
from p2pwatch.ports.clock import MonotonicClock, WallClock
from p2pwatch.ports.crawler_control import CrawlerControl
from p2pwatch.webui.adapters.catalog_read import (
    DEFAULT_DIR,
    DEFAULT_SORT,
    PAGE_SIZE,
    SORT_COLUMNS,
    SORT_DIRECTIONS,
    CatalogReader,
)
from p2pwatch.webui.adapters.local_read import LocalReader
from p2pwatch.webui.adapters.matching_read import MatchingExplainer
from p2pwatch.webui.adapters.sql_console import (
    ROW_CAP,
    TIMEOUT_SECONDS,
    ConsoleOutcome,
    run_query,
)
from p2pwatch.webui.domain.coverage import coverage_of
from p2pwatch.webui.domain.format import (
    average_rate,
    human_size,
    input_timestamp,
    micros_timestamp,
    seasonal_locator,
    short_hash,
    short_timestamp,
    utc_timestamp,
)
from p2pwatch.webui.domain.interval import (
    INTERVAL_PRESETS,
    Interval,
    interval_ending,
    requested_interval,
)
from p2pwatch.webui.domain.views import (
    BackoffEntry,
    ChannelLine,
    ClientLine,
    ConsoleResult,
    ConsoleRow,
    DbOption,
    DecisionCell,
    FileDetailDisplay,
    FileRow,
    FileRowDisplay,
    FilesSummary,
    FilterBar,
    HiddenInput,
    IntervalLink,
    IntervalSelector,
    NavItem,
    PageNav,
    PeriodWindow,
    SearchBar,
    SortHeader,
    SortHeaders,
    SourceFilePeriod,
    SourceFileRow,
    SourceHistoryRow,
    SourceListRow,
    SourcePeriodView,
    SourceRow,
    TargetCoverageRow,
    TierFacet,
    TimelineRow,
    TokenCoverage,
)

# A detail page's path segment: a file_id or a source_id as 32 lowercase hex (stage 1 and 4 D13).
_HEX_ID = re.compile(r"[0-9a-f]{32}")

_CLAMPED_NOTICE = (
    "The interval requested is longer than 7 days: showing the 7 days ending at its end."
)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

# The top-nav destinations, in render order: (path, label). The single source of truth for what
# base.html renders; every page reaches all of them.
_NAV_DESTINATIONS: tuple[tuple[str, str], ...] = (
    ("/", "Dashboard"),
    ("/files", "Files"),
    ("/sources", "Sources"),
    ("/node", "Node"),
    ("/console", "Console"),
)


def _make_nav_context(amule_url: str) -> Callable[[Request], dict[str, Any]]:
    """Build the context processor that gives EVERY TemplateResponse its ``nav_items`` (no
    handler has to pass them). The entry whose path matches the request exactly loses its link,
    which base.html then renders as the bold current page: that is what replaces the per-page
    ``<h1>``.

    The match is exact, so a sub-page (``/files/{file_id}``, ``/targets/{id}``) marks no entry
    active: it is not itself a nav destination, and it names itself with its own heading.

    The last entry is the aMule container's web surface, amuleapi's own UI. Its base
    is operator-configured: p2pwatch cannot know how it is reachable from the browser.
    """

    def nav_context(request: Request) -> dict[str, Any]:
        current = request.url.path
        return {
            "nav_items": (
                *(
                    NavItem(label=label, link=() if path == current else (path,))
                    for path, label in _NAV_DESTINATIONS
                ),
                NavItem(label="aMule", link=(amule_url,)),
            )
        }

    return nav_context


def _resolve_target_display(
    row: FileRow, segment_by_id: Mapping[str, TargetSegment]
) -> list[tuple[str, str]]:
    """Per-decision ``(target, title)`` pairs for a file row, in the row's
    decision order (by target_id). Empty when the file has no current decision. The
    ``catalog → "unidentified"`` mask is applied per decision (``keroro_large`` is the only
    catalog-tier rule; cf. ``domain.views.FileRowDisplay``)."""
    resolved: list[tuple[str, str]] = []
    for dec in row.decisions:
        if dec.tier == "catalog":
            resolved.append(("unidentified", "·"))
            continue
        seg = segment_by_id.get(dec.target_id)
        if seg is None:
            resolved.append((dec.target_id, "·"))
            continue
        locator = seasonal_locator(
            season=seg.season, seasonal_number=seg.seasonal_number, letter=seg.letter
        )
        resolved.append((f"{dec.target_id} / {locator}", seg.title))
    return resolved


def _to_display_rows(
    file_rows: Iterable[FileRow], segment_by_id: Mapping[str, TargetSegment]
) -> list[FileRowDisplay]:
    """Convert catalog rows into ``FileRowDisplay`` view-models: one row per file, the file's
    (usually two) segment decisions surfaced as one ``DecisionCell`` each in ``decisions_display``
    while ``tier_display`` still aggregates (shared tier, or per-target joined with ``" · "``).
    Shared by ``handle_files`` and ``handle_target``."""
    rows = []
    for row in file_rows:
        if row.decisions:
            pairs = _resolve_target_display(row, segment_by_id)
            decisions_display = tuple(DecisionCell(target=t, title=ti) for t, ti in pairs)
            tier_values = {dec.tier for dec in row.decisions}
            if len(tier_values) == 1:
                tier_display = row.decisions[0].tier
            else:
                tier_display = " · ".join(f"{dec.target_id}: {dec.tier}" for dec in row.decisions)
        else:
            decisions_display = ()
            tier_display = "·"
        rows.append(
            FileRowDisplay(
                file_id=row.file.file_id.hex(),
                short_hash=short_hash(row.file.native_id),
                filename=row.filename,
                sources_display="unknown" if row.source_count is None else str(row.source_count),
                decisions_display=decisions_display,
                size_display=human_size(row.size_bytes),
                last_seen_display=short_timestamp(row.last_seen),
                tier_display=tier_display,
            )
        )
    return rows


def _timeline_row(sighting: Sighting) -> TimelineRow:
    """A sighting as one timeline line."""
    return TimelineRow(
        name=sighting.filename,
        size_bytes=sighting.size_bytes,
        sources=str(sighting.source_count),
        keyword=sighting.keyword,
        observed_at=sighting.observed_at,
    )


def _name_link(source_name: str | None) -> tuple[str, ...]:
    """The name page's href (D13), none without a name."""
    if source_name is None:
        return ()
    return (f"/sources/name?{urlencode({'source_name': source_name})}",)


def _source_link(source: SourceKey | None) -> tuple[str, ...]:
    """The source page's href (D13), none without a user hash."""
    return () if source is None else (f"/sources/{source.source_id.hex()}",)


def _source_history_row(period: SourcePeriodView) -> SourceHistoryRow:
    """A source period as one line; its name links to the name page, its hash to the source
    page."""
    name, source = period.name, period.source
    return SourceHistoryRow(
        name="unknown" if name is None else name,
        name_link=_name_link(name),
        short_hash="unknown" if source is None else short_hash(source.native_id),
        source_link=_source_link(source),
        role=period.role,
        contact_point=period.contact_point or "unknown",
        connectable=_YES_NO[period.connectable],
        first_seen=micros_timestamp(period.first_seen_at),
        last_seen=micros_timestamp(period.last_seen_at),
        received=human_size(period.received_bytes) if period.received_bytes else "",
        rate=average_rate(period.received_bytes, period.first_seen_at, period.last_seen_at),
        node=period.node_id,
    )


def _period_window(interval: Interval, gap: timedelta) -> PeriodWindow:
    """The interval in microseconds, with the gap that cuts a period."""
    return PeriodWindow(
        since=(interval.since - _EPOCH) // _MICROSECOND,
        until=(interval.until - _EPOCH) // _MICROSECOND,
        gap=gap // _MICROSECOND,
    )


def _interval_params(request: Request) -> dict[str, str]:
    """The request's own ``from`` and ``to``, which a page's list links keep."""
    query_params = request.query_params
    return {key: query_params[key] for key in ("from", "to") if key in query_params}


def _page_param(page: int) -> dict[str, str]:
    """The ``page`` param an interval's links keep, none on the first page."""
    return {"page": str(page)} if page > 1 else {}


def _interval_selector(
    interval: Interval, now: datetime, path: str, kept_params: dict[str, str]
) -> IntervalSelector:
    """The selector of the page at ``path``, whose other params are ``kept_params`` (D6): the
    presets end ``now``, and Next is offered until the interval reaches it."""

    def url(shown: Interval) -> str:
        ends = {"from": utc_timestamp(shown.since), "to": utc_timestamp(shown.until)}
        return f"{path}?{urlencode({**kept_params, **ends})}"

    return IntervalSelector(
        hidden=tuple(HiddenInput(name=name, value=value) for name, value in kept_params.items()),
        shown=f"{utc_timestamp(interval.since)} to {utc_timestamp(interval.until)}",
        notices=(_CLAMPED_NOTICE,) if interval.clamped else (),
        presets=tuple(
            IntervalLink(label, url(interval_ending(now, span))) for label, span in INTERVAL_PRESETS
        ),
        from_value=input_timestamp(interval.since),
        to_value=input_timestamp(interval.until),
        previous_url=url(interval.shifted(-1)),
        next_urls=() if interval.until >= now else (url(interval.shifted(1)),),
    )


def _source_list_row(source: SourceRow) -> SourceListRow:
    """A source as one line of ``/sources``."""
    return SourceListRow(
        name="unknown" if source.name is None else source.name,
        name_link=_name_link(source.name),
        short_hash=short_hash(source.source.native_id),
        source_link=_source_link(source.source),
        last_seen=micros_timestamp(source.last_seen_at),
        files=str(source.file_count),
    )


def _source_file_row(item: SourceFilePeriod) -> SourceFileRow:
    """A period of a source's or a name's page, with the file it was read on."""
    return SourceFileRow(
        file=item.file_name or short_hash(item.file.native_id),
        file_link=f"/files/{item.file.file_id.hex()}",
        history=_source_history_row(item.period),
    )


def _normalize_param(raw: str | None) -> str | None:
    """Normalize a query param: whitespace stripped, empty ⇒ ``None``. Without it, an HTML
    select with an empty option sends ``?target_id=`` → ``""`` → ``dec.target_id = ''`` matches
    NOTHING → 0 results with no message (webui-security#0/filters)."""
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def _page_number(raw: str | None) -> int:
    """The ``page`` param, 1 when absent or not a number."""
    try:
        page = int(raw or "1")
    except ValueError:
        page = 1
    # ``max(1, ...)`` (webui-security#2): ``?page=0`` → OFFSET=-50 which SQLite treats as 0.
    return max(1, page)


def _page_nav(page: int, row_count: int, base_path: str, kept_params: dict[str, str]) -> PageNav:
    """Precompute the prev/next links for a page (W-D8: view-model, no template logic).
    We don't have the total count → ``next`` is rendered when the page is FULL (standard
    heuristic; at worst a next click returns an empty page)."""
    prev_url: str | None = None
    next_url: str | None = None
    if page > 1:
        prev = dict(kept_params)
        prev["page"] = str(page - 1)
        prev_url = f"{base_path}?{urlencode(prev)}"
    if row_count >= PAGE_SIZE:
        nxt = dict(kept_params)
        nxt["page"] = str(page + 1)
        next_url = f"{base_path}?{urlencode(nxt)}"
    return PageNav(page=page, prev_url=prev_url, next_url=next_url)


def _files_summary(
    matched_count: int, total_count: int, show_unmatched: bool, kept_params: dict[str, str]
) -> FilesSummary:
    """Precompute the /files summary line + matched/all toggle (W-D8: no template logic).

    The toggle preserves the active filters and drops ``page`` (counts differ between modes,
    so page N may not exist → back to page 1)."""
    if show_unmatched:
        summary_text = (
            f"Showing all catalogued files: {total_count:,} catalogued ({matched_count:,} matched)."
        )
        toggle_label = "Matched only"
        toggle_params = dict(kept_params)  # drop show_unmatched → matched only
    else:
        summary_text = (
            f"Showing matched files only: {matched_count:,} of {total_count:,} catalogued."
        )
        toggle_label = "Show all catalogued files"
        toggle_params = {**kept_params, "show_unmatched": "1"}
    toggle_url = "/files?" + urlencode(toggle_params) if toggle_params else "/files"
    return FilesSummary(summary_text=summary_text, toggle_label=toggle_label, toggle_url=toggle_url)


# The sortable columns in display order: (allowlist key, header label).
_SORTABLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("name", "Name"),
    ("size", "Size"),
    ("sources", "Sources"),
    ("last_seen", "Last seen"),
    ("tier", "Tier"),
)
# A column's direction while it is not the active sort: Name reads best ascending, the metrics and
# last-seen descending (webui spec §3.1).
_DEFAULT_DIRECTION_BY_COLUMN: dict[str, str] = {
    "name": "asc",
    "size": "desc",
    "sources": "desc",
    "last_seen": "desc",
    "tier": "desc",
}
_OPPOSITE_BY_DIRECTION: dict[str, str] = {"asc": "desc", "desc": "asc"}


def _normalize_sort(raw: str | None) -> str:
    """Map a raw ``sort`` param to an allowlist key, or the default (unknown/missing -> default)."""
    return raw if raw in SORT_COLUMNS else DEFAULT_SORT


def _normalize_direction(raw: str | None) -> str:
    """Map a raw ``direction`` param to ``asc``/``desc``, or the default when unknown or missing."""
    return raw if raw in SORT_DIRECTIONS else DEFAULT_DIR


def _sort_header(
    column_key: str,
    label: str,
    active_sort: str,
    active_direction: str,
    kept_params: dict[str, str],
) -> SortHeader:
    """Build one column header. Keeps every ``kept_params`` param and OVERRIDES ``sort`` and
    ``direction``: the active column flips direction and shows its indicator; an inactive column
    uses its default direction and no indicator. Params equal to the default are omitted from the
    URL (clean, deterministic).
    """
    active = column_key == active_sort
    next_direction = (
        _OPPOSITE_BY_DIRECTION[active_direction]
        if active
        else _DEFAULT_DIRECTION_BY_COLUMN[column_key]
    )
    indicator = active_direction if active else ""
    link_params = dict(kept_params)
    if column_key != DEFAULT_SORT:
        link_params["sort"] = column_key
    if next_direction != DEFAULT_DIR:
        link_params["direction"] = next_direction
    url = "/files?" + urlencode(link_params) if link_params else "/files"
    return SortHeader(label=label, url=url, indicator=indicator)


def _sort_headers(
    *, active_sort: str, active_direction: str, kept_params: dict[str, str]
) -> SortHeaders:
    """Precompute all five sortable headers (W-D8)."""
    built = {
        column_key: _sort_header(column_key, label, active_sort, active_direction, kept_params)
        for column_key, label in _SORTABLE_COLUMNS
    }
    return SortHeaders(
        name=built["name"],
        size=built["size"],
        sources=built["sources"],
        last_seen=built["last_seen"],
        tier=built["tier"],
    )


# Tier facet display order (strongest first) and the catalog→"unidentified" mask, matching the
# row rendering. Only tiers PRESENT in the counts are rendered.
_FACET_TIER_ORDER: tuple[str, ...] = ("download", "notify", "catalog")


def _facet_label(tier: str) -> str:
    """Display label for a tier facet: ``catalog`` is masked to ``"unidentified"`` (the
    keroro_large catch-all), every other tier shows its own name."""
    return "unidentified" if tier == "catalog" else tier


def _tier_facets(
    *, file_count_by_tier: Mapping[str, int], active_tier: str | None, kept_params: dict[str, str]
) -> tuple[TierFacet, ...]:
    """Precompute the tier facet (W-D8): an "all" reset (no count) followed by one entry per tier
    present, in ``_FACET_TIER_ORDER``. ``kept_params`` are the params to preserve (the filters but
    ``tier``, plus ``sort`` and ``direction``; ``page`` already excluded); a tier entry appends
    ``tier=<t>``, the reset omits it."""
    all_url = "/files?" + urlencode(kept_params) if kept_params else "/files"
    facets = [
        TierFacet(
            label="all",
            count_display="",
            url=all_url,
            selected_flag="1" if active_tier is None else "",
        )
    ]
    for tier in _FACET_TIER_ORDER:
        if tier not in file_count_by_tier:
            continue
        link_params = {**kept_params, "tier": tier}
        facets.append(
            TierFacet(
                label=_facet_label(tier),
                count_display=f"({file_count_by_tier[tier]})",
                url="/files?" + urlencode(link_params),
                selected_flag="1" if active_tier == tier else "",
            )
        )
    return tuple(facets)


def _search_bar(*, search_text: str | None, kept_params: dict[str, str]) -> SearchBar:
    """Precompute the search form (W-D8): the ``search`` prefill (empty string when none) + hidden
    inputs from ``kept_params`` (already without ``search`` and ``page``)."""
    hidden = tuple(HiddenInput(name=k, value=v) for k, v in kept_params.items())
    return SearchBar(query=search_text or "", hidden=hidden)


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defense-in-depth security headers (webui-security#3).

    The webui has no built-in auth and binds 0.0.0.0 in-container, so exposure is governed by
    the operator's compose (published port + networks) plus a reverse proxy / VPN, not by the
    bind address. Jinja2 autoescape already neutralizes XSS. CSP ``default-src 'self'`` prevents
    an injected fragment from loading an external asset (a net under autoescape).
    ``X-Content-Type-Options: nosniff`` prevents a browser from re-guessing the MIME type.
    ``Referrer-Policy: no-referrer`` avoids leaking the eD2k hash to any third-party asset
    (paranoia consistent with the project's spirit).
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


# Human status messages shown after a control POST (via the PRG ``?done=<code>`` param). The
# strings avoid em/en-dashes (project UI rule). A ``done`` code absent from this mapping (or no
# ``done`` at all) renders NO banner.
_CONTROL_MESSAGES: dict[str, str] = {
    "paused": (
        "Crawl paused. Searches in flight or already waiting their network slot still run, "
        "then the crawler idles."
    ),
    "resumed": "Crawl resumed.",
    "restarted": "Restart requested. The service goes offline briefly, then returns.",
}


_YES_NO: dict[bool | None, str] = {True: "yes", False: "no", None: "unknown"}


def _client_lines(status_readings: StatusReadings) -> tuple[ClientLine, ...]:
    """Each client's last reading, its values shown only while current (stage 2 D20)."""
    lines = []
    for client_name, reading in status_readings.readings().items():
        if reading is None:
            lines.append(ClientLine(client_name, "No reading yet.", "unknown", "unknown", ()))
            continue
        read_at = short_timestamp(reading.read_at.isoformat())
        client_status = reading.status
        if not status_readings.is_current(client_name):
            text = f"Out of date: last reading at {read_at}."
            lines.append(ClientLine(client_name, text, "unknown", "unknown", ()))
        elif client_status is None:
            lines.append(ClientLine(client_name, f"Read at {read_at}.", "unknown", "no", ()))
        else:
            channels = tuple(
                ChannelLine(c.channel, _YES_NO[c.connected], _YES_NO[c.connectable])
                for c in client_status.channels
            )
            version = client_status.version or "unknown"
            lines.append(ClientLine(client_name, f"Read at {read_at}.", version, "yes", channels))
    return tuple(lines)


# SQL console (spec §11). The two selectable databases, in display order: value (allowlist key)
# + human label. Neither holds a peer's address (a source is a pseudonymous id at most), so
# read-only exposure of either is fine.
_CONSOLE_DBS: tuple[tuple[str, str], ...] = (
    ("catalog", "catalog.db"),
    ("local", "local.db"),
)
_CONSOLE_UNKNOWN_DB = "Unknown database. Choose catalog.db or local.db."
_CONSOLE_TRUNCATED = f"Results truncated to the first {ROW_CAP:,} rows."


def _console_db_options(selected: str) -> tuple[DbOption, ...]:
    """Precompute the DB picker options, marking ``selected`` (W-D8: no template logic). An
    unknown ``selected`` (e.g. a bogus form value echoed back) marks none."""
    return tuple(
        DbOption(
            value=value,
            label=label,
            selected_attr="selected" if value == selected else "",
        )
        for value, label in _CONSOLE_DBS
    )


async def _read_console_form(request: Request) -> tuple[str, str]:
    """Read the console form's ``sql`` + ``db`` fields from the urlencoded POST body.

    Parsed with stdlib ``parse_qs`` on purpose: Starlette's ``request.form()`` would pull in
    ``python-multipart``, an extra dependency the read-only console does not need (the form is a
    plain ``application/x-www-form-urlencoded`` submit, no file uploads)."""
    raw = await request.body()
    parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    return parsed.get("sql", [""])[0], parsed.get("db", [""])[0]


def _to_console_result(outcome: ConsoleOutcome) -> ConsoleResult:
    """Build the console result view-model from a successful ``run_query`` outcome. ``truncated``
    becomes a 0-or-1 message tuple for the logic-free banner."""
    truncated = (_CONSOLE_TRUNCATED,) if outcome.truncated else ()
    return ConsoleResult(
        columns=outcome.columns,
        rows=tuple(ConsoleRow(cells=cells) for cells in outcome.rows),
        row_count=outcome.row_count,
        elapsed_ms=outcome.elapsed_ms,
        truncated=truncated,
    )


def build_app(
    *,
    catalog_db_path: Path,
    local_db_path: Path,
    matcher_config: MatcherConfig,
    target_segments: tuple[TargetSegment, ...],
    templates_dir: Path,
    static_dir: Path,
    control: CrawlerControl,
    status_readings: StatusReadings,
    amule_url: str,
    wall_clock: WallClock,
    monotonic_clock: MonotonicClock,
    source_period_gap: timedelta,
) -> Starlette:
    """Build and return the wired Starlette application.

    ``matcher_config`` + ``target_segments`` arrive ALREADY PARSED from the caller (``__main__`` for
    the standalone entrypoint, ``CrawlerApp`` in-process later); this module no longer reads
    ``matcher.yml`` / ``targets.yml`` itself. Passing the crawler's own parsed matcher is what
    keeps the explainer's config from drifting from the persisted decisions (spec §8).

    ``control`` is the runtime-control PORT (``CrawlerControl``): the webui depends on the port,
    never on the concrete adapter (composition wires ``LoopCrawlerControl``). Every control POST
    dispatches a thread-safe, fire-and-forget intent to the crawler loop; the webui itself holds
    no write connection (spec §4/§10). ``status_readings`` holds the status loops' last readings.

    ``amule_url`` is the base the nav's aMule entry points at (design §9); the caller reads it
    from ``webui.amule_url``. ``source_period_gap`` is the longest gap within a source period, from
    ``webui.source_period_gap_seconds`` (source points spec, D6)."""

    # No type checker reads templates: a name missing from the context raises, never prints "".
    templates = Jinja2Templates(
        env=Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(),
            undefined=StrictUndefined,
        ),
        context_processors=[_make_nav_context(amule_url)],
    )
    explainer = MatchingExplainer(matcher_config=matcher_config, targets=target_segments)

    # Centralized read-only connection management (spec §7): one reused, thread-affine
    # connection per DB per thread: warm page cache, no per-request cold open. Handlers
    # obtain a connection via ``provider.connection()`` and NEVER close it (the point is
    # reuse).
    catalog_reader = ReaderProvider(catalog_db_path)
    local_reader = ReaderProvider(local_db_path)

    def _now_and_interval(request: Request) -> tuple[datetime, Interval]:
        """The second the request is read at, and the interval it asks for."""
        now = wall_clock.now().replace(microsecond=0)
        query_params = request.query_params
        return now, requested_interval(query_params.get("from"), query_params.get("to"), now)

    # Full segment by target_id (Task 3: seasonal locator + title resolution on /files)
    _segment_by_id = {seg.target_id: seg for seg in target_segments}

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def handle_health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def handle_dashboard(request: Request) -> Response:
        catalog = CatalogReader(catalog_reader.connection())
        coverage_data = catalog.target_coverage()
        local = LocalReader(local_reader.connection())
        node_state = local.node_state()

        coverage_rows = []
        for seg in target_segments:
            decisions = coverage_data.get(seg.target_id, [])
            cov = coverage_of(decisions)
            coverage_rows.append(
                TargetCoverageRow(
                    target_id=seg.target_id,
                    title=seg.title,
                    status=cov.status,
                    best_tier_display=cov.best_tier if cov.best_tier is not None else "·",
                    file_count=cov.file_count,
                )
            )

        done = request.query_params.get("done")
        message = _CONTROL_MESSAGES.get(done) if done is not None else None
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "coverage_rows": coverage_rows,
                "node_state": node_state,
                "clients": _client_lines(status_readings),
                "crawl_state": "paused" if control.is_paused() else "running",
                # 0-or-1-element tuple the template iterates with {% for %} (no {% if %}, W-D8).
                "messages": (message,) if message is not None else (),
            },
        )

    async def handle_files(request: Request) -> Response:
        # Filters: ``param.strip() or None`` (webui-security#0). A select with an empty option
        # sent ``?target_id=`` (empty string) that matched 0 results with no message.
        target_id_param = _normalize_param(request.query_params.get("target_id"))
        tier_param = _normalize_param(request.query_params.get("tier"))
        search_text = _normalize_param(request.query_params.get("search"))
        # Presence of ``show_unmatched`` (any value) opts into the whole catalogue.
        show_unmatched = request.query_params.get("show_unmatched") is not None
        sort_param = _normalize_sort(request.query_params.get("sort"))
        direction_param = _normalize_direction(request.query_params.get("direction"))
        page = _page_number(request.query_params.get("page"))

        catalog = CatalogReader(catalog_reader.connection())
        file_rows = catalog.list_files(
            target=target_id_param,
            tier=tier_param,
            query=search_text,
            page=page,
            matched_only=not show_unmatched,
            sort=sort_param,
            direction=direction_param,
        )
        matched_count, total_count = catalog.count_files(
            target=target_id_param,
            tier=tier_param,
            query=search_text,
        )

        display_rows = _to_display_rows(file_rows, _segment_by_id)
        # Active, non-default params (page excluded). Every URL derives from these two ordered
        # dicts, so param order is deterministic. ``filter_params`` is what a re-sort keeps;
        # ``sort_params`` is what a filter/toggle/page keeps.
        filter_params: dict[str, str] = {}
        if target_id_param is not None:
            filter_params["target_id"] = target_id_param
        if tier_param is not None:
            filter_params["tier"] = tier_param
        if search_text is not None:
            filter_params["search"] = search_text
        if show_unmatched:
            filter_params["show_unmatched"] = "1"
        sort_params: dict[str, str] = {}
        if sort_param != DEFAULT_SORT:
            sort_params["sort"] = sort_param
        if direction_param != DEFAULT_DIR:
            sort_params["direction"] = direction_param

        sort_headers = _sort_headers(
            active_sort=sort_param, active_direction=direction_param, kept_params=filter_params
        )

        # summary toggle preserves sort and direction (not show_unmatched, which it manages itself)
        summary_kept_params = {k: v for k, v in filter_params.items() if k != "show_unmatched"}
        summary_kept_params.update(sort_params)
        summary = _files_summary(matched_count, total_count, show_unmatched, summary_kept_params)

        # Tier facet (facet-lite: never filtered by its own tier) + filename search form. The
        # facet links carry every active param except ``tier`` and ``page`` (selecting a tier
        # replaces it, resets page); the search hidden inputs carry every active param except
        # ``search`` and ``page`` (submitting a search preserves the rest, resets page).
        file_count_by_tier = catalog.tier_counts(target=target_id_param, query=search_text)
        facet_kept_params = {k: v for k, v in filter_params.items() if k != "tier"}
        facet_kept_params.update(sort_params)
        facets = _tier_facets(
            file_count_by_tier=file_count_by_tier,
            active_tier=tier_param,
            kept_params=facet_kept_params,
        )

        search_kept_params = {k: v for k, v in filter_params.items() if k != "search"}
        search_kept_params.update(sort_params)
        searchbar = _search_bar(search_text=search_text, kept_params=search_kept_params)

        filter_bar = FilterBar(searchbar=searchbar, facets=facets)

        nav = _page_nav(page, len(display_rows), "/files", {**filter_params, **sort_params})
        return templates.TemplateResponse(
            request,
            "files.html",
            {
                "rows": display_rows,
                "nav": nav,
                "headings": (),  # the nav's bold "Files" entry already names this page
                "summaries": (summary,),
                "sort_headers": (sort_headers,),
                "filter_bar": (filter_bar,),
            },
        )

    async def handle_sources(request: Request) -> Response:
        search_text = _normalize_param(request.query_params.get("search"))
        page = _page_number(request.query_params.get("page"))
        catalog = CatalogReader(catalog_reader.connection())
        rows = tuple(
            _source_list_row(row) for row in catalog.list_sources(query=search_text, page=page)
        )
        count = catalog.count_sources(query=search_text)
        kept_params = {} if search_text is None else {"search": search_text}
        return templates.TemplateResponse(
            request,
            "sources.html",
            {
                "rows": rows,
                "nav": _page_nav(page, len(rows), "/sources", kept_params),
                "summary": (
                    f"Sources recorded: {count:,}."
                    if search_text is None
                    else f"Sources matching the search: {count:,}."
                ),
                "search_text": search_text or "",
            },
        )

    async def handle_source(request: Request) -> Response:
        source_id_hex: str = request.path_params["source_id"]
        page = _page_number(request.query_params.get("page"))
        now, interval = _now_and_interval(request)
        window = _period_window(interval, source_period_gap)
        catalog = CatalogReader(catalog_reader.connection())
        detail = (
            catalog.source_detail(bytes.fromhex(source_id_hex), page=page, window=window)
            if _HEX_ID.fullmatch(source_id_hex)
            else None
        )
        if detail is None:
            return templates.TemplateResponse(request, "404.html", {}, status_code=404)
        path = f"/sources/{source_id_hex}"
        return templates.TemplateResponse(
            request,
            "source_detail.html",
            {
                "source": detail.source,
                "names": tuple(_source_list_row(row) for row in detail.names),
                "periods": tuple(_source_file_row(item) for item in detail.periods),
                "nav": _page_nav(page, len(detail.names), path, _interval_params(request)),
                "interval": _interval_selector(interval, now, path, _page_param(page)),
            },
        )

    async def handle_source_name(request: Request) -> Response:
        source_name = request.query_params.get("source_name")
        page = _page_number(request.query_params.get("page"))
        now, interval = _now_and_interval(request)
        window = _period_window(interval, source_period_gap)
        catalog = CatalogReader(catalog_reader.connection())
        detail = (
            None
            if source_name is None
            else catalog.name_detail(source_name, page=page, window=window)
        )
        if detail is None:
            return templates.TemplateResponse(request, "404.html", {}, status_code=404)
        path, source_name_params = "/sources/name", {"source_name": detail.name}
        return templates.TemplateResponse(
            request,
            "source_name.html",
            {
                "name": detail.name,
                "sources": tuple(_source_list_row(row) for row in detail.sources),
                "periods": tuple(_source_file_row(item) for item in detail.periods),
                "nav": _page_nav(
                    page,
                    len(detail.sources),
                    path,
                    {**source_name_params, **_interval_params(request)},
                ),
                "interval": _interval_selector(
                    interval, now, path, {**source_name_params, **_page_param(page)}
                ),
            },
        )

    async def handle_file_detail(request: Request) -> Response:
        file_id_hex: str = request.path_params["file_id"]

        now, interval = _now_and_interval(request)
        window = _period_window(interval, source_period_gap)
        catalog = CatalogReader(catalog_reader.connection())
        detail = (
            catalog.file_detail(bytes.fromhex(file_id_hex), window)
            if _HEX_ID.fullmatch(file_id_hex)
            else None
        )

        if detail is None:
            return templates.TemplateResponse(request, "404.html", {}, status_code=404)

        latest = detail.latest
        ed2k_link = ""
        if latest is not None:
            match detail.file.network:
                case Network.ED2K:
                    ed2k_link = build_ed2k_link(
                        latest.filename, latest.size_bytes, detail.file.native_id
                    )
                case _:  # pragma: no cover
                    assert_never(detail.file.network)

        # Explanation from the current config
        explanation_target_id: str | None = None
        explanation_rules_fired: tuple[str, ...] = ()
        explanation_tokens_matched: tuple[str, ...] = ()
        explanation_coverage_values: tuple[TokenCoverage, ...] = ()
        explanation_vetoes_fired: tuple[str, ...] = ()
        explanation_notes: tuple[str, ...] = ()

        first_decision = detail.decisions[0] if detail.decisions else None
        if first_decision is not None and latest is not None:
            # Every known name with the latest fields, as the crawler judges.
            explanation = explainer.explain(
                filenames=detail.known_filenames,
                size_bytes=latest.size_bytes,
                duration_seconds=latest.duration_seconds,
                bitrate_kbps=latest.bitrate_kbps,
                target_id=first_decision.target_id,
            )
            if explanation is not None:
                explanation_target_id = explanation.target_id
                explanation_rules_fired = explanation.rules_fired
                explanation_tokens_matched = explanation.tokens_matched
                explanation_coverage_values = tuple(
                    TokenCoverage(token_name=token_name, coverage=f"{coverage:.2f}")
                    for token_name, coverage in explanation.coverage_values
                )
                explanation_vetoes_fired = explanation.vetoes_fired
                explanation_notes = ("Evaluated against the current configuration",)

        display = FileDetailDisplay(
            network=detail.file.network,
            native_id=detail.file.native_id,
            size_bytes=detail.size_bytes,
            timeline=tuple(_timeline_row(sighting) for sighting in detail.sightings),
            source_history=tuple(
                _source_history_row(period)
                for period in catalog.source_periods(detail.file.file_id, window)
            ),
            decisions=detail.decisions,
            ed2k_link=ed2k_link,
            explanation_target_id=explanation_target_id,
            explanation_rules_fired=explanation_rules_fired,
            explanation_tokens_matched=explanation_tokens_matched,
            explanation_coverage_values=explanation_coverage_values,
            explanation_vetoes_fired=explanation_vetoes_fired,
            explanation_notes=explanation_notes,
        )

        return templates.TemplateResponse(
            request,
            "file_detail.html",
            {
                "file": display,
                "interval": _interval_selector(interval, now, f"/files/{file_id_hex}", {}),
            },
        )

    async def handle_target(request: Request) -> Response:
        target_id: str = request.path_params["target_id"]
        catalog = CatalogReader(catalog_reader.connection())
        file_rows = catalog.list_files(
            target=target_id,
            tier=None,
            query=None,
            page=1,
        )

        display_rows = _to_display_rows(file_rows, _segment_by_id)
        # No pagination here (target view: we expect few). Empty nav.
        nav = PageNav(page=1, prev_url=None, next_url=None)
        # files.html is shared with /files, whose matched/all summary line and filter bar are
        # meaningless on a target-scoped page: pass empty tuples so they render nothing. This
        # page is NOT a nav destination, though, so unlike /files it does carry a heading.
        return templates.TemplateResponse(
            request,
            "files.html",
            {
                "rows": display_rows,
                "nav": nav,
                "headings": (f"Files for target {target_id}",),
                "summaries": (),
                "sort_headers": (),
                "filter_bar": (),
            },
        )

    async def handle_node(request: Request) -> Response:
        local = LocalReader(local_reader.connection())
        node_state = local.node_state()

        backoff_entries = tuple(
            BackoffEntry(
                client_name=row.client_name,
                channel=row.channel if row.channel is not None else "whole client",
                attempts=row.attempts,
                retry_at_display=row.retry_at.isoformat(timespec="microseconds"),
            )
            for row in node_state.backoff_rows
        )

        return templates.TemplateResponse(
            request,
            "node.html",
            {"node_state": node_state, "backoff_entries": backoff_entries},
        )

    # ------------------------------------------------------------------
    # Runtime controls (phase P6a): POST intents dispatched to the crawler loop via
    # ``control`` (a ``CrawlerControl`` port). Each POST is fire-and-forget then redirects
    # (PRG) to ``/?done=<code>``, where the dashboard shows a 0-or-1 message banner.
    # NO CSRF token: consistent with the no-auth, network-trust-boundary posture (spec §12).
    # ------------------------------------------------------------------

    async def handle_pause(request: Request) -> Response:
        control.pause()
        return RedirectResponse("/?done=paused", status_code=303)

    async def handle_resume(request: Request) -> Response:
        control.resume()
        return RedirectResponse("/?done=resumed", status_code=303)

    async def handle_restart(request: Request) -> Response:
        control.restart()
        return RedirectResponse("/?done=restarted", status_code=303)

    # ------------------------------------------------------------------
    # SQL console (spec §11): a read-only power-user console over either DB.
    # ``run_query`` opens its OWN fresh ``mode=ro`` + ``query_only`` connection with a per-query
    # progress-handler timeout, so a runaway query cannot write and cannot disturb the reused
    # page-serving readers. It runs OFF the event loop via ``run_in_threadpool`` so a slow query
    # (up to the timeout) blocks neither the crawler thread nor the webui loop, only its pool slot.
    # NO CSRF token: consistent with the no-auth, network-trust-boundary posture (spec §12).
    # ------------------------------------------------------------------

    _console_db_paths = {"catalog": catalog_db_path, "local": local_db_path}

    async def handle_console(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "console.html",
            {
                "sql": "",
                "db_options": _console_db_options("catalog"),
                "results": (),
                "errors": (),
            },
        )

    async def handle_console_run(request: Request) -> Response:
        sql, db_key = await _read_console_form(request)
        db_options = _console_db_options(db_key)
        if db_key not in _console_db_paths:
            return templates.TemplateResponse(
                request,
                "console.html",
                {
                    "sql": sql,
                    "db_options": db_options,
                    "results": (),
                    "errors": (_CONSOLE_UNKNOWN_DB,),
                },
            )
        outcome = await run_in_threadpool(
            run_query,
            db_path=_console_db_paths[db_key],
            sql=sql,
            row_cap=ROW_CAP,
            timeout_seconds=TIMEOUT_SECONDS,
            monotonic_clock=monotonic_clock,
        )
        if outcome.error is not None:
            return templates.TemplateResponse(
                request,
                "console.html",
                {
                    "sql": sql,
                    "db_options": db_options,
                    "results": (),
                    "errors": (outcome.error,),
                },
            )
        return templates.TemplateResponse(
            request,
            "console.html",
            {
                "sql": sql,
                "db_options": db_options,
                "results": (_to_console_result(outcome),),
                "errors": (),
            },
        )

    async def handle_console_csv(request: Request) -> Response:
        sql, db_key = await _read_console_form(request)
        if db_key not in _console_db_paths:
            return Response(_CONSOLE_UNKNOWN_DB, status_code=400, media_type="text/plain")
        outcome = await run_in_threadpool(
            run_query,
            db_path=_console_db_paths[db_key],
            sql=sql,
            row_cap=ROW_CAP,
            timeout_seconds=TIMEOUT_SECONDS,
            monotonic_clock=monotonic_clock,
        )
        if outcome.error is not None:
            return Response(outcome.error, status_code=400, media_type="text/plain")
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(outcome.columns)
        writer.writerows(outcome.rows)
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="query.csv"'},
        )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    return Starlette(
        routes=[
            Route("/health", handle_health),
            Route("/", handle_dashboard),
            Route("/files", handle_files),
            Route("/files/{file_id}", handle_file_detail),
            Route("/sources", handle_sources),
            # Before ``/sources/{source_id}``, which would otherwise take ``name`` (D13).
            Route("/sources/name", handle_source_name),
            Route("/sources/{source_id}", handle_source),
            Route("/targets/{target_id}", handle_target),
            Route("/node", handle_node),
            Route("/controls/pause", handle_pause, methods=["POST"]),
            Route("/controls/resume", handle_resume, methods=["POST"]),
            Route("/controls/restart", handle_restart, methods=["POST"]),
            Route("/console", handle_console),
            Route("/console", handle_console_run, methods=["POST"]),
            Route("/console.csv", handle_console_csv, methods=["POST"]),
            Mount("/static", StaticFiles(directory=static_dir)),
        ],
        middleware=[Middleware(_SecurityHeadersMiddleware)],
    )
