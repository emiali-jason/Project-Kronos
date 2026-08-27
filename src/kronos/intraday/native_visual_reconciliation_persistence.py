"""Append-only persistence for Intraday WO-10 reconciliation authority."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.native_visual_reconciliation import (
    CurrentReconciliationPointer,
    PromotionRecord,
    ReadinessRecord,
    ReconciliationError,
    ReconciliationFact,
    ReconciliationFailure,
    ReconciliationPolicyPublication,
    ReconciliationRun,
    ReviewStateRecord,
    reconciliation_artifact_bytes,
    reconciliation_artifact_from_bytes,
)


DEFAULT_INTRADAY_RECONCILIATION_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "intraday-v1"
    / "native-visual-reconciliation-v1"
)


class IntradayNativeVisualReconciliationStore:
    """Explicit-identity immutable artifacts plus one integrity-bound pointer."""

    def __init__(self, root: Path = DEFAULT_INTRADAY_RECONCILIATION_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_RECONCILIATION_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_policy(self, value: ReconciliationPolicyPublication) -> Path:
        return self._retain_typed("policies", value.publication_identity, value)

    def retain_fact(self, value: ReconciliationFact) -> Path:
        return self._retain_typed("facts", value.fact_identity, value)

    def retain_review_state(self, value: ReviewStateRecord) -> Path:
        return self._retain_typed("review-states", value.review_state_identity, value)

    def retain_readiness(self, value: ReadinessRecord) -> Path:
        return self._retain_typed("readiness", value.readiness_identity, value)

    def retain_promotion(self, value: PromotionRecord) -> Path:
        return self._retain_typed("promotions", value.promotion_identity, value)

    def retain_run(self, value: ReconciliationRun) -> Path:
        return self._retain_typed("runs", value.run_identity, value)

    def retain_complete(self, value: ReconciliationRun, policy: ReconciliationPolicyPublication) -> Path:
        if value.policy_publication_identity != policy.publication_identity:
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        with self._lock:
            self.retain_policy(policy)
            for fact in value.facts:
                self.retain_fact(fact)
            self.retain_review_state(value.review_state)
            self.retain_readiness(value.readiness)
            self.retain_promotion(value.promotion)
            return self.retain_run(value)

    def save_current(self, value: CurrentReconciliationPointer) -> Path:
        if type(value) is not CurrentReconciliationPointer:
            raise ReconciliationError(ReconciliationFailure.INPUT_INVALID)
        path = self._root / "current" / "CURRENT-RECONCILIATION-POINTER.json"
        with self._lock:
            self._replace(path, reconciliation_artifact_bytes(value))
        return path

    def load_policy(self, identity: str) -> ReconciliationPolicyPublication:
        return self._load_typed("policies", identity, ReconciliationPolicyPublication, "publication_identity")

    def load_fact(self, identity: str) -> ReconciliationFact:
        return self._load_typed("facts", identity, ReconciliationFact, "fact_identity")

    def load_review_state(self, identity: str) -> ReviewStateRecord:
        return self._load_typed("review-states", identity, ReviewStateRecord, "review_state_identity")

    def load_readiness(self, identity: str) -> ReadinessRecord:
        return self._load_typed("readiness", identity, ReadinessRecord, "readiness_identity")

    def load_promotion(self, identity: str) -> PromotionRecord:
        return self._load_typed("promotions", identity, PromotionRecord, "promotion_identity")

    def load_run(self, identity: str) -> ReconciliationRun:
        return self._load_typed("runs", identity, ReconciliationRun, "run_identity")

    def load_current(self) -> CurrentReconciliationPointer | None:
        path = self._root / "current" / "CURRENT-RECONCILIATION-POINTER.json"
        if not path.exists():
            return None
        value = reconciliation_artifact_from_bytes(self._read(path))
        if type(value) is not CurrentReconciliationPointer:
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        return value

    def _retain_typed(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        with self._lock:
            self._retain(path, reconciliation_artifact_bytes(value))
        return path

    def _load_typed(self, family: str, identity: str, expected: type, identity_name: str):  # type: ignore[no-untyped-def]
        value = reconciliation_artifact_from_bytes(self._read(self._path(family, identity)))
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        return value

    def _path(self, family: str, identity: str) -> Path:
        if not _component(identity):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        return self._root / family / f"{identity}.json"

    @staticmethod
    def _retain(path: Path, payload: bytes) -> None:
        if path.exists():
            if IntradayNativeVisualReconciliationStore._read(path) != payload:
                raise ReconciliationError(ReconciliationFailure.PERSISTENCE_CONFLICT)
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
            raise ReconciliationError(ReconciliationFailure.ARTIFACT_UNAVAILABLE) from error


def _component(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
    )


__all__ = ["DEFAULT_INTRADAY_RECONCILIATION_ROOT", "IntradayNativeVisualReconciliationStore"]
