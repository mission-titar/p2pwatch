from pathlib import PurePath

import pytest

from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.invalid_config import InvalidConfigError

_PROBLEMS = (
    ConfigProblem(file_path=PurePath("/srv/crawler.yml"), key="search.keywords", message="missing"),
    ConfigProblem(
        file_path=PurePath("/srv/matcher.yml"), key=None, message="'rules' section: list expected"
    ),
)


def test_a_refused_config_carries_every_problem_in_their_order() -> None:
    assert InvalidConfigError(_PROBLEMS).problems == _PROBLEMS


def test_a_refused_config_holds_at_least_one_problem() -> None:
    with pytest.raises(ValueError, match="^an invalid config holds at least one problem$"):
        InvalidConfigError(())
