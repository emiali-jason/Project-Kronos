"""Headless local lifecycle. No acquisition, reconciliation or consumer authority."""

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from .contracts import (
    CoreFailureCode, CoreRecord, CoreStatus, IdentityChannel, RecordRef,
    _fail, _identity, _validate_successor,
)
from .persistence import _RecordStore


class TvcaCore:
    def __init__(self, storage_root: Path) -> None:
        self._store = _RecordStore(storage_root)

    def create(self, request_id: str, expected_subject_identity: str,
               recorded_at: datetime) -> CoreRecord:
        record = CoreRecord(1, request_id, 0, None, CoreStatus.OPEN,
                            expected_subject_identity, None, None, recorded_at)
        return self._store.retain(record)

    def record_identity(self, base: RecordRef, channel: IdentityChannel,
                        raw_identity: str, recorded_at: datetime) -> CoreRecord:
        if type(channel) is not IdentityChannel:
            _fail(CoreFailureCode.INVALID_INPUT)
        previous = self.restore(base)
        name = ("adapter_observed_identity" if channel is IdentityChannel.ADAPTER_OBSERVED
                else "visually_observed_identity")
        if getattr(previous, name) is not None:
            _fail(CoreFailureCode.INVALID_TRANSITION)
        # An optional record field still requires an actual string for this action.
        _identity(raw_identity)
        record = replace(previous, revision=previous.revision + 1,
                         previous_record_sha256=previous.ref.sha256,
                         recorded_at=recorded_at, **{name: raw_identity})
        _validate_successor(previous, record)
        return self._store.retain(record)

    def seal(self, base: RecordRef, recorded_at: datetime) -> CoreRecord:
        previous = self.restore(base)
        record = replace(previous, revision=previous.revision + 1,
                         previous_record_sha256=previous.ref.sha256,
                         recorded_at=recorded_at, status=CoreStatus.SEALED)
        _validate_successor(previous, record)
        return self._store.retain(record)

    def restore(self, ref: RecordRef) -> CoreRecord:
        return self._store.restore(ref)
