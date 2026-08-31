"""Append-only explicit-identity persistence for Intraday WO-13 Slice 6."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from typing import Mapping
from uuid import uuid4

from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.mcx_commissioning import McxCommissioningState
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import (
    CurrentWo13Pointer, Wo13ConstructionRequest, Wo13ContractError,
    Wo13FieldAvailability, Wo13FieldAvailabilityRecord, Wo13GeometryAvailability,
    Wo13GeometryField, Wo13OperationOutcome, Wo13OperationProvenance,
    Wo13OperationStage, Wo13PolicyBinding, Wo13SupersessionLineage,
    Wo13SupersessionReason, Wo13SupersessionReference, Wo13TradePlan,
    Wo13WarningCode,
)
from kronos.intraday.wo13_handoff import Wo13SetupFamily, Wo13Step31Handoff
from kronos.validation.kr370 import Kr370AnalyticalClassification


DEFAULT_WO13_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "intraday-v1" / "wo13-step31-v1"
)


class Wo13PersistenceError(Wo13ContractError):
    """Sanitized immutable-store or restoration failure."""


@dataclass(frozen=True, slots=True)
class RestoredWo13State:
    pointer: CurrentWo13Pointer
    request: Wo13ConstructionRequest
    handoff: Wo13Step31Handoff
    trade_plan: Wo13TradePlan
    operation: Wo13OperationProvenance
    supersession: Wo13SupersessionLineage | None


class Wo13Store:
    """Dedicated WO-13 store with append-only artifacts and one final pointer."""

    def __init__(self, root: Path = DEFAULT_WO13_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("WO13_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_handoff(self, value: Wo13Step31Handoff) -> Path:
        return self._retain("handoffs", value.handoff_identity, value)

    def retain_request(self, value: Wo13ConstructionRequest) -> Path:
        return self._retain("requests", value.request_identity, value)

    def retain_trade_plan(self, value: Wo13TradePlan) -> Path:
        return self._retain("plans", value.trade_plan_identity, value)

    def retain_operation(self, value: Wo13OperationProvenance) -> Path:
        return self._retain("operations", value.operation_identity, value)

    def retain_supersession(self, value: Wo13SupersessionLineage) -> Path:
        return self._retain("supersessions", value.lineage_identity, value)

    def load_handoff(self, identity: str) -> Wo13Step31Handoff:
        return self._load("handoffs", identity, Wo13Step31Handoff, "handoff_identity")

    def load_request(self, identity: str) -> Wo13ConstructionRequest:
        return self._load("requests", identity, Wo13ConstructionRequest, "request_identity")

    def load_trade_plan(self, identity: str) -> Wo13TradePlan:
        return self._load("plans", identity, Wo13TradePlan, "trade_plan_identity")

    def load_operation(self, identity: str) -> Wo13OperationProvenance:
        return self._load("operations", identity, Wo13OperationProvenance, "operation_identity")

    def load_supersession(self, identity: str) -> Wo13SupersessionLineage:
        return self._load("supersessions", identity, Wo13SupersessionLineage, "lineage_identity")

    def publish_current(self, value: CurrentWo13Pointer) -> Path:
        if type(value) is not CurrentWo13Pointer:
            raise Wo13PersistenceError("WO13_CURRENT_POINTER_INVALID")
        path = self._root / "current" / "CURRENT-INTRADAY-WO13-V1.json"
        with self._lock:
            self._retain("current", value.pointer_identity, value)
            _replace_atomic(path, _artifact_bytes(value))
        return path

    def load_current(self) -> CurrentWo13Pointer | None:
        path = self._root / "current" / "CURRENT-INTRADAY-WO13-V1.json"
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if type(value) is not CurrentWo13Pointer:
            raise Wo13PersistenceError("WO13_CURRENT_POINTER_INTEGRITY_INVALID")
        return value

    def restore_current(self) -> RestoredWo13State | None:
        pointer = self.load_current()
        if pointer is None:
            return None
        request = self.load_request(pointer.request_identity)
        handoff = self.load_handoff(pointer.handoff_identity)
        plan = self.load_trade_plan(pointer.trade_plan_identity)
        operation = self.load_operation(pointer.operation_identity)
        supersession = (
            None if pointer.supersession_lineage_identity is None
            else self.load_supersession(pointer.supersession_lineage_identity)
        )
        if (
            request.request_integrity != pointer.request_integrity
            or request.handoff != handoff
            or plan.trade_plan_integrity != pointer.trade_plan_integrity
            or plan.request_identity != request.request_identity
            or plan.source_handoff_identity != handoff.handoff_identity
            or pointer.source_wo12_result_identity != handoff.wo12_result_identity
            or pointer.canonical_subject_identity != handoff.canonical_subject_identity
            or pointer.market_family is not handoff.market_family
            or pointer.direction is not handoff.inherited_direction
            or pointer.setup_family is not handoff.setup_family
            or pointer.analysis_boundary != handoff.analysis_boundary
            or pointer.policy != request.policy
            or operation.operation_integrity != pointer.operation_integrity
            or operation.outcome is not Wo13OperationOutcome.COMPLETED
            or operation.trade_plan_identity != plan.trade_plan_identity
            or supersession is not None
            and supersession.successor_trade_plan_identity != plan.trade_plan_identity
        ):
            raise Wo13PersistenceError("WO13_RESTORATION_BINDING_INVALID")
        return RestoredWo13State(pointer, request, handoff, plan, operation, supersession)

    def _retain(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        encoded = _artifact_bytes(value)
        with self._lock:
            if path.exists():
                if _read(path) != encoded:
                    raise Wo13PersistenceError("WO13_IMMUTABLE_CONFLICT")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(encoded)
        return path

    def _load(self, family: str, identity: str, expected: type, identity_name: str):  # type: ignore[no-untyped-def]
        value = _artifact_from_bytes(_read(self._path(family, identity)))
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise Wo13PersistenceError("WO13_ARTIFACT_INTEGRITY_INVALID")
        return value

    def _path(self, family: str, identity: str) -> Path:
        if family not in {"handoffs", "requests", "plans", "operations", "supersessions", "current"} or not _component(identity):
            raise Wo13PersistenceError("WO13_ARTIFACT_PATH_INVALID")
        return self._root / family / f"{identity}.json"


_DATACLASSES = {item.__name__: item for item in (
    Wo13Step31Handoff, Wo13PolicyBinding, Wo13ConstructionRequest,
    Wo13FieldAvailabilityRecord, Wo13SupersessionReference, Wo13TradePlan,
    Wo13SupersessionLineage, Wo13OperationProvenance, CurrentWo13Pointer,
)}
_ENUMS = {item.__name__: item for item in (
    IntradayAnalysisPhase, SemanticDirection, IntradayMarketFamily,
    McxCommissioningState, Kr370AnalyticalClassification, Wo13SetupFamily,
    Wo13FieldAvailability, Wo13GeometryAvailability, Wo13GeometryField,
    Wo13WarningCode, Wo13OperationStage, Wo13OperationOutcome,
    Wo13SupersessionReason,
)}


def _artifact_bytes(value: object) -> bytes:
    core = {"artifact_type": type(value).__name__, "artifact_identity": _artifact_identity(value), "artifact": _to_wire(value)}
    return _encode({**core, "document_integrity": sha256(_encode(core)).hexdigest()}) + b"\n"


def _artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
        core = {key: document[key] for key in ("artifact_type", "artifact_identity", "artifact")}
        if set(document) != {*core, "document_integrity"} or document["document_integrity"] != sha256(_encode(core)).hexdigest():
            raise ValueError
        value = _from_wire(document["artifact"])
        if type(value).__name__ != document["artifact_type"] or _artifact_identity(value) != document["artifact_identity"]:
            raise ValueError
        return value
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise Wo13PersistenceError("WO13_ARTIFACT_INTEGRITY_INVALID") from error


def _artifact_identity(value: object) -> str:
    for name in ("handoff_identity", "request_identity", "trade_plan_identity", "operation_identity", "lineage_identity", "pointer_identity"):
        identity = getattr(value, name, None)
        if type(identity) is str:
            return identity
    raise Wo13PersistenceError("WO13_ARTIFACT_IDENTITY_INVALID")


def _to_wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {"__dataclass__": type(value).__name__, "fields": {item.name: _to_wire(getattr(value, item.name)) for item in fields(value)}}
    if isinstance(value, StrEnum):
        return {"__enum__": type(value).__name__, "value": value.value}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__decimal__": format(value, "f")}
    if isinstance(value, tuple):
        return {"__tuple__": [_to_wire(item) for item in value]}
    if isinstance(value, Mapping):
        return {str(key): _to_wire(item) for key, item in value.items()}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise Wo13PersistenceError("WO13_ARTIFACT_ENCODING_INVALID")


def _from_wire(value: object) -> object:
    if type(value) is not dict:
        return value
    if set(value) == {"__datetime__"}:
        return datetime.fromisoformat(value["__datetime__"])
    if set(value) == {"__date__"}:
        return date.fromisoformat(value["__date__"])
    if set(value) == {"__decimal__"}:
        return Decimal(value["__decimal__"])
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


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise Wo13PersistenceError("WO13_ARTIFACT_UNAVAILABLE") from error


def _replace_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(path)


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _component(value: object) -> bool:
    return type(value) is str and 2 < len(value) <= 256 and all(item.isalnum() or item in "-_.:" for item in value)


__all__ = ["DEFAULT_WO13_ROOT", "RestoredWo13State", "Wo13PersistenceError", "Wo13Store"]
