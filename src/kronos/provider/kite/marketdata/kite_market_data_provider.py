"""Kite market-data provider skeleton."""

from typing import Optional

from kronos.provider.contracts import MarketDataProvider


class KiteMarketDataProvider(MarketDataProvider):
    """Kite implementation placeholder for market-data capabilities."""

    def __init__(self, dependencies: Optional[object] = None) -> None:
        self._dependencies = dependencies
