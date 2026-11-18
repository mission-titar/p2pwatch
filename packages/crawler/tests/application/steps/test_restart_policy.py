"""The restart policy: a bugs rule of a part turning failing restarts the object that part is of,
such as the aMule client; three rebuilds in vain at most, the count reset once every bugs rule of
its parts is healthy again."""

from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.restart_policy import RestartPolicy, RestartRequest
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.domain.health.external_dependency import ExternalDependency
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword
from p2pwatch.domain.status_reading import (
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    channel_dependency,
    client_dependency,
)
from p2pwatch.domain.work_dependencies import (
    BUGS,
    keyword_search_dependency,
    status_reading_dependency,
)
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.composition.fake_restartable import FakeRestartable

pytestmark = pytest.mark.asyncio

_AMULED = ClientName("amuled")


class _Search(Work):
    """A search whose turns are never taken."""

    def __str__(self) -> str:
        return "search 'keroro' amuled kad"

    async def wait_for_next_turn(self) -> None:
        """Never awaited."""

    async def run_once(self) -> None:
        """Never awaited."""


def _search_recorded_on(*parts: ExternalDependency) -> SupervisedWork:
    return SupervisedWork(work=_Search(), time_limit=timedelta(minutes=25), dependencies=parts)


class _Policy:
    """A policy over the aMule client and three of its parts, fed through the node's health; it
    keeps each restart it requests, which the supervisor would take."""

    def __init__(self) -> None:
        self.logger = FakeLogger()
        self.client = FakeRestartable("client amuled")
        self.search = keyword_search_dependency(
            keyword=Keyword("keroro"), client_name=_AMULED, channel=Channel("kad")
        )
        self.status = status_reading_dependency(_AMULED)
        self.kad = channel_dependency(client_name=_AMULED, channel=Channel("kad"))
        self.requests: list[RestartRequest] = []
        policy = RestartPolicy(
            dependencies_of={self.client: (self.search, self.status, self.kad)},
            works=[_search_recorded_on(self.search, self.kad)],
            restart=self.requests.append,
            logger=self.logger,
        )
        self.node_health = NodeHealth(logger=FakeLogger(), subscribers=(policy,))

    async def check(
        self, part: ExternalDependency, *, rule: HealthRule = BUGS, detected: bool, times: int
    ) -> None:
        for _ in range(times):
            await self.node_health.record(on=part, rule=rule, detected=detected)

    async def fail(self, part: ExternalDependency) -> None:
        """Three turns in a row meeting a bug: its bugs rule turns failing."""
        await self.check(part, detected=True, times=3)

    async def heal(self, *parts: ExternalDependency) -> None:
        """Ten turns without a bug on each of ``parts``: their bugs rules turn healthy."""
        for part in parts:
            await self.check(part, detected=False, times=10)

    def rebuild(self) -> None:
        """What the supervisor does once the latest restart's rebuild returned."""
        self.requests[-1].rebuilt()


async def test_a_bugs_rule_turning_failing_restarts_the_object_its_part_is_of() -> None:
    policy = _Policy()
    await policy.check(policy.search, detected=True, times=2)
    assert policy.requests == []

    await policy.check(policy.search, detected=True, times=1)

    assert [request.restartable for request in policy.requests] == [policy.client]
    assert policy.requests[0].dependencies == (policy.search, policy.status, policy.kad)
    message = "restarting client amuled: bugs in search 'keroro' amuled kad"
    assert policy.logger.lines == [LoggedLine(level="warning", message=message)]


async def test_another_rule_turning_failing_restarts_nothing() -> None:
    policy = _Policy()

    await policy.check(policy.kad, rule=CHANNEL_NOT_CONNECTED, detected=True, times=6)
    # The client's own part is no object's: aMule down is never repaired by a rebuild.
    await policy.check(client_dependency(_AMULED), rule=CLIENT_UNREACHABLE, detected=True, times=3)

    assert policy.requests == []
    assert policy.logger.lines == []


async def test_another_part_failing_while_its_object_restarts_requests_no_second_restart() -> None:
    policy = _Policy()

    await policy.fail(policy.search)
    await policy.fail(policy.status)

    assert len(policy.requests) == 1


async def test_bugs_failing_again_after_each_rebuild_restart_it_three_times_then_never() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    for _ in range(3):
        policy.rebuild()
        await policy.fail(policy.search)

    assert len(policy.requests) == 3
    bugs_in = "bugs in search 'keroro' amuled kad"
    assert policy.logger.lines == [
        LoggedLine(level="warning", message=f"restarting client amuled: {bugs_in}"),
        LoggedLine(
            level="warning",
            message=f"restarting client amuled again, 1 of 3 rebuilds in vain: {bugs_in}",
        ),
        LoggedLine(
            level="warning",
            message=f"restarting client amuled again, 2 of 3 rebuilds in vain: {bugs_in}",
        ),
        LoggedLine(level="error", message="client amuled not restarted again: 3 rebuilds in vain"),
    ]


