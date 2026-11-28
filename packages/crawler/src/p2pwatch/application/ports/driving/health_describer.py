"""``HealthDescriber``: describes the node's health, for ``/health``."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(kw_only=True, frozen=True)
class HealthDescription:
    unrepaired_objects: tuple[str, ...]  # by name, "client amuled": the node is up while none


class HealthDescriber(ABC):
    """Describes the node's health, from any thread."""

    @abstractmethod
    def describe_health(self) -> HealthDescription:
        """The objects whose alert of being left unrepaired is open; an outage's alert is not."""
