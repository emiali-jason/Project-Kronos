"""Exact successor verification against actual disposable WO06H proof/relations."""
from copy import deepcopy
import json

import pytest

from tools.failed_active_successor import verify_documents, _json
from tests.unit.intraday.test_live_shadow_epoch_deterministic_digest import production_case
from tests.unit.intraday.test_live_shadow_successor_compatibility import relation


@pytest.fixture
def exact_successor(production_case):
    service = production_case
    record = relation(service)
    service._epochs.retain(record)
    service._restore_acceptance()
    shadow = service.status()
    shadow["publication_hook_failure"] = None
    proof = shadow["runtime_proof"]
    maintenance = dict(protocol="KRONOS_MAINTENANCE_HANDOFF_V1", state="INACTIVE",
        active=False, generation="a" * 64, startup="READY", failure=None)
    runtime = dict(schema="KRONOS-RUNTIME-STATE/1.0.0",
        process=dict(pid=proof["pid"], revision=proof["revision"], source_state="CLEAN_COMMIT"),
        maintenance=maintenance, rest_authentication="DISCONNECTED", rest_capability="ABSENT",
        connection_attempt=None, provider_runtime=dict(capability_state="ABSENT", cleanup_state="COMPLETE",
            owned_work_count=0, retained_lease_count=0, unresolved_cleanup_count=0))
    status = dict(service="KRONOS_BROWSER_V1", runtime_ready=True, provider="DISCONNECTED", maintenance=deepcopy(maintenance))
    intraday = dict(active_operation_identity=None, current_failure=None, live_shadow=shadow)
    expected = dict(pid=proof["pid"], revision=proof["revision"], generation="a" * 64,
                    capability=record["body"]["target_aggregate"])
    return [runtime, status, intraday], record, expected


def test_valid_actual_successor_proof(exact_successor):
    documents, record, expected = exact_successor
    verify_documents(documents, record, **expected)


@pytest.mark.parametrize("fault", ["pid", "revision", "source", "status_generation", "status_failure",
    "runtime_ready", "provider", "provider_work", "operation", "acceptance", "epoch", "window",
    "window_start", "window_end", "new_acceptance", "not_accepted", "disabled", "shadow_failure",
    "publication_failure", "capability", "proof_pid", "proof_revision", "map", "pending"])
def test_exact_successor_rejects_mismatch(exact_successor, fault):
    documents, record, expected = deepcopy(exact_successor)
    runtime, status, intraday = documents
    shadow = intraday["live_shadow"]
    if fault == "pid": runtime["process"]["pid"] += 1
    elif fault == "revision": runtime["process"]["revision"] = "0" * 40
    elif fault == "source": runtime["process"]["source_state"] = "DIRTY"
    elif fault == "status_generation": status["maintenance"]["generation"] = "b" * 64
    elif fault == "status_failure": status["maintenance"]["failure"] = "FAILED"
    elif fault == "runtime_ready": status["runtime_ready"] = False
    elif fault == "provider": runtime["rest_capability"] = "AVAILABLE"
    elif fault == "provider_work": runtime["provider_runtime"]["owned_work_count"] = 1
    elif fault == "operation": intraday["active_operation_identity"] = "active"
    elif fault == "acceptance": shadow["acceptance_identity"] = "other"
    elif fault == "epoch": shadow["current_epoch"] = "other"
    elif fault == "window": shadow["window"]["identity"] = "other"
    elif fault == "window_start": shadow["window"]["start"] = "2026-01-01T00:00:00+00:00"
    elif fault == "window_end": shadow["window"]["end"] = "2027-01-01T00:00:00+00:00"
    elif fault == "new_acceptance": shadow["acceptance_disposition"] = "NEW_ACCEPTANCE_GRANTED"
    elif fault == "not_accepted": shadow["runtime_accepted"] = False
    elif fault == "disabled": shadow["enabled"] = False
    elif fault == "shadow_failure": shadow["failure"] = "FAILED"
    elif fault == "publication_failure": shadow["publication_hook_failure"] = "FAILED"
    elif fault == "capability": expected["capability"] = "WO06H-CAPABILITY-" + "0" * 64
    elif fault == "proof_pid": shadow["runtime_proof"]["pid"] += 1
    elif fault == "proof_revision": shadow["runtime_proof"]["revision"] = "0" * 40
    elif fault == "map": record["body"]["target_capabilities"][0]["implementation_digest"] = "0" * 64
    elif fault == "pending": record["body"]["owner_approvals"][0]["disposition"] = "PENDING"
    with pytest.raises((ValueError, KeyError, TypeError)):
        verify_documents(documents, record, **expected)


@pytest.mark.parametrize("raw", ['{"ready":true,"ready":false}', '{"value":NaN}', '{"nested":{"a":0,"a":1}}'])
def test_ambiguous_document_rejected(raw):
    with pytest.raises(ValueError):
        _json(raw)


