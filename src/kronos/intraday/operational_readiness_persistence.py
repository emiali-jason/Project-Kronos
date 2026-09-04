"""Append-only persistence for WO-B operational-readiness review snapshots."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from typing import Mapping, Sequence
from uuid import uuid4

from kronos.intraday.operational_readiness import (
    WO_B_CONTRACT_VERSION,
    WO_B_POLICY_IDENTITY,
    WO_B_POLICY_VERSION,
    WoBClassificationBasis,
    WoBContractError,
    WoBOperationalReviewSnapshot,
    WoBPolicyBinding,
    WoBReviewClassification,
    WoBReviewItem,
    WoBSourceArtifactReference,
    WoBSourceBoundary,
    canonical_document_bytes,
)
from kronos.intraday.universe import IntradayMarketFamily


DEFAULT_WO_B_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "intraday-v1"
    / "wo-b-operational-readiness-review-v1"
)
WO_B_CURRENT_POINTER_IDENTITY = (
    "KRONOS-INTRADAY-OPERATIONAL-READINESS-CURRENT-POINTER-V1"
)
WO_B_FAILURE_IDENTITY = (
    "KRONOS-INTRADAY-OPERATIONAL-READINESS-FAILURE-V1"
)


class WoBPersistenceError(WoBContractError):
    """Sanitized WO-B persistence or restoration failure."""


class WoBFailureStage(StrEnum):
    SNAPSHOT_VALIDATION = "SNAPSHOT_VALIDATION"
    SOURCE_BINDING = "SOURCE_BINDING"
    PERSISTENCE = "PERSISTENCE"
    POINTER_PUBLICATION = "POINTER_PUBLICATION"
    RESTORATION = "RESTORATION"


@dataclass(frozen=True, slots=True)
class WoBReviewFailure:
    failure_identity: str
    failure_integrity: str
    candidate_identity: str
    analysis_run_identity: str | None
    stage: WoBFailureStage
    reason: str
    failed_at: datetime
    source_identities: tuple[str, ...]
    policy_identity: str = WO_B_POLICY_IDENTITY
    policy_version: str = WO_B_POLICY_VERSION
    schema_identity: str = WO_B_FAILURE_IDENTITY
    schema_version: str = WO_B_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "failure_identity", "failure_integrity")
        if (
            not _text(self.candidate_identity)
            or not _optional_text(self.analysis_run_identity)
            or type(self.stage) is not WoBFailureStage
            or not _code(self.reason)
            or not _aware(self.failed_at)
            or any(not _text(item) for item in self.source_identities)
            or self.policy_identity != WO_B_POLICY_IDENTITY
            or self.policy_version != WO_B_POLICY_VERSION
            or self.schema_identity != WO_B_FAILURE_IDENTITY
            or self.schema_version != WO_B_CONTRACT_VERSION
            or self.failure_identity
            != _identity("INTRADAY-WO-B-FAILURE-", values)
            or self.failure_integrity
            != _identity("INTEGRITY-INTRADAY-WO-B-FAILURE-", values)
        ):
            raise WoBPersistenceError("WO_B_FAILURE_INVALID")


@dataclass(frozen=True, slots=True)
class CurrentWoBPointer:
    pointer_identity: str
    pointer_integrity: str
    candidate_identity: str
    analysis_run_identity: str
    review_snapshot_identity: str
    snapshot_integrity_hash: str
    review_boundary: datetime
    published_at: datetime
    policy_identity: str = WO_B_POLICY_IDENTITY
    policy_version: str = WO_B_POLICY_VERSION
    schema_identity: str = WO_B_CURRENT_POINTER_IDENTITY
    schema_version: str = WO_B_CONTRACT_VERSION
    semantic_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "pointer_identity", "pointer_integrity")
        if (
            not _texts(
                (
                    self.candidate_identity,
                    self.analysis_run_identity,
                    self.review_snapshot_identity,
                    self.snapshot_integrity_hash,
                )
            )
            or not _aware(self.review_boundary)
            or not _aware(self.published_at)
            or self.published_at < self.review_boundary
            or self.policy_identity != WO_B_POLICY_IDENTITY
            or self.policy_version != WO_B_POLICY_VERSION
            or self.schema_identity != WO_B_CURRENT_POINTER_IDENTITY
            or self.schema_version != WO_B_CONTRACT_VERSION
            or self.semantic_authority is not False
            or self.pointer_identity
            != _identity("CURRENT-INTRADAY-WO-B-", values)
            or self.pointer_integrity
            != _identity("INTEGRITY-CURRENT-INTRADAY-WO-B-", values)
        ):
            raise WoBPersistenceError("WO_B_CURRENT_POINTER_INVALID")


@dataclass(frozen=True, slots=True)
class RestoredWoBState:
    pointer: CurrentWoBPointer
    snapshot: WoBOperationalReviewSnapshot
    latest_failure: WoBReviewFailure | None


def create_wo_b_failure(
    *,
    candidate_identity: str,
    analysis_run_identity: str | None,
    stage: WoBFailureStage,
    reason: str,
    failed_at: datetime,
    source_identities: tuple[str, ...] = (),
) -> WoBReviewFailure:
    values = {
        "candidate_identity": candidate_identity,
        "analysis_run_identity": analysis_run_identity,
        "stage": stage,
        "reason": reason,
        "failed_at": failed_at,
        "source_identities": source_identities,
        "policy_identity": WO_B_POLICY_IDENTITY,
        "policy_version": WO_B_POLICY_VERSION,
        "schema_identity": WO_B_FAILURE_IDENTITY,
        "schema_version": WO_B_CONTRACT_VERSION,
    }
    return WoBReviewFailure(
        failure_identity=_identity("INTRADAY-WO-B-FAILURE-", values),
        failure_integrity=_identity(
            "INTEGRITY-INTRADAY-WO-B-FAILURE-", values
        ),
        **values,
    )


def create_current_wo_b_pointer(
    snapshot: WoBOperationalReviewSnapshot,
) -> CurrentWoBPointer:
    values = {
        "candidate_identity": snapshot.candidate_identity,
        "analysis_run_identity": snapshot.analysis_run_lineage[-1],
        "review_snapshot_identity": snapshot.review_snapshot_identity,
        "snapshot_integrity_hash": snapshot.snapshot_integrity_hash,
        "review_boundary": snapshot.review_boundary,
        "published_at": snapshot.created_at,
        "policy_identity": WO_B_POLICY_IDENTITY,
        "policy_version": WO_B_POLICY_VERSION,
        "schema_identity": WO_B_CURRENT_POINTER_IDENTITY,
        "schema_version": WO_B_CONTRACT_VERSION,
        "semantic_authority": False,
    }
    return CurrentWoBPointer(
        pointer_identity=_identity("CURRENT-INTRADAY-WO-B-", values),
        pointer_integrity=_identity(
            "INTEGRITY-CURRENT-INTRADAY-WO-B-", values
        ),
        **values,
    )


class WoBStore:
    """Product-local immutable history with atomic candidate projections."""

    _FAMILIES = frozenset({"snapshots", "current-snapshots", "failures"})

    def __init__(self, root: Path = DEFAULT_WO_B_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("WO_B_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_snapshot(self, value: WoBOperationalReviewSnapshot) -> Path:
        if type(value) is not WoBOperationalReviewSnapshot:
            raise WoBPersistenceError("WO_B_REVIEW_SNAPSHOT_INVALID")
        return self._retain("snapshots", value.review_snapshot_identity, value)

    def load_snapshot(self, identity: str) -> WoBOperationalReviewSnapshot:
        value = self._load("snapshots", identity)
        if (
            type(value) is not WoBOperationalReviewSnapshot
            or value.review_snapshot_identity != identity
        ):
            raise WoBPersistenceError("WO_B_ARTIFACT_INTEGRITY_INVALID")
        return value

    def replay_snapshot(
        self, value: WoBOperationalReviewSnapshot
    ) -> WoBOperationalReviewSnapshot:
        self.retain_snapshot(value)
        return self.load_snapshot(value.review_snapshot_identity)

    def publish_current(
        self, value: WoBOperationalReviewSnapshot
    ) -> CurrentWoBPointer:
        if type(value) is not WoBOperationalReviewSnapshot:
            raise WoBPersistenceError("WO_B_REVIEW_SNAPSHOT_INVALID")
        path = self._current_path(value.candidate_identity)
        with self._lock:
            previous_pointer = self.load_current(value.candidate_identity)
            if previous_pointer is not None:
                if previous_pointer.review_snapshot_identity == value.review_snapshot_identity:
                    if self.restore_current(value.candidate_identity).snapshot != value:
                        raise WoBPersistenceError("WO_B_CURRENT_POINTER_CONFLICT")
                    return previous_pointer
                if value.review_boundary <= previous_pointer.review_boundary:
                    raise WoBPersistenceError("WO_B_CURRENT_SNAPSHOT_NOT_NEWER")
            self.retain_snapshot(value)
            pointer = create_current_wo_b_pointer(value)
            self._retain("current-snapshots", pointer.pointer_identity, pointer)
            self.restore_pointer(pointer)
            previous_bytes = _read(path) if path.exists() else None
            try:
                _replace_atomic(path, _artifact_bytes(pointer))
                if self.load_current(value.candidate_identity) != pointer:
                    raise WoBPersistenceError("WO_B_CURRENT_ALIAS_INVALID")
            except Exception:
                if previous_bytes is None:
                    path.unlink(missing_ok=True)
                else:
                    _replace_atomic(path, previous_bytes)
                raise
            return pointer

    def publish_latest_failure(self, value: WoBReviewFailure) -> Path:
        if type(value) is not WoBReviewFailure:
            raise WoBPersistenceError("WO_B_FAILURE_INVALID")
        path = self._failure_path(value.candidate_identity)
        with self._lock:
            self._retain("failures", value.failure_identity, value)
            _replace_atomic(path, _artifact_bytes(value))
        return path

    def load_current(self, candidate_identity: str) -> CurrentWoBPointer | None:
        path = self._current_path(candidate_identity)
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if (
            type(value) is not CurrentWoBPointer
            or value.candidate_identity != candidate_identity
        ):
            raise WoBPersistenceError("WO_B_CURRENT_POINTER_INTEGRITY_INVALID")
        return value

    def load_latest_failure(
        self, candidate_identity: str
    ) -> WoBReviewFailure | None:
        path = self._failure_path(candidate_identity)
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if (
            type(value) is not WoBReviewFailure
            or value.candidate_identity != candidate_identity
        ):
            raise WoBPersistenceError("WO_B_FAILURE_POINTER_INTEGRITY_INVALID")
        return value

    def restore_pointer(
        self, pointer: CurrentWoBPointer
    ) -> WoBOperationalReviewSnapshot:
        if type(pointer) is not CurrentWoBPointer:
            raise WoBPersistenceError("WO_B_CURRENT_POINTER_INVALID")
        snapshot = self.load_snapshot(pointer.review_snapshot_identity)
        if (
            snapshot.candidate_identity != pointer.candidate_identity
            or snapshot.snapshot_integrity_hash != pointer.snapshot_integrity_hash
            or snapshot.review_boundary != pointer.review_boundary
            or snapshot.created_at != pointer.published_at
            or pointer.analysis_run_identity not in snapshot.analysis_run_lineage
            or snapshot.review_policy_identity != pointer.policy_identity
            or snapshot.review_policy_version != pointer.policy_version
        ):
            raise WoBPersistenceError("WO_B_RESTORATION_BINDING_INVALID")
        return snapshot

    def restore_current(self, candidate_identity: str) -> RestoredWoBState:
        pointer = self.load_current(candidate_identity)
        if pointer is None:
            raise WoBPersistenceError("WO_B_CURRENT_POINTER_UNAVAILABLE")
        return RestoredWoBState(
            pointer=pointer,
            snapshot=self.restore_pointer(pointer),
            latest_failure=self.load_latest_failure(candidate_identity),
        )

    def _retain(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        encoded = _artifact_bytes(value)
        with self._lock:
            _write_new_atomic(path, encoded)
        return path

    def _load(self, family: str, identity: str) -> object:
        return _artifact_from_bytes(_read(self._path(family, identity)))

    def _path(self, family: str, identity: str) -> Path:
        if family not in self._FAMILIES or not _component(identity):
            raise WoBPersistenceError("WO_B_ARTIFACT_PATH_INVALID")
        return self._root / family / f"{identity}.json"

    def _current_path(self, candidate_identity: str) -> Path:
        return self._alias_path("current", "CURRENT-WO-B", candidate_identity)

    def _failure_path(self, candidate_identity: str) -> Path:
        return self._alias_path(
            "latest-failure", "LATEST-WO-B-FAILURE", candidate_identity
        )

    def _alias_path(self, family: str, prefix: str, scope: str) -> Path:
        if not _component(scope):
            raise WoBPersistenceError("WO_B_ARTIFACT_PATH_INVALID")
        digest = sha256(scope.encode("utf-8")).hexdigest().upper()
        return self._root / family / f"{prefix}-{digest}.json"


_DATACLASSES = {
    item.__name__: item
    for item in (
        WoBPolicyBinding,
        WoBSourceArtifactReference,
        WoBReviewItem,
        WoBOperationalReviewSnapshot,
        WoBReviewFailure,
        CurrentWoBPointer,
    )
}
_ENUMS = {
    item.__name__: item
    for item in (
        IntradayMarketFamily,
        WoBReviewClassification,
        WoBClassificationBasis,
        WoBSourceBoundary,
        WoBFailureStage,
    )
}


def _artifact_bytes(value: object) -> bytes:
    core = {
        "artifact_type": type(value).__name__,
        "artifact_identity": _artifact_identity(value),
        "artifact": _to_wire(value),
    }
    return _encode(
        {**core, "document_integrity": sha256(_encode(core)).hexdigest()}
    ) + b"\n"


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
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        WoBContractError,
    ) as error:
        raise WoBPersistenceError("WO_B_ARTIFACT_INTEGRITY_INVALID") from error


def _artifact_identity(value: object) -> str:
    for name in (
        "review_snapshot_identity",
        "pointer_identity",
        "failure_identity",
    ):
        identity = getattr(value, name, None)
        if type(identity) is str:
            return identity
    raise WoBPersistenceError("WO_B_ARTIFACT_IDENTITY_INVALID")


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
        if not _aware(value):
            raise WoBPersistenceError("WO_B_TIMESTAMP_TIMEZONE_REQUIRED")
        return {"__datetime__": value.isoformat()}
    if isinstance(value, tuple):
        return {"__tuple__": [_to_wire(item) for item in value]}
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise WoBPersistenceError("WO_B_ARTIFACT_ENCODING_INVALID")
        return {key: _to_wire(item) for key, item in value.items()}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise WoBPersistenceError("WO_B_ARTIFACT_ENCODING_INVALID")


def _from_wire(value: object) -> object:
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
        if set(raw) != {item.name for item in fields(cls)}:
            raise ValueError
        return cls(**{key: _from_wire(item) for key, item in raw.items()})
    return {key: _from_wire(item) for key, item in value.items()}


def _write_new_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        temporary.write_bytes(encoded)
        try:
            os.link(temporary, path)
        except FileExistsError:
            if _read(path) != encoded:
                raise WoBPersistenceError("WO_B_IMMUTABLE_CONFLICT")
    finally:
        temporary.unlink(missing_ok=True)


def _replace_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        temporary.write_bytes(encoded)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise WoBPersistenceError("WO_B_ARTIFACT_UNAVAILABLE") from error


def _encode(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _without(value: object, *names: str) -> dict[str, object]:
    return {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name not in names
    }


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_document_bytes(value)).hexdigest().upper()


def _component(value: object) -> bool:
    return (
        type(value) is str
        and 2 < len(value) <= 256
        and all(character.isalnum() or character in "-_.:" for character in value)
    )


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(value) for value in values)


def _optional_text(value: object) -> bool:
    return value is None or _text(value)


def _code(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= 160
        and all(
            character.isupper()
            or character.isdigit()
            or character in "_-.:"
            for character in value
        )
    )


__all__ = [
    "DEFAULT_WO_B_ROOT",
    "CurrentWoBPointer",
    "RestoredWoBState",
    "WoBFailureStage",
    "WoBPersistenceError",
    "WoBReviewFailure",
    "WoBStore",
    "create_current_wo_b_pointer",
    "create_wo_b_failure",
]
