---
paths:
  - "packages/crawler/src/p2pwatch/adapters/driven/persistence_sqlite/**"
  - "packages/crawler/src/p2pwatch/adapters/driven/in_memory_*_store.py"
---

# Stores

- **A store has no clock**: a SQLite store, or `InMemoryStatusReadingStore`, stores the instants it is given and decides no wait; its caller reads the clock right before each write (`wall_clock.now()` for a row). An adapter other than a store may hold a clock for its own I/O: a `MonotonicClock` for the amuleapi client's start pacing and search deadlines and the SQL console's query budget, a `WallClock` for the instant that names a pre-migration copy and a `Ticker` for the lines reporting its progress.
