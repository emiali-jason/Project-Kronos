"""Provider-agnostic market-data contract."""

from typing import Protocol


class MarketDataProvider(Protocol):
    """Contract for provider market-data capabilities."""
