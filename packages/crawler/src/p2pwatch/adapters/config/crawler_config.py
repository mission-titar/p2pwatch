"""UNIFIED crawler config (``crawler.yml``, versioned — deploy-simplification design).

Merges the former POLICY config (cadences, polling budgets, jitter, backoff, shutdown
deadline) and the former LOCAL config (secrets + DB paths + download wiring). Parsed
from the dict ``load_yaml`` returns into FROZEN dataclasses, with FAIL-FAST validation: a bound
that does not hold or a missing field is a ``ConfigError`` and the crawler refuses to start.

Deployment-sensitive values (secrets, URLs) are interpolated from the environment via
``${NAME}`` (substring, LAZY: a disabled section requires no variable, D1). The
``download`` section is present ⟺ enabled (``enabled: true``, D5):
``enabled`` absent/``false`` ⇒ section ``None`` (we don't descend into the rest); ``enabled:
true`` ⇒ all wiring fields required.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from p2pwatch.adapters.config.errors import ConfigError as ConfigError  # explicit re-export
from p2pwatch.adapters.config.interpolation import interpolate
from p2pwatch.domain.observability.policy import Audience


@dataclass(frozen=True)
class BackoffConfig:
    """Exponential backoff + jitter per (client, channel) (spec §3/§5).

    ``jitter_ratio``: fraction of the nominal delay drawn as additional jitter
    (anti-thundering-herd): 0 = no jitter, 0.3 = up to +30%.
    """

    base_seconds: float
    cap_seconds: float
    factor: float
    jitter_ratio: float


@dataclass(frozen=True)
class SearchConfig:
    """The ``search`` section: the keywords every search queries, and the backoff of a failure."""

    keywords: tuple[str, ...]
    backoff: BackoffConfig


@dataclass(frozen=True)
class AmuleEndpoint:
    """An ``amuled`` daemon reachable through ``amuleapi``. ``client_name`` is the client's label
    (logging, backoff/scheduler_state key)."""

    client_name: str
    host: str
    port: int
    password: str


# aMule's service in the direct variant, a network alias of its VPN sidecar in the vpn one.
AMULE_API_HOST = "ed2k"
AMULE_API_PORT = 4711
AMULE_CLIENT_NAME = "amuled"


@dataclass(frozen=True)
class NotificationTarget:
    """An apprise target (secret via ``${...}``). ``tag`` = the consuming audience (E-D7).
    ``node_prefix: false`` drops the ``[node-id]`` prefix, for a service with its own identity."""

    url: str
    tag: Audience
    node_prefix: bool = True


@dataclass(frozen=True)
class DownloadConfig:
    """Download policy and wiring, present ⟺ ``enabled``. ``output_dir`` is measured with
    ``statvfs`` and never opened: amuled writes the finished file, nothing here touches it."""

    poll_interval_seconds: float
    min_free_bytes: int
    lost_after_seconds: float
    output_dir: str
    reappeared_after: timedelta
    sources_interval: timedelta


# 3 x (300 + 30): the writer's tolerance at the shipped intervals (source points spec, D6).
_DEFAULT_SOURCE_PERIOD_GAP = timedelta(seconds=990)


@dataclass(frozen=True)
class WebuiConfig:
    """In-process read-only webui HTTP surface (monolith-consolidation spec §8).

    ``enabled`` gates the WHOLE HTTP surface (``false`` ⇒ headless crawler, no port). The section
    is OPTIONAL (absent ⇒ enabled). The uvicorn bind is FIXED at ``0.0.0.0:8080`` in the
    composition layer, not configurable here; exposure is governed by the operator's Docker
    compose (published port + networks), not by an app-level bind address.

    ``amule_url`` is where the nav's aMule link points. The two containers each publish a web
    surface and p2pwatch cannot know how its own is reached, so this is a plain configurable
    base: the default is the no-proxy case, and an operator behind a reverse proxy overrides it.

    ``source_period_gap`` is the longest gap within a displayed source period (source points
    spec, D6): a reading option, so a crawl-only node viewing a merged catalog has one too.
    """

    enabled: bool
    amule_url: str = "http://localhost:4711"
    source_period_gap: timedelta = _DEFAULT_SOURCE_PERIOD_GAP


_DEFAULT_WEBUI = WebuiConfig(enabled=True)

_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

# Keys no longer read: refused, so an operator never believes they still apply.
_REMOVED_KEYS = (
    "cycle_interval_seconds",
    "decision_poll_interval_seconds",
    "keyword_pause_max_seconds",
    "keyword_pause_min_seconds",
    "port_sync",
    "search_poll_budget_seconds",
    "search_poll_interval_seconds",
)

# Keys read elsewhere now: refused with their new place, so an operator never edits a dead one.
_MOVED_KEYS = {"backoff": "search.backoff"}


@dataclass(frozen=True)
class MetricsConfig:
    """Crawler's Prometheus metrics server (E-D9). ``port`` = dedicated HTTP server."""

    enabled: bool
    port: int


