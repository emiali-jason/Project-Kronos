from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from kronos.configuration.credentials import OneUseSecretLease
from kronos.configuration.principals import PrincipalBindingResult
from kronos.provider.adapters.kite import client as client_module
from kronos.provider.adapters.kite.authentication import (
    create_kite_authentication_adapter,
)
from kronos.provider.contracts.instrument import (
    InstrumentKind,
    InstrumentRecord,
    InstrumentResolutionError,
    InstrumentResolutionFailure,
    InstrumentResolutionRequest,
)
from kronos.provider.contracts.market_data import (
    HistoricalCandleRequest,
    HistoricalDataError,
    HistoricalDataFailure,
    HistoricalInterval,
    LiveSnapshotError,
    LiveSnapshotFailure,
    LtpSnapshot,
    OhlcSnapshot,
    QuoteSnapshot,
)
from kronos.provider.kite.instruments.kite_instrument_provider import (
    KiteInstrumentProvider,
)
from kronos.provider.kite.marketdata.kite_market_data_provider import (
    KiteMarketDataProvider,
)


AS_OF = date(2026, 8, 9)
_API_KEY = "instrument-api-key"
_API_SECRET = "instrument-api-secret"
_REQUEST_TOKEN = "instrument-request-token"
_PRINCIPAL = "INSTRUMENT123"


class _FakeSession:
    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


class _FakeKiteClient:
    instances: list["_FakeKiteClient"] = []
    instrument_effects: list[object] = []

    def __init__(self, **_arguments: object) -> None:
        self.reqsession = _FakeSession()
        self.instruments_count = 0
        self.historical_arguments: list[dict[str, object]] = []
        self.historical_effects: list[object] = []
        self.instrument_exchanges: list[str] = []
        self.live_arguments: dict[str, list[tuple[str, ...]]] = {
            "quote": [],
            "ltp": [],
            "ohlc": [],
        }
        self.live_effects: dict[str, list[object]] = {
            "quote": [],
            "ltp": [],
            "ohlc": [],
        }
        self.invalidate_count = 0
        self.profile_count = 0
        self.session_expiry_hook: Callable[[], None] | None = None
        type(self).instances.append(self)

    def set_session_expiry_hook(self, hook: Callable[[], None]) -> None:
        self.session_expiry_hook = hook

    def generate_session(self, request_token: str, api_secret: str) -> object:
        assert request_token == _REQUEST_TOKEN
        assert api_secret == _API_SECRET
        return {"access_token": "private-access-token"}

    def profile(self) -> object:
        self.profile_count += 1
        return {"user_id": _PRINCIPAL}

    def instruments(self, exchange: str) -> object:
        self.instruments_count += 1
        self.instrument_exchanges.append(exchange)
        return type(self).instrument_effects.pop(0)

    def historical_data(self, **arguments: object) -> object:
        self.historical_arguments.append(arguments)
        effect = self.historical_effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect

    def quote(self, instruments: list[str]) -> object:
        return self._live_effect("quote", instruments)

    def ltp(self, instruments: list[str]) -> object:
        return self._live_effect("ltp", instruments)

    def ohlc(self, instruments: list[str]) -> object:
        return self._live_effect("ohlc", instruments)

    def _live_effect(self, operation: str, instruments: list[str]) -> object:
        self.live_arguments[operation].append(tuple(instruments))
        effect = self.live_effects[operation].pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect

    def invalidate_access_token(self) -> object:
        self.invalidate_count += 1
        raise AssertionError("remote invalidation is prohibited")

    def expire_session(self) -> None:
        assert self.session_expiry_hook is not None
        self.session_expiry_hook()


class _FakeRequestToken:
    def __init__(self) -> None:
        self._token: str | None = _REQUEST_TOKEN

    def consume_for_call(self, operation: Callable[[str], object]) -> object:
        assert self._token is not None
        token = self._token
        self._token = None
        return operation(token)

    def close(self) -> None:
        self._token = None


