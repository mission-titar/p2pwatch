import pytest

from p2pwatch.domain.catalog_copy_error import CatalogCopyError
from p2pwatch.domain.client_errors import ClientAuthError, ClientError
from p2pwatch.domain.expected_error import ExpectedError
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError
from p2pwatch.domain.store_error import StoreError


# Written by hand: a new driven port's error is missed until it is added here.
@pytest.mark.parametrize(
    "error",
    [ClientError, ClientAuthError, StoreError, InaccessiblePathError, CatalogCopyError],
)
def test_every_error_a_driven_port_declares_is_an_expected_error(error: type[Exception]) -> None:
    assert issubclass(error, ExpectedError)
