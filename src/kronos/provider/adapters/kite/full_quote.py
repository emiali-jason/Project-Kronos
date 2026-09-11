"""Exact token-bound Kite batch normalization, retaining no response extras."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from kronos.provider.contracts.full_quote import FullQuote, DepthLevel


def normalize_full_quotes(raw, instruments):
    if not isinstance(raw, dict):
        raise ValueError("FULL_QUOTE_RESPONSE_INVALID")
    result = []
    for instrument in instruments:
        key = f"{instrument.exchange}:{instrument.trading_symbol}"
        item = raw.get(key)
        if item is None:
            continue
        if not isinstance(item, dict) or item.get("instrument_token") != instrument.provider_instrument_token:
            raise ValueError("FULL_QUOTE_TOKEN_MISMATCH")
        fields = dict(exchange_timestamp=_time(item.get("timestamp")),
                      last_trade_timestamp=_time(item.get("last_trade_time")),
                      last_price=_decimal(item.get("last_price")), volume=_integer(item.get("volume")),
                      total_bid_quantity=_integer(item.get("buy_quantity")),
                      total_ask_quantity=_integer(item.get("sell_quantity")), oi=_integer(item.get("oi")))
        ohlc = item.get("ohlc") or {}
        depth = item.get("depth") or {}
        fields.update(ohlc=tuple((k, _decimal(ohlc.get(k))) for k in ("open", "high", "low", "close")),
                      bids=_depth(depth.get("buy")), asks=_depth(depth.get("sell")))
        availability_fields = {k: v for k, v in fields.items() if k != "ohlc"}
        availability_fields.update({"ohlc." + k: v for k, v in fields["ohlc"]})
        availability = tuple((k, "AVAILABLE" if v is not None and v != () else "UNAVAILABLE")
                             for k, v in availability_fields.items())
        mapping = {"exchange_timestamp": "timestamp", "last_trade_timestamp": "last_trade_time",
                   "total_bid_quantity": "buy_quantity", "total_ask_quantity": "sell_quantity",
                   "bids": "depth.buy", "asks": "depth.sell"}
        result.append(FullQuote(provider_record_identity=instrument.provider_record_identity,
                                provider=instrument.provider, exchange=instrument.exchange,
                                trading_symbol=instrument.trading_symbol,
                                provider_instrument_token=instrument.provider_instrument_token,
                                availability=availability,
                                provenance=tuple((k, "KITE_FULL_QUOTE:" + mapping.get(k, k)) for k in availability_fields), **fields))
    return tuple(result)


def _decimal(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("FULL_QUOTE_NUMBER_INVALID")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("FULL_QUOTE_NUMBER_INVALID") from None
    if not result.is_finite() or result < 0:
        raise ValueError("FULL_QUOTE_NUMBER_INVALID")
    return result


def _integer(value):
    if value is None:
        return None
    n = _decimal(value)
    if n != n.to_integral_value():
        raise ValueError("FULL_QUOTE_INTEGER_INVALID")
    return int(n)


def _time(value):
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError("FULL_QUOTE_TIMESTAMP_INVALID")
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    return value.astimezone(timezone.utc)


def _depth(value):
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > 5:
        raise ValueError("FULL_QUOTE_DEPTH_INVALID")
    return tuple(DepthLevel(_decimal(x.get("price")), _integer(x.get("quantity")), _integer(x.get("orders"))) for x in value)