def _raw(
    *,
    token: int,
    exchange: str,
    segment: str,
    symbol: str,
    name: str,
    instrument_type: str,
    expiry: date | str | None = None,
) -> dict[str, object]:
    return {
        "instrument_token": token,
        "exchange": exchange,
        "segment": segment,
        "tradingsymbol": symbol,
        "name": name,
        "instrument_type": instrument_type,
        "expiry": expiry,
        "last_price": 999999.0,
        "exchange_token": "provider-private",
    }


def _provider(
    monkeypatch: pytest.MonkeyPatch,
    records: list[object],
) -> tuple[KiteInstrumentProvider, _FakeKiteClient, object, object]:
    _FakeKiteClient.instances = []
    _FakeKiteClient.instrument_effects = [records]
    monkeypatch.setattr(client_module, "_KiteConnect", _FakeKiteClient)
    adapter = create_kite_authentication_adapter(_API_KEY)
    candidate = adapter.exchange_once(
        _FakeRequestToken(),
        OneUseSecretLease(_API_SECRET),
    )
    evidence = candidate.principal_evidence()
    assert evidence.compare_expected(_PRINCIPAL) is PrincipalBindingResult.MATCHED
    capability = candidate.issue_read_only_capability()
    return (
        KiteInstrumentProvider(capability),
        _FakeKiteClient.instances[0],
        candidate,
        capability,
    )


def _request(kind: InstrumentKind, symbol: str) -> InstrumentResolutionRequest:
    return InstrumentResolutionRequest(kind=kind, symbol=symbol, as_of=AS_OF)


def _historical_request(record: object) -> HistoricalCandleRequest:
    return HistoricalCandleRequest(
        instrument=record,  # type: ignore[arg-type]
        start=datetime(2026, 8, 7, 3, 45, tzinfo=UTC),
        end=datetime(2026, 8, 8, 3, 45, tzinfo=UTC),
        interval=HistoricalInterval.SIXTY_MINUTE,
    )


def _candles() -> list[dict[str, object]]:
    return [
        {
            "date": datetime(2026, 8, 7, 3, 45, tzinfo=UTC),
            "open": 100.0,
            "high": 104.0,
            "low": 99.5,
            "close": 103.0,
            "volume": 12500,
            "oi": 987654,
            "provider_extra": "discarded",
        },
        {
            "date": datetime(2026, 8, 7, 4, 45, tzinfo=UTC),
            "open": 103.0,
            "high": 105.0,
            "low": 102.0,
            "close": 104.5,
            "volume": 13750,
        },
    ]


def _live_payload(identity: str, token: int) -> dict[str, object]:
    return {
        identity: {
            "instrument_token": token,
            "timestamp": datetime(2026, 8, 10, 10, 0),
            "last_price": 102.5,
            "volume": 12500,
            "ohlc": {
                "open": 100.0,
                "high": 104.0,
                "low": 99.0,
                "close": 101.0,
            },
            "depth": {"provider": "discarded"},
        }
    }


def test_valid_master_is_normalized_without_provider_token_or_raw_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, client, _, capability = _provider(
        monkeypatch,
        [
            _raw(
                token=101,
                exchange="NSE",
                segment="NSE",
                symbol="RELIANCE",
                name="RELIANCE",
                instrument_type="EQ",
            )
        ],
    )

    records = provider.retrieve("NSE")

    assert len(records) == 1
    assert records[0].trading_symbol == "RELIANCE"
    assert not hasattr(records[0], "instrument_token")
    assert not hasattr(records[0], "exchange_token")
    assert client.instrument_exchanges == ["NSE"]
    assert capability.active is True
    for prohibited in (
        "client",
        "sdk_client",
        "access_token",
        "api_secret",
        "place_order",
        "modify_order",
        "cancel_order",
    ):
        assert not hasattr(capability, prohibited)


def test_legitimate_empty_kite_name_is_preserved_without_rejecting_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _, _, _ = _provider(
        monkeypatch,
        [
            _raw(
                token=100,
                exchange="NSE",
                segment="NSE",
                symbol="UNNAMED",
                name="",
                instrument_type="EQ",
            ),
            _raw(
                token=101,
                exchange="NSE",
                segment="NSE",
                symbol="RELIANCE",
                name="RELIANCE",
                instrument_type="EQ",
            ),
        ],
    )

    records = provider.retrieve("NSE")

    assert records[0].name == ""
    assert records[1].name == "RELIANCE"


