"""Maps the amuleapi payloads onto the ports' DTOs. An unknown key is never an error.

Typed JSON does not preserve the capture-all invariant on its own, so every key of a search
result no structured field consumes lands under ``raw_metadata``'s ``unmapped`` - except ``ecid``, a
session-local id we never persist. A source keeps only D7's keys (stage 4 spec).
"""

import json
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from p2pwatch.domain.download.states import FailureReason, WaitingReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, Keyword
from p2pwatch.domain.json_object_text import JsonObjectText
from p2pwatch.domain.observation import ReportedFile, fold_raw_metadata
from p2pwatch.domain.source import (
    ContactPoint,
    SourceKey,
    SourceReading,
    SourceRole,
    parse_contact_point,
)
from p2pwatch.domain.status_reading import ChannelStatus, ClientStatus
from p2pwatch.domain.value_bounds import is_quantity, replace_surrogates

_HASH_LENGTH = 32

# What amuleapi reports for a peer that has not sent its hash yet (stage 4 spec, D7).
_NO_USER_HASH = "0" * _HASH_LENGTH

# The relations of a row we ask the file of; any other row is a source only when parked (D1).
_ASKING_RELATIONS = ("downloading_from", "both")

# The download states that say what a source holds of what we lack (D3).
_SOURCE_ROLES = {
    "downloading": SourceRole.SENDING,
    "queued": SourceRole.QUEUED,
    "no_needed_parts": SourceRole.NOTHING_NEW,
}

# States aMule leaves on its own: no role here, the domain's ``carried_role`` keeps the latest one.
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

# Result keys consumed by a structured field, hence EXCLUDED from raw_metadata.
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
    "waiting": WaitingReason.LOCAL_PROCESSING,
    "hashing": WaitingReason.LOCAL_PROCESSING,
    "allocating": WaitingReason.LOCAL_PROCESSING,
    "completing": WaitingReason.LOCAL_PROCESSING,
}


def map_search_results(
    search_results: object, *, keyword: Keyword
) -> tuple[tuple[ReportedFile, ...], int]:
    """The ``results[]`` of a search → ``(reported_files, skipped_result_count)``, counting the
    results that yield no reported file; a nameless name row beside a named one is not counted."""
    reported_files: list[ReportedFile] = []
    skipped_result_count = 0
    if not isinstance(search_results, list):
        return (), 0  # unexpected envelope: tolerated, ignored (not a result set)
    for search_result in search_results:
        mapped = _map_result(search_result, keyword=keyword)
        if not mapped:
            skipped_result_count += 1
        reported_files.extend(mapped)
    return tuple(reported_files), skipped_result_count


def map_download_status(row: object) -> DownloadStatus | None:
    """A /downloads row, or ``None`` if the hash is unusable. Only ``completed`` completes: it
    is the one status amuleapi reserves for a file verified and moved (spec stage 2, D10)."""
    if not isinstance(row, dict):
        return None
    native_id = _hash_hex(row.get("hash"))
    if native_id is None:
        return None
    status = _string(row.get("status")) or ""
    completed = status == "completed"
    failure = FailureReason.ERROR if status == "erroneous" else None
    waiting = None if completed or failure else _waiting_reason(status, sources=row.get("sources"))
    return DownloadStatus(
        file=FileKey(network=Network.ED2K, native_id=native_id),
        bytes_done=_int_or_zero(row.get("completed_bytes")),
        size_bytes=_int_or_zero(row.get("size_bytes")),
        completed=completed,
        waiting_reason=waiting,
        failure_reason=failure,
    )


def map_shared_download(row: object) -> DownloadStatus | None:
    """A /shared row as a download completed then cleared, or ``None`` if the hash is unusable.
    Partfiles are shared too, so the caller reads it only for a file the queue no longer lists."""
    if not isinstance(row, dict):
        return None
    native_id = _hash_hex(row.get("hash"))
    if native_id is None:
        return None
    size = _int_or_zero(row.get("size_bytes"))
    return DownloadStatus(
        file=FileKey(network=Network.ED2K, native_id=native_id),
        bytes_done=size,
        size_bytes=size,
        completed=True,
        waiting_reason=None,
        failure_reason=None,
    )


