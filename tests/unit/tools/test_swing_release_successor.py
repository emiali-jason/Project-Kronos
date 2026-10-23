"""Exact release-recovery verifier qualification using disposable owner proofs.

No production HTTP, bundle, store or process operation is performed. The real
V2 publication/consumption and startup receipt owners operate on temporary roots.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kronos.common.connection_governance import (
    ConnectionAuditStore, ConnectionGovernance, ConnectionProcess,
)
from kronos.common.maintenance import consume_drain_handoff, publish_drain_handoff
from kronos.intraday.live_shadow_transition import capability_identity
from kronos.intraday.runtime_identity import (
    LauncherConfiguration, LoadedCapability, create_runtime_manifest, runtime_document,
)
from tools import failed_active_successor as helper
from tests.unit.intraday.test_runtime_identity import _seed
from tests.unit.tools.test_failed_active_successor import (
    exact_successor, incident_documents, production_case,
)


NOW = datetime(2026, 10, 22, 8, tzinfo=UTC)
NOW_US = 1792656000000000
SUCCESSOR = "b" * 40
REVIEW_BINDINGS = (
    "incident_id", "predecessor_revision", "predecessor_pid", "predecessor_start_us",
    "predecessor_maintenance_identity", "successor_revision", "installed_package_identity",
    "rollback_package_identity", "expected_successor_capability", "expected_startup_failure",
    "diagnosis_sha256", "sponsor_authorization_reference", "sponsor_authorization_sha256",
    "private_control_sha256",
)


def _write_private(path, value):
    path.write_bytes(json.dumps(value).encode() if isinstance(value, dict) else value)
    path.chmod(0o600)
    return sha256(path.read_bytes()).hexdigest()


def _bind_runtime(documents):
    """Use actual identity owners to bind the fixture's complete runtime proof."""
    intraday = documents[2]
    proof = intraday["live_shadow"]["runtime_proof"]
    startup = _seed(process_id=proof["pid"], source_revision=proof["revision"],
                    startup_boundary_at=datetime.fromisoformat(proof["startup"]))
    configuration = LauncherConfiguration(8947, False)
    assert configuration.identity == proof["configuration"]
    manifest = create_runtime_manifest(startup, configuration,
        tuple(LoadedCapability(**value) for value in proof["capabilities"]))
    with patch("kronos.intraday.runtime_identity.os.getpid", return_value=proof["pid"]):
        intraday["runtime_identity"] = runtime_document(manifest)
    proof["manifest"] = manifest.manifest_identity


@pytest.fixture
def release_case(incident_documents, tmp_path):
    documents, expected = incident_documents
    runtime, status, intraday = documents
    proof = intraday["live_shadow"]["runtime_proof"]
    runtime["process"]["revision"] = SUCCESSOR
    proof["revision"] = SUCCESSOR
    proof["startup"] = (NOW - timedelta(seconds=3)).isoformat()
    _bind_runtime(documents)
    runtime["maintenance_drain"] = {
        "state": "OPEN", "generation": None, "failure": None, "owners": {"SERVER_PULSE": 1},
    }
    runtime["maintenance_claim"] = "DRAINABLE"
    root = tmp_path.resolve()
    rollback = root / "disposable-rollback.app"
    rollback.mkdir()
    authority = dict(
        schema="KRONOS-SWING-RELEASE-RECOVERY-AUTHORIZATION/1.0.0",
        state="SPONSOR_APPROVED", recovery_class="FAILED_ACTIVE_RECOVERY_REPLACEMENT",
        incident_id="KRONOS-SWING-FAILED-ACTIVE-AND-FENCED-RECOVERY-ENGINEERING-20261022",
        attempt_identity="a" * 64, sponsor_authorization_reference="DISPOSABLE TEST ONLY",
        predecessor_revision="355922f92f7b826191ae86bd7bb0473349f3c1cc",
        predecessor_pid=expected["pid"] + 100,
        predecessor_start_us=NOW_US - 10000000,
        predecessor_maintenance_identity="d" * 64, private_control_sha256="e" * 64,
        installed_package_identity="f" * 64, rollback_bundle=str(rollback),
        rollback_package_identity="1" * 64, successor_revision=SUCCESSOR,
        expected_successor_capability=capability_identity(proof),
        expected_startup_failure="SWING_RESTORATION_NOT_ESTABLISHED",
        valid_from_us=NOW_US - 5000000, valid_until_us=NOW_US + 5000000,
    )
    for name, content in (("sponsor_authorization", b"disposable Sponsor test authority"),
                          ("diagnosis", b"disposable exact recovery diagnosis")):
        path = root / (name + ".txt")
        authority[name + "_path"] = str(path)
        authority[name + "_sha256"] = _write_private(path, content)
    review = {key: authority[key] for key in REVIEW_BINDINGS}
    review.update(schema="KRONOS-SWING-RECOVERY-ARTIFACT-REVIEW/1.0.0", state="APPROVED",
                  approved_at=(NOW - timedelta(seconds=6)).isoformat())
    authority["artifact_review_path"] = str(root / "artifact-review.json")
    authority["artifact_review_sha256"] = _write_private(Path(authority["artifact_review_path"]), review)
    assert len(authority) == 25
    assert len(review) == 17
    assert helper._release_time_us(NOW.isoformat()) == NOW_US
    return authority, review, documents, expected


