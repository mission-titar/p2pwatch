from dataclasses import dataclass
from datetime import datetime

from p2pwatch.application.ports.driving.file_describer import FileDescriber, FileDescription
from p2pwatch.domain.identifiers import FileId


@dataclass(frozen=True)
class DescribeFileCall:
    """The arguments of one ``describe_file`` call."""

    file_id: FileId
    requested_since: datetime | None
    requested_until: datetime | None


class FakeFileDescriber(FileDescriber):
    """Describes any file as it is given, and keeps each call's arguments."""

    def __init__(self, file_description: FileDescription | None) -> None:
        self._file_description = file_description
        self.calls: list[DescribeFileCall] = []

    def describe_file(
        self,
        file_id: FileId,
        *,
        requested_since: datetime | None,
        requested_until: datetime | None,
    ) -> FileDescription | None:
        self.calls.append(DescribeFileCall(file_id, requested_since, requested_until))
        return self._file_description
