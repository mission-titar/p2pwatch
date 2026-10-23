from p2pwatch.domain.invalid_config import InvalidConfigError


def test_an_error_on_a_key_carries_its_key_path_apart_and_prints_it_first() -> None:
    error = InvalidConfigError("search.keywords", "non-empty list of strings expected")
    assert (error.key, error.message) == ("search.keywords", "non-empty list of strings expected")
    assert str(error) == "search.keywords: non-empty list of strings expected"


def test_an_error_on_no_key_prints_its_message_alone() -> None:
    error = InvalidConfigError(None, "key 'port_sync' was removed, delete it from crawler.yml")
    assert error.key is None
    assert str(error) == "key 'port_sync' was removed, delete it from crawler.yml"
