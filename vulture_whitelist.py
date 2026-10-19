# A rare exit (AGENTS.md): a hook only a library calls, which no rewrite can show vulture.
_.optionxform  # amule domain/conf.py: configparser calls it on every option name
_.row_factory  # crawler adapters/driven/persistence_sqlite/reader.py: sqlite3 builds rows with it
_.should_exit  # crawler adapters/driving/webui/uvicorn_server_thread.py: uvicorn polls it
