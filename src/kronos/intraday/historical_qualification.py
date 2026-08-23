"""WO-06H historical qualification reconstruction research contracts.

Historical reconstruction uses today's governed Intraday membership only as a
research subject set.  It neither backdates that publication nor creates a
production Discovery run, candidate, Probable, Promotion, trade, Risk state,
execution eligibility, notification authority, or broker state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Iterable, Mapping, Protocol

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.qualification import (
    NARROW_CPR_FACT_IDENTITY,
    PART1_CONTRACT_VERSION,
    QUALIFICATION_CONTRACT_IDENTITY,
    NarrowCprFact,
    PreviousCompletedDailyCandle,
    QualificationError,
    QualificationFailure,
    create_narrow_cpr_fact,
    qualification_artifact_from_document,
)
from kronos.intraday.universe import (
    IntradayMarketFamily,
    IntradayUniversePublication,
)
from kronos.market.schedule import MarketDaySchedule, TradingDayStatus


HISTORICAL_RECONSTRUCTION_IDENTITY = (
    "KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-RECONSTRUCTION-V0"
)
HISTORICAL_FACT_BUNDLE_IDENTITY = (
    "KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-FACT-BUNDLE-V0"
)
HISTORICAL_SUBJECT_SET_IDENTITY = (
    "KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-SUBJECT-SET-V0"
)
HISTORICAL_CORPUS_ELIGIBILITY_IDENTITY = (
    "KRONOS-INTRADAY-HISTORICAL-CORPUS-ELIGIBILITY-V0"
)
HISTORICAL_OUTCOME_IDENTITY = (
    "KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-OUTCOME-V0"
)
HISTORICAL_FAILURE_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-HISTORICAL-FACTUAL-FAILURE-EVIDENCE-V0"
)
WO06H_CONTRACT_VERSION = "0.1.0"


class HistoricalQualificationFailure(StrEnum):
    INPUT_INVALID = "HISTORICAL_QUALIFICATION_INPUT_INVALID"
    INTEGRITY_INVALID = "HISTORICAL_QUALIFICATION_INTEGRITY_INVALID"
    EXPLICIT_SESSION_REQUIRED = "HISTORICAL_SESSION_EXPLICIT_IDENTITY_REQUIRED"
    CANONICAL_BINDING_UNAVAILABLE = "HISTORICAL_CANONICAL_BINDING_UNAVAILABLE"
    PREREQUISITE_UNAVAILABLE = "HISTORICAL_PREREQUISITE_UNAVAILABLE"
    INCOMPLETE_CANDLE = "INCOMPLETE_HISTORICAL_CANDLE_REJECTED"
    LOOK_AHEAD = "HISTORICAL_QUALIFICATION_LOOK_AHEAD_REJECTED"
    CORPUS_INELIGIBLE = "HISTORICAL_RECONSTRUCTION_CORPUS_INELIGIBLE"
    PERSISTENCE_CONFLICT = "HISTORICAL_RECONSTRUCTION_PERSISTENCE_CONFLICT"
    ARTIFACT_UNAVAILABLE = "HISTORICAL_RECONSTRUCTION_ARTIFACT_UNAVAILABLE"


class HistoricalQualificationError(RuntimeError):
    def __init__(self, failure: HistoricalQualificationFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class HistoricalEvidenceSource(StrEnum):
    PRODUCTION_POST_ACTIVATION_DISCOVERY_EVIDENCE = (
        "PRODUCTION_POST_ACTIVATION_DISCOVERY_EVIDENCE"
    )
    HISTORICAL_QUALIFICATION_RECONSTRUCTION = (
        "HISTORICAL_QUALIFICATION_RECONSTRUCTION"
    )
    SYNTHETIC_TEST_FIXTURE = "SYNTHETIC_TEST_FIXTURE"


class HistoricalResearchPurpose(StrEnum):
    QUALIFICATION_RESEARCH = "QUALIFICATION_RESEARCH"


class HistoricalBindingAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    HISTORICAL_CANONICAL_BINDING_UNAVAILABLE = (
        "HISTORICAL_CANONICAL_BINDING_UNAVAILABLE"
    )
    HISTORICAL_PREREQUISITE_UNAVAILABLE = "HISTORICAL_PREREQUISITE_UNAVAILABLE"


class HistoricalFactFamily(StrEnum):
    COMPLETED_OHLCV = "COMPLETED_OHLCV"
    PREVIOUS_SESSION_HLC_PDH_PDL = "PREVIOUS_SESSION_HLC_PDH_PDL"
    CLASSIC_PIVOTS_CPR = "CLASSIC_PIVOTS_CPR"
    NARROW_CPR = "NARROW_CPR"
    STRUCTURAL_FACTS = "STRUCTURAL_FACTS"
    VOLUME_FACTS = "VOLUME_FACTS"
    DISTANCE_PATH_FACTS = "DISTANCE_PATH_FACTS"


class HistoricalFailureClassification(StrEnum):
    MISSING_EXPECTED_CANDLE = "MISSING_EXPECTED_CANDLE"
    EXTRA_UNEXPECTED_CANDLE = "EXTRA_UNEXPECTED_CANDLE"
    TIMESTAMP_OFFSET = "TIMESTAMP_OFFSET"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    OUT_OF_ORDER_TIMESTAMP = "OUT_OF_ORDER_TIMESTAMP"
    CANDLE_AFTER_OBSERVATION_BOUNDARY = (
        "CANDLE_AFTER_OBSERVATION_BOUNDARY"
    )
    EXPECTED_BOUNDARY_UNAVAILABLE = "EXPECTED_BOUNDARY_UNAVAILABLE"
    PROVIDER_ACQUISITION_FAILED = "PROVIDER_ACQUISITION_FAILED"


class HistoricalProviderFailureFamily(StrEnum):
    PROVIDER_REQUEST_FAILED = "PROVIDER_REQUEST_FAILED"
    PROVIDER_RESPONSE_INVALID = "PROVIDER_RESPONSE_INVALID"
    INSTRUMENT_RECORD_UNAVAILABLE = "INSTRUMENT_RECORD_UNAVAILABLE"


class CorpusEligibilityState(StrEnum):
    ELIGIBLE_FOR_EXPLICIT_BINDING_REVIEW = "ELIGIBLE_FOR_EXPLICIT_BINDING_REVIEW"
    INELIGIBLE = "INELIGIBLE"


class HistoricalCalendarSource(Protocol):
    def schedule_for(self, exchange: str, trading_date: date) -> MarketDaySchedule | None:
        ...

    def previous_trading_schedule(
        self, exchange: str, before_date: date
    ) -> MarketDaySchedule | None:
        ...


@dataclass(frozen=True, slots=True)
class HistoricalFactualFailureEvidence:
    evidence_identity: str
    canonical_identity: str
    target_session_identity: str
    timeframe: IntradayTimeframe | None
    expected_timestamp_count: int
    actual_timestamp_count: int | None
    classifications: tuple[HistoricalFailureClassification, ...]
    mismatch_ordinal: int | None
    observation_boundary: datetime
    diagnosed_at: datetime
    source_identity: str
    provider_failure_family: HistoricalProviderFailureFamily | None
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = HISTORICAL_FAILURE_EVIDENCE_IDENTITY
    schema_version: str = WO06H_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.evidence_identity.startswith(
                "INTRADAY-HISTORICAL-FACTUAL-FAILURE-"
            )
            or not _texts(
                (
                    self.canonical_identity,
                    self.target_session_identity,
                    self.source_identity,
                )
            )
            or self.timeframe is not None
            and type(self.timeframe) is not IntradayTimeframe
            or type(self.expected_timestamp_count) is not int
            or self.expected_timestamp_count < 0
            or self.actual_timestamp_count is not None
            and (
                type(self.actual_timestamp_count) is not int
                or self.actual_timestamp_count < 0
            )
            or not self.classifications
            or any(
                type(item) is not HistoricalFailureClassification
                for item in self.classifications
            )
            or len(set(self.classifications)) != len(self.classifications)
            or self.mismatch_ordinal is not None
            and (
                type(self.mismatch_ordinal) is not int
                or self.mismatch_ordinal < 0
            )
            or not _aware(self.observation_boundary)
            or not _aware(self.diagnosed_at)
            or self.diagnosed_at < self.observation_boundary
            or self.provider_failure_family is not None
            and type(self.provider_failure_family)
            is not HistoricalProviderFailureFamily
            or not _texts(self.provenance)
            or self.schema_identity != HISTORICAL_FAILURE_EVIDENCE_IDENTITY
            or self.schema_version != WO06H_CONTRACT_VERSION
        ):
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.INPUT_INVALID
            )
        _verify(
            self,
            "INTRADAY-HISTORICAL-FACTUAL-FAILURE-",
            "INTEGRITY-HISTORICAL-FACTUAL-FAILURE-",
        )


def create_historical_failure_evidence(
    *,
    canonical_identity: str,
    target_session_identity: str,
    timeframe: IntradayTimeframe | None,
    expected_timestamp_count: int,
    actual_timestamp_count: int | None,
    classifications: tuple[HistoricalFailureClassification, ...],
    mismatch_ordinal: int | None,
    observation_boundary: datetime,
    diagnosed_at: datetime,
    source_identity: str,
    provider_failure_family: HistoricalProviderFailureFamily | None,
    provenance: tuple[str, ...],
) -> HistoricalFactualFailureEvidence:
    payload = {
        "canonical_identity": canonical_identity,
        "target_session_identity": target_session_identity,
        "timeframe": timeframe,
        "expected_timestamp_count": expected_timestamp_count,
        "actual_timestamp_count": actual_timestamp_count,
        "classifications": classifications,
        "mismatch_ordinal": mismatch_ordinal,
        "observation_boundary": observation_boundary,
        "diagnosed_at": diagnosed_at,
        "source_identity": source_identity,
        "provider_failure_family": provider_failure_family,
        "provenance": provenance,
        "schema_identity": HISTORICAL_FAILURE_EVIDENCE_IDENTITY,
        "schema_version": WO06H_CONTRACT_VERSION,
    }
    return HistoricalFactualFailureEvidence(
        evidence_identity=_identity(
            "INTRADAY-HISTORICAL-FACTUAL-FAILURE-", payload
        ),
        integrity_identity=_identity(
            "INTEGRITY-HISTORICAL-FACTUAL-FAILURE-", payload
        ),
        **payload,
    )

@dataclass(frozen=True, slots=True)
class HistoricalResearchSubject:
    universe_member_identity: str
    sponsor_label: str
    canonical_identity: str | None
    market_family: IntradayMarketFamily
    universe_member_source_identity: str

    def __post_init__(self) -> None:
        if (
            not _text(self.universe_member_identity)
            or not _text(self.sponsor_label)
            or self.canonical_identity is not None and not _text(self.canonical_identity)
            or type(self.market_family) is not IntradayMarketFamily
            or not _text(self.universe_member_source_identity)
        ):
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.INPUT_INVALID
            )


@dataclass(frozen=True, slots=True)
class HistoricalResearchSubjectSet:
    subject_set_identity: str
    current_universe_identity: str
    current_universe_version: str
    current_universe_integrity_identity: str
    current_universe_valid_from: datetime
    subjects: tuple[HistoricalResearchSubject, ...]
    current_membership_used_for_research: bool
    historical_operational_membership_claim: bool
    provider_presence_creates_membership: bool
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = HISTORICAL_SUBJECT_SET_IDENTITY
    schema_version: str = WO06H_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.subject_set_identity.startswith("INTRADAY-HISTORICAL-SUBJECT-SET-")
            or not _text(self.current_universe_identity)
            or not _text(self.current_universe_version)
            or not _text(self.current_universe_integrity_identity)
            or not _aware(self.current_universe_valid_from)
            or not self.subjects
            or any(type(item) is not HistoricalResearchSubject for item in self.subjects)
            or len({item.universe_member_identity for item in self.subjects})
            != len(self.subjects)
            or not self.current_membership_used_for_research
            or self.historical_operational_membership_claim
            or self.provider_presence_creates_membership
            or not _texts(self.provenance)
            or self.schema_identity != HISTORICAL_SUBJECT_SET_IDENTITY
            or self.schema_version != WO06H_CONTRACT_VERSION
        ):
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.INPUT_INVALID
            )
        _verify(
            self,
            "INTRADAY-HISTORICAL-SUBJECT-SET-",
            "INTEGRITY-HISTORICAL-SUBJECT-SET-",
        )

    def lookup(self, sponsor_label: str) -> HistoricalResearchSubject:
        matches = tuple(item for item in self.subjects if item.sponsor_label == sponsor_label)
        if len(matches) != 1:
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.CANONICAL_BINDING_UNAVAILABLE
            )
        return matches[0]


def create_historical_research_subject_set(
    universe: IntradayUniversePublication,
) -> HistoricalResearchSubjectSet:
    if type(universe) is not IntradayUniversePublication:
        raise HistoricalQualificationError(HistoricalQualificationFailure.INPUT_INVALID)
    subjects = tuple(
        HistoricalResearchSubject(
            universe_member_identity=item.membership_identity,
            sponsor_label=item.sponsor_label,
            canonical_identity=item.canonical_instrument_id,
            market_family=item.market_family,
            universe_member_source_identity=item.source_identity,
        )
        for item in universe.members
    )
    payload = {
        "current_universe_identity": universe.publication_identity,
        "current_universe_version": universe.publication_version,
        "current_universe_integrity_identity": universe.integrity_identity,
        "current_universe_valid_from": universe.valid_from,
        "subjects": subjects,
        "current_membership_used_for_research": True,
        "historical_operational_membership_claim": False,
        "provider_presence_creates_membership": False,
        "provenance": (
            "WO-06H-CURRENT-GOVERNED-MEMBERSHIP-AS-RESEARCH-SUBJECT-SET",
        ),
        "schema_identity": HISTORICAL_SUBJECT_SET_IDENTITY,
        "schema_version": WO06H_CONTRACT_VERSION,
    }
    return HistoricalResearchSubjectSet(
        subject_set_identity=_identity("INTRADAY-HISTORICAL-SUBJECT-SET-", payload),
        integrity_identity=_identity("INTEGRITY-HISTORICAL-SUBJECT-SET-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class HistoricalSubjectBinding:
    binding_identity: str
    universe_member_identity: str
    canonical_identity: str | None
    market_family: IntradayMarketFamily
    historical_provider_fact_identity: str | None
    historical_derivative_contract_identity: str | None
    availability: HistoricalBindingAvailability
    reason: str
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        available = self.availability is HistoricalBindingAvailability.AVAILABLE
        mcx = self.market_family is IntradayMarketFamily.MCX
        if (
            not self.binding_identity.startswith("INTRADAY-HISTORICAL-SUBJECT-BINDING-")
            or not _text(self.universe_member_identity)
            or self.canonical_identity is not None and not _text(self.canonical_identity)
            or type(self.market_family) is not IntradayMarketFamily
            or self.historical_provider_fact_identity is not None
            and not _text(self.historical_provider_fact_identity)
            or self.historical_derivative_contract_identity is not None
            and not _text(self.historical_derivative_contract_identity)
            or type(self.availability) is not HistoricalBindingAvailability
            or not _text(self.reason)
            or not _texts(self.provenance)
            or available
            != (
                self.canonical_identity is not None
                and self.historical_provider_fact_identity is not None
                and (not mcx or self.historical_derivative_contract_identity is not None)
            )
        ):
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.INPUT_INVALID
            )
        _verify(
            self,
            "INTRADAY-HISTORICAL-SUBJECT-BINDING-",
            "INTEGRITY-HISTORICAL-SUBJECT-BINDING-",
        )


def create_historical_subject_binding(
    *,
    subject: HistoricalResearchSubject,
    historical_provider_fact_identity: str | None,
    historical_derivative_contract_identity: str | None = None,
    provenance: tuple[str, ...],
) -> HistoricalSubjectBinding:
    if type(subject) is not HistoricalResearchSubject:
        raise HistoricalQualificationError(HistoricalQualificationFailure.INPUT_INVALID)
    mcx = subject.market_family is IntradayMarketFamily.MCX
    if subject.canonical_identity is None:
        availability = HistoricalBindingAvailability.HISTORICAL_CANONICAL_BINDING_UNAVAILABLE
        reason = HistoricalQualificationFailure.CANONICAL_BINDING_UNAVAILABLE.value
    elif historical_provider_fact_identity is None or (
        mcx and historical_derivative_contract_identity is None
    ):
        availability = HistoricalBindingAvailability.HISTORICAL_PREREQUISITE_UNAVAILABLE
        reason = HistoricalQualificationFailure.PREREQUISITE_UNAVAILABLE.value
    else:
        availability = HistoricalBindingAvailability.AVAILABLE
        reason = "EXACT_HISTORICAL_BINDING_AVAILABLE"
    payload = {
        "universe_member_identity": subject.universe_member_identity,
        "canonical_identity": subject.canonical_identity,
        "market_family": subject.market_family,
        "historical_provider_fact_identity": historical_provider_fact_identity,
        "historical_derivative_contract_identity": historical_derivative_contract_identity,
        "availability": availability,
        "reason": reason,
        "provenance": provenance,
    }
    return HistoricalSubjectBinding(
        binding_identity=_identity("INTRADAY-HISTORICAL-SUBJECT-BINDING-", payload),
        integrity_identity=_identity("INTEGRITY-HISTORICAL-SUBJECT-BINDING-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class HistoricalSessionSelection:
    selection_identity: str
    exchange: str
    target_session_identity: str
    target_trading_date: date
    target_schedule_source_identity: str
    target_schedule_source_version: str
    previous_session_identity: str
    previous_trading_date: date
    previous_schedule_source_identity: str
    previous_schedule_source_version: str
    observation_boundary_identity: str
    observation_boundary: datetime
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        if (
            not self.selection_identity.startswith("INTRADAY-HISTORICAL-SESSION-")
            or not _text(self.exchange)
            or not _texts(
                (
                    self.target_session_identity,
                    self.target_schedule_source_identity,
                    self.target_schedule_source_version,
                    self.previous_session_identity,
                    self.previous_schedule_source_identity,
                    self.previous_schedule_source_version,
                    self.observation_boundary_identity,
                )
            )
            or type(self.target_trading_date) is not date
            or type(self.previous_trading_date) is not date
            or self.previous_trading_date >= self.target_trading_date
            or not _aware(self.observation_boundary)
            or not _texts(self.provenance)
            or any(
                value.upper() in {"LATEST", "NEWEST", "CURRENT"}
                for value in (
                    self.target_session_identity,
                    self.observation_boundary_identity,
                )
            )
        ):
            failure = (
                HistoricalQualificationFailure.EXPLICIT_SESSION_REQUIRED
                if not _text(self.target_session_identity)
                else HistoricalQualificationFailure.INPUT_INVALID
            )
            raise HistoricalQualificationError(failure)
        _verify(
            self,
            "INTRADAY-HISTORICAL-SESSION-",
            "INTEGRITY-HISTORICAL-SESSION-",
        )


def select_historical_session(
    *,
    calendar: HistoricalCalendarSource,
    exchange: str,
    target_trading_date: date,
    observation_boundary_identity: str,
    observation_boundary: datetime,
    provenance: tuple[str, ...],
) -> HistoricalSessionSelection:
    if (
        not callable(getattr(calendar, "schedule_for", None))
        or not callable(getattr(calendar, "previous_trading_schedule", None))
        or not _text(observation_boundary_identity)
        or observation_boundary_identity.upper() in {"LATEST", "NEWEST", "CURRENT"}
    ):
        raise HistoricalQualificationError(
            HistoricalQualificationFailure.EXPLICIT_SESSION_REQUIRED
        )
    target = calendar.schedule_for(exchange, target_trading_date)
    previous = calendar.previous_trading_schedule(exchange, target_trading_date)
    if (
        type(target) is not MarketDaySchedule
        or type(previous) is not MarketDaySchedule
        or target.status is not TradingDayStatus.TRADING
        or previous.status is not TradingDayStatus.TRADING
        or target.exchange != exchange
        or previous.exchange != exchange
        or previous.trading_date >= target.trading_date
    ):
        raise HistoricalQualificationError(
            HistoricalQualificationFailure.PREREQUISITE_UNAVAILABLE
        )
    payload = {
        "exchange": exchange,
        "target_session_identity": target.session_id,
        "target_trading_date": target.trading_date,
        "target_schedule_source_identity": target.source_identity,
        "target_schedule_source_version": target.source_version,
        "previous_session_identity": previous.session_id,
        "previous_trading_date": previous.trading_date,
        "previous_schedule_source_identity": previous.source_identity,
        "previous_schedule_source_version": previous.source_version,
        "observation_boundary_identity": observation_boundary_identity,
        "observation_boundary": observation_boundary,
        "provenance": provenance,
    }
    return HistoricalSessionSelection(
        selection_identity=_identity("INTRADAY-HISTORICAL-SESSION-", payload),
        integrity_identity=_identity("INTEGRITY-HISTORICAL-SESSION-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class HistoricalPreviousSessionFacts:
    facts_identity: str
    canonical_identity: str
    target_session_identity: str
    previous_session_identity: str
    previous_daily_candle_identity: str
    completed_at: datetime
    observation_boundary: datetime
    high: Decimal
    low: Decimal
    close: Decimal
    narrow_cpr: NarrowCprFact
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        if (
            not self.facts_identity.startswith("INTRADAY-HISTORICAL-PREVIOUS-SESSION-")
            or not _texts(
                (
                    self.canonical_identity,
                    self.target_session_identity,
                    self.previous_session_identity,
                    self.previous_daily_candle_identity,
                )
            )
            or not _aware(self.completed_at)
            or not _aware(self.observation_boundary)
            or self.completed_at > self.observation_boundary
            or any(
                type(value) is not Decimal or not value.is_finite()
                for value in (self.high, self.low, self.close)
            )
            or type(self.narrow_cpr) is not NarrowCprFact
            or self.narrow_cpr.schema_identity != NARROW_CPR_FACT_IDENTITY
            or self.narrow_cpr.schema_version != PART1_CONTRACT_VERSION
            or not _texts(self.provenance)
        ):
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.LOOK_AHEAD
            )
        _verify(
            self,
            "INTRADAY-HISTORICAL-PREVIOUS-SESSION-",
            "INTEGRITY-HISTORICAL-PREVIOUS-SESSION-",
        )


def reconstruct_previous_session_facts(
    *,
    canonical_identity: str,
    session: HistoricalSessionSelection,
    previous_daily_candle_identity: str,
    completed_at: datetime,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    source_integrity_identity: str,
    provenance: tuple[str, ...],
) -> HistoricalPreviousSessionFacts:
    if type(session) is not HistoricalSessionSelection:
        raise HistoricalQualificationError(HistoricalQualificationFailure.INPUT_INVALID)
    try:
        candle = PreviousCompletedDailyCandle(
            canonical_subject_identity=canonical_identity,
            previous_session_identity=session.previous_session_identity,
            observation_session_identity=session.target_session_identity,
            source_daily_candle_identity=previous_daily_candle_identity,
            completed_at=completed_at,
            observation_boundary=session.observation_boundary,
            high=high,
            low=low,
            close=close,
            completed=True,
            source_integrity_identity=source_integrity_identity,
            provenance=provenance,
        )
        narrow = create_narrow_cpr_fact(candle)
    except QualificationError as error:
        failure = (
            HistoricalQualificationFailure.LOOK_AHEAD
            if error.failure is QualificationFailure.LOOK_AHEAD
            else HistoricalQualificationFailure.INCOMPLETE_CANDLE
        )
        raise HistoricalQualificationError(failure) from error
    payload = {
        "canonical_identity": canonical_identity,
        "target_session_identity": session.target_session_identity,
        "previous_session_identity": session.previous_session_identity,
        "previous_daily_candle_identity": previous_daily_candle_identity,
        "completed_at": completed_at,
        "observation_boundary": session.observation_boundary,
        "high": high,
        "low": low,
        "close": close,
        "narrow_cpr": narrow,
        "provenance": provenance,
    }
    return HistoricalPreviousSessionFacts(
        facts_identity=_identity("INTRADAY-HISTORICAL-PREVIOUS-SESSION-", payload),
        integrity_identity=_identity("INTEGRITY-HISTORICAL-PREVIOUS-SESSION-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class HistoricalTimeframeFacts:
    fact_set_identity: str
    timeframe: IntradayTimeframe
    completed_candle_identities: tuple[str, ...]
    source_identities: tuple[str, ...]
    available_at: datetime
    completed: bool
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        if (
            not self.fact_set_identity.startswith("INTRADAY-HISTORICAL-TIMEFRAME-FACTS-")
            or type(self.timeframe) is not IntradayTimeframe
            or not _texts(self.completed_candle_identities)
            or not _texts(self.source_identities)
            or not _aware(self.available_at)
            or type(self.completed) is not bool
            or not self.completed
            or not _texts(self.provenance)
        ):
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.INCOMPLETE_CANDLE
            )
        _verify(
            self,
            "INTRADAY-HISTORICAL-TIMEFRAME-FACTS-",
            "INTEGRITY-HISTORICAL-TIMEFRAME-FACTS-",
        )


def create_historical_timeframe_facts(
    *,
    timeframe: IntradayTimeframe,
    completed_candle_identities: tuple[str, ...],
    source_identities: tuple[str, ...],
    available_at: datetime,
    completed: bool,
    provenance: tuple[str, ...],
) -> HistoricalTimeframeFacts:
    payload = {
        "timeframe": timeframe,
        "completed_candle_identities": completed_candle_identities,
        "source_identities": source_identities,
        "available_at": available_at,
        "completed": completed,
        "provenance": provenance,
    }
    return HistoricalTimeframeFacts(
        fact_set_identity=_identity("INTRADAY-HISTORICAL-TIMEFRAME-FACTS-", payload),
        integrity_identity=_identity("INTEGRITY-HISTORICAL-TIMEFRAME-FACTS-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class HistoricalAuxiliaryFact:
    fact_identity: str
    family: HistoricalFactFamily
    source_identities: tuple[str, ...]
    available_at: datetime
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not _text(self.fact_identity)
            or type(self.family) is not HistoricalFactFamily
            or self.family is HistoricalFactFamily.COMPLETED_OHLCV
            or not _texts(self.source_identities)
            or not _aware(self.available_at)
            or not _texts(self.provenance)
        ):
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.INPUT_INVALID
            )


def create_historical_auxiliary_fact(
    *,
    family: HistoricalFactFamily,
    source_identities: tuple[str, ...],
    available_at: datetime,
    provenance: tuple[str, ...],
) -> HistoricalAuxiliaryFact:
    payload = {
        "family": family,
        "source_identities": source_identities,
        "available_at": available_at,
        "provenance": provenance,
    }
    return HistoricalAuxiliaryFact(
        fact_identity=_identity("INTRADAY-HISTORICAL-AUXILIARY-FACT-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class HistoricalQualificationFactBundle:
    bundle_identity: str
    subject_binding_identity: str
    universe_member_identity: str
    canonical_identity: str
    target_session_identity: str
    observation_boundary_identity: str
    observation_boundary: datetime
    timeframe_facts: tuple[HistoricalTimeframeFacts, ...]
    previous_session_facts_identity: str
    narrow_cpr_fact_identity: str
    auxiliary_facts: tuple[HistoricalAuxiliaryFact, ...]
    historical_source_identities: tuple[str, ...]
    evidence_source: HistoricalEvidenceSource
    research_only: bool
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = HISTORICAL_FACT_BUNDLE_IDENTITY
    schema_version: str = WO06H_CONTRACT_VERSION

    def __post_init__(self) -> None:
        expected = {
            IntradayTimeframe.DAILY,
            IntradayTimeframe.ONE_HOUR,
            IntradayTimeframe.FIFTEEN_MINUTES,
            IntradayTimeframe.FIVE_MINUTES,
        }
        actual = {item.timeframe for item in self.timeframe_facts}
        late = any(
            item.available_at > self.observation_boundary
            for item in (*self.timeframe_facts, *self.auxiliary_facts)
        )
        if (
            not self.bundle_identity.startswith("INTRADAY-HISTORICAL-FACT-BUNDLE-")
            or not _texts(
                (
                    self.subject_binding_identity,
                    self.universe_member_identity,
                    self.canonical_identity,
                    self.target_session_identity,
                    self.observation_boundary_identity,
                    self.previous_session_facts_identity,
                    self.narrow_cpr_fact_identity,
                )
            )
            or not _aware(self.observation_boundary)
            or actual != expected
            or len(self.timeframe_facts) != len(expected)
            or any(type(item) is not HistoricalTimeframeFacts for item in self.timeframe_facts)
            or any(type(item) is not HistoricalAuxiliaryFact for item in self.auxiliary_facts)
            or late
            or not _texts(self.historical_source_identities)
            or self.evidence_source
            is not HistoricalEvidenceSource.HISTORICAL_QUALIFICATION_RECONSTRUCTION
            or not self.research_only
            or not _texts(self.provenance)
            or self.schema_identity != HISTORICAL_FACT_BUNDLE_IDENTITY
            or self.schema_version != WO06H_CONTRACT_VERSION
        ):
            failure = (
                HistoricalQualificationFailure.LOOK_AHEAD
                if late
                else HistoricalQualificationFailure.INPUT_INVALID
            )
            raise HistoricalQualificationError(failure)
        _verify(
            self,
            "INTRADAY-HISTORICAL-FACT-BUNDLE-",
            "INTEGRITY-HISTORICAL-FACT-BUNDLE-",
        )


def create_historical_fact_bundle(
    *,
    binding: HistoricalSubjectBinding,
    session: HistoricalSessionSelection,
    timeframe_facts: tuple[HistoricalTimeframeFacts, ...],
    previous_session_facts: HistoricalPreviousSessionFacts,
    auxiliary_facts: tuple[HistoricalAuxiliaryFact, ...],
    historical_source_identities: tuple[str, ...],
    provenance: tuple[str, ...],
) -> HistoricalQualificationFactBundle:
    if (
        type(binding) is not HistoricalSubjectBinding
        or binding.availability is not HistoricalBindingAvailability.AVAILABLE
        or binding.canonical_identity is None
        or type(session) is not HistoricalSessionSelection
        or type(previous_session_facts) is not HistoricalPreviousSessionFacts
        or previous_session_facts.canonical_identity != binding.canonical_identity
        or previous_session_facts.target_session_identity != session.target_session_identity
        or previous_session_facts.observation_boundary != session.observation_boundary
    ):
        raise HistoricalQualificationError(
            HistoricalQualificationFailure.PREREQUISITE_UNAVAILABLE
        )
    payload = {
        "subject_binding_identity": binding.binding_identity,
        "universe_member_identity": binding.universe_member_identity,
        "canonical_identity": binding.canonical_identity,
        "target_session_identity": session.target_session_identity,
        "observation_boundary_identity": session.observation_boundary_identity,
        "observation_boundary": session.observation_boundary,
        "timeframe_facts": timeframe_facts,
        "previous_session_facts_identity": previous_session_facts.facts_identity,
        "narrow_cpr_fact_identity": previous_session_facts.narrow_cpr.fact_identity,
        "auxiliary_facts": auxiliary_facts,
        "historical_source_identities": historical_source_identities,
        "evidence_source": HistoricalEvidenceSource.HISTORICAL_QUALIFICATION_RECONSTRUCTION,
        "research_only": True,
        "provenance": provenance,
        "schema_identity": HISTORICAL_FACT_BUNDLE_IDENTITY,
        "schema_version": WO06H_CONTRACT_VERSION,
    }
    return HistoricalQualificationFactBundle(
        bundle_identity=_identity("INTRADAY-HISTORICAL-FACT-BUNDLE-", payload),
        integrity_identity=_identity("INTEGRITY-HISTORICAL-FACT-BUNDLE-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class HistoricalQualificationReconstruction:
    reconstruction_identity: str
    subject_set_identity: str
    current_universe_identity: str
    current_universe_version: str
    reconciliation_identity: str
    reconciliation_version: str
    target_session_identity: str
    observation_boundary_identity: str
    observation_boundary: datetime
    fact_bundle_identities: tuple[str, ...]
    qualification_contract_identity: str
    qualification_contract_version: str
    hypothesis_versions: tuple[tuple[str, str], ...]
    purpose: HistoricalResearchPurpose
    evidence_source: HistoricalEvidenceSource
    research_only: bool
    not_production_discovery: bool
    not_probable: bool
    not_promotion: bool
    not_execution: bool
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = HISTORICAL_RECONSTRUCTION_IDENTITY
    schema_version: str = WO06H_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.reconstruction_identity.startswith("INTRADAY-HISTORICAL-RECONSTRUCTION-")
            or not _texts(
                (
                    self.subject_set_identity,
                    self.current_universe_identity,
                    self.current_universe_version,
                    self.reconciliation_identity,
                    self.reconciliation_version,
                    self.target_session_identity,
                    self.observation_boundary_identity,
                )
            )
            or not _aware(self.observation_boundary)
            or not _texts(self.fact_bundle_identities)
            or self.qualification_contract_identity != QUALIFICATION_CONTRACT_IDENTITY
            or self.qualification_contract_version != PART1_CONTRACT_VERSION
            or not self.hypothesis_versions
            or any(not _texts(item) for item in self.hypothesis_versions)
            or type(self.purpose) is not HistoricalResearchPurpose
            or self.purpose is not HistoricalResearchPurpose.QUALIFICATION_RESEARCH
            or self.evidence_source
            is not HistoricalEvidenceSource.HISTORICAL_QUALIFICATION_RECONSTRUCTION
            or not all(
                (
                    self.research_only,
                    self.not_production_discovery,
                    self.not_probable,
                    self.not_promotion,
                    self.not_execution,
                )
            )
            or not _texts(self.provenance)
            or self.schema_identity != HISTORICAL_RECONSTRUCTION_IDENTITY
            or self.schema_version != WO06H_CONTRACT_VERSION
        ):
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.INPUT_INVALID
            )
        _verify(
            self,
            "INTRADAY-HISTORICAL-RECONSTRUCTION-",
            "INTEGRITY-HISTORICAL-RECONSTRUCTION-",
        )


def create_historical_reconstruction(
    *,
    subject_set: HistoricalResearchSubjectSet,
    reconciliation_identity: str,
    reconciliation_version: str,
    session: HistoricalSessionSelection,
    fact_bundles: tuple[HistoricalQualificationFactBundle, ...],
    hypothesis_versions: tuple[tuple[str, str], ...],
    provenance: tuple[str, ...],
) -> HistoricalQualificationReconstruction:
    if (
        type(subject_set) is not HistoricalResearchSubjectSet
        or type(session) is not HistoricalSessionSelection
        or not fact_bundles
        or any(type(item) is not HistoricalQualificationFactBundle for item in fact_bundles)
        or any(item.target_session_identity != session.target_session_identity for item in fact_bundles)
        or any(item.observation_boundary != session.observation_boundary for item in fact_bundles)
        or any(
            item.universe_member_identity
            not in {subject.universe_member_identity for subject in subject_set.subjects}
            for item in fact_bundles
        )
    ):
        raise HistoricalQualificationError(HistoricalQualificationFailure.INPUT_INVALID)
    payload = {
        "subject_set_identity": subject_set.subject_set_identity,
        "current_universe_identity": subject_set.current_universe_identity,
        "current_universe_version": subject_set.current_universe_version,
        "reconciliation_identity": reconciliation_identity,
        "reconciliation_version": reconciliation_version,
        "target_session_identity": session.target_session_identity,
        "observation_boundary_identity": session.observation_boundary_identity,
        "observation_boundary": session.observation_boundary,
        "fact_bundle_identities": tuple(item.bundle_identity for item in fact_bundles),
        "qualification_contract_identity": QUALIFICATION_CONTRACT_IDENTITY,
        "qualification_contract_version": PART1_CONTRACT_VERSION,
        "hypothesis_versions": hypothesis_versions,
        "purpose": HistoricalResearchPurpose.QUALIFICATION_RESEARCH,
        "evidence_source": HistoricalEvidenceSource.HISTORICAL_QUALIFICATION_RECONSTRUCTION,
        "research_only": True,
        "not_production_discovery": True,
        "not_probable": True,
        "not_promotion": True,
        "not_execution": True,
        "provenance": provenance,
        "schema_identity": HISTORICAL_RECONSTRUCTION_IDENTITY,
        "schema_version": WO06H_CONTRACT_VERSION,
    }
    return HistoricalQualificationReconstruction(
        reconstruction_identity=_identity("INTRADAY-HISTORICAL-RECONSTRUCTION-", payload),
        integrity_identity=_identity("INTEGRITY-HISTORICAL-RECONSTRUCTION-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class HistoricalOutcomeEvidence:
    outcome_identity: str
    reconstruction_identity: str
    source_bundle_identity: str
    observation_boundary: datetime
    available_at: datetime
    factual_measure_identities: tuple[str, ...]
    evidence_source: HistoricalEvidenceSource
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = HISTORICAL_OUTCOME_IDENTITY
    schema_version: str = WO06H_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.outcome_identity.startswith("INTRADAY-HISTORICAL-OUTCOME-")
            or not _texts(
                (
                    self.reconstruction_identity,
                    self.source_bundle_identity,
                    *self.factual_measure_identities,
                )
            )
            or not _aware(self.observation_boundary)
            or not _aware(self.available_at)
            or self.available_at <= self.observation_boundary
            or self.evidence_source
            is not HistoricalEvidenceSource.HISTORICAL_QUALIFICATION_RECONSTRUCTION
            or not _texts(self.provenance)
            or self.schema_identity != HISTORICAL_OUTCOME_IDENTITY
            or self.schema_version != WO06H_CONTRACT_VERSION
        ):
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.LOOK_AHEAD
            )
        _verify(
            self,
            "INTRADAY-HISTORICAL-OUTCOME-",
            "INTEGRITY-HISTORICAL-OUTCOME-",
        )


def create_historical_outcome_evidence(
    *,
    reconstruction: HistoricalQualificationReconstruction,
    source_bundle_identity: str,
    available_at: datetime,
    factual_measure_identities: tuple[str, ...],
    provenance: tuple[str, ...],
) -> HistoricalOutcomeEvidence:
    payload = {
        "reconstruction_identity": reconstruction.reconstruction_identity,
        "source_bundle_identity": source_bundle_identity,
        "observation_boundary": reconstruction.observation_boundary,
        "available_at": available_at,
        "factual_measure_identities": factual_measure_identities,
        "evidence_source": HistoricalEvidenceSource.HISTORICAL_QUALIFICATION_RECONSTRUCTION,
        "provenance": provenance,
        "schema_identity": HISTORICAL_OUTCOME_IDENTITY,
        "schema_version": WO06H_CONTRACT_VERSION,
    }
    return HistoricalOutcomeEvidence(
        outcome_identity=_identity("INTRADAY-HISTORICAL-OUTCOME-", payload),
        integrity_identity=_identity("INTEGRITY-HISTORICAL-OUTCOME-", payload),
        **payload,
    )


@dataclass(frozen=True, slots=True)
class HistoricalCorpusEligibility:
    eligibility_identity: str
    reconstruction_identity: str
    subject_set_identity: str
    target_session_identity: str
    observation_boundary_identity: str
    fact_bundle_identities: tuple[str, ...]
    state: CorpusEligibilityState
    explicit_binding_required: bool
    automatic_append: bool
    reasons: tuple[str, ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = HISTORICAL_CORPUS_ELIGIBILITY_IDENTITY
    schema_version: str = WO06H_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.eligibility_identity.startswith("INTRADAY-HISTORICAL-CORPUS-ELIGIBILITY-")
            or not _texts(
                (
                    self.reconstruction_identity,
                    self.subject_set_identity,
                    self.target_session_identity,
                    self.observation_boundary_identity,
                    *self.fact_bundle_identities,
                )
            )
            or type(self.state) is not CorpusEligibilityState
            or not self.explicit_binding_required
            or self.automatic_append
            or not _texts(self.reasons)
            or not _texts(self.provenance)
            or self.schema_identity != HISTORICAL_CORPUS_ELIGIBILITY_IDENTITY
            or self.schema_version != WO06H_CONTRACT_VERSION
        ):
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.CORPUS_INELIGIBLE
            )
        _verify(
            self,
            "INTRADAY-HISTORICAL-CORPUS-ELIGIBILITY-",
            "INTEGRITY-HISTORICAL-CORPUS-ELIGIBILITY-",
        )


def assess_historical_corpus_eligibility(
    reconstruction: HistoricalQualificationReconstruction,
) -> HistoricalCorpusEligibility:
    if type(reconstruction) is not HistoricalQualificationReconstruction:
        raise HistoricalQualificationError(HistoricalQualificationFailure.INPUT_INVALID)
    payload = {
        "reconstruction_identity": reconstruction.reconstruction_identity,
        "subject_set_identity": reconstruction.subject_set_identity,
        "target_session_identity": reconstruction.target_session_identity,
        "observation_boundary_identity": reconstruction.observation_boundary_identity,
        "fact_bundle_identities": reconstruction.fact_bundle_identities,
        "state": CorpusEligibilityState.ELIGIBLE_FOR_EXPLICIT_BINDING_REVIEW,
        "explicit_binding_required": True,
        "automatic_append": False,
        "reasons": (
            "RESEARCH_IDENTITY_EXPLICIT",
            "SESSION_IDENTITY_EXPLICIT",
            "SUBJECT_SET_EXPLICIT",
            "SOURCE_INTEGRITY_BOUND",
            "NO_LOOK_AHEAD_VALIDATED",
        ),
        "provenance": ("WO-06H-CORPUS-ELIGIBILITY-ASSESSMENT",),
        "schema_identity": HISTORICAL_CORPUS_ELIGIBILITY_IDENTITY,
        "schema_version": WO06H_CONTRACT_VERSION,
    }
    return HistoricalCorpusEligibility(
        eligibility_identity=_identity("INTRADAY-HISTORICAL-CORPUS-ELIGIBILITY-", payload),
        integrity_identity=_identity("INTEGRITY-HISTORICAL-CORPUS-ELIGIBILITY-", payload),
        **payload,
    )


def historical_artifact_document(value: object) -> dict[str, object]:
    artifact_type, artifact_identity = _artifact_coordinates(value)
    artifact = _normalize(value)
    core = {
        "artifact_type": artifact_type,
        "artifact_identity": artifact_identity,
        "artifact": artifact,
    }
    return {
        **core,
        "document_integrity": _identity("INTEGRITY-HISTORICAL-DOCUMENT-", core),
    }


def historical_artifact_bytes(value: object) -> bytes:
    return _encode(historical_artifact_document(value)) + b"\n"


def historical_artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise HistoricalQualificationError(
            HistoricalQualificationFailure.INTEGRITY_INVALID
        ) from error
    if type(document) is not dict:
        raise HistoricalQualificationError(
            HistoricalQualificationFailure.INTEGRITY_INVALID
        )
    return historical_artifact_from_document(document)


def historical_artifact_from_document(document: Mapping[str, object]) -> object:
    verify_historical_artifact_document(document)
    artifact_type = document["artifact_type"]
    artifact_identity = document["artifact_identity"]
    data = document["artifact"]
    if type(artifact_type) is not str or type(data) is not dict:
        raise HistoricalQualificationError(
            HistoricalQualificationFailure.INTEGRITY_INVALID
        )
    try:
        value = _decode_historical_artifact(artifact_type, data)
        actual_type, actual_identity = _artifact_coordinates(value)
        if actual_type != artifact_type or actual_identity != artifact_identity:
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.INTEGRITY_INVALID
            )
    except (KeyError, TypeError, ValueError, QualificationError) as error:
        raise HistoricalQualificationError(
            HistoricalQualificationFailure.INTEGRITY_INVALID
        ) from error
    return value


def verify_historical_artifact_document(document: Mapping[str, object]) -> None:
    if set(document) != {
        "artifact_type",
        "artifact_identity",
        "artifact",
        "document_integrity",
    }:
        raise HistoricalQualificationError(
            HistoricalQualificationFailure.INTEGRITY_INVALID
        )
    core = {
        name: document.get(name)
        for name in ("artifact_type", "artifact_identity", "artifact")
    }
    if (
        not _text(core["artifact_type"])
        or not _text(core["artifact_identity"])
        or type(core["artifact"]) is not dict
        or document.get("document_integrity")
        != _identity("INTEGRITY-HISTORICAL-DOCUMENT-", core)
    ):
        raise HistoricalQualificationError(
            HistoricalQualificationFailure.INTEGRITY_INVALID
        )


def _decode_historical_artifact(
    artifact_type: str, data: Mapping[str, object]
) -> object:
    if artifact_type == "HistoricalResearchSubjectSet":
        return HistoricalResearchSubjectSet(
            subject_set_identity=data["subject_set_identity"],
            current_universe_identity=data["current_universe_identity"],
            current_universe_version=data["current_universe_version"],
            current_universe_integrity_identity=data[
                "current_universe_integrity_identity"
            ],
            current_universe_valid_from=datetime.fromisoformat(
                data["current_universe_valid_from"]
            ),
            subjects=tuple(_decode_subject(item) for item in data["subjects"]),
            current_membership_used_for_research=data[
                "current_membership_used_for_research"
            ],
            historical_operational_membership_claim=data[
                "historical_operational_membership_claim"
            ],
            provider_presence_creates_membership=data[
                "provider_presence_creates_membership"
            ],
            provenance=tuple(data["provenance"]),
            integrity_identity=data["integrity_identity"],
            schema_identity=data["schema_identity"],
            schema_version=data["schema_version"],
        )
    if artifact_type == "HistoricalSubjectBinding":
        return HistoricalSubjectBinding(
            binding_identity=data["binding_identity"],
            universe_member_identity=data["universe_member_identity"],
            canonical_identity=data["canonical_identity"],
            market_family=IntradayMarketFamily(data["market_family"]),
            historical_provider_fact_identity=data[
                "historical_provider_fact_identity"
            ],
            historical_derivative_contract_identity=data[
                "historical_derivative_contract_identity"
            ],
            availability=HistoricalBindingAvailability(data["availability"]),
            reason=data["reason"],
            provenance=tuple(data["provenance"]),
            integrity_identity=data["integrity_identity"],
        )
    if artifact_type == "HistoricalSessionSelection":
        return HistoricalSessionSelection(
            selection_identity=data["selection_identity"],
            exchange=data["exchange"],
            target_session_identity=data["target_session_identity"],
            target_trading_date=date.fromisoformat(data["target_trading_date"]),
            target_schedule_source_identity=data[
                "target_schedule_source_identity"
            ],
            target_schedule_source_version=data["target_schedule_source_version"],
            previous_session_identity=data["previous_session_identity"],
            previous_trading_date=date.fromisoformat(
                data["previous_trading_date"]
            ),
            previous_schedule_source_identity=data[
                "previous_schedule_source_identity"
            ],
            previous_schedule_source_version=data[
                "previous_schedule_source_version"
            ],
            observation_boundary_identity=data["observation_boundary_identity"],
            observation_boundary=datetime.fromisoformat(
                data["observation_boundary"]
            ),
            provenance=tuple(data["provenance"]),
            integrity_identity=data["integrity_identity"],
        )
    if artifact_type == "HistoricalFactualFailureEvidence":
        return HistoricalFactualFailureEvidence(
            evidence_identity=data["evidence_identity"],
            canonical_identity=data["canonical_identity"],
            target_session_identity=data["target_session_identity"],
            timeframe=(
                None
                if data["timeframe"] is None
                else IntradayTimeframe(data["timeframe"])
            ),
            expected_timestamp_count=data["expected_timestamp_count"],
            actual_timestamp_count=data["actual_timestamp_count"],
            classifications=tuple(
                HistoricalFailureClassification(item)
                for item in data["classifications"]
            ),
            mismatch_ordinal=data["mismatch_ordinal"],
            observation_boundary=datetime.fromisoformat(
                data["observation_boundary"]
            ),
            diagnosed_at=datetime.fromisoformat(data["diagnosed_at"]),
            source_identity=data["source_identity"],
            provider_failure_family=(
                None
                if data["provider_failure_family"] is None
                else HistoricalProviderFailureFamily(
                    data["provider_failure_family"]
                )
            ),
            provenance=tuple(data["provenance"]),
            integrity_identity=data["integrity_identity"],
            schema_identity=data["schema_identity"],
            schema_version=data["schema_version"],
        )
    if artifact_type == "HistoricalPreviousSessionFacts":
        narrow = qualification_artifact_from_document(
            {"artifact_type": "NarrowCprFact", "artifact": data["narrow_cpr"]}
        )
        if type(narrow) is not NarrowCprFact:
            raise HistoricalQualificationError(
                HistoricalQualificationFailure.INTEGRITY_INVALID
            )
        return HistoricalPreviousSessionFacts(
            facts_identity=data["facts_identity"],
            canonical_identity=data["canonical_identity"],
            target_session_identity=data["target_session_identity"],
            previous_session_identity=data["previous_session_identity"],
            previous_daily_candle_identity=data["previous_daily_candle_identity"],
            completed_at=datetime.fromisoformat(data["completed_at"]),
            observation_boundary=datetime.fromisoformat(
                data["observation_boundary"]
            ),
            high=Decimal(data["high"]),
            low=Decimal(data["low"]),
            close=Decimal(data["close"]),
            narrow_cpr=narrow,
            provenance=tuple(data["provenance"]),
            integrity_identity=data["integrity_identity"],
        )
    if artifact_type == "HistoricalTimeframeFacts":
        return _decode_timeframe_facts(data)
    if artifact_type == "HistoricalQualificationFactBundle":
        return HistoricalQualificationFactBundle(
            bundle_identity=data["bundle_identity"],
            subject_binding_identity=data["subject_binding_identity"],
            universe_member_identity=data["universe_member_identity"],
            canonical_identity=data["canonical_identity"],
            target_session_identity=data["target_session_identity"],
            observation_boundary_identity=data["observation_boundary_identity"],
            observation_boundary=datetime.fromisoformat(
                data["observation_boundary"]
            ),
            timeframe_facts=tuple(
                _decode_timeframe_facts(item) for item in data["timeframe_facts"]
            ),
            previous_session_facts_identity=data[
                "previous_session_facts_identity"
            ],
            narrow_cpr_fact_identity=data["narrow_cpr_fact_identity"],
            auxiliary_facts=tuple(
                _decode_auxiliary_fact(item) for item in data["auxiliary_facts"]
            ),
            historical_source_identities=tuple(
                data["historical_source_identities"]
            ),
            evidence_source=HistoricalEvidenceSource(data["evidence_source"]),
            research_only=data["research_only"],
            provenance=tuple(data["provenance"]),
            integrity_identity=data["integrity_identity"],
            schema_identity=data["schema_identity"],
            schema_version=data["schema_version"],
        )
    if artifact_type == "HistoricalQualificationReconstruction":
        return HistoricalQualificationReconstruction(
            reconstruction_identity=data["reconstruction_identity"],
            subject_set_identity=data["subject_set_identity"],
            current_universe_identity=data["current_universe_identity"],
            current_universe_version=data["current_universe_version"],
            reconciliation_identity=data["reconciliation_identity"],
            reconciliation_version=data["reconciliation_version"],
            target_session_identity=data["target_session_identity"],
            observation_boundary_identity=data["observation_boundary_identity"],
            observation_boundary=datetime.fromisoformat(
                data["observation_boundary"]
            ),
            fact_bundle_identities=tuple(data["fact_bundle_identities"]),
            qualification_contract_identity=data[
                "qualification_contract_identity"
            ],
            qualification_contract_version=data[
                "qualification_contract_version"
            ],
            hypothesis_versions=tuple(
                tuple(item) for item in data["hypothesis_versions"]
            ),
            purpose=HistoricalResearchPurpose(data["purpose"]),
            evidence_source=HistoricalEvidenceSource(data["evidence_source"]),
            research_only=data["research_only"],
            not_production_discovery=data["not_production_discovery"],
            not_probable=data["not_probable"],
            not_promotion=data["not_promotion"],
            not_execution=data["not_execution"],
            provenance=tuple(data["provenance"]),
            integrity_identity=data["integrity_identity"],
            schema_identity=data["schema_identity"],
            schema_version=data["schema_version"],
        )
    if artifact_type == "HistoricalOutcomeEvidence":
        return HistoricalOutcomeEvidence(
            outcome_identity=data["outcome_identity"],
            reconstruction_identity=data["reconstruction_identity"],
            source_bundle_identity=data["source_bundle_identity"],
            observation_boundary=datetime.fromisoformat(
                data["observation_boundary"]
            ),
            available_at=datetime.fromisoformat(data["available_at"]),
            factual_measure_identities=tuple(data["factual_measure_identities"]),
            evidence_source=HistoricalEvidenceSource(data["evidence_source"]),
            provenance=tuple(data["provenance"]),
            integrity_identity=data["integrity_identity"],
            schema_identity=data["schema_identity"],
            schema_version=data["schema_version"],
        )
    if artifact_type == "HistoricalCorpusEligibility":
        return HistoricalCorpusEligibility(
            eligibility_identity=data["eligibility_identity"],
            reconstruction_identity=data["reconstruction_identity"],
            subject_set_identity=data["subject_set_identity"],
            target_session_identity=data["target_session_identity"],
            observation_boundary_identity=data["observation_boundary_identity"],
            fact_bundle_identities=tuple(data["fact_bundle_identities"]),
            state=CorpusEligibilityState(data["state"]),
            explicit_binding_required=data["explicit_binding_required"],
            automatic_append=data["automatic_append"],
            reasons=tuple(data["reasons"]),
            provenance=tuple(data["provenance"]),
            integrity_identity=data["integrity_identity"],
            schema_identity=data["schema_identity"],
            schema_version=data["schema_version"],
        )
    raise HistoricalQualificationError(
        HistoricalQualificationFailure.INTEGRITY_INVALID
    )


def _decode_subject(data: Mapping[str, object]) -> HistoricalResearchSubject:
    return HistoricalResearchSubject(
        universe_member_identity=data["universe_member_identity"],
        sponsor_label=data["sponsor_label"],
        canonical_identity=data["canonical_identity"],
        market_family=IntradayMarketFamily(data["market_family"]),
        universe_member_source_identity=data["universe_member_source_identity"],
    )


def _decode_timeframe_facts(
    data: Mapping[str, object]
) -> HistoricalTimeframeFacts:
    return HistoricalTimeframeFacts(
        fact_set_identity=data["fact_set_identity"],
        timeframe=IntradayTimeframe(data["timeframe"]),
        completed_candle_identities=tuple(data["completed_candle_identities"]),
        source_identities=tuple(data["source_identities"]),
        available_at=datetime.fromisoformat(data["available_at"]),
        completed=data["completed"],
        provenance=tuple(data["provenance"]),
        integrity_identity=data["integrity_identity"],
    )


def _decode_auxiliary_fact(
    data: Mapping[str, object]
) -> HistoricalAuxiliaryFact:
    return HistoricalAuxiliaryFact(
        fact_identity=data["fact_identity"],
        family=HistoricalFactFamily(data["family"]),
        source_identities=tuple(data["source_identities"]),
        available_at=datetime.fromisoformat(data["available_at"]),
        provenance=tuple(data["provenance"]),
    )


def _artifact_coordinates(value: object) -> tuple[str, str]:
    names = {
        HistoricalResearchSubjectSet: "subject_set_identity",
        HistoricalSubjectBinding: "binding_identity",
        HistoricalSessionSelection: "selection_identity",
        HistoricalFactualFailureEvidence: "evidence_identity",
        HistoricalPreviousSessionFacts: "facts_identity",
        HistoricalTimeframeFacts: "fact_set_identity",
        HistoricalQualificationFactBundle: "bundle_identity",
        HistoricalQualificationReconstruction: "reconstruction_identity",
        HistoricalOutcomeEvidence: "outcome_identity",
        HistoricalCorpusEligibility: "eligibility_identity",
    }
    for kind, name in names.items():
        if type(value) is kind:
            return kind.__name__, getattr(value, name)
    raise HistoricalQualificationError(HistoricalQualificationFailure.INPUT_INVALID)


def _verify(value: object, identity_prefix: str, integrity_prefix: str) -> None:
    fields = asdict(value)
    own_identity_name = next(
        name
        for name in fields
        if name.endswith("_identity")
        and str(getattr(value, name)).startswith(identity_prefix)
    )
    fields.pop(own_identity_name)
    fields.pop("integrity_identity")
    if getattr(value, own_identity_name) != _identity(identity_prefix, fields):
        raise HistoricalQualificationError(
            HistoricalQualificationFailure.INTEGRITY_INVALID
        )
    if getattr(value, "integrity_identity") != _identity(integrity_prefix, fields):
        raise HistoricalQualificationError(
            HistoricalQualificationFailure.INTEGRITY_INVALID
        )


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {name: _normalize(item) for name, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Iterable[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(value) for value in retained)


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "HISTORICAL_CORPUS_ELIGIBILITY_IDENTITY",
    "HISTORICAL_FACT_BUNDLE_IDENTITY",
    "HISTORICAL_FAILURE_EVIDENCE_IDENTITY",
    "HISTORICAL_OUTCOME_IDENTITY",
    "HISTORICAL_RECONSTRUCTION_IDENTITY",
    "HISTORICAL_SUBJECT_SET_IDENTITY",
    "WO06H_CONTRACT_VERSION",
    "CorpusEligibilityState",
    "HistoricalAuxiliaryFact",
    "HistoricalBindingAvailability",
    "HistoricalCorpusEligibility",
    "HistoricalEvidenceSource",
    "HistoricalFactFamily",
    "HistoricalFactualFailureEvidence",
    "HistoricalFailureClassification",
    "HistoricalOutcomeEvidence",
    "HistoricalPreviousSessionFacts",
    "HistoricalProviderFailureFamily",
    "HistoricalQualificationError",
    "HistoricalQualificationFactBundle",
    "HistoricalQualificationFailure",
    "HistoricalQualificationReconstruction",
    "HistoricalResearchPurpose",
    "HistoricalResearchSubject",
    "HistoricalResearchSubjectSet",
    "HistoricalSessionSelection",
    "HistoricalSubjectBinding",
    "HistoricalTimeframeFacts",
    "assess_historical_corpus_eligibility",
    "create_historical_auxiliary_fact",
    "create_historical_fact_bundle",
    "create_historical_failure_evidence",
    "create_historical_outcome_evidence",
    "create_historical_reconstruction",
    "create_historical_research_subject_set",
    "create_historical_subject_binding",
    "create_historical_timeframe_facts",
    "historical_artifact_bytes",
    "historical_artifact_document",
    "historical_artifact_from_bytes",
    "historical_artifact_from_document",
    "reconstruct_previous_session_facts",
    "select_historical_session",
    "verify_historical_artifact_document",
]