def map_client_status(status: object, *, version: object) -> ClientStatus:
    """A /status and a /version body → ``ClientStatus``. Never raises: missing reads unknown."""
    body = _as_dict(status)
    ed2k, kad = _as_dict(body.get("ed2k")), _as_dict(body.get("kad"))
    high_id, firewalled = ed2k.get("high_id"), kad.get("firewalled_tcp")
    channels = (
        _channel(
            Channel("ed2k"),
            channel_json=ed2k,
            connectable=high_id if isinstance(high_id, bool) else None,
        ),
        _channel(
            Channel("kad"),
            channel_json=kad,
            connectable=not firewalled if isinstance(firewalled, bool) else None,
        ),
    )
    return ClientStatus(version=_string(_as_dict(version).get("daemon_version")), channels=channels)


def offering_source_ecid(row: object) -> int | None:
    """The ``ecid`` to ask the detail of, for a row of ``GET /downloads/{hash}/clients`` that
    offers us the file (D1); ``None`` for any other."""
    if not isinstance(row, dict):
        return None
    if row.get("role") not in _ASKING_RELATIONS and row.get("a4af") is not True:
        return None
    return _optional_int(row.get("ecid"))


def map_source(row: dict[str, Any], *, detail: dict[str, Any]) -> SourceReading:
    """A source's row, which alone carries its relation to the file, and its client detail."""
    asked = row.get("role") in _ASKING_RELATIONS
    software = (_string(row.get("software")), _string(row.get("software_version")))
    return SourceReading(
        source=_source_key(row.get("user_hash")),
        source_name=_string(row.get("name")),
        software=" ".join(part for part in software if part) or None,
        role=_source_role(row.get("download_state")) if asked else SourceRole.STANDBY,
        contact_point=_contact_point(detail),
        connectable=_connectable(detail),
        raw_metadata=JsonObjectText.from_object(
            {
                **_source_metadata(row, keys=_SOURCE_META_KEYS),
                **_source_metadata(detail, keys=_SOURCE_DETAIL_META_KEYS),
            }
        ),
        session_received_bytes=_int_or_zero(row.get("downloaded_bytes_session")),
    )


def merge_duplicate_sources(readings: Iterable[SourceReading]) -> tuple[SourceReading, ...]:
    """One reading per source, by user hash or else by name: the most informative role, and the
    larger ``session_received_bytes`` (D7). A reading with neither is never merged."""
    merged: dict[object, SourceReading] = {}
    for reading in readings:
        identity = reading.source or reading.source_name or object()
        held = merged.get(identity)
        if held is not None:
            best = min(held, reading, key=lambda kept: _INFORMATIVE_ROLES.index(kept.role))
            counter = max(held.session_received_bytes, reading.session_received_bytes)
            reading = replace(best, session_received_bytes=counter)
        merged[identity] = reading
    return tuple(merged.values())


def _source_key(user_hash: object) -> SourceKey | None:
    """No identity for a hash amuleapi does not have yet, rather than one shared by all (D7)."""
    native_id = _hash_hex(user_hash)
    if native_id is None or native_id == _NO_USER_HASH:
        return None
    return SourceKey(network=Network.ED2K, native_id=native_id)


def _source_role(state: object) -> SourceRole | None:
    """Any state that is neither says nothing of the parts we lack: ``undetermined`` (D3)."""
    if not isinstance(state, str):
        return SourceRole.UNDETERMINED
    if state in _PASSING_STATES:
        return None
    return _SOURCE_ROLES.get(state, SourceRole.UNDETERMINED)


def _contact_point(detail: dict[str, Any]) -> ContactPoint | None:
    """The eD2k server the source connects through (D3); ``None`` when ``ip:port`` names none, an
    unknown server's ``null`` included."""
    return parse_contact_point(
        Network.ED2K, server=f"{detail.get('server_ip')}:{detail.get('server_port')}"
    )


def _connectable(detail: dict[str, Any]) -> bool | None:
    """``high_id``, unknown while the client has no eD2k id (``ed2k_user_id`` 0) (D3)."""
    high_id = detail.get("high_id")
    if not _optional_int(detail.get("ed2k_user_id")) or not isinstance(high_id, bool):
        return None
    return high_id


def _source_metadata(fields: dict[str, Any], *, keys: tuple[str, ...]) -> dict[str, object]:
    """The ``keys`` that ``fields`` holds; an absent one is left out, not read as ``None``."""
    return {key: _meta_value(fields[key]) for key in keys if key in fields}


def _meta_value(field: object) -> str | int | bool | list[str] | None:
    """A JSON value as the catalog keeps it: a list as a list of text, anything else unforeseen
    as its JSON text."""
    if field is None or isinstance(field, int | bool):
        return field
    if isinstance(field, list):
        return [_render(element) for element in field]
    return _render(field)


