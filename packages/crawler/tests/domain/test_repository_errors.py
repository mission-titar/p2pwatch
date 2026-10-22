from p2pwatch.domain.repository_errors import StoreError


def test_repository_error_is_an_exception() -> None:
    assert issubclass(StoreError, Exception)
    error = StoreError("boum")
    assert str(error) == "boum"
