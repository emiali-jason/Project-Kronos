"""Frozen Native Layer-2 conditions and eight-state Readiness policy.

Evidence providers describe facts.  This module alone converts already-typed,
bound evidence into Native conditions and a Readiness result.  It has no trade
construction, Risk, Sponsor-decision, or execution authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
from threading import RLock

from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.native_discovery import Native1DState, Native1HState, Native4HState
from kronos.swing.v1.native_review import (
    McxReferenceEvidenceState,
    McxReferenceResult,
    NativeIndependentLayer2Evidence,
    NativeLayer2EvidenceState,
    NativeReviewRequirement,
)
from kronos.swing.v1.visual_evidence_v2 import (
    VISUAL_QUESTION_SET_V2_ID,
    VISUAL_QUESTION_SET_V2_VERSION,
    VisualEvidenceSubjectKind,
    VisualEvidenceV2Response,
    VisualObservationStatus,
    VisualQuestionRouting,
    VisualQuestionV2,
    visual_question_routing,
)


NATIVE_LAYER2_CONDITION_POLICY_ID = "SWING-V1-NATIVE-LAYER2-CONDITIONS-V0"
NATIVE_LAYER2_CONDITION_POLICY_VERSION = "0"
NATIVE_READINESS_POLICY_ID = "SWING-V1-NATIVE-LAYER2-READINESS-V0"
NATIVE_READINESS_POLICY_VERSION = "0"
NATIVE_POLICY_STATUS = "FROZEN"
NATIVE_READINESS_RECORD_SCHEMA = "KRONOS-SWING-V1-NATIVE-LAYER2-READINESS-V0"
NATIVE_READINESS_AUTHORITY = "READINESS_ONLY_NO_TRADE_GEOMETRY_OR_EXECUTION_AUTHORITY"


class ThesisIntact(StrEnum):
    YES = "YES"
    NO = "NO"
    UNAVAILABLE = "UNAVAILABLE"


class PullbackCondition(StrEnum):
    NONE = "NONE"
    DEVELOPING = "DEVELOPING"
    COMPLETE = "COMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class RetestCondition(StrEnum):
    NONE = "NONE"
    DEVELOPING = "DEVELOPING"
    COMPLETE = "COMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class ExtensionCondition(StrEnum):
    NONE = "NONE"
    MATERIAL_EXTENSION = "MATERIAL_EXTENSION"
    UNAVAILABLE = "UNAVAILABLE"


class DeteriorationCondition(StrEnum):
    NONE = "NONE"
    MEANINGFUL_DETERIORATION = "MEANINGFUL_DETERIORATION"
    UNAVAILABLE = "UNAVAILABLE"


class FailureCondition(StrEnum):
    NONE = "NONE"
    AFFIRMATIVE_FAILURE = "AFFIRMATIVE_FAILURE"
    UNAVAILABLE = "UNAVAILABLE"


class ObstacleCondition(StrEnum):
    NONE = "NONE"
    ADVERSE_NON_BLOCKING = "ADVERSE_NON_BLOCKING"
    ADVERSE_BLOCKING = "ADVERSE_BLOCKING"
    UNAVAILABLE = "UNAVAILABLE"


class PineCondition(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReferenceCondition(StrEnum):
    SUPPORTS = "SUPPORTS"
    NEUTRAL = "NEUTRAL"
    CONTRADICTS = "CONTRADICTS"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"


class LevelAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    LEVEL_UNAVAILABLE = "LEVEL_UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class NextConditionState(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NONE = "NONE"


class NativeReadinessState(StrEnum):
    READY_FOR_TRADE_CONSTRUCTION = "READY_FOR_TRADE_CONSTRUCTION"
    WAIT_PULLBACK_DEVELOPING = "WAIT_PULLBACK_DEVELOPING"
    WAIT_RETEST_DEVELOPING = "WAIT_RETEST_DEVELOPING"
    WAIT_OBSTACLE_CLEARANCE = "WAIT_OBSTACLE_CLEARANCE"
    EXTENDED_DO_NOT_CHASE = "EXTENDED_DO_NOT_CHASE"
    WEAKENING = "WEAKENING"
    INVALIDATED = "INVALIDATED"
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class ConditionEvidence:
    condition_identity: str
    source_evidence_ids: tuple[str, ...]
    timeframe: FactualTimeframe | None
    reference_identity: str | None
    level_availability: LevelAvailability
    price: float | None
    zone_low: float | None
    zone_high: float | None
    observation_boundary: datetime
    reason_code: str
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not _code(self.condition_identity)
            or not self.source_evidence_ids
            or any(not item for item in self.source_evidence_ids)
            or (self.timeframe is not None and type(self.timeframe) is not FactualTimeframe)
            or (self.reference_identity is not None and not self.reference_identity)
            or type(self.level_availability) is not LevelAvailability
            or not _level_shape(self.level_availability, self.price, self.zone_low, self.zone_high)
            or not _aware(self.observation_boundary)
            or not _code(self.reason_code)
            or not self.provenance
        ):
            raise ValueError("NATIVE_CONDITION_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class NextConditionEvidence:
    timeframe: FactualTimeframe
    condition_type: str
    required_event: str
    reference_identity: str
    level_availability: LevelAvailability
    price: float | None
    zone_low: float | None
    zone_high: float | None
    source_evidence_ids: tuple[str, ...]
    observation_boundary: datetime
    authority: str = "CHART_HEALTH_EVENT"

    def __post_init__(self) -> None:
        if (
            type(self.timeframe) is not FactualTimeframe
            or not _code(self.condition_type)
            or not _code(self.required_event)
            or not self.reference_identity
            or not _level_shape(self.level_availability, self.price, self.zone_low, self.zone_high)
            or not self.source_evidence_ids
            or not _aware(self.observation_boundary)
            or self.authority != "CHART_HEALTH_EVENT"
        ):
            raise ValueError("NATIVE_NEXT_CONDITION_INVALID")


@dataclass(frozen=True, slots=True)
class DeterministicRetestEvidence:
    reference: ConditionEvidence
    crossed_in_native_direction: bool
    returned_to_same_reference: bool
    reference_failed: bool
    outcome_resolved: bool
    accepted_away_in_native_direction: bool
    requires_unapproved_tolerance: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.reference) is not ConditionEvidence
            or self.reference.reference_identity is None
            or self.reference.level_availability is LevelAvailability.NOT_APPLICABLE
            or any(type(item) is not bool for item in (
                self.crossed_in_native_direction, self.returned_to_same_reference,
                self.reference_failed, self.outcome_resolved,
                self.accepted_away_in_native_direction,
                self.requires_unapproved_tolerance,
            ))
        ):
            raise ValueError("NATIVE_RETEST_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class DeterministicExtensionEvidence:
    structural_context: ConditionEvidence
    materially_beyond_recent_structure: bool

    def __post_init__(self) -> None:
        if type(self.structural_context) is not ConditionEvidence or type(self.materially_beyond_recent_structure) is not bool:
            raise ValueError("NATIVE_EXTENSION_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class DeterministicObstacleEvidence:
    obstacle: ConditionEvidence
    adverse_directional_path: bool
    clearance_required_for_trade_construction: bool

    def __post_init__(self) -> None:
        if (
            type(self.obstacle) is not ConditionEvidence
            or type(self.adverse_directional_path) is not bool
            or type(self.clearance_required_for_trade_construction) is not bool
        ):
            raise ValueError("NATIVE_OBSTACLE_EVIDENCE_INVALID")


@dataclass(frozen=True, slots=True)
class NativeConditionInputs:
    retest: DeterministicRetestEvidence | None = None
    extension: DeterministicExtensionEvidence | None = None
    obstacle: DeterministicObstacleEvidence | None = None
    next_condition: NextConditionEvidence | None = None

    def __post_init__(self) -> None:
        if (
            self.retest is not None and type(self.retest) is not DeterministicRetestEvidence
            or self.extension is not None and type(self.extension) is not DeterministicExtensionEvidence
            or self.obstacle is not None and type(self.obstacle) is not DeterministicObstacleEvidence
            or self.next_condition is not None and type(self.next_condition) is not NextConditionEvidence
        ):
            raise ValueError("NATIVE_CONDITION_INPUTS_INVALID")


@dataclass(frozen=True, slots=True)
class NativeLayer2Conditions:
    thesis_intact: ThesisIntact
    pullback_condition: PullbackCondition
    retest_condition: RetestCondition
    extension_condition: ExtensionCondition
    deterioration_condition: DeteriorationCondition
    failure_condition: FailureCondition
    obstacle_condition: ObstacleCondition
    pine_condition: PineCondition
    reference_condition: ReferenceCondition
    evidence_completeness: EvidenceCompleteness
    next_condition_state: NextConditionState
    next_condition: NextConditionEvidence | None
    evidence: tuple[ConditionEvidence, ...]
    condition_policy_identity: str = NATIVE_LAYER2_CONDITION_POLICY_ID
    condition_policy_version: str = NATIVE_LAYER2_CONDITION_POLICY_VERSION
    policy_status: str = NATIVE_POLICY_STATUS

    def __post_init__(self) -> None:
        if (
            any(type(value) is not expected for value, expected in (
                (self.thesis_intact, ThesisIntact),
                (self.pullback_condition, PullbackCondition),
                (self.retest_condition, RetestCondition),
                (self.extension_condition, ExtensionCondition),
                (self.deterioration_condition, DeteriorationCondition),
                (self.failure_condition, FailureCondition),
                (self.obstacle_condition, ObstacleCondition),
                (self.pine_condition, PineCondition),
                (self.reference_condition, ReferenceCondition),
                (self.evidence_completeness, EvidenceCompleteness),
                (self.next_condition_state, NextConditionState),
            ))
            or (self.next_condition_state is NextConditionState.AVAILABLE) != (self.next_condition is not None)
            or type(self.evidence) is not tuple
            or self.condition_policy_identity != NATIVE_LAYER2_CONDITION_POLICY_ID
            or self.condition_policy_version != NATIVE_LAYER2_CONDITION_POLICY_VERSION
            or self.policy_status != NATIVE_POLICY_STATUS
        ):
            raise ValueError("NATIVE_LAYER2_CONDITIONS_INVALID")


@dataclass(frozen=True, slots=True)
class NativeLayer2ReadinessRecord:
    run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    native_thesis_sha256: str
    native_evidence_ids: tuple[str, ...]
    visual_question_set_identity: str
    visual_question_set_version: str
    visual_bindings: tuple[tuple[str, str, str], ...]
    visual_evidence_hashes: tuple[str, ...]
    pine_evidence_identity: str | None
    reference_evidence_identity: str | None
    conditions: NativeLayer2Conditions
    readiness: NativeReadinessState
    primary_reason: str
    observation_boundary: datetime
    created_at: datetime
    provenance: tuple[str, ...]
    integrity_status: str
    result_sha256: str
    readiness_policy_identity: str = NATIVE_READINESS_POLICY_ID
    readiness_policy_version: str = NATIVE_READINESS_POLICY_VERSION
    policy_status: str = NATIVE_POLICY_STATUS
    authority: str = NATIVE_READINESS_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not self.run_identity
            or not self.canonical_instrument
            or not _digest(self.native_assessment_sha256)
            or not _digest(self.native_thesis_sha256)
            or not self.native_evidence_ids
            or self.visual_question_set_identity != VISUAL_QUESTION_SET_V2_ID
            or self.visual_question_set_version != VISUAL_QUESTION_SET_V2_VERSION
            or type(self.visual_bindings) is not tuple
            or any(len(item) != 3 or not _digest(item[2]) for item in self.visual_bindings)
            or type(self.visual_evidence_hashes) is not tuple
            or any(not _digest(item) for item in self.visual_evidence_hashes)
            or (self.pine_evidence_identity is not None and not self.pine_evidence_identity)
            or (self.reference_evidence_identity is not None and not self.reference_evidence_identity)
            or type(self.conditions) is not NativeLayer2Conditions
            or type(self.readiness) is not NativeReadinessState
            or not _code(self.primary_reason)
            or not _aware(self.observation_boundary)
            or not _aware(self.created_at)
            or not self.provenance
            or self.integrity_status != "PASSED"
            or not _digest(self.result_sha256)
            or self.result_sha256 != _record_digest(self)
            or self.readiness_policy_identity != NATIVE_READINESS_POLICY_ID
            or self.readiness_policy_version != NATIVE_READINESS_POLICY_VERSION
            or self.policy_status != NATIVE_POLICY_STATUS
            or self.authority != NATIVE_READINESS_AUTHORITY
        ):
            raise ValueError("NATIVE_LAYER2_READINESS_RECORD_INVALID")

    @property
    def step31_eligible(self) -> bool:
        return self.readiness is NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION


def build_native_layer2_conditions(
    requirement: NativeReviewRequirement,
    layer2: NativeIndependentLayer2Evidence,
    visual: tuple[VisualEvidenceV2Response, ...],
    *,
    reference: McxReferenceResult | None = None,
    inputs: NativeConditionInputs = NativeConditionInputs(),
) -> NativeLayer2Conditions:
    """Build typed conditions; free-form visual prose never owns a condition."""

    _validate_bindings(requirement, layer2, visual, reference)
    invalid, incomplete = _visual_completeness(requirement, visual)
    if any(state is NativeLayer2EvidenceState.UNAVAILABLE for _, state in layer2.timeframe_states):
        incomplete = True
    reference_condition = _reference_condition(requirement, reference)
    if reference_condition is ReferenceCondition.INVALID:
        invalid = True
    elif reference_condition is ReferenceCondition.UNAVAILABLE:
        incomplete = True
    completeness = (
        EvidenceCompleteness.INVALID if invalid else
        EvidenceCompleteness.INCOMPLETE if incomplete else
        EvidenceCompleteness.COMPLETE
    )
    thesis = requirement.thesis
    thesis_intact = (
        ThesisIntact.UNAVAILABLE
        if thesis.daily_state is Native1DState.UNAVAILABLE
        or thesis.four_hour_state is Native4HState.UNAVAILABLE
        else ThesisIntact.NO
        if thesis.four_hour_state is Native4HState.FAILED
        else ThesisIntact.YES
    )
    failure = (
        FailureCondition.UNAVAILABLE if thesis_intact is ThesisIntact.UNAVAILABLE else
        FailureCondition.AFFIRMATIVE_FAILURE if thesis_intact is ThesisIntact.NO else
        FailureCondition.NONE
    )
    pullback = (
        PullbackCondition.UNAVAILABLE if thesis_intact is ThesisIntact.UNAVAILABLE else
        PullbackCondition.DEVELOPING
        if thesis_intact is ThesisIntact.YES and thesis.four_hour_state is Native4HState.DEVELOPING_PULLBACK else
        PullbackCondition.NONE
    )
    deterioration = (
        DeteriorationCondition.UNAVAILABLE if thesis_intact is ThesisIntact.UNAVAILABLE else
        DeteriorationCondition.MEANINGFUL_DETERIORATION
        if thesis_intact is ThesisIntact.YES and (
            thesis.four_hour_state is Native4HState.DETERIORATING
            or (
                thesis.one_hour_state is Native1HState.DETERIORATING
                and thesis.four_hour_state not in {Native4HState.FAILED, Native4HState.UNAVAILABLE}
            )
        ) else DeteriorationCondition.NONE
    )
    retest = _retest_condition(inputs.retest)
    if retest is RetestCondition.UNAVAILABLE and completeness is EvidenceCompleteness.COMPLETE:
        completeness = EvidenceCompleteness.INCOMPLETE
    visual_extended = _visual_exact(visual, VisualQuestionV2.MATURITY_AND_CHASE_CONTEXT, "VISIBLY_EXTENDED")
    extension = (
        ExtensionCondition.MATERIAL_EXTENSION
        if thesis_intact is ThesisIntact.YES
        and failure is not FailureCondition.AFFIRMATIVE_FAILURE
        and visual_extended
        and inputs.extension is not None
        and inputs.extension.materially_beyond_recent_structure
        else ExtensionCondition.NONE
    )
    visual_obstacle = _visual_observed(visual, VisualQuestionV2.VISUAL_OBSTACLE_EVIDENCE)
    obstacle = (
        ObstacleCondition.NONE if inputs.obstacle is None or not visual_obstacle else
        ObstacleCondition.NONE if not inputs.obstacle.adverse_directional_path else
        ObstacleCondition.ADVERSE_BLOCKING
        if inputs.obstacle.clearance_required_for_trade_construction else
        ObstacleCondition.ADVERSE_NON_BLOCKING
    )
    pine = {
        NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS: PineCondition.SUPPORTS,
        NativeLayer2EvidenceState.CONTRADICTS_NATIVE_THESIS: PineCondition.CONTRADICTS,
        NativeLayer2EvidenceState.MIXED: PineCondition.UNAVAILABLE,
        NativeLayer2EvidenceState.UNAVAILABLE: PineCondition.UNAVAILABLE,
    }[layer2.pine_state]
    native_condition_evidence: list[ConditionEvidence] = []
    if pullback is PullbackCondition.DEVELOPING:
        native_condition_evidence.append(_native_condition_evidence(
            requirement, "PULLBACK", FactualTimeframe.FOUR_HOUR,
            "NATIVE_FOUR_HOUR_DEVELOPING_PULLBACK",
        ))
    if deterioration is DeteriorationCondition.MEANINGFUL_DETERIORATION:
        timeframe = (
            FactualTimeframe.FOUR_HOUR
            if thesis.four_hour_state is Native4HState.DETERIORATING
            else FactualTimeframe.ONE_HOUR
        )
        native_condition_evidence.append(_native_condition_evidence(
            requirement, "DETERIORATION", timeframe,
            f"NATIVE_{timeframe.value.replace('H', '_HOUR')}_DETERIORATING",
        ))
    if failure is FailureCondition.AFFIRMATIVE_FAILURE:
        native_condition_evidence.append(_native_condition_evidence(
            requirement, "FAILURE", FactualTimeframe.FOUR_HOUR,
            "NATIVE_FOUR_HOUR_AFFIRMATIVE_FAILURE",
        ))
    if pine in {PineCondition.SUPPORTS, PineCondition.CONTRADICTS}:
        native_condition_evidence.append(ConditionEvidence(
            "PINE", layer2.source_provenance, None, "PINE_VISIBLE_EVIDENCE",
            LevelAvailability.NOT_APPLICABLE, None, None, None,
            max(item.observation_boundary for item in thesis.timeframe_facts),
            f"PINE_{pine.value}", layer2.source_provenance,
        ))
    if reference is not None and reference_condition in {
        ReferenceCondition.SUPPORTS, ReferenceCondition.NEUTRAL,
        ReferenceCondition.CONTRADICTS,
    }:
        native_condition_evidence.append(ConditionEvidence(
            "REFERENCE", (reference.reference_evidence_sha256 or reference.requirement.requirement_sha256,),
            None, reference.requirement.reference_subject_identity,
            LevelAvailability.NOT_APPLICABLE, None, None, None,
            max((item[1] for item in reference.observation_boundaries), default=thesis.operative_anchor_boundary),
            f"REFERENCE_{reference_condition.value}", reference.source_provenance,
        ))
    condition_evidence = tuple(
        item for item in (
            inputs.retest.reference if inputs.retest is not None else None,
            inputs.extension.structural_context if inputs.extension is not None else None,
            inputs.obstacle.obstacle if inputs.obstacle is not None else None,
        ) if item is not None
    ) + tuple(native_condition_evidence)
    next_condition = inputs.next_condition
    if next_condition is None and pullback is PullbackCondition.DEVELOPING:
        next_condition = _pullback_next_condition(requirement)
    wait_possible = any((
        pullback is PullbackCondition.DEVELOPING,
        retest is RetestCondition.DEVELOPING,
        obstacle is ObstacleCondition.ADVERSE_BLOCKING,
        extension is ExtensionCondition.MATERIAL_EXTENSION,
        deterioration is DeteriorationCondition.MEANINGFUL_DETERIORATION,
    ))
    if not wait_possible:
        next_condition = None
    next_state = (
        NextConditionState.AVAILABLE if next_condition is not None else
        NextConditionState.UNAVAILABLE if wait_possible else
        NextConditionState.NONE
    )
    return NativeLayer2Conditions(
        thesis_intact, pullback, retest, extension, deterioration, failure,
        obstacle, pine, reference_condition, completeness, next_state,
        next_condition, condition_evidence,
    )


def resolve_native_readiness(conditions: NativeLayer2Conditions) -> tuple[NativeReadinessState, str]:
    """Apply the frozen categorical precedence exactly."""

    if type(conditions) is not NativeLayer2Conditions:
        raise TypeError("NATIVE_LAYER2_CONDITIONS_INVALID")
    if conditions.evidence_completeness is not EvidenceCompleteness.COMPLETE or conditions.thesis_intact is ThesisIntact.UNAVAILABLE:
        return NativeReadinessState.CONTEXT_INCOMPLETE, "REQUIRED_REVIEW_EVIDENCE_INCOMPLETE_OR_INVALID"
    if conditions.failure_condition is FailureCondition.AFFIRMATIVE_FAILURE or conditions.thesis_intact is ThesisIntact.NO:
        return NativeReadinessState.INVALIDATED, "AUTHORITATIVE_NATIVE_THESIS_FAILURE"
    if conditions.extension_condition is ExtensionCondition.MATERIAL_EXTENSION:
        return NativeReadinessState.EXTENDED_DO_NOT_CHASE, "MATERIAL_EXTENSION_FROM_RELEVANT_STRUCTURE"
    if conditions.deterioration_condition is DeteriorationCondition.MEANINGFUL_DETERIORATION:
        return NativeReadinessState.WEAKENING, "NATIVE_OPPORTUNITY_MEANINGFULLY_DETERIORATING"
    if conditions.pullback_condition is PullbackCondition.DEVELOPING:
        return NativeReadinessState.WAIT_PULLBACK_DEVELOPING, "AUTHORITATIVE_PULLBACK_STILL_DEVELOPING"
    if conditions.retest_condition is RetestCondition.DEVELOPING:
        return NativeReadinessState.WAIT_RETEST_DEVELOPING, "AUTHORITATIVE_RETEST_STILL_DEVELOPING"
    if conditions.obstacle_condition is ObstacleCondition.ADVERSE_BLOCKING:
        return NativeReadinessState.WAIT_OBSTACLE_CLEARANCE, "AUTHORITATIVE_OBSTACLE_REQUIRES_CLEARANCE"
    return NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION, "NO_APPROVED_READINESS_BLOCK_REMAINS"


def create_native_readiness_record(
    requirement: NativeReviewRequirement,
    layer2: NativeIndependentLayer2Evidence,
    visual: tuple[VisualEvidenceV2Response, ...],
    *,
    created_at: datetime,
    reference: McxReferenceResult | None = None,
    inputs: NativeConditionInputs = NativeConditionInputs(),
) -> NativeLayer2ReadinessRecord:
    conditions = build_native_layer2_conditions(
        requirement, layer2, visual, reference=reference, inputs=inputs,
    )
    readiness, reason = resolve_native_readiness(conditions)
    thesis_hash = sha256(_canonical(asdict(requirement.thesis))).hexdigest()
    reference_identity = (
        None if reference is None else
        reference.reference_evidence_sha256 or reference.requirement.requirement_sha256
    )
    fields = dict(
        run_identity=requirement.native_run_identity,
        canonical_instrument=requirement.canonical_instrument,
        native_assessment_sha256=requirement.thesis.native_assessment_sha256,
        native_thesis_sha256=thesis_hash,
        native_evidence_ids=layer2.source_provenance,
        visual_question_set_identity=VISUAL_QUESTION_SET_V2_ID,
        visual_question_set_version=VISUAL_QUESTION_SET_V2_VERSION,
        visual_bindings=tuple(
            (item.subject_identity, item.timeframe.value, item.chart_revision_sha256)
            for item in sorted(visual, key=lambda value: (value.subject_identity, value.timeframe.value))
        ),
        visual_evidence_hashes=tuple(item.evidence_sha256 for item in sorted(visual, key=lambda value: (value.subject_identity, value.timeframe.value))),
        pine_evidence_identity=(
            None if layer2.pine_state is NativeLayer2EvidenceState.UNAVAILABLE
            else next((item for item in layer2.source_provenance if "PINE" in item.upper()), layer2.source_provenance[-1])
        ),
        reference_evidence_identity=reference_identity,
        conditions=conditions,
        readiness=readiness,
        primary_reason=reason,
        observation_boundary=max(item.observation_boundary for item in requirement.thesis.timeframe_facts),
        created_at=created_at,
        provenance=tuple(dict.fromkeys((*requirement.thesis.provider_provenance, *layer2.source_provenance, *(item.evidence_sha256 for item in visual)))),
        integrity_status="PASSED",
    )
    digest_payload = {
        **fields,
        "result_sha256": "",
        "readiness_policy_identity": NATIVE_READINESS_POLICY_ID,
        "readiness_policy_version": NATIVE_READINESS_POLICY_VERSION,
        "policy_status": NATIVE_POLICY_STATUS,
        "authority": NATIVE_READINESS_AUTHORITY,
    }
    return NativeLayer2ReadinessRecord(
        result_sha256=sha256(_canonical(digest_payload)).hexdigest(),
        **fields,
    )


class NativeLayer2ReadinessStore:
    """Immutable integrity-checked combined Native Readiness persistence."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("NATIVE_READINESS_STORE_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, record: NativeLayer2ReadinessRecord) -> Path:
        if type(record) is not NativeLayer2ReadinessRecord:
            raise TypeError("NATIVE_LAYER2_READINESS_RECORD_INVALID")
        path = (
            self._root / record.run_identity
            / f"{record.canonical_instrument}--{record.result_sha256}.json"
        )
        payload = {"schema": NATIVE_READINESS_RECORD_SCHEMA, "record": _primitive(record)}
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("NATIVE_LAYER2_READINESS_RECORD_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def load_for_requirements(
        self,
        requirements: tuple[NativeReviewRequirement, ...],
        *,
        visual_evidence_hashes: frozenset[str] | None = None,
    ) -> tuple[NativeLayer2ReadinessRecord, ...]:
        if not requirements:
            return ()
        expected = {item.canonical_instrument: item for item in requirements}
        root = self._root / requirements[0].native_run_identity
        if not root.exists():
            return ()
        values = []
        for path in sorted(root.glob("*.json")):
            payload = _read(path)
            if payload.get("schema") != NATIVE_READINESS_RECORD_SCHEMA:
                raise ValueError("NATIVE_READINESS_RESTART_INTEGRITY_INVALID")
            record = _record_from_dict(payload.get("record"))
            requirement = expected.get(record.canonical_instrument)
            if (
                requirement is None
                or record.run_identity != requirement.native_run_identity
                or record.native_assessment_sha256 != requirement.thesis.native_assessment_sha256
                or record.native_thesis_sha256 != sha256(_canonical(asdict(requirement.thesis))).hexdigest()
            ):
                raise ValueError("NATIVE_READINESS_RESTART_BINDING_INVALID")
            if (
                visual_evidence_hashes is not None
                and not set(record.visual_evidence_hashes).issubset(
                    visual_evidence_hashes
                )
            ):
                continue
            values.append(record)
        selected: dict[str, NativeLayer2ReadinessRecord] = {}
        for record in values:
            current = selected.get(record.canonical_instrument)
            if current is None or (record.created_at, record.result_sha256) > (
                current.created_at,
                current.result_sha256,
            ):
                selected[record.canonical_instrument] = record
        return tuple(selected[key] for key in sorted(selected))


