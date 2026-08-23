from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import inspect
from pathlib import Path
from threading import Event, Thread
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_historical_operation import (
    HISTORICAL_OPERATION_LEASE_CAPABILITIES,
    IntradayHistoricalQualificationHarness,
    IntradayHistoricalQualificationOperationService,
)
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.intraday import historical_operation, historical_source
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_operation import (
    COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY,
    COMPLETED_SESSION_EOD_BOUNDARY_VERSION,
    HISTORICAL_OPERATION_IDENTITY,
    HISTORICAL_OPERATION_REQUEST_IDENTITY,
    HISTORICAL_OPERATION_TIMEFRAMES,
    HISTORICAL_OPERATION_VERSION,
    REQUIRED_HISTORICAL_FACT_FAMILIES,
    HistoricalOperationError,
    HistoricalOperationFailure,
    HistoricalOperationSessionRequest,
    HistoricalOperationStage,
    HistoricalOperationState,
    create_historical_operation_request,
    create_historical_request_plan,
    resolve_historical_eod_sessions,
    resolve_historical_operational_subjects,
)
from kronos.intraday.historical_qualification import (
    HistoricalBindingAvailability,
    HistoricalFactFamily,
    HistoricalFactualFailureEvidence,
    HistoricalFailureClassification,
    HistoricalProviderFailureFamily,
    HistoricalQualificationError,
    HistoricalQualificationFailure,
    create_historical_research_subject_set,
)
from kronos.intraday.historical_qualification_persistence import (
    HistoricalQualificationStore,
)
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.intraday.reconciliation import RECONCILIATION_IDENTITY
from kronos.intraday.reconciliation_persistence import IntradayReconciliationStore
from kronos.intraday.universe import load_intraday_universe_publication
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalInterval,
)
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.models.authentication import AuthenticatedContextState
from tests.unit.provider.test_shared_provider_runtime import _authenticate, _shared


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 8, 23, 12, 0, tzinfo=IST)
TRADING_DATES = (
    date(2026, 8, 14),
    date(2026, 8, 17),
    date(2026, 8, 18),
    date(2026, 8, 19),
    date(2026, 8, 20),
    date(2026, 8, 21),
)


def _schedule(day: date) -> MarketDaySchedule:
    return MarketDaySchedule(
        exchange="NSE",
        trading_date=day,
        session_id=f"NSE:{day.isoformat()}",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(
            MarketWindow(
                datetime.combine(day, time(9, 15), IST),
                datetime.combine(day, time(15, 30), IST),
            ),
        ),
        source_identity="KRONOS-MARKET-CALENDAR-V1/WO-06HA-FIXTURE",
        source_version="1",
    )


class _Calendar:
    def __init__(self) -> None:
        self.schedules = {day: _schedule(day) for day in TRADING_DATES}
        self.calls: list[tuple[str, date]] = []

    def schedule_for(self, exchange: str, trading_date: date):  # type: ignore[no-untyped-def]
        self.calls.append(("schedule", trading_date))
        return self.schedules.get(trading_date) if exchange == "NSE" else None

    def previous_trading_schedule(self, exchange: str, before_date: date):  # type: ignore[no-untyped-def]
        self.calls.append(("previous", before_date))
        candidates = [day for day in self.schedules if day < before_date]
        if exchange != "NSE" or not candidates:
            return None
        return self.schedules[max(candidates)]

    def for_subject(
        self,
        *,
        canonical_identity: str,
        domain_008_subject_identity: str,
    ):
        assert canonical_identity
        assert domain_008_subject_identity
        return self


def _universe_and_reconciliation():  # type: ignore[no-untyped-def]
    universe = load_intraday_universe_publication()
    reconciliation = IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version="1.0.0",
    )
    return universe, reconciliation


def _subjects():  # type: ignore[no-untyped-def]
    universe, reconciliation = _universe_and_reconciliation()
    return resolve_historical_operational_subjects(
        subject_set=create_historical_research_subject_set(universe),
        reconciliation=reconciliation,
    )


def _records() -> tuple[InstrumentRecord, ...]:
    return tuple(
        InstrumentRecord(
            provider="KITE",
            exchange=item.exchange,
            segment="INDICES" if item.sponsor_label in {"NIFTY", "BANKNIFTY"} else "NSE",
            trading_symbol=item.provider_symbol or "",
            name=item.sponsor_label,
            instrument_type="EQ",
            expiry=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
        )
        for item in _subjects()
        if item.binding.availability is HistoricalBindingAvailability.AVAILABLE
    )


