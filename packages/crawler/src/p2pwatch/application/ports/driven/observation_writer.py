"""``ObservationWriter``: appends to the catalog, append-only (spec data-model §4);
synchronous, as every catalog port (spec data-model §3)."""

from abc import ABC, abstractmethod

from p2pwatch.domain.observation import FileObservation


class ObservationWriter(ABC):
    """Appends what the network reported of a file."""

    @abstractmethod
    def record_observation(self, observation: FileObservation) -> None:
        """Appends ``observation``."""
