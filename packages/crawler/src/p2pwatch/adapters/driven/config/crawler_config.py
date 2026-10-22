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
from pathlib import Path
from typing import Any

from catalog_matching.domain.config import MatcherConfig
from catalog_matching.domain.models import TargetSegment
from catalog_matching.domain.validation import (
    MatchingConfigError,
    parse_matcher_config,
    parse_targets,
)
from p2pwatch.adapters.driven.config.errors import ConfigError as ConfigError  # explicit re-export
from p2pwatch.adapters.driven.config.interpolation import interpolate
from p2pwatch.adapters.driven.config.yaml_loader import YamlLoadError, load_yaml
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
    DEFAULT_WEBUI_ENABLED,
)
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.policy_fingerprint import policy_fingerprint


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


AMULE_CLIENT_NAME = "amuled"


@dataclass(frozen=True)
class NotificationTarget:
    """An apprise target (secret via ``${...}``), notified for one ``audience`` (E-D7).
    ``node_prefix: false`` drops the ``[node-id]`` prefix, for a service with its own identity."""

    url: str
    audience: Audience
    node_prefix: bool


@dataclass(frozen=True)
class DownloadConfig:
    """Download policy and wiring, present ⟺ ``enabled``. ``output_dir`` is measured with
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
    amule_url: str
    source_period_gap: timedelta


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

    @property
    def metrics_port(self) -> int | None:
        """The port the metrics server listens on, ``None`` when it is off."""
        if self.metrics is None or not self.metrics.enabled:
            return None
        return self.metrics.port


@dataclass(frozen=True)
class CrawlerConfig:
    """Unified crawler config (policy + wiring). All durations in SECONDS.

    Policy: ``search`` (keywords and backoff), ``shutdown_deadline_seconds`` (hard bound of the
    clean shutdown).

    Wiring (ex-local): ``amule_api_password`` (the daemon's amuleapi admin password, the same
    one the aMule web UI takes; host/port are code
    constants), DB paths, ``node_id`` (``None`` = the one from ``local.db``), ``observability``,
    ``download`` (``None`` ⟺ download off, crawl-only).
    """

    search: SearchConfig
    shutdown_deadline_seconds: float
    amule_api_password: str
    catalog_db_path: str
    local_db_path: str
    node_id: str | None
    observability: ObservabilityConfig
    download: DownloadConfig | None
    webui: WebuiConfig


def _require_mapping(value: Any, error_label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{error_label}: mapping expected, got {type(value).__name__}")
    return value


# The root's error label: crawler.yml has no section around its root keys, so they print bare.
_ROOT = ""


def _key_path(error_label: str, key: str) -> str:
    return f"{error_label}.{key}" if error_label else key


def _required(section: dict[str, Any], key: str, error_label: str) -> Any:
    if key in section:
        return section[key]
    prefix = f"{error_label}: " if error_label else ""
    raise ConfigError(f"{prefix}key {key!r} missing")


def _number(section: dict[str, Any], key: str, error_label: str) -> float:
    value = _required(section, key, error_label)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ConfigError(f"{_key_path(error_label, key)}: number expected, got {value!r}")
    if not math.isfinite(value):  # .inf makes a sleep endless, .nan passes every comparison
        raise ConfigError(f"{_key_path(error_label, key)}: finite number expected, got {value!r}")
    return float(value)


def _positive(section: dict[str, Any], key: str, error_label: str) -> float:
    number = _number(section, key, error_label)
    if number <= 0:
        raise ConfigError(
            f"{_key_path(error_label, key)}: strictly positive expected, got {number}"
        )
    return number


def _non_negative(section: dict[str, Any], key: str, error_label: str) -> float:
    number = _number(section, key, error_label)
    if number < 0:
        raise ConfigError(f"{_key_path(error_label, key)}: ≥ 0 expected, got {number}")
    return number


def _positive_int(section: dict[str, Any], key: str, error_label: str) -> int:
    """Strictly positive integer (bool refused), else ``ConfigError`` (fail-fast §5/§14)."""
    value = _required(section, key, error_label)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(
            f"{_key_path(error_label, key)}: strictly positive integer expected, got {value!r}"
        )
    return value


def _bool(section: dict[str, Any], key: str, error_label: str) -> bool:
    """REQUIRED boolean, else ``ConfigError`` (fail-fast §5/§14)."""
    value = _required(section, key, error_label)
    if not isinstance(value, bool):
        raise ConfigError(f"{_key_path(error_label, key)}: boolean expected, got {value!r}")
    return value


# Coherent bounds for a P2P watch: a day for a delay, 30 days for an absence (operator, 2026-10-13).
_A_DAY_SECONDS = 86_400.0
_THIRTY_DAYS_SECONDS = 2_592_000.0


def _seconds(
    section: dict[str, Any],
    key: str,
    error_label: str,
    default: float | None = None,
    *,
    at_most: float = _A_DAY_SECONDS,
) -> float:
    """Strictly positive seconds up to ``at_most``; OPTIONAL when given a ``default``."""
    if default is not None and key not in section:
        return default
    seconds = _positive(section, key, error_label)
    if seconds > at_most:
        raise ConfigError(
            f"{_key_path(error_label, key)}: at most {at_most:.0f} seconds expected, got {seconds}"
        )
    return seconds


def _positive_int_default(section: dict[str, Any], key: str, error_label: str, default: int) -> int:
    """OPTIONAL strictly positive integer (default ``default``)."""
    if key not in section:
        return default
    return _positive_int(section, key, error_label)


def _bool_default(section: dict[str, Any], key: str, error_label: str, default: bool) -> bool:
    """OPTIONAL boolean (default ``default``); refuses a non-bool, fail-fast (§5/§14)."""
    if key not in section:
        return default
    value = section[key]
    if not isinstance(value, bool):
        raise ConfigError(f"{_key_path(error_label, key)}: boolean expected, got {value!r}")
    return value


def _string(section: dict[str, Any], key: str, error_label: str, env: Mapping[str, str]) -> str:
    """Non-empty string, ``${NAME}``-interpolated from ``env`` AFTER reading, BEFORE the non-empty
    check (fail-fast §5/§14). Missing env variable ⇒ ``ConfigError`` (via ``interpolate``)."""
    key_path = _key_path(error_label, key)
    value = _required(section, key, error_label)
    if not isinstance(value, str):
        raise ConfigError(f"{key_path}: non-empty string expected, got {value!r}")
    interpolated = interpolate(value, env, key_path)
    if not interpolated:
        raise ConfigError(f"{key_path}: non-empty string expected, got {interpolated!r}")
    return interpolated


def _parse_observability(section: dict[str, Any], env: Mapping[str, str]) -> ObservabilityConfig:
    log_level = section.get("log_level", DEFAULT_LOG_LEVEL)
    if not isinstance(log_level, str) or log_level not in _LOG_LEVELS:
        raise ConfigError(
            f"observability.log_level: one of {sorted(_LOG_LEVELS)} expected, got {log_level!r}"
        )
    metrics: MetricsConfig | None = None
    if "metrics" in section:
        metrics_raw = _require_mapping(section["metrics"], "observability.metrics")
        metrics = MetricsConfig(
            enabled=_bool(metrics_raw, "enabled", "observability.metrics"),
            port=_positive_int(metrics_raw, "port", "observability.metrics"),
        )
    timeout = _seconds(
        section,
        "notification_timeout_seconds",
        "observability",
        DEFAULT_NOTIFICATION_TIMEOUT_SECONDS,
    )
    notifications: list[NotificationTarget] = []
    for index, entry in enumerate(section.get("notifications", [])):
        error_label = f"observability.notifications[{index}]"
        notification = _require_mapping(entry, error_label)
        if "tag" in notification:  # the 4.x name, refused like _MOVED_KEYS
            raise ConfigError(
                f"{error_label}: key 'tag' was renamed 'audience', rename it in crawler.yml"
            )
        audience_raw = _string(notification, "audience", error_label, env)
        try:
            audience = Audience(audience_raw)
        except ValueError as error:
            raise ConfigError(
                f"{error_label}.audience: 'community' or 'operations' expected, "
                f"got {audience_raw!r}"
            ) from error
        notifications.append(
            NotificationTarget(
                url=_string(notification, "url", error_label, env),
                audience=audience,
                node_prefix=_bool_default(
                    notification, "node_prefix", error_label, DEFAULT_NODE_PREFIX
                ),
            )
        )
    return ObservabilityConfig(
        log_level=log_level,
        metrics=metrics,
        notification_timeout_seconds=timeout,
        notifications=tuple(notifications),
    )


def _parse_download(document: dict[str, Any]) -> DownloadConfig | None:
    section = _require_mapping(document.get("download", {}), "section 'download'")
    if not _bool_default(section, "enabled", "download", DEFAULT_DOWNLOAD_ENABLED):
        return None  # laziness: we read/interpolate NOTHING else (no variable required)
    output_directory = section.get("output_dir", DEFAULT_OUTPUT_DIRECTORY)
    if not isinstance(output_directory, str) or not output_directory:
        raise ConfigError(
            f"download.output_dir: non-empty string expected, got {output_directory!r}"
        )
    return DownloadConfig(
        poll_interval_seconds=_seconds(section, "poll_interval_seconds", "download"),
        min_free_bytes=_positive_int_default(
            section, "min_free_bytes", "download", DEFAULT_MIN_FREE_BYTES
        ),
        lost_after=timedelta(
            seconds=_seconds(
                section,
                "lost_after_seconds",
                "download",
                DEFAULT_LOST_AFTER.total_seconds(),
                at_most=_THIRTY_DAYS_SECONDS,
            )
        ),
        output_directory=output_directory,
        reappeared_after=timedelta(
            seconds=_seconds(
                section,
                "reappeared_after_seconds",
                "download",
                DEFAULT_REAPPEARED_AFTER.total_seconds(),
                at_most=_THIRTY_DAYS_SECONDS,
            )
        ),
        sources_interval=timedelta(
            seconds=_seconds(
                section,
                "sources_interval_seconds",
                "download",
                DEFAULT_SOURCES_INTERVAL.total_seconds(),
            )
        ),
    )


def _parse_search(document: dict[str, Any]) -> SearchConfig:
    """`search` section, required: its non-empty keywords and its backoff."""
    section = _require_mapping(document.get("search", {}), "section 'search'")
    keywords = _required(section, "keywords", "search")
    if not isinstance(keywords, list) or not keywords:
        raise ConfigError("search.keywords: non-empty list of strings expected")
    parsed_keywords: list[str] = []
    for entry in keywords:
        if not isinstance(entry, str) or not entry:
            raise ConfigError(f"search.keywords: non-empty string expected, got {entry!r}")
        parsed_keywords.append(entry)
    return SearchConfig(keywords=tuple(parsed_keywords), backoff=_parse_backoff(section))


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


def _parse_webui(document: dict[str, Any], env: Mapping[str, str]) -> WebuiConfig:
    """`webui` section (optional): an absent section or key takes the domain's default.

    The bind is FIXED at 0.0.0.0:8080 in the composition layer, so this reads no host/port: an
    unknown key (a legacy ``host``/``port``) is ignored silently, no fail-fast."""
    section = _require_mapping(document.get("webui", {}), "section 'webui'")
    enabled = _bool_default(section, "enabled", "webui", DEFAULT_WEBUI_ENABLED)
    gap = timedelta(
        seconds=_seconds(
            section,
            "source_period_gap_seconds",
            "webui",
            DEFAULT_SOURCE_PERIOD_GAP.total_seconds(),
        )
    )
    amule_url = (
        _string(section, "amule_url", "webui", env) if "amule_url" in section else DEFAULT_AMULE_URL
    )
    return WebuiConfig(enabled=enabled, amule_url=amule_url, source_period_gap=gap)


def parse_crawler_config(document: dict[str, Any], env: Mapping[str, str]) -> CrawlerConfig:
    """Builds a validated ``CrawlerConfig`` from the parsed YAML dict + the ``env`` environment
    (interpolation of ``${NAME}``). Fail-fast §5/§14: any inconsistency → ``ConfigError``."""
    for key in _REMOVED_KEYS:
        if key in document:
            raise ConfigError(f"key '{key}' was removed, delete it from crawler.yml")
    for key, new_path in _MOVED_KEYS.items():
        if key in document:
            raise ConfigError(f"key '{key}' moved to '{new_path}', move it in crawler.yml")
    node_id_raw = document.get("node_id")
    if node_id_raw is not None and (not isinstance(node_id_raw, str) or not node_id_raw):
        raise ConfigError(f"node_id: non-empty string or absent expected, got {node_id_raw!r}")
    observability = _parse_observability(
        _require_mapping(document.get("observability", {}), "section 'observability'"), env
    )
    return CrawlerConfig(
        search=_parse_search(document),
        shutdown_deadline_seconds=_seconds(document, "shutdown_deadline_seconds", _ROOT),
        amule_api_password=_string(document, "amule_api_password", _ROOT, env),
        catalog_db_path=_string(document, "catalog_db_path", _ROOT, env),
        local_db_path=_string(document, "local_db_path", _ROOT, env),
        node_id=node_id_raw,
        observability=observability,
        download=_parse_download(document),
        webui=_parse_webui(document, env),
    )


@dataclass(frozen=True)
class LoadedConfig:
    """The three config files, parsed, and the fingerprint of the two that make the policy."""

    crawler_config: CrawlerConfig
    targets: tuple[TargetSegment, ...]
    matcher_config: MatcherConfig
    policy_fingerprint: str


def load_config(
    config_path: Path, targets_path: Path, matcher_path: Path, env: Mapping[str, str]
) -> LoadedConfig:
    """Loads ``crawler.yml``, ``targets.yml`` and ``matcher.yml``; any of them invalid raises
    ``InvalidConfigError``.

    The fingerprint hashes the two policy files' RAW bytes, not their parse, so a
    comment-only edit still triggers one harmless re-evaluation at the next start.
    """
    try:
        crawler_config = parse_crawler_config(load_yaml(config_path), env)
        targets = parse_targets(load_yaml(targets_path))
        matcher_config = parse_matcher_config(load_yaml(matcher_path))
    except (YamlLoadError, ConfigError, MatchingConfigError) as error:
        raise InvalidConfigError(str(error)) from error
    return LoadedConfig(
        crawler_config=crawler_config,
        targets=targets,
        matcher_config=matcher_config,
        policy_fingerprint=policy_fingerprint(matcher_path.read_bytes(), targets_path.read_bytes()),
    )