class _HistoricalCapability:
    def __init__(
        self,
        *,
        omit_interval: HistoricalInterval | None = None,
        late_interval: HistoricalInterval | None = None,
        raw_failure: bool = False,
        sequence_mutation: str | None = None,
        block: Event | None = None,
        proceed: Event | None = None,
    ) -> None:
        self.active = True
        self.operations = frozenset(ReadOnlyProviderOperation)
        self.instrument_calls = 0
        self.historical_calls = 0
        self.requests: list[HistoricalCandleRequest] = []
        self._records = _records()
        self._omit_interval = omit_interval
        self._late_interval = late_interval
        self._raw_failure = raw_failure
        self._sequence_mutation = sequence_mutation
        self._block = block
        self._proceed = proceed

    @property
    def calls(self) -> int:
        return self.instrument_calls + self.historical_calls

    def instrument_records(self, exchange: str):  # type: ignore[no-untyped-def]
        self.instrument_calls += 1
        assert exchange == "NSE"
        return self._records

    def historical_candles(self, request: HistoricalCandleRequest):
        self.historical_calls += 1
        self.requests.append(request)
        if self._block is not None and self.historical_calls == 1:
            self._block.set()
            assert self._proceed is not None
            assert self._proceed.wait(timeout=10)
        if self._raw_failure:
            raise RuntimeError(
                "access_token=SECRET request_token=TOKEN api_secret=HIDDEN "
                "Authorization: Bearer X instrument_token=738561 "
                "ohlcv=[100,101,99,100.5,999] traceback SDK failure prose"
            )
        candles = list(_candles(request))
        if request.interval is self._omit_interval:
            candles = candles[:-1]
        if request.interval is self._late_interval:
            candles.append(
                HistoricalCandle(
                    timestamp=request.end + timedelta(minutes=5),
                    open=100.0,
                    high=101.0,
                    low=100.0,
                    close=100.5,
                    volume=999,
                )
            )
        if (
            request.interval is HistoricalInterval.SIXTY_MINUTE
            and self._sequence_mutation is not None
        ):
            if self._sequence_mutation == "EXTRA":
                candles.insert(1, replace(
                    candles[0], timestamp=candles[0].timestamp + timedelta(minutes=1)
                ))
            elif self._sequence_mutation == "OFFSET":
                candles = [
                    replace(item, timestamp=item.timestamp + timedelta(minutes=1))
                    for item in candles
                ]
            elif self._sequence_mutation == "DUPLICATE":
                candles.insert(1, candles[0])
            elif self._sequence_mutation == "OUT_OF_ORDER":
                candles[0], candles[1] = candles[1], candles[0]
        return tuple(candles)


def _candles(request: HistoricalCandleRequest) -> tuple[HistoricalCandle, ...]:
    if request.interval is HistoricalInterval.DAY:
        starts = (
            request.start,
            datetime.combine(request.end.astimezone(IST).date(), time(9, 15), IST),
        )
    else:
        span = {
            HistoricalInterval.SIXTY_MINUTE: timedelta(hours=1),
            HistoricalInterval.FIFTEEN_MINUTE: timedelta(minutes=15),
            HistoricalInterval.FIVE_MINUTE: timedelta(minutes=5),
        }[request.interval]
        retained = []
        cursor = request.start
        while cursor < request.end:
            retained.append(cursor)
            cursor = min(cursor + span, request.end)
        starts = tuple(retained)
    return tuple(
        HistoricalCandle(
            timestamp=value,
            open=100.0,
            high=101.0,
            low=100.0,
            close=100.5,
            volume=999,
        )
        for value in starts
    )


def _request(
    *,
    dates: tuple[date, ...] = (date(2026, 8, 17),),
    maximum: int = 373,
    requested_at: datetime = NOW,
    timeframes: tuple[IntradayTimeframe, ...] = HISTORICAL_OPERATION_TIMEFRAMES,
    facts: tuple[HistoricalFactFamily, ...] = REQUIRED_HISTORICAL_FACT_FAMILIES,
    outcomes: tuple[str, ...] = (),
    boundary_identity: str = COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY,
    universe_integrity_identity: str | None = None,
):
    universe = load_intraday_universe_publication()
    return create_historical_operation_request(
        universe_identity=universe.publication_identity,
        universe_version=universe.publication_version,
        universe_integrity_identity=(
            universe.integrity_identity
            if universe_integrity_identity is None
            else universe_integrity_identity
        ),
        sessions=tuple(
            HistoricalOperationSessionRequest(day, f"NSE:{day.isoformat()}")
            for day in dates
        ),
        boundary_family_identity=boundary_identity,
        boundary_family_version=COMPLETED_SESSION_EOD_BOUNDARY_VERSION,
        timeframes=timeframes,
        maximum_provider_requests=maximum,
        requested_factual_families=facts,
        requested_outcome_families=outcomes,
        requested_at=requested_at,
        provenance=("WO-06HA-CONTROLLED-FIXTURE",),
    )


def _repository_request(
    *,
    dates: tuple[date, ...] = (date(2026, 8, 17),),
    maximum: int = 373,
    requested_at: datetime = NOW,
    timeframes: tuple[IntradayTimeframe, ...] = HISTORICAL_OPERATION_TIMEFRAMES,
):
    universe = load_intraday_universe_publication()
    return create_historical_operation_request(
        universe_identity=universe.publication_identity,
        universe_version=universe.publication_version,
        universe_integrity_identity=universe.integrity_identity,
        sessions=tuple(
            HistoricalOperationSessionRequest(
                day,
                (
                    "KRONOS-NSE-CAPITAL-MARKET-2022-2026:2026.1.2:"
                    f"{day.isoformat()}:REGULAR"
                ),
            )
            for day in dates
        ),
        boundary_family_identity=COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY,
        boundary_family_version=COMPLETED_SESSION_EOD_BOUNDARY_VERSION,
        timeframes=timeframes,
        maximum_provider_requests=maximum,
        requested_factual_families=REQUIRED_HISTORICAL_FACT_FAMILIES,
        requested_outcome_families=(),
        requested_at=requested_at,
        provenance=("WO-06HC-COMPOSED-CONTROLLED-FIXTURE",),
    )


