"""Strict Answer import for independent MCX and reference observations."""

from __future__ import annotations

from kronos.intraday import visual_contract_v2 as visual_v2
from kronos.intraday.review_answer import _parse_answer
from kronos.intraday.review import ObservationStatus

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
MCX_REFERENCE_OBSERVATION_PLACEHOLDER = "REPLACE_WITH_EXACT_OBSERVED_REFERENCE_IDENTITY"
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
    cross_market_answers: tuple[visual_v2.VisualObservationV2, ...] | None = None

    def __post_init__(self) -> None:
        _validate_observations(self)
        modern = self.schema_version == visual_v2.VERSION
        values = _without(self, "answer_pack_identity")
        if (
            not _sha(self.source_sha256)
            or self.question_set_identity != (visual_v2.MCX_QUESTION_SET if modern else MCX_PAIRED_QUESTION_SET_IDENTITY)
            or self.question_set_version != self.schema_version
            or not _texts((self.review_pack_identity, self.paired_bundle_identity,
                           self.review_cycle_identity, self.canonical_mcx_subject_identity,
                           self.direction, self.native_observed_visible_identity,
                           self.reference_observed_visible_identity))
            or self.direction not in {"LONG", "SHORT"}
            or self.schema_identity != (visual_v2.MCX_ANSWER_SCHEMA if modern else MCX_PAIRED_ANSWER_PACK_IDENTITY)
            or self.schema_version not in {MCX_PAIRED_ANSWER_PACK_VERSION, visual_v2.VERSION}
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
    reference_resolution: VisualIdentityResolution | None
    native_answers: tuple[McxPairedAnswer, ...]
    reference_answers: tuple[McxPairedAnswer, ...]
    escape_hatch_answer: McxPairedAnswer
    imported_at: datetime
    integrity_identity: str
    authority: str = "INDEPENDENT_VISUAL_OBSERVATION_ONLY"
    schema_identity: str = MCX_PAIRED_IMPORTED_EVIDENCE_IDENTITY
    schema_version: str = MCX_PAIRED_CONTRACT_VERSION
    cross_market_answers: tuple[visual_v2.VisualObservationV2, ...] | None = None

    def __post_init__(self) -> None:
        _validate_observations(self)
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
            or (self.schema_version == MCX_PAIRED_CONTRACT_VERSION and type(self.reference_resolution) is not VisualIdentityResolution)
            or (self.schema_version in {"1.1.0", visual_v2.VERSION} and self.reference_resolution is not None)
            or self.native_resolution.canonical_subject_identity != (self.actual_derivative_contract_identity if self.schema_version in {"1.1.0", visual_v2.VERSION} else self.canonical_mcx_subject_identity)
            or self.native_resolution.observed_visible_subject_identity != self.native_observed_visible_identity
            or (self.reference_resolution is not None and self.reference_resolution.observed_visible_subject_identity != self.reference_observed_visible_identity)
            or self.authority != "INDEPENDENT_VISUAL_OBSERVATION_ONLY"
            or self.schema_identity != MCX_PAIRED_IMPORTED_EVIDENCE_IDENTITY
            or self.schema_version not in {MCX_PAIRED_CONTRACT_VERSION, "1.1.0", visual_v2.VERSION}
            or self.visual_evidence_identity != _identity("INTRADAY-MCX-PAIRED-VISUAL-EVIDENCE-", values)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-MCX-PAIRED-VISUAL-EVIDENCE-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


    @property
    def reference_constituent_relationship(self) -> str:
        return "NOT_ESTABLISHED"

    @property
    def reference_role(self) -> str:
        return "SUPPORTING_ONLY"


def parse_mcx_paired_answer(payload: bytes) -> McxPairedAnswerPack:
    if type(payload) is not bytes or not payload or len(payload) > MAX_MCX_PAIRED_ANSWER_BYTES:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
    try:
        document = json.loads(payload.decode("utf-8"))
        modern = type(document) is dict and document.get("schema_version") == visual_v2.VERSION
        if type(document) is not dict or frozenset(document) != (_TOP_LEVEL | {"cross_market_answers"} if modern else _TOP_LEVEL):
            raise ValueError
        if modern:
            native = tuple(_parse_answer(item, visual_v2.VisualObservationV2) for item in document["native_answers"])
            reference = tuple(_parse_answer(item, visual_v2.VisualObservationV2) for item in document["reference_answers"])
            escape = _parse_answer(document["escape_hatch_answer"], visual_v2.VisualObservationV2)
            cross = tuple(_parse_answer(item, visual_v2.VisualObservationV2) for item in document["cross_market_answers"])
        else:
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
        if modern:
            values["cross_market_answers"] = cross
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
    supporting_reference_only: bool = False,
) -> McxPairedImportedVisualEvidence:
    if (
        type(pack) is not McxPairedReviewPack or type(bundle) is not McxPairedChartBundle
        or type(answer) is not McxPairedAnswerPack
        or (answer.question_set_identity, answer.question_set_version) != (pack.question_set_identity, pack.question_set_version)
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
    if answer.schema_version == visual_v2.VERSION:
        if not pack.native_governed_levels and answer.native_answers[-1].answer not in {None, "UNCLEAR", "NOT_OBSERVABLE"}:
            raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_UNVERIFIABLE)
        if not supporting_reference_only or any(item.observation_status is ObservationStatus.INVALID for item in (*answer.native_answers, *answer.reference_answers, *answer.cross_market_answers, answer.escape_hatch_answer)):
            raise ReviewError(ReviewFailure.ANSWER_INVALID)
    if supporting_reference_only and answer.reference_observed_visible_identity == MCX_REFERENCE_OBSERVATION_PLACEHOLDER:
        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
    native = native_resolver.resolve(
        observed_visible_subject_identity=answer.native_observed_visible_identity,
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        governed_observation_boundary=(native_chart.received_at if supporting_reference_only else bundle.analysis_boundary),
    )
    reference = None if supporting_reference_only else reference_resolver.resolve(
        observed_visible_subject_identity=answer.reference_observed_visible_identity,
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        governed_observation_boundary=bundle.analysis_boundary,
    )
    expected_native = (bundle.native_identity_binding.actual_derivative_contract_identity
                       if supporting_reference_only else bundle.canonical_mcx_subject_identity)
    if (native.canonical_subject_identity != expected_native
        or not supporting_reference_only and (
            reference.canonical_subject_identity != bundle.reference_relationship.reference_analytical_subject_identity
            or answer.reference_observed_visible_identity != bundle.reference_relationship.governed_visible_identity)):
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
        "schema_version": visual_v2.VERSION if answer.schema_version == visual_v2.VERSION else ("1.1.0" if supporting_reference_only else MCX_PAIRED_CONTRACT_VERSION),
    }
    if answer.cross_market_answers is not None:
        values["cross_market_answers"] = answer.cross_market_answers
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
    if pack.question_set_version == visual_v2.VERSION:
        def observation(q):
            return {"question_id": q.question_id, "observation_status": "INVALID",
                    "answer": None, "visible_timeframes": [], "visible_basis": None,
                    "status_detail": "REPLACE WITH GOVERNED OBSERVATION", "why_not_covered_elsewhere": None}
        document.update(schema_identity=visual_v2.MCX_ANSWER_SCHEMA, schema_version=visual_v2.VERSION,
                        native_answers=[observation(q) for q in pack.questions[5:10]],
                        reference_answers=[observation(q) for q in pack.questions[:5]],
                        cross_market_answers=[observation(q) for q in pack.questions[10:14]],
                        escape_hatch_answer=observation(pack.questions[14]),
                        reference_observed_visible_identity=MCX_REFERENCE_OBSERVATION_PLACEHOLDER)
    return _canonical(document) + b"\n"


