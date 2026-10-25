import pytest

# pytest rewrites the asserts of test modules only, and the contracts' run through their subclasses.
pytest.register_assert_rewrite("tests.contracts")

pytest_plugins = ["tests.support.adapters.driven.persistence_sqlite.migrated_databases"]
