"""The notifier as the node rebuilds it: built anew, no work handed back, the next send going to
the notifier built latest."""

from collections.abc import Sequence

import pytest

from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.composition.notifier_restartable import NotifierRestartable
from tests.contracts.application.ports.driven.restartable_contract import RestartableContract
from tests.fakes.adapters.driven.fake_apprise import FakeApprise


class _Notifiers:
    """Builds apprise notifiers with no service, keeping each, as the composition builds them."""

    def __init__(self) -> None:
        self.built: list[AppriseNotifier] = []

    def build(self) -> AppriseNotifier:
        self.built.append(AppriseNotifier((), apprise_factory=FakeApprise))
        return self.built[-1]


class TestNotifierRestartable(RestartableContract):
    @pytest.fixture
    def restartable(self) -> NotifierRestartable:
        self._notifiers = _Notifiers()
        self._restartable = NotifierRestartable(build_notifier=self._notifiers.build)
        return self._restartable

    def state_of(self, restartable: Restartable[object]) -> object:
        return self._notifiers.built[-1]

    def state_under(self, works: Sequence[object]) -> object:
        # No work runs over the notifier: the sends reach it through ``notifier()``.
        assert list(works) == []
        return self._restartable.notifier()


def test_it_is_named_as_the_notifier_s_part_is() -> None:
    notifier = NotifierRestartable(build_notifier=_Notifiers().build)

    assert str(notifier) == "notifier"


@pytest.mark.asyncio
async def test_the_next_send_goes_to_the_notifier_built_latest() -> None:
    notifiers = _Notifiers()
    notifier = NotifierRestartable(build_notifier=notifiers.build)
    first = notifier.notifier()

    await notifier.rebuild()

    assert notifiers.built[0] is first
    assert notifier.notifier() is notifiers.built[1]