def sponsor_status(state: NativeReadinessState) -> str:
    return {
        NativeReadinessState.READY_FOR_TRADE_CONSTRUCTION: "READY FOR TRADE CONSTRUCTION",
        NativeReadinessState.WAIT_PULLBACK_DEVELOPING: "WAIT — PULLBACK DEVELOPING",
        NativeReadinessState.WAIT_RETEST_DEVELOPING: "WAIT — RETEST DEVELOPING",
        NativeReadinessState.WAIT_OBSTACLE_CLEARANCE: "WAIT — OBSTACLE CLEARANCE",
        NativeReadinessState.EXTENDED_DO_NOT_CHASE: "WAIT — DO NOT CHASE",
        NativeReadinessState.WEAKENING: "WAIT — WEAKENING",
        NativeReadinessState.INVALIDATED: "INVALIDATED / DISCARD FROM CURRENT TRADE PATH",
        NativeReadinessState.CONTEXT_INCOMPLETE: "CONTEXT INCOMPLETE",
    }[state]


def _retest_condition(value: DeterministicRetestEvidence | None) -> RetestCondition:
    if value is None:
        return RetestCondition.NONE
    if value.requires_unapproved_tolerance:
        return RetestCondition.UNAVAILABLE
    if value.reference_failed:
        return RetestCondition.NONE
    if value.crossed_in_native_direction and value.returned_to_same_reference:
        if value.outcome_resolved and value.accepted_away_in_native_direction:
            return RetestCondition.COMPLETE
        if not value.outcome_resolved:
            return RetestCondition.DEVELOPING
    return RetestCondition.NONE


