"""The guard the catalog's writers run before a write: a ``native_id`` in the v0.5.0 canon."""

import re

from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError
from p2pwatch.domain.file_key import FileKey

_CANONICAL_HASH_RE = re.compile(r"[0-9a-f]{32}\Z")


def require_canonical_native_id(file: FileKey) -> None:
    """Raises ``PersistenceError`` unless ``file``'s ``native_id`` is 32 lowercase hex digits."""
    if not _CANONICAL_HASH_RE.fullmatch(file.native_id):
        raise PersistenceError(f"non-canonical eD2k hash: {file.native_id!r}")
