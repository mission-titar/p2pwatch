"""Maps the amuleapi payloads onto the ports' DTOs. An unknown key is never an error.

Typed JSON does not preserve the capture-all invariant on its own, so every key of a search
result no structured field consumes lands in ``raw_meta`` - except ``ecid``, a session-local id
we never persist. A source keeps only D7's keys (stage 4 spec).
"""

import json
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation, fold_raw_meta
from p2pwatch.domain.source import (
    SourceKey,
    SourceMeta,
    SourceReading,
    SourceRole,
    is_contact_point,
)
from p2pwatch.ports.client_status import ChannelStatus, ClientStatus
from p2pwatch.ports.download_client import DownloadStatus, FailureReason, WaitingReason

_HASH_LENGTH = 32

# What amuleapi reports for a peer that has not sent its hash yet (stage 4 spec, D7).
_NO_USER_HASH = "0" * _HASH_LENGTH

# The relations of a row we ask the file of; any other row is a source only when parked (D1).
_ASKED = ("downloading_from", "both")

# The download states that say what a source holds of what we lack (D3).
_SOURCE_ROLES = {
    "downloading": SourceRole.SENDING,
    "queued": SourceRole.QUEUED,
    "no_needed_parts": SourceRole.NOTHING_NEW,
}

# States aMule leaves on its own: no role, the writer carries the latest point's group (D3).
_PASSING_STATES = frozenset(
    {
        "idle",
        "connecting",
        "connected",
        "waiting_callback",
        "waiting_callback_kad",
        "requesting_hashset",
        "too_many_connections",
        "too_many_connections_kad",
        "remote_queue_full",
    }
)

# A source row's stable keys, never an address nor a value that moves between reads (D3, D7).
_SOURCE_META_KEYS = (
    "ident_state",
    "source_origin",
    "client_mod_name",
    "reported_os",
    "shared_files_browsable",
    "protocol_extensions",
)
_SOURCE_DETAIL_META_KEYS = ("server_name",)

# D7's order, the most informative role first: a passing state (None) says more than unknown.
_INFORMATIVE_ROLES: tuple[SourceRole | None, ...] = (
    SourceRole.SENDING,
    SourceRole.QUEUED,
    SourceRole.NOTHING_NEW,
    None,
    SourceRole.UNDETERMINED,
    SourceRole.STANDBY,
)

# Result keys consumed by a structured field, hence EXCLUDED from raw_meta.
_MAPPED_KEYS = frozenset(
    {"hash", "name", "size_bytes", "sources", "media", "file_type", "alternate_names"}
)
_MAPPED_MEDIA_KEYS = frozenset({"duration_seconds", "bitrate_kilobits_per_second", "codec"})

# amuleapi download statuses that say why a download waits, before its sources are read (D12).
# `waiting` is a local hash wait, not a remote queue; `completing` hashes then moves the file.
_WAITING_STATUSES = {
    "insufficient_disk": WaitingReason.DISK_FULL,
    "paused": WaitingReason.PAUSED,
    "stopped": WaitingReason.PAUSED,
    "waiting": WaitingReason.LOCAL,
    "hashing": WaitingReason.LOCAL,
    "allocating": WaitingReason.LOCAL,
    "completing": WaitingReason.LOCAL,
}


def map_search_results(results: object, keyword: str) -> tuple[tuple[FileObservation, ...], int]:
    """The ``results[]`` of a search → ``(observations, skipped_count)``."""
    observations: list[FileObservation] = []
    skipped = 0
    if not isinstance(results, list):
        return (), 0  # unexpected envelope: tolerated, ignored (not a result set)
    for result in results:
        mapped, result_skipped = _map_result(result, keyword)
        observations.extend(mapped)
        skipped += result_skipped
    return tuple(observations), skipped


def map_download_status(row: object) -> DownloadStatus | None:
    """A /downloads row, or ``None`` if the hash is unusable. Only ``completed`` completes: it
    is the one status amuleapi reserves for a file verified and moved (spec stage 2, D10)."""
    if not isinstance(row, dict):
        return None
    ed2k_hash = _hash_hex(row.get("hash"))
    if ed2k_hash is None:
        return None
    status = _string(row.get("status")) or ""
    completed = status == "completed"
    failure = FailureReason.ERROR if status == "erroneous" else None
    waiting = None if completed or failure else _waiting_reason(status, row.get("sources"))
    return DownloadStatus(
        file=FileKey(Network.ED2K, ed2k_hash),
        bytes_done=_int(row.get("completed_bytes")),
        bytes_total=_int(row.get("size_bytes")),
        completed=completed,
        waiting_reason=waiting,
        failure_reason=failure,
    )


