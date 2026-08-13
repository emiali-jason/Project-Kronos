"""Deterministic Swing V1 model-trade construction.

This module owns model geometry only.  It does not rank, size, approve,
execute, or monitor trades and it has no OpenAI, Pine, Sponsor, or broker
geometry authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from kronos.application.swing_v1_review import (
    STEP31_V1_HANDOFF_SCHEMA_ID,
    Step31EligibilityHandoff,
    Step31EligibleInstrument,
)
from kronos.swing.v1.chart_analyst_v2_layer2 import (
    CHART_ANALYST_V2_OPERATIONAL_AUTHORITY,
    ChartAnalystV2Layer2State,
)
from kronos.swing.v1.layer2 import ReadinessState
from kronos.swing.v1.models import V1Direction, V1Setup


TRADE_CONSTRUCTION_ENGINE_ID = "SWING-V1-TRADE-CONSTRUCTION"
TRADE_CANDIDATE_CONTRACT_ID = "KRONOS-SWING-V1-TRADE-CANDIDATE-V1"
TRADE_CANDIDATE_CONTRACT_VERSION = "1"
TRADE_CONSTRUCTION_POLICY_ID = "SWING-V1-TRADE-CONSTRUCTION-POLICY"
TRADE_CONSTRUCTION_POLICY_VERSION = "1"
DOMAIN_007_HANDOFF_ID = "KRONOS-SWING-V1-DOMAIN-007-RISK-HANDOFF-V1"
_SUPPORTED_PRODUCTS = {
    "NSE_CASH_EQUITY",
    "NSE_INDEX",
    "NSE_FUTURE",
    "MCX_FUTURE",
}


class TradeConstructionStatus(StrEnum):
    COMPLETE = "TRADE_CONSTRUCTION_COMPLETE"
    INCOMPLETE = "TRADE_CONSTRUCTION_INCOMPLETE"


class TradeViabilityStatus(StrEnum):
    VIABLE = "VIABLE"
    NOT_VIABLE = "NOT_VIABLE"


class TradeCandidateEntryState(StrEnum):
    WAITING = "TRADE_CANDIDATE_WAITING_FOR_ENTRY"
    TRIGGERED = "ENTRY_TRIGGERED"
    RECONSTRUCTION_REQUIRED = "TRADE_CANDIDATE_RECONSTRUCTION_REQUIRED"


class TradeCandidateStaleness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"


class TradeCandidateIntegrity(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"


class MaterialBarrierStatus(StrEnum):
    CLEAR_AIR = "CLEAR_AIR"
    TARGET_TRUNCATED = "TARGET_TRUNCATED"
    DESTROYS_POSITIVE_REWARD = "DESTROYS_POSITIVE_REWARD"


@dataclass(frozen=True, slots=True)
class TradeConstructionExecutionContext:
    """Provider-neutral market facts; never an execution authorization."""

    identity: str
    canonical_instrument: str
    product: str
    tick_size: Decimal
    price_precision: int
    session_calendar_identity: str
    market_available: bool

    def __post_init__(self) -> None:
        tick = _decimal(self.tick_size)
        if (
            not _identity(self.identity)
            or not self.canonical_instrument
            or not self.product
            or not _positive(tick)
            or type(self.price_precision) is not int
            or self.price_precision < 0
            or _decimal_places(tick) > self.price_precision
            or not self.session_calendar_identity
            or type(self.market_available) is not bool
        ):
            raise ValueError("TRADE_CONSTRUCTION_EXECUTION_CONTEXT_INVALID")
        object.__setattr__(self, "tick_size", tick)


@dataclass(frozen=True, slots=True)
class MaterialBarrier:
    evidence_identity: str
    price: Decimal

    def __post_init__(self) -> None:
        price = _decimal(self.price)
        if not _identity(self.evidence_identity) or not _positive(price):
            raise ValueError("TRADE_CONSTRUCTION_BARRIER_INVALID")
        object.__setattr__(self, "price", price)


@dataclass(frozen=True, slots=True)
class TradeConstructionInput:
    """Bound evidence required to construct one supported child thesis."""

    handoff: Step31EligibilityHandoff
    eligibility: Step31EligibleInstrument
    layer1_assessment_identity: str
    setup_family: V1Setup | str
    direction: V1Direction | str
    layer2_state_identity: str
    readiness_identity: str
    qualification_observation_boundary: datetime
    active_chart_revision_identity: str
    qualification_high: Decimal | None
    qualification_low: Decimal | None
    pullback_structural_low: Decimal | None = None
    pullback_structural_high: Decimal | None = None
    prior_directional_swing_high: Decimal | None = None
    prior_directional_swing_low: Decimal | None = None
    original_range_high: Decimal | None = None
    original_range_low: Decimal | None = None
    clear_air_identity: str = ""
    material_barriers: tuple[MaterialBarrier, ...] = ()
    execution_context: TradeConstructionExecutionContext | None = None
    source_evidence_identities: tuple[str, ...] = ()
    market_data_boundary: datetime | None = None
    qualification_candle_completed: bool = True

    def __post_init__(self) -> None:
        for name in (
            "qualification_high",
            "qualification_low",
            "pullback_structural_low",
            "pullback_structural_high",
            "prior_directional_swing_high",
            "prior_directional_swing_low",
            "original_range_high",
            "original_range_low",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(value))
        if self.market_data_boundary is None:
            object.__setattr__(
                self, "market_data_boundary", self.qualification_observation_boundary
            )


@dataclass(frozen=True, slots=True)
class SwingV1TradeCandidate:
    contract_identity: str
    contract_version: str
    run_id: str
    candidate_id: str
    canonical_instrument: str
    product: str
    execution_context_identity: str
    setup_identity: str
    setup_family: str
    direction: str
    layer1_assessment_identity: str
    layer2_state_identity: str
    readiness_identity: str
    qualification_observation_boundary: datetime
    active_chart_revision_identity: str
    entry_price: Decimal | None
    entry_condition: str
    entry_state: TradeCandidateEntryState
    stop_price: Decimal | None
    stop_basis: str
    invalidation_level_or_reference: Decimal | None
    invalidation_condition: str
    target_price: Decimal | None
    target_basis: str
    risk_per_unit: Decimal | None
    reward_per_unit: Decimal | None
    risk_reward_ratio: Decimal | None
    clear_air_identity: str
    material_barrier_status: MaterialBarrierStatus
    barrier_references: tuple[str, ...]
    construction_status: TradeConstructionStatus
    viability_status: TradeViabilityStatus
    trade_construction_policy_identity: str
    trade_construction_policy_version: str
    source_evidence_identities: tuple[str, ...]
    market_data_boundary: datetime
    construction_timestamp: datetime
    tick_size: Decimal | None
    price_precision: int | None
    provenance: tuple[str, ...]
    integrity_status: TradeCandidateIntegrity
    integrity_reason: str
    staleness_status: TradeCandidateStaleness

    def __post_init__(self) -> None:
        complete = self.construction_status is TradeConstructionStatus.COMPLETE
        geometry = (
            self.entry_price,
            self.stop_price,
            self.invalidation_level_or_reference,
            self.target_price,
            self.risk_per_unit,
            self.reward_per_unit,
            self.risk_reward_ratio,
        )
        if (
            self.contract_identity != TRADE_CANDIDATE_CONTRACT_ID
            or self.contract_version != TRADE_CANDIDATE_CONTRACT_VERSION
            or not _identity(self.run_id)
            or not _identity(self.candidate_id)
            or not self.canonical_instrument
            or not _aware(self.qualification_observation_boundary)
            or not _aware(self.market_data_boundary)
            or not _aware(self.construction_timestamp)
            or type(self.entry_state) is not TradeCandidateEntryState
            or type(self.material_barrier_status) is not MaterialBarrierStatus
            or type(self.construction_status) is not TradeConstructionStatus
            or type(self.viability_status) is not TradeViabilityStatus
            or type(self.integrity_status) is not TradeCandidateIntegrity
            or type(self.staleness_status) is not TradeCandidateStaleness
            or type(self.barrier_references) is not tuple
            or type(self.source_evidence_identities) is not tuple
            or type(self.provenance) is not tuple
            or self.trade_construction_policy_identity
            != TRADE_CONSTRUCTION_POLICY_ID
            or self.trade_construction_policy_version
            != TRADE_CONSTRUCTION_POLICY_VERSION
            or (complete and any(value is None for value in geometry))
            or (
                complete
                and (
                    self.viability_status is not TradeViabilityStatus.VIABLE
                    or self.integrity_status is not TradeCandidateIntegrity.VALID
                    or self.staleness_status is not TradeCandidateStaleness.CURRENT
                    or self.entry_state is not TradeCandidateEntryState.WAITING
                )
            )
        ):
            raise ValueError("SWING_V1_TRADE_CANDIDATE_INVALID")


@dataclass(frozen=True, slots=True)
class Domain007RiskHandoff:
    handoff_identity: str
    candidate_id: str
    run_id: str
    canonical_instrument: str
    direction: str
    entry_price: Decimal
    stop_price: Decimal
    invalidation_level_or_reference: Decimal
    target_price: Decimal
    setup_family: str
    observation_boundary: datetime
    integrity_status: TradeCandidateIntegrity


@dataclass(frozen=True, slots=True)
class PreEntryObservation:
    run_id: str
    active_chart_revision_identity: str
    observation_boundary: datetime
    layer1_assessment_identity: str
    direction: V1Direction
    readiness_state: ReadinessState
    execution_context_identity: str
    completed_close: Decimal | None
    observed_high: Decimal
    observed_low: Decimal
    candidate_armed: bool


@dataclass(frozen=True, slots=True)
class TradeCandidateLifecycleAssessment:
    candidate_id: str
    entry_state: TradeCandidateEntryState
    staleness_status: TradeCandidateStaleness
    reason: str


def construct_trade_candidate(
    item: TradeConstructionInput,
    *,
    clock: datetime | None = None,
) -> SwingV1TradeCandidate:
    """Construct one candidate or return a fail-closed incomplete record."""

    timestamp = clock or datetime.now(UTC)
    reason = _validate_binding(item)
    setup = _setup(item.setup_family)
    direction = _direction(item.direction)
    context = item.execution_context
    entry = stop = invalidation = native_target = None
    entry_basis = stop_basis = invalidation_condition = target_basis = "UNAVAILABLE"
    barrier_status = MaterialBarrierStatus.CLEAR_AIR
    barrier_references: tuple[str, ...] = ()

    if reason is None:
        try:
            assert setup is not None and direction is not None and context is not None
            entry, entry_basis = _entry(item, setup, direction, context)
            stop, stop_basis, invalidation, invalidation_condition = _stop_invalidation(
                item, setup, direction, context
            )
            native_target, target_basis = _target(item, setup, direction, context)
            target, barrier_status, barrier_references = _constrain_target(
                entry, native_target, item.material_barriers, direction, context
            )
            if barrier_status is MaterialBarrierStatus.DESTROYS_POSITIVE_REWARD:
                raise ValueError("MATERIAL_BARRIER_DESTROYS_POSITIVE_REWARD")
            risk, reward = _risk_reward(entry, stop, target, direction)
            ratio = reward / risk
            if not _positive(ratio):
                raise ValueError("RISK_REWARD_INVALID")
        except (AssertionError, InvalidOperation, ValueError) as exc:
            reason = str(exc) or type(exc).__name__
            target = native_target
            risk = reward = ratio = None
    else:
        target = native_target
        risk = reward = ratio = None

    complete = reason is None
    setup_value = setup.value if setup is not None else str(item.setup_family)
    direction_value = direction.value if direction is not None else str(item.direction)
    product = context.product if context is not None else "UNAVAILABLE"
    context_id = context.identity if context is not None else "UNAVAILABLE"
    tick = context.tick_size if context is not None else None
    precision = context.price_precision if context is not None else None
    identity_material = "|".join((
        item.handoff.swing_analysis_run_identity,
        item.eligibility.canonical_instrument,
        item.layer1_assessment_identity,
        item.active_chart_revision_identity,
        item.qualification_observation_boundary.isoformat(),
        TRADE_CONSTRUCTION_POLICY_VERSION,
    ))
    candidate_id = f"SWING-V1-TRADE-CANDIDATE-{sha256(identity_material.encode()).hexdigest()}"
    return SwingV1TradeCandidate(
        contract_identity=TRADE_CANDIDATE_CONTRACT_ID,
        contract_version=TRADE_CANDIDATE_CONTRACT_VERSION,
        run_id=item.handoff.swing_analysis_run_identity,
        candidate_id=candidate_id,
        canonical_instrument=item.eligibility.canonical_instrument,
        product=product,
        execution_context_identity=context_id,
        setup_identity=item.layer1_assessment_identity,
        setup_family=setup_value,
        direction=direction_value,
        layer1_assessment_identity=item.layer1_assessment_identity,
        layer2_state_identity=item.layer2_state_identity,
        readiness_identity=item.readiness_identity,
        qualification_observation_boundary=item.qualification_observation_boundary,
        active_chart_revision_identity=item.active_chart_revision_identity,
        entry_price=entry,
        entry_condition=entry_basis,
        entry_state=(
            TradeCandidateEntryState.WAITING
            if complete
            else TradeCandidateEntryState.RECONSTRUCTION_REQUIRED
        ),
        stop_price=stop,
        stop_basis=stop_basis,
        invalidation_level_or_reference=invalidation,
        invalidation_condition=invalidation_condition,
        target_price=target,
        target_basis=target_basis,
        risk_per_unit=risk,
        reward_per_unit=reward,
        risk_reward_ratio=ratio,
        clear_air_identity=item.clear_air_identity,
        material_barrier_status=barrier_status,
        barrier_references=barrier_references,
        construction_status=(
            TradeConstructionStatus.COMPLETE if complete
            else TradeConstructionStatus.INCOMPLETE
        ),
        viability_status=(
            TradeViabilityStatus.VIABLE if complete else TradeViabilityStatus.NOT_VIABLE
        ),
        trade_construction_policy_identity=TRADE_CONSTRUCTION_POLICY_ID,
        trade_construction_policy_version=TRADE_CONSTRUCTION_POLICY_VERSION,
        source_evidence_identities=item.source_evidence_identities,
        market_data_boundary=item.market_data_boundary
        or item.qualification_observation_boundary,
        construction_timestamp=timestamp,
        tick_size=tick,
        price_precision=precision,
        provenance=(
            STEP31_V1_HANDOFF_SCHEMA_ID,
            item.handoff.operational_authority,
            item.eligibility.layer1_run_identity,
            item.eligibility.source_image_sha256,
            context_id,
        ),
        integrity_status=(
            TradeCandidateIntegrity.VALID if complete else TradeCandidateIntegrity.INVALID
        ),
        integrity_reason="VALID" if complete else _safe_reason(reason),
        staleness_status=(
            TradeCandidateStaleness.CURRENT if complete else TradeCandidateStaleness.STALE
        ),
    )


def construct_all_trade_candidates(
    handoff: Step31EligibilityHandoff,
    inputs: tuple[TradeConstructionInput, ...],
    *,
    clock: datetime | None = None,
) -> tuple[SwingV1TradeCandidate, ...]:
    """Construct every eligible child thesis independently, without ranking."""

    if type(handoff) is not Step31EligibilityHandoff or handoff.schema_identity != STEP31_V1_HANDOFF_SCHEMA_ID:
        raise ValueError("TRADE_CONSTRUCTION_HANDOFF_INVALID")
    if any(item.handoff != handoff for item in inputs):
        raise ValueError("TRADE_CONSTRUCTION_HANDOFF_BINDING_MISMATCH")
    identities = tuple(item.layer1_assessment_identity for item in inputs)
    expected = tuple(
        identity
        for eligible in handoff.eligible_instruments
        for identity in eligible.probable_assessment_identities
    )
    if len(set(identities)) != len(identities):
        raise ValueError("TRADE_CONSTRUCTION_DUPLICATE_ACTIVE_CANDIDATE")
    if set(identities) != set(expected):
        raise ValueError("TRADE_CONSTRUCTION_ELIGIBLE_POPULATION_MISMATCH")
    return tuple(construct_trade_candidate(item, clock=clock) for item in inputs)


def domain_007_handoff(candidate: SwingV1TradeCandidate) -> Domain007RiskHandoff:
    if (
        candidate.construction_status is not TradeConstructionStatus.COMPLETE
        or candidate.viability_status is not TradeViabilityStatus.VIABLE
        or candidate.integrity_status is not TradeCandidateIntegrity.VALID
        or candidate.staleness_status is not TradeCandidateStaleness.CURRENT
        or any(value is None for value in (
            candidate.entry_price,
            candidate.stop_price,
            candidate.invalidation_level_or_reference,
            candidate.target_price,
        ))
    ):
        raise ValueError("DOMAIN_007_HANDOFF_INELIGIBLE")
    assert candidate.entry_price is not None
    assert candidate.stop_price is not None
    assert candidate.invalidation_level_or_reference is not None
    assert candidate.target_price is not None
    return Domain007RiskHandoff(
        DOMAIN_007_HANDOFF_ID,
        candidate.candidate_id,
        candidate.run_id,
        candidate.canonical_instrument,
        candidate.direction,
        candidate.entry_price,
        candidate.stop_price,
        candidate.invalidation_level_or_reference,
        candidate.target_price,
        candidate.setup_family,
        candidate.market_data_boundary,
        candidate.integrity_status,
    )


def assess_pre_entry(
    candidate: SwingV1TradeCandidate,
    observation: PreEntryObservation,
) -> TradeCandidateLifecycleAssessment:
    """Evaluate state without mutating canonical candidate geometry."""

    stale_reason = _staleness_reason(candidate, observation)
    if stale_reason is not None:
        return TradeCandidateLifecycleAssessment(
            candidate.candidate_id,
            TradeCandidateEntryState.RECONSTRUCTION_REQUIRED,
            TradeCandidateStaleness.STALE,
            stale_reason,
        )
    assert candidate.entry_price is not None
    triggered = (
        observation.observed_high >= candidate.entry_price
        if candidate.direction == V1Direction.LONG.value
        else observation.observed_low <= candidate.entry_price
    )
    if triggered and not observation.candidate_armed:
        return TradeCandidateLifecycleAssessment(
            candidate.candidate_id,
            TradeCandidateEntryState.RECONSTRUCTION_REQUIRED,
            TradeCandidateStaleness.STALE,
            "ENTRY_TRADED_THROUGH_BEFORE_ARMED",
        )
    return TradeCandidateLifecycleAssessment(
        candidate.candidate_id,
        TradeCandidateEntryState.TRIGGERED if triggered
        else TradeCandidateEntryState.WAITING,
        TradeCandidateStaleness.CURRENT,
        "ENTRY_TRIGGER_OBSERVED" if triggered else "ENTRY_NOT_TRIGGERED",
    )


class LocalTradeCandidateStore:
    """Append-only local store for restart recovery and audit reconstruction."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute() or root in {Path("/"), Path("/private/tmp")}:
            raise ValueError("TRADE_CANDIDATE_STORE_ROOT_INVALID")
        self._root = root

    def retain(self, candidate: SwingV1TradeCandidate) -> Path:
        payload = _candidate_payload(candidate)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        path = self._root / candidate.run_id / f"{candidate.candidate_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists():
            if path.read_text(encoding="utf-8") != encoded:
                raise ValueError("TRADE_CANDIDATE_IMMUTABLE_CONFLICT")
            return path
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(encoded, encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return path

    def load(self, run_id: str, candidate_id: str) -> SwingV1TradeCandidate:
        path = self._root / run_id / f"{candidate_id}.json"
        return _candidate_from_payload(json.loads(path.read_text(encoding="utf-8")))


def audit_reconstructs(
    candidate: SwingV1TradeCandidate,
    source: TradeConstructionInput,
) -> bool:
    return construct_trade_candidate(
        source, clock=candidate.construction_timestamp
    ) == candidate


def _validate_binding(item: TradeConstructionInput) -> str | None:
    handoff = item.handoff
    eligible = item.eligibility
    context = item.execution_context
    setup = _setup(item.setup_family)
    direction = _direction(item.direction)
    if type(handoff) is not Step31EligibilityHandoff:
        return "STEP31_HANDOFF_MISSING"
    if handoff.schema_identity != STEP31_V1_HANDOFF_SCHEMA_ID:
        return "STEP31_HANDOFF_SCHEMA_INVALID"
    if handoff.operational_authority != CHART_ANALYST_V2_OPERATIONAL_AUTHORITY:
        return "OPERATIONAL_AUTHORITY_INVALID"
    if eligible not in handoff.eligible_instruments:
        return "STEP31_ELIGIBILITY_BINDING_MISMATCH"
    if setup is None:
        return "SETUP_UNSUPPORTED_OR_AMBIGUOUS"
    if direction is None:
        return "DIRECTION_INVALID"
    expected_identity = "|".join((
        eligible.canonical_instrument,
        setup.value,
        direction.value,
        eligible.observation_boundary.isoformat(),
    ))
    if (
        item.layer1_assessment_identity != expected_identity
        or item.layer1_assessment_identity
        not in eligible.probable_assessment_identities
    ):
        return "LAYER1_ASSESSMENT_IDENTITY_MISMATCH"
    if item.layer2_state_identity != ChartAnalystV2Layer2State.SHADOW_COMPLETE.value:
        return "LAYER2_STATE_INVALID"
    if (
        eligible.readiness_state is not ReadinessState.READY_FOR_TRADE_CONSTRUCTION
        or item.readiness_identity != eligible.readiness_policy_identity
    ):
        return "READINESS_NO_LONGER_VALID"
    if item.active_chart_revision_identity != eligible.source_image_sha256:
        return "ACTIVE_CHART_REVISION_MISMATCH"
    if (
        item.qualification_observation_boundary != eligible.observation_boundary
        or item.market_data_boundary != eligible.observation_boundary
        or not item.qualification_candle_completed
    ):
        return "COMPLETED_DAILY_BOUNDARY_INVALID"
    if not item.clear_air_identity:
        return "CLEAR_AIR_EVIDENCE_MISSING"
    if not item.source_evidence_identities:
        return "SOURCE_EVIDENCE_MISSING"
    if context is None:
        return "EXECUTION_CONTEXT_MISSING"
    if (
        context.canonical_instrument != eligible.canonical_instrument
        or context.product not in _SUPPORTED_PRODUCTS
        or not context.market_available
    ):
        return "EXECUTION_CONTEXT_INCONSISTENT"
    if (
        type(item.material_barriers) is not tuple
        or any(type(barrier) is not MaterialBarrier for barrier in item.material_barriers)
        or len({barrier.evidence_identity for barrier in item.material_barriers})
        != len(item.material_barriers)
    ):
        return "MATERIAL_BARRIER_EVIDENCE_INVALID"
    if (
        type(item.source_evidence_identities) is not tuple
        or any(not _identity(identity) for identity in item.source_evidence_identities)
        or len(set(item.source_evidence_identities))
        != len(item.source_evidence_identities)
    ):
        return "SOURCE_EVIDENCE_INVALID"
    return None


def _entry(item, setup, direction, context):  # type: ignore[no-untyped-def]
    raw = item.qualification_high if direction is V1Direction.LONG else item.qualification_low
    if not _positive(raw):
        raise ValueError("ENTRY_MISSING")
    return (
        _round_tick(raw, context, up=direction is V1Direction.LONG),
        "COMPLETED_DIRECTIONAL_QUALIFICATION_CANDLE_HIGH"
        if direction is V1Direction.LONG
        else "COMPLETED_DIRECTIONAL_QUALIFICATION_CANDLE_LOW",
    )


def _stop_invalidation(item, setup, direction, context):  # type: ignore[no-untyped-def]
    if setup is V1Setup.PULLBACK_CONTINUATION:
        raw = item.pullback_structural_low if direction is V1Direction.LONG else item.pullback_structural_high
        basis = "QUALIFIED_PULLBACK_LOWEST_STRUCTURAL_LOW" if direction is V1Direction.LONG else "QUALIFIED_PULLBACK_HIGHEST_STRUCTURAL_HIGH"
        condition = "COMPLETED_DAILY_CLOSE_BELOW_PULLBACK_STRUCTURAL_LOW" if direction is V1Direction.LONG else "COMPLETED_DAILY_CLOSE_ABOVE_PULLBACK_STRUCTURAL_HIGH"
    else:
        raw = item.qualification_low if direction is V1Direction.LONG else item.qualification_high
        basis = "BREAKOUT_QUALIFICATION_CANDLE_LOW" if direction is V1Direction.LONG else "BREAKDOWN_QUALIFICATION_CANDLE_HIGH"
        raw_invalidation = item.original_range_high if direction is V1Direction.LONG else item.original_range_low
        if not _positive(raw_invalidation):
            raise ValueError("INVALIDATION_MISSING")
        condition = "COMPLETED_DAILY_CLOSE_AT_OR_BELOW_ORIGINAL_RANGE_HIGH" if direction is V1Direction.LONG else "COMPLETED_DAILY_CLOSE_AT_OR_ABOVE_ORIGINAL_RANGE_LOW"
    if not _positive(raw):
        raise ValueError("STOP_OR_STRUCTURAL_EVIDENCE_MISSING")
    stop = _round_tick(raw, context, up=direction is V1Direction.SHORT)
    invalidation = (
        _decimal(raw)
        if setup is V1Setup.PULLBACK_CONTINUATION
        else _decimal(raw_invalidation)
    )
    return stop, basis, invalidation, condition


def _target(item, setup, direction, context):  # type: ignore[no-untyped-def]
    if setup is V1Setup.PULLBACK_CONTINUATION:
        raw = item.prior_directional_swing_high if direction is V1Direction.LONG else item.prior_directional_swing_low
        basis = "PRIOR_DIRECTIONAL_SWING_HIGH" if direction is V1Direction.LONG else "PRIOR_DIRECTIONAL_SWING_LOW"
    else:
        high, low = item.original_range_high, item.original_range_low
        if not _positive(high) or not _positive(low) or high <= low:
            raise ValueError("ORIGINAL_RANGE_INVALID")
        width = high - low
        raw = high + width if direction is V1Direction.LONG else low - width
        basis = "ORIGINAL_RANGE_MEASURED_TARGET"
    if not _positive(raw):
        raise ValueError("TARGET_MISSING")
    return _round_tick(raw, context, up=direction is V1Direction.SHORT), basis


def _constrain_target(entry, native, barriers, direction, context):  # type: ignore[no-untyped-def]
    relevant = tuple(
        barrier for barrier in barriers
        if (entry < barrier.price < native if direction is V1Direction.LONG else native < barrier.price < entry)
    )
    if not relevant:
        return native, MaterialBarrierStatus.CLEAR_AIR, ()
    nearest = min(relevant, key=lambda item: abs(item.price - entry))
    target = _round_tick(nearest.price, context, up=direction is V1Direction.SHORT)
    reward = target - entry if direction is V1Direction.LONG else entry - target
    refs = tuple(item.evidence_identity for item in relevant)
    if not _positive(reward):
        return target, MaterialBarrierStatus.DESTROYS_POSITIVE_REWARD, refs
    return target, MaterialBarrierStatus.TARGET_TRUNCATED, refs


def _risk_reward(entry, stop, target, direction):  # type: ignore[no-untyped-def]
    risk = entry - stop if direction is V1Direction.LONG else stop - entry
    reward = target - entry if direction is V1Direction.LONG else entry - target
    if not _positive(risk):
        raise ValueError("STOP_WRONG_SIDE_OR_RISK_NON_POSITIVE")
    if not _positive(reward):
        raise ValueError("TARGET_WRONG_SIDE_OR_REWARD_NON_POSITIVE")
    return risk, reward


def _staleness_reason(candidate, observed):  # type: ignore[no-untyped-def]
    if candidate.construction_status is not TradeConstructionStatus.COMPLETE:
        return "CANDIDATE_INCOMPLETE"
    checks = (
        (observed.run_id != candidate.run_id, "UPSTREAM_RUN_CHANGED"),
        (observed.active_chart_revision_identity != candidate.active_chart_revision_identity, "CHART_REVISION_SUPERSEDED"),
        (observed.observation_boundary != candidate.market_data_boundary, "COMPLETED_DAILY_BOUNDARY_SUPERSEDED"),
        (observed.layer1_assessment_identity != candidate.layer1_assessment_identity, "SETUP_BINDING_CHANGED"),
        (observed.direction.value != candidate.direction, "DIRECTION_CHANGED"),
        (observed.readiness_state is not ReadinessState.READY_FOR_TRADE_CONSTRUCTION, "READINESS_CHANGED"),
        (observed.execution_context_identity != candidate.execution_context_identity, "EXECUTION_CONTEXT_CHANGED"),
    )
    for failed, reason in checks:
        if failed:
            return reason
    assert candidate.stop_price is not None and candidate.target_price is not None
    close = observed.completed_close
    invalidated = close is not None and (
        close < candidate.invalidation_level_or_reference
        if candidate.invalidation_condition.endswith("BELOW_PULLBACK_STRUCTURAL_LOW")
        else close > candidate.invalidation_level_or_reference
        if candidate.invalidation_condition.endswith("ABOVE_PULLBACK_STRUCTURAL_HIGH")
        else close <= candidate.invalidation_level_or_reference
        if candidate.direction == V1Direction.LONG.value
        else close >= candidate.invalidation_level_or_reference
    )
    if invalidated:
        return "ANALYTICAL_INVALIDATION_OCCURRED"
    if candidate.direction == V1Direction.LONG.value:
        if observed.observed_high >= candidate.target_price:
            return "TARGET_REACHED_BEFORE_ENTRY"
        if observed.observed_low <= candidate.stop_price:
            return "STOP_SIDE_CROSSED_BEFORE_ENTRY"
    else:
        if observed.observed_low <= candidate.target_price:
            return "TARGET_REACHED_BEFORE_ENTRY"
        if observed.observed_high >= candidate.stop_price:
            return "STOP_SIDE_CROSSED_BEFORE_ENTRY"
    return None


def _round_tick(value: Decimal, context: TradeConstructionExecutionContext, *, up: bool) -> Decimal:
    value = _decimal(value)
    units = value / context.tick_size
    rounded = units.to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR) * context.tick_size
    quantum = Decimal(1).scaleb(-context.price_precision)
    result = rounded.quantize(quantum)
    if not _positive(result):
        raise ValueError("PRICE_UNROUNDABLE")
    return result


