"""Read-only WO-06H acceptance restoration under the mandatory isolation runner."""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from types import CodeType
from unittest.mock import Mock
import json
import marshal
import subprocess

import pytest

from kronos.application.intraday_live_shadow import IntradayLiveShadowService, REQUIRED
from kronos.intraday.live_shadow import artifact, canonical, identity, key, instant, COHORT_A, COHORT_B
from kronos.intraday.live_shadow_persistence import ShadowStore
from kronos.intraday.runtime_identity import create_runtime_manifest, LauncherConfiguration, LoadedCapability
from tests.unit.intraday.test_live_shadow import service, seed_row, NOW
from tests.unit.intraday.test_runtime_identity import _seed


def files(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}


def restart(root, old, now=NOW + timedelta(hours=1), **startup):
    new = IntradayLiveShadowService(store=ShadowStore(root), clock=lambda: now)
    manifest = create_runtime_manifest(_seed(startup_boundary_at=now, process_nonce='2'*32,
        source_revision='b'*40, **startup), LauncherConfiguration(8947, False), old._manifest.capabilities)
    new.bind_runtime(manifest)
    return new


def rewrite(root, kind, change):
    path = next((root/'live-shadow-v1'/kind).glob('*.json'))
    value = json.loads(path.read_bytes())
    change(value)
    value['integrity'] = identity('WO06H-INTEGRITY-', {k:v for k,v in value.items() if k != 'integrity'})
    target = path.with_name(value['key'] + '.json')
    if target != path:
        path.unlink()
    target.write_bytes(canonical(value))


def assert_closed(new, before, root):
    state = new.status()
    assert state['enabled'] is False and state['runtime_accepted'] is False
    assert state['acceptance_identity'] is None and state['acceptance_disposition'] == 'NOT_ACCEPTED'
    assert state['failure'] is not None
    assert files(root) == before


def test_restores_existing_identity_without_acceptance_creation_or_write(tmp_path, monkeypatch):
    old, _, _ = service(tmp_path)
    original = old.store.all('acceptance')[0]
    assert old.status()['acceptance_disposition'] == 'NEW_ACCEPTANCE_GRANTED'
    assert old.status()['acceptance_identity'] == original.key
    before = files(tmp_path)
    monkeypatch.setattr(IntradayLiveShadowService, 'accept_runtime', Mock(side_effect=AssertionError('NEW_ACCEPTANCE_FORBIDDEN')))
    monkeypatch.setattr(ShadowStore, 'retain', Mock(side_effect=AssertionError('RESTORATION_WRITE_FORBIDDEN')))
    new = restart(tmp_path, old)
    assert new._manifest.manifest_identity != old._manifest.manifest_identity
    for _ in range(3):
        new.bind_runtime(new._manifest)
        state = new.status()
        assert state['runtime_accepted'] and state['enabled']
        assert state['acceptance_disposition'] == 'EXISTING_ACCEPTANCE_RESTORED'
        assert state['acceptance_identity'] == original.key
        assert state['window'] == old.status()['window']
        assert state['counts'] == old.status()['counts']
        assert state['failure'] is None
        assert files(tmp_path) == before
    IntradayLiveShadowService.accept_runtime.assert_not_called()
    ShadowStore.retain.assert_not_called()


@pytest.mark.parametrize('missing', ['window', 'acceptance'])
def test_missing_authority_fails_closed(tmp_path, missing):
    old, _, _ = service(tmp_path)
    next((tmp_path/'live-shadow-v1'/missing).glob('*.json')).unlink()
    before = files(tmp_path)
    assert_closed(restart(tmp_path, old), before, tmp_path)


