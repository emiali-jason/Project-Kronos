"""Frozen Step-31 Native trade construction from governed evidence only."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock

from kronos.instrument.facts import CanonicalInstrumentContext, InstrumentContextStatus
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.kr370_step31_handoff import Kr370Step31EligibilityHandoff
from kronos.swing.v1.native_discovery import NativeOpportunityIdentity
from kronos.swing.v1.native_readiness import NativeLayer2ReadinessRecord, NativeReadinessState
from kronos.swing.v1.native_review import NativeReviewRequirement


TRADE_CONSTRUCTION_POLICY_ID_V0 = "SWING-V1-TRADE-CONSTRUCTION-V0"
TRADE_CONSTRUCTION_POLICY_VERSION_V0 = "0"
TRADE_PLAN_CONTRACT_ID_V0 = "KRONOS-SWING-V1-TRADE-PLAN-RECORD-V0"
TRADE_PLAN_CONTRACT_VERSION_V0 = "0"
TRADE_PLAN_SCHEMA_V0 = "KRONOS-SWING-V1-TRADE-PLAN-STORE-V0"

TRADE_CONSTRUCTION_POLICY_ID = "SWING-V1-TRADE-CONSTRUCTION-V1"
TRADE_CONSTRUCTION_POLICY_VERSION = "1.0"
TRADE_CONSTRUCTION_POLICY_STATUS = "FROZEN"
TRADE_PLAN_CONTRACT_ID = "KRONOS-SWING-V1-TRADE-PLAN-RECORD-V1"
TRADE_PLAN_CONTRACT_VERSION = "1"
TRADE_PLAN_SCHEMA = "KRONOS-SWING-V1-TRADE-PLAN-STORE-V1"
TRADE_PLAN_AUTHORITY = "MODEL_TRADE_GEOMETRY_ONLY_NO_SPONSOR_OR_EXECUTION_AUTHORITY"


class TradeSetupIdentity(StrEnum):
    PULLBACK_CONTINUATION = "PULLBACK_CONTINUATION"
    CONSOLIDATION_BREAKOUT = "CONSOLIDATION_BREAKOUT"


class TradePlanStatus(StrEnum):
    TRADE_PLAN_READY = "TRADE_PLAN_READY"
    TRADE_PLAN_UNAVAILABLE = "TRADE_PLAN_UNAVAILABLE"


class TradePlanUnavailableReason(StrEnum):
    ENTRY_AUTHORITY_UNAVAILABLE = "ENTRY_AUTHORITY_UNAVAILABLE"
    STOP_AUTHORITY_UNAVAILABLE = "STOP_AUTHORITY_UNAVAILABLE"
    INVALIDATION_AUTHORITY_UNAVAILABLE = "INVALIDATION_AUTHORITY_UNAVAILABLE"
    TARGET_AUTHORITY_UNAVAILABLE = "TARGET_AUTHORITY_UNAVAILABLE"
    TARGET_NOT_FORWARD_OF_ENTRY = "TARGET_NOT_FORWARD_OF_ENTRY"
    CURRENT_QUOTE_REQUIRED_BUT_UNAVAILABLE = "CURRENT_QUOTE_REQUIRED_BUT_UNAVAILABLE"
    EVIDENCE_BINDING_INVALID = "EVIDENCE_BINDING_INVALID"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    GEOMETRY_INVALID = "GEOMETRY_INVALID"
    MATERIAL_BARRIER_ELIMINATES_POSITIVE_REWARD = "MATERIAL_BARRIER_ELIMINATES_POSITIVE_REWARD"
    EXECUTION_CONTEXT_INCOMPLETE = "EXECUTION_CONTEXT_INCOMPLETE"
    OTHER_GOVERNED_UNAVAILABLE_REASON = "OTHER_GOVERNED_UNAVAILABLE_REASON"


@dataclass(frozen=True, slots=True)
class AuthoritativePriceEvidence:
    identity: str
    evidence_sha256: str
    price: Decimal
    observation_boundary: datetime
    source: str
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not _identity(self.identity)
            or not _digest(self.evidence_sha256)
            or not _positive_decimal(self.price)
            or not _aware(self.observation_boundary)
            or not self.source
            or not _governed_geometry_source(self.source)
            or not self.provenance
        ):
            raise ValueError("TRADE_PRICE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class QualificationCandleEvidence:
    identity: str
    evidence_sha256: str
    high: Decimal
    low: Decimal
    observation_boundary: datetime
    completed: bool
    source: str
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not _identity(self.identity)
            or not _digest(self.evidence_sha256)
            or not _positive_decimal(self.high)
            or not _positive_decimal(self.low)
            or self.high < self.low
            or not _aware(self.observation_boundary)
            or type(self.completed) is not bool
            or not self.source
            or not _governed_geometry_source(self.source)
            or not self.provenance
        ):
            raise ValueError("QUALIFICATION_CANDLE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class MaterialPricedBarrier:
    identity: str
    evidence_sha256: str
    price: Decimal
    observation_boundary: datetime
    source: str
    provenance: tuple[str, ...]
    material: bool = True

    def __post_init__(self) -> None:
        if (
            not _identity(self.identity)
            or not _digest(self.evidence_sha256)
            or not _positive_decimal(self.price)
            or not _aware(self.observation_boundary)
            or not self.source
            or not _governed_geometry_source(self.source)
            or not self.provenance
            or type(self.material) is not bool
        ):
            raise ValueError("MATERIAL_PRICED_BARRIER_INVALID")


@dataclass(frozen=True, slots=True)
class TradeConstructionEvidencePackage:
    package_identity: str
    package_sha256: str
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    setup_identity: TradeSetupIdentity
    qualification_candle: QualificationCandleEvidence | None
    governing_structural_low: AuthoritativePriceEvidence | None
    governing_structural_high: AuthoritativePriceEvidence | None
    prior_directional_swing_high: AuthoritativePriceEvidence | None
    prior_directional_swing_low: AuthoritativePriceEvidence | None
    original_range_high: AuthoritativePriceEvidence | None
    original_range_low: AuthoritativePriceEvidence | None
    material_barriers: tuple[MaterialPricedBarrier, ...]
    observation_boundary: datetime
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not _identity(self.package_identity)
            or not _digest(self.package_sha256)
            or not self.native_run_identity
            or not self.canonical_instrument
            or not _digest(self.native_assessment_sha256)
            or type(self.setup_identity) is not TradeSetupIdentity
            or not _aware(self.observation_boundary)
            or type(self.material_barriers) is not tuple
            or not self.provenance
            or self.package_sha256 != _package_digest(self)
        ):
            raise ValueError("TRADE_CONSTRUCTION_EVIDENCE_PACKAGE_INVALID")

    @property
    def evidence_identities(self) -> tuple[str, ...]:
        values: list[str] = [self.package_identity]
        for item in (
            self.qualification_candle,
            self.governing_structural_low,
            self.governing_structural_high,
            self.prior_directional_swing_high,
            self.prior_directional_swing_low,
            self.original_range_high,
            self.original_range_low,
            *self.material_barriers,
        ):
            if item is not None:
                values.append(item.identity)
        return tuple(values)

    @property
    def evidence_hashes(self) -> tuple[str, ...]:
        values: list[str] = [self.package_sha256]
        for item in (
            self.qualification_candle,
            self.governing_structural_low,
            self.governing_structural_high,
            self.prior_directional_swing_high,
            self.prior_directional_swing_low,
            self.original_range_high,
            self.original_range_low,
            *self.material_barriers,
        ):
            if item is not None:
                values.append(item.evidence_sha256)
        return tuple(values)


@dataclass(frozen=True, slots=True)
class TradePlanRecord:
    contract_identity: str
    contract_version: str
    trade_plan_id: str
    native_run_identity: str
    native_opportunity_identity: NativeOpportunityIdentity
    canonical_instrument: str
    native_direction: V1Direction
    native_assessment_sha256: str
    readiness_record_identity: str
    readiness_record_sha256: str
    trade_construction_policy_identity: str
    trade_construction_policy_version: str
    observation_boundary: datetime
    evidence_package_identity: str
    evidence_package_sha256: str
    evidence_identities: tuple[str, ...]
    evidence_hashes: tuple[str, ...]
    setup_identity: TradeSetupIdentity
    entry: Decimal | None
    entry_condition: str | None
    entry_authority_source: str | None
    stop: Decimal | None
    stop_authority_source: str | None
    invalidation_reference: Decimal | None
    invalidation_condition: str | None
    invalidation_authority_source: str | None
    setup_native_raw_target: Decimal | None
    canonical_target: Decimal | None
    target_authority_source: str | None
    material_barrier_identity: str | None
    material_barrier_reference: Decimal | None
    risk_per_unit: Decimal | None
    reward_per_unit: Decimal | None
    risk_reward_ratio: Decimal | None
    rejected_target_candidate_identity: str | None
    rejected_target_candidate_price: Decimal | None
    rejected_target_candidate_timeframe: str | None
    rejected_target_candidate_source: str | None
    rejected_target_candidate_boundary: datetime | None
    rejected_target_candidate_evidence_sha256: str | None
    rejected_target_candidate_provenance: tuple[str, ...]
    target_rejection_reason: TradePlanUnavailableReason | None
    execution_context_identity: str
    tick_size: Decimal | None
    price_precision: int | None
    geometry_viability: TradePlanStatus
    unavailable_reason: TradePlanUnavailableReason | None
    provenance: tuple[str, ...]
    created_at: datetime
    integrity_hash: str
    policy_status: str = TRADE_CONSTRUCTION_POLICY_STATUS
    authority: str = TRADE_PLAN_AUTHORITY

    def __post_init__(self) -> None:
        ready = self.geometry_viability is TradePlanStatus.TRADE_PLAN_READY
        legacy = (
            self.contract_identity == TRADE_PLAN_CONTRACT_ID_V0
            and self.contract_version == TRADE_PLAN_CONTRACT_VERSION_V0
            and self.trade_construction_policy_identity == TRADE_CONSTRUCTION_POLICY_ID_V0
            and self.trade_construction_policy_version == TRADE_CONSTRUCTION_POLICY_VERSION_V0
        )
        current = (
            self.contract_identity == TRADE_PLAN_CONTRACT_ID
            and self.contract_version == TRADE_PLAN_CONTRACT_VERSION
            and self.trade_construction_policy_identity == TRADE_CONSTRUCTION_POLICY_ID
            and self.trade_construction_policy_version == TRADE_CONSTRUCTION_POLICY_VERSION
        )
        rejected = self.target_rejection_reason is TradePlanUnavailableReason.TARGET_NOT_FORWARD_OF_ENTRY
        geometry = (
            self.entry,
            self.stop,
            self.invalidation_reference,
            self.setup_native_raw_target,
            self.canonical_target,
            self.risk_per_unit,
            self.reward_per_unit,
            self.risk_reward_ratio,
        )
        if (
            not (legacy or current)
            or not _identity(self.trade_plan_id)
            or not self.native_run_identity
            or type(self.native_opportunity_identity) is not NativeOpportunityIdentity
            or not self.canonical_instrument
            or self.native_direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not _digest(self.native_assessment_sha256)
            or not _identity(self.readiness_record_identity)
            or not _digest(self.readiness_record_sha256)
            or not _aware(self.observation_boundary)
            or not _identity(self.evidence_package_identity)
            or not _digest(self.evidence_package_sha256)
            or not self.evidence_identities
            or not self.evidence_hashes
            or type(self.setup_identity) is not TradeSetupIdentity
            or type(self.geometry_viability) is not TradePlanStatus
            or not self.execution_context_identity
            or not self.provenance
            or not _aware(self.created_at)
            or self.policy_status != TRADE_CONSTRUCTION_POLICY_STATUS
            or self.authority != TRADE_PLAN_AUTHORITY
            or (ready and (any(item is None for item in geometry) or self.unavailable_reason is not None))
            or (not ready and self.unavailable_reason is None)
            or (legacy and any((
                self.rejected_target_candidate_identity,
                self.rejected_target_candidate_price,
                self.rejected_target_candidate_timeframe,
                self.rejected_target_candidate_source,
                self.rejected_target_candidate_boundary,
                self.rejected_target_candidate_evidence_sha256,
                self.rejected_target_candidate_provenance,
                self.target_rejection_reason,
            )))
            or rejected != (self.unavailable_reason is TradePlanUnavailableReason.TARGET_NOT_FORWARD_OF_ENTRY)
            or rejected != all((
                self.rejected_target_candidate_identity is not None,
                self.rejected_target_candidate_price is not None,
                self.rejected_target_candidate_timeframe is not None,
                self.rejected_target_candidate_source is not None,
                self.rejected_target_candidate_boundary is not None,
                self.rejected_target_candidate_evidence_sha256 is not None,
                bool(self.rejected_target_candidate_provenance),
            ))
            or (not rejected and any((
                self.rejected_target_candidate_identity,
                self.rejected_target_candidate_price,
                self.rejected_target_candidate_timeframe,
                self.rejected_target_candidate_source,
                self.rejected_target_candidate_boundary,
                self.rejected_target_candidate_evidence_sha256,
                self.rejected_target_candidate_provenance,
                self.target_rejection_reason,
            )))
            or (rejected and (
                not _identity(self.rejected_target_candidate_identity)
                or not _positive_decimal(self.rejected_target_candidate_price)
                or not self.rejected_target_candidate_timeframe
                or not self.rejected_target_candidate_source
                or not _aware(self.rejected_target_candidate_boundary)
                or not _digest(self.rejected_target_candidate_evidence_sha256)
                or self.canonical_target is not None
                or self.reward_per_unit is not None
                or self.risk_reward_ratio is not None
                or self.material_barrier_identity is not None
                or self.material_barrier_reference is not None
            ))
            or (ready and not all((self.entry_condition, self.entry_authority_source,
                                   self.stop_authority_source, self.invalidation_condition,
                                   self.invalidation_authority_source, self.target_authority_source)))
            or (self.tick_size is not None and not _positive_decimal(self.tick_size))
            or (self.price_precision is not None and (type(self.price_precision) is not int or self.price_precision < 0))
            or (ready and (not _positive_decimal(self.risk_per_unit)
                           or not _positive_decimal(self.reward_per_unit)
                           or not _positive_decimal(self.risk_reward_ratio)))
            or not _digest(self.integrity_hash)
            or self.integrity_hash != _record_digest(self)
        ):
            raise ValueError("TRADE_PLAN_RECORD_INVALID")


class TradeConstructionInputRejected(ValueError):
    """The hard Step-31 input gate rejected a non-ready or foreign binding."""


class LocalTradePlanStore:
    """Append-only, integrity-checked Step-31 persistence."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("TRADE_PLAN_STORE_INVALID")
        self._lock = RLock()

    def retain(self, record: TradePlanRecord) -> Path:
        if type(record) is not TradePlanRecord:
            raise TypeError("TRADE_PLAN_RECORD_INVALID")
        path = self.root / record.native_run_identity / record.canonical_instrument / f"{record.trade_plan_id}.json"
        schema = TRADE_PLAN_SCHEMA_V0 if record.contract_identity == TRADE_PLAN_CONTRACT_ID_V0 else TRADE_PLAN_SCHEMA
        payload = {"schema": schema, "record": _primitive(record)}
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("TRADE_PLAN_RECORD_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load_for_requirements(self, requirements: tuple[NativeReviewRequirement, ...]) -> tuple[TradePlanRecord, ...]:
        if not requirements:
            return ()
        expected = {item.canonical_instrument: item for item in requirements}
        root = self.root / requirements[0].native_run_identity
        if not root.exists():
            return ()
        values: list[TradePlanRecord] = []
        for path in sorted(root.glob("*/*.json")):
            payload = _read(path)
            if payload.get("schema") not in {TRADE_PLAN_SCHEMA_V0, TRADE_PLAN_SCHEMA}:
                raise ValueError("TRADE_PLAN_RESTART_INTEGRITY_INVALID")
            record = _record_from_dict(payload.get("record"))
            requirement = expected.get(record.canonical_instrument)
            if (
                requirement is None
                or record.native_run_identity != requirement.native_run_identity
                or record.native_assessment_sha256 != requirement.thesis.native_assessment_sha256
                or record.native_opportunity_identity != requirement.thesis.opportunity_identity
                or record.native_direction != requirement.thesis.direction
            ):
                raise ValueError("TRADE_PLAN_RESTART_BINDING_INVALID")
            values.append(record)
        return tuple(values)


def create_trade_construction_evidence_package(
    *,
    package_identity: str,
    native_run_identity: str,
    canonical_instrument: str,
    native_assessment_sha256: str,
    setup_identity: TradeSetupIdentity,
    observation_boundary: datetime,
    provenance: tuple[str, ...],
    qualification_candle: QualificationCandleEvidence | None = None,
    governing_structural_low: AuthoritativePriceEvidence | None = None,
    governing_structural_high: AuthoritativePriceEvidence | None = None,
    prior_directional_swing_high: AuthoritativePriceEvidence | None = None,
    prior_directional_swing_low: AuthoritativePriceEvidence | None = None,
    original_range_high: AuthoritativePriceEvidence | None = None,
    original_range_low: AuthoritativePriceEvidence | None = None,
    material_barriers: tuple[MaterialPricedBarrier, ...] = (),
) -> TradeConstructionEvidencePackage:
    fields = dict(
        package_identity=package_identity,
        native_run_identity=native_run_identity,
        canonical_instrument=canonical_instrument,
        native_assessment_sha256=native_assessment_sha256,
        setup_identity=setup_identity,
        qualification_candle=qualification_candle,
        governing_structural_low=governing_structural_low,
        governing_structural_high=governing_structural_high,
        prior_directional_swing_high=prior_directional_swing_high,
        prior_directional_swing_low=prior_directional_swing_low,
        original_range_high=original_range_high,
        original_range_low=original_range_low,
        material_barriers=material_barriers,
        observation_boundary=observation_boundary,
        provenance=provenance,
    )
    digest = sha256(_canonical({**_primitive(fields), "package_sha256": ""})).hexdigest()
    return TradeConstructionEvidencePackage(package_sha256=digest, **fields)


def construct_trade_plan(
    requirement: NativeReviewRequirement,
    readiness: NativeLayer2ReadinessRecord | Kr370Step31EligibilityHandoff,
    evidence: TradeConstructionEvidencePackage,
    execution_context: CanonicalInstrumentContext,
    *,
    created_at: datetime,
) -> TradePlanRecord:
    """Construct governed V1 geometry; no readiness or review is recalculated."""

    if type(requirement) is not NativeReviewRequirement or type(readiness) not in {
        NativeLayer2ReadinessRecord,
        Kr370Step31EligibilityHandoff,
    }:
        raise TradeConstructionInputRejected("STEP31_INPUT_INVALID")
    if (
        type(readiness) is NativeLayer2ReadinessRecord
        and readiness.readiness is not NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION
    ):
        raise TradeConstructionInputRejected("STEP31_READINESS_NOT_ELIGIBLE")
    if not _hard_binding_valid(requirement, readiness):
        raise TradeConstructionInputRejected("STEP31_READINESS_BINDING_INVALID")

    reason = _evidence_binding_reason(requirement, readiness, evidence)
    if reason is not None:
        return _unavailable(requirement, readiness, evidence, execution_context, created_at, reason)
    if (
        type(execution_context) is not CanonicalInstrumentContext
        or execution_context.canonical_instrument != requirement.canonical_instrument
        or execution_context.status is not InstrumentContextStatus.COMPLETE
        or execution_context.tick_size is None
        or execution_context.price_precision is None
    ):
        return _unavailable(
            requirement, readiness, evidence, execution_context, created_at,
            TradePlanUnavailableReason.EXECUTION_CONTEXT_INCOMPLETE,
        )

    direction = requirement.thesis.direction
    candle = evidence.qualification_candle
    if candle is None or not candle.completed:
        return _unavailable(requirement, readiness, evidence, execution_context, created_at,
                            TradePlanUnavailableReason.ENTRY_AUTHORITY_UNAVAILABLE)
    entry = _round_tick(candle.high if direction is V1Direction.LONG else candle.low,
                        execution_context, up=direction is V1Direction.LONG)
    entry_condition = (
        f"SUBSEQUENT_DIRECTIONAL_CROSSING_ABOVE_{entry}"
        if direction is V1Direction.LONG else
        f"SUBSEQUENT_DIRECTIONAL_CROSSING_BELOW_{entry}"
    )

    stop_evidence: AuthoritativePriceEvidence | QualificationCandleEvidence | None
    invalidation_evidence: AuthoritativePriceEvidence | None
    target_evidence: AuthoritativePriceEvidence | None
    raw_target: Decimal | None
    if evidence.setup_identity is TradeSetupIdentity.PULLBACK_CONTINUATION:
        stop_evidence = (
            evidence.governing_structural_low
            if direction is V1Direction.LONG
            else evidence.governing_structural_high
        )
        invalidation_evidence = stop_evidence if isinstance(stop_evidence, AuthoritativePriceEvidence) else None
        target_evidence = (
            evidence.prior_directional_swing_high
            if direction is V1Direction.LONG
            else evidence.prior_directional_swing_low
        )
        raw_target = None if target_evidence is None else target_evidence.price
        stop_raw = None if stop_evidence is None else stop_evidence.price
        stop_source = None if stop_evidence is None else stop_evidence.source
        target_source = None if target_evidence is None else target_evidence.source
        invalidation_condition = (
            "COMPLETED_DAILY_CLOSE_BELOW_GOVERNING_PULLBACK_STRUCTURAL_LOW"
            if direction is V1Direction.LONG else
            "COMPLETED_DAILY_CLOSE_ABOVE_GOVERNING_PULLBACK_STRUCTURAL_HIGH"
        )
    else:
        stop_evidence = candle
        stop_raw = candle.low if direction is V1Direction.LONG else candle.high
        stop_source = candle.source
        invalidation_evidence = (
            evidence.original_range_high
            if direction is V1Direction.LONG
            else evidence.original_range_low
        )
        if evidence.original_range_high is None or evidence.original_range_low is None:
            raw_target = None
        else:
            width = evidence.original_range_high.price - evidence.original_range_low.price
            raw_target = (
                evidence.original_range_high.price + width
                if direction is V1Direction.LONG
                else evidence.original_range_low.price - width
            )
        target_evidence = evidence.original_range_high if direction is V1Direction.LONG else evidence.original_range_low
        target_source = None if target_evidence is None else target_evidence.source
        invalidation_condition = (
            "COMPLETED_DAILY_CLOSE_AT_OR_BELOW_ORIGINAL_RANGE_HIGH"
            if direction is V1Direction.LONG else
            "COMPLETED_DAILY_CLOSE_AT_OR_ABOVE_ORIGINAL_RANGE_LOW"
        )

    if stop_raw is None:
        return _unavailable(requirement, readiness, evidence, execution_context, created_at,
                            TradePlanUnavailableReason.STOP_AUTHORITY_UNAVAILABLE)
    if invalidation_evidence is None:
        return _unavailable(requirement, readiness, evidence, execution_context, created_at,
                            TradePlanUnavailableReason.INVALIDATION_AUTHORITY_UNAVAILABLE)
    if raw_target is None or raw_target <= 0:
        return _unavailable(requirement, readiness, evidence, execution_context, created_at,
                            TradePlanUnavailableReason.TARGET_AUTHORITY_UNAVAILABLE)

    stop = _round_tick(stop_raw, execution_context, up=direction is V1Direction.SHORT)
    invalidation_reference = _round_tick(
        invalidation_evidence.price, execution_context, up=direction is V1Direction.SHORT,
    )
    target = _round_tick(raw_target, execution_context, up=direction is V1Direction.SHORT)
    if not _forward_target(entry, target, direction):
        return _target_rejected(
            requirement=requirement,
            readiness=readiness,
            evidence=evidence,
            context=execution_context,
            created_at=created_at,
            entry=entry,
            entry_condition=entry_condition,
            entry_source=candle.source,
            stop=stop,
            stop_source=stop_source,
            invalidation_reference=invalidation_reference,
            invalidation_condition=invalidation_condition,
            invalidation_source=invalidation_evidence.source,
            raw_target=raw_target,
            rounded_target=target,
            target_evidence=target_evidence,
        )
    barrier = _nearest_barrier(evidence.material_barriers, entry, target, direction)
    if barrier is not None:
        target = _round_tick(barrier.price, execution_context, up=direction is V1Direction.SHORT)

    risk = entry - stop if direction is V1Direction.LONG else stop - entry
    reward = target - entry if direction is V1Direction.LONG else entry - target
    if barrier is not None and reward <= 0:
        return _unavailable(
            requirement, readiness, evidence, execution_context, created_at,
            TradePlanUnavailableReason.MATERIAL_BARRIER_ELIMINATES_POSITIVE_REWARD,
        )
    if risk <= 0 or reward <= 0:
        return _unavailable(requirement, readiness, evidence, execution_context, created_at,
                            TradePlanUnavailableReason.GEOMETRY_INVALID)
    ratio = reward / risk
    if not ratio.is_finite() or ratio <= 0:
        return _unavailable(requirement, readiness, evidence, execution_context, created_at,
                            TradePlanUnavailableReason.GEOMETRY_INVALID)

    fields = _base_fields(requirement, readiness, evidence, execution_context, created_at)
    fields.update(
        entry=entry,
        entry_condition=entry_condition,
        entry_authority_source=candle.source,
        stop=stop,
        stop_authority_source=stop_source,
        invalidation_reference=invalidation_reference,
        invalidation_condition=invalidation_condition,
        invalidation_authority_source=invalidation_evidence.source,
        setup_native_raw_target=raw_target,
        canonical_target=target,
        target_authority_source=(
            barrier.source if barrier is not None else target_source
        ),
        material_barrier_identity=None if barrier is None else barrier.identity,
        material_barrier_reference=None if barrier is None else barrier.price,
        risk_per_unit=risk,
        reward_per_unit=reward,
        risk_reward_ratio=ratio,
        rejected_target_candidate_identity=None,
        rejected_target_candidate_price=None,
        rejected_target_candidate_timeframe=None,
        rejected_target_candidate_source=None,
        rejected_target_candidate_boundary=None,
        rejected_target_candidate_evidence_sha256=None,
        rejected_target_candidate_provenance=(),
        target_rejection_reason=None,
        geometry_viability=TradePlanStatus.TRADE_PLAN_READY,
        unavailable_reason=None,
    )
    return _record(fields)


def step32_handoff(record: TradePlanRecord) -> TradePlanRecord:
    """Expose only ready immutable geometry; Step 32 itself is not implemented."""

    if type(record) is not TradePlanRecord or record.geometry_viability is not TradePlanStatus.TRADE_PLAN_READY:
        raise ValueError("STEP32_TRADE_PLAN_HANDOFF_REJECTED")
    return record


def _hard_binding_valid(
    requirement: NativeReviewRequirement,
    readiness: NativeLayer2ReadinessRecord | Kr370Step31EligibilityHandoff,
) -> bool:
    thesis = requirement.thesis
    if type(readiness) is Kr370Step31EligibilityHandoff:
        return (
            readiness.native_run_identity == requirement.native_run_identity
            and readiness.canonical_instrument == requirement.canonical_instrument
            and readiness.native_assessment_sha256 == thesis.native_assessment_sha256
            and readiness.native_requirement_sha256 == requirement.requirement_sha256
            and readiness.native_opportunity_identity is thesis.opportunity_identity
            and readiness.direction is thesis.direction
        )
    return (
        readiness.run_identity == requirement.native_run_identity
        and readiness.canonical_instrument == requirement.canonical_instrument
        and readiness.native_assessment_sha256 == thesis.native_assessment_sha256
        and readiness.native_thesis_sha256
        == sha256(_canonical(_primitive(thesis))).hexdigest()
        and readiness.observation_boundary == max(item.observation_boundary for item in thesis.timeframe_facts)
    )


def _evidence_binding_reason(requirement, readiness, evidence):  # type: ignore[no-untyped-def]
    if type(evidence) is not TradeConstructionEvidencePackage:
        return TradePlanUnavailableReason.EVIDENCE_BINDING_INVALID
    if (
        evidence.native_run_identity != requirement.native_run_identity
        or evidence.canonical_instrument != requirement.canonical_instrument
        or evidence.native_assessment_sha256 != requirement.thesis.native_assessment_sha256
    ):
        return TradePlanUnavailableReason.EVIDENCE_BINDING_INVALID
    if evidence.observation_boundary != _eligibility_boundary(readiness):
        return TradePlanUnavailableReason.EVIDENCE_STALE
    return None


def _base_fields(requirement, readiness, evidence, context, created_at):  # type: ignore[no-untyped-def]
    thesis = requirement.thesis
    readiness_identity, readiness_sha256 = _readiness_lineage(readiness)
    plan_seed = {
        "readiness_record_sha256": readiness_sha256,
        "eligibility_integrity_sha256": (
            readiness.integrity_sha256
            if type(readiness) is Kr370Step31EligibilityHandoff
            else readiness_sha256
        ),
        "evidence_package_sha256": evidence.package_sha256,
        "policy_identity": TRADE_CONSTRUCTION_POLICY_ID,
        "policy_version": TRADE_CONSTRUCTION_POLICY_VERSION,
    }
    trade_plan_id = "TRADE-PLAN-" + sha256(_canonical(plan_seed)).hexdigest()
    return dict(
        contract_identity=TRADE_PLAN_CONTRACT_ID,
        contract_version=TRADE_PLAN_CONTRACT_VERSION,
        trade_plan_id=trade_plan_id,
        native_run_identity=requirement.native_run_identity,
        native_opportunity_identity=thesis.opportunity_identity,
        canonical_instrument=requirement.canonical_instrument,
        native_direction=thesis.direction,
        native_assessment_sha256=thesis.native_assessment_sha256,
        readiness_record_identity=readiness_identity,
        readiness_record_sha256=readiness_sha256,
        trade_construction_policy_identity=TRADE_CONSTRUCTION_POLICY_ID,
        trade_construction_policy_version=TRADE_CONSTRUCTION_POLICY_VERSION,
        observation_boundary=_eligibility_boundary(readiness),
        evidence_package_identity=evidence.package_identity,
        evidence_package_sha256=evidence.package_sha256,
        evidence_identities=evidence.evidence_identities,
        evidence_hashes=evidence.evidence_hashes,
        setup_identity=evidence.setup_identity,
        execution_context_identity=(context.identity if type(context) is CanonicalInstrumentContext else "EXECUTION-CONTEXT-UNAVAILABLE"),
        tick_size=(context.tick_size if type(context) is CanonicalInstrumentContext else None),
        price_precision=(context.price_precision if type(context) is CanonicalInstrumentContext else None),
        provenance=tuple(dict.fromkeys((
            *thesis.provider_provenance,
            *thesis.calendar_provenance,
            *evidence.provenance,
            *(
                (
                    *readiness.provenance,
                    readiness.handoff_identity,
                    readiness.integrity_sha256,
                )
                if type(readiness) is Kr370Step31EligibilityHandoff else ()
            ),
            "DOMAIN-001",
            "DOMAIN-008",
        ))),
        created_at=created_at,
        policy_status=TRADE_CONSTRUCTION_POLICY_STATUS,
        authority=TRADE_PLAN_AUTHORITY,
    )


def _readiness_lineage(
    value: NativeLayer2ReadinessRecord | Kr370Step31EligibilityHandoff,
) -> tuple[str, str]:
    if type(value) is Kr370Step31EligibilityHandoff:
        return value.v3_readiness_identity, value.v3_readiness_sha256
    return f"NATIVE-READINESS-{value.result_sha256}", value.result_sha256


def _eligibility_boundary(
    value: NativeLayer2ReadinessRecord | Kr370Step31EligibilityHandoff,
) -> datetime:
    return (
        value.analysis_boundary
        if type(value) is Kr370Step31EligibilityHandoff
        else value.observation_boundary
    )


def _unavailable(requirement, readiness, evidence, context, created_at, reason):  # type: ignore[no-untyped-def]
    if type(evidence) is not TradeConstructionEvidencePackage:
        raise TradeConstructionInputRejected("STEP31_EVIDENCE_PACKAGE_INVALID")
    fields = _base_fields(requirement, readiness, evidence, context, created_at)
    fields.update(
        entry=None, entry_condition=None, entry_authority_source=None,
        stop=None, stop_authority_source=None,
        invalidation_reference=None, invalidation_condition=None,
        invalidation_authority_source=None, setup_native_raw_target=None,
        canonical_target=None, target_authority_source=None,
        material_barrier_identity=None, material_barrier_reference=None,
        risk_per_unit=None, reward_per_unit=None, risk_reward_ratio=None,
        rejected_target_candidate_identity=None,
        rejected_target_candidate_price=None,
        rejected_target_candidate_timeframe=None,
        rejected_target_candidate_source=None,
        rejected_target_candidate_boundary=None,
        rejected_target_candidate_evidence_sha256=None,
        rejected_target_candidate_provenance=(),
        target_rejection_reason=None,
        geometry_viability=TradePlanStatus.TRADE_PLAN_UNAVAILABLE,
        unavailable_reason=reason,
    )
    return _record(fields)


def _target_rejected(
    *,
    requirement: NativeReviewRequirement,
    readiness: NativeLayer2ReadinessRecord | Kr370Step31EligibilityHandoff,
    evidence: TradeConstructionEvidencePackage,
    context: CanonicalInstrumentContext,
    created_at: datetime,
    entry: Decimal,
    entry_condition: str,
    entry_source: str,
    stop: Decimal,
    stop_source: str,
    invalidation_reference: Decimal,
    invalidation_condition: str,
    invalidation_source: str,
    raw_target: Decimal,
    rounded_target: Decimal,
    target_evidence: AuthoritativePriceEvidence,
) -> TradePlanRecord:
    """Retain a non-forward candidate as context without granting target authority."""

    (
        candidate_identity,
        candidate_source,
        candidate_boundary,
        candidate_sha256,
        candidate_provenance,
    ) = _target_candidate_lineage(evidence, target_evidence, raw_target)
    timeframe = _timeframe_from_source(candidate_source)
    if timeframe is None:
        raise TradeConstructionInputRejected("STEP31_TARGET_TIMEFRAME_UNAVAILABLE")
    fields = _base_fields(requirement, readiness, evidence, context, created_at)
    fields.update(
        entry=entry,
        entry_condition=entry_condition,
        entry_authority_source=entry_source,
        stop=stop,
        stop_authority_source=stop_source,
        invalidation_reference=invalidation_reference,
        invalidation_condition=invalidation_condition,
        invalidation_authority_source=invalidation_source,
        setup_native_raw_target=raw_target,
        canonical_target=None,
        target_authority_source=None,
        material_barrier_identity=None,
        material_barrier_reference=None,
        risk_per_unit=(
            entry - stop if requirement.thesis.direction is V1Direction.LONG
            else stop - entry
        ),
        reward_per_unit=None,
        risk_reward_ratio=None,
        rejected_target_candidate_identity=candidate_identity,
        rejected_target_candidate_price=rounded_target,
        rejected_target_candidate_timeframe=timeframe,
        rejected_target_candidate_source=candidate_source,
        rejected_target_candidate_boundary=candidate_boundary,
        rejected_target_candidate_evidence_sha256=candidate_sha256,
        rejected_target_candidate_provenance=candidate_provenance,
        target_rejection_reason=TradePlanUnavailableReason.TARGET_NOT_FORWARD_OF_ENTRY,
        geometry_viability=TradePlanStatus.TRADE_PLAN_UNAVAILABLE,
        unavailable_reason=TradePlanUnavailableReason.TARGET_NOT_FORWARD_OF_ENTRY,
    )
    return _record(fields)


def _forward_target(entry: Decimal, target: Decimal, direction: V1Direction) -> bool:
    return target > entry if direction is V1Direction.LONG else target < entry


def _timeframe_from_source(source: str) -> str | None:
    upper = source.upper()
    for token in ("4H", "1H", "DAILY", "WEEKLY"):
        if token in upper:
            return token
    return None


def _target_candidate_lineage(
    evidence: TradeConstructionEvidencePackage,
    source_evidence: AuthoritativePriceEvidence,
    raw_target: Decimal,
) -> tuple[str, str, datetime, str, tuple[str, ...]]:
    if evidence.setup_identity is TradeSetupIdentity.PULLBACK_CONTINUATION:
        return (
            source_evidence.identity,
            source_evidence.source,
            source_evidence.observation_boundary,
            source_evidence.evidence_sha256,
            source_evidence.provenance,
        )
    identity = f"BREAKOUT-PROJECTION:{evidence.package_identity}"
    digest = sha256(_canonical({
        "identity": identity,
        "raw_target": str(raw_target),
        "source_evidence": source_evidence.evidence_sha256,
        "setup": evidence.setup_identity.value,
    })).hexdigest()
    return (
        identity,
        source_evidence.source,
        evidence.observation_boundary,
        digest,
        tuple(dict.fromkeys((*source_evidence.provenance, evidence.package_sha256))),
    )


def _record(fields: dict[str, object]) -> TradePlanRecord:
    digest_fields = {**fields, "integrity_hash": ""}
    record = TradePlanRecord(integrity_hash=sha256(_canonical(_primitive(digest_fields))).hexdigest(), **fields)
    return record


def _nearest_barrier(barriers, entry, target, direction):  # type: ignore[no-untyped-def]
    eligible = [
        item for item in barriers
        if item.material and (
            entry < item.price < target if direction is V1Direction.LONG
            else target < item.price < entry
        )
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda item: abs(item.price - entry))


def _round_tick(value: Decimal, context: CanonicalInstrumentContext, *, up: bool) -> Decimal:
    assert context.tick_size is not None and context.price_precision is not None
    units = value / context.tick_size
    rounded = units.to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR) * context.tick_size
    quantum = Decimal(1).scaleb(-context.price_precision)
    return rounded.quantize(quantum)