def test_non_string_name_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _raw(
        token=100,
        exchange="MCX",
        segment="MCX-FUT",
        symbol="GOLD26AUGFUT",
        name="GOLD",
        instrument_type="FUT",
        expiry=date(2026, 8, 28),
    )
    record["name"] = None
    provider, _, _, _ = _provider(monkeypatch, [record])

    with pytest.raises(InstrumentResolutionError) as captured:
        provider.retrieve("MCX")

    assert captured.value.failure is InstrumentResolutionFailure.MALFORMED_PROVIDER_DATA


def test_optional_kite_name_outer_padding_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _raw(
        token=100,
        exchange="NSE",
        segment="NSE",
        symbol="RELIANCE",
        name=" RELIANCE ",
        instrument_type="EQ",
    )
    provider, _, _, _ = _provider(monkeypatch, [record])

    records = provider.retrieve("NSE")

    assert records[0].name == "RELIANCE"


@pytest.mark.parametrize(
    ("kind", "symbol", "exchange", "record", "expected_symbol"),
    [
        (
            InstrumentKind.NSE_EQUITY,
            "RELIANCE",
            "NSE",
            _raw(
                token=101,
                exchange="NSE",
                segment="NSE",
                symbol="RELIANCE",
                name="RELIANCE",
                instrument_type="EQ",
            ),
            "RELIANCE",
        ),
        (
            InstrumentKind.NSE_INDEX,
            "NIFTY",
            "NSE",
            _raw(
                token=102,
                exchange="NSE",
                segment="INDICES",
                symbol="NIFTY 50",
                name="NIFTY 50",
                instrument_type="EQ",
            ),
            "NIFTY 50",
        ),
        (
            InstrumentKind.NSE_INDEX,
            "BANK NIFTY",
            "NSE",
            _raw(
                token=112,
                exchange="NSE",
                segment="INDICES",
                symbol="NIFTY BANK",
                name="NIFTY BANK",
                instrument_type="EQ",
            ),
            "NIFTY BANK",
        ),
        (
            InstrumentKind.NSE_EQUITY,
            "BAJAJ_AUTO",
            "NSE",
            _raw(
                token=113,
                exchange="NSE",
                segment="NSE",
                symbol="BAJAJ-AUTO",
                name="BAJAJ AUTO LIMITED",
                instrument_type="EQ",
            ),
            "BAJAJ-AUTO",
        ),
        (
            InstrumentKind.MCX_FUTURE,
            "GOLD",
            "MCX",
            _raw(
                token=103,
                exchange="MCX",
                segment="MCX-FUT",
                symbol="GOLD26AUGFUT",
                name="",
                instrument_type="FUT",
                expiry=date(2026, 8, 28),
            ),
            "GOLD26AUGFUT",
        ),
        (
            InstrumentKind.CDS_FUTURE,
            "USDINR",
            "CDS",
            _raw(
                token=104,
                exchange="CDS",
                segment="CDS-FUT",
                symbol="USDINR26AUGFUT",
                name="",
                instrument_type="FUT",
                expiry=date(2026, 8, 26),
            ),
            "USDINR26AUGFUT",
        ),
    ],
)
def test_representative_resolution_is_exact(
    monkeypatch: pytest.MonkeyPatch,
    kind: InstrumentKind,
    symbol: str,
    exchange: str,
    record: dict[str, object],
    expected_symbol: str,
) -> None:
    provider, client, _, _ = _provider(monkeypatch, [record])

    resolved = provider.resolve(_request(kind, symbol))

    assert resolved.trading_symbol == expected_symbol
    assert client.instrument_exchanges == [exchange]


