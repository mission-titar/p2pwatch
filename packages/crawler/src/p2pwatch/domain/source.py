"""A source: a peer that shares a file with one of our downloads, by its pseudonymous identity.

PURE domain. Never a network address of the peer (stage 4 spec, D2, D3 and D7).
"""

import ipaddress
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from p2pwatch.domain.file_key import Network

# Its own namespace, so that a source_id never equals a file_id (stage 4 spec, D2).
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://mission-titar.github.io/p2pwatch/source")

_NATIVE_IDS = {Network.ED2K: (re.compile("[0-9a-f]{32}"), "32 lowercase hex characters")}

_PORT = re.compile("[1-9][0-9]{0,4}")

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


class SourceUsefulness(StrEnum):
    """Whether a source holds what we lack (D3)."""

    USEFUL = "useful"
    NOT_USEFUL = "not_useful"
    UNKNOWN = "unknown"


class SourceRole(StrEnum):
    """What the node knows of what a source holds for our download: useful, not, or unknown."""

    SENDING = "sending"
    QUEUED = "queued"
    NOTHING_NEW = "nothing_new"
    STANDBY = "standby"
    UNDETERMINED = "undetermined"

    @property
    def usefulness(self) -> SourceUsefulness:
        return _USEFULNESS_BY_ROLE[self]


_USEFULNESS_BY_ROLE = {
    SourceRole.SENDING: SourceUsefulness.USEFUL,
    SourceRole.QUEUED: SourceUsefulness.USEFUL,
    SourceRole.NOTHING_NEW: SourceUsefulness.NOT_USEFUL,
    SourceRole.STANDBY: SourceUsefulness.UNKNOWN,
    SourceRole.UNDETERMINED: SourceUsefulness.UNKNOWN,
}

# Not SENDING after a useful point: a source no longer downloading is not sending (D3).
_CARRIED = {
    SourceUsefulness.USEFUL: SourceRole.QUEUED,
    SourceUsefulness.NOT_USEFUL: SourceRole.NOTHING_NEW,
    SourceUsefulness.UNKNOWN: SourceRole.UNDETERMINED,
}

# One missed read stays within three times between reads; a cycle takes under half of one (source
# points spec, D4).
_TOLERATED_READS = 3


def carried_role(previous: SourceRole | None) -> SourceRole:
    """The role of a reading in a passing state, from its latest point's, ``None`` without one."""
    return SourceRole.UNDETERMINED if previous is None else _CARRIED[previous.usefulness]


def carried_role_max_age(time_between_reads: timedelta) -> timedelta:
    """The longest gap over which the writer carries a role (source points spec, D4)."""
    return _TOLERATED_READS * time_between_reads


def is_contact_point(network: Network, contact_point: str) -> bool:
    """Whether ``contact_point`` is a server as ``network`` names one: on eD2k, ``ip:port``."""
    return _CONTACT_POINTS[network](contact_point)


def _is_ed2k_server(contact_point: str) -> bool:
    host, _, port = contact_point.rpartition(":")
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        return False
    return _PORT.fullmatch(port) is not None and int(port) <= 65535


_CONTACT_POINTS = {Network.ED2K: _is_ed2k_server}


@dataclass(frozen=True)
class SourceReading:
    """One source of one download at one read. ``role`` is ``None`` in a passing state, whose
    role the writer carries from the source's latest point (D3)."""

    source: SourceKey | None
    name: str | None
    software: str | None
    role: SourceRole | None
    contact_point: str | None
    connectable: bool | None
    raw_meta: SourceMeta
    session_received_bytes: int
