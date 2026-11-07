"""``crawler.yml`` as written, its root read by pydantic, and the ``CrawlerConfig`` it builds."""

from pathlib import PurePath
from typing import Any

from pydantic import ConfigDict, ValidationError, create_model

from p2pwatch.adapters.driven.config.validation_problems import (
    moved_key,
    removed_key,
    validation_problems,
)
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.config_value_error import ConfigValueError
from p2pwatch.domain.crawler_config import CrawlerConfig, parse_crawler_config
from p2pwatch.domain.invalid_config import InvalidConfigError

_FILE_NAME = "crawler.yml"

# Read by the domain's parse, whatever their value here.
_READ_KEYS = (
    "amule_api_password",
    "catalog_db_path",
    "download",
    "local_db_path",
    "observability",
    "search",
    "shutdown_deadline_seconds",
    "webui",
)

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
    {key: (Any, None) for key in _READ_KEYS}
    | {key: (removed_key(_FILE_NAME), None) for key in _REMOVED_KEYS}
    | {"backoff": (moved_key("search.backoff", file_name=_FILE_NAME), None)}
)
CrawlerConfigSchema = create_model(
    "CrawlerConfigSchema", __config__=ConfigDict(extra="forbid"), **_FIELDS
)


def crawler_config_from_document(document: dict[str, Any], *, file_path: PurePath) -> CrawlerConfig:
    """``document``'s ``CrawlerConfig``; ``InvalidConfigError`` with every key nothing reads, and
    the parse's first problem."""
    problems: list[ConfigProblem] = []
    try:
        CrawlerConfigSchema.model_validate(document)
    except ValidationError as error:
        problems.extend(validation_problems(error, file_path=file_path))
    try:
        crawler_config = parse_crawler_config(document)
    except ConfigValueError as error:
        problem = ConfigProblem(file_path=file_path, key=error.key, message=error.message)
        raise InvalidConfigError((*problems, problem)) from error
    if problems:
        raise InvalidConfigError(tuple(problems))
    return crawler_config
