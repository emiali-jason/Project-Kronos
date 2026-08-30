"""Append-only persistence for Intraday WO-11 promotion publications."""

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
from kronos.intraday.wo10 import Wo10PolicyBinding, Wo10ReasonCode, Wo10ReasonScope, Wo10State
from kronos.intraday.wo11 import (
    CurrentWo11PromotionPointer,
    Wo11ContractError,
    Wo11DownstreamEligibility,
    Wo11FamilyCount,
    Wo11Member,
    Wo11MemberBinding,
    Wo11OperationOutcome,
    Wo11OperationProvenance,
    Wo11OperationStage,
    Wo11PromotionPublication,
    Wo11PublicationRequest,
    Wo11SourceBatchBinding,
    Wo11StateCount,
    create_wo11_handoff_reference,
)


DEFAULT_WO11_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "intraday-v1" / "wo11-promotion-publication-v1"
)


class Wo11PersistenceError(Wo11ContractError):
    """Sanitized immutable persistence or restoration failure."""


@dataclass(frozen=True, slots=True)
class RestoredWo11State:
    pointer: CurrentWo11PromotionPointer
    request: Wo11PublicationRequest
    publication: Wo11PromotionPublication
    members: tuple[Wo11Member, ...]


class Wo11Store:
    """Explicit identities plus one final-write current publication pointer."""

    def __init__(self, root: Path = DEFAULT_WO11_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("WO11_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_request(self, value: Wo11PublicationRequest) -> Path:
        return self._retain("requests", value.request_identity, value)

    def retain_member(self, value: Wo11Member) -> Path:
        return self._retain("members", value.member_identity, value)

    def retain_publication(self, value: Wo11PromotionPublication) -> Path:
        return self._retain("publications", value.publication_identity, value)

    def retain_operation(self, value: Wo11OperationProvenance) -> Path:
        return self._retain("operations", value.operation_identity, value)

    def load_request(self, identity: str) -> Wo11PublicationRequest:
        return self._load("requests", identity, Wo11PublicationRequest, "request_identity")

    def load_member(self, identity: str) -> Wo11Member:
        return self._load("members", identity, Wo11Member, "member_identity")

    def load_publication(self, identity: str) -> Wo11PromotionPublication:
        return self._load(
            "publications", identity, Wo11PromotionPublication, "publication_identity"
        )

    def load_operation(self, identity: str) -> Wo11OperationProvenance:
        return self._load("operations", identity, Wo11OperationProvenance, "operation_identity")

    def publish_current(self, value: CurrentWo11PromotionPointer) -> Path:
        if type(value) is not CurrentWo11PromotionPointer:
            raise Wo11PersistenceError("WO11_POINTER_INVALID")
        path = self._root / "current" / "CURRENT-INTRADAY-WO11-V1.json"
        with self._lock:
            _replace_atomic(path, _artifact_bytes(value))
        return path

    def load_current(self) -> CurrentWo11PromotionPointer | None:
        path = self._root / "current" / "CURRENT-INTRADAY-WO11-V1.json"
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if type(value) is not CurrentWo11PromotionPointer:
            raise Wo11PersistenceError("WO11_POINTER_INTEGRITY_INVALID")
        return value

    def restore_current(self) -> RestoredWo11State | None:
        pointer = self.load_current()
        if pointer is None:
            return None
        publication = self.load_publication(pointer.publication_identity)
        request = self.load_request(publication.request_identity)
        members = tuple(self.load_member(item.member_identity) for item in publication.member_bindings)
        if (
            pointer.publication_integrity != publication.publication_integrity
            or pointer.source_batches != publication.source_batches
            or pointer.eligible_member_identities != publication.eligible_member_identities
            or pointer.state_counts != publication.state_counts
            or request.request_integrity != publication.request_integrity
            or request.source_batches != publication.source_batches
            or any(
                member.member_identity != binding.member_identity
                or member.member_integrity != binding.member_integrity
                or member.canonical_subject_identity != binding.canonical_subject_identity
                or member.market_family is not binding.market_family
                for member, binding in zip(members, publication.member_bindings, strict=True)
            )
            or tuple(sorted(
                member.member_identity for member in members
                if member.downstream_eligibility
                is Wo11DownstreamEligibility.ELIGIBLE_FOR_DOWNSTREAM_HANDOFF
            )) != publication.eligible_member_identities
        ):
            raise Wo11PersistenceError("WO11_RESTORATION_BINDING_INVALID")
        return RestoredWo11State(pointer, request, publication, members)

    def load_handoff(self, publication_identity: str, member_identity: str):  # type: ignore[no-untyped-def]
        """Load an exact eligible member; never select latest or by symbol."""

        publication = self.load_publication(publication_identity)
        member = self.load_member(member_identity)
        return create_wo11_handoff_reference(publication, member)

    def _retain(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        with self._lock:
            _retain_immutable(path, _artifact_bytes(value))
        return path

    def _load(self, family: str, identity: str, expected: type, identity_name: str):  # type: ignore[no-untyped-def]
        value = _artifact_from_bytes(_read(self._path(family, identity)))
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise Wo11PersistenceError("WO11_ARTIFACT_INTEGRITY_INVALID")
        return value

    def _path(self, family: str, identity: str) -> Path:
        if family not in {"requests", "members", "publications", "operations"} or not _component(identity):
            raise Wo11PersistenceError("WO11_ARTIFACT_PATH_INVALID")
        return self._root / family / f"{identity}.json"


_DATACLASSES = {item.__name__: item for item in (
    Wo10PolicyBinding,
    Wo10ReasonCode,
    Wo11SourceBatchBinding,
    Wo11PublicationRequest,
    Wo11Member,
    Wo11FamilyCount,
    Wo11StateCount,
    Wo11MemberBinding,
    Wo11PromotionPublication,
    CurrentWo11PromotionPointer,
    Wo11OperationProvenance,
)}

_ENUMS = {item.__name__: item for item in (
    IntradayAnalysisPhase,
    SemanticDirection,
    IntradayMarketFamily,
    Wo10ReasonScope,
    Wo10State,
    Wo11DownstreamEligibility,
    Wo11OperationStage,
    Wo11OperationOutcome,
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
        raise Wo11PersistenceError("WO11_ARTIFACT_INVALID") from error
    if not isinstance(document, Mapping):
        raise Wo11PersistenceError("WO11_ARTIFACT_INVALID")
    core = {
        "artifact_type": document.get("artifact_type"),
        "artifact_identity": document.get("artifact_identity"),
        "artifact": document.get("artifact"),
    }
    if document.get("document_integrity") != _document_identity(core):
        raise Wo11PersistenceError("WO11_ARTIFACT_INTEGRITY_INVALID")
    try:
        value = _from_wire(core["artifact"])
    except (TypeError, ValueError, Wo11ContractError) as error:
        raise Wo11PersistenceError("WO11_ARTIFACT_INTEGRITY_INVALID") from error
    if type(value).__name__ != core["artifact_type"] or _artifact_identity(value) != core["artifact_identity"]:
        raise Wo11PersistenceError("WO11_ARTIFACT_INTEGRITY_INVALID")
    return value


def _artifact_identity(value: object) -> str:
    for name in (
        "request_identity", "member_identity", "publication_identity",
        "operation_identity", "pointer_identity",
    ):
        identity = getattr(value, name, None)
        if _component(identity):
            return identity
    raise Wo11PersistenceError("WO11_ARTIFACT_TYPE_INVALID")


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
    if isinstance(value, tuple):
        return {"$tuple": [_to_wire(item) for item in value]}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise Wo11PersistenceError("WO11_ARTIFACT_VALUE_INVALID")


def _from_wire(value: object) -> object:
    if value is None or type(value) in {str, int, bool}:
        return value
    if not isinstance(value, Mapping):
        raise Wo11PersistenceError("WO11_ARTIFACT_VALUE_INVALID")
    if set(value) == {"$datetime"}:
        return datetime.fromisoformat(str(value["$datetime"]))
    if set(value) == {"$datetime", "$zone"}:
        return datetime.fromisoformat(str(value["$datetime"])).astimezone(ZoneInfo(str(value["$zone"])))
    if set(value) == {"$tuple"} and isinstance(value["$tuple"], list):
        return tuple(_from_wire(item) for item in value["$tuple"])
    if set(value) == {"$enum", "value"}:
        enum_type = _ENUMS.get(str(value["$enum"]))
        if enum_type is None:
            raise Wo11PersistenceError("WO11_ARTIFACT_VALUE_INVALID")
        return enum_type(value["value"])
    if set(value) == {"$type", "fields"} and isinstance(value["fields"], Mapping):
        cls = _DATACLASSES.get(str(value["$type"]))
        if cls is None or set(value["fields"]) != {field.name for field in fields(cls)}:
            raise Wo11PersistenceError("WO11_ARTIFACT_VALUE_INVALID")
        return cls(**{name: _from_wire(item) for name, item in value["fields"].items()})
    raise Wo11PersistenceError("WO11_ARTIFACT_VALUE_INVALID")


def _retain_immutable(path: Path, encoded: bytes) -> None:
    if path.exists():
        if _read(path) != encoded:
            raise Wo11PersistenceError("WO11_PERSISTENCE_CONFLICT")
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
        raise Wo11PersistenceError("WO11_ARTIFACT_UNAVAILABLE") from error


def _document_identity(value: object) -> str:
    return "INTEGRITY-INTRADAY-WO11-DOCUMENT-" + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _component(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip() and value not in {".", ".."} and "/" not in value and "\\" not in value


__all__ = ["DEFAULT_WO11_ROOT", "RestoredWo11State", "Wo11PersistenceError", "Wo11Store"]
