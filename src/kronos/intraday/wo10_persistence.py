"""Append-only persistence and explicit restoration for Intraday WO-10 V2."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from typing import Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import (
    CurrentWo10ReconciliationPointer,
    Wo10BatchResult,
    Wo10ContractError,
    Wo10OperationOutcome,
    Wo10OperationProvenance,
    Wo10OperationStage,
    Wo10PolicyBinding,
    Wo10ProbableBindingV2,
    Wo10ReasonCode,
    Wo10ReasonScope,
    Wo10ReconciliationRequest,
    Wo10ReconciliationResult,
    Wo10ResultBinding,
    Wo10State,
    Wo10StateCount,
)
from kronos.intraday.wo10_evidence import (
    Wo10CommonFactBindings,
    Wo10EquityEvidenceExtension,
    Wo10EvidenceReference,
    Wo10EvidenceSnapshot,
    Wo10IndexEvidenceExtension,
    Wo10McxEvidenceExtension,
)


DEFAULT_WO10_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "intraday-v1"
    / "wo10-reconciliation-v2"
)


class Wo10PersistenceError(Wo10ContractError):
    """Sanitized immutable-store or restoration failure."""


@dataclass(frozen=True, slots=True)
class RestoredWo10State:
    pointer: CurrentWo10ReconciliationPointer
    request: Wo10ReconciliationRequest
    batch: Wo10BatchResult
    results: tuple[Wo10ReconciliationResult, ...]
    evidence_snapshots: tuple[Wo10EvidenceSnapshot, ...]


class Wo10Store:
    """Explicit-identity artifacts plus one integrity-bound family pointer."""

    def __init__(self, root: Path = DEFAULT_WO10_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("WO10_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_policy(self, value: Wo10PolicyBinding) -> Path:
        return self._retain_typed("policies", value.integrity_identity, value)

    def retain_request(self, value: Wo10ReconciliationRequest) -> Path:
        return self._retain_typed("requests", value.request_identity, value)

    def retain_evidence_snapshot(self, value: Wo10EvidenceSnapshot) -> Path:
        return self._retain_typed("evidence-snapshots", value.snapshot_identity, value)

    def retain_result(self, value: Wo10ReconciliationResult) -> Path:
        return self._retain_typed("results", value.result_identity, value)

    def retain_batch(self, value: Wo10BatchResult) -> Path:
        return self._retain_typed("batches", value.batch_identity, value)

    def retain_operation(self, value: Wo10OperationProvenance) -> Path:
        return self._retain_typed("operations", value.operation_identity, value)

    def load_policy(self, identity: str) -> Wo10PolicyBinding:
        return self._load_typed("policies", identity, Wo10PolicyBinding, "integrity_identity")

    def load_request(self, identity: str) -> Wo10ReconciliationRequest:
        return self._load_typed("requests", identity, Wo10ReconciliationRequest, "request_identity")

    def load_evidence_snapshot(self, identity: str) -> Wo10EvidenceSnapshot:
        return self._load_typed(
            "evidence-snapshots", identity, Wo10EvidenceSnapshot, "snapshot_identity"
        )

    def load_result(self, identity: str) -> Wo10ReconciliationResult:
        return self._load_typed("results", identity, Wo10ReconciliationResult, "result_identity")

    def load_batch(self, identity: str) -> Wo10BatchResult:
        return self._load_typed("batches", identity, Wo10BatchResult, "batch_identity")

    def load_operation(self, identity: str) -> Wo10OperationProvenance:
        return self._load_typed(
            "operations", identity, Wo10OperationProvenance, "operation_identity"
        )

    def publish_current(self, value: CurrentWo10ReconciliationPointer) -> Path:
        if type(value) is not CurrentWo10ReconciliationPointer:
            raise Wo10PersistenceError("WO10_CURRENT_POINTER_INVALID")
        path = self._current_path(value.market_family)
        with self._lock:
            _replace_atomic(path, _artifact_bytes(value))
        return path

    def load_current(
        self, market_family: IntradayMarketFamily
    ) -> CurrentWo10ReconciliationPointer | None:
        if type(market_family) is not IntradayMarketFamily:
            raise Wo10PersistenceError("WO10_MARKET_FAMILY_INVALID")
        path = self._current_path(market_family)
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if (
            type(value) is not CurrentWo10ReconciliationPointer
            or value.market_family is not market_family
        ):
            raise Wo10PersistenceError("WO10_CURRENT_POINTER_INTEGRITY_INVALID")
        return value

    def restore_current(
        self, market_family: IntradayMarketFamily
    ) -> RestoredWo10State | None:
        """Restore exact persisted artifacts without policy evaluation or Provider IO."""

        pointer = self.load_current(market_family)
        if pointer is None:
            return None
        request = self.load_request(pointer.request_identity)
        batch = self.load_batch(pointer.batch_identity)
        results = tuple(self.load_result(item.result_identity) for item in pointer.result_bindings)
        snapshots = tuple(
            self.load_evidence_snapshot(item.evidence_snapshot_identity) for item in results
        )
        if (
            request.request_integrity != pointer.request_integrity
            or request.probables_run_identity != pointer.probables_run_identity
            or request.probables_run_integrity != pointer.probables_run_integrity
            or request.market_family is not market_family
            or request.policy != pointer.policy
            or batch.batch_integrity != pointer.batch_integrity
            or batch.request_identity != request.request_identity
            or batch.request_integrity != request.request_integrity
            or batch.result_bindings != pointer.result_bindings
            or any(
                result.request_identity != request.request_identity
                or result.request_integrity != request.request_integrity
                or result.market_family is not market_family
                or result.policy != request.policy
                or result.result_identity != binding.result_identity
                or result.result_integrity != binding.result_integrity
                or snapshot.snapshot_identity != result.evidence_snapshot_identity
                or snapshot.snapshot_integrity != result.evidence_snapshot_integrity
                or snapshot.policy != request.policy
                for binding, result, snapshot in zip(
                    pointer.result_bindings, results, snapshots, strict=True
                )
            )
        ):
            raise Wo10PersistenceError("WO10_RESTORATION_BINDING_INVALID")
        return RestoredWo10State(pointer, request, batch, results, snapshots)

    def _retain_typed(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        with self._lock:
            _retain_immutable(path, _artifact_bytes(value))
        return path

    def _load_typed(
        self, family: str, identity: str, expected: type, identity_name: str
    ):  # type: ignore[no-untyped-def]
        value = _artifact_from_bytes(_read(self._path(family, identity)))
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise Wo10PersistenceError("WO10_ARTIFACT_INTEGRITY_INVALID")
        return value

    def _path(self, family: str, identity: str) -> Path:
        if family not in {
            "policies", "requests", "evidence-snapshots", "results", "batches", "operations"
        } or not _component(identity):
            raise Wo10PersistenceError("WO10_ARTIFACT_PATH_INVALID")
        return self._root / family / f"{identity}.json"

    def _current_path(self, market_family: IntradayMarketFamily) -> Path:
        return self._root / "current" / f"CURRENT-{market_family.value}-WO10-V2.json"


_DATACLASSES = {
    item.__name__: item
    for item in (
        Wo10PolicyBinding,
        Wo10ProbableBindingV2,
        Wo10ReconciliationRequest,
        Wo10ReasonCode,
        Wo10ReconciliationResult,
        Wo10StateCount,
        Wo10ResultBinding,
        Wo10BatchResult,
        CurrentWo10ReconciliationPointer,
        Wo10OperationProvenance,
        Wo10EvidenceReference,
        Wo10CommonFactBindings,
        Wo10EquityEvidenceExtension,
        Wo10IndexEvidenceExtension,
        Wo10McxEvidenceExtension,
        Wo10EvidenceSnapshot,
    )
}

_ENUMS = {
    item.__name__: item
    for item in (
        IntradayAnalysisPhase,
        SemanticDirection,
        IntradayMarketFamily,
        Wo10State,
        Wo10ReasonScope,
        Wo10OperationStage,
        Wo10OperationOutcome,
    )
}


def _artifact_bytes(value: object) -> bytes:
    identity = _artifact_identity(value)
    core = {
        "artifact_type": type(value).__name__,
        "artifact_identity": identity,
        "artifact": _to_wire(value),
    }
    document = {
        **core,
        "document_integrity": _document_identity(core),
    }
    return _encode(document) + b"\n"


def _artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise Wo10PersistenceError("WO10_ARTIFACT_INVALID") from error
    if not isinstance(document, Mapping):
        raise Wo10PersistenceError("WO10_ARTIFACT_INVALID")
    core = {
        "artifact_type": document.get("artifact_type"),
        "artifact_identity": document.get("artifact_identity"),
        "artifact": document.get("artifact"),
    }
    if document.get("document_integrity") != _document_identity(core):
        raise Wo10PersistenceError("WO10_ARTIFACT_INTEGRITY_INVALID")
    try:
        value = _from_wire(core["artifact"])
    except Wo10PersistenceError:
        raise
    except (TypeError, ValueError, Wo10ContractError) as error:
        raise Wo10PersistenceError("WO10_ARTIFACT_INTEGRITY_INVALID") from error
    if (
        type(value).__name__ != core["artifact_type"]
        or _artifact_identity(value) != core["artifact_identity"]
    ):
        raise Wo10PersistenceError("WO10_ARTIFACT_INTEGRITY_INVALID")
    return value


def _artifact_identity(value: object) -> str:
    for name in (
        "integrity_identity",
        "request_identity",
        "snapshot_identity",
        "result_identity",
        "batch_identity",
        "operation_identity",
        "pointer_identity",
    ):
        identity = getattr(value, name, None)
        if _component(identity):
            return identity
    raise Wo10PersistenceError("WO10_ARTIFACT_TYPE_INVALID")


def _to_wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "$type": type(value).__name__,
            "fields": {
                field.name: _to_wire(getattr(value, field.name)) for field in fields(value)
            },
        }
    if isinstance(value, StrEnum):
        return {"$enum": type(value).__name__, "value": value.value}
    if isinstance(value, datetime):
        zone = getattr(value.tzinfo, "key", None)
        return (
            {"$datetime": value.isoformat()}
            if zone is None
            else {"$datetime": value.isoformat(), "$zone": zone}
        )
    if isinstance(value, tuple):
        return {"$tuple": [_to_wire(item) for item in value]}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise Wo10PersistenceError("WO10_ARTIFACT_VALUE_INVALID")


def _from_wire(value: object) -> object:
    if value is None or type(value) in {str, int, bool}:
        return value
    if not isinstance(value, Mapping):
        raise Wo10PersistenceError("WO10_ARTIFACT_VALUE_INVALID")
    if set(value) == {"$datetime"}:
        return datetime.fromisoformat(str(value["$datetime"]))
    if set(value) == {"$datetime", "$zone"}:
        return datetime.fromisoformat(str(value["$datetime"])).astimezone(
            ZoneInfo(str(value["$zone"]))
        )
    if set(value) == {"$tuple"} and isinstance(value["$tuple"], list):
        return tuple(_from_wire(item) for item in value["$tuple"])
    if set(value) == {"$enum", "value"}:
        enum_type = _ENUMS.get(str(value["$enum"]))
        if enum_type is None:
            raise Wo10PersistenceError("WO10_ARTIFACT_VALUE_INVALID")
        return enum_type(value["value"])
    if set(value) == {"$type", "fields"} and isinstance(value["fields"], Mapping):
        cls = _DATACLASSES.get(str(value["$type"]))
        if cls is None or set(value["fields"]) != {field.name for field in fields(cls)}:
            raise Wo10PersistenceError("WO10_ARTIFACT_VALUE_INVALID")
        return cls(**{
            name: _from_wire(item) for name, item in value["fields"].items()
        })
    raise Wo10PersistenceError("WO10_ARTIFACT_VALUE_INVALID")


def _retain_immutable(path: Path, encoded: bytes) -> None:
    if path.exists():
        if _read(path) != encoded:
            raise Wo10PersistenceError("WO10_PERSISTENCE_CONFLICT")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(encoded)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _replace_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(encoded)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise Wo10PersistenceError("WO10_ARTIFACT_UNAVAILABLE") from error


def _document_identity(value: object) -> str:
    return "INTEGRITY-INTRADAY-WO10-DOCUMENT-" + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


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
    "DEFAULT_WO10_ROOT",
    "RestoredWo10State",
    "Wo10PersistenceError",
    "Wo10Store",
]
