import logging

import pytest

from p2pwatch.adapters.driven.stdlib_logger import StdlibLogger

_NAME = "p2pwatch.application.example"


def test_each_level_writes_a_record_of_the_named_logger(caplog: pytest.LogCaptureFixture) -> None:
    logger = StdlibLogger(_NAME)

    with caplog.at_level(logging.INFO, logger=_NAME):
        logger.info("searched '%s'", "keroro")
        logger.warning("backoff %.1fs", 2.0)
        logger.error("backoff not saved (%s)", "database is locked")

    assert [(record.name, record.levelno, record.getMessage()) for record in caplog.records] == [
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
