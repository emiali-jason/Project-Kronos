"""Post-expiry history is readable but never grants research acceptance."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import subprocess

import pytest

from kronos.application.intraday_shadow_history import HistoricalIntradayLiveShadowService, validate_historical_relation
from kronos.intraday.live_shadow import ShadowError, instant
from kronos.intraday.live_shadow_persistence import ShadowStore
from kronos.intraday.live_shadow_epochs import document
from tests.unit.intraday.test_live_shadow import service, seed_row, NOW
from tests.unit.intraday.test_live_shadow_epochs import inventory
from tests.unit.intraday.test_live_shadow_epoch_deterministic_digest import production_case, sources, capability, CALCULATION
from tests.unit.intraday.test_live_shadow_successor_compatibility import relation, mutate
from tests.unit.browser.test_runtime01 import server_for, complete_startup
from tests.unit.provider.test_connection_governance import governance, GENERATION


def historical(old, now):
    current = HistoricalIntradayLiveShadowService(store=old._epochs.raw, clock=lambda:now)
    current.bind_runtime(old._manifest)
    return current


@pytest.mark.parametrize('boundary', ['before', 'during', 'end', 'after'])
def test_exact_window_boundaries_and_shared_startup(tmp_path, boundary):
    old, _, _ = service(tmp_path/'shadow'); seed_row(old)
    end=instant(old._window.body['end'])
    now={'before':NOW-timedelta(microseconds=1),'during':NOW,'end':end,'after':end+timedelta(days=1)}[boundary]
    before=inventory(tmp_path/'shadow'); current=historical(old, now); state=current.status()
    server=server_for(governance(tmp_path/'governance',maintenance=GENERATION))
    complete_startup(server,current)
    assert server.connection_governance.startup_state == ('BLOCKED' if boundary=='before' else 'READY')
    assert state['enabled'] is (boundary=='during')
    if boundary in ('end','after'):
        assert state['acceptance_disposition']=='HISTORICAL_ACCEPTANCE_EXPIRED'
        assert state['runtime_accepted'] is False and current._accepted is None
        assert state['historical_evidence']=='READABLE'
        try:
            acceptance=current.accept_runtime(expected_revision=current._manifest.startup.source_revision,request_identity='NO_NEW_ACCEPTANCE')
            assert not acceptance['runtime_accepted']
        except ShadowError:
            pass
        assert current.monthly_ledger(NOW.strftime('%Y-%m'))['raw_observations']==1
        current.begin_operation('NO_BACKFILL', NOW)
        current.capture_published(None,None,None,facts=None,source=None,operation='NO_BACKFILL',operation_start=NOW,newly_published=True)
        with pytest.raises(ShadowError,match='RUNTIME_NOT_ACCEPTED'):
            current.complete_eod('ANY',schedule=None,candle=None)
    assert inventory(tmp_path/'shadow')==before


def test_already_running_collector_cannot_complete_eod_after_expiry(tmp_path):
    old, _, _=service(tmp_path)
    current=historical(old,NOW)
    assert current._accepted is not None
    current.clock=lambda:instant(old._window.body['end'])
    before=inventory(tmp_path)
    assert current.status()['acceptance_disposition']=='HISTORICAL_ACCEPTANCE_EXPIRED'
    with pytest.raises(ShadowError,match='RUNTIME_NOT_ACCEPTED'):
        current.complete_eod('ANY',schedule=None,candle=None)
    assert inventory(tmp_path)==before


def test_production_shaped_direct_relation_history(production_case,tmp_path):
    old=production_case; old._epochs.retain(relation(old))
    before=inventory(old._epochs.raw.root)
    current=historical(old,instant(old._window.body['end'])+timedelta(hours=1))
    state=current.status()
    assert state['acceptance_disposition']=='HISTORICAL_ACCEPTANCE_EXPIRED'
    assert state['all_epoch_counts']==dict(cohort_a=34,cohort_b=66,eod_available=0)
    assert inventory(old._epochs.raw.root)==before


@pytest.mark.parametrize('fault',['missing','pending','configuration','target','window','delta','duplicate','corrupt'])
def test_expired_relation_errors_fail_closed(production_case,tmp_path,fault):
    old=production_case; record=relation(old)
    if fault=='pending':record=mutate(record,lambda b:b['owner_approvals'][0].update(disposition='PENDING'))
    elif fault=='configuration':record=mutate(record,lambda b:b.update(configuration='INTRADAY-LAUNCHER-CONFIG-'+'0'*64))
    elif fault=='target':record=mutate(record,lambda b:b['target_capabilities'][0].update(implementation_digest='0'*64))
    elif fault=='window':record=mutate(record,lambda b:b.update(end='2099-01-01T00:00:00+00:00'))
    elif fault=='delta':record=mutate(record,lambda b:b.update(reviewed_changes=b['reviewed_changes'][:-1]))
    if fault!='missing':old._epochs.retain(record)
    if fault=='duplicate':old._epochs.retain(mutate(record,lambda b:b['semantic_assessment'].update(identity='OTHER')))
    if fault=='corrupt':(old._epochs.root/(record['identity']+'.json')).write_text('{}')
    current=historical(old,instant(old._window.body['end'])+timedelta(hours=1))
    before=inventory(old._epochs.raw.root)
    server=server_for(governance(tmp_path/'governance',maintenance=GENERATION));complete_startup(server,current)
    assert server.connection_governance.startup_state=='BLOCKED'
    assert not current.status()['runtime_accepted'] and current.status()['failure']
    assert inventory(old._epochs.raw.root)==before


@pytest.mark.parametrize('kind',['window','acceptance','observation','batch'])
@pytest.mark.parametrize('fault',['corrupt','missing'])
def test_expired_required_evidence_errors_fail_closed(tmp_path,kind,fault):
    old,_,_=service(tmp_path/'shadow');seed_row(old)
    end=instant(old._window.body['end'])
    path=next((old._epochs.raw.root/kind).glob('*.json'))
    if fault=='missing':path.unlink()
    else:path.write_text('{}')
    current=historical(old,end)
    server=server_for(governance(tmp_path/'governance',maintenance=GENERATION));complete_startup(server,current)
    # Missing observation is existing explicit incomplete accounting, not corrupt
    # authority; existing missing-row behavior remains unchanged.
    if kind=='observation' and fault=='missing':
        assert current.status()['counts']['missing_rows']==1
    else:assert server.connection_governance.startup_state=='BLOCKED'


def test_accepted_capability_ast_exactly_preserved():
    root=Path(__file__).resolve().parents[3]
    current=sources()
    baseline={name:subprocess.check_output(['git','show','37c9dc94ccbbfd35b78c3dfa7c0369a7f41b0df3:src/'+name.replace('.','/')+'.py'],cwd=root,text=True) for name in current}
    assert capability(CALCULATION,sources=current)==capability(CALCULATION,sources=baseline)
