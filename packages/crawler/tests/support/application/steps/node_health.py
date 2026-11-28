"""The node's health as the tests of the steps that record checks build it."""

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes


def build_node_health(
    *,
    observability_dispatcher: ObservabilityDispatcher | None = None,
    logger: Logger | None = None,
) -> NodeHealth:
    """The node's health over the dispatcher and the log a test reads, such as the alerts a
    status watcher's rules dispatched, over fakes for those it does not."""
    return NodeHealth(
        logger=logger or FakeLogger(),
        observability_dispatcher=observability_dispatcher or ObservabilityOverFakes().dispatcher,
    )
