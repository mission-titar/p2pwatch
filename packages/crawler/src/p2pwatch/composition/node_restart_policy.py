"""The node's restart policy, over the objects it can rebuild: the aMule client, the webui and the
notifier."""

from collections.abc import Sequence

from p2pwatch.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.ports.driven.restartable_builder import RestartableBuilder
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import HeldRestartable, Supervisor
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.domain.health.component import Component

type _Held = HeldRestartable[Restartable[SupervisedWork]]


def node_restart_policy(
    objects: Sequence[_Held],
    *,
    notifier: _Held,
    observability_dispatcher: ObservabilityDispatcher,
    supervisor: Supervisor,
) -> RestartPolicy:
    """Has ``supervisor`` rebuild an object it holds, such as the webui, when a bugs rule of one
    of its parts turns failing: a part the works of one of ``objects`` are recorded on, or for
    ``notifier`` the part of each service the dispatcher records each send on."""
    # A rebuild builds every work over its object anew: each of their parts is that object's.
    components_of: dict[RestartableBuilder[Restartable[SupervisedWork]], Sequence[Component]] = {
        held.builder: [
            part for supervised in held.latest().works() for part in supervised.components
        ]
        for held in objects
    }
    # Read from the dispatcher: no other part could be the notifier's.
    components_of[notifier.builder] = observability_dispatcher.service_components()
    logger = StdlibLogger(RestartPolicy.__module__)
    for builder, parts in components_of.items():
        names = ", ".join(dict.fromkeys(part.name for part in parts)) or "no part"
        logger.debug("%s: rebuilt for bugs in %s", builder, names)
    return RestartPolicy(
        components_of=components_of,
        works=[supervised for held in objects for supervised in held.latest().works()],
        restart=supervisor.restart,
        logger=logger,
    )
