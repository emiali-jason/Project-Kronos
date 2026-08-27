"""Governed Intraday Chart Analyst Answer Pack and imported evidence contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Iterable, Mapping

from kronos.intraday.review import (
    CHART_TIMEFRAMES,
    QUESTIONS,
    QUESTION_SET_IDENTITY,
    REVIEW_CONTRACT_VERSION,
    ObservationStatus,
    ReviewError,
    ReviewFailure,
    ReviewQuestionPack,
)
from kronos.intraday.review_batch import ReviewBatchPdf
from kronos.intraday.review_transport import ReviewBatchTransport
from kronos.instrument.visual_identity import (
    VisualIdentityResolutionError,
    VisualIdentityResolutionFailure,
    VisualIdentityResolver,
    VisualIdentitySourceContext,
)


ANSWER_PACK_IDENTITY = "KRONOS-INTRADAY-CHART-ANALYST-ANSWER-PACK-V1"
IMPORTED_VISUAL_EVIDENCE_IDENTITY = "KRONOS-INTRADAY-IMPORTED-VISUAL-EVIDENCE-V1"
ANSWER_IMPORT_RECORD_IDENTITY = "KRONOS-INTRADAY-ANSWER-IMPORT-RECORD-V1"
VISUAL_EVIDENCE_POINTER_IDENTITY = "KRONOS-INTRADAY-VISUAL-EVIDENCE-POINTER-V1"
ANSWER_CONTRACT_VERSION = "1.0.0"
BATCH_ANSWER_PACK_IDENTITY = "KRONOS-INTRADAY-CHART-ANALYST-BATCH-ANSWER-PACK-V1"
MAX_ANSWER_BYTES = 1024 * 1024

_TOP_LEVEL_FIELDS = {
    "schema_identity",
    "schema_version",
    "question_set_identity",
    "question_set_version",
    "review_pack_identity",
    "review_cycle_identity",
    "review_request_identity",
    "chart_revision_identity",
    "expected_canonical_subject_identity",
    "observed_visible_subject_identity",
    "proposed_direction",
    "global_observation_status",
    "answers",
}
_ANSWER_FIELDS = {
    "question_id",
    "observation_status",
    "answer",
    "visible_timeframes",
    "visible_basis",
    "status_detail",
    "why_not_covered_elsewhere",
}
_BATCH_TOP_LEVEL_FIELDS = {
    "schema_identity",
    "schema_version",
    "question_set_identity",
    "question_set_version",
    "review_batch_identity",
    "probables_run_identity",
    "candidates",
}


class AnswerImportState(StrEnum):
    IMPORTED = "IMPORTED"
    ALREADY_IMPORTED = "ALREADY_IMPORTED"
    MISSING = "MISSING"
    INVALID = "INVALID"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class ChartAnalystBatchAnswerTransport:
    review_batch_identity: str
    probables_run_identity: str
    candidate_documents: tuple[Mapping[str, object], ...]
    source_sha256: str


def batch_answer_pack_filename(transport: ReviewBatchTransport) -> str:
    if type(transport) is not ReviewBatchTransport:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    return transport.expected_answer_filename


def batch_answer_pack_template(
    batch: ReviewBatchPdf,
    packs: Iterable[ReviewQuestionPack],
) -> bytes:
    retained = tuple(packs)
    if (
        type(batch) is not ReviewBatchPdf
        or tuple(pack.review_pack_identity for pack in retained)
        != tuple(member.review_pack_identity for member in batch.members)
    ):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    document = {
        "schema_identity": BATCH_ANSWER_PACK_IDENTITY,
        "schema_version": ANSWER_CONTRACT_VERSION,
        "question_set_identity": QUESTION_SET_IDENTITY,
        "question_set_version": REVIEW_CONTRACT_VERSION,
        "review_batch_identity": batch.batch_identity,
        "probables_run_identity": batch.probables_run_identity,
        "candidates": [json.loads(answer_pack_template(pack)) for pack in retained],
    }
    return _canonical(document) + b"\n"


def parse_batch_answer_transport(payload: bytes) -> ChartAnalystBatchAnswerTransport:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_ANSWER_BYTES:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID) from error
    if (
        type(document) is not dict
        or set(document) != _BATCH_TOP_LEVEL_FIELDS
        or document["schema_identity"] != BATCH_ANSWER_PACK_IDENTITY
        or document["schema_version"] != ANSWER_CONTRACT_VERSION
        or document["question_set_identity"] != QUESTION_SET_IDENTITY
        or document["question_set_version"] != REVIEW_CONTRACT_VERSION
        or not _text(document["review_batch_identity"])
        or not _text(document["probables_run_identity"])
        or type(document["candidates"]) is not list
        or not document["candidates"]
        or any(type(item) is not dict for item in document["candidates"])
    ):
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
    return ChartAnalystBatchAnswerTransport(
        review_batch_identity=document["review_batch_identity"],
        probables_run_identity=document["probables_run_identity"],
        candidate_documents=tuple(document["candidates"]),
        source_sha256=sha256(payload).hexdigest(),
    )


@dataclass(frozen=True, slots=True)
class ChartAnalystAnswer:
    question_id: str
    observation_status: ObservationStatus
    answer: str | None
    visible_timeframes: tuple[str, ...]
    visible_basis: str | None
    status_detail: str | None
    why_not_covered_elsewhere: str | None

    def __post_init__(self) -> None:
        question = next((item for item in QUESTIONS if item.question_id == self.question_id), None)
        if question is None or type(self.observation_status) is not ObservationStatus:
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        if any(item not in CHART_TIMEFRAMES for item in self.visible_timeframes):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        if len(set(self.visible_timeframes)) != len(self.visible_timeframes):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        if any(item not in question.timeframe_scope for item in self.visible_timeframes):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        present = self.observation_status in {ObservationStatus.OBSERVED, ObservationStatus.PARTIAL}
        if present:
            if self.answer not in question.allowed_answers or not _text(self.visible_basis):
                raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
            if not self.visible_timeframes:
                raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
            if self.observation_status is ObservationStatus.OBSERVED and self.visible_timeframes != question.timeframe_scope:
                raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
            if self.observation_status is ObservationStatus.PARTIAL and not _text(self.status_detail):
                raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        elif (
            self.answer is not None
            or self.visible_timeframes
            or self.visible_basis is not None
            or self.observation_status is not ObservationStatus.NOT_APPLICABLE and not _text(self.status_detail)
        ):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        if self.question_id == "Q7" and present and self.answer == "PRESENT" and not _text(self.visible_basis):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        if self.question_id == "Q10":
            if present and self.answer == "MATERIAL_OBSERVATION" and not _text(self.why_not_covered_elsewhere):
                raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
            if self.answer != "MATERIAL_OBSERVATION" and self.why_not_covered_elsewhere is not None:
                raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        elif self.why_not_covered_elsewhere is not None:
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)


@dataclass(frozen=True, slots=True)
class ChartAnalystAnswerPack:
    answer_pack_identity: str
    question_set_identity: str
    question_set_version: str
    review_pack_identity: str
    review_cycle_identity: str
    review_request_identity: str
    chart_revision_identity: str
    expected_canonical_subject_identity: str
    observed_visible_subject_identity: str | None
    proposed_direction: str
    global_observation_status: ObservationStatus
    answers: tuple[ChartAnalystAnswer, ...]
    source_sha256: str
    schema_identity: str = ANSWER_PACK_IDENTITY
    schema_version: str = ANSWER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.answer_pack_identity.startswith("INTRADAY-ANSWER-PACK-")
            or self.question_set_identity != QUESTION_SET_IDENTITY
            or self.question_set_version != REVIEW_CONTRACT_VERSION
            or not _texts((self.review_pack_identity, self.review_cycle_identity, self.review_request_identity,
                           self.chart_revision_identity, self.expected_canonical_subject_identity, self.proposed_direction))
            or self.observed_visible_subject_identity is not None and not _text(self.observed_visible_subject_identity)
            or self.proposed_direction not in {"LONG", "SHORT"}
            or type(self.global_observation_status) is not ObservationStatus
            or tuple(item.question_id for item in self.answers) != tuple(item.question_id for item in QUESTIONS)
            or re.fullmatch(r"[0-9a-f]{64}", self.source_sha256) is None
            or self.schema_identity != ANSWER_PACK_IDENTITY
            or self.schema_version != ANSWER_CONTRACT_VERSION
        ):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        statuses = tuple(item.observation_status for item in self.answers)
        if self.global_observation_status is ObservationStatus.OBSERVED:
            consistent = all(item is ObservationStatus.OBSERVED for item in statuses)
        elif self.global_observation_status is ObservationStatus.PARTIAL:
            consistent = (
                any(item in {ObservationStatus.OBSERVED, ObservationStatus.PARTIAL} for item in statuses)
                and not all(item is ObservationStatus.OBSERVED for item in statuses)
                and ObservationStatus.INVALID not in statuses
            )
        else:
            consistent = all(item is self.global_observation_status for item in statuses)
        if not consistent:
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        source_document = {
            "schema_identity": self.schema_identity,
            "schema_version": self.schema_version,
            "question_set_identity": self.question_set_identity,
            "question_set_version": self.question_set_version,
            "review_pack_identity": self.review_pack_identity,
            "review_cycle_identity": self.review_cycle_identity,
            "review_request_identity": self.review_request_identity,
            "chart_revision_identity": self.chart_revision_identity,
            "expected_canonical_subject_identity": self.expected_canonical_subject_identity,
            "observed_visible_subject_identity": self.observed_visible_subject_identity,
            "proposed_direction": self.proposed_direction,
            "global_observation_status": self.global_observation_status,
            "answers": self.answers,
        }
        identity_values = {
            "question_set_identity": self.question_set_identity,
            "question_set_version": self.question_set_version,
            "review_pack_identity": self.review_pack_identity,
            "review_cycle_identity": self.review_cycle_identity,
            "review_request_identity": self.review_request_identity,
            "chart_revision_identity": self.chart_revision_identity,
            "expected_canonical_subject_identity": self.expected_canonical_subject_identity,
            "observed_visible_subject_identity": self.observed_visible_subject_identity,
            "proposed_direction": self.proposed_direction,
            "global_observation_status": self.global_observation_status,
            "answers": self.answers,
            "schema_identity": self.schema_identity,
            "schema_version": self.schema_version,
        }
        if (
            self.source_sha256 != sha256(_canonical(_normalize(source_document))).hexdigest()
            or self.answer_pack_identity != _identity("INTRADAY-ANSWER-PACK-", identity_values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


@dataclass(frozen=True, slots=True)
class ImportedVisualEvidence:
    visual_evidence_identity: str
    answer_pack_identity: str
    question_set_identity: str
    question_set_version: str
    probables_run_identity: str
    probable_result_identity: str
    review_pack_identity: str
    review_cycle_identity: str
    review_request_identity: str
    chart_revision_identity: str
    chart_artifact_identity: str
    expected_canonical_subject_identity: str
    observed_visible_subject_identity: str
    proposed_direction: str
    global_observation_status: ObservationStatus
    answers: tuple[ChartAnalystAnswer, ...]
    imported_at: datetime
    provenance: tuple[str, ...]
    integrity_identity: str
    resolved_canonical_subject_identity: str | None = None
    visual_identity_source_context: str | None = None
    visual_identity_governed_observation_boundary: datetime | None = None
    visual_identity_relationship_identity: str | None = None
    visual_identity_relationship_integrity_identity: str | None = None
    visual_identity_publication_identity: str | None = None
    visual_identity_publication_version: str | None = None
    visual_identity_publication_integrity_identity: str | None = None
    schema_identity: str = IMPORTED_VISUAL_EVIDENCE_IDENTITY
    schema_version: str = ANSWER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        relationship_evidence = (
            self.resolved_canonical_subject_identity,
            self.visual_identity_source_context,
            self.visual_identity_relationship_identity,
            self.visual_identity_relationship_integrity_identity,
            self.visual_identity_publication_identity,
            self.visual_identity_publication_version,
            self.visual_identity_publication_integrity_identity,
        )
        legacy = all(item is None for item in relationship_evidence) and self.visual_identity_governed_observation_boundary is None
        governed = (
            all(_text(item) for item in relationship_evidence)
            and _aware(self.visual_identity_governed_observation_boundary)
            and self.resolved_canonical_subject_identity == self.expected_canonical_subject_identity
            and self.visual_identity_source_context
            == VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART.value
        )
        if (
            not self.visual_evidence_identity.startswith("INTRADAY-VISUAL-EVIDENCE-")
            or not _texts((self.answer_pack_identity, self.probables_run_identity, self.probable_result_identity,
                           self.review_pack_identity, self.review_cycle_identity, self.review_request_identity,
                           self.chart_revision_identity, self.chart_artifact_identity,
                           self.expected_canonical_subject_identity, self.observed_visible_subject_identity,
                           self.proposed_direction))
            or not (legacy or governed)
            or legacy
            and self.expected_canonical_subject_identity
            != self.observed_visible_subject_identity
            or self.question_set_identity != QUESTION_SET_IDENTITY
            or self.question_set_version != REVIEW_CONTRACT_VERSION
            or self.global_observation_status is ObservationStatus.INVALID
            or tuple(item.question_id for item in self.answers) != tuple(item.question_id for item in QUESTIONS)
            or not _aware(self.imported_at)
            or not _texts(self.provenance)
            or self.schema_identity != IMPORTED_VISUAL_EVIDENCE_IDENTITY
            or self.schema_version != ANSWER_CONTRACT_VERSION
        ):
            raise ReviewError(ReviewFailure.ANSWER_INVALID)
        if legacy:
            _verify_legacy_visual_evidence(self)
        else:
            _verify(self, "visual_evidence_identity", "INTRADAY-VISUAL-EVIDENCE-", "INTEGRITY-VISUAL-EVIDENCE-")


@dataclass(frozen=True, slots=True)
class AnswerImportRecord:
    import_identity: str
    review_pack_identity: str
    review_cycle_identity: str
    expected_canonical_subject_identity: str
    answer_filename: str
    answer_sha256: str | None
    state: AnswerImportState
    failure: str | None
    answer_pack_identity: str | None
    visual_evidence_identity: str | None
    imported_at: datetime
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = ANSWER_IMPORT_RECORD_IDENTITY
    schema_version: str = ANSWER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.import_identity.startswith("INTRADAY-ANSWER-IMPORT-")
            or not _texts((self.review_pack_identity, self.review_cycle_identity,
                           self.expected_canonical_subject_identity, self.answer_filename))
            or self.answer_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", self.answer_sha256) is None
            or type(self.state) is not AnswerImportState
            or self.state in {AnswerImportState.IMPORTED, AnswerImportState.ALREADY_IMPORTED}
            and (not _text(self.answer_pack_identity) or not _text(self.visual_evidence_identity) or self.failure is not None)
            or self.state not in {AnswerImportState.IMPORTED, AnswerImportState.ALREADY_IMPORTED}
            and (self.answer_pack_identity is not None or self.visual_evidence_identity is not None or not _text(self.failure))
            or not _aware(self.imported_at)
            or not _texts(self.provenance)
            or self.schema_identity != ANSWER_IMPORT_RECORD_IDENTITY
            or self.schema_version != ANSWER_CONTRACT_VERSION
        ):
            raise ReviewError(ReviewFailure.ANSWER_INVALID)
        _verify(self, "import_identity", "INTRADAY-ANSWER-IMPORT-", "INTEGRITY-ANSWER-IMPORT-")


@dataclass(frozen=True, slots=True)
class VisualEvidencePointer:
    review_pack_identity: str
    review_cycle_identity: str
    chart_revision_identity: str
    answer_pack_identity: str
    import_identity: str
    visual_evidence_identity: str
    integrity_identity: str
    schema_identity: str = VISUAL_EVIDENCE_POINTER_IDENTITY
    schema_version: str = ANSWER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            not _texts((self.review_pack_identity, self.review_cycle_identity, self.chart_revision_identity,
                        self.answer_pack_identity, self.import_identity, self.visual_evidence_identity))
            or self.schema_identity != VISUAL_EVIDENCE_POINTER_IDENTITY
            or self.schema_version != ANSWER_CONTRACT_VERSION
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        _verify_integrity(self, "INTEGRITY-VISUAL-EVIDENCE-POINTER-")


def answer_pack_filename(pack: ReviewQuestionPack) -> str:
    instrument = re.sub(r"[^A-Z0-9_-]", "-", pack.expected_canonical_subject_identity.upper())
    cycle = pack.review_cycle_identity.rsplit("-", 1)[-1][:12]
    revision = pack.chart_revision_identity.rsplit("-", 1)[-1][:12]
    return f"{instrument}_INTRADAY_ANSWER_{cycle}_CHART-{revision}_QV1.json"


def answer_pack_template(pack: ReviewQuestionPack) -> bytes:
    if type(pack) is not ReviewQuestionPack:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    document = {
        "schema_identity": ANSWER_PACK_IDENTITY,
        "schema_version": ANSWER_CONTRACT_VERSION,
        "question_set_identity": pack.question_set_identity,
        "question_set_version": pack.question_set_version,
        "review_pack_identity": pack.review_pack_identity,
        "review_cycle_identity": pack.review_cycle_identity,
        "review_request_identity": pack.review_request_identity,
        "chart_revision_identity": pack.chart_revision_identity,
        "expected_canonical_subject_identity": pack.expected_canonical_subject_identity,
        "observed_visible_subject_identity": None,
        "proposed_direction": pack.proposed_direction,
        "global_observation_status": ObservationStatus.INVALID.value,
        "answers": [{
            "question_id": question.question_id,
            "observation_status": ObservationStatus.INVALID.value,
            "answer": None,
            "visible_timeframes": [],
            "visible_basis": None,
            "status_detail": "REPLACE WITH GOVERNED OBSERVATION",
            "why_not_covered_elsewhere": None,
        } for question in QUESTIONS],
    }
    return _canonical(document) + b"\n"


def parse_answer_pack(payload: bytes) -> ChartAnalystAnswerPack:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_ANSWER_BYTES:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID) from error
    if type(document) is not dict or set(document) != _TOP_LEVEL_FIELDS or type(document["answers"]) is not list:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
    try:
        answers = tuple(_parse_answer(item) for item in document["answers"])
        normalized = dict(document)
        normalized["answers"] = [_normalize(item) for item in answers]
        source = _canonical(normalized)
        values = {
            "question_set_identity": document["question_set_identity"],
            "question_set_version": document["question_set_version"],
            "review_pack_identity": document["review_pack_identity"],
            "review_cycle_identity": document["review_cycle_identity"],
            "review_request_identity": document["review_request_identity"],
            "chart_revision_identity": document["chart_revision_identity"],
            "expected_canonical_subject_identity": document["expected_canonical_subject_identity"],
            "observed_visible_subject_identity": document["observed_visible_subject_identity"],
            "proposed_direction": document["proposed_direction"],
            "global_observation_status": ObservationStatus(document["global_observation_status"]),
            "answers": answers,
            "source_sha256": sha256(source).hexdigest(),
            "schema_identity": document["schema_identity"],
            "schema_version": document["schema_version"],
        }
        identity_values = dict(values)
        identity_values.pop("source_sha256")
        return ChartAnalystAnswerPack(
            answer_pack_identity=_identity("INTRADAY-ANSWER-PACK-", identity_values),
            **values,
        )
    except (KeyError, TypeError, ValueError, ReviewError) as error:
        if isinstance(error, ReviewError):
            raise
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID) from error


def bind_imported_evidence(
    pack: ReviewQuestionPack,
    answer: ChartAnalystAnswerPack,
    *,
    imported_at: datetime,
    visual_identity_resolver: VisualIdentityResolver,
) -> ImportedVisualEvidence:
    if (
        type(pack) is not ReviewQuestionPack
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
    if any(left != right for left, right in bindings):
        raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
    if answer.observed_visible_subject_identity is None:
        raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
    try:
        resolution = visual_identity_resolver.resolve(
            observed_visible_subject_identity=answer.observed_visible_subject_identity,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=pack.observation_boundary,
        )
    except VisualIdentityResolutionError as error:
        if error.failure is VisualIdentityResolutionFailure.RELATIONSHIP_AMBIGUOUS:
            raise ReviewError(
                ReviewFailure.VISUAL_IDENTITY_RELATIONSHIP_AMBIGUOUS
            ) from error
        if error.failure in {
            VisualIdentityResolutionFailure.RELATIONSHIP_UNAVAILABLE,
            VisualIdentityResolutionFailure.PUBLICATION_STALE,
        }:
            raise ReviewError(
                ReviewFailure.VISUAL_IDENTITY_RELATIONSHIP_UNAVAILABLE
            ) from error
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error
    if resolution.canonical_subject_identity != pack.expected_canonical_subject_identity:
        raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
    if answer.global_observation_status is ObservationStatus.INVALID:
        raise ReviewError(ReviewFailure.ANSWER_INVALID)
    values = {
        "answer_pack_identity": answer.answer_pack_identity,
        "question_set_identity": answer.question_set_identity,
        "question_set_version": answer.question_set_version,
        "probables_run_identity": pack.probables_run_identity,
        "probable_result_identity": pack.probable_result_identity,
        "review_pack_identity": pack.review_pack_identity,
        "review_cycle_identity": pack.review_cycle_identity,
        "review_request_identity": pack.review_request_identity,
        "chart_revision_identity": pack.chart_revision_identity,
        "chart_artifact_identity": pack.chart_artifact_identity,
        "expected_canonical_subject_identity": pack.expected_canonical_subject_identity,
        "observed_visible_subject_identity": answer.observed_visible_subject_identity,
        "proposed_direction": pack.proposed_direction,
        "global_observation_status": answer.global_observation_status,
        "answers": answer.answers,
        "imported_at": imported_at,
        "provenance": ("WO-09", pack.review_pack_identity, answer.answer_pack_identity),
        "resolved_canonical_subject_identity": resolution.canonical_subject_identity,
        "visual_identity_source_context": resolution.source_context.value,
        "visual_identity_governed_observation_boundary": resolution.governed_observation_boundary,
        "visual_identity_relationship_identity": resolution.relationship_identity,
        "visual_identity_relationship_integrity_identity": resolution.relationship_integrity_identity,
        "visual_identity_publication_identity": resolution.publication_identity,
        "visual_identity_publication_version": resolution.publication_version,
        "visual_identity_publication_integrity_identity": resolution.publication_integrity_identity,
        "schema_identity": IMPORTED_VISUAL_EVIDENCE_IDENTITY,
        "schema_version": ANSWER_CONTRACT_VERSION,
    }
    return ImportedVisualEvidence(
        visual_evidence_identity=_identity("INTRADAY-VISUAL-EVIDENCE-", values),
        integrity_identity=_identity("INTEGRITY-VISUAL-EVIDENCE-", values),
        **values,
    )


def create_import_record(
    pack: ReviewQuestionPack,
    *,
    answer_filename: str,
    answer_sha256: str | None,
    state: AnswerImportState,
    imported_at: datetime,
    failure: str | None = None,
    answer_pack_identity: str | None = None,
    visual_evidence_identity: str | None = None,
) -> AnswerImportRecord:
    values = {
        "review_pack_identity": pack.review_pack_identity,
        "review_cycle_identity": pack.review_cycle_identity,
        "expected_canonical_subject_identity": pack.expected_canonical_subject_identity,
        "answer_filename": answer_filename,
        "answer_sha256": answer_sha256,
        "state": state,
        "failure": failure,
        "answer_pack_identity": answer_pack_identity,
        "visual_evidence_identity": visual_evidence_identity,
        "imported_at": imported_at,
        "provenance": ("WO-09", pack.review_pack_identity),
        "schema_identity": ANSWER_IMPORT_RECORD_IDENTITY,
        "schema_version": ANSWER_CONTRACT_VERSION,
    }
    return AnswerImportRecord(
        import_identity=_identity("INTRADAY-ANSWER-IMPORT-", values),
        integrity_identity=_identity("INTEGRITY-ANSWER-IMPORT-", values),
        **values,
    )


def create_visual_evidence_pointer(evidence: ImportedVisualEvidence, record: AnswerImportRecord) -> VisualEvidencePointer:
    if record.visual_evidence_identity != evidence.visual_evidence_identity or record.answer_pack_identity != evidence.answer_pack_identity:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    values = {
        "review_pack_identity": evidence.review_pack_identity,
        "review_cycle_identity": evidence.review_cycle_identity,
        "chart_revision_identity": evidence.chart_revision_identity,
        "answer_pack_identity": evidence.answer_pack_identity,
        "import_identity": record.import_identity,
        "visual_evidence_identity": evidence.visual_evidence_identity,
        "schema_identity": VISUAL_EVIDENCE_POINTER_IDENTITY,
        "schema_version": ANSWER_CONTRACT_VERSION,
    }
    return VisualEvidencePointer(
        integrity_identity=_identity("INTEGRITY-VISUAL-EVIDENCE-POINTER-", values),
        **values,
    )


def answer_artifact_bytes(value: object) -> bytes:
    if type(value) not in {ChartAnalystAnswerPack, ImportedVisualEvidence, AnswerImportRecord, VisualEvidencePointer}:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    return _canonical({"artifact_type": type(value).__name__, "value": _normalize(value)})


def answer_artifact_from_bytes(payload: bytes) -> object:
    try:
        document = json.loads(payload.decode("utf-8"))
        if type(document) is not dict or set(document) != {"artifact_type", "value"} or type(document["value"]) is not dict:
            raise ValueError
        kind, raw = document["artifact_type"], dict(document["value"])
        if kind == "ChartAnalystAnswerPack":
            raw["global_observation_status"] = ObservationStatus(raw["global_observation_status"])
            raw["answers"] = tuple(_restore_answer(item) for item in raw["answers"])
            return ChartAnalystAnswerPack(**raw)
        if kind == "ImportedVisualEvidence":
            raw["global_observation_status"] = ObservationStatus(raw["global_observation_status"])
            raw["answers"] = tuple(_restore_answer(item) for item in raw["answers"])
            raw["imported_at"] = datetime.fromisoformat(raw["imported_at"])
            if raw.get("visual_identity_governed_observation_boundary") is not None:
                raw["visual_identity_governed_observation_boundary"] = datetime.fromisoformat(
                    raw["visual_identity_governed_observation_boundary"]
                )
            raw["provenance"] = tuple(raw["provenance"])
            return ImportedVisualEvidence(**raw)
        if kind == "AnswerImportRecord":
            raw["state"] = AnswerImportState(raw["state"])
            raw["imported_at"] = datetime.fromisoformat(raw["imported_at"])
            raw["provenance"] = tuple(raw["provenance"])
            return AnswerImportRecord(**raw)
        if kind == "VisualEvidencePointer":
            return VisualEvidencePointer(**raw)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, ReviewError) as error:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error
    raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def _parse_answer(value: object) -> ChartAnalystAnswer:
    if type(value) is not dict or set(value) != _ANSWER_FIELDS or type(value["visible_timeframes"]) is not list:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
    return ChartAnalystAnswer(
        question_id=value["question_id"],
        observation_status=ObservationStatus(value["observation_status"]),
        answer=value["answer"],
        visible_timeframes=tuple(value["visible_timeframes"]),
        visible_basis=value["visible_basis"],
        status_detail=value["status_detail"],
        why_not_covered_elsewhere=value["why_not_covered_elsewhere"],
    )


def _restore_answer(value: Mapping[str, object]) -> ChartAnalystAnswer:
    raw = dict(value)
    raw["observation_status"] = ObservationStatus(raw["observation_status"])
    raw["visible_timeframes"] = tuple(raw["visible_timeframes"])
    return ChartAnalystAnswer(**raw)


def _verify(value: object, identity_name: str, identity_prefix: str, integrity_prefix: str) -> None:
    raw = _without(value, identity_name, "integrity_identity")
    if getattr(value, identity_name) != _identity(identity_prefix, raw) or getattr(value, "integrity_identity") != _identity(integrity_prefix, raw):
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def _verify_legacy_visual_evidence(value: ImportedVisualEvidence) -> None:
    additions = (
        "resolved_canonical_subject_identity",
        "visual_identity_source_context",
        "visual_identity_governed_observation_boundary",
        "visual_identity_relationship_identity",
        "visual_identity_relationship_integrity_identity",
        "visual_identity_publication_identity",
        "visual_identity_publication_version",
        "visual_identity_publication_integrity_identity",
    )
    raw = _without(value, "visual_evidence_identity", "integrity_identity", *additions)
    if (
        value.visual_evidence_identity
        != _identity("INTRADAY-VISUAL-EVIDENCE-", raw)
        or value.integrity_identity
        != _identity("INTEGRITY-VISUAL-EVIDENCE-", raw)
    ):
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
    "ANSWER_CONTRACT_VERSION", "ANSWER_IMPORT_RECORD_IDENTITY", "ANSWER_PACK_IDENTITY",
    "BATCH_ANSWER_PACK_IDENTITY",
    "IMPORTED_VISUAL_EVIDENCE_IDENTITY", "MAX_ANSWER_BYTES", "VISUAL_EVIDENCE_POINTER_IDENTITY",
    "AnswerImportRecord", "AnswerImportState", "ChartAnalystAnswer", "ChartAnalystAnswerPack",
    "ChartAnalystBatchAnswerTransport",
    "ImportedVisualEvidence", "VisualEvidencePointer", "answer_artifact_bytes",
    "answer_artifact_from_bytes", "answer_pack_filename", "answer_pack_template",
    "batch_answer_pack_filename", "batch_answer_pack_template",
    "bind_imported_evidence", "create_import_record", "create_visual_evidence_pointer",
    "parse_answer_pack", "parse_batch_answer_transport",
]
