"""Append-only persistence for current Intraday WO-12 V2 artifacts."""

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

from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import Wo10PolicyBinding
from kronos.intraday.wo11 import Wo11DownstreamEligibility
from kronos.intraday.wo12 import (
    Wo12ContractError,
    Wo12Handoff,
    Wo12HardGate,
    Wo12OperationOutcome,
    Wo12OperationStage,
)
from kronos.intraday.wo12_v2 import (
    CurrentWo12PointerV2,
    Wo12CriterionIdentityV2,
    Wo12CriterionResultV2,
    Wo12EvidenceV2,
    Wo12OperationProvenanceV2,
    Wo12PolicyBindingV2,
    Wo12RequestV2,
    Wo12ResultV2,
    Wo13EligibilityRecordV2,
    Wo13EligibilityV2,
)
from kronos.validation.kr370 import (
    Kr370AnalyticalClassification,
    Kr370CriterionState,
)


DEFAULT_WO12_V2_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "intraday-v1" / "wo12-kr370-v2"
)


class Wo12V2PersistenceError(Wo12ContractError):
    """Sanitized V2 immutable persistence or restoration failure."""


@dataclass(frozen=True, slots=True)
class RestoredWo12V2State:
    pointer: CurrentWo12PointerV2
    request: Wo12RequestV2
    handoff: Wo12Handoff
    evidence: Wo12EvidenceV2
    result: Wo12ResultV2
    eligibility: Wo13EligibilityRecordV2


