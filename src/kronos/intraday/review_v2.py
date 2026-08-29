"""Versioned Review intake contracts for phase-aware Probables V2/V2.1.

The module is deliberately additive.  It reuses the governed Q1-Q10 visual
question set and DOMAIN-001 visual-identity resolver, but never reinterprets
or updates a V1 Review artifact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Mapping

from kronos.instrument.visual_identity import (
    VisualIdentityResolutionError,
    VisualIdentityResolutionFailure,
    VisualIdentityResolver,
    VisualIdentitySourceContext,
)
from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.mcx_commissioning import McxCommissioningState
from kronos.intraday.nifty_relative_context import NiftyApplicability, NiftyRelationship
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import (
    DiscoveryProbablesEvidenceV2,
    ProbableMemberResultV2,
    ProbablesRunV2,
    probables_v2_methodology_binding_supported,
)
from kronos.intraday.review import (
    AnswerState,
    CHART_TIMEFRAMES,
    DownstreamState,
    ObservationStatus,
    QUESTIONS,
    QUESTION_SET_IDENTITY,
    ReviewError,
    ReviewFailure,
    ReviewState,
    REVIEW_CONTRACT_VERSION,
    TRUST_BOUNDARY,
    TRADING_PROHIBITION,
    VisualState,
)
from kronos.intraday.review_answer import ChartAnalystAnswer, ChartAnalystAnswerPack


REVIEW_HANDOFF_V2_IDENTITY = "KRONOS-INTRADAY-REVIEW-HANDOFF-V2"
REVIEW_CYCLE_V2_IDENTITY = "KRONOS-INTRADAY-REVIEW-CYCLE-V2"
CHART_REVISION_V2_IDENTITY = "KRONOS-INTRADAY-CHART-REVISION-V2"
QUESTION_PACK_V2_IDENTITY = "KRONOS-INTRADAY-VISUAL-REVIEW-QUESTION-PACK-V2"
REVIEW_BATCH_V2_IDENTITY = "KRONOS-INTRADAY-REVIEW-BATCH-V2"
IMPORTED_VISUAL_EVIDENCE_V2_IDENTITY = (
    "KRONOS-INTRADAY-IMPORTED-VISUAL-EVIDENCE-V2"
)
CURRENT_REVIEW_V2_POINTER_IDENTITY = (
    "KRONOS-INTRADAY-CURRENT-REVIEW-POINTER-V2"
)
REVIEW_V2_CONTRACT_VERSION = "2.0.0"


@dataclass(frozen=True, slots=True)
class McxReviewCommissioningBindingV2:
    state: McxCommissioningState
    publication_identity: str
    publication_integrity_identity: str
    qualification_evidence_identity: str
    qualification_integrity_identity: str
    family_expiry_evidence_identity: str
    family_expiry_evidence_integrity: str

    def __post_init__(self) -> None:
        if (
            self.state is not McxCommissioningState.COMMISSIONED
            or not _texts(tuple(asdict(self).values())[1:])
        ):
            raise ReviewError(ReviewFailure.NOT_ELIGIBLE)


@dataclass(frozen=True, slots=True)
class ReviewHandoffV2:
    handoff_identity: str
    probables_run_identity: str
    probable_result_identity: str
    source_discovery_run_identity: str
    source_discovery_result_identity: str
    source_mapping_identity: str
    canonical_subject_identity: str
    direction: str
    market_session_identity: str
    analysis_boundary: datetime
    methodology_identity: str
    methodology_version: str
    methodology_publication_identity: str
    methodology_checksum: str
    phase: IntradayAnalysisPhase
    completed_evidence_selection_identity: str
    completed_evidence_integrity_identity: str
    semantic_evidence_identity: str
    semantic_evidence_integrity_identity: str
    nifty_applicability: NiftyApplicability | None
    nifty_relationship: NiftyRelationship | None
    nifty_evidence_identity: str | None
    nifty_evidence_integrity_identity: str | None
    mcx_commissioning: McxReviewCommissioningBindingV2 | None
    universe_identity: str
    universe_version: str
    reconciliation_identity: str
    reconciliation_version: str
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = REVIEW_HANDOFF_V2_IDENTITY
    schema_version: str = REVIEW_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "handoff_identity", "integrity_identity")
        nifty_pair = (self.nifty_evidence_identity, self.nifty_evidence_integrity_identity)
        if (
            not _texts((
                self.probables_run_identity,
                self.probable_result_identity,
                self.source_discovery_run_identity,
                self.source_discovery_result_identity,
                self.source_mapping_identity,
                self.canonical_subject_identity,
                self.direction,
                self.market_session_identity,
                self.methodology_identity,
                self.methodology_version,
                self.methodology_publication_identity,
                self.methodology_checksum,
                self.completed_evidence_selection_identity,
                self.completed_evidence_integrity_identity,
                self.semantic_evidence_identity,
                self.semantic_evidence_integrity_identity,
                self.universe_identity,
                self.universe_version,
                self.reconciliation_identity,
                self.reconciliation_version,
            ))
            or self.direction not in {"LONG", "SHORT"}
            or not _aware(self.analysis_boundary)
            or type(self.phase) is not IntradayAnalysisPhase
            or not probables_v2_methodology_binding_supported(
                self.methodology_identity,
                self.methodology_version,
                self.methodology_publication_identity,
                self.methodology_checksum,
            )
            or (nifty_pair[0] is None) != (nifty_pair[1] is None)
            or any(item is not None and not _text(item) for item in nifty_pair)
            or self.nifty_applicability is not None
            and type(self.nifty_applicability) is not NiftyApplicability
            or self.nifty_relationship is not None
            and type(self.nifty_relationship) is not NiftyRelationship
            or self.canonical_subject_identity.startswith("MCX-SUBJECT-")
            and self.mcx_commissioning is None
            or not self.canonical_subject_identity.startswith("MCX-SUBJECT-")
            and self.mcx_commissioning is not None
            or not _texts(self.provenance)
            or self.schema_identity != REVIEW_HANDOFF_V2_IDENTITY
            or self.schema_version != REVIEW_V2_CONTRACT_VERSION
            or self.handoff_identity
            != _identity("INTRADAY-REVIEW-V2-HANDOFF-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-REVIEW-V2-HANDOFF-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class ReviewCycleV2:
    cycle_identity: str
    handoff_identity: str
    probables_run_identity: str
    probable_result_identity: str
    canonical_subject_identity: str
    direction: str
    analysis_boundary: datetime
    methodology_identity: str
    methodology_version: str
    methodology_publication_identity: str
    methodology_checksum: str
    phase: IntradayAnalysisPhase
    completed_evidence_selection_identity: str
    completed_evidence_integrity_identity: str
    semantic_evidence_identity: str
    semantic_evidence_integrity_identity: str
    nifty_applicability: NiftyApplicability | None
    nifty_evidence_identity: str | None
    mcx_commissioning: McxReviewCommissioningBindingV2 | None
    source_discovery_run_identity: str
    source_discovery_result_identity: str
    initial_review_state: ReviewState
    visual_state: VisualState
    answer_state: AnswerState
    downstream_state: DownstreamState
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = REVIEW_CYCLE_V2_IDENTITY
    schema_version: str = REVIEW_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "cycle_identity", "integrity_identity")
        if (
            not _texts((
                self.handoff_identity, self.probables_run_identity,
                self.probable_result_identity, self.canonical_subject_identity,
                self.direction, self.methodology_identity, self.methodology_version,
                self.methodology_publication_identity, self.methodology_checksum,
                self.completed_evidence_selection_identity,
                self.completed_evidence_integrity_identity,
                self.semantic_evidence_identity, self.semantic_evidence_integrity_identity,
                self.source_discovery_run_identity, self.source_discovery_result_identity,
            ))
            or not _aware(self.analysis_boundary)
            or type(self.phase) is not IntradayAnalysisPhase
            or self.direction not in {"LONG", "SHORT"}
            or self.initial_review_state is not ReviewState.CHART_REQUIRED
            or self.visual_state is not VisualState.NOT_ANALYZED
            or self.answer_state is not AnswerState.NOT_IMPORTED
            or self.downstream_state is not DownstreamState.NOT_ESTABLISHED
            or not _texts(self.provenance)
            or self.schema_identity != REVIEW_CYCLE_V2_IDENTITY
            or self.schema_version != REVIEW_V2_CONTRACT_VERSION
            or self.cycle_identity != _identity("INTRADAY-REVIEW-V2-CYCLE-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-REVIEW-V2-CYCLE-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class ChartRevisionV2:
    chart_revision_identity: str
    chart_artifact_identity: str
    review_cycle_identity: str
    probables_run_identity: str
    probable_result_identity: str
    expected_canonical_subject_identity: str
    direction: str
    methodology_publication_identity: str
    methodology_checksum: str
    phase: IntradayAnalysisPhase
    revision_ordinal: int
    payload_sha256: str
    media_type: str
    byte_count: int
    received_at: datetime
    timeframe_set: tuple[str, ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = CHART_REVISION_V2_IDENTITY
    schema_version: str = REVIEW_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "chart_revision_identity", "integrity_identity")
        if (
            not _texts((self.chart_artifact_identity, self.review_cycle_identity,
                        self.probables_run_identity, self.probable_result_identity,
                        self.expected_canonical_subject_identity, self.direction,
                        self.methodology_publication_identity, self.methodology_checksum))
            or self.direction not in {"LONG", "SHORT"}
            or type(self.phase) is not IntradayAnalysisPhase
            or type(self.revision_ordinal) is not int or self.revision_ordinal < 1
            or re.fullmatch(r"[0-9a-f]{64}", self.payload_sha256) is None
            or self.media_type not in {"image/png", "image/jpeg"}
            or type(self.byte_count) is not int or self.byte_count < 1
            or not _aware(self.received_at)
            or self.timeframe_set != CHART_TIMEFRAMES
            or not _texts(self.provenance)
            or self.schema_identity != CHART_REVISION_V2_IDENTITY
            or self.schema_version != REVIEW_V2_CONTRACT_VERSION
            or self.chart_revision_identity
            != _identity("INTRADAY-CHART-REVISION-V2-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-CHART-REVISION-V2-", values)
        ):
            raise ReviewError(ReviewFailure.CHART_INVALID)


@dataclass(frozen=True, slots=True)
class ReviewQuestionPackV2:
    review_pack_identity: str
    question_set_identity: str
    question_set_version: str
    probables_run_identity: str
    probable_result_identity: str
    discovery_run_identity: str
    discovery_result_identity: str
    expected_canonical_subject_identity: str
    proposed_direction: str
    analysis_boundary: datetime
    methodology_identity: str
    methodology_version: str
    methodology_publication_identity: str
    methodology_checksum: str
    phase: IntradayAnalysisPhase
    completed_evidence_selection_identity: str
    completed_evidence_integrity_identity: str
    semantic_evidence_identity: str
    semantic_evidence_integrity_identity: str
    review_cycle_identity: str
    review_request_identity: str
    chart_revision_identity: str
    chart_artifact_identity: str
    chart_payload_sha256: str
    questions: tuple[object, ...]
    observation_statuses: tuple[ObservationStatus, ...]
    trust_boundary: str
    trading_authority_prohibition: str
    created_at: datetime
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = QUESTION_PACK_V2_IDENTITY
    schema_version: str = REVIEW_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "review_pack_identity", "integrity_identity")
        if (
            self.question_set_identity != QUESTION_SET_IDENTITY
            or self.question_set_version != REVIEW_CONTRACT_VERSION
            or not _texts((self.probables_run_identity, self.probable_result_identity,
                           self.discovery_run_identity, self.discovery_result_identity,
                           self.expected_canonical_subject_identity, self.proposed_direction,
                           self.methodology_identity, self.methodology_version,
                           self.methodology_publication_identity, self.methodology_checksum,
                           self.completed_evidence_selection_identity,
                           self.completed_evidence_integrity_identity,
                           self.semantic_evidence_identity, self.semantic_evidence_integrity_identity,
                           self.review_cycle_identity, self.review_request_identity,
                           self.chart_revision_identity, self.chart_artifact_identity))
            or self.proposed_direction not in {"LONG", "SHORT"}
            or not _aware(self.analysis_boundary) or not _aware(self.created_at)
            or type(self.phase) is not IntradayAnalysisPhase
            or re.fullmatch(r"[0-9a-f]{64}", self.chart_payload_sha256) is None
            or self.questions != QUESTIONS
            or self.observation_statuses != tuple(ObservationStatus)
            or self.trust_boundary != TRUST_BOUNDARY
            or self.trading_authority_prohibition != TRADING_PROHIBITION
            or not _texts(self.provenance)
            or self.schema_identity != QUESTION_PACK_V2_IDENTITY
            or self.schema_version != REVIEW_V2_CONTRACT_VERSION
            or self.review_pack_identity
            != _identity("INTRADAY-REVIEW-PACK-V2-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-REVIEW-PACK-V2-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class ReviewQuestionBatchV2:
    batch_identity: str
    probables_run_identity: str
    review_pack_identities: tuple[str, ...]
    review_cycle_identities: tuple[str, ...]
    candidate_identities: tuple[str, ...]
    created_at: datetime
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = REVIEW_BATCH_V2_IDENTITY
    schema_version: str = REVIEW_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "batch_identity", "integrity_identity")
        if (
            not _text(self.probables_run_identity)
            or not self.review_pack_identities
            or len(self.review_pack_identities) != len(self.review_cycle_identities)
            or len(self.review_pack_identities) != len(self.candidate_identities)
            or not _texts(self.review_pack_identities)
            or not _texts(self.review_cycle_identities)
            or not _texts(self.candidate_identities)
            or len(set(self.review_pack_identities)) != len(self.review_pack_identities)
            or tuple(sorted(self.candidate_identities)) != self.candidate_identities
            or not _aware(self.created_at)
            or not _texts(self.provenance)
            or self.schema_identity != REVIEW_BATCH_V2_IDENTITY
            or self.schema_version != REVIEW_V2_CONTRACT_VERSION
            or self.batch_identity != _identity("INTRADAY-REVIEW-BATCH-V2-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-REVIEW-BATCH-V2-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class ImportedVisualEvidenceV2:
    visual_evidence_identity: str
    answer_pack_identity: str
    answer_source_sha256: str
    probables_run_identity: str
    probable_result_identity: str
    review_pack_identity: str
    review_cycle_identity: str
    chart_revision_identity: str
    expected_canonical_subject_identity: str
    observed_visible_subject_identity: str
    resolved_canonical_subject_identity: str
    proposed_direction: str
    analysis_boundary: datetime
    methodology_publication_identity: str
    methodology_checksum: str
    phase: IntradayAnalysisPhase
    global_observation_status: ObservationStatus
    answers: tuple[ChartAnalystAnswer, ...]
    visual_identity_relationship_identity: str
    visual_identity_relationship_integrity_identity: str
    visual_identity_publication_identity: str
    visual_identity_publication_version: str
    visual_identity_publication_integrity_identity: str
    imported_at: datetime
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = IMPORTED_VISUAL_EVIDENCE_V2_IDENTITY
    schema_version: str = REVIEW_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "visual_evidence_identity", "integrity_identity")
        if (
            not _texts((self.answer_pack_identity, self.answer_source_sha256,
                        self.probables_run_identity, self.probable_result_identity,
                        self.review_pack_identity, self.review_cycle_identity,
                        self.chart_revision_identity, self.expected_canonical_subject_identity,
                        self.observed_visible_subject_identity,
                        self.resolved_canonical_subject_identity, self.proposed_direction,
                        self.methodology_publication_identity, self.methodology_checksum,
                        self.visual_identity_relationship_identity,
                        self.visual_identity_relationship_integrity_identity,
                        self.visual_identity_publication_identity,
                        self.visual_identity_publication_version,
                        self.visual_identity_publication_integrity_identity))
            or re.fullmatch(r"[0-9a-f]{64}", self.answer_source_sha256) is None
            or self.resolved_canonical_subject_identity
            != self.expected_canonical_subject_identity
            or self.proposed_direction not in {"LONG", "SHORT"}
            or not _aware(self.analysis_boundary) or not _aware(self.imported_at)
            or type(self.phase) is not IntradayAnalysisPhase
            or self.global_observation_status is ObservationStatus.INVALID
            or tuple(item.question_id for item in self.answers)
            != tuple(item.question_id for item in QUESTIONS)
            or not _texts(self.provenance)
            or self.schema_identity != IMPORTED_VISUAL_EVIDENCE_V2_IDENTITY
            or self.schema_version != REVIEW_V2_CONTRACT_VERSION
            or self.visual_evidence_identity
            != _identity("INTRADAY-VISUAL-EVIDENCE-V2-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-VISUAL-EVIDENCE-V2-", values)
        ):
            raise ReviewError(ReviewFailure.ANSWER_INVALID)


@dataclass(frozen=True, slots=True)
class ReviewCyclePointerV2:
    cycle_identity: str
    probable_result_identity: str
    canonical_subject_identity: str
    direction: str

    def __post_init__(self) -> None:
        if (
            not _texts((self.cycle_identity, self.probable_result_identity,
                        self.canonical_subject_identity, self.direction))
            or self.direction not in {"LONG", "SHORT"}
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class CurrentReviewPointerV2:
    probables_run_identity: str
    cycles: tuple[ReviewCyclePointerV2, ...]
    integrity_identity: str
    schema_identity: str = CURRENT_REVIEW_V2_POINTER_IDENTITY
    schema_version: str = REVIEW_V2_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not _text(self.probables_run_identity)
            or tuple(sorted(self.cycles, key=lambda item: item.probable_result_identity))
            != self.cycles
            or len({item.probable_result_identity for item in self.cycles})
            != len(self.cycles)
            or self.schema_identity != CURRENT_REVIEW_V2_POINTER_IDENTITY
            or self.schema_version != REVIEW_V2_CONTRACT_VERSION
            or self.integrity_identity
            != _identity(
                "INTEGRITY-CURRENT-INTRADAY-REVIEW-V2-POINTER-",
                _without(self, "integrity_identity"),
            )
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def create_review_handoff_v2(
    run: ProbablesRunV2,
    result: ProbableMemberResultV2,
    mapping: DiscoveryProbablesEvidenceV2,
) -> ReviewHandoffV2:
    if (
        type(run) is not ProbablesRunV2
        or type(result) is not ProbableMemberResultV2
        or type(mapping) is not DiscoveryProbablesEvidenceV2
        or result not in run.results
        or result.state not in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
        or result.direction is None
        or result.source_mapping_identity != mapping.mapping_identity
        or result.canonical_subject_identity != mapping.canonical_subject_identity
        or result.analysis_boundary != mapping.analysis_boundary
        or result.phase is not mapping.phase
        or result.completed_evidence_selection_identity
        != mapping.completed_evidence.selection_identity
        or result.semantic_evidence_identity != mapping.semantic_evidence.evidence_identity
        or result.methodology_publication_identity
        != mapping.methodology_publication_identity
        or result.methodology_checksum != mapping.methodology_checksum
    ):
        raise ReviewError(ReviewFailure.NOT_ELIGIBLE)

    nifty_integrity = None
    if result.nifty_relative_evidence_identity is not None:
        if (
            mapping.nifty_relative is None
            or mapping.nifty_relative.evidence_identity
            != result.nifty_relative_evidence_identity
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        nifty_integrity = mapping.nifty_relative.integrity_identity

    mcx = _mcx_binding(result)
    values = {
        "probables_run_identity": run.run_identity,
        "probable_result_identity": result.result_identity,
        "source_discovery_run_identity": result.source_discovery_run_identity,
        "source_discovery_result_identity": result.source_discovery_member_identity,
        "source_mapping_identity": mapping.mapping_identity,
        "canonical_subject_identity": result.canonical_subject_identity,
        "direction": result.direction.value,
        "market_session_identity": result.market_session_identity,
        "analysis_boundary": result.analysis_boundary,
        "methodology_identity": result.methodology_identity,
        "methodology_version": result.methodology_version,
        "methodology_publication_identity": result.methodology_publication_identity,
        "methodology_checksum": result.methodology_checksum,
        "phase": result.phase,
        "completed_evidence_selection_identity": mapping.completed_evidence.selection_identity,
        "completed_evidence_integrity_identity": mapping.completed_evidence.integrity_identity,
        "semantic_evidence_identity": mapping.semantic_evidence.evidence_identity,
        "semantic_evidence_integrity_identity": mapping.semantic_evidence.integrity_identity,
        "nifty_applicability": result.nifty_applicability,
        "nifty_relationship": result.nifty_relationship,
        "nifty_evidence_identity": result.nifty_relative_evidence_identity,
        "nifty_evidence_integrity_identity": nifty_integrity,
        "mcx_commissioning": mcx,
        "universe_identity": run.universe_identity,
        "universe_version": run.universe_version,
        "reconciliation_identity": run.reconciliation_identity,
        "reconciliation_version": run.reconciliation_version,
        "provenance": (
            "KRONOS-INTRADAY-V2-REVIEW-SUCCESSOR-SEAM",
            run.run_identity,
            result.result_identity,
            mapping.mapping_identity,
        ),
        "schema_identity": REVIEW_HANDOFF_V2_IDENTITY,
        "schema_version": REVIEW_V2_CONTRACT_VERSION,
    }
    return ReviewHandoffV2(
        handoff_identity=_identity("INTRADAY-REVIEW-V2-HANDOFF-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-REVIEW-V2-HANDOFF-", values
        ),
        **values,
    )


def create_review_cycle_v2(handoff: ReviewHandoffV2) -> ReviewCycleV2:
    if type(handoff) is not ReviewHandoffV2:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    values = {
        "handoff_identity": handoff.handoff_identity,
        "probables_run_identity": handoff.probables_run_identity,
        "probable_result_identity": handoff.probable_result_identity,
        "canonical_subject_identity": handoff.canonical_subject_identity,
        "direction": handoff.direction,
        "analysis_boundary": handoff.analysis_boundary,
        "methodology_identity": handoff.methodology_identity,
        "methodology_version": handoff.methodology_version,
        "methodology_publication_identity": handoff.methodology_publication_identity,
        "methodology_checksum": handoff.methodology_checksum,
        "phase": handoff.phase,
        "completed_evidence_selection_identity": handoff.completed_evidence_selection_identity,
        "completed_evidence_integrity_identity": handoff.completed_evidence_integrity_identity,
        "semantic_evidence_identity": handoff.semantic_evidence_identity,
        "semantic_evidence_integrity_identity": handoff.semantic_evidence_integrity_identity,
        "nifty_applicability": handoff.nifty_applicability,
        "nifty_evidence_identity": handoff.nifty_evidence_identity,
        "mcx_commissioning": handoff.mcx_commissioning,
        "source_discovery_run_identity": handoff.source_discovery_run_identity,
        "source_discovery_result_identity": handoff.source_discovery_result_identity,
        "initial_review_state": ReviewState.CHART_REQUIRED,
        "visual_state": VisualState.NOT_ANALYZED,
        "answer_state": AnswerState.NOT_IMPORTED,
        "downstream_state": DownstreamState.NOT_ESTABLISHED,
        "provenance": (
            "KRONOS-INTRADAY-V2-REVIEW-SUCCESSOR-SEAM",
            handoff.handoff_identity,
        ),
        "schema_identity": REVIEW_CYCLE_V2_IDENTITY,
        "schema_version": REVIEW_V2_CONTRACT_VERSION,
    }
    return ReviewCycleV2(
        cycle_identity=_identity("INTRADAY-REVIEW-V2-CYCLE-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-REVIEW-V2-CYCLE-", values
        ),
        **values,
    )


def create_chart_revision_v2(
    cycle: ReviewCycleV2,
    *,
    revision_ordinal: int,
    payload: bytes,
    media_type: str,
    received_at: datetime,
) -> ChartRevisionV2:
    if type(cycle) is not ReviewCycleV2:
        raise ReviewError(ReviewFailure.CHART_INVALID)
    from kronos.intraday.review_persistence import validate_chart_payload

    validate_chart_payload(media_type, payload)
    digest = sha256(payload).hexdigest()
    artifact = _identity(
        "INTRADAY-CHART-ARTIFACT-V2-",
        {"cycle_identity": cycle.cycle_identity, "sha256": digest, "media_type": media_type},
    )
    values = {
        "chart_artifact_identity": artifact,
        "review_cycle_identity": cycle.cycle_identity,
        "probables_run_identity": cycle.probables_run_identity,
        "probable_result_identity": cycle.probable_result_identity,
        "expected_canonical_subject_identity": cycle.canonical_subject_identity,
        "direction": cycle.direction,
        "methodology_publication_identity": cycle.methodology_publication_identity,
        "methodology_checksum": cycle.methodology_checksum,
        "phase": cycle.phase,
        "revision_ordinal": revision_ordinal,
        "payload_sha256": digest,
        "media_type": media_type,
        "byte_count": len(payload),
        "received_at": received_at,
        "timeframe_set": CHART_TIMEFRAMES,
        "provenance": ("KRONOS-INTRADAY-V2-REVIEW-SUCCESSOR-SEAM", cycle.cycle_identity),
        "schema_identity": CHART_REVISION_V2_IDENTITY,
        "schema_version": REVIEW_V2_CONTRACT_VERSION,
    }
    return ChartRevisionV2(
        chart_revision_identity=_identity("INTRADAY-CHART-REVISION-V2-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-CHART-REVISION-V2-", values
        ),
        **values,
    )


def create_question_pack_v2(
    handoff: ReviewHandoffV2,
    cycle: ReviewCycleV2,
    chart: ChartRevisionV2,
) -> ReviewQuestionPackV2:
    if (
        type(handoff) is not ReviewHandoffV2
        or type(cycle) is not ReviewCycleV2
        or type(chart) is not ChartRevisionV2
        or cycle.handoff_identity != handoff.handoff_identity
        or chart.review_cycle_identity != cycle.cycle_identity
        or chart.probables_run_identity != handoff.probables_run_identity
        or chart.probable_result_identity != handoff.probable_result_identity
        or chart.methodology_publication_identity
        != handoff.methodology_publication_identity
        or chart.methodology_checksum != handoff.methodology_checksum
        or chart.phase is not handoff.phase
    ):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    values = {
        "question_set_identity": QUESTION_SET_IDENTITY,
        "question_set_version": REVIEW_CONTRACT_VERSION,
        "probables_run_identity": handoff.probables_run_identity,
        "probable_result_identity": handoff.probable_result_identity,
        "discovery_run_identity": handoff.source_discovery_run_identity,
        "discovery_result_identity": handoff.source_discovery_result_identity,
        "expected_canonical_subject_identity": handoff.canonical_subject_identity,
        "proposed_direction": handoff.direction,
        "analysis_boundary": handoff.analysis_boundary,
        "methodology_identity": handoff.methodology_identity,
        "methodology_version": handoff.methodology_version,
        "methodology_publication_identity": handoff.methodology_publication_identity,
        "methodology_checksum": handoff.methodology_checksum,
        "phase": handoff.phase,
        "completed_evidence_selection_identity": handoff.completed_evidence_selection_identity,
        "completed_evidence_integrity_identity": handoff.completed_evidence_integrity_identity,
        "semantic_evidence_identity": handoff.semantic_evidence_identity,
        "semantic_evidence_integrity_identity": handoff.semantic_evidence_integrity_identity,
        "review_cycle_identity": cycle.cycle_identity,
        "review_request_identity": cycle.cycle_identity,
        "chart_revision_identity": chart.chart_revision_identity,
        "chart_artifact_identity": chart.chart_artifact_identity,
        "chart_payload_sha256": chart.payload_sha256,
        "questions": QUESTIONS,
        "observation_statuses": tuple(ObservationStatus),
        "trust_boundary": TRUST_BOUNDARY,
        "trading_authority_prohibition": TRADING_PROHIBITION,
        "created_at": chart.received_at,
        "provenance": (
            "KRONOS-INTRADAY-V2-REVIEW-SUCCESSOR-SEAM",
            cycle.cycle_identity,
            chart.chart_revision_identity,
        ),
        "schema_identity": QUESTION_PACK_V2_IDENTITY,
        "schema_version": REVIEW_V2_CONTRACT_VERSION,
    }
    return ReviewQuestionPackV2(
        review_pack_identity=_identity("INTRADAY-REVIEW-PACK-V2-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-REVIEW-PACK-V2-", values
        ),
        **values,
    )


def bind_imported_visual_evidence_v2(
    pack: ReviewQuestionPackV2,
    answer: ChartAnalystAnswerPack,
    *,
    imported_at: datetime,
    visual_identity_resolver: VisualIdentityResolver,
) -> ImportedVisualEvidenceV2:
    if (
        type(pack) is not ReviewQuestionPackV2
        or type(answer) is not ChartAnalystAnswerPack
        or not _aware(imported_at)
        or type(visual_identity_resolver) is not VisualIdentityResolver
    ):
        raise ReviewError(ReviewFailure.ANSWER_INVALID)
    bindings = (
        (answer.question_set_identity, pack.question_set_identity),
        (answer.question_set_version, pack.question_set_version),
        (answer.review_pack_identity, pack.review_pack_identity),
        (answer.review_cycle_identity, pack.review_cycle_identity),
        (answer.review_request_identity, pack.review_request_identity),
        (answer.chart_revision_identity, pack.chart_revision_identity),
        (answer.expected_canonical_subject_identity, pack.expected_canonical_subject_identity),
        (answer.proposed_direction, pack.proposed_direction),
    )
    if (
        any(left != right for left, right in bindings)
        or answer.observed_visible_subject_identity is None
        or answer.global_observation_status is ObservationStatus.INVALID
    ):
        raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
    try:
        resolution = visual_identity_resolver.resolve(
            observed_visible_subject_identity=answer.observed_visible_subject_identity,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=pack.analysis_boundary,
        )
    except VisualIdentityResolutionError as error:
        failure = (
            ReviewFailure.VISUAL_IDENTITY_RELATIONSHIP_AMBIGUOUS
            if error.failure is VisualIdentityResolutionFailure.RELATIONSHIP_AMBIGUOUS
            else ReviewFailure.VISUAL_IDENTITY_RELATIONSHIP_UNAVAILABLE
        )
        raise ReviewError(failure) from error
    if resolution.canonical_subject_identity != pack.expected_canonical_subject_identity:
        raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
    values = {
        "answer_pack_identity": answer.answer_pack_identity,
        "answer_source_sha256": answer.source_sha256,
        "probables_run_identity": pack.probables_run_identity,
        "probable_result_identity": pack.probable_result_identity,
        "review_pack_identity": pack.review_pack_identity,
        "review_cycle_identity": pack.review_cycle_identity,
        "chart_revision_identity": pack.chart_revision_identity,
        "expected_canonical_subject_identity": pack.expected_canonical_subject_identity,
        "observed_visible_subject_identity": answer.observed_visible_subject_identity,
        "resolved_canonical_subject_identity": resolution.canonical_subject_identity,
        "proposed_direction": pack.proposed_direction,
        "analysis_boundary": pack.analysis_boundary,
        "methodology_publication_identity": pack.methodology_publication_identity,
        "methodology_checksum": pack.methodology_checksum,
        "phase": pack.phase,
        "global_observation_status": answer.global_observation_status,
        "answers": answer.answers,
        "visual_identity_relationship_identity": resolution.relationship_identity,
        "visual_identity_relationship_integrity_identity": resolution.relationship_integrity_identity,
        "visual_identity_publication_identity": resolution.publication_identity,
        "visual_identity_publication_version": resolution.publication_version,
        "visual_identity_publication_integrity_identity": resolution.publication_integrity_identity,
        "imported_at": imported_at,
        "provenance": (
            "KRONOS-INTRADAY-V2-REVIEW-SUCCESSOR-SEAM",
            pack.review_pack_identity,
            answer.answer_pack_identity,
        ),
        "schema_identity": IMPORTED_VISUAL_EVIDENCE_V2_IDENTITY,
        "schema_version": REVIEW_V2_CONTRACT_VERSION,
    }
    return ImportedVisualEvidenceV2(
        visual_evidence_identity=_identity("INTRADAY-VISUAL-EVIDENCE-V2-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-VISUAL-EVIDENCE-V2-", values
        ),
        **values,
    )


def create_question_batch_v2(
    packs: tuple[ReviewQuestionPackV2, ...],
) -> ReviewQuestionBatchV2:
    if not packs or any(type(item) is not ReviewQuestionPackV2 for item in packs):
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    ordered = tuple(sorted(packs, key=lambda item: item.expected_canonical_subject_identity))
    if (
        len({item.expected_canonical_subject_identity for item in ordered}) != len(ordered)
        or len({item.probables_run_identity for item in ordered}) != 1
    ):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    values = {
        "probables_run_identity": ordered[0].probables_run_identity,
        "review_pack_identities": tuple(item.review_pack_identity for item in ordered),
        "review_cycle_identities": tuple(item.review_cycle_identity for item in ordered),
        "candidate_identities": tuple(
            item.expected_canonical_subject_identity for item in ordered
        ),
        "created_at": max(item.created_at for item in ordered),
        "provenance": (
            "KRONOS-INTRADAY-V2-REVIEW-SUCCESSOR-SEAM",
            ordered[0].probables_run_identity,
        ),
        "schema_identity": REVIEW_BATCH_V2_IDENTITY,
        "schema_version": REVIEW_V2_CONTRACT_VERSION,
    }
    return ReviewQuestionBatchV2(
        batch_identity=_identity("INTRADAY-REVIEW-BATCH-V2-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-REVIEW-BATCH-V2-", values
        ),
        **values,
    )


def create_current_review_pointer_v2(
    run: ProbablesRunV2,
    cycles: tuple[ReviewCycleV2, ...],
) -> CurrentReviewPointerV2:
    if (
        type(run) is not ProbablesRunV2
        or any(type(item) is not ReviewCycleV2 for item in cycles)
        or any(item.probables_run_identity != run.run_identity for item in cycles)
    ):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    pointers = tuple(sorted((ReviewCyclePointerV2(
        cycle_identity=item.cycle_identity,
        probable_result_identity=item.probable_result_identity,
        canonical_subject_identity=item.canonical_subject_identity,
        direction=item.direction,
    ) for item in cycles), key=lambda item: item.probable_result_identity))
    values = {
        "probables_run_identity": run.run_identity,
        "cycles": pointers,
        "schema_identity": CURRENT_REVIEW_V2_POINTER_IDENTITY,
        "schema_version": REVIEW_V2_CONTRACT_VERSION,
    }
    return CurrentReviewPointerV2(
        integrity_identity=_identity(
            "INTEGRITY-CURRENT-INTRADAY-REVIEW-V2-POINTER-", values
        ),
        **values,
    )


def artifact_bytes_v2(value: object) -> bytes:
    if type(value) not in {
        ReviewHandoffV2, ReviewCycleV2, ChartRevisionV2, ReviewQuestionPackV2,
        ReviewQuestionBatchV2, ImportedVisualEvidenceV2, CurrentReviewPointerV2,
    }:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    return _canonical(_normalize(value)) + b"\n"


def artifact_from_bytes_v2(payload: bytes) -> object:
    try:
        document = json.loads(payload.decode("utf-8"))
        if type(document) is not dict:
            raise ValueError
        schema = document.get("schema_identity")
        expected = {
            REVIEW_HANDOFF_V2_IDENTITY: ReviewHandoffV2,
            REVIEW_CYCLE_V2_IDENTITY: ReviewCycleV2,
            CHART_REVISION_V2_IDENTITY: ChartRevisionV2,
            QUESTION_PACK_V2_IDENTITY: ReviewQuestionPackV2,
            REVIEW_BATCH_V2_IDENTITY: ReviewQuestionBatchV2,
            IMPORTED_VISUAL_EVIDENCE_V2_IDENTITY: ImportedVisualEvidenceV2,
            CURRENT_REVIEW_V2_POINTER_IDENTITY: CurrentReviewPointerV2,
        }.get(schema)
        if expected is None:
            raise ValueError
        decoded = _decode(expected, document)
        if artifact_bytes_v2(decoded) != payload:
            raise ValueError
        return decoded
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error


def _mcx_binding(result: ProbableMemberResultV2) -> McxReviewCommissioningBindingV2 | None:
    if not result.canonical_subject_identity.startswith("MCX-SUBJECT-"):
        return None
    from kronos.intraday.mcx_commissioning import load_mcx_commissioning_publication

    publication = load_mcx_commissioning_publication()
    entry = publication.subject(result.canonical_subject_identity)
    values = (
        publication.publication_identity,
        publication.integrity_identity,
        entry.qualification_evidence_identity,
        entry.qualification_integrity_identity,
        entry.family_expiry_evidence_identity,
        entry.family_expiry_evidence_integrity,
        f"MCX_COMMISSIONING_STATE:{entry.state.value}",
    )
    if entry.state is not McxCommissioningState.COMMISSIONED or any(
        item not in result.provenance for item in values
    ):
        raise ReviewError(ReviewFailure.NOT_ELIGIBLE)
    return McxReviewCommissioningBindingV2(
        state=entry.state,
        publication_identity=publication.publication_identity,
        publication_integrity_identity=publication.integrity_identity,
        qualification_evidence_identity=entry.qualification_evidence_identity,
        qualification_integrity_identity=entry.qualification_integrity_identity,
        family_expiry_evidence_identity=entry.family_expiry_evidence_identity,
        family_expiry_evidence_integrity=entry.family_expiry_evidence_integrity,
    )


def _decode(expected: type, value: object) -> object:
    if expected is CurrentReviewPointerV2:
        document = dict(value)  # type: ignore[arg-type]
        document["cycles"] = tuple(ReviewCyclePointerV2(**item) for item in document["cycles"])
        return CurrentReviewPointerV2(**document)
    document = dict(value)  # type: ignore[arg-type]
    for name in ("analysis_boundary", "received_at", "imported_at", "created_at"):
        if name in document:
            document[name] = datetime.fromisoformat(document[name])
    if "phase" in document:
        document["phase"] = IntradayAnalysisPhase(document["phase"])
    if "nifty_applicability" in document and document["nifty_applicability"] is not None:
        document["nifty_applicability"] = NiftyApplicability(document["nifty_applicability"])
    if "nifty_relationship" in document and document["nifty_relationship"] is not None:
        document["nifty_relationship"] = NiftyRelationship(document["nifty_relationship"])
    if "mcx_commissioning" in document and document["mcx_commissioning"] is not None:
        mcx = document["mcx_commissioning"]
        mcx["state"] = McxCommissioningState(mcx["state"])
        document["mcx_commissioning"] = McxReviewCommissioningBindingV2(**mcx)
    for name, enum_type in (
        ("initial_review_state", ReviewState), ("visual_state", VisualState),
        ("answer_state", AnswerState), ("downstream_state", DownstreamState),
        ("global_observation_status", ObservationStatus),
    ):
        if name in document:
            document[name] = enum_type(document[name])
    for name in (
        "provenance", "timeframe_set", "observation_statuses",
        "review_pack_identities", "review_cycle_identities", "candidate_identities",
    ):
        if name in document:
            document[name] = tuple(document[name])
    if "observation_statuses" in document:
        document["observation_statuses"] = tuple(
            ObservationStatus(item) for item in document["observation_statuses"]
        )
    if "questions" in document:
        from kronos.intraday.review import ReviewQuestion
        document["questions"] = tuple(ReviewQuestion(
            question_id=item["question_id"],
            wording=item["wording"],
            allowed_answers=tuple(item["allowed_answers"]),
            timeframe_scope=tuple(item["timeframe_scope"]),
            authority=item["authority"],
            conditional_instruction=item["conditional_instruction"],
            constraints=tuple(item["constraints"]),
        ) for item in document["questions"])
    if "answers" in document:
        document["answers"] = tuple(ChartAnalystAnswer(
            question_id=item["question_id"],
            observation_status=ObservationStatus(item["observation_status"]),
            answer=item["answer"],
            visible_timeframes=tuple(item["visible_timeframes"]),
            visible_basis=item["visible_basis"],
            status_detail=item["status_detail"],
            why_not_covered_elsewhere=item["why_not_covered_elsewhere"],
        ) for item in document["answers"])
    return expected(**document)


def _without(value: object, *names: str) -> dict[str, object]:
    return {name: item for name, item in asdict(value).items() if name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_canonical(_normalize(value))).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
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


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: tuple[object, ...]) -> bool:
    return bool(values) and all(_text(item) for item in values)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "CHART_REVISION_V2_IDENTITY", "CURRENT_REVIEW_V2_POINTER_IDENTITY",
    "IMPORTED_VISUAL_EVIDENCE_V2_IDENTITY", "QUESTION_PACK_V2_IDENTITY",
    "REVIEW_BATCH_V2_IDENTITY", "REVIEW_CYCLE_V2_IDENTITY",
    "REVIEW_HANDOFF_V2_IDENTITY",
    "REVIEW_V2_CONTRACT_VERSION", "ChartRevisionV2", "CurrentReviewPointerV2",
    "ImportedVisualEvidenceV2", "McxReviewCommissioningBindingV2",
    "ReviewCycleV2", "ReviewHandoffV2", "ReviewQuestionBatchV2",
    "ReviewQuestionPackV2",
    "artifact_bytes_v2", "artifact_from_bytes_v2",
    "bind_imported_visual_evidence_v2", "create_chart_revision_v2",
    "create_current_review_pointer_v2", "create_question_batch_v2",
    "create_question_pack_v2",
    "create_review_cycle_v2", "create_review_handoff_v2",
]
