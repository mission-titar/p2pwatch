"""Read-only Python scan of the real catalog: replays catalog/0007's transforms with main's functions.

Counts text that is not valid UTF-8, raw_meta shapes the fold does not expect, folds that raise,
stamps iso_to_micros refuses, and the observations 0007's ON CONFLICT DO NOTHING drops.
"""

import json
import sqlite3
import sys
import time
from collections import Counter

from p2pwatch.adapters.driven.persistence_sqlite import micros
from p2pwatch.adapters.driven.persistence_sqlite.variants import (
    _unmapped_from_pairs,
    content_hash_by_position,
)
from p2pwatch.domain.observation import fold_raw_metadata

CATALOG = "file:/home/geoffrey/Projets/mulewatch/data/catalog.db?mode=ro"
iso_to_micros = micros.iso_to_micros  # type: ignore[deprecated]

counts: Counter[str] = Counter()
examples: dict[str, object] = {}


def note(case: str, example: object) -> None:
    counts[case] += 1
    examples.setdefault(case, example)


def decode(value: object, *, column: str, row_id: int) -> object:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            note(f"{column}: not valid UTF-8", row_id)
            return value.decode("utf-8", "replace")
    return value


def inspect_raw(raw: str, row_id: int) -> None:
    pairs = json.loads(raw)
    if not isinstance(pairs, list):
        note("raw_meta: not a list", raw[:200])
        return
    names = []
    for pair in pairs:
        if not (isinstance(pair, list) and len(pair) == 2):
            note("raw_meta: element not a 2-list", raw[:200])
            continue
        name, value = pair
        if not isinstance(name, str):
            note("raw_meta: name not a string", raw[:200])
        if not isinstance(value, str):
            note(f"raw_meta: value of type {type(value).__name__}", raw[:200])
        names.append(name)
    repeated = [name for name, n in Counter(names).items() if n > 1]
    if repeated:
        note("raw_meta (distinct): a repeated name, the fold keeps its last value", raw[:300])
    if "media" in names and any(isinstance(n, str) and n.startswith("media.") for n in names):
        note("raw_meta (distinct): 'media' beside 'media.*', the fold overwrites", raw[:300])
    if any(name == "media." for name in names):
        note("raw_meta (distinct): bare 'media.' name", raw[:300])
    for name in names:
        counts[f"raw_meta name {name!r}"] += 0  # registered, counted below


folded_memo: dict[tuple[object, ...], str | None] = {}
variants: dict[tuple[object, ...], int] = {}
observation_keys: set[int] = set()
raw_seen: set[str] = set()
name_counter: Counter[str] = Counter()

connection = sqlite3.connect(CATALOG, uri=True)
connection.execute("PRAGMA query_only=ON")
connection.text_factory = bytes
started = time.monotonic()
cursor = connection.execute(
    "SELECT id, ed2k_hash, filename, media_length_sec, bitrate_kbps, raw_meta, codec, file_type,"
    " complete_source_count, keyword, node_id, observed_at, source_count FROM file_observations"
)
total = 0
for row in cursor:
    total += 1
    row_id = row[0]
    (ed2k_hash, filename, length, bitrate, raw, codec, file_type, complete, keyword, node_id,
     observed_at, source_count) = (
        decode(value, column=column, row_id=row_id)
        for value, column in zip(
            row[1:],
            ("ed2k_hash", "filename", "media_length_sec", "bitrate_kbps", "raw_meta", "codec",
             "file_type", "complete_source_count", "keyword", "node_id", "observed_at",
             "source_count"),
            strict=True,
        )
    )
    fold_key = (raw, codec, file_type, complete)
    if fold_key not in folded_memo:
        if raw not in raw_seen:
            raw_seen.add(raw)
            try:
                inspect_raw(raw, row_id)
                for pair in json.loads(raw):
                    name_counter[str(pair[0])] += 1
            except Exception as error:  # noqa: BLE001
                note(f"raw_meta: inspect raised {type(error).__name__}", raw[:200])
        try:
            folded_memo[fold_key] = fold_raw_metadata(
                _unmapped_from_pairs(json.loads(raw)),
                codec=codec,
                file_type=file_type,
                complete_source_count=complete,
            ).text
        except Exception as error:  # noqa: BLE001
            note(f"fold_raw_meta raises {type(error).__name__}: {error}", fold_key)
            folded_memo[fold_key] = None
    folded = folded_memo[fold_key]
    if folded is None:
        continue
    try:
        stamp = iso_to_micros(observed_at)
    except Exception as error:  # noqa: BLE001
        note(f"iso_to_micros raises {type(error).__name__}", observed_at)
        continue
    variant_key = (ed2k_hash, filename, length, bitrate, folded, keyword, node_id)
    variant_index = variants.get(variant_key)
    if variant_index is None:
        try:
            content_hash_by_position(*variant_key)
        except Exception as error:  # noqa: BLE001
            note(f"content_hash raises {type(error).__name__}", variant_key)
        variant_index = variants[variant_key] = len(variants)
    observation_keys.add(hash((variant_index, stamp, source_count)))
    if total % 2_000_000 == 0:
        print(f"  {total} rows, {time.monotonic() - started:.0f}s", flush=True)

print(f"file_observations rows scanned: {total} in {time.monotonic() - started:.0f}s")
print(f"distinct raw_meta: {len(raw_seen)}; distinct fold keys: {len(folded_memo)}")
print(f"variants 0007 would write: {len(variants)}")
print(f"observations 0007 would write: {len(observation_keys)}")
print(f"observations 0007 drops as duplicates: {total - len(observation_keys)}")
print("raw_meta names (distinct raw_meta holding each):")
for name, n in name_counter.most_common():
    print(f"   {name!r}: {n}")
print("cases:")
for case, n in sorted(counts.items()):
    if n:
        print(f"   {case}: {n}  e.g. {examples.get(case)!r}"[:600])
sys.stdout.flush()
