"""Starlette application factory (webui spec, Task 11).

``build_app`` wires the adapters (SQLite, YAML, templates) and registers all
routes. The handlers are closures capturing the dependencies: no ``app.state``.
"""

import csv
import io
import re
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, assert_never
from urllib.parse import parse_qs, urlencode

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from catalog_matching.domain.ed2k_link import build_ed2k_link
from catalog_matching.domain.models import TargetSegment
from p2pwatch.adapters.driving.webui.displays import (
    BackoffEntryDisplay,
    ChannelLineDisplay,
    ClientLineDisplay,
    DbOptionDisplay,
    DecisionCellDisplay,
    DecisionDisplay,
    FileDetailDisplay,
    FileRowDisplay,
    FilesSummaryDisplay,
    FilterBarDisplay,
    HiddenInputDisplay,
    IntervalLinkDisplay,
    IntervalSelectorDisplay,
    NavItemDisplay,
    NodeStateDisplay,
    PageNavDisplay,
    QueryAnswerDisplay,
    QueryRowDisplay,
    SearchBarDisplay,
    SortHeaderDisplay,
    SortHeadersDisplay,
    SourceFileRowDisplay,
    SourceHistoryRowDisplay,
    SourceKeyDisplay,
    SourceListRowDisplay,
    TargetCoverageDisplay,
    TierFacetDisplay,
    TimelineRowDisplay,
    TokenCoverageDisplay,
    TrackedDownloadDisplay,
)
from p2pwatch.adapters.driving.webui.format import (
    average_rate,
    human_size,
    input_timestamp,
    parse_instant,
    seasonal_locator,
    short_hash,
    short_timestamp,
    utc_timestamp,
)
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.console_query import ConsoleDatabase, QueryAnswer, QueryFailure
from p2pwatch.domain.file_key import Network
from p2pwatch.domain.interval import (
    MAX_INTERVAL_SPAN,
    Interval,
    interval_ending,
)
from p2pwatch.domain.known_source import KnownSource
from p2pwatch.domain.node_state import NodeState
from p2pwatch.domain.observation import FileObservation
from p2pwatch.domain.sharing_period import SharingPeriod
from p2pwatch.domain.source import SourceKey
from p2pwatch.domain.source_history import SourceNaming
from p2pwatch.ports.driving.console_query_runner import ConsoleQueryRunner
from p2pwatch.ports.driving.crawl_pauser import CrawlPauser
from p2pwatch.ports.driving.crawl_resumer import CrawlResumer
from p2pwatch.ports.driving.crawl_summarizer import ClientSummary, CrawlSummarizer
from p2pwatch.ports.driving.file_describer import FileDescriber
from p2pwatch.ports.driving.file_lister import FileLister
from p2pwatch.ports.driving.node_describer import NodeDescriber
from p2pwatch.ports.driving.shutdown_requester import ShutdownRequester
from p2pwatch.ports.driving.source_describer import SourceDescriber
from p2pwatch.ports.driving.source_lister import SourceLister
from p2pwatch.ports.driving.source_name_describer import SourceNameDescriber

# A detail page's path segment: a file_id or a source_id as 32 lowercase hex (stage 1 and 4 D13).
_HEX_ID = re.compile(r"[0-9a-f]{32}")

_INTERVAL_PRESETS: tuple[tuple[str, timedelta], ...] = (
    ("Last hour", timedelta(hours=1)),
    ("Last 6 hours", timedelta(hours=6)),
    ("Last 24 hours", timedelta(hours=24)),
    ("Last 7 days", MAX_INTERVAL_SPAN),
)
_CLAMPED_NOTICE = (
    "The interval requested is longer than 7 days: showing the 7 days ending at its end."
)
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
                    NavItemDisplay(label=label, link=() if path == current else (path,))
                    for path, label in _NAV_DESTINATIONS
                ),
                NavItemDisplay(label="aMule", link=(amule_url,)),
            )
        }

    return nav_context


