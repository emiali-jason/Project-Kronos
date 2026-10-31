"""One-use child claim for an explicitly selected failed-successor restoration.

This module is deliberately not a launcher, admission-head writer, approval
parser, or recovery coordinator.  A trusted controlled-release procedure must
select the exact permit and the native parent must already have durably reserved
the incident and selected one child.  The child validates those immutable facts
under adopted installation custody, creates its sole exclusive claim, and
returns a context for later composition wiring.

Matching hashes prove byte identity only.  They do not authenticate Sponsor or
owner consent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from kronos.common.release_admission import AdmissionCustody, ValidationBudget


PERMIT_SCHEMA = "KRONOS_FAILED_SUCCESSOR_RESTORATION_PERMIT_V1"
INCIDENT_SCHEMA = "KRONOS_FAILED_SUCCESSOR_INCIDENT_V1"
FAILURE_SCHEMA = "KRONOS_FAILED_SUCCESSOR_FAILURE_CLEANUP_V1"
SETTLED_SCHEMA = "KRONOS_FAILED_SUCCESSOR_SETTLED_STATE_V1"
RESERVATION_SCHEMA = "KRONOS_FAILED_SUCCESSOR_RESTORATION_RESERVATION_V1"
HEAD_SCHEMA = "KRONOS_RESTORATION_ADMISSION_HEAD_V1"
CLAIM_SCHEMA = "KRONOS_FAILED_SUCCESSOR_RESTORATION_CHILD_CLAIM_V1"
MAX_DOCUMENT_BYTES = 65536

_HEX64 = re.compile(r"[a-f0-9]{64}")
_REVISION = re.compile(r"[a-f0-9]{40}|[a-f0-9]{64}")
_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}")
_REF = frozenset({"identity", "path", "bytes", "sha256"})
_INSTALLATION = frozenset({
    "identity", "anchor_path", "device", "inode", "owner", "bundle_id",
    "bundle_path", "repository_path",
})
_TARGET = frozenset({
    "revision", "tree_sha256", "source_manifest_sha256",
    "artifact_manifest_sha256", "pinned_capture_sha256", "origin_url",
    "source_ref",
})
_PROCESS = frozenset({"pid", "kernel_birth", "runtime_identity", "revision"})
_V2 = frozenset({
    "handoff_identity", "handoff_sha256", "consumption_identity",
    "consumption_sha256",
})
_CHECKPOINT = frozenset({"state", "pending_count", "sha256"})


class FailedSuccessorRestoreError(ValueError):
    """Closed restoration denial without leaking untrusted document content."""


def _deny() -> None:
    raise FailedSuccessorRestoreError("FAILED_SUCCESSOR_RESTORE_REJECTED")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _hex64(value: object) -> bool:
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def _identity(value: object) -> bool:
    return isinstance(value, str) and _IDENTITY.fullmatch(value) is not None


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, str):
        _deny()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _deny()
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        _deny()
    return parsed


def _closed(value: object, fields: frozenset[str]) -> dict:
    if type(value) is not dict or set(value) != fields:
        _deny()
    return value


def _secure_parent(path: Path) -> None:
    if (not path.is_absolute() or ".." in path.parts
            or any(part.is_symlink() for part in (path, *path.parents))):
        _deny()
    try:
        metadata = path.stat()
    except OSError:
        _deny()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        _deny()


def _read_raw(path: Path, expected_bytes: int, expected_sha256: str) -> bytes:
    if (not isinstance(path, Path) or not path.is_absolute()
            or type(expected_bytes) is not int
            or not 1 <= expected_bytes <= MAX_DOCUMENT_BYTES
            or not _hex64(expected_sha256)):
        _deny()
    _secure_parent(path.parent)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if (not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                    or metadata.st_size != expected_bytes):
                _deny()
            raw = handle.read(MAX_DOCUMENT_BYTES + 1)
    except FailedSuccessorRestoreError:
        raise
    except (OSError, ValueError):
        _deny()
    if len(raw) != expected_bytes or sha256(raw).hexdigest() != expected_sha256:
        _deny()
    return raw


def _document(path: Path, expected_bytes: int, expected_sha256: str) -> tuple[dict, bytes]:
    raw = _read_raw(path, expected_bytes, expected_sha256)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _deny()
    if type(value) is not dict or raw != _canonical(value):
        _deny()
    return value, raw


def _current_document(path: Path) -> tuple[dict, bytes]:
    """Read a current mutable selector without following a replacement link."""
    if not isinstance(path, Path) or not path.is_absolute():
        _deny()
    _secure_parent(path.parent)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if (not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o600
                    or not 1 <= metadata.st_size <= MAX_DOCUMENT_BYTES):
                _deny()
            raw = handle.read(MAX_DOCUMENT_BYTES + 1)
    except FailedSuccessorRestoreError:
        raise
    except OSError:
        _deny()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _deny()
    if len(raw) != metadata.st_size or type(value) is not dict or raw != _canonical(value):
        _deny()
    return value, raw


def _reference(value: object) -> dict:
    value = _closed(value, _REF)
    if (not _identity(value["identity"]) or not isinstance(value["path"], str)
            or not Path(value["path"]).is_absolute()
            or type(value["bytes"]) is not int
            or not 1 <= value["bytes"] <= MAX_DOCUMENT_BYTES
            or not _hex64(value["sha256"])):
        _deny()
    return value


def _load_reference(value: object) -> tuple[dict, bytes, dict]:
    reference = _reference(value)
    document, raw = _document(Path(reference["path"]), reference["bytes"],
                              reference["sha256"])
    return document, raw, reference


def _installation(value: object) -> dict:
    value = _closed(value, _INSTALLATION)
    paths = ("anchor_path", "bundle_path", "repository_path")
    if (not _hex64(value["identity"])
            or any(not isinstance(value[key], str) or not Path(value[key]).is_absolute()
                   for key in paths)
            or type(value["device"]) is not int or value["device"] <= 0
            or type(value["inode"]) is not int or value["inode"] <= 0
            or type(value["owner"]) is not int or value["owner"] < 0
            or not isinstance(value["bundle_id"], str) or not value["bundle_id"]):
        _deny()
    core = dict(value)
    identity = core.pop("identity")
    if identity != sha256(_canonical(core)).hexdigest():
        _deny()
    return value


def _target(value: object) -> dict:
    value = _closed(value, _TARGET)
    if (_REVISION.fullmatch(value["revision"]) is None
            or any(not _hex64(value[key]) for key in (
                "tree_sha256", "source_manifest_sha256",
                "artifact_manifest_sha256", "pinned_capture_sha256"))
            or not isinstance(value["origin_url"], str) or not value["origin_url"]
            or not isinstance(value["source_ref"], str)
            or not value["source_ref"].startswith("refs/heads/")):
        _deny()
    return value


def _process(value: object) -> dict:
    value = _closed(value, _PROCESS)
    if (type(value["pid"]) is not int or value["pid"] < 2
            or not _hex64(value["kernel_birth"])
            or not _hex64(value["runtime_identity"])
            or _REVISION.fullmatch(value["revision"]) is None):
        _deny()
    return value


def _v2(value: object) -> dict:
    value = _closed(value, _V2)
    if (not _identity(value["handoff_identity"])
            or not _hex64(value["handoff_sha256"])
            or not _identity(value["consumption_identity"])
            or not _hex64(value["consumption_sha256"])):
        _deny()
    return value


def _checkpoint(value: object) -> dict:
    value = _closed(value, _CHECKPOINT)
    if (value["state"] not in {"EMPTY", "VALID_PENDING"}
            or type(value["pending_count"]) is not int
            or value["pending_count"] < 0
            or (value["state"] == "EMPTY") != (value["pending_count"] == 0)
            or not _hex64(value["sha256"])):
        _deny()
    return value


@dataclass(frozen=True, slots=True)
class SelectedPermit:
    """Exact permit chosen by the external trusted operator procedure."""

    path: Path
    byte_size: int
    sha256: str
    permit_id: str

    def __post_init__(self) -> None:
        if (not isinstance(self.path, Path) or not self.path.is_absolute()
                or type(self.byte_size) is not int
                or not 1 <= self.byte_size <= MAX_DOCUMENT_BYTES
                or not _hex64(self.sha256) or not _identity(self.permit_id)):
            _deny()


@dataclass(frozen=True, slots=True)
class SelectedReservation:
    """Exact reservation selected by the already-authoritative native parent."""

    path: Path
    byte_size: int
    sha256: str
    reservation_id: str

    def __post_init__(self) -> None:
        if (not isinstance(self.path, Path) or not self.path.is_absolute()
                or type(self.byte_size) is not int
                or not 1 <= self.byte_size <= MAX_DOCUMENT_BYTES
                or not _hex64(self.sha256) or not _identity(self.reservation_id)):
            _deny()


@dataclass(frozen=True, slots=True)
class RestorationChildIdentity:
    process_id: int
    parent_pid: int
    parent_kernel_birth: str
    kernel_birth: str
    runtime_identity: str
    loaded_revision: str
    source_manifest_sha256: str
    artifact_manifest_sha256: str
    pinned_capture_sha256: str

    def __post_init__(self) -> None:
        if (type(self.process_id) is not int or self.process_id < 2
                or type(self.parent_pid) is not int or self.parent_pid < 2
                or any(not _hex64(value) for value in (
                    self.parent_kernel_birth, self.kernel_birth,
                    self.runtime_identity, self.source_manifest_sha256,
                    self.artifact_manifest_sha256, self.pinned_capture_sha256))
                or _REVISION.fullmatch(self.loaded_revision) is None):
            _deny()


@dataclass(frozen=True, slots=True)
class RestorationStartupContext:
    """Immutable restoration context; never a predecessor drain context."""

    incident_id: str
    original_attempt_id: str
    permit_id: str
    permit_sha256: str
    reservation_id: str
    reservation_sha256: str
    process_id: int
    runtime_identity: str
    loaded_revision: str
    maintenance_identity: str
    settled_state_manifest_identity: str
    settled_state_manifest_sha256: str
    notification_state: str
    notification_pending_count: int
    notification_sha256: str
    original_v2_handoff_identity: str
    original_v2_handoff_sha256: str
    original_v2_consumption_identity: str
    original_v2_consumption_sha256: str

    def notification_checkpoint(self) -> dict[str, object]:
        return {"state": self.notification_state,
                "pending_count": self.notification_pending_count,
                "sha256": self.notification_sha256}


def _permit(document: object, selection: SelectedPermit, now: datetime) -> dict:
    fields = frozenset({
        "schema", "permit_id", "installation", "incident", "failure_cleanup",
        "settled_state", "restoration_target", "authority", "valid_from",
        "valid_until", "created_at", "approved_at", "maximum_children",
        "operation_scope",
    })
    value = _closed(document, fields)
    authority_fields = frozenset({
        "sponsor_order_identity", "sponsor_order_sha256", "ca_decision_identity",
        "ca_decision_sha256", "pcp_decision_identity", "pcp_decision_sha256",
        "product_decision_identity", "product_decision_sha256",
    })
    authority = _closed(value["authority"], authority_fields)
    if (value["schema"] != PERMIT_SCHEMA or value["permit_id"] != selection.permit_id
            or any(not _identity(authority[key]) for key in authority
                   if key.endswith("_identity"))
            or any(not _hex64(authority[key]) for key in authority
                   if key.endswith("_sha256"))
            or type(value["maximum_children"]) is not int
            or value["maximum_children"] != 1
            or value["operation_scope"] != "ONE_FAILED_SUCCESSOR_RESTORATION_START"):
        _deny()
    _installation(value["installation"])
    _reference(value["incident"])
    _reference(value["failure_cleanup"])
    _reference(value["settled_state"])
    _target(value["restoration_target"])
    created_at, approved_at = _aware_utc(value["created_at"]), _aware_utc(value["approved_at"])
    valid_from, valid_until = _aware_utc(value["valid_from"]), _aware_utc(value["valid_until"])
    if (not created_at <= approved_at <= valid_from < valid_until
            or not valid_from <= now <= valid_until):
        _deny()
    return value


def _incident(document: object, reference: dict, installation: dict) -> dict:
    fields = frozenset({
        "schema", "incident_id", "original_attempt_id", "installation_identity",
        "predecessor", "original_parent", "failed_successor", "failed_target",
        "original_admission_identity", "original_v2", "created_at",
    })
    value = _closed(document, fields)
    if (value["schema"] != INCIDENT_SCHEMA
            or value["incident_id"] != reference["identity"]
            or not _identity(value["original_attempt_id"])
            or value["installation_identity"] != installation["identity"]
            or not _identity(value["original_admission_identity"])):
        _deny()
    predecessor = _process(value["predecessor"])
    original_parent = _process(value["original_parent"])
    failed = _process(value["failed_successor"])
    _target(value["failed_target"])
    if len({predecessor["pid"], original_parent["pid"], failed["pid"]}) != 3:
        _deny()
    _v2(value["original_v2"])
    _aware_utc(value["created_at"])
    return value


def _failure(document: object, reference: dict, incident: dict,
             settled_reference: dict) -> dict:
    fields = frozenset({
        "schema", "failure_cleanup_id", "incident_id", "original_attempt_id",
        "failed_successor", "failure_stage", "failure_result", "ready",
        "cleanup", "parent_terminal", "settled_state", "recorded_at",
    })
    ready_fields = frozenset({"completion_entered", "outcome", "receipt", "ambiguity"})
    cleanup_fields = frozenset({
        "state", "owner_ledger_identity", "owner_ledger_sha256",
        "final_owner_proof_identity", "final_owner_proof_sha256",
        "validation_helpers", "actionable_owner_count", "acknowledged",
        "custody_disposition",
    })
    terminal_fields = frozenset({
        "parent_pid", "parent_kernel_birth", "child_pid", "child_kernel_birth",
        "observation", "exit_code",
    })
    value = _closed(document, fields)
    ready = _closed(value["ready"], ready_fields)
    cleanup = _closed(value["cleanup"], cleanup_fields)
    terminal = _closed(value["parent_terminal"], terminal_fields)
    if (value["schema"] != FAILURE_SCHEMA
            or value["failure_cleanup_id"] != reference["identity"]
            or value["incident_id"] != incident["incident_id"]
            or value["original_attempt_id"] != incident["original_attempt_id"]
            or _process(value["failed_successor"]) != incident["failed_successor"]
            or not _identity(value["failure_stage"])
            or not _identity(value["failure_result"])
            or type(ready["completion_entered"]) is not bool
            or (ready["completion_entered"], ready["outcome"]) not in {
                (False, "COMPLETION_PROVEN_NOT_ENTERED"),
                (True, "NEVER_READY_POSITIVELY_ESTABLISHED"),
            }
            or ready["receipt"] != "PROVEN_NOT_CREATED"
            or ready["ambiguity"] != "NONE"
            or cleanup["state"] != "COMPLETE"
            or cleanup["validation_helpers"] != "TERMINAL"
            or cleanup["actionable_owner_count"] != 0
            or cleanup["acknowledged"] is not True
            or cleanup["custody_disposition"] != "RELEASED_AFTER_COMPLETE_CLEANUP"
            or any(not _identity(cleanup[key]) for key in (
                "owner_ledger_identity", "final_owner_proof_identity"))
            or any(not _hex64(cleanup[key]) for key in (
                "owner_ledger_sha256", "final_owner_proof_sha256"))
            or type(cleanup["actionable_owner_count"]) is not int
            or type(terminal["parent_pid"]) is not int or terminal["parent_pid"] < 2
            or type(terminal["child_pid"]) is not int or terminal["child_pid"] < 2
            or not _hex64(terminal["parent_kernel_birth"])
            or not _hex64(terminal["child_kernel_birth"])
            or terminal["observation"] != "TERMINAL_REAPED"
            or type(terminal["exit_code"]) is not int or terminal["exit_code"] != 78
            or terminal["parent_pid"] == terminal["child_pid"]
            or terminal["parent_pid"] != incident["original_parent"]["pid"]
            or terminal["parent_kernel_birth"] != incident["original_parent"]["kernel_birth"]
            or terminal["child_pid"] != incident["failed_successor"]["pid"]
            or terminal["child_kernel_birth"] != incident["failed_successor"]["kernel_birth"]
            or value["settled_state"] != settled_reference):
        _deny()
    if not (_aware_utc(incident["created_at"])
            <= _aware_utc(value["recorded_at"])):
        _deny()
    return value


def _settled(document: object, reference: dict, incident: dict) -> dict:
    fields = frozenset({
        "schema", "settled_state_id", "incident_id", "status",
        "state_manifest_identity", "state_manifest_sha256", "owner_results_sha256",
        "notification_checkpoint", "original_v2", "certified_at",
    })
    value = _closed(document, fields)
    if (value["schema"] != SETTLED_SCHEMA
            or value["settled_state_id"] != reference["identity"]
            or value["incident_id"] != incident["incident_id"]
            or value["status"] != "CERTIFIED_CURRENT"
            or not _identity(value["state_manifest_identity"])
            or not _hex64(value["state_manifest_sha256"])
            or not _hex64(value["owner_results_sha256"])
            or _v2(value["original_v2"]) != incident["original_v2"]):
        _deny()
    _checkpoint(value["notification_checkpoint"])
    if _aware_utc(value["certified_at"]) < _aware_utc(incident["created_at"]):
        _deny()
    return value


def _reservation(document: object, selection: SelectedReservation, permit: dict,
                 permit_selection: SelectedPermit, incident: dict,
                 settled_reference: dict) -> dict:
    fields = frozenset({
        "schema", "reservation_id", "incident_id", "permit_id", "permit_sha256",
        "installation_identity", "state", "parent", "restoration_target",
        "settled_state", "attempt_nonce", "created_at", "valid_until",
        "head_path", "claim_path",
    })
    value = _closed(document, fields)
    parent_fields = frozenset({"pid", "kernel_birth", "runtime_identity", "revision"})
    parent = _closed(value["parent"], parent_fields)
    if (value["schema"] != RESERVATION_SCHEMA
            or value["reservation_id"] != selection.reservation_id
            or value["incident_id"] != incident["incident_id"]
            or value["permit_id"] != permit["permit_id"]
            or value["permit_sha256"] != permit_selection.sha256
            or value["installation_identity"] != permit["installation"]["identity"]
            or value["state"] != "RESTORATION_RESERVED"
            or _process(parent) != parent
            or value["restoration_target"] != permit["restoration_target"]
            or value["settled_state"] != settled_reference
            or not _hex64(value["attempt_nonce"])
            or not isinstance(value["head_path"], str)
            or not isinstance(value["claim_path"], str)):
        _deny()
    created_at, valid_until = _aware_utc(value["created_at"]), _aware_utc(value["valid_until"])
    if (created_at < _aware_utc(permit["valid_from"]) or created_at >= valid_until
            or valid_until != _aware_utc(permit["valid_until"])):
        _deny()
    head_path, claim_path = Path(value["head_path"]), Path(value["claim_path"])
    if (not head_path.is_absolute() or not claim_path.is_absolute()
            or claim_path.name != f"{incident['incident_id']}.{selection.reservation_id}.child-claimed.json"
            or head_path.parent != claim_path.parent):
        _deny()
    _secure_parent(head_path.parent)
    return value


# A later, separately approved exact-source/artifact release may embed one
# canonical disposition. Never read this policy from an environment or caller.
# Preparation cannot populate it and deliberately cannot admit its own result.
INITIALIZATION_DISPOSITION = None
INITIALIZATION_ATTEMPT_SCHEMA = 'KRONOS_ADMISSION_INITIALIZATION_ATTEMPT_V1'
INITIALIZATION_DISPOSITION_SCHEMA = 'KRONOS_ADMISSION_INITIALIZATION_DISPOSITION_V1'
INITIALIZATION_EVIDENCE_SCHEMA = 'KRONOS_ADMISSION_INITIALIZATION_RESOLUTION_EVIDENCE_V1'


def _initialization_admission(root: Path, installation: dict, *, checks) -> str:
    """Read-only, exact-source admission policy, including direct R3.1 entry.

    A live native parent independently checks/syncs the same evidence before
    effects. This reader neither fsyncs nor clears an initialization fence.
    The supplied checks retain the actual owner's original budget/custody.
    """
    from kronos.common import release_admission as admission
    try:
        if (checks is None or checks.budget is None
                or type(INITIALIZATION_DISPOSITION) is not bytes
                or not 1<=len(INITIALIZATION_DISPOSITION)<MAX_DOCUMENT_BYTES):
            _deny()
        checks.check()
        checks.budget.check()
        descriptor = json.loads(INITIALIZATION_DISPOSITION)
        _closed(descriptor, frozenset({'schema', 'identity', 'scope',
            'installation_identity', 'attempt', 'genesis_head', 'genesis_phase',
            'original_outcome', 'evidence', 'authority', 'decided_at'}))
        if (INITIALIZATION_DISPOSITION != _canonical(descriptor)
                or descriptor['schema'] != INITIALIZATION_DISPOSITION_SCHEMA
                or not _identity(descriptor['identity'])
                or descriptor['scope'] != 'ADMIT_THIS_RETAINED_GENESIS_LINEAGE'
                or descriptor['installation_identity'] != installation['identity']
                or descriptor['original_outcome'] not in {
                    'OBSERVED_PREPARED_WITHIN_ORIGINAL_DEADLINE',
                    'UNPROVED_OR_LATE_UNRESOLVED'}):
            _deny()
        _aware_utc(descriptor['decided_at'])
        _secure_parent(root)
        anchor = root.parent.stat()
        if (root != Path(installation['anchor_path']) / 'failed-successor-restore-v1'
                or not admission.validate_installation_anchor(installation,checks)):
            _deny()

        def document(path):
            checks.check()
            checks.budget.check()
            before = path.lstat()
            value, raw = _current_document(path)
            after = path.lstat()
            if ((before.st_dev, before.st_ino, before.st_size, before.st_mode,
                 before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_dev, after.st_ino, after.st_size, after.st_mode,
                 after.st_mtime_ns, after.st_ctime_ns)):
                _deny()
            checks.check()
            checks.budget.check()
            return value, raw

        def reference(ref, *, name=None, raw_only=False, source_manifest=False):
            if source_manifest:
                _closed(ref, _REF)
                if (not _identity(ref['identity']) or type(ref['bytes']) is not int
                        or not 1 <= ref['bytes'] <= 8*1024*1024 or not _hex64(ref['sha256'])): _deny()
            else:
                ref = _reference(ref)
                if ref['bytes']>=MAX_DOCUMENT_BYTES: _deny()  # Native 64 KiB buffer includes NUL.
            path = Path(ref['path'])
            if name is not None and path != root / name:
                _deny()
            if raw_only:
                checks.check()
                checks.budget.check()
                before = path.lstat()
                if source_manifest:
                    _secure_parent(path.parent)
                    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                    with os.fdopen(fd,'rb') as handle:
                        held=os.fstat(handle.fileno())
                        if (not stat.S_ISREG(held.st_mode) or held.st_uid!=os.getuid()
                                or stat.S_IMODE(held.st_mode)!=0o600 or held.st_size!=ref['bytes']): _deny()
                        chunks=[];used=0
                        while used<=ref['bytes']:
                            checks.check();checks.budget.check()
                            chunk=handle.read(min(65536,ref['bytes']+1-used))
                            if not chunk:break
                            chunks.append(chunk);used+=len(chunk)
                        raw=b''.join(chunks)
                        closed=os.fstat(handle.fileno())
                        if (held.st_dev,held.st_ino,held.st_size,held.st_mtime_ns,held.st_ctime_ns)!=(
                            closed.st_dev,closed.st_ino,closed.st_size,closed.st_mtime_ns,closed.st_ctime_ns): _deny()
                    if len(raw)!=ref['bytes'] or sha256(raw).hexdigest()!=ref['sha256']: _deny()
                else:
                    raw = _read_raw(path, ref['bytes'], ref['sha256'])
                after = path.lstat()
                if ((before.st_dev,before.st_ino,before.st_size,before.st_mode,
                     before.st_uid,before.st_mtime_ns,before.st_ctime_ns) !=
                    (after.st_dev,after.st_ino,after.st_size,after.st_mode,
                     after.st_uid,after.st_mtime_ns,after.st_ctime_ns)): _deny()
                checks.check()
                checks.budget.check()
                return None, raw
            value, raw = document(path)
            if len(raw) != ref['bytes'] or sha256(raw).hexdigest() != ref['sha256']:
                _deny()
            return value, raw

        attempt, _ = reference(descriptor['attempt'], name='initialization-attempt.json')
        _closed(attempt, frozenset({'schema','attempt_id','installation','selection',
            'operator_order','parent','predecessor','eligibility','started_at','deadline_ns'}))
        if (attempt['schema'] != INITIALIZATION_ATTEMPT_SCHEMA
                or not _identity(attempt['attempt_id'])
                or attempt['installation'] != installation
                or _installation(attempt['installation']) != installation
                or type(attempt['deadline_ns']) is not int or attempt['deadline_ns'] <= 0
                or attempt['eligibility'] not in {'COLD_ABSENT','EXISTING_RELEASE_B'}):
            _deny()
        _process(attempt['parent'])
        _aware_utc(attempt['started_at'])
        selection, _ = reference(attempt['selection'])
        _closed(selection,frozenset({'schema','selection_id','mode','installation','target',
            'source_manifest','artifact_manifest','operational_order','decisions','permit','valid_from','valid_until'}))
        if (selection['schema']!='KRONOS_NATIVE_STARTUP_SELECTION_V1'
                or selection['selection_id']!=attempt['selection']['identity']
                or selection['mode']!='ORDINARY' or selection['installation']!=installation
                or selection['permit'] is not None): _deny()
        _target(selection['target'])
        if (selection['target']['source_manifest_sha256']!=selection['source_manifest']['sha256']
                or selection['target']['artifact_manifest_sha256']!=selection['artifact_manifest']['sha256']): _deny()
        if not (_aware_utc(selection['valid_from']) <= _aware_utc(attempt['started_at'])
                <= _aware_utc(selection['valid_until'])): _deny()
        reference(selection['source_manifest'],raw_only=True,source_manifest=True)
        reference(selection['artifact_manifest'],raw_only=True)
        decisions=_closed(selection['decisions'],frozenset({'sponsor','ca','pcp','product'}))
        if selection['operational_order']!=decisions['sponsor']: _deny()
        for ref in decisions.values(): reference(ref,raw_only=True)
        reference(attempt['operator_order'], raw_only=True)
        first, first_raw = reference(descriptor['genesis_head'], name='head-1.json')
        phase, _ = reference(descriptor['genesis_phase'], name=attempt['attempt_id']+'.json')
        _closed(phase, frozenset({'schema','identity','phase','original_attempt_id',
            'installation_identity','installation','parent','predecessor','selection',
            'previous','details','recorded_at'}))
        if (phase['schema'] != 'KRONOS_NATIVE_ADMISSION_PHASE_V1'
                or phase['phase'] != 'NATIVE_ACTIVATED'
                or phase['identity'] != attempt['attempt_id']
                or phase['original_attempt_id'] != attempt['attempt_id']
                or phase['installation'] != installation
                or phase['installation_identity'] != installation['identity']
                or phase['parent'] != attempt['parent']
                or phase['selection'] != attempt['selection']
                or phase['previous'] is not None
                or type(phase['details']) is not dict
                or phase['details'].get('initialization_attempt') != descriptor['attempt']):
            _deny()
        if _aware_utc(phase['recorded_at'])!=_aware_utc(attempt['started_at']): _deny()
        if attempt['eligibility'] == 'COLD_ABSENT':
            if (attempt['predecessor'] is not None or phase['predecessor'] is not None
                    or phase['details'].get('enrolled_predecessor') is not None): _deny()
        else:
            enrollment = _closed(attempt['predecessor'], frozenset({'process','evidence'}))
            _process(enrollment['process'])
            reference(enrollment['evidence'],raw_only=True,source_manifest=True)
            if (phase['predecessor'] != enrollment['process']
                    or phase['details'].get('enrolled_predecessor') != enrollment): _deny()
        evidence, _ = reference(descriptor['evidence'])
        _closed(evidence, frozenset({'schema','identity','attempt','observations',
            'missing_or_uncertain','subsequent_observations'}))
        if (evidence['schema'] != INITIALIZATION_EVIDENCE_SCHEMA
                or evidence['identity'] != descriptor['evidence']['identity']
                or evidence['attempt'] != descriptor['attempt']
                or type(evidence['missing_or_uncertain']) is not list
                or any(type(x) is not str or not x for x in evidence['missing_or_uncertain'])):
            _deny()
        for label in ('observations','subsequent_observations'):
            if type(evidence[label]) is not list: _deny()
            for ref in evidence[label]: reference(ref, raw_only=True)
        authority = _closed(descriptor['authority'], frozenset({'sponsor','ca','pcp','product'}))
        for ref in authority.values(): reference(ref, raw_only=True)

        head, current_raw = document(root / 'admission-head.json')
        count = head.get('sequence')
        if type(count) is not int or not 1 <= count <= 1_000_000_000: _deny()
        if os.path.lexists(root / f'head-{count+1}.json'): _deny()
        previous_raw = None
        previous_at = None
        fields = frozenset({'schema','installation_identity','sequence','state',
            'incident_id','active_reservation_id','active_reservation_sha256',
            'previous_head_sha256','recorded_at'})
        for sequence in range(1, count+1):
            item, raw = document(root / f'head-{sequence}.json')
            _closed(item, fields)
            at = _aware_utc(item['recorded_at'])
            if (item['schema'] != HEAD_SCHEMA or item['sequence'] != sequence
                    or item['installation_identity'] != installation['identity']
                    or item['previous_head_sha256'] != (
                        '0'*64 if previous_raw is None else sha256(previous_raw).hexdigest())
                    or (previous_at is not None and at < previous_at)):
                _deny()
            if sequence == 1 and (raw != first_raw or item != first
                    or at!=_aware_utc(attempt['started_at'])
                    or item['state'] != 'NATIVE_ACTIVATED' or item['incident_id'] is not None
                    or item['active_reservation_id'] != phase['identity']
                    or item['active_reservation_sha256'] != descriptor['genesis_phase']['sha256']):
                _deny()
            previous_raw, previous_at = raw, at
        if previous_raw != current_raw: _deny()
        checks.check()
        checks.budget.check()
        return sha256(INITIALIZATION_DISPOSITION).hexdigest()
    except FailedSuccessorRestoreError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        _deny()


def _head(path: Path, reservation: dict, selection: SelectedReservation,
          installation: dict, *, checks) -> tuple[dict, bytes]:
    _initialization_admission(path.parent, installation, checks=checks)
    value, raw = _current_document(path)
    fields = frozenset({
        "schema", "installation_identity", "sequence", "state", "incident_id",
        "active_reservation_id", "active_reservation_sha256", "previous_head_sha256",
        "recorded_at",
    })
    value = _closed(value, fields)
    if (value["schema"] != HEAD_SCHEMA
            or value["installation_identity"] != installation["identity"]
            or type(value["sequence"]) is not int or value["sequence"] < 1
            or value["state"] != "RESTORATION_RESERVED"
            or value["incident_id"] != reservation["incident_id"]
            or value["active_reservation_id"] != selection.reservation_id
            or value["active_reservation_sha256"] != selection.sha256
            or not _hex64(value["previous_head_sha256"])):
        _deny()
    _aware_utc(value["recorded_at"])
    checks.check()
    checks.budget.check()
    return value, raw


def _write_claim(path: Path, document: dict, *, custody: AdmissionCustody) -> bytes:
    _secure_parent(path.parent)
    payload = _canonical(document)
    descriptor = None
    directory = None
    try:
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        # The inherited budget remains authoritative through the irreversible
        # create.  Check after all pre-write preparation and immediately before
        # O_EXCL so expiry cannot create a claim that was never eligible.
        custody.check()
        custody.budget.check()
        descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600):
            _deny()
        written = os.write(descriptor, payload)
        if written != len(payload):
            _deny()
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.fsync(directory)
        raw = _read_raw(path, len(payload), sha256(payload).hexdigest())
        if raw != payload:
            _deny()
        return payload
    except FailedSuccessorRestoreError:
        raise
    except (OSError, ValueError):
        _deny()
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if directory is not None:
            try:
                os.close(directory)
            except OSError:
                pass


def consume_failed_successor_restore(
        permit_selection: SelectedPermit,
        reservation_selection: SelectedReservation,
        *, custody: AdmissionCustody,
        child: RestorationChildIdentity,
        clock=lambda: datetime.now(UTC)) -> RestorationStartupContext:
    """Validate exact R3 facts and irreversibly claim one restoration child.

    The caller must have obtained ``permit_selection`` through the approved
    trusted-operator procedure and ``reservation_selection`` from the native
    parent.  This function never searches for either input and never writes the
    native admission head.
    """
    try:
        if (type(permit_selection) is not SelectedPermit
                or type(reservation_selection) is not SelectedReservation
                or type(child) is not RestorationChildIdentity
                or type(custody) is not AdmissionCustody):
            _deny()
        if type(custody.budget) is not ValidationBudget:
            _deny()
        custody.check()
        initial_now = clock()
        if (not isinstance(initial_now, datetime) or initial_now.tzinfo is None
                or initial_now.utcoffset() != UTC.utcoffset(initial_now)):
            _deny()

        permit_document, permit_raw = _document(
            permit_selection.path, permit_selection.byte_size, permit_selection.sha256)
        permit = _permit(permit_document, permit_selection, initial_now)
        incident_document, incident_raw, incident_ref = _load_reference(permit["incident"])
        incident = _incident(incident_document, incident_ref, permit["installation"])
        settled_document, settled_raw, settled_ref = _load_reference(permit["settled_state"])
        settled = _settled(settled_document, settled_ref, incident)
        failure_document, failure_raw, failure_ref = _load_reference(permit["failure_cleanup"])
        failure = _failure(failure_document, failure_ref, incident, settled_ref)
        reservation_document, reservation_raw = _document(
            reservation_selection.path, reservation_selection.byte_size,
            reservation_selection.sha256)
        reservation = _reservation(
            reservation_document, reservation_selection, permit, permit_selection,
            incident, settled_ref)

        if (incident["failed_target"]["revision"]
                != incident["failed_successor"]["revision"]
                or _aware_utc(incident["created_at"]) > initial_now
                or _aware_utc(settled["certified_at"]) > initial_now
                or _aware_utc(failure["recorded_at"]) > initial_now
                or _aware_utc(reservation["created_at"]) > initial_now
                or not (_aware_utc(settled["certified_at"])
                        <= _aware_utc(failure["recorded_at"])
                        <= _aware_utc(permit["created_at"]))):
            _deny()

        evidence_root = (Path(permit["installation"]["anchor_path"])
                         / "failed-successor-restore-v1")
        if (reservation_selection.path.parent != evidence_root
                or any(Path(reference["path"]).parent != evidence_root
                       for reference in (incident_ref, failure_ref, settled_ref))
                or Path(reservation["head_path"]).parent != evidence_root
                or Path(reservation["claim_path"]).parent != evidence_root):
            _deny()

        custody.check()
        from kronos.common import release_admission as admission
        binding = custody.binding
        installation = permit["installation"]
        parent = reservation["parent"]
        target = permit["restoration_target"]
        if (Path(installation["anchor_path"]) != binding.path
                or not admission.validate_installation_anchor(installation,custody)
                or child.process_id != os.getpid()
                or child.parent_pid != os.getppid()
                or child.parent_pid != custody.parent
                or parent["pid"] != child.parent_pid
                or parent["kernel_birth"] != child.parent_kernel_birth
                or child.process_id in {parent["pid"], incident["failed_successor"]["pid"]}
                or child.loaded_revision != target["revision"]
                or child.source_manifest_sha256 != target["source_manifest_sha256"]
                or child.artifact_manifest_sha256 != target["artifact_manifest_sha256"]
                or child.pinned_capture_sha256 != target["pinned_capture_sha256"]
                or not _hex64(child.runtime_identity)):
            _deny()

        head_path = Path(reservation["head_path"])
        _, head_raw = _head(head_path, reservation, reservation_selection, installation, checks=custody)
        head_document = json.loads(head_raw)
        if (_aware_utc(head_document["recorded_at"]) < _aware_utc(reservation["created_at"])
                or _aware_utc(head_document["recorded_at"]) > initial_now):
            _deny()
        claim_now = clock()
        if (not isinstance(claim_now, datetime) or claim_now.tzinfo is None
                or claim_now.utcoffset() != UTC.utcoffset(claim_now)
                or claim_now < initial_now
                or not _aware_utc(permit["valid_from"]) <= claim_now
                    <= _aware_utc(reservation["valid_until"])):
            _deny()

        checkpoint = settled["notification_checkpoint"]
        maintenance_identity = sha256(_canonical({
            "protocol": CLAIM_SCHEMA,
            "incident_id": incident["incident_id"],
            "reservation_id": reservation["reservation_id"],
            "attempt_nonce": reservation["attempt_nonce"],
            "process_id": child.process_id,
            "kernel_birth": child.kernel_birth,
            "runtime_identity": child.runtime_identity,
        })).hexdigest()
        claim = {
            "schema": CLAIM_SCHEMA,
            "incident_id": incident["incident_id"],
            "original_attempt_id": incident["original_attempt_id"],
            "permit_id": permit["permit_id"],
            "permit_sha256": permit_selection.sha256,
            "reservation_id": reservation["reservation_id"],
            "reservation_sha256": reservation_selection.sha256,
            "attempt_nonce": reservation["attempt_nonce"],
            "installation_identity": installation["identity"],
            "parent": parent,
            "child": {
                "pid": child.process_id,
                "kernel_birth": child.kernel_birth,
                "runtime_identity": child.runtime_identity,
                "revision": child.loaded_revision,
            },
            "source_manifest_sha256": child.source_manifest_sha256,
            "artifact_manifest_sha256": child.artifact_manifest_sha256,
            "pinned_capture_sha256": child.pinned_capture_sha256,
            "settled_state_id": settled["settled_state_id"],
            "settled_state_sha256": settled_ref["sha256"],
            "maintenance_identity": maintenance_identity,
            "claimed_at": claim_now.isoformat(),
        }
        _write_claim(Path(reservation["claim_path"]), claim, custody=custody)

        # A successful exclusive write is spent even if a subsequent recheck
        # fails.  Re-read every selected input and the mutable admission head;
        # never delete or repair the claim on disagreement.
        custody.check()
        if (_read_raw(permit_selection.path, permit_selection.byte_size,
                      permit_selection.sha256) != permit_raw
                or _read_raw(reservation_selection.path,
                             reservation_selection.byte_size,
                             reservation_selection.sha256) != reservation_raw
                or _read_raw(Path(incident_ref["path"]), incident_ref["bytes"],
                             incident_ref["sha256"]) != incident_raw
                or _read_raw(Path(failure_ref["path"]), failure_ref["bytes"],
                             failure_ref["sha256"]) != failure_raw
                or _read_raw(Path(settled_ref["path"]), settled_ref["bytes"],
                             settled_ref["sha256"]) != settled_raw):
            _deny()
        _, final_head_raw = _head(head_path, reservation, reservation_selection, installation, checks=custody)
        if final_head_raw != head_raw:
            _deny()
        final_now = clock()
        if (not isinstance(final_now, datetime) or final_now.tzinfo is None
                or final_now.utcoffset() != UTC.utcoffset(final_now)
                or final_now < claim_now
                or final_now > _aware_utc(reservation["valid_until"])):
            _deny()
        original_v2 = incident["original_v2"]
        context = RestorationStartupContext(
            incident_id=incident["incident_id"],
            original_attempt_id=incident["original_attempt_id"],
            permit_id=permit["permit_id"], permit_sha256=permit_selection.sha256,
            reservation_id=reservation["reservation_id"],
            reservation_sha256=reservation_selection.sha256,
            process_id=child.process_id, runtime_identity=child.runtime_identity,
            loaded_revision=child.loaded_revision,
            maintenance_identity=maintenance_identity,
            settled_state_manifest_identity=settled["state_manifest_identity"],
            settled_state_manifest_sha256=settled["state_manifest_sha256"],
            notification_state=checkpoint["state"],
            notification_pending_count=checkpoint["pending_count"],
            notification_sha256=checkpoint["sha256"],
            original_v2_handoff_identity=original_v2["handoff_identity"],
            original_v2_handoff_sha256=original_v2["handoff_sha256"],
            original_v2_consumption_identity=original_v2["consumption_identity"],
            original_v2_consumption_sha256=original_v2["consumption_sha256"],
        )
        # Final source/head validation can consume the remaining inherited
        # budget.  A late result is denied while the exclusive claim remains
        # permanently spent; no budget is renewed and no claim is repaired.
        custody.check()
        custody.budget.check()
        return context
    except FailedSuccessorRestoreError:
        raise
    except (AttributeError, KeyError, OSError, TypeError, ValueError, OverflowError):
        _deny()
