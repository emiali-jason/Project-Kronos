"""WO-09 governed promotion and active-readiness policy.

The module composes exact WO-07F and already-governed machine/visual facts.  It
does not acquire evidence, reinterpret visual prose, or create trading authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Iterable

from kronos.intraday.visual_reconciliation_v2 import (
    DownstreamEligibility,
    VisualReconciliationOutcome,
    VisualReconciliationRecord,
)
from kronos.intraday.completed_evidence import (
    CompletedEvidenceSelection, is_completed_evidence_selection,
)
from kronos.intraday.probables_v2 import SemanticQualificationEvidenceV2
from kronos.intraday.review_mcx_paired_answer import McxPairedImportedVisualEvidence
from kronos.intraday.review_v2 import ImportedVisualEvidenceV2


POLICY_IDENTITY = "KRONOS-INTRADAY-WO-09-PROMOTION-READINESS-POLICY"
POLICY_VERSION = "1.0.0"
SCHEMA_IDENTITY = "KRONOS-INTRADAY-WO-09-READINESS-RECORD-V1"
SCHEMA_VERSION = "1.0.0"
REQUIREMENT_SCHEMA = "KRONOS-INTRADAY-WO-09-REQUIREMENT-RECORD-V1"
HANDOFF_SCHEMA = "KRONOS-INTRADAY-WO-09-NEXT-WO-HANDOFF-V1"
HISTORICAL_ELIGIBILITY_VALUE = "ELIGIBLE_FOR_WO10_EVALUATION"
ZERO_AUTHORITY = "NO_ENTRY_STOP_TARGET_RISK_CAPITAL_PAPER_LIVE_ORDER_FILL_OR_BROKER_AUTHORITY"

_POLICY_MATERIAL = {
    "criteria": ("I1", "I2", "I3", "I4", "I5"),
    "counts": {"0-2": "NO_FOCUS", "3": "NEAR_READY", "4": "DIRECTION_READY", "5": "DIRECTION_NOW"},
    "hard_gates": ("07F_CONTRADICTED", "07F_INSUFFICIENT", "07F_NOT_RECONCILABLE", "NATGAS_COMMISSIONING_HELD"),
    "unavailable": "READINESS_UNAVAILABLE",
    "numeric_gap": "NUMERIC_GAP_NOT_GOVERNED",
}
POLICY_CHECKSUM = sha256(json.dumps(_POLICY_MATERIAL, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CriterionId(StrEnum):
    I1 = "I1"
    I2 = "I2"
    I3 = "I3"
    I4 = "I4"
    I5 = "I5"


class CriterionState(StrEnum):
    SATISFIED = "SATISFIED"
    OUTSTANDING = "OUTSTANDING"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReadinessState(StrEnum):
    HARD_GATE = "HARD_GATE"
    READINESS_UNAVAILABLE = "READINESS_UNAVAILABLE"
    NO_FOCUS = "NO_FOCUS"
    NEAR_READY = "NEAR_READY"
    BUY_READY = "BUY_READY"
    SELL_READY = "SELL_READY"
    BUY_NOW = "BUY_NOW"
    SELL_NOW = "SELL_NOW"


class CurrentnessState(StrEnum):
    CURRENT = "CURRENT"
    REASSESSMENT_DUE = "REASSESSMENT_DUE"
    STALE_UNAVAILABLE = "STALE_UNAVAILABLE"
    SUPERSEDED = "SUPERSEDED"


class AttentionState(StrEnum):
    NONE = "NONE"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    NEXT_WO_ONLY = "NEXT_WO_ONLY"


class Monitorability(StrEnum):
    COMPLETED_CANDLE_REQUIRED = "COMPLETED_CANDLE_REQUIRED"
    FRESH_MACHINE_ANALYSIS_REQUIRED = "FRESH_MACHINE_ANALYSIS_REQUIRED"
    MARKET_SCHEDULE_EVENT_REQUIRED = "MARKET_SCHEDULE_EVENT_REQUIRED"
    FRESH_VISUAL_REVIEW_REQUIRED = "FRESH_VISUAL_REVIEW_REQUIRED"
    WO07F_RECONCILIATION_REQUIRED = "WO07F_RECONCILIATION_REQUIRED"
    NO_AUTOMATIC_NUMERIC_WATCH = "NO_AUTOMATIC_NUMERIC_WATCH"


class HardGate(StrEnum):
    NONE = "NONE"
    WO07F_CONTRADICTED = "07F_CONTRADICTED"
    WO07F_INSUFFICIENT = "07F_INSUFFICIENT"
    WO07F_NOT_RECONCILABLE = "07F_NOT_RECONCILABLE"
    NATGAS_COMMISSIONING_HELD = "NATGAS_COMMISSIONING_HELD"
    INVALID_EXACT_EVIDENCE_BINDING = "INVALID_EXACT_EVIDENCE_BINDING"
    GOVERNING_15M_STRUCTURE_FAILED = "GOVERNING_15M_STRUCTURE_FAILED"
    AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT = "AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT"


@dataclass(frozen=True, slots=True)
class Wo09Evidence:
    """Already-governed facts required by WO-09; no raw prose belongs here."""

    canonical_subject_identity: str
    market_family: str
    direction: str
    analysis_boundary: datetime
    session_identity: str
    one_hour_direction: str | None
    fifteen_minute_direction: str | None
    follow_through: str | None
    trade_space: str | None
    extension: str | None
    machine_evidence_identity: str
    machine_evidence_integrity: str
    visual_evidence_identity: str
    visual_evidence_integrity: str
    exact_mcx_contract_identity: str | None = None
    exact_mcx_roll_lineage: str | None = None
    exact_binding_valid: bool = True
    setup_quality_available: bool = True
    governing_15m_structure_failed: bool = False
    authoritative_directional_conflict: bool = False
    machine_progression_failure: bool = False
    natgas_commissioning_state: str | None = None

    def __post_init__(self) -> None:
        if (
            not _texts((self.canonical_subject_identity, self.market_family, self.direction,
                        self.session_identity, self.machine_evidence_identity,
                        self.machine_evidence_integrity, self.visual_evidence_identity,
                        self.visual_evidence_integrity))
            or self.direction not in {"LONG", "SHORT"}
            or not _aware(self.analysis_boundary)
            or any(type(value) is not bool for value in (
                self.exact_binding_valid, self.setup_quality_available,
                self.governing_15m_structure_failed,
                self.authoritative_directional_conflict,
                self.machine_progression_failure,
            ))
            or self.market_family == "MCX" and not _texts((
                self.exact_mcx_contract_identity, self.exact_mcx_roll_lineage,
            ))
        ):
            raise ValueError("WO09_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class CriterionSnapshot:
    criterion_id: CriterionId
    category: str
    state: CriterionState
    current_value: str | None
    required_value: str | None
    gap: str
    unit: str | None
    authority: str
    source_evidence_identity: str
    observation_boundary: datetime
    monitorability: tuple[Monitorability, ...]
    next_reassessment_trigger: str
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.criterion_id) is not CriterionId
            or type(self.state) is not CriterionState
            or not _texts((self.category, self.gap, self.authority,
                           self.source_evidence_identity, self.next_reassessment_trigger))
            or not _aware(self.observation_boundary)
            or any(type(item) is not Monitorability for item in self.monitorability)
            or any(not _text(item) for item in self.reason_codes)
        ):
            raise ValueError("WO09_CRITERION_INVALID")


@dataclass(frozen=True, slots=True)
class RequirementRecord:
    requirement_identity: str
    readiness_identity: str
    criterion: CriterionSnapshot
    watch_identity: str | None
    last_transition_at: datetime
    notification_state: str
    lifecycle_state: CurrentnessState
    integrity_identity: str
    schema_identity: str = REQUIREMENT_SCHEMA
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "requirement_identity", "integrity_identity")
        if (
            not _texts((self.readiness_identity, self.notification_state))
            or type(self.criterion) is not CriterionSnapshot
            or type(self.lifecycle_state) is not CurrentnessState
            or not _aware(self.last_transition_at)
            or self.schema_identity != REQUIREMENT_SCHEMA
            or self.schema_version != SCHEMA_VERSION
            or self.requirement_identity != _identity("INTRADAY-WO09-REQUIREMENT-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO09-REQUIREMENT-", values)
        ):
            raise ValueError("WO09_REQUIREMENT_INVALID")


@dataclass(frozen=True, slots=True)
class ReadinessRecord:
    readiness_identity: str
    integrity_identity: str
    canonical_subject_identity: str
    market_family: str
    exact_mcx_contract_identity: str | None
    exact_mcx_roll_lineage: str | None
    direction: str
    wo07f_identity: str
    wo07f_integrity: str
    wo07f_outcome: VisualReconciliationOutcome
    probables_run_identity: str
    probable_result_identity: str
    review_cycle_identity: str
    review_pack_identity: str
    chart_revision_identity: str
    answer_pack_identity: str
    answer_source_sha256: str
    correspondence_identity: str
    machine_evidence_identities: tuple[str, ...]
    machine_evidence_integrity: str
    visual_evidence_identity: str
    visual_evidence_integrity: str
    analysis_boundary: datetime
    session_identity: str
    criteria: tuple[CriterionSnapshot, ...]
    hard_gate: HardGate
    satisfied_count: int | None
    outstanding_count: int | None
    readiness_state: ReadinessState
    attention_state: AttentionState
    currentness: CurrentnessState
    created_at: datetime
    source_provenance: tuple[str, ...]
    policy_identity: str = POLICY_IDENTITY
    policy_version: str = POLICY_VERSION
    policy_checksum: str = POLICY_CHECKSUM
    authority: str = ZERO_AUTHORITY
    schema_identity: str = SCHEMA_IDENTITY
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "readiness_identity", "integrity_identity")
        if (
            not _texts((self.canonical_subject_identity, self.market_family, self.direction,
                        self.wo07f_identity, self.wo07f_integrity,
                        self.probables_run_identity, self.probable_result_identity,
                        self.review_cycle_identity, self.review_pack_identity,
                        self.chart_revision_identity, self.answer_pack_identity,
                        self.answer_source_sha256, self.correspondence_identity,
                        self.machine_evidence_integrity, self.visual_evidence_identity,
                        self.visual_evidence_integrity, self.session_identity))
            or self.direction not in {"LONG", "SHORT"}
            or type(self.wo07f_outcome) is not VisualReconciliationOutcome
            or tuple(item.criterion_id for item in self.criteria) != tuple(CriterionId)
            or type(self.hard_gate) is not HardGate
            or type(self.readiness_state) is not ReadinessState
            or type(self.attention_state) is not AttentionState
            or type(self.currentness) is not CurrentnessState
            or not _aware(self.analysis_boundary) or not _aware(self.created_at)
            or not _texts(self.machine_evidence_identities)
            or not _texts(self.source_provenance)
            or self.market_family not in {"NSE", "MCX"}
            or self.market_family == "MCX" and not _texts((
                self.exact_mcx_contract_identity, self.exact_mcx_roll_lineage,
            ))
            or self.policy_identity != POLICY_IDENTITY
            or self.policy_version != POLICY_VERSION
            or self.policy_checksum != POLICY_CHECKSUM
            or self.authority != ZERO_AUTHORITY
            or self.schema_identity != SCHEMA_IDENTITY
            or self.schema_version != SCHEMA_VERSION
            or not _valid_state(self)
            or self.readiness_identity != _identity("INTRADAY-WO09-READINESS-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO09-READINESS-", values)
        ):
            raise ValueError("WO09_READINESS_RECORD_INVALID")

    @property
    def outstanding(self) -> tuple[CriterionSnapshot, ...]:
        return tuple(item for item in self.criteria if item.state is CriterionState.OUTSTANDING)


@dataclass(frozen=True, slots=True)
class NextWoHandoff:
    handoff_identity: str
    integrity_identity: str
    readiness_identity: str
    readiness_integrity: str
    current_readiness_identity: str
    current_pointer_integrity: str
    currentness: CurrentnessState
    superseded_readiness_identity: str | None
    policy_identity: str
    policy_version: str
    policy_checksum: str
    canonical_subject_identity: str
    market_family: str
    direction: str
    exact_mcx_contract_identity: str | None
    exact_mcx_roll_lineage: str | None
    wo07f_identity: str
    wo07f_outcome: VisualReconciliationOutcome
    criteria: tuple[CriterionSnapshot, ...]
    satisfied_count: int
    hard_gate: HardGate
    readiness_state: ReadinessState
    analysis_boundary: datetime
    session_identity: str
    machine_evidence_identities: tuple[str, ...]
    machine_evidence_integrity: str
    visual_evidence_identity: str
    visual_evidence_integrity: str
    created_at: datetime
    first_five_of_five_at: datetime | None
    authority: str = ZERO_AUTHORITY
    schema_identity: str = HANDOFF_SCHEMA
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "handoff_identity", "integrity_identity")
        if (
            self.readiness_state not in {ReadinessState.BUY_NOW, ReadinessState.SELL_NOW}
            or self.satisfied_count != 5 or self.hard_gate is not HardGate.NONE
            or any(item.state is not CriterionState.SATISFIED for item in self.criteria)
            or self.currentness is not CurrentnessState.CURRENT
            or self.current_readiness_identity != self.readiness_identity
            or not _text(self.current_pointer_integrity)
            or self.authority != ZERO_AUTHORITY
            or self.schema_identity != HANDOFF_SCHEMA
            or self.schema_version != SCHEMA_VERSION
            or self.handoff_identity != _identity("INTRADAY-WO09-HANDOFF-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO09-HANDOFF-", values)
        ):
            raise ValueError("WO09_HANDOFF_INVALID")


class Wo07fCompatibilityAdapter:
    """Preserve the historical eligibility spelling while changing its destination."""

    identity = "KRONOS-INTRADAY-WO07F-TO-WO09-COMPATIBILITY-ADAPTER-V1"
    version = "1.0.0"

    @classmethod
    def eligible(cls, record: VisualReconciliationRecord) -> bool:
        if type(record) is not VisualReconciliationRecord:
            raise ValueError("WO09_WO07F_RECORD_INVALID")
        return (
            record.outcome in {VisualReconciliationOutcome.CONFIRMED, VisualReconciliationOutcome.CONDITIONAL}
            and record.downstream_eligibility.value == HISTORICAL_ELIGIBILITY_VALUE
        )


def build_wo09_evidence(
    record: VisualReconciliationRecord,
    semantic: SemanticQualificationEvidenceV2,
    selection: CompletedEvidenceSelection,
    visual: ImportedVisualEvidenceV2 | McxPairedImportedVisualEvidence,
    *,
    exact_mcx_contract_identity: str | None = None,
    exact_mcx_roll_lineage: str | None = None,
    natgas_commissioning_state: str | None = None,
) -> Wo09Evidence:
    """Adapt exact governed artifacts; never parse prose or acquire new facts."""
    machine_bindings = set(record.machine_evidence_identities)
    market_family = selection.market_identity
    nse_visual = type(visual) is ImportedVisualEvidenceV2
    mcx_visual = type(visual) is McxPairedImportedVisualEvidence
    visual_subject = (
        visual.resolved_canonical_subject_identity
        if nse_visual else visual.canonical_mcx_subject_identity
        if mcx_visual else None
    )
    visual_direction = (
        visual.proposed_direction if nse_visual else visual.direction if mcx_visual else None
    )
    if (
        type(record) is not VisualReconciliationRecord
        or type(semantic) is not SemanticQualificationEvidenceV2
        or not is_completed_evidence_selection(selection)
        or market_family not in {"NSE", "MCX"}
        or nse_visual != (market_family == "NSE")
        or mcx_visual != (market_family == "MCX")
        or len({record.canonical_subject_identity, semantic.canonical_subject_identity,
                selection.canonical_subject_identity, visual_subject}) != 1
        or semantic.completed_evidence_selection_identity != selection.selection_identity
        or record.visual_evidence_identity != visual.visual_evidence_identity
        or record.proposed_direction != visual_direction
        or record.review_cycle_identity != visual.review_cycle_identity
        or record.review_pack_identity != visual.review_pack_identity
        or record.answer_pack_identity != visual.answer_pack_identity
        or record.answer_source_sha256 != visual.answer_source_sha256
        or semantic.analysis_boundary != visual.analysis_boundary
        or semantic.evidence_identity not in machine_bindings
        or semantic.integrity_identity not in machine_bindings
        or selection.selection_identity not in machine_bindings
        or selection.integrity_identity not in machine_bindings
        or nse_visual and (
            record.probables_run_identity != visual.probables_run_identity
            or record.probable_result_identity != visual.probable_result_identity
            or record.chart_revision_identity != visual.chart_revision_identity
        )
        or mcx_visual and (
            visual.actual_derivative_contract_identity not in machine_bindings
            or visual.active_binding_identity not in machine_bindings
            or exact_mcx_contract_identity is not None
            and exact_mcx_contract_identity != visual.actual_derivative_contract_identity
            or exact_mcx_roll_lineage is not None
            and exact_mcx_roll_lineage != visual.active_binding_identity
        )
    ):
        raise ValueError("WO09_GOVERNED_SOURCE_BINDING_INVALID")
    observations = visual.answers if nse_visual else visual.native_answers
    by_id = {item.question_id: item.answer for item in observations}
    one_hour = semantic.fact("1H_REGIME").direction.value
    fifteen = semantic.fact("15M_STRUCTURE").direction.value
    conflicts = any(
        value in {"LONG", "SHORT"} and value != record.proposed_direction
        for value in (one_hour, fifteen)
    )
    return Wo09Evidence(
        canonical_subject_identity=record.canonical_subject_identity,
        market_family=market_family,
        direction=record.proposed_direction,
        analysis_boundary=semantic.analysis_boundary,
        session_identity=selection.current_market_session_identity,
        one_hour_direction=one_hour,
        fifteen_minute_direction=fifteen,
        follow_through=by_id.get("Q4") or by_id.get("M3"),
        trade_space=by_id.get("Q7"),
        extension=by_id.get("Q8"),
        machine_evidence_identity=semantic.evidence_identity,
        machine_evidence_integrity=semantic.integrity_identity,
        visual_evidence_identity=visual.visual_evidence_identity,
        visual_evidence_integrity=visual.integrity_identity,
        exact_mcx_contract_identity=(
            visual.actual_derivative_contract_identity if mcx_visual
            else exact_mcx_contract_identity
        ),
        exact_mcx_roll_lineage=(
            visual.active_binding_identity if mcx_visual else exact_mcx_roll_lineage
        ),
        authoritative_directional_conflict=conflicts,
        natgas_commissioning_state=natgas_commissioning_state,
    )


def evaluate_readiness(
    record: VisualReconciliationRecord,
    evidence: Wo09Evidence,
    *,
    created_at: datetime,
    provenance: tuple[str, ...] = ("WO07F_IMMUTABLE_LINEAGE", "WO09_POLICY_V1"),
) -> tuple[ReadinessRecord, tuple[RequirementRecord, ...]]:
    """Evaluate the frozen five criteria and build immutable bound evidence."""

    if type(record) is not VisualReconciliationRecord or type(evidence) is not Wo09Evidence:
        raise ValueError("WO09_INPUT_INVALID")
    if not _aware(created_at) or not _texts(provenance):
        raise ValueError("WO09_INPUT_INVALID")

    gate = _hard_gate(record, evidence)
    criteria = _not_applicable_criteria(evidence) if gate is not HardGate.NONE else (
        _i1(evidence), _i2(evidence), _i3(evidence), _i4(record, evidence), _i5(evidence)
    )
    if gate is not HardGate.NONE:
        satisfied = outstanding = None
        state = ReadinessState.HARD_GATE
    elif any(item.state is CriterionState.UNAVAILABLE for item in criteria):
        satisfied = outstanding = None
        state = ReadinessState.READINESS_UNAVAILABLE
    else:
        satisfied = sum(item.state is CriterionState.SATISFIED for item in criteria)
        outstanding = 5 - satisfied
        state = _readiness_state(evidence.direction, satisfied)
    attention = _attention(state)
    values = {
        "canonical_subject_identity": record.canonical_subject_identity,
        "market_family": evidence.market_family,
        "exact_mcx_contract_identity": evidence.exact_mcx_contract_identity,
        "exact_mcx_roll_lineage": evidence.exact_mcx_roll_lineage,
        "direction": record.proposed_direction,
        "wo07f_identity": record.reconciliation_identity,
        "wo07f_integrity": record.integrity_identity,
        "wo07f_outcome": record.outcome,
        "probables_run_identity": record.probables_run_identity,
        "probable_result_identity": record.probable_result_identity,
        "review_cycle_identity": record.review_cycle_identity,
        "review_pack_identity": record.review_pack_identity,
        "chart_revision_identity": record.chart_revision_identity,
        "answer_pack_identity": record.answer_pack_identity,
        "answer_source_sha256": record.answer_source_sha256,
        "correspondence_identity": record.correspondence_identity,
        "machine_evidence_identities": record.machine_evidence_identities,
        "machine_evidence_integrity": evidence.machine_evidence_integrity,
        "visual_evidence_identity": record.visual_evidence_identity,
        "visual_evidence_integrity": evidence.visual_evidence_integrity,
        "analysis_boundary": evidence.analysis_boundary,
        "session_identity": evidence.session_identity,
        "criteria": criteria,
        "hard_gate": gate,
        "satisfied_count": satisfied,
        "outstanding_count": outstanding,
        "readiness_state": state,
        "attention_state": attention,
        "currentness": CurrentnessState.CURRENT,
        "created_at": created_at,
        "source_provenance": provenance,
        "policy_identity": POLICY_IDENTITY,
        "policy_version": POLICY_VERSION,
        "policy_checksum": POLICY_CHECKSUM,
        "authority": ZERO_AUTHORITY,
        "schema_identity": SCHEMA_IDENTITY,
        "schema_version": SCHEMA_VERSION,
    }
    readiness = ReadinessRecord(
        readiness_identity=_identity("INTRADAY-WO09-READINESS-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO09-READINESS-", values),
        **values,
    )
    requirements = tuple(create_requirement(readiness, item, created_at) for item in criteria)
    return readiness, requirements


def create_requirement(readiness: ReadinessRecord, item: CriterionSnapshot, at: datetime) -> RequirementRecord:
    watch_identity = None
    if (
        readiness.attention_state in {AttentionState.NORMAL, AttentionState.HIGH}
        and item.state is CriterionState.OUTSTANDING
    ):
        watch_identity = prospective_watch_identity(
            readiness_identity=readiness.readiness_identity,
            criterion_id=item.criterion_id,
            subject=readiness.canonical_subject_identity,
            exact_contract=readiness.exact_mcx_contract_identity,
            source_fact_identity=item.source_evidence_identity,
            governed_trigger=item.next_reassessment_trigger,
        )
    values = {
        "readiness_identity": readiness.readiness_identity,
        "criterion": item,
        "watch_identity": watch_identity,
        "last_transition_at": at,
        "notification_state": "NOT_REQUESTED" if readiness.attention_state is AttentionState.NONE else "PROJECTABLE",
        "lifecycle_state": readiness.currentness,
        "schema_identity": REQUIREMENT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
    }
    return RequirementRecord(
        requirement_identity=_identity("INTRADAY-WO09-REQUIREMENT-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO09-REQUIREMENT-", values),
        **values,
    )


def prospective_watch_identity(*, readiness_identity: str, criterion_id: CriterionId,
                               subject: str, exact_contract: str | None,
                               source_fact_identity: str, governed_trigger: str) -> str:
    """Bind a requirement to its possible watch without activating that watch."""
    values = dict(
        readiness_identity=readiness_identity, criterion_id=criterion_id,
        canonical_subject_identity=subject, exact_contract_identity=exact_contract,
        source_fact_identity=source_fact_identity, governed_trigger=governed_trigger,
        policy_identity=POLICY_IDENTITY, policy_version=POLICY_VERSION,
        owner_identity="INTRADAY_WO09",
    )
    return _identity("INTRADAY-WO09-WATCH-", values)


def create_next_wo_handoff(
    readiness: ReadinessRecord,
    *,
    created_at: datetime,
    current_readiness_identity: str,
    current_pointer_integrity: str,
    currentness: CurrentnessState,
    superseded_readiness_identity: str | None,
    first_five_of_five_at: datetime | None = None,
) -> NextWoHandoff:
    if (
        readiness.currentness is not CurrentnessState.CURRENT
        or currentness is not CurrentnessState.CURRENT
        or current_readiness_identity != readiness.readiness_identity
        or not _text(current_pointer_integrity)
    ):
        raise ValueError("WO09_HANDOFF_SOURCE_NOT_CURRENT")
    values = {
        "readiness_identity": readiness.readiness_identity,
        "readiness_integrity": readiness.integrity_identity,
        "current_readiness_identity": current_readiness_identity,
        "current_pointer_integrity": current_pointer_integrity,
        "currentness": currentness,
        "superseded_readiness_identity": superseded_readiness_identity,
        "policy_identity": readiness.policy_identity,
        "policy_version": readiness.policy_version,
        "policy_checksum": readiness.policy_checksum,
        "canonical_subject_identity": readiness.canonical_subject_identity,
        "market_family": readiness.market_family,
        "direction": readiness.direction,
        "exact_mcx_contract_identity": readiness.exact_mcx_contract_identity,
        "exact_mcx_roll_lineage": readiness.exact_mcx_roll_lineage,
        "wo07f_identity": readiness.wo07f_identity,
        "wo07f_outcome": readiness.wo07f_outcome,
        "criteria": readiness.criteria,
        "satisfied_count": readiness.satisfied_count,
        "hard_gate": readiness.hard_gate,
        "readiness_state": readiness.readiness_state,
        "analysis_boundary": readiness.analysis_boundary,
        "session_identity": readiness.session_identity,
        "machine_evidence_identities": readiness.machine_evidence_identities,
        "machine_evidence_integrity": readiness.machine_evidence_integrity,
        "visual_evidence_identity": readiness.visual_evidence_identity,
        "visual_evidence_integrity": readiness.visual_evidence_integrity,
        "created_at": created_at,
        "first_five_of_five_at": first_five_of_five_at,
        "authority": ZERO_AUTHORITY,
        "schema_identity": HANDOFF_SCHEMA,
        "schema_version": SCHEMA_VERSION,
    }
    return NextWoHandoff(
        handoff_identity=_identity("INTRADAY-WO09-HANDOFF-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO09-HANDOFF-", values),
        **values,
    )


def artifact_bytes(value: object) -> bytes:
    return json.dumps(_primitive(value), sort_keys=True, separators=(",", ":")).encode()


def _hard_gate(record: VisualReconciliationRecord, evidence: Wo09Evidence) -> HardGate:
    if record.outcome is VisualReconciliationOutcome.CONTRADICTED:
        return HardGate.WO07F_CONTRADICTED
    if record.outcome is VisualReconciliationOutcome.INSUFFICIENT:
        return HardGate.WO07F_INSUFFICIENT
    if record.outcome is VisualReconciliationOutcome.NOT_RECONCILABLE:
        return HardGate.WO07F_NOT_RECONCILABLE
    if evidence.natgas_commissioning_state == "HELD" or record.canonical_subject_identity in {"MCX-SUBJECT-NATGAS", "MCX-FUT-NATGAS"}:
        return HardGate.NATGAS_COMMISSIONING_HELD
    if (
        not Wo07fCompatibilityAdapter.eligible(record)
        or not evidence.exact_binding_valid
        or record.canonical_subject_identity != evidence.canonical_subject_identity
        or record.proposed_direction != evidence.direction
        or record.visual_evidence_identity != evidence.visual_evidence_identity
        or evidence.machine_evidence_identity not in record.machine_evidence_identities
        or evidence.market_family == "MCX" and not evidence.exact_mcx_contract_identity
    ):
        return HardGate.INVALID_EXACT_EVIDENCE_BINDING
    if evidence.governing_15m_structure_failed:
        return HardGate.GOVERNING_15M_STRUCTURE_FAILED
    directional_conflict = any(
        value in {"LONG", "SHORT"} and value != evidence.direction
        for value in (evidence.one_hour_direction, evidence.fifteen_minute_direction)
    )
    if evidence.authoritative_directional_conflict or directional_conflict:
        return HardGate.AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT
    return HardGate.NONE


def _criterion(identifier: CriterionId, category: str, state: CriterionState,
               current: str | None, required: str | None, authority: str,
               evidence: Wo09Evidence, monitorability: tuple[Monitorability, ...],
               trigger: str, reasons: tuple[str, ...] = ()) -> CriterionSnapshot:
    return CriterionSnapshot(
        identifier, category, state, current, required,
        "NONE" if state is CriterionState.SATISFIED else "NUMERIC_GAP_NOT_GOVERNED",
        None, authority,
        evidence.machine_evidence_identity if authority == "MACHINE" else evidence.visual_evidence_identity,
        evidence.analysis_boundary, monitorability, trigger, reasons,
    )


def _i1(e: Wo09Evidence) -> CriterionSnapshot:
    vals = (e.one_hour_direction, e.fifteen_minute_direction)
    state = CriterionState.UNAVAILABLE if any(
        value is None or value == "UNAVAILABLE" for value in vals
    ) else (
        CriterionState.SATISFIED if vals == (e.direction, e.direction) else CriterionState.OUTSTANDING
    )
    return _criterion(CriterionId.I1, "DIRECTION_STRUCTURE", state,
                      f"1H={vals[0] or 'UNAVAILABLE'};15M={vals[1] or 'UNAVAILABLE'}",
                      f"1H={e.direction};15M={e.direction}", "MACHINE", e,
                      (Monitorability.COMPLETED_CANDLE_REQUIRED, Monitorability.FRESH_MACHINE_ANALYSIS_REQUIRED,
                       Monitorability.MARKET_SCHEDULE_EVENT_REQUIRED),
                      "NEXT_GOVERNED_COMPLETED_CANDLE_AND_FRESH_MACHINE_ANALYSIS")


def _i2(e: Wo09Evidence) -> CriterionSnapshot:
    mapping = {"CLEAR_FOLLOW_THROUGH": CriterionState.SATISFIED,
               "WEAK_OR_STALLING": CriterionState.OUTSTANDING, "MIXED": CriterionState.OUTSTANDING}
    state = mapping.get(e.follow_through, CriterionState.UNAVAILABLE)
    if e.machine_progression_failure and state is CriterionState.SATISFIED:
        state = CriterionState.OUTSTANDING
    return _criterion(CriterionId.I2, "ESTABLISHMENT_FOLLOW_THROUGH", state,
                      e.follow_through or "UNAVAILABLE", "CLEAR_FOLLOW_THROUGH", "COMPOSED", e,
                      (Monitorability.COMPLETED_CANDLE_REQUIRED, Monitorability.FRESH_MACHINE_ANALYSIS_REQUIRED,
                       Monitorability.FRESH_VISUAL_REVIEW_REQUIRED),
                      "FRESH_MACHINE_ANALYSIS_AND_RENEWED_VISUAL_RECONCILIATION")


def _i3(e: Wo09Evidence) -> CriterionSnapshot:
    mapping = {"CLEAR_SPACE": CriterionState.SATISFIED, "LIMITED_SPACE": CriterionState.OUTSTANDING,
               "OBSTACLE_CLOSE": CriterionState.OUTSTANDING}
    state = mapping.get(e.trade_space, CriterionState.UNAVAILABLE)
    return _criterion(CriterionId.I3, "PATH_OBSTACLE_CLEARANCE", state,
                      e.trade_space or "UNAVAILABLE", None, "WO07F_RECONCILED_VISUAL", e,
                      (Monitorability.FRESH_VISUAL_REVIEW_REQUIRED, Monitorability.NO_AUTOMATIC_NUMERIC_WATCH),
                      "FRESH_VISUAL_REVIEW")


_SETUP_REASONS = {
    "Q2_MIXED_STRUCTURE", "Q2_CONGESTED_STRUCTURE", "Q3_WEAK_OR_MIXED_BASE", "Q3_NO_CLEAR_BASE",
    "Q5_MIXED", "Q5_DISORDERLY", "Q5_NO_CLEAR_PULLBACK_OR_PROGRESSION",
    "M2_MIXED_STRUCTURE", "M2_CONGESTED_STRUCTURE", "M4_MIXED", "M4_DISORDERLY",
    "M4_NO_CLEAR_PULLBACK_OR_PROGRESSION",
}


def _i4(record: VisualReconciliationRecord, e: Wo09Evidence) -> CriterionSnapshot:
    active = tuple(item.reason_code for item in record.reasons if item.reason_code in _SETUP_REASONS)
    state = CriterionState.UNAVAILABLE if not e.setup_quality_available else (
        CriterionState.OUTSTANDING if active else CriterionState.SATISFIED
    )
    return _criterion(CriterionId.I4, "SETUP_QUALITY", state,
                      ",".join(active) if active else ("UNAVAILABLE" if not e.setup_quality_available else "NO_ACTIVE_DEGRADATION"),
                      "NO_ACTIVE_SETUP_QUALITY_DEGRADATION", "WO07F_REASON_LINEAGE", e,
                      (Monitorability.FRESH_VISUAL_REVIEW_REQUIRED, Monitorability.WO07F_RECONCILIATION_REQUIRED),
                      "FRESH_VISUAL_REVIEW_THEN_WO07F_RECONCILIATION", active)


def _i5(e: Wo09Evidence) -> CriterionSnapshot:
    mapping = {"NOT_VISIBLY_EXTENDED": CriterionState.SATISFIED,
               "VISIBLY_EXTENDED": CriterionState.OUTSTANDING, "MIXED": CriterionState.OUTSTANDING}
    state = mapping.get(e.extension, CriterionState.UNAVAILABLE)
    return _criterion(CriterionId.I5, "ANALYTICAL_VISUAL_EXTENSION", state,
                      e.extension or "UNAVAILABLE", "NOT_VISIBLY_EXTENDED", "WO07F_RECONCILED_VISUAL", e,
                      (Monitorability.FRESH_VISUAL_REVIEW_REQUIRED, Monitorability.WO07F_RECONCILIATION_REQUIRED),
                      "FRESH_VISUAL_REVIEW_THEN_WO07F_RECONCILIATION")


def _not_applicable_criteria(e: Wo09Evidence) -> tuple[CriterionSnapshot, ...]:
    return tuple(_criterion(identifier, category, CriterionState.NOT_APPLICABLE,
                            "NOT_APPLICABLE", None, authority, e, (), "NONE")
                 for identifier, category, authority in (
                     (CriterionId.I1, "DIRECTION_STRUCTURE", "MACHINE"),
                     (CriterionId.I2, "ESTABLISHMENT_FOLLOW_THROUGH", "COMPOSED"),
                     (CriterionId.I3, "PATH_OBSTACLE_CLEARANCE", "WO07F_RECONCILED_VISUAL"),
                     (CriterionId.I4, "SETUP_QUALITY", "WO07F_REASON_LINEAGE"),
                     (CriterionId.I5, "ANALYTICAL_VISUAL_EXTENSION", "WO07F_RECONCILED_VISUAL"),
                 ))


def _readiness_state(direction: str, count: int) -> ReadinessState:
    if count <= 2:
        return ReadinessState.NO_FOCUS
    if count == 3:
        return ReadinessState.NEAR_READY
    if count == 4:
        return ReadinessState.BUY_READY if direction == "LONG" else ReadinessState.SELL_READY
    return ReadinessState.BUY_NOW if direction == "LONG" else ReadinessState.SELL_NOW


def _attention(state: ReadinessState) -> AttentionState:
    if state is ReadinessState.NEAR_READY:
        return AttentionState.NORMAL
    if state in {ReadinessState.BUY_READY, ReadinessState.SELL_READY}:
        return AttentionState.HIGH
    if state in {ReadinessState.BUY_NOW, ReadinessState.SELL_NOW}:
        return AttentionState.NEXT_WO_ONLY
    return AttentionState.NONE


def _valid_state(record: ReadinessRecord) -> bool:
    if record.hard_gate is not HardGate.NONE:
        return (
            record.readiness_state is ReadinessState.HARD_GATE
            and record.attention_state is AttentionState.NONE
            and record.satisfied_count is None and record.outstanding_count is None
            and all(item.state is CriterionState.NOT_APPLICABLE for item in record.criteria)
        )
    if any(item.state is CriterionState.UNAVAILABLE for item in record.criteria):
        return (
            record.readiness_state is ReadinessState.READINESS_UNAVAILABLE
            and record.attention_state is AttentionState.NONE
            and record.satisfied_count is None and record.outstanding_count is None
            and all(item.state is not CriterionState.NOT_APPLICABLE for item in record.criteria)
        )
    if any(item.state is CriterionState.NOT_APPLICABLE for item in record.criteria):
        return False
    return (
        type(record.satisfied_count) is int and type(record.outstanding_count) is int
        and record.satisfied_count + record.outstanding_count == 5
        and record.satisfied_count == sum(item.state is CriterionState.SATISFIED for item in record.criteria)
        and record.outstanding_count == sum(item.state is CriterionState.OUTSTANDING for item in record.criteria)
        and record.readiness_state is _readiness_state(record.direction, record.satisfied_count)
        and record.attention_state is _attention(record.readiness_state)
    )


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(artifact_bytes(value)).hexdigest().upper()


def _without(value: object, *names: str) -> dict[str, object]:
    return {field.name: getattr(value, field.name) for field in fields(value) if field.name not in names}


def _primitive(value: object) -> object:
    if is_dataclass(value):
        return {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    return value


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: Iterable[object]) -> bool:
    return all(_text(value) for value in values)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None


__all__ = [
    "AttentionState", "CriterionId", "CriterionSnapshot", "CriterionState",
    "CurrentnessState", "HANDOFF_SCHEMA", "HISTORICAL_ELIGIBILITY_VALUE", "HardGate",
    "Monitorability", "NextWoHandoff", "POLICY_CHECKSUM", "POLICY_IDENTITY", "POLICY_VERSION",
    "ReadinessRecord", "ReadinessState", "RequirementRecord", "Wo07fCompatibilityAdapter",
    "Wo09Evidence", "ZERO_AUTHORITY", "artifact_bytes", "build_wo09_evidence",
    "create_next_wo_handoff", "evaluate_readiness", "prospective_watch_identity",
]
