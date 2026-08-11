"""Deterministic Swing Phase 1 V0 Trade Plan construction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.candidate_validation import SwingCandidate
from kronos.swing.zero import SwingAssessment, SwingDirection, SwingSetup


SWING_PHASE1_TRADE_PLAN_POLICY_ID = "SWING-PHASE1-V0-TRADE-PLAN-POLICY"
_PULLBACK_WINDOW = 5
_PULLBACK_TARGET_WINDOW = 20
_BREAKOUT_WINDOW = 10


class TradePlanStatus(StrEnum):
    """V0 actionability of one still-QUALIFIED candidate."""

    ACTIONABLE = "ACTIONABLE"
    NOT_ACTIONABLE = "NOT_ACTIONABLE"
    INVALID = "INVALID"


class TradePlanFailure(StrEnum):
    """Typed V0 construction and actionability failures."""

    EVIDENCE_UNAVAILABLE = "EVIDENCE_UNAVAILABLE"
    INVALID_STOP_GEOMETRY = "INVALID_STOP_GEOMETRY"
    NO_VALID_STRUCTURAL_TARGET = "NO_VALID_STRUCTURAL_TARGET"


class TradePlanConstructionError(RuntimeError):
    """Fail-closed construction error without Provider implementation data."""

    def __init__(self, failure: TradePlanFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class TradePlan:
    """Immutable setup-native V0 plan preserving its qualified assessment."""

    canonical_instrument: InstrumentRecord
    canonical_identity: str
    candidate_identity: str
    setup: SwingSetup
    direction: SwingDirection
    qualification_boundary: datetime
    analytical_policy_version: str
    trade_plan_policy_version: str
    original_assessment: SwingAssessment
    status: TradePlanStatus
    failure: TradePlanFailure | None
    entry: float
    entry_condition: str
    entry_zone: None
    stop: float
    thesis_invalidation: tuple[str, ...]
    target_1: float
    target_2: None
    risk_per_unit: float
    reward_per_unit: float
    risk_reward: float | None
    calculation_inputs: tuple[str, ...]
    reason: str
    provider_neutral_provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        numeric = (
            self.entry,
            self.stop,
            self.target_1,
            self.risk_per_unit,
            self.reward_per_unit,
        )
        actionable = self.status is TradePlanStatus.ACTIONABLE
        invalid = self.status is TradePlanStatus.INVALID
        if (
            type(self.canonical_instrument) is not InstrumentRecord
            or type(self.canonical_identity) is not str
            or not self.canonical_identity
            or type(self.candidate_identity) is not str
            or not self.candidate_identity
            or type(self.setup) is not SwingSetup
            or type(self.direction) is not SwingDirection
            or self.direction is SwingDirection.NONE
            or self.qualification_boundary.tzinfo is None
            or self.qualification_boundary.utcoffset() is None
            or self.analytical_policy_version
            != self.original_assessment.rule_set_version
            or self.trade_plan_policy_version
            != SWING_PHASE1_TRADE_PLAN_POLICY_ID
            or type(self.original_assessment) is not SwingAssessment
            or self.original_assessment.setup is not self.setup
            or self.original_assessment.direction is not self.direction
            or type(self.status) is not TradePlanStatus
            or (actionable and self.failure is not None)
            or (not actionable and type(self.failure) is not TradePlanFailure)
            or any(type(value) is not float or not math.isfinite(value) for value in numeric)
            or self.entry_zone is not None
            or self.target_2 is not None
            or type(self.thesis_invalidation) is not tuple
            or not self.thesis_invalidation
            or any(not item for item in self.thesis_invalidation)
            or type(self.calculation_inputs) is not tuple
            or not self.calculation_inputs
            or any(not item for item in self.calculation_inputs)
            or not self.reason
            or type(self.provider_neutral_provenance) is not tuple
            or not self.provider_neutral_provenance
            or any(not item for item in self.provider_neutral_provenance)
            or (actionable and (self.risk_per_unit <= 0.0 or self.reward_per_unit <= 0.0))
            or (actionable and self.risk_reward is None)
            or (not actionable and self.risk_reward is not None)
            or (invalid and self.risk_per_unit > 0.0)
        ):
            raise ValueError("TRADE_PLAN_INVALID")


def build_trade_plan(
    candidate: SwingCandidate,
    candles: Sequence[HistoricalCandle],
) -> TradePlan:
    """Construct one V0 plan without mutating its qualified assessment."""

    observations = _validated_evidence(candidate, candles)
    current = observations[-1]
    long = candidate.direction is SwingDirection.LONG
    entry = current.high if long else current.low
    entry_condition = (
        "A subsequent session trades ABOVE Entry"
        if long
        else "A subsequent session trades BELOW Entry"
    )

    if candidate.setup is SwingSetup.PULLBACK_CONTINUATION:
        pullback = observations[-(_PULLBACK_WINDOW + 1) : -1]
        target_window = observations[
            -(_PULLBACK_WINDOW + _PULLBACK_TARGET_WINDOW + 1) :
            -(_PULLBACK_WINDOW + 1)
        ]
        structural_low = min(candle.low for candle in pullback)
        structural_high = max(candle.high for candle in pullback)
        stop = structural_low if long else structural_high
        target = (
            max(candle.high for candle in target_window)
            if long
            else min(candle.low for candle in target_window)
        )
        thesis = (
            "Completed Daily Close < SMA20",
            f"Completed Daily Close < Pullback Structural Low ({_number(structural_low)})",
        ) if long else (
            "Completed Daily Close > SMA20",
            f"Completed Daily Close > Pullback Structural High ({_number(structural_high)})",
        )
        inputs = (
            f"qualification_high={_number(current.high)}",
            f"qualification_low={_number(current.low)}",
            f"pullback_structural_low={_number(structural_low)}",
            f"pullback_structural_high={_number(structural_high)}",
            f"prior_twenty_high={_number(max(candle.high for candle in target_window))}",
            f"prior_twenty_low={_number(min(candle.low for candle in target_window))}",
        )
    else:
        consolidation = observations[-(_BREAKOUT_WINDOW + 1) : -1]
        range_high = max(candle.high for candle in consolidation)
        range_low = min(candle.low for candle in consolidation)
        range_width = range_high - range_low
        stop = current.low if long else current.high
        target = range_high + range_width if long else range_low - range_width
        thesis = (
            f"Completed Daily Close <= original Consolidation Range High ({_number(range_high)})",
        ) if long else (
            f"Completed Daily Close >= original Consolidation Range Low ({_number(range_low)})",
        )
        inputs = (
            f"qualification_high={_number(current.high)}",
            f"qualification_low={_number(current.low)}",
            f"range_high={_number(range_high)}",
            f"range_low={_number(range_low)}",
            f"range_width={_number(range_width)}",
        )

    risk = entry - stop if long else stop - entry
    reward = target - entry if long else entry - target
    if risk <= 0.0:
        status = TradePlanStatus.INVALID
        failure = TradePlanFailure.INVALID_STOP_GEOMETRY
        ratio = None
    elif reward <= 0.0:
        status = TradePlanStatus.NOT_ACTIONABLE
        failure = TradePlanFailure.NO_VALID_STRUCTURAL_TARGET
        ratio = None
    else:
        status = TradePlanStatus.ACTIONABLE
        failure = None
        ratio = reward / risk

    boundary = candidate.observation_boundary
    return TradePlan(
        canonical_instrument=candidate.assessment.instrument,
        canonical_identity=candidate.canonical_identity,
        candidate_identity=(
            f"{candidate.canonical_identity}|{candidate.setup.value}|"
            f"{candidate.direction.value}|{boundary.isoformat()}"
        ),
        setup=candidate.setup,
        direction=candidate.direction,
        qualification_boundary=boundary,
        analytical_policy_version=candidate.rule_set_version,
        trade_plan_policy_version=SWING_PHASE1_TRADE_PLAN_POLICY_ID,
        original_assessment=candidate.assessment,
        status=status,
        failure=failure,
        entry=entry,
        entry_condition=entry_condition,
        entry_zone=None,
        stop=stop,
        thesis_invalidation=thesis,
        target_1=target,
        target_2=None,
        risk_per_unit=risk,
        reward_per_unit=reward,
        risk_reward=ratio,
        calculation_inputs=inputs,
        reason=candidate.assessment.why,
        provider_neutral_provenance=(
            "source=Provider Foundation V2 normalized completed Daily candles",
            f"completed_boundary={boundary.isoformat()}",
        ),
    )


def _validated_evidence(
    candidate: SwingCandidate,
    candles: Sequence[HistoricalCandle],
) -> tuple[HistoricalCandle, ...]:
    minimum = (
        _PULLBACK_WINDOW + _PULLBACK_TARGET_WINDOW + 1
        if isinstance(candidate, SwingCandidate)
        and candidate.setup is SwingSetup.PULLBACK_CONTINUATION
        else _BREAKOUT_WINDOW + 1
    )
    if (
        type(candidate) is not SwingCandidate
        or isinstance(candles, (str, bytes))
        or not isinstance(candles, Sequence)
    ):
        raise TradePlanConstructionError(TradePlanFailure.EVIDENCE_UNAVAILABLE)
    observations = tuple(candles)
    if (
        len(observations) < minimum
        or any(type(candle) is not HistoricalCandle for candle in observations)
        or observations[-1].timestamp != candidate.observation_boundary
        or any(
            current.timestamp <= previous.timestamp
            for previous, current in zip(observations, observations[1:])
        )
    ):
        raise TradePlanConstructionError(TradePlanFailure.EVIDENCE_UNAVAILABLE)
    return observations


def _number(value: float) -> str:
    return f"{value:.12g}"


__all__ = [
    "SWING_PHASE1_TRADE_PLAN_POLICY_ID",
    "TradePlan",
    "TradePlanConstructionError",
    "TradePlanFailure",
    "TradePlanStatus",
    "build_trade_plan",
]
