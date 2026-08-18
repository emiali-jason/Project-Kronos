"""Shadow-only multi-timeframe discovery and validation evidence.

The module reconciles already-produced deterministic structural evidence.  It
does not calculate a new setup predicate, threshold, readiness, or trade plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.v1.evidence import (
    candle_evidence,
    impulse_maturity_evidence,
    moving_average_evidence,
    structural_evidence,
    volatility_evidence,
)
from kronos.swing.v1.layer1 import classify_probable_from_existing_evidence
from kronos.swing.v1.models import (
    ProbableClassification,
    StructuralState,
    V1Direction,
    V1Setup,
)


SHADOW_MTF_POLICY_ID = "SWING-V1-SHADOW-MTF-DISCOVERY-V0"
SHADOW_MTF_AUTHORITY = "SHADOW_VALIDATION_ONLY"


class ShadowTimeframe(StrEnum):
    WEEKLY = "1W"
    DAILY = "1D"
    FOUR_HOUR = "4H"
    ONE_HOUR = "1H"


class ShadowCandidateState(StrEnum):
    CREATED = "CREATED"
    MAINTAINED = "MAINTAINED"
    STRENGTHENED = "STRENGTHENED"
    WEAKENED = "WEAKENED"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"
    ABSENT = "ABSENT"


@dataclass(frozen=True, slots=True)
class TimeframeStructuralEvidence:
    timeframe: ShadowTimeframe
    observation_boundary: datetime
    structure: StructuralState
    setup: V1Setup | None = None
    direction: V1Direction = V1Direction.NONE
    reason: str = ""
    relevant_levels: tuple[str, ...] = ()
    participation: str = "UNAVAILABLE"
    completed: bool = True
    session_remainder_participated: bool = False

    def __post_init__(self) -> None:
        candidate = self.setup is not None
        if (
            type(self.timeframe) is not ShadowTimeframe
            or not _aware(self.observation_boundary)
            or type(self.structure) is not StructuralState
            or (self.setup is not None and type(self.setup) is not V1Setup)
            or type(self.direction) is not V1Direction
            or candidate != (self.direction is not V1Direction.NONE)
            or not self.reason
            or type(self.relevant_levels) is not tuple
            or type(self.participation) is not str
            or not self.participation
            or self.completed is not True
            or type(self.session_remainder_participated) is not bool
            or (
                self.session_remainder_participated
                and self.timeframe is not ShadowTimeframe.FOUR_HOUR
            )
        ):
            raise ValueError("SHADOW_TIMEFRAME_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class DailyControlProbableIdentity:
    """One unchanged Daily Layer-1 probable identity retained for comparison."""

    setup: V1Setup
    direction: V1Direction

    def __post_init__(self) -> None:
        if (
            type(self.setup) is not V1Setup
            or type(self.direction) is not V1Direction
            or self.direction is V1Direction.NONE
        ):
            raise ValueError("DAILY_CONTROL_PROBABLE_IDENTITY_INVALID")


@dataclass(frozen=True, slots=True)
class DailyControlEvidence:
    candidate: bool
    setup: V1Setup | None
    direction: V1Direction
    reason: str
    observation_boundary: datetime
    probable_identities: tuple[DailyControlProbableIdentity, ...] = ()

    def __post_init__(self) -> None:
        retained = self.probable_identities
        legacy_single = self.setup is not None
        if (
            type(self.candidate) is not bool
            or type(retained) is not tuple
            or any(type(item) is not DailyControlProbableIdentity for item in retained)
            or len({(item.setup, item.direction) for item in retained}) != len(retained)
            or self.candidate != bool(retained or legacy_single)
            or (self.setup is not None and type(self.setup) is not V1Setup)
            or type(self.direction) is not V1Direction
            or (
                retained
                and len(retained) == 1
                and (
                    self.setup is not retained[0].setup
                    or self.direction is not retained[0].direction
                )
            )
            or (
                len(retained) > 1
                and (
                    self.setup is not None
                    or self.direction is not V1Direction.NONE
                )
            )
            or (
                not retained
                and self.candidate != (
                    self.setup is not None
                    and self.direction is not V1Direction.NONE
                )
            )
            or (not self.candidate and self.direction is not V1Direction.NONE)
            or not self.reason
            or not _aware(self.observation_boundary)
        ):
            raise ValueError("DAILY_CONTROL_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ShadowInstrumentAssessment:
    run_identity: str
    provider_source_identity: str
    canonical_instrument: str
    control: DailyControlEvidence
    weekly: TimeframeStructuralEvidence
    daily: TimeframeStructuralEvidence
    four_hour: TimeframeStructuralEvidence
    one_hour: TimeframeStructuralEvidence
    state: ShadowCandidateState
    setup: V1Setup | None
    direction: V1Direction
    primary_reason: str
    contradictions: tuple[str, ...]
    session_remainder_dependent_change: bool
    sponsor_observation: str = ""
    eventual_market_development: str = ""
    policy_identity: str = SHADOW_MTF_POLICY_ID
    authority: str = SHADOW_MTF_AUTHORITY

    def __post_init__(self) -> None:
        candidate = self.state in {
            ShadowCandidateState.CREATED,
            ShadowCandidateState.MAINTAINED,
            ShadowCandidateState.STRENGTHENED,
            ShadowCandidateState.WEAKENED,
            ShadowCandidateState.SUSPENDED,
        }
        if (
            not self.run_identity
            or not self.provider_source_identity
            or not self.canonical_instrument
            or type(self.control) is not DailyControlEvidence
            or tuple(item.timeframe for item in (
                self.weekly, self.daily, self.four_hour, self.one_hour
            )) != (
                ShadowTimeframe.WEEKLY,
                ShadowTimeframe.DAILY,
                ShadowTimeframe.FOUR_HOUR,
                ShadowTimeframe.ONE_HOUR,
            )
            or type(self.state) is not ShadowCandidateState
            or candidate != (self.setup is not None)
            or (self.setup is not None and type(self.setup) is not V1Setup)
            or type(self.direction) is not V1Direction
            or candidate != (self.direction is not V1Direction.NONE)
            or not self.primary_reason
            or type(self.contradictions) is not tuple
            or type(self.session_remainder_dependent_change) is not bool
            or (
                self.session_remainder_dependent_change
                and not self.four_hour.session_remainder_participated
            )
            or self.policy_identity != SHADOW_MTF_POLICY_ID
            or self.authority != SHADOW_MTF_AUTHORITY
        ):
            raise ValueError("SHADOW_INSTRUMENT_ASSESSMENT_INVALID")


@dataclass(frozen=True, slots=True)
class ShadowMtfRun:
    run_identity: str
    provider_source_identity: str
    assessments: tuple[ShadowInstrumentAssessment, ...]
    control_population_size: int = 98
    shadow_population_size: int = 98
    policy_identity: str = SHADOW_MTF_POLICY_ID
    authority: str = SHADOW_MTF_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not self.run_identity
            or not self.provider_source_identity
            or type(self.assessments) is not tuple
            or len(self.assessments) != 98
            or len({item.canonical_instrument for item in self.assessments}) != 98
            or any(
                type(item) is not ShadowInstrumentAssessment
                or item.run_identity != self.run_identity
                or item.provider_source_identity != self.provider_source_identity
                for item in self.assessments
            )
            or self.control_population_size != 98
            or self.shadow_population_size != 98
            or self.policy_identity != SHADOW_MTF_POLICY_ID
            or self.authority != SHADOW_MTF_AUTHORITY
        ):
            raise ValueError("SHADOW_MTF_RUN_INVALID")


def reconcile_shadow_candidate(
    *,
    run_identity: str,
    provider_source_identity: str,
    canonical_instrument: str,
    control: DailyControlEvidence,
    weekly: TimeframeStructuralEvidence,
    daily: TimeframeStructuralEvidence,
    four_hour: TimeframeStructuralEvidence,
    one_hour: TimeframeStructuralEvidence,
    previous: ShadowInstrumentAssessment | None = None,
    remainder_material_to_change: bool = False,
) -> ShadowInstrumentAssessment:
    """Reconcile exact structural states; no numeric cutoff is introduced here."""

    _validate_timeframes(weekly, daily, four_hour, one_hour)
    higher_direction = _direction_for_structure(weekly.structure)
    daily_direction = _direction_for_structure(daily.structure)
    higher_compatible = (
        higher_direction is not V1Direction.NONE
        and higher_direction is daily_direction
    )
    four_hour_candidate = four_hour.setup is not None
    four_hour_compatible = (
        four_hour_candidate
        and four_hour.direction is higher_direction
        and higher_compatible
    )
    prior_active = previous is not None and previous.setup is not None
    contradictions: list[str] = []
    if weekly.structure is StructuralState.EVIDENCE_INCOMPLETE:
        contradictions.append("1W_EVIDENCE_INCOMPLETE")
    elif not higher_compatible:
        contradictions.append("1W_1D_CONTEXT_INCOMPATIBLE")
    if four_hour_candidate and not four_hour_compatible:
        contradictions.append("4H_OPPOSES_OR_LACKS_VALID_HIGHER_CONTEXT")

    if not four_hour_compatible:
        state = (
            ShadowCandidateState.RETIRED
            if prior_active
            else ShadowCandidateState.ABSENT
        )
        setup = None
        direction = V1Direction.NONE
        reason = (
            "PRIOR_SHADOW_THESIS_NO_LONGER_HAS_VALID_1W_1D_4H_ALIGNMENT"
            if prior_active
            else "NO_VALID_1W_1D_4H_SHADOW_THESIS"
        )
    else:
        setup = four_hour.setup
        direction = four_hour.direction
        one_hour_direction = _direction_for_structure(one_hour.structure)
        if one_hour_direction not in {V1Direction.NONE, direction}:
            state = ShadowCandidateState.SUSPENDED
            reason = "1H_STRUCTURAL_PROGRESSION_OPPOSES_VALID_HIGHER_THESIS"
            contradictions.append("1H_OPPOSES_1W_1D_4H")
        elif one_hour_direction is V1Direction.NONE:
            state = ShadowCandidateState.WEAKENED
            reason = "1H_PROGRESSION_MIXED_OR_UNAVAILABLE"
        elif not prior_active:
            state = ShadowCandidateState.CREATED
            reason = "COMPLETED_1W_1D_4H_1H_STRUCTURE_ALIGNED"
        elif previous is not None and previous.state in {
            ShadowCandidateState.WEAKENED,
            ShadowCandidateState.SUSPENDED,
        }:
            state = ShadowCandidateState.STRENGTHENED
            reason = "1H_PROGRESSION_REALIGNED_WITH_EXISTING_HIGHER_THESIS"
        else:
            state = ShadowCandidateState.MAINTAINED
            reason = "COMPLETED_MTF_STRUCTURE_CONTINUES_TO_ALIGN"

    return ShadowInstrumentAssessment(
        run_identity,
        provider_source_identity,
        canonical_instrument,
        control,
        weekly,
        daily,
        four_hour,
        one_hour,
        state,
        setup,
        direction,
        reason,
        tuple(contradictions),
        remainder_material_to_change,
    )


def measure_shadow_timeframe(
    *,
    timeframe: ShadowTimeframe,
    candles: tuple[HistoricalCandle, ...],
    completed: bool,
    session_remainder_participated: bool = False,
) -> TimeframeStructuralEvidence:
    """Measure one completed timeframe with existing Layer-1 evidence only.

    Setup discovery is allowed only on 4H. Weekly, Daily and 1H provide their
    approved contextual/progression roles. Ambiguous dual setup output fails
    closed rather than adding a preference rule.
    """

    if (
        type(timeframe) is not ShadowTimeframe
        or type(candles) is not tuple
        or not candles
        or any(type(item) is not HistoricalCandle for item in candles)
        or completed is not True
        or any(
            current.timestamp <= previous.timestamp
            for previous, current in zip(candles, candles[1:])
        )
        or (
            session_remainder_participated
            and timeframe is not ShadowTimeframe.FOUR_HOUR
        )
    ):
        raise ValueError("SHADOW_COMPLETED_SERIES_INVALID")
    structural = structural_evidence(candles)
    setup = None
    direction = V1Direction.NONE
    reasons: tuple[str, ...]
    if timeframe is ShadowTimeframe.FOUR_HOUR:
        moving_average = moving_average_evidence(candles)
        candle = candle_evidence(candles)
        candidates = []
        for candidate_setup in V1Setup:
            classification, candidate_direction, candidate_reasons = (
                classify_probable_from_existing_evidence(
                    candidate_setup,
                    structural,
                    moving_average,
                    candle,
                    volatility_evidence(candles, candidate_setup),
                    impulse_maturity_evidence(candles, candidate_setup),
                )
            )
            if classification is ProbableClassification.PROBABLE_CANDIDATE:
                candidates.append(
                    (candidate_setup, candidate_direction, candidate_reasons)
                )
        if len(candidates) == 1:
            setup, direction, reasons = candidates[0]
        elif len(candidates) > 1:
            reasons = ("MULTIPLE_EXISTING_SETUP_PREDICATES_MATCH_FAIL_CLOSED",)
        else:
            reasons = ("NO_EXISTING_4H_SETUP_PREDICATE_MATCH",)
    else:
        reasons = (f"{timeframe.value}_STRUCTURAL_ROLE_ONLY",)
    return TimeframeStructuralEvidence(
        timeframe=timeframe,
        observation_boundary=candles[-1].timestamp,
        structure=(
            structural.consensus
            if structural.consensus is not None
            else StructuralState.MIXED_UNCLEAR
            if structural.availability.value == "AVAILABLE"
            else StructuralState.EVIDENCE_INCOMPLETE
        ),
        setup=setup,
        direction=direction,
        reason=" · ".join(reasons),
        relevant_levels=tuple(
            f"{alternative.definition_id}:{pivot.kind.value}:{pivot.value}"
            for alternative in structural.alternatives
            for pivot in (
                *alternative.swing_highs[-2:],
                *alternative.swing_lows[-2:],
            )
        ),
        participation="EXISTING_VOLUME_EVIDENCE_ONLY_NO_NEW_THRESHOLD",
        completed=True,
        session_remainder_participated=session_remainder_participated,
    )


def _validate_timeframes(*items: TimeframeStructuralEvidence) -> None:
    if tuple(item.timeframe for item in items) != (
        ShadowTimeframe.WEEKLY,
        ShadowTimeframe.DAILY,
        ShadowTimeframe.FOUR_HOUR,
        ShadowTimeframe.ONE_HOUR,
    ):
        raise ValueError("SHADOW_TIMEFRAME_SEQUENCE_INVALID")


def _direction_for_structure(state: StructuralState) -> V1Direction:
    return {
        StructuralState.BULLISH_HH_HL: V1Direction.LONG,
        StructuralState.BEARISH_LH_LL: V1Direction.SHORT,
        StructuralState.MIXED_UNCLEAR: V1Direction.NONE,
        StructuralState.EVIDENCE_INCOMPLETE: V1Direction.NONE,
    }[state]


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "DailyControlEvidence",
    "DailyControlProbableIdentity",
    "SHADOW_MTF_AUTHORITY",
    "SHADOW_MTF_POLICY_ID",
    "ShadowCandidateState",
    "ShadowInstrumentAssessment",
    "ShadowMtfRun",
    "ShadowTimeframe",
    "TimeframeStructuralEvidence",
    "measure_shadow_timeframe",
    "reconcile_shadow_candidate",
]
