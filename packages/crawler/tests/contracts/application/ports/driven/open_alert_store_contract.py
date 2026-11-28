"""The promise of the ``OpenAlertReader`` and ``OpenAlertWriter`` pair."""

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

import pytest

from p2pwatch.application.ports.driven.open_alert_reader import OpenAlertReader
from p2pwatch.application.ports.driven.open_alert_writer import OpenAlertWriter
from tests.support.domain.health_alerts import UNREACHABLE, UNREPAIRED


class OpenAlertStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> OpenAlertWriter:
        """The writer of a store just built."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> OpenAlertReader:
        """The reader of the writer's store."""

    def test_no_alert_is_open_before_the_first_set(self, reader: OpenAlertReader) -> None:
        assert reader.read_open_alerts() == ()

    def test_the_alerts_set_are_read_in_their_order(
        self, *, writer: OpenAlertWriter, reader: OpenAlertReader
    ) -> None:
        writer.set_open_alerts((UNREACHABLE, UNREPAIRED))
        assert reader.read_open_alerts() == (UNREACHABLE, UNREPAIRED)

    def test_a_set_replaces_the_alerts_set_before(
        self, *, writer: OpenAlertWriter, reader: OpenAlertReader
    ) -> None:
        writer.set_open_alerts((UNREACHABLE, UNREPAIRED))
        writer.set_open_alerts((UNREPAIRED,))
        assert reader.read_open_alerts() == (UNREPAIRED,)

    def test_the_alerts_set_are_read_from_another_thread(
        self, *, writer: OpenAlertWriter, reader: OpenAlertReader
    ) -> None:
        writer.set_open_alerts((UNREACHABLE,))
        with ThreadPoolExecutor(max_workers=1) as executor:
            open_alerts = executor.submit(reader.read_open_alerts).result()
        assert open_alerts == (UNREACHABLE,)
