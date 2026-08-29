"""Append-only persistence for the separately versioned V2 Review seam."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4
from hashlib import sha256

from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_v2 import (
    ChartIntakeRequestV2,
    ChartRevisionV2,
    CurrentChartPointerV2,
    CurrentReviewPointerV2,
    ImportedVisualEvidenceV2,
    ReviewCycleV2,
    ReviewHandoffV2,
    ReviewQuestionBatchV2,
    ReviewQuestionPackV2,
    artifact_bytes_v2,
    artifact_from_bytes_v2,
)
from kronos.intraday.review_persistence import validate_chart_payload


DEFAULT_INTRADAY_REVIEW_V2_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "intraday-v1"
    / "review-v2"
)


class IntradayReviewV2Store:
    """Explicit-identity V2 store; it never reads or writes review-v1."""

    def __init__(self, root: Path = DEFAULT_INTRADAY_REVIEW_V2_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_REVIEW_V2_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_handoff(self, value: ReviewHandoffV2) -> Path:
        return self._retain_typed("handoffs", value.handoff_identity, value)

    def retain_cycle(self, value: ReviewCycleV2) -> Path:
        return self._retain_typed("cycles", value.cycle_identity, value)

    def retain_chart_request(self, value: ChartIntakeRequestV2) -> Path:
        return self._retain_typed("chart-requests", value.request_identity, value)

    def retain_chart(self, value: ChartRevisionV2, payload: bytes) -> Path:
        if type(value) is not ChartRevisionV2:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        validate_chart_payload(value.media_type, payload)
        if (
            len(payload) != value.byte_count
            or sha256(payload).hexdigest() != value.payload_sha256
        ):
            raise ReviewError(ReviewFailure.CHART_INVALID)
        suffix = ".png" if value.media_type == "image/png" else ".jpg"
        binary_path = self._path("chart-binaries", value.chart_artifact_identity, suffix)
        manifest_path = self._path("chart-revisions", value.chart_revision_identity)
        with self._lock:
            self._retain(binary_path, payload)
            self._retain(manifest_path, artifact_bytes_v2(value))
        return manifest_path

    def retain_pack(self, value: ReviewQuestionPackV2) -> Path:
        return self._retain_typed("question-packs", value.review_pack_identity, value)

    def retain_batch(self, value: ReviewQuestionBatchV2) -> Path:
        return self._retain_typed("question-batches", value.batch_identity, value)

    def retain_visual_evidence(self, value: ImportedVisualEvidenceV2) -> Path:
        return self._retain_typed("visual-evidence", value.visual_evidence_identity, value)

    def retain_answer_transport(self, review_pack_identity: str, payload: bytes) -> Path:
        if not _component(review_pack_identity) or type(payload) is not bytes or not payload:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        digest = sha256(payload).hexdigest()
        path = self._path(
            "answer-transports", f"{review_pack_identity}-{digest}"
        )
        with self._lock:
            self._retain(path, payload)
        return path

    def load_handoff(self, identity: str) -> ReviewHandoffV2:
        return self._load_typed("handoffs", identity, ReviewHandoffV2, "handoff_identity")

    def load_cycle(self, identity: str) -> ReviewCycleV2:
        return self._load_typed("cycles", identity, ReviewCycleV2, "cycle_identity")

    def load_chart(self, identity: str) -> ChartRevisionV2:
        return self._load_typed(
            "chart-revisions", identity, ChartRevisionV2, "chart_revision_identity"
        )

    def load_chart_request(self, identity: str) -> ChartIntakeRequestV2:
        return self._load_typed(
            "chart-requests", identity, ChartIntakeRequestV2, "request_identity"
        )

    def load_pack(self, identity: str) -> ReviewQuestionPackV2:
        return self._load_typed(
            "question-packs", identity, ReviewQuestionPackV2, "review_pack_identity"
        )

    def load_batch(self, identity: str) -> ReviewQuestionBatchV2:
        return self._load_typed(
            "question-batches", identity, ReviewQuestionBatchV2, "batch_identity"
        )

    def load_visual_evidence(self, identity: str) -> ImportedVisualEvidenceV2:
        return self._load_typed(
            "visual-evidence", identity, ImportedVisualEvidenceV2,
            "visual_evidence_identity",
        )

    def load_chart_bytes(self, value: ChartRevisionV2) -> bytes:
        if type(value) is not ChartRevisionV2:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        suffix = ".png" if value.media_type == "image/png" else ".jpg"
        payload = self._read(
            self._path("chart-binaries", value.chart_artifact_identity, suffix)
        )
        validate_chart_payload(value.media_type, payload)
        if (
            len(payload) != value.byte_count
            or sha256(payload).hexdigest() != value.payload_sha256
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return payload

    def save_current_chart(self, value: CurrentChartPointerV2) -> Path:
        if type(value) is not CurrentChartPointerV2:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        path = self._path("current-charts", value.review_cycle_identity)
        with self._lock:
            self._replace(path, artifact_bytes_v2(value))
        return path

    def load_current_chart(
        self, cycle_identity: str,
    ) -> CurrentChartPointerV2 | None:
        path = self._path("current-charts", cycle_identity)
        if not path.exists():
            return None
        value = artifact_from_bytes_v2(self._read(path))
        if (
            type(value) is not CurrentChartPointerV2
            or value.review_cycle_identity != cycle_identity
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        cycle = self.load_cycle(cycle_identity)
        request = self.load_chart_request(value.chart_request_identity)
        chart = self.load_chart(value.chart_revision_identity)
        if (
            request.review_cycle_identity != cycle_identity
            or chart.review_cycle_identity != cycle_identity
            or value.probables_run_identity != cycle.probables_run_identity
            or value.probable_result_identity != cycle.probable_result_identity
            or value.expected_canonical_subject_identity
            != cycle.canonical_subject_identity
            or value.direction != cycle.direction
            or value.methodology_publication_identity
            != cycle.methodology_publication_identity
            or value.methodology_checksum != cycle.methodology_checksum
            or value.phase is not cycle.phase
            or value.analysis_boundary != cycle.analysis_boundary
            or value.chart_artifact_identity != chart.chart_artifact_identity
            or value.revision_ordinal != chart.revision_ordinal
            or value.payload_sha256 != chart.payload_sha256
            or value.media_type != chart.media_type
            or request.payload_sha256 != chart.payload_sha256
            or request.media_type != chart.media_type
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def save_current(self, value: CurrentReviewPointerV2) -> Path:
        if type(value) is not CurrentReviewPointerV2:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        path = self._root / "current" / "CURRENT-REVIEW-V2-POINTER.json"
        with self._lock:
            self._replace(path, artifact_bytes_v2(value))
        return path

    def load_current(self) -> CurrentReviewPointerV2 | None:
        path = self._root / "current" / "CURRENT-REVIEW-V2-POINTER.json"
        if not path.exists():
            return None
        value = artifact_from_bytes_v2(self._read(path))
        if type(value) is not CurrentReviewPointerV2:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        for pointer in value.cycles:
            cycle = self.load_cycle(pointer.cycle_identity)
            if (
                cycle.probables_run_identity != value.probables_run_identity
                or cycle.probable_result_identity != pointer.probable_result_identity
                or cycle.canonical_subject_identity != pointer.canonical_subject_identity
                or cycle.direction != pointer.direction
            ):
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            handoff = self.load_handoff(cycle.handoff_identity)
            if (
                handoff.probables_run_identity != cycle.probables_run_identity
                or handoff.probable_result_identity != cycle.probable_result_identity
                or handoff.methodology_publication_identity
                != cycle.methodology_publication_identity
                or handoff.methodology_checksum != cycle.methodology_checksum
                or handoff.phase is not cycle.phase
            ):
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def cycles_for_run(self, run_identity: str) -> tuple[ReviewCycleV2, ...]:
        pointer = self.load_current()
        if pointer is None or pointer.probables_run_identity != run_identity:
            return ()
        return tuple(self.load_cycle(item.cycle_identity) for item in pointer.cycles)

    def _retain_typed(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        payload = artifact_bytes_v2(value)
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
                temporary.unlink(missing_ok=True)
        return path

    def _retain(self, path: Path, payload: bytes) -> None:
        if path.exists():
            if self._read(path) != payload:
                raise ReviewError(ReviewFailure.PERSISTENCE_CONFLICT)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(payload)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _load_typed(
        self, family: str, identity: str, expected: type, identity_name: str,
    ):  # type: ignore[no-untyped-def]
        value = artifact_from_bytes_v2(self._read(self._path(family, identity)))
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return value

    def _path(self, family: str, identity: str, suffix: str = ".json") -> Path:
        if not _component(identity):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return self._root / family / f"{identity}{suffix}"

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


def _component(value: object) -> bool:
    return (
        type(value) is str and bool(value) and value == value.strip()
        and value not in {".", ".."} and "/" not in value and "\\" not in value
    )


__all__ = ["DEFAULT_INTRADAY_REVIEW_V2_ROOT", "IntradayReviewV2Store"]
