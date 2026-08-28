"""Append-only persistence for V2 replay envelopes and failure details."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.probables_v2 import ProbablesV2Error
from kronos.intraday.probables_v2_diagnostics import (
    ProbablesV2FailureDetail,
    ProbablesV2ReplayEnvelope,
)
from kronos.intraday.probables_v2_persistence import _artifact_bytes, _artifact_from_bytes


class ProbablesV2DiagnosticsStore:
    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_PROBABLES_V2_DIAGNOSTICS_ROOT_INVALID")
        self._root = root / "refresh-v2" / "diagnostics"
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_envelope(self, value: ProbablesV2ReplayEnvelope) -> Path:
        if type(value) is not ProbablesV2ReplayEnvelope:
            raise ValueError("INTRADAY_PROBABLES_V2_REPLAY_ENVELOPE_INVALID")
        return self._retain("replay-envelopes", value.envelope_identity, value)

    def load_envelope(self, identity: str) -> ProbablesV2ReplayEnvelope:
        value = self._load("replay-envelopes", identity)
        if type(value) is not ProbablesV2ReplayEnvelope:
            raise ValueError("INTRADAY_PROBABLES_V2_REPLAY_ENVELOPE_INVALID")
        return value

    def retain_failure(self, value: ProbablesV2FailureDetail) -> Path:
        if type(value) is not ProbablesV2FailureDetail:
            raise ValueError("INTRADAY_PROBABLES_V2_FAILURE_DETAIL_INVALID")
        return self._retain("failure-details", value.failure_identity, value)

    def load_failure(self, identity: str) -> ProbablesV2FailureDetail:
        value = self._load("failure-details", identity)
        if type(value) is not ProbablesV2FailureDetail:
            raise ValueError("INTRADAY_PROBABLES_V2_FAILURE_DETAIL_INVALID")
        return value

    def _retain(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        encoded = _artifact_bytes(value)
        with self._lock:
            if path.exists():
                if path.read_bytes() != encoded:
                    raise ValueError("INTRADAY_PROBABLES_V2_DIAGNOSTICS_CONFLICT")
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_bytes(encoded)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        return path

    def _load(self, family: str, identity: str) -> object:
        path = self._path(family, identity)
        try:
            return _artifact_from_bytes(path.read_bytes())
        except OSError as error:
            raise ValueError("INTRADAY_PROBABLES_V2_DIAGNOSTIC_UNAVAILABLE") from error
        except ProbablesV2Error as error:
            raise ValueError("INTRADAY_PROBABLES_V2_DIAGNOSTIC_INVALID") from error

    def _path(self, family: str, identity: str) -> Path:
        if family not in {"replay-envelopes", "failure-details"} or not _component(identity):
            raise ValueError("INTRADAY_PROBABLES_V2_DIAGNOSTIC_IDENTITY_INVALID")
        return self._root / family / f"{identity}.json"


def _component(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip() and len(value) <= 256 and "/" not in value and "\\" not in value


__all__ = ["ProbablesV2DiagnosticsStore"]
