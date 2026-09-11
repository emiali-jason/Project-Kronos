"""Provider-neutral full quote facts; no analytical or execution authority."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DepthLevel:
    price: Decimal
    quantity: int
    orders: int | None

    def __post_init__(self):
        if (not isinstance(self.price, Decimal) or not self.price.is_finite() or self.price < 0
                or type(self.quantity) is not int or self.quantity < 0
                or self.orders is not None and (type(self.orders) is not int or self.orders < 0)):
            raise ValueError("FULL_QUOTE_DEPTH_INVALID")


@dataclass(frozen=True, slots=True)
class FullQuote:
    provider_record_identity: str
    provider: str
    exchange: str
    trading_symbol: str
    provider_instrument_token: int
    exchange_timestamp: datetime | None
    last_trade_timestamp: datetime | None
    last_price: Decimal | None
    volume: int | None
    ohlc: tuple[tuple[str, Decimal | None], ...]
    total_bid_quantity: int | None
    total_ask_quantity: int | None
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]
    oi: int | None
    availability: tuple[tuple[str, str], ...]
    provenance: tuple[tuple[str, str], ...]

    def __post_init__(self):
        if (not self.provider_record_identity or not self.provider or not self.exchange
                or not self.trading_symbol or type(self.provider_instrument_token) is not int
                or self.provider_instrument_token <= 0 or len(self.bids) > 5 or len(self.asks) > 5
                or any(type(x) is not DepthLevel for x in (*self.bids, *self.asks))):
            raise ValueError("FULL_QUOTE_IDENTITY_INVALID")
        for ts in (self.exchange_timestamp, self.last_trade_timestamp):
            if ts is not None and (not isinstance(ts, datetime) or ts.tzinfo is None):
                raise ValueError("FULL_QUOTE_TIMESTAMP_INVALID")
        for n in (self.volume, self.oi, self.total_bid_quantity, self.total_ask_quantity):
            if n is not None and (type(n) is not int or n < 0):
                raise ValueError("FULL_QUOTE_QUANTITY_INVALID")
        for n in (self.last_price, *(v for _, v in self.ohlc)):
            if n is not None and (not isinstance(n, Decimal) or not n.is_finite() or n < 0):
                raise ValueError("FULL_QUOTE_PRICE_INVALID")