def _package_digest(package: TradeConstructionEvidencePackage) -> str:
    payload = _primitive(package)
    payload["package_sha256"] = ""
    return sha256(_canonical(payload)).hexdigest()


def _record_digest(record: TradePlanRecord) -> str:
    payload = _primitive(record)
    if record.contract_identity == TRADE_PLAN_CONTRACT_ID_V0:
        for key in (
            "rejected_target_candidate_identity",
            "rejected_target_candidate_price",
            "rejected_target_candidate_timeframe",
            "rejected_target_candidate_source",
            "rejected_target_candidate_boundary",
            "rejected_target_candidate_evidence_sha256",
            "rejected_target_candidate_provenance",
            "target_rejection_reason",
        ):
            payload.pop(key)
    payload["integrity_hash"] = ""
    return sha256(_canonical(payload)).hexdigest()


def _primitive(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _record_from_dict(value: object) -> TradePlanRecord:
    if type(value) is not dict:
        raise ValueError("TRADE_PLAN_STORED_RECORD_INVALID")
    try:
        data = dict(value)
        for name in (
            "entry", "stop", "invalidation_reference", "setup_native_raw_target",
            "canonical_target", "material_barrier_reference", "risk_per_unit",
            "reward_per_unit", "risk_reward_ratio", "tick_size",
            "rejected_target_candidate_price",
        ):
            if name not in data:
                data[name] = None
            data[name] = None if data[name] is None else Decimal(data[name])
        data.setdefault("rejected_target_candidate_identity", None)
        data.setdefault("rejected_target_candidate_timeframe", None)
        data.setdefault("rejected_target_candidate_source", None)
        data.setdefault("rejected_target_candidate_boundary", None)
        data.setdefault("rejected_target_candidate_evidence_sha256", None)
        data.setdefault("rejected_target_candidate_provenance", ())
        data.setdefault("target_rejection_reason", None)
        data["native_opportunity_identity"] = NativeOpportunityIdentity(data["native_opportunity_identity"])
        data["native_direction"] = V1Direction(data["native_direction"])
        data["setup_identity"] = TradeSetupIdentity(data["setup_identity"])
        data["geometry_viability"] = TradePlanStatus(data["geometry_viability"])
        data["unavailable_reason"] = (
            None if data["unavailable_reason"] is None
            else TradePlanUnavailableReason(data["unavailable_reason"])
        )
        data["target_rejection_reason"] = (
            None if data["target_rejection_reason"] is None
            else TradePlanUnavailableReason(data["target_rejection_reason"])
        )
        data["observation_boundary"] = datetime.fromisoformat(data["observation_boundary"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data["rejected_target_candidate_boundary"] is not None:
            data["rejected_target_candidate_boundary"] = datetime.fromisoformat(
                data["rejected_target_candidate_boundary"]
            )
        for name in (
            "evidence_identities", "evidence_hashes", "provenance",
            "rejected_target_candidate_provenance",
        ):
            data[name] = tuple(data[name])
        return TradePlanRecord(**data)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("TRADE_PLAN_STORED_RECORD_INVALID") from error


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("TRADE_PLAN_STORED_RECORD_INVALID") from error
    if type(value) is not dict:
        raise ValueError("TRADE_PLAN_STORED_RECORD_INVALID")
    return value


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _identity(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:@|+/-]{1,512}", value) is not None


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _positive_decimal(value: object) -> bool:
    return type(value) is Decimal and value.is_finite() and value > 0


def _governed_geometry_source(value: str) -> bool:
    upper = value.upper()
    return not any(
        prohibited in upper
        for prohibited in ("OPENAI", "PINE", "COMEX", "NYMEX", "REFERENCE_MARKET")
    )


__all__ = [
    "AuthoritativePriceEvidence",
    "LocalTradePlanStore",
    "MaterialPricedBarrier",
    "QualificationCandleEvidence",
    "TRADE_CONSTRUCTION_POLICY_ID",
    "TRADE_CONSTRUCTION_POLICY_VERSION",
    "TRADE_PLAN_CONTRACT_ID",
    "TradeConstructionEvidencePackage",
    "TradeConstructionInputRejected",
    "TradePlanRecord",
    "TradePlanStatus",
    "TradePlanUnavailableReason",
    "TradeSetupIdentity",
    "construct_trade_plan",
    "create_trade_construction_evidence_package",
    "step32_handoff",
]
