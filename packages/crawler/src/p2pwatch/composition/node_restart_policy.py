"""The node's restart policy, over the objects it can rebuild: the aMule client and the webui."""

from collections.abc import Mapping, Sequence

from p2pwatch.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import SupervisedWork


def node_restart_policy(
    works_of: Mapping[Restartable[SupervisedWork], Sequence[SupervisedWork]],
    *,
    supervisor: Supervisor,
) -> RestartPolicy:
    """Has ``supervisor`` rebuild an object, such as the webui, when a bugs rule of a part its
    first ``works_of`` are recorded on turns failing."""
    return RestartPolicy(
        # A rebuild builds every work over its object anew: each of their parts is that object's.
        components_of={
            restartable: [part for supervised in works for part in supervised.components]
            for restartable, works in works_of.items()
        },
        works=[supervised for works in works_of.values() for supervised in works],
        restart=supervisor.restart,
        logger=StdlibLogger(RestartPolicy.__module__),
    )
