"""The promise of the ``Notifier`` port."""

from abc import ABC, abstractmethod

import pytest

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.observability.notifier_outcomes import NotificationRefused
from p2pwatch.domain.observability.severity import Severity

_LINE = RelayedLogLine(message="online", severity=Severity.INFO, node_id=NodeId("n1"))


class NotifierContract(ABC):
    pytestmark = pytest.mark.asyncio

    @abstractmethod
    def notifier(self) -> Notifier:
        """A notifier built anew at each call over one configuration, its services accepting
        every send."""

    @abstractmethod
    def refusing_notifier(self) -> Notifier:
        """A notifier over the same configuration, its services refusing every send."""

    def test_two_builds_on_one_configuration_list_the_same_services(self) -> None:
        services = self.notifier().services()
        assert services
        assert self.notifier().services() == services

    async def test_a_send_its_service_accepts_raises_nothing(self) -> None:
        notifier = self.notifier()
        for service in notifier.services():
            await notifier.notify(service, notification=_LINE)

    async def test_a_send_its_service_refuses_raises_notification_refused(self) -> None:
        notifier = self.refusing_notifier()
        for service in notifier.services():
            with pytest.raises(NotificationRefused):
                await notifier.notify(service, notification=_LINE)