@pytest.mark.parametrize(
    ("kind", "symbol", "record"),
    [
        (
            InstrumentKind.NSE_EQUITY,
            "RELIANCE",
            _raw(
                token=105,
                exchange="NSE",
                segment="NSE",
                symbol="RELIANCE",
                name="RELIANCE INDUSTRIES LIMITED",
                instrument_type="EQ",
            ),
        ),
        (
            InstrumentKind.NSE_INDEX,
            "NIFTY",
            _raw(
                token=106,
                exchange="NSE",
                segment="INDICES",
                symbol="NIFTY 50",
                name="",
                instrument_type="EQ",
            ),
        ),
    ],
)
def test_non_authoritative_name_does_not_change_exact_nse_identity_resolution(
    monkeypatch: pytest.MonkeyPatch,
    kind: InstrumentKind,
    symbol: str,
    record: dict[str, object],
) -> None:
    provider, _, _, _ = _provider(monkeypatch, [record])

    resolved = provider.resolve(_request(kind, symbol))

    assert resolved.trading_symbol in {"RELIANCE", "NIFTY 50"}


def test_unknown_nse_alias_is_not_inferred() -> None:
    record = InstrumentRecord(
        provider="KITE",
        exchange="NSE",
        segment="NSE",
        trading_symbol="UNKNOWN-SYMBOL",
        name="UNKNOWN",
        instrument_type="EQ",
        expiry=None,
    )

    with pytest.raises(InstrumentResolutionError) as captured:
        KiteInstrumentProvider.resolve_from_records(  # type: ignore[misc]
            object(),
            (record,),
            _request(InstrumentKind.NSE_EQUITY, "UNKNOWN_SYMBOL"),
        )

    assert captured.value.failure is InstrumentResolutionFailure.NO_MATCH


def test_many_equities_resolve_from_one_retrieved_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, client, _, _ = _provider(
        monkeypatch,
        [
            _raw(
                token=107,
                exchange="NSE",
                segment="NSE",
                symbol="RELIANCE",
                name="RELIANCE INDUSTRIES LIMITED",
                instrument_type="EQ",
            ),
            _raw(
                token=108,
                exchange="NSE",
                segment="NSE",
                symbol="ADANIENT",
                name="ADANI ENTERPRISES LIMITED",
                instrument_type="EQ",
            ),
        ],
    )
    master = provider.retrieve("NSE")

    resolved = tuple(
        provider.resolve_from_records(
            master,
            _request(InstrumentKind.NSE_EQUITY, symbol),
        )
        for symbol in ("RELIANCE", "ADANIENT")
    )

    assert tuple(record.trading_symbol for record in resolved) == (
        "RELIANCE",
        "ADANIENT",
    )
    assert client.instruments_count == 1


def test_nearest_unexpired_future_is_selected_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, _, _, _ = _provider(
        monkeypatch,
        [
            _raw(
                token=201,
                exchange="MCX",
                segment="MCX-FUT",
                symbol="GOLD26SEPFUT",
                name="GOLD",
                instrument_type="FUT",
                expiry=date(2026, 9, 28),
            ),
            _raw(
                token=202,
                exchange="MCX",
                segment="MCX-FUT",
                symbol="GOLD26AUGFUT",
                name="GOLD",
                instrument_type="FUT",
                expiry=date(2026, 8, 28),
            ),
        ],
    )

    resolved = provider.resolve(_request(InstrumentKind.MCX_FUTURE, "GOLD"))

    assert resolved.trading_symbol == "GOLD26AUGFUT"


def test_absent_instrument_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _, _, _ = _provider(monkeypatch, [])

    with pytest.raises(InstrumentResolutionError) as captured:
        provider.resolve(_request(InstrumentKind.CDS_FUTURE, "USDINR"))

    assert captured.value.failure is InstrumentResolutionFailure.NO_MATCH


def test_duplicate_exact_instrument_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _raw(
        token=301,
        exchange="NSE",
        segment="NSE",
        symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
    )
    provider, _, _, _ = _provider(monkeypatch, [record, {**record, "instrument_token": 302}])

    with pytest.raises(InstrumentResolutionError) as captured:
        provider.resolve(_request(InstrumentKind.NSE_EQUITY, "RELIANCE"))

    assert captured.value.failure is InstrumentResolutionFailure.AMBIGUOUS_MATCH


