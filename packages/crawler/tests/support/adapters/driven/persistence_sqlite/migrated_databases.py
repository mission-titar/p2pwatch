"""Pytest fixtures: a migrated catalog.db and local.db."""

from pathlib import Path

import pytest

from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_catalog,
    open_local,
)


@pytest.fixture
def catalog_db(tmp_path: Path) -> Path:
    """An empty catalog.db migrated by the crawler's own migrations."""
    path = tmp_path / "catalog.db"
    open_catalog(path).close()
    return path


@pytest.fixture
def local_db(tmp_path: Path) -> Path:
    """An empty local.db migrated by the crawler's own migrations."""
    path = tmp_path / "local.db"
    open_local(path).close()
    return path