def _resolve_target_display(
    entry: CatalogEntry, segment_by_id: Mapping[str, TargetSegment]
) -> list[tuple[str, str]]:
    """Per-decision ``(target, title)`` pairs for a catalog entry, in the entry's
    decision order (by target_id). Empty when the file has no current decision. The
    ``catalog → "unidentified"`` mask is applied per decision (``keroro_large`` is the only
    catalog-tier rule; cf. ``displays.FileRowDisplay``)."""
    resolved: list[tuple[str, str]] = []
    for dec in entry.decisions:
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
    catalog_entries: Iterable[CatalogEntry], segment_by_id: Mapping[str, TargetSegment]
) -> list[FileRowDisplay]:
    """Convert catalog entries into ``FileRowDisplay`` view-models: one row per file, the file's
    (usually two) segment decisions surfaced as one ``DecisionCellDisplay`` each in
    ``decisions_display`` while ``tier_display`` still aggregates (shared tier, or per-target
    joined with ``" · "``). Shared by ``handle_files`` and ``handle_target``."""
    rows = []
    for entry in catalog_entries:
        if entry.decisions:
            pairs = _resolve_target_display(entry, segment_by_id)
            decisions_display = tuple(DecisionCellDisplay(target=t, title=ti) for t, ti in pairs)
            tier_values = {dec.tier for dec in entry.decisions}
            if len(tier_values) == 1:
                tier_display = entry.decisions[0].tier
            else:
                tier_display = " · ".join(f"{dec.target_id}: {dec.tier}" for dec in entry.decisions)
        else:
            decisions_display = ()
            tier_display = "·"
        latest = entry.latest_observation
        rows.append(
            FileRowDisplay(
                file_id=entry.file.file_id.hex(),
                short_hash=short_hash(entry.file.native_id),
                filename="" if latest is None else latest.reported_file.filename,
                sources_display=(
                    "unknown" if latest is None else str(latest.reported_file.source_count)
                ),
                decisions_display=decisions_display,
                size_display=human_size(entry.size_bytes),
                last_seen_display=(
                    "" if latest is None else short_timestamp(latest.observed_at.isoformat())
                ),
                tier_display=tier_display,
            )
        )
    return rows


def _timeline_row(observation: FileObservation) -> TimelineRowDisplay:
    """An observation as one timeline line, its instant as ``utc_iso`` writes it."""
    reported_file = observation.reported_file
    return TimelineRowDisplay(
        name=reported_file.filename,
        size_bytes=reported_file.size_bytes,
        sources=str(reported_file.source_count),
        keyword=reported_file.keyword,
        observed_at=observation.observed_at.isoformat(timespec="microseconds"),
    )


def _name_link(source_name: str | None) -> tuple[str, ...]:
    """The name page's href (D13), none without a name."""
    if source_name is None:
        return ()
    return (f"/sources/name?{urlencode({'source_name': source_name})}",)


def _source_link(source: SourceKey | None) -> tuple[str, ...]:
    """The source page's href (D13), none without a user hash."""
    return () if source is None else (f"/sources/{source.source_id.hex()}",)


def _source_history_row(period: SharingPeriod) -> SourceHistoryRowDisplay:
    """A sharing period as one line; its name links to the name page, its hash to the source
    page."""
    source_name, source = period.source_name, period.source
    return SourceHistoryRowDisplay(
        name="unknown" if source_name is None else source_name,
        name_link=_name_link(source_name),
        short_hash="unknown" if source is None else short_hash(source.native_id),
        source_link=_source_link(source),
        role=period.role,
        contact_point=period.contact_point or "unknown",
        connectable=_YES_NO[period.connectable],
        first_seen=utc_timestamp(period.first_seen_at),
        last_seen=utc_timestamp(period.last_seen_at),
        received=human_size(period.received_bytes) if period.received_bytes else "",
        rate=average_rate(period.received_bytes, period.first_seen_at, period.last_seen_at),
        node=period.node_id,
    )


def _requested_ends(request: Request) -> tuple[datetime | None, datetime | None]:
    """The interval's ends the query asks for, ``None`` where absent or malformed."""
    query_params = request.query_params
    return parse_instant(query_params.get("from")), parse_instant(query_params.get("to"))


