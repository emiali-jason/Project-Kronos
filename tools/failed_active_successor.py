"""Read-only exact successor verification for the authorized recovery launcher.

No Browser construction, remote calls, restoration, enrollment or mutations.
The launcher supplies documents read from its child and an already hash-bound
approved relation. This check confers no authority on an arbitrary relation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def read_private(path, *, private=False):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("unsafe path")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or private and info.st_mode & 0o077 or not 0 < info.st_size <= 262144):
            raise ValueError("unsafe record")
        raw = source.read(262145)
    if len(raw) != info.st_size:
        raise ValueError("record changed")
    return raw


def verify_documents(documents, relation, *, pid, revision, generation, capability, research_state="ACTIVE"):
    from kronos.intraday.live_shadow_epochs import capabilities, validate
    from kronos.intraday.live_shadow_transition import capability_identity
    validate(relation)
    if relation["kind"] != "successor_compatibility":
        raise ValueError("wrong relation")
    body = relation["body"]
    runtime, status, intraday = documents
    maintenance = {"protocol": "KRONOS_MAINTENANCE_HANDOFF_V1", "state": "INACTIVE",
        "active": False, "generation": generation, "startup": "READY", "failure": None}
    if (runtime["schema"] != "KRONOS-RUNTIME-STATE/1.0.0"
            or runtime["process"] != {"pid": pid, "revision": revision, "source_state": "CLEAN_COMMIT"}
            or runtime["maintenance"] != maintenance or status["maintenance"] != maintenance
            or status["service"] != "KRONOS_BROWSER_V1" or status["runtime_ready"] is not True
            or status["provider"] != "DISCONNECTED"
            or runtime["rest_authentication"] != "DISCONNECTED"
            or runtime["rest_capability"] != "ABSENT" or runtime["connection_attempt"] is not None
            or intraday["active_operation_identity"] is not None or intraday["current_failure"] is not None):
        raise ValueError("successor binding")
    provider = runtime["provider_runtime"]
    if (provider["capability_state"] != "ABSENT" or provider["cleanup_state"] != "COMPLETE"
            or any(type(provider[name]) is not int or provider[name] != 0 for name in
                   ("owned_work_count", "retained_lease_count", "unresolved_cleanup_count"))):
        raise ValueError("provider authority")
    shadow = intraday["live_shadow"]
    if research_state == "HISTORICAL_ACCEPTANCE_EXPIRED":
        restored = (shadow["runtime_accepted"] is False and shadow["enabled"] is False
            and shadow["acceptance_disposition"] == research_state
            and shadow.get("historical_restoration") == "KRONOS-WO06H-HISTORICAL-RESTORATION/1.0.0"
            and shadow.get("historical_evidence") == "READABLE"
            and shadow.get("collection_authority") == "EXPIRED"
            and all(type(shadow["counts"][key]) is int for key in ("cohort_a", "cohort_b", "eod_available"))
            and {key:shadow["counts"][key] for key in ("cohort_a", "cohort_b", "eod_available")}
                == {"cohort_a":1, "cohort_b":18, "eod_available":0})
    else:
        restored = (research_state == "ACTIVE" and shadow["runtime_accepted"] is True
            and shadow["enabled"] is True
            and shadow["acceptance_disposition"] == "EXISTING_ACCEPTANCE_RESTORED")
    if (not restored or shadow["acceptance_identity"] != body["acceptance"]
            or shadow["current_epoch"] != body["epoch"]
            or shadow["window"] != {"identity": body["window"], "start": body["start"], "end": body["end"]}
            or any(shadow[name] is not None for name in ("failure", "epoch_failure", "publication_hook_failure"))):
        raise ValueError("restoration binding")
    proof = shadow["runtime_proof"]
    mapped = capabilities(proof)
    if (type(proof["pid"]) is not int or proof["pid"] != pid or proof["revision"] != revision
            or proof["source_state"] != "CLEAN_COMMIT"
            or capability_identity(proof) != capability or body["target_aggregate"] != capability
            or proof["configuration"] != body["configuration"]
            or [asdict(mapped[name]) for name in sorted(mapped)] != body["target_capabilities"]
            or any(row["disposition"] != "APPROVED" for row in body["owner_approvals"])):
        raise ValueError("capability binding")


# IWO-07R3: closed incident verification. This is not compatibility authority;
# the unchanged startup owners must establish their own exact restoration.
INCIDENT_SCHEMA = "KRONOS-IWO07R3-RECOVERY-AUTHORIZATION/1.0.0"
INCIDENT_REVISION = "7b0729402687b2f05607ce99a5c99a9cea35568b"
INCIDENT_PID = 45583
INCIDENT_START_US = 1791996740356956
INCIDENT_GENERATION = "02a8392f4d88082bf96d3e807c6f1acf00e381ac63f62f7433aecfd2e1c762b3"
INCIDENT_PACKAGE = "35a468ca66dfe127479112d777323a63c1221cd381c63d93db09a8b36d4cbd18"
INCIDENT_DIAGNOSIS = "014e7571a779a6411655240b92dfbe77bda4f85661c95c243738118b1e3d4d6b"
INCIDENT_DIRECTORY = Path("/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/SWING/KRONOS QUESTIONS")
INCIDENT_DIRECTORY_ID = (16777232, 696853852, 501, 20, 0o700)
INCIDENT_ARTIFACTS = (
    ("KRONOS_V3_REVIEW_20260904_094858_IST_QUESTIONS.pdf", 943061,
     "f97f6c6009e45594342df83a35d3007e75640770b445f16758212a8a6b0ba277"),
    ("KRONOS_V3_REVIEW_BA8681C0DACC46F98E9E51FEFEA037D3_RECOVERY_01A_QUESTIONS.pdf", 944514,
     "e87517e430c0bd82f3c7aed630f723843916cd8f05f4f12e049cfe3b3af8555c"),
)
INCIDENT_SELECTION = Path("/Users/imranali/Library/Application Support/KRONOS/evidence/swing-v1/native-review/pdf-transport-v3")
INCIDENT_SELECTION_HASHES = {
    "current-review-pack.json": "426e2c70dfc866f3c1c8ffc198a7a74aa1d8d4decc7e7a86a843f5392728c18b",
    "artifact-recoveries/d4a0303941ba9274174e2f6c2dd10a7aa383ff2ffde8e014017f90dbe29c1e4f.json":
        "229e09e408d57080f4b1894fc64ea2d38049dcb6a3783f7ae390d5760fe61458",
}
INCIDENT_AUTH_FIELDS = frozenset((
    "schema state recovery_class attempt_identity sponsor_authorization_reference "
    "sponsor_authorization_path sponsor_authorization_sha256 predecessor_revision "
    "predecessor_pid predecessor_start_us predecessor_maintenance_identity "
    "private_control_sha256 predecessor_package_identity successor_revision "
    "installed_package_identity rollback_bundle rollback_package_identity "
    "diagnosis_path diagnosis_sha256 stage_a_receipt_path stage_a_receipt_sha256 "
    "valid_from_us valid_until_us").split())


def _incident_require(condition, reason):
    if not condition:
        raise ValueError("IWO07R3_" + reason)


def _incident_digest(path, *, expected_size=None):
    """Descriptor-anchored no-follow traversal; no evidence writes or imports."""
    path = Path(path)
    _incident_require(path.is_absolute() and ".." not in path.parts, "PATH")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(leaf)
            _incident_require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                and (expected_size is None or before.st_size == expected_size), "FILE")
            digest = hashlib.sha256()
            while block := os.read(leaf, 65536):
                digest.update(block)
            after = os.fstat(leaf)
            current = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            # A lawful read may advance access time. Compare immutable-file
            # stability using nanosecond modification/change times, not atime.
            stable = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_size",
                      "st_nlink", "st_mtime_ns", "st_ctime_ns")
            _incident_require(all(getattr(before, key) == getattr(after, key) for key in stable)
                and (after.st_dev, after.st_ino) == (current.st_dev, current.st_ino), "FILE_CHANGED")
            return digest.hexdigest(), before
        finally:
            os.close(leaf)
    finally:
        os.close(fd)


def verify_incident_artifacts(receipt):
    _incident_require(set(receipt) == {"schema", "state", "incident_revision", "incident_generation",
        "directory_identity", "artifacts", "completed_at"}
        and receipt["schema"] == "KRONOS-IWO07R3-ARTIFACT-RESTORATION/1.0.0"
        and receipt["state"] == "COMPLETE"
        and receipt["incident_revision"] == INCIDENT_REVISION
        and receipt["incident_generation"] == INCIDENT_GENERATION, "STAGE_A_RECEIPT")
    for parent in (INCIDENT_DIRECTORY, *INCIDENT_DIRECTORY.parents):
        _incident_require(not parent.is_symlink(), "DIRECTORY_LINK")
    info = INCIDENT_DIRECTORY.stat()
    identity = (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))
    _incident_require(identity == INCIDENT_DIRECTORY_ID == tuple(receipt["directory_identity"]), "DIRECTORY_IDENTITY")
    _incident_require(type(receipt["artifacts"]) is list and len(receipt["artifacts"]) == 2, "ARTIFACT_PAIR")
    for row, (name, size, expected) in zip(receipt["artifacts"], INCIDENT_ARTIFACTS, strict=True):
        path = INCIDENT_DIRECTORY / name
        actual, info = _incident_digest(path, expected_size=size)
        _incident_require(set(row) == {"path", "size", "sha256", "device", "inode", "uid", "gid", "mode", "prior_absent"}
            and row == dict(path=str(path), size=size, sha256=expected, device=info.st_dev,
                inode=info.st_ino, uid=info.st_uid, gid=info.st_gid, mode=0o600, prior_absent=True)
            and row["prior_absent"] is True and stat.S_IMODE(info.st_mode) == 0o600 and actual == expected, "ARTIFACT_IDENTITY")
    after = INCIDENT_DIRECTORY.stat()
    _incident_require((after.st_dev, after.st_ino, after.st_uid, after.st_gid, stat.S_IMODE(after.st_mode))
        == INCIDENT_DIRECTORY_ID, "DIRECTORY_CHANGED")
    for relative, expected in INCIDENT_SELECTION_HASHES.items():
        _incident_require(_incident_digest(INCIDENT_SELECTION / relative)[0] == expected, "SELECTION_CHANGED")


def verify_incident_authorization(authority, *, now_us, revision):
    _incident_require(set(authority) == INCIDENT_AUTH_FIELDS, "AUTH_FIELDS")
    exact = dict(schema=INCIDENT_SCHEMA, state="SPONSOR_APPROVED",
        recovery_class="FAILED_ACTIVE_RECOVERY_REPLACEMENT", predecessor_revision=INCIDENT_REVISION,
        predecessor_pid=INCIDENT_PID, predecessor_start_us=INCIDENT_START_US,
        predecessor_maintenance_identity=INCIDENT_GENERATION,
        predecessor_package_identity=INCIDENT_PACKAGE, rollback_package_identity=INCIDENT_PACKAGE,
        diagnosis_sha256=INCIDENT_DIAGNOSIS, successor_revision=revision)
    _incident_require(all(type(authority[k]) is type(v) and authority[k] == v for k, v in exact.items())
        and re.fullmatch("[a-f0-9]{40}", revision) and revision != INCIDENT_REVISION, "INCIDENT_IDENTITY")
    _incident_require(all(type(authority[k]) is str and re.fullmatch("[a-f0-9]{64}", authority[k]) for k in
        ("attempt_identity", "private_control_sha256", "installed_package_identity",
         "stage_a_receipt_sha256", "sponsor_authorization_sha256"))
        and authority["installed_package_identity"] != INCIDENT_PACKAGE
        and type(authority["sponsor_authorization_reference"]) is str
        and bool(authority["sponsor_authorization_reference"].strip()), "AUTH_IDENTITY")
    start, end = authority["valid_from_us"], authority["valid_until_us"]
    _incident_require(type(start) is int and type(end) is int
        and INCIDENT_START_US < start <= now_us < end and 0 < end-start <= 1800000000, "AUTH_TIME")
    for path, digest in (("diagnosis_path", "diagnosis_sha256"),
                         ("sponsor_authorization_path", "sponsor_authorization_sha256"),
                         ("stage_a_receipt_path", "stage_a_receipt_sha256")):
        _incident_require(_incident_digest(authority[path])[0] == authority[digest], "AUTH_ARTIFACT_CHANGED")
    raw = read_private(authority["stage_a_receipt_path"], private=True)
    _incident_require(hashlib.sha256(raw).hexdigest() == authority["stage_a_receipt_sha256"], "RECEIPT_CHANGED")
    receipt = _json(raw)
    verify_incident_artifacts(receipt)
    completed = datetime.fromisoformat(receipt["completed_at"])
    _incident_require(completed.tzinfo is not None and INCIDENT_START_US < int(completed.timestamp()*1000000)
        <= now_us, "RESTORATION_TIME")


def verify_incident_documents(documents, *, pid, revision, generation, successor,
                              _capability=None, _start_us=None,
                              _failure="SWING_RESTORATION_NOT_ESTABLISHED"):
    from kronos.browser.runtime_state import _swing_restoration_failure
    from kronos.intraday.live_shadow_transition import capability_identity
    runtime, status, intraday = documents
    maintenance = dict(protocol="KRONOS_MAINTENANCE_HANDOFF_V1", state="INACTIVE" if successor else "FAILED_ACTIVE",
        active=not successor, generation=generation, startup="READY" if successor else "BLOCKED",
        failure=None if successor else _failure)
    _incident_require(runtime["process"] == dict(pid=pid, revision=revision, source_state="CLEAN_COMMIT")
        and runtime["schema"] == "KRONOS-RUNTIME-STATE/1.0.0"
        and runtime["maintenance"] == status["maintenance"] == maintenance
        and status["service"] == "KRONOS_BROWSER_V1" and status["runtime_ready"] is successor
        and status["provider"] == runtime["rest_authentication"] == "DISCONNECTED"
        and runtime["rest_capability"] == "ABSENT" and runtime["connection_attempt"] is None
        and intraday["active_operation_identity"] is None and intraday["current_failure"] is None, "RUNTIME")
    provider = runtime["provider_runtime"]
    _incident_require(provider["capability_state"] == "ABSENT" and provider["cleanup_state"] == "COMPLETE"
        and all(type(provider[k]) is int and provider[k] == 0 for k in
            ("owned_work_count", "retained_lease_count", "unresolved_cleanup_count")), "PROVIDER")
    shadow = intraday["live_shadow"]
    _incident_require(shadow["acceptance_disposition"] == "HISTORICAL_ACCEPTANCE_EXPIRED"
        and shadow["historical_restoration"] == "KRONOS-WO06H-HISTORICAL-RESTORATION/1.0.0"
        and shadow["historical_evidence"] == "READABLE" and shadow["collection_authority"] == "EXPIRED"
        and shadow["enabled"] is False and shadow["runtime_accepted"] is False
        and all(shadow[k] is None for k in ("failure", "epoch_failure", "publication_hook_failure"))
        and shadow["acceptance_identity"] == "WO06H-ACCEPTANCE-705befed9c2ff4d8d3a53aa94b4b9d8b9c5d67b99f6a0093d22ed4335cd71259"
        and shadow["current_epoch"] == "WO06H-EPOCH-4bc5e40a837f8ba26ea8ed91245148c4e45a6d24178d90ba187822586b16dcc3"
        and shadow["window"] == dict(identity="WO06H-WINDOW-ed7a53dfdc22e1f95440c7778b381a9a2d7ad69d10b892a5857c29576f1e094c",
            start="2026-09-12T07:50:33.006722+05:30", end="2026-10-12T07:50:33.006722+05:30")
        and all(type(shadow["counts"][k]) is int and shadow["counts"][k] == v for k,v in
            dict(cohort_a=1, cohort_b=18, eod_available=0).items()), "WO06H_HISTORY")
    proof = shadow["runtime_proof"]
    _incident_require(type(proof["pid"]) is int and proof["pid"] == pid and proof["revision"] == revision
        and proof["source_state"] == "CLEAN_COMMIT"
        and capability_identity(proof) == (INCIDENT_CAPABILITY if _capability is None else _capability),
        "WO06H_CAPABILITY")
    if not successor:
        if _start_us is None:
            _incident_require(proof["startup"] == "2026-10-14T16:52:20.386116+00:00", "START_IDENTITY")
        else:
            # Startup capture follows kernel birth; exact kernel identity is
            # independently checked by the launcher, not inferred from this timestamp.
            _incident_require(_start_us <= _release_time_us(proof["startup"]), "START_IDENTITY")
    else:
        outcomes = runtime["startup_restoration_outcomes"]
        _incident_require(type(outcomes) is list and all(type(row) is list and len(row) == 2
            and all(type(v) is str for v in row) for row in outcomes)
            and not _swing_restoration_failure(tuple(tuple(row) for row in outcomes)), "SWING_OUTCOMES")
        _incident_require(runtime["owner_restoration"] == "DEFERRED_PROVIDER_DISCONNECTED", "MONITORING")


def incident_main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident-phase", required=True, choices=("preflight", "retired", "successor"))
    for name in ("authorization", "authorization-sha256", "revision", "generation", "maintenance-root", "evidence-root"):
        parser.add_argument("--"+name, required=True)
    parser.add_argument("--pid", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        now = datetime.now(timezone.utc)
        now_us = int(now.timestamp()*1000000)
        raw = read_private(args.authorization, private=True)
        _incident_require(hashlib.sha256(raw).hexdigest() == args.authorization_sha256, "AUTH_CHANGED")
        authority = _json(raw)
        verify_incident_authorization(authority, now_us=now_us, revision=args.revision)
        raw = sys.stdin.buffer.read(196609)
        _incident_require(len(raw) <= 196608, "DOCUMENT_SIZE")
        if args.incident_phase != "retired":
            successor = args.incident_phase == "successor"
            documents = _json(raw)
            verify_incident_documents(documents, pid=args.pid if successor else INCIDENT_PID,
                revision=args.revision if successor else INCIDENT_REVISION,
                generation=args.generation if successor else INCIDENT_GENERATION, successor=successor)
        if args.incident_phase == "successor":
            claim = _json(read_private(Path(args.maintenance_root)/(args.generation+".consumed.json"), private=True))
            _incident_require(set(claim) == {"schema", "generation", "parent_pid", "process_id", "runtime_identity", "accepted_at"}
                and claim["schema"] == "KRONOS_MAINTENANCE_CONSUMPTION_V2" and claim["generation"] == args.generation
                and type(claim["parent_pid"]) is int and claim["parent_pid"] == INCIDENT_PID
                and type(claim["process_id"]) is int and claim["process_id"] == args.pid
                and re.fullmatch("[a-f0-9]{64}",claim["runtime_identity"]), "CONSUMPTION")
            receipt = _json(read_private(Path(args.evidence_root)/"shared/provider-connection-v1/maintenance"/
                (claim["runtime_identity"]+"-startup.json"), private=True))
            _incident_require(set(receipt) == {"schema", "runtime_identity", "maintenance_identity", "at", "trigger"}
                and receipt["schema"] == "RUNTIME_STARTUP_MAINTENANCE_EXIT_V1"
                and receipt["runtime_identity"] == claim["runtime_identity"]
                and receipt["maintenance_identity"] == args.generation
                and receipt["trigger"] == "VERIFIED_CANONICAL_STARTUP"
                and datetime.fromisoformat(documents[2]["live_shadow"]["runtime_proof"]["startup"])
                <= datetime.fromisoformat(claim["accepted_at"]) <= datetime.fromisoformat(receipt["at"]) <= now,
                "STARTUP_RECEIPT")
    except Exception:
        print("KRONOS_IWO07R3_RECOVERY_V1 INVALID")
        return 2
    print("KRONOS_IWO07R3_RECOVERY_V1 VALID")
    return 0

INCIDENT_CAPABILITY = 'WO06H-CAPABILITY-f61cfe6c7395d0ee8554d82946a5a7fa88444c09151f53bc171253a3d35aa31b'


# Closed 2026-10-22 Swing release incident. This is validation only; the sealed
# launcher still owns source admission, private control, reservation and drain.
RELEASE_SCHEMA = "KRONOS-SWING-RELEASE-RECOVERY-AUTHORIZATION/1.0.0"
RELEASE_INCIDENT = "KRONOS-SWING-FAILED-ACTIVE-AND-FENCED-RECOVERY-ENGINEERING-20261022"
RELEASE_PREDECESSORS = frozenset((
    "355922f92f7b826191ae86bd7bb0473349f3c1cc",
    "1579f1cbad2f98370b62f5511a7d339c131ab15a"))
RELEASE_FAILURES = frozenset((
    "ACCEPTANCE_RESTORATION_NOT_ESTABLISHED", "SWING_RESTORATION_NOT_ESTABLISHED",
    "RUNTIME_RESTORATION_PROOF_UNAVAILABLE", "WO11_RESTORATION_FAILED",
    "WO17_RESTORATION_FAILED", "STARTUP_COMPLETION_RECORD_UNAVAILABLE"))
RELEASE_AUTH_FIELDS = frozenset((
    "schema state recovery_class incident_id attempt_identity sponsor_authorization_reference "
    "sponsor_authorization_path sponsor_authorization_sha256 predecessor_revision predecessor_pid "
    "predecessor_start_us predecessor_maintenance_identity private_control_sha256 "
    "installed_package_identity rollback_bundle rollback_package_identity successor_revision "
    "expected_successor_capability expected_startup_failure diagnosis_path diagnosis_sha256 "
    "artifact_review_path artifact_review_sha256 valid_from_us valid_until_us").split())
RELEASE_REVIEW_BINDINGS = frozenset((
    "incident_id predecessor_revision predecessor_pid predecessor_start_us "
    "predecessor_maintenance_identity private_control_sha256 successor_revision installed_package_identity "
    "rollback_package_identity expected_successor_capability expected_startup_failure "
    "diagnosis_sha256 sponsor_authorization_reference sponsor_authorization_sha256").split())


def _release_time_us(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("RELEASE_TIMEZONE")
    delta = parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def verify_release_authorization(authority, *, now_us, revision):
    """Recheck the exact reviewed incident; never enroll or repair authority."""
    def require(condition, reason):
        if not condition:
            raise ValueError("SWING_RELEASE_" + reason)
    require(type(authority) is dict and set(authority) == RELEASE_AUTH_FIELDS, "AUTH_FIELDS")
    require(authority["schema"] == RELEASE_SCHEMA and authority["state"] == "SPONSOR_APPROVED"
        and authority["recovery_class"] == "FAILED_ACTIVE_RECOVERY_REPLACEMENT"
        and authority["incident_id"] == RELEASE_INCIDENT
        and authority["predecessor_revision"] in RELEASE_PREDECESSORS
        and type(revision) is str and re.fullmatch("[a-f0-9]{40}", revision)
        and authority["successor_revision"] == revision
        and revision != authority["predecessor_revision"], "SCOPE")
    require(type(authority["predecessor_pid"]) is int and 1 < authority["predecessor_pid"] <= 2147483647
        and type(authority["predecessor_start_us"]) is int and authority["predecessor_start_us"] > 0
        and authority["expected_startup_failure"] in RELEASE_FAILURES
        and type(authority["expected_successor_capability"]) is str
        and re.fullmatch("WO06H-CAPABILITY-[a-f0-9]{64}", authority["expected_successor_capability"]), "PROCESS")
    require(all(type(authority[k]) is str and re.fullmatch("[a-f0-9]{64}", authority[k]) for k in
        ("attempt_identity", "predecessor_maintenance_identity", "private_control_sha256",
         "installed_package_identity", "rollback_package_identity", "diagnosis_sha256",
         "sponsor_authorization_sha256", "artifact_review_sha256"))
        and type(authority["sponsor_authorization_reference"]) is str
        and bool(authority["sponsor_authorization_reference"].strip()), "IDENTITY")
    start, end = authority["valid_from_us"], authority["valid_until_us"]
    require(type(start) is int and type(end) is int and type(now_us) is int
        and start >= 1791771633006722
        and authority["predecessor_start_us"] < start <= now_us < end
        and 0 < end-start <= 1800000000, "VALIDITY")
    for name in ("sponsor_authorization", "diagnosis", "artifact_review"):
        require(_incident_digest(authority[name+"_path"])[0] == authority[name+"_sha256"], "ARTIFACT_CHANGED")
    raw = read_private(authority["artifact_review_path"], private=True)
    require(hashlib.sha256(raw).hexdigest() == authority["artifact_review_sha256"], "REVIEW_CHANGED")
    review = _json(raw)
    require(type(review) is dict and set(review) == RELEASE_REVIEW_BINDINGS | {"schema", "state", "approved_at"}
        and review["schema"] == "KRONOS-SWING-RECOVERY-ARTIFACT-REVIEW/1.0.0"
        and review["state"] == "APPROVED"
        and all(type(review[k]) is type(authority[k]) and review[k] == authority[k]
                for k in RELEASE_REVIEW_BINDINGS)
        and authority["predecessor_start_us"] <= _release_time_us(review["approved_at"]) <= start,
        "ARTIFACT_REVIEW_BINDING")


def _release_runtime_identity(intraday, *, pid, revision):
    """Bind receipt identity to the child's actual retained startup manifest."""
    from kronos.intraday.runtime_identity import (
        LoadedCapability, RuntimeManifest, StartupEvidence,
    )
    projection = intraday["runtime_identity"]
    if type(projection) is not dict or projection["availability"] != "RETAINED":
        raise ValueError("SWING_RELEASE_RUNTIME_IDENTITY")
    raw_startup = projection["startup"]
    if (type(raw_startup) is not dict
            or raw_startup.get("load_verification") != "PINNED_STARTUP_IMPORTS"
            or type(raw_startup.get("source_snapshot_digest")) is not str
            or re.fullmatch("[a-f0-9]{64}", raw_startup["source_snapshot_digest"]) is None
            or type(raw_startup["startup_boundary_at"]) is not str
            or type(raw_startup["loaded_modules"]) is not list
            or any(type(row) is not list or len(row) != 2
                   or any(type(value) is not str for value in row)
                   for row in raw_startup["loaded_modules"])
            or type(projection["capabilities"]) is not list):
        raise ValueError("SWING_RELEASE_STARTUP_EVIDENCE")
    startup = StartupEvidence(**dict(raw_startup,
        startup_boundary_at=datetime.fromisoformat(raw_startup["startup_boundary_at"]),
        loaded_modules=tuple(tuple(row) for row in raw_startup["loaded_modules"])))
    manifest = RuntimeManifest(
        startup=startup,
        configuration_identity=projection["configuration_identity"],
        capabilities=tuple(LoadedCapability(**row) for row in projection["capabilities"]),
        manifest_identity=projection["manifest_identity"],
        product=projection["product"], contract_version=projection["contract_version"])
    expected_proof = dict(manifest=manifest.manifest_identity, pid=startup.process_id,
        revision=startup.source_revision, source_state=startup.source_state,
        startup=startup.startup_boundary_at.isoformat(), configuration=manifest.configuration_identity,
        capabilities=[asdict(capability) for capability in manifest.capabilities])
    if (startup.process_id != pid or startup.source_revision != revision
            or startup.source_state != "CLEAN_COMMIT" or startup.branch != "develop"
            or startup.checkout_mode != "BRANCH"
            or projection["loaded_commit_revision"] != revision
            or projection["startup_checkout_mode"] != startup.checkout_mode
            or projection["source_proof_scope"] != "LAUNCHER_STARTUP_IMPORTS"
            or intraday["live_shadow"]["runtime_proof"] != expected_proof):
        raise ValueError("SWING_RELEASE_RUNTIME_PROOF_BINDING")
    # Canonical tools/kronos_browser.py uses this same derivation for the
    # consumed V2 record and ConnectionProcess startup receipt identity.
    return hashlib.sha256(startup.evidence_identity.encode()).hexdigest()


