import pytest

from p2pwatch.domain.catalog_copy_error import CatalogCopyError
from p2pwatch.domain.client_errors import ClientError
from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError
from p2pwatch.domain.store_error import StoreError


@pytest.mark.parametrize(
    "failure", [StoreError, InaccessiblePathError, CatalogCopyError, ClientError]
)
def test_each_failure_a_driven_port_declares_is_a_declared_failure(
    failure: type[Exception],
) -> None:
    assert issubclass(failure, DeclaredFailure)


def test_a_declared_failure_is_an_exception_carrying_its_message() -> None:
    assert issubclass(DeclaredFailure, Exception)
    assert str(DeclaredFailure("disk full")) == "disk full"
