"""KRONOS-native MTF Discovery V0, independent of Pine and Shadow authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from threading import RLock

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.models import (
    PivotCandidate,
    ProbableClassification,
    V1Direction,
    V1Layer1Run,
)
from kronos.swing.v1.mtf_facts import (
    CompletedTimeframeFact,
    FactualPivotSeries,
    FactualTimeframe,
    InstrumentMtfFactSnapshot,
    SameRunMtfFactSnapshot,
)
from kronos.swing.v1.weekly_facts import (
    FactualPivotRelation,
    FactualPriceRelation,
    NseWeeklyFactualFoundation,
    WeeklyFactAvailability,
    WeeklySmaDirection,
)


NATIVE_DISCOVERY_POLICY_ID = "SWING-V1-KRONOS-NATIVE-MTF-DISCOVERY-V0"
NATIVE_DISCOVERY_POLICY_VERSION = "0"
NATIVE_DISCOVERY_AUTHORITY = "DISCOVERY_ONLY_NO_READINESS_OR_EXECUTION_AUTHORITY"
NATIVE_DISCOVERY_SCHEMA = "KRONOS-NATIVE-MTF-DISCOVERY-RUN-V1"
DEFAULT_NATIVE_DISCOVERY_EVIDENCE_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "swing-v1" / "native-discovery"
)


class NativeProductPath(StrEnum):
    NSE = "NSE_1W_1D_4H_1H"
    MCX = "MCX_CURRENT_CONTRACT_1D_4H_1H"


class Native1WState(StrEnum):
    SUPPORTIVE = "SUPPORTIVE"
    NEUTRAL = "NEUTRAL"
    OPPOSING = "OPPOSING"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Native1DState(StrEnum):
    BULLISH_SWING_REGIME = "BULLISH_SWING_REGIME"
    BEARISH_SWING_REGIME = "BEARISH_SWING_REGIME"
    BULLISH_REVERSAL_DEVELOPING = "BULLISH_REVERSAL_DEVELOPING"
    BEARISH_REVERSAL_DEVELOPING = "BEARISH_REVERSAL_DEVELOPING"
    NO_VALID_SWING_REGIME = "NO_VALID_SWING_REGIME"
    UNAVAILABLE = "UNAVAILABLE"


class Native4HState(StrEnum):
    DEVELOPING_PULLBACK = "DEVELOPING_PULLBACK"
    STRUCTURAL_HOLD = "STRUCTURAL_HOLD"
    RESUMPTION_DEVELOPING = "RESUMPTION_DEVELOPING"
    CONTINUATION_DEVELOPING = "CONTINUATION_DEVELOPING"
    DETERIORATING = "DETERIORATING"
    FAILED = "FAILED"
    NO_CURRENT_OPPORTUNITY = "NO_CURRENT_OPPORTUNITY"
    UNAVAILABLE = "UNAVAILABLE"


class Native1HState(StrEnum):
    PROGRESSING = "PROGRESSING"
    STALLING = "STALLING"
    NEUTRAL = "NEUTRAL"
    DETERIORATING = "DETERIORATING"
    FAILING = "FAILING"
    UNAVAILABLE = "UNAVAILABLE"


class NativeDiscoveryStatus(StrEnum):
    PROBABLE = "PROBABLE"
    FORMING_WATCH = "FORMING_WATCH"
    NO_CURRENT_OPPORTUNITY = "NO_CURRENT_OPPORTUNITY"
    UNAVAILABLE = "UNAVAILABLE"


class NativeContextKind(StrEnum):
    ESTABLISHED_TREND = "ESTABLISHED_TREND"
    REVERSAL = "REVERSAL"


class NativeOpportunityIdentity(StrEnum):
    ESTABLISHED_TREND_STRUCTURAL_HOLD = "ESTABLISHED_TREND_STRUCTURAL_HOLD"
    ESTABLISHED_TREND_RESUMPTION = "ESTABLISHED_TREND_RESUMPTION"
    ESTABLISHED_TREND_CONTINUATION = "ESTABLISHED_TREND_CONTINUATION"
    REVERSAL_STRUCTURAL_HOLD = "REVERSAL_STRUCTURAL_HOLD"
    REVERSAL_RESUMPTION = "REVERSAL_RESUMPTION"


class NativeAnchorType(StrEnum):
    DAILY_RADIUS_2_STRUCTURE = "DAILY_RADIUS_2_STRUCTURE"
    DAILY_SMA50 = "DAILY_SMA50"
    DAILY_SMA20 = "DAILY_SMA20"
    FOUR_HOUR_RADIUS_2_STRUCTURE = "FOUR_HOUR_RADIUS_2_STRUCTURE"


@dataclass(frozen=True, slots=True)
class NativeAnchor:
    anchor_type: NativeAnchorType
    price: float
    source_boundary: datetime

    def __post_init__(self) -> None:
        if (
            type(self.anchor_type) is not NativeAnchorType
            or type(self.price) is not float
            or not math.isfinite(self.price)
            or self.price < 0.0
            or not _aware(self.source_boundary)
        ):
            raise ValueError("NATIVE_DISCOVERY_ANCHOR_INVALID")


@dataclass(frozen=True, slots=True)
class NativeInstrumentDiscovery:
    run_identity: str
    provider_source_identity: str
    canonical_instrument: str
    product_path: NativeProductPath
    direction: V1Direction
    weekly_state: Native1WState
    daily_state: Native1DState
    four_hour_state: Native4HState
    one_hour_state: Native1HState
    status: NativeDiscoveryStatus
    context_kind: NativeContextKind | None
    opportunity_identity: NativeOpportunityIdentity | None
    operative_anchor: NativeAnchor | None
    factual_levels: tuple[tuple[str, float], ...]
    factual_boundaries: tuple[tuple[str, datetime], ...]
    volume_facts: tuple[tuple[str, int, float | None], ...]
    provider_provenance: tuple[str, ...]
    calendar_provenance: tuple[str, ...]
    reason_codes: tuple[str, ...]
    daily_control_probable_identities: tuple[str, ...]
    predecessor_result_sha256: str | None
    result_sha256: str
    policy_identity: str = NATIVE_DISCOVERY_POLICY_ID
    policy_version: str = NATIVE_DISCOVERY_POLICY_VERSION
    authority: str = NATIVE_DISCOVERY_AUTHORITY

    def __post_init__(self) -> None:
        directional = self.direction in {V1Direction.LONG, V1Direction.SHORT}
        opportunity = self.opportunity_identity is not None
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or not self.provider_source_identity
            or not self.canonical_instrument
            or type(self.product_path) is not NativeProductPath
            or type(self.direction) is not V1Direction
            or type(self.weekly_state) is not Native1WState
            or type(self.daily_state) is not Native1DState
            or type(self.four_hour_state) is not Native4HState
            or type(self.one_hour_state) is not Native1HState
            or type(self.status) is not NativeDiscoveryStatus
            or (self.context_kind is not None and type(self.context_kind) is not NativeContextKind)
            or (self.opportunity_identity is not None and type(self.opportunity_identity) is not NativeOpportunityIdentity)
            or (self.operative_anchor is not None and type(self.operative_anchor) is not NativeAnchor)
            or type(self.factual_levels) is not tuple
            or type(self.factual_boundaries) is not tuple
            or type(self.volume_facts) is not tuple
            or type(self.provider_provenance) is not tuple
            or not self.provider_provenance
            or type(self.calendar_provenance) is not tuple
            or not self.calendar_provenance
            or type(self.reason_codes) is not tuple
            or not self.reason_codes
            or type(self.daily_control_probable_identities) is not tuple
            or any(not item for item in self.daily_control_probable_identities)
            or (self.predecessor_result_sha256 is not None and len(self.predecessor_result_sha256) != 64)
            or len(self.result_sha256) != 64
            or self.policy_identity != NATIVE_DISCOVERY_POLICY_ID
            or self.policy_version != NATIVE_DISCOVERY_POLICY_VERSION
            or self.authority != NATIVE_DISCOVERY_AUTHORITY
            or (self.product_path is NativeProductPath.MCX and self.weekly_state is not Native1WState.NOT_APPLICABLE)
            or (self.status in {NativeDiscoveryStatus.PROBABLE, NativeDiscoveryStatus.FORMING_WATCH} and not directional)
            or (self.status is NativeDiscoveryStatus.PROBABLE and not opportunity)
        ):
            raise ValueError("NATIVE_INSTRUMENT_DISCOVERY_INVALID")


@dataclass(frozen=True, slots=True)
class NativeDiscoveryRun:
    run_identity: str
    provider_source_identity: str
    observed_at: datetime
    assessments: tuple[NativeInstrumentDiscovery, ...]
    result_sha256: str
    policy_identity: str = NATIVE_DISCOVERY_POLICY_ID
    policy_version: str = NATIVE_DISCOVERY_POLICY_VERSION
    authority: str = NATIVE_DISCOVERY_AUTHORITY
    schema: str = NATIVE_DISCOVERY_SCHEMA

    def __post_init__(self) -> None:
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or not self.provider_source_identity
            or not _aware(self.observed_at)
            or type(self.assessments) is not tuple
            or len(self.assessments) != 98
            or len({item.canonical_instrument for item in self.assessments}) != 98
            or any(item.run_identity != self.run_identity for item in self.assessments)
            or len(self.result_sha256) != 64
            or self.policy_identity != NATIVE_DISCOVERY_POLICY_ID
            or self.policy_version != NATIVE_DISCOVERY_POLICY_VERSION
            or self.authority != NATIVE_DISCOVERY_AUTHORITY
            or self.schema != NATIVE_DISCOVERY_SCHEMA
        ):
            raise ValueError("NATIVE_DISCOVERY_RUN_INVALID")


def discover_native_mtf(
    snapshot: SameRunMtfFactSnapshot,
    predecessor: NativeDiscoveryRun | None = None,
    daily_control: V1Layer1Run | None = None,
) -> NativeDiscoveryRun:
    """Classify one immutable same-98 factual snapshot under Native V0."""

    if type(snapshot) is not SameRunMtfFactSnapshot or (
        predecessor is not None and type(predecessor) is not NativeDiscoveryRun
    ) or (
        daily_control is not None and type(daily_control) is not V1Layer1Run
    ):
        raise ValueError("NATIVE_DISCOVERY_REQUEST_INVALID")
    previous = {} if predecessor is None else {
        item.canonical_instrument: item for item in predecessor.assessments
    }
    control = {} if daily_control is None else {
        item.canonical_identity: tuple(
            f"{assessment.setup.value}:{assessment.direction.value}"
            for assessment in item.assessments
            if assessment.classification is ProbableClassification.PROBABLE_CANDIDATE
        )
        for item in daily_control.instruments
    }
    assessments = tuple(
        _discover_instrument(
            snapshot,
            instrument,
            previous.get(instrument.canonical_instrument),
            control.get(instrument.canonical_instrument, ()),
        )
        for instrument in snapshot.instruments
    )
    digest = _digest({
        "run_identity": snapshot.run_identity,
        "provider_source_identity": snapshot.provider_source_identity,
        "observed_at": snapshot.observed_at,
        "assessments": assessments,
    })
    return NativeDiscoveryRun(
        snapshot.run_identity, snapshot.provider_source_identity,
        snapshot.observed_at, assessments, digest,
    )


def _discover_instrument(
    snapshot: SameRunMtfFactSnapshot,
    instrument: InstrumentMtfFactSnapshot,
    predecessor: NativeInstrumentDiscovery | None,
    daily_control_probable_identities: tuple[str, ...],
) -> NativeInstrumentDiscovery:
    daily = instrument.fact(FactualTimeframe.DAILY)
    four = instrument.fact(FactualTimeframe.FOUR_HOUR)
    hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    daily_state, direction, daily_reasons = classify_native_daily(
        daily, predecessor
    )
    weekly_state, weekly_reasons = (
        classify_native_weekly(instrument.nse_weekly_foundation, direction)
        if instrument.exchange == "NSE"
        else (Native1WState.NOT_APPLICABLE, ("MCX_1W_DISCOVERY_AUTHORITY_NONE",))
    )
    four_state, anchor, four_reasons = classify_native_four_hour(
        daily, four, daily_state, direction,
        None if predecessor is None else predecessor.four_hour_state,
    )
    one_state, one_reasons = classify_native_one_hour(
        hour, four_state, direction, anchor
    )
    status, context, opportunity, composition_reasons = _compose(
        instrument.exchange, weekly_state, daily_state, four_state,
        one_state, direction,
    )
    levels = _levels(daily, four, hour, anchor)
    if instrument.nse_weekly_foundation is not None:
        weekly = instrument.nse_weekly_foundation
        levels = (*levels, *tuple(
            (name, value)
            for name, value in (
                ("1W_CLOSE", weekly.latest_weekly_close),
                ("1W_SMA200", weekly.current_sma200),
                ("1W_SMA200_PRIOR_5W", weekly.prior_sma200_5w),
            )
            if value is not None
        ))
    boundaries = tuple(
        (item.timeframe.value, item.observation_boundary)
        for item in instrument.timeframes
    )
    volumes = tuple(
        (
            item.timeframe.value,
            item.volume,
            None if item.volume_facts is None else item.volume_facts.prior_20_mean,
        )
        for item in instrument.timeframes
    )
    calendar = tuple(dict.fromkeys(
        f"{item.timeframe.value}:{item.calendar_identity}:{item.calendar_version}:{item.session_identity}"
        for item in instrument.timeframes
    ))
    reasons = (*weekly_reasons, *daily_reasons, *four_reasons, *one_reasons, *composition_reasons)
    predecessor_hash = None if predecessor is None else predecessor.result_sha256
    common = {
        "run_identity": snapshot.run_identity,
        "provider_source_identity": snapshot.provider_source_identity,
        "canonical_instrument": instrument.canonical_instrument,
        "product_path": NativeProductPath.NSE if instrument.exchange == "NSE" else NativeProductPath.MCX,
        "direction": direction,
        "weekly_state": weekly_state,
        "daily_state": daily_state,
        "four_hour_state": four_state,
        "one_hour_state": one_state,
        "status": status,
        "context_kind": context,
        "opportunity_identity": opportunity,
        "operative_anchor": anchor,
        "factual_levels": levels,
        "factual_boundaries": boundaries,
        "volume_facts": volumes,
        "provider_provenance": tuple(dict.fromkeys(
            (snapshot.provider_source_identity, *(item.source_provider_identity for item in instrument.timeframes))
        )),
        "calendar_provenance": calendar,
        "reason_codes": reasons,
        "daily_control_probable_identities": daily_control_probable_identities,
        "predecessor_result_sha256": predecessor_hash,
    }
    return NativeInstrumentDiscovery(**common, result_sha256=_digest(common))


def classify_native_weekly(
    foundation: NseWeeklyFactualFoundation | None,
    direction: V1Direction,
) -> tuple[Native1WState, tuple[str, ...]]:
    if (
        foundation is None
        or foundation.availability is WeeklyFactAvailability.UNAVAILABLE
        or foundation.current_sma200 is None
        or foundation.prior_sma200_5w is None
        or foundation.latest_close_relation is None
        or foundation.sma200_direction is None
    ):
        return Native1WState.UNAVAILABLE, ("WEEKLY_SMA200_FACTS_UNAVAILABLE",)
    if direction not in {V1Direction.LONG, V1Direction.SHORT}:
        return Native1WState.NEUTRAL, ("NO_DIRECTIONAL_DAILY_PROPOSAL",)
    bars = foundation.completed_weekly_bars
    closes = tuple(item.close for item in bars)
    previous_sma = math.fsum(closes[-201:-1]) / 200
    previous_relation = _price_relation(closes[-2], previous_sma)
    if previous_relation is not foundation.latest_close_relation:
        return Native1WState.NEUTRAL, ("FRESH_WEEKLY_SMA200_CROSS_TRANSITIONAL",)
    supportive_location = (
        FactualPriceRelation.ABOVE
        if direction is V1Direction.LONG else FactualPriceRelation.BELOW
    )
    supportive_slope = (
        WeeklySmaDirection.RISING
        if direction is V1Direction.LONG else WeeklySmaDirection.FALLING
    )
    opposite_location = (
        FactualPriceRelation.BELOW
        if direction is V1Direction.LONG else FactualPriceRelation.ABOVE
    )
    opposite_slope = (
        WeeklySmaDirection.FALLING
        if direction is V1Direction.LONG else WeeklySmaDirection.RISING
    )
    structure = _weekly_structure_direction(foundation)
    if (
        foundation.latest_close_relation is supportive_location
        and foundation.sma200_direction is supportive_slope
    ):
        if structure not in {V1Direction.NONE, direction}:
            return Native1WState.NEUTRAL, ("PRIMARY_WEEKLY_SUPPORT_WITH_CONTRADICTORY_RADIUS2",)
        return Native1WState.SUPPORTIVE, ("WEEKLY_LOCATION_AND_SMA200_DIRECTION_SUPPORT",)
    if (
        foundation.latest_close_relation is opposite_location
        and foundation.sma200_direction is opposite_slope
    ):
        if structure is direction:
            return Native1WState.NEUTRAL, ("PRIMARY_WEEKLY_OPPOSITION_WITH_SUPPORTIVE_RADIUS2",)
        return Native1WState.OPPOSING, ("AFFIRMATIVE_WEEKLY_LOCATION_AND_SMA200_OPPOSITION",)
    return Native1WState.NEUTRAL, ("WEEKLY_PRIMARY_EVIDENCE_TRANSITIONAL_OR_MIXED",)


def classify_native_daily(
    fact: CompletedTimeframeFact,
    predecessor: NativeInstrumentDiscovery | None = None,
) -> tuple[Native1DState, V1Direction, tuple[str, ...]]:
    ma = fact.moving_averages
    r2 = _pivot_series(fact, 2)
    if ma is None or ma.sma20 is None or ma.sma50 is None or not _complete_pivots(r2):
        return Native1DState.UNAVAILABLE, V1Direction.NONE, ("DAILY_REQUIRED_FACTS_UNAVAILABLE",)
    structure = _pivot_direction(r2)
    prior_direction = None if predecessor is None else predecessor.direction
    prior_established = predecessor is not None and predecessor.daily_state in {
        Native1DState.BULLISH_SWING_REGIME,
        Native1DState.BEARISH_SWING_REGIME,
    }
    if prior_established and prior_direction in {V1Direction.LONG, V1Direction.SHORT}:
        failure = _structural_failure(fact.close, r2, prior_direction)
        if failure:
            return Native1DState.NO_VALID_SWING_REGIME, V1Direction.NONE, ("DAILY_RADIUS2_STRUCTURAL_FAILURE",)
    if structure is V1Direction.LONG and fact.close > ma.sma20 and fact.close > ma.sma50:
        return Native1DState.BULLISH_SWING_REGIME, V1Direction.LONG, ("DAILY_RADIUS2_HH_HL_ABOVE_SMA20_SMA50",)
    if structure is V1Direction.SHORT and fact.close < ma.sma20 and fact.close < ma.sma50:
        return Native1DState.BEARISH_SWING_REGIME, V1Direction.SHORT, ("DAILY_RADIUS2_LH_LL_BELOW_SMA20_SMA50",)
    if prior_established and prior_direction is not None:
        reason = (
            "DAILY_REGIME_MA50_DETERIORATING_STRUCTURE_INTACT"
            if (prior_direction is V1Direction.LONG and fact.close < ma.sma50)
            or (prior_direction is V1Direction.SHORT and fact.close > ma.sma50)
            else "DAILY_REGIME_MA_PULLBACK_STRUCTURE_INTACT"
        )
        state = (
            Native1DState.BULLISH_SWING_REGIME
            if prior_direction is V1Direction.LONG
            else Native1DState.BEARISH_SWING_REGIME
        )
        return state, prior_direction, (reason,)
    r1 = _pivot_series(fact, 1)
    r1_direction = _pivot_direction(r1)
    if structure is V1Direction.SHORT and r1_direction is V1Direction.LONG and _reversal_interaction(fact, ma.sma200, r2, V1Direction.LONG) and fact.close >= ma.sma20 and fact.close >= ma.sma50:
        return Native1DState.BULLISH_REVERSAL_DEVELOPING, V1Direction.LONG, ("DAILY_BULLISH_REVERSAL_SEQUENCE_DEVELOPING",)
    if structure is V1Direction.LONG and r1_direction is V1Direction.SHORT and _reversal_interaction(fact, ma.sma200, r2, V1Direction.SHORT) and fact.close <= ma.sma20 and fact.close <= ma.sma50:
        return Native1DState.BEARISH_REVERSAL_DEVELOPING, V1Direction.SHORT, ("DAILY_BEARISH_REVERSAL_SEQUENCE_DEVELOPING",)
    return Native1DState.NO_VALID_SWING_REGIME, V1Direction.NONE, ("NO_APPROVED_DAILY_REGIME_OR_REVERSAL_PREDICATE",)


def classify_native_four_hour(
    daily: CompletedTimeframeFact,
    four: CompletedTimeframeFact,
    daily_state: Native1DState,
    direction: V1Direction,
    previous_state: Native4HState | None = None,
) -> tuple[Native4HState, NativeAnchor | None, tuple[str, ...]]:
    if daily_state in {
        Native1DState.NO_VALID_SWING_REGIME,
        Native1DState.UNAVAILABLE,
    } or direction is V1Direction.NONE:
        return Native4HState.UNAVAILABLE, None, ("VALID_DIRECTIONAL_DAILY_CONTEXT_UNAVAILABLE",)
    r1, r2 = _pivot_series(four, 1), _pivot_series(four, 2)
    if not _complete_pivots(r1) or not _complete_pivots(r2):
        return Native4HState.UNAVAILABLE, None, ("FOUR_HOUR_REQUIRED_PIVOTS_UNAVAILABLE",)
    basis = _structural_anchor(four, daily, direction)
    if basis is None:
        return Native4HState.UNAVAILABLE, None, ("FOUR_HOUR_STRUCTURAL_BASIS_UNAVAILABLE",)
    if _beyond(four.close, basis.price, direction, adverse=True):
        return Native4HState.FAILED, basis, ("FOUR_HOUR_CLOSE_THROUGH_RADIUS2_BASIS",)
    supportive_r1 = _supportive_pivot(r1, direction)
    opposing_r1 = _opposing_pivot(r1, direction)
    if supportive_r1 is not None and _beyond(four.close, supportive_r1.value, direction, adverse=True):
        return Native4HState.DETERIORATING, basis, ("FOUR_HOUR_CLOSE_THROUGH_SUPPORTIVE_RADIUS1",)
    pullback = _pivot_direction(r1) is _opposite(direction)
    progress = opposing_r1 is not None and _beyond(four.close, opposing_r1.value, direction, adverse=False)
    if progress and (pullback or previous_state in {Native4HState.DEVELOPING_PULLBACK, Native4HState.STRUCTURAL_HOLD}):
        return Native4HState.RESUMPTION_DEVELOPING, basis, ("FOUR_HOUR_RADIUS1_RESUMPTION_WITH_RADIUS2_INTACT",)
    hold = _hold_anchor(four, daily, direction)
    if hold is not None:
        return Native4HState.STRUCTURAL_HOLD, hold, ("FOUR_HOUR_INTERACTION_AND_SUPPORTIVE_CLOSE",)
    if pullback:
        return Native4HState.DEVELOPING_PULLBACK, basis, ("FOUR_HOUR_COUNTER_DIRECTIONAL_RADIUS1_PULLBACK",)
    if _pivot_direction(r2) is direction and _pivot_direction(r1) is direction and progress:
        return Native4HState.CONTINUATION_DEVELOPING, basis, ("FOUR_HOUR_DIRECTIONAL_RADIUS1_RENEWAL_WITH_RADIUS2_INTACT",)
    return Native4HState.NO_CURRENT_OPPORTUNITY, basis, ("NO_APPROVED_CURRENT_FOUR_HOUR_OPPORTUNITY",)


def classify_native_one_hour(
    hour: CompletedTimeframeFact,
    four_state: Native4HState,
    direction: V1Direction,
    basis: NativeAnchor | None,
) -> tuple[Native1HState, tuple[str, ...]]:
    if four_state in {Native4HState.UNAVAILABLE, Native4HState.FAILED} or direction is V1Direction.NONE or basis is None:
        return Native1HState.UNAVAILABLE, ("VALID_FOUR_HOUR_OPPORTUNITY_BASIS_UNAVAILABLE",)
    r1 = _pivot_series(hour, 1)
    if not _complete_pivots(r1):
        return Native1HState.UNAVAILABLE, ("ONE_HOUR_RADIUS1_FACTS_UNAVAILABLE",)
    if hour.close == basis.price or _beyond(hour.close, basis.price, direction, adverse=True):
        return Native1HState.FAILING, ("ONE_HOUR_REACHES_OPERATIVE_FOUR_HOUR_BASIS",)
    supportive = _supportive_pivot(r1, direction)
    opposing = _opposing_pivot(r1, direction)
    if supportive is not None and _beyond(hour.close, supportive.value, direction, adverse=True):
        return Native1HState.DETERIORATING, ("ONE_HOUR_CLOSE_THROUGH_SUPPORTIVE_RADIUS1",)
    if opposing is not None and _beyond(hour.close, opposing.value, direction, adverse=False):
        return Native1HState.PROGRESSING, ("ONE_HOUR_CLOSE_BEYOND_OPPOSING_RADIUS1",)
    if _pivot_direction(r1) is direction:
        return Native1HState.STALLING, ("ONE_HOUR_DIRECTIONAL_STRUCTURE_WITHOUT_FRESH_PROGRESS",)
    return Native1HState.NEUTRAL, ("ONE_HOUR_COMPLETE_MIXED_NON_DESTRUCTIVE_EVIDENCE",)


def _compose(
    exchange: str,
    weekly: Native1WState,
    daily: Native1DState,
    four: Native4HState,
    hour: Native1HState,
    direction: V1Direction,
) -> tuple[NativeDiscoveryStatus, NativeContextKind | None, NativeOpportunityIdentity | None, tuple[str, ...]]:
    valid_daily = daily in {
        Native1DState.BULLISH_SWING_REGIME, Native1DState.BEARISH_SWING_REGIME,
        Native1DState.BULLISH_REVERSAL_DEVELOPING, Native1DState.BEARISH_REVERSAL_DEVELOPING,
    }
    context = (
        NativeContextKind.REVERSAL
        if daily in {Native1DState.BULLISH_REVERSAL_DEVELOPING, Native1DState.BEARISH_REVERSAL_DEVELOPING}
        else NativeContextKind.ESTABLISHED_TREND if valid_daily else None
    )
    if not valid_daily or direction is V1Direction.NONE:
        status = NativeDiscoveryStatus.UNAVAILABLE if daily is Native1DState.UNAVAILABLE else NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY
        return status, context, None, ("DIRECTIONAL_DAILY_CONTEXT_NOT_AVAILABLE",)
    if exchange == "NSE" and weekly in {Native1WState.OPPOSING, Native1WState.UNAVAILABLE}:
        return NativeDiscoveryStatus.UNAVAILABLE, context, None, (f"NSE_WEEKLY_{weekly.value}_BLOCKS_FRESH_PROBABLE",)
    if four is Native4HState.DEVELOPING_PULLBACK:
        return NativeDiscoveryStatus.FORMING_WATCH, context, None, ("DEVELOPING_PULLBACK_REMAINS_FORMING_WATCH",)
    if four in {Native4HState.UNAVAILABLE, Native4HState.FAILED} or hour is Native1HState.UNAVAILABLE:
        return NativeDiscoveryStatus.UNAVAILABLE, context, None, ("REQUIRED_OPPORTUNITY_OR_PROGRESSION_EVIDENCE_UNAVAILABLE",)
    qualifying = four in {
        Native4HState.STRUCTURAL_HOLD,
        Native4HState.RESUMPTION_DEVELOPING,
        Native4HState.CONTINUATION_DEVELOPING,
    }
    permissive_hour = hour in {
        Native1HState.PROGRESSING, Native1HState.STALLING, Native1HState.NEUTRAL,
    }
    if qualifying and permissive_hour:
        identity = _opportunity_identity(context, four)
        if identity is None:
            return NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY, context, None, ("OPPORTUNITY_IDENTITY_NOT_APPROVED_FAIL_CLOSED",)
        return NativeDiscoveryStatus.PROBABLE, context, identity, ("NATIVE_MTF_PROBABLE_COMPOSITION_SATISFIED",)
    return NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY, context, None, ("NATIVE_MTF_COMPOSITION_NOT_QUALIFIED",)


def _opportunity_identity(
    context: NativeContextKind | None, state: Native4HState
) -> NativeOpportunityIdentity | None:
    mapping = {
        (NativeContextKind.ESTABLISHED_TREND, Native4HState.STRUCTURAL_HOLD): NativeOpportunityIdentity.ESTABLISHED_TREND_STRUCTURAL_HOLD,
        (NativeContextKind.ESTABLISHED_TREND, Native4HState.RESUMPTION_DEVELOPING): NativeOpportunityIdentity.ESTABLISHED_TREND_RESUMPTION,
        (NativeContextKind.ESTABLISHED_TREND, Native4HState.CONTINUATION_DEVELOPING): NativeOpportunityIdentity.ESTABLISHED_TREND_CONTINUATION,
        (NativeContextKind.REVERSAL, Native4HState.STRUCTURAL_HOLD): NativeOpportunityIdentity.REVERSAL_STRUCTURAL_HOLD,
        (NativeContextKind.REVERSAL, Native4HState.RESUMPTION_DEVELOPING): NativeOpportunityIdentity.REVERSAL_RESUMPTION,
    }
    return mapping.get((context, state))


def _pivot_series(fact: CompletedTimeframeFact, radius: int) -> FactualPivotSeries:
    return next(item for item in fact.structural_measurements if item.radius == radius)


def _pivot_direction(series: FactualPivotSeries) -> V1Direction:
    if not _complete_pivots(series):
        return V1Direction.NONE
    high = _relation(series.swing_highs[-2], series.swing_highs[-1])
    low = _relation(series.swing_lows[-2], series.swing_lows[-1])
    if high is FactualPivotRelation.HIGHER and low is FactualPivotRelation.HIGHER:
        return V1Direction.LONG
    if high is FactualPivotRelation.LOWER and low is FactualPivotRelation.LOWER:
        return V1Direction.SHORT
    return V1Direction.NONE


def _weekly_structure_direction(foundation: NseWeeklyFactualFoundation) -> V1Direction:
    facts = foundation.radius_2_structure
    if facts is None:
        return V1Direction.NONE
    if facts.high_relation is FactualPivotRelation.HIGHER and facts.low_relation is FactualPivotRelation.HIGHER:
        return V1Direction.LONG
    if facts.high_relation is FactualPivotRelation.LOWER and facts.low_relation is FactualPivotRelation.LOWER:
        return V1Direction.SHORT
    return V1Direction.NONE


def _complete_pivots(series: FactualPivotSeries) -> bool:
    return len(series.swing_highs) >= 2 and len(series.swing_lows) >= 2


def _relation(previous: PivotCandidate, current: PivotCandidate) -> FactualPivotRelation:
    return FactualPivotRelation.HIGHER if current.value > previous.value else FactualPivotRelation.LOWER if current.value < previous.value else FactualPivotRelation.EQUAL


def _supportive_pivot(series: FactualPivotSeries, direction: V1Direction) -> PivotCandidate | None:
    values = series.swing_lows if direction is V1Direction.LONG else series.swing_highs
    return values[-1] if values else None


def _opposing_pivot(series: FactualPivotSeries, direction: V1Direction) -> PivotCandidate | None:
    values = series.swing_highs if direction is V1Direction.LONG else series.swing_lows
    return values[-1] if values else None


def _structural_failure(close: float, series: FactualPivotSeries, direction: V1Direction) -> bool:
    pivot = _supportive_pivot(series, direction)
    return pivot is not None and _beyond(close, pivot.value, direction, adverse=True)


def _beyond(value: float, level: float, direction: V1Direction, *, adverse: bool) -> bool:
    if direction is V1Direction.LONG:
        return value < level if adverse else value > level
    return value > level if adverse else value < level


def _opposite(direction: V1Direction) -> V1Direction:
    return V1Direction.SHORT if direction is V1Direction.LONG else V1Direction.LONG


def _reversal_interaction(
    fact: CompletedTimeframeFact,
    sma200: float | None,
    r2: FactualPivotSeries,
    direction: V1Direction,
) -> bool:
    structural = _supportive_pivot(r2, direction)
    levels = tuple(item for item in (sma200, None if structural is None else structural.value) if item is not None)
    return any(
        fact.low <= level <= fact.high
        and (fact.close >= level if direction is V1Direction.LONG else fact.close <= level)
        for level in levels
    )


def _structural_anchor(
    four: CompletedTimeframeFact,
    daily: CompletedTimeframeFact,
    direction: V1Direction,
) -> NativeAnchor | None:
    local = _supportive_pivot(_pivot_series(four, 2), direction)
    daily_pivot = _supportive_pivot(_pivot_series(daily, 2), direction)
    pivot = local or daily_pivot
    if pivot is None:
        return None
    return NativeAnchor(
        NativeAnchorType.FOUR_HOUR_RADIUS_2_STRUCTURE if local is not None else NativeAnchorType.DAILY_RADIUS_2_STRUCTURE,
        pivot.value, pivot.timestamp,
    )


def _hold_anchor(
    four: CompletedTimeframeFact,
    daily: CompletedTimeframeFact,
    direction: V1Direction,
) -> NativeAnchor | None:
    daily_r2 = _supportive_pivot(_pivot_series(daily, 2), direction)
    four_r2 = _supportive_pivot(_pivot_series(four, 2), direction)
    ma = daily.moving_averages
    candidates = (
        None if daily_r2 is None else NativeAnchor(NativeAnchorType.DAILY_RADIUS_2_STRUCTURE, daily_r2.value, daily_r2.timestamp),
        None if ma is None or ma.sma50 is None else NativeAnchor(NativeAnchorType.DAILY_SMA50, ma.sma50, daily.observation_boundary),
        None if ma is None or ma.sma20 is None else NativeAnchor(NativeAnchorType.DAILY_SMA20, ma.sma20, daily.observation_boundary),
        None if four_r2 is None else NativeAnchor(NativeAnchorType.FOUR_HOUR_RADIUS_2_STRUCTURE, four_r2.value, four_r2.timestamp),
    )
    for anchor in candidates:
        if anchor is not None and four.low <= anchor.price <= four.high and not _beyond(four.close, anchor.price, direction, adverse=True):
            return anchor
    return None


def _price_relation(value: float, average: float) -> FactualPriceRelation:
    return FactualPriceRelation.ABOVE if value > average else FactualPriceRelation.BELOW if value < average else FactualPriceRelation.AT


def _levels(
    daily: CompletedTimeframeFact,
    four: CompletedTimeframeFact,
    hour: CompletedTimeframeFact,
    anchor: NativeAnchor | None,
) -> tuple[tuple[str, float], ...]:
    values = []
    for prefix, fact in (("1D", daily), ("4H", four), ("1H", hour)):
        ma = fact.moving_averages
        if ma is not None:
            values.extend((f"{prefix}_{name}", value) for name, value in (("SMA20", ma.sma20), ("SMA50", ma.sma50), ("SMA200", ma.sma200)) if value is not None)
        for series in fact.structural_measurements:
            values.extend((f"{prefix}_R{series.radius}_{pivot.kind.value}", pivot.value) for pivot in (*series.swing_highs[-2:], *series.swing_lows[-2:]))
    if anchor is not None:
        values.append(("OPERATIVE_ANCHOR", anchor.price))
    return tuple(values)


class NativeDiscoveryEvidenceStore:
    """Atomic immutable restart store for Native Discovery runs."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("NATIVE_DISCOVERY_STORE_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, run: NativeDiscoveryRun) -> Path:
        if type(run) is not NativeDiscoveryRun:
            raise ValueError("NATIVE_DISCOVERY_RUN_INVALID")
        path = self._root / "complete-runs" / f"{run.run_identity}.json"
        payload = {"schema": NATIVE_DISCOVERY_SCHEMA, "run": _json_value(asdict(run))}
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("NATIVE_DISCOVERY_RUN_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load(self, run_identity: str) -> NativeDiscoveryRun:
        payload = _read(self._root / "complete-runs" / f"{run_identity}.json")
        return _run(payload.get("run"))

    def latest(self) -> NativeDiscoveryRun | None:
        directory = self._root / "complete-runs"
        if not directory.exists():
            return None
        runs = []
        for path in directory.glob("SWING-RUN-*.json"):
            try:
                runs.append(_run(_read(path).get("run")))
            except ValueError:
                continue
        return max(runs, key=lambda item: item.observed_at, default=None)


def _run(value: object) -> NativeDiscoveryRun:
    if type(value) is not dict:
        raise ValueError("NATIVE_DISCOVERY_RUN_INVALID")
    try:
        run = NativeDiscoveryRun(
            value["run_identity"], value["provider_source_identity"],
            datetime.fromisoformat(value["observed_at"]),
            tuple(_assessment(item) for item in value["assessments"]),
            value["result_sha256"], value["policy_identity"],
            value["policy_version"], value["authority"], value["schema"],
        )
        if any(_assessment_digest(item) != item.result_sha256 for item in run.assessments):
            raise ValueError("NATIVE_DISCOVERY_RESULT_INTEGRITY_FAILED")
        expected = _digest({
            "run_identity": run.run_identity,
            "provider_source_identity": run.provider_source_identity,
            "observed_at": run.observed_at,
            "assessments": run.assessments,
        })
        if expected != run.result_sha256:
            raise ValueError("NATIVE_DISCOVERY_RESULT_INTEGRITY_FAILED")
        return run
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("NATIVE_DISCOVERY_RUN_INVALID") from error


def _assessment(value: object) -> NativeInstrumentDiscovery:
    if type(value) is not dict:
        raise ValueError("NATIVE_DISCOVERY_RUN_INVALID")
    anchor = value["operative_anchor"]
    return NativeInstrumentDiscovery(
        value["run_identity"], value["provider_source_identity"],
        value["canonical_instrument"], NativeProductPath(value["product_path"]),
        V1Direction(value["direction"]), Native1WState(value["weekly_state"]),
        Native1DState(value["daily_state"]), Native4HState(value["four_hour_state"]),
        Native1HState(value["one_hour_state"]), NativeDiscoveryStatus(value["status"]),
        None if value["context_kind"] is None else NativeContextKind(value["context_kind"]),
        None if value["opportunity_identity"] is None else NativeOpportunityIdentity(value["opportunity_identity"]),
        None if anchor is None else NativeAnchor(NativeAnchorType(anchor["anchor_type"]), anchor["price"], datetime.fromisoformat(anchor["source_boundary"])),
        tuple((name, number) for name, number in value["factual_levels"]),
        tuple((name, datetime.fromisoformat(boundary)) for name, boundary in value["factual_boundaries"]),
        tuple((name, current, mean) for name, current, mean in value["volume_facts"]),
        tuple(value["provider_provenance"]), tuple(value["calendar_provenance"]),
        tuple(value["reason_codes"]),
        tuple(value.get("daily_control_probable_identities", ())),
        value["predecessor_result_sha256"],
        value["result_sha256"], value["policy_identity"], value["policy_version"], value["authority"],
    )


def _assessment_digest(value: NativeInstrumentDiscovery) -> str:
    fields = asdict(value)
    for name in (
        "result_sha256", "policy_identity", "policy_version", "authority",
    ):
        fields.pop(name)
    return _digest(fields)


def _digest(value: object) -> str:
    return sha256(json.dumps(_json_value(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _json_value(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return _json_value(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def _read(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("NATIVE_DISCOVERY_RUN_UNAVAILABLE") from error
    if type(payload) is not dict or set(payload) != {"schema", "run"} or payload["schema"] != NATIVE_DISCOVERY_SCHEMA:
        raise ValueError("NATIVE_DISCOVERY_RUN_INVALID")
    return payload


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "DEFAULT_NATIVE_DISCOVERY_EVIDENCE_ROOT", "NATIVE_DISCOVERY_AUTHORITY",
    "NATIVE_DISCOVERY_POLICY_ID", "NATIVE_DISCOVERY_POLICY_VERSION",
    "Native1DState", "Native1HState", "Native1WState", "Native4HState",
    "NativeAnchor", "NativeAnchorType", "NativeContextKind",
    "NativeDiscoveryEvidenceStore", "NativeDiscoveryRun", "NativeDiscoveryStatus",
    "NativeInstrumentDiscovery", "NativeOpportunityIdentity", "NativeProductPath",
    "classify_native_daily", "classify_native_four_hour",
    "classify_native_one_hour", "classify_native_weekly", "discover_native_mtf",
]
