"""Append-only explicit-identity persistence for Intraday WO-14."""

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

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import Wo13GeometryAvailability
from kronos.intraday.wo13_handoff import Wo13SetupFamily
from kronos.intraday.wo14 import (
    CurrentWo14Pointer,
    Wo14AlertSeverity,
    Wo14CalculationProvenance,
    Wo14CapitalReference,
    Wo14ContractError,
    Wo14FieldAvailability,
    Wo14FieldAvailabilityRecord,
    Wo14InstrumentEconomics,
    Wo14InvalidObservationProvenance,
    Wo14MarginContext,
    Wo14ObservationRequest,
    Wo14ObservationState,
    Wo14OperationOutcome,
    Wo14OperationProvenance,
    Wo14OperationStage,
    Wo14PlanBinding,
    Wo14PolicyBinding,
    Wo14PortfolioRiskSnapshot,
    Wo14QuantitySemantics,
    Wo14ReferenceQuantity,
    Wo14RiskField,
    Wo14RiskObservation,
    Wo14SupersessionLineage,
    Wo14UnitSemantics,
)


DEFAULT_WO14_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "intraday-v1" / "wo14-risk-observation-v1"
)


class Wo14PersistenceError(Wo14ContractError):
    """Sanitized WO-14 immutable-store or restoration failure."""


@dataclass(frozen=True, slots=True)
class RestoredWo14State:
    pointer: CurrentWo14Pointer
    request: Wo14ObservationRequest
    observation: Wo14RiskObservation
    operation: Wo14OperationProvenance
    supersession: Wo14SupersessionLineage | None
    latest_failure: Wo14InvalidObservationProvenance | None


