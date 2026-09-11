"""WO-07F deterministic reconciliation of machine and qualified visual evidence.

This module owns analytical reconciliation only.  It does not select a trade,
change direction, calculate execution economics, or invoke downstream policy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Iterable

from kronos.intraday.review import ObservationStatus, ReviewError, ReviewFailure
from kronos.intraday.visual_contract_v2 import VisualObservationV2


POLICY_IDENTITY = "KRONOS-INTRADAY-WO-07F-VISUAL-RECONCILIATION-POLICY"
POLICY_VERSION = "1.0.0"
RECORD_SCHEMA = "KRONOS-INTRADAY-WO-07F-RECONCILIATION-RECORD-V1"
RECORD_SCHEMA_VERSION = "1.0.0"
POINTER_SCHEMA = "KRONOS-INTRADAY-WO-07F-CURRENT-POINTER-V1"
POINTER_SCHEMA_VERSION = "1.0.0"


class VisualReconciliationOutcome(StrEnum):
    CONFIRMED = "CONFIRMED"
    CONDITIONAL = "CONDITIONAL"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"
    NOT_RECONCILABLE = "NOT_RECONCILABLE"


class ReconciliationReasonClass(StrEnum):
    UPSTREAM_PREREQUISITE_FAILURE = "UPSTREAM_PREREQUISITE_FAILURE"
    HARD_CONTRADICTION = "HARD_CONTRADICTION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONDITIONAL_DEGRADATION = "CONDITIONAL_DEGRADATION"


class DownstreamEligibility(StrEnum):
    ELIGIBLE_FOR_WO10_EVALUATION = "ELIGIBLE_FOR_WO10_EVALUATION"
    NOT_ELIGIBLE_FOR_WO10_EVALUATION = "NOT_ELIGIBLE_FOR_WO10_EVALUATION"


class Q10Classification(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONDITIONAL_REASON = "CONDITIONAL_REASON"
    CONTRADICTION_REASON = "CONTRADICTION_REASON"
    NOT_DETERMINISTICALLY_CLASSIFIABLE = "NOT_DETERMINISTICALLY_CLASSIFIABLE"


class AnchorState(StrEnum):
    NOT_ESTABLISHED = "NOT_ESTABLISHED"
    ESTABLISHED = "ESTABLISHED"


class NativeMarketAuthority(StrEnum):
    NSE = "NSE"
    MCX = "MCX"


@dataclass(frozen=True, slots=True)
class ReconciliationPrerequisites:
    machine_review_current: bool = True
    answer_accepted: bool = True
    identity_bound: bool = True
    chart_bound: bool = True
    correspondence_confirmed: bool = True
    machine_sources_bound: bool = True
    native_mcx_contract_bound: bool = True


@dataclass(frozen=True, slots=True)
class GovernedAnchorContext:
    state: AnchorState = AnchorState.NOT_ESTABLISHED
    anchor_identity: str | None = None
    invalidating_observations: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        valid_ids = {"Q6", "Q9", "M5"}
        if self.state is AnchorState.NOT_ESTABLISHED:
            if self.anchor_identity is not None or self.invalidating_observations:
                raise ValueError("WO07F_ANCHOR_CONTEXT_INVALID")
            return
        if not _text(self.anchor_identity):
            raise ValueError("WO07F_ANCHOR_CONTEXT_INVALID")
        if any(
            type(item) is not tuple
            or len(item) != 2
            or item[0] not in valid_ids
            or not _text(item[1])
            for item in self.invalidating_observations
        ):
            raise ValueError("WO07F_ANCHOR_CONTEXT_INVALID")


@dataclass(frozen=True, slots=True)
class VisualReconciliationInput:
    canonical_subject_identity: str
    proposed_direction: str
    probables_run_identity: str
    probable_result_identity: str
    review_cycle_identity: str
    review_pack_identity: str
    chart_revision_identity: str
    answer_pack_identity: str
    answer_source_sha256: str
    visual_evidence_identity: str
    correspondence_identity: str
    machine_evidence_identities: tuple[str, ...]
    observations: tuple[VisualObservationV2, ...]
    prerequisites: ReconciliationPrerequisites = ReconciliationPrerequisites()
    anchor: GovernedAnchorContext = GovernedAnchorContext()
    q10_classification: Q10Classification = Q10Classification.NOT_APPLICABLE
    native_market: NativeMarketAuthority = NativeMarketAuthority.NSE
    supporting_reference_observations: tuple[VisualObservationV2, ...] = ()
    supporting_reference_authority: str | None = None
    supporting_reference_independence: str | None = None
    natgas_commissioning_state: str | None = None

    def __post_init__(self) -> None:
        identities = (
            self.canonical_subject_identity,
            self.probables_run_identity,
            self.probable_result_identity,
            self.review_cycle_identity,
            self.review_pack_identity,
            self.chart_revision_identity,
            self.answer_pack_identity,
            self.visual_evidence_identity,
            self.correspondence_identity,
        )
        if (
            not _texts(identities)
            or self.proposed_direction not in {"LONG", "SHORT"}
            or re.fullmatch(r"[0-9a-f]{64}", self.answer_source_sha256) is None
            or not _texts(self.machine_evidence_identities)
            or len(set(self.machine_evidence_identities))
            != len(self.machine_evidence_identities)
            or type(self.prerequisites) is not ReconciliationPrerequisites
            or type(self.anchor) is not GovernedAnchorContext
            or type(self.q10_classification) is not Q10Classification
            or type(self.native_market) is not NativeMarketAuthority
            or any(type(item) is not VisualObservationV2 for item in self.observations)
            or any(
                type(item) is not VisualObservationV2
                for item in self.supporting_reference_observations
            )
        ):
            raise ValueError("WO07F_INPUT_INVALID")
        ids = tuple(item.question_id for item in self.observations)
        required = (
            tuple(f"Q{index}" for index in range(1, 11))
            if self.native_market is NativeMarketAuthority.NSE
            else tuple(f"M{index}" for index in range(1, 6))
        )
        if ids != required:
            raise ValueError("WO07F_NATIVE_OBSERVATION_SET_INVALID")
        if self.native_market is NativeMarketAuthority.MCX:
            if (
                self.supporting_reference_authority
                != "SUPPORTING_VISUAL_CONTEXT_ONLY"
                or self.supporting_reference_independence
                != "NOT_INDEPENDENTLY_ESTABLISHED"
                or tuple(item.question_id for item in self.supporting_reference_observations)
                != tuple(f"R{index}" for index in range(1, 6))
                + tuple(f"X{index}" for index in range(1, 6))
            ):
                raise ValueError("WO07F_MCX_AUTHORITY_INVALID")
        elif self.supporting_reference_observations:
            raise ValueError("WO07F_REFERENCE_SCOPE_INVALID")
        escape = next(
            (
                item
                for item in self.observations
                + self.supporting_reference_observations
                if item.question_id in {"Q10", "X5"}
            ),
            None,
        )
        if escape is None or (
            escape.answer == "NONE"
            and self.q10_classification is not Q10Classification.NOT_APPLICABLE
        ) or (
            escape.answer == "MATERIAL_OBSERVATION"
            and self.q10_classification is Q10Classification.NOT_APPLICABLE
        ):
            raise ValueError("WO07F_RESIDUAL_CLASSIFICATION_INVALID")


@dataclass(frozen=True, slots=True)
class ReconciliationReason:
    reason_class: ReconciliationReasonClass
    reason_code: str
    question_id: str | None
    source_identity: str
    detail: str

    def __post_init__(self) -> None:
        if (
            type(self.reason_class) is not ReconciliationReasonClass
            or not _text(self.reason_code)
            or self.question_id is not None and not _text(self.question_id)
            or not _texts((self.source_identity, self.detail))
        ):
            raise ValueError("WO07F_REASON_INVALID")


@dataclass(frozen=True, slots=True)
class VisualReconciliationDecision:
    outcome: VisualReconciliationOutcome
    reasons: tuple[ReconciliationReason, ...]
    downstream_eligibility: DownstreamEligibility


@dataclass(frozen=True, slots=True)
class VisualReconciliationRecord:
    reconciliation_identity: str
    created_at: datetime
    canonical_subject_identity: str
    proposed_direction: str
    probables_run_identity: str
    probable_result_identity: str
    review_cycle_identity: str
    review_pack_identity: str
    chart_revision_identity: str
    answer_pack_identity: str
    answer_source_sha256: str
    visual_evidence_identity: str
    correspondence_identity: str
    machine_evidence_identities: tuple[str, ...]
    outcome: VisualReconciliationOutcome
    reasons: tuple[ReconciliationReason, ...]
    downstream_eligibility: DownstreamEligibility
    policy_identity: str
    policy_version: str
    input_identity: str
    integrity_identity: str
    schema_identity: str = RECORD_SCHEMA
    schema_version: str = RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        identities = (
            self.reconciliation_identity,
            self.canonical_subject_identity,
            self.probables_run_identity,
            self.probable_result_identity,
            self.review_cycle_identity,
            self.review_pack_identity,
            self.chart_revision_identity,
            self.answer_pack_identity,
            self.visual_evidence_identity,
            self.correspondence_identity,
            self.policy_identity,
            self.policy_version,
            self.input_identity,
            self.integrity_identity,
        )
        expected_reason_class = {
            VisualReconciliationOutcome.NOT_RECONCILABLE:
                ReconciliationReasonClass.UPSTREAM_PREREQUISITE_FAILURE,
            VisualReconciliationOutcome.CONTRADICTED:
                ReconciliationReasonClass.HARD_CONTRADICTION,
            VisualReconciliationOutcome.INSUFFICIENT:
                ReconciliationReasonClass.INSUFFICIENT_EVIDENCE,
            VisualReconciliationOutcome.CONDITIONAL:
                ReconciliationReasonClass.CONDITIONAL_DEGRADATION,
        }.get(self.outcome)
        analytically_eligible = self.outcome in {
            VisualReconciliationOutcome.CONFIRMED,
            VisualReconciliationOutcome.CONDITIONAL,
        }
        downstream_expected = (
            analytically_eligible
            and self.canonical_subject_identity != "MCX-SUBJECT-NATGAS"
        )
        if (
            not _texts(identities)
            or self.proposed_direction not in {"LONG", "SHORT"}
            or re.fullmatch(r"[0-9a-f]{64}", self.answer_source_sha256) is None
            or not _texts(self.machine_evidence_identities)
            or not _aware(self.created_at)
            or type(self.outcome) is not VisualReconciliationOutcome
            or type(self.downstream_eligibility) is not DownstreamEligibility
            or any(type(item) is not ReconciliationReason for item in self.reasons)
            or (self.outcome is VisualReconciliationOutcome.CONFIRMED)
            != (not self.reasons)
            or expected_reason_class is not None
            and any(item.reason_class is not expected_reason_class for item in self.reasons)
            or (
                self.downstream_eligibility
                is DownstreamEligibility.ELIGIBLE_FOR_WO10_EVALUATION
            )
            != downstream_expected
            or self.policy_identity != POLICY_IDENTITY
            or self.policy_version != POLICY_VERSION
            or self.schema_identity != RECORD_SCHEMA
            or self.schema_version != RECORD_SCHEMA_VERSION
        ):
            raise ValueError("WO07F_RECORD_INVALID")
        values = _record_values(self)
        if (
            self.reconciliation_identity
            != _identity("INTRADAY-WO07F-RECONCILIATION-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-WO07F-RECONCILIATION-", values)
        ):
            raise ValueError("WO07F_RECORD_INTEGRITY_INVALID")


@dataclass(frozen=True, slots=True)
class CurrentReconciliationPointer:
    review_cycle_identity: str
    reconciliation_identity: str
    input_identity: str
    integrity_identity: str
    schema_identity: str = POINTER_SCHEMA
    schema_version: str = POINTER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "integrity_identity")
        if (
            not _texts(
                (
                    self.review_cycle_identity,
                    self.reconciliation_identity,
                    self.input_identity,
                )
            )
            or self.schema_identity != POINTER_SCHEMA
            or self.schema_version != POINTER_SCHEMA_VERSION
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-WO07F-POINTER-", values)
        ):
            raise ValueError("WO07F_POINTER_INVALID")


_PREREQUISITE_ORDER = (
    ("machine_review_current", "MACHINE_REVIEW_NOT_CURRENT"),
    ("answer_accepted", "ANSWER_NOT_ACCEPTED"),
    ("identity_bound", "VISUAL_IDENTITY_NOT_BOUND"),
    ("chart_bound", "CHART_REVISION_NOT_BOUND"),
    ("correspondence_confirmed", "CORRESPONDENCE_NOT_CONFIRMED"),
    ("machine_sources_bound", "MACHINE_EVIDENCE_NOT_BOUND"),
    ("native_mcx_contract_bound", "NATIVE_MCX_CONTRACT_NOT_BOUND"),
)

_CONDITIONAL = {
    "Q1": {"OPPOSING", "MIXED"},
    "Q2": {"MIXED_STRUCTURE", "CONGESTED_STRUCTURE"},
    "Q3": {"WEAK_OR_MIXED_BASE", "NO_CLEAR_BASE"},
    "Q4": {"WEAK_OR_STALLING", "MIXED"},
    "Q5": {"MIXED", "DISORDERLY", "NO_CLEAR_PULLBACK_OR_PROGRESSION"},
    "Q7": {"LIMITED_SPACE", "OBSTACLE_CLOSE"},
    "Q8": {"VISIBLY_EXTENDED", "MIXED"},
    "M1": {"OPPOSING", "MIXED"},
    "M2": {"MIXED_STRUCTURE", "CONGESTED_STRUCTURE"},
    "M3": {"WEAK_OR_STALLING", "MIXED"},
    "M4": {"MIXED", "DISORDERLY", "NO_CLEAR_PULLBACK_OR_PROGRESSION"},
}

_REQUIRED_DETERMINATE = {"Q1", "Q2", "Q3", "Q4", "Q5", "Q7", "Q8", "Q10", "M1", "M2", "M3", "M4"}


def evaluate_visual_reconciliation(
    value: VisualReconciliationInput,
) -> VisualReconciliationDecision:
    """Apply the frozen matrix with stable precedence and reason order."""

    if type(value) is not VisualReconciliationInput:
        raise ValueError("WO07F_INPUT_INVALID")
    upstream = tuple(
        _reason(
            ReconciliationReasonClass.UPSTREAM_PREREQUISITE_FAILURE,
            code,
            None,
            value.correspondence_identity,
            code.replace("_", " ").title(),
        )
        for field, code in _PREREQUISITE_ORDER
        if not getattr(value.prerequisites, field)
        and (field != "native_mcx_contract_bound" or value.native_market is NativeMarketAuthority.MCX)
    )
    if upstream:
        return _decision(VisualReconciliationOutcome.NOT_RECONCILABLE, upstream)

    by_id = {item.question_id: item for item in value.observations}
    hard: list[ReconciliationReason] = []
    follow = by_id["Q4"] if value.native_market is NativeMarketAuthority.NSE else by_id["M3"]
    if follow.answer == "FAILED_OR_RETURNED_THROUGH":
        hard.append(
            _reason(
                ReconciliationReasonClass.HARD_CONTRADICTION,
                "SETUP_FAILED_OR_RETURNED_THROUGH",
                follow.question_id,
                value.visual_evidence_identity,
                f"{value.proposed_direction} setup is visibly failed or returned through.",
            )
        )
    invalidating = set(value.anchor.invalidating_observations)
    if value.anchor.state is AnchorState.ESTABLISHED:
        for question_id in ("Q6", "Q9", "M5"):
            item = by_id.get(question_id)
            if item is not None and (question_id, item.answer or "") in invalidating:
                hard.append(
                    _reason(
                        ReconciliationReasonClass.HARD_CONTRADICTION,
                        "GOVERNED_ANCHOR_INVALIDATES_DIRECTION",
                        question_id,
                        value.anchor.anchor_identity or value.visual_evidence_identity,
                        f"Governed {question_id} state invalidates the {value.proposed_direction} thesis.",
                    )
                )
    escape = (
        by_id["Q10"]
        if "Q10" in by_id
        else next(
            (
                item
                for item in value.supporting_reference_observations
                if item.question_id == "X5"
            ),
            None,
        )
    )
    if (
        escape is not None
        and escape.answer == "MATERIAL_OBSERVATION"
        and value.q10_classification is Q10Classification.CONTRADICTION_REASON
    ):
        hard.append(
            _reason(
                ReconciliationReasonClass.HARD_CONTRADICTION,
                f"{escape.question_id}_MATERIAL_CONTRADICTION",
                escape.question_id,
                value.visual_evidence_identity,
                escape.why_not_covered_elsewhere or "Governed Q10 contradiction.",
            )
        )
    if hard:
        return _decision(VisualReconciliationOutcome.CONTRADICTED, tuple(hard))

    insufficient: list[ReconciliationReason] = []
    for item in value.observations:
        neutral_anchor = (
            item.question_id in {"Q6", "Q9", "M5"}
            and value.anchor.state is AnchorState.NOT_ESTABLISHED
            and (
                item.answer == "NOT_OBSERVABLE"
                or item.observation_status
                in {
                    ObservationStatus.NOT_VISIBLE,
                    ObservationStatus.UNAVAILABLE,
                    ObservationStatus.NOT_APPLICABLE,
                }
            )
        )
        if neutral_anchor:
            continue
        if item.observation_status is not ObservationStatus.OBSERVED:
            insufficient.append(
                _reason(
                    ReconciliationReasonClass.INSUFFICIENT_EVIDENCE,
                    "REQUIRED_OBSERVATION_NOT_COMPLETE",
                    item.question_id,
                    value.visual_evidence_identity,
                    f"{item.question_id} status is {item.observation_status.value}.",
                )
            )
        elif item.question_id in _REQUIRED_DETERMINATE and item.answer in {"UNCLEAR", "NOT_OBSERVABLE"}:
            insufficient.append(
                _reason(
                    ReconciliationReasonClass.INSUFFICIENT_EVIDENCE,
                    "REQUIRED_OBSERVATION_UNCLEAR",
                    item.question_id,
                    value.visual_evidence_identity,
                    f"{item.question_id} does not establish a required analytical state.",
                )
            )
    if (
        escape is not None
        and escape.answer == "MATERIAL_OBSERVATION"
        and value.q10_classification
        is Q10Classification.NOT_DETERMINISTICALLY_CLASSIFIABLE
    ):
        insufficient.append(
            _reason(
                ReconciliationReasonClass.INSUFFICIENT_EVIDENCE,
                f"{escape.question_id}_MATERIAL_CLASSIFICATION_NOT_ESTABLISHED",
                escape.question_id,
                value.visual_evidence_identity,
                escape.why_not_covered_elsewhere or "Q10 cannot be classified deterministically.",
            )
        )
    if insufficient:
        return _decision(VisualReconciliationOutcome.INSUFFICIENT, tuple(insufficient))

    conditional: list[ReconciliationReason] = []
    for item in value.observations:
        if item.answer in _CONDITIONAL.get(item.question_id, set()):
            conditional.append(
                _reason(
                    ReconciliationReasonClass.CONDITIONAL_DEGRADATION,
                    f"{item.question_id}_{item.answer}",
                    item.question_id,
                    value.visual_evidence_identity,
                    f"{item.question_id} establishes {item.answer}.",
                )
            )
    if (
        escape is not None
        and escape.answer == "MATERIAL_OBSERVATION"
        and value.q10_classification is Q10Classification.CONDITIONAL_REASON
    ):
        conditional.append(
            _reason(
                ReconciliationReasonClass.CONDITIONAL_DEGRADATION,
                f"{escape.question_id}_MATERIAL_CONDITION",
                escape.question_id,
                value.visual_evidence_identity,
                escape.why_not_covered_elsewhere or "Governed Q10 condition.",
            )
        )
    if value.native_market is NativeMarketAuthority.MCX:
        conditional.extend(_reference_conditions(value))
    if conditional:
        return _decision(
            VisualReconciliationOutcome.CONDITIONAL,
            tuple(conditional),
            natgas_held=value.natgas_commissioning_state == "HELD",
        )
    return _decision(
        VisualReconciliationOutcome.CONFIRMED,
        (),
        natgas_held=value.natgas_commissioning_state == "HELD",
    )


def input_identity(value: VisualReconciliationInput) -> str:
    return _identity("INTRADAY-WO07F-INPUT-", _primitive(asdict(value)))


def create_reconciliation_record(
    value: VisualReconciliationInput,
    *,
    created_at: datetime,
) -> VisualReconciliationRecord:
    decision = evaluate_visual_reconciliation(value)
    values = {
        "created_at": created_at,
        "canonical_subject_identity": value.canonical_subject_identity,
        "proposed_direction": value.proposed_direction,
        "probables_run_identity": value.probables_run_identity,
        "probable_result_identity": value.probable_result_identity,
        "review_cycle_identity": value.review_cycle_identity,
        "review_pack_identity": value.review_pack_identity,
        "chart_revision_identity": value.chart_revision_identity,
        "answer_pack_identity": value.answer_pack_identity,
        "answer_source_sha256": value.answer_source_sha256,
        "visual_evidence_identity": value.visual_evidence_identity,
        "correspondence_identity": value.correspondence_identity,
        "machine_evidence_identities": value.machine_evidence_identities,
        "outcome": decision.outcome,
        "reasons": decision.reasons,
        "downstream_eligibility": decision.downstream_eligibility,
        "policy_identity": POLICY_IDENTITY,
        "policy_version": POLICY_VERSION,
        "input_identity": input_identity(value),
        "schema_identity": RECORD_SCHEMA,
        "schema_version": RECORD_SCHEMA_VERSION,
    }
    return VisualReconciliationRecord(
        reconciliation_identity=_identity(
            "INTRADAY-WO07F-RECONCILIATION-", _primitive(values)
        ),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-WO07F-RECONCILIATION-", _primitive(values)
        ),
        **values,
    )


def create_current_pointer(
    record: VisualReconciliationRecord,
) -> CurrentReconciliationPointer:
    values = {
        "review_cycle_identity": record.review_cycle_identity,
        "reconciliation_identity": record.reconciliation_identity,
        "input_identity": record.input_identity,
        "schema_identity": POINTER_SCHEMA,
        "schema_version": POINTER_SCHEMA_VERSION,
    }
    return CurrentReconciliationPointer(
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-WO07F-POINTER-", values
        ),
        **values,
    )


def artifact_bytes(value: object) -> bytes:
    return json.dumps(
        _primitive(asdict(value)), sort_keys=True, separators=(",", ":")
    ).encode() + b"\n"


def record_from_bytes(payload: bytes) -> VisualReconciliationRecord:
    try:
        document = json.loads(payload)
        document["created_at"] = datetime.fromisoformat(document["created_at"])
        document["outcome"] = VisualReconciliationOutcome(document["outcome"])
        document["downstream_eligibility"] = DownstreamEligibility(
            document["downstream_eligibility"]
        )
        document["machine_evidence_identities"] = tuple(
            document["machine_evidence_identities"]
        )
        document["reasons"] = tuple(
            ReconciliationReason(
                reason_class=ReconciliationReasonClass(item["reason_class"]),
                reason_code=item["reason_code"],
                question_id=item["question_id"],
                source_identity=item["source_identity"],
                detail=item["detail"],
            )
            for item in document["reasons"]
        )
        if set(document) != {field.name for field in fields(VisualReconciliationRecord)}:
            raise ValueError
        return VisualReconciliationRecord(**document)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("WO07F_RECORD_INVALID") from error


def pointer_from_bytes(payload: bytes) -> CurrentReconciliationPointer:
    try:
        document = json.loads(payload)
        if set(document) != {field.name for field in fields(CurrentReconciliationPointer)}:
            raise ValueError
        return CurrentReconciliationPointer(**document)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("WO07F_POINTER_INVALID") from error


def _reference_conditions(
    value: VisualReconciliationInput,
) -> tuple[ReconciliationReason, ...]:
    """Reference context may condition native evidence, never decide it."""

    conditions = []
    for item in value.supporting_reference_observations:
        if item.question_id == "X1" and item.answer in {
            "PARTIAL_CONFIRMATION",
            "CONFLICTS_WITH_REFERENCE",
        } or item.question_id == "X4" and item.answer in {
            "PARTIAL_DIVERGENCE",
            "MATERIAL_DIVERGENCE",
        }:
            conditions.append(
                _reason(
                    ReconciliationReasonClass.CONDITIONAL_DEGRADATION,
                    f"SUPPORTING_REFERENCE_{item.question_id}_{item.answer}",
                    item.question_id,
                    value.visual_evidence_identity,
                    f"Supporting-only reference context reports {item.answer}.",
                )
            )
    return tuple(conditions)


def _decision(
    outcome: VisualReconciliationOutcome,
    reasons: tuple[ReconciliationReason, ...],
    *,
    natgas_held: bool = False,
) -> VisualReconciliationDecision:
    eligibility = (
        DownstreamEligibility.ELIGIBLE_FOR_WO10_EVALUATION
        if not natgas_held and outcome
        in {
            VisualReconciliationOutcome.CONFIRMED,
            VisualReconciliationOutcome.CONDITIONAL,
        }
        else DownstreamEligibility.NOT_ELIGIBLE_FOR_WO10_EVALUATION
    )
    return VisualReconciliationDecision(outcome, reasons, eligibility)


def _reason(reason_class, reason_code, question_id, source_identity, detail):
    return ReconciliationReason(
        reason_class, reason_code, question_id, source_identity, detail
    )


def _record_values(value: VisualReconciliationRecord) -> dict[str, object]:
    return _primitive(
        _without(value, "reconciliation_identity", "integrity_identity")
    )


def _without(value: object, *names: str) -> dict[str, object]:
    return {
        field.name: getattr(value, field.name)
        for field in fields(value)
        if field.name not in names
    }


def _primitive(value):
    if is_dataclass(value):
        return _primitive(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _identity(prefix: str, value: object) -> str:
    payload = json.dumps(
        _primitive(value), sort_keys=True, separators=(",", ":")
    ).encode()
    return prefix + sha256(payload).hexdigest().upper()


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Iterable[object]) -> bool:
    return bool(values) and all(_text(value) for value in values)


def _aware(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "AnchorState",
    "CurrentReconciliationPointer",
    "DownstreamEligibility",
    "GovernedAnchorContext",
    "NativeMarketAuthority",
    "POLICY_IDENTITY",
    "POLICY_VERSION",
    "Q10Classification",
    "ReconciliationPrerequisites",
    "ReconciliationReason",
    "ReconciliationReasonClass",
    "VisualReconciliationDecision",
    "VisualReconciliationInput",
    "VisualReconciliationOutcome",
    "VisualReconciliationRecord",
    "artifact_bytes",
    "create_current_pointer",
    "create_reconciliation_record",
    "evaluate_visual_reconciliation",
    "input_identity",
    "pointer_from_bytes",
    "record_from_bytes",
]
