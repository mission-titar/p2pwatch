"""Decides when to rebuild an object holding state in memory, such as the aMule client and its
session: when a bugs rule of one of its parts turns failing, three rebuilds in vain at most."""

from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.work_components import BUGS

# Past three, a rebuild is taken to repair nothing, as an OTP supervisor bounds its restarts.
REBUILDS_IN_VAIN_AT_MOST = 3

# Rebuilt: a bugs rule turning failing again counts that rebuild in vain.
type _Phase = Literal["running", "restarting", "rebuilt", "given up"]


class _Restarts:
    """The restarts of one object: where the latest is, and how many rebuilds were in vain."""

    def __init__(
        self,
        restartable: Restartable[SupervisedWork],
        *,
        components: tuple[Component, ...],
        logger: Logger,
    ) -> None:
        self.restartable = restartable
        self.components = components
        self.phase: _Phase = "running"
        self.in_vain = 0
        self._logger = logger

    def count_in_vain(self) -> bool:
        """Counts one rebuild in vain; whether to rebuild again, never past three."""
        self.in_vain += 1
        if self.in_vain < REBUILDS_IN_VAIN_AT_MOST:
            return True
        self.phase = "given up"
        message = "%s not restarted again: %d rebuilds in vain"
        self._logger.error(message, self.restartable, self.in_vain)
        return False


class RestartRequest:
    """The restart of one object, such as the aMule client: the supervisor stops the works over it,
    has it rebuilt, then says how the rebuild ended."""

    def __init__(self, restarts: _Restarts) -> None:
        self.restartable = restarts.restartable
        self.components = restarts.components  # its parts, every work over it recorded on some
        self._restarts = restarts

    def rebuilt(self) -> None:
        """Forgets the bugs of its parts, their other rules kept, so an open alert stays open; a
        bugs rule failing again counts this rebuild in vain."""
        for component in self.components:
            component.forget(BUGS)
        self._restarts.phase = "rebuilt"

    def rebuild_raised(self) -> bool:
        """Counts this rebuild in vain; whether to try it again."""
        return self._restarts.count_in_vain()


# Restarts ``request``'s object, as the supervisor does, in a task of its own.
class RestartRunner(Protocol):
    def __call__(self, request: RestartRequest, /) -> None: ...


class RestartPolicy:
    """Restarts an object such as the aMule client when a bugs rule of one of its parts turns
    failing, three rebuilds in vain at most, the count reset once its parts are healthy again."""

    def __init__(
        self,
        *,
        components_of: Mapping[Restartable[SupervisedWork], Sequence[Component]],
        components_restarting_nothing: Sequence[Component] = (),
        works: Sequence[SupervisedWork],
        restart: RestartRunner,
        logger: Logger,
    ) -> None:
        self._restarts_of: dict[Component, _Restarts] = {}
        for restartable, components in components_of.items():
            # A channel's part is recorded on by each of its searches: named once.
            each_once = tuple(dict.fromkeys(components))
            restarts = _Restarts(restartable, components=each_once, logger=logger)
            for component in each_once:
                if (other := self._restarts_of.get(component)) is not None:
                    of_both = f"{other.restartable} and of {restartable}"
                    raise ValueError(f"{component.name}: a part of {of_both}")
                self._restarts_of[component] = restarts
        # Parts nothing can rebuild yet, such as the webui's: their bugs are only logged.
        self._restarting_nothing = frozenset(components_restarting_nothing)
        for supervised in works:
            self._refuse_unless_over_an_object(supervised)
        self._restart = restart
        self._logger = logger

    def _refuse_unless_over_an_object(self, supervised: SupervisedWork) -> None:
        """Refuses a work no restart would stop: one whose turns are recorded on no part, or on a
        part of no object."""
        if not supervised.components:
            raise ValueError(f"{supervised.work}: recorded on no part, so over no object")
        for component in supervised.components:
            if component not in self._restarts_of and component not in self._restarting_nothing:
                of_no_object = f"{component.name}, a part of no object"
                raise ValueError(f"{supervised.work}: recorded on {of_no_object}")

    async def __call__(self, transition: HealthTransition) -> None:
        """Takes one change of health, such as a search's bugs turning failing."""
        if transition.rule is not BUGS or transition.component in self._restarting_nothing:
            return
        # Every other part a turn is recorded on is an object's: refused at construction otherwise.
        restarts = self._restarts_of[transition.component]
        if transition.current is HealthState.FAILING:
            self._on_failing(transition.component, restarts=restarts)
        elif all(part.state(BUGS) is HealthState.HEALTHY for part in restarts.components):
            restarts.phase, restarts.in_vain = "running", 0

    def _on_failing(self, component: Component, *, restarts: _Restarts) -> None:
        bugs_in = f"bugs in {component.name}"
        if restarts.phase == "rebuilt":
            if not restarts.count_in_vain():
                return
            in_vain = f"{restarts.in_vain} of {REBUILDS_IN_VAIN_AT_MOST} rebuilds in vain"
            self._logger.warning(
                "restarting %s again, %s: %s", restarts.restartable, in_vain, bugs_in
            )
        elif restarts.phase == "running":
            self._logger.warning("restarting %s: %s", restarts.restartable, bugs_in)
        else:
            return  # a restart under way, or none to come
        restarts.phase = "restarting"
        self._restart(RestartRequest(restarts))
