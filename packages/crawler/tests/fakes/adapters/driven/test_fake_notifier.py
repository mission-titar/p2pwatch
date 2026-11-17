from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.notification_sends import NotificationService
from tests.contracts.application.ports.driven.notifier_contract import NotifierContract
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE, FakeNotifier


class TestFakeNotifier(NotifierContract):
    def notifier(self) -> Notifier:
        self._built = FakeNotifier()
        return self._built

    def refusing_notifier(self) -> Notifier:
        return FakeNotifier(refusing=True)

    def configured_services(self) -> tuple[NotificationService, ...]:
        return ONE_SERVICE_PER_AUDIENCE

    def sent_under(self) -> list[str]:
        return [str(node_id) for node_id in self._built.node_ids]
