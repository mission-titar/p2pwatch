from pathlib import PurePath

import pytest

from p2pwatch.adapters.driven.config.targets_schema import targets_from_document
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.models import TargetSegment

_FILE = PurePath("/srv/targets.yml")


def test_a_document_gives_its_targets() -> None:
    document = {
        "episodes": [
            {
                "season": 2,
                "seasonal_number": 11,
                "absolute_number": 62,
                "segments": [{"letter": "a", "title": "La Grenouille Cosmique"}],
            }
        ]
    }
    assert targets_from_document(document, file_path=_FILE) == (
        TargetSegment(
            season=2,
            seasonal_number=11,
            absolute_number=62,
            letter="a",
            title="La Grenouille Cosmique",
        ),
    )


def test_a_wrong_document_is_refused_with_its_problem() -> None:
    with pytest.raises(InvalidConfigError) as refusal:
        targets_from_document({"episodes": "nope"}, file_path=_FILE)
    assert refusal.value.problems == (
        ConfigProblem(file_path=_FILE, key=None, message="'episodes' section: list expected"),
    )
