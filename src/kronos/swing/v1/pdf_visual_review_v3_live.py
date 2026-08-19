"""Versioned Sponsor-mediated PDF transport for live Visual V3 review cycles.

The transport composes the already-governed per-instrument V3 Question Pack
writer into one immutable all-eligible Review Pack.  It accepts only the V3
Answer identity and binds KRONOS-owned run, assessment, machine-fact, and
provenance fields after the untrusted visual Answer has passed identity checks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from typing import Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer

from kronos.configuration.pdf_visual_review import PdfVisualReviewConfiguration
from kronos.swing.v1.pdf_visual_review import (
    BEGIN_GOVERNED_ANSWER_DATA,
    END_GOVERNED_ANSWER_DATA,
    PdfReviewTransportError,
    _extract_governed_payload,
)
from kronos.swing.v1.pdf_visual_review_v3 import (
    VisualV3ReviewPackRecord,
    write_visual_v3_question_pack,
)
from kronos.swing.v1.visual_evidence_v3 import (
    VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
    VISUAL_EVIDENCE_V3_AUTHORITY,
    VISUAL_EVIDENCE_V3_SCHEMA,
    VISUAL_QUESTION_SET_V3_ID,
    VISUAL_QUESTION_SET_V3_VERSION,
    VisualEvidenceV3Request,
    VisualEvidenceV3Response,
    VisualTimeframe,
    visual_evidence_v3_response_from_dict,
)


VISUAL_V3_LIVE_TRANSPORT_ID = "SWING-V1-PDF-VISUAL-REVIEW-TRANSPORT-V3"
VISUAL_V3_LIVE_TRANSPORT_VERSION = "3.0"
VISUAL_V3_LIVE_REVIEW_SCHEMA = "KRONOS-SWING-V1-VISUAL-V3-LIVE-REVIEW-PACK"
VISUAL_V3_LIVE_IMPORT_SCHEMA = "KRONOS-SWING-V1-VISUAL-V3-ANSWER-IMPORT"
VISUAL_V3_LIVE_SELECTION_SCHEMA = "KRONOS-SWING-V1-VISUAL-V3-CURRENT-SELECTION"
PDF_ANSWER_PROVIDER_IDENTITY = "SPONSOR_MEDIATED_PDF"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_IST = ZoneInfo("Asia/Kolkata")


class VisualV3AnswerImportState(StrEnum):
    ANSWER_PACK_VERIFIED = "ANSWER_PACK_VERIFIED"
    ANSWER_PACK_REJECTED = "ANSWER_PACK_REJECTED"
    ANSWER_PACK_INCOMPLETE = "ANSWER_PACK_INCOMPLETE"
    REVIEW_EVIDENCE_IMPORTED = "REVIEW_EVIDENCE_IMPORTED"


@dataclass(frozen=True, slots=True)
class VisualV3LiveReviewPack:
    review_pack_id: str
    native_run_identity: str
    question_filename: str
    question_path: str
    expected_answer_filename: str
    question_pdf_sha256: str
    created_at: datetime
    observation_boundary: datetime
    candidate_packs: tuple[VisualV3ReviewPackRecord, ...]
    scope: str
    skipped: tuple[tuple[str, str], ...]
    question_set_identity: str = VISUAL_QUESTION_SET_V3_ID
    question_set_version: str = VISUAL_QUESTION_SET_V3_VERSION
    answer_schema: str = VISUAL_EVIDENCE_V3_ANSWER_SCHEMA
    transport_identity: str = VISUAL_V3_LIVE_TRANSPORT_ID
    transport_version: str = VISUAL_V3_LIVE_TRANSPORT_VERSION
    schema: str = VISUAL_V3_LIVE_REVIEW_SCHEMA

    def __post_init__(self) -> None:
        if (
            not self.review_pack_id.startswith("KRONOS-V3-REVIEW-")
            or not self.native_run_identity
            or not self.question_filename.endswith("_QUESTIONS.pdf")
            or Path(self.question_path).name != self.question_filename
            or not self.expected_answer_filename.endswith("_ANSWERS.pdf")
            or _DIGEST.fullmatch(self.question_pdf_sha256) is None
            or not _aware(self.created_at)
            or not _aware(self.observation_boundary)
            or not self.candidate_packs
            or any(
                item.native_run_identity != self.native_run_identity
                or item.review_pack_id != self.review_pack_id
                or item.question_path != self.question_path
                or item.question_pdf_sha256 != self.question_pdf_sha256
                for item in self.candidate_packs
            )
            or tuple(item.canonical_instrument for item in self.candidate_packs)
            != tuple(sorted(item.canonical_instrument for item in self.candidate_packs))
            or self.scope not in {"ALL_ELIGIBLE", "INDIVIDUAL"}
            or (self.scope == "INDIVIDUAL" and (len(self.candidate_packs) != 1 or self.skipped))
            or any(len(item) != 2 or item[1] != "CHART REQUIRED" for item in self.skipped)
            or self.question_set_identity != VISUAL_QUESTION_SET_V3_ID
            or self.question_set_version != VISUAL_QUESTION_SET_V3_VERSION
            or self.answer_schema != VISUAL_EVIDENCE_V3_ANSWER_SCHEMA
            or self.transport_identity != VISUAL_V3_LIVE_TRANSPORT_ID
            or self.transport_version != VISUAL_V3_LIVE_TRANSPORT_VERSION
            or self.schema != VISUAL_V3_LIVE_REVIEW_SCHEMA
        ):
            raise ValueError("VISUAL_V3_LIVE_REVIEW_PACK_INVALID")


@dataclass(frozen=True, slots=True)
class VisualV3AnswerImportRecord:
    review_pack_id: str
    answer_filename: str
    answer_path: str
    answer_pdf_sha256: str
    observed_at: datetime
    state: VisualV3AnswerImportState
    reasons: tuple[str, ...]
    consumed: bool
    evidence_import_identity: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.review_pack_id.startswith("KRONOS-V3-REVIEW-")
            or not self.answer_filename.endswith(".pdf")
            or Path(self.answer_path).name != self.answer_filename
            or _DIGEST.fullmatch(self.answer_pdf_sha256) is None
            or not _aware(self.observed_at)
            or type(self.state) is not VisualV3AnswerImportState
            or not self.reasons
            or self.consumed
            != (self.state is VisualV3AnswerImportState.REVIEW_EVIDENCE_IMPORTED)
            or (
                self.evidence_import_identity is not None
                and _DIGEST.fullmatch(self.evidence_import_identity) is None
            )
        ):
            raise ValueError("VISUAL_V3_ANSWER_IMPORT_INVALID")


@dataclass(frozen=True, slots=True)
class ValidatedVisualV3Candidate:
    canonical_instrument: str
    responses: tuple[VisualEvidenceV3Response, ...]


@dataclass(frozen=True, slots=True)
class ValidatedVisualV3Answer:
    answer_path: Path
    answer_sha256: str
    candidates: tuple[ValidatedVisualV3Candidate, ...]


class VisualV3PdfRecordStore:
    """Immutable V3 Review Pack selection and Answer-import records."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("VISUAL_V3_PDF_STORE_INVALID")
        self.root = root
        self._lock = RLock()

    def retain_pack(self, value: VisualV3LiveReviewPack) -> Path:
        path = self.root / "review-packs" / f"{value.review_pack_id}.json"
        self._retain(path, {"schema": VISUAL_V3_LIVE_REVIEW_SCHEMA, "record": _primitive(value)})
        return path

    def select_current(self, value: VisualV3LiveReviewPack) -> Path:
        self.retain_pack(value)
        path = self.root / "current-review-pack.json"
        payload = {
            "schema": VISUAL_V3_LIVE_SELECTION_SCHEMA,
            "review_pack_id": value.review_pack_id,
        }
        with self._lock:
            _atomic_json(path, payload, replace_existing=True)
        return path

    def load_current(self) -> VisualV3LiveReviewPack | None:
        path = self.root / "current-review-pack.json"
        if not path.exists():
            return None
        selection = _read(path)
        if selection.get("schema") != VISUAL_V3_LIVE_SELECTION_SCHEMA:
            raise ValueError("VISUAL_V3_SELECTION_INVALID")
        pack_path = self.root / "review-packs" / f"{selection.get('review_pack_id')}.json"
        payload = _read(pack_path)
        if payload.get("schema") != VISUAL_V3_LIVE_REVIEW_SCHEMA:
            raise ValueError("VISUAL_V3_REVIEW_PACK_RESTORE_INVALID")
        return _pack_from_dict(payload.get("record"))

    def retain_import(self, value: VisualV3AnswerImportRecord) -> Path:
        path = (
            self.root / "answer-imports" / value.review_pack_id
            / value.answer_pdf_sha256 / f"{value.observed_at.timestamp():.6f}.json"
        )
        self._retain(path, {"schema": VISUAL_V3_LIVE_IMPORT_SCHEMA, "record": _primitive(value)})
        return path

    def load_imports(self, review_pack_id: str) -> tuple[VisualV3AnswerImportRecord, ...]:
        root = self.root / "answer-imports" / _safe(review_pack_id)
        if not root.exists():
            return ()
        values = []
        for path in sorted(root.rglob("*.json")):
            payload = _read(path)
            if payload.get("schema") != VISUAL_V3_LIVE_IMPORT_SCHEMA:
                raise ValueError("VISUAL_V3_ANSWER_IMPORT_RESTORE_INVALID")
            values.append(_import_from_dict(payload.get("record")))
        return tuple(values)

    def _retain(self, path: Path, payload: dict[str, object]) -> None:
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("VISUAL_V3_PDF_RECORD_IMMUTABLE")
                return
            _atomic_json(path, payload)


