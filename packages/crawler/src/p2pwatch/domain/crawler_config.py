"""UNIFIED crawler config (``crawler.yml``, versioned, deploy-simplification design).

Merges the former POLICY config (cadences, polling budgets, jitter, backoff, shutdown
deadline) and the former LOCAL config (secrets + DB paths + download wiring). Parsed from the
dict the config adapter's ``load_yaml`` returns into FROZEN dataclasses, with FAIL-FAST
validation: a bound that does not hold or a missing field is an ``InvalidConfigError`` and the
crawler refuses to start.

The adapter's ``load_config`` resolves ``${NAME}`` in every string value before the parse, which
never sees the environment. The ``download`` section is present ⟺ enabled (``enabled: true``, D5):
``enabled`` absent/``false`` ⇒ section ``None`` (we don't descend into the rest); ``enabled:
true`` ⇒ all wiring fields required.
"""

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from catalog_matching.domain.config import MatcherConfig
from catalog_matching.domain.models import TargetSegment
from p2pwatch.domain.config_defaults import (
    DEFAULT_AMULE_URL,
    DEFAULT_DOWNLOAD_ENABLED,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOST_AFTER,
    DEFAULT_MIN_FREE_BYTES,
    DEFAULT_NODE_PREFIX,
    DEFAULT_NOTIFICATION_TIMEOUT_SECONDS,
    DEFAULT_OUTPUT_DIRECTORY,
    DEFAULT_REAPPEARED_AFTER,
    DEFAULT_SOURCE_PERIOD_GAP,
    DEFAULT_SOURCES_INTERVAL,
)
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.observability.policy import Audience


@dataclass(kw_only=True, frozen=True)
class BackoffConfig:
    """Exponential backoff + jitter per (client, channel) (spec §3/§5).

    ``jitter_ratio``: fraction of the nominal delay drawn as additional jitter
    (anti-thundering-herd): 0 = no jitter, 0.3 = up to +30%.
    """

    base_seconds: float
    cap_seconds: float
    factor: float
    jitter_ratio: float


@dataclass(kw_only=True, frozen=True)
class SearchConfig:
    """The ``search`` section: the keywords every search queries, and the backoff of a failure."""

    keywords: tuple[str, ...]
    backoff: BackoffConfig


@dataclass(kw_only=True, frozen=True)
class NotificationTarget:
    """An apprise target (secret via ``${...}``), notified for one ``audience`` (E-D7).
    ``node_prefix: false`` drops the ``[node-id]`` prefix, for a service with its own identity."""

    url: str
    audience: Audience
    node_prefix: bool


@dataclass(kw_only=True, frozen=True)
class DownloadConfig:
    """Download policy and wiring, present ⟺ ``enabled``. ``output_directory`` is measured with
    ``statvfs`` and never opened: amuled writes the finished file, nothing here touches it."""

    poll_interval_seconds: float
    min_free_bytes: int
    lost_after: timedelta
    output_directory: str
    reappeared_after: timedelta
    sources_interval: timedelta

    @property
    def time_between_source_reads(self) -> timedelta:
        """The time between reads the carried role's max age assumes: the interval plus a poll
        (source points spec, D3), since the step runs on the first round past its interval."""
        return self.sources_interval + timedelta(seconds=self.poll_interval_seconds)


@dataclass(kw_only=True, frozen=True)
class WebuiConfig:
    """In-process read-only webui HTTP surface (monolith-consolidation spec §8), always served.

    The section is OPTIONAL. The uvicorn bind is FIXED at ``0.0.0.0:8080`` in the composition
    ring, not configurable here; exposure is governed by the operator's Docker compose
    (published port + networks), not by an app-level bind address.

    ``amule_url`` is where the nav's aMule link points. The two containers each publish a web
    surface and p2pwatch cannot know how its own is reached, so this is a plain configurable
    base: the default is the no-proxy case, and an operator behind a reverse proxy overrides it.

    ``source_period_gap`` is the longest gap within a displayed source period (source points
    spec, D6): a reading option, so a crawl-only node viewing a merged catalog has one too.
    """

    amule_url: str
    source_period_gap: timedelta


_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

# Keys no longer read, by dotted path: refused, so an operator never believes they still apply.
_REMOVED_KEYS = (
    "cycle_interval_seconds",
    "decision_poll_interval_seconds",
    "keyword_pause_max_seconds",
    "keyword_pause_min_seconds",
    "node_id",
    "observability.metrics",
    "port_sync",
    "search_poll_budget_seconds",
    "search_poll_interval_seconds",
    "webui.enabled",
)

