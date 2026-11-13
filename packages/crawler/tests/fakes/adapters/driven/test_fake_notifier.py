from p2pwatch.application.ports.driven.notifier import Notifier
from tests.contracts.application.ports.driven.notifier_contract import NotifierContract
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier


class TestFakeNotifier(NotifierContract):
    def notifier(self) -> Notifier:
        return FakeNotifier()

    def refusing_notifier(self) -> Notifier:
        return FakeNotifier(refusing=True)
