from typing import NoReturn

from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.file_key import FileKey


class FakeDecisionReader(DecisionReader):
    """The download loop's decision reads, scripted: its candidates."""

    def __init__(self, *, candidates: tuple[DownloadCandidate, ...] = ()) -> None:
        self._candidates = candidates

    def read_latest_decisions(self, file: FileKey) -> NoReturn:
        raise AssertionError("the download loop reads no file's decisions")

    def read_download_candidates(self) -> tuple[DownloadCandidate, ...]:
        return self._candidates
