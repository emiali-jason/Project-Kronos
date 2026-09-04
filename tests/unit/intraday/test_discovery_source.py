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
from kronos.intraday.probables_refresh import map_discovery_execution_to_probables
from kronos.intraday.mcx_history_persistence import McxContractHistoryStore
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
    observed_at: datetime = OBSERVED,
    active_mcx: bool = False,
    retain_mcx: bool = False,
    operation_identity: str | None = None,
    historical_error_target: str | None = None,
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
        if request.instrument.trading_symbol == historical_error_target:
            raise RuntimeError(
                "credential_material=SENSITIVE_VALUE /sensitive/provider-response.json"
            )
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
    resolutions = None
    if active_mcx:
        from tests.unit.instrument.test_active_derivative_selection import _resolve

        resolutions = _resolve(observed_at)
    session, boundary_identity = governed_market_session_identities(
        calendar_publisher=calendar,
        reconciliation=reconciliation,
        observed_at=observed_at,
        active_derivative_resolutions=resolutions,
    )
    source = ProviderDiscoveryFactualSource(
        lease=lease,
        calendar_publisher=calendar,
        universe_identity=universe.publication_identity,
        universe_version=universe.publication_version,
        reconciliation_identity=reconciliation.publication_identity,
        reconciliation_version=reconciliation.publication_version,
        reconciliation=reconciliation,
        active_derivative_resolutions=resolutions,
        produce_probables_v2_facts=retain_mcx,
        mcx_history_store=(
            McxContractHistoryStore(tmp_path.resolve()) if retain_mcx else None
        ),
    )
    service = IntradayNativeDiscoveryService(
        universe=universe,
        reconciliation=reconciliation,
        factual_source=source,
        store=NativeDiscoveryStore(tmp_path.resolve()),
        runtime_evaluable_member_ids=(
            ()
            if resolutions is None
            else tuple(
                item.universe_member_identity
                for item in reconciliation.members
                if item.exchange == "MCX"
            )
        ),
        additional_source_identities=(
            ()
            if resolutions is None
            else tuple(
                item.binding_identity for item in resolutions.successful_bindings
            )
        ),
    )
    execution = service.execute(DiscoveryRunBoundary(
        observation_boundary=observed_at,
        market_session_identity=session,
        market_session_boundary_identity=boundary_identity,
        operation_identity=operation_identity,
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


def test_active_bindings_drive_all_five_mcx_subjects_without_changing_identity(
    tmp_path: Path,
) -> None:
    observed = datetime(2026, 8, 26, 10, 17, tzinfo=IST)
    execution, source, record_requests, requests, _ = _composition(
        tmp_path,
        observed_at=observed,
        active_mcx=True,
    )

    assert execution.run.accounting.universe_members == 98
    assert execution.run.accounting.prerequisite_unavailable == 0
    assert execution.run.accounting.factual_failures == 0
    assert len(execution.bundles) == 98
    assert source.historical_request_count == len(requests) == 392
    assert record_requests == ["NSE"]
    mcx = tuple(
        item for item in requests if item.instrument.exchange == "MCX"
    )
    assert len(mcx) == 20
    assert {item.instrument.name for item in mcx} == {
        "GOLDM", "SILVERM", "COPPER", "NATURALGAS", "CRUDEOIL"
    }
    assert {
        item.canonical_identity
        for item in execution.run.results
        if item.canonical_identity.startswith("MCX-SUBJECT-")
    } == {
        "MCX-SUBJECT-GOLDM",
        "MCX-SUBJECT-SILVERM",
        "MCX-SUBJECT-COPPER",
        "MCX-SUBJECT-NATGAS",
        "MCX-SUBJECT-CRUDE",
    }
    assert all(
        item.completed_candle is not False
        for bundle in execution.bundles
        for item in bundle.evidence
    )


def test_v2_retention_reuses_the_same_acquired_mcx_candles_without_extra_reads(
    tmp_path: Path,
) -> None:
    observed = datetime(2026, 8, 26, 10, 17, tzinfo=IST)
    _, source, _, requests, _ = _composition(
        tmp_path,
        observed_at=observed,
        active_mcx=True,
        retain_mcx=True,
    )
    assert source.historical_request_count == len(requests) == 490
    assert len(tuple((tmp_path / "mcx-contract-history-v1").glob("*/*/*/*.json"))) > 0
    assert not any("token" in path.read_text().lower() for path in (
        tmp_path / "mcx-contract-history-v1"
    ).glob("*/*/*/*.json"))


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


def test_latest_completed_windows_create_typed_probables_semantics(
    tmp_path: Path,
) -> None:
    boundary = datetime(2026, 8, 24, 11, 17, tzinfo=IST)
    execution, _, _, requests, _ = _composition(
        tmp_path,
        observed_at=boundary,
    )

    assert len(execution.probables_facts) == 93
    assert len(requests) == 372
    assert all(item.observation_boundary == boundary for item in execution.probables_facts)
    assert all(
        fact.available_at <= boundary
        for item in execution.probables_facts
        for fact in item.semantic_evidence.facts
    )
    assert all(
        item.semantic_evidence.source_bundle_identity
        == item.discovery_bundle_identity
        for item in execution.probables_facts
    )
    reconciliation = IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version=RECONCILIATION_VERSION,
    )
    mapping = map_discovery_execution_to_probables(
        execution=execution,
        reconciliation=reconciliation,
    )
    assert len(mapping.member_evidence) == 93
    assert len(mapping.unavailable_members) == 5
    assert all(
        item.source_run_identity == execution.run.run_identity
        and item.observation_boundary == execution.run.observation_boundary
        for item in mapping.member_evidence
    )


def test_insufficient_completed_hourly_history_is_member_unavailable_not_future_fill(
    tmp_path: Path,
) -> None:
    execution, _, _, _, _ = _composition(tmp_path, observed_at=OBSERVED)

    assert len(execution.bundles) == 93
    assert execution.probables_facts == ()
