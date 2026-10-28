"""The identifiers this package carries, each a type of its own so that mypy refuses a swap."""

from typing import NewType

Uid = NewType("Uid", int)
Gid = NewType("Gid", int)
