"""Strict Answer import for independent MCX and reference observations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Mapping

from kronos.instrument.visual_identity import (
    VisualIdentityResolution,
    VisualIdentityResolver,
    VisualIdentitySourceContext,
)
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_mcx_paired import (
    MCX_PAIRED_CONTRACT_VERSION,
    MCX_PAIRED_IMPORTED_EVIDENCE_IDENTITY,
    MCX_PAIRED_QUESTIONS,
    MCX_PAIRED_QUESTION_SET_IDENTITY,
    MCX_PAIRED_QUESTION_SET_VERSION,
    MCX_PAIRED_REVIEW_PACK_IDENTITY,
    McxPairedChartBundle,
    McxPairedChartRevision,
    McxPairedQuestion,
    McxPairedReviewPack,
)


MCX_PAIRED_ANSWER_PACK_IDENTITY = "KRONOS-INTRADAY-MCX-PAIRED-ANSWER-PACK-V1"
MCX_PAIRED_ANSWER_PACK_VERSION = "1.0.0"
MAX_MCX_PAIRED_ANSWER_BYTES = 1_000_000
_TOP_LEVEL = frozenset({
    "schema_identity", "schema_version", "question_set_identity",
    "question_set_version", "review_pack_identity", "paired_bundle_identity",
    "review_cycle_identity", "canonical_mcx_subject_identity", "direction",
    "native_observed_visible_identity", "reference_observed_visible_identity",
    "native_answers", "reference_answers", "escape_hatch_answer",
})
_ANSWER_FIELDS = frozenset({"question_id", "answer", "note"})


@dataclass(frozen=True, slots=True)
class McxPairedAnswer:
    question_id: str
    answer: str
    note: str | None

    def __post_init__(self) -> None:
        question = _question(self.question_id)
        if self.answer not in question.allowed_answers or self.note is not None and (
            type(self.note) is not str or self.note != self.note.strip() or len(self.note) > 2_000
        ):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        if self.question_id == "X01":
            if self.answer == "NONE" and self.note not in {None, ""}:
                raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
            if self.answer == "MATERIAL_OBSERVATION" and not self.note:
                raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        elif self.note not in {None, ""}:
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)


@dataclass(frozen=True, slots=True)
class McxPairedAnswerPack:
    answer_pack_identity: str
    source_sha256: str
    question_set_identity: str
    question_set_version: str
    review_pack_identity: str
    paired_bundle_identity: str
    review_cycle_identity: str
    canonical_mcx_subject_identity: str
    direction: str
    native_observed_visible_identity: str
    reference_observed_visible_identity: str
    native_answers: tuple[McxPairedAnswer, ...]
    reference_answers: tuple[McxPairedAnswer, ...]
    escape_hatch_answer: McxPairedAnswer
    schema_identity: str = MCX_PAIRED_ANSWER_PACK_IDENTITY
    schema_version: str = MCX_PAIRED_ANSWER_PACK_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "answer_pack_identity")
        if (
            not _sha(self.source_sha256)
            or self.question_set_identity != MCX_PAIRED_QUESTION_SET_IDENTITY
            or self.question_set_version != MCX_PAIRED_QUESTION_SET_VERSION
            or not _texts((self.review_pack_identity, self.paired_bundle_identity,
                           self.review_cycle_identity, self.canonical_mcx_subject_identity,
                           self.direction, self.native_observed_visible_identity,
                           self.reference_observed_visible_identity))
            or self.direction not in {"LONG", "SHORT"}
            or tuple(item.question_id for item in self.native_answers) != tuple(item.question_id for item in MCX_PAIRED_QUESTIONS[:10])
            or tuple(item.question_id for item in self.reference_answers) != tuple(item.question_id for item in MCX_PAIRED_QUESTIONS[10:16])
            or self.escape_hatch_answer.question_id != "X01"
            or self.schema_identity != MCX_PAIRED_ANSWER_PACK_IDENTITY
            or self.schema_version != MCX_PAIRED_ANSWER_PACK_VERSION
            or self.answer_pack_identity != _identity("INTRADAY-MCX-PAIRED-ANSWER-PACK-", values)
        ):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)


@dataclass(frozen=True, slots=True)
class McxPairedImportedVisualEvidence:
    visual_evidence_identity: str
    answer_pack_identity: str
    answer_source_sha256: str
    review_pack_identity: str
    paired_bundle_identity: str
    review_cycle_identity: str
    canonical_mcx_subject_identity: str
    actual_derivative_contract_identity: str
    active_binding_identity: str
    direction: str
    phase: str
    analysis_boundary: datetime
    native_expected_visible_identity: str
    native_observed_visible_identity: str
    native_resolution: VisualIdentityResolution
    reference_expected_visible_identity: str
    reference_observed_visible_identity: str
    reference_resolution: VisualIdentityResolution
    native_answers: tuple[McxPairedAnswer, ...]
    reference_answers: tuple[McxPairedAnswer, ...]
    escape_hatch_answer: McxPairedAnswer
    imported_at: datetime
    integrity_identity: str
    authority: str = "INDEPENDENT_VISUAL_OBSERVATION_ONLY"
    schema_identity: str = MCX_PAIRED_IMPORTED_EVIDENCE_IDENTITY
    schema_version: str = MCX_PAIRED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "visual_evidence_identity", "integrity_identity")
        if (
            not _texts((self.answer_pack_identity, self.review_pack_identity,
                        self.paired_bundle_identity, self.review_cycle_identity,
                        self.canonical_mcx_subject_identity,
                        self.actual_derivative_contract_identity, self.active_binding_identity,
                        self.direction, self.phase, self.native_expected_visible_identity,
                        self.native_observed_visible_identity,
                        self.reference_expected_visible_identity,
                        self.reference_observed_visible_identity))
            or not _sha(self.answer_source_sha256)
            or self.direction not in {"LONG", "SHORT"}
            or not _aware(self.analysis_boundary) or not _aware(self.imported_at)
            or type(self.native_resolution) is not VisualIdentityResolution
            or type(self.reference_resolution) is not VisualIdentityResolution
            or self.native_resolution.canonical_subject_identity != self.canonical_mcx_subject_identity
            or self.native_resolution.observed_visible_subject_identity != self.native_observed_visible_identity
            or self.reference_resolution.observed_visible_subject_identity != self.reference_observed_visible_identity
            or self.authority != "INDEPENDENT_VISUAL_OBSERVATION_ONLY"
            or self.schema_identity != MCX_PAIRED_IMPORTED_EVIDENCE_IDENTITY
            or self.schema_version != MCX_PAIRED_CONTRACT_VERSION
            or self.visual_evidence_identity != _identity("INTRADAY-MCX-PAIRED-VISUAL-EVIDENCE-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-PAIRED-VISUAL-EVIDENCE-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def parse_mcx_paired_answer(payload: bytes) -> McxPairedAnswerPack:
    if type(payload) is not bytes or not payload or len(payload) > MAX_MCX_PAIRED_ANSWER_BYTES:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
    try:
        document = json.loads(payload.decode("utf-8"))
        if type(document) is not dict or frozenset(document) != _TOP_LEVEL:
            raise ValueError
        native = _parse_answer_block(document["native_answers"], MCX_PAIRED_QUESTIONS[:10])
        reference = _parse_answer_block(document["reference_answers"], MCX_PAIRED_QUESTIONS[10:16])
        escape = _parse_one(document["escape_hatch_answer"], MCX_PAIRED_QUESTIONS[16])
        values = {
            **{name: document[name] for name in (
                "question_set_identity", "question_set_version", "review_pack_identity",
                "paired_bundle_identity", "review_cycle_identity",
                "canonical_mcx_subject_identity", "direction",
                "native_observed_visible_identity", "reference_observed_visible_identity",
                "schema_identity", "schema_version",
            )},
            "source_sha256": sha256(payload).hexdigest(),
            "native_answers": native,
            "reference_answers": reference,
            "escape_hatch_answer": escape,
        }
        return McxPairedAnswerPack(
            answer_pack_identity=_identity("INTRADAY-MCX-PAIRED-ANSWER-PACK-", values),
            **values,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID) from error


def bind_mcx_paired_import(
    *, pack: McxPairedReviewPack, bundle: McxPairedChartBundle,
    native_chart: McxPairedChartRevision, reference_chart: McxPairedChartRevision,
    answer: McxPairedAnswerPack, native_resolver: VisualIdentityResolver,
    reference_resolver: VisualIdentityResolver, imported_at: datetime,
) -> McxPairedImportedVisualEvidence:
    if (
        type(pack) is not McxPairedReviewPack or type(bundle) is not McxPairedChartBundle
        or type(answer) is not McxPairedAnswerPack
        or answer.review_pack_identity != pack.review_pack_identity
        or answer.paired_bundle_identity != bundle.bundle_identity
        or answer.review_cycle_identity != pack.review_cycle_identity
        or answer.canonical_mcx_subject_identity != pack.canonical_mcx_subject_identity
        or answer.direction != pack.direction
        or bundle.native_chart_revision_identity != native_chart.chart_revision_identity
        or bundle.reference_chart_revision_identity != reference_chart.chart_revision_identity
        or not _aware(imported_at)
    ):
        raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
    native = native_resolver.resolve(
        observed_visible_subject_identity=answer.native_observed_visible_identity,
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        governed_observation_boundary=bundle.analysis_boundary,
    )
    reference = reference_resolver.resolve(
        observed_visible_subject_identity=answer.reference_observed_visible_identity,
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        governed_observation_boundary=bundle.analysis_boundary,
    )
    if (
        native.canonical_subject_identity != bundle.canonical_mcx_subject_identity
        or reference.canonical_subject_identity != bundle.reference_relationship.reference_analytical_subject_identity
        or answer.reference_observed_visible_identity != bundle.reference_relationship.governed_visible_identity
    ):
        raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
    values = {
        "answer_pack_identity": answer.answer_pack_identity,
        "answer_source_sha256": answer.source_sha256,
        "review_pack_identity": pack.review_pack_identity,
        "paired_bundle_identity": bundle.bundle_identity,
        "review_cycle_identity": bundle.review_cycle_identity,
        "canonical_mcx_subject_identity": bundle.canonical_mcx_subject_identity,
        "actual_derivative_contract_identity": bundle.native_identity_binding.actual_derivative_contract_identity,
        "active_binding_identity": bundle.native_identity_binding.active_binding_identity,
        "direction": bundle.direction,
        "phase": bundle.phase,
        "analysis_boundary": bundle.analysis_boundary,
        "native_expected_visible_identity": native_chart.expected_visible_identity,
        "native_observed_visible_identity": answer.native_observed_visible_identity,
        "native_resolution": native,
        "reference_expected_visible_identity": reference_chart.expected_visible_identity,
        "reference_observed_visible_identity": answer.reference_observed_visible_identity,
        "reference_resolution": reference,
        "native_answers": answer.native_answers,
        "reference_answers": answer.reference_answers,
        "escape_hatch_answer": answer.escape_hatch_answer,
        "imported_at": imported_at,
        "authority": "INDEPENDENT_VISUAL_OBSERVATION_ONLY",
        "schema_identity": MCX_PAIRED_IMPORTED_EVIDENCE_IDENTITY,
        "schema_version": MCX_PAIRED_CONTRACT_VERSION,
    }
    return McxPairedImportedVisualEvidence(
        visual_evidence_identity=_identity("INTRADAY-MCX-PAIRED-VISUAL-EVIDENCE-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-PAIRED-VISUAL-EVIDENCE-", values),
        **values,
    )


def answer_template(pack: McxPairedReviewPack, bundle: McxPairedChartBundle) -> bytes:
    if pack.paired_bundle_identity != bundle.bundle_identity:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
    def row(question: McxPairedQuestion) -> dict[str, object]:
        return {"question_id": question.question_id, "answer": question.allowed_answers[0], "note": None}
    document = {
        "schema_identity": MCX_PAIRED_ANSWER_PACK_IDENTITY,
        "schema_version": MCX_PAIRED_ANSWER_PACK_VERSION,
        "question_set_identity": pack.question_set_identity,
        "question_set_version": pack.question_set_version,
        "review_pack_identity": pack.review_pack_identity,
        "paired_bundle_identity": bundle.bundle_identity,
        "review_cycle_identity": pack.review_cycle_identity,
        "canonical_mcx_subject_identity": pack.canonical_mcx_subject_identity,
        "direction": pack.direction,
        "native_observed_visible_identity": "REPLACE_WITH_EXACT_VISIBLE_NATIVE_IDENTITY",
        "reference_observed_visible_identity": bundle.reference_relationship.governed_visible_identity,
        "native_answers": [row(item) for item in MCX_PAIRED_QUESTIONS[:10]],
        "reference_answers": [row(item) for item in MCX_PAIRED_QUESTIONS[10:16]],
        "escape_hatch_answer": {"question_id": "X01", "answer": "NONE", "note": None},
    }
    return _canonical(document) + b"\n"


def answer_artifact_from_bytes(payload: bytes) -> McxPairedAnswerPack | McxPairedImportedVisualEvidence:
    try:
        raw = json.loads(payload.decode("utf-8"))
        if type(raw) is not dict:
            raise ValueError
        values = dict(raw)
        for name in ("native_answers", "reference_answers"):
            values[name] = tuple(McxPairedAnswer(**item) for item in values[name])
        values["escape_hatch_answer"] = McxPairedAnswer(**values["escape_hatch_answer"])
        if values.get("schema_identity") == MCX_PAIRED_ANSWER_PACK_IDENTITY:
            value: McxPairedAnswerPack | McxPairedImportedVisualEvidence = McxPairedAnswerPack(**values)
        elif values.get("schema_identity") == MCX_PAIRED_IMPORTED_EVIDENCE_IDENTITY:
            values["analysis_boundary"] = datetime.fromisoformat(values["analysis_boundary"])
            values["imported_at"] = datetime.fromisoformat(values["imported_at"])
            for name in ("native_resolution", "reference_resolution"):
                resolution = values[name]
                resolution["source_context"] = VisualIdentitySourceContext(resolution["source_context"])
                resolution["governed_observation_boundary"] = datetime.fromisoformat(resolution["governed_observation_boundary"])
                values[name] = VisualIdentityResolution(**resolution)
            value = McxPairedImportedVisualEvidence(**values)
        else:
            raise ValueError
        from kronos.intraday.review_mcx_paired import artifact_bytes
        if artifact_bytes(value) != payload:
            raise ValueError
        return value
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error


def _parse_answer_block(value: object, questions: tuple[McxPairedQuestion, ...]) -> tuple[McxPairedAnswer, ...]:
    if type(value) is not list or len(value) != len(questions):
        raise ValueError
    return tuple(_parse_one(item, question) for item, question in zip(value, questions, strict=True))


def _parse_one(value: object, question: McxPairedQuestion) -> McxPairedAnswer:
    if type(value) is not dict or frozenset(value) != _ANSWER_FIELDS or value["question_id"] != question.question_id:
        raise ValueError
    return McxPairedAnswer(value["question_id"], value["answer"], value["note"])


def _question(identity: str) -> McxPairedQuestion:
    matches = tuple(item for item in MCX_PAIRED_QUESTIONS if item.question_id == identity)
    if len(matches) != 1:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
    return matches[0]


def _without(value: object, *names: str) -> dict[str, object]:
    return {name: item for name, item in asdict(value).items() if name not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_canonical(_normalize(value))).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _normalize(value: object) -> object:
    if is_dataclass(value): return _normalize(asdict(value))
    if isinstance(value, StrEnum): return value.value
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, Mapping): return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: tuple[object, ...]) -> bool:
    return bool(values) and all(_text(item) for item in values)


def _sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


__all__ = [
    "MCX_PAIRED_ANSWER_PACK_IDENTITY", "MCX_PAIRED_ANSWER_PACK_VERSION",
    "McxPairedAnswer", "McxPairedAnswerPack", "McxPairedImportedVisualEvidence",
    "answer_template", "parse_mcx_paired_answer", "bind_mcx_paired_import",
    "answer_artifact_from_bytes",
]
