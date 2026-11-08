"""Reads ``matcher.yml``'s document into the domain's matcher config."""

from pathlib import PurePath
from typing import Any

from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.config import MatcherConfig
from p2pwatch.domain.matching.validation import MatchingConfigError, parse_matcher_config


def matcher_config_from_document(document: dict[str, Any], *, file_path: PurePath) -> MatcherConfig:
    """``document``'s matcher config; ``InvalidConfigError`` with its problem."""
    try:
        return parse_matcher_config(document)
    except MatchingConfigError as error:
        problem = ConfigProblem(file_path=file_path, key=None, message=str(error))
        raise InvalidConfigError((problem,)) from error
