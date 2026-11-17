"""The aMule client as the node rebuilds it: its session with aMule, its eD2k lock, its Kad slots,
built anew with every work over it."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.domain.identifiers import ClientName


class ClientBuilder(Protocol):
    def __call__(self) -> AmuleApiClient: ...


# Every work over ``client``, such as ``AmuleClientWorks.over``.
class WorksOverClient(Protocol):
    def __call__(self, client: AmuleApiClient, /) -> Sequence[SupervisedWork]: ...


class AmuleClientRestartable(Restartable[SupervisedWork]):
    """The aMule client the works use now, rebuilt with them: the node's shutdown closes the one
    it holds then."""

    def __init__(
        self,
        client: AmuleApiClient,
        *,
        client_name: ClientName,
        build_client: ClientBuilder,
        works_over: WorksOverClient,
    ) -> None:
        self._client = client
        self._client_name = client_name
        self._build_client = build_client
        self._works_over = works_over

    def __str__(self) -> str:
        return f"client {self._client_name}"

    async def rebuild(self) -> Sequence[SupervisedWork]:
        """Logs the old session out, logs a client built anew in, its first searches spaced from
        the latest starts it reads, and returns the works over it."""
        await self._client.close()
        # Held before its login, so the shutdown closes it even when the login is cut.
        self._client = self._build_client()
        await self._client.open()
        return self._works_over(self._client)

    async def close(self) -> None:
        """Logs out the client it holds now."""
        await self._client.close()