# Keys read elsewhere now: refused with their new place, so an operator never edits a dead one.
_MOVED_KEYS = {"backoff": "search.backoff"}


@dataclass(kw_only=True, frozen=True)
class ObservabilityConfig:
    """Observability settings (``crawler.yml``). ``log_level`` drives the global logging
    (bootstrap → setLevel); ``notifications`` = apprise targets (interpolated URLs, E-D2/E-D7)."""

    log_level: str
    notification_timeout_seconds: float
    notifications: tuple[NotificationTarget, ...]


@dataclass(kw_only=True, frozen=True)
class CrawlerConfig:
    """Unified crawler config (policy + wiring). All durations in SECONDS.

    Policy: ``search`` (keywords and backoff), ``shutdown_deadline_seconds`` (hard bound of the
    clean shutdown).

    Wiring (ex-local): ``amule_api_password`` (the daemon's amuleapi admin password, the same
    one the aMule web UI takes; host/port are code
    constants), DB paths, ``observability``,
    ``download`` (``None`` ⟺ download off, crawl-only).
    """

    search: SearchConfig
    shutdown_deadline_seconds: float
    amule_api_password: str
    catalog_db_path: str
    local_db_path: str
    observability: ObservabilityConfig
    download: DownloadConfig | None
    webui: WebuiConfig


def _require_mapping(node: Any, *, key_path: str) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise InvalidConfigError(key_path, message=f"mapping expected, got {type(node).__name__}")
    return node


# The root's error label: crawler.yml has no section around its root keys, so they print bare.
_ROOT = ""


def _key_path(error_label: str, *, key: str) -> str:
    return f"{error_label}.{key}" if error_label else key


def _required(section: dict[str, Any], *, key: str, error_label: str) -> Any:
    if key in section:
        return section[key]
    raise InvalidConfigError(_key_path(error_label, key=key), message="missing")


def _number(section: dict[str, Any], *, key: str, error_label: str) -> float:
    setting = _required(section, key=key, error_label=error_label)
    if not isinstance(setting, int | float) or isinstance(setting, bool):
        raise InvalidConfigError(
            _key_path(error_label, key=key), message=f"number expected, got {setting!r}"
        )
    if not math.isfinite(setting):  # .inf makes a sleep endless, .nan passes every comparison
        raise InvalidConfigError(
            _key_path(error_label, key=key), message=f"finite number expected, got {setting!r}"
        )
    return float(setting)


def _positive(section: dict[str, Any], *, key: str, error_label: str) -> float:
    number = _number(section, key=key, error_label=error_label)
    if number <= 0:
        raise InvalidConfigError(
            _key_path(error_label, key=key), message=f"strictly positive expected, got {number}"
        )
    return number


def _non_negative(section: dict[str, Any], *, key: str, error_label: str) -> float:
    number = _number(section, key=key, error_label=error_label)
    if number < 0:
        raise InvalidConfigError(
            _key_path(error_label, key=key), message=f"≥ 0 expected, got {number}"
        )
    return number


def _positive_int(section: dict[str, Any], *, key: str, error_label: str) -> int:
    """Strictly positive integer (bool refused), else ``InvalidConfigError`` (fail-fast §5/§14)."""
    setting = _required(section, key=key, error_label=error_label)
    if not isinstance(setting, int) or isinstance(setting, bool) or setting <= 0:
        raise InvalidConfigError(
            _key_path(error_label, key=key),
            message=f"strictly positive integer expected, got {setting!r}",
        )
    return setting


# Coherent bounds for a P2P watch: a day for a delay, 30 days for an absence (operator, 2026-10-13).
_A_DAY_SECONDS = 86_400.0
_THIRTY_DAYS_SECONDS = 2_592_000.0


def _seconds(
    section: dict[str, Any],
    *,
    key: str,
    error_label: str,
    default: float | None = None,
    at_most: float = _A_DAY_SECONDS,
) -> float:
    """Strictly positive seconds up to ``at_most``; OPTIONAL when given a ``default``."""
    if default is not None and key not in section:
        return default
    seconds = _positive(section, key=key, error_label=error_label)
    if seconds > at_most:
        raise InvalidConfigError(
            _key_path(error_label, key=key),
            message=f"at most {at_most:.0f} seconds expected, got {seconds}",
        )
    return seconds