def _service(tmp_path: Path, capability: _HistoricalCapability | None = None):  # type: ignore[no-untyped-def]
    shared, runtime, factory_calls = _shared()
    selected = capability or _HistoricalCapability()
    runtime.capability = selected
    universe, reconciliation = _universe_and_reconciliation()
    service = IntradayHistoricalQualificationOperationService(
        provider_runtime=shared,
        universe=universe,
        reconciliation=reconciliation,
        calendar=_Calendar(),
        store=HistoricalQualificationStore(tmp_path),
        clock=lambda: NOW,
    )
    return service, shared, runtime, selected, factory_calls


def test_operation_contracts_are_explicit_research_only_and_bounded() -> None:
    request = _request()
    assert HISTORICAL_OPERATION_IDENTITY.endswith("OPERATION-V0")
    assert HISTORICAL_OPERATION_VERSION == "0.1.0"
    assert HISTORICAL_OPERATION_REQUEST_IDENTITY.endswith("REQUEST-V0")
    assert COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY.endswith("RESEARCH-V0")
    assert request.request_identity.startswith("INTRADAY-HISTORICAL-REQUEST-")
    assert request.operation_identity.startswith(
        "INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-"
    )
    assert request.requested_outcome_families == ()
    assert request.maximum_provider_requests == 373
    assert request.timeframes == HISTORICAL_OPERATION_TIMEFRAMES
    assert "DISCOVERY-OPERATION-SERVICE" not in request.operation_identity


@pytest.mark.parametrize("alias", ["LATEST", "NEWEST", "CURRENT"])
def test_session_aliases_are_rejected(alias: str) -> None:
    with pytest.raises(HistoricalOperationError) as captured:
        HistoricalOperationSessionRequest(date(2026, 8, 17), alias)
    assert captured.value.failure is HistoricalOperationFailure.REQUEST_INVALID


def test_request_identity_covers_every_governed_input() -> None:
    baseline = _request()
    variants = (
        _request(dates=(date(2026, 8, 18),)),
        _request(universe_integrity_identity="CHANGED-SUBJECT-SET"),
        _request(boundary_identity="ANOTHER-GOVERNED-BOUNDARY-V0"),
        _request(timeframes=(IntradayTimeframe.DAILY,)),
        _request(maximum=374),
        _request(facts=(*REQUIRED_HISTORICAL_FACT_FAMILIES, HistoricalFactFamily.VOLUME_FACTS)),
    )
    identities = {baseline.operation_identity}
    for variant in variants:
        identities.add(variant.operation_identity)
    assert len(identities) == 7


def test_current_subject_resolution_is_derived_98_93_5_and_preserves_mcx() -> None:
    subjects = _subjects()
    available = tuple(
        item for item in subjects
        if item.binding.availability is HistoricalBindingAvailability.AVAILABLE
    )
    unavailable = tuple(
        item for item in subjects
        if item.binding.availability
        is HistoricalBindingAvailability.HISTORICAL_PREREQUISITE_UNAVAILABLE
    )
    assert len(subjects) == 98
    assert len(available) == 93
    assert len(unavailable) == 5
    assert {item.sponsor_label for item in unavailable} == {
        "GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"
    }
    assert all(item.provider_symbol is None for item in unavailable)
    source = inspect.getsource(historical_operation)
    assert "front month" not in source.lower()
    assert "nearest expiry" not in source.lower()
    assert "liquidity" not in source.lower()


def test_domain008_resolves_exact_session_previous_and_eod_boundary() -> None:
    calendar = _Calendar()
    sessions = resolve_historical_eod_sessions(
        calendar=calendar,
        requested=(HistoricalOperationSessionRequest(date(2026, 8, 17), "NSE:2026-08-17"),),
        exchange="NSE",
        provenance=("WO-06HA-FIXTURE",),
    )
    resolved = sessions[0]
    assert resolved.target_schedule.trading_date == date(2026, 8, 17)
    assert resolved.previous_schedule.trading_date == date(2026, 8, 14)
    assert resolved.selection.previous_session_identity == "NSE:2026-08-14"
    assert resolved.selection.observation_boundary == datetime(2026, 8, 17, 15, 30, tzinfo=IST)
    assert ("previous", date(2026, 8, 17)) in calendar.calls
    assert date(2026, 8, 16) not in {value for _, value in calendar.calls}


def test_request_plan_is_collection_derived_and_enforced_before_provider(tmp_path: Path) -> None:
    service, shared, _, capability, factory_calls = _service(tmp_path)
    _authenticate(shared)
    request = _request(maximum=372)
    result = service.execute(request)
    assert result.state is HistoricalOperationState.FAILED
    assert result.stage is HistoricalOperationStage.REQUEST_PLANNING
    assert result.failure is HistoricalOperationFailure.REQUEST_BOUND_EXCEEDED
    assert result.provider_request_count == 0
    assert capability.calls == 0
    assert len(factory_calls) == 1


