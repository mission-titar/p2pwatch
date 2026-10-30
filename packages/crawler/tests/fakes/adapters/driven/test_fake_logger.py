from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine


def test_a_logged_line_keeps_its_level_and_its_formatted_message() -> None:
    logger = FakeLogger()

    logger.debug("read %d downloads", 3)
    logger.info("searched '%s'", "keroro")
    logger.warning("backoff %.1fs", 2.0)
    logger.error("100% lost")

    assert logger.lines == [
        LoggedLine(level="debug", message="read 3 downloads"),
        LoggedLine(level="info", message="searched 'keroro'"),
        LoggedLine(level="warning", message="backoff 2.0s"),
        LoggedLine(
            level="error", message="100% lost"
        ),  # no argument: kept as written, as logging does
    ]
