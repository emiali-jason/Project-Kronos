"""WO-05 Swing-local commit authority. No directory scan selects current state.

Artifact owners retain their original bytes. One control-file replacement under
a stable flock commits a verified immutable manifest. Analysis never holds flock.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.run_provenance import LocalSwingRunProvenanceStore
from kronos.swing.universe import SWING_PHASE1_UNIVERSE
from kronos.swing.v1 import mtf_facts, native_discovery, relative_context
from kronos.swing.v1.opportunity_continuity import (
    CommittedContinuity, ContinuityEvidenceStore,
)

SCHEMA = "KRONOS-SWING-RUN-PUBLICATION-V1"
STATES = {"RUNNING", "SUCCEEDED", "FAILED", "INTERRUPTED"}
FAILURES = {"SWING_ANALYSIS_FAILED", "SWING_PUBLICATION_FAILED", "SWING_ANALYSIS_INTERRUPTED"}


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _hash(value):
    return sha256(_bytes(value)).hexdigest()


def _timestamp(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("SWING_PUBLICATION_TIMESTAMP_INVALID")
    return value.isoformat()


def _digest_valid(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _require(condition):
    # Trust-boundary validation must also execute with python -O.
    if not condition:
        raise ValueError("SWING_PUBLICATION_CONSTRAINT_INVALID")


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _mkdir(path):
    if not path.exists():
        _mkdir(path.parent)
        path.mkdir(mode=0o700, exist_ok=True)
        _sync_directory(path.parent)


def _atomic(path, payload):
    _mkdir(path.parent)
    temporary = path.with_name("." + uuid4().hex + ".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class OperationToken:
    generation: int
    run_id: str
    predecessor_manifest: dict


@dataclass(frozen=True)
class CommittedRun:
    reference: dict
    manifest: dict
    mtf: object
    native: object
    relative: object
    provenance: object
    continuity: CommittedContinuity | None


class SwingRunPublication:
    """One product-local control owner; constructors do not write or recover."""

    def __init__(self, root, *, mtf_store, native_store, relative_store,
                 provenance_store, fault=lambda phase: None):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root == Path("/"):
            raise ValueError("SWING_PUBLICATION_ROOT_INVALID")
        self.mtf_store = mtf_store
        self.native_store = native_store
        self.relative_store = relative_store
        self.provenance_store = provenance_store
        self.continuity_store = ContinuityEvidenceStore(self.root / "continuity")
        self.fault = fault

    @property
    def initialized(self):
        return (self.root / "control.json").exists()

    @contextmanager
    def _lock(self):
        _mkdir(self.root)
        # Never replace/unlink this inode or lock the replaceable control file.
        fd = os.open(self.root / "publication.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _control(self):
        try:
            value = json.loads((self.root / "control.json").read_bytes())
            _require(type(value) is dict)
            checksum = value.pop("integrity_sha256")
            _require(value.keys() == {"schema_version", "admission_generation", "latest_attempt", "current_manifest"})
            _require(value["schema_version"] == SCHEMA and _hash(value) == checksum)
            generation = value["admission_generation"]
            _require(type(generation) is int and generation >= 0)
            attempt = value["latest_attempt"]
            _require(type(attempt) is dict)
            _require(attempt.keys() == {"run_id", "state", "predecessor_manifest", "accepted_at", "completed_at", "failure_reason"})
            _require(is_swing_analysis_run_id(attempt["run_id"]) and attempt["state"] in STATES)
            _require(attempt["failure_reason"] in FAILURES | {None})
            _require((attempt["state"] in {"FAILED", "INTERRUPTED"}) == (attempt["failure_reason"] is not None))
            _require(attempt["accepted_at"] is not None)
            for key in ("accepted_at", "completed_at"):
                if attempt[key] is not None:
                    _timestamp(datetime.fromisoformat(attempt[key]))
            _require((attempt["state"] == "RUNNING") == (attempt["completed_at"] is None))
            self._manifest_path(value["current_manifest"])
            if attempt["predecessor_manifest"] is not None:
                self._manifest_path(attempt["predecessor_manifest"])
            return value
        except (OSError, KeyError, TypeError, ValueError, AssertionError) as error:
            raise ValueError("SWING_PUBLICATION_CONTROL_INVALID") from error

    def _write_control(self, value):
        payload = _bytes({**value, "integrity_sha256": _hash(value)})
        try:
            self.fault("before_control_replace")
            _atomic(self.root / "control.json", payload)
            self.fault("after_control_replace")
        except OSError:
            # Under the same lock, resolve a possibly successful replacement.
            if self._control() != value:
                raise
            _sync_directory(self.root)

    def status(self):
        """Observational: no lock-file creation, reconciliation or recovery."""
        control = self._control()
        ref = control["current_manifest"]
        if sha256(self._manifest_path(ref).read_bytes()).hexdigest() != ref["sha256"]:
            raise ValueError("SWING_PUBLICATION_MANIFEST_INTEGRITY_INVALID")
        return control

    def _manifest_path(self, reference):
        if (type(reference) is not dict or set(reference) != {"path", "sha256"}
                or not _digest_valid(reference["sha256"])
                or reference["path"] != "manifests/" + reference["sha256"] + ".json"):
            raise ValueError("SWING_PUBLICATION_MANIFEST_REFERENCE_INVALID")
        return self.root / reference["path"]

    def _paths(self, run):
        if not is_swing_analysis_run_id(run):
            raise ValueError("SWING_ANALYSIS_RUN_IDENTITY_INVALID")
        return {
            "mtf": self.mtf_store._path(run),
            "native": self.native_store._root / "complete-runs" / (run + ".json"),
            "relative": self.relative_store._path(run),
            "provenance": self.provenance_store.root / run / "run-provenance.json",
            "continuity": self.continuity_store._path(run),
        }

    def _references(self, run, *, continuity):
        result = {}
        for kind, path in self._paths(run).items():
            if kind == "continuity" and not continuity:
                result[kind] = None
                continue
            data = path.read_bytes()
            result[kind] = {"path": str(path), "sha256": sha256(data).hexdigest()}
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
            _sync_directory(path.parent)
            _sync_directory(path.parent.parent)
        return result

    def _load(self, reference):
        path = self._manifest_path(reference)
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("SWING_PUBLICATION_MANIFEST_INTEGRITY_INVALID")
        manifest = json.loads(raw)
        return self._validate(manifest, reference)

    def _exact_commit_fence(self, bundle):
        reference = bundle.reference
        _require(
            sha256(self._manifest_path(reference).read_bytes()).hexdigest()
            == reference["sha256"]
        )
        for artifact in bundle.manifest["artifacts"].values():
            if artifact is not None:
                _require(
                    sha256(Path(artifact["path"]).read_bytes()).hexdigest()
                    == artifact["sha256"]
                )

    def _validate(self, manifest, reference):
        try:
            _require(set(manifest) == {"schema_version", "generation", "run_id", "predecessor_manifest", "kind", "artifacts"})
            _require(manifest["schema_version"] == SCHEMA)
            _require(type(manifest["generation"]) is int and manifest["generation"] >= 0)
            _require(manifest["kind"] in {"ANALYSIS", "ADOPTED_EXISTING_CHECKPOINT"})
            adopted = manifest["kind"] == "ADOPTED_EXISTING_CHECKPOINT"
            _require((manifest["generation"] == 0) == adopted)
            _require((manifest["predecessor_manifest"] is None) == adopted)
            if not adopted:
                self._manifest_path(manifest["predecessor_manifest"])
            paths = self._paths(manifest["run_id"])
            _require(set(manifest["artifacts"]) == set(paths))
            for kind, path in paths.items():
                ref = manifest["artifacts"][kind]
                if kind == "continuity" and adopted:
                    _require(ref is None)
                    continue
                _require(set(ref) == {"path", "sha256"} and ref["path"] == str(path))
                _require(sha256(path.read_bytes()).hexdigest() == ref["sha256"])
                if kind == "native":
                    _require(json.loads(path.read_bytes()).get("schema") == native_discovery.NATIVE_DISCOVERY_SCHEMA)
            rid = manifest["run_id"]
            m = self.mtf_store.load(rid)
            n = self.native_store.load(rid)
            r = self.relative_store.load(rid)
            p = self.provenance_store.load(rid)
            _require(m.run_identity == n.run_identity == r.run_identity == p.run_id == rid)
            _require(m.observed_at == n.observed_at == r.created_at == p.run_created_at)
            _require(p.successful_completed_at is not None)
            _require(m.provider_source_identity == n.provider_source_identity)
            universe = {v.canonical_identity for v in SWING_PHASE1_UNIVERSE}
            _require({v.canonical_instrument for v in m.instruments} == universe)
            _require({v.canonical_instrument for v in n.assessments} == universe)
            _require({v.canonical_instrument for v in r.records} == universe)
            _require(all(v.run_identity == rid for v in r.records))
            c = None if adopted else CommittedContinuity.verify(
                self.continuity_store.load_prepared(rid), native_run=n,
                mtf_snapshot=m, provenance=p,
                committed_contribution_sha256=self.continuity_store.load_prepared(rid).integrity_sha256)
            # Detect a change between raw-byte verification and typed loading.
            for kind, path in paths.items():
                if kind != "continuity" or not adopted:
                    _require(sha256(path.read_bytes()).hexdigest() == manifest["artifacts"][kind]["sha256"])
            return CommittedRun(reference, manifest, m, n, r, p, c)
        except (AssertionError, KeyError, TypeError, ValueError, OSError) as error:
            raise ValueError("SWING_PUBLICATION_BUNDLE_INVALID") from error

    def _retain_manifest(self, manifest):
        payload = _bytes(manifest)
        digest = sha256(payload).hexdigest()
        reference = {"path": "manifests/" + digest + ".json", "sha256": digest}
        self._validate(manifest, reference)
        path = self._manifest_path(reference)
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError("SWING_PUBLICATION_MANIFEST_IMMUTABLE")
        else:
            _atomic(path, payload)
        self.fault("after_manifest")
        return reference

    def adopt(self, run_id, expected_artifacts):
        """Explicit exact checkpoint only; never invoke an independent latest scan."""
        refs = self._references(run_id, continuity=False)
        if {k: v for k, v in refs.items() if k != "continuity"} != expected_artifacts:
            raise ValueError("SWING_ACTIVATION_CHECKPOINT_INVALID")
        reference = self._retain_manifest({"schema_version": SCHEMA, "generation": 0,
            "run_id": run_id, "predecessor_manifest": None,
            "kind": "ADOPTED_EXISTING_CHECKPOINT", "artifacts": refs})
        bundle = self._load(reference)
        with self._lock():
            if self.initialized:
                if self._control()["current_manifest"] != reference:
                    raise ValueError("SWING_PUBLICATION_ALREADY_INITIALIZED")
            else:
                self._write_control({"schema_version": SCHEMA, "admission_generation": 0,
                    "latest_attempt": {"run_id": run_id, "state": "SUCCEEDED",
                        "predecessor_manifest": None,
                        "accepted_at": _timestamp(bundle.provenance.run_created_at),
                        "completed_at": _timestamp(bundle.provenance.successful_completed_at),
                        "failure_reason": None}, "current_manifest": reference})
        return bundle

    def current(self):
        control = self._control()
        bundle = self._load(control["current_manifest"])
        attempt = control["latest_attempt"]
        if attempt["state"] == "SUCCEEDED":
            _require(attempt["run_id"] == bundle.native.run_identity)
            _require(control["admission_generation"] == bundle.manifest["generation"])
        else:
            _require(attempt["predecessor_manifest"] == bundle.reference)
            _require(control["admission_generation"] > bundle.manifest["generation"])
        if self._control()["current_manifest"] != bundle.reference:
            raise ValueError("SWING_PUBLICATION_CURRENT_CHANGED")
        return bundle

    def admit(self, run_id, now):
        if not is_swing_analysis_run_id(run_id):
            raise ValueError("SWING_ANALYSIS_RUN_IDENTITY_INVALID")
        accepted_at = _timestamp(now)
        if self._paths(run_id)["native"].exists():
            raise ValueError("SWING_PUBLICATION_RUN_REUSED")
        with self._lock():
            control = self._control()
            if control["latest_attempt"]["run_id"] == run_id:
                raise ValueError("SWING_PUBLICATION_RUN_REUSED")
            token = OperationToken(control["admission_generation"] + 1, run_id, control["current_manifest"])
            self._write_control({**control, "admission_generation": token.generation,
                "latest_attempt": {"run_id": run_id, "state": "RUNNING",
                    "predecessor_manifest": token.predecessor_manifest,
                    "accepted_at": accepted_at, "completed_at": None, "failure_reason": None}})
        # One exact captured predecessor, outside flock and before acquisition.
        return token, self._load(token.predecessor_manifest)

    @staticmethod
    def _eligible(control, token):
        return (control["admission_generation"] == token.generation
                and control["latest_attempt"]["run_id"] == token.run_id
                and control["latest_attempt"]["state"] == "RUNNING"
                and control["latest_attempt"]["predecessor_manifest"] == token.predecessor_manifest
                and control["current_manifest"] == token.predecessor_manifest)

    def prepare(self, token, *, mtf, native, relative, provenance, continuity):
        if any(getattr(v, "run_identity", getattr(v, "run_id", None)) != token.run_id
               for v in (mtf, native, relative, provenance)):
            raise ValueError("SWING_PUBLICATION_RUN_MISMATCH")
        prior = self._load(token.predecessor_manifest)
        previous_hashes = {a.canonical_instrument: a.result_sha256 for a in prior.native.assessments}
        if any(a.predecessor_result_sha256 != previous_hashes[a.canonical_instrument]
               for a in native.assessments):
            raise ValueError("SWING_PUBLICATION_PREDECESSOR_MISMATCH")
        for kind, store, value in (("mtf", self.mtf_store, mtf),
                                  ("native", self.native_store, native),
                                  ("relative", self.relative_store, relative),
                                  ("provenance", self.provenance_store, provenance)):
            store.retain(value)
            self.fault("after_" + kind)
        self.continuity_store.retain_prepared(continuity)
        self.fault("after_continuity")
        return self._retain_manifest({"schema_version": SCHEMA, "generation": token.generation,
            "run_id": token.run_id, "predecessor_manifest": token.predecessor_manifest,
            "kind": "ANALYSIS", "artifacts": self._references(token.run_id, continuity=True)})

    def publish(
        self,
        token,
        reference,
        now,
        *,
        before_commit=None,
        commit_ready=None,
    ):
        bundle = self._load(reference)
        if (bundle.manifest["generation"] != token.generation
                or bundle.manifest["run_id"] != token.run_id
                or bundle.manifest["predecessor_manifest"] != token.predecessor_manifest):
            raise ValueError("SWING_PUBLICATION_TOKEN_MISMATCH")
        completed_at = _timestamp(now)
        if now != bundle.provenance.successful_completed_at:
            raise ValueError("SWING_PUBLICATION_COMPLETION_MISMATCH")
        if before_commit is not None:
            if not callable(before_commit) or before_commit(bundle) is not True:
                raise ValueError("SWING_PUBLICATION_COMMIT_NOT_AUTHORIZED")
        # A callback may wait while the validated predecessor remains current.
        # Recheck the exact bytes immediately before the atomic control commit.
        self._exact_commit_fence(bundle)
        if commit_ready is not None:
            if not callable(commit_ready) or commit_ready(bundle) is not True:
                raise ValueError("SWING_PUBLICATION_COMMIT_NOT_AUTHORIZED")
        with self._lock():
            control = self._control()
            if not self._eligible(control, token):
                return None  # Includes duplicate completion: no repeated effects.
            self._write_control({**control, "current_manifest": reference,
                "latest_attempt": {**control["latest_attempt"], "state": "SUCCEEDED",
                    "completed_at": completed_at, "failure_reason": None}})
        return bundle

    def fail(self, token, now, reason="SWING_ANALYSIS_FAILED"):
        if reason not in FAILURES:
            raise ValueError("SWING_PUBLICATION_FAILURE_INVALID")
        with self._lock():
            control = self._control()
            if not self._eligible(control, token):
                return False
            self._write_control({**control, "latest_attempt": {**control["latest_attempt"],
                "state": "FAILED", "completed_at": _timestamp(now), "failure_reason": reason}})
        return True

    def recover(self, now):
        """Explicit canonical startup only. GET must never invoke recovery."""
        bundle = self.current()  # Corrupt authority must not be repaired from orphans.
        with self._lock():
            control = self._control()
            if control["current_manifest"] != bundle.reference:
                raise ValueError("SWING_PUBLICATION_CURRENT_CHANGED")
            if control["latest_attempt"]["state"] == "RUNNING":
                self._write_control({**control, "latest_attempt": {**control["latest_attempt"],
                    "state": "INTERRUPTED", "completed_at": _timestamp(now),
                    "failure_reason": "SWING_ANALYSIS_INTERRUPTED"}})
        return bundle
