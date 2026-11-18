"""The aMule client as the node builds it at each restart: a client logged in, its eD2k lock, its
Kad slots, and every work over it."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.ports.driven.restartable_builder import RestartableBuilder
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.domain.identifiers import ClientName


class ClientBuilder(Protocol):
    def __call__(self) -> AmuleApiClient: ...


# Every work over ``client``, such as ``AmuleClientWorks.over``.
class WorksOverClient(Protocol):
    def __call__(self, client: AmuleApiClient, /) -> Sequence[SupervisedWork]: ...


class AmuleClientRestartable(Restartable[SupervisedWork]):
    """A client logged in to aMule and every work over it."""

    def __init__(self, client: AmuleApiClient, *, works: Sequence[SupervisedWork]) -> None:
        self.client = client
        self._works = tuple(works)

    def works(self) -> Sequence[SupervisedWork]:
        return self._works

    async def close(self) -> None:
        """Logs its session out."""
        await self.client.close()


class AmuleClientRestartableBuilder(RestartableBuilder[AmuleClientRestartable]):
    """Builds a client of aMule and logs it in, its first searches spaced from the latest starts
    it reads, with every work over it."""

    def __init__(
        self,
        *,
        client_name: ClientName,
        build_client: ClientBuilder,
        works_over: WorksOverClient,
    ) -> None:
        self._client_name = client_name
        self._build_client = build_client
        self._works_over = works_over

    def __str__(self) -> str:
        return f"client {self._client_name}"

    async def build(self) -> AmuleClientRestartable:
        client = self._build_client()
        # A login refused or cut closes its own session: the client holds nothing then.
        await client.open()
        return AmuleClientRestartable(client, works=self._works_over(client))
