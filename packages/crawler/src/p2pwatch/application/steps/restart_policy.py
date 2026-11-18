"""Decides when to rebuild an object holding state in memory, such as the aMule client and its
session: when a bugs rule of one of its parts turns failing, three rebuilds in vain at most."""

from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.domain.health.external_dependency import ExternalDependency, HealthTransition
from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.work_dependencies import BUGS

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
        dependencies: tuple[ExternalDependency, ...],
        logger: Logger,
    ) -> None:
        self.restartable = restartable
        self.dependencies = dependencies
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
        self.dependencies = restarts.dependencies  # its parts, every work over it recorded on some
        self._restarts = restarts

    def rebuilt(self) -> None:
        """Forgets the bugs of its parts, their other rules kept, so an open alert stays open; a
        bugs rule failing again counts this rebuild in vain."""
        for dependency in self.dependencies:
            dependency.forget(BUGS)
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
        dependencies_of: Mapping[Restartable[SupervisedWork], Sequence[ExternalDependency]],
        works: Sequence[SupervisedWork],
        restart: RestartRunner,
        logger: Logger,
    ) -> None:
        self._restarts_of: dict[ExternalDependency, _Restarts] = {}
        for restartable, dependencies in dependencies_of.items():
            # A channel's part is recorded on by each of its searches: named once.
            each_once = tuple(dict.fromkeys(dependencies))
            restarts = _Restarts(restartable, dependencies=each_once, logger=logger)
            for dependency in each_once:
                if (other := self._restarts_of.get(dependency)) is not None:
                    of_both = f"{other.restartable} and of {restartable}"
                    raise ValueError(f"{dependency.name}: a part of {of_both}")
                self._restarts_of[dependency] = restarts
        for supervised in works:
            self._refuse_unless_over_an_object(supervised)
        self._restart = restart
        self._logger = logger

    def _refuse_unless_over_an_object(self, supervised: SupervisedWork) -> None:
        """Refuses a work no restart would stop: one whose turns are recorded on no part, or on a
        part of no object."""
        if not supervised.dependencies:
            raise ValueError(f"{supervised.work}: recorded on no part, so over no object")
        for dependency in supervised.dependencies:
            if dependency not in self._restarts_of:
                of_no_object = f"{dependency.name}, a part of no object"
                raise ValueError(f"{supervised.work}: recorded on {of_no_object}")

    async def __call__(self, transition: HealthTransition) -> None:
        """Takes one change of health, such as a search's bugs turning failing."""
        if transition.rule is not BUGS:
            return
        # Every part a turn is recorded on is an object's: refused at construction otherwise.
        restarts = self._restarts_of[transition.dependency]
        if transition.current is HealthState.FAILING:
            self._on_failing(transition.dependency, restarts=restarts)
        elif all(part.state(BUGS) is HealthState.HEALTHY for part in restarts.dependencies):
            restarts.phase, restarts.in_vain = "running", 0

    def _on_failing(self, dependency: ExternalDependency, *, restarts: _Restarts) -> None:
        bugs_in = f"bugs in {dependency.name}"
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
