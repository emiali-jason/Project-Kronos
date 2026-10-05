"""Small append-only WO-12 owner-event inbox, independent of research I/O.

Only already-retained owner events can enter this inbox. It records the factual
price visible at the event boundary before a slow historical update can take
its separate research-store lock. The full owner fact is read back from its
own canonical store during explicit replay.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from uuid import uuid4


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode() + b"\n"


class SwingResearchInbox:
    KINDS = frozenset({"ADMISSION", "V2", "OWNER"})

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError("SWING_RESEARCH_INBOX_ROOT_INVALID")

    @staticmethod
    def _key(kind: str, event_identity: str) -> str:
        if (kind not in SwingResearchInbox.KINDS or type(event_identity) is not str
                or not event_identity or len(event_identity) > 300):
            raise ValueError("SWING_RESEARCH_INBOX_EVENT_INVALID")
        return sha256((kind + "\x00" + event_identity).encode()).hexdigest()

    def _path(self, kind: str, event_identity: str) -> Path:
        return self.root / kind / (self._key(kind, event_identity) + ".json")

    def read(self, kind: str, event_identity: str) -> dict | None:
        path = self._path(kind, event_identity)
        if not path.exists():
            return None
        if path.is_symlink():
            raise ValueError("SWING_RESEARCH_INBOX_INTEGRITY_INVALID")
        data = json.loads(path.read_bytes())
        payload = data.get("payload")
        if (data.get("kind") != kind or data.get("event_identity") != event_identity
                or data.get("integrity_sha256") != sha256(_canonical(payload)).hexdigest()
                or not isinstance(payload, dict)):
            raise ValueError("SWING_RESEARCH_INBOX_INTEGRITY_INVALID")
        return payload

    def retain(self, kind: str, event_identity: str, payload: dict) -> dict:
        if type(payload) is not dict:
            raise ValueError("SWING_RESEARCH_INBOX_PAYLOAD_INVALID")
        path = self._path(kind, event_identity)
        prior = self.read(kind, event_identity)
        if prior is not None:
            # First observation wins. A replay may see a later tick, but it
            # cannot rewrite what was factually available at the owner event.
            return prior
        value = {"kind": kind, "event_identity": event_identity,
                 "payload": payload,
                 "integrity_sha256": sha256(_canonical(payload)).hexdigest()}
        if self.root.is_symlink() or path.parent.is_symlink():
            raise ValueError("SWING_RESEARCH_INBOX_ROOT_INVALID")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / ("." + uuid4().hex + ".pending")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_canonical(value))
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                return self.read(kind, event_identity)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        return payload

    def empty_for_commissioning(self) -> bool:
        """Unknown/pending files block; empty known directories are permitted."""
        if self.root.is_symlink():
            raise ValueError("SWING_RESEARCH_INBOX_ROOT_INVALID")
        if not self.root.exists():
            return True
        return all(path.is_dir() and not path.is_symlink()
                   and path.parent == self.root and path.name in self.KINDS
                   for path in self.root.rglob("*"))

    def count(self) -> int:
        return sum(len(tuple((self.root / kind).glob("*.json")))
                   for kind in self.KINDS)


def serialise_price_fact(value: dict) -> dict:
    return {key: item.isoformat() if isinstance(item, datetime) else item
            for key, item in value.items()}


def restore_price_fact(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("SWING_RESEARCH_PRICE_RECEIPT_INVALID")
    expected = {"reference_price", "price_observation_identity",
                "price_observed_at", "price_received_at", "price_source"}
    if value and set(value) != expected:
        raise ValueError("SWING_RESEARCH_PRICE_RECEIPT_INVALID")
    result = dict(value)
    for key in ("price_observed_at", "price_received_at"):
        if key in result:
            result[key] = datetime.fromisoformat(result[key])
    return result