def _write_review(authority, review):
    authority["artifact_review_sha256"] = _write_private(Path(authority["artifact_review_path"]), review)


@pytest.mark.parametrize("predecessor", [
    "355922f92f7b826191ae86bd7bb0473349f3c1cc", "1579f1cbad2f98370b62f5511a7d339c131ab15a",
])
def test_exact_release_authority_and_review_are_read_only(release_case, predecessor):
    authority, review, _, _ = release_case
    authority["predecessor_revision"] = review["predecessor_revision"] = predecessor
    _write_review(authority, review)
    paths = [Path(authority[name + "_path"]) for name in
             ("sponsor_authorization", "diagnosis", "artifact_review")]
    before = {path: path.read_bytes() for path in paths}
    helper.verify_release_authorization(authority, now_us=NOW_US, revision=SUCCESSOR)
    assert {path: path.read_bytes() for path in paths} == before


@pytest.mark.parametrize("offset", [-1, 0])
def test_release_authority_preserves_original_end_exclusive_window(release_case, offset):
    authority, review, _, _ = release_case
    start = 1791771633006722 + offset
    authority.update(valid_from_us=start, valid_until_us=start + 1000000,
                     predecessor_start_us=start - 2000000)
    review["predecessor_start_us"] = authority["predecessor_start_us"]
    review["approved_at"] = (datetime(1970, 1, 1, tzinfo=UTC)
                              + timedelta(microseconds=start - 1)).isoformat()
    _write_review(authority, review)
    if offset < 0:
        with pytest.raises(ValueError, match="SWING_RELEASE_VALIDITY"):
            helper.verify_release_authorization(authority, now_us=start, revision=SUCCESSOR)
    else:
        helper.verify_release_authorization(authority, now_us=start, revision=SUCCESSOR)


@pytest.mark.parametrize("fault", [
    "schema", "state", "class", "incident", "predecessor", "successor", "same_revision",
    "pid_bool", "start_bool", "failure", "capability", "attempt", "empty_sponsor",
    "expired", "future", "too_long", "missing", "unknown", "sponsor_changed",
    "diagnosis_changed", "review_changed",
])
def test_release_authority_rejects_scope_time_shape_and_artifact_faults(release_case, fault):
    authority, _, _, _ = release_case
    changes = {
        "schema": ("schema", "OTHER"), "state": ("state", "PENDING"),
        "class": ("recovery_class", "OTHER"), "incident": ("incident_id", "OTHER"),
        "predecessor": ("predecessor_revision", "0" * 40),
        "successor": ("successor_revision", "0" * 40),
        "same_revision": ("successor_revision", authority["predecessor_revision"]),
        "pid_bool": ("predecessor_pid", True), "start_bool": ("predecessor_start_us", True),
        "failure": ("expected_startup_failure", "UNKNOWN"),
        "capability": ("expected_successor_capability", "UNKNOWN"),
        "attempt": ("attempt_identity", "invalid"),
        "empty_sponsor": ("sponsor_authorization_reference", " "),
        "expired": ("valid_until_us", NOW_US), "future": ("valid_from_us", NOW_US + 1),
        "too_long": ("valid_until_us", authority["valid_from_us"] + 1800000001),
    }
    if fault in changes:
        key, value = changes[fault]
        authority[key] = value
    elif fault == "missing":
        del authority["private_control_sha256"]
    elif fault == "unknown":
        authority["unapproved_privilege"] = True
    else:
        name = {"sponsor_changed": "sponsor_authorization", "diagnosis_changed": "diagnosis",
                "review_changed": "artifact_review"}[fault]
        Path(authority[name + "_path"]).write_bytes(b"changed after approval")
    with pytest.raises(ValueError, match="SWING_RELEASE_"):
        helper.verify_release_authorization(authority, now_us=NOW_US, revision=SUCCESSOR)