def verify_release_documents(documents, authority, *, pid, generation, successor, now_us):
    """The existing startup owners, never a sampled idle state, establish health."""
    if type(documents) is not list or len(documents) != 3:
        raise ValueError("SWING_RELEASE_DOCUMENTS")
    revision = authority["successor_revision"] if successor else authority["predecessor_revision"]
    if (type(pid) is not int or pid < 2 or not re.fullmatch("[a-f0-9]{64}", generation)
            or not successor and (pid != authority["predecessor_pid"]
                or generation != authority["predecessor_maintenance_identity"])):
        raise ValueError("SWING_RELEASE_PROCESS_BINDING")
    verify_incident_documents(documents, pid=pid, revision=revision, generation=generation,
        successor=successor, _capability=authority["expected_successor_capability"],
        _start_us=authority["predecessor_start_us"], _failure=authority["expected_startup_failure"])
    startup_us = _release_time_us(documents[2]["live_shadow"]["runtime_proof"]["startup"])
    if startup_us > now_us or successor and startup_us < authority["valid_from_us"]:
        raise ValueError("SWING_RELEASE_START_TIME")
    # These are additional read-only checks. C independently requires OPEN and
    # exact counted-owner scope before any one-use reservation/shutdown.
    drain = documents[0]["maintenance_drain"]
    if (drain["state"] != "OPEN" or drain["generation"] is not None
            or drain["failure"] is not None or documents[0]["maintenance_claim"] != "DRAINABLE"):
        raise ValueError("SWING_RELEASE_FENCED")
    return _release_runtime_identity(documents[2], pid=pid, revision=revision)


