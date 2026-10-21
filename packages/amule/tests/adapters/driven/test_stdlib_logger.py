import logging

import pytest

from p2pwatch_amule.adapters.driven.stdlib_logger import StdlibLogger

_NAME = "p2pwatch_amule.adapters.driving.port_sync"


def test_each_level_writes_a_record_of_the_named_logger(caplog: pytest.LogCaptureFixture) -> None:
    logger = StdlibLogger(_NAME)

    with caplog.at_level(logging.INFO, logger=_NAME):
        logger.info("gluetun forwards %d", 51820)
        logger.warning("gluetun reports no forwarded port (%r)", b"{}")
        logger.error("amule.conf was not written (%s)", "disk full")

    assert [(record.name, record.levelno, record.getMessage()) for record in caplog.records] == [
        (_NAME, logging.INFO, "gluetun forwards 51820"),
        (_NAME, logging.WARNING, "gluetun reports no forwarded port (b'{}')"),
        (_NAME, logging.ERROR, "amule.conf was not written (disk full)"),
    ]


def test_a_record_carries_its_callers_location(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=_NAME):
        StdlibLogger(_NAME).info("restarting amuled")

    assert (caplog.records[0].pathname, caplog.records[0].funcName) == (
        __file__,
        "test_a_record_carries_its_callers_location",
    )
