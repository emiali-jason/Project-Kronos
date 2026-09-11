"""Separate prospective immutable namespace with locked atomic pointers."""
from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile

from kronos.intraday.wo10_futures_contract import Record, encoded, digest, record, require


class FuturesStore:
    def __init__(self, root: Path):
        self.root = Path(root)  # No I/O on composition or historical restoration.

    @contextmanager
    def transaction(self, *, construction=False):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / (".construction.lock" if construction else ".operation.lock")).open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("WO10_OPERATION_BUSY") from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def retain(self, item):
        if type(item) is not Record:
            raise ValueError("WO10_RECORD_REQUIRED")
        item.__post_init__()
        target = self.root / "records" / (item.identity + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = encoded(asdict(item)) + b"\n"
        # Write/fsync a complete private file, then publish without overwrite.
        fd, temp = tempfile.mkstemp(dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temp, target)
            except FileExistsError:
                if target.read_bytes() != data:
                    raise ValueError("WO10_RECORD_CONFLICT") from None
        finally:
            os.unlink(temp)
        _sync_directory(target.parent)
        return item

    def load(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r"[A-Z0-9_]+-[a-f0-9]{64}", identity):
            raise ValueError("WO10_IDENTITY_INVALID")
        value = Record(**json.loads((self.root / "records" / (identity + ".json")).read_bytes()))
        if value.identity != identity:
            raise ValueError("WO10_RECORD_PATH_MISMATCH")
        return value

    def records(self, schema):
        path = self.root / "records"
        return tuple(self.load(p.stem) for p in sorted(path.glob(schema + "-*.json"))) if path.exists() else ()

    def current(self, subject):
        path = self.root / "current" / (digest(subject) + ".json")
        if not path.exists():
            return None
        pointer = Record(**json.loads(path.read_bytes()))
        from kronos.intraday.wo10_futures_contract import CHECKSUM
        if pointer.policy_checksum != CHECKSUM:
            return None  # Historical pointer stays on disk; never current authority.
        p = require(pointer, "WO10_CURRENT_POINTER_V1")
        if p["subject"] != subject:
            raise ValueError("WO10_CURRENT_SUBJECT_MISMATCH")
        comparison = self.load(p["comparison_identity"])
        if comparison.data["subject"] != subject:
            raise ValueError("WO10_CURRENT_COMPARISON_MISMATCH")
        return comparison

    def publish(self, comparison, *, previous):
        c = require(comparison, "WO10_SPONSOR_COMPARISON_V1")
        current = self.current(c["subject"])
        if (None if current is None else current.identity) != previous:
            raise ValueError("WO10_CURRENT_POINTER_CHANGED")
        self.retain(comparison)
        pointer = record("WO10_CURRENT_POINTER_V1", subject=c["subject"],
                         comparison_identity=comparison.identity, predecessor=previous,
                         readiness_identity=c["readiness_identity"], updated_at=c["created_at"])
        self.retain(pointer)
        path = self.root / "current" / (digest(c["subject"]) + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded(asdict(pointer)) + b"\n"); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, path)
            _sync_directory(path.parent)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return pointer


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
