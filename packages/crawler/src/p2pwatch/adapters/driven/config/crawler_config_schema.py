"""``crawler.yml`` as written, read by pydantic but its ``download``, and the ``CrawlerConfig`` it
builds."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePath
from types import GenericAlias
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, ValidationError, create_model

from p2pwatch.adapters.driven.config.validation_problems import (
    moved_key,
    removed_key,
    renamed_key,
    validation_problems,
)
from p2pwatch.domain.config_defaults import (
    DEFAULT_AMULE_URL,
    DEFAULT_LOG_LEVEL,
    DEFAULT_NODE_PREFIX,
    DEFAULT_NOTIFICATION_TIMEOUT_SECONDS,
    DEFAULT_SOURCE_PERIOD_GAP,
)
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.config_value_error import ConfigValueError
from p2pwatch.domain.crawler_config import (
    BackoffConfig,
    CrawlerConfig,
    DownloadConfig,
    NotificationTarget,
    ObservabilityConfig,
    SearchConfig,
    WebuiConfig,
    cross_value_problems,
    parse_download,
)
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.observability.policy import Audience

_FILE_NAME = "crawler.yml"

# Coherent bounds for a P2P watch: a day for a delay (operator, 2026-10-13).
_A_DAY_SECONDS = 86_400

_Seconds = Annotated[float, Field(gt=0, le=_A_DAY_SECONDS)]
_Text = Annotated[str, Field(min_length=1)]


class _BackoffSchema(BaseModel, extra="forbid", strict=True, allow_inf_nan=False):
    base_seconds: _Seconds
    cap_seconds: _Seconds
    factor: Annotated[float, Field(ge=1)]
    jitter_ratio: Annotated[float, Field(ge=0)]


class _SearchSchema(BaseModel, extra="forbid", strict=True, allow_inf_nan=False):
    keywords: Annotated[list[_Text], Field(min_length=1)]
    backoff: _BackoffSchema


# Every refusing field is built, since vulture reads a field nothing reads as dead code.
_REMOVED = removed_key(_FILE_NAME)


class _WebuiKeys(BaseModel, extra="forbid", strict=True, allow_inf_nan=False):
    amule_url: _Text = DEFAULT_AMULE_URL
    source_period_gap_seconds: _Seconds = DEFAULT_SOURCE_PERIOD_GAP.total_seconds()


# The bind is fixed in the composition ring: 4.x's host and port were ignored.
_WEBUI_REFUSED: dict[str, Any] = {key: (_REMOVED, None) for key in ("enabled", "host", "port")}
_WebuiSchema = create_model("_WebuiSchema", __base__=_WebuiKeys, **_WEBUI_REFUSED)


class _NotificationKeys(BaseModel, extra="forbid", strict=True):
    url: _Text
    audience: Literal["community", "operations"]
    node_prefix: bool = DEFAULT_NODE_PREFIX


_NOTIFICATION_RENAMED: dict[str, Any] = {
    "tag": (renamed_key("audience", file_name=_FILE_NAME), None)
}
_NotificationSchema = create_model(
    "_NotificationSchema", __base__=_NotificationKeys, **_NOTIFICATION_RENAMED
)


class _ObservabilityKeys(BaseModel, extra="forbid", strict=True, allow_inf_nan=False):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = DEFAULT_LOG_LEVEL
    notification_timeout_seconds: _Seconds = DEFAULT_NOTIFICATION_TIMEOUT_SECONDS
    notifications: list[_NotificationKeys] = Field(default_factory=list)


_OBSERVABILITY_REFUSED: dict[str, Any] = {
    "metrics": (_REMOVED, None),
    # list[_NotificationSchema], which mypy refuses since the schema is a variable.
    "notifications": (GenericAlias(list, _NotificationSchema), Field(default_factory=list)),
}
_ObservabilitySchema = create_model(
    "_ObservabilitySchema", __base__=_ObservabilityKeys, **_OBSERVABILITY_REFUSED
)


class _RootKeys(BaseModel, extra="forbid", strict=True, allow_inf_nan=False):
    shutdown_deadline_seconds: _Seconds
    amule_api_password: _Text
    catalog_db_path: _Text
    local_db_path: _Text
    search: _SearchSchema
    # Their schemas in CrawlerConfigSchema, which add the refusing keys.
    observability: _ObservabilityKeys
    webui: _WebuiKeys


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

_FIELDS: dict[str, Any] = (
    # Read by the domain's parse, until its schema.
    {"download": (dict[str, Any], Field(default_factory=dict))}
    | {"observability": (_ObservabilitySchema, Field(default_factory=_ObservabilitySchema))}
    | {"webui": (_WebuiSchema, Field(default_factory=_WebuiSchema))}
    | {key: (_REMOVED, None) for key in _REMOVED_KEYS}
    | {"backoff": (moved_key("search.backoff", file_name=_FILE_NAME), None)}
)
CrawlerConfigSchema = create_model("CrawlerConfigSchema", __base__=_RootKeys, **_FIELDS)


def crawler_config_from_document(document: dict[str, Any], *, file_path: PurePath) -> CrawlerConfig:
    """``document``'s ``CrawlerConfig``; ``InvalidConfigError`` with every problem of its values
    but download's first, or once they hold, every problem across its values."""
    problems: list[ConfigProblem] = []
    try:
        root = CrawlerConfigSchema.model_validate(document)
    except ValidationError as error:
        problems.extend(validation_problems(error, file_path=file_path))
        root = None
    download = _download(document, file_path=file_path, problems=problems)
    if root is None or download is None:
        raise InvalidConfigError(tuple(problems))
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
        download=download.value,
        webui=WebuiConfig(
            amule_url=root.webui.amule_url,
            source_period_gap=timedelta(seconds=root.webui.source_period_gap_seconds),
        ),
    )
    if rule_problems := cross_value_problems(crawler_config, file_path=file_path):
        raise InvalidConfigError(rule_problems)
    return crawler_config


def _observability(observability: _ObservabilityKeys) -> ObservabilityConfig:
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


@dataclass(kw_only=True, frozen=True)
class _Parsed:
    value: DownloadConfig | None  # apart from None, which a disabled download parses to


def _download(
    document: dict[str, Any], *, file_path: PurePath, problems: list[ConfigProblem]
) -> _Parsed | None:
    """The domain's parse of ``download``, whether the root holds or not; ``None`` with its problem
    appended to ``problems``, or when the section is no mapping, which the root's schema refuses."""
    section = document.get("download", {})
    if not isinstance(section, dict):
        return None
    try:
        return _Parsed(value=parse_download(section))
    except ConfigValueError as error:
        problems.append(ConfigProblem(file_path=file_path, key=error.key, message=error.message))
        return None