@pytest.mark.parametrize(
    "records",
    [
        None,
        [None],
        [{"exchange": "NSE"}],
        [
            _raw(
                token=0,
                exchange="NSE",
                segment="NSE",
                symbol="RELIANCE",
                name="RELIANCE",
                instrument_type="EQ",
            )
        ],
        [
            _raw(
                token=401,
                exchange="OTHER",
                segment="NSE",
                symbol="RELIANCE",
                name="RELIANCE",
                instrument_type="EQ",
            )
        ],
    ],
)
def test_malformed_provider_data_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    records: object,
) -> None:
    provider, _, _, _ = _provider(monkeypatch, records)  # type: ignore[arg-type]

    with pytest.raises(InstrumentResolutionError) as captured:
        provider.retrieve("NSE")

    assert captured.value.failure is (
        InstrumentResolutionFailure.MALFORMED_PROVIDER_DATA
    )


def test_expired_capability_cannot_retrieve_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, client, _, capability = _provider(monkeypatch, [])
    client.expire_session()

    with pytest.raises(InstrumentResolutionError) as captured:
        provider.retrieve("NSE")

    assert captured.value.failure is InstrumentResolutionFailure.CAPABILITY_UNAVAILABLE
    assert capability.active is False
    assert client.instruments_count == 0


def test_cleaned_up_session_cannot_retrieve_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, client, candidate, capability = _provider(monkeypatch, [])
    candidate.dispose_local()

    with pytest.raises(InstrumentResolutionError) as captured:
        provider.retrieve("NSE")

    assert captured.value.failure is InstrumentResolutionFailure.CAPABILITY_UNAVAILABLE
    assert capability.active is False
    assert client.instruments_count == 0
    assert client.reqsession.close_count == 1


@pytest.mark.parametrize(
    ("kind", "symbol", "record", "expected_exchange", "expected_token"),
    [
        (
            InstrumentKind.NSE_EQUITY,
            "RELIANCE",
            _raw(
                token=501,
                exchange="NSE",
                segment="NSE",
                symbol="RELIANCE",
                name="RELIANCE",
                instrument_type="EQ",
            ),
            "NSE",
            501,
        ),
        (
            InstrumentKind.NSE_INDEX,
            "NIFTY",
            _raw(
                token=502,
                exchange="NSE",
                segment="INDICES",
                symbol="NIFTY 50",
                name="NIFTY 50",
                instrument_type="EQ",
            ),
            "NSE",
            502,
        ),
        (
            InstrumentKind.MCX_FUTURE,
            "GOLD",
            _raw(
                token=503,
                exchange="MCX",
                segment="MCX-FUT",
                symbol="GOLD26AUGFUT",
                name="GOLD",
                instrument_type="FUT",
                expiry=date(2026, 8, 28),
            ),
            "MCX",
            503,
        ),
        (
            InstrumentKind.CDS_FUTURE,
            "USDINR",
            _raw(
                token=504,
                exchange="CDS",
                segment="CDS-FUT",
                symbol="USDINR26AUGFUT",
                name="USDINR",
                instrument_type="FUT",
                expiry=date(2026, 8, 26),
            ),
            "CDS",
            504,
        ),
    ],
)
def test_representative_historical_path_returns_only_normalized_candles(
    monkeypatch: pytest.MonkeyPatch,
    kind: InstrumentKind,
    symbol: str,
    record: dict[str, object],
    expected_exchange: str,
    expected_token: int,
) -> None:
    instruments, client, _, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(kind, symbol))
    client.historical_effects = [_candles()]
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]
    request = _historical_request(resolved)

    candles = market_data.historical_candles(request)

    assert len(candles) == 2
    assert candles[0].timestamp == datetime(2026, 8, 7, 3, 45, tzinfo=UTC)
    assert candles[0].open == 100.0
    assert candles[0].high == 104.0
    assert candles[0].low == 99.5
    assert candles[0].close == 103.0
    assert candles[0].volume == 12500
    assert not hasattr(candles[0], "oi")
    assert not hasattr(candles[0], "instrument_token")
    assert client.instrument_exchanges == [expected_exchange]
    assert client.historical_arguments == [
        {
            "instrument_token": expected_token,
            "from_date": request.start.astimezone(ZoneInfo("Asia/Kolkata")),
            "to_date": request.end.astimezone(ZoneInfo("Asia/Kolkata")),
            "interval": "60minute",
            "continuous": False,
            "oi": False,
        }
    ]


