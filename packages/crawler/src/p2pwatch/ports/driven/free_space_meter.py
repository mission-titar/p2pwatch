"""``FreeSpaceMeter`` port: free space on the filesystem amuled writes to (disk-cap spec §1).

PORTS layer. The admission rule needs a MEASURED free-space figure, and ``statvfs`` is I/O:
the pure ``decide_download`` receives the number, it never reads it. Reading filesystem
metadata is not reading a file's bytes, so the "the crawler never reads the downloaded bytes"
invariant holds, and the mount that backs this is read-only.
"""

from abc import ABC, abstractmethod


class FreeSpaceMeter(ABC):
    """Measures the free space the download loop admits a download against."""

    @abstractmethod
    def free_bytes(self) -> int:
        """The free bytes of the filesystem the client writes to."""
