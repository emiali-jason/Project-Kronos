"""Append-only explicit-identity store for MCX paired Review evidence."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from uuid import uuid4
from hashlib import sha256

from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_mcx_paired import (
    McxPairedChartBundle, McxPairedChartRevision, McxPairedReviewPack,
    artifact_bytes, artifact_from_bytes,
)
from kronos.intraday.review_mcx_paired_answer import (
    McxPairedAnswerPack, McxPairedImportedVisualEvidence, answer_artifact_from_bytes,
)
from kronos.intraday.review_mcx_paired_transport import McxPairedReviewTransport, transport_from_bytes


DEFAULT_MCX_PAIRED_REVIEW_ROOT = Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence" / "intraday-v1" / "review-mcx-paired-v1"


class IntradayMcxPairedReviewStore:
    """No latest-file fallback and no read/write access to review-v1/review-v2."""

    def __init__(self, root: Path = DEFAULT_MCX_PAIRED_REVIEW_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("MCX_PAIRED_REVIEW_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_chart(self, value: McxPairedChartRevision, payload: bytes) -> Path:
        if sha256(payload).hexdigest() != value.payload_sha256 or len(payload) != value.byte_count:
            raise ReviewError(ReviewFailure.CHART_INVALID)
        suffix = ".png" if value.media_type == "image/png" else ".jpg"
        with self._lock:
            self._retain(self._path("chart-binaries", value.chart_artifact_identity, suffix), payload)
            return self._retain(self._path("chart-revisions", value.chart_revision_identity), artifact_bytes(value))

    def retain_bundle(self, value: McxPairedChartBundle) -> Path:
        return self._typed("paired-bundles", value.bundle_identity, value)

    def retain_pack(self, value: McxPairedReviewPack) -> Path:
        return self._typed("review-packs", value.review_pack_identity, value)

    def retain_answer(self, value: McxPairedAnswerPack, payload: bytes) -> Path:
        if sha256(payload).hexdigest() != value.source_sha256:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        with self._lock:
            self._retain(self._path("answer-transports", value.answer_pack_identity), payload)
            return self._retain(self._path("answer-packs", value.answer_pack_identity), artifact_bytes(value))

    def retain_evidence(self, value: McxPairedImportedVisualEvidence) -> Path:
        return self._typed("imported-visual-evidence", value.visual_evidence_identity, value)

    def retain_transport(self, value: McxPairedReviewTransport, pdf: bytes, template: bytes) -> Path:
        if sha256(pdf).hexdigest() != value.question_pdf_sha256 or sha256(template).hexdigest() != value.answer_template_sha256:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        with self._lock:
            self._retain(self._path("question-pdfs", value.transport_identity, ".pdf"), pdf)
            self._retain(self._path("answer-templates", value.transport_identity), template)
            return self._retain(self._path("transports", value.transport_identity), artifact_bytes(value))

    def transport_answer_template_path(self, value: McxPairedReviewTransport) -> Path:
        """Internal retained template, outside the Sponsor Question directory."""
        path = self._path("answer-templates", value.transport_identity)
        if sha256(path.read_bytes()).hexdigest() != value.answer_template_sha256:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return path

    def retain_transport_pointer(self, value: McxPairedReviewTransport) -> Path:
        fields = {"review_pack_identity": value.review_pack_identity,
                  "transport_identity": value.transport_identity}
        fields["integrity"] = sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
        namespace = "pack-transports-pdf-only" if value.schema_version == "1.1.0" else "pack-transports"
        return self._retain(self._path(namespace, value.review_pack_identity),
                            json.dumps(fields, sort_keys=True).encode())

    def load_transport_for_pack(self, identity: str) -> McxPairedReviewTransport:
        try:
            namespace = "pack-transports-pdf-only" if self._path("pack-transports-pdf-only", identity).exists() else "pack-transports"
            fields = json.loads(self.load_bytes(namespace, identity))
            integrity = fields.pop("integrity")
            if (set(fields) != {"review_pack_identity", "transport_identity"}
                or fields["review_pack_identity"] != identity
                or integrity != sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()):
                raise ValueError
            value = self.load_transport(fields["transport_identity"])
            if value.review_pack_identity != identity:
                raise ValueError
            return value
        except (ValueError, KeyError, TypeError) as error:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error

    def retain_evidence_pointer(self, value: McxPairedImportedVisualEvidence) -> Path:
        fields = {"review_pack_identity": value.review_pack_identity,
                  "visual_evidence_identity": value.visual_evidence_identity}
        fields["integrity"] = sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
        return self._retain(self._path("current-imports", value.review_pack_identity),
                            json.dumps(fields, sort_keys=True).encode())

    def load_evidence_for_pack(self, identity: str) -> McxPairedImportedVisualEvidence | None:
        path = self._path("current-imports", identity)
        if not path.exists():
            return None
        try:
            fields = json.loads(self._read(path))
            integrity = fields.pop("integrity")
            if (set(fields) != {"review_pack_identity", "visual_evidence_identity"}
                or fields["review_pack_identity"] != identity
                or integrity != sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()):
                raise ValueError
            value = self.load_evidence(fields["visual_evidence_identity"])
            if value.review_pack_identity != identity:
                raise ValueError
            return value
        except (ValueError, KeyError, TypeError) as error:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error

    def load_bytes(self, namespace: str, identity: str, suffix: str = ".json") -> bytes:
        """Explicit identity only; callers validate the reconstructed typed artifact."""
        return self._read(self._path(namespace, identity, suffix))

    def load_chart(self, identity: str) -> McxPairedChartRevision:
        value = artifact_from_bytes(self.load_bytes("chart-revisions", identity))
        if type(value) is not McxPairedChartRevision or value.chart_revision_identity != identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def load_bundle(self, identity: str) -> McxPairedChartBundle:
        value = artifact_from_bytes(self.load_bytes("paired-bundles", identity))
        if type(value) is not McxPairedChartBundle or value.bundle_identity != identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def load_pack(self, identity: str) -> McxPairedReviewPack:
        value = artifact_from_bytes(self.load_bytes("review-packs", identity))
        if type(value) is not McxPairedReviewPack or value.review_pack_identity != identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def load_answer(self, identity: str) -> McxPairedAnswerPack:
        value = answer_artifact_from_bytes(self.load_bytes("answer-packs", identity))
        if type(value) is not McxPairedAnswerPack or value.answer_pack_identity != identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def load_evidence(self, identity: str) -> McxPairedImportedVisualEvidence:
        value = answer_artifact_from_bytes(self.load_bytes("imported-visual-evidence", identity))
        if type(value) is not McxPairedImportedVisualEvidence or value.visual_evidence_identity != identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def load_transport(self, identity: str) -> McxPairedReviewTransport:
        value = transport_from_bytes(self.load_bytes("transports", identity))
        if value.transport_identity != identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def _typed(self, namespace: str, identity: str, value: object) -> Path:
        return self._retain(self._path(namespace, identity), artifact_bytes(value))

    def _path(self, namespace: str, identity: str, suffix: str = ".json") -> Path:
        if not _component(namespace) or not _component(identity):
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        return self._root / namespace / f"{identity}{suffix}"

    def _read(self, path: Path) -> bytes:
        try: return path.read_bytes()
        except OSError as error: raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE) from error

    def _retain(self, path: Path, payload: bytes) -> Path:
        with self._lock:
            if path.exists():
                if self._read(path) != payload:
                    raise ReviewError(ReviewFailure.PERSISTENCE_CONFLICT)
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_bytes(payload)
                temporary.replace(path)
            finally:
                try: temporary.unlink()
                except FileNotFoundError: pass
            return path


def _component(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip() and value not in {".", ".."} and "/" not in value and "\\" not in value


__all__ = ["DEFAULT_MCX_PAIRED_REVIEW_ROOT", "IntradayMcxPairedReviewStore"]
