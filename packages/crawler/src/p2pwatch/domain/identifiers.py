"""The identifiers this package reads, each a type of its own so that mypy refuses a swap."""

from typing import NewType

NodeId = NewType("NodeId", str)
ClientName = NewType("ClientName", str)
Channel = NewType("Channel", str)
Keyword = NewType("Keyword", str)
FileId = NewType("FileId", bytes)
SourceId = NewType("SourceId", bytes)
