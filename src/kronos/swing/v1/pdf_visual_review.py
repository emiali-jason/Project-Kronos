"""Sponsor-mediated PDF transport for frozen Visual Evidence V2 Review."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from threading import RLock
from typing import Callable
from uuid import uuid4
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from kronos.configuration.pdf_visual_review import PdfVisualReviewConfiguration
from kronos.swing.v1.evidence_store import NativeTradingViewEvidencePackage
from kronos.swing.v1.native_review import NativeReviewRequirement
from kronos.swing.v1.visual_evidence_v2 import (
    FROZEN_VISUAL_QUESTION_SET_V2,
    VISUAL_EVIDENCE_V2_AUTHORITY,
    VISUAL_EVIDENCE_V2_SCHEMA,
    VISUAL_QUESTION_SEMANTICS_V2,
    VISUAL_QUESTION_SET_V2_ID,
    VISUAL_QUESTION_SET_V2_VERSION,
    VisualEvidenceV2Response,
    VisualLevelAvailability,
    VisualObservationStatus,
    VisualTimeframe,
    visual_evidence_v2_response_from_dict,
    visual_question_routing,
)


PDF_VISUAL_REVIEW_TRANSPORT_ID = "SWING-V1-PDF-VISUAL-REVIEW-TRANSPORT-V0"
PDF_VISUAL_REVIEW_TRANSPORT_VERSION = "0"
REVIEW_PACK_RECORD_SCHEMA = "KRONOS-SWING-V1-PDF-REVIEW-PACK-V0"
ANSWER_IMPORT_RECORD_SCHEMA = "KRONOS-SWING-V1-PDF-ANSWER-IMPORT-V0"
ANSWER_ARTIFACT_RECORD_SCHEMA = "KRONOS-SWING-V1-PDF-ANSWER-ARTIFACT-V0"
CURRENT_REVIEW_PACK_SELECTION_SCHEMA = (
    "KRONOS-SWING-V1-CURRENT-PDF-REVIEW-PACK-SELECTION-V0"
)
GOVERNED_ANSWER_SCHEMA = "KRONOS-SWING-V1-GOVERNED-PDF-ANSWER-V0"
PDF_ANSWER_PROVIDER_IDENTITY = "SPONSOR_MEDIATED_PDF"
BEGIN_GOVERNED_ANSWER_DATA = "BEGIN KRONOS GOVERNED ANSWER DATA"
END_GOVERNED_ANSWER_DATA = "END KRONOS GOVERNED ANSWER DATA"
_IST = ZoneInfo("Asia/Kolkata")
_MAX_PDF_BYTES = 128 * 1024 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
CANDIDATE_CHART_MAX_WIDTH = 250 * mm
CANDIDATE_CHART_MAX_HEIGHT = 141 * mm
VALID_OBSERVATION_EXAMPLE = {
    "question_id": "VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS",
    "timeframe": "1W",
    "observation_status": "OBSERVED",
    "observation": "NONE",
    "level_availability": "NOT_APPLICABLE",
    "price": None,
    "zone_low": None,
    "zone_high": None,
    "visible_basis": "NO ADDITIONAL MATERIAL VISIBLE FACT",
    "source_chart_identity": "EXAMPLE",
    "source_chart_revision": "0" * 64,
    "confidence_in_extraction": "HIGH",
    "ambiguity_reason": "",
    "why_not_covered_elsewhere": None,
}


class ReviewPackState(StrEnum):
    REVIEW_PACK_GENERATED = "REVIEW_PACK_GENERATED"
    WAITING_FOR_CHART_ANALYST = "WAITING_FOR_CHART_ANALYST"


class AnswerImportState(StrEnum):
    ANSWER_PACK_FOUND = "ANSWER_PACK_FOUND"
    ANSWER_PACK_VERIFIED = "ANSWER_PACK_VERIFIED"
    ANSWER_PACK_REJECTED = "ANSWER_PACK_REJECTED"
    ANSWER_PACK_INCOMPLETE = "ANSWER_PACK_INCOMPLETE"
    REVIEW_EVIDENCE_IMPORTED = "REVIEW_EVIDENCE_IMPORTED"


@dataclass(frozen=True, slots=True)
class ReviewPackCandidate:
    canonical_instrument: str
    native_direction: str
    native_opportunity_identity: str
    native_assessment_sha256: str
    chart_identity: str
    chart_revision_sha256: str
    expected_timeframes: tuple[str, ...]
    reference_subject_identity: str | None = None
    reference_market: str | None = None
    reference_symbol: str | None = None
    reference_expected_timeframes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.canonical_instrument
            or self.native_direction not in {"LONG", "SHORT"}
            or not self.native_opportunity_identity
            or _DIGEST.fullmatch(self.native_assessment_sha256) is None
            or not self.chart_identity
            or _DIGEST.fullmatch(self.chart_revision_sha256) is None
            or self.expected_timeframes
            not in {("1W", "1D", "4H", "1H"), ("1H",)}
            or (
                self.reference_subject_identity is None
                and (
                    self.reference_market is not None
                    or self.reference_symbol is not None
                    or self.reference_expected_timeframes
                )
            )
            or (
                self.reference_subject_identity is not None
                and (
                    not self.reference_market
                    or not self.reference_symbol
                    or self.reference_expected_timeframes != ("1D", "4H", "1H")
                    or self.expected_timeframes != ("1H",)
                )
            )
        ):
            raise ValueError("PDF_REVIEW_PACK_CANDIDATE_INVALID")


@dataclass(frozen=True, slots=True)
class ReviewPackRecord:
    review_pack_id: str
    native_run_identity: str
    question_filename: str
    question_path: str
    expected_answer_filename: str
    question_pdf_sha256: str
    created_at: datetime
    observation_boundary: datetime
    candidates: tuple[ReviewPackCandidate, ...]
    state: ReviewPackState
    state_history: tuple[str, ...]
    question_set_identity: str = VISUAL_QUESTION_SET_V2_ID
    question_set_version: str = VISUAL_QUESTION_SET_V2_VERSION
    transport_policy_identity: str = PDF_VISUAL_REVIEW_TRANSPORT_ID
    transport_policy_version: str = PDF_VISUAL_REVIEW_TRANSPORT_VERSION

    def __post_init__(self) -> None:
        if (
            not self.review_pack_id.startswith("KRONOS-REVIEW-")
            or not self.native_run_identity
            or not self.question_filename.endswith("_QUESTIONS.pdf")
            or Path(self.question_path).name != self.question_filename
            or not self.expected_answer_filename.endswith("_ANSWERS.pdf")
            or _DIGEST.fullmatch(self.question_pdf_sha256) is None
            or not _aware(self.created_at)
            or not _aware(self.observation_boundary)
            or not self.candidates
            or tuple(item.canonical_instrument for item in self.candidates)
            != tuple(sorted(item.canonical_instrument for item in self.candidates))
            or self.state is not ReviewPackState.WAITING_FOR_CHART_ANALYST
            or self.state_history != (
                ReviewPackState.REVIEW_PACK_GENERATED.value,
                ReviewPackState.WAITING_FOR_CHART_ANALYST.value,
            )
            or self.question_set_identity != VISUAL_QUESTION_SET_V2_ID
            or self.question_set_version != VISUAL_QUESTION_SET_V2_VERSION
            or self.transport_policy_identity != PDF_VISUAL_REVIEW_TRANSPORT_ID
            or self.transport_policy_version != PDF_VISUAL_REVIEW_TRANSPORT_VERSION
        ):
            raise ValueError("PDF_REVIEW_PACK_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class AnswerImportRecord:
    review_pack_id: str
    answer_filename: str
    answer_path: str
    answer_pdf_sha256: str
    discovered_at: datetime
    state: AnswerImportState
    validation_reasons: tuple[str, ...]
    consumed: bool
    evidence_import_identity: str | None

    def __post_init__(self) -> None:
        if (
            not self.review_pack_id.startswith("KRONOS-REVIEW-")
            or not self.answer_filename.endswith(".pdf")
            or Path(self.answer_path).name != self.answer_filename
            or _DIGEST.fullmatch(self.answer_pdf_sha256) is None
            or not _aware(self.discovered_at)
            or type(self.state) is not AnswerImportState
            or type(self.validation_reasons) is not tuple
            or not self.validation_reasons
            or type(self.consumed) is not bool
            or (self.consumed != (self.state is AnswerImportState.REVIEW_EVIDENCE_IMPORTED))
            or (self.evidence_import_identity is not None and _DIGEST.fullmatch(self.evidence_import_identity) is None)
        ):
            raise ValueError("PDF_ANSWER_IMPORT_RECORD_INVALID")

    @property
    def attempt_identity(self) -> str:
        return sha256(_canonical(_primitive(self))).hexdigest()


@dataclass(frozen=True, slots=True)
class AnswerArtifactRecord:
    review_pack_id: str
    answer_filename: str
    answer_path: str
    answer_pdf_sha256: str
    first_discovered_at: datetime

    def __post_init__(self) -> None:
        if (
            not self.review_pack_id.startswith("KRONOS-REVIEW-")
            or not self.answer_filename.endswith(".pdf")
            or Path(self.answer_path).name != self.answer_filename
            or _DIGEST.fullmatch(self.answer_pdf_sha256) is None
            or not _aware(self.first_discovered_at)
        ):
            raise ValueError("PDF_ANSWER_ARTIFACT_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class ValidatedAnswerCandidate:
    canonical_instrument: str
    observed_chart_instrument: str
    chart_revision_sha256: str
    responses: tuple[VisualEvidenceV2Response, ...]
    reference_responses: tuple[VisualEvidenceV2Response, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidatedAnswerPack:
    answer_path: Path
    answer_sha256: str
    candidates: tuple[ValidatedAnswerCandidate, ...]


@dataclass(frozen=True, slots=True)
class CurrentReviewPackSelection:
    review_pack_id: str
    scope: str
    skipped: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if (
            not self.review_pack_id.startswith("KRONOS-REVIEW-")
            or self.scope not in {"ALL_ELIGIBLE", "INDIVIDUAL"}
            or type(self.skipped) is not tuple
            or any(
                not instrument or reason != "CHART REQUIRED"
                for instrument, reason in self.skipped
            )
            or tuple(item[0] for item in self.skipped)
            != tuple(sorted(item[0] for item in self.skipped))
            or (self.scope == "INDIVIDUAL" and self.skipped)
        ):
            raise ValueError("CURRENT_REVIEW_PACK_SELECTION_INVALID")


class PdfReviewTransportError(ValueError):
    """One sanitized fail-closed PDF transport failure."""


class PdfReviewRecordStore:
    """Immutable Review Packs, Answer artifacts, and import attempts."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("PDF_REVIEW_RECORD_STORE_INVALID")
        self.root = root
        self._lock = RLock()

    def retain_review_pack(self, record: ReviewPackRecord) -> Path:
        path = self.root / "review-packs" / f"{record.review_pack_id}.json"
        self._retain(path, {"schema": REVIEW_PACK_RECORD_SCHEMA, "record": _primitive(record)})
        return path

    def retain_answer_import(self, record: AnswerImportRecord) -> Path:
        self.retain_answer_artifact(AnswerArtifactRecord(
            record.review_pack_id,
            record.answer_filename,
            record.answer_path,
            record.answer_pdf_sha256,
            record.discovered_at,
        ))
        path = (
            self.root / "answer-imports" / record.review_pack_id
            / record.answer_pdf_sha256 / f"{record.attempt_identity}.json"
        )
        self._retain(path, {"schema": ANSWER_IMPORT_RECORD_SCHEMA, "record": _primitive(record)})
        return path

    def retain_answer_artifact(self, record: AnswerArtifactRecord) -> Path:
        path = (
            self.root / "answer-artifacts" / record.review_pack_id
            / f"{record.answer_pdf_sha256}.json"
        )
        with self._lock:
            if path.exists():
                payload = _read_json(path)
                existing = _answer_artifact_from_dict(payload.get("record"))
                if (
                    payload.get("schema") != ANSWER_ARTIFACT_RECORD_SCHEMA
                    or existing.review_pack_id != record.review_pack_id
                    or existing.answer_filename != record.answer_filename
                    or existing.answer_path != record.answer_path
                    or existing.answer_pdf_sha256 != record.answer_pdf_sha256
                ):
                    raise PdfReviewTransportError("PDF_REVIEW_RECORD_IMMUTABLE")
                return path
            _atomic_json(path, {
                "schema": ANSWER_ARTIFACT_RECORD_SCHEMA,
                "record": _primitive(record),
            })
        return path

    def load_answer_artifacts(
        self, review_pack_id: str,
    ) -> tuple[AnswerArtifactRecord, ...]:
        directory = self.root / "answer-artifacts" / _safe(review_pack_id)
        if not directory.exists():
            return ()
        values = []
        for path in sorted(directory.glob("*.json")):
            payload = _read_json(path)
            if payload.get("schema") != ANSWER_ARTIFACT_RECORD_SCHEMA:
                raise PdfReviewTransportError("ANSWER_ARTIFACT_RECORD_INVALID")
            values.append(_answer_artifact_from_dict(payload.get("record")))
        return tuple(values)

    def load_review_packs(self) -> tuple[ReviewPackRecord, ...]:
        directory = self.root / "review-packs"
        if not directory.exists():
            return ()
        return tuple(
            _review_pack_from_dict(_read_json(path).get("record"))
            for path in sorted(directory.glob("*.json"))
            if _read_json(path).get("schema") == REVIEW_PACK_RECORD_SCHEMA
        )

    def load_answer_imports(self, review_pack_id: str) -> tuple[AnswerImportRecord, ...]:
        directory = self.root / "answer-imports" / _safe(review_pack_id)
        if not directory.exists():
            return ()
        values = []
        for path in sorted(directory.rglob("*.json")):
            payload = _read_json(path)
            if payload.get("schema") != ANSWER_IMPORT_RECORD_SCHEMA:
                raise PdfReviewTransportError("ANSWER_IMPORT_RECORD_INVALID")
            values.append(_answer_import_from_dict(payload.get("record")))
        return tuple(sorted(values, key=lambda item: item.discovered_at))

    def select_current(
        self,
        record: ReviewPackRecord,
        *,
        scope: str,
        skipped: tuple[tuple[str, str], ...] = (),
    ) -> CurrentReviewPackSelection:
        if type(record) is not ReviewPackRecord:
            raise TypeError("PDF_REVIEW_PACK_SELECTION_INVALID")
        selection = CurrentReviewPackSelection(record.review_pack_id, scope, skipped)
        retained = tuple(
            item for item in self.load_review_packs()
            if item.review_pack_id == record.review_pack_id
        )
        if retained != (record,):
            raise PdfReviewTransportError("REVIEW_PACK_RECORD_UNAVAILABLE")
        path = self.root / "current-review-pack.json"
        with self._lock:
            _atomic_json(path, {
                "schema": CURRENT_REVIEW_PACK_SELECTION_SCHEMA,
                "selection": _primitive(selection),
            })
        return selection

    def load_current(
        self,
    ) -> tuple[ReviewPackRecord, CurrentReviewPackSelection] | None:
        path = self.root / "current-review-pack.json"
        if not path.exists():
            return None
        payload = _read_json(path)
        if payload.get("schema") != CURRENT_REVIEW_PACK_SELECTION_SCHEMA:
            raise PdfReviewTransportError("CURRENT_REVIEW_PACK_SELECTION_INVALID")
        value = payload.get("selection")
        try:
            if type(value) is not dict:
                raise ValueError
            selection = CurrentReviewPackSelection(
                value["review_pack_id"],
                value["scope"],
                tuple(tuple(item) for item in value["skipped"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise PdfReviewTransportError(
                "CURRENT_REVIEW_PACK_SELECTION_INVALID"
            ) from error
        matches = tuple(
            item for item in self.load_review_packs()
            if item.review_pack_id == selection.review_pack_id
        )
        if len(matches) != 1:
            raise PdfReviewTransportError("REVIEW_PACK_RECORD_UNAVAILABLE")
        return matches[0], selection

    def latest_for_run(self, run_identity: str) -> ReviewPackRecord | None:
        values = tuple(
            item for item in self.load_review_packs()
            if item.native_run_identity == run_identity
        )
        return max(values, key=lambda item: item.created_at, default=None)

    def _retain(self, path: Path, payload: dict[str, object]) -> None:
        with self._lock:
            if path.exists():
                if _read_json(path) != payload:
                    raise PdfReviewTransportError("PDF_REVIEW_RECORD_IMMUTABLE")
                return
            _atomic_json(path, payload)


class PdfVisualReviewTransport:
    """Generate Question PDFs and validate governed Answer PDFs without API use."""

    def __init__(
        self,
        configuration: PdfVisualReviewConfiguration,
        record_store: PdfReviewRecordStore,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        if (
            type(configuration) is not PdfVisualReviewConfiguration
            or type(record_store) is not PdfReviewRecordStore
            or not callable(clock)
        ):
            raise TypeError("PDF_VISUAL_REVIEW_TRANSPORT_DEPENDENCY_INVALID")
        self.configuration = configuration
        self.record_store = record_store
        self._clock = clock

    def generate(
        self,
        requirements: tuple[NativeReviewRequirement, ...],
        packages: tuple[NativeTradingViewEvidencePackage, ...],
        chart_bytes: Callable[[str], bytes],
    ) -> ReviewPackRecord:
        if not requirements:
            raise PdfReviewTransportError("NATIVE_REVIEW_PROBABLES_UNAVAILABLE")
        self.configuration.ensure_directories()
        ordered = tuple(sorted(requirements, key=lambda item: item.canonical_instrument))
        package_by_instrument = {
            item.binding.canonical_instrument: item
            for item in packages
            if item.binding.subject_kind == "NATIVE"
        }
        candidates = []
        candidate_material = []
        for requirement in ordered:
            package = package_by_instrument.get(requirement.canonical_instrument)
            if (
                package is None
                or package.missing_required_timeframes
                or len(package.active_revisions) != 1
            ):
                raise PdfReviewTransportError(
                    f"REQUIRED_CHART_MISSING:{requirement.canonical_instrument}"
                )
            revision = package.active_revisions[0]
            image = chart_bytes(revision.sha256)
            if sha256(image).hexdigest() != revision.sha256:
                raise PdfReviewTransportError("CHART_REVISION_INTEGRITY_INVALID")
            candidate = ReviewPackCandidate(
                requirement.canonical_instrument,
                requirement.thesis.direction.value,
                requirement.thesis.opportunity_identity.value,
                requirement.thesis.native_assessment_sha256,
                package.binding.chart_subject_identity,
                revision.sha256,
                (
                    ("1H",)
                    if requirement.mcx_reference is not None
                    else tuple(
                        "1D" if item.value == "DAILY" else item.value
                        for item in package.binding.required_timeframes
                    )
                ),
                (
                    None
                    if requirement.mcx_reference is None
                    else requirement.mcx_reference.reference_subject_identity
                ),
                (
                    None
                    if requirement.mcx_reference is None
                    else requirement.mcx_reference.reference_market.value
                ),
                (
                    None
                    if requirement.mcx_reference is None
                    else requirement.mcx_reference.reference_symbol
                ),
                (
                    ()
                    if requirement.mcx_reference is None
                    else ("1D", "4H", "1H")
                ),
            )
            candidates.append(candidate)
            candidate_material.append((requirement, package, revision, image))
        now = self._now()
        timestamp = now.astimezone(_IST).strftime("%Y%m%d_%H%M%S")
        base = f"KRONOS_REVIEW_{timestamp}_IST"
        question_filename = f"{base}_QUESTIONS.pdf"
        answer_filename = f"{base}_ANSWERS.pdf"
        question_path = self.configuration.question_directory / question_filename
        if question_path.exists():
            raise PdfReviewTransportError("REVIEW_PACK_FILENAME_EXISTS")
        review_pack_id = f"KRONOS-REVIEW-{uuid4().hex.upper()}"
        boundary = max(
            fact.observation_boundary
            for requirement in ordered
            for fact in requirement.thesis.timeframe_facts
        )
        manifest = _review_manifest(
            review_pack_id, ordered[0].native_run_identity, now, boundary,
            tuple(candidates), answer_filename,
        )
        _render_question_pdf(
            question_path,
            manifest,
            tuple(candidate_material),
        )
        digest = sha256(question_path.read_bytes()).hexdigest()
        record = ReviewPackRecord(
            review_pack_id,
            ordered[0].native_run_identity,
            question_filename,
            str(question_path),
            answer_filename,
            digest,
            now,
            boundary,
            tuple(candidates),
            ReviewPackState.WAITING_FOR_CHART_ANALYST,
            (
                ReviewPackState.REVIEW_PACK_GENERATED.value,
                ReviewPackState.WAITING_FOR_CHART_ANALYST.value,
            ),
        )
        self.record_store.retain_review_pack(record)
        return record

    def find_and_validate_answer(self, record: ReviewPackRecord) -> ValidatedAnswerPack:
        self.configuration.ensure_directories()
        candidates: list[tuple[Path, dict[str, object]]] = []
        expected_path = self.configuration.answer_directory / record.expected_answer_filename
        for path in sorted(self.configuration.answer_directory.glob("*_ANSWERS.pdf")):
            try:
                payload = _extract_governed_payload(path)
            except PdfReviewTransportError:
                if path == expected_path:
                    raise
                continue
            manifest = payload.get("manifest")
            if type(manifest) is dict and manifest.get("review_pack_id") == record.review_pack_id:
                candidates.append((path, payload))
        if not candidates:
            raise PdfReviewTransportError("ANSWER_PACK_NOT_FOUND")
        if len(candidates) > 1:
            raise PdfReviewTransportError("AMBIGUOUS_ANSWER_PACK")
        path, payload = candidates[0]
        if path.name != record.expected_answer_filename:
            raise PdfReviewTransportError("ANSWER_FILENAME_MISMATCH")
        answer_sha = sha256(path.read_bytes()).hexdigest()
        for previous in self.record_store.load_answer_imports(record.review_pack_id):
            if previous.answer_pdf_sha256 == answer_sha and previous.consumed:
                return ValidatedAnswerPack(path, answer_sha, ())
        validated = _validate_answer_payload(record, payload)
        return ValidatedAnswerPack(path, answer_sha, validated)

    def record_rejection(
        self,
        record: ReviewPackRecord,
        path: Path,
        reason: str,
    ) -> AnswerImportRecord:
        answer_sha = sha256(path.read_bytes()).hexdigest() if path.exists() else "0" * 64
        value = AnswerImportRecord(
            record.review_pack_id,
            path.name or record.expected_answer_filename,
            str(path),
            answer_sha,
            self._now(),
            (
                AnswerImportState.ANSWER_PACK_INCOMPLETE
                if reason in {"ANSWER_PACK_NOT_FOUND", "ANSWER_INCOMPLETE"}
                else AnswerImportState.ANSWER_PACK_REJECTED
            ),
            (reason,),
            False,
            None,
        )
        self.record_store.retain_answer_import(value)
        return value

    def record_import(
        self,
        record: ReviewPackRecord,
        answer: ValidatedAnswerPack,
        evidence_hashes: tuple[str, ...],
    ) -> AnswerImportRecord:
        identity = sha256(
            _canonical({
                "review_pack_id": record.review_pack_id,
                "answer_sha256": answer.answer_sha256,
                "evidence_hashes": evidence_hashes,
            })
        ).hexdigest()
        value = AnswerImportRecord(
            record.review_pack_id,
            answer.answer_path.name,
            str(answer.answer_path),
            answer.answer_sha256,
            self._now(),
            AnswerImportState.REVIEW_EVIDENCE_IMPORTED,
            (
                AnswerImportState.ANSWER_PACK_FOUND.value,
                AnswerImportState.ANSWER_PACK_VERIFIED.value,
                AnswerImportState.REVIEW_EVIDENCE_IMPORTED.value,
            ),
            True,
            identity,
        )
        self.record_store.retain_answer_import(value)
        return value

    def _now(self) -> datetime:
        value = self._clock()
        if not _aware(value):
            raise PdfReviewTransportError("PDF_REVIEW_CLOCK_INVALID")
        return value


def _validate_answer_payload(
    record: ReviewPackRecord,
    payload: dict[str, object],
) -> tuple[ValidatedAnswerCandidate, ...]:
    if type(payload) is not dict or set(payload) != {"schema", "manifest", "candidates"}:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    if payload.get("schema") != GOVERNED_ANSWER_SCHEMA:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    manifest = payload.get("manifest")
    if type(manifest) is not dict:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    checks = (
        ("review_pack_id", record.review_pack_id, "REVIEW_PACK_ID_MISMATCH"),
        ("native_run_identity", record.native_run_identity, "NATIVE_RUN_MISMATCH"),
        ("question_set_identity", record.question_set_identity, "QUESTION_SET_MISMATCH"),
        ("question_set_version", record.question_set_version, "QUESTION_SET_MISMATCH"),
        ("transport_policy_identity", record.transport_policy_identity, "TRANSPORT_POLICY_MISMATCH"),
        ("transport_policy_version", record.transport_policy_version, "TRANSPORT_POLICY_MISMATCH"),
    )
    for key, expected, code in checks:
        if manifest.get(key) != expected:
            raise PdfReviewTransportError(code)
    expected_population = [
        {
            "canonical_instrument": item.canonical_instrument,
            "chart_revision_sha256": item.chart_revision_sha256,
        }
        for item in record.candidates
    ]
    if manifest.get("candidate_population") != expected_population:
        raise PdfReviewTransportError("CANDIDATE_POPULATION_MISMATCH")
    raw_candidates = payload.get("candidates")
    if type(raw_candidates) is not list:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    if tuple(item.get("canonical_instrument") for item in raw_candidates if type(item) is dict) != tuple(
        item.canonical_instrument for item in record.candidates
    ):
        raise PdfReviewTransportError("CANDIDATE_POPULATION_MISMATCH")
    results = []
    for expected, value in zip(record.candidates, raw_candidates, strict=True):
        if _DIGEST.fullmatch(expected.native_assessment_sha256) is None:
            raise PdfReviewTransportError("NATIVE_ASSESSMENT_BINDING_INVALID")
        if type(value) is not dict:
            raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
        observed = value.get("observed_chart_instrument")
        if type(observed) is not str or observed != expected.canonical_instrument:
            raise PdfReviewTransportError("CHART_IDENTITY_MISMATCH")
        if value.get("canonical_instrument") != expected.canonical_instrument:
            raise PdfReviewTransportError("CANDIDATE_POPULATION_MISMATCH")
        if value.get("chart_revision_sha256") != expected.chart_revision_sha256:
            raise PdfReviewTransportError("CHART_REVISION_MISMATCH")
        responses = value.get("responses")
        if (
            type(responses) is not list
            or len(responses) != len(expected.expected_timeframes)
        ):
            raise PdfReviewTransportError("ANSWER_INCOMPLETE")
        try:
            if any(
                type(item) is not dict
                or item.get("chart_identity") != expected.chart_identity
                for item in responses
            ):
                raise PdfReviewTransportError("CHART_IDENTITY_MISMATCH")
            if any(
                type(observation) is not dict
                or observation.get("source_chart_identity")
                != expected.chart_identity
                for item in responses
                for observation in (
                    item.get("observations", ())
                    if type(item) is dict
                    and type(item.get("observations")) is list
                    else ()
                )
            ):
                raise PdfReviewTransportError("CHART_IDENTITY_MISMATCH")
            parsed = tuple(
                visual_evidence_v2_response_from_dict(
                    _bind_kronos_owned_response_provenance(record, expected, item)
                )
                for item in responses
            )
        except PdfReviewTransportError:
            raise
        except ValueError as error:
            raise PdfReviewTransportError("ANSWER_FORMAT_INVALID") from error
        if (
            tuple(item.timeframe.value for item in parsed) != expected.expected_timeframes
            or any(item.native_run_identity != record.native_run_identity for item in parsed)
            or any(item.native_canonical_instrument != expected.canonical_instrument for item in parsed)
            or any(item.chart_identity != expected.chart_identity for item in parsed)
            or any(item.chart_revision_sha256 != expected.chart_revision_sha256 for item in parsed)
            or any(item.question_set_identity != record.question_set_identity for item in parsed)
            or any(item.question_set_version != record.question_set_version for item in parsed)
            or any(item.provider_identity != PDF_ANSWER_PROVIDER_IDENTITY for item in parsed)
            or any(
                item.subject_kind.value != "NATIVE_ANALYTICAL_SUBJECT"
                or item.subject_identity != expected.canonical_instrument
                or item.reference_market is not None
                or item.reference_symbol is not None
                for item in parsed
            )
        ):
            raise PdfReviewTransportError("ANSWER_INCOMPLETE")

        reference_parsed: tuple[VisualEvidenceV2Response, ...] = ()
        raw_reference = value.get("reference_responses", [])
        observed_reference = value.get("observed_reference_chart_instrument")
        if expected.reference_subject_identity is None:
            if raw_reference not in (None, []) or observed_reference is not None:
                raise PdfReviewTransportError("REFERENCE_BINDING_MISMATCH")
        else:
            if observed_reference != expected.reference_symbol:
                raise PdfReviewTransportError("REFERENCE_IDENTITY_MISMATCH")
            if (
                type(raw_reference) is not list
                or len(raw_reference) != len(expected.reference_expected_timeframes)
            ):
                raise PdfReviewTransportError("REFERENCE_ANSWER_INCOMPLETE")
            if any(
                type(item) is not dict
                or item.get("chart_identity") != expected.reference_symbol
                for item in raw_reference
            ):
                raise PdfReviewTransportError("REFERENCE_IDENTITY_MISMATCH")
            if any(
                type(observation) is not dict
                or observation.get("source_chart_identity")
                != expected.reference_symbol
                for item in raw_reference
                for observation in (
                    item.get("observations", ())
                    if type(item) is dict
                    and type(item.get("observations")) is list
                    else ()
                )
            ):
                raise PdfReviewTransportError("REFERENCE_IDENTITY_MISMATCH")
            try:
                reference_parsed = tuple(
                    visual_evidence_v2_response_from_dict(
                        _bind_kronos_owned_response_provenance(
                            record, expected, item
                        )
                    )
                    for item in raw_reference
                )
            except ValueError as error:
                raise PdfReviewTransportError("REFERENCE_ANSWER_INVALID") from error
            if (
                tuple(item.timeframe.value for item in reference_parsed)
                != expected.reference_expected_timeframes
                or any(
                    item.native_run_identity != record.native_run_identity
                    or item.native_canonical_instrument
                    != expected.canonical_instrument
                    or item.chart_revision_sha256
                    != expected.chart_revision_sha256
                    or item.question_set_identity != record.question_set_identity
                    or item.question_set_version != record.question_set_version
                    or item.provider_identity != PDF_ANSWER_PROVIDER_IDENTITY
                    or item.subject_kind.value != "REFERENCE_EVIDENCE_SUBJECT"
                    or item.subject_identity != expected.reference_subject_identity
                    or item.reference_market != expected.reference_market
                    or item.reference_symbol != expected.reference_symbol
                    or item.chart_identity != expected.reference_symbol
                    for item in reference_parsed
                )
            ):
                raise PdfReviewTransportError("REFERENCE_BINDING_MISMATCH")
        results.append(ValidatedAnswerCandidate(
            expected.canonical_instrument, observed,
            expected.chart_revision_sha256, parsed, reference_parsed,
        ))
    return tuple(results)


def _bind_kronos_owned_response_provenance(
    record: ReviewPackRecord,
    candidate: ReviewPackCandidate,
    value: object,
) -> dict[str, object]:
    """Bind internal provenance after untrusted Answer identity verification."""

    if type(value) is not dict:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    bound = dict(value)
    observations = bound.get("observations")
    if type(observations) is not list:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    bound["observations"] = [
        {
            **item,
            "provenance": (
                record.transport_policy_identity,
                record.review_pack_id,
            ),
        }
        if type(item) is dict
        else item
        for item in observations
    ]
    bound.update({
        "provider_identity": PDF_ANSWER_PROVIDER_IDENTITY,
        "native_assessment_sha256": candidate.native_assessment_sha256,
        "source_provenance": (
            record.transport_policy_identity,
            record.review_pack_id,
        ),
        "schema": VISUAL_EVIDENCE_V2_SCHEMA,
        "authority": VISUAL_EVIDENCE_V2_AUTHORITY,
    })
    bound.pop("observed_chart_instrument", None)
    return bound


def _review_manifest(
    review_pack_id: str,
    run_identity: str,
    created_at: datetime,
    boundary: datetime,
    candidates: tuple[ReviewPackCandidate, ...],
    expected_answer_filename: str,
) -> dict[str, object]:
    return {
        "review_pack_id": review_pack_id,
        "native_run_identity": run_identity,
        "question_set_identity": VISUAL_QUESTION_SET_V2_ID,
        "question_set_version": VISUAL_QUESTION_SET_V2_VERSION,
        "transport_policy_identity": PDF_VISUAL_REVIEW_TRANSPORT_ID,
        "transport_policy_version": PDF_VISUAL_REVIEW_TRANSPORT_VERSION,
        "creation_timestamp": created_at.isoformat(),
        "observation_boundary": boundary.isoformat(),
        "candidate_count": len(candidates),
        "expected_answer_filename": expected_answer_filename,
        "candidates": [_primitive(item) for item in candidates],
    }


def _render_question_pdf(
    path: Path,
    manifest: dict[str, object],
    material: tuple[tuple[NativeReviewRequirement, NativeTradingViewEvidencePackage, object, bytes], ...],
) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "KronosTitle", parent=styles["Title"], textColor=colors.HexColor("#16BDEB"),
        fontName="Helvetica-Bold", fontSize=19, leading=21, alignment=TA_CENTER,
        spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        "KronosHead", parent=styles["Heading2"], textColor=colors.HexColor("#0D3851"),
        fontName="Helvetica-Bold", fontSize=11, leading=13, spaceBefore=4, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "KronosBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.2,
        leading=10.2, textColor=colors.HexColor("#172B3A"), spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        "KronosSmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=6.7,
        leading=8.1, textColor=colors.HexColor("#172B3A"), spaceAfter=1,
    ))
    styles.add(ParagraphStyle(
        "KronosCode", parent=styles["Code"], fontName="Courier", fontSize=6.0,
        leading=7.0, backColor=colors.HexColor("#F1F6F8"), borderPadding=4,
    ))
    styles.add(ParagraphStyle(
        "KronosCallout", parent=styles["BodyText"], fontName="Helvetica-Bold",
        fontSize=8.4, leading=10.5, textColor=colors.HexColor("#083C55"),
        backColor=colors.HexColor("#E4F5FA"), borderPadding=6, spaceAfter=5,
    ))
    doc = SimpleDocTemplate(
        str(temporary), pagesize=landscape(A4), rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=11 * mm, bottomMargin=10 * mm,
        title="KRONOS Swing Governed Review Questions",
        author="KRONOS",
    )
    candidates = manifest["candidates"]
    summary_rows = [
        ["Review Pack", manifest["review_pack_id"], "Native Run", manifest["native_run_identity"]],
        ["Question Set", f"{manifest['question_set_identity']} v{manifest['question_set_version']}",
         "Transport", f"{manifest['transport_policy_identity']} v{manifest['transport_policy_version']}"],
        ["Candidates", str(manifest["candidate_count"]), "Observation Boundary", _display_time(manifest["observation_boundary"])],
    ]
    candidate_rows = [["INSTRUMENT", "DIRECTION", "NATIVE OPPORTUNITY", "CHART REVISION"]] + [
        [
            _p(item["canonical_instrument"], styles["KronosSmall"]),
            item["native_direction"],
            item["native_opportunity_identity"].replace("_", " "),
            item["chart_revision_sha256"],
        ]
        for item in candidates
    ]
    story = [
        Paragraph("KRONOS SWING CHART ANALYST", styles["KronosTitle"]),
        Paragraph("GOVERNED REVIEW INSTRUCTIONS", styles["KronosHead"]),
        Paragraph(
            "ROLE: VISUAL EVIDENCE EXTRACTOR ONLY. Extract only requested visible evidence. "
            "Do not determine READY or WAIT, contradiction consequence, material barrier consequence, "
            "Clear-Air, Native direction, Entry, Stop, Invalidation, Target, R:R, trade recommendation, "
            "or execution.", styles["KronosBody"],
        ),
        Paragraph(
            "The supplied Native direction and opportunity are context only. Do not seek confirming evidence. "
            "Report supportive, contradictory, neutral, incomplete, ambiguous, and adverse visible facts with "
            "equal priority. Do not force visual evidence to agree with the Native thesis.",
            styles["KronosCallout"],
        ),
        Paragraph(
            "Identity is fail-closed: independently read OBSERVED_CHART_INSTRUMENT from every composite. "
            "Unreadable, cropped, ambiguous, or mismatched identity cannot pass. Never infer identity from price, "
            "company context, or chart shape.",
            styles["KronosBody"],
        ),
        Paragraph(
            "Do not reproduce or invent KRONOS internal provenance hashes. KRONOS binds its own Native "
            "assessment and deterministic provenance after Answer verification.",
            styles["KronosCallout"],
        ),
        Paragraph("REVIEW PACK SUMMARY", styles["KronosHead"]),
        _compact_table(summary_rows, (28 * mm, 100 * mm, 34 * mm, 105 * mm), font_size=6.5),
        Spacer(1, 4),
        _compact_table(candidate_rows, (35 * mm, 25 * mm, 100 * mm, 107 * mm), font_size=6.1, header=True),
        Paragraph(
            "The complete immutable ReviewPackRecord, machine provenance, timestamps, and final Question PDF "
            "SHA-256 remain persisted by KRONOS; this visible summary is intentionally compact.",
            styles["KronosSmall"],
        ),
        PageBreak(),
        Paragraph("FROZEN VISUAL QUESTION SET V2", styles["KronosTitle"]),
    ]
    question_rows = [["QUESTION", "VISIBLE EVIDENCE TASK", "1W", "1D", "4H", "1H"]]
    for index, question in enumerate(FROZEN_VISUAL_QUESTION_SET_V2, 1):
        question_rows.append([
            f"Q{index} {question.value}",
            VISUAL_QUESTION_SEMANTICS_V2[question],
            *(dict(visual_question_routing(timeframe))[question].value for timeframe in VisualTimeframe),
        ])
    story.append(_compact_table(
        question_rows,
        (56 * mm, 115 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm),
        font_size=5.9,
        header=True,
    ))
    story.extend([
        Paragraph("COVERAGE AND CORE RULES", styles["KronosHead"]),
        Paragraph(
            "Every timeframe response MUST contain Q1 through Q10 exactly once and in order. Where routing is "
            "not applicable, return the governed NOT_APPLICABLE representation; do not omit the question. "
            "Q3 reports only material visual S/R absent from supplied deterministic evidence. For Q3, a "
            "confident finding that no additional material S/R exists is OBSERVED / NONE / NOT_APPLICABLE; "
            "do not use NOT_VISIBLE for that negative finding. Use NOT_VISIBLE only when the supplied chart "
            "does not permit reliable determination. Q10 is a strict "
            "escape hatch for a clearly visible, materially relevant fact not covered by Q1-Q9 or supplied facts.",
            styles["KronosBody"],
        ),
        _compact_table(
            [
                ["VALID Q3 CONFIDENT NEGATIVE", '{"observation_status":"OBSERVED","observation":"NONE","level_availability":"NOT_APPLICABLE","price":null,"zone_low":null,"zone_high":null}'],
                ["Q3 CANNOT DETERMINE", "Use NOT_VISIBLE only when the chart does not permit reliable determination."],
            ],
            (52 * mm, 215 * mm),
            font_size=6.2,
        ),
        Paragraph(
            "Q10 observation = NONE requires why_not_covered_elsewhere = null. Q10 observation != NONE requires "
            "a bounded non-empty why_not_covered_elsewhere explanation. For Q1-Q9 it MUST be null.",
            styles["KronosBody"],
        ),
        _compact_table(
            [
                ["INVALID Q10 NONE", '{"observation":"NONE","why_not_covered_elsewhere":"No additional fact met the escape hatch."}'],
                ["VALID Q10 NONE", '{"observation":"NONE","why_not_covered_elsewhere":null}'],
            ],
            (42 * mm, 225 * mm),
            font_size=6.2,
        ),
        Paragraph(
            "POINT: price = 127.50, zone_low = null, zone_high = null. ZONE: price = null, zone_low = 127.00, "
            "zone_high = 128.00. LEVEL_UNAVAILABLE: all three numeric fields = null. Never combine price and zone. "
            "LEVEL_UNAVAILABLE and NOT_APPLICABLE cannot carry numeric values.",
            styles["KronosBody"],
        ),
        Paragraph(
            "observation_status: " + ", ".join(item.value for item in VisualObservationStatus)
            + ". level_availability: " + ", ".join(item.value for item in VisualLevelAvailability) + ".",
            styles["KronosSmall"],
        ),
    ])
    for requirement, package, revision, image_bytes in material:
        story.append(PageBreak())
        thesis = requirement.thesis
        image = _fit_image(
            image_bytes,
            CANDIDATE_CHART_MAX_WIDTH,
            (
                CANDIDATE_CHART_MAX_HEIGHT - 10 * mm
                if requirement.mcx_reference is not None
                else CANDIDATE_CHART_MAX_HEIGHT
            ),
        )
        image.hAlign = "CENTER"
        context = (
            f"EXPECTED {requirement.canonical_instrument}  |  {thesis.direction.value}  |  "
            f"{thesis.opportunity_identity.value.replace('_', ' ')}  |  "
            f"1W {thesis.weekly_state.value}  |  1D {thesis.daily_state.value}  |  "
            f"4H {thesis.four_hour_state.value}  |  1H {thesis.one_hour_state.value}"
        )
        subject_binding = (
            ""
            if requirement.mcx_reference is None
            else (
                f"NATIVE SUBJECT: MCX {requirement.canonical_instrument} (1H)  |  "
                f"REFERENCE SUBJECT: {requirement.mcx_reference.reference_subject_identity} / "
                f"{requirement.mcx_reference.reference_symbol} (1D / 4H / 1H)  |  "
                "ONE SHARED REVISION; DISTINCT ROLES; COMEX REFERENCE ONLY"
            )
        )
        story.extend([
            Paragraph(xml_escape(requirement.canonical_instrument), styles["KronosTitle"]),
            Paragraph(xml_escape(context), styles["KronosSmall"]),
            *(
                [Paragraph(xml_escape(subject_binding), styles["KronosSmall"])]
                if subject_binding else []
            ),
            image,
            Spacer(1, 3),
            _candidate_fact_table(thesis.timeframe_facts),
            Spacer(1, 2),
            Paragraph(
                "ANCHOR: " + xml_escape(thesis.operative_anchor_identity.replace("_", " "))
                + " @ " + _price(thesis.operative_anchor_price)
                + "  |  CHART: " + xml_escape(package.binding.chart_subject_identity)
                + "  |  REVISION: " + revision.sha256
                + "<br/>Independently report OBSERVED_CHART_INSTRUMENT. Unreadable or ambiguous identity cannot pass.",
                styles["KronosSmall"],
            ),
        ])
    story.extend([
        PageBreak(),
        Paragraph("CANONICAL GOVERNED ANSWER CONTRACT", styles["KronosTitle"]),
        Paragraph(
            f"Exactly one section: {BEGIN_GOVERNED_ANSWER_DATA} ... {END_GOVERNED_ANSWER_DATA}. "
            "Use valid JSON only. No Markdown fences or commentary inside. Prose outside has no machine authority.",
            styles["KronosBody"],
        ),
        Table(
            [[
                [
                    Paragraph("VALID OBSERVATION OBJECT", styles["KronosHead"]),
                    Preformatted(
                        json.dumps(VALID_OBSERVATION_EXAMPLE, indent=2),
                        styles["KronosCode"],
                    ),
                ],
                [
                    Paragraph("STRICT GOVERNED JSON SHAPE", styles["KronosHead"]),
                    Preformatted(
                        BEGIN_GOVERNED_ANSWER_DATA + "\n"
                        + json.dumps(_answer_contract_example(manifest), indent=2)
                        + "\n" + END_GOVERNED_ANSWER_DATA,
                        styles["KronosCode"],
                    ),
                ],
            ]],
            colWidths=(78 * mm, 189 * mm),
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]),
        ),
        PageBreak(),
        Paragraph("ANSWER FILE AND FINAL OPERATING INSTRUCTIONS", styles["KronosTitle"]),
        Paragraph(
            f"Question: {Path(path).name}<br/>Answer: {manifest['expected_answer_filename']}<br/>"
            "Use the same timestamp. Do not generate a new Answer timestamp.",
            styles["KronosBody"],
        ),
        Paragraph(
            "Repeat exactly: review_pack_id, Native run, question-set identity/version, transport identity/version, "
            "candidate population, canonical instrument, independently observed chart instrument, and source chart "
            "revision. Produce the exact routed responses printed for each candidate: standard Native subjects use "
            "1W, 1D, 4H, 1H; GOLDM uses Native MCX 1H plus separate Reference COMEX 1D, 4H, 1H. Every response "
            "contains Q1-Q10 exactly once and in order.",
            styles["KronosBody"],
        ),
        Paragraph(
            "FIELDS THE CHART ANALYST MUST RETURN are limited to the governed Answer transport/chart bindings and "
            "visible observations shown in the contract. KRONOS INTERNAL PROVENANCE - including Native assessment "
            "hashes and generated provenance arrays - is populated by KRONOS and must not be reproduced or invented.",
            styles["KronosSmall"],
        ),
        _compact_table(
            [["INSTRUMENT", "DIRECTION", "OPPORTUNITY", "CHART REVISION"]]
            + [[
                _p(item["canonical_instrument"], styles["KronosSmall"]),
                item["native_direction"],
                item["native_opportunity_identity"].replace("_", " "),
                item["chart_revision_sha256"],
            ] for item in candidates],
            (35 * mm, 25 * mm, 100 * mm, 107 * mm),
            font_size=6.1,
            header=True,
        ),
        Spacer(1, 5),
        Paragraph(
            "Final checks: preserve exact readable point/zone values; otherwise LEVEL_UNAVAILABLE. Do not omit "
            "routed questions. Do not infer chart identity. Do not create analytical consequences, trade geometry, "
            "recommendations, or execution. Save one Answer PDF in the configured CHATGPT ANSWERS directory.",
            styles["KronosCallout"],
        ),
    ])
    try:
        doc.build(story, onFirstPage=_page_frame, onLaterPages=_page_frame)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _page_frame(canvas, document) -> None:  # type: ignore[no-untyped-def]
    width, height = landscape(A4)
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#061725"))
    canvas.rect(0, height - 8 * mm, width, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#16BDEB"))
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(10 * mm, height - 5.5 * mm, "KRONOS - GOVERNED VISUAL REVIEW")
    canvas.setFillColor(colors.HexColor("#546A78"))
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(width - 10 * mm, 6 * mm, f"Page {document.page}")
    canvas.restoreState()


def _fit_image(payload: bytes, max_width: float, max_height: float) -> Image:
    reader = ImageReader(BytesIO(payload))
    width, height = reader.getSize()
    scale = min(max_width / width, max_height / height)
    return Image(BytesIO(payload), width=width * scale, height=height * scale)


def _display_time(value: object) -> str:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return parsed.astimezone(_IST).strftime("%d %b %Y %H:%M IST")


def _price(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _p(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(xml_escape(str(value)), style)


def _compact_table(
    rows: list[list[object]],
    widths: tuple[float, ...],
    *,
    font_size: float,
    header: bool = False,
) -> Table:
    body = ParagraphStyle(
        "KronosTableBody", fontName="Helvetica", fontSize=font_size,
        leading=font_size + 1.2, textColor=colors.HexColor("#172B3A"),
    )
    heading = ParagraphStyle(
        "KronosTableHead", parent=body, fontName="Helvetica-Bold",
        textColor=colors.white,
    )
    values = [
        [
            item if isinstance(item, Paragraph)
            else Paragraph(xml_escape(str(item)), heading if header and row_index == 0 else body)
            for item in row
        ]
        for row_index, row in enumerate(rows)
    ]
    rules: list[tuple[object, ...]] = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AFC4CF")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1),
         (colors.white, colors.HexColor("#F3F7F9"))),
    ]
    if header:
        rules.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D3851")))
    return Table(values, colWidths=widths, style=TableStyle(rules), repeatRows=1 if header else 0)


def _candidate_fact_table(facts: tuple[object, ...]) -> Table:
    rows: list[list[object]] = [["TF", "OHLC / VOLUME", "SMA20", "SMA50", "SMA200", "KEY STRUCTURE"]]
    for fact in facts:
        latest: dict[tuple[int, str], object] = {}
        for pivot in fact.pivots:
            key = (pivot.radius, pivot.kind.value)
            current = latest.get(key)
            if current is None or pivot.timestamp > current.timestamp:
                latest[key] = pivot
        structure = " / ".join(
            f"R{radius} {kind} {_price(latest[(radius, kind)].price)}"
            for radius in (1, 2)
            for kind in ("HIGH", "LOW")
            if (radius, kind) in latest
        ) or "No governed pivots available"
        rows.append([
            fact.timeframe.value,
            f"O {_price(fact.open)}  H {_price(fact.high)}  L {_price(fact.low)}  "
            f"C {_price(fact.close)}  V {fact.volume:,}",
            _price(fact.sma20),
            _price(fact.sma50),
            _price(fact.sma200),
            structure,
        ])
    return _compact_table(
        rows,
        (10 * mm, 72 * mm, 22 * mm, 22 * mm, 22 * mm, 119 * mm),
        font_size=5.9,
        header=True,
    )


def _answer_contract_example(manifest: dict[str, object]) -> dict[str, object]:
    reference_candidate = next(
        (
            item for item in manifest["candidates"]
            if item.get("reference_subject_identity") is not None
        ),
        None,
    )
    example_candidate = (
        reference_candidate
        if reference_candidate is not None
        else manifest["candidates"][0]
    )
    has_reference = reference_candidate is not None
    return {
        "schema": GOVERNED_ANSWER_SCHEMA,
        "manifest": {
            "review_pack_id": manifest["review_pack_id"],
            "native_run_identity": manifest["native_run_identity"],
            "question_set_identity": manifest["question_set_identity"],
            "question_set_version": manifest["question_set_version"],
            "transport_policy_identity": manifest["transport_policy_identity"],
            "transport_policy_version": manifest["transport_policy_version"],
            "candidate_population": [
                {
                    "canonical_instrument": example_candidate["canonical_instrument"],
                    "chart_revision_sha256": example_candidate["chart_revision_sha256"],
                }
            ],
        },
        "candidates": [
            {
                "canonical_instrument": example_candidate["canonical_instrument"],
                "observed_chart_instrument": "<READ INDEPENDENTLY FROM CHART>",
                "chart_revision_sha256": example_candidate["chart_revision_sha256"],
                "responses": [
                    {
                        "model_identity": "<CHART ANALYST IDENTITY>",
                        "request_timestamp": "<ISO-8601>",
                        "native_run_identity": "<EXACT MANIFEST VALUE>",
                        "native_canonical_instrument": example_candidate["canonical_instrument"],
                        "subject_kind": "NATIVE_ANALYTICAL_SUBJECT",
                        "subject_identity": example_candidate["canonical_instrument"],
                        "reference_market": None,
                        "reference_symbol": None,
                        "timeframe": " | ".join(example_candidate["expected_timeframes"]),
                        "observation_boundary": "<EXACT SUPPLIED FACT VALUE>",
                        "chart_identity": "<READ INDEPENDENTLY FROM CHART>",
                        "chart_revision_sha256": example_candidate["chart_revision_sha256"],
                        "observations": ["Q1 THROUGH Q10 EXACTLY ONCE AND IN ORDER"],
                        "question_set_identity": VISUAL_QUESTION_SET_V2_ID,
                        "question_set_version": VISUAL_QUESTION_SET_V2_VERSION,
                    }
                ],
                **(
                    {
                        "observed_reference_chart_instrument": example_candidate["reference_symbol"],
                        "reference_responses": [
                            {
                                "model_identity": "<CHART ANALYST IDENTITY>",
                                "request_timestamp": "<ISO-8601>",
                                "native_run_identity": "<EXACT MANIFEST VALUE>",
                                "native_canonical_instrument": example_candidate["canonical_instrument"],
                                "subject_kind": "REFERENCE_EVIDENCE_SUBJECT",
                                "subject_identity": example_candidate["reference_subject_identity"],
                                "reference_market": example_candidate["reference_market"],
                                "reference_symbol": example_candidate["reference_symbol"],
                                "timeframe": " | ".join(example_candidate["reference_expected_timeframes"]),
                                "observation_boundary": "<EXACT SUPPLIED FACT VALUE>",
                                "chart_identity": example_candidate["reference_symbol"],
                                "chart_revision_sha256": example_candidate["chart_revision_sha256"],
                                "observations": ["Q1 THROUGH Q10 EXACTLY ONCE AND IN ORDER"],
                                "question_set_identity": VISUAL_QUESTION_SET_V2_ID,
                                "question_set_version": VISUAL_QUESTION_SET_V2_VERSION,
                            }
                        ],
                    }
                    if has_reference else {}
                ),
            }
        ],
    }


def _extract_governed_payload(path: Path) -> dict[str, object]:
    _validate_pdf_file(path)
    try:
        reader = PdfReader(str(path), strict=True)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as error:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID") from error
    if text.count(BEGIN_GOVERNED_ANSWER_DATA) != 1 or text.count(END_GOVERNED_ANSWER_DATA) != 1:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    section = text.split(BEGIN_GOVERNED_ANSWER_DATA, 1)[1].split(
        END_GOVERNED_ANSWER_DATA, 1
    )[0].strip()
    if not section or len(section.encode("utf-8")) > 16 * 1024 * 1024:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    try:
        payload = json.loads(section)
    except json.JSONDecodeError as error:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID") from error
    if type(payload) is not dict:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    return payload


def _validate_pdf_file(path: Path) -> None:
    try:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size <= 8
            or metadata.st_size > _MAX_PDF_BYTES
        ):
            raise PdfReviewTransportError("ANSWER_FILE_UNSAFE")
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise PdfReviewTransportError("ANSWER_FILE_TYPE_INVALID")
    except OSError as error:
        raise PdfReviewTransportError("ANSWER_FILE_UNAVAILABLE") from error


