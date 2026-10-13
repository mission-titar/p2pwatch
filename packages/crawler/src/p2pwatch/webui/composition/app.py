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
from p2pwatch.ports.clock import Clock
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
from p2pwatch.webui.domain.coverage import coverage_for
from p2pwatch.webui.domain.format import (
    average_rate,
    human_size,
    input_timestamp,
    micros_timestamp,
    seasonal_id,
    short_hash,
    short_timestamp,
    utc_timestamp,
)
from p2pwatch.webui.domain.interval import PRESETS, Interval, last, requested_interval
from p2pwatch.webui.domain.views import (
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
    SchedulerEntry,
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
)

# A detail page's path segment: a file_id or a source_id as 32 lowercase hex (stage 1 and 4 D13).
_HEX_ID = re.compile(r"[0-9a-f]{32}")

_CUT_NOTICE = "The interval requested is longer than 7 days: showing the 7 days ending at its end."
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

# The top-nav destinations, in render order: (path, label). The single source of truth for what
# base.html renders; every page reaches all of them.
_NAV_DESTINATIONS: tuple[tuple[str, str], ...] = (
    ("/", "Dashboard"),
    ("/files", "Files"),
    ("/sources", "Sources"),
    ("/node", "Nodes"),
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
        locator = seasonal_id(
            season=seg.season, seasonal_number=seg.seasonal_number, letter=seg.segment
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
        name=sighting.name,
        size_bytes=sighting.size_bytes,
        sources=str(sighting.source_count),
        keyword=sighting.keyword,
        observed_at=sighting.observed_at,
    )


def _name_link(name: str | None) -> tuple[str, ...]:
    """The name page's href (D13), none without a name."""
    return () if name is None else (f"/sources/name?{urlencode({'name': name})}",)


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
        high_id=_YES_NO[period.directly_reachable],
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
    query = request.query_params
    return {key: query[key] for key in ("from", "to") if key in query}


def _page_param(page: int) -> dict[str, str]:
    """The ``page`` param an interval's links keep, none on the first page."""
    return {"page": str(page)} if page > 1 else {}


def _interval_selector(
    interval: Interval, now: datetime, path: str, kept: dict[str, str]
) -> IntervalSelector:
    """The selector of the page at ``path``, whose other params are ``kept`` (D6): the presets end
    ``now``, and Next is offered until the interval reaches it."""

    def url(shown: Interval) -> str:
        ends = {"from": utc_timestamp(shown.since), "to": utc_timestamp(shown.until)}
        return f"{path}?{urlencode({**kept, **ends})}"

    return IntervalSelector(
        hidden=tuple(HiddenInput(name=name, value=value) for name, value in kept.items()),
        shown=f"{utc_timestamp(interval.since)} to {utc_timestamp(interval.until)}",
        notices=(_CUT_NOTICE,) if interval.cut else (),
        presets=tuple(IntervalLink(label, url(last(span, now))) for label, span in PRESETS),
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


def _normalize(raw: str | None) -> str | None:
    """Normalize a query param: whitespace stripped, empty ⇒ ``None``. Without it, an HTML
    select with an empty option sends ``?target=`` → ``""`` → ``dec.target_id = ''`` matches
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


def _page_nav(page: int, n_rows: int, base_path: str, query: dict[str, str]) -> PageNav:
    """Precompute the prev/next links for a page (W-D8: view-model, no template logic).
    We don't have the total count → ``next`` is rendered when the page is FULL (standard
    heuristic; at worst a next click returns an empty page)."""
    prev_url: str | None = None
    next_url: str | None = None
    if page > 1:
        prev = dict(query)
        prev["page"] = str(page - 1)
        prev_url = f"{base_path}?{urlencode(prev)}"
    if n_rows >= PAGE_SIZE:
        nxt = dict(query)
        nxt["page"] = str(page + 1)
        next_url = f"{base_path}?{urlencode(nxt)}"
    return PageNav(page=page, prev_url=prev_url, next_url=next_url)


def _build_summary(
    matched: int, total: int, show_unmatched: bool, filter_query: dict[str, str]
) -> FilesSummary:
    """Precompute the /files summary line + matched/all toggle (W-D8: no template logic).

    The toggle preserves the active filters and drops ``page`` (counts differ between modes,
    so page N may not exist → back to page 1)."""
    if show_unmatched:
        summary_text = f"Showing all catalogued files: {total:,} catalogued ({matched:,} matched)."
        toggle_label = "Matched only"
        toggle_query = dict(filter_query)  # drop show_unmatched → matched only
    else:
        summary_text = f"Showing matched files only: {matched:,} of {total:,} catalogued."
        toggle_label = "Show all catalogued files"
        toggle_query = {**filter_query, "show_unmatched": "1"}
    toggle_url = "/files?" + urlencode(toggle_query) if toggle_query else "/files"
    return FilesSummary(summary_text=summary_text, toggle_label=toggle_label, toggle_url=toggle_url)


# Sortable columns in display order: allowlist key -> (header label, default direction when this
# column is NOT the active sort). Name reads best ascending; the metrics and last-seen read best
# descending (webui spec §3.1).
_SORT_LABELS: tuple[tuple[str, str], ...] = (
    ("name", "Name"),
    ("size", "Size"),
    ("sources", "Sources"),
    ("last_seen", "Last seen"),
    ("tier", "Tier"),
)
_COLUMN_DEFAULT_DIR: dict[str, str] = {
    "name": "asc",
    "size": "desc",
    "sources": "desc",
    "last_seen": "desc",
    "tier": "desc",
}
_FLIP: dict[str, str] = {"asc": "desc", "desc": "asc"}


def _normalize_sort(raw: str | None) -> str:
    """Map a raw ``sort`` param to an allowlist key, or the default (unknown/missing -> default)."""
    return raw if raw in SORT_COLUMNS else DEFAULT_SORT


def _normalize_dir(raw: str | None) -> str:
    """Map a raw ``dir`` param to ``asc``/``desc``, or the default (unknown/missing -> default)."""
    return raw if raw in SORT_DIRECTIONS else DEFAULT_DIR


def _sort_header(
    col: str, label: str, sort: str, direction: str, filters: dict[str, str]
) -> SortHeader:
    """Build one column header. Keeps every ``filters`` param and OVERRIDES sort/dir: the active
    column flips direction and shows its indicator; an inactive column uses its default direction
    and no indicator. Params equal to the default are omitted from the URL (clean, deterministic).
    """
    active = col == sort
    next_dir = _FLIP[direction] if active else _COLUMN_DEFAULT_DIR[col]
    indicator = direction if active else ""
    params = dict(filters)
    if col != DEFAULT_SORT:
        params["sort"] = col
    if next_dir != DEFAULT_DIR:
        params["dir"] = next_dir
    url = "/files?" + urlencode(params) if params else "/files"
    return SortHeader(label=label, url=url, indicator=indicator)


def _sort_headers(*, sort: str, direction: str, filters: dict[str, str]) -> SortHeaders:
    """Precompute all five sortable headers (W-D8)."""
    built = {col: _sort_header(col, label, sort, direction, filters) for col, label in _SORT_LABELS}
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
    *, counts: Mapping[str, int], active_tier: str | None, base: dict[str, str]
) -> tuple[TierFacet, ...]:
    """Precompute the tier facet (W-D8): an "all" reset (no count) followed by one entry per tier
    present, in ``_FACET_TIER_ORDER``. ``base`` is the params to preserve (filters minus ``tier``,
    plus sort/dir; page already excluded); a tier entry appends ``tier=<t>``, the reset omits it."""
    all_url = "/files?" + urlencode(base) if base else "/files"
    facets = [
        TierFacet(
            label="all",
            count_display="",
            url=all_url,
            selected_flag="1" if active_tier is None else "",
        )
    ]
    for tier in _FACET_TIER_ORDER:
        if tier not in counts:
            continue
        params = {**base, "tier": tier}
        facets.append(
            TierFacet(
                label=_facet_label(tier),
                count_display=f"({counts[tier]})",
                url="/files?" + urlencode(params),
                selected_flag="1" if active_tier == tier else "",
            )
        )
    return tuple(facets)


def _search_bar(*, query: str | None, hidden_state: dict[str, str]) -> SearchBar:
    """Precompute the search form (W-D8): the ``q`` prefill (empty string when none) + hidden
    inputs from ``hidden_state`` (already excludes ``q`` and ``page``)."""
    hidden = tuple(HiddenInput(name=k, value=v) for k, v in hidden_state.items())
    return SearchBar(query=query or "", hidden=hidden)


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
    "restart": "Restart requested. The service goes offline briefly, then returns.",
}


_YES_NO: dict[bool | None, str] = {True: "yes", False: "no", None: "unknown"}


def _client_lines(status: StatusReadings) -> tuple[ClientLine, ...]:
    """Each client's last reading, its values shown only while current (stage 2 D20)."""
    lines = []
    for name, reading in status.readings().items():
        if reading is None:
            lines.append(ClientLine(name, "No reading yet.", "unknown", "unknown", ()))
            continue
        read_at = short_timestamp(reading.read_at.isoformat())
        client = reading.status
        if not status.is_current(reading):
            text = f"Out of date: last reading at {read_at}."
            lines.append(ClientLine(name, text, "unknown", "unknown", ()))
        elif client is None:
            lines.append(ClientLine(name, f"Read at {read_at}.", "unknown", "no", ()))
        else:
            channels = tuple(
                ChannelLine(c.channel, _YES_NO[c.on_network], _YES_NO[c.connectable])
                for c in client.channels
            )
            version = client.version or "unknown"
            lines.append(ClientLine(name, f"Read at {read_at}.", version, "yes", channels))
    return tuple(lines)


# SQL console (spec §11). The two selectable databases, in display order: value (allowlist key)
# + human label. Neither holds a peer's address (a source is a pseudonymous id at most), so
# read-only exposure of either is fine.
_CONSOLE_DB_LABELS: tuple[tuple[str, str], ...] = (
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
        for value, label in _CONSOLE_DB_LABELS
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
    catalog_db: Path,
    local_db: Path,
    matcher_config: MatcherConfig,
    targets: tuple[TargetSegment, ...],
    templates_dir: Path,
    static_dir: Path,
    control: CrawlerControl,
    status: StatusReadings,
    amule_url: str,
    clock: Clock,
    source_period_gap: timedelta,
) -> Starlette:
    """Build and return the wired Starlette application.

    ``matcher_config`` + ``targets`` arrive ALREADY PARSED from the caller (``__main__`` for
    the standalone entrypoint, ``CrawlerApp`` in-process later); this module no longer reads
    ``matcher.yml`` / ``targets.yml`` itself. Passing the crawler's own parsed matcher is what
    keeps the explainer's config from drifting from the persisted decisions (spec §8).

    ``control`` is the runtime-control PORT (``CrawlerControl``): the webui depends on the port,
    never on the concrete adapter (composition wires ``LoopCrawlerControl``). Every control POST
    dispatches a thread-safe, fire-and-forget intent to the crawler loop; the webui itself holds
    no write connection (spec §4/§10). ``status`` holds the status loops' last readings.

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
    target_segments = targets
    explainer = MatchingExplainer(matcher_config=matcher_config, targets=targets)

    # Centralized read-only connection management (spec §7): one reused, thread-affine
    # connection per DB per thread: warm page cache, no per-request cold open. Handlers
    # obtain a connection via ``provider.connection()`` and NEVER close it (the point is
    # reuse); ``quiesce()`` is the seam livrable 3's maintenance swap will use.
    catalog_reader = ReaderProvider(catalog_db)
    local_reader = ReaderProvider(local_db)

    def _interval(request: Request) -> tuple[datetime, Interval]:
        """The second the request is read at, and the interval it asks for."""
        now = clock.now().replace(microsecond=0)
        query = request.query_params
        return now, requested_interval(query.get("from"), query.get("to"), now)

    # Title by target_id (quick access)
    _title_by_id = {seg.target_id: seg.title for seg in target_segments}
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

        rows = []
        for seg in target_segments:
            decisions = coverage_data.get(seg.target_id, [])
            cov = coverage_for(seg.target_id, decisions)
            rows.append(
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
                "rows": rows,
                "node_state": node_state,
                "clients": _client_lines(status),
                "crawl": "paused" if control.is_paused() else "running",
                # 0-or-1-element tuple the template iterates with {% for %} (no {% if %}, W-D8).
                "messages": (message,) if message is not None else (),
            },
        )

    async def handle_files(request: Request) -> Response:
        # Filters: ``param.strip() or None`` (webui-security#0). A select with an empty option
        # sent ``?target=`` (empty string) that matched 0 results with no message.
        target_param = _normalize(request.query_params.get("target"))
        tier_param = _normalize(request.query_params.get("tier"))
        query_param = _normalize(request.query_params.get("q"))
        # Presence of ``show_unmatched`` (any value) opts into the whole catalogue.
        show_unmatched = request.query_params.get("show_unmatched") is not None
        sort_param = _normalize_sort(request.query_params.get("sort"))
        dir_param = _normalize_dir(request.query_params.get("dir"))
        page = _page_number(request.query_params.get("page"))

        catalog = CatalogReader(catalog_reader.connection())
        file_rows = catalog.list_files(
            target=target_param,
            tier=tier_param,
            query=query_param,
            page=page,
            matched_only=not show_unmatched,
            sort=sort_param,
            direction=dir_param,
        )
        matched, total = catalog.count_files(
            target=target_param,
            tier=tier_param,
            query=query_param,
        )

        display_rows = _to_display_rows(file_rows, _segment_by_id)
        # Active, non-default params (page excluded). Every URL derives from these two ordered
        # dicts, so param order is deterministic. ``filters`` is what a re-sort keeps; ``sort_dir``
        # is what a filter/toggle/page keeps.
        filters: dict[str, str] = {}
        if target_param is not None:
            filters["target"] = target_param
        if tier_param is not None:
            filters["tier"] = tier_param
        if query_param is not None:
            filters["q"] = query_param
        if show_unmatched:
            filters["show_unmatched"] = "1"
        sort_dir: dict[str, str] = {}
        if sort_param != DEFAULT_SORT:
            sort_dir["sort"] = sort_param
        if dir_param != DEFAULT_DIR:
            sort_dir["dir"] = dir_param

        headers = _sort_headers(sort=sort_param, direction=dir_param, filters=filters)

        # summary toggle preserves sort/dir (but not show_unmatched, which it manages itself)
        summary_base = {k: v for k, v in filters.items() if k != "show_unmatched"}
        summary_base.update(sort_dir)
        summary = _build_summary(matched, total, show_unmatched, summary_base)

        # Tier facet (facet-lite: never filtered by its own tier) + filename search form. The
        # facet links carry every active param except ``tier`` and ``page`` (selecting a tier
        # replaces it, resets page); the search hidden inputs carry every active param except
        # ``q`` and ``page`` (submitting a search preserves the rest, resets page).
        tier_count_map = catalog.tier_counts(target=target_param, query=query_param)
        facet_base = {k: v for k, v in filters.items() if k != "tier"}
        facet_base.update(sort_dir)
        facets = _tier_facets(counts=tier_count_map, active_tier=tier_param, base=facet_base)

        hidden_state = {k: v for k, v in filters.items() if k != "q"}
        hidden_state.update(sort_dir)
        searchbar = _search_bar(query=query_param, hidden_state=hidden_state)

        filter_bar = FilterBar(searchbar=searchbar, facets=facets)

        nav = _page_nav(page, len(display_rows), "/files", {**filters, **sort_dir})
        return templates.TemplateResponse(
            request,
            "files.html",
            {
                "rows": display_rows,
                "nav": nav,
                "headings": (),  # the nav's bold "Files" entry already names this page
                "summaries": (summary,),
                "headers": (headers,),
                "filter_bar": (filter_bar,),
            },
        )

    async def handle_sources(request: Request) -> Response:
        query = _normalize(request.query_params.get("q"))
        page = _page_number(request.query_params.get("page"))
        catalog = CatalogReader(catalog_reader.connection())
        rows = tuple(_source_list_row(row) for row in catalog.list_sources(query=query, page=page))
        count = catalog.count_sources(query=query)
        filters = {} if query is None else {"q": query}
        return templates.TemplateResponse(
            request,
            "sources.html",
            {
                "rows": rows,
                "nav": _page_nav(page, len(rows), "/sources", filters),
                "summary": (
                    f"Sources recorded: {count:,}."
                    if query is None
                    else f"Sources matching the search: {count:,}."
                ),
                "query": query or "",
            },
        )

    async def handle_source(request: Request) -> Response:
        raw_id: str = request.path_params["source_id"]
        page = _page_number(request.query_params.get("page"))
        now, interval = _interval(request)
        window = _period_window(interval, source_period_gap)
        catalog = CatalogReader(catalog_reader.connection())
        detail = (
            catalog.source_detail(bytes.fromhex(raw_id), page=page, window=window)
            if _HEX_ID.fullmatch(raw_id)
            else None
        )
        if detail is None:
            return templates.TemplateResponse(request, "404.html", {}, status_code=404)
        path = f"/sources/{raw_id}"
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
        name = request.query_params.get("name")
        page = _page_number(request.query_params.get("page"))
        now, interval = _interval(request)
        window = _period_window(interval, source_period_gap)
        catalog = CatalogReader(catalog_reader.connection())
        detail = None if name is None else catalog.name_detail(name, page=page, window=window)
        if detail is None:
            return templates.TemplateResponse(request, "404.html", {}, status_code=404)
        path, named = "/sources/name", {"name": detail.name}
        return templates.TemplateResponse(
            request,
            "source_name.html",
            {
                "name": detail.name,
                "sources": tuple(_source_list_row(row) for row in detail.sources),
                "periods": tuple(_source_file_row(item) for item in detail.periods),
                "nav": _page_nav(
                    page, len(detail.sources), path, {**named, **_interval_params(request)}
                ),
                "interval": _interval_selector(interval, now, path, {**named, **_page_param(page)}),
            },
        )

    async def handle_file_detail(request: Request) -> Response:
        raw_id: str = request.path_params["file_id"]

        now, interval = _interval(request)
        window = _period_window(interval, source_period_gap)
        catalog = CatalogReader(catalog_reader.connection())
        detail = (
            catalog.file_detail(bytes.fromhex(raw_id), window)
            if _HEX_ID.fullmatch(raw_id)
            else None
        )

        if detail is None:
            return templates.TemplateResponse(request, "404.html", {}, status_code=404)

        latest = detail.latest
        link = ""
        if latest is not None:
            match detail.file.network:
                case Network.ED2K:
                    link = build_ed2k_link(latest.name, latest.size_bytes, detail.file.native_id)
                case _:  # pragma: no cover
                    assert_never(detail.file.network)

        # Explanation from the current config
        explanation_target_id: str | None = None
        explanation_rules_fired: tuple[str, ...] = ()
        explanation_tokens_matched: tuple[str, ...] = ()
        explanation_vetoes_fired: tuple[str, ...] = ()
        explanation_notes: tuple[str, ...] = ()

        first_decision = detail.decisions[0] if detail.decisions else None
        if first_decision is not None and latest is not None:
            # Every known name with the latest fields, as the crawler judges.
            explanation = explainer.explain(
                filenames=detail.known_filenames,
                size_bytes=latest.size_bytes,
                media_length_sec=latest.media_length_sec,
                bitrate_kbps=latest.bitrate_kbps,
                target_id=first_decision.target_id,
            )
            if explanation is not None:
                explanation_target_id = explanation.target_id
                explanation_rules_fired = explanation.rules_fired
                explanation_tokens_matched = explanation.tokens_matched
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
            ed2k_link=link,
            explanation_target_id=explanation_target_id,
            explanation_rules_fired=explanation_rules_fired,
            explanation_tokens_matched=explanation_tokens_matched,
            explanation_vetoes_fired=explanation_vetoes_fired,
            explanation_notes=explanation_notes,
        )

        return templates.TemplateResponse(
            request,
            "file_detail.html",
            {
                "file": display,
                "title_by_id": _title_by_id,
                "interval": _interval_selector(interval, now, f"/files/{raw_id}", {}),
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
                "headers": (),
                "filter_bar": (),
            },
        )

    async def handle_node(request: Request) -> Response:
        local = LocalReader(local_reader.connection())
        node_state = local.node_state()

        scheduler_entries = tuple(
            SchedulerEntry(key=k, value=v) for k, v in node_state.scheduler.items()
        )

        return templates.TemplateResponse(
            request,
            "node.html",
            {"node_state": node_state, "scheduler_entries": scheduler_entries},
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
        return RedirectResponse("/?done=restart", status_code=303)

    # ------------------------------------------------------------------
    # SQL console (spec §11): a read-only power-user console over either DB.
    # ``run_query`` opens its OWN fresh ``mode=ro`` + ``query_only`` connection with a per-query
    # progress-handler timeout, so a runaway query cannot write and cannot disturb the reused
    # page-serving readers. It runs OFF the event loop via ``run_in_threadpool`` so a slow query
    # (up to the timeout) blocks neither the crawler thread nor the webui loop, only its pool slot.
    # NO CSRF token: consistent with the no-auth, network-trust-boundary posture (spec §12).
    # ------------------------------------------------------------------

    _console_db_paths = {"catalog": catalog_db, "local": local_db}

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
        sql, db = await _read_console_form(request)
        db_options = _console_db_options(db)
        if db not in _console_db_paths:
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
            db_path=_console_db_paths[db],
            sql=sql,
            row_cap=ROW_CAP,
            timeout_seconds=TIMEOUT_SECONDS,
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
        sql, db = await _read_console_form(request)
        if db not in _console_db_paths:
            return Response(_CONSOLE_UNKNOWN_DB, status_code=400, media_type="text/plain")
        outcome = await run_in_threadpool(
            run_query,
            db_path=_console_db_paths[db],
            sql=sql,
            row_cap=ROW_CAP,
            timeout_seconds=TIMEOUT_SECONDS,
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
