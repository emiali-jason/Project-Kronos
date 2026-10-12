"""Sponsor IWO-INT: bounded read projections and original authority protection."""
from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path

import pytest

from kronos.browser.intraday_wo08 import render_machine_review
from kronos.browser.views import render_dashboard, _dashboard_swing_card
from kronos.browser.dashboard import project_sponsor_dashboard
from kronos.application.notifications import NotificationWorkspaceSnapshot
from kronos.intraday.sponsor_presentation import security_name, waiting_for
from kronos.intraday.wo12_research_contract import opportunity_id, opportunity_origin
from tests.unit.browser.test_intraday_iwo_ux import presentation_fixture, _snapshot
from tests.unit.application.test_intraday_experimental_watch import setup_watch, canonical_adapter
from tests.unit.application.test_shared_monitoring import Capability, Consumer
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.provider.contracts.monitoring import MonitoringConnectionState


def test_exact_live_observer_required_and_read_is_inert(tmp_path):
    watch,r,req,bindings,clock,current,instrument,expiry = setup_watch(tmp_path)
    adapter = canonical_adapter(watch,clock)
    adapter._session_instrument = lambda _: (expiry,instrument)
    hub = SharedSwingMonitoringHub(); capability = Capability()
    adapter.hub = hub
    before = {p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    absent = adapter.monitoring_projection(r.readiness_identity)
    assert absent['state'] == 'UNAVAILABLE'
    assert absent['reason_code'] == 'SHARED_MONITORING_EXISTING_SUBSCRIPTION_REQUIRED'
    assert hub.status_document()['owner_count'] == hub.status_document()['subscription_count'] == 0
    owner = hub.open(capability, Consumer()); owner.subscribe((instrument,)); owner.connect()
    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    # Connectivity alone is still insufficient.
    assert adapter.monitoring_projection(r.readiness_identity)['state'] == 'UNAVAILABLE'
    observer = hub.observe_existing(capability, Consumer(), (instrument,))
    adapter.registrations[bindings[0]['identity']] = observer
    active = adapter.monitoring_projection(r.readiness_identity)
    assert active['state'] == 'ACTIVE' and active['criterion'] == 'I2'
    assert active['since'] == bindings[0]['watch_started_at']
    clock[0] = expiry
    assert adapter.monitoring_projection(r.readiness_identity)['state'] == 'INACTIVE'
    assert before == {p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    observer.disconnect(); owner.disconnect(); adapter.shutdown()


def test_readable_id_prospective_and_exact_historical_compatibility():
    from datetime import datetime, timezone
    at = datetime(2026,10,12,7,0,43,tzinfo=timezone.utc)
    args = dict(canonical_subject_identity='NSE-EQ-BAJAJ-AUTO', market_family='NSE', session_identity='SESSION',
                origin_at=at, probable_result_identity='P', probables_run_identity='R')
    legacy = opportunity_origin(**args, legacy_symbol=True)
    future = opportunity_origin(**args)
    assert legacy.data['opportunity_id'] == 'AUTO-20261012-123043'
    assert future.data['opportunity_id'] == 'BAJAJ_AUTO-20261012-123043'
    assert legacy.data['opportunity_identity'] != future.data['opportunity_identity']
    legacy.__post_init__()
    assert security_name('NSE-EQ-BAJAJ-AUTO') == 'BAJAJ AUTO'
    assert security_name('MCX-SUBJECT-GOLDM') == 'GOLDM'


def test_mixed_98_population_has_considered_primary_and_accountable_secondary(tmp_path):
    status, readiness = presentation_fixture(tmp_path)
    rows = list(status['assessments'])
    for i in range(95):
        rows.append(dict(rows[0], subject='NSE-EQ-EXCLUDED'+str(i), identity='EXCLUDED'+str(i),
            probable_result_identity='EXCLUDED'+str(i), probables_state='UNAVAILABLE' if i == 94 else 'NOT_ADMITTED',
            disposition='HARD_GATE', failure_reason='MANDATORY_EVIDENCE_UNAVAILABLE' if i == 94 else 'PROBABLES_NOT_ADMITTED'))
    status = dict(status, assessments=tuple(rows))
    for detail in readiness['analysis_details'].values():
        detail['F. EXPERIMENTAL OBSERVATION']['monitoring'] = dict(state='UNAVAILABLE',
            reason='Watch retained; no existing lawful market subscription is available.')
    html = render_machine_review(_snapshot(), status, readiness)
    assert 'Analysed</span><strong>98' in html
    assert 'Considered</span><strong>3' in html
    assert 'Not Admitted</span><strong>94' in html
    assert 'Unavailable</span><strong>1' in html
    assert 'Follow-through' in html and 'Two consecutive completed 5-minute candles' in html
    assert 'no existing lawful market subscription' in html
    secondary = html.index('Not Admitted / Unavailable / Retained')
    assert html.index('EXCLUDED94') > secondary
    assert 'Technical details' in html and 'I2 — Follow-through' in html
    assert html.count('id="review-candidate-') == 98
    if os.environ.get('IWO_INT_REHEARSAL_OUTPUT'):
        out=Path(os.environ['IWO_INT_REHEARSAL_OUTPUT']);out.mkdir(parents=True,exist_ok=True)
        (out/'machine-review-98.html').write_text(html)


def test_dashboard_names_do_not_change_swing(tmp_path):
    status, readiness = presentation_fixture(tmp_path)
    base = project_sponsor_dashboard(_snapshot(),None,(),NotificationWorkspaceSnapshot(()))
    summary = replace(readiness['operational_summary'], opportunities=(dict(security='BAJAJ AUTO', subject='NSE-EQ-BAJAJ-AUTO',
        direction='SHORT', status='Ready', waiting='Follow-through', contract=None,
        monitoring=dict(state='ACTIVE',reason='Observer attached to an existing lawful subscription.')),))
    result = replace(base,intraday=summary)
    html = render_dashboard(_snapshot(),result)
    assert 'BAJAJ AUTO · SHORT' in html and 'Monitoring: ACTIVE' in html
    assert _dashboard_swing_card(base) == _dashboard_swing_card(result)


@pytest.mark.parametrize('reason', ['ELIGIBILITY_AUTHORITY_UNAVAILABLE', 'SOURCE_LINEAGE_NOT_ESTABLISHED', 'FIRST_FIVE_TIME_NOT_ESTABLISHED'])
def test_missing_authority_is_unavailable_not_inactive(tmp_path,reason):
    from kronos.intraday.evidence_currentness import NewWorkNotEligible, NewWorkAction, EligibilityReason
    watch,r,req,bindings,clock,current,instrument,expiry = setup_watch(tmp_path)
    adapter = canonical_adapter(watch,clock)
    adapter._session_instrument = lambda _: (expiry,instrument)
    def deny(*args):
        raise NewWorkNotEligible(EligibilityReason(reason),
                                action=NewWorkAction.READINESS_HANDOFF)
    adapter.boundary._session = deny
    state = adapter.monitoring_projection(r.readiness_identity)
    assert state['state'] == 'UNAVAILABLE'
    assert state['reason_code'] == reason


def test_historical_bajaj_origin_reuse_and_source_validation(tmp_path):
    from types import SimpleNamespace
    from tests.unit.intraday.test_wo08_experimental import experimental_fixture
    from tests.unit.application.test_intraday_research import _application
    from tests.unit.intraday.test_wo08_wo09_integration import graph
    from kronos.intraday.wo12_research_store import ResearchStore
    _,_,_,run,_,assessment = experimental_fixture(subject='NSE-EQ-BAJAJ-AUTO')
    item = next(r for r in run.results if r.canonical_subject_identity=='NSE-EQ-BAJAJ-AUTO')
    args=dict(canonical_subject_identity=item.canonical_subject_identity, market_family='NSE',
              session_identity=item.market_session_identity, origin_at=item.analysis_boundary,
              probable_result_identity=item.result_identity, probables_run_identity=run.run_identity)
    old = opportunity_origin(**args, legacy_symbol=True)
    app,_ = _application(tmp_path/'research')
    app.store.retain(old)
    before = {p:p.read_bytes() for p in app.store.root.rglob('*') if p.is_file()}
    retained=app._ensure_origins(source_events=((item.analysis_boundary,item.result_identity,run.run_identity,item),), tracks=())
    assert retained == (old,)
    _,_,boundary,_ = graph(tmp_path/'boundary')
    boundary.research=app.store
    boundary.probables=SimpleNamespace(load_result=lambda _:item, load_run=lambda _:run)
    assert boundary.experimental_origin(assessment)==old
    assert before == {p:p.read_bytes() for p in app.store.root.rglob('*') if p.is_file()}


def test_readable_ids_do_not_collide_in_the_governed_98_catalogue():
    from datetime import datetime, timezone
    catalogue=json.loads((Path(__file__).resolve().parents[3]/'data/intraday/KRONOS-INTRADAY-CANONICAL-RUNTIME-RECONCILIATION-V1/1.0.0.json').read_text())
    at=datetime(2026,10,12,7,0,43,tzinfo=timezone.utc)
    ids=[opportunity_id(m['canonical_identity'],at) for m in catalogue['members']]
    assert len(ids)==len(set(ids))==98


def test_notification_monitoring_change_updates_poll_revision_without_new_event(tmp_path):
    from types import SimpleNamespace
    from tests.unit.browser.test_browser_swing_notifications_correction import browser, inventory
    from tests.unit.browser.test_browser_server import _request
    from tests.unit.intraday.test_wo13_notifications import details
    with browser(tmp_path) as (server, _, centre):
        record=centre.accept_intraday(details(criteria='I1:SATISFIED,I2:OUTSTANDING,I3:SATISFIED,I4:SATISFIED,I5:SATISFIED'))
        state=['UNAVAILABLE · No existing lawful subscription.']
        server.intraday_notifications=SimpleNamespace(indicator=lambda _:state[0],close=lambda **_:None)
        before=inventory(tmp_path)
        first=json.loads(_request(server,'GET','/notifications/status?product=INTRADAY')[2])
        state[0]='ACTIVE · Observer attached to an existing lawful subscription.'
        second=json.loads(_request(server,'GET','/notifications/status?product=INTRADAY')[2])
        html=_request(server,'GET','/notifications/intraday')[2]
        assert first['revision'] != second['revision'] and first['count']==second['count']==1
        assert second['revision'] in html and 'MONITORING · ACTIVE' in html
        assert 'Waiting for: Follow-through' in html
        assert centre.record(record.notification_identity)==record
        assert inventory(tmp_path)==before
        assert server.swing_monitoring_hub.status_document()['subscription_count']==0


@pytest.mark.parametrize('condition,expected,code', [
    ('missing_pointer','UNAVAILABLE','READINESS_POINTER_UNAVAILABLE'),
    ('missing_watch','UNAVAILABLE','WATCH_RECORD_UNAVAILABLE'),
    ('noncurrent','INACTIVE','READINESS_NOT_CURRENT'),
    ('inactive_watch','INACTIVE','WATCH_NOT_ACTIVE'),
    ('pointer_subject','UNAVAILABLE','READINESS_POINTER_BINDING_INVALID'),
    ('pointer_integrity','UNAVAILABLE','READINESS_POINTER_BINDING_INVALID'),
])
def test_retained_missing_and_contradictory_authority_is_not_inactivity(tmp_path,condition,expected,code):
    from dataclasses import asdict
    from kronos.intraday.wo09_readiness import CurrentnessState, artifact_bytes, _identity
    from kronos.intraday.wo09_persistence import CurrentPointer
    from kronos.intraday.wo09_watch import WatchState, transition_watch
    watch,r,req,bindings,clock,current,instrument,expiry=setup_watch(tmp_path)
    adapter=canonical_adapter(watch,clock)
    adapter._session_instrument=lambda _: (expiry,instrument)
    pointer_path=next(watch.wo09.store.current.glob('*.json'))
    if condition=='missing_pointer': pointer_path.unlink()
    elif condition=='missing_watch':
        for path in watch.wo09.store.watches.glob('*.json'):path.unlink()
    elif condition=='noncurrent':
        watch.wo09.store.mark_currentness(r.canonical_subject_identity,CurrentnessState.REASSESSMENT_DUE,
            updated_at=clock[0]+timedelta(seconds=1),expected=watch.wo09.store.expectation(r.canonical_subject_identity))
    elif condition=='inactive_watch':
        original,=watch.wo09.store.load_watches()
        watch.wo09.store.retain_watch(transition_watch(original,WatchState.INACTIVE,
            at=clock[0]+timedelta(seconds=1)))
    else:
        pointer=watch.wo09.store.load_pointer(r.canonical_subject_identity)
        values=asdict(pointer);values.pop('integrity_identity')
        values['canonical_subject_identity' if condition=='pointer_subject' else 'readiness_integrity']='SELF_VALID_BUT_CONTRADICTORY'
        changed=CurrentPointer(**values,integrity_identity=_identity('INTEGRITY-INTRADAY-WO09-POINTER-',values))
        changed.__post_init__()
        pointer_path.write_bytes(artifact_bytes(changed))
    before={p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    state=adapter.monitoring_projection(r.readiness_identity)
    assert (state['state'],state['reason_code'])==(expected,code)
    assert before=={p:p.read_bytes() for p in tmp_path.rglob('*.json')}


@pytest.mark.parametrize('condition',['released','expired','invalid_clock','revoked'])
def test_real_lease_inert_evidence_fails_closed_without_provider_sync(tmp_path,monkeypatch,condition):
    from tests.unit.provider.test_shared_provider_runtime import _shared,_authenticate,_lease,VALID_THROUGH
    from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
    shared,backend,_=_shared();_authenticate(shared)
    lease=_lease(shared,'INTRADAY')
    assert lease.read_only_active
    if condition=='released': lease.release()
    elif condition=='revoked': shared.end_kronos_session()
    elif condition=='expired':
        monkeypatch.setattr(shared,'_SharedAuthenticatedProviderRuntime__clock',lambda:VALID_THROUGH)
    else:
        monkeypatch.setattr(shared,'_SharedAuthenticatedProviderRuntime__clock',lambda:VALID_THROUGH.replace(tzinfo=None))
    def forbidden(*args,**kwargs):pytest.fail('inert lease query synchronized/revoked or called Provider')
    monkeypatch.setattr(backend,'session_status',forbidden)
    monkeypatch.setattr(SharedAuthenticatedProviderRuntime,'_SharedAuthenticatedProviderRuntime__synchronize_locked',forbidden)
    monkeypatch.setattr(SharedAuthenticatedProviderRuntime,'_SharedAuthenticatedProviderRuntime__revoke_locked',forbidden)
    before=shared.read_only_status()
    assert not lease.read_only_active
    assert not lease.read_only_active
    assert shared.read_only_status()==before


def test_actual_readiness_successor_is_inactive(tmp_path):
    from kronos.intraday.wo09_experimental import assessment_from,origin_from
    from tests.unit.intraday.test_wo09_experimental import publish
    watch,r,req,bindings,clock,current,instrument,expiry=setup_watch(tmp_path)
    adapter=canonical_adapter(watch,clock)
    successor,_=publish(watch.wo09.store,assessment_from(r.assessment_document),
        origin_from(r.origin_document),r.created_at+timedelta(seconds=1))
    assert successor.readiness_identity!=r.readiness_identity
    state=adapter.monitoring_projection(r.readiness_identity)
    assert (state['state'],state['reason_code'])==('INACTIVE','READINESS_NOT_CURRENT')


def test_inert_hub_evidence_is_fenced_by_subscription_loss_and_transport_generation():
    from tests.unit.application.test_shared_monitoring import ONE
    hub=SharedSwingMonitoringHub();capability=Capability()
    owner=hub.open(capability,Consumer());owner.subscribe((ONE,));owner.connect()
    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    observer=hub.observe_existing(capability,Consumer(),(ONE,))
    assert owner.read_only_active and observer.read_only_active
    hub.on_connection_state(MonitoringConnectionState.DISCONNECTED)
    hub.on_connection_state(MonitoringConnectionState.CONNECTED)
    assert owner.read_only_active and not observer.read_only_active
    fresh=hub.observe_existing(capability,Consumer(),(ONE,))
    assert fresh.read_only_active
    owner.disconnect()
    assert not owner.read_only_active and not fresh.read_only_active
    observer.disconnect();fresh.disconnect()


@pytest.mark.parametrize('fault',['none','missing_original','wrong_original','missing_run_member','missing_claim'])
def test_retained_original_first_five_provenance_is_preserved(tmp_path,monkeypatch,fault):
    from datetime import datetime
    from types import SimpleNamespace
    from kronos.application.intraday_evidence_currentness import IntradayPublicationBoundary
    from kronos.intraday.wo09_persistence import Wo09Store
    from tests.unit.intraday.test_wo08_experimental import experimental_fixture
    from tests.unit.intraday.test_wo09_experimental import publish,origin_for
    import kronos.intraday.native_pullback_decision as native_module
    import kronos.application.intraday_evidence_currentness as boundary_module
    *_,original=experimental_fixture()
    _,_,_,run,native,current=experimental_fixture(five_rows=[(108,102,106)]*25+[(115,110,114),(117,110,114)])
    origin=origin_for(original)
    at=datetime.fromisoformat(original.data['created_at'])+timedelta(seconds=1)
    store=Wo09Store(tmp_path/'wo09')
    publish(store,original,origin,at)
    readiness,_=publish(store,current,origin,at+timedelta(seconds=1))
    assert readiness.first_five_document is not None and readiness.satisfied_count==4
    d=current.data;result=run.results[0]
    def load(identity):
        if identity==current.identity:return current
        assert identity==original.identity
        if fault=='missing_original':raise FileNotFoundError('original assessment absent')
        return current if fault=='wrong_original' else original
    owner=SimpleNamespace(
        probables=SimpleNamespace(load_current=lambda:SimpleNamespace(run_identity=run.run_identity),
            load_current_run=lambda:run,load_result=lambda _:result),
        wo08=SimpleNamespace(current_pointer=lambda:dict(run_identity=run.run_identity),
            load=load,current_run=lambda:(current,),load_run=lambda _:(() if fault=='missing_run_member' else (original,))),
        native=SimpleNamespace(load=lambda _:native,bound_identity=lambda _:native.identity),
        wo09=store,experimental_origin=lambda _:origin)
    if fault=='missing_claim':
        for path in store.first_five.glob('*.json'):path.unlink()
    # This focused owner-comparison test substitutes only the already-covered
    # current Native source loader; the full98 HTTP rehearsal tests its files.
    monkeypatch.setattr(native_module,'load_decision_source',lambda *a:d['source_document']['native_source'])
    def forbidden(*a,**k):pytest.fail('read-only first-five provenance invoked readiness evaluation')
    monkeypatch.setattr(boundary_module,'evaluate_experimental_readiness',forbidden)
    before={p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    if fault=='none':IntradayPublicationBoundary.retained_monitoring_source(owner,readiness)
    else:
        with pytest.raises((ValueError,FileNotFoundError)):
            IntradayPublicationBoundary.retained_monitoring_source(owner,readiness)
    assert before=={p:p.read_bytes() for p in tmp_path.rglob('*.json')}
