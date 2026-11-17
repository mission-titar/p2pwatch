"""The promise of the ``Notifier`` port."""

from abc import ABC, abstractmethod

import pytest

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.observability.notification_sends import NotificationRefusedError
from p2pwatch.domain.observability.severity import Severity

_LINE = RelayedLogLine(message="online", severity=Severity.INFO, node_id=NodeId("titar-node-1"))


class NotifierContract(ABC):
    @abstractmethod
    def notifier(self) -> Notifier:
        """A notifier built anew at each call on one configuration of two services or more, each
        taking every send."""

    @abstractmethod
    def refusing_notifier(self) -> Notifier:
        """A notifier on the same configuration, each of its services refusing every send."""

    def test_two_notifiers_built_on_one_configuration_list_the_same_services(self) -> None:
        services = self.notifier().services()

        assert len(services) >= 2
        assert self.notifier().services() == services

    @pytest.mark.asyncio
    async def test_a_send_its_service_takes_raises_nothing(self) -> None:
        notifier = self.notifier()

        for service in notifier.services():
            await notifier.notify(service, notification=_LINE)

    @pytest.mark.asyncio
    async def test_a_send_its_service_refuses_raises_notification_refused(self) -> None:
        notifier = self.refusing_notifier()

        for service in notifier.services():
            with pytest.raises(NotificationRefusedError):
                await notifier.notify(service, notification=_LINE)
