from p2pwatch.domain.declared_failure import DeclaredFailure


def test_a_declared_failure_is_an_exception_carrying_its_message() -> None:
    assert issubclass(DeclaredFailure, Exception)
    assert str(DeclaredFailure("amuled refused the search")) == "amuled refused the search"