def _positive_int_default(
    section: dict[str, Any], *, key: str, error_label: str, default: int
) -> int:
    """OPTIONAL strictly positive integer (default ``default``)."""
    if key not in section:
        return default
    return _positive_int(section, key=key, error_label=error_label)


def _bool_default(section: dict[str, Any], *, key: str, error_label: str, default: bool) -> bool:
    """OPTIONAL boolean (default ``default``); refuses a non-bool, fail-fast (§5/§14)."""
    if key not in section:
        return default
    setting = section[key]
    if not isinstance(setting, bool):
        raise InvalidConfigError(
            _key_path(error_label, key=key), message=f"boolean expected, got {setting!r}"
        )
    return setting


def _string(section: dict[str, Any], *, key: str, error_label: str) -> str:
    """REQUIRED non-empty string, else ``InvalidConfigError`` (fail-fast §5/§14)."""
    setting = _required(section, key=key, error_label=error_label)
    if not isinstance(setting, str) or not setting:
        raise InvalidConfigError(
            _key_path(error_label, key=key), message=f"non-empty string expected, got {setting!r}"
        )
    return setting


def _parse_observability(section: dict[str, Any]) -> ObservabilityConfig:
    log_level = section.get("log_level", DEFAULT_LOG_LEVEL)
    if not isinstance(log_level, str) or log_level not in _LOG_LEVELS:
        raise InvalidConfigError(
            "observability.log_level",
            message=f"one of {sorted(_LOG_LEVELS)} expected, got {log_level!r}",
        )
    timeout = _seconds(
        section,
        key="notification_timeout_seconds",
        error_label="observability",
        default=DEFAULT_NOTIFICATION_TIMEOUT_SECONDS,
    )
    notifications: list[NotificationTarget] = []
    for index, notification_node in enumerate(section.get("notifications", [])):
        error_label = f"observability.notifications[{index}]"
        notification = _require_mapping(notification_node, key_path=error_label)
        if "tag" in notification:  # the 4.x name, refused like _MOVED_KEYS
            raise InvalidConfigError(
                error_label, message="key 'tag' was renamed 'audience', rename it in crawler.yml"
            )
        audience_raw = _string(notification, key="audience", error_label=error_label)
        try:
            audience = Audience(audience_raw)
        except ValueError as error:
            raise InvalidConfigError(
                f"{error_label}.audience",
                message=f"'community' or 'operations' expected, got {audience_raw!r}",
            ) from error
        notifications.append(
            NotificationTarget(
                url=_string(notification, key="url", error_label=error_label),
                audience=audience,
                node_prefix=_bool_default(
                    notification,
                    key="node_prefix",
                    error_label=error_label,
                    default=DEFAULT_NODE_PREFIX,
                ),
            )
        )
    return ObservabilityConfig(
        log_level=log_level,
        notification_timeout_seconds=timeout,
        notifications=tuple(notifications),
    )


def _parse_download(document: dict[str, Any]) -> DownloadConfig | None:
    section = _require_mapping(document.get("download", {}), key_path="download")
    if not _bool_default(
        section, key="enabled", error_label="download", default=DEFAULT_DOWNLOAD_ENABLED
    ):
        return None  # laziness: we read NOTHING else (no wiring required)
    output_directory = section.get("output_dir", DEFAULT_OUTPUT_DIRECTORY)
    if not isinstance(output_directory, str) or not output_directory:
        raise InvalidConfigError(
            "download.output_dir", message=f"non-empty string expected, got {output_directory!r}"
        )
    return DownloadConfig(
        poll_interval_seconds=_seconds(
            section, key="poll_interval_seconds", error_label="download"
        ),
        min_free_bytes=_positive_int_default(
            section, key="min_free_bytes", error_label="download", default=DEFAULT_MIN_FREE_BYTES
        ),
        lost_after=timedelta(
            seconds=_seconds(
                section,
                key="lost_after_seconds",
                error_label="download",
                default=DEFAULT_LOST_AFTER.total_seconds(),
                at_most=_THIRTY_DAYS_SECONDS,
            )
        ),
        output_directory=output_directory,
        reappeared_after=timedelta(
            seconds=_seconds(
                section,
                key="reappeared_after_seconds",
                error_label="download",
                default=DEFAULT_REAPPEARED_AFTER.total_seconds(),
                at_most=_THIRTY_DAYS_SECONDS,
            )
        ),
        sources_interval=timedelta(
            seconds=_seconds(
                section,
                key="sources_interval_seconds",
                error_label="download",
                default=DEFAULT_SOURCES_INTERVAL.total_seconds(),
            )
        ),
    )


