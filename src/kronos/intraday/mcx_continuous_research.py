"""Research-only non-back-adjusted MCX continuous futures qualification.

The series constructed here is analytical evidence, never an executable
instrument.  Every retained candle remains attributed to one exact derivative
contract.  ADR-0017 bindings in the immutable source corpus supply roll
authority; this module introduces no roll-selection rule and publishes no
production pointer.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.completed_evidence import (
    IntradayAnalysisPhase,
    build_completed_evidence_selection,
)
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.intraday.mcx_historical_research import (
    MCX_HISTORICAL_RESEARCH_AUTHORITY,
    McxHistoricalResearchCandle,
    McxHistoricalResearchCorpus,
    McxHistoricalResearchSession,
    McxHistoricalResearchState,
)
from kronos.intraday.nifty_relative_context import build_nifty_relative_context
from kronos.intraday.opening_semantic import (
    OpeningRelationship,
    build_opening_semantic_evidence,
)
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import (
    PROBABLES_V2_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_METHODOLOGY_IDENTITY,
    PROBABLES_V2_METHODOLOGY_VERSION,
    ProbableReasonV2,
    SemanticQualificationEvidenceV2,
    build_semantic_qualification_evidence_v2,
)
from kronos.intraday.probables_v2_refresh import (
    create_discovery_probables_v2_facts,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.market_data import HistoricalCandle


MCX_CONTINUOUS_RESEARCH_IDENTITY = (
    "KRONOS-INTRADAY-MCX-CONTINUOUS-FUTURES-RESEARCH-SERIES-V1"
)
MCX_CONTINUOUS_RESEARCH_VERSION = "1.0.0"
MCX_CONTINUOUS_RESEARCH_AUTHORITY = MCX_HISTORICAL_RESEARCH_AUTHORITY
MCX_CONTINUOUS_CONSTRUCTION_POLICY = (
    "KRONOS-INTRADAY-MCX-CONTINUOUS-FUTURES-CONSTRUCTION-POLICY-V1"
)
MCX_CONTINUOUS_REFERENCE_POLICY = (
    "CONTRACT_LOCAL_REFERENCES_CROSS_ROLL_UNAVAILABLE"
)
MCX_CONTINUOUS_PRIOR_1H_POLICY = (
    "CONTRACT_LOCAL_PRIOR_1H_CROSS_ROLL_UNAVAILABLE"
)
MCX_NATIVE_CONTINUOUS_CAPABILITY = {
    "1D": "NOT_SUPPORTED",
    "1H": "NOT_SUPPORTED",
    "15M": "NOT_SUPPORTED",
    "5M": "NOT_SUPPORTED",
}


class McxContinuousResearchError(ValueError):
    """Sanitized research contract or integrity failure."""


class ContinuousSeriesQuality(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"


class SubjectQualificationOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class ContinuousResearchCandle:
    candle_identity: str
    canonical_subject_identity: str
    canonical_contract_identity: str
    timeframe: IntradayTimeframe
    trading_date: date
    market_session_identity: str
    candle_start: datetime
    candle_end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source_candle_identities: tuple[str, ...]
    source_provider_identity: str
    integrity_identity: str

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("candle_identity")
        values.pop("integrity_identity")
        prices = (self.open, self.high, self.low, self.close)
        if (
            not self.candle_identity.startswith("INTRADAY-MCX-CONTINUOUS-CANDLE-")
            or not _texts((
                self.canonical_subject_identity,
                self.canonical_contract_identity,
                self.market_session_identity,
                self.source_provider_identity,
            ))
            or type(self.timeframe) is not IntradayTimeframe
            or type(self.trading_date) is not date
            or not _aware(self.candle_start)
            or not _aware(self.candle_end)
            or self.candle_start >= self.candle_end
            or any(
                type(item) is not Decimal or not item.is_finite() or item < 0
                for item in prices
            )
            or self.high < max(self.open, self.low, self.close)
            or self.low > min(self.open, self.high, self.close)
            or type(self.volume) is not int
            or self.volume < 0
            or not _texts(self.source_candle_identities)
            or tuple(sorted(set(self.source_candle_identities)))
            != self.source_candle_identities
            or self.candle_identity
            != _identity("INTRADAY-MCX-CONTINUOUS-CANDLE-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-MCX-CONTINUOUS-CANDLE-", values)
        ):
            raise McxContinuousResearchError("MCX_CONTINUOUS_CANDLE_INVALID")


@dataclass(frozen=True, slots=True)
class ContinuousRollBoundary:
    roll_identity: str
    canonical_subject_identity: str
    previous_trading_date: date
    current_trading_date: date
    old_contract_identity: str
    new_contract_identity: str
    old_contract_close: Decimal | None
    new_contract_open: Decimal | None
    price_discontinuity: Decimal | None
    reference_treatment: str
    prior_one_hour_treatment: str
    limitations: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("roll_identity")
        values.pop("integrity_identity")
        if (
            not self.roll_identity.startswith("INTRADAY-MCX-CONTINUOUS-ROLL-")
            or not _texts((
                self.canonical_subject_identity,
                self.old_contract_identity,
                self.new_contract_identity,
                self.reference_treatment,
                self.prior_one_hour_treatment,
            ))
            or self.previous_trading_date >= self.current_trading_date
            or self.old_contract_identity == self.new_contract_identity
            or self.reference_treatment != MCX_CONTINUOUS_REFERENCE_POLICY
            or self.prior_one_hour_treatment != MCX_CONTINUOUS_PRIOR_1H_POLICY
            or not _texts(self.limitations)
            or (
                self.old_contract_close is not None
                and self.new_contract_open is not None
                and self.price_discontinuity
                != self.new_contract_open - self.old_contract_close
            )
            or (
                (self.old_contract_close is None or self.new_contract_open is None)
                and self.price_discontinuity is not None
            )
            or self.roll_identity
            != _identity("INTRADAY-MCX-CONTINUOUS-ROLL-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-MCX-CONTINUOUS-ROLL-", values)
        ):
            raise McxContinuousResearchError("MCX_CONTINUOUS_ROLL_INVALID")


@dataclass(frozen=True, slots=True)
class ContinuousSubjectSeries:
    series_identity: str
    analytical_subject: str
    canonical_subject_identity: str
    governed_contract_identities: tuple[str, ...]
    represented_contract_identities: tuple[str, ...]
    candles: tuple[ContinuousResearchCandle, ...]
    roll_boundaries: tuple[ContinuousRollBoundary, ...]
    missing_trading_dates: tuple[date, ...]
    contract_attribution_exclusion_count: int
    source_duplicate_observation_count: int
    duplicate_count: int
    overlap_count: int
    contract_splice_violation_count: int
    quality: ContinuousSeriesQuality
    limitations: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("series_identity")
        values.pop("integrity_identity")
        if (
            not self.series_identity.startswith("INTRADAY-MCX-CONTINUOUS-SERIES-")
            or not _texts((self.analytical_subject, self.canonical_subject_identity))
            or not _texts(self.governed_contract_identities)
            or any(type(item) is not ContinuousResearchCandle for item in self.candles)
            or any(item.canonical_subject_identity != self.canonical_subject_identity for item in self.candles)
            or any(type(item) is not ContinuousRollBoundary for item in self.roll_boundaries)
            or any(type(item) is not int or item < 0 for item in (
                self.contract_attribution_exclusion_count,
                self.source_duplicate_observation_count,
                self.duplicate_count,
                self.overlap_count,
                self.contract_splice_violation_count,
            ))
            or self.duplicate_count != 0
            or self.overlap_count != 0
            or self.contract_splice_violation_count != 0
            or type(self.quality) is not ContinuousSeriesQuality
            or not _texts(self.limitations)
            or self.series_identity
            != _identity("INTRADAY-MCX-CONTINUOUS-SERIES-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-MCX-CONTINUOUS-SERIES-", values)
        ):
            raise McxContinuousResearchError("MCX_CONTINUOUS_SERIES_INVALID")

    @property
    def counts_by_timeframe(self) -> dict[IntradayTimeframe, int]:
        return {
            timeframe: sum(item.timeframe is timeframe for item in self.candles)
            for timeframe in IntradayTimeframe
        }


@dataclass(frozen=True, slots=True)
class ContinuousPhaseAssessment:
    assessment_identity: str
    analytical_subject: str
    canonical_subject_identity: str
    trading_date: date
    phase: IntradayAnalysisPhase
    analysis_boundary: datetime
    result: ProbableState
    direction: SemanticDirection | None
    reasons: tuple[ProbableReasonV2, ...]
    completed_evidence_selection_identity: str
    semantic_evidence_identity: str
    nifty_applicability: str
    source_contract_identities: tuple[str, ...]
    methodology_checksum: str
    integrity_identity: str

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("assessment_identity")
        values.pop("integrity_identity")
        if (
            not self.assessment_identity.startswith("INTRADAY-MCX-CONTINUOUS-ASSESSMENT-")
            or not _texts((
                self.analytical_subject,
                self.canonical_subject_identity,
                self.completed_evidence_selection_identity,
                self.semantic_evidence_identity,
                self.nifty_applicability,
                self.methodology_checksum,
            ))
            or type(self.phase) is not IntradayAnalysisPhase
            or type(self.result) is not ProbableState
            or self.direction is not None and type(self.direction) is not SemanticDirection
            or not self.reasons
            or any(type(item) is not ProbableReasonV2 for item in self.reasons)
            or not _texts(self.source_contract_identities)
            or self.nifty_applicability != "NOT_APPLICABLE"
            or self.methodology_checksum != PROBABLES_V2_METHODOLOGY_CHECKSUM
            or self.assessment_identity
            != _identity("INTRADAY-MCX-CONTINUOUS-ASSESSMENT-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-MCX-CONTINUOUS-ASSESSMENT-", values)
        ):
            raise McxContinuousResearchError("MCX_CONTINUOUS_ASSESSMENT_INVALID")


@dataclass(frozen=True, slots=True)
class ContinuousSubjectQualification:
    qualification_identity: str
    analytical_subject: str
    canonical_subject_identity: str
    complete_session_count: int
    phase_assessment_count: int
    result_accounting: tuple[tuple[str, int], ...]
    conflict_assessment_count: int
    state_transition_count: int
    outcome: SubjectQualificationOutcome
    commissioning_recommended: bool
    reasons: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("qualification_identity")
        values.pop("integrity_identity")
        if (
            not self.qualification_identity.startswith("INTRADAY-MCX-CONTINUOUS-QUALIFICATION-")
            or not _texts((self.analytical_subject, self.canonical_subject_identity))
            or any(type(item) is not int or item < 0 for item in (
                self.complete_session_count,
                self.phase_assessment_count,
                self.conflict_assessment_count,
                self.state_transition_count,
            ))
            or tuple(sorted(self.result_accounting)) != self.result_accounting
            or type(self.outcome) is not SubjectQualificationOutcome
            or self.commissioning_recommended is not (self.outcome is SubjectQualificationOutcome.PASS)
            or not _texts(self.reasons)
            or self.qualification_identity
            != _identity("INTRADAY-MCX-CONTINUOUS-QUALIFICATION-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-MCX-CONTINUOUS-QUALIFICATION-", values)
        ):
            raise McxContinuousResearchError("MCX_CONTINUOUS_QUALIFICATION_INVALID")


@dataclass(frozen=True, slots=True)
class McxContinuousResearchArtifact:
    artifact_identity: str
    created_at: datetime
    source_corpus_identity: str
    source_corpus_integrity_identity: str
    native_provider_capability: tuple[tuple[str, str], ...]
    construction_method: str
    back_adjustment_policy: str
    roll_gap_policy: str
    reference_policy: str
    prior_one_hour_policy: str
    benchmark_applicability: str
    series: tuple[ContinuousSubjectSeries, ...]
    assessments: tuple[ContinuousPhaseAssessment, ...]
    qualifications: tuple[ContinuousSubjectQualification, ...]
    provider_request_count: int
    authority: str
    limitations: tuple[str, ...]
    integrity_identity: str
    contract_identity: str = MCX_CONTINUOUS_RESEARCH_IDENTITY
    contract_version: str = MCX_CONTINUOUS_RESEARCH_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("artifact_identity")
        values.pop("integrity_identity")
        if (
            not self.artifact_identity.startswith("INTRADAY-MCX-CONTINUOUS-RESEARCH-")
            or not _aware(self.created_at)
            or not _texts((
                self.source_corpus_identity,
                self.source_corpus_integrity_identity,
                self.construction_method,
                self.back_adjustment_policy,
                self.roll_gap_policy,
                self.reference_policy,
                self.prior_one_hour_policy,
                self.benchmark_applicability,
                self.authority,
            ))
            or self.native_provider_capability != tuple(MCX_NATIVE_CONTINUOUS_CAPABILITY.items())
            or self.construction_method != "KRONOS_CONSTRUCTED_EXACT_CONTRACT_SEGMENTS"
            or self.back_adjustment_policy != "NON_BACK_ADJUSTED"
            or self.roll_gap_policy != "CONTRACT_ROLL_BOUNDARY_NOT_MARKET_GAP"
            or self.reference_policy != MCX_CONTINUOUS_REFERENCE_POLICY
            or self.prior_one_hour_policy != MCX_CONTINUOUS_PRIOR_1H_POLICY
            or self.benchmark_applicability != "NOT_APPLICABLE"
            or any(type(item) is not ContinuousSubjectSeries for item in self.series)
            or any(type(item) is not ContinuousPhaseAssessment for item in self.assessments)
            or any(type(item) is not ContinuousSubjectQualification for item in self.qualifications)
            or self.provider_request_count != 0
            or self.authority != MCX_CONTINUOUS_RESEARCH_AUTHORITY
            or not _texts(self.limitations)
            or self.contract_identity != MCX_CONTINUOUS_RESEARCH_IDENTITY
            or self.contract_version != MCX_CONTINUOUS_RESEARCH_VERSION
            or self.artifact_identity
            != _identity("INTRADAY-MCX-CONTINUOUS-RESEARCH-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-MCX-CONTINUOUS-RESEARCH-", values)
        ):
            raise McxContinuousResearchError("MCX_CONTINUOUS_ARTIFACT_INVALID")


def governed_native_continuous_capability() -> dict[str, str]:
    """Return current repository capability, not external SDK capability."""

    return dict(MCX_NATIVE_CONTINUOUS_CAPABILITY)


def build_mcx_continuous_research_artifact(
    *,
    source_corpus: McxHistoricalResearchCorpus,
    created_at: datetime,
    calendar_publisher: MarketCalendarPublisher,
) -> McxContinuousResearchArtifact:
    if (
        type(source_corpus) is not McxHistoricalResearchCorpus
        or not _aware(created_at)
        or type(calendar_publisher) is not MarketCalendarPublisher
        or source_corpus.authority != MCX_CONTINUOUS_RESEARCH_AUTHORITY
    ):
        raise McxContinuousResearchError("MCX_CONTINUOUS_INPUT_INVALID")
    series = tuple(
        _build_subject_series(source_corpus, subject)
        for subject in source_corpus.subjects
    )
    assessments: list[ContinuousPhaseAssessment] = []
    qualifications: list[ContinuousSubjectQualification] = []
    for item in series:
        complete_sessions = tuple(
            session for session in source_corpus.sessions
            if session.analytical_subject == item.analytical_subject
            and session.state is McxHistoricalResearchState.COMPLETE
        )
        contract_valid_sessions = tuple(
            session for session in complete_sessions
            if _contract_local_reference_available(
                session=session,
                subject_sessions=tuple(
                    value for value in source_corpus.sessions
                    if value.analytical_subject == item.analytical_subject
                ),
                calendar_publisher=calendar_publisher,
            )
        )
        subject_assessments: tuple[ContinuousPhaseAssessment, ...] = ()
        sufficient = (
            len(contract_valid_sessions) >= 5
            and item.quality is ContinuousSeriesQuality.COMPLETE
        )
        if sufficient:
            subject_assessments = tuple(
                assessment
                for session in contract_valid_sessions
                for assessment in _assess_session(
                    session=session,
                    calendar_publisher=calendar_publisher,
                )
            )
            assessments.extend(subject_assessments)
        expected = len(contract_valid_sessions) * len(tuple(IntradayAnalysisPhase))
        outcome = (
            SubjectQualificationOutcome.INSUFFICIENT_EVIDENCE
            if not sufficient
            else SubjectQualificationOutcome.PASS
            if len(subject_assessments) == expected
            else SubjectQualificationOutcome.FAIL
        )
        counts = Counter(value.result.value for value in subject_assessments)
        conflicts = sum(
            ProbableReasonV2.DIRECTION_CONFLICTING in value.reasons
            or ProbableReasonV2.PRIOR_1H_CONFLICTING_NO_DIRECTION_FLIP in value.reasons
            for value in subject_assessments
        )
        transitions = 0
        by_date: dict[date, list[ContinuousPhaseAssessment]] = defaultdict(list)
        for value in subject_assessments:
            by_date[value.trading_date].append(value)
        for values in by_date.values():
            transitions += sum(
                previous.result is not current.result
                for previous, current in zip(values, values[1:])
            )
        reasons = (
            ("FIVE_COMPLETE_SESSIONS_AND_FOUR_PHASE_REPLAY_PASS",)
            if outcome is SubjectQualificationOutcome.PASS
            else ("FEWER_THAN_FIVE_COMPLETE_CONTRACT_VALID_SESSIONS",)
            if outcome is SubjectQualificationOutcome.INSUFFICIENT_EVIDENCE
            else ("FOUR_PHASE_REPLAY_INCOMPLETE",)
        )
        values = {
            "analytical_subject": item.analytical_subject,
            "canonical_subject_identity": item.canonical_subject_identity,
            "complete_session_count": len(contract_valid_sessions),
            "phase_assessment_count": len(subject_assessments),
            "result_accounting": tuple(sorted(counts.items())),
            "conflict_assessment_count": conflicts,
            "state_transition_count": transitions,
            "outcome": outcome,
            "commissioning_recommended": outcome is SubjectQualificationOutcome.PASS,
            "reasons": reasons,
        }
        qualifications.append(ContinuousSubjectQualification(
            qualification_identity=_identity(
                "INTRADAY-MCX-CONTINUOUS-QUALIFICATION-", values
            ),
            integrity_identity=_identity(
                "INTEGRITY-INTRADAY-MCX-CONTINUOUS-QUALIFICATION-", values
            ),
            **values,
        ))
    values = {
        "created_at": created_at,
        "source_corpus_identity": source_corpus.corpus_identity,
        "source_corpus_integrity_identity": source_corpus.integrity_identity,
        "native_provider_capability": tuple(MCX_NATIVE_CONTINUOUS_CAPABILITY.items()),
        "construction_method": "KRONOS_CONSTRUCTED_EXACT_CONTRACT_SEGMENTS",
        "back_adjustment_policy": "NON_BACK_ADJUSTED",
        "roll_gap_policy": "CONTRACT_ROLL_BOUNDARY_NOT_MARKET_GAP",
        "reference_policy": MCX_CONTINUOUS_REFERENCE_POLICY,
        "prior_one_hour_policy": MCX_CONTINUOUS_PRIOR_1H_POLICY,
        "benchmark_applicability": "NOT_APPLICABLE",
        "series": series,
        "assessments": tuple(assessments),
        "qualifications": tuple(qualifications),
        "provider_request_count": 0,
        "authority": MCX_CONTINUOUS_RESEARCH_AUTHORITY,
        "limitations": (
            "Provider-native continuous history is not exposed by the governed KRONOS request contract.",
            "Expired NATGAS August intraday evidence remains unavailable.",
            "Cross-contract previous-day and prior-1H comparisons fail closed.",
            "No production, execution, trading, Risk, or performance authority.",
        ),
        "contract_identity": MCX_CONTINUOUS_RESEARCH_IDENTITY,
        "contract_version": MCX_CONTINUOUS_RESEARCH_VERSION,
    }
    return McxContinuousResearchArtifact(
        artifact_identity=_identity("INTRADAY-MCX-CONTINUOUS-RESEARCH-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-MCX-CONTINUOUS-RESEARCH-", values
        ),
        **values,
    )


def _build_subject_series(
    corpus: McxHistoricalResearchCorpus,
    analytical_subject: str,
) -> ContinuousSubjectSeries:
    sessions = tuple(
        item for item in corpus.sessions
        if item.analytical_subject == analytical_subject
    )
    bindings = {
        item.trading_date: item.binding
        for item in sessions
        if item.binding is not None
    }
    governed_contracts = tuple(dict.fromkeys(
        item.binding.canonical_contract_identity
        for item in sessions
        if item.binding is not None
    ))
    groups: dict[tuple[object, ...], list[McxHistoricalResearchCandle]] = defaultdict(list)
    attribution_exclusions = 0
    for session in sessions:
        if session.state is not McxHistoricalResearchState.COMPLETE:
            continue
        for candle in session.candles:
            expected = bindings.get(candle.trading_date)
            if (
                expected is not None
                and candle.canonical_contract_identity
                != expected.canonical_contract_identity
            ):
                attribution_exclusions += 1
                continue
            key = (
                candle.canonical_contract_identity,
                candle.timeframe,
                candle.candle_start,
                candle.candle_end,
            )
            groups[key].append(candle)
    candles: list[ContinuousResearchCandle] = []
    duplicate_sources = 0
    for values in groups.values():
        first = values[0]
        comparable = (
            first.open, first.high, first.low, first.close, first.volume,
            first.trading_date, first.session_identity,
        )
        if any(
            (
                item.open, item.high, item.low, item.close, item.volume,
                item.trading_date, item.session_identity,
            ) != comparable
            for item in values[1:]
        ):
            raise McxContinuousResearchError("MCX_CONTINUOUS_SOURCE_CONFLICT")
        duplicate_sources += len(values) - 1
        candle_values = {
            "canonical_subject_identity": first.canonical_subject_identity,
            "canonical_contract_identity": first.canonical_contract_identity,
            "timeframe": first.timeframe,
            "trading_date": first.trading_date,
            "market_session_identity": first.session_identity,
            "candle_start": first.candle_start,
            "candle_end": first.candle_end,
            "open": first.open,
            "high": first.high,
            "low": first.low,
            "close": first.close,
            "volume": first.volume,
            "source_candle_identities": tuple(sorted({item.candle_identity for item in values})),
            "source_provider_identity": first.source_identity,
        }
        candles.append(ContinuousResearchCandle(
            candle_identity=_identity("INTRADAY-MCX-CONTINUOUS-CANDLE-", candle_values),
            integrity_identity=_identity(
                "INTEGRITY-INTRADAY-MCX-CONTINUOUS-CANDLE-", candle_values
            ),
            **candle_values,
        ))
    ordered = tuple(sorted(candles, key=lambda item: (
        item.timeframe.value, item.candle_start, item.canonical_contract_identity
    )))
    overlaps = _overlap_count(ordered)
    rolls = _roll_boundaries(sessions, ordered)
    missing = tuple(
        item.trading_date for item in sessions
        if item.state is not McxHistoricalResearchState.COMPLETE
    )
    quality = (
        ContinuousSeriesQuality.COMPLETE
        if not missing and not attribution_exclusions and not overlaps
        else ContinuousSeriesQuality.PARTIAL
        if ordered
        else ContinuousSeriesQuality.REJECTED
    )
    canonical = sessions[0].canonical_subject_identity
    series_values = {
        "analytical_subject": analytical_subject,
        "canonical_subject_identity": canonical,
        "governed_contract_identities": governed_contracts,
        "represented_contract_identities": tuple(sorted({
            item.canonical_contract_identity for item in ordered
        })),
        "candles": ordered,
        "roll_boundaries": rolls,
        "missing_trading_dates": missing,
        "contract_attribution_exclusion_count": attribution_exclusions,
        "source_duplicate_observation_count": duplicate_sources,
        "duplicate_count": 0,
        "overlap_count": overlaps,
        "contract_splice_violation_count": 0,
        "quality": quality,
        "limitations": (
            "NON_BACK_ADJUSTED",
            MCX_CONTINUOUS_REFERENCE_POLICY,
            MCX_CONTINUOUS_PRIOR_1H_POLICY,
        ),
    }
    return ContinuousSubjectSeries(
        series_identity=_identity("INTRADAY-MCX-CONTINUOUS-SERIES-", series_values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-MCX-CONTINUOUS-SERIES-", series_values
        ),
        **series_values,
    )


def _roll_boundaries(
    sessions: tuple[McxHistoricalResearchSession, ...],
    candles: tuple[ContinuousResearchCandle, ...],
) -> tuple[ContinuousRollBoundary, ...]:
    bound = tuple(sorted(
        (item for item in sessions if item.binding is not None),
        key=lambda item: item.trading_date,
    ))
    results: list[ContinuousRollBoundary] = []
    for previous, current in zip(bound, bound[1:]):
        assert previous.binding is not None and current.binding is not None
        old = previous.binding.canonical_contract_identity
        new = current.binding.canonical_contract_identity
        if old == new:
            continue
        old_daily = tuple(
            item for item in candles
            if item.canonical_contract_identity == old
            and item.trading_date == previous.trading_date
            and item.timeframe is IntradayTimeframe.DAILY
        )
        new_five = tuple(
            item for item in candles
            if item.canonical_contract_identity == new
            and item.trading_date == current.trading_date
            and item.timeframe is IntradayTimeframe.FIVE_MINUTES
        )
        old_close = old_daily[-1].close if old_daily else None
        new_open = new_five[0].open if new_five else None
        limitations = tuple(
            item for condition, item in (
                (old_close is None, "OLD_CONTRACT_CLOSE_UNAVAILABLE"),
                (new_open is None, "NEW_CONTRACT_OPEN_UNAVAILABLE"),
                (True, "ROLL_DISCONTINUITY_HAS_NO_MARKET_GAP_AUTHORITY"),
            )
            if condition
        )
        roll_values = {
            "canonical_subject_identity": current.canonical_subject_identity,
            "previous_trading_date": previous.trading_date,
            "current_trading_date": current.trading_date,
            "old_contract_identity": old,
            "new_contract_identity": new,
            "old_contract_close": old_close,
            "new_contract_open": new_open,
            "price_discontinuity": (
                None if old_close is None or new_open is None else new_open - old_close
            ),
            "reference_treatment": MCX_CONTINUOUS_REFERENCE_POLICY,
            "prior_one_hour_treatment": MCX_CONTINUOUS_PRIOR_1H_POLICY,
            "limitations": limitations,
        }
        results.append(ContinuousRollBoundary(
            roll_identity=_identity("INTRADAY-MCX-CONTINUOUS-ROLL-", roll_values),
            integrity_identity=_identity(
                "INTEGRITY-INTRADAY-MCX-CONTINUOUS-ROLL-", roll_values
            ),
            **roll_values,
        ))
    return tuple(results)


def _assess_session(
    *,
    session: McxHistoricalResearchSession,
    calendar_publisher: MarketCalendarPublisher,
) -> tuple[ContinuousPhaseAssessment, ...]:
    if session.binding is None:
        raise McxContinuousResearchError("MCX_CONTINUOUS_SESSION_BINDING_UNAVAILABLE")
    calendar = CurrentMarketCalendarScheduleSource(
        calendar_publisher, observed_at=session.observation_boundary
    )
    current = calendar.schedule_for("MCX", session.trading_date)
    previous = calendar.previous_trading_schedule("MCX", session.trading_date)
    if current is None or previous is None:
        raise McxContinuousResearchError("MCX_CONTINUOUS_DOMAIN008_UNAVAILABLE")
    by_timeframe = {
        timeframe: tuple(
            item for item in session.candles if item.timeframe is timeframe
        )
        for timeframe in IntradayTimeframe
    }
    previous_daily = tuple(
        _historical(item) for item in by_timeframe[IntradayTimeframe.DAILY]
        if item.trading_date == previous.trading_date
    )
    previous_hour = tuple(
        _historical(item) for item in by_timeframe[IntradayTimeframe.ONE_HOUR]
        if item.trading_date == previous.trading_date
    )
    current_hour = tuple(
        item for item in by_timeframe[IntradayTimeframe.ONE_HOUR]
        if item.trading_date == current.trading_date
    )
    current_fifteen = by_timeframe[IntradayTimeframe.FIFTEEN_MINUTES]
    current_five = by_timeframe[IntradayTimeframe.FIVE_MINUTES]
    boundaries = {
        IntradayAnalysisPhase.OPENING: current_fifteen[0].candle_end,
        IntradayAnalysisPhase.STRUCTURE: current_fifteen[1].candle_end,
        IntradayAnalysisPhase.FIRST_CURRENT_SESSION_1H: current_hour[0].candle_end,
        IntradayAnalysisPhase.CURRENT_SESSION_ESTABLISHED: current_hour[1].candle_end,
    }
    results = []
    for phase, boundary in boundaries.items():
        operation = (
            f"INTRADAY-MCX-CONTINUOUS-RESEARCH:{session.session_identity}:{phase.value}"
        )
        facts = create_discovery_probables_v2_facts(
            universe_member_identity=f"RESEARCH-{session.analytical_subject}",
            canonical_subject_identity=session.canonical_subject_identity,
            subject_exchange="MCX",
            discovery_bundle_identity=operation,
            observation_boundary_identity=f"MCX-CONTINUOUS-{phase.value}",
            observation_boundary=boundary,
            current_schedule=current,
            previous_schedule=previous,
            previous_daily=previous_daily,
            previous_one_hour=previous_hour,
            current_one_hour=tuple(
                _historical(item) for item in current_hour if item.candle_end <= boundary
            ),
            current_fifteen_minute=tuple(
                _historical(item) for item in current_fifteen if item.candle_end <= boundary
            ),
            current_five_minute=tuple(
                _historical(item) for item in current_five if item.candle_end <= boundary
            ),
        )
        selection = build_completed_evidence_selection(
            canonical_subject_identity=facts.canonical_subject_identity,
            analysis_boundary=boundary,
            current_schedule=current,
            previous_schedule=previous,
            previous_daily=facts.previous_daily,
            previous_one_hour=facts.previous_one_hour,
            current_one_hour=facts.current_one_hour,
            current_fifteen_minute=facts.current_fifteen_minute,
            current_five_minute=facts.current_five_minute,
            provenance=(MCX_CONTINUOUS_CONSTRUCTION_POLICY, facts.facts_identity),
        )
        if selection.phase is not phase:
            raise McxContinuousResearchError("MCX_CONTINUOUS_PHASE_MISMATCH")
        nifty = None
        opening = None
        if phase is IntradayAnalysisPhase.OPENING:
            opening_candle = selection.candles(IntradayTimeframe.FIFTEEN_MINUTES)[0]
            direction = (
                SemanticDirection.LONG if opening_candle.close > opening_candle.open
                else SemanticDirection.SHORT if opening_candle.close < opening_candle.open
                else SemanticDirection.NON_DIRECTIONAL
            )
            nifty = build_nifty_relative_context(
                canonical_subject_identity=session.canonical_subject_identity,
                subject_exchange="MCX",
                opening_direction=direction.value,
                analysis_boundary=boundary,
                subject_candle=opening_candle,
                benchmark_candle=None,
                subject_session_open=opening_candle.open,
                benchmark_session_open=None,
                provenance=(MCX_CONTINUOUS_CONSTRUCTION_POLICY, "NIFTY_NOT_APPLICABLE"),
            )
            opening = build_opening_semantic_evidence(
                selection=selection,
                narrow_cpr_fact=facts.previous_session_facts.narrow_cpr,
                nifty_relative_evidence=nifty,
                provenance=(MCX_CONTINUOUS_CONSTRUCTION_POLICY, facts.facts_identity),
            )
        semantic = build_semantic_qualification_evidence_v2(
            selection=selection,
            narrow_cpr_fact=facts.previous_session_facts.narrow_cpr,
            opening_semantic=opening,
            nifty_relative=nifty,
            provenance=(MCX_CONTINUOUS_CONSTRUCTION_POLICY, facts.facts_identity),
        )
        state, direction, reasons = _evaluate_frozen_v2(
            phase=phase,
            semantic=semantic,
            opening=opening,
        )
        assessment_values = {
            "analytical_subject": session.analytical_subject,
            "canonical_subject_identity": session.canonical_subject_identity,
            "trading_date": session.trading_date,
            "phase": phase,
            "analysis_boundary": boundary,
            "result": state,
            "direction": direction,
            "reasons": reasons,
            "completed_evidence_selection_identity": selection.selection_identity,
            "semantic_evidence_identity": semantic.evidence_identity,
            "nifty_applicability": "NOT_APPLICABLE",
            "source_contract_identities": (session.binding.canonical_contract_identity,),
            "methodology_checksum": PROBABLES_V2_METHODOLOGY_CHECKSUM,
        }
        results.append(ContinuousPhaseAssessment(
            assessment_identity=_identity(
                "INTRADAY-MCX-CONTINUOUS-ASSESSMENT-", assessment_values
            ),
            integrity_identity=_identity(
                "INTEGRITY-INTRADAY-MCX-CONTINUOUS-ASSESSMENT-", assessment_values
            ),
            **assessment_values,
        ))
    return tuple(results)


def _contract_local_reference_available(
    *,
    session: McxHistoricalResearchSession,
    subject_sessions: tuple[McxHistoricalResearchSession, ...],
    calendar_publisher: MarketCalendarPublisher,
) -> bool:
    """Reject a previous-reference surface known to cross an ADR-0017 roll."""

    if session.binding is None:
        return False
    calendar = CurrentMarketCalendarScheduleSource(
        calendar_publisher, observed_at=session.observation_boundary
    )
    try:
        previous = calendar.previous_trading_schedule("MCX", session.trading_date)
    except ValueError:
        return False
    previous_session = next(
        (
            item for item in subject_sessions
            if item.trading_date == previous.trading_date and item.binding is not None
        ),
        None,
    )
    return (
        previous_session is None
        or previous_session.binding.canonical_contract_identity
        == session.binding.canonical_contract_identity
    )


def _evaluate_frozen_v2(
    *,
    phase: IntradayAnalysisPhase,
    semantic: SemanticQualificationEvidenceV2,
    opening: object | None,
) -> tuple[ProbableState, SemanticDirection | None, tuple[ProbableReasonV2, ...]]:
    """Mirror the frozen V2 decision after excluding the production MCX guard."""

    if phase is IntradayAnalysisPhase.OPENING:
        if opening is None:
            raise McxContinuousResearchError("MCX_CONTINUOUS_OPENING_UNAVAILABLE")
        fact = opening.fact
        direction = fact.opening_direction
        if not semantic.narrow_cpr_qualified:
            return ProbableState.NOT_ADMITTED, direction, (ProbableReasonV2.NARROW_CPR_NOT_SATISFIED,)
        if direction is SemanticDirection.NON_DIRECTIONAL:
            return ProbableState.NOT_ADMITTED, direction, (ProbableReasonV2.OPENING_NON_DIRECTIONAL,)
        reasons: list[ProbableReasonV2] = []
        if fact.prior_one_hour_relationship is OpeningRelationship.CONFLICTING:
            reasons.append(ProbableReasonV2.PRIOR_1H_CONFLICTING_NO_DIRECTION_FLIP)
        if fact.five_minute_relationship is not OpeningRelationship.SUPPORTING:
            reasons.append(ProbableReasonV2.OPENING_5M_NOT_SUPPORTING)
        if not reasons and opening.combined_relationship is not OpeningRelationship.SUPPORTING:
            reasons.append(ProbableReasonV2.OPENING_RELATIONSHIP_NOT_SUPPORTING)
        if reasons:
            return ProbableState.NOT_ADMITTED, direction, tuple(reasons)
        return (
            ProbableState.LONG_PROBABLE if direction is SemanticDirection.LONG else ProbableState.SHORT_PROBABLE,
            direction,
            (ProbableReasonV2.V2_CONDITIONS_SATISFIED,),
        )
    hourly = semantic.fact("1H_REGIME")
    fifteen = semantic.fact("15M_STRUCTURE")
    if not semantic.narrow_cpr_qualified:
        direction = _coherent_direction(hourly.direction, fifteen.direction)
        return ProbableState.NOT_ADMITTED, direction, (ProbableReasonV2.NARROW_CPR_NOT_SATISFIED,)
    if hourly.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}:
        return ProbableState.NOT_ADMITTED, hourly.direction, (ProbableReasonV2.ONE_HOUR_NON_DIRECTIONAL,)
    if fifteen.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}:
        return ProbableState.NOT_ADMITTED, fifteen.direction, (ProbableReasonV2.FIFTEEN_MINUTE_NON_DIRECTIONAL,)
    if hourly.direction is not fifteen.direction:
        return ProbableState.NOT_ADMITTED, SemanticDirection.CONFLICTING, (ProbableReasonV2.DIRECTION_CONFLICTING,)
    return (
        ProbableState.LONG_PROBABLE if hourly.direction is SemanticDirection.LONG else ProbableState.SHORT_PROBABLE,
        hourly.direction,
        (ProbableReasonV2.V2_CONDITIONS_SATISFIED,),
    )


def _coherent_direction(
    first: SemanticDirection,
    second: SemanticDirection,
) -> SemanticDirection:
    if first is second:
        return first
    if first in {SemanticDirection.LONG, SemanticDirection.SHORT} and second in {
        SemanticDirection.LONG, SemanticDirection.SHORT
    }:
        return SemanticDirection.CONFLICTING
    return SemanticDirection.NON_DIRECTIONAL


def _historical(value: McxHistoricalResearchCandle) -> HistoricalCandle:
    return HistoricalCandle(
        timestamp=value.source_timestamp,
        open=float(value.open),
        high=float(value.high),
        low=float(value.low),
        close=float(value.close),
        volume=value.volume,
    )


def _overlap_count(candles: tuple[ContinuousResearchCandle, ...]) -> int:
    count = 0
    by_timeframe: dict[IntradayTimeframe, list[ContinuousResearchCandle]] = defaultdict(list)
    for candle in candles:
        by_timeframe[candle.timeframe].append(candle)
    for values in by_timeframe.values():
        ordered = sorted(values, key=lambda item: item.candle_start)
        count += sum(
            current.candle_start < previous.candle_end
            for previous, current in zip(ordered, ordered[1:])
        )
    return count


def mcx_continuous_research_bytes(value: McxContinuousResearchArtifact) -> bytes:
    if type(value) is not McxContinuousResearchArtifact:
        raise McxContinuousResearchError("MCX_CONTINUOUS_ARTIFACT_INVALID")
    return _encode(value) + b"\n"


def parse_mcx_continuous_research(encoded: bytes) -> McxContinuousResearchArtifact:
    try:
        document = json.loads(encoded)
        value = _artifact_from_document(document)
    except McxContinuousResearchError:
        raise
    except Exception as error:
        raise McxContinuousResearchError("MCX_CONTINUOUS_INTEGRITY_INVALID") from error
    if mcx_continuous_research_bytes(value) != encoded:
        raise McxContinuousResearchError("MCX_CONTINUOUS_INTEGRITY_INVALID")
    return value


def _artifact_from_document(data: Mapping[str, object]) -> McxContinuousResearchArtifact:
    values = dict(data)
    values["created_at"] = datetime.fromisoformat(str(values["created_at"]))
    values["native_provider_capability"] = tuple(tuple(item) for item in values["native_provider_capability"])
    values["series"] = tuple(_series_from_document(item) for item in values["series"])
    values["assessments"] = tuple(_assessment_from_document(item) for item in values["assessments"])
    values["qualifications"] = tuple(_qualification_from_document(item) for item in values["qualifications"])
    values["limitations"] = tuple(values["limitations"])
    return McxContinuousResearchArtifact(**values)


def _series_from_document(data: Mapping[str, object]) -> ContinuousSubjectSeries:
    values = dict(data)
    values["governed_contract_identities"] = tuple(values["governed_contract_identities"])
    values["represented_contract_identities"] = tuple(values["represented_contract_identities"])
    values["candles"] = tuple(_candle_from_document(item) for item in values["candles"])
    values["roll_boundaries"] = tuple(_roll_from_document(item) for item in values["roll_boundaries"])
    values["missing_trading_dates"] = tuple(date.fromisoformat(str(item)) for item in values["missing_trading_dates"])
    values["quality"] = ContinuousSeriesQuality(values["quality"])
    values["limitations"] = tuple(values["limitations"])
    return ContinuousSubjectSeries(**values)


def _candle_from_document(data: Mapping[str, object]) -> ContinuousResearchCandle:
    values = dict(data)
    values["timeframe"] = IntradayTimeframe(values["timeframe"])
    values["trading_date"] = date.fromisoformat(str(values["trading_date"]))
    for name in ("candle_start", "candle_end"):
        values[name] = datetime.fromisoformat(str(values[name]))
    for name in ("open", "high", "low", "close"):
        values[name] = Decimal(str(values[name]))
    values["source_candle_identities"] = tuple(values["source_candle_identities"])
    return ContinuousResearchCandle(**values)


def _roll_from_document(data: Mapping[str, object]) -> ContinuousRollBoundary:
    values = dict(data)
    for name in ("previous_trading_date", "current_trading_date"):
        values[name] = date.fromisoformat(str(values[name]))
    for name in ("old_contract_close", "new_contract_open", "price_discontinuity"):
        if values[name] is not None:
            values[name] = Decimal(str(values[name]))
    values["limitations"] = tuple(values["limitations"])
    return ContinuousRollBoundary(**values)


def _assessment_from_document(data: Mapping[str, object]) -> ContinuousPhaseAssessment:
    values = dict(data)
    values["trading_date"] = date.fromisoformat(str(values["trading_date"]))
    values["phase"] = IntradayAnalysisPhase(values["phase"])
    values["analysis_boundary"] = datetime.fromisoformat(str(values["analysis_boundary"]))
    values["result"] = ProbableState(values["result"])
    values["direction"] = None if values["direction"] is None else SemanticDirection(values["direction"])
    values["reasons"] = tuple(ProbableReasonV2(item) for item in values["reasons"])
    values["source_contract_identities"] = tuple(values["source_contract_identities"])
    return ContinuousPhaseAssessment(**values)


def _qualification_from_document(data: Mapping[str, object]) -> ContinuousSubjectQualification:
    values = dict(data)
    values["result_accounting"] = tuple(tuple(item) for item in values["result_accounting"])
    values["outcome"] = SubjectQualificationOutcome(values["outcome"])
    values["reasons"] = tuple(values["reasons"])
    return ContinuousSubjectQualification(**values)


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
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(
        type(item) is str and bool(item) and item == item.strip()
        for item in values
    )


__all__ = [
    "ContinuousPhaseAssessment",
    "ContinuousResearchCandle",
    "ContinuousRollBoundary",
    "ContinuousSeriesQuality",
    "ContinuousSubjectQualification",
    "ContinuousSubjectSeries",
    "MCX_CONTINUOUS_RESEARCH_AUTHORITY",
    "MCX_CONTINUOUS_RESEARCH_IDENTITY",
    "MCX_CONTINUOUS_RESEARCH_VERSION",
    "McxContinuousResearchArtifact",
    "McxContinuousResearchError",
    "SubjectQualificationOutcome",
    "build_mcx_continuous_research_artifact",
    "governed_native_continuous_capability",
    "mcx_continuous_research_bytes",
    "parse_mcx_continuous_research",
]
