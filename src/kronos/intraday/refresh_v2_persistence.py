"""Append-only persistence for sanitized V2 Refresh request provenance."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4
from weakref import WeakValueDictionary

from kronos.intraday.refresh_v2 import (
    REFRESH_V2_PROVENANCE_VERSION,
    REFRESH_V2_TRUSTED_TIME_PROVENANCE_VERSION,
    RefreshV2Outcome,
    RefreshV2ProvenanceRecord,
    RefreshV2SourceClass,
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


class RefreshV2ProvenanceStore:
    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_PROBABLES_V2_PROVENANCE_ROOT_INVALID")
        self._root = root / "refresh-v2" / "request-provenance"
        with _LATEST_GUARD:
            self._latest = _LATEST.setdefault(self._root.resolve(), _Latest())
        self._lock = self._latest.lock
        self.restore_latest()

    @property
    def root(self) -> Path:
        return self._root

    def retain(self, record: RefreshV2ProvenanceRecord, *, primary: bool = True) -> Path:
        if type(record) is not RefreshV2ProvenanceRecord or type(primary) is not bool:
            raise ValueError("INTRADAY_PROBABLES_V2_PROVENANCE_INVALID")
        path = self._path(record.provenance_identity)
        encoded = _encoded(record)
        with self._lock:
            try:
                _retain_immutable(path, encoded)
                if primary:
                    index = self._request_index(record.request_identity)
                    _retain_immutable(index, encoded)
                self._select_latest(record, encoded)
            except Exception:
                self._latest.selected = None
                self._latest.failure = "INTRADAY_PROBABLES_V2_PROVENANCE_PREPARATION_FAILED"
                raise
        return path

    def load_for_request(self, request_identity: str) -> RefreshV2ProvenanceRecord | None:
        path = self._request_index(request_identity)
        if not path.exists():
            return None
        return _decoded(path.read_bytes())

    def load(self, provenance_identity: str) -> RefreshV2ProvenanceRecord:
        return _decoded(self._path(provenance_identity).read_bytes())

    def load_for_probables_run(self, run_identity: str) -> tuple[RefreshV2ProvenanceRecord, ...]:
        """Read exact resulting-run provenance without latest-state substitution."""
        _component(run_identity)
        records = self._root / "records"
        values = (self.load(path.stem) for path in sorted(records.glob("*.json")))
        return tuple(value for value in values if value.resulting_probables_identity == run_identity)

    def _select_latest(self, record, payload):
        if self._latest.failure is not None:
            return
        previous = self._latest.selected
        key = lambda item: (item.operation_completed_at, item.provenance_identity)
        if previous is None or key(record) >= key(previous[0]):
            if len(payload) > _MAX_LATEST_BYTES:
                self._latest.selected = None
                self._latest.failure = "INTRADAY_PROBABLES_V2_PROVENANCE_CAPACITY"
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
                        raise ValueError("INTRADAY_PROBABLES_V2_PROVENANCE_CAPACITY")
                    record = _decoded(payload)
                    self._select_latest(record, payload)
            except Exception:
                self._latest.selected = None
                self._latest.failure = "INTRADAY_PROBABLES_V2_PROVENANCE_PREPARATION_FAILED"
                raise

    def latest(self) -> RefreshV2ProvenanceRecord | None:
        """Observe the prepared latest record; never recover or scan history."""
        with self._lock:
            if self._latest.failure is not None:
                raise ValueError(self._latest.failure)
            selected = self._latest.selected
            if selected is None:
                return None
            record, expected = selected
            try:
                with self._path(record.provenance_identity).open("rb") as handle:
                    actual = handle.read(_MAX_LATEST_BYTES + 1)
                if actual != expected:
                    # Preserve the owner's precise codec failure on corrupt bytes.
                    _decoded(actual)
                    raise ValueError("INTRADAY_PROBABLES_V2_PROVENANCE_CHANGED")
            except Exception:
                self._latest.selected = None
                self._latest.failure = "INTRADAY_PROBABLES_V2_PROVENANCE_PREPARATION_FAILED"
                raise
            return record

    def _path(self, identity: str) -> Path:
        _component(identity)
        return self._root / "records" / f"{identity}.json"

    def _request_index(self, identity: str) -> Path:
        _component(identity)
        import hashlib
        digest = hashlib.sha256(identity.encode()).hexdigest().upper()
        return self._root / "requests" / f"{digest}.json"


def _encoded(record: RefreshV2ProvenanceRecord) -> bytes:
    values = asdict(record)
    if record.contract_version != REFRESH_V2_PROVENANCE_VERSION:
        values.pop("operation_accounting_identity")
    if record.contract_version not in {REFRESH_V2_TRUSTED_TIME_PROVENANCE_VERSION, REFRESH_V2_PROVENANCE_VERSION}:
        values.pop("trusted_admission_time")
    return (json.dumps(
        values,
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
        values.setdefault("operation_accounting_identity", None)
        values.setdefault("trusted_admission_time", None)
        if values["trusted_admission_time"] is not None:
            values["trusted_admission_time"] = datetime.fromisoformat(values["trusted_admission_time"])
        values.setdefault("replay_envelope_identity", None)
        values.setdefault("failure_detail_identity", None)
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
