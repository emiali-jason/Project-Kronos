"""Deterministic WO-10 Native plus visual evidence reconciliation.

The module consumes immutable Intraday Probables and imported Chart Analyst
evidence.  It owns analytical Review, Readiness and Promotion only.  It has no
Entry, Trade Construction, Risk, Sponsor-decision or broker authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
import json
from typing import Iterable, Mapping

from kronos.intraday.probables import ProbableMemberResult, ProbableState, ProbablesRun
from kronos.intraday.review import ObservationStatus, ReviewCycle, ReviewQuestionPack
from kronos.intraday.review_answer import ImportedVisualEvidence


RECONCILIATION_POLICY_IDENTITY = "KRONOS-INTRADAY-NATIVE-VISUAL-RECONCILIATION-POLICY-V1"
RECONCILIATION_METHODOLOGY_IDENTITY = "KRONOS-INTRADAY-NATIVE-VISUAL-RECONCILIATION-METHODOLOGY-V1"
RECONCILIATION_FACT_IDENTITY = "KRONOS-INTRADAY-NATIVE-VISUAL-RECONCILIATION-FACT-V1"
RECONCILIATION_RUN_IDENTITY = "KRONOS-INTRADAY-RECONCILIATION-RUN-V1"
REVIEW_STATE_IDENTITY = "KRONOS-INTRADAY-REVIEW-STATE-V1"
READINESS_IDENTITY = "KRONOS-INTRADAY-READINESS-V1"
PROMOTION_IDENTITY = "KRONOS-INTRADAY-ANALYTICAL-PROMOTION-V1"
CURRENT_POINTER_IDENTITY = "KRONOS-INTRADAY-CURRENT-RECONCILIATION-POINTER-V1"
RECONCILIATION_CONTRACT_VERSION = "1.0.0"
POLICY_FAMILY = "POLICY_B_CORE_STRUCTURE"
STATUS_POLICY = "STATUS_POLICY_2_COMPLETE_IF_CORE_OBSERVED"


class ReconciliationFailure(StrEnum):
    INPUT_INVALID = "INTRADAY_RECONCILIATION_INPUT_INVALID"
    NOT_CURRENT = "INTRADAY_RECONCILIATION_NOT_CURRENT"
    EVIDENCE_INCOMPLETE = "INTRADAY_RECONCILIATION_EVIDENCE_INCOMPLETE"
    EVIDENCE_INVALID = "INTRADAY_RECONCILIATION_EVIDENCE_INVALID"
    RECONCILIATION_FAILED = "INTRADAY_RECONCILIATION_FAILED"
    POLICY_UNRESOLVED = "INTRADAY_RECONCILIATION_POLICY_UNRESOLVED"
    ARTIFACT_UNAVAILABLE = "INTRADAY_RECONCILIATION_ARTIFACT_UNAVAILABLE"
    INTEGRITY_INVALID = "INTRADAY_RECONCILIATION_INTEGRITY_INVALID"
    PERSISTENCE_CONFLICT = "INTRADAY_RECONCILIATION_PERSISTENCE_CONFLICT"


class ReconciliationError(RuntimeError):
    def __init__(self, failure: ReconciliationFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class QuestionRole(StrEnum):
    INFORMATIONAL = "INFORMATIONAL"
    MANDATORY_CORE_VISUAL_EVIDENCE = "MANDATORY_CORE_VISUAL_EVIDENCE"
    SUPPORTING_ADVERSE_NON_BLOCKING = "SUPPORTING_ADVERSE_NON_BLOCKING"
    ADVERSE_MANUAL_REVIEW = "ADVERSE_MANUAL_REVIEW"
    SUPPORTING_NON_BLOCKING = "SUPPORTING_NON_BLOCKING"
    SUPPORTING_MANUAL_REVIEW = "SUPPORTING_MANUAL_REVIEW"
    MANUAL_REVIEW_ESCAPE_HATCH = "MANUAL_REVIEW_ESCAPE_HATCH"


class EvidenceRelationship(StrEnum):
    SUPPORTIVE = "SUPPORTIVE"
    ADVERSE = "ADVERSE"
    NEUTRAL = "NEUTRAL"
    AMBIGUOUS = "AMBIGUOUS"
    INCOMPLETE = "INCOMPLETE"
    INFORMATIONAL = "INFORMATIONAL"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ReviewOutcomeState(StrEnum):
    REVIEW_INCOMPLETE = "REVIEW_INCOMPLETE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVIEW_COMPLETE = "REVIEW_COMPLETE"


class AnalyticalReadinessState(StrEnum):
    NOT_READY = "NOT_READY"
    ANALYTICALLY_READY = "ANALYTICALLY_READY"


class AnalyticalPromotionState(StrEnum):
    NOT_PROMOTED = "NOT_PROMOTED"
    PROMOTED = "PROMOTED"


class RemainingConditionIdentity(StrEnum):
    CORE_VISUAL_1H_NOT_SUPPORTIVE = "CORE_VISUAL_1H_NOT_SUPPORTIVE"
    CORE_VISUAL_15M_NOT_SUPPORTIVE = "CORE_VISUAL_15M_NOT_SUPPORTIVE"
    CORE_VISUAL_DIRECTION_AMBIGUOUS = "CORE_VISUAL_DIRECTION_AMBIGUOUS"
    CORE_VISUAL_EVIDENCE_INCOMPLETE = "CORE_VISUAL_EVIDENCE_INCOMPLETE"
    ONE_HOUR_MATERIAL_OVERLAP = "ONE_HOUR_MATERIAL_OVERLAP"
    FIFTEEN_MINUTE_CONTINUATION_STALLED = "FIFTEEN_MINUTE_CONTINUATION_STALLED"
    FIFTEEN_MINUTE_OPPOSING_STRUCTURE = "FIFTEEN_MINUTE_OPPOSING_STRUCTURE"
    LOCAL_REJECTION_AGAINST_DIRECTION = "LOCAL_REJECTION_AGAINST_DIRECTION"
    MATERIAL_VISUAL_OBSERVATION_REQUIRES_REVIEW = "MATERIAL_VISUAL_OBSERVATION_REQUIRES_REVIEW"
    SECONDARY_VISUAL_EVIDENCE_INCOMPLETE = "SECONDARY_VISUAL_EVIDENCE_INCOMPLETE"


class RemainingConditionClass(StrEnum):
    BLOCKING = "BLOCKING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    ADVERSE_NON_BLOCKING = "ADVERSE_NON_BLOCKING"
    INFORMATIONAL = "INFORMATIONAL"


_ROLE_BY_QUESTION = {
    "Q1": QuestionRole.INFORMATIONAL,
    "Q2": QuestionRole.MANDATORY_CORE_VISUAL_EVIDENCE,
    "Q3": QuestionRole.SUPPORTING_ADVERSE_NON_BLOCKING,
    "Q4": QuestionRole.MANDATORY_CORE_VISUAL_EVIDENCE,
    "Q5": QuestionRole.ADVERSE_MANUAL_REVIEW,
    "Q6": QuestionRole.SUPPORTING_NON_BLOCKING,
    "Q7": QuestionRole.INFORMATIONAL,
    "Q8": QuestionRole.INFORMATIONAL,
    "Q9": QuestionRole.SUPPORTING_MANUAL_REVIEW,
    "Q10": QuestionRole.MANUAL_REVIEW_ESCAPE_HATCH,
}
_CONDITION_CLASS = {
    RemainingConditionIdentity.CORE_VISUAL_1H_NOT_SUPPORTIVE: RemainingConditionClass.BLOCKING,
    RemainingConditionIdentity.CORE_VISUAL_15M_NOT_SUPPORTIVE: RemainingConditionClass.BLOCKING,
    RemainingConditionIdentity.CORE_VISUAL_DIRECTION_AMBIGUOUS: RemainingConditionClass.REVIEW_REQUIRED,
    RemainingConditionIdentity.CORE_VISUAL_EVIDENCE_INCOMPLETE: RemainingConditionClass.EVIDENCE_INCOMPLETE,
    RemainingConditionIdentity.ONE_HOUR_MATERIAL_OVERLAP: RemainingConditionClass.ADVERSE_NON_BLOCKING,
    RemainingConditionIdentity.FIFTEEN_MINUTE_CONTINUATION_STALLED: RemainingConditionClass.ADVERSE_NON_BLOCKING,
    RemainingConditionIdentity.FIFTEEN_MINUTE_OPPOSING_STRUCTURE: RemainingConditionClass.REVIEW_REQUIRED,
    RemainingConditionIdentity.LOCAL_REJECTION_AGAINST_DIRECTION: RemainingConditionClass.REVIEW_REQUIRED,
    RemainingConditionIdentity.MATERIAL_VISUAL_OBSERVATION_REQUIRES_REVIEW: RemainingConditionClass.REVIEW_REQUIRED,
    RemainingConditionIdentity.SECONDARY_VISUAL_EVIDENCE_INCOMPLETE: RemainingConditionClass.INFORMATIONAL,
}
_POLICY_MATRIX = (
    ("Q1", "INFORMATIONAL_NO_CONSEQUENCE"),
    ("Q2", "OBSERVED_SUPPORTIVE_REQUIRED;OPPOSING_BLOCKS;MIXED_OR_UNCLEAR_REVIEW;OTHER_INCOMPLETE"),
    ("Q3", "MATERIAL_OVERLAP_ADVERSE_NON_BLOCKING"),
    ("Q4", "OBSERVED_SUPPORTIVE_REQUIRED;OPPOSING_BLOCKS;MIXED_OR_UNCLEAR_REVIEW;OTHER_INCOMPLETE"),
    ("Q5", "STALLING_ADVERSE_NON_BLOCKING;OPPOSING_OR_BOTH_REVIEW"),
    ("Q6", "SUPPORTING_NON_BLOCKING_NO_ENTRY_AUTHORITY"),
    ("Q7", "INFORMATIONAL_NO_PATH_OR_RR_AUTHORITY"),
    ("Q8", "INFORMATIONAL_NO_WAIT_OR_ENTRY_AUTHORITY"),
    ("Q9", "REJECTION_AGAINST_DIRECTION_REVIEW;NO_ENTRY_TRIGGER_AUTHORITY"),
    ("Q10", "MATERIAL_OBSERVATION_REVIEW;FREE_TEXT_NOT_MACHINE_INTERPRETED"),
)


@dataclass(frozen=True, slots=True)
class ReconciliationPolicyPublication:
    publication_identity: str
    policy_identity: str
    policy_version: str
    methodology_identity: str
    methodology_version: str
    policy_family: str
    status_policy: str
    question_roles: tuple[tuple[str, QuestionRole], ...]
    policy_matrix: tuple[tuple[str, str], ...]
    condition_classes: tuple[tuple[RemainingConditionIdentity, RemainingConditionClass], ...]
    methodology_checksum_sha256: str
    integrity_identity: str
    authority: str = "RECONCILIATION_REVIEW_READINESS_PROMOTION_ONLY"
    schema_identity: str = RECONCILIATION_POLICY_IDENTITY
    schema_version: str = RECONCILIATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        content = _without(self, "publication_identity", "methodology_checksum_sha256", "integrity_identity")
        if (
            not self.publication_identity.startswith("INTRADAY-RECONCILIATION-POLICY-")
            or self.policy_identity != RECONCILIATION_POLICY_IDENTITY
            or self.policy_version != RECONCILIATION_CONTRACT_VERSION
            or self.methodology_identity != RECONCILIATION_METHODOLOGY_IDENTITY
            or self.methodology_version != RECONCILIATION_CONTRACT_VERSION
            or self.policy_family != POLICY_FAMILY
            or self.status_policy != STATUS_POLICY
            or self.question_roles != tuple(_ROLE_BY_QUESTION.items())
            or self.policy_matrix != _POLICY_MATRIX
            or self.condition_classes != tuple(_CONDITION_CLASS.items())
            or self.methodology_checksum_sha256 != sha256(_canonical(_normalize(content))).hexdigest()
            or self.authority != "RECONCILIATION_REVIEW_READINESS_PROMOTION_ONLY"
            or self.schema_identity != RECONCILIATION_POLICY_IDENTITY
            or self.schema_version != RECONCILIATION_CONTRACT_VERSION
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        _verify(self, "publication_identity", "INTRADAY-RECONCILIATION-POLICY-", "INTEGRITY-RECONCILIATION-POLICY-")


@dataclass(frozen=True, slots=True)
class RemainingCondition:
    condition_identity: RemainingConditionIdentity
    classification: RemainingConditionClass
    source_question_id: str
    source_visual_evidence_identity: str

    def __post_init__(self) -> None:
        if (
            self.classification is not _CONDITION_CLASS.get(self.condition_identity)
            or self.source_question_id not in _ROLE_BY_QUESTION
            or not _text(self.source_visual_evidence_identity)
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class ReconciliationFact:
    fact_identity: str
    question_id: str
    role: QuestionRole
    observation_status: ObservationStatus
    answer: str | None
    relationship: EvidenceRelationship
    conditions: tuple[RemainingCondition, ...]
    source_visual_evidence_identity: str
    integrity_identity: str
    schema_identity: str = RECONCILIATION_FACT_IDENTITY
    schema_version: str = RECONCILIATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.fact_identity.startswith("INTRADAY-RECONCILIATION-FACT-")
            or self.question_id not in _ROLE_BY_QUESTION
            or self.role is not _ROLE_BY_QUESTION[self.question_id]
            or type(self.observation_status) is not ObservationStatus
            or self.observation_status is ObservationStatus.INVALID
            or self.answer is not None and not _text(self.answer)
            or type(self.relationship) is not EvidenceRelationship
            or any(item.source_question_id != self.question_id for item in self.conditions)
            or not _text(self.source_visual_evidence_identity)
            or self.schema_identity != RECONCILIATION_FACT_IDENTITY
            or self.schema_version != RECONCILIATION_CONTRACT_VERSION
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        _verify(self, "fact_identity", "INTRADAY-RECONCILIATION-FACT-", "INTEGRITY-RECONCILIATION-FACT-")


@dataclass(frozen=True, slots=True)
class ReviewStateRecord:
    review_state_identity: str
    reconciliation_run_identity: str
    state: ReviewOutcomeState
    reason: str
    condition_identities: tuple[RemainingConditionIdentity, ...]
    integrity_identity: str
    schema_identity: str = REVIEW_STATE_IDENTITY
    schema_version: str = RECONCILIATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.review_state_identity.startswith("INTRADAY-REVIEW-STATE-")
            or not _text(self.reconciliation_run_identity)
            or type(self.state) is not ReviewOutcomeState
            or not _text(self.reason)
            or any(type(item) is not RemainingConditionIdentity for item in self.condition_identities)
            or self.schema_identity != REVIEW_STATE_IDENTITY
            or self.schema_version != RECONCILIATION_CONTRACT_VERSION
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        _verify(self, "review_state_identity", "INTRADAY-REVIEW-STATE-", "INTEGRITY-REVIEW-STATE-")


@dataclass(frozen=True, slots=True)
class ReadinessRecord:
    readiness_identity: str
    reconciliation_run_identity: str
    review_state_identity: str
    state: AnalyticalReadinessState
    reason: str
    integrity_identity: str
    schema_identity: str = READINESS_IDENTITY
    schema_version: str = RECONCILIATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.readiness_identity.startswith("INTRADAY-READINESS-")
            or not _texts((self.reconciliation_run_identity, self.review_state_identity, self.reason))
            or type(self.state) is not AnalyticalReadinessState
            or self.schema_identity != READINESS_IDENTITY
            or self.schema_version != RECONCILIATION_CONTRACT_VERSION
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        _verify(self, "readiness_identity", "INTRADAY-READINESS-", "INTEGRITY-READINESS-")


@dataclass(frozen=True, slots=True)
class PromotionRecord:
    promotion_identity: str
    reconciliation_run_identity: str
    readiness_identity: str
    state: AnalyticalPromotionState
    inherited_direction: str
    reason: str
    integrity_identity: str
    schema_identity: str = PROMOTION_IDENTITY
    schema_version: str = RECONCILIATION_CONTRACT_VERSION
    entry_authority: bool = False
    trade_construction_authority: bool = False
    risk_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        if (
            not self.promotion_identity.startswith("INTRADAY-PROMOTION-")
            or not _texts((self.reconciliation_run_identity, self.readiness_identity))
            or type(self.state) is not AnalyticalPromotionState
            or self.inherited_direction not in {"LONG", "SHORT"}
            or not _text(self.reason)
            or any((self.entry_authority, self.trade_construction_authority, self.risk_authority, self.broker_authority))
            or self.schema_identity != PROMOTION_IDENTITY
            or self.schema_version != RECONCILIATION_CONTRACT_VERSION
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        _verify(self, "promotion_identity", "INTRADAY-PROMOTION-", "INTEGRITY-PROMOTION-")


@dataclass(frozen=True, slots=True)
class ReconciliationRun:
    run_identity: str
    policy_publication_identity: str
    policy_checksum_sha256: str
    probables_run_identity: str
    probable_result_identity: str
    review_cycle_identity: str
    review_pack_identity: str
    chart_revision_identity: str
    answer_pack_identity: str
    visual_evidence_identity: str
    canonical_subject_identity: str
    inherited_direction: str
    facts: tuple[ReconciliationFact, ...]
    remaining_conditions: tuple[RemainingCondition, ...]
    review_state: ReviewStateRecord
    readiness: ReadinessRecord
    promotion: PromotionRecord
    established_at: object
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = RECONCILIATION_RUN_IDENTITY
    schema_version: str = RECONCILIATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.run_identity.startswith("INTRADAY-RECONCILIATION-RUN-")
            or not _texts((self.policy_publication_identity, self.policy_checksum_sha256,
                           self.probables_run_identity, self.probable_result_identity,
                           self.review_cycle_identity, self.review_pack_identity,
                           self.chart_revision_identity, self.answer_pack_identity,
                           self.visual_evidence_identity, self.canonical_subject_identity,
                           self.inherited_direction))
            or self.inherited_direction not in {"LONG", "SHORT"}
            or len(self.policy_checksum_sha256) != 64
            or tuple(item.question_id for item in self.facts) != tuple(_ROLE_BY_QUESTION)
            or self.remaining_conditions != tuple(item for fact in self.facts for item in fact.conditions)
            or self.review_state.reconciliation_run_identity != self.run_identity
            or self.readiness.reconciliation_run_identity != self.run_identity
            or self.readiness.review_state_identity != self.review_state.review_state_identity
            or self.promotion.reconciliation_run_identity != self.run_identity
            or self.promotion.readiness_identity != self.readiness.readiness_identity
            or self.promotion.inherited_direction != self.inherited_direction
            or not _aware(self.established_at)
            or not _texts(self.provenance)
            or self.schema_identity != RECONCILIATION_RUN_IDENTITY
            or self.schema_version != RECONCILIATION_CONTRACT_VERSION
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        answer_by_id = {item.question_id: item for item in self.facts}
        core_incomplete = any(
            answer_by_id[question].observation_status is not ObservationStatus.OBSERVED
            for question in ("Q2", "Q4")
        )
        manual = any(
            item.classification is RemainingConditionClass.REVIEW_REQUIRED
            for item in self.remaining_conditions
        )
        expected_review = (
            ReviewOutcomeState.REVIEW_INCOMPLETE
            if core_incomplete
            else ReviewOutcomeState.REVIEW_REQUIRED
            if manual
            else ReviewOutcomeState.REVIEW_COMPLETE
        )
        expected_ready = (
            self.review_state.state is ReviewOutcomeState.REVIEW_COMPLETE
            and all(
                answer_by_id[question].observation_status is ObservationStatus.OBSERVED
                and answer_by_id[question].answer == "SUPPORTIVE"
                for question in ("Q2", "Q4")
            )
        )
        if (
            self.review_state.state is not expected_review
            or (self.readiness.state is AnalyticalReadinessState.ANALYTICALLY_READY) != expected_ready
            or (self.promotion.state is AnalyticalPromotionState.PROMOTED) != expected_ready
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        seed = _without(
            self, "run_identity", "integrity_identity", "review_state", "readiness", "promotion"
        )
        complete = _without(self, "run_identity", "integrity_identity")
        if (
            self.run_identity != _identity("INTRADAY-RECONCILIATION-RUN-", seed)
            or self.integrity_identity
            != _identity("INTEGRITY-RECONCILIATION-RUN-", complete)
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class ReconciliationPointerEntry:
    probable_result_identity: str
    review_cycle_identity: str
    review_pack_identity: str
    visual_evidence_identity: str
    reconciliation_run_identity: str
    canonical_subject_identity: str
    inherited_direction: str

    def __post_init__(self) -> None:
        if (
            not _texts((self.probable_result_identity, self.review_cycle_identity,
                        self.review_pack_identity, self.visual_evidence_identity,
                        self.reconciliation_run_identity, self.canonical_subject_identity))
            or self.inherited_direction not in {"LONG", "SHORT"}
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class CurrentReconciliationPointer:
    probables_run_identity: str
    entries: tuple[ReconciliationPointerEntry, ...]
    integrity_identity: str
    schema_identity: str = CURRENT_POINTER_IDENTITY
    schema_version: str = RECONCILIATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not _text(self.probables_run_identity)
            or tuple(sorted(self.entries, key=lambda item: item.probable_result_identity)) != self.entries
            or len({item.probable_result_identity for item in self.entries}) != len(self.entries)
            or any(type(item) is not ReconciliationPointerEntry for item in self.entries)
            or self.schema_identity != CURRENT_POINTER_IDENTITY
            or self.schema_version != RECONCILIATION_CONTRACT_VERSION
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        _verify_integrity(self, "INTEGRITY-CURRENT-RECONCILIATION-POINTER-")


def create_v1_reconciliation_policy() -> ReconciliationPolicyPublication:
    values = {
        "policy_identity": RECONCILIATION_POLICY_IDENTITY,
        "policy_version": RECONCILIATION_CONTRACT_VERSION,
        "methodology_identity": RECONCILIATION_METHODOLOGY_IDENTITY,
        "methodology_version": RECONCILIATION_CONTRACT_VERSION,
        "policy_family": POLICY_FAMILY,
        "status_policy": STATUS_POLICY,
        "question_roles": tuple(_ROLE_BY_QUESTION.items()),
        "policy_matrix": _POLICY_MATRIX,
        "condition_classes": tuple(_CONDITION_CLASS.items()),
        "authority": "RECONCILIATION_REVIEW_READINESS_PROMOTION_ONLY",
        "schema_identity": RECONCILIATION_POLICY_IDENTITY,
        "schema_version": RECONCILIATION_CONTRACT_VERSION,
    }
    checksum = sha256(_canonical(_normalize(values))).hexdigest()
    identity_values = {**values, "methodology_checksum_sha256": checksum}
    return ReconciliationPolicyPublication(
        publication_identity=_identity("INTRADAY-RECONCILIATION-POLICY-", identity_values),
        methodology_checksum_sha256=checksum,
        integrity_identity=_identity("INTEGRITY-RECONCILIATION-POLICY-", identity_values),
        **values,
    )


def reconcile_native_visual_evidence(
    *,
    policy: ReconciliationPolicyPublication,
    probables_run: ProbablesRun,
    probable: ProbableMemberResult,
    cycle: ReviewCycle,
    question_pack: ReviewQuestionPack,
    visual_evidence: ImportedVisualEvidence,
) -> ReconciliationRun:
    if policy != create_v1_reconciliation_policy():
        raise ReconciliationError(ReconciliationFailure.POLICY_UNRESOLVED)
    _validate_bindings(probables_run, probable, cycle, question_pack, visual_evidence)
    facts = tuple(_fact(answer, visual_evidence.visual_evidence_identity) for answer in visual_evidence.answers)
    conditions = tuple(item for fact in facts for item in fact.conditions)
    core_incomplete = any(
        item.question_id in {"Q2", "Q4"} and item.observation_status is not ObservationStatus.OBSERVED
        for item in facts
    )
    manual = any(item.classification is RemainingConditionClass.REVIEW_REQUIRED for item in conditions)
    if core_incomplete:
        review_state, review_reason = ReviewOutcomeState.REVIEW_INCOMPLETE, "MANDATORY_CORE_VISUAL_EVIDENCE_INCOMPLETE"
    elif manual:
        review_state, review_reason = ReviewOutcomeState.REVIEW_REQUIRED, "GOVERNED_MANUAL_REVIEW_CONDITION_PRESENT"
    else:
        review_state, review_reason = ReviewOutcomeState.REVIEW_COMPLETE, "MANDATORY_CORE_VISUAL_EVIDENCE_OBSERVED"
    answer_by_id = {item.question_id: item for item in visual_evidence.answers}
    ready = (
        review_state is ReviewOutcomeState.REVIEW_COMPLETE
        and all(
            answer_by_id[question].observation_status is ObservationStatus.OBSERVED
            and answer_by_id[question].answer == "SUPPORTIVE"
            for question in ("Q2", "Q4")
        )
    )
    readiness_state = AnalyticalReadinessState.ANALYTICALLY_READY if ready else AnalyticalReadinessState.NOT_READY
    promotion_state = AnalyticalPromotionState.PROMOTED if ready else AnalyticalPromotionState.NOT_PROMOTED
    base = {
        "policy_publication_identity": policy.publication_identity,
        "policy_checksum_sha256": policy.methodology_checksum_sha256,
        "probables_run_identity": probables_run.run_identity,
        "probable_result_identity": probable.result_identity,
        "review_cycle_identity": cycle.cycle_identity,
        "review_pack_identity": question_pack.review_pack_identity,
        "chart_revision_identity": question_pack.chart_revision_identity,
        "answer_pack_identity": visual_evidence.answer_pack_identity,
        "visual_evidence_identity": visual_evidence.visual_evidence_identity,
        "canonical_subject_identity": probable.canonical_subject_identity,
        "inherited_direction": probable.direction.value,
        "facts": facts,
        "remaining_conditions": conditions,
        "established_at": visual_evidence.imported_at,
        "provenance": ("WO-10", probables_run.run_identity, visual_evidence.visual_evidence_identity, policy.publication_identity),
        "schema_identity": RECONCILIATION_RUN_IDENTITY,
        "schema_version": RECONCILIATION_CONTRACT_VERSION,
    }
    seed = _identity("INTRADAY-RECONCILIATION-RUN-", base)
    review = _review_record(seed, review_state, review_reason, conditions)
    readiness = _readiness_record(seed, review, readiness_state)
    promotion = _promotion_record(seed, readiness, promotion_state, probable.direction.value)
    values = {**base, "review_state": review, "readiness": readiness, "promotion": promotion}
    # The seed is the exact input identity; records bind it and do not recursively
    # influence that identity.  The run integrity covers the complete output.
    return ReconciliationRun(
        run_identity=seed,
        integrity_identity=_identity("INTEGRITY-RECONCILIATION-RUN-", values),
        **values,
    )


def create_current_reconciliation_pointer(
    probables_run_identity: str,
    entries: Iterable[ReconciliationPointerEntry],
) -> CurrentReconciliationPointer:
    retained = tuple(sorted(entries, key=lambda item: item.probable_result_identity))
    values = {
        "probables_run_identity": probables_run_identity,
        "entries": retained,
        "schema_identity": CURRENT_POINTER_IDENTITY,
        "schema_version": RECONCILIATION_CONTRACT_VERSION,
    }
    return CurrentReconciliationPointer(
        integrity_identity=_identity("INTEGRITY-CURRENT-RECONCILIATION-POINTER-", values),
        **values,
    )


def reconciliation_artifact_bytes(value: object) -> bytes:
    allowed = {
        ReconciliationPolicyPublication, ReconciliationFact, ReviewStateRecord,
        ReadinessRecord, PromotionRecord, ReconciliationRun, CurrentReconciliationPointer,
    }
    if type(value) not in allowed:
        raise ReconciliationError(ReconciliationFailure.INPUT_INVALID)
    return _canonical({"artifact_type": type(value).__name__, "value": _normalize(value)})


def reconciliation_artifact_from_bytes(payload: bytes) -> object:
    try:
        document = json.loads(payload.decode("utf-8"))
        if type(document) is not dict or set(document) != {"artifact_type", "value"} or type(document["value"]) is not dict:
            raise ValueError
        kind, raw = document["artifact_type"], dict(document["value"])
        if kind == "ReconciliationPolicyPublication":
            raw["question_roles"] = tuple((q, QuestionRole(role)) for q, role in raw["question_roles"])
            raw["policy_matrix"] = tuple(tuple(item) for item in raw["policy_matrix"])
            raw["condition_classes"] = tuple((RemainingConditionIdentity(c), RemainingConditionClass(k)) for c, k in raw["condition_classes"])
            return ReconciliationPolicyPublication(**raw)
        if kind == "ReconciliationFact":
            return _fact_from(raw)
        if kind == "ReviewStateRecord":
            raw["state"] = ReviewOutcomeState(raw["state"])
            raw["condition_identities"] = tuple(RemainingConditionIdentity(item) for item in raw["condition_identities"])
            return ReviewStateRecord(**raw)
        if kind == "ReadinessRecord":
            raw["state"] = AnalyticalReadinessState(raw["state"])
            return ReadinessRecord(**raw)
        if kind == "PromotionRecord":
            raw["state"] = AnalyticalPromotionState(raw["state"])
            return PromotionRecord(**raw)
        if kind == "ReconciliationRun":
            raw["facts"] = tuple(_fact_from(item) for item in raw["facts"])
            raw["remaining_conditions"] = tuple(_condition_from(item) for item in raw["remaining_conditions"])
            raw["review_state"] = _record_from("ReviewStateRecord", raw["review_state"])
            raw["readiness"] = _record_from("ReadinessRecord", raw["readiness"])
            raw["promotion"] = _record_from("PromotionRecord", raw["promotion"])
            from datetime import datetime
            raw["established_at"] = datetime.fromisoformat(raw["established_at"])
            raw["provenance"] = tuple(raw["provenance"])
            return ReconciliationRun(**raw)
        if kind == "CurrentReconciliationPointer":
            raw["entries"] = tuple(ReconciliationPointerEntry(**item) for item in raw["entries"])
            return CurrentReconciliationPointer(**raw)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, ReconciliationError) as error:
        raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID) from error
    raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)


def _record_from(kind: str, raw: Mapping[str, object]) -> object:
    values = dict(raw)
    if kind == "ReviewStateRecord":
        values["state"] = ReviewOutcomeState(values["state"])
        values["condition_identities"] = tuple(RemainingConditionIdentity(item) for item in values["condition_identities"])
        return ReviewStateRecord(**values)
    if kind == "ReadinessRecord":
        values["state"] = AnalyticalReadinessState(values["state"])
        return ReadinessRecord(**values)
    values["state"] = AnalyticalPromotionState(values["state"])
    return PromotionRecord(**values)


def _condition_from(raw: Mapping[str, object]) -> RemainingCondition:
    return RemainingCondition(
        condition_identity=RemainingConditionIdentity(raw["condition_identity"]),
        classification=RemainingConditionClass(raw["classification"]),
        source_question_id=raw["source_question_id"],
        source_visual_evidence_identity=raw["source_visual_evidence_identity"],
    )


def _fact_from(raw: Mapping[str, object]) -> ReconciliationFact:
    values = dict(raw)
    values["role"] = QuestionRole(values["role"])
    values["observation_status"] = ObservationStatus(values["observation_status"])
    values["relationship"] = EvidenceRelationship(values["relationship"])
    values["conditions"] = tuple(_condition_from(item) for item in values["conditions"])
    return ReconciliationFact(**values)


def _fact(answer, visual_identity: str) -> ReconciliationFact:  # type: ignore[no-untyped-def]
    relationship, identities = _consequence(answer.question_id, answer.observation_status, answer.answer)
    conditions = tuple(RemainingCondition(item, _CONDITION_CLASS[item], answer.question_id, visual_identity) for item in identities)
    values = {
        "question_id": answer.question_id,
        "role": _ROLE_BY_QUESTION[answer.question_id],
        "observation_status": answer.observation_status,
        "answer": answer.answer,
        "relationship": relationship,
        "conditions": conditions,
        "source_visual_evidence_identity": visual_identity,
        "schema_identity": RECONCILIATION_FACT_IDENTITY,
        "schema_version": RECONCILIATION_CONTRACT_VERSION,
    }
    return ReconciliationFact(
        fact_identity=_identity("INTRADAY-RECONCILIATION-FACT-", values),
        integrity_identity=_identity("INTEGRITY-RECONCILIATION-FACT-", values),
        **values,
    )


def _consequence(question: str, status: ObservationStatus, answer: str | None) -> tuple[EvidenceRelationship, tuple[RemainingConditionIdentity, ...]]:
    if status is ObservationStatus.INVALID:
        raise ReconciliationError(ReconciliationFailure.EVIDENCE_INVALID)
    if status is not ObservationStatus.OBSERVED:
        condition = (
            RemainingConditionIdentity.CORE_VISUAL_EVIDENCE_INCOMPLETE
            if question in {"Q2", "Q4"}
            else RemainingConditionIdentity.SECONDARY_VISUAL_EVIDENCE_INCOMPLETE
        )
        return EvidenceRelationship.INCOMPLETE, (condition,)
    if question in {"Q2", "Q4"}:
        if answer == "SUPPORTIVE":
            return EvidenceRelationship.SUPPORTIVE, ()
        if answer == "OPPOSING":
            condition = RemainingConditionIdentity.CORE_VISUAL_1H_NOT_SUPPORTIVE if question == "Q2" else RemainingConditionIdentity.CORE_VISUAL_15M_NOT_SUPPORTIVE
            return EvidenceRelationship.ADVERSE, (condition,)
        if answer in {"MIXED", "UNCLEAR"}:
            return EvidenceRelationship.AMBIGUOUS, (RemainingConditionIdentity.CORE_VISUAL_DIRECTION_AMBIGUOUS,)
    if question == "Q3" and answer == "MATERIAL_OVERLAP":
        return EvidenceRelationship.ADVERSE, (RemainingConditionIdentity.ONE_HOUR_MATERIAL_OVERLAP,)
    if question == "Q5":
        if answer == "STALLING_OR_FAILED_CONTINUATION":
            return EvidenceRelationship.ADVERSE, (RemainingConditionIdentity.FIFTEEN_MINUTE_CONTINUATION_STALLED,)
        if answer in {"OPPOSING_STRUCTURE_VISIBLE", "BOTH"}:
            return EvidenceRelationship.MANUAL_REVIEW, (RemainingConditionIdentity.FIFTEEN_MINUTE_OPPOSING_STRUCTURE,)
    if question == "Q9":
        if answer == "DIRECTIONAL_ACCEPTANCE":
            return EvidenceRelationship.SUPPORTIVE, ()
        if answer == "REJECTION_AGAINST_DIRECTION":
            return EvidenceRelationship.MANUAL_REVIEW, (RemainingConditionIdentity.LOCAL_REJECTION_AGAINST_DIRECTION,)
    if question == "Q10" and answer == "MATERIAL_OBSERVATION":
        return EvidenceRelationship.MANUAL_REVIEW, (RemainingConditionIdentity.MATERIAL_VISUAL_OBSERVATION_REQUIRES_REVIEW,)
    if question in {"Q1", "Q7", "Q8"}:
        return EvidenceRelationship.INFORMATIONAL, ()
    if answer in {"SUPPORTIVE", "ORDERLY", "DIRECTIONAL_ACCEPTANCE"}:
        return EvidenceRelationship.SUPPORTIVE, ()
    return EvidenceRelationship.NEUTRAL, ()


def _review_record(run_id: str, state: ReviewOutcomeState, reason: str, conditions: tuple[RemainingCondition, ...]) -> ReviewStateRecord:
    values = {
        "reconciliation_run_identity": run_id,
        "state": state,
        "reason": reason,
        "condition_identities": tuple(item.condition_identity for item in conditions),
        "schema_identity": REVIEW_STATE_IDENTITY,
        "schema_version": RECONCILIATION_CONTRACT_VERSION,
    }
    return ReviewStateRecord(
        review_state_identity=_identity("INTRADAY-REVIEW-STATE-", values),
        integrity_identity=_identity("INTEGRITY-REVIEW-STATE-", values),
        **values,
    )


def _readiness_record(run_id: str, review: ReviewStateRecord, state: AnalyticalReadinessState) -> ReadinessRecord:
    values = {
        "reconciliation_run_identity": run_id,
        "review_state_identity": review.review_state_identity,
        "state": state,
        "reason": "CORE_Q2_AND_Q4_SUPPORTIVE" if state is AnalyticalReadinessState.ANALYTICALLY_READY else "ANALYTICAL_READINESS_PREDICATES_NOT_SATISFIED",
        "schema_identity": READINESS_IDENTITY,
        "schema_version": RECONCILIATION_CONTRACT_VERSION,
    }
    return ReadinessRecord(
        readiness_identity=_identity("INTRADAY-READINESS-", values),
        integrity_identity=_identity("INTEGRITY-READINESS-", values),
        **values,
    )


def _promotion_record(run_id: str, readiness: ReadinessRecord, state: AnalyticalPromotionState, direction: str) -> PromotionRecord:
    values = {
        "reconciliation_run_identity": run_id,
        "readiness_identity": readiness.readiness_identity,
        "state": state,
        "inherited_direction": direction,
        "reason": "ANALYTICALLY_READY" if state is AnalyticalPromotionState.PROMOTED else "NOT_ANALYTICALLY_READY",
        "schema_identity": PROMOTION_IDENTITY,
        "schema_version": RECONCILIATION_CONTRACT_VERSION,
        "entry_authority": False,
        "trade_construction_authority": False,
        "risk_authority": False,
        "broker_authority": False,
    }
    return PromotionRecord(
        promotion_identity=_identity("INTRADAY-PROMOTION-", values),
        integrity_identity=_identity("INTEGRITY-PROMOTION-", values),
        **values,
    )


def _validate_bindings(run: ProbablesRun, probable: ProbableMemberResult, cycle: ReviewCycle, pack: ReviewQuestionPack, evidence: ImportedVisualEvidence) -> None:
    if probable not in run.results or probable.state not in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE} or probable.direction is None:
        raise ReconciliationError(ReconciliationFailure.INPUT_INVALID)
    expected = (
        (probable.result_identity, cycle.probable_result_identity, pack.probable_result_identity, evidence.probable_result_identity),
        (run.run_identity, cycle.probables_run_identity, pack.probables_run_identity, evidence.probables_run_identity),
        (probable.canonical_subject_identity, cycle.canonical_subject_identity, pack.expected_canonical_subject_identity, evidence.expected_canonical_subject_identity, evidence.observed_visible_subject_identity),
        (probable.direction.value, cycle.direction, pack.proposed_direction, evidence.proposed_direction),
        (cycle.cycle_identity, pack.review_cycle_identity, evidence.review_cycle_identity),
        (pack.review_pack_identity, evidence.review_pack_identity),
        (pack.review_request_identity, evidence.review_request_identity),
        (pack.chart_revision_identity, evidence.chart_revision_identity),
        (pack.chart_artifact_identity, evidence.chart_artifact_identity),
    )
    if any(len(set(values)) != 1 for values in expected) or evidence.global_observation_status is ObservationStatus.INVALID:
        raise ReconciliationError(ReconciliationFailure.EVIDENCE_INVALID)


def _verify(value: object, identity_name: str, identity_prefix: str, integrity_prefix: str) -> None:
    raw = _without(value, identity_name, "integrity_identity")
    if getattr(value, identity_name) != _identity(identity_prefix, raw) or getattr(value, "integrity_identity") != _identity(integrity_prefix, raw):
        raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)


def _verify_integrity(value: object, prefix: str) -> None:
    if getattr(value, "integrity_identity") != _identity(prefix, _without(value, "integrity_identity")):
        raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)


def _without(value: object, *names: str) -> dict[str, object]:
    return {name: item for name, item in asdict(value).items() if name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_canonical(_normalize(value))).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _normalize(value: object) -> object:
    from datetime import datetime
    if hasattr(value, "__dataclass_fields__"):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    from datetime import datetime
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Iterable[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


__all__ = [
    "CURRENT_POINTER_IDENTITY", "POLICY_FAMILY", "PROMOTION_IDENTITY",
    "READINESS_IDENTITY", "RECONCILIATION_CONTRACT_VERSION", "RECONCILIATION_FACT_IDENTITY",
    "RECONCILIATION_METHODOLOGY_IDENTITY", "RECONCILIATION_POLICY_IDENTITY",
    "RECONCILIATION_RUN_IDENTITY", "REVIEW_STATE_IDENTITY", "STATUS_POLICY",
    "AnalyticalPromotionState", "AnalyticalReadinessState", "CurrentReconciliationPointer",
    "EvidenceRelationship", "PromotionRecord", "QuestionRole", "ReadinessRecord",
    "ReconciliationError", "ReconciliationFact", "ReconciliationFailure",
    "ReconciliationPointerEntry", "ReconciliationPolicyPublication", "ReconciliationRun",
    "RemainingCondition", "RemainingConditionClass", "RemainingConditionIdentity",
    "ReviewOutcomeState", "ReviewStateRecord", "create_current_reconciliation_pointer",
    "create_v1_reconciliation_policy", "reconcile_native_visual_evidence",
    "reconciliation_artifact_bytes", "reconciliation_artifact_from_bytes",
]
