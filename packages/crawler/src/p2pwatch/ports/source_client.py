"""What the crawler expects from a client that lists the sources of its downloads.

Protocol stubs stay on ONE line: a body on a second one is an uncovered branch.
"""

from typing import Protocol

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import SourceReading


class SourceClient(Protocol):
    """``sources`` reads the sources of one of the client's downloads, none once it left."""

    async def sources(self, file: FileKey) -> tuple[SourceReading, ...]: ...