@dataclass(frozen=True)
class ObservabilityConfig:
    """Observability settings (``crawler.yml``). ``log_level`` drives the global logging
    (bootstrap → setLevel); ``notifications`` = apprise targets (interpolated URLs, E-D2/E-D7)."""

    log_level: str
    metrics: MetricsConfig | None
    notification_timeout_seconds: float
    notifications: tuple[NotificationTarget, ...]


@dataclass(frozen=True)
class CrawlerConfig:
    """Unified crawler config (policy + wiring). All durations in SECONDS.

    Policy: ``search`` (keywords and backoff), ``shutdown_deadline_seconds`` (hard bound of the
    clean shutdown).

    Wiring (ex-local): ``amule_api_password`` (the daemon's amuleapi admin password, the same
    one the aMule web UI takes; host/port are code
    constants), DB paths, ``node_id`` (``None`` = the one from ``local.db``), ``observability``,
    ``download`` (``None`` ⟺ observer mode).
    """

    search: SearchConfig
    shutdown_deadline_seconds: float
    amule_api_password: str
    catalog_db_path: str
    local_db_path: str
    node_id: str | None
    observability: ObservabilityConfig | None = None
    download: DownloadConfig | None = None
    webui: WebuiConfig = _DEFAULT_WEBUI

    @property
    def amule_endpoint(self) -> AmuleEndpoint:
        """The single daemon's amuleapi endpoint: code constants + the configured password.

        ONE derivation point for both sessions (search, download).
        """
        return AmuleEndpoint(
            client_name=AMULE_CLIENT_NAME,
            host=AMULE_API_HOST,
            port=AMULE_API_PORT,
            password=self.amule_api_password,
        )


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{label}: mapping expected, got {type(value).__name__}")
    return value


def _number(mapping: dict[str, Any], key: str, section: str) -> float:
    if key not in mapping:
        raise ConfigError(f"{section}: key {key!r} missing")
    value = mapping[key]
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ConfigError(f"{section}.{key}: number expected, got {value!r}")
    if not math.isfinite(value):  # .inf makes a sleep endless, .nan passes every comparison
        raise ConfigError(f"{section}.{key}: finite number expected, got {value!r}")
    return float(value)


def _positive(mapping: dict[str, Any], key: str, section: str) -> float:
    number = _number(mapping, key, section)
    if number <= 0:
        raise ConfigError(f"{section}.{key}: strictly positive expected, got {number}")
    return number


def _non_negative(mapping: dict[str, Any], key: str, section: str) -> float:
    number = _number(mapping, key, section)
    if number < 0:
        raise ConfigError(f"{section}.{key}: ≥ 0 expected, got {number}")
    return number


def _positive_int(mapping: dict[str, Any], key: str, section: str) -> int:
    """Strictly positive integer (bool refused), else ``ConfigError`` (fail-fast §5/§14)."""
    if key not in mapping:
        raise ConfigError(f"{section}: key {key!r} missing")
    value = mapping[key]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{section}.{key}: strictly positive integer expected, got {value!r}")
    return value


def _bool(mapping: dict[str, Any], key: str, section: str) -> bool:
    """REQUIRED boolean, else ``ConfigError`` (fail-fast §5/§14)."""
    if key not in mapping:
        raise ConfigError(f"{section}: key {key!r} missing")
    value = mapping[key]
    if not isinstance(value, bool):
        raise ConfigError(f"{section}.{key}: boolean expected, got {value!r}")
    return value


# Coherent bounds for a P2P watch: a day for a delay, 30 days for an absence (operator, 2026-10-13).
_A_DAY = 86_400.0
_THIRTY_DAYS = 2_592_000.0


def _seconds(
    mapping: dict[str, Any],
    key: str,
    section: str,
    default: float | None = None,
    *,
    at_most: float = _A_DAY,
) -> float:
    """Strictly positive seconds up to ``at_most``; OPTIONAL when given a ``default``."""
    if default is not None and key not in mapping:
        return default
    seconds = _positive(mapping, key, section)
    if seconds > at_most:
        raise ConfigError(f"{section}.{key}: at most {at_most:.0f} seconds expected, got {seconds}")
    return seconds


def _positive_int_default(mapping: dict[str, Any], key: str, default: int, section: str) -> int:
    """OPTIONAL strictly positive integer (default ``default``)."""
    if key not in mapping:
        return default
    return _positive_int(mapping, key, section)


