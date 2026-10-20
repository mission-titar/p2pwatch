"""What the crawler expects from a client that lists the sources of its downloads."""

from abc import ABC, abstractmethod

from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import SourceReading


class SourceClient(ABC):
    """Lists the sources of the client's downloads."""

    @abstractmethod
    async def sources(self, file: FileKey) -> tuple[SourceReading, ...]:
        """The sources of one of the client's downloads, none once it left."""
