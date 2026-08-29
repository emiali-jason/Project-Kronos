from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from kronos.configuration.principals import PrincipalBindingResult
from kronos.instrument.active_derivative import ACTIVE_DERIVATIVE_FAMILY_MAPPINGS
from kronos.instrument.semantic_v2 import DerivativeContractV2
from kronos.instrument.semantic_v2_persistence import (
    DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT,
    InstrumentSemanticV2Store,
)
from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.mcx_historical_research import (
    MCX_HISTORICAL_RESEARCH_AUTHORITY,
    McxHistoricalResearchError,
    McxHistoricalResearchFailure,
    McxHistoricalResearchState,
    acquire_mcx_historical_research_corpus,
    mcx_historical_research_corpus_bytes,
    parse_mcx_historical_research_corpus,
    resolve_historical_derivative_binding,
)
from kronos.intraday.mcx_historical_research_persistence import (
    McxHistoricalResearchCorpusStore,
)
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.instrument_master import (
    KITE_INSTRUMENT_MASTER_DATASET,
    KITE_INSTRUMENT_MASTER_OPERATION,
    ProviderInstrumentMasterSourceRecord,
)
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalInterval,
)
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.instrument_master import (
    ProviderAcquisitionOutcome,
    create_provider_instrument_snapshot,
)
from kronos.provider.models.authentication import (
    AuthenticatedContextState,
    AuthenticationAttemptState,
    ProviderAvailabilityState,
)
from kronos.provider.runtime import SharedAuthenticatedProviderRuntime


IST = ZoneInfo("Asia/Kolkata")
CREATED = datetime(2026, 8, 29, 8, 0, tzinfo=IST)
CATALOGUE = InstrumentSemanticV2Store(DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT).load(
    publication_identity="KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2",
    publication_version="1.2.0",
)
FAMILY_BY_SUBJECT = {
    subject: family for _, subject, family in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS
}


def _source_rows() -> tuple[ProviderInstrumentMasterSourceRecord, ...]:
    rows = []
    token = 800_000
    for contract in CATALOGUE.semantic_objects:
        if type(contract) is not DerivativeContractV2:
            continue
        family = FAMILY_BY_SUBJECT.get(contract.parent_subject_id)
        if family is None:
            continue
        token += 1
        geometry = contract.geometry[0]
        rows.append(ProviderInstrumentMasterSourceRecord(
            provider="KITE",
            provider_instrument_token=token,
            exchange_token=token + 1_000_000,
            trading_symbol=contract.canonical_symbol,
            name=family,
            last_price=Decimal("0"),
            expiry=contract.expiry,
            strike=Decimal("0"),
            tick_size=geometry.tick_size,
            lot_size=geometry.lot_size,
            instrument_type="FUT",
            segment="MCX-FUT",
            exchange="MCX",
        ))
    return tuple(rows)


def _snapshot(acquired: datetime):  # type: ignore[no-untyped-def]
    return create_provider_instrument_snapshot(
        records=_source_rows(),
        provider="KITE",
        dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
        operation_identity=KITE_INSTRUMENT_MASTER_OPERATION,
        source_boundary=acquired,
        request_started_at=acquired,
        response_received_at=acquired,
        acquired_at=acquired,
        acquisition_effective_at=acquired,
        authenticated_context_identity="RESEARCH-SNAPSHOT-CONTEXT",
        authorized_operation_identity=KITE_INSTRUMENT_MASTER_OPERATION,
        component_identities=("MCX-HISTORICAL-RESEARCH-SNAPSHOT",),
        acquisition_outcome=ProviderAcquisitionOutcome.COMPLETE,
        provenance=("ADR-0017", "MCX-HISTORICAL-RESEARCH-TEST"),
    )


def _instrument_records(*, include_expired_natgas: bool = True):  # type: ignore[no-untyped-def]
    result = []
    for row in _source_rows():
        if (
            not include_expired_natgas
            and row.trading_symbol == "NATURALGAS26AUGFUT"
        ):
            continue
        result.append(InstrumentRecord(
            provider=row.provider,
            exchange=row.exchange,
            segment=row.segment,
            trading_symbol=row.trading_symbol,
            name=row.name,
            instrument_type=row.instrument_type,
            expiry=row.expiry,
            tick_size=row.tick_size,
            lot_size=row.lot_size,
        ))
    return tuple(result)