def _interval_params(request: Request) -> dict[str, str]:
    """The request's own ``from`` and ``to``, which a page's list links keep."""
    query_params = request.query_params
    return {key: query_params[key] for key in ("from", "to") if key in query_params}


def _page_param(page: int) -> dict[str, str]:
    """The ``page`` param an interval's links keep, none on the first page."""
    return {"page": str(page)} if page > 1 else {}


def _interval_selector(
    interval: Interval, now: datetime, path: str, kept_params: dict[str, str]
) -> IntervalSelectorDisplay:
    """The selector of the page at ``path``, whose other params are ``kept_params`` (D6): the
    presets end ``now``, and Next is offered until the interval reaches it."""

    def url(shown: Interval) -> str:
        ends = {"from": utc_timestamp(shown.since), "to": utc_timestamp(shown.until)}
        return f"{path}?{urlencode({**kept_params, **ends})}"

    return IntervalSelectorDisplay(
        hidden=tuple(
            HiddenInputDisplay(name=name, value=value) for name, value in kept_params.items()
        ),
        shown=f"{utc_timestamp(interval.since)} to {utc_timestamp(interval.until)}",
        notices=(_CLAMPED_NOTICE,) if interval.clamped else (),
        presets=tuple(
            IntervalLinkDisplay(label, url(interval_ending(now, span)))
            for label, span in _INTERVAL_PRESETS
        ),
        from_value=input_timestamp(interval.since),
        to_value=input_timestamp(interval.until),
        previous_url=url(interval.shifted(-1)),
        next_urls=() if interval.until >= now else (url(interval.shifted(1)),),
    )


def _known_source_row(known_source: KnownSource) -> SourceListRowDisplay:
    """A source as one line of ``/sources``."""
    source_name = known_source.source_name
    return SourceListRowDisplay(
        name="unknown" if source_name is None else source_name,
        name_link=_name_link(source_name),
        short_hash=short_hash(known_source.source.native_id),
        source_link=_source_link(known_source.source),
        last_seen=utc_timestamp(known_source.last_seen_at),
        files=str(known_source.file_count),
    )


def _source_naming_row(source_naming: SourceNaming) -> SourceListRowDisplay:
    """A source under one of its names, as one line of a source's or a name's page."""
    return SourceListRowDisplay(
        name=source_naming.source_name,
        name_link=_name_link(source_naming.source_name),
        short_hash=short_hash(source_naming.source.native_id),
        source_link=_source_link(source_naming.source),
        last_seen=utc_timestamp(source_naming.last_seen_at),
        files=str(source_naming.file_count),
    )


