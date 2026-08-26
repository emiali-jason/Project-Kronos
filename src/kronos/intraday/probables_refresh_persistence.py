"""Explicit restart metadata for the composed Discovery/Probables refresh."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4


REFRESH_OPERATIONAL_STATE_IDENTITY = (
    "KRONOS-INTRADAY-DISCOVERY-PROBABLES-REFRESH-STATE-V1"
)
REFRESH_OPERATIONAL_STATE_VERSION = "1.0.0"


class RefreshOperationalStateError(ValueError):
    """Sanitized persistence or integrity failure."""


@dataclass(frozen=True, slots=True)
class RefreshOperationalState:
    state_identity: str
    operation_identity: str
    observation_boundary: datetime
    completed_at: datetime
    last_successful_discovery_run_identity: str | None
    last_successful_probables_run_identity: str | None
    current_failure_stage: str | None
    current_failure: str | None
    integrity_identity: str
    schema_identity: str = REFRESH_OPERATIONAL_STATE_IDENTITY
    schema_version: str = REFRESH_OPERATIONAL_STATE_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("state_identity")
        values.pop("integrity_identity")
        if (
            not self.state_identity.startswith("INTRADAY-REFRESH-STATE-")
            or not _text(self.operation_identity)
            or not _aware(self.observation_boundary)
            or not _aware(self.completed_at)
            or self.completed_at < self.observation_boundary
            or any(
                item is not None and not _text(item)
                for item in (
                    self.last_successful_discovery_run_identity,
                    self.last_successful_probables_run_identity,
                    self.current_failure_stage,
                    self.current_failure,
                )
            )
            or (self.current_failure_stage is None) != (self.current_failure is None)
            or self.schema_identity != REFRESH_OPERATIONAL_STATE_IDENTITY
            or self.schema_version != REFRESH_OPERATIONAL_STATE_VERSION
            or self.state_identity != _identity("INTRADAY-REFRESH-STATE-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-REFRESH-STATE-", values)
        ):
            raise RefreshOperationalStateError("INTRADAY_REFRESH_STATE_INVALID")


def create_refresh_operational_state(
    *,
    operation_identity: str,
    observation_boundary: datetime,
    completed_at: datetime,
    last_successful_discovery_run_identity: str | None,
    last_successful_probables_run_identity: str | None,
    current_failure_stage: str | None,
    current_failure: str | None,
) -> RefreshOperationalState:
    values = {
        "operation_identity": operation_identity,
        "observation_boundary": observation_boundary,
        "completed_at": completed_at,
        "last_successful_discovery_run_identity": (
            last_successful_discovery_run_identity
        ),
        "last_successful_probables_run_identity": (
            last_successful_probables_run_identity
        ),
        "current_failure_stage": current_failure_stage,
        "current_failure": current_failure,
        "schema_identity": REFRESH_OPERATIONAL_STATE_IDENTITY,
        "schema_version": REFRESH_OPERATIONAL_STATE_VERSION,
    }
    return RefreshOperationalState(
        state_identity=_identity("INTRADAY-REFRESH-STATE-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-REFRESH-STATE-", values
        ),
        **values,
    )


class RefreshOperationalStateStore:
    """Retain immutable states and one integrity-bound explicit current pointer."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_REFRESH_STATE_ROOT_INVALID")
        self._root = root / "refresh-v1"
        self._lock = RLock()

    def retain(self, value: RefreshOperationalState) -> Path:
        if type(value) is not RefreshOperationalState:
            raise RefreshOperationalStateError("INTRADAY_REFRESH_STATE_INVALID")
        encoded = _encode({"state": _normalize(value)}) + b"\n"
        path = self._root / "states" / f"{value.state_identity}.json"
        pointer_core = {"state_identity": value.state_identity}
        pointer = _encode({
            **pointer_core,
            "integrity": _identity("INTEGRITY-INTRADAY-REFRESH-POINTER-", pointer_core),
        }) + b"\n"
        with self._lock:
            _retain_immutable(path, encoded)
            _replace_atomic(self._root / "current-state.json", pointer)
        return path

    def load_current(self) -> RefreshOperationalState | None:
        pointer_path = self._root / "current-state.json"
        if not pointer_path.exists():
            return None
        try:
            pointer = json.loads(pointer_path.read_bytes())
            core = {"state_identity": pointer["state_identity"]}
            if pointer.get("integrity") != _identity(
                "INTEGRITY-INTRADAY-REFRESH-POINTER-", core
            ):
                raise RefreshOperationalStateError(
                    "INTRADAY_REFRESH_POINTER_INVALID"
                )
            return self.load(state_identity=pointer["state_identity"])
        except (OSError, KeyError, TypeError, ValueError) as error:
            if isinstance(error, RefreshOperationalStateError):
                raise
            raise RefreshOperationalStateError(
                "INTRADAY_REFRESH_POINTER_INVALID"
            ) from error

    def load(self, *, state_identity: str) -> RefreshOperationalState:
        if not _text(state_identity) or not state_identity.startswith(
            "INTRADAY-REFRESH-STATE-"
        ):
            raise RefreshOperationalStateError("INTRADAY_REFRESH_STATE_INVALID")
        path = self._root / "states" / f"{state_identity}.json"
        try:
            document = json.loads(path.read_bytes())
            data = document["state"]
            data["observation_boundary"] = datetime.fromisoformat(
                data["observation_boundary"]
            )
            data["completed_at"] = datetime.fromisoformat(data["completed_at"])
            value = RefreshOperationalState(**data)
        except (OSError, KeyError, TypeError, ValueError) as error:
            if isinstance(error, RefreshOperationalStateError):
                raise
            raise RefreshOperationalStateError(
                "INTRADAY_REFRESH_STATE_UNAVAILABLE"
            ) from error
        if value.state_identity != state_identity:
            raise RefreshOperationalStateError("INTRADAY_REFRESH_STATE_INVALID")
        return value


def _retain_immutable(path: Path, encoded: bytes) -> None:
    if path.exists():
        try:
            if path.read_bytes() != encoded:
                raise RefreshOperationalStateError(
                    "INTRADAY_REFRESH_STATE_CONFLICT"
                )
        except OSError as error:
            raise RefreshOperationalStateError(
                "INTRADAY_REFRESH_STATE_UNAVAILABLE"
            ) from error
        return
    _replace_atomic(path, encoded)


def _replace_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(encoded)
        temporary.replace(path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(_normalize(value))).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {name: _normalize(item) for name, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


__all__ = [
    "REFRESH_OPERATIONAL_STATE_IDENTITY",
    "REFRESH_OPERATIONAL_STATE_VERSION",
    "RefreshOperationalState",
    "RefreshOperationalStateError",
    "RefreshOperationalStateStore",
    "create_refresh_operational_state",
]