def map_shared_download(row: object) -> DownloadStatus | None:
    """A /shared row as a download completed then cleared, or ``None`` if the hash is unusable.
    Partfiles are shared too, so the caller reads it only for a file the queue no longer lists."""
    if not isinstance(row, dict):
        return None
    ed2k_hash = _hash_hex(row.get("hash"))
    if ed2k_hash is None:
        return None
    size = _int(row.get("size_bytes"))
    return DownloadStatus(FileKey(Network.ED2K, ed2k_hash), size, size, True, None, None)


def map_client_status(status: object, version: object) -> ClientStatus:
    """A /status and a /version body → ``ClientStatus``. Never raises: missing reads unknown."""
    body = _object(status)
    ed2k, kad = _object(body.get("ed2k")), _object(body.get("kad"))
    high_id, firewalled = ed2k.get("high_id"), kad.get("firewalled_tcp")
    channels = (
        _channel("ed2k", ed2k, high_id if isinstance(high_id, bool) else None),
        _channel("kad", kad, not firewalled if isinstance(firewalled, bool) else None),
    )
    return ClientStatus(version=_string(_object(version).get("daemon_version")), channels=channels)


def source_ecid(row: object) -> int | None:
    """The ``ecid`` to ask the detail of, for a row of ``GET /downloads/{hash}/clients`` that
    offers us the file (D1); ``None`` for any other."""
    if not isinstance(row, dict):
        return None
    if row.get("role") not in _ASKED and row.get("a4af") is not True:
        return None
    return _optional_int(row.get("ecid"))


def map_source(row: dict[str, Any], detail: dict[str, Any]) -> SourceReading:
    """A source's row, which alone carries its relation to the file, and its client detail."""
    asked = row.get("role") in _ASKED
    software = (_string(row.get("software")), _string(row.get("software_version")))
    return SourceReading(
        key=_source_key(row.get("user_hash")),
        name=_string(row.get("name")),
        software=" ".join(part for part in software if part) or None,
        role=_source_role(row.get("download_state")) if asked else SourceRole.STANDBY,
        contact_point=_contact_point(detail),
        directly_reachable=_directly_reachable(detail),
        raw_meta=(
            *_source_meta(row, _SOURCE_META_KEYS),
            *_source_meta(detail, _SOURCE_DETAIL_META_KEYS),
        ),
        transfer_counter=_int(row.get("downloaded_bytes_session")),
    )


def merge_duplicate_sources(readings: Iterable[SourceReading]) -> tuple[SourceReading, ...]:
    """One reading per source, by user hash or else by name: the most informative role, and the
    larger counter (D7). A reading with neither is never merged."""
    merged: dict[object, SourceReading] = {}
    for reading in readings:
        identity = reading.key or reading.name or object()
        held = merged.get(identity)
        if held is not None:
            best = min(held, reading, key=lambda kept: _INFORMATIVE_ROLES.index(kept.role))
            counter = max(held.transfer_counter, reading.transfer_counter)
            reading = replace(best, transfer_counter=counter)
        merged[identity] = reading
    return tuple(merged.values())


def _source_key(user_hash: object) -> SourceKey | None:
    """No identity for a hash amuleapi does not have yet, rather than one shared by all (D7)."""
    native_id = _hash_hex(user_hash)
    if native_id is None or native_id == _NO_USER_HASH:
        return None
    return SourceKey(Network.ED2K, native_id)


def _source_role(state: object) -> SourceRole | None:
    """Any state that is neither says nothing of the parts we lack: ``undetermined`` (D3)."""
    if not isinstance(state, str):
        return SourceRole.UNDETERMINED
    if state in _PASSING_STATES:
        return None
    return _SOURCE_ROLES.get(state, SourceRole.UNDETERMINED)


def _contact_point(detail: dict[str, Any]) -> str | None:
    """The eD2k server the source connects through, as ``ip:port``, the one form the writer
    accepts (D3); ``None`` for anything else, an unknown server's ``null`` included."""
    contact_point = f"{detail.get('server_ip')}:{detail.get('server_port')}"
    return contact_point if is_contact_point(Network.ED2K, contact_point) else None