@pytest.mark.parametrize('kind', ['window', 'acceptance'])
@pytest.mark.parametrize('fault', ['tamper', 'malformed', 'schema', 'authority', 'foreign_key', 'symlink', 'unknown_field'])
def test_invalid_artifact_rejected(tmp_path, kind, fault):
    old, _, _ = service(tmp_path)
    path = next((tmp_path/'live-shadow-v1'/kind).glob('*.json'))
    if fault == 'malformed':
        path.write_bytes(b'{')
    elif fault == 'symlink':
        target = tmp_path/'isolated-copy'; target.write_bytes(path.read_bytes()); path.unlink(); path.symlink_to(target)
    elif fault == 'tamper':
        value = json.loads(path.read_bytes()); value['body']['request'] = 'TAMPERED'; path.write_bytes(canonical(value))
    else:
        def mutate(v):
            if fault == 'schema': v['schema'] = 'KRONOS-INTRADAY-LIVE-SHADOW/99.0.0'
            elif fault == 'authority': v['body']['authority'] = 'TRADING'
            elif fault == 'foreign_key': v['key'] = key(kind, 'FOREIGN')
            else: v['body']['unknown'] = 'REJECT'
        rewrite(tmp_path, kind, mutate)
    before = files(tmp_path)
    assert_closed(restart(tmp_path, old), before, tmp_path)


@pytest.mark.parametrize('kind', ['window', 'acceptance'])
def test_duplicate_conflicting_authority_rejected(tmp_path, kind):
    old, _, _ = service(tmp_path)
    original = old.store.all(kind)[0]
    # Individually well-formed artifact but a second authority is ambiguous.
    old.store.retain(artifact(kind, key(kind, 'OTHER'), original.body))
    before = files(tmp_path)
    assert_closed(restart(tmp_path, old), before, tmp_path)


@pytest.mark.parametrize('fault', ['window_binding', 'runtime_binding', 'configuration', 'capability',
    'duplicate_capability', 'missing_capability', 'source_state', 'source_revision', 'pid',
    'startup_after_acceptance', 'invalid_timestamp', 'accepted_before_window', 'accepted_after_window',
    'proof_extra', 'request'])
def test_rehashed_acceptance_semantic_mismatch_rejected(tmp_path, fault):
    old, _, _ = service(tmp_path)
    def mutate(v):
        b = v['body']; proof = b['runtime_proof']
        if fault == 'window_binding': b['window'] = key('window', 'FOREIGN')
        elif fault == 'runtime_binding': b['runtime'] = 'INTRADAY-RUNTIME-' + 'e'*64
        elif fault == 'configuration': proof['configuration'] = LauncherConfiguration(9999, False).identity
        elif fault == 'capability': proof['capabilities'][0]['implementation_digest'] = 'e'*64
        elif fault == 'duplicate_capability': proof['capabilities'].append(proof['capabilities'][0])
        elif fault == 'missing_capability': proof['capabilities'].pop()
        elif fault == 'source_state': proof['source_state'] = 'DIRTY_WORKTREE'
        elif fault == 'source_revision': proof['revision'] = 'UNAVAILABLE'
        elif fault == 'pid': proof['pid'] = True
        elif fault == 'startup_after_acceptance': proof['startup'] = (NOW + timedelta(hours=1)).isoformat()
        elif fault == 'invalid_timestamp': b['accepted_at'] = 'invalid'
        elif fault == 'accepted_before_window': b['accepted_at'] = (NOW - timedelta(seconds=1)).isoformat()
        elif fault == 'accepted_after_window': b['accepted_at'] = old._window.body['end']
        elif fault == 'proof_extra': proof['unknown'] = 'NO'
        elif fault == 'request': b['request'] = '../unsafe'
    rewrite(tmp_path, 'acceptance', mutate)
    before = files(tmp_path)
    assert_closed(restart(tmp_path, old), before, tmp_path)


@pytest.mark.parametrize('fault', ['end', 'start_utc', 'methodology', 'definitions', 'research_inputs', 'runtime_binding'])
def test_window_contract_not_replaced(tmp_path, fault):
    old, _, _ = service(tmp_path)
    def mutate(v):
        b=v['body']
        if fault == 'end': b['end'] = (NOW+timedelta(days=40)).isoformat()
        elif fault == 'start_utc': b['start_utc'] = (NOW+timedelta(minutes=1)).isoformat()
        elif fault == 'methodology': b['methodology'] = '2.3.0'
        elif fault == 'definitions': b['definitions']['selection'] = 'OTHER'
        elif fault == 'research_inputs': b['research_inputs']['WO06E'] = 'OTHER'
        else: b['runtime'] = 'INTRADAY-RUNTIME-'+'e'*64
    rewrite(tmp_path, 'window', mutate)
    before=files(tmp_path)
    assert_closed(restart(tmp_path, old), before, tmp_path)