def release_main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-phase", required=True, choices=("preflight", "retired", "successor"))
    for name in ("authorization", "authorization-sha256", "revision", "generation", "maintenance-root", "evidence-root"):
        parser.add_argument("--"+name, required=True)
    parser.add_argument("--pid", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        now = datetime.now(timezone.utc)
        now_us = _release_time_us(now.isoformat())
        raw = read_private(args.authorization, private=True)
        if hashlib.sha256(raw).hexdigest() != args.authorization_sha256:
            raise ValueError("SWING_RELEASE_AUTH_CHANGED")
        authority = _json(raw)
        verify_release_authorization(authority, now_us=now_us, revision=args.revision)
        raw = sys.stdin.buffer.read(196609)
        if len(raw) > 196608:
            raise ValueError("SWING_RELEASE_DOCUMENT_SIZE")
        if args.release_phase != "retired":
            documents = _json(raw)
            process_identity = verify_release_documents(documents, authority, pid=args.pid, generation=args.generation,
                successor=args.release_phase == "successor", now_us=now_us)
        elif args.pid != authority["predecessor_pid"] or args.generation != authority["predecessor_maintenance_identity"]:
            raise ValueError("SWING_RELEASE_RETIRED_BINDING")
        if args.release_phase == "successor":
            claim = _json(read_private(Path(args.maintenance_root)/(args.generation+".consumed.json"), private=True))
            if (set(claim) != {"schema", "generation", "parent_pid", "process_id", "runtime_identity", "accepted_at"}
                    or claim["schema"] != "KRONOS_MAINTENANCE_CONSUMPTION_V2" or claim["generation"] != args.generation
                    or type(claim["parent_pid"]) is not int or claim["parent_pid"] != authority["predecessor_pid"]
                    or type(claim["process_id"]) is not int or claim["process_id"] != args.pid
                    or claim["runtime_identity"] != process_identity):
                raise ValueError("SWING_RELEASE_CONSUMPTION")
            receipt = _json(read_private(Path(args.evidence_root)/"shared/provider-connection-v1/maintenance"/
                (claim["runtime_identity"]+"-startup.json"), private=True))
            if (set(receipt) != {"schema", "runtime_identity", "maintenance_identity", "at", "trigger"}
                    or receipt["schema"] != "RUNTIME_STARTUP_MAINTENANCE_EXIT_V1"
                    or receipt["runtime_identity"] != claim["runtime_identity"]
                    or receipt["maintenance_identity"] != args.generation
                    or receipt["trigger"] != "VERIFIED_CANONICAL_STARTUP"
                    or not (_release_time_us(documents[2]["live_shadow"]["runtime_proof"]["startup"])
                        <= _release_time_us(claim["accepted_at"]) <= _release_time_us(receipt["at"]) <= now_us)):
                raise ValueError("SWING_RELEASE_STARTUP_RECEIPT")
    except Exception:
        print("KRONOS_SWING_RELEASE_RECOVERY_V1 INVALID")
        return 2
    print("KRONOS_SWING_RELEASE_RECOVERY_V1 VALID")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--release-phase" in argv:
        return release_main(argv)
    if "--incident-phase" in argv:
        return incident_main(argv)
    parser = argparse.ArgumentParser()
    for name in ("relation", "relation-sha256", "capability", "revision", "generation", "maintenance-root", "evidence-root"):
        parser.add_argument("--" + name, required=True)
    for name in ("pid", "parent-pid", "valid-from-us", "valid-until-us"):
        parser.add_argument("--" + name, required=True, type=int)
    parser.add_argument("--research-state", choices=("ACTIVE", "HISTORICAL_ACCEPTANCE_EXPIRED"), default="ACTIVE")
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(196609)
        if len(raw) > 196608:
            raise ValueError("documents too large")
        relation_raw = read_private(args.relation)
        if hashlib.sha256(relation_raw).hexdigest() != args.relation_sha256:
            raise ValueError("relation changed")
        relation = _json(relation_raw)
        documents = _json(raw)
        verify_documents(documents, relation, pid=args.pid, revision=args.revision,
            generation=args.generation, capability=args.capability, research_state=args.research_state)
        claim = _json(read_private(Path(args.maintenance_root) / (args.generation + ".consumed.json"), private=True))
        if (set(claim) != {"schema", "generation", "parent_pid", "process_id", "runtime_identity", "accepted_at"}
                or claim["schema"] != "KRONOS_MAINTENANCE_CONSUMPTION_V2"
                or claim["generation"] != args.generation or claim["process_id"] != args.pid
                or claim["parent_pid"] != args.parent_pid
                or not re.fullmatch(r"[a-f0-9]{64}", claim["runtime_identity"])):
            raise ValueError("handoff consumption")
        receipt = _json(read_private(Path(args.evidence_root) / "shared/provider-connection-v1/maintenance" /
            (claim["runtime_identity"] + "-startup.json"), private=True))
        if (set(receipt) != {"schema", "runtime_identity", "maintenance_identity", "at", "trigger"}
                or receipt["schema"] != "RUNTIME_STARTUP_MAINTENANCE_EXIT_V1"
                or receipt["runtime_identity"] != claim["runtime_identity"]
                or receipt["maintenance_identity"] != args.generation
                or receipt["trigger"] != "VERIFIED_CANONICAL_STARTUP"):
            raise ValueError("startup receipt")
        now = datetime.now(timezone.utc)
        delta = now - datetime(1970, 1, 1, tzinfo=timezone.utc)
        now_us = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
        body = relation["body"]
        expired = args.research_state == "HISTORICAL_ACCEPTANCE_EXPIRED"
        window_valid = (now >= datetime.fromisoformat(body["end"]) if expired else
            datetime.fromisoformat(body["start"]) <= now < datetime.fromisoformat(body["end"]))
        if expired and (args.valid_from_us < int(datetime.fromisoformat(body["end"]).timestamp()*1000000)
                or not 0 < args.valid_until_us-args.valid_from_us <= 1800000000):
            raise ValueError("historical authorization validity")
        if not (args.valid_from_us <= now_us < args.valid_until_us and window_valid
                and datetime.fromisoformat(documents[2]["live_shadow"]["runtime_proof"]["startup"])
                <= datetime.fromisoformat(claim["accepted_at"])
                <= datetime.fromisoformat(receipt["at"]) <= now):
            raise ValueError("expired")
    except Exception:
        print("KRONOS_RECOVERY_SUCCESSOR_V1 INVALID")
        return 2
    print("KRONOS_RECOVERY_SUCCESSOR_V1 VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