def test_five_session_plan_is_1860_history_plus_one_instrument() -> None:
    subject_set = create_historical_research_subject_set(
        load_intraday_universe_publication()
    )
    _, reconciliation = _universe_and_reconciliation()
    subjects = resolve_historical_operational_subjects(
        subject_set=subject_set, reconciliation=reconciliation
    )
    dates = TRADING_DATES[1:]
    sessions = resolve_historical_eod_sessions(
        calendar=_Calendar(),
        requested=tuple(
            HistoricalOperationSessionRequest(day, f"NSE:{day.isoformat()}")
            for day in dates
        ),
        exchange="NSE",
        provenance=("WO-06HA-PLAN",),
    )
    plan = create_historical_request_plan(
        request=_request(dates=dates, maximum=1861),
        subjects=subjects,
        sessions=sessions,
    )
    assert (plan.subject_set_count, plan.eligible_subject_count, plan.unavailable_subject_count) == (98, 93, 5)
    assert (plan.session_count, plan.timeframe_count) == (5, 4)
    assert plan.subject_session_observations == 490
    assert plan.historical_request_count == 1860
    assert plan.instrument_record_request_count == 1
    assert plan.total_provider_request_count == 1861
    assert plan.sequential and not plan.automatic_retry


def test_repository_domain008_resolves_proposed_five_sessions_without_provider() -> None:
    source = CurrentMarketCalendarScheduleSource(
        MarketCalendarPublisher(), observed_at=NOW
    )
    dates = TRADING_DATES[1:]
    resolved = resolve_historical_eod_sessions(
        calendar=source,
        requested=tuple(
            HistoricalOperationSessionRequest(
                day,
                (
                    "KRONOS-NSE-CAPITAL-MARKET-2022-2026:2026.1.2:"
                    f"{day.isoformat()}:REGULAR"
                ),
            )
            for day in dates
        ),
        exchange="NSE",
        provenance=("WO-06HA-REPOSITORY-DOMAIN-008-PROPOSAL",),
    )
    assert tuple(item.target_schedule.trading_date for item in resolved) == dates
    assert tuple(item.previous_schedule.trading_date for item in resolved) == (
        date(2026, 8, 14),
        date(2026, 8, 17),
        date(2026, 8, 18),
        date(2026, 8, 19),
        date(2026, 8, 20),
    )
    assert all(
        item.selection.observation_boundary.hour == 15
        and item.selection.observation_boundary.minute == 30
        and item.target_schedule.source_identity == "KRONOS-MARKET-CALENDAR-V1"
        and item.target_schedule.source_version == "2026.1.2"
        for item in resolved
    )


def test_absent_and_expired_context_fail_without_authentication_or_provider(tmp_path: Path) -> None:
    service, shared, runtime, capability, factory_calls = _service(tmp_path)
    absent = service.execute(_request())
    assert absent.failure is HistoricalOperationFailure.CONTEXT_UNAVAILABLE
    assert capability.calls == 0 and factory_calls == [] and runtime.begin_count == 0

    _authenticate(shared)
    runtime.context_state = AuthenticatedContextState.EXPIRED
    expired_service, _, _, _, _ = _service(tmp_path / "expired", capability)
    expired_service._runtime = shared
    expired = expired_service.execute(_request(requested_at=NOW + timedelta(seconds=1)))
    assert expired.failure is HistoricalOperationFailure.CONTEXT_EXPIRED
    assert capability.calls == 0


def test_active_fixture_completes_all_nse_and_persists_explicit_artifacts(tmp_path: Path) -> None:
    service, shared, runtime, capability, factory_calls = _service(tmp_path)
    _authenticate(shared)
    result = service.execute(_request())
    assert result.state is HistoricalOperationState.COMPLETE
    assert result.stage is HistoricalOperationStage.COMPLETE
    assert (result.subject_set_count, result.historically_resolvable_count) == (98, 93)
    assert result.prerequisite_unavailable_count == 5
    assert result.successful_reconstructions == 93
    assert result.factual_failures == 0
    assert result.prerequisite_unavailable_observations == 5
    assert result.narrow_cpr_true_count + result.narrow_cpr_false_count == 93
    assert result.narrow_cpr_unavailable_count == 5
    assert result.provider_request_count == 373
    assert len(result.bundle_identities) == 93
    assert len(result.reconstruction_identities) == 1
    assert result.persistence_complete and result.reload_verified
    assert not result.corpus_binding_performed
    assert not result.production_state_mutated
    assert capability.instrument_calls == 1
    assert capability.historical_calls == 372
    assert len(factory_calls) == 1 and runtime.begin_count == 1
    assert HISTORICAL_OPERATION_LEASE_CAPABILITIES == frozenset(
        {ReadOnlyProviderOperation.INSTRUMENTS, ReadOnlyProviderOperation.HISTORICAL_DATA}
    )
    store = HistoricalQualificationStore(tmp_path)
    identity = result.reconstruction_identities[0]
    reloaded = store.load(
        artifact_type="HistoricalQualificationReconstruction",
        artifact_identity=identity,
    )
    assert reloaded.reconstruction_identity == identity
    assert len(reloaded.fact_bundle_identities) == 93
    bundle_identity = result.bundle_identities[0]
    bundle = store.load(
        artifact_type="HistoricalQualificationFactBundle",
        artifact_identity=bundle_identity,
    )
    assert bundle.bundle_identity == bundle_identity
    assert {item.timeframe for item in bundle.timeframe_facts} == set(HISTORICAL_OPERATION_TIMEFRAMES)
    assert bundle.previous_session_facts_identity.startswith(
        "INTRADAY-HISTORICAL-PREVIOUS-SESSION-"
    )