class Wo14Store:
    """Dedicated append-only observation store and separate current pointers."""

    def __init__(self, root: Path = DEFAULT_WO14_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("WO14_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_request(self, value: Wo14ObservationRequest) -> Path:
        return self._retain("requests", value.request_identity, value)

    def retain_observation(self, value: Wo14RiskObservation) -> Path:
        return self._retain("observations", value.observation_identity, value)

    def retain_operation(self, value: Wo14OperationProvenance) -> Path:
        return self._retain("operations", value.operation_identity, value)

    def retain_invalid(self, value: Wo14InvalidObservationProvenance) -> Path:
        return self._retain("invalid", value.invalid_identity, value)

    def retain_supersession(self, value: Wo14SupersessionLineage) -> Path:
        return self._retain("supersessions", value.lineage_identity, value)

    def load_request(self, identity: str) -> Wo14ObservationRequest:
        return self._load("requests", identity, Wo14ObservationRequest, "request_identity")

    def load_observation(self, identity: str) -> Wo14RiskObservation:
        return self._load(
            "observations", identity, Wo14RiskObservation, "observation_identity"
        )

    def load_operation(self, identity: str) -> Wo14OperationProvenance:
        return self._load(
            "operations", identity, Wo14OperationProvenance, "operation_identity"
        )

    def load_invalid(self, identity: str) -> Wo14InvalidObservationProvenance:
        return self._load(
            "invalid", identity, Wo14InvalidObservationProvenance, "invalid_identity"
        )

    def load_supersession(self, identity: str) -> Wo14SupersessionLineage:
        return self._load(
            "supersessions", identity, Wo14SupersessionLineage, "lineage_identity"
        )

    def publish_current(self, value: CurrentWo14Pointer) -> Path:
        if type(value) is not CurrentWo14Pointer:
            raise Wo14PersistenceError("WO14_CURRENT_POINTER_INVALID")
        path = self._root / "current" / "CURRENT-INTRADAY-WO14-V1.json"
        with self._lock:
            self._retain("current", value.pointer_identity, value)
            _replace_atomic(path, _artifact_bytes(value))
        return path

    def publish_latest_failure(self, value: Wo14InvalidObservationProvenance) -> Path:
        if type(value) is not Wo14InvalidObservationProvenance:
            raise Wo14PersistenceError("WO14_INVALID_PROVENANCE_INVALID")
        path = self._root / "current" / "LATEST-WO14-FAILURE-V1.json"
        with self._lock:
            self.retain_invalid(value)
            _replace_atomic(path, _artifact_bytes(value))
        return path

    def load_current(self) -> CurrentWo14Pointer | None:
        path = self._root / "current" / "CURRENT-INTRADAY-WO14-V1.json"
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if type(value) is not CurrentWo14Pointer:
            raise Wo14PersistenceError("WO14_CURRENT_POINTER_INTEGRITY_INVALID")
        return value

    def load_latest_failure(self) -> Wo14InvalidObservationProvenance | None:
        path = self._root / "current" / "LATEST-WO14-FAILURE-V1.json"
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if type(value) is not Wo14InvalidObservationProvenance:
            raise Wo14PersistenceError("WO14_FAILURE_POINTER_INTEGRITY_INVALID")
        return value

    def restore_current(self) -> RestoredWo14State | None:
        pointer = self.load_current()
        if pointer is None:
            return None
        request = self.load_request(pointer.request_identity)
        observation = self.load_observation(pointer.observation_identity)
        operation = self.load_operation(pointer.operation_identity)
        supersession = (
            None if pointer.supersession_lineage_identity is None
            else self.load_supersession(pointer.supersession_lineage_identity)
        )
        latest_failure = self.load_latest_failure()
        if (
            request.request_integrity != pointer.request_integrity
            or observation.observation_integrity != pointer.observation_integrity
            or observation.request_identity != request.request_identity
            or observation.plan_binding.trade_plan_identity
            != pointer.trade_plan_identity
            or observation.plan_binding.trade_plan_integrity
            != pointer.trade_plan_integrity
            or observation.plan_binding.canonical_subject_identity
            != pointer.canonical_subject_identity
            or observation.plan_binding.market_family is not pointer.market_family
            or observation.state is not pointer.state
            or observation.policy != pointer.policy
            or operation.operation_integrity != pointer.operation_integrity
            or operation.outcome is not Wo14OperationOutcome.COMPLETED
            or operation.observation_identity != observation.observation_identity
            or supersession is not None
            and supersession.successor_observation_identity
            != observation.observation_identity
        ):
            raise Wo14PersistenceError("WO14_RESTORATION_BINDING_INVALID")
        return RestoredWo14State(
            pointer, request, observation, operation, supersession, latest_failure
        )

    def _retain(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        encoded = _artifact_bytes(value)
        with self._lock:
            if path.exists():
                if _read(path) != encoded:
                    raise Wo14PersistenceError("WO14_IMMUTABLE_CONFLICT")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(encoded)
        return path

    def _load(
        self, family: str, identity: str, expected: type, identity_name: str
    ):  # type: ignore[no-untyped-def]
        value = _artifact_from_bytes(_read(self._path(family, identity)))
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise Wo14PersistenceError("WO14_ARTIFACT_INTEGRITY_INVALID")
        return value

    def _path(self, family: str, identity: str) -> Path:
        if family not in {
            "requests", "observations", "operations", "invalid",
            "supersessions", "current",
        } or not _component(identity):
            raise Wo14PersistenceError("WO14_ARTIFACT_PATH_INVALID")
        return self._root / family / f"{identity}.json"


_DATACLASSES = {item.__name__: item for item in (
    Wo14PolicyBinding, Wo14PlanBinding, Wo14ReferenceQuantity,
    Wo14InstrumentEconomics, Wo14CapitalReference, Wo14PortfolioRiskSnapshot,
    Wo14MarginContext, Wo14ObservationRequest, Wo14FieldAvailabilityRecord,
    Wo14CalculationProvenance, Wo14RiskObservation, Wo14OperationProvenance,
    Wo14InvalidObservationProvenance, Wo14SupersessionLineage,
    CurrentWo14Pointer,
)}
_ENUMS = {item.__name__: item for item in (
    SemanticDirection, IntradayMarketFamily, Wo13SetupFamily,
    Wo13GeometryAvailability, Wo14ObservationState, Wo14AlertSeverity,
    Wo14FieldAvailability, Wo14RiskField, Wo14QuantitySemantics,
    Wo14UnitSemantics, Wo14OperationStage, Wo14OperationOutcome,
)}


def _artifact_bytes(value: object) -> bytes:
    core = {
        "artifact_type": type(value).__name__,
        "artifact_identity": _artifact_identity(value),
        "artifact": _to_wire(value),
    }
    return _encode({
        **core, "document_integrity": sha256(_encode(core)).hexdigest()
    }) + b"\n"


def _artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
        core = {
            key: document[key]
            for key in ("artifact_type", "artifact_identity", "artifact")
        }
        if (
            set(document) != {*core, "document_integrity"}
            or document["document_integrity"] != sha256(_encode(core)).hexdigest()
        ):
            raise ValueError
        value = _from_wire(document["artifact"])
        if (
            type(value).__name__ != document["artifact_type"]
            or _artifact_identity(value) != document["artifact_identity"]
        ):
            raise ValueError
        return value
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise Wo14PersistenceError("WO14_ARTIFACT_INTEGRITY_INVALID") from error


def _artifact_identity(value: object) -> str:
    for name in (
        "request_identity", "observation_identity", "operation_identity",
        "invalid_identity", "lineage_identity", "pointer_identity",
    ):
        identity = getattr(value, name, None)
        if type(identity) is str:
            return identity
    raise Wo14PersistenceError("WO14_ARTIFACT_IDENTITY_INVALID")


def _to_wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "__dataclass__": type(value).__name__,
            "fields": {
                item.name: _to_wire(getattr(value, item.name))
                for item in fields(value)
            },
        }
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
    raise Wo14PersistenceError("WO14_ARTIFACT_ENCODING_INVALID")


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
        raise Wo14PersistenceError("WO14_ARTIFACT_UNAVAILABLE") from error


def _replace_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(path)


def _encode(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def _component(value: object) -> bool:
    return (
        type(value) is str
        and 2 < len(value) <= 256
        and all(item.isalnum() or item in "-_.:" for item in value)
    )


__all__ = [
    "DEFAULT_WO14_ROOT", "RestoredWo14State", "Wo14PersistenceError",
    "Wo14Store",
]
