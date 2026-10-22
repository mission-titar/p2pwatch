"""The pytest settings every package's tests share, loaded through the `pytest11` entry point."""

import pytest

# The first stands for `--strict-markers`, which pytest reads before it loads an entry-point plugin.
SHARED_WARNING_FILTERS = (
    "error::pytest.PytestUnknownMarkWarning",
    "error::ResourceWarning",
    "error::pytest.PytestUnraisableExceptionWarning",
)


def pytest_configure(config: pytest.Config) -> None:
    """Appends the shared filters after the package's own, so that they win over them."""
    for warning_filter in SHARED_WARNING_FILTERS:
        config.addinivalue_line("filterwarnings", warning_filter)