@pytest.mark.parametrize(
    "interval",
    [HistoricalInterval.DAY, HistoricalInterval.SIXTY_MINUTE, HistoricalInterval.FIFTEEN_MINUTE, HistoricalInterval.FIVE_MINUTE],
)
def test_each_mandatory_timeframe_fails_closed_when_incomplete(
    tmp_path: Path, interval: HistoricalInterval
) -> None:
    capability = _HistoricalCapability(omit_interval=interval)
    service, shared, _, _, _ = _service(tmp_path, capability)
    _authenticate(shared)
    result = service.execute(_request())
    assert result.state is HistoricalOperationState.COMPLETE
    assert result.successful_reconstructions == 0
    assert result.factual_failures == 93
    assert result.observation_failure_counts == (
        (HistoricalOperationFailure.MANDATORY_TIMEFRAME_UNAVAILABLE.value if interval is HistoricalInterval.DAY else HistoricalOperationFailure.INCOMPLETE_CANDLE_NOT_AUTHORIZED.value, 93),
    )
    assert capability.historical_calls <= 372


def test_later_candle_is_rejected_as_typed_no_look_ahead(tmp_path: Path) -> None:
    capability = _HistoricalCapability(late_interval=HistoricalInterval.FIVE_MINUTE)
    service, shared, _, _, _ = _service(tmp_path, capability)
    _authenticate(shared)
    result = service.execute(_request())
    assert result.successful_reconstructions == 0
    assert result.observation_failure_counts == (
        (HistoricalOperationFailure.QUALIFICATION_LOOK_AHEAD_REJECTED.value, 93),
    )


def test_provider_raw_failure_is_sanitized_and_never_retried(tmp_path: Path) -> None:
    capability = _HistoricalCapability(raw_failure=True)
    service, shared, _, _, _ = _service(tmp_path, capability)
    _authenticate(shared)
    result = service.execute(_request())
    projection = repr(result)
    assert result.state is HistoricalOperationState.COMPLETE
    assert result.factual_failures == 93
    assert result.observation_failure_counts == (
        (HistoricalOperationFailure.PROVIDER_ACQUISITION_FAILED.value, 93),
    )
    assert capability.instrument_calls == 1
    assert capability.historical_calls == 93
    assert len(result.failure_evidence_identities) == 93
    evidence = HistoricalQualificationStore(tmp_path).load(
        artifact_type="HistoricalFactualFailureEvidence",
        artifact_identity=result.failure_evidence_identities[0],
    )
    assert type(evidence) is HistoricalFactualFailureEvidence
    assert evidence.timeframe is IntradayTimeframe.DAILY
    assert evidence.provider_failure_family is (
        HistoricalProviderFailureFamily.PROVIDER_REQUEST_FAILED
    )
    assert evidence.classifications == (
        HistoricalFailureClassification.PROVIDER_ACQUISITION_FAILED,
    )
    for forbidden in (
        "SECRET", "TOKEN", "HIDDEN", "Bearer", "738561", "ohlcv", "SDK", "traceback", "100.5"
    ):
        assert forbidden not in projection
        assert forbidden not in repr(evidence)
    assert "PROVIDER_ACQUISITION_FAILED" in projection


@pytest.mark.parametrize(
    ("capability", "classification", "actual_count"),
    (
        (
            _HistoricalCapability(
                omit_interval=HistoricalInterval.SIXTY_MINUTE
            ),
            HistoricalFailureClassification.MISSING_EXPECTED_CANDLE,
            6,
        ),
        (
            _HistoricalCapability(sequence_mutation="EXTRA"),
            HistoricalFailureClassification.EXTRA_UNEXPECTED_CANDLE,
            8,
        ),
        (
            _HistoricalCapability(sequence_mutation="OFFSET"),
            HistoricalFailureClassification.TIMESTAMP_OFFSET,
            7,
        ),
        (
            _HistoricalCapability(sequence_mutation="DUPLICATE"),
            HistoricalFailureClassification.DUPLICATE_TIMESTAMP,
            8,
        ),
        (
            _HistoricalCapability(sequence_mutation="OUT_OF_ORDER"),
            HistoricalFailureClassification.OUT_OF_ORDER_TIMESTAMP,
            7,
        ),
        (
            _HistoricalCapability(
                late_interval=HistoricalInterval.SIXTY_MINUTE
            ),
            HistoricalFailureClassification.CANDLE_AFTER_OBSERVATION_BOUNDARY,
            8,
        ),
    ),
)
def test_strict_sequence_failures_retain_sanitized_classification(
    tmp_path: Path,
    capability: _HistoricalCapability,
    classification: HistoricalFailureClassification,
    actual_count: int,
) -> None:
    service, shared, _, _, _ = _service(tmp_path, capability)
    _authenticate(shared)

    result = service.execute(_request())

    assert result.successful_reconstructions == 0
    assert result.factual_failures == 93
    assert len(result.failure_evidence_identities) == 93
    evidence = HistoricalQualificationStore(tmp_path).load(
        artifact_type="HistoricalFactualFailureEvidence",
        artifact_identity=result.failure_evidence_identities[0],
    )
    assert evidence.canonical_identity.startswith("NSE-")
    assert evidence.target_session_identity == "NSE:2026-08-17"
    assert evidence.timeframe is IntradayTimeframe.ONE_HOUR
    assert evidence.expected_timestamp_count == 7
    assert evidence.actual_timestamp_count == actual_count
    assert classification in evidence.classifications
    assert evidence.mismatch_ordinal is not None
    assert evidence.observation_boundary == datetime(
        2026, 8, 17, 15, 30, tzinfo=IST
    )
    document = HistoricalQualificationStore(tmp_path).load_document(
        artifact_type="HistoricalFactualFailureEvidence",
        artifact_identity=evidence.evidence_identity,
    )
    sanitized = repr(document)
    for forbidden in (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "instrument_token",
        "exchange_token",
        "access_token",
        "request_token",
        "api_secret",
        "Authorization",
        "RuntimeError",
        "traceback",
    ):
        assert forbidden not in sanitized