@pytest.mark.parametrize("field", REVIEW_BINDINGS)
def test_every_review_binding_is_exact_even_when_changed_receipt_hash_is_current(release_case, field):
    authority, review, _, _ = release_case
    review[field] = review[field] + 1 if type(review[field]) is int else review[field] + "changed"
    _write_review(authority, review)
    with pytest.raises(ValueError, match="ARTIFACT_REVIEW_BINDING"):
        helper.verify_release_authorization(authority, now_us=NOW_US, revision=SUCCESSOR)


@pytest.mark.parametrize("fault", ["pending", "unknown", "missing", "future", "before_birth", "naive", "duplicate"])
def test_artifact_review_requires_closed_approved_unambiguous_receipt(release_case, fault):
    authority, review, _, _ = release_case
    if fault == "pending": review["state"] = "PENDING"
    elif fault == "unknown": review["extra"] = True
    elif fault == "missing": del review["diagnosis_sha256"]
    elif fault == "future": review["approved_at"] = NOW.isoformat()
    elif fault == "before_birth": review["approved_at"] = (NOW - timedelta(seconds=11)).isoformat()
    elif fault == "naive": review["approved_at"] = NOW.replace(tzinfo=None).isoformat()
    _write_review(authority, review)
    if fault == "duplicate":
        raw = json.dumps(review)[:-1] + ',"state":"APPROVED"}'
        authority["artifact_review_sha256"] = _write_private(Path(authority["artifact_review_path"]), raw.encode())
    with pytest.raises(ValueError):
        helper.verify_release_authorization(authority, now_us=NOW_US, revision=SUCCESSOR)


def _phase_documents(release_case, successor):
    authority, _, original, expected = release_case
    documents = deepcopy(original)
    pid, generation = expected["pid"], expected["generation"]
    if not successor:
        pid, generation = authority["predecessor_pid"], authority["predecessor_maintenance_identity"]
        documents[0]["process"].update(pid=pid, revision=authority["predecessor_revision"])
        for document in documents[:2]:
            document["maintenance"].update(state="FAILED_ACTIVE", active=True, generation=generation,
                                           startup="BLOCKED", failure=authority["expected_startup_failure"])
        documents[1]["runtime_ready"] = False
        documents[2]["live_shadow"]["runtime_proof"].update(
            pid=pid, revision=authority["predecessor_revision"],
            startup=(NOW - timedelta(seconds=9)).isoformat())
        _bind_runtime(documents)
    return documents, dict(pid=pid, generation=generation, successor=successor, now_us=NOW_US)


@pytest.mark.parametrize("successor", [False, True])
def test_actual_owner_proof_accepts_exact_preflight_and_successor(release_case, successor):
    authority, _, _, _ = release_case
    documents, expected = _phase_documents(release_case, successor)
    before = deepcopy(documents)
    identity = helper.verify_release_documents(documents, authority, **expected)
    assert identity == sha256(documents[2]["runtime_identity"]["startup"]["evidence_identity"].encode()).hexdigest()
    assert documents == before


@pytest.mark.parametrize("successor", [False, True])
@pytest.mark.parametrize("field,value", [
    ("load_verification", "NOT_PROVEN"),
    ("source_snapshot_digest", None),
    ("source_snapshot_digest", ""),
])
def test_release_documents_require_pinned_imports_and_source_snapshot(release_case, successor, field, value):
    authority, _, _, _ = release_case
    documents, expected = _phase_documents(release_case, successor)
    documents[2]["runtime_identity"]["startup"][field] = value
    with pytest.raises(ValueError, match="SWING_RELEASE_STARTUP_EVIDENCE"):
        helper.verify_release_documents(documents, authority, **expected)


@pytest.mark.parametrize("successor", [False, True])
@pytest.mark.parametrize("fault", ["fenced", "failed_fenced", "claimed", "drain_failure", "not_drainable",
    "pid", "revision", "provider", "history", "capability", "future_start", "startup_integrity",
    "manifest_integrity", "proof_manifest", "proof_startup", "source_scope"])