def test_one_interval_leading_exchange_bucket_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _raw(
        token=505,
        exchange="MCX",
        segment="MCX-FUT",
        symbol="GOLD26AUGFUT",
        name="",
        instrument_type="FUT",
        expiry=date(2026, 8, 28),
    )
    instruments, client, _, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(InstrumentKind.MCX_FUTURE, "GOLD"))
    request = _historical_request(resolved)
    client.historical_effects = [
        [
            {
                "date": request.start - timedelta(minutes=30),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1,
            }
        ]
    ]
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]

    candles = market_data.historical_candles(request)

    assert candles[0].timestamp == request.start - timedelta(minutes=30)


def test_unresolved_instrument_cannot_reach_historical_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instruments, client, _, _ = _provider(monkeypatch, [])

    with pytest.raises(InstrumentResolutionError):
        instruments.resolve(_request(InstrumentKind.NSE_EQUITY, "RELIANCE"))

    assert client.historical_arguments == []


def test_ambiguous_instrument_cannot_reach_historical_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _raw(
        token=601,
        exchange="NSE",
        segment="NSE",
        symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
    )
    instruments, client, _, _ = _provider(
        monkeypatch,
        [record, {**record, "instrument_token": 602}],
    )

    with pytest.raises(InstrumentResolutionError):
        instruments.resolve(_request(InstrumentKind.NSE_EQUITY, "RELIANCE"))

    assert client.historical_arguments == []


@pytest.mark.parametrize(
    "response",
    [
        None,
        [None],
        [{"date": datetime(2026, 8, 7, tzinfo=UTC)}],
        [
            {
                "date": "2026-08-07T03:45:00Z",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1,
            }
        ],
        [
            {
                "date": datetime(2026, 8, 7, 3, 45, tzinfo=UTC),
                "open": 100.0,
                "high": 99.0,
                "low": 98.0,
                "close": 100.5,
                "volume": 1,
            }
        ],
    ],
)
def test_malformed_historical_payload_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    response: object,
) -> None:
    record = _raw(
        token=701,
        exchange="NSE",
        segment="NSE",
        symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
    )
    instruments, client, _, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(InstrumentKind.NSE_EQUITY, "RELIANCE"))
    client.historical_effects = [response]
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]

    with pytest.raises(HistoricalDataError) as captured:
        market_data.historical_candles(_historical_request(resolved))

    assert captured.value.failure is HistoricalDataFailure.MALFORMED_PROVIDER_DATA
    assert captured.value.__cause__ is None


def test_expired_capability_cannot_call_historical_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _raw(
        token=801,
        exchange="NSE",
        segment="NSE",
        symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
    )
    instruments, client, _, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(InstrumentKind.NSE_EQUITY, "RELIANCE"))
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]
    client.expire_session()

    with pytest.raises(HistoricalDataError) as captured:
        market_data.historical_candles(_historical_request(resolved))

    assert captured.value.failure is HistoricalDataFailure.CAPABILITY_UNAVAILABLE
    assert client.historical_arguments == []


def test_cleaned_session_cannot_call_historical_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _raw(
        token=901,
        exchange="NSE",
        segment="NSE",
        symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
    )
    instruments, client, candidate, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(InstrumentKind.NSE_EQUITY, "RELIANCE"))
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]
    candidate.dispose_local()

    with pytest.raises(HistoricalDataError) as captured:
        market_data.historical_candles(_historical_request(resolved))

    assert captured.value.failure is HistoricalDataFailure.CAPABILITY_UNAVAILABLE
    assert client.historical_arguments == []


def test_provider_exception_is_sanitized_without_raw_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _raw(
        token=1001,
        exchange="NSE",
        segment="NSE",
        symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
    )
    instruments, client, _, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(InstrumentKind.NSE_EQUITY, "RELIANCE"))
    client.historical_effects = [RuntimeError("raw-provider-sensitive-material")]
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]

    with pytest.raises(HistoricalDataError) as captured:
        market_data.historical_candles(_historical_request(resolved))

    assert captured.value.failure is HistoricalDataFailure.PROVIDER_FAILURE
    assert "raw-provider-sensitive-material" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


