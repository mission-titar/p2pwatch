from pathlib import PurePath

import pytest

from p2pwatch.adapters.driven.config.matcher_config_schema import matcher_config_from_document
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.config import KeywordDefinition, MatcherConfig

_FILE = PurePath("/srv/matcher.yml")


def test_a_document_gives_its_matcher_config() -> None:
    document = {"tokens": {"titar": {"keyword": "mission titar"}}, "vetoes": ["titar"]}
    assert matcher_config_from_document(document, file_path=_FILE) == MatcherConfig(
        tokens={"titar": KeywordDefinition(phrase="mission titar")}, vetoes=("titar",)
    )


def test_a_wrong_document_is_refused_with_its_problem() -> None:
    with pytest.raises(InvalidConfigError) as refusal:
        matcher_config_from_document({"rules": "nope"}, file_path=_FILE)
    assert refusal.value.problems == (
        ConfigProblem(file_path=_FILE, key=None, message="'rules' section: list expected, got str"),
    )
