"""``targets.yml`` as written, read by pydantic, and the targets it builds."""

from pathlib import PurePath
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, Field, ValidationError

from p2pwatch.adapters.driven.config.validation_problems import (
    refuse_control_character,
    validation_problems,
)
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.models import LOST, TargetSegment, TargetStatus
from p2pwatch.domain.matching.validation import duplicate_targets


class _SegmentSchema(BaseModel, extra="forbid", strict=True):
    letter: Annotated[str, AfterValidator(refuse_control_character)]
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
    they hold, every duplicate target."""
    try:
        schema = TargetsSchema.model_validate(document)
    except ValidationError as error:
        raise InvalidConfigError(validation_problems(error, file_path=file_path)) from error
    located = [
        (
            f"episodes[{episode_index}].segments[{segment_index}]",
            TargetSegment(
                season=episode.season,
                seasonal_number=episode.seasonal_number,
                absolute_number=episode.absolute_number,
                letter=segment.letter,
                title=segment.title,
                status=segment.status,
            ),
        )
        for episode_index, episode in enumerate(schema.episodes)
        for segment_index, segment in enumerate(episode.segments)
    ]
    locations = [location for location, _ in located]
    targets = tuple(target for _, target in located)
    if duplicates := duplicate_targets(targets):
        raise InvalidConfigError(
            tuple(
                ConfigProblem(
                    file_path=file_path,
                    key=locations[duplicate.index],
                    message=f"same target_id as {locations[duplicate.first_index]}, "
                    "letters compared upper-cased",
                )
                for duplicate in duplicates
            )
        )
    return targets
