"""same_content.py A.db B.db: same user_version, same schema, and every table's rows equal both ways."""

import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
connection.execute("PRAGMA temp_store=FILE")
connection.execute("ATTACH ? AS b", (f"file:{sys.argv[2]}?mode=ro",))
ok = True
versions = (connection.execute("PRAGMA main.user_version").fetchone()[0], connection.execute("PRAGMA b.user_version").fetchone()[0])
print("user_version", versions)
ok &= versions[0] == versions[1]
schema_a = sorted(connection.execute("SELECT type, name, sql FROM main.sqlite_master").fetchall(), key=str)
schema_b = sorted(connection.execute("SELECT type, name, sql FROM b.sqlite_master").fetchall(), key=str)
print("schema equal", schema_a == schema_b)
ok &= schema_a == schema_b
for (table,) in connection.execute("SELECT name FROM main.sqlite_master WHERE type = 'table'").fetchall():
    counts = [connection.execute(f"SELECT COUNT(*) FROM {s}.{table}").fetchone()[0] for s in ("main", "b")]
    only_a = connection.execute(f"SELECT COUNT(*) FROM (SELECT * FROM main.{table} EXCEPT SELECT * FROM b.{table})").fetchone()[0]
    only_b = connection.execute(f"SELECT COUNT(*) FROM (SELECT * FROM b.{table} EXCEPT SELECT * FROM main.{table})").fetchone()[0]
    print(table, counts, "only in A", only_a, "only in B", only_b)
    ok &= counts[0] == counts[1] and only_a == 0 and only_b == 0
print("SAME CONTENT" if ok else "DIFFERENT")
