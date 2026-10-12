"""A source: a peer that shares a file with one of our downloads, by its pseudonymous identity.

PURE domain. Never a network address of the peer (stage 4 spec, D2, D3 and D7).
"""

import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from p2pwatch.domain.file_key import Network

# Its own namespace, so that a source_id never equals a file_id (stage 4 spec, D2).
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://mission-titar.github.io/p2pwatch/source")

_NATIVE_IDS = {Network.ED2K: (re.compile("[0-9a-f]{32}"), "32 lowercase hex characters")}

SourceMeta = tuple[tuple[str, str | int | bool | tuple[str, ...] | None], ...]


@dataclass(frozen=True)
class SourceKey:
    """A source as its network names it: for ``ED2K``, its user hash in 32 lowercase hex."""

    network: Network
    native_id: str

    def __post_init__(self) -> None:
        pattern, shape = _NATIVE_IDS[self.network]
        if not pattern.fullmatch(self.native_id):
            raise ValueError(f"a {self.network} source's native_id is {shape}")

    @property
    def source_id(self) -> bytes:
        """The 16 bytes of ``uuid5(namespace, "<network>:<native_id>")``."""
        return uuid.uuid5(_NAMESPACE, f"{self.network}:{self.native_id}").bytes


class SourceRole(StrEnum):
    """What the node knows of what a source holds for our download: useful, not, or unknown."""

    SENDING = "sending"
    QUEUED = "queued"
    NOTHING_NEW = "nothing_new"
    STANDBY = "standby"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True)
class SourceReading:
    """One source of one download at one read. ``role`` is ``None`` in a passing state, whose
    role the writer carries from the source's latest range (D3)."""

    key: SourceKey | None
    name: str | None
    software: str | None
    role: SourceRole | None
    contact_point: str | None
    directly_reachable: bool | None
    raw_meta: SourceMeta
    transfer_counter: int