@pytest.mark.parametrize("fault", [None, "claim_missing", "claim_pid", "claim_parent", "claim_generation",
    "receipt_missing", "receipt_identity", "receipt_generation", "receipt_trigger", "receipt_future",
    "relation_drift", "window_expired", "authorization_expired"])
def test_cli_actual_v2_consumption_and_startup_receipt(exact_successor, tmp_path, monkeypatch, capsys, fault):
    from datetime import datetime, timedelta, timezone
    import hashlib
    import io
    from kronos.common.maintenance import publish_drain_handoff, consume_drain_handoff, _DRAIN_ZERO_FIELDS
    from kronos.common.connection_governance import ConnectionProcess, ConnectionGovernance, ConnectionAuditStore
    from tools import failed_active_successor as helper

    documents, record, expected = exact_successor
    pid, generation = expected["pid"], expected["generation"]
    parent = pid + 100
    now = datetime.fromisoformat(documents[2]["live_shadow"]["runtime_proof"]["startup"]) + timedelta(seconds=2)
    maintenance = tmp_path.resolve() / "maintenance"
    runtime_identity = "c" * 64
    drain = {field: 0 for field in _DRAIN_ZERO_FIELDS}
    drain["notification_checkpoint"] = dict(state="EMPTY", pending_count=0, sha256=hashlib.sha256(b"[]").hexdigest())
    with monkeypatch.context() as scoped:
        scoped.setattr("kronos.common.maintenance.os.getpid", lambda: parent)
        publish_drain_handoff(maintenance, generation=generation, parent_pid=parent, proof="d" * 64,
            runtime_identity="e" * 64, loaded_revision="f" * 40, drain=drain, now=now-timedelta(seconds=1))
    context = consume_drain_handoff(maintenance,
        dict(KRONOS_MAINTENANCE_GENERATION=generation, KRONOS_MAINTENANCE_PARENT=str(parent), KRONOS_MAINTENANCE_PROOF="d" * 64),
        runtime_identity=runtime_identity, now=now, process_id=pid, loaded_revision="f" * 40,
        predecessor_gone=lambda value: value == parent, port_free=lambda: True)
    assert context.generation == generation
    evidence = tmp_path.resolve() / "evidence"
    audit = ConnectionAuditStore(evidence / "shared/provider-connection-v1")
    governance = ConnectionGovernance(ConnectionProcess(pid, now.isoformat(), runtime_identity,
        expected["revision"], "CLEAN_COMMIT"), audit, maintenance_identity=generation, clock=lambda: now)
    governance.complete_startup()
    assert governance.startup_state == "READY"
    claim_path = maintenance / (generation + ".consumed.json")
    receipt_path = audit.root / "maintenance" / (runtime_identity + "-startup.json")
    claim = json.loads(claim_path.read_text()); receipt = json.loads(receipt_path.read_text())
    if fault == "claim_missing": claim_path.unlink()
    elif fault in ("claim_pid", "claim_parent", "claim_generation"):
        claim[{"claim_pid": "process_id", "claim_parent": "parent_pid", "claim_generation": "generation"}[fault]] = "wrong"
        claim_path.write_text(json.dumps(claim))
    elif fault == "receipt_missing": receipt_path.unlink()
    elif fault and fault.startswith("receipt_"):
        field = {"receipt_identity": "runtime_identity", "receipt_generation": "maintenance_identity",
                 "receipt_trigger": "trigger", "receipt_future": "at"}[fault]
        receipt[field] = (now + timedelta(seconds=1)).isoformat() if fault == "receipt_future" else "wrong"
        receipt_path.write_text(json.dumps(receipt))
    relation_path = tmp_path / "relation.json"; relation_path.write_text(json.dumps(record))
    relation_hash = hashlib.sha256(relation_path.read_bytes()).hexdigest()
    if fault == "relation_drift": relation_path.write_text("{}")
    if fault == "window_expired": now = datetime.fromisoformat(record["body"]["end"])
    until = now if fault == "authorization_expired" else now + timedelta(seconds=1)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return now.astimezone(tz or timezone.utc)
    monkeypatch.setattr(helper, "datetime", Clock)
    monkeypatch.setattr(helper.sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(documents).encode())))
    args = ["--relation", str(relation_path), "--relation-sha256", relation_hash,
        "--capability", expected["capability"], "--revision", expected["revision"], "--generation", generation,
        "--maintenance-root", str(maintenance), "--evidence-root", str(evidence), "--pid", str(pid), "--parent-pid", str(parent),
        "--valid-from-us", str(int((now-timedelta(days=1)).timestamp()*1000000)),
        "--valid-until-us", str(int(until.timestamp()*1000000))]
    assert helper.main(args) == (0 if fault is None else 2)
    assert capsys.readouterr().out == "KRONOS_RECOVERY_SUCCESSOR_V1 " + ("VALID\n" if fault is None else "INVALID\n")
