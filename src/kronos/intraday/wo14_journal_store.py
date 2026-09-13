"""Append-only WO-14 Journal revisions with atomic current/suppression pointers."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import tempfile

from kronos.intraday.wo14_journal_contract import JournalRevision, JournalSnapshot


_IDENTITY = re.compile(r"WO14-JOURNAL-[a-f0-9]{64}\Z")
_REVISION = re.compile(r"WO14-JOURNAL-REVISION-[a-f0-9]{64}\Z")


def _encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _sync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class JournalStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def retain(self, item: JournalRevision) -> JournalRevision:
        if type(item) is not JournalRevision:
            raise ValueError("WO14_JOURNAL_EXACT_REVISION_REQUIRED")
        item.__post_init__()
        path = self.root / "revisions" / f"{item.revision_identity}.json"
        payload = _encoded(asdict(item))
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise ValueError("WO14_JOURNAL_IMMUTABLE_REVISION_CONFLICT") from None
        finally:
            os.unlink(temporary)
        _sync(path.parent)
        return item

    def load_revision(self, identity: str) -> JournalRevision:
        if not isinstance(identity, str) or not _REVISION.fullmatch(identity):
            raise ValueError("WO14_JOURNAL_REVISION_IDENTITY_INVALID")
        item = JournalRevision(**json.loads((self.root / "revisions" / f"{identity}.json").read_bytes()))
        item.__post_init__()
        return item

    def publish(self, item: JournalRevision) -> JournalRevision:
        self.retain(item)
        path = self.root / "current" / f"{item.journal_identity}.json"
        _replace(path, _encoded({"journal_identity": item.journal_identity,
                                 "revision_identity": item.revision_identity}))
        return item

    def current(self, identity: str) -> JournalRevision | None:
        if not isinstance(identity, str) or not _IDENTITY.fullmatch(identity):
            raise ValueError("WO14_JOURNAL_IDENTITY_INVALID")
        path = self.root / "current" / f"{identity}.json"
        if not path.exists():
            return None
        pointer = json.loads(path.read_bytes())
        if pointer != {"journal_identity": identity, "revision_identity": pointer.get("revision_identity")}:
            raise ValueError("WO14_JOURNAL_POINTER_INVALID")
        item = self.load_revision(pointer["revision_identity"])
        if item.journal_identity != identity:
            raise ValueError("WO14_JOURNAL_POINTER_MISMATCH")
        return item

    def suppress(self, identity: str, *, revision_identity: str, action_identity: str) -> None:
        current = self.current(identity)
        if current is None or current.revision_identity != revision_identity:
            raise ValueError("WO14_JOURNAL_SUPPRESSION_STALE")
        if not isinstance(action_identity, str) or not action_identity.strip() or len(action_identity) > 200:
            raise ValueError("WO14_JOURNAL_SPONSOR_ACTION_REQUIRED")
        path = self.root / "suppressed" / f"{identity}.json"
        payload = _encoded({"journal_identity": identity, "revision_identity": revision_identity,
                            "action_identity": action_identity,
                            "authority": "PRESENTATION_SUPPRESSION_ONLY"})
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError("WO14_JOURNAL_SUPPRESSION_CONFLICT")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise ValueError("WO14_JOURNAL_SUPPRESSION_CONFLICT") from None
        finally:
            os.unlink(temporary)
        _sync(path.parent)

    def snapshot(self) -> JournalSnapshot:
        current_root = self.root / "current"
        suppressed_root = self.root / "suppressed"
        records = tuple(self.current(path.stem) for path in sorted(current_root.glob("*.json"))) if current_root.exists() else ()
        suppressed = tuple(path.stem for path in sorted(suppressed_root.glob("*.json"))) if suppressed_root.exists() else ()
        return JournalSnapshot(tuple(item for item in records if item is not None), suppressed)


__all__ = ["JournalStore"]
