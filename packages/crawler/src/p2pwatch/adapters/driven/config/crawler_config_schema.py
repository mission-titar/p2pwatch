"""``crawler.yml`` as written, read by pydantic, and the ``CrawlerConfig`` it builds."""

from datetime import timedelta
from pathlib import PurePath
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    Discriminator,
    Field,
    GetPydanticSchema,
    Tag,
    ValidationError,
    create_model,
)
from pydantic_core import PydanticCustomError

from p2pwatch.adapters.driven.config.validation_problems import (
    TAG_MARK,
    StrictSchema,
    moved_key,
    removed_key,
    renamed_key,
    validation_problems,
)
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
from p2pwatch.domain.crawler_config import (
    BackoffConfig,
    CrawlerConfig,
    DownloadConfig,
    NotificationTarget,
    ObservabilityConfig,
    SearchConfig,
    WebuiConfig,
    cross_value_problems,
)
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.observability.policy import Audience

_FILE_NAME = "crawler.yml"

# Coherent bounds for a P2P watch: a day for a delay, 30 days for an absence (operator, 2026-10-13).
_A_DAY_SECONDS = 86_400
_THIRTY_DAYS_SECONDS = 2_592_000

# Past it, a delay reaches its cap after a failure or two: a step rather than a backoff.
_MAX_FACTOR = 10

# deploy/compose.yml's stop_grace_period (30 s) minus the close the composition then allows (5 s).
MAX_SHUTDOWN_DEADLINE_SECONDS = 25


def _within_the_stop_grace(deadline_seconds: float) -> float:
    if deadline_seconds > MAX_SHUTDOWN_DEADLINE_SECONDS:
        raise PydanticCustomError(
            "shutdown_deadline_past_the_stop_grace",
            f"Input should be less than or equal to {MAX_SHUTDOWN_DEADLINE_SECONDS}: past it, "
            "deploy/compose.yml's stop_grace_period (30s) kills the crawler before its close ends",
        )
    return deadline_seconds


_Seconds = Annotated[float, Field(gt=0, le=_A_DAY_SECONDS)]
_ShutdownDeadline = Annotated[float, Field(gt=0), AfterValidator(_within_the_stop_grace)]
_Absence = Annotated[float, Field(gt=0, le=_THIRTY_DAYS_SECONDS)]
_Text = Annotated[str, Field(min_length=1)]


class _BackoffSchema(StrictSchema):
    base_seconds: _Seconds
    cap_seconds: _Seconds
    factor: Annotated[float, Field(ge=1, le=_MAX_FACTOR)]
    jitter_ratio: Annotated[float, Field(ge=0, le=1)]


class _SearchSchema(StrictSchema):
    keywords: Annotated[list[_Text], Field(min_length=1)]
    backoff: _BackoffSchema


class _DownloadKeysSchema(StrictSchema):
    min_free_bytes: Annotated[int, Field(gt=0)] = DEFAULT_MIN_FREE_BYTES
    lost_after_seconds: _Absence = DEFAULT_LOST_AFTER.total_seconds()
    output_dir: _Text = DEFAULT_OUTPUT_DIRECTORY
    reappeared_after_seconds: _Absence = DEFAULT_REAPPEARED_AFTER.total_seconds()
    sources_interval_seconds: _Seconds = DEFAULT_SOURCES_INTERVAL.total_seconds()


# Two schemas, so that only a download on requires its wiring and every key is checked either way.
class _DownloadOffSchema(_DownloadKeysSchema):
    enabled: bool = DEFAULT_DOWNLOAD_ENABLED
    # Never read when off: pydantic validates no default, so the key stays optional, a null refused.
    poll_interval_seconds: _Seconds = 0.0


class _DownloadOnSchema(_DownloadKeysSchema):
    enabled: Literal[True]
    poll_interval_seconds: _Seconds


_ON = f"{TAG_MARK}on"
_OFF = f"{TAG_MARK}off"


def _download_tag(download: object) -> str:
    """The schema of ``download``: on when its ``enabled`` is true, off for anything else."""
    if isinstance(download, dict) and download.get("enabled", DEFAULT_DOWNLOAD_ENABLED) is True:
        return _ON
    return _OFF


_DownloadSchema = Annotated[
    Annotated[_DownloadOnSchema, Tag(_ON)] | Annotated[_DownloadOffSchema, Tag(_OFF)],
    Discriminator(_download_tag),
]


# Every refusing field is built, since vulture reads a field nothing reads as dead code.
_REMOVED = removed_key(_FILE_NAME)


class _WebuiKeysSchema(StrictSchema):
    amule_url: _Text = DEFAULT_AMULE_URL
    source_period_gap_seconds: _Seconds = DEFAULT_SOURCE_PERIOD_GAP.total_seconds()


# The bind is fixed in the composition ring: 4.x's host and port were ignored.
_WEBUI_REFUSED: dict[str, Any] = {key: (_REMOVED, None) for key in ("enabled", "host", "port")}
_WebuiSchema = create_model("_WebuiSchema", __base__=_WebuiKeysSchema, **_WEBUI_REFUSED)


