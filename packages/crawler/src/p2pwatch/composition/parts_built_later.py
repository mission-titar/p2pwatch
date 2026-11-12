"""The parts built after those that reach them: the dispatcher records through the recorder, whose
subscribers it serves, and each owner adds its works to the supervisor, which runs its restarts."""

from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.supervisor import SupervisedWork, Supervisor
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.outcome import Outcome, OutcomeSource


class PartNotBuiltYetError(RuntimeError):
    """A part read before the composition set it: a bug of the build order."""

    def __init__(self, part: str) -> None:
        super().__init__(f"{part}, read before it is set")


class PartsBuiltLater:
    """Built first, set once the recorder and the supervisor are built; read at each use."""

    def __init__(self) -> None:
        self._health_recorder: HealthRecorder | None = None
        self._supervisor: Supervisor | None = None

    @property
    def health_recorder(self) -> HealthRecorder:
        if self._health_recorder is None:
            raise PartNotBuiltYetError("the health recorder")
        return self._health_recorder

    @health_recorder.setter
    def health_recorder(self, health_recorder: HealthRecorder) -> None:
        self._health_recorder = health_recorder

    @property
    def supervisor(self) -> Supervisor:
        if self._supervisor is None:
            raise PartNotBuiltYetError("the supervisor")
        return self._supervisor

    @supervisor.setter
    def supervisor(self, supervisor: Supervisor) -> None:
        self._supervisor = supervisor

    async def record(self, outcome: Outcome, *, on: Component, by: OutcomeSource) -> None:
        await self.health_recorder.record(outcome, on=on, by=by)

    def add_work(self, supervised: SupervisedWork, /) -> None:
        self.supervisor.add(supervised)
