"""Append-only persistence for sanitized V2 Refresh request provenance."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.refresh_v2 import (
    RefreshV2Outcome,
    RefreshV2ProvenanceRecord,
    RefreshV2SourceClass,
)


class RefreshV2ProvenanceStore:
    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_PROBABLES_V2_PROVENANCE_ROOT_INVALID")
        self._root = root / "refresh-v2" / "request-provenance"
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain(self, record: RefreshV2ProvenanceRecord, *, primary: bool = True) -> Path:
        if type(record) is not RefreshV2ProvenanceRecord or type(primary) is not bool:
            raise ValueError("INTRADAY_PROBABLES_V2_PROVENANCE_INVALID")
        path = self._path(record.provenance_identity)
        encoded = _encoded(record)
        with self._lock:
            _retain_immutable(path, encoded)
            if primary:
                index = self._request_index(record.request_identity)
                _retain_immutable(index, encoded)
        return path

    def load_for_request(self, request_identity: str) -> RefreshV2ProvenanceRecord | None:
        path = self._request_index(request_identity)
        if not path.exists():
            return None
        return _decoded(path.read_bytes())

    def load(self, provenance_identity: str) -> RefreshV2ProvenanceRecord:
        return _decoded(self._path(provenance_identity).read_bytes())

    def latest(self) -> RefreshV2ProvenanceRecord | None:
        records = self._root / "records"
        if not records.exists():
            return None
        values = tuple(_decoded(path.read_bytes()) for path in records.glob("*.json"))
        return max(
            values,
            key=lambda item: (item.operation_completed_at, item.provenance_identity),
            default=None,
        )

    def _path(self, identity: str) -> Path:
        _component(identity)
        return self._root / "records" / f"{identity}.json"

    def _request_index(self, identity: str) -> Path:
        _component(identity)
        import hashlib
        digest = hashlib.sha256(identity.encode()).hexdigest().upper()
        return self._root / "requests" / f"{digest}.json"


def _encoded(record: RefreshV2ProvenanceRecord) -> bytes:
    return (json.dumps(
        asdict(record),
        default=lambda value: value.value if hasattr(value, "value") else value.isoformat(),
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n").encode()


def _decoded(payload: bytes) -> RefreshV2ProvenanceRecord:
    try:
        values = json.loads(payload)
        for name in (
            "observation_boundary",
            "received_at",
            "operation_started_at",
            "operation_completed_at",
        ):
            if values[name] is not None:
                values[name] = datetime.fromisoformat(values[name])
        values["outcome"] = RefreshV2Outcome(values["outcome"])
        values["source_class"] = RefreshV2SourceClass(values["source_class"])
        return RefreshV2ProvenanceRecord(**values)
    except Exception as error:
        raise ValueError("INTRADAY_PROBABLES_V2_PROVENANCE_INVALID") from error


def _retain_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("INTRADAY_PROBABLES_V2_PROVENANCE_CONFLICT")
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
        or "/" in value
        or "\\" in value
        or len(value) > 256
    ):
        raise ValueError("INTRADAY_PROBABLES_V2_PROVENANCE_IDENTITY_INVALID")


__all__ = ["RefreshV2ProvenanceStore"]
