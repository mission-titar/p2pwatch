"""main's reevaluation, dry, on a main-migrated catalog opened read-only: the rows it would write.

argv: migrated catalog.db, config dir, v4 output dir (inputs.json, decisions.json from evaluate.py).
Also compares main's read-path inputs and decisions with v4's, file by file. Exit 1 on any difference.
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

from catalog_matching.domain.engine import MatchingEngine, to_record
from p2pwatch.adapters.driven.config.crawler_config import read_matcher_config, read_targets
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_scan_reader import (
    SqliteCatalogScanReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.domain.file_target_decision import records_to_write

catalog, cfg, v4_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
connection = SqliteDatabaseOpener(None).open_reader(catalog)  # type: ignore[arg-type]  # copier unused
engine = MatchingEngine(
    read_matcher_config(cfg / "matcher.yml"),
    targets=read_targets(cfg / "targets.yml"),
    max_filename_length=4096,
)
observation_store = SqliteObservationStore(connection)
decision_store = SqliteDecisionStore(connection)
v4_inputs = {row["hash"]: row for row in json.loads((v4_dir / "inputs.json").read_text())}
v4_decisions = json.loads((v4_dir / "decisions.json").read_text())

input_diffs, decision_diffs, files, writes = [], [], 0, []
for observation in SqliteCatalogScanReader(connection).iter_latest_observations():
    files += 1
    reported = observation.reported_file
    native_id = reported.file.native_id
    filenames = observation_store.read_known_filenames(reported.file)
    mine = {
        "size_bytes": reported.size_bytes,
        "duration_seconds": reported.duration_seconds,
        "bitrate_kbps": reported.bitrate_kbps,
        "known_filenames": list(filenames),
    }
    theirs = v4_inputs.get(native_id)
    if theirs is None or any(theirs[k] != v for k, v in mine.items()):
        input_diffs.append((native_id, mine, theirs))
    fresh = engine.evaluate_file(
        replace(reported.to_candidate(), filename=filename) for filename in filenames
    )
    decisions = sorted([d.target_id, d.rule_name, str(d.tier)] for d in fresh)
    if decisions != v4_decisions.get(native_id):
        decision_diffs.append((native_id, decisions, v4_decisions.get(native_id)))
    persisted = decision_store.read_latest_decisions(reported.file)
    for record in records_to_write([to_record(d) for d in fresh], persisted=persisted):
        writes.append((native_id, repr(record), repr(persisted.get(record.target_id))))
print(f"files main={files} v4={len(v4_inputs)}")
print(f"input differences: {len(input_diffs)}")
for diff in input_diffs[:10]:
    print("  ", diff)
print(f"decision differences vs v4: {len(decision_diffs)}")
for diff in decision_diffs[:10]:
    print("  ", diff)
print(f"rows the reevaluation would write: {len(writes)}")
for write in writes[:10]:
    print("  ", write)
download_candidates = decision_store.read_download_candidates()
print(f"download candidates: {len(download_candidates)}")
sys.exit(1 if input_diffs or decision_diffs or writes or files != len(v4_inputs) else 0)
