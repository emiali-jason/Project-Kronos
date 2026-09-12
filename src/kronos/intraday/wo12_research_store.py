"""Append-only WO-12 research records and verified local publication pointers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile

from kronos.intraday.wo12_research_contract import ResearchRecord, digest, encoded, require


class ResearchStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @contextmanager
    def transaction(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".operation.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("WO12_RESEARCH_UPDATE_BUSY") from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def retain(self, item: ResearchRecord) -> ResearchRecord:
        if type(item) is not ResearchRecord:
            raise ValueError("WO12_EXACT_RECORD_REQUIRED")
        item.__post_init__()
        target = self.root / "records" / f"{item.identity}.json"
        payload = encoded(asdict(item)) + b"\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.read_bytes() != payload:
                    raise ValueError("WO12_IMMUTABLE_RECORD_CONFLICT") from None
        finally:
            os.unlink(temporary)
        _sync(target.parent)
        return item

    def load(self, identity: str) -> ResearchRecord:
        if not isinstance(identity, str) or not re.fullmatch(r"WO12_[A-Z0-9_]+-[a-f0-9]{64}", identity):
            raise ValueError("WO12_RECORD_IDENTITY_INVALID")
        item = ResearchRecord(**json.loads((self.root / "records" / f"{identity}.json").read_bytes()))
        if item.identity != identity:
            raise ValueError("WO12_RECORD_PATH_MISMATCH")
        return item

    def records(self, schema: str) -> tuple[ResearchRecord, ...]:
        root = self.root / "records"
        if not root.exists():
            return ()
        return tuple(self.load(path.stem) for path in sorted(root.glob(f"{schema}-*.json")))

    def origin_for(self, subject: str, session_identity: str) -> ResearchRecord | None:
        matches = [item for item in self.origins_for(subject, session_identity)
                   if item.data["reset_identity"] is None]
        if len(matches) > 1:
            raise ValueError("WO12_OPPORTUNITY_ORIGIN_CONFLICT")
        return matches[0] if matches else None

    def origins_for(self, subject: str, session_identity: str) -> tuple[ResearchRecord, ...]:
        return tuple(item for item in self.records("WO12_OPPORTUNITY_ORIGIN_V1")
                     if item.data["canonical_subject_identity"] == subject
                     and item.data["market_session_identity"] == session_identity)

    def current_receipt(self, year_month: str) -> ResearchRecord | None:
        path = self.root / "current" / f"{year_month}.json"
        if not path.exists():
            return None
        item = ResearchRecord(**json.loads(path.read_bytes()))
        receipt = require(item, "WO12_LOCAL_PUBLICATION_RECEIPT_V1")
        if receipt["year_month"] != year_month:
            raise ValueError("WO12_PUBLICATION_POINTER_MISMATCH")
        retained = self.load(item.identity)
        if retained != item:
            raise ValueError("WO12_PUBLICATION_RECEIPT_MISMATCH")
        return item

    def publish_receipt(self, receipt: ResearchRecord) -> None:
        data = require(receipt, "WO12_LOCAL_PUBLICATION_RECEIPT_V1")
        self.retain(receipt)
        path = self.root / "current" / f"{data['year_month']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = encoded(asdict(receipt)) + b"\n"
        descriptor, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            _sync(path.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def operation(self, operation_identity: str) -> ResearchRecord | None:
        receipts = [item for item in self.records("WO12_LOCAL_PUBLICATION_RECEIPT_V1")
                    if item.data.get("operation_identity") == operation_identity]
        current = [item for item in receipts
                   if (pointer := self.current_receipt(str(item.data["year_month"]))) is not None
                   and pointer.identity == item.identity]
        updates = [item for item in self.records("WO12_RESEARCH_UPDATE_V1")
                   if item.data.get("operation_identity") == operation_identity]
        failures = [item for item in self.records("WO12_LOCAL_PUBLICATION_FAILURE_V1")
                    if item.data.get("operation_identity") == operation_identity]
        matches = current or failures or updates
        if len(matches) > 1:
            raise ValueError("WO12_OPERATION_IDENTITY_CONFLICT")
        return matches[0] if matches else None


def _sync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = ["ResearchStore"]
