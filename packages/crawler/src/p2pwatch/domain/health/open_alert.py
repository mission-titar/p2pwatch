"""An alert open, as the node's health keeps it, with the instant it opened."""

from dataclasses import dataclass
from datetime import datetime

from p2pwatch.domain.health.external_dependency import HealthAlert


@dataclass(kw_only=True, frozen=True)
class OpenAlert:
    """An alert opened and not yet ended, with the wall-clock instant it opened: "amuled
    unreachable for 2 min" since 2026-06-12 14:02 UTC."""

    alert: HealthAlert
    opened_at: datetime
