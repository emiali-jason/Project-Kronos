"""AD-TVCA-007: immutable local records, without evidence interpretation."""

from dataclasses import dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
import re
from uuid import UUID


class CoreFailureCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    RECORD_NOT_FOUND = "RECORD_NOT_FOUND"
    RECORD_CONFLICT = "RECORD_CONFLICT"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
    STORAGE_ROOT_INVALID = "STORAGE_ROOT_INVALID"
    STORAGE_IO_FAILURE = "STORAGE_IO_FAILURE"


@dataclass(frozen=True, slots=True)
class CoreFailure:
    code: CoreFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not CoreFailureCode:
            raise TypeError("CoreFailure requires CoreFailureCode")


class TvcaCoreError(Exception):
    """A fixed failure code, without raw filesystem or external payloads."""

    def __init__(self, failure: CoreFailure) -> None:
        if type(failure) is not CoreFailure:
            raise TypeError("TvcaCoreError requires CoreFailure")
        self.failure = failure
        super().__init__(failure.code.value)


def _fail(code: CoreFailureCode) -> None:
    raise TvcaCoreError(CoreFailure(code)) from None


class CoreStatus(StrEnum):
    OPEN = "OPEN"
    SEALED = "SEALED"


class IdentityChannel(StrEnum):
    ADAPTER_OBSERVED = "ADAPTER_OBSERVED"
    VISUALLY_OBSERVED = "VISUALLY_OBSERVED"


def _uuid(value: str) -> None:
    try:
        valid = type(value) is str and str(UUID(value)) == value
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        _fail(CoreFailureCode.INVALID_INPUT)


def _revision(value: int) -> None:
    if type(value) is not int or value < 0:
        _fail(CoreFailureCode.INVALID_INPUT)


def _digest(value: str) -> None:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _fail(CoreFailureCode.INVALID_INPUT)


def _identity(value: str) -> None:
    if type(value) is not str or not value or value.isspace() or "\x00" in value:
        _fail(CoreFailureCode.INVALID_INPUT)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        _fail(CoreFailureCode.INVALID_INPUT)


def _timestamp(value: datetime) -> str:
    try:
        if type(value) is not datetime or value.utcoffset() is None:
            _fail(CoreFailureCode.INVALID_INPUT)
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    except (ValueError, OverflowError, TypeError):
        _fail(CoreFailureCode.INVALID_INPUT)


@dataclass(frozen=True, slots=True)
class RecordRef:
    request_id: str
    revision: int
    sha256: str

    def __post_init__(self) -> None:
        _uuid(self.request_id)
        _revision(self.revision)
        _digest(self.sha256)


@dataclass(frozen=True, slots=True)
class CoreRecord:
    format_version: int
    request_id: str
    revision: int
    previous_record_sha256: str | None
    status: CoreStatus
    expected_subject_identity: str
    adapter_observed_identity: str | None
    visually_observed_identity: str | None
    recorded_at: datetime

    def __post_init__(self) -> None:
        if type(self.format_version) is not int or self.format_version != 1:
            _fail(CoreFailureCode.INVALID_INPUT)
        _uuid(self.request_id)
        _revision(self.revision)
        if type(self.status) is not CoreStatus:
            _fail(CoreFailureCode.INVALID_INPUT)
        _identity(self.expected_subject_identity)
        for value in (self.adapter_observed_identity, self.visually_observed_identity):
            if value is not None:
                _identity(value)
        _timestamp(self.recorded_at)
        if self.revision == 0:
            if (self.previous_record_sha256 is not None
                    or self.status is not CoreStatus.OPEN
                    or self.adapter_observed_identity is not None
                    or self.visually_observed_identity is not None):
                _fail(CoreFailureCode.INVALID_INPUT)
        else:
            _digest(self.previous_record_sha256)

    @property
    def ref(self) -> RecordRef:
        return RecordRef(self.request_id, self.revision, sha256(_canonical(self)).hexdigest())


def _canonical(record: CoreRecord) -> bytes:
    payload = {field.name: getattr(record, field.name) for field in fields(CoreRecord)}
    payload["recorded_at"] = _timestamp(record.recorded_at)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _decode(data: bytes) -> CoreRecord:
    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs)
        if type(payload) is not dict or set(payload) != {f.name for f in fields(CoreRecord)}:
            raise ValueError("fields")
        payload["status"] = CoreStatus(payload["status"])
        payload["recorded_at"] = datetime.fromisoformat(payload["recorded_at"])
        record = CoreRecord(**payload)
        if _canonical(record) != data:
            raise ValueError("noncanonical")
        return record
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, TvcaCoreError):
        _fail(CoreFailureCode.INTEGRITY_FAILURE)


def _validate_successor(previous: CoreRecord, successor: CoreRecord) -> None:
    if successor.recorded_at.astimezone(UTC) < previous.recorded_at.astimezone(UTC):
        _fail(CoreFailureCode.INVALID_INPUT)
    if (previous.status is not CoreStatus.OPEN
            or successor.request_id != previous.request_id
            or successor.revision != previous.revision + 1
            or successor.previous_record_sha256 != previous.ref.sha256
            or successor.expected_subject_identity != previous.expected_subject_identity):
        _fail(CoreFailureCode.INVALID_TRANSITION)
    before = (previous.adapter_observed_identity, previous.visually_observed_identity)
    after = (successor.adapter_observed_identity, successor.visually_observed_identity)
    if successor.status is CoreStatus.SEALED:
        valid = before == after
    else:
        changed = [(a, b) for a, b in zip(before, after) if a != b]
        valid = len(changed) == 1 and changed[0][0] is None and changed[0][1] is not None
    if not valid:
        _fail(CoreFailureCode.INVALID_TRANSITION)
