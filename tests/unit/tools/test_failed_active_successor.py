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


@pytest.fixture
def incident_documents(exact_successor, monkeypatch):
    from tools import failed_active_successor as h
    documents, record, expected = deepcopy(exact_successor)
    runtime, _, intraday = documents
    shadow = intraday['live_shadow']
    shadow.update(acceptance_disposition='HISTORICAL_ACCEPTANCE_EXPIRED', enabled=False, runtime_accepted=False,
        historical_restoration='KRONOS-WO06H-HISTORICAL-RESTORATION/1.0.0', historical_evidence='READABLE', collection_authority='EXPIRED',
        acceptance_identity='WO06H-ACCEPTANCE-705befed9c2ff4d8d3a53aa94b4b9d8b9c5d67b99f6a0093d22ed4335cd71259',
        current_epoch='WO06H-EPOCH-4bc5e40a837f8ba26ea8ed91245148c4e45a6d24178d90ba187822586b16dcc3',
        window=dict(identity='WO06H-WINDOW-ed7a53dfdc22e1f95440c7778b381a9a2d7ad69d10b892a5857c29576f1e094c',
            start='2026-09-12T07:50:33.006722+05:30', end='2026-10-12T07:50:33.006722+05:30'),
        counts=dict(cohort_a=1,cohort_b=18,eod_available=0))
    # Exercise the actual proof parser against disposable source-capability fixtures.
    monkeypatch.setattr(h, 'INCIDENT_CAPABILITY', expected['capability'])
    runtime['startup_restoration_outcomes'] = [[owner,'SUCCESS'] for owner in
        ('LEGACY_MTF','LEGACY_NATIVE','NATIVE_REVIEW','V3_RECORDS','V3_RESTORE','TRADE_WINDOW')]
    runtime['owner_restoration'] = 'DEFERRED_PROVIDER_DISCONNECTED'
    expected.pop('capability')
    return documents, expected


@pytest.mark.parametrize('owner', ['LEGACY_MTF','LEGACY_NATIVE','NATIVE_REVIEW','V3_RECORDS','V3_RESTORE','TRADE_WINDOW'])
@pytest.mark.parametrize('outcome', ['SUCCESS','NOT_APPLICABLE','APPLICABILITY_NOT_ESTABLISHED','FAILED','UNKNOWN'])
def test_iwo07r3_exact_six_owner_acceptance_sets(incident_documents, owner, outcome):
    from tools.failed_active_successor import verify_incident_documents
    documents, expected = incident_documents
    for row in documents[0]['startup_restoration_outcomes']:
        if row[0] == owner: row[1] = outcome
    allowed = outcome == 'SUCCESS' or (outcome == 'NOT_APPLICABLE' and owner not in ('V3_RECORDS','TRADE_WINDOW')) or (
        outcome == 'APPLICABILITY_NOT_ESTABLISHED' and owner == 'NATIVE_REVIEW')
    if allowed: verify_incident_documents(documents, **expected, successor=True)
    else:
        with pytest.raises(ValueError): verify_incident_documents(documents, **expected, successor=True)


@pytest.mark.parametrize('fault', ['missing','duplicate','unknown','malformed','provider','epoch','window','enabled','counts','capability','generation','pid','not_ready','monitoring'])
def test_iwo07r3_successor_rejects_false_health(incident_documents, fault):
    from tools.failed_active_successor import verify_incident_documents
    documents, expected = incident_documents
    r,s,d = documents; shadow=d['live_shadow']; outcomes=r['startup_restoration_outcomes']
    if fault == 'missing': outcomes.pop()
    elif fault == 'duplicate': outcomes[-1]=outcomes[0]
    elif fault == 'unknown': outcomes[-1][0]='OTHER'
    elif fault == 'malformed': outcomes[-1][1]=[]
    elif fault == 'provider': r['provider_runtime']['owned_work_count']=1
    elif fault == 'epoch': shadow['current_epoch']='OTHER'
    elif fault == 'window': shadow['window']['end']='2027-10-12T07:50:33.006722+05:30'
    elif fault == 'enabled': shadow['enabled']=True
    elif fault == 'counts': shadow['counts']['cohort_a']=True
    elif fault == 'capability': shadow['runtime_proof']['configuration']='OTHER'
    elif fault == 'generation': r['maintenance']['generation']='b'*64
    elif fault == 'pid': r['process']['pid']+=1
    elif fault == 'not_ready': s['runtime_ready']=False
    elif fault == 'monitoring': r['owner_restoration']='ACTIVE'
    with pytest.raises((ValueError,KeyError,TypeError)): verify_incident_documents(documents, **expected, successor=True)