class VisualV3PdfReviewTransport:
    """Create one V3 all-eligible PDF and validate one matching V3 Answer."""

    def __init__(
        self,
        configuration: PdfVisualReviewConfiguration,
        record_store: VisualV3PdfRecordStore,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if (
            type(configuration) is not PdfVisualReviewConfiguration
            or type(record_store) is not VisualV3PdfRecordStore
            or not callable(clock)
        ):
            raise TypeError("VISUAL_V3_PDF_TRANSPORT_DEPENDENCY_INVALID")
        self.configuration = configuration
        self.record_store = record_store
        self._clock = clock

    def generate(
        self,
        prepared: tuple[tuple[VisualEvidenceV3Request, ...], ...],
        *,
        scope: str,
        skipped: tuple[tuple[str, str], ...],
    ) -> VisualV3LiveReviewPack:
        if (
            not prepared
            or any(len(item) != 4 for item in prepared)
            or len({item[0].requirement.native_run_identity for item in prepared}) != 1
        ):
            raise PdfReviewTransportError("VISUAL_V3_REVIEW_INPUT_INVALID")
        self.configuration.ensure_directories()
        ordered = tuple(sorted(prepared, key=lambda item: item[0].requirement.canonical_instrument))
        now = ordered[0][0].request_timestamp
        if any(
            request.request_timestamp != now
            for requests in ordered for request in requests
        ):
            raise PdfReviewTransportError("VISUAL_V3_REQUEST_TIMESTAMP_MISMATCH")
        stamp = now.astimezone(_IST).strftime("%Y%m%d_%H%M%S")
        base = f"KRONOS_V3_REVIEW_{stamp}_IST"
        question_filename = f"{base}_QUESTIONS.pdf"
        answer_filename = f"{base}_ANSWERS.pdf"
        question_path = self.configuration.question_directory / question_filename
        if question_path.exists():
            raise PdfReviewTransportError("REVIEW_PACK_FILENAME_EXISTS")
        review_pack_id = f"KRONOS-V3-REVIEW-{uuid4().hex.upper()}"
        writer = PdfWriter()
        with tempfile.TemporaryDirectory(prefix="kronos-v3-review-") as directory:
            temporary_root = Path(directory)
            for index, requests in enumerate(ordered):
                temporary = temporary_root / f"candidate-{index}.pdf"
                write_visual_v3_question_pack(
                    requests, temporary,
                    review_pack_id=review_pack_id,
                    created_at=now,
                )
                for page in PdfReader(temporary).pages:
                    writer.add_page(page)
            contract = temporary_root / "answer-contract.pdf"
            _write_answer_contract(contract, review_pack_id, ordered, answer_filename)
            for page in PdfReader(contract).pages:
                writer.add_page(page)
            question_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_output = question_path.with_suffix(".tmp")
            with temporary_output.open("wb") as stream:
                writer.write(stream)
            os.chmod(temporary_output, 0o600)
            os.replace(temporary_output, question_path)
        digest = sha256(question_path.read_bytes()).hexdigest()
        candidate_packs = tuple(
            VisualV3ReviewPackRecord(
                review_pack_id=review_pack_id,
                native_run_identity=requests[0].requirement.native_run_identity,
                canonical_instrument=requests[0].requirement.canonical_instrument,
                native_assessment_sha256=requests[0].requirement.thesis.native_assessment_sha256,
                created_at=now,
                question_path=str(question_path),
                question_pdf_sha256=digest,
                chart_revisions=tuple(
                    (item.timeframe.value, item.chart_revision_sha256) for item in requests
                ),
                machine_fact_bindings=tuple(
                    (item.timeframe.value, item.machine_fact.integrity_sha256) for item in requests
                ),
            )
            for requests in ordered
        )
        boundary = max(item.observation_boundary for requests in ordered for item in requests)
        record = VisualV3LiveReviewPack(
            review_pack_id,
            ordered[0][0].requirement.native_run_identity,
            question_filename,
            str(question_path),
            answer_filename,
            digest,
            now,
            boundary,
            candidate_packs,
            scope,
            skipped,
        )
        self.record_store.select_current(record)
        return record

    def find_and_validate_answer(
        self,
        record: VisualV3LiveReviewPack,
        requests: tuple[tuple[VisualEvidenceV3Request, ...], ...],
    ) -> ValidatedVisualV3Answer:
        self.configuration.ensure_directories()
        expected = self.configuration.answer_directory / record.expected_answer_filename
        matches: list[tuple[Path, dict[str, object]]] = []
        for path in sorted(self.configuration.answer_directory.glob("*_ANSWERS.pdf")):
            try:
                payload = _extract_governed_payload(path)
            except PdfReviewTransportError:
                if path == expected:
                    raise
                continue
            manifest = payload.get("manifest")
            if type(manifest) is dict and manifest.get("review_pack_id") == record.review_pack_id:
                matches.append((path, payload))
        if not matches:
            raise PdfReviewTransportError("ANSWER_PACK_NOT_FOUND")
        if len(matches) != 1:
            raise PdfReviewTransportError("AMBIGUOUS_ANSWER_PACK")
        path, payload = matches[0]
        if path.name != record.expected_answer_filename:
            raise PdfReviewTransportError("ANSWER_FILENAME_MISMATCH")
        digest = sha256(path.read_bytes()).hexdigest()
        imported = tuple(
            item for item in self.record_store.load_imports(record.review_pack_id)
            if item.answer_pdf_sha256 == digest and item.consumed
        )
        if imported:
            return ValidatedVisualV3Answer(path, digest, ())
        validated = _validate_answer(record, requests, payload)
        return ValidatedVisualV3Answer(path, digest, validated)

    def record_rejection(
        self, record: VisualV3LiveReviewPack, reason: str
    ) -> VisualV3AnswerImportRecord:
        path = self.configuration.answer_directory / record.expected_answer_filename
        digest = sha256(path.read_bytes()).hexdigest() if path.exists() else "0" * 64
        value = VisualV3AnswerImportRecord(
            record.review_pack_id,
            path.name,
            str(path),
            digest,
            self._now(),
            (
                VisualV3AnswerImportState.ANSWER_PACK_INCOMPLETE
                if reason == "ANSWER_PACK_NOT_FOUND"
                else VisualV3AnswerImportState.ANSWER_PACK_REJECTED
            ),
            (reason,),
            False,
        )
        self.record_store.retain_import(value)
        return value

    def record_import(
        self,
        record: VisualV3LiveReviewPack,
        answer: ValidatedVisualV3Answer,
        evidence_hashes: tuple[str, ...],
    ) -> VisualV3AnswerImportRecord:
        identity = sha256(_canonical({
            "review_pack_id": record.review_pack_id,
            "answer_sha256": answer.answer_sha256,
            "evidence_hashes": evidence_hashes,
        })).hexdigest()
        value = VisualV3AnswerImportRecord(
            record.review_pack_id,
            answer.answer_path.name,
            str(answer.answer_path),
            answer.answer_sha256,
            self._now(),
            VisualV3AnswerImportState.REVIEW_EVIDENCE_IMPORTED,
            (
                VisualV3AnswerImportState.ANSWER_PACK_VERIFIED.value,
                VisualV3AnswerImportState.REVIEW_EVIDENCE_IMPORTED.value,
            ),
            True,
            identity,
        )
        self.record_store.retain_import(value)
        return value

    def _now(self) -> datetime:
        value = self._clock()
        if not _aware(value):
            raise PdfReviewTransportError("VISUAL_V3_PDF_CLOCK_INVALID")
        return value


def _validate_answer(
    record: VisualV3LiveReviewPack,
    requests: tuple[tuple[VisualEvidenceV3Request, ...], ...],
    payload: dict[str, object],
) -> tuple[ValidatedVisualV3Candidate, ...]:
    if type(payload) is not dict or set(payload) != {"schema", "manifest", "candidates"}:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    if payload.get("schema") != VISUAL_EVIDENCE_V3_ANSWER_SCHEMA:
        raise PdfReviewTransportError("ANSWER_VERSION_MISMATCH")
    manifest = payload.get("manifest")
    if type(manifest) is not dict:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    for key, expected in (
        ("review_pack_id", record.review_pack_id),
        ("native_run_identity", record.native_run_identity),
        ("question_set_identity", VISUAL_QUESTION_SET_V3_ID),
        ("question_set_version", VISUAL_QUESTION_SET_V3_VERSION),
        ("answer_schema", VISUAL_EVIDENCE_V3_ANSWER_SCHEMA),
    ):
        if manifest.get(key) != expected:
            raise PdfReviewTransportError("ANSWER_VERSION_MISMATCH")
    expected_population = [
        {
            "canonical_instrument": item.canonical_instrument,
            "chart_revision_sha256": item.chart_revisions[0][1],
        }
        for item in record.candidate_packs
    ]
    if manifest.get("candidate_population") != expected_population:
        raise PdfReviewTransportError("CANDIDATE_POPULATION_MISMATCH")
    raw_candidates = payload.get("candidates")
    if type(raw_candidates) is not list or len(raw_candidates) != len(requests):
        raise PdfReviewTransportError("ANSWER_INCOMPLETE")
    by_instrument = {item[0].requirement.canonical_instrument: item for item in requests}
    results = []
    for pack, raw in zip(record.candidate_packs, raw_candidates, strict=True):
        if type(raw) is not dict:
            raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
        instrument = pack.canonical_instrument
        if (
            raw.get("canonical_instrument") != instrument
            or raw.get("observed_chart_instrument") != instrument
            or raw.get("chart_revision_sha256") != pack.chart_revisions[0][1]
        ):
            raise PdfReviewTransportError("CHART_IDENTITY_MISMATCH")
        raw_responses = raw.get("responses")
        if type(raw_responses) is not list or len(raw_responses) != 4:
            raise PdfReviewTransportError("ANSWER_INCOMPLETE")
        candidate_requests = by_instrument.get(instrument)
        if candidate_requests is None:
            raise PdfReviewTransportError("CANDIDATE_POPULATION_MISMATCH")
        responses = []
        for request, raw_response in zip(candidate_requests, raw_responses, strict=True):
            if type(raw_response) is not dict:
                raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
            if (
                raw_response.get("timeframe") != request.timeframe.value
                or raw_response.get("chart_identity") != instrument
                or raw_response.get("chart_revision_sha256") != request.chart_revision_sha256
                or raw_response.get("question_set_identity") != VISUAL_QUESTION_SET_V3_ID
                or raw_response.get("question_set_version") != VISUAL_QUESTION_SET_V3_VERSION
            ):
                raise PdfReviewTransportError("ANSWER_VERSION_MISMATCH")
            observations = raw_response.get("observations")
            if type(observations) is not list or any(
                type(item) is not dict
                or item.get("source_chart_identity") != instrument
                or item.get("source_chart_revision") != request.chart_revision_sha256
                for item in observations
            ):
                raise PdfReviewTransportError("CHART_IDENTITY_MISMATCH")
            bound = dict(raw_response)
            bound.update({
                "provider_identity": PDF_ANSWER_PROVIDER_IDENTITY,
                "native_run_identity": record.native_run_identity,
                "native_assessment_sha256": request.requirement.thesis.native_assessment_sha256,
                "native_canonical_instrument": instrument,
                "observation_boundary": request.observation_boundary.isoformat(),
                "analysis_boundary": request.analysis_boundary.isoformat(),
                "machine_fact_integrity_sha256": request.machine_fact.integrity_sha256,
                "source_provenance": (record.transport_identity, record.review_pack_id),
                "schema": VISUAL_EVIDENCE_V3_SCHEMA,
                "authority": VISUAL_EVIDENCE_V3_AUTHORITY,
            })
            try:
                response = visual_evidence_v3_response_from_dict(bound)
                response.validate_binding(request)
            except ValueError as error:
                raise PdfReviewTransportError("ANSWER_FORMAT_INVALID") from error
            responses.append(response)
        results.append(ValidatedVisualV3Candidate(instrument, tuple(responses)))
    return tuple(results)


def _write_answer_contract(
    path: Path,
    review_pack_id: str,
    prepared: tuple[tuple[VisualEvidenceV3Request, ...], ...],
    expected_answer_filename: str,
) -> None:
    styles = getSampleStyleSheet()
    first = prepared[0][0]
    population = [
        {
            "canonical_instrument": item[0].requirement.canonical_instrument,
            "chart_revision_sha256": item[0].chart_revision_sha256,
        }
        for item in prepared
    ]
    example = {
        "schema": VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
        "manifest": {
            "review_pack_id": review_pack_id,
            "native_run_identity": first.requirement.native_run_identity,
            "question_set_identity": VISUAL_QUESTION_SET_V3_ID,
            "question_set_version": VISUAL_QUESTION_SET_V3_VERSION,
            "answer_schema": VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
            "candidate_population": population,
        },
        "candidates": [{
            "canonical_instrument": population[0]["canonical_instrument"],
            "observed_chart_instrument": "<READ EXACTLY FROM CHART>",
            "chart_revision_sha256": population[0]["chart_revision_sha256"],
            "responses": [{
                "model_identity": "<CHART ANALYST IDENTITY>",
                "request_timestamp": "<ISO-8601>",
                "timeframe": "1W | 1D | 4H | 1H",
                "chart_identity": population[0]["canonical_instrument"],
                "chart_revision_sha256": population[0]["chart_revision_sha256"],
                "observations": "Q1 THROUGH Q10 EXACTLY ONCE AND IN ORDER",
                "question_set_identity": VISUAL_QUESTION_SET_V3_ID,
                "question_set_version": VISUAL_QUESTION_SET_V3_VERSION,
            }],
        }],
    }
    document = SimpleDocTemplate(BytesIO(), pagesize=A4)
    buffer = document.filename
    story = [
        Paragraph("KRONOS SWING — VISUAL V3 ANSWER CONTRACT", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "Return independent visual observations only. Do not return or infer "
            "KRONOS machine CP, BC, TC, reference H/L, or any machine-fact hash.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
        Paragraph(f"Expected Answer: {expected_answer_filename}", styles["BodyText"]),
        Preformatted(
            BEGIN_GOVERNED_ANSWER_DATA + "\n"
            + json.dumps(example, indent=2)
            + "\n" + END_GOVERNED_ANSWER_DATA,
            styles["Code"],
        ),
    ]
    document.build(story)
    path.write_bytes(buffer.getvalue())


def _pack_from_dict(value: object) -> VisualV3LiveReviewPack:
    if type(value) is not dict:
        raise ValueError("VISUAL_V3_REVIEW_PACK_RESTORE_INVALID")
    try:
        candidates = tuple(_candidate_pack_from_dict(item) for item in value["candidate_packs"])
        return VisualV3LiveReviewPack(
            value["review_pack_id"],
            value["native_run_identity"],
            value["question_filename"],
            value["question_path"],
            value["expected_answer_filename"],
            value["question_pdf_sha256"],
            datetime.fromisoformat(value["created_at"]),
            datetime.fromisoformat(value["observation_boundary"]),
            candidates,
            value["scope"],
            tuple(tuple(item) for item in value["skipped"]),
            value["question_set_identity"],
            value["question_set_version"],
            value["answer_schema"],
            value["transport_identity"],
            value["transport_version"],
            value["schema"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("VISUAL_V3_REVIEW_PACK_RESTORE_INVALID") from error


def _candidate_pack_from_dict(value: object) -> VisualV3ReviewPackRecord:
    if type(value) is not dict:
        raise ValueError("VISUAL_V3_REVIEW_PACK_RESTORE_INVALID")
    return VisualV3ReviewPackRecord(
        review_pack_id=value["review_pack_id"],
        native_run_identity=value["native_run_identity"],
        canonical_instrument=value["canonical_instrument"],
        native_assessment_sha256=value["native_assessment_sha256"],
        created_at=datetime.fromisoformat(value["created_at"]),
        question_path=value["question_path"],
        question_pdf_sha256=value["question_pdf_sha256"],
        chart_revisions=tuple(tuple(item) for item in value["chart_revisions"]),
        machine_fact_bindings=tuple(tuple(item) for item in value["machine_fact_bindings"]),
        question_set_identity=value["question_set_identity"],
        question_set_version=value["question_set_version"],
        schema=value["schema"],
        analyst_authority=value["analyst_authority"],
    )


def _import_from_dict(value: object) -> VisualV3AnswerImportRecord:
    if type(value) is not dict:
        raise ValueError("VISUAL_V3_ANSWER_IMPORT_RESTORE_INVALID")
    try:
        return VisualV3AnswerImportRecord(
            value["review_pack_id"], value["answer_filename"], value["answer_path"],
            value["answer_pdf_sha256"], datetime.fromisoformat(value["observed_at"]),
            VisualV3AnswerImportState(value["state"]), tuple(value["reasons"]),
            value["consumed"], value["evidence_import_identity"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("VISUAL_V3_ANSWER_IMPORT_RESTORE_INVALID") from error


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


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("VISUAL_V3_PDF_RECORD_INVALID") from error
    if type(value) is not dict:
        raise ValueError("VISUAL_V3_PDF_RECORD_INVALID")
    return value


def _atomic_json(
    path: Path, payload: dict[str, object], *, replace_existing: bool = False
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(_canonical(payload))
        os.chmod(temporary, 0o600)
        if path.exists() and not replace_existing:
            if _read(path) != payload:
                raise ValueError("VISUAL_V3_PDF_RECORD_IMMUTABLE")
            temporary.unlink()
            return
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _safe(value: str) -> str:
    if not value or re.fullmatch(r"[A-Za-z0-9_.&!:-]+", value) is None:
        raise ValueError("VISUAL_V3_PDF_IDENTITY_INVALID")
    return value


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "ValidatedVisualV3Answer",
    "ValidatedVisualV3Candidate",
    "VisualV3AnswerImportRecord",
    "VisualV3AnswerImportState",
    "VisualV3LiveReviewPack",
    "VisualV3PdfRecordStore",
    "VisualV3PdfReviewTransport",
]