async def test_bugs_in_another_part_after_a_rebuild_count_that_rebuild_in_vain_too() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    for failing in (policy.status, policy.kad, policy.search):
        policy.rebuild()
        await policy.fail(failing)

    assert len(policy.requests) == 3


async def test_every_bugs_rule_of_its_parts_healthy_after_a_rebuild_resets_the_count() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    for _ in range(2):
        policy.rebuild()
        await policy.fail(policy.search)
    policy.rebuild()
    await policy.heal(policy.search, policy.status, policy.kad)

    for _ in range(3):
        await policy.fail(policy.search)
        policy.rebuild()

    # Three restarts before the reset, three after: none of these was a fourth in vain.
    assert len(policy.requests) == 6


async def test_one_part_healthy_again_alone_keeps_the_count() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    for _ in range(3):
        policy.rebuild()
        await policy.heal(policy.status)
        await policy.fail(policy.search)

    assert len(policy.requests) == 3


async def test_three_rebuilds_in_vain_then_every_bugs_rule_healthy_then_a_bug_restart_it() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    for _ in range(3):
        policy.rebuild()
        await policy.fail(policy.search)
    assert len(policy.requests) == 3  # given up: its works run on, only the buggy turns failing

    await policy.heal(policy.search, policy.status, policy.kad)
    await policy.fail(policy.status)

    assert len(policy.requests) == 4


async def test_a_rebuild_that_raises_counts_in_vain_and_the_third_gives_up() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    [request] = policy.requests

    tries_again = [request.rebuild_raised() for _ in range(3)]

    assert tries_again == [True, True, False]
    assert policy.logger.lines[-1] == LoggedLine(
        level="error", message="client amuled not restarted again: 3 rebuilds in vain"
    )
    await policy.fail(policy.status)
    assert len(policy.requests) == 1


async def test_rebuilds_that_raised_and_rebuilds_failing_again_share_one_count() -> None:
    policy = _Policy()
    await policy.fail(policy.search)
    policy.requests[-1].rebuild_raised()
    policy.requests[-1].rebuild_raised()
    policy.rebuild()

    await policy.fail(policy.search)

    assert len(policy.requests) == 1  # its third rebuild in vain


async def test_a_rebuild_forgets_the_bugs_of_its_parts_and_keeps_their_other_rules() -> None:
    policy = _Policy()
    await policy.check(policy.kad, rule=CHANNEL_NOT_CONNECTED, detected=True, times=6)
    await policy.fail(policy.kad)

    policy.rebuild()

    # Forgetting the readings' rules would end an open alert, or send it twice.
    assert policy.kad.state(CHANNEL_NOT_CONNECTED) is HealthState.FAILING
    assert [part.state(BUGS) for part in (policy.search, policy.status, policy.kad)] == [
        HealthState.UNKNOWN
    ] * 3


async def test_a_part_of_two_objects_is_refused() -> None:
    search = keyword_search_dependency(
        keyword=Keyword("keroro"), client_name=_AMULED, channel=Channel("kad")
    )
    dependencies_of: dict[Restartable[SupervisedWork], list[ExternalDependency]] = {
        FakeRestartable("client amuled"): [search],
        FakeRestartable("webui"): [search],
    }

    message = "^search 'keroro' amuled kad: a part of client amuled and of webui$"
    with pytest.raises(ValueError, match=message):
        RestartPolicy(
            dependencies_of=dependencies_of, works=(), restart=lambda _: None, logger=FakeLogger()
        )


async def test_a_work_recorded_on_a_part_of_no_object_is_refused() -> None:
    search = keyword_search_dependency(
        keyword=Keyword("keroro"), client_name=_AMULED, channel=Channel("kad")
    )
    kad = channel_dependency(client_name=_AMULED, channel=Channel("kad"))

    message = "^search 'keroro' amuled kad: recorded on channel amuled kad, a part of no object$"
    with pytest.raises(ValueError, match=message):
        RestartPolicy(
            dependencies_of={FakeRestartable("client amuled"): [search]},
            works=[_search_recorded_on(search, kad)],
            restart=lambda _: None,
            logger=FakeLogger(),
        )


async def test_a_work_recorded_on_no_part_is_refused() -> None:
    # No restart would ever stop it: it would run on over a closed client.
    message = "^search 'keroro' amuled kad: recorded on no part, so over no object$"
    with pytest.raises(ValueError, match=message):
        RestartPolicy(
            dependencies_of={FakeRestartable("client amuled"): []},
            works=[_search_recorded_on()],
            restart=lambda _: None,
            logger=FakeLogger(),
        )
