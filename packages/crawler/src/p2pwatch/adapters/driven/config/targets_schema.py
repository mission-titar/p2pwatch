"""Reads ``targets.yml``'s document into the domain's targets."""

from pathlib import PurePath
from typing import Any

from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.models import TargetSegment
from p2pwatch.domain.matching.validation import MatchingConfigError, parse_targets


def targets_from_document(
    document: dict[str, Any], *, file_path: PurePath
) -> tuple[TargetSegment, ...]:
    """``document``'s targets; ``InvalidConfigError`` with its problem."""
    try:
        return parse_targets(document)
    except MatchingConfigError as error:
        problem = ConfigProblem(file_path=file_path, key=None, message=str(error))
        raise InvalidConfigError((problem,)) from error