def test_real_domain008_subject_schedules_drive_each_provider_request(
    tmp_path: Path,
) -> None:
    shared, runtime, _ = _shared()
    capability = _HistoricalCapability()
    runtime.capability = capability
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: NOW,
    )

    result = composition.historical_invocation.execute(
        _repository_request(dates=(date(2026, 8, 18),))
    )

    assert result.state is HistoricalOperationState.COMPLETE
    assert result.factual_failures == 0
    assert len(result.reconstruction_identities) == 2
    hourly = {
        item.instrument.trading_symbol: item
        for item in capability.requests
        if item.interval is HistoricalInterval.SIXTY_MINUTE
    }
    assert hourly["RELIANCE"].end == datetime(
        2026, 8, 18, 15, 15, tzinfo=IST
    )
    assert hourly["NIFTY 50"].end == datetime(
        2026, 8, 18, 15, 30, tzinfo=IST
    )
    assert hourly["NIFTY BANK"].end == datetime(
        2026, 8, 18, 15, 30, tzinfo=IST
    )
    assert len(_candles(hourly["RELIANCE"])) == 6
    assert len(_candles(hourly["NIFTY 50"])) == 7
    assert len(_candles(hourly["NIFTY BANK"])) == 7


def test_unavailable_subject_schedule_fails_closed_before_provider_request(
    tmp_path: Path,
) -> None:
    class _UnavailableSubjectCalendar(_Calendar):
        def for_subject(
            self,
            *,
            canonical_identity: str,
            domain_008_subject_identity: str,
        ):
            if domain_008_subject_identity == "RELIANCE":
                raise ValueError("SUBJECT_SCHEDULE_UNAVAILABLE")
            return self

    shared, runtime, _ = _shared()
    capability = _HistoricalCapability()
    runtime.capability = capability
    universe, reconciliation = _universe_and_reconciliation()
    service = IntradayHistoricalQualificationOperationService(
        provider_runtime=shared,
        universe=universe,
        reconciliation=reconciliation,
        calendar=_UnavailableSubjectCalendar(),
        store=HistoricalQualificationStore(tmp_path),
        clock=lambda: NOW,
    )
    _authenticate(shared)

    result = service.execute(_request())

    assert result.factual_failures == 1
    assert "RELIANCE" not in {
        item.instrument.trading_symbol for item in capability.requests
    }
    evidence = HistoricalQualificationStore(tmp_path).load(
        artifact_type="HistoricalFactualFailureEvidence",
        artifact_identity=result.failure_evidence_identities[0],
    )
    assert evidence.canonical_identity == "RELIANCE"
    assert evidence.classifications == (
        HistoricalFailureClassification.EXPECTED_BOUNDARY_UNAVAILABLE,
    )
    assert evidence.timeframe is None


def test_duplicate_completed_identity_returns_terminal_result_without_provider(tmp_path: Path) -> None:
    service, shared, _, capability, _ = _service(tmp_path)
    _authenticate(shared)
    request = _request()
    first = service.execute(request)
    calls = capability.calls
    second = service.execute(request)
    assert second is first
    assert capability.calls == calls


@pytest.mark.parametrize("same_identity", [True, False])
def test_concurrent_operation_conflicts_bounded(
    tmp_path: Path, same_identity: bool
) -> None:
    blocked, proceed = Event(), Event()
    capability = _HistoricalCapability(block=blocked, proceed=proceed)
    service, shared, _, _, _ = _service(tmp_path, capability)
    _authenticate(shared)
    first_request = _request()
    holder: list[object] = []
    thread = Thread(target=lambda: holder.append(service.execute(first_request)))
    thread.start()
    assert blocked.wait(timeout=10)
    other = first_request if same_identity else _request(requested_at=NOW + timedelta(seconds=1))
    conflict = service.execute(other)
    assert conflict.state is HistoricalOperationState.CONFLICT
    assert conflict.failure is HistoricalOperationFailure.OPERATION_CONFLICT
    proceed.set()
    thread.join(timeout=20)
    assert not thread.is_alive()
    assert holder and holder[0].state is HistoricalOperationState.COMPLETE


