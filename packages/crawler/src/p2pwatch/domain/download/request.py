"""A file asked of a client to download."""

from dataclasses import dataclass

from p2pwatch.domain.file_key import FileKey


@dataclass(frozen=True)
class DownloadRequest:
    file: FileKey
    filename: str
    size_bytes: int
