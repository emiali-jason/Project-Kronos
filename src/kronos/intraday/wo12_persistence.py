"""Append-only persistence for Intraday WO-12 KR-370 core artifacts."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
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
from kronos.intraday.wo10 import Wo10PolicyBinding
from kronos.intraday.wo11 import Wo11DownstreamEligibility
from kronos.intraday.wo12 import (
    CurrentWo12Pointer,
    Wo12ContractError,
    Wo12CriterionIdentity,
    Wo12CriterionResult,
    Wo12Evidence,
    Wo12Handoff,
    Wo12HardGate,
    Wo12OperationOutcome,
    Wo12OperationProvenance,
    Wo12OperationStage,
    Wo12PolicyBinding,
    Wo12Request,
    Wo12Result,
    Wo13Eligibility,
    Wo13EligibilityRecord,
)
from kronos.intraday.wo12_facts import Wo12ExtensionMeasurement
from kronos.validation.kr370 import (
    Kr370AnalyticalClassification,
    Kr370CriterionState,
)


DEFAULT_WO12_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "intraday-v1" / "wo12-kr370-v1"
)


class Wo12PersistenceError(Wo12ContractError):
    """Sanitized immutable persistence or restoration failure."""


@dataclass(frozen=True, slots=True)
class RestoredWo12State:
    pointer: CurrentWo12Pointer
    request: Wo12Request
    handoff: Wo12Handoff
    evidence: Wo12Evidence
    result: Wo12Result
    eligibility: Wo13EligibilityRecord
    extension_measurement: Wo12ExtensionMeasurement | None


class Wo12Store:
    """Explicit identity store with one final-write replaceable pointer."""

    def __init__(self, root: Path = DEFAULT_WO12_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("WO12_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_request(self, value: Wo12Request) -> Path:
        return self._retain("requests", value.request_identity, value)

    def retain_handoff(self, value: Wo12Handoff) -> Path:
        return self._retain("handoffs", value.handoff_identity, value)

    def retain_extension_measurement(self, value: Wo12ExtensionMeasurement) -> Path:
        return self._retain("measurements", value.measurement_identity, value)

    def retain_evidence(self, value: Wo12Evidence) -> Path:
        return self._retain("evidence", value.evidence_identity, value)

    def retain_result(self, value: Wo12Result) -> Path:
        return self._retain("results", value.result_identity, value)

    def retain_eligibility(self, value: Wo13EligibilityRecord) -> Path:
        return self._retain("eligibility", value.eligibility_identity, value)

    def retain_operation(self, value: Wo12OperationProvenance) -> Path:
        return self._retain("operations", value.operation_identity, value)

    def load_request(self, identity: str) -> Wo12Request:
        return self._load("requests", identity, Wo12Request, "request_identity")

    def load_handoff(self, identity: str) -> Wo12Handoff:
        return self._load("handoffs", identity, Wo12Handoff, "handoff_identity")

    def load_extension_measurement(self, identity: str) -> Wo12ExtensionMeasurement:
        return self._load(
            "measurements", identity, Wo12ExtensionMeasurement, "measurement_identity"
        )

    def load_evidence(self, identity: str) -> Wo12Evidence:
        return self._load("evidence", identity, Wo12Evidence, "evidence_identity")

    def load_result(self, identity: str) -> Wo12Result:
        return self._load("results", identity, Wo12Result, "result_identity")

    def load_eligibility(self, identity: str) -> Wo13EligibilityRecord:
        return self._load(
            "eligibility", identity, Wo13EligibilityRecord, "eligibility_identity"
        )

    def load_operation(self, identity: str) -> Wo12OperationProvenance:
        return self._load(
            "operations", identity, Wo12OperationProvenance, "operation_identity"
        )

    def publish_current(self, value: CurrentWo12Pointer) -> Path:
        if type(value) is not CurrentWo12Pointer:
            raise Wo12PersistenceError("WO12_POINTER_INVALID")
        path = self._root / "current" / "CURRENT-INTRADAY-WO12-V1.json"
        with self._lock:
            _replace_atomic(path, _artifact_bytes(value))
        return path

    def load_current(self) -> CurrentWo12Pointer | None:
        path = self._root / "current" / "CURRENT-INTRADAY-WO12-V1.json"
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if type(value) is not CurrentWo12Pointer:
            raise Wo12PersistenceError("WO12_POINTER_INTEGRITY_INVALID")
        return value

    def restore_current(self) -> RestoredWo12State | None:
        pointer = self.load_current()
        if pointer is None:
            return None
        request = self.load_request(pointer.request_identity)
        handoff = self.load_handoff(request.handoff.handoff_identity)
        result = self.load_result(pointer.result_identity)
        evidence = self.load_evidence(result.evidence_identity)
        eligibility = self.load_eligibility(pointer.eligibility_identity)
        measurement = (
            None
            if evidence.extension_measurement_identity is None
            else self.load_extension_measurement(evidence.extension_measurement_identity)
        )
        if (
            pointer.request_integrity != request.request_integrity
            or request.handoff != handoff
            or pointer.result_integrity != result.result_integrity
            or result.request_identity != request.request_identity
            or result.request_integrity != request.request_integrity
            or result.handoff_identity != handoff.handoff_identity
            or result.handoff_integrity != handoff.handoff_integrity
            or result.evidence_integrity != evidence.evidence_integrity
            or pointer.eligibility_integrity != eligibility.eligibility_integrity
            or eligibility.wo12_result_identity != result.result_identity
            or eligibility.wo12_result_integrity != result.result_integrity
            or (
                measurement is not None
                and measurement.measurement_integrity
                != evidence.extension_measurement_integrity
            )
        ):
            raise Wo12PersistenceError("WO12_RESTORATION_BINDING_INVALID")
        return RestoredWo12State(
            pointer,
            request,
            handoff,
            evidence,
            result,
            eligibility,
            measurement,
        )

    def _retain(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        with self._lock:
            _retain_immutable(path, _artifact_bytes(value))
        return path

    def _load(
        self,
        family: str,
        identity: str,
        expected: type,
        identity_name: str,
    ):  # type: ignore[no-untyped-def]
        value = _artifact_from_bytes(_read(self._path(family, identity)))
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise Wo12PersistenceError("WO12_ARTIFACT_INTEGRITY_INVALID")
        return value

    def _path(self, family: str, identity: str) -> Path:
        if family not in {
            "requests",
            "handoffs",
            "measurements",
            "evidence",
            "results",
            "eligibility",
            "operations",
        } or not _component(identity):
            raise Wo12PersistenceError("WO12_ARTIFACT_PATH_INVALID")
        return self._root / family / f"{identity}.json"


_DATACLASSES = {item.__name__: item for item in (
    Wo10PolicyBinding,
    Wo12PolicyBinding,
    Wo12Handoff,
    Wo12Request,
    Wo12CriterionResult,
    Wo12ExtensionMeasurement,
    Wo12Evidence,
    Wo12Result,
    Wo13EligibilityRecord,
    CurrentWo12Pointer,
    Wo12OperationProvenance,
)}

_ENUMS = {item.__name__: item for item in (
    IntradayAnalysisPhase,
    SemanticDirection,
    IntradayMarketFamily,
    Wo11DownstreamEligibility,
    Wo12CriterionIdentity,
    Wo12HardGate,
    Wo13Eligibility,
    Wo12OperationStage,
    Wo12OperationOutcome,
    Kr370CriterionState,
    Kr370AnalyticalClassification,
)}


def _artifact_bytes(value: object) -> bytes:
    identity = _artifact_identity(value)
    core = {
        "artifact_type": type(value).__name__,
        "artifact_identity": identity,
        "artifact": _to_wire(value),
    }
    return _encode({**core, "document_integrity": _document_identity(core)}) + b"\n"


def _artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise Wo12PersistenceError("WO12_ARTIFACT_INVALID") from error
    if not isinstance(document, Mapping):
        raise Wo12PersistenceError("WO12_ARTIFACT_INVALID")
    core = {
        "artifact_type": document.get("artifact_type"),
        "artifact_identity": document.get("artifact_identity"),
        "artifact": document.get("artifact"),
    }
    if document.get("document_integrity") != _document_identity(core):
        raise Wo12PersistenceError("WO12_ARTIFACT_INTEGRITY_INVALID")
    try:
        value = _from_wire(core["artifact"])
    except (TypeError, ValueError, Wo12ContractError) as error:
        raise Wo12PersistenceError("WO12_ARTIFACT_INTEGRITY_INVALID") from error
    if (
        type(value).__name__ != core["artifact_type"]
        or _artifact_identity(value) != core["artifact_identity"]
    ):
        raise Wo12PersistenceError("WO12_ARTIFACT_INTEGRITY_INVALID")
    return value


def _artifact_identity(value: object) -> str:
    for name in (
        "request_identity",
        "handoff_identity",
        "measurement_identity",
        "evidence_identity",
        "result_identity",
        "eligibility_identity",
        "operation_identity",
        "pointer_identity",
    ):
        identity = getattr(value, name, None)
        if _component(identity):
            return identity
    raise Wo12PersistenceError("WO12_ARTIFACT_TYPE_INVALID")


def _to_wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {"$type": type(value).__name__, "fields": {
            field.name: _to_wire(getattr(value, field.name)) for field in fields(value)
        }}
    if isinstance(value, StrEnum):
        return {"$enum": type(value).__name__, "value": value.value}
    if isinstance(value, datetime):
        zone = getattr(value.tzinfo, "key", None)
        return {"$datetime": value.isoformat(), **({} if zone is None else {"$zone": zone})}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, tuple):
        return {"$tuple": [_to_wire(item) for item in value]}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise Wo12PersistenceError("WO12_ARTIFACT_VALUE_INVALID")


def _from_wire(value: object) -> object:
    if value is None or type(value) in {str, int, bool}:
        return value
    if not isinstance(value, Mapping):
        raise Wo12PersistenceError("WO12_ARTIFACT_VALUE_INVALID")
    if set(value) == {"$datetime"}:
        return datetime.fromisoformat(str(value["$datetime"]))
    if set(value) == {"$datetime", "$zone"}:
        return datetime.fromisoformat(str(value["$datetime"])).astimezone(
            ZoneInfo(str(value["$zone"]))
        )
    if set(value) == {"$decimal"}:
        return Decimal(str(value["$decimal"]))
    if set(value) == {"$tuple"} and isinstance(value["$tuple"], list):
        return tuple(_from_wire(item) for item in value["$tuple"])
    if set(value) == {"$enum", "value"}:
        enum_type = _ENUMS.get(str(value["$enum"]))
        if enum_type is None:
            raise Wo12PersistenceError("WO12_ARTIFACT_VALUE_INVALID")
        return enum_type(value["value"])
    if set(value) == {"$type", "fields"} and isinstance(value["fields"], Mapping):
        cls = _DATACLASSES.get(str(value["$type"]))
        if cls is None or set(value["fields"]) != {field.name for field in fields(cls)}:
            raise Wo12PersistenceError("WO12_ARTIFACT_VALUE_INVALID")
        return cls(**{
            name: _from_wire(item) for name, item in value["fields"].items()
        })
    raise Wo12PersistenceError("WO12_ARTIFACT_VALUE_INVALID")


def _retain_immutable(path: Path, encoded: bytes) -> None:
    if path.exists():
        if _read(path) != encoded:
            raise Wo12PersistenceError("WO12_PERSISTENCE_CONFLICT")
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
        raise Wo12PersistenceError("WO12_ARTIFACT_UNAVAILABLE") from error


def _document_identity(value: object) -> str:
    return "INTEGRITY-INTRADAY-WO12-DOCUMENT-" + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


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
    "DEFAULT_WO12_ROOT",
    "RestoredWo12State",
    "Wo12PersistenceError",
    "Wo12Store",
]