class _NotificationKeysSchema(StrictSchema):
    url: _Text
    audience: Literal["community", "operations"]
    node_prefix: bool = DEFAULT_NODE_PREFIX


_NOTIFICATION_RENAMED: dict[str, Any] = {
    "tag": (renamed_key("audience", file_name=_FILE_NAME), None)
}
_NotificationSchema = create_model(
    "_NotificationSchema", __base__=_NotificationKeysSchema, **_NOTIFICATION_RENAMED
)


class _ObservabilityKeysSchema(StrictSchema):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = DEFAULT_LOG_LEVEL
    notification_timeout_seconds: _Seconds = DEFAULT_NOTIFICATION_TIMEOUT_SECONDS
    notifications: list[
        Annotated[
            _NotificationKeysSchema,
            GetPydanticSchema(lambda _source, handler: handler(_NotificationSchema)),
        ]
    ] = Field(default_factory=list)


_OBSERVABILITY_REFUSED: dict[str, Any] = {"metrics": (_REMOVED, None)}
_ObservabilitySchema = create_model(
    "_ObservabilitySchema", __base__=_ObservabilityKeysSchema, **_OBSERVABILITY_REFUSED
)


# mypy reads the keys' class, which a built schema extends: pydantic validates by the schema.
class _RootKeysSchema(StrictSchema):
    shutdown_deadline_seconds: _ShutdownDeadline
    amule_api_password: _Text
    catalog_db_path: _Text
    local_db_path: _Text
    search: _SearchSchema
    download: _DownloadSchema = Field(default_factory=_DownloadOffSchema)
    observability: Annotated[
        _ObservabilityKeysSchema,
        GetPydanticSchema(lambda _source, handler: handler(_ObservabilitySchema)),
    ] = Field(default_factory=_ObservabilitySchema)
    webui: Annotated[
        _WebuiKeysSchema, GetPydanticSchema(lambda _source, handler: handler(_WebuiSchema))
    ] = Field(default_factory=_WebuiSchema)


_REMOVED_KEYS = (
    "cycle_interval_seconds",
    "decision_poll_interval_seconds",
    "keyword_pause_max_seconds",
    "keyword_pause_min_seconds",
    "node_id",
    "port_sync",
    "search_poll_budget_seconds",
    "search_poll_interval_seconds",
)

_FIELDS: dict[str, Any] = {key: (_REMOVED, None) for key in _REMOVED_KEYS} | {
    "backoff": (moved_key("search.backoff", file_name=_FILE_NAME), None)
}
CrawlerConfigSchema = create_model("CrawlerConfigSchema", __base__=_RootKeysSchema, **_FIELDS)


def crawler_config_from_document(document: dict[str, Any], *, file_path: PurePath) -> CrawlerConfig:
    """``document``'s ``CrawlerConfig``; ``InvalidConfigError`` with every problem of its values,
    or once they hold, every problem across its values."""
    try:
        root = CrawlerConfigSchema.model_validate(document)
    except ValidationError as error:
        raise InvalidConfigError(
            validation_problems(error, document=document, file_path=file_path)
        ) from None
    backoff = root.search.backoff
    crawler_config = CrawlerConfig(
        search=SearchConfig(
            keywords=tuple(root.search.keywords),
            backoff=BackoffConfig(
                base_seconds=backoff.base_seconds,
                cap_seconds=backoff.cap_seconds,
                factor=backoff.factor,
                jitter_ratio=backoff.jitter_ratio,
            ),
        ),
        shutdown_deadline_seconds=root.shutdown_deadline_seconds,
        amule_api_password=root.amule_api_password,
        catalog_db_path=root.catalog_db_path,
        local_db_path=root.local_db_path,
        observability=_observability(root.observability),
        download=_download(root.download),
        webui=WebuiConfig(
            amule_url=root.webui.amule_url,
            source_period_gap=timedelta(seconds=root.webui.source_period_gap_seconds),
        ),
    )
    if rule_problems := cross_value_problems(crawler_config, file_path=file_path):
        raise InvalidConfigError(rule_problems)
    return crawler_config


def _observability(observability: _ObservabilityKeysSchema) -> ObservabilityConfig:
    return ObservabilityConfig(
        log_level=observability.log_level,
        notification_timeout_seconds=observability.notification_timeout_seconds,
        notifications=tuple(
            NotificationTarget(
                url=notification.url,
                audience=Audience(notification.audience),
                node_prefix=notification.node_prefix,
            )
            for notification in observability.notifications
        ),
    )


def _download(download: _DownloadOnSchema | _DownloadOffSchema) -> DownloadConfig | None:
    match download:
        case _DownloadOnSchema(enabled=True):
            return DownloadConfig(
                poll_interval_seconds=download.poll_interval_seconds,
                min_free_bytes=download.min_free_bytes,
                lost_after=timedelta(seconds=download.lost_after_seconds),
                output_directory=download.output_dir,
                reappeared_after=timedelta(seconds=download.reappeared_after_seconds),
                sources_interval=timedelta(seconds=download.sources_interval_seconds),
            )
        case _:
            return None
