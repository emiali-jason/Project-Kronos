"""Retained capability facts, synthetic isolated epochs; no live service access."""
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from copy import deepcopy
import json
import pytest

import tests.unit.intraday.test_live_shadow as base
import tests.unit.intraday.test_live_shadow_epochs as epochs
from kronos.application.intraday_live_shadow import IntradayLiveShadowService
from kronos.intraday.live_shadow_epochs import document, capabilities, compatible
from kronos.intraday.live_shadow_transition import capability_identity
from kronos.intraday.runtime_identity import LoadedCapability, create_runtime_manifest, LauncherConfiguration
from tests.unit.intraday.test_runtime_identity import _seed

FACTS = json.loads(Path(__file__).with_name('wo06h_production_capability_mismatch.json').read_text())
START = datetime.fromisoformat(FACTS['historical_start'])
CURRENT = datetime.fromisoformat('2026-09-11T20:00:00+05:30')


def bound_service(root, caps, revision, at):
    from kronos.intraday.live_shadow_persistence import ShadowStore
    s = IntradayLiveShadowService(store=ShadowStore(root), clock=lambda:at)
    m = create_runtime_manifest(_seed(source_revision=revision, startup_boundary_at=at),
        LauncherConfiguration(8947, False), tuple(LoadedCapability(**c) for c in caps))
    s.bind_runtime(m)
    return s


@pytest.fixture
def production_case(tmp_path, monkeypatch):
    def initial(root):
        s = bound_service(root, FACTS['historical_capabilities'], FACTS['historical_revision'], START)
        s.accept_runtime(expected_revision=FACTS['historical_revision'], request_identity='ISOLATED_HISTORICAL')
        return s, None, s._manifest
    original_restart = epochs.restart
    monkeypatch.setattr(base, 'NOW', START)
    monkeypatch.setattr(epochs, 'service', initial)
    monkeypatch.setattr(epochs, 'restart', lambda root, old: bound_service(root,
        FACTS['current_capabilities'], FACTS['current_revision'], CURRENT))
    old, new = epochs.current_fixture(tmp_path)
    monkeypatch.setattr(epochs, 'restart', original_restart)
    return old, new


def authority(s):
    payload = epochs.authorize(s)
    # Bind the precise reviewed diagnosis, without accessing production stores.
    auth = s._epochs.load(payload['authorization_identity'])
    d = s._epochs.load(auth['body']['diagnosis'])
    diagnosis = document('diagnosis', dict(d['body'], report_sha256=FACTS['diagnosis_report_sha256'],
        changed_semantics=FACTS['changed_semantics']))
    s._epochs.retain(diagnosis)
    bridge = s._epochs.load(auth['body']['bridge'])
    bridge = document('bridge', dict(bridge['body'], diagnosis=diagnosis['identity'], changed_semantics=FACTS['changed_semantics']))
    s._epochs.retain(bridge)
    auth = document('authorization', dict(auth['body'], diagnosis=diagnosis['identity'], bridge=bridge['identity']))
    s._epochs.retain(auth)
    return dict(payload, authorization_identity=auth['identity'])


def rewrite_bridge(s, payload, edit):
    auth = s._epochs.load(payload['authorization_identity'])
    bridge = s._epochs.load(auth['body']['bridge']);body = deepcopy(bridge['body']);edit(body)
    bridge = document('bridge', body);s._epochs.retain(bridge)
    auth = document('authorization', dict(auth['body'], bridge=bridge['identity']));s._epochs.retain(auth)
    return dict(payload, authorization_identity=auth['identity'])