def _setup(value: V1Setup | str) -> V1Setup | None:
    try:
        return value if type(value) is V1Setup else V1Setup(value)
    except ValueError:
        return None


def _direction(value: V1Direction | str) -> V1Direction | None:
    try:
        result = value if type(value) is V1Direction else V1Direction(value)
    except ValueError:
        return None
    return result if result in {V1Direction.LONG, V1Direction.SHORT} else None


def _decimal(value: object) -> Decimal:
    try:
        result = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("DECIMAL_VALUE_INVALID") from exc
    if not result.is_finite():
        raise ValueError("DECIMAL_VALUE_INVALID")
    return result


def _positive(value: object) -> bool:
    try:
        return _decimal(value) > 0
    except ValueError:
        return False


def _decimal_places(value: Decimal) -> int:
    return max(0, -value.normalize().as_tuple().exponent)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _identity(value: object) -> bool:
    return type(value) is str and bool(value) and re.fullmatch(r"[A-Za-z0-9_.:@|+/-]{1,512}", value) is not None


def _safe_reason(value: object) -> str:
    text = str(value or "TRADE_CONSTRUCTION_INVALID")
    return text if re.fullmatch(r"[A-Z0-9_]+", text) else "TRADE_CONSTRUCTION_INVALID"


def _candidate_payload(candidate: SwingV1TradeCandidate) -> dict[str, object]:
    payload = asdict(candidate)
    for key, value in tuple(payload.items()):
        if isinstance(value, (StrEnum, Decimal, datetime)):
            payload[key] = value.value if isinstance(value, StrEnum) else str(value) if isinstance(value, Decimal) else value.isoformat()
    payload["barrier_references"] = list(candidate.barrier_references)
    payload["source_evidence_identities"] = list(candidate.source_evidence_identities)
    payload["provenance"] = list(candidate.provenance)
    return payload


