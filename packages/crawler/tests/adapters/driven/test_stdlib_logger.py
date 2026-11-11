import logging

import pytest

from p2pwatch.adapters.driven.stdlib_logger import StdlibLogger

_NAME = "p2pwatch.application.example"


def test_each_level_writes_a_record_of_the_named_logger(caplog: pytest.LogCaptureFixture) -> None:
    logger = StdlibLogger(_NAME)

    with caplog.at_level(logging.DEBUG, logger=_NAME):
        logger.debug("read %d downloads", 3)
        logger.info("searched '%s'", "keroro")
        logger.warning("backoff %.1fs", 2.0)
        logger.error("backoff not saved (%s)", "database is locked")

    assert [(record.name, record.levelno, record.getMessage()) for record in caplog.records] == [
        (_NAME, logging.DEBUG, "read 3 downloads"),
        (_NAME, logging.INFO, "searched 'keroro'"),
        (_NAME, logging.WARNING, "backoff 2.0s"),
        (_NAME, logging.ERROR, "backoff not saved (database is locked)"),
    ]


def test_a_record_carries_its_callers_location(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=_NAME):
        StdlibLogger(_NAME).info("searched")

    assert (caplog.records[0].pathname, caplog.records[0].funcName) == (
        __file__,
        "test_a_record_carries_its_callers_location",
    )


def test_an_exception_writes_an_error_record_with_its_errors_trace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = KeyError("channels")

    with caplog.at_level(logging.ERROR, logger=_NAME):
        StdlibLogger(_NAME).exception("bug in %s", "status reading", error=error)

    [record] = caplog.records
    assert (record.levelno, record.getMessage(), record.funcName) == (
        logging.ERROR,
        "bug in status reading",
        "test_an_exception_writes_an_error_record_with_its_errors_trace",
    )
    assert record.exc_info is not None
    assert record.exc_info[1] is error
