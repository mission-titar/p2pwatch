"""The aMule client's owner: its session, its eD2k lock, its Kad slots and its caches, built anew by
a restart with every object holding the client (spec v5 lot 4, D5)."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.application.ports.driven.state_owner import StateOwner
from p2pwatch.application.steps.supervisor import SupervisedWork
from p2pwatch.domain.identifiers import ClientName


class ClientBuilder(Protocol):
    def __call__(self) -> AmuleApiClient: ...


# Every work over ``client``, each object holding it built anew.
class ClientWorks(Protocol):
    def __call__(self, client: AmuleApiClient, /) -> Sequence[SupervisedWork]: ...


class WorkAdder(Protocol):
    def __call__(self, supervised: SupervisedWork, /) -> None: ...


class AmuleClientOwner(StateOwner):
    """Holds the client the works use now, which the resource stack closes at the shutdown."""

    def __init__(
        self,
        client: AmuleApiClient,
        *,
        client_name: ClientName,
        build_client: ClientBuilder,
        build_works: ClientWorks,
        add_work: WorkAdder,
    ) -> None:
        self._client = client
        self._client_name = client_name
        self._build_client = build_client
        self._build_works = build_works
        self._add_work = add_work

    def __str__(self) -> str:
        return f"owner of client {self._client_name}"

    async def restart(self) -> None:
        """Logs the session out, then logs a client built anew in, its first starts spaced from
        the persisted ones, and adds the works holding it."""
        await self._client.close()
        # Held before its login, so the shutdown closes it even when the login is cut.
        self._client = self._build_client()
        await self._client.open()
        for supervised in self._build_works(self._client):
            self._add_work(supervised)

    async def close(self) -> None:
        await self._client.close()