@pytest.mark.parametrize(
    ("kind", "symbol", "record", "quote_volume"),
    [
        (
            InstrumentKind.NSE_EQUITY,
            "RELIANCE",
            _raw(
                token=1101,
                exchange="NSE",
                segment="NSE",
                symbol="RELIANCE",
                name="RELIANCE",
                instrument_type="EQ",
            ),
            12500,
        ),
        (
            InstrumentKind.NSE_INDEX,
            "NIFTY",
            _raw(
                token=1102,
                exchange="NSE",
                segment="INDICES",
                symbol="NIFTY 50",
                name="NIFTY 50",
                instrument_type="EQ",
            ),
            None,
        ),
        (
            InstrumentKind.MCX_FUTURE,
            "GOLD",
            _raw(
                token=1103,
                exchange="MCX",
                segment="MCX-FUT",
                symbol="GOLD26AUGFUT",
                name="",
                instrument_type="FUT",
                expiry=date(2026, 8, 28),
            ),
            12500,
        ),
    ],
)
def test_live_snapshot_operations_return_only_provider_neutral_results(
    monkeypatch: pytest.MonkeyPatch,
    kind: InstrumentKind,
    symbol: str,
    record: dict[str, object],
    quote_volume: int | None,
) -> None:
    instruments, client, _, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(kind, symbol))
    identity = f"{resolved.exchange}:{resolved.trading_symbol}"
    token = record["instrument_token"]
    assert type(token) is int
    for operation in ("quote", "ltp", "ohlc"):
        client.live_effects[operation] = [_live_payload(identity, token)]
    client.live_effects["quote"][0][identity]["volume"] = quote_volume  # type: ignore[index]
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]

    quote = market_data.quote(resolved)
    ltp = market_data.ltp(resolved)
    ohlc = market_data.ohlc(resolved)

    assert type(quote) is QuoteSnapshot
    assert quote.instrument is resolved
    assert quote.timestamp == datetime(
        2026,
        8,
        10,
        10,
        0,
        tzinfo=ZoneInfo("Asia/Kolkata"),
    )
    assert quote.last_price == 102.5
    assert quote.volume == quote_volume
    assert quote.ohlc.close == 101.0
    assert type(ltp) is LtpSnapshot
    assert ltp.instrument is resolved
    assert ltp.last_price == 102.5
    assert type(ohlc) is OhlcSnapshot
    assert ohlc.instrument is resolved
    assert ohlc.last_price == 102.5
    assert ohlc.ohlc.high == 104.0
    assert client.live_arguments == {
        "quote": [(identity,)],
        "ltp": [(identity,)],
        "ohlc": [(identity,)],
    }
    for result in (quote, ltp, ohlc):
        assert not hasattr(result, "instrument_token")
        assert not hasattr(result, "raw_payload")
        assert not hasattr(result, "client")


@pytest.mark.parametrize("operation", ["quote", "ltp", "ohlc"])
def test_unresolved_instrument_cannot_reach_live_snapshot_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    _, client, _, capability = _provider(monkeypatch, [])
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]
    unresolved = InstrumentRecord(
        provider="KITE",
        exchange="NSE",
        segment="NSE",
        trading_symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
        expiry=None,
    )

    with pytest.raises(LiveSnapshotError) as captured:
        getattr(market_data, operation)(unresolved)

    assert captured.value.failure is LiveSnapshotFailure.INSTRUMENT_NOT_RESOLVED
    assert all(not calls for calls in client.live_arguments.values())


@pytest.mark.parametrize("operation", ["quote", "ltp", "ohlc"])
@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {"NSE:RELIANCE": None},
        {
            "NSE:RELIANCE": {
                "instrument_token": 999999,
                "last_price": 102.5,
            }
        },
    ],
)
def test_malformed_live_snapshot_response_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    response: object,
) -> None:
    record = _raw(
        token=1201,
        exchange="NSE",
        segment="NSE",
        symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
    )
    instruments, client, _, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(InstrumentKind.NSE_EQUITY, "RELIANCE"))
    client.live_effects[operation] = [response]
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]

    with pytest.raises(LiveSnapshotError) as captured:
        getattr(market_data, operation)(resolved)

    assert captured.value.failure is LiveSnapshotFailure.MALFORMED_PROVIDER_DATA
    assert captured.value.__cause__ is None


