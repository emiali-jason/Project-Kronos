from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from kronos.intraday.discovery import FactualEvaluability
from kronos.intraday.discovery_persistence import NativeDiscoveryStore
from kronos.intraday.discovery_runtime import (
    DiscoveryRunBoundary,
    IntradayNativeDiscoveryService,
)
from kronos.intraday.discovery_source import (
    ProviderDiscoveryFactualSource,
    governed_market_session_identities,
)
from kronos.intraday.reconciliation import (
    Availability,
    RECONCILIATION_IDENTITY,
    RECONCILIATION_VERSION,
)
from kronos.intraday.reconciliation_persistence import IntradayReconciliationStore
from kronos.intraday.universe import load_intraday_universe_publication
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import HistoricalCandle, HistoricalInterval
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from tests.unit.provider.test_shared_provider_runtime import _authenticate, _shared


IST = ZoneInfo("Asia/Kolkata")
OBSERVED = datetime(2026, 8, 24, 10, 17, tzinfo=IST)


def _composition(
    tmp_path: Path,
    *,
    omit_target: str | None = None,
    include_partial: bool = True,
):  # type: ignore[no-untyped-def]
    universe = load_intraday_universe_publication()
    reconciliation = IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version=RECONCILIATION_VERSION,
    )
    records = tuple(
        InstrumentRecord(
            provider="KITE",
            exchange=member.exchange,
            segment=("INDICES" if member.sponsor_label in {"NIFTY", "BANKNIFTY"} else "NSE"),
            trading_symbol=member.provider_symbol,
            name=member.sponsor_label,
            instrument_type="EQ",
            expiry=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
        )
        for member in reconciliation.members
        if member.dimensions.machine_fact_consumability is Availability.AVAILABLE
        and member.provider_symbol is not None
    )
    shared, runtime, factory_calls = _shared()
    record_requests: list[str] = []
    historical_requests = []

    def instrument_records(exchange):  # type: ignore[no-untyped-def]
        record_requests.append(exchange)
        return tuple(item for item in records if item.exchange == exchange)

    def historical_candles(request):  # type: ignore[no-untyped-def]
        historical_requests.append(request)
        if request.interval is HistoricalInterval.DAY:
            return (_candle(request.start),)
        step = {
            HistoricalInterval.SIXTY_MINUTE: timedelta(hours=1),
            HistoricalInterval.FIFTEEN_MINUTE: timedelta(minutes=15),
            HistoricalInterval.FIVE_MINUTE: timedelta(minutes=5),
        }[request.interval]
        values = []
        cursor = request.start
        while cursor <= request.end:
            if (
                (include_partial or cursor + step <= request.end)
                and not (
                    request.instrument.trading_symbol == omit_target
                    and request.interval is HistoricalInterval.FIFTEEN_MINUTE
                    and cursor == request.start
                )
            ):
                values.append(_candle(cursor))
            cursor += step
        return tuple(values)

    runtime.capability.instrument_records = instrument_records  # type: ignore[method-assign]
    runtime.capability.historical_candles = historical_candles  # type: ignore[method-assign]
    _authenticate(shared)
    lease = shared.acquire_lease(
        consumer_identity="INTRADAY_NATIVE_DISCOVERY",
        operations=frozenset({
            ReadOnlyProviderOperation.INSTRUMENTS,
            ReadOnlyProviderOperation.HISTORICAL_DATA,
        }),
    )
    calendar = MarketCalendarPublisher()
    session, boundary_identity = governed_market_session_identities(
        calendar_publisher=calendar,
        reconciliation=reconciliation,
        observed_at=OBSERVED,
    )
    source = ProviderDiscoveryFactualSource(
        lease=lease,
        calendar_publisher=calendar,
        universe_identity=universe.publication_identity,
        universe_version=universe.publication_version,
        reconciliation_identity=reconciliation.publication_identity,
        reconciliation_version=reconciliation.publication_version,
        reconciliation=reconciliation,
    )
    service = IntradayNativeDiscoveryService(
        universe=universe,
        reconciliation=reconciliation,
        factual_source=source,
        store=NativeDiscoveryStore(tmp_path.resolve()),
    )
    execution = service.execute(DiscoveryRunBoundary(
        observation_boundary=OBSERVED,
        market_session_identity=session,
        market_session_boundary_identity=boundary_identity,
    ))
    lease.release()
    return execution, source, record_requests, historical_requests, factory_calls


def _candle(timestamp: datetime) -> HistoricalCandle:
    return HistoricalCandle(timestamp, 100.0, 102.0, 99.0, 101.0, 1000)


def test_generic_provider_source_runs_91_equities_and_two_indexes(tmp_path: Path) -> None:
    execution, source, record_requests, requests, factory_calls = _composition(tmp_path)

    assert execution.run.accounting.universe_members == 98
    assert execution.run.accounting.factually_evaluable == 93
    assert execution.run.accounting.prerequisite_unavailable == 5
    assert execution.run.accounting.factual_failures == 0
    assert len(execution.bundles) == 93
    assert source.historical_request_count == len(requests) == 372
    assert record_requests == ["NSE"]
    assert factory_calls == [1]
    symbols = {item.instrument.trading_symbol for item in requests}
    assert {"NIFTY 50", "NIFTY BANK", "RELIANCE"}.issubset(symbols)
    assert not {"GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"} & symbols
    assert {item.interval for item in requests} == {
        HistoricalInterval.DAY,
        HistoricalInterval.SIXTY_MINUTE,
        HistoricalInterval.FIFTEEN_MINUTE,
        HistoricalInterval.FIVE_MINUTE,
    }


def test_missing_completed_member_window_is_isolated(tmp_path: Path) -> None:
    execution, _, _, requests, _ = _composition(tmp_path, omit_target="RELIANCE")

    reliance = next(
        item for item in execution.run.results
        if item.canonical_identity == "RELIANCE"
    )
    assert reliance.evaluability is FactualEvaluability.FACTUAL_FAILURE
    assert execution.run.accounting.factual_failures == 1
    assert len(execution.run.results) == 98
    assert len(execution.bundles) == 92
    assert all(item.instrument.trading_symbol not in {
        "GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"
    } for item in requests)


def test_current_incomplete_candles_cannot_change_structural_bundle(tmp_path: Path) -> None:
    with_partial, _, _, _, _ = _composition(tmp_path / "with", include_partial=True)
    without_partial, _, _, _, _ = _composition(
        tmp_path / "without",
        include_partial=False,
    )

    assert tuple(item.bundle_identity for item in with_partial.bundles) == tuple(
        item.bundle_identity for item in without_partial.bundles
    )