@pytest.mark.parametrize('point,active', [('before',False), ('start',True), ('inside',True), ('end',False), ('after',False)])
def test_half_open_window_does_not_extend_or_backdate(tmp_path, point, active):
    old, _, _=service(tmp_path)
    times={'before':NOW-timedelta(seconds=1), 'start':NOW, 'inside':NOW+timedelta(days=1),
        'end':instant(old._window.body['end']), 'after':instant(old._window.body['end'])+timedelta(seconds=1)}
    before=files(tmp_path);new=restart(tmp_path,old,now=times[point])
    assert new.status()['enabled'] is active
    assert new.status()['runtime_accepted'] is active
    assert new.status()['window']==old.status()['window']
    assert files(tmp_path)==before


@pytest.mark.parametrize('fault',['dirty','unavailable','foreign_process','configuration','capability','missing_capability','future_start','tampered_manifest'])
def test_current_process_authority_must_be_compatible(tmp_path, fault):
    old, _, m=service(tmp_path)
    now=NOW+timedelta(hours=1)
    changes={'startup_boundary_at':now,'process_nonce':'2'*32}
    if fault=='dirty': changes['source_state']='DIRTY_WORKTREE'
    if fault=='unavailable': changes.update(source_revision=None,source_state='REVISION_UNAVAILABLE',branch=None)
    if fault=='foreign_process': changes['process_id']=999999
    if fault=='future_start': changes['startup_boundary_at']=now+timedelta(seconds=1)
    config=LauncherConfiguration(9999 if fault=='configuration' else 8947,False)
    caps=m.capabilities
    if fault=='capability':caps=(LoadedCapability(caps[0].identity,'1.0.0','e'*64),*caps[1:])
    if fault=='missing_capability':caps=caps[:-1]
    manifest=create_runtime_manifest(_seed(**changes),config,caps)
    if fault=='tampered_manifest':object.__setattr__(manifest,'manifest_identity','INTRADAY-RUNTIME-'+'e'*64)
    before=files(tmp_path);new=IntradayLiveShadowService(store=ShadowStore(tmp_path),clock=lambda:now)
    if fault=='tampered_manifest':
        with pytest.raises(ValueError):new.bind_runtime(manifest)
        assert not new.status()['enabled']
        assert files(tmp_path)==before
    else:
        new.bind_runtime(manifest);assert_closed(new,before,tmp_path)


@pytest.mark.parametrize('cohort',[COHORT_A,COHORT_B])
def test_counts_and_missing_prices_preserved_without_downtime_backfill(tmp_path,cohort):
    old, _, _=service(tmp_path);seed_row(old,cohort=cohort,price=None)
    old.begin_operation('UNFINISHED_BEFORE_DOWNTIME',NOW)
    old._reconcile();before=files(tmp_path)
    new=restart(tmp_path,old,now=NOW+timedelta(days=2))
    assert new.status()['enabled']
    assert new.status()['counts']==old.status()['counts']
    assert new.status()['counts']['incomplete_operations']==1
    assert new.status()['counts']['assessment_available']==0
    assert len(new.store.all('observation'))==1 and new.store.all('outcome')==()
    assert files(tmp_path)==before


def test_frozen_research_function_code_unchanged():
    """The existing accepted capability digest includes marshal line metadata."""
    path=Path(__file__).resolve().parents[3]/'src/kronos/application/intraday_live_shadow.py'
    original=subprocess.check_output(['git','show','738f532adc74b133ad983220c880c9bee1a89b3f:src/kronos/application/intraday_live_shadow.py'],cwd=path.parents[3])
    def functions(source):
        module=compile(source,str(path),'exec')
        cls=next(c for c in module.co_consts if isinstance(c,CodeType) and c.co_name=='IntradayLiveShadowService')
        return {c.co_name:c for c in cls.co_consts if isinstance(c,CodeType)}
    before,after=functions(original),functions(path.read_bytes())
    for name in ['capture_published','_capture','complete_eod','accept_runtime']:
        assert before[name]==after[name],name
        assert before[name].co_firstlineno==after[name].co_firstlineno
        assert before[name].co_linetable==after[name].co_linetable
        assert before[name].co_filename==after[name].co_filename
        assert marshal.dumps(before[name])==marshal.dumps(after[name])