@pytest.fixture
def incident_authority(tmp_path, monkeypatch):
    import hashlib, stat
    from datetime import datetime, timezone
    from tools import failed_active_successor as h
    root = tmp_path.resolve(); directory=root/'pdfs';directory.mkdir(mode=0o700)
    selection=root/'selection';selection.mkdir()
    artifacts=[]; pins=[]
    for i in range(2):
        p=directory/f'{i}.pdf';p.write_bytes(b'%PDF disposable'+bytes([i]));p.chmod(0o600)
        v=p.stat();digest=hashlib.sha256(p.read_bytes()).hexdigest()
        pins.append((p.name,v.st_size,digest))
        artifacts.append(dict(path=str(p),size=v.st_size,sha256=digest,device=v.st_dev,inode=v.st_ino,uid=v.st_uid,gid=v.st_gid,mode=0o600,prior_absent=True))
    q=selection/'pointer.json';q.write_text('{}')
    monkeypatch.setattr(h,'INCIDENT_ARTIFACTS',tuple(pins));monkeypatch.setattr(h,'INCIDENT_DIRECTORY',directory)
    monkeypatch.setattr(h,'INCIDENT_SELECTION',selection);monkeypatch.setattr(h,'INCIDENT_SELECTION_HASHES',{'pointer.json':hashlib.sha256(q.read_bytes()).hexdigest()})
    v=directory.stat();identity=(v.st_dev,v.st_ino,v.st_uid,v.st_gid,stat.S_IMODE(v.st_mode));monkeypatch.setattr(h,'INCIDENT_DIRECTORY_ID',identity)
    now=h.INCIDENT_START_US+10000000
    receipt=dict(schema='KRONOS-IWO07R3-ARTIFACT-RESTORATION/1.0.0',state='COMPLETE',incident_revision=h.INCIDENT_REVISION,
        incident_generation=h.INCIDENT_GENERATION,directory_identity=list(identity),artifacts=artifacts,
        completed_at=datetime.fromtimestamp((now-1000000)/1000000,timezone.utc).isoformat())
    a=dict(schema=h.INCIDENT_SCHEMA,state='SPONSOR_APPROVED',recovery_class='FAILED_ACTIVE_RECOVERY_REPLACEMENT',
        attempt_identity='a'*64,sponsor_authorization_reference='DISPOSABLE TEST AUTHORITY',predecessor_revision=h.INCIDENT_REVISION,
        predecessor_pid=h.INCIDENT_PID,predecessor_start_us=h.INCIDENT_START_US,predecessor_maintenance_identity=h.INCIDENT_GENERATION,
        private_control_sha256='c'*64,predecessor_package_identity=h.INCIDENT_PACKAGE,successor_revision='b'*40,
        installed_package_identity='b'*64,rollback_bundle=str(root/'rollback.app'),rollback_package_identity=h.INCIDENT_PACKAGE,
        valid_from_us=now-1000000,valid_until_us=now+1000000)
    for field,content in [('diagnosis',b'disposable forensic'),('sponsor_authorization',b'disposable sponsor'),('stage_a_receipt',json.dumps(receipt).encode())]:
        p=root/(field+'.json');p.write_bytes(content);p.chmod(0o600)
        a[field+'_path']=str(p);a[field+'_sha256']=hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(h,'INCIDENT_DIAGNOSIS',a['diagnosis_sha256'])
    return a, receipt, now


