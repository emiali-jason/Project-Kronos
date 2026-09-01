"""Observation-phase Step-31 geometry evidence with no trading authority."""

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
from kronos.swing.v1.kr370_step31_handoff import Kr370Step31EligibilityHandoff
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_discovery import NativeOpportunityIdentity
from kronos.swing.v1.native_review import NativeReviewRequirement
from kronos.swing.v1.native_trade_construction import (
    AuthoritativePriceEvidence,
    QualificationCandleEvidence,
    TradeConstructionEvidencePackage,
    TradePlanRecord,
    TradePlanStatus,
    TradeSetupIdentity,
    TRADE_CONSTRUCTION_POLICY_ID,
    TRADE_CONSTRUCTION_POLICY_ID_V0,
    TRADE_CONSTRUCTION_POLICY_VERSION,
    TRADE_CONSTRUCTION_POLICY_VERSION_V0,
    _target_candidate_lineage,
)


STEP31_OBSERVATION_CONTRACT_ID_V1 = "KRONOS-SWING-STEP31-OBSERVATION-EVIDENCE-V1"
STEP31_OBSERVATION_CONTRACT_VERSION_V1 = "1"
STEP31_OBSERVATION_SCHEMA_V1 = "KRONOS-SWING-STEP31-OBSERVATION-STORE-V1"
STEP31_OBSERVATION_CONTRACT_ID = "KRONOS-SWING-STEP31-OBSERVATION-EVIDENCE-V2"
STEP31_OBSERVATION_CONTRACT_VERSION = "2"
STEP31_OBSERVATION_POLICY_ID = "SWING-STEP31-OBSERVATION-PHASE-V1"
STEP31_OBSERVATION_POLICY_VERSION = "1"
STEP31_OBSERVATION_SCHEMA = "KRONOS-SWING-STEP31-OBSERVATION-STORE-V2"
STEP31_OBSERVATION_AUTHORITY = (
    "ADVISORY_GEOMETRY_EVIDENCE_ONLY_NO_RISK_SPONSOR_EXECUTION_OR_BROKER_AUTHORITY"
)


class Step31FactAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class Step31RiskRewardState(StrEnum):
    AVAILABLE = "AVAILABLE"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"


class Step31ObservationWarning(StrEnum):
    TARGET_BELOW_ENTRY = "TARGET_BELOW_ENTRY"
    TARGET_ABOVE_ENTRY = "TARGET_ABOVE_ENTRY"
    NON_POSITIVE_REWARD = "NON_POSITIVE_REWARD"
    NON_POSITIVE_RISK = "NON_POSITIVE_RISK"
    RR_UNFAVOURABLE = "RR_UNFAVOURABLE"
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
    TARGET_NOT_FORWARD_OF_ENTRY = "TARGET_NOT_FORWARD_OF_ENTRY"
    STOP_UNAVAILABLE = "STOP_UNAVAILABLE"
    ENTRY_UNAVAILABLE = "ENTRY_UNAVAILABLE"
    STRUCTURAL_GEOMETRY_WARNING = "STRUCTURAL_GEOMETRY_WARNING"


