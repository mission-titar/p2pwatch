from p2pwatch.domain.store_error import StoreError


def test_store_error_is_an_exception() -> None:
    assert issubclass(StoreError, Exception)
    error = StoreError("boum")
    assert str(error) == "boum"
