"""``targets.yml`` as written, read by pydantic, and the targets it builds."""

from pathlib import PurePath
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, Field, ValidationError
from pydantic_core import PydanticCustomError

from p2pwatch.adapters.driven.config.validation_problems import validation_problems
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.models import LOST, TargetSegment, TargetStatus
from p2pwatch.domain.matching.validation import (
    MatchingConfigError,
    has_control_character,
    parse_targets,
)


def _refuse_control_character(letter: str) -> str:
    if has_control_character(letter):
        raise PydanticCustomError("control_character", "holds a control character")
    return letter


class _SegmentSchema(BaseModel, extra="forbid", strict=True):
    letter: Annotated[str, AfterValidator(_refuse_control_character)]
    title: str
    status: TargetStatus = LOST


class _EpisodeSchema(BaseModel, extra="forbid", strict=True):
    season: int
    seasonal_number: int
    absolute_number: int
    segments: list[_SegmentSchema] = Field(default_factory=list)


class TargetsSchema(BaseModel, extra="forbid", strict=True):
    episodes: list[_EpisodeSchema]


def targets_from_document(
    document: dict[str, Any], *, file_path: PurePath
) -> tuple[TargetSegment, ...]:
    """``document``'s targets; ``InvalidConfigError`` with every problem of its values, or once
    they hold, its first duplicate target."""
    try:
        schema = TargetsSchema.model_validate(document)
    except ValidationError as error:
        raise InvalidConfigError(validation_problems(error, file_path=file_path)) from error
    # The domain builds the targets until the next block, from the checked values.
    checked = {
        "episodes": [
            {
                "season": episode.season,
                "seasonal_number": episode.seasonal_number,
                "absolute_number": episode.absolute_number,
                "segments": [
                    {"letter": segment.letter, "title": segment.title, "status": segment.status}
                    for segment in episode.segments
                ],
            }
            for episode in schema.episodes
        ]
    }
    try:
        return parse_targets(checked)
    except MatchingConfigError as error:
        problem = ConfigProblem(file_path=file_path, key=None, message=str(error))
        raise InvalidConfigError((problem,)) from error