def test_retained_production_mismatch_commissions_only_new_epoch(production_case, tmp_path):
    old, s = production_case
    before = epochs.inventory(tmp_path)
    a, b = capabilities(old._runtime_proof()), capabilities(s._runtime_proof())
    changed = {n for n in a if a[n] != b[n]}
    assert changed == {'INTRADAY_DISCOVERY_OPERATION', 'WO_05A_TRUSTED_TIME_ADMISSION', 'WO_05B_OPERATION_ACCOUNTING'}
    assert a['WO_06H_LIVE_SHADOW'] == b['WO_06H_LIVE_SHADOW']
    assert not s.status()['enabled'] and s.status()['failure'] == 'SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE'
    assert old._window.body['start'] == FACTS['historical_start'] and old._window.body['end'] == FACTS['historical_end']
    result = epochs.perform(s, authority(s));st = result['status']
    assert result['outcome'] == 'ESTABLISHED'
    assert st['enabled'] and st['epochs'][1]['compatibility'] == 'INCOMPATIBLE'
    assert [st['epochs'][1]['counts'][k] for k in ('cohort_a','cohort_b','eod_available')] == [34,66,0]
    assert [st['counts'][k] for k in ('cohort_a','cohort_b','eod_available')] == [0,0,0]
    assert st['window']['start'] == CURRENT.isoformat() and st['window']['end'] == '2026-10-11T20:00:00+05:30'
    assert s._epochs.chain()[0]['body']['proof'] == s._runtime_proof()
    assert all((tmp_path/p).read_bytes() == v for p,v in before.items())
    assert len(s._epochs.raw.all('observation')) == 100 and len(s._epochs.raw.all('outcome')) == 0
    assert len(s._epochs.raw.all('window')) == len(s._epochs.raw.all('acceptance')) == 2
    assert old._epochs.bound(old._epochs.chain()[1])


@pytest.mark.parametrize('case', ['A_A','A_B','B_B','B_C','B_A'])
def test_same_epoch_equality_is_never_relaxed(production_case, tmp_path, case):
    old, s = production_case
    if case.startswith('B'):
        epochs.perform(s, authority(s))
    ref = s if case in {'B_B','B_C'} else old
    restored = epochs.restart(tmp_path, ref, changed=False, at=CURRENT+timedelta(minutes=1))
    if case in {'A_B','B_C'}:
        restored = bound_service(tmp_path, FACTS['current_capabilities'], FACTS['current_revision'], CURRENT+timedelta(minutes=1))
        if case == 'B_C':
            caps = [dict(c, implementation_digest='e'*64) if c['identity']=='WO_05B_OPERATION_ACCOUNTING' else c for c in FACTS['current_capabilities']]
            restored = bound_service(tmp_path, caps, 'e'*40, CURRENT+timedelta(minutes=1))
    assert restored.status()['enabled'] == (case in {'A_A','B_B'})
    if case not in {'A_A','B_B'}:
        assert restored.status()['failure'] == 'SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE'


@pytest.mark.parametrize('field,value,code', [
    ('predecessor','WO06H-EPOCH-'+'f'*64,'PREDECESSOR_CAPABILITY_INVALID'),
    ('predecessor_capability','WO06H-CAPABILITY-'+'f'*64,'PREDECESSOR_CAPABILITY_INVALID'),
    ('current_capability','WO06H-CAPABILITY-'+'f'*64,'SUCCESSOR_CAPABILITY_NOT_BOUND'),
    ('diagnosis','WO06H-DIAGNOSIS-'+'f'*64,'DIAGNOSIS_MISMATCH'),
    ('classification','COMPATIBLE_EVOLUTION','DIAGNOSIS_MISMATCH'),
    ('changed_capabilities',[],'DIAGNOSIS_MISMATCH'),
    ('unchanged_capabilities',[],'DIAGNOSIS_MISMATCH'),
    ('changed_semantics','UNRELATED','DIAGNOSIS_MISMATCH'),
    ('unchanged_semantics',[],'DIAGNOSIS_MISMATCH'),
    ('methodology','OTHER','POLICY_MISMATCH'),
    ('narrow_cpr','OTHER','POLICY_MISMATCH'),
    ('sponsor_reference','OTHER','DIAGNOSIS_MISMATCH'),
])
def test_bridge_cannot_substitute_any_authority(production_case, tmp_path, field, value, code):
    _, s = production_case;payload = rewrite_bridge(s, authority(s), lambda b:b.update({field:value}))
    before = epochs.inventory(tmp_path)
    with pytest.raises(ValueError, match=code):epochs.perform(s, payload)
    assert s._epochs.pointer() is None and len(s._epochs.raw.all('window')) == 1
    assert all((tmp_path/p).read_bytes()==v for p,v in before.items())


@pytest.mark.parametrize('part,value,code', [('revision','e'*40,'REVISION_MISMATCH'),('manifest','INTRADAY-RUNTIME-'+'e'*64,'CAPABILITY_NOT_BOUND'),('configuration','INTRADAY-LAUNCHER-CONFIG-'+'e'*64,'CAPABILITY_NOT_BOUND')])
def test_bridge_successor_proof_must_match_running_process(production_case, part, value, code):
    _,s=production_case;payload=rewrite_bridge(s,authority(s),lambda b:b['current_proof'].update({part:value}))
    with pytest.raises(ValueError,match=code):epochs.perform(s,payload)


