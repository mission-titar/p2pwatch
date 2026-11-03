---
paths:
  - "packages/crawler/src/p2pwatch/adapters/driven/config/**"
  - "packages/crawler/src/p2pwatch/adapters/driven/amule_api/mapping.py"
  - "packages/crawler/src/p2pwatch/domain/value_bounds.py"
  - "packages/crawler/src/p2pwatch/application/use_cases/merge_catalogs.py"
---

# Text encoding

- **The node supports UTF-8 text only**: a text that is not valid UTF-8 is refused where the operator wrote it (the config files, the environment variables they read) or where another catalog holds it (`merge`), and replaced with U+FFFD where a network sent it (the mapper). The domain values carrying network data refuse one when they are built (`domain/value_bounds.py`), so a mapper that forgets to clean fails in its own tests, not in a store.
