"""v4.1.0's engine over the real catalog (read-only): dumps the inputs, v4's decisions and the persisted ones."""

import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

from catalog_matching.engine import MatchingEngine
from catalog_matching.validation import parse_matcher_config, parse_targets
from mulewatch.adapters.config.yaml_loader import load_yaml
from mulewatch.adapters.persistence_sqlite import sightings
from mulewatch.adapters.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from mulewatch.domain.observation import candidate_from_fields

cfg = Path(sys.argv[1])
out = Path(sys.argv[2])
uri = "file:/home/geoffrey/Projets/mulewatch/data/catalog.db?mode=ro"

connection = sqlite3.connect(uri, uri=True)
connection.row_factory = sqlite3.Row
engine = MatchingEngine(
    parse_matcher_config(load_yaml(cfg / "matcher.yml")), parse_targets(load_yaml(cfg / "targets.yml"))
)
repository = SqliteCatalogRepository(connection, "audit")
inputs = []
v4_decisions = {}
persisted = {}
for latest in sightings.iter_latest_sightings(connection):
    names = sightings.known_names(connection, latest.ed2k_hash)
    inputs.append(
        {
            "hash": latest.ed2k_hash,
            "filename": latest.names[0],
            "size_bytes": latest.size_bytes,
            "duration_seconds": latest.media_length_sec,
            "bitrate_kbps": latest.bitrate_kbps,
            "known_filenames": list(names),
        }
    )
    candidate = candidate_from_fields(
        latest.names[0], latest.size_bytes, latest.media_length_sec, latest.bitrate_kbps
    )
    fresh = engine.evaluate_all(replace(candidate, filename=name) for name in names)
    v4_decisions[latest.ed2k_hash] = sorted(
        [d.target_id, d.rule_name, str(d.tier)] for d in fresh
    )
    persisted[latest.ed2k_hash] = sorted(
        [r.target_id, r.rule_name, str(r.tier)]
        for r in repository.last_decisions(latest.ed2k_hash).values()
        if r.tier != "retracted"
    )
out.mkdir(exist_ok=True)
(out / "inputs.json").write_text(json.dumps(inputs, ensure_ascii=False))
(out / "decisions.json").write_text(json.dumps(v4_decisions, ensure_ascii=False))
(out / "persisted.json").write_text(json.dumps(persisted, ensure_ascii=False))
print(f"files={len(inputs)} with_decision={sum(1 for v in v4_decisions.values() if v)}")
