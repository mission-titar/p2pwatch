"""A 4.x catalog (version 5) of N observations that share no variant: make_nofold.py OUT_DIR N."""
import json, sqlite3, sys
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path
from p2pwatch.adapters.driven.persistence_sqlite.migration_scripts import load_scripts
out, count = Path(sys.argv[1]), int(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
c = sqlite3.connect(out / "catalog.db", autocommit=True)
c.execute("PRAGMA journal_mode=WAL")
for m in load_scripts(resources.files("p2pwatch.adapters.driven.persistence_sqlite") / "migrations" / "catalog"):
    if m.version > 5: break
    c.execute("BEGIN"); c.executescript(m.script); c.execute(f"PRAGMA user_version={m.version}"); c.execute("COMMIT")
start = datetime(2026, 8, 1, tzinfo=UTC)
hashes = [f"{n:032x}" for n in range(1000, 3000)]
c.execute("BEGIN")
c.executemany("INSERT INTO files (ed2k_hash, size_bytes, aich_hash) VALUES (?, ?, NULL)", [(h, 1000) for h in hashes])
c.executemany(
    "INSERT INTO file_observations (ed2k_hash, filename, size_bytes, source_count, complete_source_count,"
    " media_length_sec, bitrate_kbps, codec, file_type, raw_meta, keyword, observed_at, node_id)"
    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
    ((hashes[n % 2000], f"Keroro mission Titar episode name number {n}.avi", 1000, n % 13, n % 3, n % 1400, n % 5000,
      "xvid", "Video", json.dumps([["media.title", f"title {n}"], ["0x0308", str(n % 7)]]), "keroro",
      (start + timedelta(microseconds=n * 1_000_003)).isoformat(timespec="microseconds"), "node-a")
     for n in range(count)))
c.execute("COMMIT"); c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
print("version", c.execute("PRAGMA user_version").fetchone()[0], "size", (out / "catalog.db").stat().st_size)