def _pullback_next_condition(requirement: NativeReviewRequirement) -> NextConditionEvidence:
    thesis = requirement.thesis
    return NextConditionEvidence(
        FactualTimeframe.FOUR_HOUR,
        "PULLBACK_REVIEW",
        "REVIEW_FOR_RENEWED_PROGRESSION",
        thesis.operative_anchor_identity,
        LevelAvailability.AVAILABLE,
        thesis.operative_anchor_price,
        None,
        None,
        (thesis.native_assessment_sha256,),
        thesis.operative_anchor_boundary,
    )


def _native_condition_evidence(
    requirement: NativeReviewRequirement,
    identity: str,
    timeframe: FactualTimeframe,
    reason: str,
) -> ConditionEvidence:
    fact = next(item for item in requirement.thesis.timeframe_facts if item.timeframe is timeframe)
    return ConditionEvidence(
        identity,
        (requirement.thesis.native_assessment_sha256,),
        timeframe,
        requirement.thesis.operative_anchor_identity,
        LevelAvailability.AVAILABLE,
        requirement.thesis.operative_anchor_price,
        None,
        None,
        fact.observation_boundary,
        reason,
        fact.provenance,
    )


def _visual_completeness(requirement: NativeReviewRequirement, visual: tuple[VisualEvidenceV2Response, ...]) -> tuple[bool, bool]:
    native = tuple(item for item in visual if item.subject_kind is VisualEvidenceSubjectKind.NATIVE)
    by_timeframe = {item.timeframe.value: item for item in native}
    invalid = False
    incomplete = False
    for fact in requirement.thesis.timeframe_facts:
        response = by_timeframe.get(fact.timeframe.value)
        if response is None:
            incomplete = True
            continue
        for question, routing in visual_question_routing(response.timeframe):
            observation = next(item for item in response.observations if item.question_id is question)
            if (
                observation.observation_status is VisualObservationStatus.INVALID
                and routing is VisualQuestionRouting.YES
            ):
                invalid = True
            elif routing is VisualQuestionRouting.YES and observation.observation_status is not VisualObservationStatus.OBSERVED:
                incomplete = True
    return invalid, incomplete


