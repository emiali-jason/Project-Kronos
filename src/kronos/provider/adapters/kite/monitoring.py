"""Adapter-private Kite WebSocket transport for factual Swing monitoring input."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from kiteconnect import KiteTicker as _KiteTicker

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    MonitoringConsumer,
    MonitoringDisconnect,
    MonitoringError,
    MonitoringFailure,
    ProviderMarketTick,
    ProviderOrderUpdateEvidence,
    RecoveredMarketInterval,
)


_KITE_TIMEZONE = ZoneInfo("Asia/Kolkata")
_KITE_SOURCE = "KITE_CONNECT_WEBSOCKET"


class KiteReadOnlyMonitoringSession:
    """Opaque read/observe session; raw Kite identity never crosses this seam."""

    __slots__ = (
        "__clock",
        "__connection_id",
        "__consumer",
        "__ever_connected",
        "__gap_instruments",
        "__last_disconnect",
        "__last_observed_at",
        "__record_to_token",
        "__socket",
        "__state",
        "__token_resolver",
        "__token_to_record",
    )

    def __init__(
        self,
        *,
        api_key: str,
        access_token: str,
        token_resolver: Callable[[InstrumentRecord], int | None],
        consumer: MonitoringConsumer,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        socket_factory: Callable[[str, str], object] | None = None,
    ) -> None:
        if not api_key or not access_token or not callable(token_resolver):
            raise MonitoringError(MonitoringFailure.CAPABILITY_UNAVAILABLE)
        factory = socket_factory or _create_socket
        self.__socket = factory(api_key, access_token)
        self.__token_resolver = token_resolver
        self.__consumer = consumer
        self.__clock = clock
        self.__connection_id = f"KITE-WS-{uuid4().hex}"
        self.__state = MonitoringConnectionState.DISCONNECTED
        self.__record_to_token: dict[InstrumentRecord, int] = {}
        self.__token_to_record: dict[int, InstrumentRecord] = {}
        self.__gap_instruments: set[InstrumentRecord] = set()
        self.__last_observed_at: datetime | None = None
        self.__last_disconnect: MonitoringDisconnect | None = None
        self.__ever_connected = False
        self.__wire_callbacks()

    @property
    def state(self) -> MonitoringConnectionState:
        return self.__state

    @property
    def subscriptions(self) -> tuple[InstrumentRecord, ...]:
        return tuple(sorted(self.__record_to_token, key=_instrument_key))

    @property
    def last_disconnect(self) -> MonitoringDisconnect | None:
        return self.__last_disconnect

    def connect(self) -> None:
        if self.__state is not MonitoringConnectionState.DISCONNECTED:
            raise MonitoringError(MonitoringFailure.INVALID_REQUEST)
        endpoint = getattr(self.__socket, "connect", None)
        if not callable(endpoint):
            raise MonitoringError(MonitoringFailure.PROVIDER_FAILURE)
        try:
            endpoint(threaded=True)
        except Exception:
            raise MonitoringError(MonitoringFailure.PROVIDER_FAILURE) from None

    def subscribe(self, instruments: tuple[InstrumentRecord, ...]) -> None:
        if not instruments or any(type(item) is not InstrumentRecord for item in instruments):
            raise MonitoringError(MonitoringFailure.INVALID_REQUEST)
        additions: list[int] = []
        for instrument in instruments:
            token = self.__token_resolver(instrument)
            if type(token) is not int or token <= 0:
                raise MonitoringError(MonitoringFailure.INSTRUMENT_NOT_RESOLVED)
            existing = self.__token_to_record.get(token)
            if existing is not None and existing != instrument:
                raise MonitoringError(MonitoringFailure.INSTRUMENT_BINDING_MISMATCH)
            if instrument not in self.__record_to_token:
                self.__record_to_token[instrument] = token
                self.__token_to_record[token] = instrument
                additions.append(token)
        if additions and self.__state in {
            MonitoringConnectionState.CONNECTED,
            MonitoringConnectionState.CONTEXT_INCOMPLETE,
        }:
            self.__subscribe_tokens(tuple(additions))

    def unsubscribe(self, instruments: tuple[InstrumentRecord, ...]) -> None:
        if any(type(item) is not InstrumentRecord for item in instruments):
            raise MonitoringError(MonitoringFailure.INVALID_REQUEST)
        removals: list[int] = []
        for instrument in instruments:
            token = self.__record_to_token.pop(instrument, None)
            self.__gap_instruments.discard(instrument)
            if token is not None:
                self.__token_to_record.pop(token, None)
                removals.append(token)
        if removals and self.__state is not MonitoringConnectionState.DISCONNECTED:
            endpoint = getattr(self.__socket, "unsubscribe", None)
            if not callable(endpoint):
                raise MonitoringError(MonitoringFailure.PROVIDER_FAILURE)
            try:
                endpoint(removals)
            except Exception:
                raise MonitoringError(MonitoringFailure.PROVIDER_FAILURE) from None

    def disconnect(self) -> None:
        endpoint = getattr(self.__socket, "close", None)
        try:
            if callable(endpoint):
                endpoint()
        except Exception:
            raise MonitoringError(MonitoringFailure.PROVIDER_FAILURE) from None
        finally:
            self.__set_state(MonitoringConnectionState.DISCONNECTED)

    def recover_interval(self, interval: RecoveredMarketInterval) -> None:
        """Admit only authoritative ordered Provider reconstruction."""

        if (
            type(interval) is not RecoveredMarketInterval
            or interval.instrument not in self.__gap_instruments
            or not interval.authoritative_ordering
        ):
            self.__set_state(MonitoringConnectionState.CONTEXT_INCOMPLETE)
            raise MonitoringError(MonitoringFailure.RECONCILIATION_REQUIRED)
        ordered = tuple(sorted(interval.observations, key=lambda item: item.observed_at))
        if ordered != interval.observations or any(
            left.observed_at >= right.observed_at for left, right in zip(ordered, ordered[1:])
        ):
            self.__set_state(MonitoringConnectionState.CONTEXT_INCOMPLETE)
            raise MonitoringError(MonitoringFailure.RECONCILIATION_REQUIRED)
        for tick in ordered:
            self.__consumer.on_market_tick(tick)
            self.__last_observed_at = tick.observed_at
        self.__gap_instruments.remove(interval.instrument)
        if not self.__gap_instruments:
            self.__set_state(MonitoringConnectionState.CONNECTED)

    def __wire_callbacks(self) -> None:
        for name, callback in (
            ("on_connect", self.__on_connect),
            ("on_ticks", self.__on_ticks),
            ("on_order_update", self.__on_order_update),
            ("on_close", self.__on_close),
            ("on_error", self.__on_error),
            ("on_reconnect", self.__on_reconnect),
            ("on_noreconnect", self.__on_no_reconnect),
        ):
            setattr(self.__socket, name, callback)

    def __on_connect(self, _socket: object, _response: object) -> None:
        reconnect = self.__ever_connected
        self.__ever_connected = True
        if reconnect:
            self.__gap_instruments.update(self.__record_to_token)
            if self.__last_disconnect is not None:
                self.__last_disconnect = replace(
                    self.__last_disconnect,
                    reconnected_at=self.__clock(),
                )
            self.__set_state(MonitoringConnectionState.CONTEXT_INCOMPLETE)
        else:
            self.__set_state(MonitoringConnectionState.CONNECTED)
        if self.__record_to_token:
            self.__subscribe_tokens(tuple(self.__record_to_token.values()))

    def __on_ticks(self, _socket: object, ticks: object) -> None:
        if not isinstance(ticks, list):
            raise MonitoringError(MonitoringFailure.MALFORMED_PROVIDER_DATA)
        for raw in ticks:
            tick = self.__normalize_tick(raw)
            self.__consumer.on_market_tick(tick)
            self.__last_observed_at = tick.observed_at

    def __on_order_update(self, _socket: object, raw: object) -> None:
        self.__consumer.on_order_update(self.__normalize_order_update(raw))

    def __on_close(self, _socket: object, _code: object, _reason: object) -> None:
        self.__record_disconnect()
        self.__set_state(MonitoringConnectionState.RECONNECTING)

    def __on_error(self, _socket: object, _code: object, _reason: object) -> None:
        self.__record_disconnect()
        self.__set_state(MonitoringConnectionState.RECONNECTING)

    def __on_reconnect(self, _socket: object, _attempts: object) -> None:
        self.__set_state(MonitoringConnectionState.RECONNECTING)

    def __on_no_reconnect(self, _socket: object) -> None:
        self.__set_state(MonitoringConnectionState.CONTEXT_INCOMPLETE)

    def __record_disconnect(self) -> None:
        disconnected = self.__clock()
        affected = self.subscriptions
        self.__gap_instruments.update(affected)
        self.__last_disconnect = MonitoringDisconnect(
            disconnected,
            self.__last_observed_at,
            affected,
        )

    def __normalize_tick(self, raw: object) -> ProviderMarketTick:
        if not isinstance(raw, Mapping):
            raise MonitoringError(MonitoringFailure.MALFORMED_PROVIDER_DATA)
        token = raw.get("instrument_token")
        instrument = self.__token_to_record.get(token) if type(token) is int else None
        if instrument is None:
            raise MonitoringError(MonitoringFailure.INSTRUMENT_BINDING_MISMATCH)
        observed = _kite_timestamp(raw.get("timestamp", raw.get("last_trade_time")))
        received = self.__clock()
        try:
            price = Decimal(str(raw.get("last_price")))
        except Exception:
            raise MonitoringError(MonitoringFailure.MALFORMED_PROVIDER_DATA) from None
        if not price.is_finite() or price < 0 or observed > received:
            raise MonitoringError(MonitoringFailure.MALFORMED_PROVIDER_DATA)
        gap = instrument in self.__gap_instruments
        if (
            gap
            and self.__last_disconnect is not None
            and self.__last_disconnect.first_post_reconnect_observation_at is None
        ):
            self.__last_disconnect = replace(
                self.__last_disconnect,
                first_post_reconnect_observation_at=observed,
            )
        return ProviderMarketTick(
            instrument,
            price,
            observed,
            received,
            _KITE_SOURCE,
            self.__connection_id,
            None,
            not gap,
            not gap,
            not gap,
        )

    def __normalize_order_update(self, raw: object) -> ProviderOrderUpdateEvidence:
        if not isinstance(raw, Mapping):
            raise MonitoringError(MonitoringFailure.MALFORMED_PROVIDER_DATA)
        exchange = raw.get("exchange")
        symbol = raw.get("tradingsymbol")
        matches = tuple(
            item
            for item in self.__record_to_token
            if item.exchange == exchange and item.trading_symbol == symbol
        )
        if len(matches) != 1:
            raise MonitoringError(MonitoringFailure.INSTRUMENT_BINDING_MISMATCH)
        timestamp = _kite_timestamp(raw.get("exchange_timestamp", raw.get("order_timestamp")))
        received = self.__clock()
        try:
            return ProviderOrderUpdateEvidence(
                str(raw.get("order_id", "")),
                matches[0],
                str(raw.get("status", "")),
                str(raw.get("transaction_type", "")),
                Decimal(str(raw.get("filled_quantity", ""))),
                None
                if raw.get("average_price") is None
                else Decimal(str(raw.get("average_price"))),
                timestamp,
                received,
                "KITE_CONNECT_ORDER_UPDATE",
            )
        except (ValueError, ArithmeticError):
            raise MonitoringError(MonitoringFailure.MALFORMED_PROVIDER_DATA) from None

    def __subscribe_tokens(self, tokens: tuple[int, ...]) -> None:
        subscribe = getattr(self.__socket, "subscribe", None)
        set_mode = getattr(self.__socket, "set_mode", None)
        mode_full = getattr(self.__socket, "MODE_FULL", "full")
        if not callable(subscribe) or not callable(set_mode):
            raise MonitoringError(MonitoringFailure.PROVIDER_FAILURE)
        try:
            subscribe(list(tokens))
            set_mode(mode_full, list(tokens))
        except Exception:
            raise MonitoringError(MonitoringFailure.PROVIDER_FAILURE) from None

    def __set_state(self, state: MonitoringConnectionState) -> None:
        self.__state = state
        self.__consumer.on_connection_state(state)

    def __repr__(self) -> str:
        return "<KiteReadOnlyMonitoringSession redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("KITE_MONITORING_SESSION_SERIALIZATION_PROHIBITED")


def _create_socket(api_key: str, access_token: str) -> object:
    return _KiteTicker(
        api_key,
        access_token,
        debug=False,
        reconnect=True,
    )


def _kite_timestamp(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise MonitoringError(MonitoringFailure.MALFORMED_PROVIDER_DATA)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=_KITE_TIMEZONE)
    return value.astimezone(_KITE_TIMEZONE)


def _instrument_key(item: InstrumentRecord) -> tuple[str, str, str]:
    return item.exchange, item.trading_symbol, item.instrument_type


__all__ = ["KiteReadOnlyMonitoringSession"]