class Step31WarningSeverity(StrEnum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class Step31GeometryStatus(StrEnum):
    COMPLETE_FAVOURABLE = "COMPLETE_FAVOURABLE"
    COMPLETE_WARNING = "COMPLETE_WARNING"
    INCOMPLETE_WARNING = "INCOMPLETE_WARNING"
    HARD_UNAVAILABLE = "HARD_UNAVAILABLE"


class Step31ObservationHardFailure(ValueError):
    """A trust, identity, integrity, or binding gate failed closed."""


@dataclass(frozen=True, slots=True)
class Step31ObservationEvidence:
    contract_identity: str
    contract_version: str
    observation_evidence_id: str
    native_run_identity: str
    canonical_instrument: str
    native_direction: V1Direction
    native_opportunity_identity: NativeOpportunityIdentity
    native_assessment_sha256: str
    kr370_handoff_identity: str
    kr370_handoff_integrity_sha256: str
    v3_readiness_identity: str
    v3_readiness_sha256: str
    evidence_package_identity: str
    evidence_package_sha256: str
    execution_context_identity: str
    setup_identity: TradeSetupIdentity
    observation_boundary: datetime
    entry: Decimal | None
    entry_availability: Step31FactAvailability
    entry_condition: str | None
    entry_authority_source: str | None
    stop: Decimal | None
    stop_availability: Step31FactAvailability
    stop_authority_source: str | None
    invalidation_reference: Decimal | None
    invalidation_availability: Step31FactAvailability
    invalidation_condition: str | None
    invalidation_authority_source: str | None
    setup_native_raw_target: Decimal | None
    canonical_target: Decimal | None
    target_availability: Step31FactAvailability
    target_authority_source: str | None
    material_barrier_identity: str | None
    material_barrier_reference: Decimal | None
    risk_per_unit: Decimal | None
    reward_per_unit: Decimal | None
    risk_reward_ratio: Decimal | None
    risk_reward_state: Step31RiskRewardState
    trade_construction_policy_identity: str
    trade_construction_policy_version: str
    rejected_target_candidate_identity: str | None
    rejected_target_candidate_price: Decimal | None
    rejected_target_candidate_timeframe: str | None
    rejected_target_candidate_source: str | None
    rejected_target_candidate_boundary: datetime | None
    rejected_target_candidate_evidence_sha256: str | None
    rejected_target_candidate_provenance: tuple[str, ...]
    target_rejection_reason: str | None
    warnings: tuple[Step31ObservationWarning, ...]
    severity: Step31WarningSeverity
    geometry_status: Step31GeometryStatus
    conventional_trade_plan_id: str | None
    conventional_trade_plan_sha256: str | None
    provenance: tuple[str, ...]
    created_at: datetime
    integrity_sha256: str
    policy_identity: str = STEP31_OBSERVATION_POLICY_ID
    policy_version: str = STEP31_OBSERVATION_POLICY_VERSION
    authority: str = STEP31_OBSERVATION_AUTHORITY

    def __post_init__(self) -> None:
        available_pairs = (
            (self.entry, self.entry_availability),
            (self.stop, self.stop_availability),
            (self.invalidation_reference, self.invalidation_availability),
            (self.canonical_target, self.target_availability),
        )
        plan_bound = self.conventional_trade_plan_id is not None
        legacy = (
            self.contract_identity == STEP31_OBSERVATION_CONTRACT_ID_V1
            and self.contract_version == STEP31_OBSERVATION_CONTRACT_VERSION_V1
            and self.trade_construction_policy_identity == TRADE_CONSTRUCTION_POLICY_ID_V0
            and self.trade_construction_policy_version == TRADE_CONSTRUCTION_POLICY_VERSION_V0
        )
        current = (
            self.contract_identity == STEP31_OBSERVATION_CONTRACT_ID
            and self.contract_version == STEP31_OBSERVATION_CONTRACT_VERSION
            and self.trade_construction_policy_identity == TRADE_CONSTRUCTION_POLICY_ID
            and self.trade_construction_policy_version == TRADE_CONSTRUCTION_POLICY_VERSION
        )
        rejected = self.target_rejection_reason == "TARGET_NOT_FORWARD_OF_ENTRY"
        if (
            not (legacy or current)
            or not _identity(self.observation_evidence_id)
            or not self.native_run_identity
            or not self.canonical_instrument
            or self.native_direction not in {V1Direction.LONG, V1Direction.SHORT}
            or type(self.native_opportunity_identity) is not NativeOpportunityIdentity
            or not _digest(self.native_assessment_sha256)
            or not _identity(self.kr370_handoff_identity)
            or not _digest(self.kr370_handoff_integrity_sha256)
            or not _identity(self.v3_readiness_identity)
            or not _digest(self.v3_readiness_sha256)
            or not _identity(self.evidence_package_identity)
            or not _digest(self.evidence_package_sha256)
            or not _identity(self.execution_context_identity)
            or type(self.setup_identity) is not TradeSetupIdentity
            or not _aware(self.observation_boundary)
            or any((value is None) != (state is Step31FactAvailability.UNAVAILABLE)
                   for value, state in available_pairs)
            or any(value is not None and not _finite_decimal(value) for value, _ in available_pairs)
            or (self.entry is None) != (
                self.entry_condition is None and self.entry_authority_source is None
            )
            or (self.stop is None) != (self.stop_authority_source is None)
            or (self.invalidation_reference is None) != (
                self.invalidation_condition is None
                and self.invalidation_authority_source is None
            )
            or (self.canonical_target is None) != (self.target_authority_source is None)
            or (self.setup_native_raw_target is not None and not _finite_decimal(self.setup_native_raw_target))
            or (self.material_barrier_reference is not None and not _positive_decimal(self.material_barrier_reference))
            or (self.material_barrier_identity is None) != (self.material_barrier_reference is None)
            or (self.risk_per_unit is not None and not _finite_decimal(self.risk_per_unit))
            or (self.reward_per_unit is not None and not _finite_decimal(self.reward_per_unit))
            or (self.risk_reward_ratio is not None and not _positive_decimal(self.risk_reward_ratio))
            or type(self.risk_reward_state) is not Step31RiskRewardState
            or ((self.risk_reward_ratio is not None) != (self.risk_reward_state is Step31RiskRewardState.AVAILABLE))
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
                or self.risk_reward_state is not Step31RiskRewardState.UNAVAILABLE
                or Step31ObservationWarning.TARGET_NOT_FORWARD_OF_ENTRY not in self.warnings
            ))
            or type(self.warnings) is not tuple
            or any(type(item) is not Step31ObservationWarning for item in self.warnings)
            or len(set(self.warnings)) != len(self.warnings)
            or type(self.severity) is not Step31WarningSeverity
            or type(self.geometry_status) is not Step31GeometryStatus
            or self.geometry_status is Step31GeometryStatus.HARD_UNAVAILABLE
            or (self.severity is Step31WarningSeverity.GREEN) != (not self.warnings)
            or (self.geometry_status is Step31GeometryStatus.COMPLETE_FAVOURABLE) != (
                all(value is not None for value, _ in available_pairs) and not self.warnings
            )
            or plan_bound != (self.conventional_trade_plan_sha256 is not None)
            or (plan_bound and (not _identity(self.conventional_trade_plan_id)
                                or not _digest(self.conventional_trade_plan_sha256)))
            or not self.provenance
            or not _aware(self.created_at)
            or self.policy_identity != STEP31_OBSERVATION_POLICY_ID
            or self.policy_version != STEP31_OBSERVATION_POLICY_VERSION
            or self.authority != STEP31_OBSERVATION_AUTHORITY
            or not _digest(self.integrity_sha256)
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("STEP31_OBSERVATION_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class Step31SponsorObservationHandoff:
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    kr370_handoff_identity: str
    observation_evidence_id: str
    observation_evidence_sha256: str
    conventional_trade_plan_id: str | None
    warnings: tuple[Step31ObservationWarning, ...]
    severity: Step31WarningSeverity
    risk_state: str
    risk_evidence_identity: str | None
    execution_context_identity: str
    integrity_sha256: str

    def __post_init__(self) -> None:
        if (
            not self.native_run_identity
            or not self.canonical_instrument
            or not _digest(self.native_assessment_sha256)
            or not _identity(self.kr370_handoff_identity)
            or not _identity(self.observation_evidence_id)
            or not _digest(self.observation_evidence_sha256)
            or (self.conventional_trade_plan_id is not None and not _identity(self.conventional_trade_plan_id))
            or type(self.warnings) is not tuple
            or type(self.severity) is not Step31WarningSeverity
            or self.risk_state not in {
                "RISK_UNAVAILABLE",
                "RISK_APPROVED",
                "RISK_CONSTRAINED",
                "RISK_REJECTED",
            }
            or (self.risk_evidence_identity is not None and not _identity(self.risk_evidence_identity))
            or not _identity(self.execution_context_identity)
            or self.integrity_sha256 != _handoff_digest(self)
        ):
            raise ValueError("STEP31_SPONSOR_OBSERVATION_HANDOFF_INVALID")


class LocalStep31ObservationStore:
    """Append-only persistence for advisory observation-phase records."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("STEP31_OBSERVATION_STORE_INVALID")
        self._lock = RLock()

    def retain(self, record: Step31ObservationEvidence) -> Path:
        if type(record) is not Step31ObservationEvidence:
            raise TypeError("STEP31_OBSERVATION_EVIDENCE_INVALID")
        path = self.root / record.native_run_identity / record.canonical_instrument / f"{record.observation_evidence_id}.json"
        schema = (
            STEP31_OBSERVATION_SCHEMA_V1
            if record.contract_identity == STEP31_OBSERVATION_CONTRACT_ID_V1
            else STEP31_OBSERVATION_SCHEMA
        )
        payload = {"schema": schema, "record": _primitive(record)}
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("STEP31_OBSERVATION_EVIDENCE_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load_for_requirements(
        self, requirements: tuple[NativeReviewRequirement, ...]
    ) -> tuple[Step31ObservationEvidence, ...]:
        if not requirements:
            return ()
        expected = {item.canonical_instrument: item for item in requirements}
        root = self.root / requirements[0].native_run_identity
        if not root.exists():
            return ()
        values: list[Step31ObservationEvidence] = []
        for path in sorted(root.glob("*/*.json")):
            payload = _read(path)
            if payload.get("schema") not in {STEP31_OBSERVATION_SCHEMA_V1, STEP31_OBSERVATION_SCHEMA}:
                raise ValueError("STEP31_OBSERVATION_RESTART_INTEGRITY_INVALID")
            record = _record_from_dict(payload.get("record"))
            requirement = expected.get(record.canonical_instrument)
            if (
                requirement is None
                or record.native_run_identity != requirement.native_run_identity
                or record.native_assessment_sha256 != requirement.thesis.native_assessment_sha256
                or record.native_opportunity_identity is not requirement.thesis.opportunity_identity
                or record.native_direction is not requirement.thesis.direction
            ):
                raise ValueError("STEP31_OBSERVATION_RESTART_BINDING_INVALID")
            values.append(record)
        return tuple(values)


def construct_step31_observation(
    requirement: NativeReviewRequirement,
    handoff: Kr370Step31EligibilityHandoff,
    evidence: TradeConstructionEvidencePackage,
    execution_context: CanonicalInstrumentContext,
    *,
    created_at: datetime,
    conventional_plan: TradePlanRecord | None = None,
) -> Step31ObservationEvidence:
    """Evaluate available Step-31 facts without manufacturing a Trade Plan."""

    _validate_hard_inputs(requirement, handoff, evidence, execution_context, created_at)
    direction = requirement.thesis.direction
    candle = evidence.qualification_candle
    candle_available = candle is not None and candle.completed
    entry = (
        _round_tick(candle.high if direction is V1Direction.LONG else candle.low,
                    execution_context, up=direction is V1Direction.LONG)
        if candle_available else None
    )
    entry_condition = (
        None if entry is None else
        f"SUBSEQUENT_DIRECTIONAL_CROSSING_ABOVE_{entry}"
        if direction is V1Direction.LONG else
        f"SUBSEQUENT_DIRECTIONAL_CROSSING_BELOW_{entry}"
    )

    stop_evidence: AuthoritativePriceEvidence | QualificationCandleEvidence | None
    invalidation_evidence: AuthoritativePriceEvidence | None
    target_source: str | None
    if evidence.setup_identity is TradeSetupIdentity.PULLBACK_CONTINUATION:
        stop_evidence = (
            evidence.governing_structural_low
            if direction is V1Direction.LONG else evidence.governing_structural_high
        )
        invalidation_evidence = (
            stop_evidence if isinstance(stop_evidence, AuthoritativePriceEvidence) else None
        )
        target_evidence = (
            evidence.prior_directional_swing_high
            if direction is V1Direction.LONG else evidence.prior_directional_swing_low
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
        stop_evidence = candle if candle_available else None
        stop_raw = (
            None if not candle_available else
            candle.low if direction is V1Direction.LONG else candle.high
        )
        stop_source = None if stop_evidence is None else stop_evidence.source
        invalidation_evidence = (
            evidence.original_range_high
            if direction is V1Direction.LONG else evidence.original_range_low
        )
        if evidence.original_range_high is None or evidence.original_range_low is None:
            raw_target = None
        else:
            width = evidence.original_range_high.price - evidence.original_range_low.price
            raw_target = (
                evidence.original_range_high.price + width
                if direction is V1Direction.LONG else
                evidence.original_range_low.price - width
            )
        target_evidence = (
            evidence.original_range_high
            if direction is V1Direction.LONG else evidence.original_range_low
        )
        target_source = None if target_evidence is None else target_evidence.source
        invalidation_condition = (
            "COMPLETED_DAILY_CLOSE_AT_OR_BELOW_ORIGINAL_RANGE_HIGH"
            if direction is V1Direction.LONG else
            "COMPLETED_DAILY_CLOSE_AT_OR_ABOVE_ORIGINAL_RANGE_LOW"
        )

    stop = (
        None if stop_raw is None else
        _round_tick(stop_raw, execution_context, up=direction is V1Direction.SHORT)
    )
    invalidation = (
        None if invalidation_evidence is None else
        _round_tick(invalidation_evidence.price, execution_context,
                    up=direction is V1Direction.SHORT)
    )
    target_candidate = (
        None if raw_target is None or raw_target <= 0 else
        _round_tick(raw_target, execution_context, up=direction is V1Direction.SHORT)
    )
    target_rejected = (
        entry is not None
        and target_candidate is not None
        and not _forward_target(entry, target_candidate, direction)
    )
    target = None if target_rejected else target_candidate
    barrier = (
        None if entry is None or target is None else
        _nearest_barrier(evidence, entry, target, direction)
    )
    if barrier is not None:
        target = _round_tick(barrier.price, execution_context,
                             up=direction is V1Direction.SHORT)

    risk = (
        None if entry is None or stop is None else
        entry - stop if direction is V1Direction.LONG else stop - entry
    )
    reward = (
        None if entry is None or target is None else
        target - entry if direction is V1Direction.LONG else entry - target
    )
    ratio = (
        reward / risk
        if risk is not None and reward is not None and risk > 0 and reward > 0
        else None
    )
    rr_state = (
        Step31RiskRewardState.AVAILABLE if ratio is not None else
        Step31RiskRewardState.INVALID if risk is not None and reward is not None else
        Step31RiskRewardState.UNAVAILABLE
    )

    warnings: list[Step31ObservationWarning] = []
    if entry is None:
        warnings.append(Step31ObservationWarning.ENTRY_UNAVAILABLE)
    if stop is None:
        warnings.append(Step31ObservationWarning.STOP_UNAVAILABLE)
    if target is None:
        warnings.append(Step31ObservationWarning.TARGET_UNAVAILABLE)
    if target_rejected:
        warnings.append(Step31ObservationWarning.TARGET_NOT_FORWARD_OF_ENTRY)
    if invalidation is None:
        warnings.append(Step31ObservationWarning.STRUCTURAL_GEOMETRY_WARNING)
    if risk is not None and risk <= 0:
        warnings.append(Step31ObservationWarning.NON_POSITIVE_RISK)
    warning_tuple = tuple(dict.fromkeys(warnings))
    red = any(item in {
        Step31ObservationWarning.TARGET_BELOW_ENTRY,
        Step31ObservationWarning.TARGET_ABOVE_ENTRY,
        Step31ObservationWarning.NON_POSITIVE_REWARD,
        Step31ObservationWarning.NON_POSITIVE_RISK,
    } for item in warning_tuple)
    severity = (
        Step31WarningSeverity.RED if red else
        Step31WarningSeverity.AMBER if warning_tuple else
        Step31WarningSeverity.GREEN
    )
    complete = all(item is not None for item in (entry, stop, target, invalidation))
    geometry_status = (
        Step31GeometryStatus.COMPLETE_FAVOURABLE if complete and not warning_tuple else
        Step31GeometryStatus.COMPLETE_WARNING if complete else
        Step31GeometryStatus.INCOMPLETE_WARNING
    )

    if conventional_plan is not None:
        if (
            type(conventional_plan) is not TradePlanRecord
            or conventional_plan.geometry_viability is not TradePlanStatus.TRADE_PLAN_READY
            or conventional_plan.native_run_identity != requirement.native_run_identity
            or conventional_plan.canonical_instrument != requirement.canonical_instrument
            or (conventional_plan.entry, conventional_plan.stop,
                conventional_plan.invalidation_reference,
                conventional_plan.setup_native_raw_target,
                conventional_plan.canonical_target,
                conventional_plan.risk_per_unit,
                conventional_plan.reward_per_unit,
                conventional_plan.risk_reward_ratio)
            != (entry, stop, invalidation, raw_target, target, risk, reward, ratio)
        ):
            raise Step31ObservationHardFailure("STEP31_OBSERVATION_TRADE_PLAN_BINDING_INVALID")

    seed = {
        "handoff": handoff.integrity_sha256,
        "evidence": evidence.package_sha256,
        "context": execution_context.identity,
        "policy": STEP31_OBSERVATION_POLICY_ID,
        "trade_construction_policy": TRADE_CONSTRUCTION_POLICY_ID,
    }
    observation_id = "STEP31-OBSERVATION-" + sha256(_canonical(seed)).hexdigest()
    rejected_lineage = (
        None
        if not target_rejected or target_evidence is None or raw_target is None
        else _target_candidate_lineage(evidence, target_evidence, raw_target)
    )
    fields = dict(
        contract_identity=STEP31_OBSERVATION_CONTRACT_ID,
        contract_version=STEP31_OBSERVATION_CONTRACT_VERSION,
        observation_evidence_id=observation_id,
        native_run_identity=requirement.native_run_identity,
        canonical_instrument=requirement.canonical_instrument,
        native_direction=direction,
        native_opportunity_identity=requirement.thesis.opportunity_identity,
        native_assessment_sha256=requirement.thesis.native_assessment_sha256,
        kr370_handoff_identity=handoff.handoff_identity,
        kr370_handoff_integrity_sha256=handoff.integrity_sha256,
        v3_readiness_identity=handoff.v3_readiness_identity,
        v3_readiness_sha256=handoff.v3_readiness_sha256,
        evidence_package_identity=evidence.package_identity,
        evidence_package_sha256=evidence.package_sha256,
        execution_context_identity=execution_context.identity,
        setup_identity=evidence.setup_identity,
        observation_boundary=evidence.observation_boundary,
        entry=entry,
        entry_availability=_availability(entry),
        entry_condition=entry_condition,
        entry_authority_source=None if not candle_available else candle.source,
        stop=stop,
        stop_availability=_availability(stop),
        stop_authority_source=stop_source,
        invalidation_reference=invalidation,
        invalidation_availability=_availability(invalidation),
        invalidation_condition=(None if invalidation is None else invalidation_condition),
        invalidation_authority_source=(None if invalidation_evidence is None else invalidation_evidence.source),
        setup_native_raw_target=raw_target,
        canonical_target=target,
        target_availability=_availability(target),
        target_authority_source=(
            None if target is None else
            barrier.source if barrier is not None else target_source
        ),
        material_barrier_identity=None if barrier is None else barrier.identity,
        material_barrier_reference=None if barrier is None else barrier.price,
        risk_per_unit=risk,
        reward_per_unit=reward,
        risk_reward_ratio=ratio,
        risk_reward_state=rr_state,
        trade_construction_policy_identity=TRADE_CONSTRUCTION_POLICY_ID,
        trade_construction_policy_version=TRADE_CONSTRUCTION_POLICY_VERSION,
        rejected_target_candidate_identity=(
            None if rejected_lineage is None else rejected_lineage[0]
        ),
        rejected_target_candidate_price=(None if not target_rejected else target_candidate),
        rejected_target_candidate_timeframe=(
            None if rejected_lineage is None else _timeframe_from_source(rejected_lineage[1])
        ),
        rejected_target_candidate_source=(
            None if rejected_lineage is None else rejected_lineage[1]
        ),
        rejected_target_candidate_boundary=(
            None if rejected_lineage is None else rejected_lineage[2]
        ),
        rejected_target_candidate_evidence_sha256=(
            None if rejected_lineage is None else rejected_lineage[3]
        ),
        rejected_target_candidate_provenance=(
            () if rejected_lineage is None else rejected_lineage[4]
        ),
        target_rejection_reason=("TARGET_NOT_FORWARD_OF_ENTRY" if target_rejected else None),
        warnings=warning_tuple,
        severity=severity,
        geometry_status=geometry_status,
        conventional_trade_plan_id=(None if conventional_plan is None else conventional_plan.trade_plan_id),
        conventional_trade_plan_sha256=(None if conventional_plan is None else conventional_plan.integrity_hash),
        provenance=tuple(dict.fromkeys((
            *requirement.thesis.provider_provenance,
            *requirement.thesis.calendar_provenance,
            *evidence.provenance,
            handoff.handoff_identity,
            handoff.integrity_sha256,
            execution_context.identity,
            STEP31_OBSERVATION_POLICY_ID,
            TRADE_CONSTRUCTION_POLICY_ID,
            "DOMAIN-001",
            "DOMAIN-008",
        ))),
        created_at=created_at,
        policy_identity=STEP31_OBSERVATION_POLICY_ID,
        policy_version=STEP31_OBSERVATION_POLICY_VERSION,
        authority=STEP31_OBSERVATION_AUTHORITY,
    )
    return Step31ObservationEvidence(
        **fields,
        integrity_sha256=sha256(_canonical(_primitive(fields | {"integrity_sha256": ""}))).hexdigest(),
    )


def create_sponsor_observation_handoff(
    observation: Step31ObservationEvidence,
    *,
    risk_state: str,
    risk_evidence_identity: str | None,
) -> Step31SponsorObservationHandoff:
    fields = dict(
        native_run_identity=observation.native_run_identity,
        canonical_instrument=observation.canonical_instrument,
        native_assessment_sha256=observation.native_assessment_sha256,
        kr370_handoff_identity=observation.kr370_handoff_identity,
        observation_evidence_id=observation.observation_evidence_id,
        observation_evidence_sha256=observation.integrity_sha256,
        conventional_trade_plan_id=observation.conventional_trade_plan_id,
        warnings=observation.warnings,
        severity=observation.severity,
        risk_state=risk_state,
        risk_evidence_identity=risk_evidence_identity,
        execution_context_identity=observation.execution_context_identity,
    )
    return Step31SponsorObservationHandoff(
        **fields,
        integrity_sha256=sha256(_canonical(_primitive(fields | {"integrity_sha256": ""}))).hexdigest(),
    )


def _validate_hard_inputs(requirement, handoff, evidence, context, created_at):  # type: ignore[no-untyped-def]
    if type(requirement) is not NativeReviewRequirement or type(handoff) is not Kr370Step31EligibilityHandoff:
        raise Step31ObservationHardFailure("STEP31_OBSERVATION_INPUT_INVALID")
    thesis = requirement.thesis
    if (
        handoff.native_run_identity != requirement.native_run_identity
        or handoff.canonical_instrument != requirement.canonical_instrument
        or handoff.native_assessment_sha256 != thesis.native_assessment_sha256
        or handoff.native_requirement_sha256 != requirement.requirement_sha256
        or handoff.native_opportunity_identity is not thesis.opportunity_identity
        or handoff.direction is not thesis.direction
    ):
        raise Step31ObservationHardFailure("STEP31_OBSERVATION_HANDOFF_BINDING_INVALID")
    if type(evidence) is not TradeConstructionEvidencePackage:
        raise Step31ObservationHardFailure("STEP31_OBSERVATION_EVIDENCE_BINDING_INVALID")
    if (
        evidence.native_run_identity != requirement.native_run_identity
        or evidence.canonical_instrument != requirement.canonical_instrument
        or evidence.native_assessment_sha256 != thesis.native_assessment_sha256
    ):
        raise Step31ObservationHardFailure("STEP31_OBSERVATION_EVIDENCE_BINDING_INVALID")
    if evidence.observation_boundary != handoff.analysis_boundary:
        raise Step31ObservationHardFailure("STEP31_OBSERVATION_EVIDENCE_STALE")
    if (
        type(context) is not CanonicalInstrumentContext
        or context.canonical_instrument != requirement.canonical_instrument
        or context.status is not InstrumentContextStatus.COMPLETE
        or context.tick_size is None
        or context.price_precision is None
    ):
        raise Step31ObservationHardFailure("STEP31_OBSERVATION_EXECUTION_CONTEXT_UNTRUSTED")
    if not _aware(created_at):
        raise Step31ObservationHardFailure("STEP31_OBSERVATION_CREATED_AT_INVALID")


def _availability(value: Decimal | None) -> Step31FactAvailability:
    return Step31FactAvailability.AVAILABLE if value is not None else Step31FactAvailability.UNAVAILABLE


def _round_tick(value: Decimal, context: CanonicalInstrumentContext, *, up: bool) -> Decimal:
    assert context.tick_size is not None and context.price_precision is not None
    units = value / context.tick_size
    rounded = units.to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR) * context.tick_size
    return rounded.quantize(Decimal(1).scaleb(-context.price_precision))


def _nearest_barrier(evidence, entry, target, direction):  # type: ignore[no-untyped-def]
    barriers = tuple(
        item for item in evidence.material_barriers
        if item.material and (
            entry < item.price < target if direction is V1Direction.LONG
            else target < item.price < entry
        )
    )
    return None if not barriers else min(barriers, key=lambda item: abs(item.price - entry))


def _forward_target(entry: Decimal, target: Decimal, direction: V1Direction) -> bool:
    return target > entry if direction is V1Direction.LONG else target < entry


def _timeframe_from_source(source: str) -> str | None:
    upper = source.upper()
    for token in ("4H", "1H", "DAILY", "WEEKLY"):
        if token in upper:
            return token
    return None


def _record_digest(record: Step31ObservationEvidence) -> str:
    payload = _primitive(record)
    if record.contract_identity == STEP31_OBSERVATION_CONTRACT_ID_V1:
        for key in (
            "trade_construction_policy_identity",
            "trade_construction_policy_version",
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
    payload["integrity_sha256"] = ""
    return sha256(_canonical(payload)).hexdigest()


def _handoff_digest(record: Step31SponsorObservationHandoff) -> str:
    payload = _primitive(record)
    payload["integrity_sha256"] = ""
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


def _record_from_dict(value: object) -> Step31ObservationEvidence:
    if type(value) is not dict:
        raise ValueError("STEP31_OBSERVATION_STORED_RECORD_INVALID")
    try:
        data = dict(value)
        for name in (
            "entry", "stop", "invalidation_reference", "setup_native_raw_target",
            "canonical_target", "material_barrier_reference", "risk_per_unit",
            "reward_per_unit", "risk_reward_ratio",
            "rejected_target_candidate_price",
        ):
            if name not in data:
                data[name] = None
            data[name] = None if data[name] is None else Decimal(data[name])
        legacy = data.get("contract_identity") == STEP31_OBSERVATION_CONTRACT_ID_V1
        data.setdefault(
            "trade_construction_policy_identity",
            TRADE_CONSTRUCTION_POLICY_ID_V0 if legacy else TRADE_CONSTRUCTION_POLICY_ID,
        )
        data.setdefault(
            "trade_construction_policy_version",
            TRADE_CONSTRUCTION_POLICY_VERSION_V0 if legacy else TRADE_CONSTRUCTION_POLICY_VERSION,
        )
        data.setdefault("rejected_target_candidate_identity", None)
        data.setdefault("rejected_target_candidate_timeframe", None)
        data.setdefault("rejected_target_candidate_source", None)
        data.setdefault("rejected_target_candidate_boundary", None)
        data.setdefault("rejected_target_candidate_evidence_sha256", None)
        data.setdefault("rejected_target_candidate_provenance", ())
        data.setdefault("target_rejection_reason", None)
        data["native_direction"] = V1Direction(data["native_direction"])
        data["native_opportunity_identity"] = NativeOpportunityIdentity(data["native_opportunity_identity"])
        data["setup_identity"] = TradeSetupIdentity(data["setup_identity"])
        for name in ("entry_availability", "stop_availability", "invalidation_availability", "target_availability"):
            data[name] = Step31FactAvailability(data[name])
        data["risk_reward_state"] = Step31RiskRewardState(data["risk_reward_state"])
        data["warnings"] = tuple(Step31ObservationWarning(item) for item in data["warnings"])
        data["severity"] = Step31WarningSeverity(data["severity"])
        data["geometry_status"] = Step31GeometryStatus(data["geometry_status"])
        data["observation_boundary"] = datetime.fromisoformat(data["observation_boundary"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data["rejected_target_candidate_boundary"] is not None:
            data["rejected_target_candidate_boundary"] = datetime.fromisoformat(
                data["rejected_target_candidate_boundary"]
            )
        data["provenance"] = tuple(data["provenance"])
        data["rejected_target_candidate_provenance"] = tuple(
            data["rejected_target_candidate_provenance"]
        )
        return Step31ObservationEvidence(**data)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("STEP31_OBSERVATION_STORED_RECORD_INVALID") from error


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("STEP31_OBSERVATION_STORED_RECORD_INVALID") from error
    if type(value) is not dict:
        raise ValueError("STEP31_OBSERVATION_STORED_RECORD_INVALID")
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


def _finite_decimal(value: object) -> bool:
    return type(value) is Decimal and value.is_finite()


def _positive_decimal(value: object) -> bool:
    return _finite_decimal(value) and value > 0


__all__ = [
    "LocalStep31ObservationStore",
    "STEP31_OBSERVATION_CONTRACT_ID",
    "STEP31_OBSERVATION_POLICY_ID",
    "Step31FactAvailability",
    "Step31GeometryStatus",
    "Step31ObservationEvidence",
    "Step31ObservationHardFailure",
    "Step31ObservationWarning",
    "Step31RiskRewardState",
    "Step31SponsorObservationHandoff",
    "Step31WarningSeverity",
    "construct_step31_observation",
    "create_sponsor_observation_handoff",
]