def _reference_condition(requirement: NativeReviewRequirement, value: McxReferenceResult | None) -> ReferenceCondition:
    if requirement.mcx_reference is None:
        return ReferenceCondition.NOT_APPLICABLE
    if value is None:
        return ReferenceCondition.UNAVAILABLE
    return ReferenceCondition(value.evidence_state.value)


def _visual_exact(values: tuple[VisualEvidenceV2Response, ...], question: VisualQuestionV2, expected: str) -> bool:
    return any(
        item.question_id is question
        and item.observation_status is VisualObservationStatus.OBSERVED
        and item.observation.strip().upper() == expected
        for response in values for item in response.observations
    )


def _visual_observed(values: tuple[VisualEvidenceV2Response, ...], question: VisualQuestionV2) -> bool:
    return any(
        item.question_id is question and item.observation_status is VisualObservationStatus.OBSERVED
        for response in values for item in response.observations
    )


def _validate_bindings(requirement: NativeReviewRequirement, layer2: NativeIndependentLayer2Evidence, visual: tuple[VisualEvidenceV2Response, ...], reference: McxReferenceResult | None) -> None:
    if (
        type(requirement) is not NativeReviewRequirement
        or type(layer2) is not NativeIndependentLayer2Evidence
        or layer2.native_run_identity != requirement.native_run_identity
        or layer2.canonical_instrument != requirement.canonical_instrument
        or type(visual) is not tuple
        or any(
            item.native_run_identity != requirement.native_run_identity
            or item.native_assessment_sha256 != requirement.thesis.native_assessment_sha256
            or item.native_canonical_instrument != requirement.canonical_instrument
            for item in visual
        )
        or (reference is not None and reference.requirement != requirement.mcx_reference)
    ):
        raise ValueError("NATIVE_READINESS_EVIDENCE_BINDING_INVALID")