class _Capability:
    def __init__(self, *, include_expired_natgas: bool = True) -> None:
        self.active = True
        self.operations = frozenset({
            ReadOnlyProviderOperation.INSTRUMENTS,
            ReadOnlyProviderOperation.HISTORICAL_DATA,
        })
        self._records = _instrument_records(
            include_expired_natgas=include_expired_natgas
        )
        self.historical_calls = 0
        self.calendar = CurrentMarketCalendarScheduleSource(
            MarketCalendarPublisher(), observed_at=CREATED
        )

    def instrument_records(self, exchange: str):  # type: ignore[no-untyped-def]
        return tuple(item for item in self._records if item.exchange == exchange)

    def historical_candles(self, request):  # type: ignore[no-untyped-def]
        self.historical_calls += 1
        local_start = request.start.astimezone(IST).date()
        local_end = request.end.astimezone(IST).date()
        dates = tuple(
            date.fromordinal(ordinal)
            for ordinal in range(local_start.toordinal(), local_end.toordinal() + 1)
        )
        schedules = tuple(
            schedule
            for item in dates
            if (
                schedule := self.calendar.schedule_for("MCX", item)
            ) is not None
        )
        timeframe = {
            HistoricalInterval.DAY: IntradayTimeframe.DAILY,
            HistoricalInterval.SIXTY_MINUTE: IntradayTimeframe.ONE_HOUR,
            HistoricalInterval.FIFTEEN_MINUTE: IntradayTimeframe.FIFTEEN_MINUTES,
            HistoricalInterval.FIVE_MINUTE: IntradayTimeframe.FIVE_MINUTES,
        }[request.interval]
        boundaries = tuple(
            boundary
            for schedule in schedules
            for boundary in expected_candle_boundaries(schedule, timeframe)
            if request.start <= boundary.start <= request.end
        )
        return tuple(
            HistoricalCandle(
                timestamp=(
                    datetime.combine(boundary.trading_date, datetime.min.time(), IST)
                    if timeframe is IntradayTimeframe.DAILY
                    else boundary.start
                ),
                open=100.0,
                high=102.0,
                low=99.0,
                close=101.0,
                volume=100,
            )
            for boundary in boundaries
        )


class _Runtime:
    def __init__(self, capability: _Capability) -> None:
        self.capability = capability
        self.state = AuthenticatedContextState.ABSENT

    def begin_login(self):  # type: ignore[no-untyped-def]
        return object()

    def complete_callback(self, _attempt):  # type: ignore[no-untyped-def]
        self.state = AuthenticatedContextState.ACTIVE
        return SimpleNamespace(
            state=AuthenticationAttemptState.SUCCEEDED,
            binding_result=PrincipalBindingResult.MATCHED,
        )

    def session_status(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            context_state=self.state,
            provider_availability=ProviderAvailabilityState.NOT_VERIFIED,
        )

    def current_context(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            provider="KITE",
            context_id="MCX-RESEARCH-CONTEXT",
            valid_until=datetime(2026, 8, 30, tzinfo=UTC),
        )

    def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
        return self.capability

    def end_kronos_session(self) -> None:
        self.state = AuthenticatedContextState.ENDED
        self.capability.active = False


def _lease(*, include_expired_natgas: bool = True):  # type: ignore[no-untyped-def]
    capability = _Capability(include_expired_natgas=include_expired_natgas)
    runtime = _Runtime(capability)
    shared = SharedAuthenticatedProviderRuntime(
        lambda: runtime,
        provider_identity="KITE",
        clock=lambda: CREATED.astimezone(UTC),
        identity_factory=lambda: "MCX-RESEARCH-LEASE",
    )
    shared.complete_callback(shared.begin_login())
    return shared.acquire_lease(
        consumer_identity="INTRADAY_MCX_HISTORICAL_RESEARCH",
        operations=frozenset({
            ReadOnlyProviderOperation.INSTRUMENTS,
            ReadOnlyProviderOperation.HISTORICAL_DATA,
        }),
    ), capability


def _schedule(day: int):  # type: ignore[no-untyped-def]
    source = CurrentMarketCalendarScheduleSource(
        MarketCalendarPublisher(), observed_at=CREATED
    )
    result = source.schedule_for("MCX", date(2026, 8, day))
    assert result is not None
    return result


