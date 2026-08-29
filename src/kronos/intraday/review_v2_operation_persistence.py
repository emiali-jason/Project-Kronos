"""Append-only persistence for sanitized V2 Review operation provenance."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.review_v2_operation import (
    ReviewV2OperationOutcome,
    ReviewV2OperationProvenance,
    ReviewV2OperationSource,
)


class ReviewV2OperationProvenanceStore:
    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_REVIEW_V2_OPERATION_ROOT_INVALID")
        self._root = root / "operations"
        self._lock = RLock()

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
            _retain(path, payload)
            if primary:
                _retain(self._request_path(record.request_identity), payload)
        return path

    def load_for_request(
        self, request_identity: str
    ) -> ReviewV2OperationProvenance | None:
        path = self._request_path(request_identity)
        return None if not path.exists() else _decoded(path.read_bytes())

    def latest(self) -> ReviewV2OperationProvenance | None:
        records = self._root / "records"
        if not records.exists():
            return None
        values = tuple(_decoded(path.read_bytes()) for path in records.glob("*.json"))
        return max(
            values,
            key=lambda item: (item.operation_completed_at, item.provenance_identity),
            default=None,
        )

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
