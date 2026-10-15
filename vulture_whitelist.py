# A rare exit (AGENTS.md): a hook only a library calls, which no rewrite can show vulture.
_.optionxform  # amule boot/conf.py: configparser calls it on every option name
_.row_factory  # crawler persistence_sqlite/reader.py: sqlite3 builds each fetched row with it
_.should_exit  # crawler composition/app.py: uvicorn's Server.main_loop polls it