def test_historical_binding_uses_explicit_snapshot_and_preserves_natgas_roll() -> None:
    snapshot = _snapshot(datetime(2026, 8, 26, 17, 0, tzinfo=IST))
    august = resolve_historical_derivative_binding(
        analytical_subject="NATGAS",
        target_schedule=_schedule(26),
        provider_snapshot=snapshot,
        catalogue=CATALOGUE,
        calendar_publisher=MarketCalendarPublisher(),
    )
    september = resolve_historical_derivative_binding(
        analytical_subject="NATGAS",
        target_schedule=_schedule(27),
        provider_snapshot=snapshot,
        catalogue=CATALOGUE,
        calendar_publisher=MarketCalendarPublisher(),
    )

    assert august.provider_symbol == "NATURALGAS26AUGFUT"
    assert september.provider_symbol == "NATURALGAS26SEPFUT"
    assert august.canonical_contract_identity != september.canonical_contract_identity
    assert august.retrospective_reconstruction is True


def test_complete_research_corpus_is_immutable_reloadable_and_token_free(
    tmp_path: Path,
) -> None:
    lease, capability = _lease()
    target = date(2026, 8, 28)
    corpus = acquire_mcx_historical_research_corpus(
        lease=lease,
        requested_trading_dates=(target,),
        provider_snapshots={target: _snapshot(CREATED)},
        catalogue=CATALOGUE,
        calendar_publisher=MarketCalendarPublisher(),
        created_at=CREATED,
        limitations=("Research fixture; no production authority",),
    )

    assert all(item.state is McxHistoricalResearchState.COMPLETE for item in corpus.sessions)
    assert corpus.provider_instrument_request_count == 1
    assert corpus.provider_historical_request_count == 20
    assert capability.historical_calls == 20
    assert corpus.authority == MCX_HISTORICAL_RESEARCH_AUTHORITY
    assert corpus.benchmark_applicability == "NOT_APPLICABLE"
    assert all(item.counts_by_timeframe == {
        IntradayTimeframe.DAILY: 2,
        IntradayTimeframe.ONE_HOUR: 30,
        IntradayTimeframe.FIFTEEN_MINUTES: 58,
        IntradayTimeframe.FIVE_MINUTES: 174,
    } for item in corpus.sessions)

    encoded = mcx_historical_research_corpus_bytes(corpus)
    assert b"provider_instrument_token" not in encoded
    assert b"instrument_token" not in encoded
    assert parse_mcx_historical_research_corpus(encoded) == corpus
    store = McxHistoricalResearchCorpusStore(tmp_path.resolve())
    path = store.retain(corpus)
    before = capability.historical_calls
    assert store.load(corpus_identity=corpus.corpus_identity) == corpus
    assert capability.historical_calls == before
    assert path.read_bytes() == encoded


def test_expired_provider_record_unavailable_does_not_substitute_next_contract() -> None:
    lease, capability = _lease(include_expired_natgas=False)
    target = date(2026, 8, 24)
    corpus = acquire_mcx_historical_research_corpus(
        lease=lease,
        requested_trading_dates=(target,),
        provider_snapshots={target: _snapshot(datetime(2026, 8, 26, 17, 0, tzinfo=IST))},
        catalogue=CATALOGUE,
        calendar_publisher=MarketCalendarPublisher(),
        created_at=CREATED,
        limitations=("Expired Provider token intentionally unavailable",),
    )
    natgas = next(item for item in corpus.sessions if item.analytical_subject == "NATGAS")

    assert natgas.state is McxHistoricalResearchState.REJECTED
    assert natgas.binding is not None
    assert natgas.binding.provider_symbol == "NATURALGAS26AUGFUT"
    assert natgas.reasons == (
        McxHistoricalResearchFailure.PROVIDER_INSTRUMENT_UNAVAILABLE,
    )
    assert natgas.provider_request_count == 0
    assert capability.historical_calls == 16


def test_tampered_corpus_fails_closed(tmp_path: Path) -> None:
    lease, _capability = _lease()
    target = date(2026, 8, 28)
    corpus = acquire_mcx_historical_research_corpus(
        lease=lease,
        requested_trading_dates=(target,),
        provider_snapshots={target: _snapshot(CREATED)},
        catalogue=CATALOGUE,
        calendar_publisher=MarketCalendarPublisher(),
        created_at=CREATED,
        limitations=("Tamper test",),
    )
    encoded = mcx_historical_research_corpus_bytes(corpus)
    with pytest.raises(McxHistoricalResearchError) as failure:
        parse_mcx_historical_research_corpus(
            encoded.replace(b'"volume":100', b'"volume":101', 1)
        )
    assert failure.value.failure is McxHistoricalResearchFailure.INTEGRITY_INVALID