def _directly_reachable(detail: dict[str, Any]) -> bool | None:
    """``high_id``, unknown while the client has no eD2k id (``ed2k_user_id`` 0) (D3)."""
    high_id = detail.get("high_id")
    if not _optional_int(detail.get("ed2k_user_id")) or not isinstance(high_id, bool):
        return None
    return high_id


def _source_meta(fields: dict[str, Any], keys: tuple[str, ...]) -> SourceMeta:
    """The ``keys`` the payload carries; an absent one is left out, not read as ``None``."""
    return tuple((key, _meta_value(fields[key])) for key in keys if key in fields)


def _meta_value(value: object) -> str | int | bool | tuple[str, ...] | None:
    """A JSON value in a shape ``SourceMeta`` holds: a list as a tuple of text, anything else
    unforeseen as its JSON text."""
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, list):
        return tuple(_render(item) for item in value)
    return _render(value)


def _channel(channel: str, channel_json: dict[str, Any], connectable: bool | None) -> ChannelStatus:
    """Off the network the flag tells nothing: there ``high_id`` false means "no id yet"."""
    connected = channel_json.get("state") == "connected"
    return ChannelStatus(channel, connected, connectable if connected else None)


def _map_result(result: object, keyword: str) -> tuple[list[FileObservation], int]:
    """One result row → one observation PER FILENAME, plus the skipped count."""
    if not isinstance(result, dict):
        return [], 1
    ed2k_hash = _hash_hex(result.get("hash"))
    size_bytes = result.get("size_bytes")
    if ed2k_hash is None or not isinstance(size_bytes, int) or isinstance(size_bytes, bool):
        return [], 1
    media = _object(result.get("media"))
    raw_meta = _raw_meta(result, media)
    codec, file_type = _string(media.get("codec")), _string(result.get("file_type"))
    alternates = result.get("alternate_names")
    entries: list[object] = [result, *(alternates if isinstance(alternates, list) else [])]
    observations: list[FileObservation] = []
    skipped = 0
    for entry in entries:
        fields = _object(entry)
        name = _string(fields.get("name"))
        if name is None:
            skipped += 1
            continue
        total, complete = _sources(fields.get("sources"))
        observations.append(
            FileObservation(
                file=FileKey(Network.ED2K, ed2k_hash),
                filename=name,
                size_bytes=size_bytes,
                source_count=total,
                keyword=keyword,
                media_length_sec=_optional_int(media.get("duration_seconds")),
                bitrate_kbps=_optional_int(media.get("bitrate_kilobits_per_second")),
                raw_meta=fold_raw_meta(raw_meta, codec, file_type, complete),
            )
        )
    return observations, skipped


def _raw_meta(result: dict[str, Any], media: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Every unmapped key → ``(key, rendered_value)``, in wire order."""
    collected = [(key, _render(value)) for key, value in result.items() if key not in _MAPPED_KEYS]
    collected += [
        (f"media.{key}", _render(value))
        for key, value in media.items()
        if key not in _MAPPED_MEDIA_KEYS
    ]
    return tuple(collected)


def _render(value: object) -> str:
    """Rendering that NEVER raises: text as-is, anything else as JSON."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: object) -> str | None:
    """A blank string reads as absent: an empty name is as unusable as a missing one."""
    return value if isinstance(value, str) and value else None


def _hash_hex(value: object) -> str | None:
    """Lowercased MD4 hash, or ``None``: without it the row has no identifier at all."""
    if not isinstance(value, str) or len(value) != _HASH_LENGTH:
        return None
    lowered = value.lower()
    return lowered if all(character in "0123456789abcdef" for character in lowered) else None


def _int(value: object) -> int:
    """Absent or malformed reads as 0, and ``bool`` is not a count though it is an ``int``."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _optional_int(value: object) -> int | None:
    """Keeps "the daemon reported nothing" distinct from a reported zero."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _sources(value: object) -> tuple[int, int]:
    sources = _object(value)
    return _int(sources.get("total")), _int(sources.get("complete"))


def _waiting_reason(status: str, sources: object) -> WaitingReason | None:
    """The status's own reason first, then the sources: none at all, or none sending."""
    reason = _WAITING_STATUSES.get(status)
    if reason is not None:
        return reason
    counts = _object(sources)
    if _int(counts.get("total")) == 0:
        return WaitingReason.NO_SOURCE
    return WaitingReason.REMOTE_QUEUE if _int(counts.get("transferring")) == 0 else None
