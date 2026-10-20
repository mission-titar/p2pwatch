"""What the crawler expects from any client that downloads; its errors are in ``client_errors``.

Protocol stubs stay on ONE line: a body on a second one is an uncovered branch.
"""

from dataclasses import dataclass
from typing import Protocol

from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey


@dataclass(frozen=True)
class DownloadRequest:
    file: FileKey
    filename: str
    size_bytes: int


class DownloadClient(Protocol):
    """``downloads`` returns every download the client knows, completed ones included."""

    async def start(self, request: DownloadRequest) -> None: ...

    async def downloads(self) -> tuple[DownloadStatus, ...]: ...