def _record_digest(record: NativeLayer2ReadinessRecord) -> str:
    payload = _primitive(record)
    payload["result_sha256"] = ""
    return sha256(_canonical(payload)).hexdigest()


def _primitive(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _record_from_dict(value: object) -> NativeLayer2ReadinessRecord:
    if type(value) is not dict:
        raise ValueError("NATIVE_READINESS_STORED_RECORD_INVALID")
    try:
        conditions_value = value["conditions"]
        evidence = tuple(_condition_from_dict(item) for item in conditions_value["evidence"])
        next_value = conditions_value["next_condition"]
        conditions = NativeLayer2Conditions(
            ThesisIntact(conditions_value["thesis_intact"]),
            PullbackCondition(conditions_value["pullback_condition"]),
            RetestCondition(conditions_value["retest_condition"]),
            ExtensionCondition(conditions_value["extension_condition"]),
            DeteriorationCondition(conditions_value["deterioration_condition"]),
            FailureCondition(conditions_value["failure_condition"]),
            ObstacleCondition(conditions_value["obstacle_condition"]),
            PineCondition(conditions_value["pine_condition"]),
            ReferenceCondition(conditions_value["reference_condition"]),
            EvidenceCompleteness(conditions_value["evidence_completeness"]),
            NextConditionState(conditions_value["next_condition_state"]),
            None if next_value is None else _next_from_dict(next_value),
            evidence,
            conditions_value["condition_policy_identity"],
            conditions_value["condition_policy_version"],
            conditions_value["policy_status"],
        )
        return NativeLayer2ReadinessRecord(
            run_identity=value["run_identity"], canonical_instrument=value["canonical_instrument"],
            native_assessment_sha256=value["native_assessment_sha256"], native_thesis_sha256=value["native_thesis_sha256"],
            native_evidence_ids=tuple(value["native_evidence_ids"]), visual_question_set_identity=value["visual_question_set_identity"],
            visual_question_set_version=value["visual_question_set_version"], visual_bindings=tuple(tuple(item) for item in value["visual_bindings"]),
            visual_evidence_hashes=tuple(value["visual_evidence_hashes"]), pine_evidence_identity=value["pine_evidence_identity"],
            reference_evidence_identity=value["reference_evidence_identity"], conditions=conditions,
            readiness=NativeReadinessState(value["readiness"]), primary_reason=value["primary_reason"],
            observation_boundary=datetime.fromisoformat(value["observation_boundary"]), created_at=datetime.fromisoformat(value["created_at"]),
            provenance=tuple(value["provenance"]), integrity_status=value["integrity_status"], result_sha256=value["result_sha256"],
            readiness_policy_identity=value["readiness_policy_identity"], readiness_policy_version=value["readiness_policy_version"],
            policy_status=value["policy_status"], authority=value["authority"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("NATIVE_READINESS_STORED_RECORD_INVALID") from error


def _condition_from_dict(value: dict[str, object]) -> ConditionEvidence:
    return ConditionEvidence(
        value["condition_identity"], tuple(value["source_evidence_ids"]),
        None if value["timeframe"] is None else FactualTimeframe(value["timeframe"]),
        value["reference_identity"], LevelAvailability(value["level_availability"]),
        value["price"], value["zone_low"], value["zone_high"],
        datetime.fromisoformat(value["observation_boundary"]), value["reason_code"],
        tuple(value["provenance"]),
    )


def _next_from_dict(value: dict[str, object]) -> NextConditionEvidence:
    return NextConditionEvidence(
        FactualTimeframe(value["timeframe"]), value["condition_type"], value["required_event"],
        value["reference_identity"], LevelAvailability(value["level_availability"]),
        value["price"], value["zone_low"], value["zone_high"], tuple(value["source_evidence_ids"]),
        datetime.fromisoformat(value["observation_boundary"]), value["authority"],
    )


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("NATIVE_READINESS_STORED_EVIDENCE_INVALID") from error
    if type(value) is not dict:
        raise ValueError("NATIVE_READINESS_STORED_EVIDENCE_INVALID")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(_primitive(value), sort_keys=True, separators=(",", ":")).encode()


def _level_shape(availability: LevelAvailability, price: float | None, low: float | None, high: float | None) -> bool:
    if type(availability) is not LevelAvailability:
        return False
    values = (price, low, high)
    if any(item is not None and (type(item) is not float or not math.isfinite(item)) for item in values):
        return False
    if availability is LevelAvailability.AVAILABLE:
        return (price is not None) != (low is not None and high is not None) and ((low is None) == (high is None))
    return all(item is None for item in values)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _code(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", value) is not None


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


__all__ = [
    "ConditionEvidence", "DeterministicExtensionEvidence", "DeterministicObstacleEvidence",
    "DeterministicRetestEvidence", "DeteriorationCondition", "EvidenceCompleteness",
    "ExtensionCondition", "FailureCondition", "LevelAvailability", "NATIVE_LAYER2_CONDITION_POLICY_ID",
    "NATIVE_READINESS_POLICY_ID", "NativeConditionInputs", "NativeLayer2Conditions",
    "NativeLayer2ReadinessRecord", "NativeLayer2ReadinessStore", "NativeReadinessState",
    "NextConditionEvidence", "NextConditionState", "ObstacleCondition", "PineCondition",
    "PullbackCondition", "ReferenceCondition", "RetestCondition", "ThesisIntact",
    "build_native_layer2_conditions", "create_native_readiness_record",
    "resolve_native_readiness", "sponsor_status",
]