@pytest.mark.parametrize('fault', ['missing_bridge','missing_diagnosis','missing_authorization','not_material','dirty','wrong_revision','invalid_manifest','wrong_predecessor'])
def test_explicit_successor_preconditions(production_case, fault):
    _,s=production_case
    mapped={'missing_diagnosis':'missing_diagnosis','not_material':'non_material','wrong_revision':'wrong_revision','wrong_predecessor':'predecessor'}
    payload=epochs.authorize(s,fault=mapped.get(fault))
    if fault=='missing_bridge':
        auth=s._epochs.load(payload['authorization_identity']);b=dict(auth['body']);b.pop('bridge');auth=document('authorization',b);s._epochs.retain(auth);payload['authorization_identity']=auth['identity']
    if fault=='missing_authorization':payload['authorization_identity']='WO06H-AUTHORIZATION-'+'f'*64
    if fault=='dirty':object.__setattr__(s._manifest.startup,'source_state','DIRTY_WORKTREE')
    if fault=='invalid_manifest':object.__setattr__(s._manifest,'manifest_identity','INTRADAY-RUNTIME-'+'f'*64)
    with pytest.raises(ValueError):epochs.perform(s,payload)
    assert s._epochs.pointer() is None


@pytest.mark.parametrize('part', ['window','acceptance','epoch'])
def test_corrupt_predecessor_rejects_before_publication(production_case, part):
    _,s=production_case;payload=authority(s);old=s._epochs.chain()[0]
    if part=='epoch':
        s._epochs.anchor_legacy(old);path=s._epochs.root/(old['identity']+'.json')
    else:path=s._epochs.raw.root/part/(old['body'][part]+'.json')
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='PREDECESSOR_EPOCH_INVALID'):epochs.perform(s,payload)
    assert s._epochs.pointer() is None


def test_two_material_bridges_do_not_create_transitive_restoration(production_case,tmp_path):
    old,s=production_case;epochs.perform(s,authority(s));historical=epochs.inventory(tmp_path)
    caps=[dict(c,implementation_digest='e'*64) if c['identity']=='WO_05B_OPERATION_ACCOUNTING' else c for c in FACTS['current_capabilities']]
    third=bound_service(tmp_path,caps,'e'*40,CURRENT+timedelta(hours=1))
    payload=epochs.authorize(third,request='THIRD');epochs.perform(third,payload)
    rows=third.status()['epochs'];assert len(rows)==3 and sum(r['current'] for r in rows)==1
    assert all((tmp_path/p).read_bytes()==v for p,v in historical.items() if not p.endswith('CURRENT.json'))
    old_runtime=epochs.restart(tmp_path,old,changed=False,at=CURRENT+timedelta(hours=2))
    assert not old_runtime.status()['enabled']
    b_runtime=epochs.restart(tmp_path,s,changed=False,at=CURRENT+timedelta(hours=2))
    assert not b_runtime.status()['enabled']
    c_runtime=epochs.restart(tmp_path,third,changed=False,at=CURRENT+timedelta(hours=2))
    assert c_runtime.status()['enabled']
    assert rows[0]['counts']['cohort_a']==rows[0]['counts']['cohort_b']==rows[0]['counts']['eod_available']==0


def test_current_calculation_change_still_rejects(production_case):
    _,s=production_case
    caps=tuple(replace(c,implementation_digest='f'*64) if c.identity=='WO_06H_LIVE_SHADOW' else c for c in s._manifest.capabilities)
    s._manifest=create_runtime_manifest(s._manifest.startup,LauncherConfiguration(8947,False),caps)
    with pytest.raises(ValueError,match='FROZEN_IMPLEMENTATION_CHANGED'):epochs.perform(s,authority(s))


def test_rehashed_bridge_tampering_breaks_current_chain(production_case,tmp_path):
    _,s=production_case;payload=authority(s);epochs.perform(s,payload)
    auth=s._epochs.load(payload['authorization_identity']);path=s._epochs.root/(auth['body']['bridge']+'.json');path.write_bytes(b'corrupt')
    new=epochs.restart(tmp_path,s,changed=False,at=CURRENT+timedelta(minutes=1))
    assert not new.status()['enabled'] and new.status()['epoch_failure']=='SHADOW_EPOCH_READ_FAILED'
