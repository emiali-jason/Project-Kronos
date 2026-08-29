"""Research-only MCX historical corpus acquisition.

This module deliberately sits outside production Discovery and Probables.  It
reconstructs an exact ADR-0017 derivative binding from an explicitly supplied
immutable Provider snapshot, then acquires completed candles through one
read-only DOMAIN-006 lease.  It never chooses a snapshot or contract by file
order and never publishes a product current pointer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from kronos.instrument.active_derivative import (
    ACTIVE_DERIVATIVE_FAMILY_MAPPINGS,
    ACTIVE_DERIVATIVE_SELECTION_RULE_IDENTITY,
    ACTIVE_DERIVATIVE_SELECTION_RULE_VERSION,
)
from kronos.instrument.semantic_v2 import (
    CanonicalClassification,
    DerivativeContractV2,
    InstrumentSemanticPublicationV2,
)
from kronos.intraday.candles import expected_candle_boundaries, provider_interval
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.market.calendar import (
    MarketCalendarPublisher,
    McxContractSessionUnavailable,
)
from kronos.market.schedule import MarketDaySchedule
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
)
from kronos.provider.instrument_master import (
    ProviderAcquisitionOutcome,
    ProviderInstrumentRecord,
    ProviderInstrumentSnapshot,
)
from kronos.provider.runtime import ReadOnlyProviderLease


MCX_HISTORICAL_RESEARCH_CORPUS_IDENTITY = (
    "KRONOS-INTRADAY-MCX-HISTORICAL-RESEARCH-CORPUS-V1"
)
MCX_HISTORICAL_RESEARCH_CORPUS_VERSION = "1.0.0"
MCX_HISTORICAL_RESEARCH_AUTHORITY = (
    "RESEARCH_ONLY_NO_PRODUCTION_TRADING_OR_PERFORMANCE_AUTHORITY"
)
MCX_HISTORICAL_RESEARCH_OPERATION_IDENTITY = (
    "KRONOS-INTRADAY-MCX-HISTORICAL-RESEARCH-ACQUISITION-V1"
)
MCX_HISTORICAL_RESEARCH_BINDING_IDENTITY = (
    "KRONOS-INTRADAY-MCX-HISTORICAL-DERIVATIVE-BINDING-V1"
)
MCX_HISTORICAL_RESEARCH_TIMEFRAMES = (
    IntradayTimeframe.DAILY,
    IntradayTimeframe.ONE_HOUR,
    IntradayTimeframe.FIFTEEN_MINUTES,
    IntradayTimeframe.FIVE_MINUTES,
)


class McxHistoricalResearchState(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"


class McxHistoricalResearchFailure(StrEnum):
    INPUT_INVALID = "MCX_HISTORICAL_RESEARCH_INPUT_INVALID"
    SNAPSHOT_UNAVAILABLE = "MCX_HISTORICAL_PROVIDER_SNAPSHOT_UNAVAILABLE"
    SNAPSHOT_NOT_GOVERNED = "MCX_HISTORICAL_PROVIDER_SNAPSHOT_NOT_GOVERNED"
    CONTRACT_UNAVAILABLE = "MCX_HISTORICAL_CONTRACT_BINDING_UNAVAILABLE"
    CONTRACT_AMBIGUOUS = "MCX_HISTORICAL_CONTRACT_BINDING_AMBIGUOUS"
    DOMAIN008_UNAVAILABLE = "MCX_HISTORICAL_DOMAIN008_SESSION_UNAVAILABLE"
    PROVIDER_INSTRUMENT_UNAVAILABLE = "MCX_HISTORICAL_PROVIDER_INSTRUMENT_UNAVAILABLE"
    PROVIDER_REQUEST_FAILED = "MCX_HISTORICAL_PROVIDER_REQUEST_FAILED"
    MISSING_CANDLE = "MCX_HISTORICAL_MISSING_CANDLE"
    DUPLICATE_CANDLE = "MCX_HISTORICAL_DUPLICATE_CANDLE"
    OUT_OF_ORDER = "MCX_HISTORICAL_OUT_OF_ORDER"
    UNEXPECTED_CANDLE = "MCX_HISTORICAL_UNEXPECTED_CANDLE"
    INTEGRITY_INVALID = "MCX_HISTORICAL_RESEARCH_INTEGRITY_INVALID"


class McxHistoricalResearchError(RuntimeError):
    def __init__(self, failure: McxHistoricalResearchFailure) -> None:
        if type(failure) is not McxHistoricalResearchFailure:
            raise ValueError("MCX_HISTORICAL_RESEARCH_ERROR_INVALID")
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class McxHistoricalDerivativeBinding:
    binding_identity: str
    analytical_subject: str
    canonical_subject_identity: str
    provider_contract_family: str
    canonical_contract_identity: str
    provider_symbol: str
    provider_record_identity: str
    provider_snapshot_identity: str
    provider_snapshot_integrity_identity: str
    provider_snapshot_acquired_at: datetime
    contract_expiry: date
    target_trading_date: date
    observation_boundary: datetime
    expiry_eligibility_boundary: datetime
    domain008_session_identity: str
    domain008_publication_identity: str
    domain008_publication_version: str
    domain008_publication_sha256: str
    selection_rule_identity: str
    selection_rule_version: str
    catalogue_identity: str
    catalogue_version: str
    catalogue_integrity_identity: str
    retrospective_reconstruction: bool
    integrity_identity: str
    schema_identity: str = MCX_HISTORICAL_RESEARCH_BINDING_IDENTITY
    schema_version: str = MCX_HISTORICAL_RESEARCH_CORPUS_VERSION

    def __post_init__(self) -> None:
        if (
            not self.binding_identity.startswith("INTRADAY-MCX-HISTORICAL-BINDING-")
            or self.schema_identity != MCX_HISTORICAL_RESEARCH_BINDING_IDENTITY
            or self.schema_version != MCX_HISTORICAL_RESEARCH_CORPUS_VERSION
            or not _texts((
                self.analytical_subject,
                self.canonical_subject_identity,
                self.provider_contract_family,
                self.canonical_contract_identity,
                self.provider_symbol,
                self.provider_record_identity,
                self.provider_snapshot_identity,
                self.provider_snapshot_integrity_identity,
                self.domain008_session_identity,
                self.domain008_publication_identity,
                self.domain008_publication_version,
                self.domain008_publication_sha256,
                self.selection_rule_identity,
                self.selection_rule_version,
                self.catalogue_identity,
                self.catalogue_version,
                self.catalogue_integrity_identity,
            ))
            or not _aware(self.provider_snapshot_acquired_at)
            or type(self.contract_expiry) is not date
            or type(self.target_trading_date) is not date
            or not _aware(self.observation_boundary)
            or not _aware(self.expiry_eligibility_boundary)
            or self.target_trading_date
            != self.observation_boundary.astimezone(
                self.observation_boundary.tzinfo
            ).date()
            or self.observation_boundary > self.expiry_eligibility_boundary
            or self.selection_rule_identity
            != ACTIVE_DERIVATIVE_SELECTION_RULE_IDENTITY
            or self.selection_rule_version
            != ACTIVE_DERIVATIVE_SELECTION_RULE_VERSION
            or self.retrospective_reconstruction is not True
        ):
            raise McxHistoricalResearchError(
                McxHistoricalResearchFailure.INTEGRITY_INVALID
            )
        _verify(self, "binding_identity", "INTRADAY-MCX-HISTORICAL-BINDING-")


@dataclass(frozen=True, slots=True)
class McxHistoricalResearchCandle:
    candle_identity: str
    canonical_subject_identity: str
    canonical_contract_identity: str
    historical_binding_identity: str
    provider_record_identity: str
    trading_date: date
    session_identity: str
    timeframe: IntradayTimeframe
    source_timestamp: datetime
    candle_start: datetime
    candle_end: datetime
    completion_boundary: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source_identity: str
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        prices = (self.open, self.high, self.low, self.close)
        if (
            not self.candle_identity.startswith("INTRADAY-MCX-HISTORICAL-CANDLE-")
            or not _texts((
                self.canonical_subject_identity,
                self.canonical_contract_identity,
                self.historical_binding_identity,
                self.provider_record_identity,
                self.session_identity,
                self.source_identity,
            ))
            or type(self.trading_date) is not date
            or type(self.timeframe) is not IntradayTimeframe
            or not all(_aware(item) for item in (
                self.source_timestamp,
                self.candle_start,
                self.candle_end,
                self.completion_boundary,
            ))
            or self.candle_start >= self.candle_end
            or self.candle_end != self.completion_boundary
            or any(type(item) is not Decimal or not item.is_finite() or item < 0 for item in prices)
            or self.high < max(self.open, self.low, self.close)
            or self.low > min(self.open, self.high, self.close)
            or type(self.volume) is not int
            or self.volume < 0
            or not _texts(self.provenance)
        ):
            raise McxHistoricalResearchError(
                McxHistoricalResearchFailure.INTEGRITY_INVALID
            )
        _verify(self, "candle_identity", "INTRADAY-MCX-HISTORICAL-CANDLE-")


@dataclass(frozen=True, slots=True)
class McxHistoricalResearchSession:
    session_identity: str
    analytical_subject: str
    canonical_subject_identity: str
    trading_date: date
    market_session_identity: str
    previous_market_session_identity: str
    observation_boundary: datetime
    binding: McxHistoricalDerivativeBinding | None
    candles: tuple[McxHistoricalResearchCandle, ...]
    state: McxHistoricalResearchState
    reasons: tuple[McxHistoricalResearchFailure, ...]
    provider_request_count: int
    automatic_retry_count: int
    integrity_identity: str

    def __post_init__(self) -> None:
        counts = self.counts_by_timeframe
        if (
            not self.session_identity.startswith("INTRADAY-MCX-HISTORICAL-SESSION-")
            or not _texts((
                self.analytical_subject,
                self.canonical_subject_identity,
                self.market_session_identity,
                self.previous_market_session_identity,
            ))
            or type(self.trading_date) is not date
            or not _aware(self.observation_boundary)
            or self.binding is not None
            and type(self.binding) is not McxHistoricalDerivativeBinding
            or any(type(item) is not McxHistoricalResearchCandle for item in self.candles)
            or any(item.canonical_subject_identity != self.canonical_subject_identity for item in self.candles)
            or any(type(item) is not McxHistoricalResearchFailure for item in self.reasons)
            or type(self.provider_request_count) is not int
            or self.provider_request_count < 0
            or self.automatic_retry_count != 0
            or self.state is McxHistoricalResearchState.COMPLETE
            and (
                self.binding is None
                or self.reasons
                or counts != {
                    IntradayTimeframe.DAILY: 2,
                    IntradayTimeframe.ONE_HOUR: 30,
                    IntradayTimeframe.FIFTEEN_MINUTES: 58,
                    IntradayTimeframe.FIVE_MINUTES: 174,
                }
            )
            or self.state is McxHistoricalResearchState.REJECTED and self.candles
        ):
            raise McxHistoricalResearchError(
                McxHistoricalResearchFailure.INTEGRITY_INVALID
            )
        _verify(self, "session_identity", "INTRADAY-MCX-HISTORICAL-SESSION-")

    @property
    def counts_by_timeframe(self) -> dict[IntradayTimeframe, int]:
        return {
            timeframe: sum(item.timeframe is timeframe for item in self.candles)
            for timeframe in MCX_HISTORICAL_RESEARCH_TIMEFRAMES
        }


@dataclass(frozen=True, slots=True)
class McxHistoricalResearchCorpus:
    corpus_identity: str
    created_at: datetime
    requested_trading_dates: tuple[date, ...]
    subjects: tuple[str, ...]
    sessions: tuple[McxHistoricalResearchSession, ...]
    provider_context_identity: str
    provider_snapshot_identities: tuple[str, ...]
    catalogue_identity: str
    catalogue_version: str
    domain008_calendar_identity: str
    domain008_calendar_version: str
    provider_instrument_request_count: int
    provider_historical_request_count: int
    provider_failure_count: int
    automatic_retry_count: int
    benchmark_applicability: str
    authority: str
    limitations: tuple[str, ...]
    integrity_identity: str
    contract_identity: str = MCX_HISTORICAL_RESEARCH_CORPUS_IDENTITY
    contract_version: str = MCX_HISTORICAL_RESEARCH_CORPUS_VERSION

    def __post_init__(self) -> None:
        expected_subjects = tuple(item[0] for item in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS)
        if (
            not self.corpus_identity.startswith("INTRADAY-MCX-HISTORICAL-CORPUS-")
            or self.contract_identity != MCX_HISTORICAL_RESEARCH_CORPUS_IDENTITY
            or self.contract_version != MCX_HISTORICAL_RESEARCH_CORPUS_VERSION
            or not _aware(self.created_at)
            or not self.requested_trading_dates
            or tuple(sorted(set(self.requested_trading_dates)))
            != self.requested_trading_dates
            or self.subjects != expected_subjects
            or len(self.sessions) != len(self.subjects) * len(self.requested_trading_dates)
            or any(type(item) is not McxHistoricalResearchSession for item in self.sessions)
            or not _texts((
                self.provider_context_identity,
                self.catalogue_identity,
                self.catalogue_version,
                self.domain008_calendar_identity,
                self.domain008_calendar_version,
            ))
            or not _texts(self.provider_snapshot_identities)
            or any(type(item) is not int or item < 0 for item in (
                self.provider_instrument_request_count,
                self.provider_historical_request_count,
                self.provider_failure_count,
                self.automatic_retry_count,
            ))
            or self.automatic_retry_count != 0
            or self.provider_historical_request_count
            != sum(item.provider_request_count for item in self.sessions)
            or self.benchmark_applicability != "NOT_APPLICABLE"
            or self.authority != MCX_HISTORICAL_RESEARCH_AUTHORITY
            or not _texts(self.limitations)
        ):
            raise McxHistoricalResearchError(
                McxHistoricalResearchFailure.INTEGRITY_INVALID
            )
        _verify(self, "corpus_identity", "INTRADAY-MCX-HISTORICAL-CORPUS-")


def resolve_historical_derivative_binding(
    *,
    analytical_subject: str,
    target_schedule: MarketDaySchedule,
    provider_snapshot: ProviderInstrumentSnapshot,
    catalogue: InstrumentSemanticPublicationV2,
    calendar_publisher: MarketCalendarPublisher,
) -> McxHistoricalDerivativeBinding:
    """Reconstruct one exact historical binding from an explicit snapshot."""

    mappings = tuple(
        item for item in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS
        if item[0] == analytical_subject
    )
    if (
        len(mappings) != 1
        or type(target_schedule) is not MarketDaySchedule
        or type(provider_snapshot) is not ProviderInstrumentSnapshot
        or type(catalogue) is not InstrumentSemanticPublicationV2
        or type(calendar_publisher) is not MarketCalendarPublisher
    ):
        raise McxHistoricalResearchError(McxHistoricalResearchFailure.INPUT_INVALID)
    if provider_snapshot.acquisition_outcome is not ProviderAcquisitionOutcome.COMPLETE:
        raise McxHistoricalResearchError(
            McxHistoricalResearchFailure.SNAPSHOT_NOT_GOVERNED
        )
    label, canonical_subject, family = mappings[0]
    boundary = target_schedule.windows[-1].closes_at
    if not catalogue.effective_from <= boundary <= catalogue.effective_through:
        raise McxHistoricalResearchError(
            McxHistoricalResearchFailure.CONTRACT_UNAVAILABLE
        )
    candidates: list[tuple[ProviderInstrumentRecord, DerivativeContractV2, object]] = []
    for record in provider_snapshot.records:
        if not (
            record.provider == "KITE"
            and record.exchange == "MCX"
            and record.segment == "MCX-FUT"
            and record.instrument_type == "FUT"
            and record.name == family
            and record.expiry is not None
            and record.expiry >= target_schedule.trading_date
        ):
            continue
        try:
            profile = calendar_publisher.mcx_contract_session_profile(
                contract_family=family,
                contract_expiry=record.expiry,
                trading_date=target_schedule.trading_date,
                observed_at=boundary,
            )
        except McxContractSessionUnavailable:
            continue
        if not profile.contract_eligible:
            continue
        contracts = tuple(
            item for item in catalogue.semantic_objects
            if type(item) is DerivativeContractV2
            and item.parent_subject_id == canonical_subject
            and item.canonical_symbol == record.trading_symbol
            and item.expiry == record.expiry
            and item.exchange == "MCX"
            and item.valid_from <= boundary <= item.valid_through
        )
        if len(contracts) != 1:
            continue
        contract = contracts[0]
        directives = tuple(
            item for item in catalogue.provider_directives
            if item.canonical_object_id == contract.canonical_id
            and item.provider == "KITE"
            and item.provider_symbol == record.trading_symbol
            and item.active_at(boundary)
        )
        mappings_v2 = tuple(
            item for item in catalogue.classification_mappings
            if len(directives) == 1
            and item.mapping_identity == directives[0].classification_mapping_identity
            and item.provider_key == ("KITE", "MCX", "MCX-FUT", "FUT")
            and item.canonical_classification is CanonicalClassification.MCX_FUTURE
            and item.active_at(boundary)
        )
        geometry = tuple(item for item in contract.geometry if item.active_at(boundary))
        if (
            len(directives) != 1
            or len(mappings_v2) != 1
            or len(geometry) != 1
            or geometry[0].tick_size != record.tick_size
            or geometry[0].lot_size != record.lot_size
        ):
            continue
        candidates.append((record, contract, profile))
    if not candidates:
        raise McxHistoricalResearchError(
            McxHistoricalResearchFailure.CONTRACT_UNAVAILABLE
        )
    minimum = min(item[0].expiry for item in candidates)
    selected = tuple(item for item in candidates if item[0].expiry == minimum)
    if len(selected) != 1:
        raise McxHistoricalResearchError(
            McxHistoricalResearchFailure.CONTRACT_AMBIGUOUS
        )
    record, contract, profile = selected[0]
    values = {
        "analytical_subject": label,
        "canonical_subject_identity": canonical_subject,
        "provider_contract_family": family,
        "canonical_contract_identity": contract.canonical_id,
        "provider_symbol": record.trading_symbol,
        "provider_record_identity": record.provider_record_identity,
        "provider_snapshot_identity": provider_snapshot.snapshot_identity,
        "provider_snapshot_integrity_identity": provider_snapshot.integrity_identity,
        "provider_snapshot_acquired_at": provider_snapshot.acquired_at,
        "contract_expiry": record.expiry,
        "target_trading_date": target_schedule.trading_date,
        "observation_boundary": boundary,
        "expiry_eligibility_boundary": profile.expiry_eligibility_boundary,
        "domain008_session_identity": profile.continuous_trading.session_identity,
        "domain008_publication_identity": profile.publication_identity,
        "domain008_publication_version": profile.publication_version,
        "domain008_publication_sha256": profile.publication_sha256,
        "selection_rule_identity": ACTIVE_DERIVATIVE_SELECTION_RULE_IDENTITY,
        "selection_rule_version": ACTIVE_DERIVATIVE_SELECTION_RULE_VERSION,
        "catalogue_identity": catalogue.publication_identity,
        "catalogue_version": catalogue.publication_version,
        "catalogue_integrity_identity": catalogue.integrity_identity,
        "retrospective_reconstruction": True,
        "schema_identity": MCX_HISTORICAL_RESEARCH_BINDING_IDENTITY,
        "schema_version": MCX_HISTORICAL_RESEARCH_CORPUS_VERSION,
    }
    return McxHistoricalDerivativeBinding(
        binding_identity=_identity("INTRADAY-MCX-HISTORICAL-BINDING-", values),
        integrity_identity=_identity("INTEGRITY-MCX-HISTORICAL-BINDING-", values),
        **values,
    )


def acquire_mcx_historical_research_corpus(
    *,
    lease: ReadOnlyProviderLease,
    requested_trading_dates: tuple[date, ...],
    provider_snapshots: Mapping[date, ProviderInstrumentSnapshot],
    catalogue: InstrumentSemanticPublicationV2,
    calendar_publisher: MarketCalendarPublisher,
    created_at: datetime,
    limitations: tuple[str, ...],
) -> McxHistoricalResearchCorpus:
    """Acquire a bounded five-family corpus without production side effects."""

    if (
        type(lease) is not ReadOnlyProviderLease
        or not lease.active
        or not requested_trading_dates
        or tuple(sorted(set(requested_trading_dates))) != requested_trading_dates
        or set(provider_snapshots) != set(requested_trading_dates)
        or type(catalogue) is not InstrumentSemanticPublicationV2
        or type(calendar_publisher) is not MarketCalendarPublisher
        or not _aware(created_at)
        or not _texts(limitations)
    ):
        raise McxHistoricalResearchError(McxHistoricalResearchFailure.INPUT_INVALID)
    calendar = CurrentMarketCalendarScheduleSource(
        calendar_publisher,
        observed_at=created_at,
    )
    try:
        provider_records = lease.instrument_records("MCX")
    except Exception as error:
        raise McxHistoricalResearchError(
            McxHistoricalResearchFailure.PROVIDER_REQUEST_FAILED
        ) from error
    sessions: list[McxHistoricalResearchSession] = []
    provider_failures = 0
    for analytical_subject, _canonical_subject, _family in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS:
        for trading_date in requested_trading_dates:
            target = calendar.schedule_for("MCX", trading_date)
            try:
                previous = calendar.previous_trading_schedule("MCX", trading_date)
            except ValueError:
                previous = None
            if target is None or previous is None:
                sessions.append(_rejected_session(
                    analytical_subject=analytical_subject,
                    trading_date=trading_date,
                    target=target,
                    previous=previous,
                    failure=McxHistoricalResearchFailure.DOMAIN008_UNAVAILABLE,
                ))
                continue
            try:
                binding = resolve_historical_derivative_binding(
                    analytical_subject=analytical_subject,
                    target_schedule=target,
                    provider_snapshot=provider_snapshots[trading_date],
                    catalogue=catalogue,
                    calendar_publisher=calendar_publisher,
                )
            except McxHistoricalResearchError as error:
                sessions.append(_rejected_session(
                    analytical_subject=analytical_subject,
                    trading_date=trading_date,
                    target=target,
                    previous=previous,
                    failure=error.failure,
                ))
                continue
            matches = tuple(
                item for item in provider_records
                if item.provider == "KITE"
                and item.exchange == "MCX"
                and item.segment == "MCX-FUT"
                and item.instrument_type == "FUT"
                and item.trading_symbol == binding.provider_symbol
                and item.expiry == binding.contract_expiry
            )
            if len(matches) != 1:
                sessions.append(_rejected_session(
                    analytical_subject=analytical_subject,
                    trading_date=trading_date,
                    target=target,
                    previous=previous,
                    failure=McxHistoricalResearchFailure.PROVIDER_INSTRUMENT_UNAVAILABLE,
                    binding=binding,
                ))
                continue
            acquired, request_count, reasons = _acquire_session_candles(
                lease=lease,
                instrument=matches[0],
                binding=binding,
                target=target,
                previous=previous,
            )
            provider_failures += sum(
                item is McxHistoricalResearchFailure.PROVIDER_REQUEST_FAILED
                for item in reasons
            )
            state = (
                McxHistoricalResearchState.COMPLETE
                if not reasons
                else McxHistoricalResearchState.PARTIAL
                if acquired
                else McxHistoricalResearchState.REJECTED
            )
            values = {
                "analytical_subject": analytical_subject,
                "canonical_subject_identity": binding.canonical_subject_identity,
                "trading_date": trading_date,
                "market_session_identity": target.session_id,
                "previous_market_session_identity": previous.session_id,
                "observation_boundary": target.windows[-1].closes_at,
                "binding": binding,
                "candles": acquired,
                "state": state,
                "reasons": reasons,
                "provider_request_count": request_count,
                "automatic_retry_count": 0,
            }
            sessions.append(McxHistoricalResearchSession(
                session_identity=_identity("INTRADAY-MCX-HISTORICAL-SESSION-", values),
                integrity_identity=_identity("INTEGRITY-MCX-HISTORICAL-SESSION-", values),
                **values,
            ))
    publication = calendar_publisher.publication("MCX")
    values = {
        "created_at": created_at,
        "requested_trading_dates": requested_trading_dates,
        "subjects": tuple(item[0] for item in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS),
        "sessions": tuple(sessions),
        "provider_context_identity": lease.authenticated_context_identity,
        "provider_snapshot_identities": tuple(
            provider_snapshots[item].snapshot_identity for item in requested_trading_dates
        ),
        "catalogue_identity": catalogue.publication_identity,
        "catalogue_version": catalogue.publication_version,
        "domain008_calendar_identity": publication.calendar_identity,
        "domain008_calendar_version": publication.calendar_version,
        "provider_instrument_request_count": 1,
        "provider_historical_request_count": sum(item.provider_request_count for item in sessions),
        "provider_failure_count": provider_failures,
        "automatic_retry_count": 0,
        "benchmark_applicability": "NOT_APPLICABLE",
        "authority": MCX_HISTORICAL_RESEARCH_AUTHORITY,
        "limitations": limitations,
        "contract_identity": MCX_HISTORICAL_RESEARCH_CORPUS_IDENTITY,
        "contract_version": MCX_HISTORICAL_RESEARCH_CORPUS_VERSION,
    }
    return McxHistoricalResearchCorpus(
        corpus_identity=_identity("INTRADAY-MCX-HISTORICAL-CORPUS-", values),
        integrity_identity=_identity("INTEGRITY-MCX-HISTORICAL-CORPUS-", values),
        **values,
    )


def mcx_historical_research_corpus_bytes(value: McxHistoricalResearchCorpus) -> bytes:
    if type(value) is not McxHistoricalResearchCorpus:
        raise McxHistoricalResearchError(McxHistoricalResearchFailure.INPUT_INVALID)
    return _encode(value) + b"\n"


def parse_mcx_historical_research_corpus(encoded: bytes) -> McxHistoricalResearchCorpus:
    try:
        raw = json.loads(encoded)
        value = _corpus_from_data(raw)
    except McxHistoricalResearchError:
        raise
    except Exception as error:
        raise McxHistoricalResearchError(
            McxHistoricalResearchFailure.INTEGRITY_INVALID
        ) from error
    if mcx_historical_research_corpus_bytes(value) != encoded:
        raise McxHistoricalResearchError(
            McxHistoricalResearchFailure.INTEGRITY_INVALID
        )
    return value


def _acquire_session_candles(
    *,
    lease: ReadOnlyProviderLease,
    instrument: InstrumentRecord,
    binding: McxHistoricalDerivativeBinding,
    target: MarketDaySchedule,
    previous: MarketDaySchedule,
) -> tuple[
    tuple[McxHistoricalResearchCandle, ...],
    int,
    tuple[McxHistoricalResearchFailure, ...],
]:
    retained: list[McxHistoricalResearchCandle] = []
    reasons: list[McxHistoricalResearchFailure] = []
    requests = 0
    for timeframe in MCX_HISTORICAL_RESEARCH_TIMEFRAMES:
        timeframe_reasons: list[McxHistoricalResearchFailure] = []
        schedules = (
            (previous, target)
            if timeframe in {IntradayTimeframe.DAILY, IntradayTimeframe.ONE_HOUR}
            else (target,)
        )
        expected = tuple(
            boundary
            for schedule in schedules
            for boundary in expected_candle_boundaries(schedule, timeframe)
        )
        requests += 1
        try:
            supplied = tuple(lease.historical_candles(HistoricalCandleRequest(
                instrument=instrument,
                start=schedules[0].windows[0].opens_at,
                end=target.windows[-1].closes_at,
                interval=provider_interval(timeframe),
            )))
        except Exception:
            reasons.append(McxHistoricalResearchFailure.PROVIDER_REQUEST_FAILED)
            continue
        starts = tuple(item.start for item in expected)
        matched: list[tuple[HistoricalCandle, object]] = []
        actual_keys: list[datetime] = []
        for candle in supplied:
            boundary = next((
                item for item in expected
                if candle.timestamp.astimezone(item.start.tzinfo).date() == item.trading_date
                if timeframe is IntradayTimeframe.DAILY
            ), None) if timeframe is IntradayTimeframe.DAILY else next((
                item for item in expected if candle.timestamp == item.start
            ), None)
            if boundary is None:
                timeframe_reasons.append(
                    McxHistoricalResearchFailure.UNEXPECTED_CANDLE
                )
                continue
            matched.append((candle, boundary))
            actual_keys.append(boundary.start)
        if any(current <= prior for prior, current in zip(actual_keys, actual_keys[1:])):
            timeframe_reasons.append(McxHistoricalResearchFailure.OUT_OF_ORDER)
        if len(actual_keys) != len(set(actual_keys)):
            timeframe_reasons.append(McxHistoricalResearchFailure.DUPLICATE_CANDLE)
        if tuple(actual_keys) != starts:
            timeframe_reasons.append(McxHistoricalResearchFailure.MISSING_CANDLE)
        if timeframe_reasons:
            reasons.extend(timeframe_reasons)
            continue
        for candle, boundary in matched:
            values = {
                "canonical_subject_identity": binding.canonical_subject_identity,
                "canonical_contract_identity": binding.canonical_contract_identity,
                "historical_binding_identity": binding.binding_identity,
                "provider_record_identity": binding.provider_record_identity,
                "trading_date": boundary.trading_date,
                "session_identity": boundary.session_id,
                "timeframe": timeframe,
                "source_timestamp": candle.timestamp,
                "candle_start": boundary.start,
                "candle_end": boundary.end,
                "completion_boundary": boundary.end,
                "open": Decimal(str(candle.open)),
                "high": Decimal(str(candle.high)),
                "low": Decimal(str(candle.low)),
                "close": Decimal(str(candle.close)),
                "volume": candle.volume,
                "source_identity": f"DOMAIN-006:KITE:HISTORICAL:{provider_interval(timeframe).value}",
                "provenance": (
                    MCX_HISTORICAL_RESEARCH_OPERATION_IDENTITY,
                    binding.provider_snapshot_identity,
                    binding.domain008_publication_identity,
                    "Provider token excluded from research corpus",
                ),
            }
            retained.append(McxHistoricalResearchCandle(
                candle_identity=_identity("INTRADAY-MCX-HISTORICAL-CANDLE-", values),
                integrity_identity=_identity("INTEGRITY-MCX-HISTORICAL-CANDLE-", values),
                **values,
            ))
    return tuple(retained), requests, tuple(dict.fromkeys(reasons))


def _rejected_session(
    *,
    analytical_subject: str,
    trading_date: date,
    target: MarketDaySchedule | None,
    previous: MarketDaySchedule | None,
    failure: McxHistoricalResearchFailure,
    binding: McxHistoricalDerivativeBinding | None = None,
) -> McxHistoricalResearchSession:
    canonical = next(
        item[1] for item in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS
        if item[0] == analytical_subject
    )
    values = {
        "analytical_subject": analytical_subject,
        "canonical_subject_identity": canonical,
        "trading_date": trading_date,
        "market_session_identity": "UNAVAILABLE" if target is None else target.session_id,
        "previous_market_session_identity": "UNAVAILABLE" if previous is None else previous.session_id,
        "observation_boundary": (
            datetime.combine(
                trading_date,
                datetime.min.time(),
                ZoneInfo("Asia/Kolkata"),
            )
            if target is None
            else target.windows[-1].closes_at
        ),
        "binding": binding,
        "candles": (),
        "state": McxHistoricalResearchState.REJECTED,
        "reasons": (failure,),
        "provider_request_count": 0,
        "automatic_retry_count": 0,
    }
    return McxHistoricalResearchSession(
        session_identity=_identity("INTRADAY-MCX-HISTORICAL-SESSION-", values),
        integrity_identity=_identity("INTEGRITY-MCX-HISTORICAL-SESSION-", values),
        **values,
    )


def _corpus_from_data(data: Mapping[str, object]) -> McxHistoricalResearchCorpus:
    values = dict(data)
    values["created_at"] = datetime.fromisoformat(str(values["created_at"]))
    values["requested_trading_dates"] = tuple(
        date.fromisoformat(str(item)) for item in values["requested_trading_dates"]
    )
    values["subjects"] = tuple(values["subjects"])
    values["sessions"] = tuple(_session_from_data(item) for item in values["sessions"])
    values["provider_snapshot_identities"] = tuple(values["provider_snapshot_identities"])
    values["limitations"] = tuple(values["limitations"])
    return McxHistoricalResearchCorpus(**values)


def _session_from_data(data: Mapping[str, object]) -> McxHistoricalResearchSession:
    values = dict(data)
    values["trading_date"] = date.fromisoformat(str(values["trading_date"]))
    values["observation_boundary"] = datetime.fromisoformat(str(values["observation_boundary"]))
    values["binding"] = None if values["binding"] is None else _binding_from_data(values["binding"])
    values["candles"] = tuple(_candle_from_data(item) for item in values["candles"])
    values["state"] = McxHistoricalResearchState(values["state"])
    values["reasons"] = tuple(McxHistoricalResearchFailure(item) for item in values["reasons"])
    return McxHistoricalResearchSession(**values)


def _binding_from_data(data: Mapping[str, object]) -> McxHistoricalDerivativeBinding:
    values = dict(data)
    values["provider_snapshot_acquired_at"] = datetime.fromisoformat(str(values["provider_snapshot_acquired_at"]))
    values["contract_expiry"] = date.fromisoformat(str(values["contract_expiry"]))
    values["target_trading_date"] = date.fromisoformat(str(values["target_trading_date"]))
    values["observation_boundary"] = datetime.fromisoformat(str(values["observation_boundary"]))
    values["expiry_eligibility_boundary"] = datetime.fromisoformat(str(values["expiry_eligibility_boundary"]))
    return McxHistoricalDerivativeBinding(**values)


def _candle_from_data(data: Mapping[str, object]) -> McxHistoricalResearchCandle:
    values = dict(data)
    values["trading_date"] = date.fromisoformat(str(values["trading_date"]))
    values["timeframe"] = IntradayTimeframe(values["timeframe"])
    for name in ("source_timestamp", "candle_start", "candle_end", "completion_boundary"):
        values[name] = datetime.fromisoformat(str(values[name]))
    for name in ("open", "high", "low", "close"):
        values[name] = Decimal(str(values[name]))
    values["provenance"] = tuple(values["provenance"])
    return McxHistoricalResearchCandle(**values)


def _verify(value: object, identity_name: str, identity_prefix: str) -> None:
    payload = asdict(value)
    payload.pop(identity_name)
    payload.pop("integrity_identity")
    if getattr(value, identity_name) != _identity(identity_prefix, payload):
        raise McxHistoricalResearchError(McxHistoricalResearchFailure.INTEGRITY_INVALID)
    integrity_prefix = "INTEGRITY-MCX-HISTORICAL-"
    suffix = identity_prefix.removeprefix("INTRADAY-MCX-HISTORICAL-")
    if value.integrity_identity != _identity(integrity_prefix + suffix, payload):
        raise McxHistoricalResearchError(McxHistoricalResearchFailure.INTEGRITY_INVALID)


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {name: _normalize(item) for name, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(
        type(item) is str and bool(item) and item == item.strip() for item in values
    )


__all__ = [
    "MCX_HISTORICAL_RESEARCH_AUTHORITY",
    "MCX_HISTORICAL_RESEARCH_BINDING_IDENTITY",
    "MCX_HISTORICAL_RESEARCH_CORPUS_IDENTITY",
    "MCX_HISTORICAL_RESEARCH_CORPUS_VERSION",
    "MCX_HISTORICAL_RESEARCH_OPERATION_IDENTITY",
    "MCX_HISTORICAL_RESEARCH_TIMEFRAMES",
    "McxHistoricalDerivativeBinding",
    "McxHistoricalResearchCandle",
    "McxHistoricalResearchCorpus",
    "McxHistoricalResearchError",
    "McxHistoricalResearchFailure",
    "McxHistoricalResearchSession",
    "McxHistoricalResearchState",
    "acquire_mcx_historical_research_corpus",
    "mcx_historical_research_corpus_bytes",
    "parse_mcx_historical_research_corpus",
    "resolve_historical_derivative_binding",
]
