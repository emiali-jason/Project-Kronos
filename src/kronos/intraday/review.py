"""Governed Intraday visual-review contracts with no trading authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Iterable, Mapping

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.probables import ProbableMemberResult, ProbableState, ProbablesRun


REVIEW_HANDOFF_IDENTITY = "KRONOS-INTRADAY-REVIEW-HANDOFF-V1"
REVIEW_CYCLE_IDENTITY = "KRONOS-INTRADAY-REVIEW-CYCLE-V1"
CHART_ARTIFACT_IDENTITY = "KRONOS-INTRADAY-CHART-ARTIFACT-V1"
CHART_REVISION_IDENTITY = "KRONOS-INTRADAY-CHART-REVISION-V1"
QUESTION_SET_IDENTITY = "KRONOS-INTRADAY-CHART-ANALYST-QUESTION-SET-V1"
QUESTION_PACK_IDENTITY = "KRONOS-INTRADAY-VISUAL-REVIEW-QUESTION-PACK-V1"
CURRENT_REVIEW_POINTER_IDENTITY = "KRONOS-INTRADAY-CURRENT-REVIEW-POINTER-V1"
REVIEW_CONTRACT_VERSION = "1.0.0"
CHART_TIMEFRAMES = ("1D", "1H", "15M", "5M")


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Iterable[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


class ReviewFailure(StrEnum):
    INPUT_INVALID = "INTRADAY_REVIEW_INPUT_INVALID"
    NOT_ELIGIBLE = "INTRADAY_REVIEW_NOT_ELIGIBLE"
    NOT_CURRENT = "INTRADAY_REVIEW_NOT_CURRENT"
    CHART_REQUIRED = "INTRADAY_REVIEW_CHART_REQUIRED"
    CYCLE_UNAVAILABLE = "INTRADAY_REVIEW_CYCLE_UNAVAILABLE"
    ARTIFACT_UNAVAILABLE = "INTRADAY_REVIEW_ARTIFACT_UNAVAILABLE"
    INTEGRITY_INVALID = "INTRADAY_REVIEW_INTEGRITY_INVALID"
    PERSISTENCE_CONFLICT = "INTRADAY_REVIEW_PERSISTENCE_CONFLICT"
    CHART_INVALID = "INTRADAY_REVIEW_CHART_INVALID"
    ANSWER_MISSING = "INTRADAY_REVIEW_ANSWER_MISSING"
    ANSWER_INVALID = "INTRADAY_REVIEW_ANSWER_INVALID"
    ANSWER_IDENTITY_MISMATCH = "INTRADAY_REVIEW_ANSWER_IDENTITY_MISMATCH"
    VISUAL_IDENTITY_RELATIONSHIP_UNAVAILABLE = "VISUAL_IDENTITY_RELATIONSHIP_UNAVAILABLE"
    VISUAL_IDENTITY_RELATIONSHIP_AMBIGUOUS = "VISUAL_IDENTITY_RELATIONSHIP_AMBIGUOUS"
    ANSWER_SCHEMA_INVALID = "INTRADAY_REVIEW_ANSWER_SCHEMA_INVALID"
    ANSWER_CONFLICT = "INTRADAY_REVIEW_ANSWER_CONFLICT"


class ReviewError(RuntimeError):
    def __init__(self, failure: ReviewFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class ReviewState(StrEnum):
    CHART_REQUIRED = "CHART_REQUIRED"
    CHART_READY = "CHART_READY"
    QUESTION_PACK_CREATED = "QUESTION_PACK_CREATED"


class VisualState(StrEnum):
    NOT_ANALYZED = "NOT_ANALYZED"


class AnswerState(StrEnum):
    NOT_IMPORTED = "NOT_IMPORTED"


class DownstreamState(StrEnum):
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


class ObservationStatus(StrEnum):
    OBSERVED = "OBSERVED"
    PARTIAL = "PARTIAL"
    NOT_VISIBLE = "NOT_VISIBLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class ReviewQuestion:
    question_id: str
    wording: str
    allowed_answers: tuple[str, ...]
    timeframe_scope: tuple[str, ...]
    authority: str = "VISUAL_EVIDENCE_ONLY"
    conditional_instruction: str | None = None
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            re.fullmatch(r"Q(?:[1-9]|10)", self.question_id) is None
            or not _text(self.wording)
            or not _texts(self.allowed_answers)
            or not self.timeframe_scope
            or any(item not in CHART_TIMEFRAMES for item in self.timeframe_scope)
            or not _text(self.authority)
            or self.conditional_instruction is not None
            and not _text(self.conditional_instruction)
            or any(not _text(item) for item in self.constraints)
        ):
            raise ReviewError(ReviewFailure.INPUT_INVALID)


QUESTIONS = (
    ReviewQuestion(
        "Q1",
        "On the visible completed 1D chart, does the broader price structure visually support, oppose, or neither clearly support nor oppose the proposed Intraday direction?",
        ("SUPPORTIVE", "OPPOSING", "MIXED", "UNCLEAR"),
        ("1D",),
        "INFORMATIONAL VISUAL CONTEXT",
    ),
    ReviewQuestion(
        "Q2",
        "On the visible completed 1H chart, does price structure visually support the proposed direction, oppose it, or remain mixed or unclear?",
        ("SUPPORTIVE", "OPPOSING", "MIXED", "UNCLEAR"),
        ("1H",),
    ),
    ReviewQuestion(
        "Q3",
        "On the visible completed 1H chart, how strongly is price action characterized by sustained directional sequencing versus overlapping or alternating movement?",
        ("ORDERLY", "SOME_OVERLAP", "MATERIAL_OVERLAP", "UNCLEAR"),
        ("1H",),
        constraints=("No numerical chop threshold.",),
    ),
    ReviewQuestion(
        "Q4",
        "On the visible completed 15M chart, does price structure visually support the proposed direction, oppose it, or remain mixed or unclear?",
        ("SUPPORTIVE", "OPPOSING", "MIXED", "UNCLEAR"),
        ("15M",),
    ),
    ReviewQuestion(
        "Q5",
        "On the visible completed 15M chart, is there evidence that directional continuation has stalled or failed, or that opposing structure has become visible against the proposed direction?",
        ("NONE_VISIBLE", "STALLING_OR_FAILED_CONTINUATION", "OPPOSING_STRUCTURE_VISIBLE", "BOTH", "UNCLEAR"),
        ("15M",),
        constraints=("Does not establish REVERSAL_CONFIRMED, INVALIDATED or REJECT.",),
    ),
    ReviewQuestion(
        "Q6",
        "On the visible completed 5M chart, how is immediate price progression behaving relative to the proposed direction?",
        ("SUPPORTIVE", "STALLING", "OPPOSING", "CHOPPY", "MIXED", "UNCLEAR"),
        ("5M",),
        constraints=("NOT ENTRY TIMING.", "SUPPORTIVE does not mean ENTER NOW."),
    ),
    ReviewQuestion(
        "Q7",
        "On the visible completed 15M and 5M charts, is there an obvious structural obstacle ahead of current price in the proposed direction?",
        ("NONE_VISIBLE", "PRESENT", "UNCLEAR"),
        ("15M", "5M"),
        conditional_instruction="If PRESENT, require timeframe and concise visible basis.",
        constraints=("No distance/materiality consequence.",),
    ),
    ReviewQuestion(
        "Q8",
        "Relative to the most recent clearly visible 15M and 5M structural base or consolidation, does current completed price action appear materially extended in the proposed direction?",
        ("NOT_VISIBLY_EXTENDED", "VISIBLY_EXTENDED", "MIXED", "UNCLEAR"),
        ("15M", "5M"),
        constraints=("No numerical extension threshold.", "No DO_NOT_CHASE consequence."),
    ),
    ReviewQuestion(
        "Q9",
        "On the visible completed 15M and 5M charts, does current price action show clear directional acceptance away from recent local structure, clear rejection back against the proposed direction, or neither?",
        ("DIRECTIONAL_ACCEPTANCE", "REJECTION_AGAINST_DIRECTION", "MIXED", "NO_CLEAR_ACCEPTANCE_OR_REJECTION", "UNCLEAR"),
        ("15M", "5M"),
        constraints=("No Entry Trigger authority.",),
    ),
    ReviewQuestion(
        "Q10",
        "Is there any material visible chart condition relevant to review of the proposed Intraday direction that is not adequately represented by Q1–Q9?",
        ("NONE", "MATERIAL_OBSERVATION"),
        CHART_TIMEFRAMES,
        conditional_instruction=(
            "If NONE, why_not_covered_elsewhere must be null. If MATERIAL_OBSERVATION, require timeframe, concise visible observation, and why Q1–Q9 do not capture it."
        ),
        constraints=("No prediction, recommendation or consequence.",),
    ),
)


TRUST_BOUNDARY = (
    "Chart Analyst authority is VISUAL EVIDENCE ONLY. Observed chart identity is independent of the expected canonical identity. "
    "Do not manufacture KRONOS or Provider identities, hashes, provenance, internal timestamps, CPR or Pivot values."
)
TRADING_PROHIBITION = (
    "Do not return BUY, SELL, ENTER NOW, trade approval or rejection, Entry, Stop, Target, R:R, position size, "
    "instrument choice, option choice, strike, expiry, Risk permission, PAPER/LIVE, probability, win rate, expected return, or trade-confidence score."
)


@dataclass(frozen=True, slots=True)
class ReviewHandoff:
    handoff_identity: str
    probables_run_identity: str
    probable_result_identity: str
    source_discovery_run_identity: str
    source_discovery_member_identity: str
    canonical_subject_identity: str
    direction: str
    market_session_identity: str
    observation_boundary: datetime
    methodology_identity: str
    methodology_version: str
    universe_identity: str
    universe_version: str
    reconciliation_identity: str
    reconciliation_version: str
    evidence_lineage: tuple[str, ...]
    created_at: datetime
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = REVIEW_HANDOFF_IDENTITY
    schema_version: str = REVIEW_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.handoff_identity.startswith("INTRADAY-REVIEW-HANDOFF-")
            or not _texts((
                self.probables_run_identity,
                self.probable_result_identity,
                self.source_discovery_run_identity,
                self.source_discovery_member_identity,
                self.canonical_subject_identity,
                self.direction,
                self.market_session_identity,
                self.methodology_identity,
                self.methodology_version,
                self.universe_identity,
                self.universe_version,
                self.reconciliation_identity,
                self.reconciliation_version,
            ))
            or self.direction not in {"LONG", "SHORT"}
            or not _aware(self.observation_boundary)
            or not _aware(self.created_at)
            or not _texts(self.evidence_lineage)
            or not _texts(self.provenance)
            or self.schema_identity != REVIEW_HANDOFF_IDENTITY
            or self.schema_version != REVIEW_CONTRACT_VERSION
        ):
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        _verify(self, "handoff_identity", "INTRADAY-REVIEW-HANDOFF-", "INTEGRITY-REVIEW-HANDOFF-")


@dataclass(frozen=True, slots=True)
class ReviewCycle:
    cycle_identity: str
    handoff_identity: str
    probables_run_identity: str
    probable_result_identity: str
    canonical_subject_identity: str
    direction: str
    created_at: datetime
    initial_review_state: ReviewState
    visual_state: VisualState
    answer_state: AnswerState
    downstream_state: DownstreamState
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = REVIEW_CYCLE_IDENTITY
    schema_version: str = REVIEW_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.cycle_identity.startswith("INTRADAY-REVIEW-CYCLE-")
            or not _texts((self.handoff_identity, self.probables_run_identity, self.probable_result_identity, self.canonical_subject_identity, self.direction))
            or self.direction not in {"LONG", "SHORT"}
            or not _aware(self.created_at)
            or self.initial_review_state is not ReviewState.CHART_REQUIRED
            or self.visual_state is not VisualState.NOT_ANALYZED
            or self.answer_state is not AnswerState.NOT_IMPORTED
            or self.downstream_state is not DownstreamState.NOT_ESTABLISHED
            or not _texts(self.provenance)
            or self.schema_identity != REVIEW_CYCLE_IDENTITY
            or self.schema_version != REVIEW_CONTRACT_VERSION
        ):
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        _verify(self, "cycle_identity", "INTRADAY-REVIEW-CYCLE-", "INTEGRITY-REVIEW-CYCLE-")


@dataclass(frozen=True, slots=True)
class ChartRevision:
    chart_revision_identity: str
    chart_artifact_identity: str
    cycle_identity: str
    probables_run_identity: str
    probable_result_identity: str
    expected_canonical_subject_identity: str
    direction: str
    revision_ordinal: int
    payload_sha256: str
    media_type: str
    byte_count: int
    received_at: datetime
    timeframe_set: tuple[str, ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = CHART_REVISION_IDENTITY
    schema_version: str = REVIEW_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.chart_revision_identity.startswith("INTRADAY-CHART-REVISION-")
            or not self.chart_artifact_identity.startswith("INTRADAY-CHART-ARTIFACT-")
            or not _texts((self.cycle_identity, self.probables_run_identity, self.probable_result_identity, self.expected_canonical_subject_identity, self.direction))
            or self.direction not in {"LONG", "SHORT"}
            or type(self.revision_ordinal) is not int
            or self.revision_ordinal < 1
            or re.fullmatch(r"[0-9a-f]{64}", self.payload_sha256) is None
            or self.media_type not in {"image/png", "image/jpeg"}
            or type(self.byte_count) is not int
            or self.byte_count < 1
            or not _aware(self.received_at)
            or self.timeframe_set != CHART_TIMEFRAMES
            or not _texts(self.provenance)
            or self.schema_identity != CHART_REVISION_IDENTITY
            or self.schema_version != REVIEW_CONTRACT_VERSION
        ):
            raise ReviewError(ReviewFailure.CHART_INVALID)
        _verify(self, "chart_revision_identity", "INTRADAY-CHART-REVISION-", "INTEGRITY-CHART-REVISION-")


@dataclass(frozen=True, slots=True)
class ReviewQuestionPack:
    review_pack_identity: str
    question_set_identity: str
    question_set_version: str
    probables_run_identity: str
    probable_result_identity: str
    discovery_run_identity: str
    discovery_member_identity: str
    expected_canonical_subject_identity: str
    proposed_direction: str
    observation_boundary: datetime
    review_cycle_identity: str
    review_request_identity: str
    chart_revision_identity: str
    chart_artifact_identity: str
    chart_payload_sha256: str
    questions: tuple[ReviewQuestion, ...]
    observation_statuses: tuple[ObservationStatus, ...]
    trust_boundary: str
    trading_authority_prohibition: str
    created_at: datetime
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = QUESTION_PACK_IDENTITY
    schema_version: str = REVIEW_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.review_pack_identity.startswith("INTRADAY-REVIEW-PACK-")
            or self.question_set_identity != QUESTION_SET_IDENTITY
            or self.question_set_version != REVIEW_CONTRACT_VERSION
            or not _texts((
                self.probables_run_identity,
                self.probable_result_identity,
                self.discovery_run_identity,
                self.discovery_member_identity,
                self.expected_canonical_subject_identity,
                self.proposed_direction,
                self.review_cycle_identity,
                self.review_request_identity,
                self.chart_revision_identity,
                self.chart_artifact_identity,
            ))
            or self.proposed_direction not in {"LONG", "SHORT"}
            or not _aware(self.observation_boundary)
            or re.fullmatch(r"[0-9a-f]{64}", self.chart_payload_sha256) is None
            or self.questions != QUESTIONS
            or self.observation_statuses != tuple(ObservationStatus)
            or self.trust_boundary != TRUST_BOUNDARY
            or self.trading_authority_prohibition != TRADING_PROHIBITION
            or not _aware(self.created_at)
            or not _texts(self.provenance)
            or self.schema_identity != QUESTION_PACK_IDENTITY
            or self.schema_version != REVIEW_CONTRACT_VERSION
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        _verify(self, "review_pack_identity", "INTRADAY-REVIEW-PACK-", "INTEGRITY-REVIEW-PACK-")


@dataclass(frozen=True, slots=True)
class ReviewCyclePointer:
    cycle_identity: str
    probable_result_identity: str
    canonical_subject_identity: str
    direction: str
    state: ReviewState
    active_chart_revision_identity: str | None
    active_review_pack_identity: str | None

    def __post_init__(self) -> None:
        if (
            not _texts((self.cycle_identity, self.probable_result_identity, self.canonical_subject_identity, self.direction))
            or self.direction not in {"LONG", "SHORT"}
            or type(self.state) is not ReviewState
            or self.active_chart_revision_identity is not None and not _text(self.active_chart_revision_identity)
            or self.active_review_pack_identity is not None and not _text(self.active_review_pack_identity)
            or (self.state is ReviewState.CHART_REQUIRED and (self.active_chart_revision_identity is not None or self.active_review_pack_identity is not None))
            or (self.state is ReviewState.CHART_READY and (self.active_chart_revision_identity is None or self.active_review_pack_identity is not None))
            or (self.state is ReviewState.QUESTION_PACK_CREATED and (self.active_chart_revision_identity is None or self.active_review_pack_identity is None))
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class CurrentReviewPointer:
    probables_run_identity: str
    cycles: tuple[ReviewCyclePointer, ...]
    integrity_identity: str
    schema_identity: str = CURRENT_REVIEW_POINTER_IDENTITY
    schema_version: str = REVIEW_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not _text(self.probables_run_identity)
            or tuple(sorted(self.cycles, key=lambda item: item.probable_result_identity)) != self.cycles
            or len({item.probable_result_identity for item in self.cycles}) != len(self.cycles)
            or self.schema_identity != CURRENT_REVIEW_POINTER_IDENTITY
            or self.schema_version != REVIEW_CONTRACT_VERSION
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        _verify_integrity(self, "INTEGRITY-CURRENT-REVIEW-POINTER-")


@dataclass(frozen=True, slots=True)
class FutureVisualAnswerIdentity:
    """WO-09 compatibility proof; this does not authorize answer import."""

    expected_canonical_subject_identity: str
    observed_visible_subject_identity: str | None

    def __post_init__(self) -> None:
        if not _text(self.expected_canonical_subject_identity) or (
            self.observed_visible_subject_identity is not None
            and not _text(self.observed_visible_subject_identity)
        ):
            raise ReviewError(ReviewFailure.INPUT_INVALID)


@dataclass(frozen=True, slots=True)
class FutureAnswerPackBinding:
    """Exact WO-09 identity envelope without answer-import authority."""

    probables_run_identity: str
    expected_canonical_subject_identity: str
    observed_visible_subject_identity: str | None
    review_cycle_identity: str
    chart_revision_identity: str
    review_pack_identity: str
    question_set_identity: str = QUESTION_SET_IDENTITY
    question_set_version: str = REVIEW_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not _texts((
                self.probables_run_identity,
                self.expected_canonical_subject_identity,
                self.review_cycle_identity,
                self.chart_revision_identity,
                self.review_pack_identity,
            ))
            or self.observed_visible_subject_identity is not None
            and not _text(self.observed_visible_subject_identity)
            or self.question_set_identity != QUESTION_SET_IDENTITY
            or self.question_set_version != REVIEW_CONTRACT_VERSION
        ):
            raise ReviewError(ReviewFailure.INPUT_INVALID)


def create_review_handoff(run: ProbablesRun, result: ProbableMemberResult, *, created_at: datetime) -> ReviewHandoff:
    if (
        type(run) is not ProbablesRun
        or type(result) is not ProbableMemberResult
        or result not in run.results
        or result.state not in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
        or result.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
        or not _aware(created_at)
    ):
        raise ReviewError(ReviewFailure.NOT_ELIGIBLE)
    lineage = result.lineage
    evidence_lineage = tuple(item for item in (
        lineage.semantic_evidence_identity,
        lineage.narrow_cpr_fact_identity,
        lineage.one_hour_fact_identity,
        lineage.fifteen_minute_fact_identity,
        lineage.coherence_fact_identity,
        lineage.participation_fact_identity,
        *lineage.informational_fact_identities,
    ) if item is not None)
    values = {
        "probables_run_identity": run.run_identity,
        "probable_result_identity": result.result_identity,
        "source_discovery_run_identity": lineage.source_run_identity,
        "source_discovery_member_identity": lineage.source_member_identity,
        "canonical_subject_identity": result.canonical_subject_identity,
        "direction": result.direction.value,
        "market_session_identity": result.market_session_identity,
        "observation_boundary": result.observation_boundary,
        "methodology_identity": result.methodology_identity,
        "methodology_version": result.methodology_version,
        "universe_identity": run.universe_identity,
        "universe_version": run.universe_version,
        "reconciliation_identity": run.reconciliation_identity,
        "reconciliation_version": run.reconciliation_version,
        "evidence_lineage": evidence_lineage,
        "created_at": created_at,
        "provenance": ("WO-07", run.run_identity, result.result_identity),
        "schema_identity": REVIEW_HANDOFF_IDENTITY,
        "schema_version": REVIEW_CONTRACT_VERSION,
    }
    return ReviewHandoff(
        handoff_identity=_identity("INTRADAY-REVIEW-HANDOFF-", values),
        integrity_identity=_identity("INTEGRITY-REVIEW-HANDOFF-", values),
        **values,
    )


def create_review_cycle(handoff: ReviewHandoff) -> ReviewCycle:
    if type(handoff) is not ReviewHandoff:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    values = {
        "handoff_identity": handoff.handoff_identity,
        "probables_run_identity": handoff.probables_run_identity,
        "probable_result_identity": handoff.probable_result_identity,
        "canonical_subject_identity": handoff.canonical_subject_identity,
        "direction": handoff.direction,
        "created_at": handoff.created_at,
        "initial_review_state": ReviewState.CHART_REQUIRED,
        "visual_state": VisualState.NOT_ANALYZED,
        "answer_state": AnswerState.NOT_IMPORTED,
        "downstream_state": DownstreamState.NOT_ESTABLISHED,
        "provenance": ("WO-07", handoff.handoff_identity),
        "schema_identity": REVIEW_CYCLE_IDENTITY,
        "schema_version": REVIEW_CONTRACT_VERSION,
    }
    return ReviewCycle(
        cycle_identity=_identity("INTRADAY-REVIEW-CYCLE-", values),
        integrity_identity=_identity("INTEGRITY-REVIEW-CYCLE-", values),
        **values,
    )


def create_chart_revision(
    cycle: ReviewCycle,
    *,
    revision_ordinal: int,
    payload: bytes,
    media_type: str,
    received_at: datetime,
) -> ChartRevision:
    digest = sha256(payload).hexdigest()
    artifact_values = {
        "cycle_identity": cycle.cycle_identity,
        "payload_sha256": digest,
        "media_type": media_type,
    }
    values = {
        "chart_artifact_identity": _identity("INTRADAY-CHART-ARTIFACT-", artifact_values),
        "cycle_identity": cycle.cycle_identity,
        "probables_run_identity": cycle.probables_run_identity,
        "probable_result_identity": cycle.probable_result_identity,
        "expected_canonical_subject_identity": cycle.canonical_subject_identity,
        "direction": cycle.direction,
        "revision_ordinal": revision_ordinal,
        "payload_sha256": digest,
        "media_type": media_type,
        "byte_count": len(payload),
        "received_at": received_at,
        "timeframe_set": CHART_TIMEFRAMES,
        "provenance": ("WO-07", cycle.cycle_identity, "SPONSOR_MANUAL_UPLOAD"),
        "schema_identity": CHART_REVISION_IDENTITY,
        "schema_version": REVIEW_CONTRACT_VERSION,
    }
    return ChartRevision(
        chart_revision_identity=_identity("INTRADAY-CHART-REVISION-", values),
        integrity_identity=_identity("INTEGRITY-CHART-REVISION-", values),
        **values,
    )


def create_question_pack(handoff: ReviewHandoff, cycle: ReviewCycle, chart: ChartRevision) -> ReviewQuestionPack:
    if (
        type(handoff) is not ReviewHandoff
        or type(cycle) is not ReviewCycle
        or type(chart) is not ChartRevision
        or cycle.handoff_identity != handoff.handoff_identity
        or chart.cycle_identity != cycle.cycle_identity
    ):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    values = {
        "question_set_identity": QUESTION_SET_IDENTITY,
        "question_set_version": REVIEW_CONTRACT_VERSION,
        "probables_run_identity": handoff.probables_run_identity,
        "probable_result_identity": handoff.probable_result_identity,
        "discovery_run_identity": handoff.source_discovery_run_identity,
        "discovery_member_identity": handoff.source_discovery_member_identity,
        "expected_canonical_subject_identity": handoff.canonical_subject_identity,
        "proposed_direction": handoff.direction,
        "observation_boundary": handoff.observation_boundary,
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
        "provenance": ("WO-07", handoff.handoff_identity, cycle.cycle_identity, chart.chart_revision_identity),
        "schema_identity": QUESTION_PACK_IDENTITY,
        "schema_version": REVIEW_CONTRACT_VERSION,
    }
    return ReviewQuestionPack(
        review_pack_identity=_identity("INTRADAY-REVIEW-PACK-", values),
        integrity_identity=_identity("INTEGRITY-REVIEW-PACK-", values),
        **values,
    )


def create_current_pointer(run_identity: str, cycles: Iterable[ReviewCyclePointer]) -> CurrentReviewPointer:
    ordered = tuple(sorted(cycles, key=lambda item: item.probable_result_identity))
    values = {
        "probables_run_identity": run_identity,
        "cycles": ordered,
        "schema_identity": CURRENT_REVIEW_POINTER_IDENTITY,
        "schema_version": REVIEW_CONTRACT_VERSION,
    }
    return CurrentReviewPointer(
        integrity_identity=_identity("INTEGRITY-CURRENT-REVIEW-POINTER-", values),
        **values,
    )


def artifact_document(value: object) -> dict[str, object]:
    if type(value) not in {ReviewHandoff, ReviewCycle, ChartRevision, ReviewQuestionPack, CurrentReviewPointer}:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    return {"artifact_type": type(value).__name__, "value": _normalize(value)}


def artifact_bytes(value: object) -> bytes:
    return _canonical(artifact_document(value))


def artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded.decode("utf-8"))
        kind = document["artifact_type"]
        value = document["value"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error
    try:
        if kind == "ReviewHandoff":
            return ReviewHandoff(**_parse_handoff(value))
        if kind == "ReviewCycle":
            return ReviewCycle(**_parse_cycle(value))
        if kind == "ChartRevision":
            return ChartRevision(**_parse_chart(value))
        if kind == "ReviewQuestionPack":
            return ReviewQuestionPack(**_parse_pack(value))
        if kind == "CurrentReviewPointer":
            return CurrentReviewPointer(**_parse_pointer(value))
    except (KeyError, TypeError, ValueError, ReviewError) as error:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error
    raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def _parse_handoff(value: Mapping[str, object]) -> dict[str, object]:
    result = dict(value)
    result["observation_boundary"] = datetime.fromisoformat(str(result["observation_boundary"]))
    result["created_at"] = datetime.fromisoformat(str(result["created_at"]))
    result["evidence_lineage"] = tuple(result["evidence_lineage"])
    result["provenance"] = tuple(result["provenance"])
    return result


def _parse_cycle(value: Mapping[str, object]) -> dict[str, object]:
    result = dict(value)
    result["created_at"] = datetime.fromisoformat(str(result["created_at"]))
    result["initial_review_state"] = ReviewState(result["initial_review_state"])
    result["visual_state"] = VisualState(result["visual_state"])
    result["answer_state"] = AnswerState(result["answer_state"])
    result["downstream_state"] = DownstreamState(result["downstream_state"])
    result["provenance"] = tuple(result["provenance"])
    return result


def _parse_chart(value: Mapping[str, object]) -> dict[str, object]:
    result = dict(value)
    result["received_at"] = datetime.fromisoformat(str(result["received_at"]))
    result["timeframe_set"] = tuple(result["timeframe_set"])
    result["provenance"] = tuple(result["provenance"])
    return result


def _parse_pack(value: Mapping[str, object]) -> dict[str, object]:
    result = dict(value)
    result["observation_boundary"] = datetime.fromisoformat(str(result["observation_boundary"]))
    result["created_at"] = datetime.fromisoformat(str(result["created_at"]))
    result["questions"] = tuple(ReviewQuestion(
        question_id=item["question_id"], wording=item["wording"],
        allowed_answers=tuple(item["allowed_answers"]),
        timeframe_scope=tuple(item["timeframe_scope"]), authority=item["authority"],
        conditional_instruction=item.get("conditional_instruction"),
        constraints=tuple(item.get("constraints", ())),
    ) for item in result["questions"])
    result["observation_statuses"] = tuple(ObservationStatus(item) for item in result["observation_statuses"])
    result["provenance"] = tuple(result["provenance"])
    return result


def _parse_pointer(value: Mapping[str, object]) -> dict[str, object]:
    result = dict(value)
    result["cycles"] = tuple(ReviewCyclePointer(
        cycle_identity=item["cycle_identity"], probable_result_identity=item["probable_result_identity"],
        canonical_subject_identity=item["canonical_subject_identity"], direction=item["direction"],
        state=ReviewState(item["state"]), active_chart_revision_identity=item["active_chart_revision_identity"],
        active_review_pack_identity=item["active_review_pack_identity"],
    ) for item in result["cycles"])
    return result


def _verify(value: object, identity_name: str, identity_prefix: str, integrity_prefix: str) -> None:
    raw = _without(value, identity_name, "integrity_identity")
    if getattr(value, identity_name) != _identity(identity_prefix, raw) or getattr(value, "integrity_identity") != _identity(integrity_prefix, raw):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def _verify_integrity(value: object, prefix: str) -> None:
    if getattr(value, "integrity_identity") != _identity(prefix, _without(value, "integrity_identity")):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def _without(value: object, *names: str) -> dict[str, object]:
    return {name: item for name, item in asdict(value).items() if name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_canonical(_normalize(value))).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _normalize(value: object) -> object:
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
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Iterable[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


__all__ = [
    "CHART_ARTIFACT_IDENTITY", "CHART_REVISION_IDENTITY",
    "CHART_TIMEFRAMES", "CURRENT_REVIEW_POINTER_IDENTITY", "QUESTIONS",
    "QUESTION_PACK_IDENTITY", "QUESTION_SET_IDENTITY", "REVIEW_CONTRACT_VERSION",
    "REVIEW_CYCLE_IDENTITY", "REVIEW_HANDOFF_IDENTITY", "TRADING_PROHIBITION",
    "TRUST_BOUNDARY", "AnswerState", "ChartRevision", "CurrentReviewPointer",
    "DownstreamState", "FutureAnswerPackBinding", "FutureVisualAnswerIdentity", "ObservationStatus",
    "ReviewCycle", "ReviewCyclePointer", "ReviewError", "ReviewFailure",
    "ReviewHandoff", "ReviewQuestion", "ReviewQuestionPack", "ReviewState",
    "VisualState", "artifact_bytes", "artifact_document", "artifact_from_bytes",
    "create_chart_revision", "create_current_pointer", "create_question_pack",
    "create_review_cycle", "create_review_handoff",
]
