import asyncio
import contextlib
from collections.abc import Collection

from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notification_sends import NotificationService
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE, FakeNotifier


class FakeHeldNotifier(FakeNotifier):
    """Holds each send to ``held`` (every service by default) until the test releases it, so a
    test can cancel the caller mid-send; ``reached`` is set once a send is held; ``refusing``,
    refuses each send once it goes on."""

    def __init__(
        self,
        services: tuple[NotificationService, ...] = ONE_SERVICE_PER_AUDIENCE,
        *,
        held: Collection[NotificationService] | None = None,
        refusing: bool = False,
    ) -> None:
        super().__init__(services, refusing=refusing)
        self._held = services if held is None else held
        self.reached = asyncio.Event()
        self.released = asyncio.Event()
        self._sent = asyncio.Event()

    async def notify(self, service: NotificationService, *, notification: Notification) -> None:
        if service in self._held:
            self.reached.set()
            await self.released.wait()
        await super().notify(service, notification=notification)
        self._sent.set()

    async def wait_until_sent(self, *, timeout_seconds: float) -> None:
        """Returns once a send is kept, or after ``timeout_seconds`` with nothing kept."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._sent.wait(), timeout=timeout_seconds)
