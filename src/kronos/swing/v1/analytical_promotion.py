"""KR-370 V1 analytical promotion from exact governed Native/V3.1 facts.

This module owns no trade geometry, Risk, Sponsor decision, Entry Outcome,
position, fill, alert, execution, or broker authority.  It consumes already
governed facts and publishes one immutable analytical-promotion record.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.extension import (
    EXTENSION_POLICY_IDENTITY,
    EXTENSION_POLICY_VERSION,
    CompletedOneHourExtensionFact,
    ExtensionAvailability,
    extension_integrity_sha256,
)
from kronos.swing.v1.mtf_facts import (
    FactualTimeframe,
    InstrumentMtfFactSnapshot,
    SameRunMtfFactSnapshot,
)
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_discovery import (
    Native1HState,
    Native1WState,
    Native4HState,
    NativeProductPath,
)
from kronos.swing.v1.native_review import NativeReviewRequirement
from kronos.swing.v1.path_clearance import (
    PATH_CLEARANCE_POLICY_IDENTITY,
    PATH_CLEARANCE_POLICY_VERSION,
    OneHourPathClearanceFact,
    PathClearanceAvailability,
    path_clearance_integrity_sha256,
)
from kronos.swing.v1.reference_facts import (
    SwingReferenceAvailability,
    SwingReferenceChartTimeframe,
    machine_fact_integrity_sha256,
)
from kronos.swing.v1.visual_evidence_v2 import (
    VisualObservationStatus,
    VisualTimeframe,
)
from kronos.swing.v1.visual_evidence_v3 import (
    VISUAL_EVIDENCE_V3_SCHEMA,
    VISUAL_QUESTION_SET_V3_ID,
    VISUAL_QUESTION_SET_V3_VERSION,
    VisualEvidenceV3Response,
    VisualQuestionV3,
    VisualSetupQuality,
    VisualV3SetupQualityObservation,
)


KR370_PROMOTION_CONTRACT_ID = "KRONOS-KR-370-ANALYTICAL-PROMOTION-V1"
KR370_PROMOTION_CONTRACT_VERSION = "1"
KR370_PROMOTION_POLICY_ID = "KR-370-V1-ANALYTICAL-PROMOTION-POLICY"
KR370_PROMOTION_POLICY_VERSION = "1"
KR370_PROMOTION_SCHEMA = "KRONOS-KR-370-ANALYTICAL-PROMOTION-RECORD-V1"
KR370_PROMOTION_AUTHORITY = "ANALYTICAL_PROMOTION_ONLY"
KR370_OWNER_IDENTITY = "KR-370"
KR370_STATE_FAMILY_IDENTITY = "KR370_ANALYTICAL_PROMOTION"
DEFAULT_KR370_PROMOTION_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "swing-v1" / "kr370-analytical-promotion-v1"
)


class Kr370CriterionIdentity(StrEnum):
    K1_DIRECTIONAL_PROGRESSION = "K1_1H_DIRECTIONAL_PROGRESSION"
    K2_CPR_ACCEPTANCE = "K2_1H_CPR_ACCEPTANCE"
    K3_PATH_CLEARANCE = "K3_IMMEDIATE_PATH_CLEARANCE"
    K4_SETUP_QUALITY = "K4_SETUP_QUALITY"
    K5_NON_EXTENSION = "K5_NON_EXTENSION"


class Kr370CriterionState(StrEnum):
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    UNAVAILABLE = "UNAVAILABLE"


class Kr370AnalyticalClassification(StrEnum):
    BUY_NOW = "BUY_NOW"
    SELL_NOW = "SELL_NOW"
    BUY_READY = "BUY_READY"
    SELL_READY = "SELL_READY"
    POTENTIAL_BUY_SETUP = "POTENTIAL_BUY_SETUP"
    POTENTIAL_SELL_SETUP = "POTENTIAL_SELL_SETUP"
    NO_SETUP = "NO_SETUP"


class Kr370Watchability(StrEnum):
    WATCH_AVAILABLE = "WATCH_AVAILABLE"
    NO_AUTOMATED_ALERT_AVAILABLE = "NO_AUTOMATED_ALERT_AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class Kr370CriterionResult:
    identity: Kr370CriterionIdentity
    state: Kr370CriterionState
    reason: str
    evidence_identities: tuple[str, ...]
    level: float | None = None
    blocking_components: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.identity) is not Kr370CriterionIdentity
            or type(self.state) is not Kr370CriterionState
            or not _code(self.reason)
            or type(self.evidence_identities) is not tuple
            or not self.evidence_identities
            or any(not item for item in self.evidence_identities)
            or (self.level is not None and (type(self.level) is not float or self.level < 0.0))
            or type(self.blocking_components) is not tuple
            or any(not item for item in self.blocking_components)
        ):
            raise ValueError("KR370_CRITERION_RESULT_INVALID")


@dataclass(frozen=True, slots=True)
class Kr370PromotionCondition:
    criterion_identity: Kr370CriterionIdentity
    timeframe: FactualTimeframe
    comparator: str
    price: float
    summary: str
    source_evidence_ids: tuple[str, ...]
    observation_boundary: datetime

    def __post_init__(self) -> None:
        if (
            self.criterion_identity is not Kr370CriterionIdentity.K2_CPR_ACCEPTANCE
            or self.timeframe is not FactualTimeframe.ONE_HOUR
            or self.comparator not in {"BAR_CLOSE_ABOVE", "BAR_CLOSE_BELOW"}
            or type(self.price) is not float
            or self.price < 0.0
            or not self.summary
            or not self.source_evidence_ids
            or not _aware(self.observation_boundary)
        ):
            raise ValueError("KR370_PROMOTION_CONDITION_INVALID")


@dataclass(frozen=True, slots=True)
class Kr370AnalyticalPromotionRecord:
    run_identity: str
    canonical_instrument: str
    direction: V1Direction
    native_assessment_sha256: str
    native_requirement_sha256: str
    visual_question_set_identity: str
    visual_question_set_version: str
    visual_evidence_bindings: tuple[tuple[str, str, str], ...]
    review_pack_identity: str
    machine_snapshot_identity: str
    machine_fact_bindings: tuple[tuple[str, str], ...]
    provenance: tuple[str, ...]
    e01_fact_integrity_sha256: str
    e03_fact_integrity_sha256: str
    analysis_boundary: datetime
    observation_boundaries: tuple[tuple[str, datetime], ...]
    criteria: tuple[Kr370CriterionResult, ...]
    satisfied_count: int
    missing_count: int | None
    hard_gate_reason: str | None
    not_evaluable_reason: str | None
    classification: Kr370AnalyticalClassification
    sole_missing_criterion: Kr370CriterionIdentity | None
    promotion_condition: Kr370PromotionCondition | None
    watchability: Kr370Watchability
    created_at: datetime
    integrity_sha256: str
    owner_identity: str = KR370_OWNER_IDENTITY
    state_family_identity: str = KR370_STATE_FAMILY_IDENTITY
    contract_identity: str = KR370_PROMOTION_CONTRACT_ID
    contract_version: str = KR370_PROMOTION_CONTRACT_VERSION
    policy_identity: str = KR370_PROMOTION_POLICY_ID
    policy_version: str = KR370_PROMOTION_POLICY_VERSION
    authority: str = KR370_PROMOTION_AUTHORITY
    product: str = "SWING"
    freshness: str = "EXACT_CURRENT_SAME_RUN"
    execution_authority: bool = False
    risk_authority: bool = False
    sponsor_decision_authority: bool = False
    position_authority: bool = False
    fill_authority: bool = False
    broker_authority: bool = False
    kr390_current_input: bool = False
    kr400_current_alert_source: bool = False
    schema: str = KR370_PROMOTION_SCHEMA

    def __post_init__(self) -> None:
        unavailable = any(
            item.state is Kr370CriterionState.UNAVAILABLE for item in self.criteria
        )
        unsatisfied = tuple(
            item for item in self.criteria
            if item.state is Kr370CriterionState.UNSATISFIED
        )
        ready = self.classification in {
            Kr370AnalyticalClassification.BUY_READY,
            Kr370AnalyticalClassification.SELL_READY,
        }
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.canonical_instrument) is None
            or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not _digest(self.native_assessment_sha256)
            or not _digest(self.native_requirement_sha256)
            or self.visual_question_set_identity != VISUAL_QUESTION_SET_V3_ID
            or self.visual_question_set_version != VISUAL_QUESTION_SET_V3_VERSION
            or tuple(item.identity for item in self.criteria) != tuple(Kr370CriterionIdentity)
            or tuple(item[0] for item in self.visual_evidence_bindings)
            != tuple(item.value for item in VisualTimeframe)
            or any(
                not _digest(evidence) or not _digest(revision)
                for _, evidence, revision in self.visual_evidence_bindings
            )
            or tuple(item[0] for item in self.machine_fact_bindings)
            != tuple(item.value for item in SwingReferenceChartTimeframe)
            or any(not _digest(integrity) for _, integrity in self.machine_fact_bindings)
            or not self.review_pack_identity
            or not self.machine_snapshot_identity.startswith("KITE-MTF-FACTS-")
            or type(self.provenance) is not tuple
            or not self.provenance
            or any(not item for item in self.provenance)
            or not _digest(self.e01_fact_integrity_sha256)
            or not _digest(self.e03_fact_integrity_sha256)
            or not _aware(self.analysis_boundary)
            or tuple(name for name, _ in self.observation_boundaries)
            != tuple(item.value for item in FactualTimeframe)
            or any(not _aware(boundary) for _, boundary in self.observation_boundaries)
            or type(self.satisfied_count) is not int
            or self.satisfied_count != sum(
                item.state is Kr370CriterionState.SATISFIED for item in self.criteria
            )
            or (unavailable != (self.missing_count is None))
            or (
                self.missing_count is not None
                and self.missing_count != len(unsatisfied)
            )
            or (self.not_evaluable_reason is not None) != unavailable
            or (self.not_evaluable_reason is not None and not _code(self.not_evaluable_reason))
            or (self.hard_gate_reason is not None and not _code(self.hard_gate_reason))
            or type(self.classification) is not Kr370AnalyticalClassification
            or (unavailable and self.classification is not Kr370AnalyticalClassification.NO_SETUP)
            or (
                not unavailable
                and self.hard_gate_reason is None
                and self.classification
                is not classify_kr370(self.direction, self.criteria)[0]
            )
            or (self.hard_gate_reason is not None and self.classification is not Kr370AnalyticalClassification.NO_SETUP)
            or ready != (self.sole_missing_criterion is not None)
            or (ready and self.sole_missing_criterion is not unsatisfied[0].identity)
            or (self.promotion_condition is not None and self.sole_missing_criterion is not Kr370CriterionIdentity.K2_CPR_ACCEPTANCE)
            or (
                (self.promotion_condition is not None)
                != (self.watchability is Kr370Watchability.WATCH_AVAILABLE)
            )
            or (
                not ready
                and self.watchability is not Kr370Watchability.NOT_APPLICABLE
            )
            or (
                ready
                and self.promotion_condition is None
                and self.watchability
                is not Kr370Watchability.NO_AUTOMATED_ALERT_AVAILABLE
            )
            or not _aware(self.created_at)
            or not _digest(self.integrity_sha256)
            or self.integrity_sha256 != kr370_promotion_integrity_sha256(self)
            or self.owner_identity != KR370_OWNER_IDENTITY
            or self.state_family_identity != KR370_STATE_FAMILY_IDENTITY
            or self.contract_identity != KR370_PROMOTION_CONTRACT_ID
            or self.contract_version != KR370_PROMOTION_CONTRACT_VERSION
            or self.policy_identity != KR370_PROMOTION_POLICY_ID
            or self.policy_version != KR370_PROMOTION_POLICY_VERSION
            or self.authority != KR370_PROMOTION_AUTHORITY
            or self.product != "SWING"
            or self.freshness != "EXACT_CURRENT_SAME_RUN"
            or self.execution_authority
            or self.risk_authority
            or self.sponsor_decision_authority
            or self.position_authority
            or self.fill_authority
            or self.broker_authority
            or self.kr390_current_input
            or self.kr400_current_alert_source
            or self.schema != KR370_PROMOTION_SCHEMA
        ):
            raise ValueError("KR370_ANALYTICAL_PROMOTION_RECORD_INVALID")

    def criterion(self, identity: Kr370CriterionIdentity) -> Kr370CriterionResult:
        return next(item for item in self.criteria if item.identity is identity)


def classify_kr370(
    direction: V1Direction,
    criteria: tuple[Kr370CriterionResult, ...],
) -> tuple[Kr370AnalyticalClassification, int, int]:
    """Map exactly five available, unweighted criteria to the frozen states."""

    if (
        direction not in {V1Direction.LONG, V1Direction.SHORT}
        or type(criteria) is not tuple
        or tuple(item.identity for item in criteria) != tuple(Kr370CriterionIdentity)
        or any(item.state is Kr370CriterionState.UNAVAILABLE for item in criteria)
    ):
        raise ValueError("KR370_CLASSIFICATION_INPUT_INVALID")
    satisfied = sum(
        item.state is Kr370CriterionState.SATISFIED for item in criteria
    )
    missing = 5 - satisfied
    if missing == 0:
        state = (
            Kr370AnalyticalClassification.BUY_NOW
            if direction is V1Direction.LONG
            else Kr370AnalyticalClassification.SELL_NOW
        )
    elif missing == 1:
        state = (
            Kr370AnalyticalClassification.BUY_READY
            if direction is V1Direction.LONG
            else Kr370AnalyticalClassification.SELL_READY
        )
    elif missing in {2, 3}:
        state = (
            Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP
            if direction is V1Direction.LONG
            else Kr370AnalyticalClassification.POTENTIAL_SELL_SETUP
        )
    else:
        state = Kr370AnalyticalClassification.NO_SETUP
    return state, satisfied, missing


def evaluate_kr370_analytical_promotion(
    requirement: NativeReviewRequirement,
    facts: SameRunMtfFactSnapshot,
    visual: tuple[VisualEvidenceV3Response, ...],
    path_clearance: OneHourPathClearanceFact,
    extension: CompletedOneHourExtensionFact,
    *,
    review_pack_identity: str,
    created_at: datetime,
) -> Kr370AnalyticalPromotionRecord:
    """Consume the exact five governed criteria without recalculating E01/E03."""

    if (
        type(requirement) is not NativeReviewRequirement
        or type(facts) is not SameRunMtfFactSnapshot
        or type(visual) is not tuple
        or type(path_clearance) is not OneHourPathClearanceFact
        or type(extension) is not CompletedOneHourExtensionFact
        or not review_pack_identity
        or not _aware(created_at)
    ):
        raise TypeError("KR370_PROMOTION_INPUT_INVALID")
    if (
        tuple(item.timeframe for item in visual) != tuple(VisualTimeframe)
        or any(
            item.question_set_identity != VISUAL_QUESTION_SET_V3_ID
            or item.question_set_version != VISUAL_QUESTION_SET_V3_VERSION
            or item.schema != VISUAL_EVIDENCE_V3_SCHEMA
            for item in visual
        )
    ):
        raise ValueError("KR370_V3_1_EVIDENCE_REQUIRED")
    instrument = facts.instrument(requirement.canonical_instrument)
    bindings = _binding_failure(
        requirement, facts, visual, path_clearance, extension
    )
    if bindings is not None:
        criteria = tuple(
            _criterion(identity, Kr370CriterionState.UNAVAILABLE, bindings,
                       (requirement.requirement_sha256,))
            for identity in Kr370CriterionIdentity
        )
        return _record(
            requirement, facts, visual, path_clearance, extension,
            review_pack_identity, created_at, criteria,
            hard_gate_reason="INVALID_EXACT_EVIDENCE_BINDING",
            not_evaluable_reason=bindings,
        )

    k1, structural_gate = _k1(requirement)
    k2 = _k2(requirement, instrument)
    k3 = _k3(path_clearance)
    k4, quality_gate = _k4(visual)
    k5 = _k5(extension)
    criteria = (k1, k2, k3, k4, k5)
    hard_gate = _hard_gate(requirement, structural_gate, quality_gate)
    unavailable = tuple(
        item for item in criteria if item.state is Kr370CriterionState.UNAVAILABLE
    )
    not_evaluable = (
        None
        if not unavailable
        else "KR370_NOT_EVALUABLE_EVIDENCE_UNAVAILABLE:"
        + ",".join(item.identity.value for item in unavailable)
    )
    return _record(
        requirement, facts, visual, path_clearance, extension,
        review_pack_identity, created_at, criteria,
        hard_gate_reason=hard_gate,
        not_evaluable_reason=not_evaluable,
    )


def _binding_failure(
    requirement: NativeReviewRequirement,
    facts: SameRunMtfFactSnapshot,
    visual: tuple[VisualEvidenceV3Response, ...],
    path_clearance: OneHourPathClearanceFact,
    extension: CompletedOneHourExtensionFact,
) -> str | None:
    instrument = facts.instrument(requirement.canonical_instrument)
    if requirement.requirement_sha256 != _native_requirement_sha256(requirement):
        return "NATIVE_REQUIREMENT_INTEGRITY_INVALID"
    if facts.run_identity != requirement.native_run_identity:
        return "MACHINE_SNAPSHOT_RUN_MISMATCH"
    if tuple(item.timeframe for item in instrument.timeframes) != tuple(FactualTimeframe):
        return "MACHINE_TIMEFRAME_SET_INVALID"
    if tuple(item.timeframe for item in visual) != tuple(VisualTimeframe):
        return "VISUAL_TIMEFRAME_SET_INVALID"
    if any(
        item.question_set_identity != VISUAL_QUESTION_SET_V3_ID
        or item.question_set_version != VISUAL_QUESTION_SET_V3_VERSION
        or item.schema != VISUAL_EVIDENCE_V3_SCHEMA
        or item.native_run_identity != requirement.native_run_identity
        or item.native_canonical_instrument != requirement.canonical_instrument
        or item.native_assessment_sha256
        != requirement.thesis.native_assessment_sha256
        for item in visual
    ):
        return "MANDATORY_V3_1_BINDING_INVALID"
    machine = instrument.reference_facts
    hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    expected_path_analysis_boundary = (
        instrument.one_hour_atr.analysis_boundary
        if instrument.one_hour_atr is not None
        else hour.observation_boundary
    )
    if len(machine) != 4 or any(
        item.run_identity != requirement.native_run_identity
        or item.canonical_instrument != requirement.canonical_instrument
        or item.integrity_sha256 != machine_fact_integrity_sha256(item)
        for item in machine
    ):
        return "MACHINE_REFERENCE_BINDING_INVALID"
    if any(
        response.machine_fact_integrity_sha256 != fact.integrity_sha256
        or response.analysis_boundary != fact.analysis_boundary
        for response, fact in zip(visual, machine, strict=True)
    ):
        return "VISUAL_MACHINE_BINDING_INVALID"
    thesis_facts = {item.timeframe: item for item in requirement.thesis.timeframe_facts}
    if any(
        thesis_facts[fact.timeframe].observation_boundary != fact.observation_boundary
        or thesis_facts[fact.timeframe].source_timestamp != fact.source_timestamp
        or thesis_facts[fact.timeframe].close != fact.close
        for fact in instrument.timeframes
    ):
        return "NATIVE_MACHINE_BOUNDARY_INVALID"
    if (
        path_clearance.integrity_sha256
        != path_clearance_integrity_sha256(path_clearance)
        or path_clearance.policy_identity != PATH_CLEARANCE_POLICY_IDENTITY
        or path_clearance.policy_version != PATH_CLEARANCE_POLICY_VERSION
        or path_clearance.run_identity != requirement.native_run_identity
        or path_clearance.canonical_instrument != requirement.canonical_instrument
        or path_clearance.direction is not requirement.thesis.direction
        or path_clearance.observation_boundary
        != hour.observation_boundary
        or path_clearance.analysis_boundary != expected_path_analysis_boundary
        or path_clearance.source_market_data_boundary
        != hour.source_market_data_boundary
        or path_clearance.completed_price != hour.close
        or (
            instrument.one_hour_atr is not None
            and path_clearance.atr_fact_integrity_sha256
            != instrument.one_hour_atr.integrity_sha256
        )
    ):
        return "E01_BINDING_INVALID"
    if (
        extension.integrity_sha256 != extension_integrity_sha256(extension)
        or extension.policy_identity != EXTENSION_POLICY_IDENTITY
        or extension.policy_version != EXTENSION_POLICY_VERSION
        or extension.run_identity != requirement.native_run_identity
        or extension.native_assessment_sha256
        != requirement.thesis.native_assessment_sha256
        or extension.canonical_instrument != requirement.canonical_instrument
        or extension.direction is not requirement.thesis.direction
        or extension.observation_boundary != hour.observation_boundary
        or extension.source_market_data_boundary != hour.source_market_data_boundary
        or extension.completed_close != hour.close
        or extension.calendar_identity != hour.calendar_identity
        or extension.calendar_version != hour.calendar_version
        or extension.session_identity != hour.session_identity
        or extension.source_provider_identity != hour.source_provider_identity
        or (
            instrument.one_hour_atr is not None
            and extension.atr_fact_integrity_sha256
            != instrument.one_hour_atr.integrity_sha256
        )
    ):
        return "E03_BINDING_INVALID"
    return None


def _k1(
    requirement: NativeReviewRequirement,
) -> tuple[Kr370CriterionResult, str | None]:
    state = requirement.thesis.one_hour_state
    evidence = (requirement.thesis.native_assessment_sha256,)
    if state is Native1HState.PROGRESSING:
        return _criterion(Kr370CriterionIdentity.K1_DIRECTIONAL_PROGRESSION,
                          Kr370CriterionState.SATISFIED,
                          "NATIVE_1H_DIRECTIONALLY_PROGRESSING", evidence), None
    if state is Native1HState.UNAVAILABLE:
        return _criterion(Kr370CriterionIdentity.K1_DIRECTIONAL_PROGRESSION,
                          Kr370CriterionState.UNAVAILABLE,
                          "NATIVE_1H_PROGRESSION_UNAVAILABLE", evidence), None
    if state is Native1HState.FAILING:
        return _criterion(Kr370CriterionIdentity.K1_DIRECTIONAL_PROGRESSION,
                          Kr370CriterionState.UNSATISFIED,
                          "NATIVE_1H_STRUCTURAL_FAILURE", evidence), "NATIVE_THESIS_INVALIDATED_OR_STRUCTURAL_FAILURE"
    return _criterion(
        Kr370CriterionIdentity.K1_DIRECTIONAL_PROGRESSION,
        Kr370CriterionState.UNSATISFIED,
        f"NATIVE_1H_{state.value}", evidence,
    ), None


def _k2(
    requirement: NativeReviewRequirement,
    instrument: InstrumentMtfFactSnapshot,
) -> Kr370CriterionResult:
    hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    reference = instrument.reference_fact(
        SwingReferenceChartTimeframe.ONE_HOUR
    )
    evidence = (reference.integrity_sha256,)
    if reference.availability is not SwingReferenceAvailability.AVAILABLE:
        return _criterion(Kr370CriterionIdentity.K2_CPR_ACCEPTANCE,
                          Kr370CriterionState.UNAVAILABLE,
                          "GOVERNED_1H_CPR_UNAVAILABLE", evidence)
    level = reference.tc if requirement.thesis.direction is V1Direction.LONG else reference.bc
    assert level is not None
    accepted = (
        hour.close > level
        if requirement.thesis.direction is V1Direction.LONG
        else hour.close < level
    )
    return _criterion(
        Kr370CriterionIdentity.K2_CPR_ACCEPTANCE,
        Kr370CriterionState.SATISFIED if accepted else Kr370CriterionState.UNSATISFIED,
        "COMPLETED_1H_CLOSE_ACCEPTED_BEYOND_CPR"
        if accepted else "COMPLETED_1H_CLOSE_NOT_ACCEPTED_BEYOND_CPR",
        evidence, level=level,
    )


def _k3(value: OneHourPathClearanceFact) -> Kr370CriterionResult:
    evidence = (value.integrity_sha256,)
    if value.availability is not PathClearanceAvailability.AVAILABLE:
        return _criterion(Kr370CriterionIdentity.K3_PATH_CLEARANCE,
                          Kr370CriterionState.UNAVAILABLE,
                          value.unavailable_reason or "E01_UNAVAILABLE", evidence)
    blockers = tuple(
        f"{item.source.value}:{item.level:g}" for item in value.blocking_obstacles
    )
    return _criterion(
        Kr370CriterionIdentity.K3_PATH_CLEARANCE,
        Kr370CriterionState.SATISFIED if value.path_clear else Kr370CriterionState.UNSATISFIED,
        "E01_PATH_CLEAR" if value.path_clear else "E01_IMMEDIATE_PATH_BLOCKED",
        evidence, level=value.clearance_level, blocking_components=blockers,
    )


def _k4(
    visual: tuple[VisualEvidenceV3Response, ...],
) -> tuple[Kr370CriterionResult, str | None]:
    hour = next(item for item in visual if item.timeframe is VisualTimeframe.ONE_HOUR)
    observation = next(
        item for item in hour.observations
        if item.question_id is VisualQuestionV3.PRICE_ACTION_QUALITY
    )
    evidence = (hour.evidence_sha256,)
    if observation.observation_status is VisualObservationStatus.INVALID:
        return _criterion(
            Kr370CriterionIdentity.K4_SETUP_QUALITY,
            Kr370CriterionState.UNAVAILABLE,
            "V3_1_1H_SETUP_QUALITY_INVALID",
            evidence,
        ), "MISSING_OR_INVALID_MANDATORY_V3_1_EVIDENCE"
    if (
        type(observation) is not VisualV3SetupQualityObservation
        or observation.observation_status is not VisualObservationStatus.OBSERVED
        or observation.setup_quality is VisualSetupQuality.NOT_OBSERVABLE
    ):
        return _criterion(Kr370CriterionIdentity.K4_SETUP_QUALITY,
                          Kr370CriterionState.UNAVAILABLE,
                          "V3_1_1H_SETUP_QUALITY_UNAVAILABLE", evidence), None
    if observation.setup_quality in {
        VisualSetupQuality.MESSY_CHOPPY, VisualSetupQuality.CONFLICTING,
    }:
        gate = (
            "V3_1_1H_MESSY_CHOPPY"
            if observation.setup_quality is VisualSetupQuality.MESSY_CHOPPY
            else "AFFIRMATIVE_GOVERNED_DIRECTIONAL_CONFLICT"
        )
        return _criterion(Kr370CriterionIdentity.K4_SETUP_QUALITY,
                          Kr370CriterionState.UNSATISFIED,
                          observation.setup_quality.value, evidence), gate
    return _criterion(Kr370CriterionIdentity.K4_SETUP_QUALITY,
                      Kr370CriterionState.SATISFIED,
                      observation.setup_quality.value, evidence), None


def _k5(value: CompletedOneHourExtensionFact) -> Kr370CriterionResult:
    evidence = (value.integrity_sha256,)
    if value.availability is not ExtensionAvailability.AVAILABLE:
        return _criterion(Kr370CriterionIdentity.K5_NON_EXTENSION,
                          Kr370CriterionState.UNAVAILABLE,
                          value.unavailable_reason or "E03_UNAVAILABLE", evidence)
    return _criterion(
        Kr370CriterionIdentity.K5_NON_EXTENSION,
        Kr370CriterionState.UNSATISFIED
        if value.materially_extended else Kr370CriterionState.SATISFIED,
        "E03_MATERIALLY_EXTENDED"
        if value.materially_extended else "E03_NOT_MATERIALLY_EXTENDED",
        evidence,
    )


def _hard_gate(
    requirement: NativeReviewRequirement,
    structural_gate: str | None,
    quality_gate: str | None,
) -> str | None:
    if structural_gate is not None:
        return structural_gate
    if requirement.thesis.four_hour_state is Native4HState.FAILED:
        return "NATIVE_THESIS_INVALIDATED_OR_STRUCTURAL_FAILURE"
    if requirement.thesis.product_path is NativeProductPath.NSE:
        if requirement.thesis.weekly_state is Native1WState.OPPOSING:
            return "NSE_WEEKLY_OPPOSING"
        if requirement.thesis.weekly_state is Native1WState.UNAVAILABLE:
            return "NSE_WEEKLY_UNAVAILABLE_MANDATORY"
    if quality_gate is not None:
        return quality_gate
    return None


def _record(
    requirement: NativeReviewRequirement,
    facts: SameRunMtfFactSnapshot,
    visual: tuple[VisualEvidenceV3Response, ...],
    path_clearance: OneHourPathClearanceFact,
    extension: CompletedOneHourExtensionFact,
    review_pack_identity: str,
    created_at: datetime,
    criteria: tuple[Kr370CriterionResult, ...],
    *,
    hard_gate_reason: str | None,
    not_evaluable_reason: str | None,
) -> Kr370AnalyticalPromotionRecord:
    unavailable = any(
        item.state is Kr370CriterionState.UNAVAILABLE for item in criteria
    )
    if unavailable or hard_gate_reason is not None:
        classification = Kr370AnalyticalClassification.NO_SETUP
        satisfied = sum(
            item.state is Kr370CriterionState.SATISFIED for item in criteria
        )
        missing = None if unavailable else sum(
            item.state is Kr370CriterionState.UNSATISFIED for item in criteria
        )
    else:
        classification, satisfied, missing = classify_kr370(
            requirement.thesis.direction, criteria
        )
    ready = classification in {
        Kr370AnalyticalClassification.BUY_READY,
        Kr370AnalyticalClassification.SELL_READY,
    }
    sole_missing = (
        next(item.identity for item in criteria
             if item.state is Kr370CriterionState.UNSATISFIED)
        if ready else None
    )
    condition = (
        _k2_condition(requirement, facts, criteria)
        if sole_missing is Kr370CriterionIdentity.K2_CPR_ACCEPTANCE else None
    )
    watchability = (
        Kr370Watchability.NOT_APPLICABLE
        if not ready else
        Kr370Watchability.WATCH_AVAILABLE
        if condition is not None else
        Kr370Watchability.NO_AUTOMATED_ALERT_AVAILABLE
    )
    instrument = facts.instrument(requirement.canonical_instrument)
    machine = instrument.reference_facts
    values = {
        "run_identity": requirement.native_run_identity,
        "canonical_instrument": requirement.canonical_instrument,
        "direction": requirement.thesis.direction,
        "native_assessment_sha256": requirement.thesis.native_assessment_sha256,
        "native_requirement_sha256": requirement.requirement_sha256,
        "visual_question_set_identity": VISUAL_QUESTION_SET_V3_ID,
        "visual_question_set_version": VISUAL_QUESTION_SET_V3_VERSION,
        "visual_evidence_bindings": tuple(
            (item.timeframe.value, item.evidence_sha256, item.chart_revision_sha256)
            for item in visual
        ),
        "review_pack_identity": review_pack_identity,
        "machine_snapshot_identity": facts.provider_source_identity,
        "machine_fact_bindings": tuple(
            (item.chart_timeframe.value, item.integrity_sha256) for item in machine
        ),
        "provenance": tuple(dict.fromkeys((
            facts.provider_source_identity,
            requirement.thesis.native_assessment_sha256,
            requirement.requirement_sha256,
            *(item.evidence_sha256 for item in visual),
            *(item.integrity_sha256 for item in machine),
            path_clearance.integrity_sha256,
            extension.integrity_sha256,
        ))),
        "e01_fact_integrity_sha256": path_clearance.integrity_sha256,
        "e03_fact_integrity_sha256": extension.integrity_sha256,
        "analysis_boundary": max(
            (item.analysis_boundary for item in machine), default=facts.observed_at
        ),
        "observation_boundaries": tuple(
            (item.timeframe.value, item.observation_boundary)
            for item in instrument.timeframes
        ),
        "criteria": criteria,
        "satisfied_count": satisfied,
        "missing_count": missing,
        "hard_gate_reason": hard_gate_reason,
        "not_evaluable_reason": not_evaluable_reason,
        "classification": classification,
        "sole_missing_criterion": sole_missing,
        "promotion_condition": condition,
        "watchability": watchability,
        "created_at": created_at,
    }
    return Kr370AnalyticalPromotionRecord(
        **values, integrity_sha256=kr370_promotion_integrity_sha256(values)
    )


def _k2_condition(
    requirement: NativeReviewRequirement,
    facts: SameRunMtfFactSnapshot,
    criteria: tuple[Kr370CriterionResult, ...],
) -> Kr370PromotionCondition:
    item = next(
        value for value in criteria
        if value.identity is Kr370CriterionIdentity.K2_CPR_ACCEPTANCE
    )
    assert item.level is not None
    hour = facts.instrument(requirement.canonical_instrument).fact(
        FactualTimeframe.ONE_HOUR
    )
    above = requirement.thesis.direction is V1Direction.LONG
    return Kr370PromotionCondition(
        criterion_identity=Kr370CriterionIdentity.K2_CPR_ACCEPTANCE,
        timeframe=FactualTimeframe.ONE_HOUR,
        comparator="BAR_CLOSE_ABOVE" if above else "BAR_CLOSE_BELOW",
        price=item.level,
        summary=(
            f"Completed 1H close above TC {item.level:g}"
            if above else f"Completed 1H close below BC {item.level:g}"
        ),
        source_evidence_ids=item.evidence_identities,
        observation_boundary=hour.observation_boundary,
    )


def _criterion(
    identity: Kr370CriterionIdentity,
    state: Kr370CriterionState,
    reason: str,
    evidence: tuple[str, ...],
    *,
    level: float | None = None,
    blocking_components: tuple[str, ...] = (),
) -> Kr370CriterionResult:
    return Kr370CriterionResult(
        identity, state, reason, evidence, level, blocking_components
    )


class LocalKr370AnalyticalPromotionStore:
    """Atomic immutable current-record store; historical versions are untouched."""

    def __init__(self, root: Path = DEFAULT_KR370_PROMOTION_ROOT) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("KR370_PROMOTION_STORE_INVALID")
        self.root = root
        self._lock = RLock()

    def retain(self, record: Kr370AnalyticalPromotionRecord) -> Path:
        if type(record) is not Kr370AnalyticalPromotionRecord:
            raise TypeError("KR370_PROMOTION_RECORD_INVALID")
        directory = self.root / record.run_identity
        path = directory / f"{_safe(record.canonical_instrument)}--{record.integrity_sha256}.json"
        payload = {"schema": KR370_PROMOTION_SCHEMA, "record": _primitive(record)}
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("KR370_PROMOTION_IMMUTABLE_CONFLICT")
                return path
            _atomic_json(path, payload)
        return path

    def load_exact(
        self,
        run_identity: str,
        canonical_instrument: str,
        native_assessment_sha256: str,
        review_pack_identity: str,
        visual_evidence_hashes: tuple[str, ...],
    ) -> Kr370AnalyticalPromotionRecord | None:
        directory = self.root / run_identity
        if not directory.exists():
            return None
        matches = []
        for path in sorted(directory.glob(f"{_safe(canonical_instrument)}--*.json")):
            payload = _read(path)
            if payload.get("schema") != KR370_PROMOTION_SCHEMA:
                raise ValueError("KR370_PROMOTION_RESTORE_SCHEMA_INVALID")
            record = _record_from_dict(payload.get("record"))
            if (
                record.run_identity == run_identity
                and record.canonical_instrument == canonical_instrument
                and record.native_assessment_sha256 == native_assessment_sha256
                and record.review_pack_identity == review_pack_identity
                and tuple(item[1] for item in record.visual_evidence_bindings)
                == visual_evidence_hashes
            ):
                matches.append(record)
        if len(matches) > 1:
            raise ValueError("KR370_PROMOTION_RESTORE_AMBIGUOUS")
        return None if not matches else matches[0]


def kr370_promotion_integrity_sha256(
    value: Kr370AnalyticalPromotionRecord | dict[str, object],
) -> str:
    material = asdict(value) if type(value) is Kr370AnalyticalPromotionRecord else dict(value)
    material.pop("integrity_sha256", None)
    material.setdefault("owner_identity", KR370_OWNER_IDENTITY)
    material.setdefault("state_family_identity", KR370_STATE_FAMILY_IDENTITY)
    material.setdefault("contract_identity", KR370_PROMOTION_CONTRACT_ID)
    material.setdefault("contract_version", KR370_PROMOTION_CONTRACT_VERSION)
    material.setdefault("policy_identity", KR370_PROMOTION_POLICY_ID)
    material.setdefault("policy_version", KR370_PROMOTION_POLICY_VERSION)
    material.setdefault("authority", KR370_PROMOTION_AUTHORITY)
    material.setdefault("product", "SWING")
    material.setdefault("freshness", "EXACT_CURRENT_SAME_RUN")
    material.setdefault("execution_authority", False)
    material.setdefault("risk_authority", False)
    material.setdefault("sponsor_decision_authority", False)
    material.setdefault("position_authority", False)
    material.setdefault("fill_authority", False)
    material.setdefault("broker_authority", False)
    material.setdefault("kr390_current_input", False)
    material.setdefault("kr400_current_alert_source", False)
    material.setdefault("schema", KR370_PROMOTION_SCHEMA)
    return sha256(_canonical(material)).hexdigest()


def _record_from_dict(value: object) -> Kr370AnalyticalPromotionRecord:
    if type(value) is not dict:
        raise ValueError("KR370_PROMOTION_RESTORE_INVALID")
    try:
        criteria = tuple(
            Kr370CriterionResult(
                Kr370CriterionIdentity(item["identity"]),
                Kr370CriterionState(item["state"]),
                item["reason"], tuple(item["evidence_identities"]),
                item["level"], tuple(item["blocking_components"]),
            )
            for item in value["criteria"]
        )
        raw_condition = value["promotion_condition"]
        condition = None if raw_condition is None else Kr370PromotionCondition(
            Kr370CriterionIdentity(raw_condition["criterion_identity"]),
            FactualTimeframe(raw_condition["timeframe"]),
            raw_condition["comparator"], raw_condition["price"],
            raw_condition["summary"], tuple(raw_condition["source_evidence_ids"]),
            datetime.fromisoformat(raw_condition["observation_boundary"]),
        )
        return Kr370AnalyticalPromotionRecord(
            run_identity=value["run_identity"],
            canonical_instrument=value["canonical_instrument"],
            direction=V1Direction(value["direction"]),
            native_assessment_sha256=value["native_assessment_sha256"],
            native_requirement_sha256=value["native_requirement_sha256"],
            visual_question_set_identity=value["visual_question_set_identity"],
            visual_question_set_version=value["visual_question_set_version"],
            visual_evidence_bindings=tuple(tuple(item) for item in value["visual_evidence_bindings"]),
            review_pack_identity=value["review_pack_identity"],
            machine_snapshot_identity=value["machine_snapshot_identity"],
            machine_fact_bindings=tuple(tuple(item) for item in value["machine_fact_bindings"]),
            provenance=tuple(value["provenance"]),
            e01_fact_integrity_sha256=value["e01_fact_integrity_sha256"],
            e03_fact_integrity_sha256=value["e03_fact_integrity_sha256"],
            analysis_boundary=datetime.fromisoformat(value["analysis_boundary"]),
            observation_boundaries=tuple(
                (item[0], datetime.fromisoformat(item[1]))
                for item in value["observation_boundaries"]
            ),
            criteria=criteria,
            satisfied_count=value["satisfied_count"],
            missing_count=value["missing_count"],
            hard_gate_reason=value["hard_gate_reason"],
            not_evaluable_reason=value["not_evaluable_reason"],
            classification=Kr370AnalyticalClassification(value["classification"]),
            sole_missing_criterion=(
                None if value["sole_missing_criterion"] is None
                else Kr370CriterionIdentity(value["sole_missing_criterion"])
            ),
            promotion_condition=condition,
            watchability=Kr370Watchability(value["watchability"]),
            created_at=datetime.fromisoformat(value["created_at"]),
            integrity_sha256=value["integrity_sha256"],
            owner_identity=value["owner_identity"],
            state_family_identity=value["state_family_identity"],
            contract_identity=value["contract_identity"],
            contract_version=value["contract_version"],
            policy_identity=value["policy_identity"],
            policy_version=value["policy_version"],
            authority=value["authority"],
            product=value["product"],
            freshness=value["freshness"],
            execution_authority=value["execution_authority"],
            risk_authority=value["risk_authority"],
            sponsor_decision_authority=value["sponsor_decision_authority"],
            position_authority=value["position_authority"],
            fill_authority=value["fill_authority"],
            broker_authority=value["broker_authority"],
            kr390_current_input=value["kr390_current_input"],
            kr400_current_alert_source=value["kr400_current_alert_source"],
            schema=value["schema"],
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("KR370_"):
            raise
        raise ValueError("KR370_PROMOTION_RESTORE_INVALID") from error


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("KR370_PROMOTION_EVIDENCE_INVALID") from error
    if type(value) is not dict:
        raise ValueError("KR370_PROMOTION_EVIDENCE_INVALID")
    return value


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _safe(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9&._-]", "_", value)
    if not result:
        raise ValueError("KR370_PROMOTION_PATH_INVALID")
    return result


def _primitive(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return _primitive(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        _primitive(value), sort_keys=True, separators=(",", ":")
    ).encode()


def _native_requirement_sha256(requirement: NativeReviewRequirement) -> str:
    return sha256(
        _canonical(
            {
                "thesis": requirement.thesis,
                "mcx_reference": requirement.mcx_reference,
            }
        )
    ).hexdigest()


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _code(value: object) -> bool:
    return type(value) is str and bool(value) and len(value) <= 256


__all__ = [
    "DEFAULT_KR370_PROMOTION_ROOT",
    "KR370_PROMOTION_AUTHORITY",
    "KR370_PROMOTION_CONTRACT_ID",
    "KR370_PROMOTION_CONTRACT_VERSION",
    "KR370_PROMOTION_POLICY_ID",
    "KR370_PROMOTION_POLICY_VERSION",
    "Kr370AnalyticalClassification",
    "Kr370AnalyticalPromotionRecord",
    "Kr370CriterionIdentity",
    "Kr370CriterionResult",
    "Kr370CriterionState",
    "Kr370PromotionCondition",
    "Kr370Watchability",
    "LocalKr370AnalyticalPromotionStore",
    "classify_kr370",
    "evaluate_kr370_analytical_promotion",
    "kr370_promotion_integrity_sha256",
]
