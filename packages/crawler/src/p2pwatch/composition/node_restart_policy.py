"""The node's restart policy, over the objects it can rebuild: the aMule client, the webui and the
notifier."""

from collections.abc import Mapping, Sequence

from p2pwatch.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.domain.health.component import Component


def node_restart_policy(
    works_of: Mapping[Restartable[SupervisedWork], Sequence[SupervisedWork]],
    *,
    parts_without_works: Mapping[Restartable[SupervisedWork], Sequence[Component]],
    supervisor: Supervisor,
) -> RestartPolicy:
    """Has ``supervisor`` rebuild an object, such as the webui, when a bugs rule of one of its
    parts turns failing: a part its first ``works_of`` are recorded on, or one of its
    ``parts_without_works``, such as the notifier's, which the dispatcher records each send on."""
    # A rebuild builds every work over its object anew: each of their parts is that object's.
    components_of = {
        restartable: [part for supervised in works for part in supervised.components]
        for restartable, works in works_of.items()
    }
    for restartable, parts in parts_without_works.items():
        components_of[restartable] = [*components_of.get(restartable, ()), *parts]
    return RestartPolicy(
        components_of=components_of,
        works=[supervised for works in works_of.values() for supervised in works],
        restart=supervisor.restart,
        logger=StdlibLogger(RestartPolicy.__module__),
    )