def test_new_service_restart_does_not_reacquire_or_resume(tmp_path: Path) -> None:
    service, shared, runtime, capability, factory_calls = _service(tmp_path)
    _authenticate(shared)
    first = service.execute(_request())
    assert first.state is HistoricalOperationState.COMPLETE
    calls = capability.calls
    new_service = IntradayHistoricalQualificationOperationService(
        provider_runtime=shared,
        universe=load_intraday_universe_publication(),
        reconciliation=_universe_and_reconciliation()[1],
        calendar=_Calendar(),
        store=HistoricalQualificationStore(tmp_path),
        clock=lambda: NOW,
    )
    assert new_service.last_result is None
    assert capability.calls == calls
    assert len(factory_calls) == 1 and runtime.begin_count == 1


def test_harness_accepts_only_typed_governed_request(tmp_path: Path) -> None:
    service, _, _, _, _ = _service(tmp_path)
    harness = IntradayHistoricalQualificationHarness(service)
    with pytest.raises(HistoricalOperationError) as captured:
        harness.execute({"symbol": "RELIANCE", "interval": "minute"})  # type: ignore[arg-type]
    assert captured.value.failure is HistoricalOperationFailure.REQUEST_INVALID


def test_normal_construction_has_zero_operation_provider_auth_and_binding(tmp_path: Path) -> None:
    service, _, runtime, capability, factory_calls = _service(tmp_path)
    assert service.last_result is None
    assert service.active_operation_identity is None
    assert capability.calls == 0
    assert runtime.begin_count == 0
    assert factory_calls == []


def test_mcx_never_reaches_provider_requests_and_no_selection_logic(tmp_path: Path) -> None:
    service, shared, _, capability, _ = _service(tmp_path)
    _authenticate(shared)
    result = service.execute(_request())
    requested_symbols = {item.instrument.trading_symbol for item in capability.requests}
    assert requested_symbols.isdisjoint({"GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"})
    assert result.session_accounting[0].prerequisite_unavailable_count == 5
    assert result.session_accounting[0].narrow_cpr_unavailable_count == 5


def test_no_competing_cpr_or_production_browser_provider_composition() -> None:
    source = inspect.getsource(historical_source)
    application = inspect.getsource(
        __import__(
            "kronos.application.intraday_historical_operation",
            fromlist=["IntradayHistoricalQualificationOperationService"],
        )
    )
    assert source.count("reconstruct_previous_session_facts(") == 1
    assert "0.10" not in source and "Chartink" not in source and "TradingView" not in source
    assert "PROBABLE" not in source.upper()
    assert "kronos.browser" not in application
    assert "kronos.swing" not in application
    assert "create_intraday_runtime" not in application
    assert "begin_login" not in application and "complete_callback" not in application
    assert "order" not in application.lower()


def test_existing_store_remains_explicit_identity_only_and_fail_closed(tmp_path: Path) -> None:
    store = HistoricalQualificationStore(tmp_path)
    assert not hasattr(store, "latest")
    with pytest.raises(HistoricalQualificationError) as missing:
        store.load(
            artifact_type="HistoricalQualificationReconstruction",
            artifact_identity="MISSING-EXPLICIT-IDENTITY",
        )
    assert missing.value.failure is HistoricalQualificationFailure.ARTIFACT_UNAVAILABLE


def test_runtime_composes_passive_typed_historical_invocation_on_shared_runtime(
    tmp_path: Path,
) -> None:
    shared, runtime, factory_calls = _shared()
    capability = _HistoricalCapability()
    runtime.capability = capability

    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: NOW,
    )

    assert type(composition.historical_operation) is (
        IntradayHistoricalQualificationOperationService
    )
    assert type(composition.historical_invocation) is (
        IntradayHistoricalQualificationHarness
    )
    assert composition.historical_operation._runtime is shared
    assert composition.historical_invocation._operation is (
        composition.historical_operation
    )
    assert composition.discovery_operation._runtime is shared
    assert composition.historical_operation.actual_context_state == "ABSENT"
    assert composition.historical_operation.last_result is None
    assert composition.historical_operation.active_operation_identity is None
    assert capability.calls == 0
    assert runtime.begin_count == 0
    assert factory_calls == []
    assert shared.active_lease_count == 0

    with pytest.raises(HistoricalOperationError) as captured:
        composition.historical_invocation.execute(  # type: ignore[arg-type]
            {"symbol": "RELIANCE", "timeframe": "5minute"}
        )
    assert captured.value.failure is HistoricalOperationFailure.REQUEST_INVALID
    assert capability.calls == 0

    ceiling = inspect.signature(create_historical_operation_request).parameters[
        "maximum_provider_requests"
    ]
    assert ceiling.default is inspect.Parameter.empty


