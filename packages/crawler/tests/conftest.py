from random import Random

import pytest

# pytest rewrites the asserts of test modules only, and the contracts' run through their subclasses.
pytest.register_assert_rewrite("tests.contracts")

pytest_plugins = [
    "tests.support.adapters.driven.persistence_sqlite.migrated_databases",
    "tests.support.virtual_time",
]


@pytest.fixture
def randomness(request: pytest.FixtureRequest) -> Random:
    """The test's draws, the same on every run: a ``str`` seed is hashed by SHA-512, never by
    ``hash``, which ``PYTHONHASHSEED`` salts."""
    return Random(request.node.nodeid)