def _review_pack_from_dict(value: object) -> ReviewPackRecord:
    if type(value) is not dict:
        raise PdfReviewTransportError("REVIEW_PACK_RECORD_INVALID")
    try:
        return ReviewPackRecord(
            review_pack_id=value["review_pack_id"],
            native_run_identity=value["native_run_identity"],
            question_filename=value["question_filename"],
            question_path=value["question_path"],
            expected_answer_filename=value["expected_answer_filename"],
            question_pdf_sha256=value["question_pdf_sha256"],
            created_at=datetime.fromisoformat(value["created_at"]),
            observation_boundary=datetime.fromisoformat(value["observation_boundary"]),
            candidates=tuple(ReviewPackCandidate(
                canonical_instrument=item["canonical_instrument"],
                native_direction=item["native_direction"],
                native_opportunity_identity=item["native_opportunity_identity"],
                native_assessment_sha256=item["native_assessment_sha256"],
                chart_identity=item["chart_identity"],
                chart_revision_sha256=item["chart_revision_sha256"],
                expected_timeframes=tuple(item["expected_timeframes"]),
                reference_subject_identity=item.get("reference_subject_identity"),
                reference_market=item.get("reference_market"),
                reference_symbol=item.get("reference_symbol"),
                reference_expected_timeframes=tuple(
                    item.get("reference_expected_timeframes", ())
                ),
            ) for item in value["candidates"]),
            state=ReviewPackState(value["state"]),
            state_history=tuple(value["state_history"]),
            question_set_identity=value["question_set_identity"],
            question_set_version=value["question_set_version"],
            transport_policy_identity=value["transport_policy_identity"],
            transport_policy_version=value["transport_policy_version"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PdfReviewTransportError("REVIEW_PACK_RECORD_INVALID") from error


def _answer_import_from_dict(value: object) -> AnswerImportRecord:
    if type(value) is not dict:
        raise PdfReviewTransportError("ANSWER_IMPORT_RECORD_INVALID")
    try:
        return AnswerImportRecord(
            value["review_pack_id"], value["answer_filename"], value["answer_path"],
            value["answer_pdf_sha256"], datetime.fromisoformat(value["discovered_at"]),
            AnswerImportState(value["state"]), tuple(value["validation_reasons"]),
            value["consumed"], value["evidence_import_identity"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PdfReviewTransportError("ANSWER_IMPORT_RECORD_INVALID") from error


def _answer_artifact_from_dict(value: object) -> AnswerArtifactRecord:
    if type(value) is not dict:
        raise PdfReviewTransportError("ANSWER_ARTIFACT_RECORD_INVALID")
    try:
        return AnswerArtifactRecord(
            value["review_pack_id"], value["answer_filename"], value["answer_path"],
            value["answer_pdf_sha256"],
            datetime.fromisoformat(value["first_discovered_at"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PdfReviewTransportError("ANSWER_ARTIFACT_RECORD_INVALID") from error


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", delete=False,
        ) as temporary:
            temporary_name = temporary.name
            json.dump(payload, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except OSError as error:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise PdfReviewTransportError("PDF_REVIEW_RECORD_WRITE_FAILED") from error


def _read_json(path: Path) -> dict[str, object]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise PdfReviewTransportError("PDF_REVIEW_RECORD_INVALID")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PdfReviewTransportError("PDF_REVIEW_RECORD_INVALID") from error
    if type(value) is not dict:
        raise PdfReviewTransportError("PDF_REVIEW_RECORD_INVALID")
    return value


def _primitive(value):  # type: ignore[no-untyped-def]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return _primitive(asdict(value))
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(_primitive(value), sort_keys=True, separators=(",", ":")).encode()


def _safe(value: str) -> str:
    if not value or re.fullmatch(r"[A-Za-z0-9_.-]+", value) is None:
        raise PdfReviewTransportError("PDF_REVIEW_IDENTITY_INVALID")
    return value


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "ANSWER_ARTIFACT_RECORD_SCHEMA",
    "ANSWER_IMPORT_RECORD_SCHEMA",
    "BEGIN_GOVERNED_ANSWER_DATA",
    "CURRENT_REVIEW_PACK_SELECTION_SCHEMA",
    "END_GOVERNED_ANSWER_DATA",
    "GOVERNED_ANSWER_SCHEMA",
    "PDF_ANSWER_PROVIDER_IDENTITY",
    "PDF_VISUAL_REVIEW_TRANSPORT_ID",
    "PDF_VISUAL_REVIEW_TRANSPORT_VERSION",
    "AnswerArtifactRecord",
    "AnswerImportRecord",
    "AnswerImportState",
    "CurrentReviewPackSelection",
    "PdfReviewRecordStore",
    "PdfReviewTransportError",
    "PdfVisualReviewTransport",
    "ReviewPackCandidate",
    "ReviewPackRecord",
    "ReviewPackState",
    "ValidatedAnswerCandidate",
    "ValidatedAnswerPack",
]
