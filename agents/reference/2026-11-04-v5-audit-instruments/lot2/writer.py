import sqlite3, sys, time
c = sqlite3.connect(sys.argv[1], autocommit=True)  # Python's default 5 s busy timeout, as the crawler
c.execute("PRAGMA journal_mode=WAL"); c.execute("CREATE TABLE IF NOT EXISTS probe_writes(t REAL)")
end = time.monotonic() + float(sys.argv[2]); ok = fail = 0; worst = 0.0
while time.monotonic() < end:
    t = time.monotonic()
    try:
        c.execute("BEGIN IMMEDIATE"); c.execute("INSERT INTO probe_writes VALUES (?)", (t,)); c.execute("COMMIT"); ok += 1
    except sqlite3.OperationalError as e:
        fail += 1; print("write failed:", e, flush=True)
        if c.in_transaction: c.execute("ROLLBACK")
    worst = max(worst, time.monotonic() - t); time.sleep(0.2)
print(f"writes ok {ok}, failed {fail}, slowest {worst:.2f} s", flush=True)
