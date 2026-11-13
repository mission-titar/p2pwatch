"""The restart policy: a bugs condition entering failing restarts its component's owner, at most
three times in vain; every bugs condition of the owner's components healthy again resets the
count; each restart a request the supervisor completes."""

import asyncio

import pytest

from p2pwatch.application.ports.driven.state_owner import StateOwner
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.restart_policy import RestartPolicy, RestartRequest
from p2pwatch.domain.health.component import Component, ComponentLabels
from p2pwatch.domain.health.health_condition import BUGS, Health
from p2pwatch.domain.health.outcome import UNITS_OF_WORK, Outcome
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.status_reading import (
    STATUS_CONNECTED_FIELD,
    ChannelNotConnected,
    channel_component,
    client_component,
)
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.composition.fake_state_owner import FakeStateOwner

pytestmark = pytest.mark.asyncio

_CLIENT = ClientName("amuled")
_BUG = Outcome.bug("KeyError('channels')")


def _component(name: str) -> Component:
    return Component(name=name, labels=ComponentLabels(client_name=_CLIENT), conditions=(BUGS,))


class _Policy:
    """A policy over two components of one owner, fed through a recorder."""

    def __init__(self) -> None:
        self.logger = FakeLogger()
        self.owner = FakeStateOwner("client amuled")
        self.search, self.status = _component("search"), _component("status")
        self.policy = RestartPolicy(
            owners={self.search: self.owner, self.status: self.owner}, logger=self.logger
        )
        self.recorder = HealthRecorder(logger=FakeLogger(), subscribers=(self.policy,))
        self.latest: RestartRequest  # the latest request taken

    async def record(self, outcome: Outcome, *, on: Component, times: int) -> None:
        for _ in range(times):
            await self.recorder.record(outcome, on=on, by=UNITS_OF_WORK)

    async def fail(self, component: Component) -> None:
        await self.record(_BUG, on=component, times=3)

    async def rebuild(self) -> None:
        """What the supervisor does once the owner's restart built it anew."""
        self.latest.rebuilt()

    async def requested(self) -> list[StateOwner]:
        """The owners of the restarts requested so far, taken from the policy."""
        owners: list[StateOwner] = []
        while True:
            request = asyncio.ensure_future(self.policy.requested())
            await asyncio.sleep(0)  # noqa: TID251
            if not request.done():
                request.cancel()
                return owners
            self.latest = request.result()
            owners.append(self.latest.owner)


async def test_a_bugs_condition_entering_failing_requests_its_owner_s_restart() -> None:
    policy = _Policy()
    await policy.record(_BUG, on=policy.search, times=2)
    assert await policy.requested() == []

    await policy.record(_BUG, on=policy.search, times=1)

    assert await policy.requested() == [policy.owner]
    assert policy.logger.lines == [
        LoggedLine(level="warning", message="search, bugs failing: restarting client amuled")
    ]


async def test_a_component_failing_while_its_owner_restarts_requests_no_other_restart() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    await policy.fail(policy.status)
    assert await policy.requested() == [policy.owner]


async def test_a_bugs_condition_failing_again_after_a_restart_restarts_three_times_then_none() -> (
    None
):
    policy = _Policy()
    await policy.fail(policy.search)
    restarts = await policy.requested()
    for _ in range(3):
        await policy.rebuild()
        await policy.fail(policy.search)
        restarts += await policy.requested()

    assert restarts == [policy.owner] * 3
    assert policy.logger.lines[-1] == LoggedLine(
        level="error",
        message="client amuled: 3 useless restarts, its components failing; not restarted again",
    )


async def test_a_bug_elsewhere_in_the_owner_counts_against_the_same_restarts() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    for failing in (policy.status, policy.search, policy.status):
        await policy.requested()
        await policy.rebuild()
        await policy.fail(failing)
    assert await policy.requested() == []


async def test_every_bugs_condition_of_the_owner_healthy_again_resets_the_count() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    for _ in range(2):
        await policy.requested()
        await policy.rebuild()
        await policy.fail(policy.search)
    await policy.requested()
    await policy.rebuild()
    await policy.record(Outcome.success(), on=policy.status, times=3)
    await policy.record(Outcome.success(), on=policy.search, times=3)

    await policy.fail(policy.search)

    assert await policy.requested() == [policy.owner]  # a fourth restart: the count reset


async def test_an_owner_given_up_whose_works_heal_restarts_again_at_a_later_bug() -> None:
    # Its rebuilds succeeded, so its works run on: only the buggy turns fail (D1).
    policy = _Policy()
    await policy.fail(policy.search)
    for _ in range(3):
        await policy.requested()
        await policy.rebuild()
        await policy.fail(policy.search)
    assert await policy.requested() == []  # given up
    await policy.record(Outcome.success(), on=policy.status, times=3)
    await policy.record(Outcome.success(), on=policy.search, times=10)

    await policy.fail(policy.status)

    assert await policy.requested() == [policy.owner]


async def test_one_component_alone_healthy_again_keeps_the_count() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    for _ in range(3):
        await policy.requested()
        await policy.rebuild()
        await policy.record(Outcome.success(), on=policy.status, times=3)
        await policy.fail(policy.search)
    assert await policy.requested() == []


async def test_a_raising_rebuild_counts_useless_the_third_giving_up() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    await policy.requested()

    tries = [policy.latest.rebuild_raised() for _ in range(3)]

    assert tries == [True, True, False]
    await policy.fail(policy.status)
    assert await policy.requested() == []


async def test_a_rebuild_after_raising_ones_keeps_their_count() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    await policy.requested()
    policy.latest.rebuild_raised()
    policy.latest.rebuild_raised()
    await policy.rebuild()

    await policy.fail(policy.search)

    assert await policy.requested() == []  # its third useless restart


async def test_a_condition_but_bugs_failing_restarts_nothing() -> None:
    policy = _Policy()
    channel = channel_component(client_name=_CLIENT, channel=Channel("kad"))
    for _ in range(6):
        await policy.recorder.record(
            Outcome.declared(ChannelNotConnected()), on=channel, by=STATUS_CONNECTED_FIELD
        )
    assert await policy.requested() == []
    assert policy.logger.lines == []


async def test_a_request_carries_the_components_the_composition_names_its_owner_s() -> None:
    policy = _Policy()
    await policy.fail(policy.status)
    await policy.requested()
    assert policy.latest.components == (policy.search, policy.status)


async def test_a_rebuilt_request_empties_its_components_bugs_windows() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    await policy.requested()

    await policy.rebuild()

    assert (policy.search.health_of(BUGS), policy.status.health_of(BUGS)) == (
        Health.UNKNOWN,
        Health.UNKNOWN,
    )


async def test_a_component_carrying_no_bugs_condition_is_refused() -> None:
    with pytest.raises(ValueError, match="^client amuled: a bugs condition expected"):
        RestartPolicy(owners={client_component(_CLIENT): FakeStateOwner()}, logger=FakeLogger())