@pytest.mark.parametrize('fault', [None,'missing_a','missing_b','wrong_hash','symlink','receipt_partial','inode','mode','selection','receipt_hash','pid','revision','generation','start','bundle','successor','expired','future','long_window','unknown','sponsor'])
def test_iwo07r3_artifact_and_authority_rejection_matrix(incident_authority, fault):
    from pathlib import Path
    import hashlib
    from tools import failed_active_successor as h
    a, receipt, now=incident_authority
    if fault in ('missing_a','missing_b'): Path(receipt['artifacts'][fault=='missing_b']['path']).unlink()
    elif fault=='wrong_hash': Path(receipt['artifacts'][0]['path']).write_bytes(b'wrong')
    elif fault=='symlink':
        p=Path(receipt['artifacts'][0]['path']);p.unlink();p.symlink_to(receipt['artifacts'][1]['path'])
    elif fault=='mode': Path(receipt['artifacts'][0]['path']).chmod(0o644)
    elif fault in ('receipt_partial','inode'):
        if fault=='receipt_partial': receipt['state']='PARTIAL_RESTORATION'
        else: receipt['artifacts'][0]['inode']+=1
        p=Path(a['stage_a_receipt_path']);p.write_text(json.dumps(receipt));a['stage_a_receipt_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    elif fault=='selection': (h.INCIDENT_SELECTION/'pointer.json').write_text('changed')
    elif fault=='receipt_hash': a['stage_a_receipt_sha256']='0'*64
    elif fault=='pid': a['predecessor_pid']+=1
    elif fault=='revision': a['predecessor_revision']='0'*40
    elif fault=='generation': a['predecessor_maintenance_identity']='0'*64
    elif fault=='start': a['predecessor_start_us']+=1
    elif fault=='bundle': a['predecessor_package_identity']='0'*64
    elif fault=='successor': a['successor_revision']=h.INCIDENT_REVISION
    elif fault=='expired': a['valid_until_us']=now
    elif fault=='future': a['valid_from_us']=now+1
    elif fault=='long_window': a['valid_until_us']=a['valid_from_us']+1800000001
    elif fault=='unknown': a['extra']=True
    elif fault=='sponsor': Path(a['sponsor_authorization_path']).write_text('changed')
    if fault is None: h.verify_incident_authorization(a, now_us=now,revision='b'*40)
    else:
        with pytest.raises((ValueError,OSError)): h.verify_incident_authorization(a,now_us=now,revision='b'*40)


@pytest.mark.parametrize('fault',[None,'claim_missing','claim_parent','claim_generation','receipt_missing','receipt_trigger','receipt_time','auth_drift','owner_failure'])
def test_iwo07r3_cli_consumption_and_startup_receipt(incident_authority, incident_documents, tmp_path, monkeypatch, capsys, fault):
    import hashlib, io
    from pathlib import Path
    from datetime import datetime, timezone
    from tools import failed_active_successor as h
    a, _, now_us=incident_authority
    docs, expected=incident_documents
    expected['revision']='b'*40
    docs[0]['process']['revision']='b'*40
    proof=docs[2]['live_shadow']['runtime_proof'];proof['revision']='b'*40
    now=datetime.fromtimestamp(now_us/1000000,timezone.utc)
    proof['startup']=datetime.fromtimestamp((now_us-500000)/1000000,timezone.utc).isoformat()
    maintenance=tmp_path.resolve()/'maintenance';maintenance.mkdir()
    evidence=tmp_path.resolve()/'evidence';receipts=evidence/'shared/provider-connection-v1/maintenance';receipts.mkdir(parents=True)
    claim=dict(schema='KRONOS_MAINTENANCE_CONSUMPTION_V2',generation=expected['generation'],parent_pid=h.INCIDENT_PID,
        process_id=expected['pid'],runtime_identity='c'*64,accepted_at=proof['startup'])
    receipt=dict(schema='RUNTIME_STARTUP_MAINTENANCE_EXIT_V1',runtime_identity='c'*64,maintenance_identity=expected['generation'],
        at=now.isoformat(),trigger='VERIFIED_CANONICAL_STARTUP')
    if fault=='claim_parent': claim['parent_pid']+=1
    elif fault=='claim_generation': claim['generation']='d'*64
    elif fault=='receipt_trigger': receipt['trigger']='MANUAL'
    elif fault=='receipt_time': receipt['at']='2030-01-01T00:00:00+00:00'
    elif fault=='owner_failure': docs[0]['startup_restoration_outcomes'][-1][1]='FAILED'
    for p,v,missing in [(maintenance/(expected['generation']+'.consumed.json'),claim,'claim_missing'),
                        (receipts/('c'*64+'-startup.json'),receipt,'receipt_missing')]:
        if fault!=missing: p.write_text(json.dumps(v));p.chmod(0o600)
    auth=tmp_path/'authorization';auth.write_text(json.dumps(a));auth.chmod(0o600)
    digest=hashlib.sha256(auth.read_bytes()).hexdigest()
    if fault=='auth_drift': auth.write_text('{}')
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return now.astimezone(tz or timezone.utc)
    monkeypatch.setattr(h,'datetime',Clock)
    monkeypatch.setattr(h.sys,'stdin',io.TextIOWrapper(io.BytesIO(json.dumps(docs).encode())))
    args=['--incident-phase','successor','--authorization',str(auth),'--authorization-sha256',digest,
        '--revision','b'*40,'--generation',expected['generation'],'--pid',str(expected['pid']),
        '--maintenance-root',str(maintenance),'--evidence-root',str(evidence)]
    assert h.main(args)==(0 if fault is None else 2)
    assert capsys.readouterr().out=='KRONOS_IWO07R3_RECOVERY_V1 '+('VALID\n' if fault is None else 'INVALID\n')


def test_iwo07r3_wrong_destination_occupancy_is_not_stage_a_success(incident_authority):
    from pathlib import Path
    from tools import failed_active_successor as h
    _,receipt,_=incident_authority
    # Even identical content at a different inode is not the exact restored file.
    p=Path(receipt['artifacts'][0]['path']);other=p.with_suffix('.new');other.write_bytes(p.read_bytes());other.chmod(0o600);other.replace(p)
    with pytest.raises(ValueError,match='ARTIFACT_IDENTITY'): h.verify_incident_artifacts(receipt)


@pytest.mark.parametrize('changed', [None, 'st_atime_ns', 'st_mtime_ns', 'st_ctime_ns',
    'st_ino', 'st_dev', 'st_size', 'st_mode', 'st_uid', 'st_gid', 'st_nlink'])
def test_iwo07r3_descriptor_stability_excludes_read_access_time(tmp_path, monkeypatch, changed):
    from types import SimpleNamespace
    from tools import failed_active_successor as h
    import hashlib
    path = tmp_path.resolve() / 'immutable-evidence'
    path.write_bytes(b'exact immutable evidence')
    path.chmod(0o600)
    original = h.os.fstat
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size',
              'st_nlink', 'st_atime_ns', 'st_mtime_ns', 'st_ctime_ns')
    calls = 0
    def observed(fd):
        nonlocal calls
        info = original(fd)
        calls += 1
        if calls == 2 and changed:
            values = {name: getattr(info, name) for name in fields}
            values[changed] += 1
            return SimpleNamespace(**values)
        return info
    monkeypatch.setattr(h.os, 'fstat', observed)
    if changed in (None, 'st_atime_ns'):
        digest, _ = h._incident_digest(path, expected_size=24)
        assert digest == hashlib.sha256(b'exact immutable evidence').hexdigest()
    else:
        with pytest.raises(ValueError, match='IWO07R3_FILE_CHANGED'):
            h._incident_digest(path, expected_size=24)
    assert calls == 2
