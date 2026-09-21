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
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer
from xml.sax.saxutils import escape

from kronos.configuration.pdf_visual_review import PdfVisualReviewConfiguration
from kronos.swing.v1 import mcx_native_visual_contract as mcx_contract
from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError, require, strict_json
from kronos.swing.v1.pdf_contract_layout_v3 import (
    PAGE_MARGIN, PARAGRAPH_SPACING, contract_block,
)
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
    FROZEN_VISUAL_QUESTION_SET_V3,
    FROZEN_VISUAL_QUESTION_SET_V3_SUCCESSOR,
    VISUAL_QUESTION_SEMANTICS_V3_SUCCESSOR,
    VISUAL_QUESTION_SET_V3_SUCCESSOR_VERSION,
    VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
    VISUAL_EVIDENCE_V3_SUCCESSOR_ANSWER_SCHEMA,
    VISUAL_EVIDENCE_V3_AUTHORITY,
    VISUAL_EVIDENCE_V3_LEGACY_ANSWER_SCHEMA,
    VISUAL_EVIDENCE_V3_LEGACY_SCHEMA,
    VISUAL_EVIDENCE_V3_SCHEMA,
    VISUAL_EVIDENCE_V3_SUCCESSOR_SCHEMA,
    VISUAL_QUESTION_SET_V3_ID,
    VISUAL_QUESTION_SET_V3_LEGACY_VERSION,
    VISUAL_QUESTION_SET_V3_VERSION,
    VisualSetupQuality,
    VisualEvidenceV3Request,
    VisualEvidenceV3Response,
    VisualTimeframe,
    visual_evidence_v3_answer_contract,
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


def extract_successor_answer_pdf(payload: bytes) -> bytes:
    """Parse the same bounded immutable bytes later retained and hashed.

    This explicit successor parser does not alter historical PDF decoders.
    Duplicate JSON keys remain visible to strict_json rather than disappearing
    through ordinary dictionary parsing.
    """
    require(type(payload) is bytes and 8 < len(payload) <= 128 * 1024 * 1024
            and payload.startswith(b"%PDF-"), "REVIEW_ACCEPTANCE_INCOMPLETE")
    try:
        reader = PdfReader(BytesIO(payload), strict=True)
        require(not reader.is_encrypted, "REVIEW_ACCEPTANCE_INCOMPLETE")
        content = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as error:
        raise ReviewEvidenceError("REVIEW_ACCEPTANCE_INCOMPLETE") from error
    require(content.count(BEGIN_GOVERNED_ANSWER_DATA) == 1
            and content.count(END_GOVERNED_ANSWER_DATA) == 1, "REVIEW_ACCEPTANCE_INCOMPLETE")
    start = content.index(BEGIN_GOVERNED_ANSWER_DATA) + len(BEGIN_GOVERNED_ANSWER_DATA)
    end = content.index(END_GOVERNED_ANSWER_DATA)
    require(start < end, "REVIEW_ACCEPTANCE_INCOMPLETE")
    governed = content[start:end].strip().encode("utf-8")
    strict_json(governed)
    return governed