def test_real_composition_restores_without_any_operational_call(tmp_path, monkeypatch):
    from kronos.application.intraday_runtime import create_intraday_runtime
    from kronos.browser.intraday_probables_v2_control import IntradayProbablesV2OperationalControl
    from tests.unit.application.test_intraday_discovery_operation import _configured_shared
    from kronos.intraday.probables_v2 import PROBABLES_V2_CORRECTION_METHODOLOGY_VERSION
    def compose(now, nonce):
        shared, provider, factories, requests = _configured_shared()
        c=create_intraday_runtime(shared,evidence_root=tmp_path,clock=lambda:now)
        control=IntradayProbablesV2OperationalControl(c.discovery_v2_operation,c.probables_v2_application,
            c.refresh_v2_provenance_store,clock=lambda:now,startup_evidence=_seed(startup_boundary_at=now,process_nonce=nonce),
            launcher_configuration=LauncherConfiguration(8947,False))
        return c,control,shared,factories,requests
    c,control,shared,factories,requests=compose(NOW,'1'*32)
    old=c.discovery_v2_operation.live_shadow
    old.accept_runtime(expected_revision='a'*40,request_identity='ISOLATED_ORIGINAL_ACCEPTANCE')
    before=files(tmp_path)
    monkeypatch.setattr(ShadowStore,'retain',Mock(side_effect=AssertionError('NO_STARTUP_WRITES')))
    new,ctrl,shared2,factories2,requests2=compose(NOW+timedelta(hours=1),'2'*32)
    state=ctrl.status_document()
    assert state['live_shadow']['enabled'] and state['live_shadow']['runtime_accepted']
    assert state['context_state']=='ABSENT'
    assert state['methodology_version']==PROBABLES_V2_CORRECTION_METHODOLOGY_VERSION=='2.2.0'
    assert factories==factories2==[] and requests==requests2==[0]
    from kronos.provider.runtime import ProviderRuntimeAccessError
    for provider_runtime in (shared, shared2):
        with pytest.raises(ProviderRuntimeAccessError, match='CONTEXT_UNAVAILABLE'):
            _ = provider_runtime.authenticated_context_identity
    assert new.probables_v2_application.snapshot().run is None
    assert state['live_shadow']['counts']['observed_operations']==0
    assert state['live_shadow']['window']==old.status()['window']
    assert files(tmp_path)==before
    ShadowStore.retain.assert_not_called()


def test_existing_eod_counts_and_bytes_restore_unchanged(tmp_path):
    old, clock, _ = service(tmp_path)
    row, w = seed_row(old, price='100')
    clock[0] = w.boundary + timedelta(seconds=1)
    old.complete_eod(row.key, schedule=w.schedule, candle=w.candles[-1])
    old._reconcile()
    before = files(tmp_path)
    new = restart(tmp_path, old, now=clock[0] + timedelta(seconds=1))
    assert new.status()['enabled']
    assert new.status()['counts'] == old.status()['counts']
    assert new.status()['counts']['eod_available'] == 1
    assert files(tmp_path) == before


def test_window_replacement_between_construction_and_binding_rejects(tmp_path):
    old, _, m = service(tmp_path)
    new = IntradayLiveShadowService(store=ShadowStore(tmp_path), clock=lambda:NOW)
    rewrite(tmp_path, 'window', lambda v:v['body'].update(request='CHANGED_AFTER_READ'))
    before = files(tmp_path)
    new.bind_runtime(m)
    assert_closed(new, before, tmp_path)


def test_unbound_process_never_restores_authority(tmp_path):
    old, _, _ = service(tmp_path)
    before = files(tmp_path)
    new = IntradayLiveShadowService(store=ShadowStore(tmp_path), clock=lambda:NOW)
    new.bind_runtime(None)
    assert not new.status()['enabled'] and not new.status()['runtime_accepted']
    assert files(tmp_path) == before
