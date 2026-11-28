"""The node's health as the tests of the steps that record checks or open alerts build it."""

from p2pwatch.adapters.driven.in_memory_open_alert_store import InMemoryOpenAlertStore
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.open_alert_writer import OpenAlertWriter
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes


def build_node_health(
    *,
    observability_dispatcher: ObservabilityDispatcher | None = None,
    logger: Logger | None = None,
    open_alert_writer: OpenAlertWriter | None = None,
) -> NodeHealth:
    """The node's health over the dispatcher, the log and the alerts open a test reads, such as
    the alerts a status watcher's rules dispatched, over fakes for those it does not."""
    return NodeHealth(
        logger=logger or FakeLogger(),
        observability_dispatcher=observability_dispatcher or ObservabilityOverFakes().dispatcher,
        open_alert_writer=open_alert_writer or InMemoryOpenAlertStore(),
    )
