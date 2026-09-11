"""Append-only persistence and restoration for WO-07F records."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.visual_reconciliation_v2 import (
    CurrentReconciliationPointer,
    VisualReconciliationRecord,
    artifact_bytes,
    create_current_pointer,
    pointer_from_bytes,
    record_from_bytes,
)


_STORE_LOCKS: dict[Path, object] = {}
_STORE_LOCKS_LOCK = RLock()


class VisualReconciliationPersistenceError(ValueError):
    pass


class VisualReconciliationStore:
    """Retain immutable records and explicit per-cycle current pointers."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("WO07F_STORE_ROOT_INVALID")
        self._root = root
        with _STORE_LOCKS_LOCK:
            self._lock = _STORE_LOCKS.setdefault(root.resolve(), RLock())

    @property
    def root(self) -> Path:
        return self._root

    def retain(
        self, record: VisualReconciliationRecord
    ) -> tuple[VisualReconciliationRecord, str]:
        if type(record) is not VisualReconciliationRecord:
            raise ValueError("WO07F_RECORD_INVALID")
        record_path = self._record_path(record.reconciliation_identity)
        pointer_path = self._pointer_path(record.review_cycle_identity)
        payload = artifact_bytes(record)
        pointer = create_current_pointer(record)
        with self._lock:
            current = self.load_current(record.review_cycle_identity)
            if current is not None and current.input_identity == record.input_identity:
                retained = self.load(current.reconciliation_identity)
                return retained, "ALREADY_RECONCILED"
            if record_path.exists():
                if self._read(record_path) != payload:
                    raise VisualReconciliationPersistenceError(
                        "WO07F_PERSISTENCE_CONFLICT"
                    )
                retained = self.load(record.reconciliation_identity)
                current = self.load_current(record.review_cycle_identity)
                if current is None or current.reconciliation_identity != record.reconciliation_identity:
                    raise VisualReconciliationPersistenceError(
                        "WO07F_POINTER_CONFLICT"
                    )
                return retained, "ALREADY_RECONCILED"
            self._retain_immutable(record_path, payload)
            self._replace(pointer_path, artifact_bytes(pointer))
            return record, "RECONCILED"

    def load(self, identity: str) -> VisualReconciliationRecord:
        try:
            value = record_from_bytes(self._read(self._record_path(identity)))
        except ValueError as error:
            raise VisualReconciliationPersistenceError(
                "WO07F_RECORD_INTEGRITY_INVALID"
            ) from error
        if value.reconciliation_identity != identity:
            raise VisualReconciliationPersistenceError("WO07F_RECORD_INTEGRITY_INVALID")
        return value

    def load_current(
        self, review_cycle_identity: str
    ) -> CurrentReconciliationPointer | None:
        path = self._pointer_path(review_cycle_identity)
        if not path.exists():
            return None
        try:
            pointer = pointer_from_bytes(self._read(path))
        except ValueError as error:
            raise VisualReconciliationPersistenceError(
                "WO07F_POINTER_INVALID"
            ) from error
        if pointer.review_cycle_identity != review_cycle_identity:
            raise VisualReconciliationPersistenceError("WO07F_POINTER_INVALID")
        record = self.load(pointer.reconciliation_identity)
        if (
            record.review_cycle_identity != review_cycle_identity
            or record.input_identity != pointer.input_identity
        ):
            raise VisualReconciliationPersistenceError("WO07F_POINTER_INVALID")
        return pointer

    def restore_current(
        self, review_cycle_identity: str
    ) -> VisualReconciliationRecord | None:
        pointer = self.load_current(review_cycle_identity)
        return None if pointer is None else self.load(pointer.reconciliation_identity)

    def list_records(self) -> tuple[VisualReconciliationRecord, ...]:
        directory = self._root / "records"
        if not directory.exists():
            return ()
        return tuple(
            self.load(path.stem) for path in sorted(directory.glob("*.json"))
        )

    def _record_path(self, identity: str) -> Path:
        return self._path("records", identity)

    def _pointer_path(self, identity: str) -> Path:
        return self._path("current", identity)

    def _path(self, family: str, identity: str) -> Path:
        if not _component(identity):
            raise ValueError("WO07F_IDENTITY_INVALID")
        return self._root / family / f"{identity}.json"

    @staticmethod
    def _read(path: Path) -> bytes:
        try:
            return path.read_bytes()
        except OSError as error:
            raise VisualReconciliationPersistenceError(
                "WO07F_ARTIFACT_UNAVAILABLE"
            ) from error

    @staticmethod
    def _retain_immutable(path: Path, payload: bytes) -> None:
        if path.exists():
            if path.read_bytes() != payload:
                raise VisualReconciliationPersistenceError(
                    "WO07F_PERSISTENCE_CONFLICT"
                )
            return
        VisualReconciliationStore._replace(path, payload)

    @staticmethod
    def _replace(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(payload)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


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
    "VisualReconciliationPersistenceError",
    "VisualReconciliationStore",
]