def answer_artifact_from_bytes(payload: bytes) -> McxPairedAnswerPack | McxPairedImportedVisualEvidence:
    try:
        raw = json.loads(payload.decode("utf-8"))
        if type(raw) is not dict:
            raise ValueError
        values = dict(raw)
        modern = values.get("schema_version") == visual_v2.VERSION
        def restore(item):
            return _parse_answer(item, visual_v2.VisualObservationV2) if modern else McxPairedAnswer(**item)
        for name in ("native_answers", "reference_answers"):
            values[name] = tuple(restore(item) for item in values[name])
        values["escape_hatch_answer"] = restore(values["escape_hatch_answer"])
        if modern:
            values["cross_market_answers"] = tuple(restore(item) for item in values["cross_market_answers"])
        if values.get("schema_identity") in {MCX_PAIRED_ANSWER_PACK_IDENTITY, visual_v2.MCX_ANSWER_SCHEMA}:
            value: McxPairedAnswerPack | McxPairedImportedVisualEvidence = McxPairedAnswerPack(**values)
        elif values.get("schema_identity") == MCX_PAIRED_IMPORTED_EVIDENCE_IDENTITY:
            values["analysis_boundary"] = datetime.fromisoformat(values["analysis_boundary"])
            values["imported_at"] = datetime.fromisoformat(values["imported_at"])
            for name in ("native_resolution", "reference_resolution"):
                resolution = values[name]
                if resolution is None:
                    continue
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
    return {name: item for name, item in asdict(value).items() if name not in names and not (name == "cross_market_answers" and item is None)}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_canonical(_normalize(value))).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _normalize(value: object) -> object:
    if is_dataclass(value): return _normalize(asdict(value))
    if isinstance(value, StrEnum): return value.value
    if isinstance(value, datetime): return value.isoformat()
    if isinstance(value, Mapping): return {str(k): _normalize(v) for k, v in value.items() if not (k == "cross_market_answers" and v is None)}
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


def _validate_observations(value):
    modern = value.schema_version == visual_v2.VERSION
    if modern:
        groups = ((value.reference_answers, visual_v2.MCX_QUESTIONS[:5]),
                  (value.native_answers, visual_v2.MCX_QUESTIONS[5:10]),
                  (value.cross_market_answers, visual_v2.MCX_QUESTIONS[10:14]),
                  ((value.escape_hatch_answer,), visual_v2.MCX_QUESTIONS[14:]))
        expected_type = visual_v2.VisualObservationV2
    else:
        if value.cross_market_answers is not None:
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        groups = ((value.native_answers, MCX_PAIRED_QUESTIONS[:10]),
                  (value.reference_answers, MCX_PAIRED_QUESTIONS[10:16]),
                  ((value.escape_hatch_answer,), MCX_PAIRED_QUESTIONS[16:]))
        expected_type = McxPairedAnswer
    for observations, questions in groups:
        if (type(observations) is not tuple or any(type(item) is not expected_type for item in observations)
            or tuple(item.question_id for item in observations) != tuple(q.question_id for q in questions)):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
