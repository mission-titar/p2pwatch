import pytest

from p2pwatch.domain.catalog_copy_error import CatalogCopyError
from p2pwatch.domain.client_errors import ClientError
from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError
from p2pwatch.domain.store_error import StoreError


def test_a_declared_failure_is_an_exception_carrying_its_message() -> None:
    assert issubclass(DeclaredFailure, Exception)
    assert str(DeclaredFailure("amuled refused the search")) == "amuled refused the search"


@pytest.mark.parametrize(
    "failure", [ClientError, StoreError, CatalogCopyError, InaccessiblePathError]
)
def test_every_failure_a_driven_port_declares_is_a_declared_failure(failure: type) -> None:
    assert issubclass(failure, DeclaredFailure)