def test_quote_timestamp_outside_legitimate_kite_datetime_shape_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _raw(
        token=1251,
        exchange="NSE",
        segment="NSE",
        symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
    )
    instruments, client, _, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(InstrumentKind.NSE_EQUITY, "RELIANCE"))
    payload = _live_payload("NSE:RELIANCE", 1251)
    payload["NSE:RELIANCE"]["timestamp"] = "2026-08-10 10:00:00"  # type: ignore[index]
    client.live_effects["quote"] = [payload]
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]

    with pytest.raises(LiveSnapshotError) as captured:
        market_data.quote(resolved)

    assert captured.value.failure is LiveSnapshotFailure.MALFORMED_PROVIDER_DATA


def test_quote_missing_volume_outside_legitimate_index_shape_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _raw(
        token=1252,
        exchange="NSE",
        segment="NSE",
        symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
    )
    instruments, client, _, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(InstrumentKind.NSE_EQUITY, "RELIANCE"))
    payload = _live_payload("NSE:RELIANCE", 1252)
    payload["NSE:RELIANCE"]["volume"] = None  # type: ignore[index]
    client.live_effects["quote"] = [payload]
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]

    with pytest.raises(LiveSnapshotError) as captured:
        market_data.quote(resolved)

    assert captured.value.failure is LiveSnapshotFailure.MALFORMED_PROVIDER_DATA


@pytest.mark.parametrize("operation", ["quote", "ltp", "ohlc"])
def test_live_snapshot_provider_failure_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    record = _raw(
        token=1301,
        exchange="MCX",
        segment="MCX-FUT",
        symbol="GOLD26AUGFUT",
        name="",
        instrument_type="FUT",
        expiry=date(2026, 8, 28),
    )
    instruments, client, _, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(InstrumentKind.MCX_FUTURE, "GOLD"))
    client.live_effects[operation] = [
        RuntimeError("raw-provider-sensitive-material")
    ]
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]

    with pytest.raises(LiveSnapshotError) as captured:
        getattr(market_data, operation)(resolved)

    assert captured.value.failure is LiveSnapshotFailure.PROVIDER_FAILURE
    assert "raw-provider-sensitive-material" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


@pytest.mark.parametrize("operation", ["quote", "ltp", "ohlc"])
def test_expired_capability_cannot_call_live_snapshot_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    record = _raw(
        token=1401,
        exchange="NSE",
        segment="INDICES",
        symbol="NIFTY 50",
        name="NIFTY 50",
        instrument_type="EQ",
    )
    instruments, client, _, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(InstrumentKind.NSE_INDEX, "NIFTY"))
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]
    client.expire_session()

    with pytest.raises(LiveSnapshotError) as captured:
        getattr(market_data, operation)(resolved)

    assert captured.value.failure is LiveSnapshotFailure.CAPABILITY_UNAVAILABLE
    assert all(not calls for calls in client.live_arguments.values())


@pytest.mark.parametrize("operation", ["quote", "ltp", "ohlc"])
def test_cleaned_session_cannot_call_live_snapshot_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    record = _raw(
        token=1501,
        exchange="NSE",
        segment="NSE",
        symbol="RELIANCE",
        name="RELIANCE",
        instrument_type="EQ",
    )
    instruments, client, candidate, capability = _provider(monkeypatch, [record])
    resolved = instruments.resolve(_request(InstrumentKind.NSE_EQUITY, "RELIANCE"))
    market_data = KiteMarketDataProvider(capability)  # type: ignore[arg-type]
    candidate.dispose_local()

    with pytest.raises(LiveSnapshotError) as captured:
        getattr(market_data, operation)(resolved)

    assert captured.value.failure is LiveSnapshotFailure.CAPABILITY_UNAVAILABLE
    assert all(not calls for calls in client.live_arguments.values())
    assert client.reqsession.close_count == 1