def test_release_documents_never_infer_recovery_from_unsafe_projection(release_case, successor, fault):
    authority, _, _, _ = release_case
    documents, expected = _phase_documents(release_case, successor)
    runtime, status, intraday = documents
    if fault == "fenced": runtime["maintenance_drain"]["state"] = "FENCED"
    elif fault == "failed_fenced": runtime["maintenance_drain"]["state"] = "FAILED_FENCED"
    elif fault == "claimed": runtime["maintenance_drain"]["generation"] = "0" * 64
    elif fault == "drain_failure": runtime["maintenance_drain"]["failure"] = "CLEANUP_UNRESOLVED"
    elif fault == "not_drainable": runtime["maintenance_claim"] = "BLOCKED"
    elif fault == "pid": runtime["process"]["pid"] += 1
    elif fault == "revision": runtime["process"]["revision"] = "0" * 40
    elif fault == "provider": runtime["provider_runtime"]["owned_work_count"] = 1
    elif fault == "history": intraday["live_shadow"]["enabled"] = True
    elif fault == "capability": intraday["live_shadow"]["runtime_proof"]["configuration"] = "CHANGED"
    elif fault == "future_start":
        intraday["live_shadow"]["runtime_proof"]["startup"] = (NOW + timedelta(microseconds=1)).isoformat()
        _bind_runtime(documents)
    elif fault == "startup_integrity": intraday["runtime_identity"]["startup"]["source_snapshot_digest"] = "0" * 64
    elif fault == "manifest_integrity": intraday["runtime_identity"]["manifest_identity"] = "INTRADAY-RUNTIME-" + "0" * 64
    elif fault == "proof_manifest": intraday["live_shadow"]["runtime_proof"]["manifest"] = "INTRADAY-RUNTIME-" + "0" * 64
    elif fault == "proof_startup": intraday["live_shadow"]["runtime_proof"]["startup"] = (NOW - timedelta(seconds=2)).isoformat()
    elif fault == "source_scope": intraday["runtime_identity"]["source_proof_scope"] = "UNVERIFIED"
    with pytest.raises(ValueError):
        helper.verify_release_documents(documents, authority, **expected)


@pytest.mark.parametrize("fault", ["wrong_failure", "before_birth", "pid_argument", "generation_argument"])
def test_preflight_requires_exact_failed_active_incident(release_case, fault):
    authority, _, _, _ = release_case
    documents, expected = _phase_documents(release_case, False)
    if fault == "wrong_failure":
        for document in documents[:2]: document["maintenance"]["failure"] = "WO11_RESTORATION_FAILED"
    elif fault == "before_birth":
        documents[2]["live_shadow"]["runtime_proof"]["startup"] = (NOW - timedelta(seconds=11)).isoformat()
        _bind_runtime(documents)
    elif fault == "pid_argument": expected["pid"] += 1
    else: expected["generation"] = "0" * 64
    with pytest.raises(ValueError):
        helper.verify_release_documents(documents, authority, **expected)


@pytest.mark.parametrize("fault", ["before_authority", "not_ready", "owner_failed", "owner_missing", "monitoring_active"])
def test_successor_requires_new_start_and_actual_complete_owner_health(release_case, fault):
    authority, _, _, _ = release_case
    documents, expected = _phase_documents(release_case, True)
    if fault == "before_authority":
        documents[2]["live_shadow"]["runtime_proof"]["startup"] = (NOW - timedelta(seconds=6)).isoformat()
        _bind_runtime(documents)
    elif fault == "not_ready": documents[1]["runtime_ready"] = False
    elif fault == "owner_failed": documents[0]["startup_restoration_outcomes"][-1][1] = "FAILED"
    elif fault == "owner_missing": documents[0]["startup_restoration_outcomes"].pop()
    else: documents[0]["owner_restoration"] = "ACTIVE"
    with pytest.raises(ValueError):
        helper.verify_release_documents(documents, authority, **expected)


def test_successor_preserves_native_owner_applicability_semantics(release_case):
    authority, _, _, _ = release_case
    documents, expected = _phase_documents(release_case, True)
    for row in documents[0]["startup_restoration_outcomes"]:
        if row[0] == "NATIVE_REVIEW": row[1] = "APPLICABILITY_NOT_ESTABLISHED"
    helper.verify_release_documents(documents, authority, **expected)


@pytest.mark.parametrize("fault", [None, "claim_missing", "claim_parent", "claim_pid", "claim_generation",
    "claim_late", "receipt_missing", "receipt_trigger", "receipt_late", "receipt_before_claim",
    "auth_changed", "auth_duplicate", "owner_failed", "claim_identity"])
