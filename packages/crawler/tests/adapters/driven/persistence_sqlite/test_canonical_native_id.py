import pytest

from p2pwatch.adapters.driven.persistence_sqlite.canonical_native_id import (
    require_canonical_native_id,
)
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.domain.file_key import FileKey, Network


def test_a_lowercase_hex_hash_of_32_digits_is_canonical() -> None:
    require_canonical_native_id(
        FileKey(network=Network.ED2K, native_id="31d6cfe0d16ae931b73c59d7e0c089c0")
    )


@pytest.mark.parametrize(
    "native_id", ["31D6CFE0D16AE931B73C59D7E0C089C0", "a" * 31, "a" * 33, "a" * 32 + "\n"]
)
def test_any_other_native_id_raises_a_persistence_error(native_id: str) -> None:
    with pytest.raises(PersistenceError, match="non-canonical eD2k hash"):
        require_canonical_native_id(FileKey(network=Network.ED2K, native_id=native_id))
