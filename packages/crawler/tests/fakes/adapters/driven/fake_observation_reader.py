from typing import NoReturn

from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.observation import FileObservation


class FakeObservationReader(ObservationReader):
    """The download loop's observation reads, scripted: its latest and best observations."""

    def __init__(
        self,
        *,
        observations: dict[str, FileObservation] | None = None,
        best: dict[str, FileObservation] | None = None,
    ) -> None:
        self._observations = observations or {}
        self._best = best or {}

    def read_latest_observation(self, file: FileKey) -> FileObservation | None:
        return self._observations.get(file.native_id)

    def read_best_observation(self, file: FileKey) -> FileObservation | None:
        return self._best.get(file.native_id)

    def read_known_filenames(self, file: FileKey) -> NoReturn:
        raise AssertionError("the download loop reads no file's filenames")