def render_mcx_successor_question_pdf(native, reference, charts: dict[str, bytes]) -> tuple:
    """Render one physical PDF without publishing any request or historical record.

    Inputs are already-issued independent pre-render mappings. Chart bytes are
    keyed by exact revision digest; no path/latest scan or native/reference image
    substitution occurs. Returns finalized mappings and final bytes for one
    subsequent atomic commit under the existing WO05 -> WO07 guard.
    """
    request = mcx_contract.mcx_question_pack_from_mappings(native, reference)
    packs = (request.value, request.value["supporting_reference_pack"])
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize, styles["BodyText"].leading = 9, 12
    styles["BodyText"].spaceAfter = PARAGRAPH_SPACING
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN, topMargin=PAGE_MARGIN, bottomMargin=PAGE_MARGIN, invariant=1)
    story = [Paragraph("KRONOS MCX - INDEPENDENT VISUAL REVIEW", styles["Title"]),
        Paragraph("Return the Answer PDF as " + escape(native.value["review_pack_identity"] + "_ANSWERS.pdf"), styles["BodyText"]),
        Paragraph("Native and supporting-reference extraction only. No Readiness, promotion, "
                  "reconciliation, trade or execution authority. Independently read visible identity; "
                  "never overwrite it with an expected label.", styles["BodyText"]),
        contract_block(json.dumps({key: native.value[key] for key in
            ("request_bundle_identity", "review_cycle_identity", "review_pack_identity")}, indent=2))]
    story.extend([Paragraph("Native and supporting-reference question contracts", styles["Heading2"]),
                  contract_block(json.dumps(request.value, indent=2))])
    for pack in packs:
        for subject in pack["subjects"]:
            seen = set()
            for chart in subject["charts"]:
                revision = chart["chart_revision_sha256"]
                require(revision in charts and type(charts[revision]) is bytes
                        and sha256(charts[revision]).hexdigest() == revision, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
                if revision in seen:
                    continue  # one original composite, not three artificial copies
                seen.add(revision)
                image = Image(BytesIO(charts[revision]))
                scale = min((A4[0] - 2 * PAGE_MARGIN - 12) / image.imageWidth,
                            (A4[1] - 2 * PAGE_MARGIN - 125) / image.imageHeight)
                image.drawWidth, image.drawHeight = image.imageWidth * scale, image.imageHeight * scale
                story.extend([PageBreak(), Paragraph(escape(subject["subject_identity"] + " - " + subject["role"]), styles["Heading1"]),
                    contract_block(json.dumps({"subject_reference": subject["subject_reference"],
                        "chart_revision_sha256": revision, "timeframes": [item["timeframe"] for item in subject["charts"]
                        if item["chart_revision_sha256"] == revision]}, indent=2)), image])
    story.extend([PageBreak(), Paragraph("Exact Answer contract", styles["Title"]),
        Paragraph("Return one governed JSON block between " + BEGIN_GOVERNED_ANSWER_DATA + " and "
                  + END_GOVERNED_ANSWER_DATA + ". All listed keys are required. No extra fields or duplicate JSON keys. "
                  "No KRONOS provenance, run, timestamps, boundaries, machine hashes or authority fields may be supplied. "
                  "Model identity is an untrusted nonempty attribution label up to 128 characters only. "
                  "Answer identities are nonempty text up to 256 characters; versions are JSON strings.", styles["BodyText"])])
    # Full closed shapes and enums are derived from the same frozen validator;
    # no second question identity or alternative analytical rule is introduced.
    successor = native.value["version"] == mcx_contract.SUCCESSOR_VERSION
    shape = {"root_fields": ["schema", "version", "request_reference", "answer_identity", "subjects"],
        "native_root_additional_required_fields": (["supporting_reference_answer", "comparison_answer"] if successor
                                                    else ["supporting_reference_answer"]),
        "native_answer_schema": mcx_contract.NATIVE_ANSWER_V2 if successor else mcx_contract.NATIVE_ANSWER,
        "reference_answer_schema": mcx_contract.REFERENCE_ANSWER_V2 if successor else mcx_contract.REFERENCE_ANSWER,
        "version": "2.0" if successor else "1.0", "request_reference_fields": sorted(mcx_contract.REQUEST_REFERENCE_FIELDS),
        "subject_fields": sorted(mcx_contract.ANSWER_SUBJECT_FIELDS - {"observed_chart_identity"} if successor
                                 else mcx_contract.ANSWER_SUBJECT_FIELDS), "response_fields": sorted(mcx_contract.RESPONSE_FIELDS),
        "observation_fields": sorted(mcx_contract.OBSERVATION_FIELDS),
        "result_fields": {qid: sorted(fields | ({"identity_correspondence"} if successor and i == 0 else set()))
            for i, (qid, fields) in enumerate(zip(mcx_contract.QUESTION_IDS_V2 if successor else mcx_contract.QUESTION_IDS,
                                                 mcx_contract.RESULT_FIELDS, strict=True))},
        "observation_status": list(mcx_contract.STATUSES), "presence": list(mcx_contract.PRESENCE),
        "price_relationship": list(mcx_contract.PRICE_RELATIONSHIP), "interaction": list(mcx_contract.INTERACTION),
        "reference_relationship": list(mcx_contract.REFERENCE_RELATIONSHIP), "setup_quality": list(mcx_contract.QUALITY),
        "clustering": list(mcx_contract.CLUSTERING), "native_components": list(mcx_contract.NATIVE_COMPONENTS),
        "reference_components": list(mcx_contract.REFERENCE_COMPONENTS)}
    if successor:
        shape["comparison_contract"] = dict(schema=mcx_contract.COMPARISON_ANSWER, version="1.0",
            root_fields=["schema", "version", "request_references", "answer_identity", "subjects"],
            subject_fields=["native_candidate_reference", "native_subject_reference",
                            "reference_subject_reference", "pair_binding_sha256", "observations"],
            questions=list(mcx_contract.COMPARISON_IDS),
            result_fields={"M1": ["mapping_state", "coverage_state", "finding"],
                           "M2": ["by_timeframe"],
                           "M3": ["relationship_to_native_direction", "affected_timeframes", "limitations", "finding"]},
            statuses=["OBSERVED", "PARTIAL", "UNAVAILABLE", "INVALID"],
            mapping_state=["MATCHED", "MISMATCHED", "UNDETERMINED"],
            coverage_state=["SUFFICIENT", "PARTIAL", "INSUFFICIENT"],
            m2_timeframes=["1D", "4H", "1H"],
            m2_relationship=["AGREES", "PARTLY_AGREES", "CONFLICTS", "NOT_COMPARABLE"],
            m3_relationship=["SUPPORTS", "CHALLENGES", "MIXED", "NO_MATERIAL_DIVERGENCE", "NOT_ESTABLISHED"],
            m3_limitations=["DIFFERENT_SESSIONS", "INCOMPLETE_BAR", "EXPIRY_OR_ROLL",
                "CONTINUOUS_BACK_ADJUSTMENT_UNKNOWN", "CONTRACT_IDENTITY_UNCLEAR",
                "CURRENCY_OR_BASIS_DIFFERENCE", "MISSING_EVIDENCE", "OTHER_VISIBLE_LIMITATION"])
    story.append(contract_block(json.dumps(shape, indent=2)))
    for paragraph in (
        "Echo each logical request reference from its own question contract. Preserve independently identified native and reference Answers. "
        "Preserve exact ordered subject references, candidate references, roles, subject identities, markets and reference symbols. "
        "Return exactly 1D, 4H, 1H per subject, and exactly Q1-Q10 in order per response. Native 1W is forbidden.",
        ("Q1 alone retains observed_identity, observed_market and observed_timeframe as independently visible raw text. "
         "Mark identity_correspondence MATCHED, CONTRADICTED or UNDETERMINED against trusted expected identity; "
         "native MATCHED is required. A correctly mapped but visually unavailable reference may remain UNDETERMINED. "
         if successor else "Read observed_chart_identity independently. Q1 result observed_identity, observed_market and observed_timeframe must be independently "
         "read; readability is READABLE, PARTIAL or UNREADABLE. Unreadable/unknown identity cannot pass. ") +
        "chart_identity, source_chart_identity and revision echoes must remain exact; do not normalize.",
        "visible_basis and finding are nonempty text up to 512 characters; confidence_in_extraction is nonempty text up to 64. "
        "ambiguity_reason is text up to 512 characters and nonempty for PARTIAL, UNAVAILABLE or INVALID. "
        "Q1-Q9 why_not_covered_elsewhere is required null. Q10 finding NONE requires null; otherwise a nonempty explanation up to 512 characters.",
        "Native Q3/Q10 machine_coverage_comparison is COMPARISON_UNAVAILABLE. Reference Q3/Q10 is NOT_APPLICABLE. "
        "No machine inventory was supplied. Q3/Q6 prices are either one finite nonnegative JSON number point_price, "
        "one complete ordered nonnegative zone_low/zone_high pair, or all three null; booleans and numeric strings fail.",
        "Q3/Q6 finding NONE or status NOT_VISIBLE, UNAVAILABLE or INVALID requires all three price fields null. "
        "Q2 and native Q4 presence other than PRESENT requires both relationship and interaction NOT_OBSERVABLE.",
        "Native Q4 uses the chart-declared PREVIOUS_MONTH for 1D/4H and PREVIOUS_WEEK for 1H. If the governed reference basis is UNAVAILABLE, "
        "return UNAVAILABLE, presence NOT_IDENTIFIABLE, relationship NOT_OBSERVABLE and interaction NOT_OBSERVABLE. "
        "Reference Q4 is NOT_APPLICABLE with not_applicable_reason REFERENCE_PERIOD_NOT_GOVERNED and all four result values null. "
        "Every other not_applicable_reason is null; NOT_APPLICABLE status is permitted only for reference Q4.",
        "Q5 setup_quality is a printed bounded enum; finding is visual extraction relative to supplied Native direction as orientation only. "
        "Do not produce reconciliation, direction changes, Readiness, promotion or trading consequences. Q7/Q8 finding is bounded text. "
        "Q8 NOT_VISIBLE or UNAVAILABLE requires finding NONE.",
        "Q9 components are distinct and ordered according to the printed role-specific component list. CLUSTERED requires at least two "
        "identifiable components (UNIDENTIFIED_PLOTTED_STRUCTURE does not count). NOT_CLUSTERED requires none; "
        "PARTIAL_COMPONENT_IDENTITY requires UNIDENTIFIED_PLOTTED_STRUCTURE; NOT_OBSERVABLE requires none. "
        "Reference components may not include native governed-reference levels or operative anchors.",
    ):
        story.append(Paragraph(escape(paragraph), styles["BodyText"]))
    if successor:
        story.append(Paragraph("All three Answer roots share one answer_identity. M1-M3 are candidate-level supporting "
                               "comparison only; do not place them in the six chart responses. Wrong mapped reference "
                               "identity or INVALID observation rejects the entire paired Answer.", styles["BodyText"]))
    document.build(story)
    pdf = buffer.getvalue()
    finalized = tuple(type(mapping).create({**mapping.value, "review_pack_sha256": sha256(pdf).hexdigest()})
                      for mapping in (native, reference))
    return (*finalized, pdf)


def render_nse_successor_question_pdf(mapping, prepared):
    """Self-contained version-dispatched successor envelope."""
    from kronos.swing.v1.review_evidence_binding import NseReviewRequestMapping
    from kronos.swing.v1.visual_evidence_v3 import VISUAL_QUESTION_SEMANTICS_V3
    require(type(mapping) is NseReviewRequestMapping, "REVIEW_REQUEST_MISMATCH")
    value = mapping.value
    require(len(prepared) == len(value["subjects"]), "REVIEW_REQUEST_MISMATCH")
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize, styles["BodyText"].leading = 9, 12
    out = BytesIO()
    document = SimpleDocTemplate(out, pagesize=A4, leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN, bottomMargin=PAGE_MARGIN, invariant=1)
    envelope = dict(schema=value["answer_schema"], version=value["answer_version"],
        request_reference=mapping.request_reference, answer_identity="<NEW UNIQUE ANSWER IDENTITY>", subjects=[])
    story = [Paragraph("KRONOS NSE - VISUAL REVIEW", styles["Title"]),
        Paragraph("Return the Answer PDF as " + escape(value["review_pack_identity"] + "_ANSWERS.pdf"), styles["BodyText"]),
        contract_block(json.dumps({key: value[key] for key in ("review_pack_identity", "native_run_identity",
            "question_set_identity", "question_set_version", "request_identity", "request_sha256")}, indent=2)),
        Paragraph("Independent visual evidence only. Read observed identity independently. Do not normalize or "
            "replace it with an expected identity. No trading, Readiness or promotion authority.", styles["BodyText"])]
    for subject, requests in zip(value["subjects"], prepared, strict=True):
        require(len(requests) == 4 and tuple(x.timeframe.value for x in requests) == ("1W", "1D", "4H", "1H")
            and all(x.requirement.canonical_instrument == subject["canonical_instrument"]
                and x.chart_revision_sha256 == subject["chart_revision_sha256"] for x in requests), "REVIEW_REQUEST_MISMATCH")
        examples = [_complete_response_example(request) for request in requests]
        # Keep the illustrative Q5 string on one physical PDF line. Wrapping
        # inside a quoted JSON value would make the printed example invalid
        # when extracted. This changes no frozen field, enum or validator.
        for example in examples:
            example["observations"][4]["finding"] = "ILLUSTRATIVE ONLY - replace with chart evidence"
        successor = value["version"] == "2.0"
        subject_answer = dict(subject_reference=subject["subject_reference"],
                              canonical_instrument=subject["canonical_instrument"], responses=examples)
        if not successor:
            subject_answer["observed_chart_instrument"] = "<READ FROM CHART>"
        envelope["subjects"].append(subject_answer)
        first = requests[0]
        image = Image(BytesIO(first.original_image))
        scale = min((A4[0]-2*PAGE_MARGIN-12)/image.imageWidth, (A4[1]-2*PAGE_MARGIN-150)/image.imageHeight)
        image.drawWidth, image.drawHeight = image.imageWidth*scale, image.imageHeight*scale
        story.extend([PageBreak(), Paragraph(escape(subject["canonical_instrument"]), styles["Heading1"]),
            Paragraph("Native direction: " + escape(first.requirement.thesis.direction.value)
                + ". Orientation only; do not select or change direction. Answer only from the supplied chart. "
                "Do not transcribe or infer machine CP, BC, TC or governed reference numerical values.", styles["BodyText"]),
            contract_block(json.dumps({key: subject[key] for key in
                ("subject_reference", "canonical_instrument", "chart_revision_sha256")}, indent=2)), image])
        for request in requests:
            story.append(Paragraph("TIMEFRAME " + request.timeframe.value, styles["Heading2"]))
            for index, (question, routing) in enumerate(request.routing, 1):
                semantics = VISUAL_QUESTION_SEMANTICS_V3_SUCCESSOR if successor else VISUAL_QUESTION_SEMANTICS_V3
                story.append(Paragraph(escape(f"Q{index} [{routing.value}] {semantics[question]}"), styles["BodyText"]))
    story.extend([PageBreak(), Paragraph("Exact Answer contract", styles["Title"]),
        Paragraph("Return exactly one governed block. Every printed key is required; extra fields and duplicate JSON keys fail. "
            "Echo request_reference and subject_reference exactly. All examples are illustrative, not chart evidence. "
            "Replace findings with independent observations for each timeframe. Never return run, assessment, "
            "request timestamp, machine hashes or other KRONOS-owned provenance. Q1-Q9 require why_not_covered_elsewhere null; "
            "Q10 finding NONE requires null, otherwise a bounded nonempty explanation. Preserve exact canonical punctuation.", styles["BodyText"]),
        Paragraph("Versioned observation fields and rules follow. These describe each response, not a second "
            "outer Answer envelope. Use only the successor envelope printed below.", styles["BodyText"]),
        contract_block(json.dumps({key: item for key, item in visual_evidence_v3_answer_contract(value["question_set_version"]).items()
            if key not in {"schema", "authority"}}, indent=2)),
        contract_block(BEGIN_GOVERNED_ANSWER_DATA + "\n" + json.dumps(envelope, indent=2) + "\n" + END_GOVERNED_ANSWER_DATA)])
    document.build(story)
    payload = out.getvalue()
    return NseReviewRequestMapping.create({**value, "review_pack_sha256": sha256(payload).hexdigest()}), payload


class VisualV3AnswerImportState(StrEnum):
    ANSWER_PACK_VERIFIED = "ANSWER_PACK_VERIFIED"
    ANSWER_PACK_REJECTED = "ANSWER_PACK_REJECTED"
    ANSWER_PACK_INCOMPLETE = "ANSWER_PACK_INCOMPLETE"
    ANSWER_IMPORT_FAILED = "ANSWER_IMPORT_FAILED"
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
                or item.question_set_version != self.question_set_version
                for item in self.candidate_packs
            )
            or tuple(item.canonical_instrument for item in self.candidate_packs)
            != tuple(sorted(item.canonical_instrument for item in self.candidate_packs))
            or self.scope not in {"ALL_ELIGIBLE", "INDIVIDUAL"}
            or (self.scope == "INDIVIDUAL" and (len(self.candidate_packs) != 1 or self.skipped))
            or any(len(item) != 2 or item[1] != "CHART REQUIRED" for item in self.skipped)
            or self.question_set_identity != VISUAL_QUESTION_SET_V3_ID
            or self.question_set_version not in {
                VISUAL_QUESTION_SET_V3_LEGACY_VERSION,
                VISUAL_QUESTION_SET_V3_VERSION,
                VISUAL_QUESTION_SET_V3_SUCCESSOR_VERSION,
            }
            or self.answer_schema != _answer_schema(self.question_set_version)
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

    _locks_guard = RLock()
    _cycle_locks: dict[Path, RLock] = {}

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("VISUAL_V3_PDF_STORE_INVALID")
        self.root = root
        # Component re-instantiation must not create another lock for the same
        # store in the threaded Browser process.
        with self._locks_guard:
            self.cycle_lock = self._cycle_locks.setdefault(root.resolve(), RLock())
        self._lock = self.cycle_lock

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
        """Observational selection only; pending publications are not repaired."""
        with self._lock:
            return self._load_current()

    def recover_pending_publications(self) -> VisualV3LiveReviewPack | None:
        """Explicit startup/mutation recovery; never a GET/read side effect."""
        with self._lock:
            self._recover_publication()
            return self._load_current()

    def _load_current(self) -> VisualV3LiveReviewPack | None:
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
        record = _pack_from_dict(payload.get("record"))
        if record.review_pack_id != selection.get("review_pack_id"):
            raise ValueError("VISUAL_V3_REVIEW_PACK_RESTORE_INVALID")
        from kronos.swing.v1.pdf_visual_review_v3_recovery import resolve_selected_artifact
        record = resolve_selected_artifact(self, record, selection)
        _verify_question_pdf(Path(record.question_path), record)
        return record

    def publish(self, record: VisualV3LiveReviewPack, temporary: Path) -> None:
        """Selection is the commit point; the pending intent permits rollback.

        Only this cycle's owned PDF/record may be removed on failure. Historical
        records and the previous selection are never rewritten by recovery.
        """
        with self._lock:
            self._recover_publication()
            _verify_question_pdf(temporary, record)
            final = Path(record.question_path)
            record_path = self.root / "review-packs" / f"{record.review_pack_id}.json"
            if final.exists() or record_path.exists():
                raise PdfReviewTransportError("REVIEW_PACK_PUBLICATION_CONFLICT")
            pending = self.root / "pending-publication.json"
            _atomic_json(pending, {
                "record": _primitive(record), "temporary": str(temporary),
            })
            try:
                # Same-filesystem, atomic, no-clobber publication; unlike
                # exists()+replace(), another PDF can never be overwritten.
                os.link(temporary, final)
                self.select_current(record)
            except Exception:
                self._recover_publication()
                raise
            self._recover_publication()

    def _recover_publication(self) -> None:
        pending = self.root / "pending-publication.json"
        if not pending.exists():
            return
        payload = _read(pending)
        record = _pack_from_dict(payload.get("record"))
        final = Path(record.question_path)
        temporary = Path(str(payload.get("temporary")))
        if (
            not final.is_absolute()
            or temporary.parent != final.parent
            or not temporary.name.startswith(f".{record.review_pack_id}.")
            or temporary.suffix != ".tmp"
        ):
            raise ValueError("VISUAL_V3_PUBLICATION_RECOVERY_INVALID")
        selection_path = self.root / "current-review-pack.json"
        selected = _read(selection_path) if selection_path.exists() else {}
        record_path = self.root / "review-packs" / f"{record.review_pack_id}.json"
        if selected.get("review_pack_id") == record.review_pack_id:
            # Commit succeeded even if the process stopped before cleanup.
            if _pack_from_dict(_read(record_path).get("record")) != record:
                raise ValueError("VISUAL_V3_PUBLICATION_RECOVERY_INVALID")
            _verify_question_pdf(final, record)
        else:
            if final.exists():
                _verify_question_pdf(final, record)
                final.unlink()
            if record_path.exists():
                if _pack_from_dict(_read(record_path).get("record")) != record:
                    raise ValueError("VISUAL_V3_PUBLICATION_RECOVERY_INVALID")
                record_path.unlink()
        temporary.unlink(missing_ok=True)
        pending.unlink()

    def replay(self, ordered, scope, skipped):  # type: ignore[no-untyped-def]
        """The same run/request-time/scope/population identifies an exact replay."""
        self._recover_publication()
        first = ordered[0][0]
        population = tuple(item[0].requirement.canonical_instrument for item in ordered)
        for path in sorted((self.root / "review-packs").glob("*.json")):
            record = _pack_from_dict(_read(path).get("record"))
            if (
                record.native_run_identity != first.requirement.native_run_identity
                or record.created_at != first.request_timestamp
                or record.scope != scope
                or tuple(item.canonical_instrument for item in record.candidate_packs) != population
            ):
                continue
            if record.skipped != skipped or record.observation_boundary != max(
                request.observation_boundary for requests in ordered for request in requests
            ) or any(
                pack.native_assessment_sha256 != requests[0].requirement.thesis.native_assessment_sha256
                or pack.chart_revisions != tuple((r.timeframe.value, r.chart_revision_sha256) for r in requests)
                or pack.machine_fact_bindings != tuple((r.timeframe.value, r.machine_fact.integrity_sha256) for r in requests)
                or pack.question_set_version != requests[0].question_set_version
                for pack, requests in zip(record.candidate_packs, ordered, strict=True)
            ):
                raise PdfReviewTransportError("REVIEW_PACK_REPLAY_CONFLICT")
            # Resolve an explicitly selected rendered successor before replay.
            # Canonical analytical bindings above still use the immutable pack.
            current = self._load_current()
            if current is not None and current.review_pack_id == record.review_pack_id:
                record = current
            _verify_question_pdf(Path(record.question_path), record)
            # An old replay must never silently re-select a superseded cycle.
            if current != record:
                raise PdfReviewTransportError("VISUAL_V3_REVIEW_PACK_SUPERSEDED")
            return record
        return None

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
        with self.record_store.cycle_lock:
            return self._generate(prepared, scope=scope, skipped=skipped)

    def _generate(self, prepared, *, scope, skipped):  # type: ignore[no-untyped-def]
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
        replay = self.record_store.replay(ordered, scope, skipped)
        if replay is not None:
            return replay
        review_pack_id = f"KRONOS-V3-REVIEW-{uuid4().hex.upper()}"
        base = f"KRONOS_V3_REVIEW_{stamp}_IST_{review_pack_id.removeprefix('KRONOS-V3-REVIEW-')}"
        question_filename = f"{base}_QUESTIONS.pdf"
        answer_filename = f"{base}_ANSWERS.pdf"
        question_path = self.configuration.question_directory / question_filename
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
            # Build before any final artifact/record is visible.
            output = BytesIO()
            writer.write(output)
        digest = sha256(output.getvalue()).hexdigest()
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
        with tempfile.NamedTemporaryFile(
            dir=question_path.parent, prefix=f".{review_pack_id}.", suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_output = Path(stream.name)
            try:
                stream.write(output.getvalue())
                stream.flush()
                os.fsync(stream.fileno())
                self.record_store.publish(record, temporary_output)
            finally:
                temporary_output.unlink(missing_ok=True)
        return record

    def find_and_validate_answer(
        self,
        record: VisualV3LiveReviewPack,
        requests: tuple[tuple[VisualEvidenceV3Request, ...], ...],
    ) -> ValidatedVisualV3Answer:
        self.configuration.ensure_directories()
        expected = self.configuration.answer_directory / record.expected_answer_filename
        matches: list[tuple[Path, dict[str, object]]] = []
        foreign = False
        extraction_error: PdfReviewTransportError | None = None
        for path in sorted(self.configuration.answer_directory.glob("*.pdf")):
            try:
                payload = _extract_governed_payload(path)
            except PdfReviewTransportError as error:
                if path == expected:
                    raise
                extraction_error = error
                continue
            manifest = payload.get("manifest")
            if type(manifest) is dict and manifest.get("review_pack_id") == record.review_pack_id:
                matches.append((path, payload))
            else:
                foreign = True
                if path == expected:
                    raise PdfReviewTransportError("REVIEW_PACK_ID_MISMATCH")
        if not matches:
            if foreign:
                raise PdfReviewTransportError("REVIEW_PACK_ID_MISMATCH")
            if extraction_error is not None:
                raise extraction_error
            raise PdfReviewTransportError("ANSWER_PACK_NOT_FOUND")
        if len(matches) != 1:
            raise PdfReviewTransportError("AMBIGUOUS_ANSWER_PACK")
        path, payload = matches[0]
        if path.name != record.expected_answer_filename:
            raise PdfReviewTransportError("ANSWER_FILENAME_MISMATCH")
        digest = sha256(path.read_bytes()).hexdigest()
        consumed = tuple(
            item for item in self.record_store.load_imports(record.review_pack_id)
            if item.consumed
        )
        if any(item.answer_pdf_sha256 != digest for item in consumed):
            raise PdfReviewTransportError("ANSWER_REPLAY_CONFLICT")
        if consumed:
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
        for existing in self.record_store.load_imports(record.review_pack_id):
            if existing.consumed:
                if (
                    existing.answer_pdf_sha256 != answer.answer_sha256
                    or existing.evidence_import_identity != identity
                ):
                    raise PdfReviewTransportError("ANSWER_REPLAY_CONFLICT")
                return existing
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

    def record_import_failure(
        self,
        record: VisualV3LiveReviewPack,
        answer: ValidatedVisualV3Answer,
        reason: str,
    ) -> VisualV3AnswerImportRecord:
        safe_reason = (
            reason
            if reason in {
                "COMPLETED_1H_EXTENSION_FACT_INVALID",
                "POST_VALIDATION_PROCESSING_FAILED",
            }
            else "POST_VALIDATION_PROCESSING_FAILED"
        )
        value = VisualV3AnswerImportRecord(
            record.review_pack_id,
            answer.answer_path.name,
            str(answer.answer_path),
            answer.answer_sha256,
            self._now(),
            VisualV3AnswerImportState.ANSWER_IMPORT_FAILED,
            (safe_reason,),
            False,
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
    if payload.get("schema") != record.answer_schema:
        raise PdfReviewTransportError("ANSWER_VERSION_MISMATCH")
    manifest = payload.get("manifest")
    if type(manifest) is not dict:
        raise PdfReviewTransportError("ANSWER_FORMAT_INVALID")
    if manifest.get("review_pack_id") != record.review_pack_id:
        raise PdfReviewTransportError("REVIEW_PACK_ID_MISMATCH")
    for key, expected in (
        ("native_run_identity", record.native_run_identity),
        ("question_set_identity", VISUAL_QUESTION_SET_V3_ID),
        ("question_set_version", record.question_set_version),
        ("answer_schema", record.answer_schema),
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
                or raw_response.get("question_set_version") != record.question_set_version
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
                "request_timestamp": request.request_timestamp.isoformat(),
                "native_run_identity": record.native_run_identity,
                "native_assessment_sha256": request.requirement.thesis.native_assessment_sha256,
                "native_canonical_instrument": instrument,
                "observation_boundary": request.observation_boundary.isoformat(),
                "analysis_boundary": request.analysis_boundary.isoformat(),
                "machine_fact_integrity_sha256": request.machine_fact.integrity_sha256,
                "source_provenance": (record.transport_identity, record.review_pack_id),
                "schema": _evidence_schema(record.question_set_version),
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


def _verify_question_pdf(path: Path, record: VisualV3LiveReviewPack) -> None:
    try:
        payload = path.read_bytes()
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(payload)).pages)
    except Exception:
        raise PdfReviewTransportError("VISUAL_V3_REVIEW_PDF_BINDING_INVALID") from None
    if (
        sha256(payload).hexdigest() != record.question_pdf_sha256
        or set(re.findall(r"KRONOS-V3-REVIEW-[A-F0-9]{32}", text)) != {record.review_pack_id}
        or set(re.findall(r"SWING-RUN-[A-F0-9]{32}", text)) != {record.native_run_identity}
    ):
        raise PdfReviewTransportError("VISUAL_V3_REVIEW_PDF_BINDING_INVALID")


def _write_answer_contract(
    path: Path,
    review_pack_id: str,
    prepared: tuple[tuple[VisualEvidenceV3Request, ...], ...],
    expected_answer_filename: str,
) -> None:
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 9
    styles["BodyText"].leading = 12
    styles["BodyText"].spaceAfter = PARAGRAPH_SPACING
    first = prepared[0][0]
    population = [
        {
            "canonical_instrument": item[0].requirement.canonical_instrument,
            "chart_revision_sha256": item[0].chart_revision_sha256,
        }
        for item in prepared
    ]
    envelope = {
        "schema": _answer_schema(first.question_set_version),
        "manifest": {
            "review_pack_id": review_pack_id,
            "native_run_identity": first.requirement.native_run_identity,
            "question_set_identity": VISUAL_QUESTION_SET_V3_ID,
            "question_set_version": first.question_set_version,
            "answer_schema": _answer_schema(first.question_set_version),
            "candidate_population": population,
        },
        "candidates": [{
            "canonical_instrument": population[0]["canonical_instrument"],
            "observed_chart_instrument": "<READ EXACTLY FROM CHART>",
            "chart_revision_sha256": population[0]["chart_revision_sha256"],
            "responses": "EXACTLY FOUR: 1W, 1D, 4H, 1H; USE THE COMPLETE RESPONSE CONTRACT BELOW",
        }],
    }
    contract = visual_evidence_v3_answer_contract()
    response_example = _complete_response_example(first)
    document = SimpleDocTemplate(
        BytesIO(), pagesize=A4, leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN, bottomMargin=PAGE_MARGIN, invariant=1,
    )
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
        Spacer(1, 8),
        Paragraph("Required Answer Envelope", styles["Heading2"]),
        contract_block(
            BEGIN_GOVERNED_ANSWER_DATA + "\n"
            + json.dumps(envelope, indent=2)
            + "\n" + END_GOVERNED_ANSWER_DATA,
        ),
        Spacer(1, 8),
        Paragraph("Exact V3 Observation Contract", styles["Heading2"]),
        Paragraph(
            "Use every Q1-Q10 question_id exactly once and in the published "
            "order. Qualitative visual results belong in finding. Do not use "
            "the legacy field named observation. Every observation also requires "
            "timeframe, observation_status, visible_basis, confidence_in_extraction, "
            "ambiguity_reason, source_chart_identity, and source_chart_revision. "
            "For Q1-Q9, why_not_covered_elsewhere is null.",
            styles["BodyText"],
        ),
        contract_block(json.dumps(contract, indent=2)),
        Spacer(1, 8),
        Paragraph("Negative and unavailable evidence", styles["Heading2"]),
        Paragraph(
            "Do not manufacture evidence to complete the schema. Use only the "
            "governed status and structured enums printed above. NONE, "
            "NOT_OBSERVABLE, NOT_IDENTIFIABLE, NOT_APPLICABLE, and PARTIAL are "
            "legitimate where the printed contract permits them. PARTIAL, "
            "UNAVAILABLE, or INVALID requires a non-empty ambiguity_reason.",
            styles["BodyText"],
        ),
        Paragraph("Q3 and Q6 level rule", styles["Heading2"]),
        Paragraph(
            "A Q3 or Q6 finding may be qualitative, including NONE, with no "
            "point or zone. If an exact visible level is reported, provide either "
            "one non-negative float point_price or one complete non-negative float "
            "zone_low/zone_high pair, never both. Do not force numerical extraction.",
            styles["BodyText"],
        ),
        Paragraph("Q10 rule", styles["Heading2"]),
        Paragraph(
            "When Q10 finding is NONE, why_not_covered_elsewhere must be null. "
            "For any non-NONE Q10 finding, provide a bounded non-empty "
            "why_not_covered_elsewhere. For Q1-Q9 it must be null.",
            styles["BodyText"],
        ),
        Paragraph("Machine and visual authority", styles["Heading2"]),
        Paragraph(
            "KRONOS owns deterministic numerical facts and binds Provider, request "
            "timestamp, run, assessment, boundary, machine-fact, provenance, schema, "
            "and authority fields after validation. The Chart Analyst must not "
            "provide, convert, round, or independently generate request_timestamp, "
            "and must not provide or infer "
            "machine CP, BC, TC, numerical governed reference levels, or machine-fact "
            "hashes. Q4 uses governed reference context, never generic PDH/PDL. Q9 "
            "uses component identities and never a numerical Confluence Zone, score, "
            "or threshold.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
        Paragraph(
            "Complete validator-compliant V3 response example - illustrative only",
            styles["Heading2"],
        ),
        Paragraph(
            "Replace every illustrative finding and visible basis with independent "
            "evidence from the applicable chart. Repeat this response shape for all "
            "four timeframes of every candidate.",
            styles["BodyText"],
        ),
        contract_block(json.dumps(response_example, indent=2)),
    ]
    document.build(story)
    path.write_bytes(buffer.getvalue())


def _complete_response_example(
    request: VisualEvidenceV3Request,
) -> dict[str, object]:
    """Return one raw Answer response that the governed importer accepts."""

    def common(
        question_id: str,
        *,
        status: str = "OBSERVED",
        ambiguity_reason: str = "",
    ) -> dict[str, object]:
        return {
            "question_id": question_id,
            "timeframe": request.timeframe.value,
            "observation_status": status,
            "visible_basis": "ILLUSTRATIVE ONLY - REPLACE WITH VISIBLE CHART BASIS",
            "confidence_in_extraction": "ILLUSTRATIVE",
            "ambiguity_reason": ambiguity_reason,
            "source_chart_identity": request.chart_identity,
            "source_chart_revision": request.chart_revision_sha256,
            "why_not_covered_elsewhere": None,
        }

    successor = request.question_set_version == VISUAL_QUESTION_SET_V3_SUCCESSOR_VERSION
    questions = iter(FROZEN_VISUAL_QUESTION_SET_V3_SUCCESSOR if successor else FROZEN_VISUAL_QUESTION_SET_V3)
    observations = []

    item = common(next(questions).value)
    item["finding"] = "ILLUSTRATIVE VISIBLE CHART VALIDATION"
    if successor:
        item.update(observed_instrument="<READ VISIBLE INSTRUMENT>", observed_market="<READ VISIBLE MARKET>",
                    observed_timeframe="<READ VISIBLE TIMEFRAME>", readability="READABLE",
                    identity_correspondence="MATCHED")
    observations.append(item)

    item = common(next(questions).value)
    item.update({
        "presence": "PRESENT",
        "price_relationship": "ABOVE",
        "interaction": "HOLD",
    })
    observations.append(item)

    item = common(next(questions).value)
    item["finding"] = "NONE"
    if successor:
        item.update(point_price=None, zone_low=None, zone_high=None)
    observations.append(item)

    item = common(next(questions).value)
    item.update({
        "presence": "PRESENT",
        "relationship": "INTERACTING_WITH_REFERENCE_HIGH",
        "interaction": "REJECTION",
    })
    observations.append(item)

    item = common(next(questions).value)
    item.update({
        "setup_quality": VisualSetupQuality.HEALTHY_CONSOLIDATION.value,
        "finding": (
            "ILLUSTRATIVE ONLY - orderly sideways pause with the supplied "
            "Native direction visibly intact"
        ),
    })
    observations.append(item)

    item = common(next(questions).value)
    item["finding"] = "ILLUSTRATIVE QUALITATIVE OBSTACLE DESCRIPTION"
    observations.append(item)

    item = common(next(questions).value)
    item["finding"] = "ILLUSTRATIVE VISIBLE MATURITY DESCRIPTION"
    observations.append(item)

    item = common(next(questions).value, status="NOT_VISIBLE" if successor else "NOT_APPLICABLE")
    item["finding"] = "NONE"
    observations.append(item)

    item = common(next(questions).value)
    item.update({
        "clustering": "CLUSTERED",
        "components": ["CPR", "SMA20"],
    })
    observations.append(item)

    item = common(next(questions).value)
    item["finding"] = "NONE"
    observations.append(item)

    return {
        "model_identity": "ILLUSTRATIVE_CHART_ANALYST",
        "timeframe": request.timeframe.value,
        "chart_identity": request.chart_identity,
        "chart_revision_sha256": request.chart_revision_sha256,
        "observations": observations,
        "question_set_identity": VISUAL_QUESTION_SET_V3_ID,
        "question_set_version": request.question_set_version,
    }


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


def _answer_schema(question_set_version: str) -> str:
    if question_set_version == VISUAL_QUESTION_SET_V3_LEGACY_VERSION:
        return VISUAL_EVIDENCE_V3_LEGACY_ANSWER_SCHEMA
    if question_set_version == VISUAL_QUESTION_SET_V3_VERSION:
        return VISUAL_EVIDENCE_V3_ANSWER_SCHEMA
    if question_set_version == VISUAL_QUESTION_SET_V3_SUCCESSOR_VERSION:
        return VISUAL_EVIDENCE_V3_SUCCESSOR_ANSWER_SCHEMA
    raise ValueError("VISUAL_V3_ANSWER_VERSION_UNSUPPORTED")


def _evidence_schema(question_set_version: str) -> str:
    if question_set_version == VISUAL_QUESTION_SET_V3_LEGACY_VERSION:
        return VISUAL_EVIDENCE_V3_LEGACY_SCHEMA
    if question_set_version == VISUAL_QUESTION_SET_V3_VERSION:
        return VISUAL_EVIDENCE_V3_SCHEMA
    if question_set_version == VISUAL_QUESTION_SET_V3_SUCCESSOR_VERSION:
        return VISUAL_EVIDENCE_V3_SUCCESSOR_SCHEMA
    raise ValueError("VISUAL_V3_EVIDENCE_VERSION_UNSUPPORTED")


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