def test_composed_context_absent_and_expired_fail_closed_without_provider(
    tmp_path: Path,
) -> None:
    shared, runtime, factory_calls = _shared()
    capability = _HistoricalCapability()
    runtime.capability = capability
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: NOW,
    )

    absent = composition.historical_invocation.execute(_repository_request())
    assert absent.state is HistoricalOperationState.FAILED
    assert absent.failure is HistoricalOperationFailure.CONTEXT_UNAVAILABLE
    assert absent.context_state == "ABSENT"
    assert capability.calls == 0 and factory_calls == []

    _authenticate(shared)
    runtime.context_state = AuthenticatedContextState.EXPIRED
    expired = composition.historical_invocation.execute(
        _repository_request(requested_at=NOW + timedelta(seconds=1))
    )
    assert expired.state is HistoricalOperationState.FAILED
    assert expired.failure is HistoricalOperationFailure.CONTEXT_EXPIRED
    assert expired.context_state == "EXPIRED"
    assert capability.calls == 0
    assert len(factory_calls) == 1 and runtime.begin_count == 1


def test_composed_fixture_completes_persists_reloads_and_is_idempotent(
    tmp_path: Path,
) -> None:
    shared, runtime, factory_calls = _shared()
    capability = _HistoricalCapability()
    runtime.capability = capability
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: NOW,
    )
    snapshot_before = composition.discovery_application.snapshot()
    invalid_timeframes = composition.historical_invocation.execute(
        _repository_request(
            timeframes=(IntradayTimeframe.DAILY,),
            requested_at=NOW - timedelta(seconds=1),
        )
    )
    assert invalid_timeframes.state is HistoricalOperationState.FAILED
    assert invalid_timeframes.stage is HistoricalOperationStage.REQUEST_VALIDATION
    assert invalid_timeframes.failure is HistoricalOperationFailure.REQUEST_INVALID
    assert capability.calls == 0
    request = _repository_request()

    result = composition.historical_invocation.execute(request)
    calls_after_first = capability.calls
    duplicate = composition.historical_invocation.execute(request)

    assert result is duplicate
    assert result.state is HistoricalOperationState.COMPLETE
    assert result.stage is HistoricalOperationStage.COMPLETE
    assert result.context_state == "ACTIVE"
    assert result.subject_set_count == 98
    assert result.historically_resolvable_count == 93
    assert result.prerequisite_unavailable_count == 5
    assert result.provider_request_count == 373
    assert result.persistence_complete and result.reload_verified
    assert not result.corpus_binding_performed
    assert not result.production_state_mutated
    assert capability.instrument_calls == 1
    assert capability.historical_calls == 372
    assert capability.calls == calls_after_first
    assert len(factory_calls) == 1 and runtime.begin_count == 1
    assert shared.active_lease_count == 0
    assert composition.discovery_application.snapshot() == snapshot_before

    store = HistoricalQualificationStore(tmp_path.resolve())
    reconstruction = store.load(
        artifact_type="HistoricalQualificationReconstruction",
        artifact_identity=result.reconstruction_identities[0],
    )
    assert reconstruction.reconstruction_identity == (
        result.reconstruction_identities[0]
    )
    bundle = store.load(
        artifact_type="HistoricalQualificationFactBundle",
        artifact_identity=result.bundle_identities[0],
    )
    assert bundle.bundle_identity == result.bundle_identities[0]
    projection = repr(result)
    for forbidden in (
        "access_token",
        "request_token",
        "instrument_token",
        "Authorization",
        "HistoricalCandle",
        "InstrumentRecord",
        "traceback",
    ):
        assert forbidden not in projection


def test_composed_five_session_plan_accepts_1861_without_provider_work(
    tmp_path: Path,
) -> None:
    shared, runtime, factory_calls = _shared()
    capability = _HistoricalCapability()
    runtime.capability = capability
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: NOW,
    )
    request = _repository_request(dates=TRADING_DATES[1:], maximum=1861)
    operation = composition.historical_operation

    operation._validate_request(request)
    subject_set = create_historical_research_subject_set(operation._universe)
    subjects = resolve_historical_operational_subjects(
        subject_set=subject_set,
        reconciliation=operation._reconciliation,
    )
    sessions = resolve_historical_eod_sessions(
        calendar=operation._calendar,
        requested=request.sessions,
        exchange="NSE",
        provenance=(request.operation_identity,),
    )
    plan = create_historical_request_plan(
        request=request,
        subjects=subjects,
        sessions=sessions,
    )

    unavailable = tuple(
        item
        for item in subjects
        if item.binding.availability
        is HistoricalBindingAvailability.HISTORICAL_PREREQUISITE_UNAVAILABLE
    )
    assert request.maximum_provider_requests == 1861
    assert tuple(item.request.trading_date for item in sessions) == (
        date(2026, 8, 17),
        date(2026, 8, 18),
        date(2026, 8, 19),
        date(2026, 8, 20),
        date(2026, 8, 21),
    )
    assert plan.subject_set_count == 98
    assert plan.eligible_subject_count == 93
    assert plan.unavailable_subject_count == 5
    assert plan.historical_request_count == 1860
    assert plan.instrument_record_request_count == 1
    assert plan.total_provider_request_count == 1861
    assert plan.sequential and not plan.automatic_retry
    assert {item.sponsor_label for item in unavailable} == {
        "GOLDM",
        "SILVERM",
        "COPPER",
        "NATGAS",
        "CRUDE",
    }
    assert all(item.provider_symbol is None for item in unavailable)
    assert capability.calls == 0
    assert runtime.begin_count == 0
    assert factory_calls == []