def _parse_search(document: dict[str, Any]) -> SearchConfig:
    """`search` section, required: its non-empty keywords and its backoff."""
    section = _require_mapping(document.get("search", {}), key_path="search")
    keywords = _required(section, key="keywords", error_label="search")
    if not isinstance(keywords, list) or not keywords:
        raise InvalidConfigError("search.keywords", message="non-empty list of strings expected")
    parsed_keywords: list[str] = []
    for keyword in keywords:
        if not isinstance(keyword, str) or not keyword:
            raise InvalidConfigError(
                "search.keywords", message=f"non-empty string expected, got {keyword!r}"
            )
        parsed_keywords.append(keyword)
    return SearchConfig(keywords=tuple(parsed_keywords), backoff=_parse_backoff(section))


def _parse_backoff(search: dict[str, Any]) -> BackoffConfig:
    """`search.backoff`, required: a factor that grows, a cap at least the base."""
    section = _require_mapping(search.get("backoff", {}), key_path="search.backoff")
    factor = _positive(section, key="factor", error_label="search.backoff")
    if factor < 1:
        raise InvalidConfigError(
            "search.backoff.factor", message=f"must be ≥ 1 (growth), got {factor}"
        )
    backoff = BackoffConfig(
        base_seconds=_seconds(section, key="base_seconds", error_label="search.backoff"),
        cap_seconds=_seconds(section, key="cap_seconds", error_label="search.backoff"),
        factor=factor,
        jitter_ratio=_non_negative(section, key="jitter_ratio", error_label="search.backoff"),
    )
    if backoff.cap_seconds < backoff.base_seconds:
        raise InvalidConfigError(
            "search.backoff.cap_seconds",
            message=f"{backoff.cap_seconds} < base_seconds ({backoff.base_seconds}): "
            "cap below floor",
        )
    return backoff


def _parse_webui(document: dict[str, Any]) -> WebuiConfig:
    """`webui` section (optional): an absent section or key takes the domain's default.

    The bind is FIXED at 0.0.0.0:8080 in the composition ring, so this reads no host/port: an
    unknown key (a legacy ``host``/``port``) is ignored silently, no fail-fast."""
    section = _require_mapping(document.get("webui", {}), key_path="webui")
    gap = timedelta(
        seconds=_seconds(
            section,
            key="source_period_gap_seconds",
            error_label="webui",
            default=DEFAULT_SOURCE_PERIOD_GAP.total_seconds(),
        )
    )
    amule_url = (
        _string(section, key="amule_url", error_label="webui")
        if "amule_url" in section
        else DEFAULT_AMULE_URL
    )
    return WebuiConfig(amule_url=amule_url, source_period_gap=gap)


def _holds_key_path(document: dict[str, Any], *, key_path: str) -> bool:
    """Whether ``document`` holds the dotted ``key_path``, each section on the way a mapping."""
    node: Any = document
    for key in key_path.split("."):
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    return True


def parse_crawler_config(document: dict[str, Any]) -> CrawlerConfig:
    """Builds a validated ``CrawlerConfig`` from the parsed YAML dict, its ``${NAME}`` already
    resolved. Fail-fast §5/§14: any inconsistency → ``InvalidConfigError``."""
    for key_path in _REMOVED_KEYS:
        if _holds_key_path(document, key_path=key_path):
            raise InvalidConfigError(key_path, message="was removed, delete it from crawler.yml")
    for key, new_path in _MOVED_KEYS.items():
        if key in document:
            raise InvalidConfigError(key, message=f"moved to '{new_path}', move it in crawler.yml")
    observability = _parse_observability(
        _require_mapping(document.get("observability", {}), key_path="observability")
    )
    return CrawlerConfig(
        search=_parse_search(document),
        shutdown_deadline_seconds=_seconds(
            document, key="shutdown_deadline_seconds", error_label=_ROOT
        ),
        amule_api_password=_string(document, key="amule_api_password", error_label=_ROOT),
        catalog_db_path=_string(document, key="catalog_db_path", error_label=_ROOT),
        local_db_path=_string(document, key="local_db_path", error_label=_ROOT),
        observability=observability,
        download=_parse_download(document),
        webui=_parse_webui(document),
    )


@dataclass(kw_only=True, frozen=True)
class LoadedConfig:
    """The three config files, parsed, and the fingerprint of the two that make the policy."""

    crawler_config: CrawlerConfig
    targets: tuple[TargetSegment, ...]
    matcher_config: MatcherConfig
    policy_fingerprint: str
