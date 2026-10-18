# A rare exit (AGENTS.md): a hook only a library calls, which no rewrite can show vulture.
_.optionxform  # amule domain/conf.py: configparser calls it on every option name
_.row_factory  # crawler persistence_sqlite/reader.py: sqlite3 builds each fetched row with it
_.should_exit  # crawler webui/uvicorn_server_thread.py: uvicorn's main_loop polls it
