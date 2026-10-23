"""A source: a peer that shares a file with one of our downloads, by its pseudonymous identity.

PURE domain. Never a network address of the peer (stage 4 spec, D2, D3 and D7).
"""

import ipaddress
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from p2pwatch.domain.file_key import Network

# Its own namespace, so that a source_id never equals a file_id (stage 4 spec, D2).
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://mission-titar.github.io/p2pwatch/source")

_NATIVE_IDS = {Network.ED2K: (re.compile("[0-9a-f]{32}"), "32 lowercase hex characters")}

_PORT = re.compile("[1-9][0-9]{0,4}")

SourceMetadata = tuple[tuple[str, str | int | bool | tuple[str, ...] | None], ...]


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


def carried_role_max_age(time_between_reads: timedelta) -> timedelta:
    """The longest gap over which the writer carries a role (source points spec, D4)."""
    return _TOLERATED_READS * time_between_reads


@dataclass(frozen=True)
class ContactPoint:
    """The server a source connects through, as its network names one: for ``ED2K``, ``ip:port``."""

    network: Network
    server: str

    def __post_init__(self) -> None:
        is_server, shape = _CONTACT_POINTS[self.network]
        if not is_server(self.server):
            raise ValueError(f"a {self.network} contact point is {shape}")


def parse_contact_point(network: Network, server: str) -> ContactPoint | None:
    """``server`` as ``network``'s contact point, ``None`` when it names none."""
    is_server, _ = _CONTACT_POINTS[network]
    return ContactPoint(network, server) if is_server(server) else None


def _is_ed2k_server(server: str) -> bool:
    host, _, port = server.rpartition(":")
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        return False
    return _PORT.fullmatch(port) is not None and int(port) <= 65535


_CONTACT_POINTS = {Network.ED2K: (_is_ed2k_server, "an IPv4 address and a port")}


@dataclass(frozen=True)
class SourceReading:
    """One source of one download at one read. ``role`` is ``None`` in a passing state, whose
    role the writer carries from the source's latest point (D3)."""

    source: SourceKey | None
    source_name: str | None
    software: str | None
    role: SourceRole | None
    contact_point: ContactPoint | None
    connectable: bool | None
    raw_metadata: SourceMetadata
    session_received_bytes: int


@dataclass(frozen=True)
class RecordedReading:
    """A reading ``record_readings`` kept, with its role, a carried one included."""

    source: SourceKey | None
    source_name: str | None
    role: SourceRole


@dataclass(frozen=True)
class LatestPoint:
    """A source's latest point under one of its variants: its role, its instant, its session's
    received bytes."""

    role: SourceRole
    observed_at: datetime
    session_received_bytes: int


def carried_role(latest: LatestPoint | None, reading: SourceReading) -> SourceRole:
    """The role of ``reading``, in a passing state, from its source's latest point: none once aMule
    recreated the client, which restarts its session's received bytes."""
    if latest is None or latest.session_received_bytes > reading.session_received_bytes:
        return SourceRole.UNDETERMINED
    return _CARRIED[latest.role.usefulness]


@dataclass(frozen=True)
class EarlierPoints:
    """D5's two answers: a useful point exists, and when the latest useful or not-useful one was."""

    has_useful_point: bool
    latest_known_at: datetime | None

    @classmethod
    def of(cls, points: Sequence[LatestPoint]) -> "EarlierPoints":
        """The two answers from the latest point of each of a source's variants."""
        known = [p.observed_at for p in points if p.role.usefulness is not SourceUsefulness.UNKNOWN]
        return cls(
            has_useful_point=any(p.role.usefulness is SourceUsefulness.USEFUL for p in points),
            latest_known_at=max(known, default=None),
        )
