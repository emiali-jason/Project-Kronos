"""Append-only persistence for sanitized V2 Review operation provenance."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4
from weakref import WeakValueDictionary

from kronos.intraday.review_v2_operation import (
    ReviewV2OperationOutcome,
    ReviewV2OperationProvenance,
    ReviewV2OperationSource,
)


# One bounded derived selection per live owner root, never a durable current pointer.
_LATEST = WeakValueDictionary()
_LATEST_GUARD = RLock()
_MAX_LATEST_BYTES = 256 * 1024


class _Latest:
    def __init__(self):
        self.lock = RLock()
        self.selected = None
        self.failure = None


class ReviewV2OperationProvenanceStore:
    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_REVIEW_V2_OPERATION_ROOT_INVALID")
        self._root = root / "operations"
        with _LATEST_GUARD:
            self._latest = _LATEST.setdefault(self._root.resolve(), _Latest())
        self._lock = self._latest.lock
        self.restore_latest()

    @property
    def root(self) -> Path:
        return self._root

    def retain(
        self, record: ReviewV2OperationProvenance, *, primary: bool = True
    ) -> Path:
        if type(record) is not ReviewV2OperationProvenance or type(primary) is not bool:
            raise ValueError("INTRADAY_REVIEW_V2_OPERATION_PROVENANCE_INVALID")
        payload = _encoded(record)
        path = self._record_path(record.provenance_identity)
        with self._lock:
            try:
                _retain(path, payload)
                if primary:
                    _retain(self._request_path(record.request_identity), payload)
                self._select_latest(record, payload)
            except Exception:
                self._latest.selected = None
                self._latest.failure = "INTRADAY_REVIEW_V2_OPERATION_PROVENANCE_PREPARATION_FAILED"
                raise
        return path

    def load_for_request(
        self, request_identity: str
    ) -> ReviewV2OperationProvenance | None:
        path = self._request_path(request_identity)
        return None if not path.exists() else _decoded(path.read_bytes())

    def _select_latest(self, record, payload):
        if self._latest.failure is not None:
            return
        previous = self._latest.selected
        key = lambda item: (item.operation_completed_at, item.provenance_identity)
        if previous is None or key(record) >= key(previous[0]):
            if len(payload) > _MAX_LATEST_BYTES:
                self._latest.selected = None
                self._latest.failure = "INTRADAY_REVIEW_V2_OPERATION_PROVENANCE_CAPACITY"
            else:
                self._latest.selected = (record, payload)

    def restore_latest(self):
        """Explicit restoration boundary: stream history once, retain one result."""
        with self._lock:
            self._latest.selected = None
            self._latest.failure = None
            try:
                for path in (self._root / "records").glob("*.json"):
                    with path.open("rb") as handle:
                        payload = handle.read(_MAX_LATEST_BYTES + 1)
                    if len(payload) > _MAX_LATEST_BYTES:
                        raise ValueError("INTRADAY_REVIEW_V2_OPERATION_PROVENANCE_CAPACITY")
                    record = _decoded(payload)
                    self._select_latest(record, payload)
            except Exception:
                self._latest.selected = None
                self._latest.failure = "INTRADAY_REVIEW_V2_OPERATION_PROVENANCE_PREPARATION_FAILED"
                raise

    def latest(self) -> ReviewV2OperationProvenance | None:
        """Observe the prepared latest record; never recover or scan history."""
        with self._lock:
            if self._latest.failure is not None:
                raise ValueError(self._latest.failure)
            selected = self._latest.selected
            if selected is None:
                return None
            record, expected = selected
            try:
                with self._record_path(record.provenance_identity).open("rb") as handle:
                    actual = handle.read(_MAX_LATEST_BYTES + 1)
                if actual != expected:
                    # Preserve the owner's precise codec failure on corrupt bytes.
                    _decoded(actual)
                    raise ValueError("INTRADAY_REVIEW_V2_OPERATION_PROVENANCE_CHANGED")
            except Exception:
                self._latest.selected = None
                self._latest.failure = "INTRADAY_REVIEW_V2_OPERATION_PROVENANCE_PREPARATION_FAILED"
                raise
            return record

    def _record_path(self, identity: str) -> Path:
        _component(identity)
        return self._root / "records" / f"{identity}.json"

    def _request_path(self, identity: str) -> Path:
        _component(identity)
        from hashlib import sha256
        return self._root / "requests" / f"{sha256(identity.encode()).hexdigest().upper()}.json"


def _encoded(record: ReviewV2OperationProvenance) -> bytes:
    return (json.dumps(
        asdict(record),
        default=lambda value: value.value if hasattr(value, "value") else value.isoformat(),
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n").encode()


def _decoded(payload: bytes) -> ReviewV2OperationProvenance:
    try:
        values = json.loads(payload)
        for name in ("received_at", "operation_started_at", "operation_completed_at"):
            if values[name] is not None:
                values[name] = datetime.fromisoformat(values[name])
        values["cycle_identities"] = tuple(values["cycle_identities"])
        values["source"] = ReviewV2OperationSource(values["source"])
        values["outcome"] = ReviewV2OperationOutcome(values["outcome"])
        return ReviewV2OperationProvenance(**values)
    except Exception as error:
        raise ValueError("INTRADAY_REVIEW_V2_OPERATION_PROVENANCE_INVALID") from error


def _retain(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("INTRADAY_REVIEW_V2_OPERATION_PROVENANCE_CONFLICT")
        return
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _component(value: object) -> None:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > 512
        or "/" in value
        or "\\" in value
    ):
        raise ValueError("INTRADAY_REVIEW_V2_OPERATION_IDENTITY_INVALID")


__all__ = ["ReviewV2OperationProvenanceStore"]