def _candidate_from_payload(payload: dict[str, object]) -> SwingV1TradeCandidate:
    decimal_fields = {
        "entry_price", "stop_price", "invalidation_level_or_reference",
        "target_price", "risk_per_unit", "reward_per_unit", "risk_reward_ratio",
        "tick_size",
    }
    for key in decimal_fields:
        if payload.get(key) is not None:
            payload[key] = Decimal(str(payload[key]))
    for key in ("qualification_observation_boundary", "market_data_boundary", "construction_timestamp"):
        payload[key] = datetime.fromisoformat(str(payload[key]))
    payload["entry_state"] = TradeCandidateEntryState(str(payload["entry_state"]))
    payload["material_barrier_status"] = MaterialBarrierStatus(str(payload["material_barrier_status"]))
    payload["construction_status"] = TradeConstructionStatus(str(payload["construction_status"]))
    payload["viability_status"] = TradeViabilityStatus(str(payload["viability_status"]))
    payload["integrity_status"] = TradeCandidateIntegrity(str(payload["integrity_status"]))
    payload["staleness_status"] = TradeCandidateStaleness(str(payload["staleness_status"]))
    for key in ("barrier_references", "source_evidence_identities", "provenance"):
        payload[key] = tuple(payload[key])
    return SwingV1TradeCandidate(**payload)  # type: ignore[arg-type]
