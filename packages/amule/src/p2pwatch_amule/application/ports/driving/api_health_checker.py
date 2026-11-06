"""``ApiHealthChecker``: whether the crawler can drive aMule, as the container's healthcheck."""

from abc import ABC, abstractmethod


class ApiHealthChecker(ABC):
    """Checks amuleapi's health."""

    @abstractmethod
    def check_api_health(self) -> bool:
        """True when amuleapi answers and is linked to amuled, else False; never raises."""
