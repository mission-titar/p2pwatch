import fcntl, sqlite3, subprocess, sys, os
db = "t.db"
if sys.argv[1:] == ["second"]:
    c = sqlite3.connect(db, autocommit=True, timeout=0)
    c.execute("PRAGMA locking_mode=EXCLUSIVE")
    try:
        c.execute("BEGIN EXCLUSIVE"); c.execute("INSERT INTO t VALUES (2)"); c.execute("COMMIT")
        print("second: exclusive-mode write OK")
    except sqlite3.Error as e:
        print("second: exclusive-mode refused:", e)
    fd = os.open(db, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); print("second: flock acquired")
    except OSError as e:
        print("second: flock refused:", e)
    sys.exit()
c = sqlite3.connect(db, autocommit=True)
c.execute("PRAGMA journal_mode=WAL"); c.execute("CREATE TABLE IF NOT EXISTS t(x)"); c.execute("INSERT INTO t VALUES (1)")
c.execute("SELECT * FROM t").fetchall()
fd = os.open(db, os.O_RDONLY); fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
print("first: idle WAL connection open, flock shared held")
subprocess.run([sys.executable, __file__, "second"])
try:
    c.execute("INSERT INTO t VALUES (3)"); print("first: still writes after second:", c.execute("SELECT count(*) FROM t").fetchone())
except sqlite3.Error as e:
    print("first: write after second fails:", e)