def _source_file_row(period: SharingPeriod, best_filename: str | None) -> SourceFileRowDisplay:
    """A period of a source's or a name's page, with the file it was read on."""
    return SourceFileRowDisplay(
        file=best_filename or short_hash(period.file.native_id),
        file_link=f"/files/{period.file.file_id.hex()}",
        history=_source_history_row(period),
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


def _page_nav(
    page: int, has_next_page: bool, base_path: str, kept_params: dict[str, str]
) -> PageNavDisplay:
    """Precompute the prev/next links for a page (W-D8: view-model, no template logic)."""
    prev_url: str | None = None
    next_url: str | None = None
    if page > 1:
        prev = dict(kept_params)
        prev["page"] = str(page - 1)
        prev_url = f"{base_path}?{urlencode(prev)}"
    if has_next_page:
        nxt = dict(kept_params)
        nxt["page"] = str(page + 1)
        next_url = f"{base_path}?{urlencode(nxt)}"
    return PageNavDisplay(page=page, prev_url=prev_url, next_url=next_url)


def _files_summary(
    matched_count: int, total_count: int, show_unmatched: bool, kept_params: dict[str, str]
) -> FilesSummaryDisplay:
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
    return FilesSummaryDisplay(
        summary_text=summary_text, toggle_label=toggle_label, toggle_url=toggle_url
    )


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


_DEFAULT_SORT = CatalogEntrySort.LAST_SEEN
_DEFAULT_DIRECTION = SortDirection.DESC


def _normalize_sort(raw: str | None) -> CatalogEntrySort:
    """Map a raw ``sort`` param to its sort, or the default (unknown/missing -> default)."""
    return CatalogEntrySort(raw) if raw is not None and raw in CatalogEntrySort else _DEFAULT_SORT


def _normalize_direction(raw: str | None) -> SortDirection:
    """Map a raw ``direction`` param to ``asc``/``desc``, or the default when unknown or missing."""
    return SortDirection(raw) if raw is not None and raw in SortDirection else _DEFAULT_DIRECTION


def _sort_header(
    column_key: str,
    label: str,
    active_sort: str,
    active_direction: str,
    kept_params: dict[str, str],
) -> SortHeaderDisplay:
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
    if column_key != _DEFAULT_SORT:
        link_params["sort"] = column_key
    if next_direction != _DEFAULT_DIRECTION:
        link_params["direction"] = next_direction
    url = "/files?" + urlencode(link_params) if link_params else "/files"
    return SortHeaderDisplay(label=label, url=url, indicator=indicator)


def _sort_headers(
    *, active_sort: str, active_direction: str, kept_params: dict[str, str]
) -> SortHeadersDisplay:
    """Precompute all five sortable headers (W-D8)."""
    built = {
        column_key: _sort_header(column_key, label, active_sort, active_direction, kept_params)
        for column_key, label in _SORTABLE_COLUMNS
    }
    return SortHeadersDisplay(
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
) -> tuple[TierFacetDisplay, ...]:
    """Precompute the tier facet (W-D8): an "all" reset (no count) followed by one entry per tier
    present, in ``_FACET_TIER_ORDER``. ``kept_params`` are the params to preserve (the filters but
    ``tier``, plus ``sort`` and ``direction``; ``page`` already excluded); a tier entry appends
    ``tier=<t>``, the reset omits it."""
    all_url = "/files?" + urlencode(kept_params) if kept_params else "/files"
    facets = [
        TierFacetDisplay(
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
            TierFacetDisplay(
                label=_facet_label(tier),
                count_display=f"({file_count_by_tier[tier]})",
                url="/files?" + urlencode(link_params),
                selected_flag="1" if active_tier == tier else "",
            )
        )
    return tuple(facets)


def _search_bar(*, search_text: str | None, kept_params: dict[str, str]) -> SearchBarDisplay:
    """Precompute the search form (W-D8): the ``search`` prefill (empty string when none) + hidden
    inputs from ``kept_params`` (already without ``search`` and ``page``)."""
    hidden = tuple(HiddenInputDisplay(name=k, value=v) for k, v in kept_params.items())
    return SearchBarDisplay(query=search_text or "", hidden=hidden)


async def _add_security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """Defense-in-depth security headers (webui-security#3).

    The webui has no built-in auth and binds 0.0.0.0 in-container, so exposure is governed by
    the operator's compose (published port + networks) plus a reverse proxy / VPN, not by the
    bind address. Jinja2 autoescape already neutralizes XSS. CSP ``default-src 'self'`` prevents
    an injected fragment from loading an external asset (a net under autoescape).
    ``X-Content-Type-Options: nosniff`` prevents a browser from re-guessing the MIME type.
    ``Referrer-Policy: no-referrer`` avoids leaking the eD2k hash to any third-party asset
    (paranoia consistent with the project's spirit).
    """
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


def _client_lines(client_summaries: tuple[ClientSummary, ...]) -> tuple[ClientLineDisplay, ...]:
    """Each client's last reading, its values shown only while fresh (stage 2 D20)."""
    lines = []
    for client_summary in client_summaries:
        client_name, reading = client_summary.client_name, client_summary.reading
        if reading is None:
            lines.append(
                ClientLineDisplay(client_name, "No reading yet.", "unknown", "unknown", ())
            )
            continue
        read_at = short_timestamp(reading.read_at.isoformat())
        client_status = reading.status
        if not client_summary.is_fresh:
            text = f"Out of date: last reading at {read_at}."
            lines.append(ClientLineDisplay(client_name, text, "unknown", "unknown", ()))
        elif client_status is None:
            lines.append(ClientLineDisplay(client_name, f"Read at {read_at}.", "unknown", "no", ()))
        else:
            channels = tuple(
                ChannelLineDisplay(c.channel, _YES_NO[c.connected], _YES_NO[c.connectable])
                for c in client_status.channels
            )
            version = client_status.version or "unknown"
            lines.append(
                ClientLineDisplay(client_name, f"Read at {read_at}.", version, "yes", channels)
            )
    return tuple(lines)


def _stored_instant(moment: datetime | None) -> str | None:
    """An instant as local.db stores it, ``None`` kept."""
    return None if moment is None else moment.isoformat(timespec="microseconds")


def _reason_text(reason: StrEnum | None) -> str | None:
    return None if reason is None else reason.value


def _node_state_display(node_state: NodeState) -> NodeStateDisplay:
    return NodeStateDisplay(
        node_id=node_state.node_id,
        created_at=_stored_instant(node_state.created_at),
        downloads=tuple(
            TrackedDownloadDisplay(
                native_id=download.file.native_id,
                target_id=download.target_id,
                state=download.state.value,
                queued_at=download.queued_at.isoformat(timespec="microseconds"),
                completed_at=_stored_instant(download.completed_at),
                last_progress_at=_stored_instant(download.last_progress_at),
                waiting_reason=_reason_text(download.waiting_reason),
                failure_reason=_reason_text(download.failure_reason),
            )
            for download in node_state.downloads
        ),
    )


def _backoff_entries(node_state: NodeState) -> tuple[BackoffEntryDisplay, ...]:
    """Each backoff and its planned retry: its start plus its delay."""
    return tuple(
        BackoffEntryDisplay(
            client_name=backoff_key.client_name,
            channel="whole client" if backoff_key.channel is None else backoff_key.channel,
            attempts=backoff_state.attempts,
            retry_at_display=(backoff_state.started_at + backoff_state.delay).isoformat(
                timespec="microseconds"
            ),
        )
        for backoff_key, backoff_state in node_state.backoff_state_by_key.items()
    )


# SQL console (spec §11). The two selectable databases, in display order: value (allowlist key)
# + human label. Neither holds a peer's address (a source is a pseudonymous id at most), so
# read-only exposure of either is fine.
_CONSOLE_DBS: tuple[tuple[ConsoleDatabase, str], ...] = (
    (ConsoleDatabase.CATALOG, "catalog.db"),
    (ConsoleDatabase.LOCAL, "local.db"),
)
_CONSOLE_UNKNOWN_DB = "Unknown database. Choose catalog.db or local.db."


def _console_db_options(selected: str) -> tuple[DbOptionDisplay, ...]:
    """Precompute the DB picker options, marking ``selected`` (W-D8: no template logic). An
    unknown ``selected`` (e.g. a bogus form value echoed back) marks none."""
    return tuple(
        DbOptionDisplay(
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


def _console_database(db_key: str) -> ConsoleDatabase | None:
    """The database the form names, ``None`` when it names none."""
    return ConsoleDatabase(db_key) if db_key in ConsoleDatabase else None


def _to_query_answer_display(query_answer: QueryAnswer, row_cap: int) -> QueryAnswerDisplay:
    """Build the console result view-model from a query's answer. ``truncated`` becomes a 0-or-1
    message tuple for the logic-free banner."""
    truncated = (
        (f"Results truncated to the first {row_cap:,} rows.",) if query_answer.truncated else ()
    )
    return QueryAnswerDisplay(
        columns=query_answer.columns,
        rows=tuple(QueryRowDisplay(cells=cells) for cells in query_answer.rows),
        row_count=len(query_answer.rows),
        elapsed_ms=round(query_answer.elapsed / timedelta(milliseconds=1)),
        truncated=truncated,
    )


def build_app(
    *,
    target_segments: tuple[TargetSegment, ...],
    templates_dir: Path,
    static_dir: Path,
    crawl_pauser: CrawlPauser,
    crawl_resumer: CrawlResumer,
    shutdown_requester: ShutdownRequester,
    crawl_summarizer: CrawlSummarizer,
    node_describer: NodeDescriber,
    file_lister: FileLister,
    file_describer: FileDescriber,
    source_lister: SourceLister,
    source_describer: SourceDescriber,
    source_name_describer: SourceNameDescriber,
    console_query_runner: ConsoleQueryRunner,
    amule_url: str,
) -> Starlette:
    """Build and return the wired Starlette application.

    ``target_segments`` arrive ALREADY PARSED from the caller, for their titles.

    Each control POST calls its use case, which returns at once; the webui itself holds no write
    connection (spec §4/§10). ``crawl_summarizer`` serves the dashboard, ``node_describer`` /node,
    ``file_lister`` /files and a target's page, ``file_describer`` a file's page, ``source_lister``
    /sources, ``source_describer`` a source's page, ``source_name_describer`` a name's page,
    ``console_query_runner`` the console.

    ``amule_url`` is the base the nav's aMule entry points at (design §9); the caller reads it
    from ``webui.amule_url``."""

    # No type checker reads templates: a name missing from the context raises, never prints "".
    templates = Jinja2Templates(
        env=Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(),
            undefined=StrictUndefined,
        ),
        context_processors=[_make_nav_context(amule_url)],
    )

    # Full segment by target_id (Task 3: seasonal locator + title resolution on /files)
    _segment_by_id = {seg.target_id: seg for seg in target_segments}

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def handle_health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def handle_dashboard(request: Request) -> Response:
        summary = crawl_summarizer.summarize_crawl()

        coverage_rows = [
            TargetCoverageDisplay(
                target_id=coverage.target_id,
                title=_segment_by_id[coverage.target_id].title,
                status=coverage.status,
                best_tier_display=coverage.best_tier if coverage.best_tier is not None else "·",
                file_count=coverage.file_count,
            )
            for coverage in summary.target_coverages
        ]

        done = request.query_params.get("done")
        message = _CONTROL_MESSAGES.get(done) if done is not None else None
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "coverage_rows": coverage_rows,
                "node_state": _node_state_display(summary.node_state),
                "clients": _client_lines(summary.client_summaries),
                "crawl_state": "paused" if summary.is_paused else "running",
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

        file_listing = file_lister.list_files(
            target_id=target_id_param,
            tier=tier_param,
            search_text=search_text,
            matched_only=not show_unmatched,
            sort=sort_param,
            direction=direction_param,
            page=page,
        )

        display_rows = _to_display_rows(file_listing.catalog_entries, _segment_by_id)
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
        if sort_param != _DEFAULT_SORT:
            sort_params["sort"] = sort_param
        if direction_param != _DEFAULT_DIRECTION:
            sort_params["direction"] = direction_param

        sort_headers = _sort_headers(
            active_sort=sort_param, active_direction=direction_param, kept_params=filter_params
        )

        # summary toggle preserves sort and direction (not show_unmatched, which it manages itself)
        summary_kept_params = {k: v for k, v in filter_params.items() if k != "show_unmatched"}
        summary_kept_params.update(sort_params)
        summary = _files_summary(
            file_listing.matched_file_count,
            file_listing.total_file_count,
            show_unmatched,
            summary_kept_params,
        )

        # Tier facet (facet-lite: never filtered by its own tier) + filename search form. The
        # facet links carry every active param except ``tier`` and ``page`` (selecting a tier
        # replaces it, resets page); the search hidden inputs carry every active param except
        # ``search`` and ``page`` (submitting a search preserves the rest, resets page).
        facet_kept_params = {k: v for k, v in filter_params.items() if k != "tier"}
        facet_kept_params.update(sort_params)
        facets = _tier_facets(
            file_count_by_tier=file_listing.file_count_by_tier,
            active_tier=tier_param,
            kept_params=facet_kept_params,
        )

        search_kept_params = {k: v for k, v in filter_params.items() if k != "search"}
        search_kept_params.update(sort_params)
        searchbar = _search_bar(search_text=search_text, kept_params=search_kept_params)

        filter_bar = FilterBarDisplay(searchbar=searchbar, facets=facets)

        nav = _page_nav(
            page, file_listing.has_next_page, "/files", {**filter_params, **sort_params}
        )
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
        source_listing = source_lister.list_sources(search_text=search_text, page=page)
        count = source_listing.source_count
        kept_params = {} if search_text is None else {"search": search_text}
        return templates.TemplateResponse(
            request,
            "sources.html",
            {
                "rows": tuple(map(_known_source_row, source_listing.known_sources)),
                "nav": _page_nav(page, source_listing.has_next_page, "/sources", kept_params),
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
        requested_since, requested_until = _requested_ends(request)
        description = (
            source_describer.describe_source(
                bytes.fromhex(source_id_hex),
                page=page,
                requested_since=requested_since,
                requested_until=requested_until,
            )
            if _HEX_ID.fullmatch(source_id_hex)
            else None
        )
        if description is None:
            return templates.TemplateResponse(request, "404.html", {}, status_code=404)
        source_history, path = description.source_history, f"/sources/{source_id_hex}"
        best_filename_by_file = source_history.best_filename_by_file
        return templates.TemplateResponse(
            request,
            "source_detail.html",
            {
                "source": SourceKeyDisplay(
                    str(source_history.source.network), source_history.source.native_id
                ),
                "names": tuple(map(_source_naming_row, source_history.source_namings)),
                "periods": tuple(
                    _source_file_row(period, best_filename_by_file.get(period.file))
                    for period in source_history.sharing_periods
                ),
                "nav": _page_nav(page, description.has_next_page, path, _interval_params(request)),
                "interval": _interval_selector(
                    description.interval, description.now, path, _page_param(page)
                ),
            },
        )

    async def handle_source_name(request: Request) -> Response:
        source_name = request.query_params.get("source_name")
        page = _page_number(request.query_params.get("page"))
        requested_since, requested_until = _requested_ends(request)
        description = (
            None
            if source_name is None
            else source_name_describer.describe_source_name(
                source_name,
                page=page,
                requested_since=requested_since,
                requested_until=requested_until,
            )
        )
        if description is None:
            return templates.TemplateResponse(request, "404.html", {}, status_code=404)
        source_name_history = description.source_name_history
        best_filename_by_file = source_name_history.best_filename_by_file
        path = "/sources/name"
        source_name_params = {"source_name": source_name_history.source_name}
        return templates.TemplateResponse(
            request,
            "source_name.html",
            {
                "source_name": source_name_history.source_name,
                "sources": tuple(map(_source_naming_row, source_name_history.source_namings)),
                "periods": tuple(
                    _source_file_row(period, best_filename_by_file.get(period.file))
                    for period in source_name_history.sharing_periods
                ),
                "nav": _page_nav(
                    page,
                    description.has_next_page,
                    path,
                    {**source_name_params, **_interval_params(request)},
                ),
                "interval": _interval_selector(
                    description.interval,
                    description.now,
                    path,
                    {**source_name_params, **_page_param(page)},
                ),
            },
        )

    async def handle_file_detail(request: Request) -> Response:
        file_id_hex: str = request.path_params["file_id"]

        requested_since, requested_until = _requested_ends(request)
        description = (
            file_describer.describe_file(
                bytes.fromhex(file_id_hex),
                requested_since=requested_since,
                requested_until=requested_until,
            )
            if _HEX_ID.fullmatch(file_id_hex)
            else None
        )

        if description is None:
            return templates.TemplateResponse(request, "404.html", {}, status_code=404)
        detail, explanation = description.file_history, description.explanation

        latest = (
            None if detail.latest_observation is None else detail.latest_observation.reported_file
        )
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
        explanation_coverage_values: tuple[TokenCoverageDisplay, ...] = ()
        explanation_vetoes_fired: tuple[str, ...] = ()
        explanation_notes: tuple[str, ...] = ()

        if explanation is not None:
            explanation_target_id = explanation.target_id
            explanation_rules_fired = explanation.rules_fired
            explanation_tokens_matched = explanation.tokens_matched
            explanation_coverage_values = tuple(
                TokenCoverageDisplay(token_name=token_name, value_display=f"{coverage:.2f}")
                for token_name, coverage in explanation.coverage_values
            )
            explanation_vetoes_fired = explanation.vetoes_fired
            explanation_notes = ("Evaluated against the current configuration",)

        display = FileDetailDisplay(
            network=detail.file.network,
            native_id=detail.file.native_id,
            size_bytes=detail.size_bytes,
            timeline=tuple(_timeline_row(observation) for observation in detail.observations),
            source_history=tuple(map(_source_history_row, description.sharing_periods)),
            decisions=tuple(
                DecisionDisplay(
                    target_id=dated.decision.target_id,
                    rule_name=dated.decision.rule_name,
                    tier=dated.decision.tier,
                    decided_at=dated.decided_at.isoformat(timespec="microseconds"),
                )
                for dated in detail.decisions
            ),
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
                "interval": _interval_selector(
                    description.interval, description.now, f"/files/{file_id_hex}", {}
                ),
            },
        )

    async def handle_target(request: Request) -> Response:
        target_id: str = request.path_params["target_id"]
        file_listing = file_lister.list_files(
            target_id=target_id,
            tier=None,
            search_text=None,
            matched_only=False,
            sort=_DEFAULT_SORT,
            direction=_DEFAULT_DIRECTION,
            page=1,
        )

        display_rows = _to_display_rows(file_listing.catalog_entries, _segment_by_id)
        # No pagination here (target view: we expect few). Empty nav.
        nav = PageNavDisplay(page=1, prev_url=None, next_url=None)
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
        node_state = node_describer.describe_node().node_state
        return templates.TemplateResponse(
            request,
            "node.html",
            {
                "node_state": _node_state_display(node_state),
                "backoff_entries": _backoff_entries(node_state),
            },
        )

    # ------------------------------------------------------------------
    # Runtime controls (phase P6a): each POST calls its use case, then redirects
    # (PRG) to ``/?done=<code>``, where the dashboard shows a 0-or-1 message banner.
    # NO CSRF token: consistent with the no-auth, network-trust-boundary posture (spec §12).
    # ------------------------------------------------------------------

    async def handle_pause(request: Request) -> Response:
        crawl_pauser.pause_crawl()
        return RedirectResponse("/?done=paused", status_code=303)

    async def handle_resume(request: Request) -> Response:
        crawl_resumer.resume_crawl()
        return RedirectResponse("/?done=resumed", status_code=303)

    async def handle_restart(request: Request) -> Response:
        shutdown_requester.request_shutdown()
        return RedirectResponse("/?done=restarted", status_code=303)

    # ------------------------------------------------------------------
    # SQL console (spec §11): a read-only power-user console over either DB.
    # A query runs OFF the event loop via ``run_in_threadpool`` so a slow query (up to its time
    # limit) blocks neither the crawler thread nor the webui loop, only its pool slot.
    # NO CSRF token: consistent with the no-auth, network-trust-boundary posture (spec §12).
    # ------------------------------------------------------------------

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
        database = _console_database(db_key)
        if database is None:
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
        outcome = await run_in_threadpool(console_query_runner.run_console_query, database, sql)
        query_answer = outcome.query_answer
        if isinstance(query_answer, QueryFailure):
            return templates.TemplateResponse(
                request,
                "console.html",
                {
                    "sql": sql,
                    "db_options": db_options,
                    "results": (),
                    "errors": (query_answer.message,),
                },
            )
        return templates.TemplateResponse(
            request,
            "console.html",
            {
                "sql": sql,
                "db_options": db_options,
                "results": (_to_query_answer_display(query_answer, outcome.row_cap),),
                "errors": (),
            },
        )

    async def handle_console_csv(request: Request) -> Response:
        sql, db_key = await _read_console_form(request)
        database = _console_database(db_key)
        if database is None:
            return Response(_CONSOLE_UNKNOWN_DB, status_code=400, media_type="text/plain")
        outcome = await run_in_threadpool(console_query_runner.run_console_query, database, sql)
        query_answer = outcome.query_answer
        if isinstance(query_answer, QueryFailure):
            return Response(query_answer.message, status_code=400, media_type="text/plain")
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(query_answer.columns)
        writer.writerows(query_answer.rows)
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
        middleware=[Middleware(BaseHTTPMiddleware, dispatch=_add_security_headers)],
    )