def _bool_default(mapping: dict[str, Any], key: str, default: bool, section: str) -> bool:
    """OPTIONAL boolean (default ``default``); refuses a non-bool — fail-fast (§5/§14)."""
    if key not in mapping:
        return default
    value = mapping[key]
    if not isinstance(value, bool):
        raise ConfigError(f"{section}.{key}: boolean expected, got {value!r}")
    return value


def _require_str(mapping: dict[str, Any], key: str, section: str, env: Mapping[str, str]) -> str:
    """Non-empty string, ``${NAME}``-interpolated from ``env`` AFTER reading, BEFORE the non-empty
    check (fail-fast §5/§14). Missing env variable ⇒ ``ConfigError`` (via ``interpolate``)."""
    if key not in mapping:
        raise ConfigError(f"{section}: key {key!r} missing")
    value = mapping[key]
    if not isinstance(value, str):
        raise ConfigError(f"{section}.{key}: non-empty string expected, got {value!r}")
    interpolated = interpolate(value, env, f"{section}.{key}")
    if not interpolated:
        raise ConfigError(f"{section}.{key}: non-empty string expected, got {interpolated!r}")
    return interpolated


def _parse_observability(raw: dict[str, Any], env: Mapping[str, str]) -> ObservabilityConfig:
    log_level = raw.get("log_level", "INFO")
    if not isinstance(log_level, str) or log_level not in _LOG_LEVELS:
        raise ConfigError(
            f"observability.log_level: one of {sorted(_LOG_LEVELS)} expected, got {log_level!r}"
        )
    metrics: MetricsConfig | None = None
    if "metrics" in raw:
        metrics_raw = _require_mapping(raw["metrics"], "observability.metrics")
        metrics = MetricsConfig(
            enabled=_bool(metrics_raw, "enabled", "observability.metrics"),
            port=_positive_int(metrics_raw, "port", "observability.metrics"),
        )
    timeout = _seconds(raw, "notification_timeout_seconds", "observability", 5.0)
    notifications: list[NotificationTarget] = []
    for index, entry in enumerate(raw.get("notifications", [])):
        section = f"observability.notifications[{index}]"
        mapping = _require_mapping(entry, section)
        tag_raw = _require_str(mapping, "tag", section, env)
        try:
            tag = Audience(tag_raw)
        except ValueError as error:
            raise ConfigError(
                f"{section}.tag: 'community' or 'operations' expected, got {tag_raw!r}"
            ) from error
        notifications.append(
            NotificationTarget(
                url=_require_str(mapping, "url", section, env),
                tag=tag,
                node_prefix=_bool_default(mapping, "node_prefix", True, section),
            )
        )
    return ObservabilityConfig(
        log_level=log_level,
        metrics=metrics,
        notification_timeout_seconds=timeout,
        notifications=tuple(notifications),
    )


# The three download knobs of 2026-09-13 default rather than fail fast: an operator config
# written before them must still boot. 24 h absorbs an amuled restart or a night of downtime.
_DEFAULT_MIN_FREE_BYTES = 10_737_418_240  # 10 GiB
_DEFAULT_LOST_AFTER_SECONDS = 86_400.0
_DEFAULT_OUTPUT_DIR = "/downloads"  # the bind mount in deploy/compose.yml
_DEFAULT_REAPPEARED_AFTER_SECONDS = 43_200.0  # 12 h: a night off does not notify (stage 4 spec, D9)
# 5 min: enough to recognise a sharer, a tenth of the detail calls (source points spec, D3).
_DEFAULT_SOURCES_INTERVAL_SECONDS = 300.0


def _parse_download(raw: dict[str, Any]) -> DownloadConfig | None:
    if "download" not in raw:
        return None
    section = _require_mapping(raw["download"], "section 'download'")
    if not _bool_default(section, "enabled", False, "download"):
        return None  # laziness: we read/interpolate NOTHING else (no variable required)
    output_dir = section.get("output_dir", _DEFAULT_OUTPUT_DIR)
    if not isinstance(output_dir, str) or not output_dir:
        raise ConfigError(f"download.output_dir: non-empty string expected, got {output_dir!r}")
    return DownloadConfig(
        poll_interval_seconds=_seconds(section, "poll_interval_seconds", "download"),
        min_free_bytes=_positive_int_default(
            section, "min_free_bytes", _DEFAULT_MIN_FREE_BYTES, "download"
        ),
        lost_after_seconds=_seconds(
            section,
            "lost_after_seconds",
            "download",
            _DEFAULT_LOST_AFTER_SECONDS,
            at_most=_THIRTY_DAYS,
        ),
        output_dir=output_dir,
        reappeared_after=timedelta(
            seconds=_seconds(
                section,
                "reappeared_after_seconds",
                "download",
                _DEFAULT_REAPPEARED_AFTER_SECONDS,
                at_most=_THIRTY_DAYS,
            )
        ),
        sources_interval=timedelta(
            seconds=_seconds(
                section, "sources_interval_seconds", "download", _DEFAULT_SOURCES_INTERVAL_SECONDS
            )
        ),
    )


