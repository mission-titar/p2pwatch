"""``crawler.yml``'s objects, which the config adapter builds, and its rules across values."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePath

from p2pwatch.domain.config_problem import ConfigProblem
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
