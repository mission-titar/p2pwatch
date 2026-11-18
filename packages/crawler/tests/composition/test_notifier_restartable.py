"""The notifier as the node builds it at each restart: a notifier built anew, no work over it."""

import pytest

from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.composition.notifier_restartable import (
    NotifierRestartable,
    NotifierRestartableBuilder,
)
from tests.contracts.application.ports.driven.restartable_builder_contract import (
    RestartableBuilderContract,
)
from tests.fakes.adapters.driven.fake_apprise import FakeApprise


class _Notifiers:
    """Builds apprise notifiers with no service, keeping each, as the composition builds them."""

    def __init__(self) -> None:
        self.built: list[AppriseNotifier] = []

    def build(self) -> AppriseNotifier:
        self.built.append(AppriseNotifier((), apprise_factory=FakeApprise))
        return self.built[-1]


class TestNotifierRestartableBuilder(RestartableBuilderContract):
    @pytest.fixture
    def builder(self) -> NotifierRestartableBuilder:
        self._notifiers = _Notifiers()
        return NotifierRestartableBuilder(build_notifier=self._notifiers.build)

    def state_of(self, restartable: Restartable[object]) -> object:
        return self._notifiers.built[-1]

    def state_reached(self, restartable: Restartable[object]) -> object:
        # No work runs over the notifier: the dispatcher's sends reach it.
        assert list(restartable.works()) == []
        assert isinstance(restartable, NotifierRestartable)
        return restartable.notifier


def test_it_names_its_notifiers_as_the_notifier_s_part_is() -> None:
    builder = NotifierRestartableBuilder(build_notifier=_Notifiers().build)

    assert str(builder) == "notifier"
