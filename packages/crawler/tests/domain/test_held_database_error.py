from p2pwatch.domain.held_database_error import HeldDatabaseError
from p2pwatch.domain.store_error import StoreError


def test_a_held_database_is_a_store_error() -> None:
    assert issubclass(HeldDatabaseError, StoreError)