def _channel(
    channel: Channel, *, channel_json: dict[str, Any], connectable: bool | None
) -> ChannelStatus:
    """Off the network the flag tells nothing: there ``high_id`` false means "no id yet"."""
    connected = channel_json.get("state") == "connected"
    return ChannelStatus(
        channel=channel, connected=connected, connectable=connectable if connected else None
    )


def _map_result(search_result: object, *, keyword: Keyword) -> list[ReportedFile]:
    """One result row → one reported file PER FILENAME; none when the row is unusable."""
    if not isinstance(search_result, dict):
        return []
    native_id = _hash_hex(search_result.get("hash"))
    # A malformed size drops the result: read as 0, it would catalogue a file aMule cannot fetch.
    size_bytes = _optional_int(search_result.get("size_bytes"))
    if native_id is None or size_bytes is None:
        return []
    media = _as_dict(search_result.get("media"))
    unmapped = _unmapped(search_result, media=media)
    codec, file_type = _string(media.get("codec")), _string(search_result.get("file_type"))
    alternates = search_result.get("alternate_names")
    name_rows: list[object] = [search_result, *(alternates if isinstance(alternates, list) else [])]
    reported_files: list[ReportedFile] = []
    for name_row in name_rows:
        fields = _as_dict(name_row)
        name = _string(fields.get("name"))
        if name is None:
            continue
        total, complete = _source_counts(fields.get("sources"))
        reported_files.append(
            ReportedFile(
                file=FileKey(network=Network.ED2K, native_id=native_id),
                filename=name,
                size_bytes=size_bytes,
                source_count=total,
                keyword=keyword,
                duration_seconds=_optional_int(media.get("duration_seconds")),
                bitrate_kbps=_optional_int(media.get("bitrate_kilobits_per_second")),
                raw_metadata=fold_raw_metadata(
                    unmapped, codec=codec, file_type=file_type, complete_source_count=complete
                ),
            )
        )
    return reported_files


def _unmapped(search_result: dict[str, Any], *, media: dict[str, Any]) -> dict[str, object]:
    """Every key no field consumes, ``media``'s under ``media`` when it holds one, each value
    rendered as text."""
    unmapped: dict[str, object] = {
        replace_surrogates(key): _render(field)
        for key, field in search_result.items()
        if key not in _MAPPED_KEYS
    }
    unmapped_media = {
        replace_surrogates(key): _render(field)
        for key, field in media.items()
        if key not in _MAPPED_MEDIA_KEYS
    }
    if unmapped_media:
        unmapped["media"] = unmapped_media
    return unmapped


def _render(field: object) -> str:
    """Rendering that NEVER raises: text as-is, anything else as JSON, surrogates replaced."""
    return replace_surrogates(
        field if isinstance(field, str) else json.dumps(field, ensure_ascii=False)
    )


def _as_dict(field: object) -> dict[str, Any]:
    return field if isinstance(field, dict) else {}


def _string(field: object) -> str | None:
    """A blank string reads as absent: an empty name is as unusable as a missing one."""
    return replace_surrogates(field) if isinstance(field, str) and field else None


def _hash_hex(field: object) -> str | None:
    """Lowercased MD4 hash, or ``None``: without it the row has no identifier at all."""
    if not isinstance(field, str) or len(field) != _HASH_LENGTH:
        return None
    lowered = field.lower()
    return lowered if all(character in "0123456789abcdef" for character in lowered) else None


def _int_or_zero(field: object) -> int:
    """Reads as 0 what ``_optional_int`` reads as ``None``: absent or malformed."""
    quantity = _optional_int(field)
    return 0 if quantity is None else quantity


def _optional_int(field: object) -> int | None:
    """Keeps "the daemon reported nothing" distinct from a reported zero. A ``bool``, a negative
    integer or one past what the catalog holds is malformed: every field it reads is unsigned."""
    if isinstance(field, bool) or not isinstance(field, int):
        return None
    return field if is_quantity(field) else None


def _source_counts(field: object) -> tuple[int, int]:
    sources = _as_dict(field)
    return _int_or_zero(sources.get("total")), _int_or_zero(sources.get("complete"))


def _waiting_reason(status: str, *, sources: object) -> WaitingReason | None:
    """The status's own reason first, then the sources: none at all, or none sending."""
    reason = _WAITING_STATUSES.get(status)
    if reason is not None:
        return reason
    counts = _as_dict(sources)
    if _int_or_zero(counts.get("total")) == 0:
        return WaitingReason.NO_SOURCE
    return WaitingReason.REMOTE_QUEUE if _int_or_zero(counts.get("transferring")) == 0 else None
