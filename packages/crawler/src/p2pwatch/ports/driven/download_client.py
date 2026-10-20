"""What the crawler expects from any client that downloads; its errors are in ``client_errors``."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey


@dataclass(frozen=True)
class DownloadRequest:
    file: FileKey
    filename: str
    size_bytes: int


class DownloadClient(ABC):
    """Queues downloads and reports them."""

    @abstractmethod
    async def start(self, request: DownloadRequest) -> None:
        """Queues the requested file."""

    @abstractmethod
    async def downloads(self) -> tuple[DownloadStatus, ...]:
        """Every download the client knows, completed ones included."""
