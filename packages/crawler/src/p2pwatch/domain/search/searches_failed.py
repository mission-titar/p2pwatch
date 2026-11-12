"""A channel's searches the network refused, counted over its search turns (spec v5 lot 4, D10)."""

from p2pwatch.domain.client_errors import SearchFailedError
from p2pwatch.domain.health.health_condition import HealthCondition
from p2pwatch.domain.health.outcome import OutcomeSource

SEARCHES = OutcomeSource(name="a search turn's success or declared failure")
SEARCHES_FAILED = HealthCondition(
    name="searches failed", source=SEARCHES, counting=SearchFailedError
)