def _parse_search(raw: dict[str, Any]) -> SearchConfig:
    """`search` section, required: its non-empty keywords and its backoff."""
    section = _require_mapping(raw.get("search", {}), "section 'search'")
    if "keywords" not in section:
        raise ConfigError("search: key 'keywords' missing")
    keywords = section["keywords"]
    if not isinstance(keywords, list) or not keywords:
        raise ConfigError("search.keywords: non-empty list of strings expected")
    result: list[str] = []
    for entry in keywords:
        if not isinstance(entry, str) or not entry:
            raise ConfigError(f"search.keywords: non-empty string expected, got {entry!r}")
        result.append(entry)
    return SearchConfig(keywords=tuple(result), backoff=_parse_backoff(section))


def _parse_backoff(search: dict[str, Any]) -> BackoffConfig:
    """`search.backoff`, required: a factor that grows, a cap at least the base."""
    section = _require_mapping(search.get("backoff", {}), "section 'search.backoff'")
    factor = _positive(section, "factor", "search.backoff")
    if factor < 1:
        raise ConfigError(f"search.backoff.factor must be ≥ 1 (growth), got {factor}")
    backoff = BackoffConfig(
        base_seconds=_seconds(section, "base_seconds", "search.backoff"),
        cap_seconds=_seconds(section, "cap_seconds", "search.backoff"),
        factor=factor,
        jitter_ratio=_non_negative(section, "jitter_ratio", "search.backoff"),
    )
    if backoff.cap_seconds < backoff.base_seconds:
        raise ConfigError(
            f"search.backoff.cap_seconds ({backoff.cap_seconds}) < base_seconds "
            f"({backoff.base_seconds}): cap below floor"
        )
    return backoff


def _parse_webui(raw: dict[str, Any], env: Mapping[str, str]) -> WebuiConfig:
    """`webui` section (optional). Absent ⇒ enabled, default aMule link and period gap.

    The bind is FIXED at 0.0.0.0:8080 in the composition layer, so this reads no host/port: an
    unknown key (a legacy ``host``/``port``) is ignored silently, no fail-fast."""
    if "webui" not in raw:
        return _DEFAULT_WEBUI
    section = _require_mapping(raw["webui"], "section 'webui'")
    enabled = _bool_default(section, "enabled", True, "webui")
    gap = timedelta(
        seconds=_seconds(
            section,
            "source_period_gap_seconds",
            "webui",
            _DEFAULT_SOURCE_PERIOD_GAP.total_seconds(),
        )
    )
    if "amule_url" not in section:
        return WebuiConfig(enabled=enabled, source_period_gap=gap)
    amule_url = _require_str(section, "amule_url", "webui", env)
    return WebuiConfig(enabled=enabled, amule_url=amule_url, source_period_gap=gap)


def parse_crawler_config(raw: dict[str, Any], env: Mapping[str, str]) -> CrawlerConfig:
    """Builds a validated ``CrawlerConfig`` from the parsed YAML dict + the ``env`` environment
    (interpolation of ``${NAME}``). Fail-fast §5/§14: any inconsistency → ``ConfigError``."""
    for key in _REMOVED_KEYS:
        if key in raw:
            raise ConfigError(f"crawler: key '{key}' was removed, delete it from crawler.yml")
    for key, place in _MOVED_KEYS.items():
        if key in raw:
            raise ConfigError(f"crawler: key '{key}' moved to '{place}', move it in crawler.yml")
    node_id_raw = raw.get("node_id")
    if node_id_raw is not None and (not isinstance(node_id_raw, str) or not node_id_raw):
        raise ConfigError(f"node_id: non-empty string or absent expected, got {node_id_raw!r}")
    observability: ObservabilityConfig | None = None
    if "observability" in raw:
        observability = _parse_observability(
            _require_mapping(raw["observability"], "section 'observability'"), env
        )
    return CrawlerConfig(
        search=_parse_search(raw),
        shutdown_deadline_seconds=_seconds(raw, "shutdown_deadline_seconds", "crawler"),
        amule_api_password=_require_str(raw, "amule_api_password", "crawler", env),
        catalog_db_path=_require_str(raw, "catalog_db_path", "crawler", env),
        local_db_path=_require_str(raw, "local_db_path", "crawler", env),
        node_id=node_id_raw,
        observability=observability,
        download=_parse_download(raw),
        webui=_parse_webui(raw, env),
    )
