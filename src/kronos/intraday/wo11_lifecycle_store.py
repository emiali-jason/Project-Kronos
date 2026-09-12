"""Prospective WO-11 append-only graph and atomic opportunity claim pointer."""
from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
from kronos.intraday.wo11_lifecycle_contract import LifecycleRecord, record, require, encoded, digest
from kronos.intraday.wo10_futures_store import _sync_directory


class LifecycleStore:
    def __init__(self, root):
        self.root = Path(root)

    @contextmanager
    def transaction(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".operation.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("WO11_OPERATION_BUSY") from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def retain(self, item):
        if type(item) is not LifecycleRecord:
            raise ValueError("WO11_EXACT_RECORD_REQUIRED")
        item.__post_init__()
        target = self.root / "records" / (item.identity + ".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = encoded(asdict(item)) + b"\n"
        fd, temp = tempfile.mkstemp(dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temp, target)
            except FileExistsError:
                if target.read_bytes() != data:
                    raise ValueError("WO11_IMMUTABLE_RECORD_CONFLICT") from None
        finally:
            os.unlink(temp)
        _sync_directory(target.parent)
        return item

    def load(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r"WO11_[A-Z0-9_]+-[a-f0-9]{64}", identity):
            raise ValueError("WO11_IDENTITY_INVALID")
        item = LifecycleRecord(**json.loads((self.root / "records" / (identity + ".json")).read_bytes()))
        if item.identity != identity:
            raise ValueError("WO11_RECORD_PATH_MISMATCH")
        return item

    def records(self, schema):
        return tuple(self.load(p.stem) for p in sorted((self.root / "records").glob(schema + "-*.json")))

    def current(self, claim):
        path = self.root / "current" / (digest(claim) + ".json")
        if not path.exists():
            return None
        pointer = LifecycleRecord(**json.loads(path.read_bytes()))
        p = require(pointer, "WO11_POINTER_V1")
        if p["claim"] != claim:
            raise ValueError("WO11_POINTER_CLAIM_MISMATCH")
        current = self.load(p["current_identity"])
        self._validate_track_graph(current, claim)
        return current

    def _validate_track_graph(self, current, claim):
        seen = set()
        authorization = current.data["authorization_identity"]
        while current is not None:
            if current.identity in seen:
                raise ValueError("WO11_GRAPH_CYCLE")
            seen.add(current.identity)
            d = require(current, "WO11_TRACK_V1")
            a = require(self.load(d["authorization_identity"]), "WO11_AUTHORIZATION_V1")
            intake = require(self.load(a["intake_identity"]), "WO11_INTAKE_V1")
            action = require(self.load(a["action_identity"]), "WO11_ACTION_V1")
            if (d["authorization_identity"] != authorization or a["claim"] != claim
                    or a["truth_class"] != d["truth_class"] or d["lots"] != 1
                    or a["intake"] != intake or d["intake"] != intake
                    or action["intake_identity"] != a["intake_identity"]):
                raise ValueError("WO11_CURRENT_AUTHORITY_MISMATCH")
            if d["event_identity"]:
                e = require(self.load(d["event_identity"]), "WO11_EVENT_V1")
                if (e["predecessor"] != d["predecessor"]
                        or e["authorization_identity"] != authorization
                        or e["to_state"] != d["state"]):
                    raise ValueError("WO11_EVENT_PREDECESSOR_MISMATCH")
                for identity in e["evidence"]:
                    self.load(identity)
            for key in ("timing_identity", "metrics"):
                if d[key]:
                    self.load(d[key])
            for key in ("entry", "exit", "close_request"):
                if d[key]:
                    retained = self.load(d[key]["identity"])
                    if retained.data != {k:v for k,v in d[key].items() if k != "identity"}:
                        raise ValueError("WO11_EMBEDDED_SOURCE_MISMATCH")
                    if key in {"entry", "exit"}:
                        self.load(retained.data["observation_identity"])
            for identity in d["gaps"]:
                self.load(identity)
            current = self.load(d["predecessor"]) if d["predecessor"] else None

    def restore(self):
        results = []
        for path in sorted((self.root / "current").glob("*.json")):
            pointer = LifecycleRecord(**json.loads(path.read_bytes()))
            d = require(pointer, "WO11_POINTER_V1")
            if path.name != digest(d["claim"]) + ".json":
                raise ValueError("WO11_POINTER_PATH_MISMATCH")
            results.append(self.current(d["claim"]))
        return tuple(results)

    def publish(self, transition, *, claim, previous):
        current = self.current(claim)
        if (current.identity if current else None) != previous:
            raise ValueError("WO11_CURRENT_POINTER_CHANGED")
        if previous is not None and transition.current.data["predecessor"] != previous:
            raise ValueError("WO11_PREDECESSOR_MISMATCH")
        for item in transition.evidence:
            self.retain(item)
        self.retain(transition.current)
        auth = require(self.load(transition.current.data["authorization_identity"]), "WO11_AUTHORIZATION_V1")
        if auth["claim"] != claim:
            raise ValueError("WO11_CLAIM_MISMATCH")
        pointer = record("WO11_POINTER_V1", claim=claim, current_identity=transition.current.identity,
                         previous=previous, updated_at=transition.current.data["updated_at"])
        self.retain(pointer)
        path = self.root / "current" / (digest(claim) + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded(asdict(pointer)) + b"\n"); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
            _sync_directory(path.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return transition.current
