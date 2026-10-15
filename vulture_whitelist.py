# Library hooks vulture sees no caller of; the names templates read come from template_checks.
_.optionxform  # amule boot/conf.py: configparser calls it on every option name
_.row_factory  # crawler persistence_sqlite/reader.py: sqlite3 builds each fetched row with it
_.should_exit  # crawler composition/app.py: uvicorn's Server.main_loop polls it
_.dispatch  # crawler webui/composition/app.py: starlette's BaseHTTPMiddleware calls it per request