class Wo12V2Store:
    """Separate V2 identity store; historical V1 namespace is untouched."""

    def __init__(self, root: Path = DEFAULT_WO12_V2_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("WO12_V2_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_handoff(self, value: Wo12Handoff) -> Path:
        return self._retain("handoffs", value.handoff_identity, value)

    def retain_request(self, value: Wo12RequestV2) -> Path:
        return self._retain("requests", value.request_identity, value)

    def retain_evidence(self, value: Wo12EvidenceV2) -> Path:
        return self._retain("evidence", value.evidence_identity, value)

    def retain_result(self, value: Wo12ResultV2) -> Path:
        return self._retain("results", value.result_identity, value)

    def retain_eligibility(self, value: Wo13EligibilityRecordV2) -> Path:
        return self._retain("eligibility", value.eligibility_identity, value)

    def retain_operation(self, value: Wo12OperationProvenanceV2) -> Path:
        return self._retain("operations", value.operation_identity, value)

    def load_handoff(self, identity: str) -> Wo12Handoff:
        return self._load("handoffs", identity, Wo12Handoff, "handoff_identity")

    def load_request(self, identity: str) -> Wo12RequestV2:
        return self._load("requests", identity, Wo12RequestV2, "request_identity")

    def load_evidence(self, identity: str) -> Wo12EvidenceV2:
        return self._load("evidence", identity, Wo12EvidenceV2, "evidence_identity")

    def load_result(self, identity: str) -> Wo12ResultV2:
        return self._load("results", identity, Wo12ResultV2, "result_identity")

    def load_eligibility(self, identity: str) -> Wo13EligibilityRecordV2:
        return self._load("eligibility", identity, Wo13EligibilityRecordV2, "eligibility_identity")

    def load_operation(self, identity: str) -> Wo12OperationProvenanceV2:
        return self._load("operations", identity, Wo12OperationProvenanceV2, "operation_identity")

    def publish_current(self, value: CurrentWo12PointerV2) -> Path:
        if type(value) is not CurrentWo12PointerV2:
            raise Wo12V2PersistenceError("WO12_V2_POINTER_INVALID")
        path = self._root / "current" / "CURRENT-INTRADAY-WO12-V2.json"
        with self._lock:
            _replace_atomic(path, _artifact_bytes(value))
        return path

    def load_current(self) -> CurrentWo12PointerV2 | None:
        path = self._root / "current" / "CURRENT-INTRADAY-WO12-V2.json"
        if not path.exists():
            return None
        value = _artifact_from_bytes(path.read_bytes())
        if type(value) is not CurrentWo12PointerV2:
            raise Wo12V2PersistenceError("WO12_V2_POINTER_INTEGRITY_INVALID")
        return value

    def restore_current(self) -> RestoredWo12V2State | None:
        pointer = self.load_current()
        if pointer is None:
            return None
        request = self.load_request(pointer.request_identity)
        handoff = self.load_handoff(request.handoff.handoff_identity)
        result = self.load_result(pointer.result_identity)
        evidence = self.load_evidence(result.evidence_identity)
        eligibility = self.load_eligibility(pointer.eligibility_identity)
        if (
            pointer.request_integrity != request.request_integrity
            or request.handoff != handoff
            or pointer.result_integrity != result.result_integrity
            or result.request_identity != request.request_identity
            or result.evidence_integrity != evidence.evidence_integrity
            or pointer.eligibility_integrity != eligibility.eligibility_integrity
            or eligibility.wo12_result_identity != result.result_identity
        ):
            raise Wo12V2PersistenceError("WO12_V2_RESTORATION_BINDING_INVALID")
        return RestoredWo12V2State(pointer, request, handoff, evidence, result, eligibility)

    def _retain(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        with self._lock:
            encoded = _artifact_bytes(value)
            if path.exists():
                if path.read_bytes() != encoded:
                    raise Wo12V2PersistenceError("WO12_V2_IMMUTABLE_CONFLICT")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(encoded)
        return path

    def _load(self, family: str, identity: str, expected: type, identity_name: str):  # type: ignore[no-untyped-def]
        path = self._path(family, identity)
        try:
            value = _artifact_from_bytes(path.read_bytes())
        except OSError as error:
            raise Wo12V2PersistenceError("WO12_V2_ARTIFACT_UNAVAILABLE") from error
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise Wo12V2PersistenceError("WO12_V2_ARTIFACT_INTEGRITY_INVALID")
        return value

    def _path(self, family: str, identity: str) -> Path:
        if family not in {"handoffs", "requests", "evidence", "results", "eligibility", "operations"} or not _component(identity):
            raise Wo12V2PersistenceError("WO12_V2_ARTIFACT_PATH_INVALID")
        return self._root / family / f"{identity}.json"


_DATACLASSES = {item.__name__: item for item in (
    Wo10PolicyBinding,
    Wo12Handoff,
    Wo12PolicyBindingV2,
    Wo12RequestV2,
    Wo12CriterionResultV2,
    Wo12EvidenceV2,
    Wo12ResultV2,
    Wo13EligibilityRecordV2,
    CurrentWo12PointerV2,
    Wo12OperationProvenanceV2,
)}
_ENUMS = {item.__name__: item for item in (
    IntradayAnalysisPhase,
    SemanticDirection,
    IntradayMarketFamily,
    Wo11DownstreamEligibility,
    Wo12CriterionIdentityV2,
    Wo12HardGate,
    Wo13EligibilityV2,
    Wo12OperationStage,
    Wo12OperationOutcome,
    Kr370CriterionState,
    Kr370AnalyticalClassification,
)}


def _artifact_bytes(value: object) -> bytes:
    identity = _artifact_identity(value)
    core = {"artifact_type": type(value).__name__, "artifact_identity": identity, "artifact": _to_wire(value)}
    return _encode({**core, "document_integrity": _document_identity(core)}) + b"\n"


def _artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
        core = {key: document[key] for key in ("artifact_type", "artifact_identity", "artifact")}
        if set(document) != {*core, "document_integrity"} or document["document_integrity"] != _document_identity(core):
            raise ValueError
        value = _from_wire(document["artifact"])
        if type(value).__name__ != document["artifact_type"] or _artifact_identity(value) != document["artifact_identity"]:
            raise ValueError
        return value
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise Wo12V2PersistenceError("WO12_V2_ARTIFACT_INTEGRITY_INVALID") from error


def _artifact_identity(value: object) -> str:
    for name in (
        "handoff_identity", "request_identity", "evidence_identity", "result_identity",
        "eligibility_identity", "pointer_identity", "operation_identity",
    ):
        identity = getattr(value, name, None)
        if type(identity) is str:
            return identity
    raise Wo12V2PersistenceError("WO12_V2_ARTIFACT_IDENTITY_INVALID")


def _to_wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {"__dataclass__": type(value).__name__, "fields": {item.name: _to_wire(getattr(value, item.name)) for item in fields(value)}}
    if isinstance(value, StrEnum):
        return {"__enum__": type(value).__name__, "value": value.value}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, tuple):
        return {"__tuple__": [_to_wire(item) for item in value]}
    if isinstance(value, Mapping):
        return {str(key): _to_wire(item) for key, item in value.items()}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise Wo12V2PersistenceError("WO12_V2_ARTIFACT_ENCODING_INVALID")


def _from_wire(value: object) -> object:
    if type(value) is list:
        return [_from_wire(item) for item in value]
    if type(value) is not dict:
        return value
    if set(value) == {"__datetime__"}:
        return datetime.fromisoformat(value["__datetime__"])
    if set(value) == {"__tuple__"}:
        return tuple(_from_wire(item) for item in value["__tuple__"])
    if set(value) == {"__enum__", "value"}:
        enum = _ENUMS.get(value["__enum__"])
        if enum is None:
            raise ValueError
        return enum(value["value"])
    if set(value) == {"__dataclass__", "fields"}:
        cls = _DATACLASSES.get(value["__dataclass__"])
        raw = value["fields"]
        if cls is None or type(raw) is not dict:
            raise ValueError
        return cls(**{key: _from_wire(item) for key, item in raw.items()})
    return {key: _from_wire(item) for key, item in value.items()}


def _replace_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(path)


def _document_identity(value: object) -> str:
    return sha256(_encode(value)).hexdigest()


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _component(value: object) -> bool:
    return type(value) is str and 2 < len(value) <= 256 and all(item.isalnum() or item in "-_.:" for item in value)


__all__ = ["DEFAULT_WO12_V2_ROOT", "RestoredWo12V2State", "Wo12V2PersistenceError", "Wo12V2Store"]
