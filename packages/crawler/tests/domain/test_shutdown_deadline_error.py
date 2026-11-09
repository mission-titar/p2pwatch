from p2pwatch.domain.shutdown_deadline_error import ShutdownDeadlineError


def test_a_fired_shutdown_deadline_is_no_timeout_error() -> None:
    assert not issubclass(ShutdownDeadlineError, TimeoutError)
