from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha1, sha256
import errno
import fcntl
import json
import os
from pathlib import Path
import signal
from threading import Barrier, Thread
import time

import pytest

from kronos.common import failed_successor_restore as restore
from kronos.common import release_admission
from kronos.common.failed_successor_restore import (
    FailedSuccessorRestoreError,
    RestorationChildIdentity,
    RestorationStartupContext,
    SelectedPermit,
    SelectedReservation,
    consume_failed_successor_restore,
)
from kronos.common.release_admission import (
    AdmissionCustody, AnchorBinding, CANONICAL_PARENT, ValidationBudget,
)


_DEFAULT_BUDGET = object()


def _h(label: str) -> str:
    return sha256(label.encode()).hexdigest()


def _revision(label: str) -> str:
    return sha1(label.encode()).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _put(path: Path, value: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    raw = _canonical(value)
    path.write_bytes(raw)
    path.chmod(0o600)
    return raw


def _ref(path: Path, identity: str, raw: bytes) -> dict[str, object]:
    return {"identity": identity, "path": str(path), "bytes": len(raw),
            "sha256": sha256(raw).hexdigest()}


def _s304_admit_fixture(root, installation, *, parent=None):
    """NEW SYNTHETIC admission authority for disposable component fixtures.

    These records are not recovered history and never operational decisions.
    The admitted historical selection is independent of the current artifact,
    avoiding a native-binary/artifact/embedded-policy digest cycle.
    """
    current = json.loads((root/'admission-head.json').read_bytes())
    first_path=root/'head-1.json'
    if first_path.exists():
        first=json.loads(first_path.read_bytes())
        if first['state']!='NATIVE_ACTIVATED': return None
        phase=json.loads((root/(first['active_reservation_id']+'.json')).read_bytes())
    else:
        identifier='s304-synthetic-original-activation'
        phase=dict(schema='KRONOS_NATIVE_ADMISSION_PHASE_V1',identity=identifier,
            phase='NATIVE_ACTIVATED',original_attempt_id=identifier,installation_identity=installation['identity'],
            installation=installation,parent=parent,predecessor=None,selection=None,previous=None,
            details={},recorded_at=current['recorded_at'])
        first=dict(current,sequence=1,state='NATIVE_ACTIVATED',incident_id=None,
            active_reservation_id=identifier,previous_head_sha256='0'*64)
    identifier=phase['identity']
    if parent is None:
        parent=phase.get('parent') or dict(pid=os.getppid(),kernel_birth=_h('synthetic-kernel-birth'),
            runtime_identity=_h('synthetic-runtime'),revision=_revision('synthetic-initializer'))
    selection_path=root/'s304-historical-selection.json'
    order_path=root/'s304-synthetic-order.json'
    order=_ref(order_path,'s304-synthetic-order',_put(order_path,{'label':'SYNTHETIC TEST AUTHORITY ONLY'}))
    source_path=root/'s304-historical-source.json';artifact_path=root/'s304-historical-artifact.json'
    source_ref=_ref(source_path,'s304-historical-source',_put(source_path,{'label':'SYNTHETIC historical source evidence'}))
    artifact_ref=_ref(artifact_path,'s304-historical-artifact',_put(artifact_path,{'label':'SYNTHETIC historical artifact evidence'}))
    target=dict(revision=parent['revision'],tree_sha256=_h('synthetic-original-tree'),
        source_manifest_sha256=source_ref['sha256'],artifact_manifest_sha256=artifact_ref['sha256'],
        pinned_capture_sha256=_h('synthetic-original-capture'),origin_url='git@github.com:imran/Project-Kronos.git',
        source_ref='refs/heads/maintenance/release-b-swing-ux')
    selected=_ref(selection_path,'s304-historical-selection',_put(selection_path,dict(
        schema='KRONOS_NATIVE_STARTUP_SELECTION_V1',selection_id='s304-historical-selection',mode='ORDINARY',
        installation=installation,target=target,source_manifest=source_ref,artifact_manifest=artifact_ref,
        operational_order=order,decisions={k:order for k in ('sponsor','ca','pcp','product')},permit=None,
        valid_from=first['recorded_at'],valid_until=first['recorded_at'])))
    attempt=dict(schema=restore.INITIALIZATION_ATTEMPT_SCHEMA,attempt_id=identifier,
        installation=installation,selection=selected,operator_order=order,parent=parent,
        predecessor=None,eligibility='COLD_ABSENT',started_at=first['recorded_at'],deadline_ns=1)
    attempt_path=root/'initialization-attempt.json'
    attempt_ref=_ref(attempt_path,identifier,_put(attempt_path,attempt))
    phase.update(schema='KRONOS_NATIVE_ADMISSION_PHASE_V1',original_attempt_id=identifier,
        installation=installation,parent=parent,predecessor=None,selection=selected,previous=None)
    phase.setdefault('recorded_at',first['recorded_at'])
    phase['details']=dict(phase.get('details',{}),initialization_attempt=attempt_ref,enrolled_predecessor=None)
    phase_path=root/(identifier+'.json');phase_raw=_put(phase_path,phase)
    first['active_reservation_sha256']=sha256(phase_raw).hexdigest()
    first_raw=_put(first_path,first)
    # Legacy arbitrary-head fixtures now have a coherent two-head roster.
    if not (root/f"head-{current['sequence']}.json").exists() and current['sequence']>2:
        current['sequence']=2
    previous=first_raw
    for sequence in range(2,current['sequence']+1):
        path=root/f'head-{sequence}.json'
        item=current if sequence==current['sequence'] else json.loads(path.read_bytes())
        item['previous_head_sha256']=sha256(previous).hexdigest();previous=_put(path,item)
    if current['sequence']==1:current=first
    _put(root/'admission-head.json',current)
    evidence_path=root/'s304-resolution-evidence.json'
    evidence=dict(schema=restore.INITIALIZATION_EVIDENCE_SCHEMA,identity='s304-resolution-evidence',
        attempt=attempt_ref,observations=[],missing_or_uncertain=['original final-write timing UNPROVED'],
        subsequent_observations=[])
    evidence_ref=_ref(evidence_path,evidence['identity'],_put(evidence_path,evidence))
    descriptor=dict(schema=restore.INITIALIZATION_DISPOSITION_SCHEMA,identity='s304-synthetic-disposition',
        scope='ADMIT_THIS_RETAINED_GENESIS_LINEAGE',installation_identity=installation['identity'],
        attempt=attempt_ref,genesis_head=_ref(first_path,'head-1',first_raw),
        genesis_phase=_ref(phase_path,identifier,phase_raw),original_outcome='UNPROVED_OR_LATE_UNRESOLVED',
        evidence=evidence_ref,authority={k:order for k in ('sponsor','ca','pcp','product')},
        decided_at=first['recorded_at'])
    raw=_canonical(descriptor)
    path=root/'s304-fixture-disposition.json';path.write_bytes(raw);path.chmod(0o600)
    for file in root.iterdir():
        if file.is_file() and not file.is_symlink():
            fd=os.open(file,os.O_RDONLY|os.O_NOFOLLOW);os.fsync(fd);os.close(fd)
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    restore.INITIALIZATION_DISPOSITION=raw
    return raw


def _s304_resolve_retained_fixture(root,installation):
    """A separately identified SYNTHETIC resolution; never repair an attempt."""
    original={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
    attempt_path=root/'initialization-attempt.json';attempt=json.loads(original[attempt_path.name])
    first_path=root/'head-1.json';first=json.loads(original[first_path.name])
    phase_path=root/(first['active_reservation_id']+'.json')
    attempt_ref=_ref(attempt_path,attempt['attempt_id'],original[attempt_path.name])
    order_path=root/'s304-separate-resolution-order.json'
    order=_ref(order_path,'s304-SEPARATE-resolution',_put(order_path,{
        'label':'NEW SYNTHETIC RESOLUTION AUTHORITY; ORIGINAL COMPLETION REMAINS UNRESOLVED'}))
    evidence_path=root/'s304-separate-resolution-evidence.json'
    evidence=dict(schema=restore.INITIALIZATION_EVIDENCE_SCHEMA,identity='s304-separate-resolution-evidence',
        attempt=attempt_ref,observations=[],missing_or_uncertain=['original completion timing unresolved'],
        subsequent_observations=[])
    raw=_canonical(dict(schema=restore.INITIALIZATION_DISPOSITION_SCHEMA,identity='s304-separately-admitted',
        scope='ADMIT_THIS_RETAINED_GENESIS_LINEAGE',installation_identity=installation['identity'],attempt=attempt_ref,
        genesis_head=_ref(first_path,'head-1',original[first_path.name]),
        genesis_phase=_ref(phase_path,first['active_reservation_id'],original[phase_path.name]),
        original_outcome='UNPROVED_OR_LATE_UNRESOLVED',
        evidence=_ref(evidence_path,evidence['identity'],_put(evidence_path,evidence)),
        authority={k:order for k in ('sponsor','ca','pcp','product')},decided_at=first['recorded_at']))
    assert original=={name:(root/name).read_bytes() for name in original}
    return raw


@dataclass
class _Case:
    root: Path
    evidence: Path
    permit_path: Path
    reservation_path: Path
    incident_path: Path
    failure_path: Path
    settled_path: Path
    head_path: Path
    claim_path: Path
    selected_permit: SelectedPermit
    selected_reservation: SelectedReservation
    custody: AdmissionCustody
    child: RestorationChildIdentity
    now: datetime
    original_v2_path: Path
    retained_path: Path

    def close(self) -> None:
        if not self.custody.released:
            self.custody._close()
        patch=getattr(self,"_fixture_pin_patch",None)
        if patch is not None:patch.undo()


def _make_case_legacy_binding(tmp_path: Path, *,
               completion_entered: bool = True, ready_outcome: str | None = None,
               receipt: str = "PROVEN_NOT_CREATED", ambiguity: str = "NONE",
               cleanup_state: str = "COMPLETE", helpers: str = "TERMINAL",
               actionable: int = 0, acknowledged: bool = True,
               custody_disposition: str = "RELEASED_AFTER_COMPLETE_CLEANUP",
               terminal_observation: str = "TERMINAL_REAPED",
               reservation_state: str = "RESTORATION_RESERVED",
               head_state: str = "RESTORATION_RESERVED",
               expired: bool = False, permit_extra: bool = False,
               budget=_DEFAULT_BUDGET, parent_image=None) -> _Case:
    root = tmp_path.resolve() / _h(str(tmp_path))[:12]
    root.mkdir(mode=0o700, parents=True)
    anchor = root / "runtime"
    anchor.mkdir(mode=0o700)
    evidence = anchor / "failed-successor-restore-v1"
    evidence.mkdir(mode=0o700)
    metadata = anchor.stat()
    installation_core = {
        "anchor_path": str(anchor), "device": metadata.st_dev,
        "inode": metadata.st_ino, "owner": os.getuid(),
        "bundle_id": "com.project-kronos.browser-v1",
        "bundle_path": str(root / "fixture-KRONOS.app"),
        "repository_path": str(root / "fixture-repository"),
    }
    installation = {"identity": sha256(_canonical(installation_core)).hexdigest(),
                    **installation_core}
    now = datetime(2026, 10, 26, 6, 0, tzinfo=UTC)
    if ready_outcome is None:
        ready_outcome = ("NEVER_READY_POSITIVELY_ESTABLISHED" if completion_entered
                         else "COMPLETION_PROVEN_NOT_ENTERED")
    valid_from = now - timedelta(minutes=1)
    valid_until = now - timedelta(seconds=1) if expired else now + timedelta(minutes=5)
    failed = {"pid": os.getpid() + 10000, "kernel_birth": _h("failed-birth"),
              "runtime_identity": _h("failed-runtime"),
              "revision": _revision("failed-revision")}
    predecessor = {"pid": os.getpid() + 9000, "kernel_birth": _h("old-birth"),
                   "runtime_identity": _h("old-runtime"),
                   "revision": _revision("old-revision")}
    original_parent = {"pid": os.getpid() + 8000,
                       "kernel_birth": _h("original-parent-birth"),
                       "runtime_identity": _h("original-parent-runtime"),
                       "revision": _revision("original-parent-revision")}
    failed_target = {"revision": failed["revision"],
                     "tree_sha256": _h("failed-tree"),
                     "source_manifest_sha256": _h("failed-source-manifest"),
                     "artifact_manifest_sha256": _h("failed-artifact-manifest"),
                     "pinned_capture_sha256": _h("failed-pinned-capture"),
                     "origin_url": "git@github.com:imran/Project-Kronos.git",
                     "source_ref": "refs/heads/maintenance/release-b-swing-ux"}
    original_v2 = {
        "handoff_identity": "v2-handoff-1", "handoff_sha256": _h("v2-handoff"),
        "consumption_identity": "v2-consumption-1",
        "consumption_sha256": _h("v2-consumption"),
    }
    incident_id = "incident-" + _h("incident")
    attempt_id = "attempt-" + _h("attempt")
    incident = {
        "schema": restore.INCIDENT_SCHEMA, "incident_id": incident_id,
        "original_attempt_id": attempt_id,
        "installation_identity": installation["identity"],
        "predecessor": predecessor, "original_parent": original_parent,
        "failed_successor": failed, "failed_target": failed_target,
        "original_admission_identity": "admission-" + _h("admission"),
        "original_v2": original_v2, "created_at": (now - timedelta(minutes=5)).isoformat(),
    }
    incident_path = evidence / "incident.json"
    incident_raw = _put(incident_path, incident)
    incident_ref = _ref(incident_path, incident_id, incident_raw)

    checkpoint = {"state": "VALID_PENDING", "pending_count": 2,
                  "sha256": _h("notification-checkpoint")}
    settled_id = "settled-" + _h("settled")
    settled = {
        "schema": restore.SETTLED_SCHEMA, "settled_state_id": settled_id,
        "incident_id": incident_id, "status": "CERTIFIED_CURRENT",
        "state_manifest_identity": "state-manifest-" + _h("state-manifest"),
        "state_manifest_sha256": _h("state-manifest-bytes"),
        "owner_results_sha256": _h("owner-results"),
        "notification_checkpoint": checkpoint, "original_v2": original_v2,
        "certified_at": (now - timedelta(minutes=3)).isoformat(),
    }
    settled_path = evidence / "settled.json"
    settled_raw = _put(settled_path, settled)
    settled_ref = _ref(settled_path, settled_id, settled_raw)

    failure_id = "failure-" + _h("failure")
    failure = {
        "schema": restore.FAILURE_SCHEMA, "failure_cleanup_id": failure_id,
        "incident_id": incident_id, "original_attempt_id": attempt_id,
        "failed_successor": failed, "failure_stage": "CANONICAL_STARTUP",
        "failure_result": "FAILED_BEFORE_READY",
        "ready": {"completion_entered": completion_entered, "outcome": ready_outcome,
                  "receipt": receipt, "ambiguity": ambiguity},
        "cleanup": {"state": cleanup_state,
                    "owner_ledger_identity": "ledger-" + _h("ledger"),
                    "owner_ledger_sha256": _h("ledger-bytes"),
                    "final_owner_proof_identity": "proof-" + _h("proof"),
                    "final_owner_proof_sha256": _h("proof-bytes"),
                    "validation_helpers": helpers,
                    "actionable_owner_count": actionable,
                    "acknowledged": acknowledged,
                    "custody_disposition": custody_disposition},
        "parent_terminal": {"parent_pid": original_parent["pid"],
                            "parent_kernel_birth": original_parent["kernel_birth"],
                            "child_pid": failed["pid"],
                            "child_kernel_birth": failed["kernel_birth"],
                            "observation": terminal_observation, "exit_code": 78},
        "settled_state": settled_ref,
        "recorded_at": (now - timedelta(minutes=2)).isoformat(),
    }
    failure_path = evidence / "failure.json"
    failure_raw = _put(failure_path, failure)
    failure_ref = _ref(failure_path, failure_id, failure_raw)

    target = {"revision": _revision("restoration-revision"),
              "tree_sha256": _h("tree"),
              "source_manifest_sha256": _h("source-manifest"),
              "artifact_manifest_sha256": _h("artifact-manifest"),
              "pinned_capture_sha256": _h("pinned-capture"),
              "origin_url": "git@github.com:imran/Project-Kronos.git",
              "source_ref": "refs/heads/maintenance/release-b-swing-ux"}
    permit_id = "permit-" + _h("permit")
    permit = {
        "schema": restore.PERMIT_SCHEMA, "permit_id": permit_id,
        "installation": installation, "incident": incident_ref,
        "failure_cleanup": failure_ref, "settled_state": settled_ref,
        "restoration_target": target,
        "authority": {
            "sponsor_order_identity": "sponsor-order-1",
            "sponsor_order_sha256": _h("sponsor-order"),
            "ca_decision_identity": "ca-decision-1",
            "ca_decision_sha256": _h("ca-decision"),
            "pcp_decision_identity": "pcp-decision-1",
            "pcp_decision_sha256": _h("pcp-decision"),
            "product_decision_identity": "product-decision-1",
            "product_decision_sha256": _h("product-decision"),
        },
        "created_at": (now - timedelta(seconds=90)).isoformat(),
        "approved_at": (now - timedelta(seconds=75)).isoformat(),
        "valid_from": valid_from.isoformat(), "valid_until": valid_until.isoformat(),
        "maximum_children": 1,
        "operation_scope": "ONE_FAILED_SUCCESSOR_RESTORATION_START",
    }
    if permit_extra:
        permit["approval"] = True
    permit_path = root / "operator-selected-permit.json"
    permit_raw = _put(permit_path, permit)
    selected_permit = SelectedPermit(permit_path, len(permit_raw),
                                     sha256(permit_raw).hexdigest(), permit_id)

    reservation_id = "reservation-" + _h("reservation")
    head_path = evidence / "admission-head.json"
    claim_path = evidence / f"{incident_id}.{reservation_id}.child-claimed.json"
    parent = {"pid": os.getppid(), "kernel_birth": _h("parent-birth"),
              "runtime_identity": _h("parent-runtime"),
              "revision": _revision("parent-revision")}
    reservation = {
        "schema": restore.RESERVATION_SCHEMA, "reservation_id": reservation_id,
        "incident_id": incident_id, "permit_id": permit_id,
        "permit_sha256": selected_permit.sha256,
        "installation_identity": installation["identity"], "state": reservation_state,
        "parent": parent, "restoration_target": target, "settled_state": settled_ref,
        "attempt_nonce": _h("attempt-nonce"), "created_at": now.isoformat(),
        "valid_until": valid_until.isoformat(), "head_path": str(head_path),
        "claim_path": str(claim_path),
    }
    reservation_path = evidence / "reservation.json"
    reservation_raw = _put(reservation_path, reservation)
    selected_reservation = SelectedReservation(
        reservation_path, len(reservation_raw), sha256(reservation_raw).hexdigest(),
        reservation_id)
    head = {"schema": restore.HEAD_SCHEMA,
            "installation_identity": installation["identity"], "sequence": 7,
            "state": head_state, "incident_id": incident_id,
            "active_reservation_id": reservation_id,
            "active_reservation_sha256": selected_reservation.sha256,
            "previous_head_sha256": _h("previous-head"),
            "recorded_at": now.isoformat()}
    _put(head_path, head)

    original_v2_path = root / "original-v2.json"
    retained_path = root / "retained-history.json"
    _put(original_v2_path, {"handoff": original_v2, "bytes": "immutable"})
    _put(retained_path, {"wo12": _h("wo12"), "intraday": _h("intraday"),
                         "journal": _h("journal"), "books": _h("books"),
                         "theta": _h("theta")})

    descriptor = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    binding = AnchorBinding(anchor, metadata.st_dev, metadata.st_ino, os.getuid())
    if budget is _DEFAULT_BUDGET:
        budget = ValidationBudget(release_admission.monotonic_ns()
                                  + 10_000_000_000)
    custody = AdmissionCustody(descriptor, binding, os.getppid(),
                               parent_image=(parent_image if parent_image is not None else lambda _pid: CANONICAL_PARENT),
                               budget=budget)
    child = RestorationChildIdentity(
        process_id=os.getpid(), parent_pid=os.getppid(),
        parent_kernel_birth=parent["kernel_birth"], kernel_birth=_h("child-birth"),
        runtime_identity=_h("child-runtime"), loaded_revision=target["revision"],
        source_manifest_sha256=target["source_manifest_sha256"],
        artifact_manifest_sha256=target["artifact_manifest_sha256"],
        pinned_capture_sha256=target["pinned_capture_sha256"])
    _s304_admit_fixture(evidence,installation,parent=parent)
    return _Case(root, evidence, permit_path, reservation_path, incident_path,
                 failure_path, settled_path, head_path, claim_path,
                 selected_permit, selected_reservation, custody, child, now,
                 original_v2_path, retained_path)


def _make_case(*args,**kwargs):
    from tests.unit.tools.test_place_release_pair import assert_actual_preparatory_source
    assert_actual_preparatory_source()
    patch=pytest.MonkeyPatch()
    patch.setattr(release_admission,'PERSISTENT_ANCHOR_BINDING',None)
    try:
        result=_make_case_legacy_binding(*args,**kwargs)
        result._fixture_pin_patch=patch
        return result
    except BaseException:
        patch.undo()
        raise


@pytest.fixture
def case_factory(tmp_path):
    cases: list[_Case] = []

    def factory(**values):
        case = _make_case(tmp_path / str(len(cases)), **values)
        cases.append(case)
        return case

    yield factory
    for case in reversed(cases):
        case.close()


def _consume(case: _Case, **values):
    clock = values.get("clock", lambda: values.get("now", case.now))
    return consume_failed_successor_restore(
        values.get("permit", case.selected_permit),
        values.get("reservation", case.selected_reservation),
        custody=values.get("custody", case.custody),
        child=values.get("child", case.child), clock=clock)


def _denied(case: _Case, **values):
    with pytest.raises(FailedSuccessorRestoreError,
                       match="^FAILED_SUCCESSOR_RESTORE_REJECTED$"):
        _consume(case, **values)


@pytest.mark.parametrize('finding', ('valid-separate-disposition','no-disposition',
    'missing-attempt','truncated-attempt','missing-evidence','missing-authority',
    'changed-first-head','changed-phase','grafted-current-lineage','next-intent',
    'contradictory-outcome','wrong-policy-installation','unsafe-attempt-mode'))
def test_s304_direct_consumer_persistent_initialization_fence(case_factory,monkeypatch,record_property,finding):
    case=case_factory(completion_entered=False)
    root=case.head_path.parent
    original=(root/'initialization-attempt.json').read_bytes()
    retained=case.retained_path.read_bytes();v2=case.original_v2_path.read_bytes()
    budget=case.custody.budget;deadline=budget.deadline_ns
    policy=json.loads(restore.INITIALIZATION_DISPOSITION)
    assert policy['original_outcome']=='UNPROVED_OR_LATE_UNRESOLVED'
    assert json.loads(original)['deadline_ns']==1  # Original expiry is never renewed.
    if finding=='no-disposition':monkeypatch.setattr(restore,'INITIALIZATION_DISPOSITION',None)
    elif finding=='missing-attempt':(root/'initialization-attempt.json').unlink()
    elif finding=='truncated-attempt':(root/'initialization-attempt.json').write_bytes(original[:13])
    elif finding=='missing-evidence':(root/'s304-resolution-evidence.json').unlink()
    elif finding=='missing-authority':(root/'s304-synthetic-order.json').unlink()
    elif finding=='changed-first-head':
        item=json.loads((root/'head-1.json').read_bytes());item['recorded_at']='2026-10-25T00:00:00+00:00'
        _put(root/'head-1.json',item)
    elif finding=='changed-phase':
        p=Path(policy['genesis_phase']['path']);p.write_bytes(p.read_bytes()+b' ')
    elif finding=='grafted-current-lineage':
        item=json.loads(case.head_path.read_bytes());item['previous_head_sha256']='f'*64
        _put(case.head_path,item);_put(root/'head-2.json',item)
    elif finding=='next-intent':_put(root/'head-3.json',{'uncertain':True})
    elif finding=='unsafe-attempt-mode':(root/'initialization-attempt.json').chmod(0o644)
    elif finding in {'contradictory-outcome','wrong-policy-installation'}:
        policy['original_outcome' if finding=='contradictory-outcome' else 'installation_identity']='NOT_AUTHORIZED'
        monkeypatch.setattr(restore,'INITIALIZATION_DISPOSITION',_canonical(policy))
    if finding=='valid-separate-disposition':
        result=_consume(case)
        assert result.process_id==os.getpid() and case.claim_path.exists()
        assert (root/'initialization-attempt.json').read_bytes()==original
        assert json.loads(restore.INITIALIZATION_DISPOSITION)['original_outcome']=='UNPROVED_OR_LATE_UNRESOLVED'
    else:
        _denied(case);assert not case.claim_path.exists()
    assert case.custody.budget is budget and budget.deadline_ns==deadline
    assert not case.custody.released and not case.custody.cleanup_started
    assert case.retained_path.read_bytes()==retained and case.original_v2_path.read_bytes()==v2
    record_property('s304_application_before_fixture_teardown',json.dumps(dict(
        claim_created=case.claim_path.exists(),custody_retained=True,cleanup_started=False,
        original_budget_unchanged=True,authority='SYNTHETIC TEST-ONLY STATIC DISPOSITION',
        fixture_teardown='case_factory close-only after observations')))


def test_s304_post_claim_fence_denial_preserves_spent_claim(case_factory,monkeypatch,record_property):
    case=case_factory(completion_entered=False)
    pin=restore.INITIALIZATION_DISPOSITION;actual=restore._write_claim
    def write(path,document,*,custody):
        raw=actual(path,document,custody=custody)
        monkeypatch.setattr(restore,'INITIALIZATION_DISPOSITION',None)
        return raw
    monkeypatch.setattr(restore,'_write_claim',write)
    _denied(case)
    spent=case.claim_path.read_bytes()
    monkeypatch.setattr(restore,'INITIALIZATION_DISPOSITION',pin)
    _denied(case)
    assert case.claim_path.read_bytes()==spent and not case.custody.released
    record_property('s304_application_outcome','post-claim denied; claim permanently spent; custody retained; teardown separate')


def test_s304_final_head_read_exact_expiry_keeps_claim_spent(case_factory,monkeypatch,record_property):
    case=case_factory(completion_entered=False)
    budget=case.custody.budget;deadline=budget.deadline_ns
    now={'mono':release_admission.monotonic_ns(),'post_claim_reads':0}
    actual=restore._current_document
    def document(path):
        result=actual(path)
        if path==case.head_path and case.claim_path.exists():
            now['post_claim_reads']+=1
            if now['post_claim_reads']==2:now['mono']=deadline
        return result
    monkeypatch.setattr(release_admission,'monotonic_ns',lambda:now['mono'])
    monkeypatch.setattr(restore,'_current_document',document)
    _denied(case)
    assert now['post_claim_reads']==2 and case.claim_path.exists()
    assert case.custody.budget is budget and budget.deadline_ns==deadline
    assert not case.custody.released
    record_property('s304_application_outcome','ACTUAL final head read at original expiry; denied; original claim spent; fixture closes separately')


def _run_owned_reader_process(reader, *, timeout_seconds: float = 0.25):
    read_descriptor, write_descriptor = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_descriptor)
        outcome = b"RETURNED"
        try:
            reader()
        except FailedSuccessorRestoreError:
            outcome = b"DENIED"
        except BaseException as error:
            outcome = f"ERROR:{type(error).__name__}".encode()
        try:
            os.write(write_descriptor, outcome)
        finally:
            os.close(write_descriptor)
        os._exit(0)

    os.close(write_descriptor)
    status = None
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        waited, status = os.waitpid(child, os.WNOHANG)
        if waited == child:
            break
        time.sleep(0.005)
    else:
        # Test teardown only: the reviewed blocking open cannot reach its
        # descriptor-type check without a writer.  Kill and reap this directly
        # owned disposable child so the isolated harness cannot hang.
        os.kill(child, signal.SIGKILL)
        _, status = os.waitpid(child, 0)
        os.close(read_descriptor)
        return "WATCHDOG_TERMINATED_BLOCKING_OPEN", status

    raw = os.read(read_descriptor, 128)
    os.close(read_descriptor)
    return raw.decode() if raw else "NO_CHILD_RESULT", status


def _private_fixture_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    return directory


def test_read_raw_writerless_fifo_denies_promptly(tmp_path):
    directory = _private_fixture_directory(tmp_path)
    fifo = directory / "selected-evidence"
    os.mkfifo(fifo, 0o600)
    fifo.chmod(0o600)

    outcome, _status = _run_owned_reader_process(
        lambda: restore._read_raw(fifo, 1, sha256(b"x").hexdigest()))

    assert outcome == "DENIED"


def test_current_document_writerless_fifo_denies_promptly(tmp_path):
    directory = _private_fixture_directory(tmp_path)
    fifo = directory / "current-head"
    os.mkfifo(fifo, 0o600)
    fifo.chmod(0o600)

    outcome, _status = _run_owned_reader_process(
        lambda: restore._current_document(fifo))

    assert outcome == "DENIED"


@pytest.mark.parametrize("reader", ["selected", "current"])
def test_evidence_readers_accept_valid_regular_file(tmp_path, reader):
    directory = _private_fixture_directory(tmp_path)
    path = directory / "evidence.json"
    raw = _put(path, {"schema": "FIXTURE", "value": 1})

    if reader == "selected":
        assert restore._read_raw(path, len(raw), sha256(raw).hexdigest()) == raw
    else:
        document, observed = restore._current_document(path)
        assert document == {"schema": "FIXTURE", "value": 1}
        assert observed == raw


@pytest.mark.parametrize("reader", ["selected", "current"])
def test_evidence_readers_deny_symlink(tmp_path, reader):
    directory = _private_fixture_directory(tmp_path)
    target = directory / "target.json"
    raw = _put(target, {"schema": "FIXTURE"})
    path = directory / "evidence.json"
    path.symlink_to(target)

    with pytest.raises(FailedSuccessorRestoreError):
        if reader == "selected":
            restore._read_raw(path, len(raw), sha256(raw).hexdigest())
        else:
            restore._current_document(path)


@pytest.mark.parametrize("reader", ["selected", "current"])
def test_evidence_readers_deny_opened_directory(tmp_path, reader):
    directory = _private_fixture_directory(tmp_path)
    path = directory / "not-a-file"
    path.mkdir(mode=0o700)

    with pytest.raises(FailedSuccessorRestoreError):
        if reader == "selected":
            restore._read_raw(path, 1, sha256(b"x").hexdigest())
        else:
            restore._current_document(path)


@pytest.mark.parametrize("reader", ["selected", "current"])
def test_descriptor_validation_denies_path_replaced_with_fifo(
        tmp_path, monkeypatch, reader):
    directory = _private_fixture_directory(tmp_path)
    path = directory / "replaceable.json"
    raw = _put(path, {"schema": "FIXTURE"})
    actual_open = restore.os.open
    replaced = {"done": False}

    def replace_before_open(target, flags, *args, **kwargs):
        if Path(target) == path and not replaced["done"]:
            path.unlink()
            os.mkfifo(path, 0o600)
            path.chmod(0o600)
            replaced["done"] = True
        return actual_open(target, flags, *args, **kwargs)

    monkeypatch.setattr(restore.os, "open", replace_before_open)
    with pytest.raises(FailedSuccessorRestoreError):
        if reader == "selected":
            restore._read_raw(path, len(raw), sha256(raw).hexdigest())
        else:
            restore._current_document(path)
    assert replaced["done"] is True


@pytest.mark.parametrize("reader", ["selected", "current"])
def test_rejected_opened_fifo_descriptor_is_closed(tmp_path, monkeypatch, reader):
    directory = _private_fixture_directory(tmp_path)
    path = directory / "evidence-pipe"
    os.mkfifo(path, 0o600)
    path.chmod(0o600)
    actual_open = restore.os.open
    opened = []

    def record_open(target, flags, *args, **kwargs):
        descriptor = actual_open(target, flags, *args, **kwargs)
        if Path(target) == path:
            opened.append(descriptor)
        return descriptor

    monkeypatch.setattr(restore.os, "open", record_open)
    with pytest.raises(FailedSuccessorRestoreError):
        if reader == "selected":
            restore._read_raw(path, 1, sha256(b"x").hexdigest())
        else:
            restore._current_document(path)
    assert len(opened) == 1
    with pytest.raises(OSError) as closed:
        os.fstat(opened[0])
    assert closed.value.errno == errno.EBADF


def test_valid_exact_selection_creates_one_claim_and_context(case_factory):
    case = case_factory()
    before_head = case.head_path.read_bytes()

    context = _consume(case)

    assert type(context) is RestorationStartupContext
    assert context.incident_id.startswith("incident-")
    assert context.process_id == os.getpid()
    assert context.notification_checkpoint() == {
        "state": "VALID_PENDING", "pending_count": 2,
        "sha256": _h("notification-checkpoint")}
    assert case.claim_path.is_file()
    claim = json.loads(case.claim_path.read_bytes())
    assert claim["schema"] == restore.CLAIM_SCHEMA
    assert claim["child"]["runtime_identity"] == case.child.runtime_identity
    assert case.head_path.read_bytes() == before_head


def test_failure_before_completion_entered_is_eligible(case_factory):
    case = case_factory(completion_entered=False)

    context = _consume(case)

    assert type(context) is RestorationStartupContext
    assert case.claim_path.is_file()


def test_duplicate_claim_is_permanently_denied(case_factory):
    case = case_factory()
    _consume(case)
    first = case.claim_path.read_bytes()

    _denied(case)

    assert case.claim_path.read_bytes() == first


def test_concurrent_claims_admit_exactly_one_child(case_factory):
    case = case_factory()
    barrier = Barrier(3)
    results = []

    def run():
        barrier.wait()
        try:
            results.append(type(_consume(case)).__name__)
        except FailedSuccessorRestoreError:
            results.append("DENIED")

    threads = [Thread(target=run), Thread(target=run)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["DENIED", "RestorationStartupContext"]


def test_renamed_permit_cannot_replay_same_incident(case_factory):
    case = case_factory()
    _consume(case)
    renamed = case.root / "renamed-permit.json"
    renamed.write_bytes(case.permit_path.read_bytes())
    renamed.chmod(0o600)
    selection = replace(case.selected_permit, path=renamed)

    _denied(case, permit=selection)


def test_partial_claim_write_is_retained_and_blocks_retry(case_factory, monkeypatch):
    case = case_factory()
    actual = restore.os.write

    def partial(descriptor, payload):
        return actual(descriptor, payload[:17])

    monkeypatch.setattr(restore.os, "write", partial)
    _denied(case)
    assert case.claim_path.exists() and 0 < case.claim_path.stat().st_size < 100
    monkeypatch.setattr(restore.os, "write", actual)
    _denied(case)


def test_interrupted_claim_write_is_retained_and_blocks_retry(case_factory, monkeypatch):
    case = case_factory()
    actual = restore.os.write

    def interrupted(descriptor, payload):
        actual(descriptor, payload[:11])
        raise InterruptedError("fixture interruption")

    monkeypatch.setattr(restore.os, "write", interrupted)
    _denied(case)
    assert case.claim_path.exists()
    monkeypatch.setattr(restore.os, "write", actual)
    _denied(case)


def test_claim_fsync_failure_is_spent(case_factory, monkeypatch):
    case = case_factory()
    actual = restore.os.fsync
    calls = 0

    def fail_first(descriptor):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("fixture fsync failure")
        return actual(descriptor)

    monkeypatch.setattr(restore.os, "fsync", fail_first)
    _denied(case)
    assert case.claim_path.exists()
    monkeypatch.setattr(restore.os, "fsync", actual)
    _denied(case)


def test_claim_readback_failure_is_spent(case_factory, monkeypatch):
    case = case_factory()
    actual = restore._read_raw

    def fail_claim(path, byte_size, digest):
        if path == case.claim_path:
            raise FailedSuccessorRestoreError("FAILED_SUCCESSOR_RESTORE_REJECTED")
        return actual(path, byte_size, digest)

    monkeypatch.setattr(restore, "_read_raw", fail_claim)
    _denied(case)
    assert case.claim_path.exists()
    monkeypatch.setattr(restore, "_read_raw", actual)
    _denied(case)


@pytest.mark.parametrize("field", [
    "source_manifest_sha256", "artifact_manifest_sha256", "pinned_capture_sha256",
    "parent_kernel_birth",
])
def test_wrong_actual_child_identity_denies_before_claim(case_factory, field):
    case = case_factory()
    child = replace(case.child, **{field: _h("wrong-" + field)})
    _denied(case, child=child)
    assert not case.claim_path.exists()


def test_wrong_actual_child_process_denies(case_factory):
    case = case_factory()
    child = replace(case.child, process_id=os.getpid() + 1)
    _denied(case, child=child)


def test_missing_or_released_custody_denies(case_factory):
    case = case_factory()
    _denied(case, custody=None)
    case.custody._close()
    _denied(case)


@pytest.mark.parametrize("values", [
    {"reservation_state": "CHILD_START_RESERVED"},
    {"head_state": "FAILED_NEVER_READY"},
])
def test_invalid_native_reservation_or_head_denies(case_factory, values):
    case = case_factory(**values)
    _denied(case)
    assert not case.claim_path.exists()


@pytest.mark.parametrize("values", [
    {"ready_outcome": "READY_REACHED"},
    {"ready_outcome": "UNKNOWN"},
    {"receipt": "MISSING"},
    {"ambiguity": "INTERRUPTED"},
])
def test_ready_or_ambiguous_ready_evidence_denies(case_factory, values):
    case = case_factory(**values)
    _denied(case)


@pytest.mark.parametrize("values", [
    {"completion_entered": False,
     "ready_outcome": "NEVER_READY_POSITIVELY_ESTABLISHED"},
    {"completion_entered": True,
     "ready_outcome": "COMPLETION_PROVEN_NOT_ENTERED"},
    {"completion_entered": False, "ready_outcome": "READY_REACHED"},
    {"completion_entered": 0,
     "ready_outcome": "COMPLETION_PROVEN_NOT_ENTERED"},
])
def test_completion_phase_and_outcome_must_be_consistent(case_factory, values):
    case = case_factory(**values)
    _denied(case)


@pytest.mark.parametrize("values", [
    {"cleanup_state": "INCOMPLETE"},
    {"helpers": "UNKNOWN"},
    {"actionable": 1},
    {"acknowledged": False},
    {"custody_disposition": "RETAINED_UNRESOLVED"},
    {"terminal_observation": "EXIT_STATUS_ONLY"},
])
def test_incomplete_or_uncertain_cleanup_denies(case_factory, values):
    case = case_factory(**values)
    _denied(case)


def test_expired_permit_denies_without_claim(case_factory):
    case = case_factory(expired=True)
    _denied(case)
    assert not case.claim_path.exists()


def test_expiry_during_validation_denies_before_claim(case_factory):
    case = case_factory()
    times = iter((case.now, case.now + timedelta(minutes=6)))
    _denied(case, clock=lambda: next(times))
    assert not case.claim_path.exists()


def test_monotonic_expiry_before_claim_creates_no_claim(case_factory, monkeypatch):
    monotonic = {"now": 1}
    monkeypatch.setattr(release_admission, "monotonic_ns",
                        lambda: monotonic["now"])
    case = case_factory(budget=ValidationBudget(10))
    actual_open = restore.os.open

    def expire_after_prewrite_open(path, flags, *args, **kwargs):
        descriptor = actual_open(path, flags, *args, **kwargs)
        if (Path(path) == case.claim_path.parent
                and flags & os.O_DIRECTORY):
            monotonic["now"] = 10
        return descriptor

    monkeypatch.setattr(restore.os, "open", expire_after_prewrite_open)
    _denied(case)
    assert not case.claim_path.exists()


def test_monotonic_expiry_during_final_revalidation_denies_spent_claim(
        case_factory, monkeypatch):
    monotonic = {"now": 1}
    monkeypatch.setattr(release_admission, "monotonic_ns",
                        lambda: monotonic["now"])
    case = case_factory(budget=ValidationBudget(10))
    actual = restore._read_raw

    def expire_during_revalidation(path, byte_size, digest):
        if case.claim_path.exists() and path == case.permit_path:
            monotonic["now"] = 10
        return actual(path, byte_size, digest)

    monkeypatch.setattr(restore, "_read_raw", expire_during_revalidation)
    _denied(case)
    assert case.claim_path.exists()


def test_expiry_during_preclaim_custody_check_creates_no_claim(
        case_factory, monkeypatch):
    monotonic = {"now": 1}
    monkeypatch.setattr(release_admission, "monotonic_ns",
                        lambda: monotonic["now"])
    case = case_factory(budget=ValidationBudget(10))
    actual_write = restore._write_claim
    actual_parent_image = case.custody.parent_image

    def expire_after_internal_budget_check(pid):
        image = actual_parent_image(pid)
        monotonic["now"] = 10
        return image

    def arm_preclaim_custody_expiry(path, document, **kwargs):
        case.custody.parent_image = expire_after_internal_budget_check
        return actual_write(path, document, **kwargs)

    monkeypatch.setattr(restore, "_write_claim", arm_preclaim_custody_expiry)
    _denied(case)
    assert not case.claim_path.exists()


def test_expiry_during_final_custody_check_denies_spent_claim(
        case_factory, monkeypatch):
    monotonic = {"now": 1}
    monkeypatch.setattr(release_admission, "monotonic_ns",
                        lambda: monotonic["now"])
    case = case_factory(budget=ValidationBudget(10))
    actual_parent_image = case.custody.parent_image
    clock_calls = {"count": 0}

    def expire_after_internal_budget_check(pid):
        image = actual_parent_image(pid)
        monotonic["now"] = 10
        return image

    def arm_at_final_validation():
        clock_calls["count"] += 1
        if clock_calls["count"] == 3:
            case.custody.parent_image = expire_after_internal_budget_check
        return case.now

    _denied(case, clock=arm_at_final_validation)
    assert case.claim_path.exists()


def test_missing_or_invalid_monotonic_budget_denies_before_claim(case_factory):
    missing = case_factory(budget=None)
    _denied(missing)
    assert not missing.claim_path.exists()

    invalid = case_factory(budget=None)
    invalid.custody.budget = object()
    _denied(invalid)
    assert not invalid.claim_path.exists()


def test_utc_clock_rollback_still_denies_before_claim(case_factory):
    case = case_factory()
    times = iter((case.now, case.now - timedelta(microseconds=1)))
    _denied(case, clock=lambda: next(times))
    assert not case.claim_path.exists()


def test_changed_current_checkpoint_bytes_deny(case_factory):
    case = case_factory()
    document = json.loads(case.settled_path.read_bytes())
    document["notification_checkpoint"]["pending_count"] = 3
    _put(case.settled_path, document)
    _denied(case)
    assert not case.claim_path.exists()


def test_unknown_permit_field_is_not_an_approval(case_factory):
    case = case_factory(permit_extra=True)
    _denied(case)


def test_missing_head_denies_without_initializing_it(case_factory):
    case = case_factory()
    case.head_path.unlink()
    _denied(case)
    assert not case.head_path.exists()


def test_preexisting_partial_claim_remains_spent(case_factory):
    case = case_factory()
    case.claim_path.write_bytes(b"{")
    case.claim_path.chmod(0o600)
    _denied(case)
    assert case.claim_path.read_bytes() == b"{"


def test_head_change_after_claim_denies_and_keeps_claim(case_factory, monkeypatch):
    case = case_factory()
    actual = restore._write_claim

    def write_then_change(path, document, **kwargs):
        result = actual(path, document, **kwargs)
        head = json.loads(case.head_path.read_bytes())
        head["sequence"] += 1
        _put(case.head_path, head)
        return result

    monkeypatch.setattr(restore, "_write_claim", write_then_change)
    _denied(case)
    assert case.claim_path.exists()


def test_exact_selection_size_or_digest_mismatch_denies(case_factory):
    case = case_factory()
    _denied(case, permit=replace(case.selected_permit,
                                 sha256=_h("wrong-selected-permit")))
    _denied(case, reservation=replace(case.selected_reservation,
                                      byte_size=case.selected_reservation.byte_size - 1))


def test_claim_preserves_original_v2_and_retained_history(case_factory):
    case = case_factory()
    preserved = {path: path.read_bytes() for path in case.root.rglob("*") if path.is_file()}

    _consume(case)

    for path, raw in preserved.items():
        assert path.read_bytes() == raw
    assert set(path for path in case.root.rglob("*") if path.is_file()) == {
        *preserved, case.claim_path}


def test_claim_does_not_release_custody_or_advance_head(case_factory):
    case = case_factory()
    head = case.head_path.read_bytes()
    _consume(case)
    assert case.custody.released is False
    case.custody.check()
    assert case.head_path.read_bytes() == head


def test_e02_actual_consumer_preserves_frozen_installation_and_spent_claim(case_factory,monkeypatch,record_property):
    case=case_factory();installation=json.loads(case.permit_path.read_bytes())['installation']
    enrollment=case.root/'e02-frozen-enrollment.json';raw=_put(enrollment,installation)
    observed=release_admission.descriptor_filesystem_identity(case.custody.descriptor)
    policy=dict(schema='KRONOS_PERSISTENT_ANCHOR_BINDING_V1',installation_identity=installation['identity'],
        enrollment=_ref(enrollment,installation['identity'],raw),anchor_path=installation['anchor_path'],
        volume_uuid=observed['volume_uuid'],file_id=observed['file_id'],owner=os.getuid(),required_mode='0700',
        bundle_id=installation['bundle_id'],bundle_path=installation['bundle_path'],repository_path=installation['repository_path'])
    monkeypatch.setattr(release_admission,'PERSISTENT_ANCHOR_BINDING',_canonical(policy))
    preserved={p:p.read_bytes() for p in [case.incident_path,case.failure_path,case.settled_path,case.original_v2_path,case.retained_path,case.head_path]}
    budget=case.custody.budget;deadline=budget.deadline_ns
    context=_consume(case)
    claim=case.claim_path.read_bytes();document=json.loads(claim)
    assert document['installation_identity']==installation['identity']
    assert document['parent']==json.loads(case.reservation_path.read_bytes())['parent']
    assert document['child']['pid']==os.getpid() and document['claimed_at']==case.now.isoformat()
    assert document['permit_sha256']==case.selected_permit.sha256 and document['reservation_sha256']==case.selected_reservation.sha256
    assert case.custody.budget is budget and budget.deadline_ns==deadline
    assert all(p.read_bytes()==v for p,v in preserved.items())
    with pytest.raises((ValueError,OSError)):_consume(case)
    assert case.claim_path.read_bytes()==claim
    changed=dict(policy,volume_uuid='00000000-0000-0000-0000-000000000001')
    monkeypatch.setattr(release_admission,'PERSISTENT_ANCHOR_BINDING',_canonical(changed))
    with pytest.raises((ValueError,OSError)):_consume(case)
    assert case.claim_path.read_bytes()==claim and not case.custody.released
    record_property('e02_actual_consumer',json.dumps(dict(actual_r31_consumer=True,frozen_installation_identity=installation['identity'],
        claim_sha256=sha256(claim).hexdigest(),claim_permanently_spent=True,original_budget_and_history_preserved=True,
        synthetic_authority_records=True,canonical_integration_claimed=False)))
