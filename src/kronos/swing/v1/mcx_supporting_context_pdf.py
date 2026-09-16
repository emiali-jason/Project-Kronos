"""Sponsor-mediated PDF transport for MCX-CONTEXT-01."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable
from uuid import uuid4

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer

from kronos.configuration.pdf_visual_review import PdfVisualReviewConfiguration
from kronos.swing.v1.mcx_supporting_context import (
    AlignmentState,
    DirectionState,
    ENERGY_PANELS,
    EvidenceQuality,
    MCX_CONTEXT_ANSWER_SCHEMA,
    MCX_CONTEXT_AUTHORITY,
    MCX_CONTEXT_QUESTION_SCHEMA,
    METALS_PANELS,
    McxContextFamily,
    McxContextPanelObservation,
    McxContextPanelValidationFailure,
    McxContextSlot,
    PanelValidation,
    StructuralCondition,
    panel_validation_failure,
    panels_for,
)
from kronos.swing.v1.pdf_visual_review import (
    BEGIN_GOVERNED_ANSWER_DATA,
    END_GOVERNED_ANSWER_DATA,
    PdfReviewTransportError,
    _extract_governed_payload,
)


MCX_CONTEXT_TRANSPORT_ID = "KRONOS-SWING-MCX-CONTEXT-PDF-TRANSPORT-V1"
MCX_CONTEXT_TRANSPORT_VERSION = "1.0"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class McxContextPanelValidationError(PdfReviewTransportError):
    """Fail-closed panel rejection with bounded Sponsor-safe context."""

    def __init__(self, failure: McxContextPanelValidationFailure) -> None:
        if type(failure) is not McxContextPanelValidationFailure:
            raise TypeError("MCX_CONTEXT_PANEL_DIAGNOSTIC_REQUIRED")
        super().__init__(failure.machine_code)
        self.failure = failure


@dataclass(frozen=True, slots=True)
class McxContextStagedImage:
    trading_date: date
    slot: McxContextSlot
    family: McxContextFamily
    content_type: str
    image_sha256: str
    staged_at: datetime
    path: str

    def __post_init__(self) -> None:
        if (
            type(self.trading_date) is not date
            or type(self.slot) is not McxContextSlot
            or type(self.family) is not McxContextFamily
            or self.content_type not in {"image/png", "image/jpeg"}
            or _DIGEST.fullmatch(self.image_sha256) is None
            or not _aware(self.staged_at)
            or not Path(self.path).is_absolute()
        ):
            raise ValueError("MCX_CONTEXT_STAGED_IMAGE_INVALID")


@dataclass(frozen=True, slots=True)
class McxContextQuestionPack:
    question_pack_identity: str
    trading_date: date
    slot: McxContextSlot
    created_at: datetime
    question_filename: str
    question_path: str
    expected_answer_filename: str
    question_pdf_sha256: str
    images: tuple[McxContextStagedImage, McxContextStagedImage]
    question_schema: str = MCX_CONTEXT_QUESTION_SCHEMA
    answer_schema: str = MCX_CONTEXT_ANSWER_SCHEMA
    authority: str = MCX_CONTEXT_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not self.question_pack_identity.startswith("MCX-CONTEXT-PACK-")
            or type(self.trading_date) is not date
            or type(self.slot) is not McxContextSlot
            or not _aware(self.created_at)
            or not self.question_filename.endswith("_QUESTIONS.pdf")
            or Path(self.question_path).name != self.question_filename
            or not self.expected_answer_filename.endswith("_ANSWERS.pdf")
            or _DIGEST.fullmatch(self.question_pdf_sha256) is None
            or tuple(item.family for item in self.images)
            != (McxContextFamily.METALS, McxContextFamily.ENERGY)
            or any(item.trading_date != self.trading_date or item.slot is not self.slot for item in self.images)
            or self.question_schema != MCX_CONTEXT_QUESTION_SCHEMA
            or self.answer_schema != MCX_CONTEXT_ANSWER_SCHEMA
            or self.authority != MCX_CONTEXT_AUTHORITY
        ):
            raise ValueError("MCX_CONTEXT_QUESTION_PACK_INVALID")


@dataclass(frozen=True, slots=True)
class McxContextValidatedFamily:
    family: McxContextFamily
    panels: tuple[McxContextPanelObservation, ...]
    wti_brent_alignment: AlignmentState | None
    natural_gas_alignment: AlignmentState | None


@dataclass(frozen=True, slots=True)
class McxContextValidatedAnswer:
    answer_pack_identity: str
    answer_path: Path
    answer_sha256: str
    captured_at: datetime
    families: tuple[McxContextValidatedFamily, McxContextValidatedFamily]


@dataclass(frozen=True, slots=True)
class McxContextCapturedAnswer:
    """One immutable capture; parsing and retention use these same bytes."""

    answer: McxContextValidatedAnswer
    pdf_bytes: bytes


class McxContextPdfStore:
    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("MCX_CONTEXT_PDF_STORE_INVALID")
        self.root = root

    def retain_pack(self, value: McxContextQuestionPack) -> None:
        path = self.root / "question-packs" / f"{value.question_pack_identity}.json"
        _retain(path, _primitive(value))
        current = self.root / "current" / value.trading_date.isoformat() / f"{value.slot.value}.json"
        _replace(current, {"question_pack_identity": value.question_pack_identity})

    def current(self, trading_date: date, slot: McxContextSlot) -> McxContextQuestionPack | None:
        path = self.root / "current" / trading_date.isoformat() / f"{slot.value}.json"
        if not path.exists():
            from kronos.swing.v1.review_evidence_store import record_prepared_read
            record_prepared_read(path, None)
            return None
        selection = _read(path)
        identity = selection.get("question_pack_identity")
        if type(identity) is not str: raise ValueError("MCX_CONTEXT_SELECTION_INVALID")
        return _pack_from_dict(_read(self.root / "question-packs" / f"{identity}.json"))

    def load_exact(self, identity: str) -> McxContextQuestionPack:
        """Exact retained authority, with no current/latest fallback."""
        if type(identity) is not str or re.fullmatch(r"MCX-CONTEXT-PACK-[A-F0-9]{32}", identity) is None:
            raise ValueError("MCX_CONTEXT_SELECTION_INVALID")
        path = self.root / "question-packs" / f"{identity}.json"
        if path.is_symlink():
            raise ValueError("MCX_CONTEXT_SELECTION_INVALID")
        pack = _pack_from_dict(_read(path))
        if pack.question_pack_identity != identity:
            raise ValueError("MCX_CONTEXT_SELECTION_INVALID")
        return pack

    def retain_image(self, value: McxContextStagedImage, payload: bytes) -> None:
        suffix = ".png" if value.content_type == "image/png" else ".jpg"
        path = Path(value.path)
        if path.suffix != suffix or sha256(payload).hexdigest() != value.image_sha256:
            raise ValueError("MCX_CONTEXT_IMAGE_BINDING_INVALID")
        if path.exists():
            if path.read_bytes() != payload: raise ValueError("MCX_CONTEXT_IMAGE_IMMUTABLE")
            return
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _atomic_bytes(path, payload)

    def current_image(
        self, trading_date: date, slot: McxContextSlot, family: McxContextFamily,
    ) -> McxContextStagedImage | None:
        path = self.root / "staged-current" / trading_date.isoformat() / slot.value / f"{family.value}.json"
        if not path.exists():
            from kronos.swing.v1.review_evidence_store import record_prepared_read
            record_prepared_read(path, None)
            return None
        return _image_from_dict(_read(path))

    def select_image(self, value: McxContextStagedImage) -> None:
        path = self.root / "staged-current" / value.trading_date.isoformat() / value.slot.value / f"{value.family.value}.json"
        _replace(path, _primitive(value))

    def remove_current_image(
        self, trading_date: date, slot: McxContextSlot, family: McxContextFamily,
    ) -> None:
        path = self.root / "staged-current" / trading_date.isoformat() / slot.value / f"{family.value}.json"
        try:
            path.unlink()
        except FileNotFoundError:
            return

    def image_bytes(self, value: McxContextStagedImage) -> bytes:
        path = Path(value.path)
        image_root = (self.root / "images").resolve()
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(image_root)
        except (FileNotFoundError, ValueError):
            raise ValueError("MCX_CONTEXT_IMAGE_BINDING_INVALID") from None
        payload = resolved.read_bytes()
        from kronos.swing.v1.review_evidence_store import record_prepared_read
        record_prepared_read(resolved, payload)
        if sha256(payload).hexdigest() != value.image_sha256:
            raise ValueError("MCX_CONTEXT_IMAGE_BINDING_INVALID")
        return payload


class McxContextPdfTransport:
    def __init__(
        self, configuration: PdfVisualReviewConfiguration, store: McxContextPdfStore,
        *, clock: Callable[[], datetime],
    ) -> None:
        self.configuration = configuration; self.store = store; self._clock = clock

    def stage_image(
        self, *, trading_date: date, slot: McxContextSlot,
        family: McxContextFamily, content_type: str, payload: bytes,
    ) -> McxContextStagedImage:
        if not 0 < len(payload) <= 25 * 1024 * 1024:
            raise PdfReviewTransportError("MCX_CONTEXT_IMAGE_SIZE_INVALID")
        normalized = content_type.split(";", 1)[0].lower()
        if not _valid_image(normalized, payload):
            raise PdfReviewTransportError("MCX_CONTEXT_IMAGE_FORMAT_INVALID")
        digest = sha256(payload).hexdigest(); suffix = ".png" if normalized == "image/png" else ".jpg"
        path = self.store.root / "images" / trading_date.isoformat() / slot.value / family.value / f"{digest}{suffix}"
        value = McxContextStagedImage(trading_date, slot, family, normalized, digest, self._now(), str(path))
        self.store.retain_image(value, payload); self.store.select_image(value)
        return value

    def prepare_intake_publication(self, trading_date, slot, operation, **values):
        """Build the existing record bytes outside both publication guards."""
        def encoded(value):
            return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")

        if operation == "GENERATE":
            if values:
                raise ValueError("REVIEW_PRECONDITION_INVALID")
            record, raw = self.prepare_question_pack(trading_date, slot)
            pdf_path = Path(record.question_path)
            if pdf_path.exists():
                raise PdfReviewTransportError("MCX_CONTEXT_QUESTION_FILENAME_EXISTS")
            writes = ((pdf_path, raw, False),
                (self.store.root / "question-packs" / (record.question_pack_identity + ".json"), encoded(_primitive(record)), False),
                (self.store.root / "current" / trading_date.isoformat() / (slot.value + ".json"),
                 encoded({"question_pack_identity": record.question_pack_identity}), True))
            return record, writes, None, (self.configuration.question_directory, self.configuration.answer_directory)
        family = values.get("family")
        if not isinstance(family, McxContextFamily):
            raise ValueError("REVIEW_PRECONDITION_INVALID")
        pointer = self.store.root / "staged-current" / trading_date.isoformat() / slot.value / (family.value + ".json")
        if operation == "REMOVE":
            if set(values) != {"family"}:
                raise ValueError("REVIEW_PRECONDITION_INVALID")
            return None, (), pointer, ()
        if operation != "STAGE" or set(values) != {"family", "content_type", "payload"}:
            raise ValueError("REVIEW_PRECONDITION_INVALID")
        payload = values["payload"]
        if type(payload) is not bytes or not 0 < len(payload) <= 25 * 1024 * 1024:
            raise PdfReviewTransportError("MCX_CONTEXT_IMAGE_SIZE_INVALID")
        normalized = values["content_type"].split(";", 1)[0].lower()
        if not _valid_image(normalized, payload):
            raise PdfReviewTransportError("MCX_CONTEXT_IMAGE_FORMAT_INVALID")
        digest = sha256(payload).hexdigest()
        path = self.store.root / "images" / trading_date.isoformat() / slot.value / family.value / (
            digest + (".png" if normalized == "image/png" else ".jpg"))
        record = McxContextStagedImage(trading_date, slot, family, normalized, digest, self._now(), str(path))
        return record, ((path, payload, False), (pointer, encoded(_primitive(record)), True)), None, ()

    def commit_intake_publication(self, prepared):
        """Only prepared bytes/existence checks; the final write is the control."""
        result, writes, removal, directories = prepared
        # Check every immutable destination before retaining any prepared bytes.
        for path, raw, replace in writes:
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
                raise ValueError("REVIEW_ARTIFACT_REFERENCE_INVALID")
            if not replace and path.exists() and path.read_bytes() != raw:
                raise ValueError("REVIEW_PUBLICATION_CONFLICT")
        for directory in directories:
            if directory.is_symlink() or any(parent.is_symlink() for parent in directory.parents) or (
                    directory.exists() and not directory.is_dir()):
                raise ValueError("PDF_VISUAL_REVIEW_DIRECTORY_INVALID")
        # Preserve the existing CREATE PDF provisioning of both governed output
        # directories, after admission, without invoking configuration parsing.
        for directory in directories:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
        for path, raw, replace in writes:
            if not replace and path.exists():
                continue
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _atomic_bytes(path, raw)
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        if removal is not None:
            removal.unlink(missing_ok=True)
            if removal.parent.exists():
                descriptor = os.open(removal.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        return result

    def remove_image(
        self, *, trading_date: date, slot: McxContextSlot, family: McxContextFamily,
    ) -> None:
        self.store.remove_current_image(trading_date, slot, family)

    def current_image_payload(
        self, *, trading_date: date, slot: McxContextSlot,
        family: McxContextFamily, image_sha256: str,
    ) -> tuple[McxContextStagedImage, bytes]:
        value = self.store.current_image(trading_date, slot, family)
        if value is None or value.image_sha256 != image_sha256:
            raise ValueError("MCX_CONTEXT_IMAGE_BINDING_INVALID")
        return value, self.store.image_bytes(value)

    def generate(self, trading_date: date, slot: McxContextSlot) -> McxContextQuestionPack:
        self.configuration.ensure_directories()
        images = tuple(self.store.current_image(trading_date, slot, family) for family in McxContextFamily)
        if any(item is None for item in images):
            raise PdfReviewTransportError("MCX_CONTEXT_IMAGES_INCOMPLETE")
        bound = (images[0], images[1])
        if not all(isinstance(item, McxContextStagedImage) for item in bound):
            raise PdfReviewTransportError("MCX_CONTEXT_IMAGES_INCOMPLETE")
        now = self._now(); identity = "MCX-CONTEXT-PACK-" + uuid4().hex.upper()
        base = (
            f"MCX_CONTEXT_{trading_date.strftime('%Y%m%d')}_{slot.value}_V1_"
            f"{identity.removeprefix('MCX-CONTEXT-PACK-')[:12]}"
        )
        question = f"{base}_QUESTIONS.pdf"; answer = f"{base}_ANSWERS.pdf"
        path = self.configuration.question_directory / question
        if path.exists():
            raise PdfReviewTransportError("MCX_CONTEXT_QUESTION_FILENAME_EXISTS")
        manifest = _answer_template(identity, trading_date, slot, answer)
        _write_question_pdf(path, identity, trading_date, slot, bound, manifest)
        value = McxContextQuestionPack(
            identity, trading_date, slot, now, question, str(path), answer,
            sha256(path.read_bytes()).hexdigest(), bound,  # type: ignore[arg-type]
        )
        self.store.retain_pack(value); return value

    def prepare_question_pack(self, trading_date: date, slot: McxContextSlot):
        """Prepare without publishing a PDF, request record or selection."""
        images = tuple(self.store.current_image(trading_date, slot, family) for family in McxContextFamily)
        if any(item is None for item in images):
            raise PdfReviewTransportError("MCX_CONTEXT_IMAGES_INCOMPLETE")
        for image in images:
            self.store.image_bytes(image)
        identity = "MCX-CONTEXT-PACK-" + uuid4().hex.upper()
        base = f"MCX_CONTEXT_{trading_date.strftime('%Y%m%d')}_{slot.value}_V1_{identity.removeprefix('MCX-CONTEXT-PACK-')[:12]}"
        question, answer = base + "_QUESTIONS.pdf", base + "_ANSWERS.pdf"
        buffer = BytesIO()
        _write_question_pdf(buffer, identity, trading_date, slot, images,
                            _answer_template(identity, trading_date, slot, answer))
        raw = buffer.getvalue()
        return McxContextQuestionPack(identity, trading_date, slot, self._now(), question,
            str(self.configuration.question_directory / question), answer,
            sha256(raw).hexdigest(), images), raw

    def publish_prepared_question_pack(self, record: McxContextQuestionPack, raw: bytes):
        """Unguarded legacy helper; governed intake uses its prepared-byte plan."""
        if sha256(raw).hexdigest() != record.question_pdf_sha256:
            raise PdfReviewTransportError("MCX_CONTEXT_QUESTION_PACK_INVALID")
        for image in record.images:
            if self.store.current_image(record.trading_date, record.slot, image.family) != image:
                raise PdfReviewTransportError("REVIEW_BINDING_STALE")
            self.store.image_bytes(image)
        path = self.configuration.question_directory / record.question_filename
        if str(path) != record.question_path or path.exists():
            raise PdfReviewTransportError("MCX_CONTEXT_QUESTION_FILENAME_EXISTS")
        self.configuration.ensure_directories()
        _atomic_bytes(path, raw)
        self.store.retain_pack(record)
        return record

    def find_and_validate(self, record: McxContextQuestionPack) -> McxContextValidatedAnswer:
        self.configuration.ensure_directories(); matches = []
        for path in sorted(self.configuration.answer_directory.glob("*_ANSWERS.pdf")):
            try: payload = _extract_governed_payload(path)
            except PdfReviewTransportError: continue
            manifest = payload.get("manifest")
            if type(manifest) is dict and manifest.get("question_pack_identity") == record.question_pack_identity:
                matches.append((path, payload))
        if not matches: raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_NOT_FOUND")
        if len(matches) != 1: raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_AMBIGUOUS")
        path, payload = matches[0]
        if path.name != record.expected_answer_filename:
            raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_FILENAME_MISMATCH")
        return _validate_answer(record, path, payload)

    def capture_and_validate(self, record: McxContextQuestionPack) -> McxContextCapturedAnswer:
        """Successor intake: exact governed filename, no latest-file selection.

        This does not create directories, publish evidence or reopen the Answer
        after validation. Historical find_and_validate remains unchanged.
        """
        from kronos.swing.v1.pdf_visual_review_v3_live import extract_successor_answer_pdf
        from kronos.swing.v1.review_evidence_binding import strict_json

        name = record.expected_answer_filename
        if Path(name).name != name or not name.endswith("_ANSWERS.pdf"):
            raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_FILENAME_MISMATCH")
        path = self.configuration.answer_directory / name
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                raw = stream.read(128 * 1024 * 1024 + 1)
        except OSError as error:
            raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_NOT_FOUND") from error
        payload = strict_json(extract_successor_answer_pdf(raw))
        answer = _validate_answer(record, path, payload, pdf_bytes=raw)
        return McxContextCapturedAnswer(answer, raw)

    def _now(self) -> datetime:
        value = self._clock()
        if not _aware(value): raise PdfReviewTransportError("MCX_CONTEXT_CLOCK_INVALID")
        return value


def _validate_answer(record: McxContextQuestionPack, path: Path, payload: dict[str, object], *, pdf_bytes: bytes | None = None) -> McxContextValidatedAnswer:
    if type(payload) is not dict or set(payload) != {"schema", "manifest", "families"}:
        raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_FORMAT_INVALID")
    if payload["schema"] != MCX_CONTEXT_ANSWER_SCHEMA:
        raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_VERSION_MISMATCH")
    manifest = payload["manifest"]
    expected_manifest = {
        "question_pack_identity": record.question_pack_identity,
        "trading_date": record.trading_date.isoformat(), "slot": record.slot.value,
        "answer_schema": record.answer_schema,
    }
    if type(manifest) is not dict or set(manifest) != set(expected_manifest) | {"answer_pack_identity", "captured_at"}:
        raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_FORMAT_INVALID")
    if any(manifest.get(key) != value for key, value in expected_manifest.items()):
        raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_BINDING_MISMATCH")
    answer_identity = manifest.get("answer_pack_identity"); captured = manifest.get("captured_at")
    if type(answer_identity) is not str or not answer_identity or type(captured) is not str:
        raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_FORMAT_INVALID")
    try: captured_at = datetime.fromisoformat(captured)
    except ValueError as error: raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_FORMAT_INVALID") from error
    if not _aware(captured_at): raise PdfReviewTransportError("MCX_CONTEXT_ANSWER_FORMAT_INVALID")
    raw_families = payload["families"]
    if type(raw_families) is not list or len(raw_families) != 2:
        raise PdfReviewTransportError("MCX_CONTEXT_FAMILY_STRUCTURE_INVALID")
    families = []
    for family, raw in zip(McxContextFamily, raw_families, strict=True):
        if type(raw) is not dict:
            raise PdfReviewTransportError("MCX_CONTEXT_FAMILY_STRUCTURE_INVALID")
        required = {"family", "panels"} | ({"wti_brent_alignment", "natural_gas_alignment"} if family is McxContextFamily.ENERGY else set())
        if set(raw) != required or raw.get("family") != family.value:
            raise PdfReviewTransportError("MCX_CONTEXT_FAMILY_STRUCTURE_INVALID")
        source = raw.get("panels"); definitions = panels_for(family)
        if type(source) is not list or len(source) != len(definitions):
            raise PdfReviewTransportError("MCX_CONTEXT_PANEL_COUNT_INVALID")
        observations = []
        for definition, item in zip(definitions, source, strict=True):
            if type(item) is not dict or set(item) != {
                "panel_id", "observed_identity", "observed_timeframe", "validation",
                "direction", "evidence_quality", "structural_condition",
            }:
                raise PdfReviewTransportError("MCX_CONTEXT_PANEL_FORMAT_INVALID")
            try:
                observation = McxContextPanelObservation(
                    item["panel_id"], item["observed_identity"], item["observed_timeframe"],
                    PanelValidation(item["validation"]), DirectionState(item["direction"]),
                    EvidenceQuality(item["evidence_quality"]), StructuralCondition(item["structural_condition"]),
                )
            except (TypeError, ValueError) as error:
                raise PdfReviewTransportError("MCX_CONTEXT_PANEL_ENUM_INVALID") from error
            if observation.panel_id != definition.panel_id:
                raise PdfReviewTransportError("MCX_CONTEXT_PANEL_ORDER_INVALID")
            failure = panel_validation_failure(family, definition, observation)
            if failure is not None:
                raise McxContextPanelValidationError(failure)
            observations.append(observation)
        try:
            wti = AlignmentState(raw["wti_brent_alignment"]) if family is McxContextFamily.ENERGY else None
            gas = AlignmentState(raw["natural_gas_alignment"]) if family is McxContextFamily.ENERGY else None
        except ValueError as error:
            raise PdfReviewTransportError("MCX_CONTEXT_ALIGNMENT_INVALID") from error
        families.append(McxContextValidatedFamily(family, tuple(observations), wti, gas))
    captured_bytes = path.read_bytes() if pdf_bytes is None else pdf_bytes
    return McxContextValidatedAnswer(answer_identity, path, sha256(captured_bytes).hexdigest(), captured_at, tuple(families))  # type: ignore[arg-type]


def _write_question_pdf(path: Path | BytesIO, identity: str, trading_date: date, slot: McxContextSlot, images: tuple[McxContextStagedImage, McxContextStagedImage], template: dict[str, object]) -> None:
    if isinstance(path, Path):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    styles = getSampleStyleSheet(); story = [
        Paragraph("KRONOS MCX TWICE-DAILY SUPPORTING CONTEXT V1", styles["Title"]),
        Paragraph(f"{trading_date.isoformat()} · {slot.value} · {identity}", styles["Heading2"]),
        Paragraph("SUPPORTING EVIDENCE ONLY — NO ANALYTICAL / TRADE / EXECUTION AUTHORITY", styles["Heading3"]),
        Paragraph("Chart Analyst: inspect only the visible panels. Do not provide BUY/SELL, tailwind/headwind, scores, recommendations, RSI conclusions, KR-370, Step-31, Risk, timing, or broker consequences.", styles["BodyText"]),
    ]
    for image in images:
        story += [PageBreak(), Paragraph(f"{image.family.value} · FROZEN COMPOSITE", styles["Heading1"])]
        definitions = panels_for(image.family)
        story.append(Paragraph(
            "Required panel order: " + " · ".join(
                f"{item.panel_id} {item.expected_identity} {item.expected_timeframe}"
                for item in definitions
            ),
            styles["BodyText"],
        ))
        reader = ImageReader(image.path); width, height = reader.getSize(); available = A4[0] - 72
        scale = min(available / width, (A4[1] - 160) / height)
        story.append(Image(image.path, width=width * scale, height=height * scale))
        questions = (
            "Q1 panel validation; Q2 visible direction; Q3 evidence quality; "
            "Q4 visible structural condition"
            if image.family is McxContextFamily.METALS else
            "Q5 panel validation; Q6 visible direction; Q7 evidence quality; "
            "Q8 visible structural condition; Q9 WTI/Brent alignment; "
            "Q10 Natural Gas 1D/4H alignment"
        )
        story.append(Paragraph(
            "Answer governed " + questions
            + " using the exact enums, schema, and panel order in the Answer Contract.",
            styles["BodyText"],
        ))
    story += [PageBreak(), Paragraph("GOVERNED ANSWER CONTRACT", styles["Heading1"]),
              Paragraph("Return only the JSON document between the markers. No additional fields or prose.", styles["BodyText"]),
              Preformatted(BEGIN_GOVERNED_ANSWER_DATA + "\n" + json.dumps(template, indent=2) + "\n" + END_GOVERNED_ANSWER_DATA, styles["Code"])]
    if isinstance(path, BytesIO):
        SimpleDocTemplate(path, pagesize=A4).build(story)
    else:
        temporary = path.with_suffix(".tmp")
        SimpleDocTemplate(str(temporary), pagesize=A4).build(story)
        os.chmod(temporary, 0o600); os.replace(temporary, path)


def _answer_template(identity: str, trading_date: date, slot: McxContextSlot, _filename: str) -> dict[str, object]:
    def panel(definition: object) -> dict[str, object]:
        return {"panel_id": definition.panel_id, "observed_identity": "<READ EXACTLY FROM CHART>", "observed_timeframe": "<READ EXACTLY FROM CHART>", "validation": "MATCH|MISMATCH|UNREADABLE", "direction": "RISING|FALLING|RANGE|UNCLEAR", "evidence_quality": "CLEAR|PARTIAL|UNREADABLE", "structural_condition": "TRENDING|CONSOLIDATING|TRANSITIONING|UNCLEAR"}
    return {"schema": MCX_CONTEXT_ANSWER_SCHEMA, "manifest": {"question_pack_identity": identity, "trading_date": trading_date.isoformat(), "slot": slot.value, "answer_schema": MCX_CONTEXT_ANSWER_SCHEMA, "answer_pack_identity": "<CHART-ANALYST-ASSIGNED-IDENTITY>", "captured_at": "<ISO-8601 WITH TIMEZONE>"}, "families": [
        {"family": "METALS", "panels": [panel(item) for item in METALS_PANELS]},
        {"family": "ENERGY", "panels": [panel(item) for item in ENERGY_PANELS], "wti_brent_alignment": "ALIGNED|DIVERGENT|UNCLEAR", "natural_gas_alignment": "ALIGNED|DIVERGENT|UNCLEAR"},
    ]}


def _valid_image(content_type: str, payload: bytes) -> bool:
    return (content_type == "image/png" and payload.startswith(b"\x89PNG\r\n\x1a\n")) or (content_type == "image/jpeg" and payload.startswith(b"\xff\xd8") and payload.endswith(b"\xff\xd9"))


def _primitive(value: object) -> dict[str, object]:
    def convert(item: object) -> object:
        from enum import Enum
        if isinstance(item, Enum): return item.value
        if isinstance(item, (date, datetime)): return item.isoformat()
        if isinstance(item, tuple): return [convert(part) for part in item]
        if isinstance(item, dict): return {str(k): convert(v) for k, v in item.items()}
        return item
    return convert(asdict(value))  # type: ignore[return-value]


def _pack_from_dict(value: dict[str, object]) -> McxContextQuestionPack:
    try:
        images = tuple(_image_from_dict(item) for item in value["images"])
        return McxContextQuestionPack(value["question_pack_identity"], date.fromisoformat(value["trading_date"]), McxContextSlot(value["slot"]), datetime.fromisoformat(value["created_at"]), value["question_filename"], value["question_path"], value["expected_answer_filename"], value["question_pdf_sha256"], images, value["question_schema"], value["answer_schema"], value["authority"])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as error: raise ValueError("MCX_CONTEXT_QUESTION_PACK_RESTORE_INVALID") from error


def _image_from_dict(value: dict[str, object]) -> McxContextStagedImage:
    return McxContextStagedImage(date.fromisoformat(value["trading_date"]), McxContextSlot(value["slot"]), McxContextFamily(value["family"]), value["content_type"], value["image_sha256"], datetime.fromisoformat(value["staged_at"]), value["path"])  # type: ignore[arg-type]


def _read(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    from kronos.swing.v1.review_evidence_store import record_prepared_read
    record_prepared_read(path, raw)
    value = json.loads(raw.decode("utf-8"))
    if type(value) is not dict: raise ValueError("MCX_CONTEXT_PDF_RECORD_INVALID")
    return value


def _retain(path: Path, payload: object) -> None:
    if path.exists():
        if _read(path) != payload: raise ValueError("MCX_CONTEXT_PDF_RECORD_IMMUTABLE")
        return
    _atomic_json(path, payload)


def _replace(path: Path, payload: object) -> None: _atomic_json(path, payload, replace=True)


def _atomic_json(path: Path, payload: object, *, replace: bool = False) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
        name = stream.name; json.dump(payload, stream, indent=2, sort_keys=True); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    os.chmod(name, 0o600)
    if path.exists() and not replace: os.unlink(name); raise ValueError("MCX_CONTEXT_PDF_RECORD_IMMUTABLE")
    os.replace(name, path)


def _atomic_bytes(path: Path, payload: bytes) -> None:
    with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
        name = stream.name; stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    os.chmod(name, 0o600); os.replace(name, path)


def _aware(value: datetime) -> bool: return value.tzinfo is not None and value.utcoffset() is not None


__all__ = ["MCX_CONTEXT_TRANSPORT_ID", "MCX_CONTEXT_TRANSPORT_VERSION", "McxContextPdfStore", "McxContextPdfTransport", "McxContextQuestionPack", "McxContextStagedImage", "McxContextValidatedAnswer", "McxContextValidatedFamily"]
