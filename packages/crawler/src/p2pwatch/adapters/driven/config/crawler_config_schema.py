"""``crawler.yml`` as written, its root read by pydantic, and the ``CrawlerConfig`` it builds."""

from dataclasses import dataclass
from pathlib import PurePath
from typing import Annotated, Any, Protocol

from pydantic import BaseModel, Field, ValidationError, create_model

from p2pwatch.adapters.driven.config.validation_problems import (
    moved_key,
    removed_key,
    validation_problems,
)
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.config_value_error import ConfigValueError
from p2pwatch.domain.crawler_config import (
    BackoffConfig,
    CrawlerConfig,
    SearchConfig,
    cross_value_problems,
    parse_download,
    parse_observability,
    parse_webui,
)
from p2pwatch.domain.invalid_config import InvalidConfigError

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


class _RootKeys(BaseModel, extra="forbid", strict=True, allow_inf_nan=False):
    shutdown_deadline_seconds: _Seconds
    amule_api_password: _Text
    catalog_db_path: _Text
    local_db_path: _Text
    search: _SearchSchema


# Read by the domain's section parses, until each section has its schema.
_SECTIONS = ("download", "observability", "webui")

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

# Built, since a field nothing reads would be dead code to vulture.
_FIELDS: dict[str, Any] = (
    {key: (dict[str, Any], Field(default_factory=dict)) for key in _SECTIONS}
    | {key: (removed_key(_FILE_NAME), None) for key in _REMOVED_KEYS}
    | {"backoff": (moved_key("search.backoff", file_name=_FILE_NAME), None)}
)
CrawlerConfigSchema = create_model("CrawlerConfigSchema", __base__=_RootKeys, **_FIELDS)


def crawler_config_from_document(document: dict[str, Any], *, file_path: PurePath) -> CrawlerConfig:
    """``document``'s ``CrawlerConfig``; ``InvalidConfigError`` with every problem of its root and
    the first of each section, or once they hold, every problem across its values."""
    problems: list[ConfigProblem] = []
    try:
        root = CrawlerConfigSchema.model_validate(document)
    except ValidationError as error:
        problems.extend(validation_problems(error, file_path=file_path))
        root = None
    sections = _Sections(document, file_path=file_path, problems=problems)
    observability = sections.parse("observability", parse=parse_observability)
    download = sections.parse("download", parse=parse_download)
    webui = sections.parse("webui", parse=parse_webui)
    if root is None or observability is None or download is None or webui is None:
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
        observability=observability.value,
        download=download.value,
        webui=webui.value,
    )
    if rule_problems := cross_value_problems(crawler_config, file_path=file_path):
        raise InvalidConfigError(rule_problems)
    return crawler_config


class _SectionParse[T](Protocol):
    def __call__(self, section: dict[str, Any], /) -> T: ...


@dataclass(kw_only=True, frozen=True)
class _Parsed[T]:
    value: T  # apart from None, which a disabled download parses to


class _Sections:
    """Runs each section's parse, whether the root holds or not, and keeps its problem."""

    def __init__(
        self, document: dict[str, Any], *, file_path: PurePath, problems: list[ConfigProblem]
    ) -> None:
        self._document = document
        self._file_path = file_path
        self._problems = problems

    def parse[T](self, key: str, *, parse: _SectionParse[T]) -> _Parsed[T] | None:
        """``parse``'s value, ``None`` when it refused or the section is no mapping, which the
        root's schema refuses."""
        section = self._document.get(key, {})
        if not isinstance(section, dict):
            return None
        try:
            return _Parsed(value=parse(section))
        except ConfigValueError as error:
            self._problems.append(
                ConfigProblem(file_path=self._file_path, key=error.key, message=error.message)
            )
            return None
