"""A file the download loop may queue."""

from dataclasses import dataclass

from p2pwatch.domain.file_key import FileKey


@dataclass(frozen=True)
class DownloadCandidate:
    """A file whose latest verdict for ``target_id`` is tier=download, for the download loop."""

    file: FileKey
    target_id: str
