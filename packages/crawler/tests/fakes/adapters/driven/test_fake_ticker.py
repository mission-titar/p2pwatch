import pytest

from p2pwatch.application.ports.driven.ticker import Ticker
from tests.contracts.application.ports.driven.ticker_contract import TickerContract
from tests.fakes.adapters.driven.fake_ticker import FakeTicker


class TestFakeTicker(TickerContract):
    @pytest.fixture
    def ticker(self) -> FakeTicker:
        return FakeTicker()

    def let_periods_pass(self, ticker: Ticker, *, periods: int) -> None:
        assert isinstance(ticker, FakeTicker)
        for _ in range(periods):
            ticker.tick()
