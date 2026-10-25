import pytest

from tests.fakes.adapters.driven.fake_blocking_monotonic_clock import FakeBlockingMonotonicClock


def test_the_blocking_clock_refuses_the_time_the_download_loop_never_reads() -> None:
    with pytest.raises(AssertionError, match="no time"):
        FakeBlockingMonotonicClock().now()
