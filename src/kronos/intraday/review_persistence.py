"""Append-only persistence for Intraday Review evidence and exact pointers."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from threading import RLock
from uuid import uuid4
from hashlib import sha256

from reportlab.lib.utils import ImageReader

from kronos.intraday.review import (
    ChartRevision,
    CurrentReviewPointer,
    ReviewCycle,
    ReviewError,
    ReviewFailure,
    ReviewHandoff,
    ReviewQuestionPack,
    artifact_bytes,
    artifact_from_bytes,
)
from kronos.intraday.review_batch import (
    ReviewBatchPdf,
    batch_artifact_bytes,
    batch_from_bytes,
)
from kronos.intraday.review_answer import (
    AnswerImportRecord,
    ChartAnalystAnswerPack,
    ImportedVisualEvidence,
    VisualEvidencePointer,
    answer_artifact_bytes,
    answer_artifact_from_bytes,
)


DEFAULT_INTRADAY_REVIEW_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "intraday-v1"
    / "review-v1"
)
MAX_CHART_BYTES = 25 * 1024 * 1024
_MEDIA = {
    "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": (".jpg", b"\xff\xd8\xff"),
}


class IntradayReviewStore:
    """Explicit-identity store; directory order and mtime have no authority."""

    def __init__(self, root: Path = DEFAULT_INTRADAY_REVIEW_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_REVIEW_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_handoff(self, value: ReviewHandoff) -> Path:
        return self._retain_typed("handoffs", value.handoff_identity, value)

    def retain_cycle(self, value: ReviewCycle) -> Path:
        return self._retain_typed("cycles", value.cycle_identity, value)

    def retain_chart(self, value: ChartRevision, payload: bytes) -> Path:
        if type(value) is not ChartRevision:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        validate_chart_payload(value.media_type, payload)
        if value.byte_count != len(payload):
            raise ReviewError(ReviewFailure.CHART_INVALID)
        suffix = _MEDIA[value.media_type][0]
        binary_path = self._path("chart-binaries", value.chart_artifact_identity, suffix)
        manifest_path = self._path("chart-revisions", value.chart_revision_identity, ".json")
        with self._lock:
            self._retain(binary_path, payload)
            self._retain(manifest_path, artifact_bytes(value))
        return manifest_path

    def retain_pack(self, value: ReviewQuestionPack) -> Path:
        return self._retain_typed("question-packs", value.review_pack_identity, value)

    def retain_batch(self, value: ReviewBatchPdf) -> Path:
        if type(value) is not ReviewBatchPdf:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        path = self._path("batch-pdfs", value.batch_identity, ".json")
        with self._lock:
            self._retain(path, batch_artifact_bytes(value))
        return path

    def retain_answer_pack(self, value: ChartAnalystAnswerPack) -> Path:
        return self._retain_answer_typed("answer-packs", value.answer_pack_identity, value)

    def retain_import_record(self, value: AnswerImportRecord) -> Path:
        return self._retain_answer_typed("answer-imports", value.import_identity, value)

    def retain_visual_evidence(self, value: ImportedVisualEvidence) -> Path:
        return self._retain_answer_typed("visual-evidence", value.visual_evidence_identity, value)

    def retain_answer_transport(self, review_pack_identity: str, payload: bytes) -> Path:
        if type(payload) is not bytes or not payload:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        digest = sha256(payload).hexdigest()
        path = self._path("answer-transports", f"{review_pack_identity}-{digest}", ".json")
        with self._lock:
            self._retain(path, payload)
        return path

    def retain_batch_answer_transport(self, batch_identity: str, payload: bytes) -> Path:
        if type(payload) is not bytes or not payload:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        digest = sha256(payload).hexdigest()
        path = self._path("batch-answer-transports", f"{batch_identity}-{digest}", ".json")
        with self._lock:
            self._retain(path, payload)
        return path

    def save_visual_evidence_pointer(self, value: VisualEvidencePointer) -> Path:
        if type(value) is not VisualEvidencePointer:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        path = self._path("visual-evidence-pointers", value.review_pack_identity, ".json")
        with self._lock:
            self._replace(path, answer_artifact_bytes(value))
        return path

    def save_current(self, value: CurrentReviewPointer) -> Path:
        if type(value) is not CurrentReviewPointer:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        path = self._root / "current" / "CURRENT-REVIEW-POINTER.json"
        with self._lock:
            self._replace(path, artifact_bytes(value))
        return path

    def load_handoff(self, identity: str) -> ReviewHandoff:
        return self._load_typed("handoffs", identity, ReviewHandoff)

    def load_cycle(self, identity: str) -> ReviewCycle:
        return self._load_typed("cycles", identity, ReviewCycle)

    def load_chart(self, identity: str) -> ChartRevision:
        return self._load_typed("chart-revisions", identity, ChartRevision)

    def load_pack(self, identity: str) -> ReviewQuestionPack:
        return self._load_typed("question-packs", identity, ReviewQuestionPack)

    def load_batch(self, identity: str) -> ReviewBatchPdf:
        value = batch_from_bytes(self._read(self._path("batch-pdfs", identity, ".json")))
        if value.batch_identity != identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def load_batch_if_present(self, identity: str) -> ReviewBatchPdf | None:
        path = self._path("batch-pdfs", identity, ".json")
        return None if not path.exists() else self.load_batch(identity)

    def load_answer_pack(self, identity: str) -> ChartAnalystAnswerPack:
        return self._load_answer_typed("answer-packs", identity, ChartAnalystAnswerPack, "answer_pack_identity")

    def load_import_record(self, identity: str) -> AnswerImportRecord:
        return self._load_answer_typed("answer-imports", identity, AnswerImportRecord, "import_identity")

    def load_visual_evidence(self, identity: str) -> ImportedVisualEvidence:
        return self._load_answer_typed("visual-evidence", identity, ImportedVisualEvidence, "visual_evidence_identity")

    def load_visual_evidence_pointer(self, review_pack_identity: str) -> VisualEvidencePointer | None:
        path = self._path("visual-evidence-pointers", review_pack_identity, ".json")
        if not path.exists():
            return None
        value = answer_artifact_from_bytes(self._read(path))
        if type(value) is not VisualEvidencePointer or value.review_pack_identity != review_pack_identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def load_current(self) -> CurrentReviewPointer | None:
        path = self._root / "current" / "CURRENT-REVIEW-POINTER.json"
        if not path.exists():
            return None
        value = artifact_from_bytes(self._read(path))
        if type(value) is not CurrentReviewPointer:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def load_chart_bytes(self, value: ChartRevision) -> bytes:
        if type(value) is not ChartRevision:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        suffix = _MEDIA[value.media_type][0]
        payload = self._read(self._path("chart-binaries", value.chart_artifact_identity, suffix))
        validate_chart_payload(value.media_type, payload)
        from hashlib import sha256

        if len(payload) != value.byte_count or sha256(payload).hexdigest() != value.payload_sha256:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return payload

    def _retain_typed(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity, ".json")
        with self._lock:
            self._retain(path, artifact_bytes(value))
        return path

    def _retain_answer_typed(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity, ".json")
        with self._lock:
            self._retain(path, answer_artifact_bytes(value))
        return path

    def _load_answer_typed(self, family: str, identity: str, expected: type, identity_name: str):  # type: ignore[no-untyped-def]
        value = answer_artifact_from_bytes(self._read(self._path(family, identity, ".json")))
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def _load_typed(self, family: str, identity: str, expected: type):  # type: ignore[no-untyped-def]
        value = artifact_from_bytes(self._read(self._path(family, identity, ".json")))
        identity_name = {
            ReviewHandoff: "handoff_identity",
            ReviewCycle: "cycle_identity",
            ChartRevision: "chart_revision_identity",
            ReviewQuestionPack: "review_pack_identity",
        }[expected]
        identity_value = getattr(value, identity_name, None)
        if type(value) is not expected or identity_value != identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def _path(self, family: str, identity: str, suffix: str) -> Path:
        if not _component(identity):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return self._root / family / f"{identity}{suffix}"

    @staticmethod
    def _retain(path: Path, payload: bytes) -> None:
        if path.exists():
            if IntradayReviewStore._read(path) != payload:
                raise ReviewError(ReviewFailure.PERSISTENCE_CONFLICT)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(payload)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _replace(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(payload)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _read(path: Path) -> bytes:
        try:
            return path.read_bytes()
        except OSError as error:
            raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE) from error


def validate_chart_payload(media_type: str, payload: bytes) -> None:
    if media_type not in _MEDIA or type(payload) is not bytes or not 0 < len(payload) <= MAX_CHART_BYTES:
        raise ReviewError(ReviewFailure.CHART_INVALID)
    if not payload.startswith(_MEDIA[media_type][1]):
        raise ReviewError(ReviewFailure.CHART_INVALID)
    try:
        reader = ImageReader(BytesIO(payload))
        width, height = reader.getSize()
        if width < 1 or height < 1:
            raise ValueError
    except Exception as error:
        raise ReviewError(ReviewFailure.CHART_INVALID) from error


def _component(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
    )


__all__ = [
    "DEFAULT_INTRADAY_REVIEW_ROOT",
    "MAX_CHART_BYTES",
    "IntradayReviewStore",
    "validate_chart_payload",
]