def test_release_cli_uses_real_v2_consumption_and_startup_receipt(
    release_case, tmp_path, monkeypatch, capsys, fault,
):
    authority, _, _, _ = release_case
    documents, expected = _phase_documents(release_case, True)
    pid, generation = expected["pid"], expected["generation"]
    parent = authority["predecessor_pid"]
    root = tmp_path.resolve()
    maintenance = root / "maintenance"
    evidence = root / "evidence"
    runtime_identity = sha256(documents[2]["runtime_identity"]["startup"]["evidence_identity"].encode()).hexdigest()
    drain = {key: 0 for key in (
        "coordinator_owners", "wo11_owned", "wo11_queued", "wo17_owned", "wo17_queued",
        "housekeeping_owned", "bulk_owned", "notification_scheduled", "monitoring_sessions",
        "provider_owned", "provider_leases",
    )}
    drain["notification_checkpoint"] = {
        "state": "EMPTY", "pending_count": 0, "sha256": sha256(b"[]").hexdigest(),
    }
    with monkeypatch.context() as patch:
        patch.setattr("kronos.common.maintenance.os.getpid", lambda: parent)
        publish_drain_handoff(maintenance, generation=generation, parent_pid=parent, proof="d" * 64,
            runtime_identity="e" * 64, loaded_revision=authority["predecessor_revision"],
            drain=drain, now=NOW - timedelta(seconds=4))
    consume_drain_handoff(maintenance, {
        "KRONOS_MAINTENANCE_GENERATION": generation, "KRONOS_MAINTENANCE_PARENT": str(parent),
        "KRONOS_MAINTENANCE_PROOF": "d" * 64,
    }, runtime_identity=runtime_identity, now=NOW - timedelta(seconds=2), process_id=pid,
        loaded_revision=authority["predecessor_revision"], predecessor_gone=lambda value: value == parent,
        port_free=lambda: True)
    audit = ConnectionAuditStore(evidence / "shared/provider-connection-v1")
    governance = ConnectionGovernance(ConnectionProcess(pid, (NOW - timedelta(seconds=3)).isoformat(),
        runtime_identity, SUCCESSOR, "CLEAN_COMMIT"), audit,
        maintenance_identity=generation, clock=lambda: NOW - timedelta(seconds=1))
    governance.complete_startup()
    assert governance.startup_state == "READY"
    claim_path = maintenance / (generation + ".consumed.json")
    receipt_path = audit.root / "maintenance" / (runtime_identity + "-startup.json")
    claim, receipt = json.loads(claim_path.read_bytes()), json.loads(receipt_path.read_bytes())
    if fault == "claim_missing": claim_path.unlink()
    elif fault in ("claim_parent", "claim_pid", "claim_generation", "claim_late"):
        field = {"claim_parent": "parent_pid", "claim_pid": "process_id",
                 "claim_generation": "generation", "claim_late": "accepted_at"}[fault]
        claim[field] = (NOW + timedelta(microseconds=1)).isoformat() if fault == "claim_late" else "wrong"
        _write_private(claim_path, claim)
    elif fault == "receipt_missing": receipt_path.unlink()
    elif fault in ("receipt_trigger", "receipt_late", "receipt_before_claim"):
        if fault == "receipt_trigger": receipt["trigger"] = "MANUAL"
        elif fault == "receipt_late": receipt["at"] = (NOW + timedelta(microseconds=1)).isoformat()
        else: receipt["at"] = (NOW - timedelta(seconds=3)).isoformat()
        _write_private(receipt_path, receipt)
    elif fault == "owner_failed": documents[0]["startup_restoration_outcomes"][-1][1] = "FAILED"
    elif fault == "claim_identity":
        claim["runtime_identity"] = receipt["runtime_identity"] = "0" * 64
        _write_private(claim_path, claim)
        receipt_path.unlink()
        _write_private(receipt_path.parent / ("0" * 64 + "-startup.json"), receipt)
    auth_path = root / "authorization.json"
    digest = _write_private(auth_path, authority)
    if fault == "auth_changed": auth_path.write_bytes(b"{}")
    elif fault == "auth_duplicate":
        digest = _write_private(auth_path, (json.dumps(authority)[:-1] + ',"state":"SPONSOR_APPROVED"}').encode())
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz or UTC)
    monkeypatch.setattr(helper, "datetime", Clock)
    monkeypatch.setattr(helper.sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(documents).encode())))
    args = ["--release-phase", "successor", "--authorization", str(auth_path),
            "--authorization-sha256", digest, "--revision", SUCCESSOR, "--generation", generation,
            "--pid", str(pid), "--maintenance-root", str(maintenance), "--evidence-root", str(evidence)]
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert helper.main(args) == (0 if fault is None else 2)
    assert capsys.readouterr().out == "KRONOS_SWING_RELEASE_RECOVERY_V1 " + ("VALID\n" if fault is None else "INVALID\n")
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before
