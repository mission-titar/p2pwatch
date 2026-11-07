"""``crawler.yml``'s objects, the parse of ``download``, which the config adapter's schema leaves
as a mapping, raising a ``ConfigValueError`` on its first problem, and its rules across values.

The config adapter resolves ``${NAME}`` in every string value before the parse, which never sees
the environment. ``download`` is ``None`` unless ``enabled: true``, its wiring keys required only
then.
"""

import math
from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePath
from typing import Any

from p2pwatch.domain.config_defaults import (
    DEFAULT_DOWNLOAD_ENABLED,
    DEFAULT_LOST_AFTER,
    DEFAULT_MIN_FREE_BYTES,
    DEFAULT_OUTPUT_DIRECTORY,
    DEFAULT_REAPPEARED_AFTER,
    DEFAULT_SOURCES_INTERVAL,
)
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.config_value_error import ConfigValueError
from p2pwatch.domain.matching.config import MatcherConfig
from p2pwatch.domain.matching.models import TargetSegment
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


def _key_path(error_label: str, *, key: str) -> str:
    return f"{error_label}.{key}"


def _required(section: dict[str, Any], *, key: str, error_label: str) -> Any:
    if key in section:
        return section[key]
    raise ConfigValueError(_key_path(error_label, key=key), message="missing")


def _number(section: dict[str, Any], *, key: str, error_label: str) -> float:
    setting = _required(section, key=key, error_label=error_label)
    if not isinstance(setting, int | float) or isinstance(setting, bool):
        raise ConfigValueError(
            _key_path(error_label, key=key), message=f"number expected, got {setting!r}"
        )
    if not math.isfinite(setting):  # .inf makes a sleep endless, .nan passes every comparison
        raise ConfigValueError(
            _key_path(error_label, key=key), message=f"finite number expected, got {setting!r}"
        )
    return float(setting)


def _positive(section: dict[str, Any], *, key: str, error_label: str) -> float:
    number = _number(section, key=key, error_label=error_label)
    if number <= 0:
        raise ConfigValueError(
            _key_path(error_label, key=key), message=f"strictly positive expected, got {number}"
        )
    return number


def _positive_int(section: dict[str, Any], *, key: str, error_label: str) -> int:
    """Strictly positive integer (bool refused), else ``ConfigValueError`` (fail-fast §5/§14)."""
    setting = _required(section, key=key, error_label=error_label)
    if not isinstance(setting, int) or isinstance(setting, bool) or setting <= 0:
        raise ConfigValueError(
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
        raise ConfigValueError(
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
        raise ConfigValueError(
            _key_path(error_label, key=key), message=f"boolean expected, got {setting!r}"
        )
    return setting


def parse_download(section: dict[str, Any]) -> DownloadConfig | None:
    """The ``download`` section, ``None`` unless ``enabled``."""
    if not _bool_default(
        section, key="enabled", error_label="download", default=DEFAULT_DOWNLOAD_ENABLED
    ):
        return None  # laziness: we read NOTHING else (no wiring required)
    output_directory = section.get("output_dir", DEFAULT_OUTPUT_DIRECTORY)
    if not isinstance(output_directory, str) or not output_directory:
        raise ConfigValueError(
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


def cross_value_problems(
    config: CrawlerConfig, *, file_path: PurePath
) -> tuple[ConfigProblem, ...]:
    """The problems of ``config`` no single value shows, once each value of its file holds."""
    backoff = config.search.backoff
    if backoff.cap_seconds < backoff.base_seconds:
        return (
            ConfigProblem(
                file_path=file_path,
                key="search.backoff.cap_seconds",
                message="should be at least base_seconds",
            ),
        )
    return ()


@dataclass(kw_only=True, frozen=True)
class LoadedConfig:
    """The three config files, parsed, and the fingerprint of the two that make the policy."""

    crawler_config: CrawlerConfig
    targets: tuple[TargetSegment, ...]
    matcher_config: MatcherConfig
    policy_fingerprint: str
