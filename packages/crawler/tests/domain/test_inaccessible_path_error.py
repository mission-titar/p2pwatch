from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError


def test_an_inaccessible_path_is_an_exception_carrying_its_message() -> None:
    assert issubclass(InaccessiblePathError, Exception)
    assert str(InaccessiblePathError("/data: gone")) == "/data: gone"
