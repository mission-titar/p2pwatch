from p2pwatch.domain.invalid_config import InvalidConfigError


def test_an_error_on_a_key_carries_its_key_path_apart_and_prints_it_first() -> None:
    error = InvalidConfigError("search.keywords", "non-empty list of strings expected")
    assert (error.key, error.message) == ("search.keywords", "non-empty list of strings expected")
    assert str(error) == "search.keywords: non-empty list of strings expected"


def test_an_error_on_no_key_prints_its_message_alone() -> None:
    error = InvalidConfigError(None, "'episodes' section: list expected")
    assert error.key is None
    assert str(error) == "'episodes' section: list expected"
