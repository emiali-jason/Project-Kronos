"""IWO-UX: operational presentation, existing authority, disposable rehearsals."""
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from kronos.browser.dashboard import IntradayDashboardSummary, project_intraday_dashboard, project_sponsor_dashboard
from kronos.browser.intraday_wo08 import render_machine_review
from kronos.browser.intraday_wo09_control import project_card, project_analysis_details
from kronos.browser.views import render_dashboard, _dashboard_swing_card
from kronos.application.notifications import NotificationWorkspaceSnapshot
from kronos.intraday.wo09_persistence import Wo09Store
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_wo09_experimental import experimental_fixture, origin_for, publish
from tests.unit.intraday.test_wo08_wo09_integration import graph


def projection_fixture(tmp_path, **kwargs):
    assessment = experimental_fixture(**kwargs)[-1]
    store = Wo09Store(tmp_path)
    record, requirements = publish(store, assessment, origin_for(assessment), datetime.fromisoformat(assessment.data['created_at']))
    detail = project_analysis_details(record, requirements)
    detail['F. EXPERIMENTAL OBSERVATION'] = dict(first_five_at=None if record.first_five_of_five_at is None else record.first_five_of_five_at.isoformat(),
        selective_watch=(), advisory_wake_hints=())
    return assessment, record, requirements, detail


def summary_sources(tmp_path, monkeypatch, **kwargs):
    _, _, owner, _ = graph(tmp_path/'source')
    assessment, record, _, _ = projection_fixture(tmp_path/'readiness', **kwargs)
    store = Wo09Store(tmp_path/'readiness')
    owner.wo09 = store
    monkeypatch.setattr(owner, '_sources', lambda _: nullcontext())
    monkeypatch.setattr(owner, '_source', lambda *a: pytest.fail('GET ran evaluator source path'))
    monkeypatch.setattr(owner, '_session', lambda *a: datetime.fromisoformat(assessment.data['created_at']))
    monkeypatch.setattr(owner.probables, 'load_current', lambda: SimpleNamespace(run_identity=record.probables_run_identity))
    monkeypatch.setattr(owner.wo08, 'current_pointer', lambda: {'run_identity': record.probables_run_identity})
    _, _, _, run, native, _ = experimental_fixture(**kwargs)
    monkeypatch.setattr(owner.probables, 'load_current_run', lambda: run)
    monkeypatch.setattr(owner.probables, 'load_result', lambda _: run.results[0])
    monkeypatch.setattr(owner.native, 'load', lambda _: native)
    monkeypatch.setattr(owner.wo08, 'load', lambda _: assessment)
    monkeypatch.setattr(owner.wo08, 'current_run', lambda: (assessment,))
    monkeypatch.setattr(owner.native, 'bound_identity', lambda _: assessment.data['native_decision_identity'])
    return store, owner, record


@pytest.mark.parametrize('fixture,now,ready', [({},1,0), ({'five_rows':[(108,102,106)]*25+[(115,110,113),(117,114,116)]},0,1), ({'missing_five':(26,)},0,0)])
def test_summary_counts_persisted_wo09_not_browser_or_98_rows(tmp_path, monkeypatch, fixture, now, ready):
    store, owner, record = summary_sources(tmp_path, monkeypatch, **fixture)
    before = {p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    summary = project_intraday_dashboard(store, owner)
    assert (summary.now,summary.ready) == (now,ready)
    assert summary.current_readiness == (record.readiness_identity,)
    assert summary.watching_disposition == 'DEFERRED_NOT_AUTHORITATIVE'
    assert before == {p:p.read_bytes() for p in tmp_path.rglob('*.json')}


@pytest.mark.parametrize('condition', ['closed','historical','superseded','native_successor','pointer_stale'])
def test_stale_sessions_and_sources_never_count_current(tmp_path, monkeypatch, condition):
    from kronos.intraday.evidence_currentness import NewWorkNotEligible, NewWorkAction, EligibilityReason
    from kronos.intraday.wo09_readiness import CurrentnessState
    store, owner, record = summary_sources(tmp_path, monkeypatch)
    def deny(*args):
        if condition == 'closed': raise ValueError('WO10_SESSION_NOT_OPEN')
        raise NewWorkNotEligible(EligibilityReason.HISTORICAL_SESSION, action=NewWorkAction.READINESS_HANDOFF)
    if condition in {'closed','historical'}: monkeypatch.setattr(owner, '_session', deny)
    elif condition == 'superseded': monkeypatch.setattr(owner.probables, 'load_current', lambda: SimpleNamespace(run_identity='NEW_RUN'))
    elif condition == 'native_successor': monkeypatch.setattr(owner.native, 'bound_identity', lambda _: 'NEW_NATIVE')
    else:
        store.mark_currentness(record.canonical_subject_identity, CurrentnessState.REASSESSMENT_DUE,
            updated_at=record.created_at+timedelta(seconds=1), expected=store.expectation(record.canonical_subject_identity))
    summary = project_intraday_dashboard(store,owner)
    assert (summary.now, summary.ready, summary.state) == (0,0,'NO_CURRENT_READINESS')
    assert not summary.current_readiness


@pytest.mark.parametrize('condition',['boundary','machine_pointer','probable_pointer','native_pointer','corrupt','source_changed'])
def test_missing_authority_and_corruption_are_not_fabricated_zero(tmp_path, monkeypatch, condition):
    store, owner, _ = summary_sources(tmp_path, monkeypatch)
    if condition == 'boundary': owner = None
    elif condition == 'machine_pointer': monkeypatch.setattr(owner.wo08, 'current_pointer', lambda: None)
    elif condition == 'probable_pointer': monkeypatch.setattr(owner.probables, 'load_current', lambda: None)
    elif condition == 'native_pointer': monkeypatch.setattr(owner.native, 'bound_identity', lambda _: None)
    elif condition == 'source_changed': monkeypatch.setattr(store, 'load_pointer', lambda _: None)
    else:
        monkeypatch.setattr(store, 'restore_current', lambda: (_ for _ in ()).throw(ValueError('CORRUPT')))
    summary = project_intraday_dashboard(store,owner)
    assert summary.now is summary.ready is None
    assert summary.state == 'CURRENT_AUTHORITY_UNAVAILABLE'


def test_empty_configured_owner_store_is_authoritative_zero(tmp_path):
    _,_,owner,app = graph(tmp_path)
    summary = project_intraday_dashboard(app.store,owner)
    assert (summary.now,summary.ready,summary.state) == (0,0,'NO_CURRENT_READINESS')
    assert not app.store.root.exists()


def presentation_fixture(tmp_path):
    rows, cards, details = [], [], {}
    for i, options in enumerate(({}, {'five_rows':[(108,102,106)]*25+[(115,110,113),(117,114,116)]}, {'missing_five':(26,)})):
        a,r,q,d = projection_fixture(tmp_path/str(i), subject=('NSE-RELIANCE','NSE-HDFCBANK','NSE-INFY')[i], **options)
        from kronos.intraday.assessment_observation import create_missing_assessment_observations
        from tests.unit.intraday.test_assessment_observation import positive
        run = experimental_fixture(subject=('NSE-RELIANCE','NSE-HDFCBANK','NSE-INFY')[i], **options)[3]
        observed = positive(create_missing_assessment_observations(run).observations[0]) if i == 0 else None
        rows.append(dict(identity=a.identity,integrity=a.integrity,**{k:v for k,v in a.data.items() if k!='source_document'},
            assessment_price=None if observed is None else str(observed.assessment_price),
            assessment_price_time=None if observed is None else observed.assessment_time.isoformat(),
            assessment_price_source=None if observed is None else observed.assessment_source_identity,
            assessment_price_authority='PRICE_NOT_RETAINED' if observed is None else observed.classification.value))
        cards.append(project_card(r,q))
        if i == 1: d['F. EXPERIMENTAL OBSERVATION']['selective_watch'] = ({'state':'RETAINED_BINDING','criterion':'I2'},)
        details[r.readiness_identity] = d
    from tests.unit.intraday.test_wo09_readiness import evaluated
    historic, requirements = evaluated()
    history_card = replace(project_card(historic,requirements),monitorability_state='HISTORICAL_ONLY',attention_state='NONE',next_action='HISTORICAL_EVIDENCE_ONLY')
    return dict(currentness='SOURCE_LINEAGE_CURRENT',assessments=tuple(rows)), dict(cards=tuple(cards),analysis_details=details,
        historical_cards=(history_card,), historical_analysis_details={historic.readiness_identity:project_analysis_details(historic,requirements)},
        operational_summary=IntradayDashboardSummary(1,1,'CURRENT_SESSION_VERIFIED',tuple(c.readiness_identity for c in cards)))


def test_compact_machine_details_history_and_paper_authority(tmp_path):
    status, readiness = presentation_fixture(tmp_path)
    html = render_machine_review(_snapshot(),status,readiness)
    for value in ('I1','I2','I3','I4','I5','READY_FIVE · 5/5 NOW','READY_FOUR · 4/5 READY','Assessment Price · UNAVAILABLE',
                  'First-five','Missing · I2','RETAINED WATCH','NOT_RETAINED','Criterion details','SATISFIED','OUTSTANDING','UNAVAILABLE',
                  'Historical Chart Analyst Evidence','Question Packs, Answers and WO07F','EXPERIMENTAL PAPER','0.1.0','Method and evidence'):
        assert value in html
    assert '<details open' not in html
    assert 'MACHINE WO08 ASSESSMENT</strong>' not in html
    assert 'font-size:22px' in html and '.main:has(.machine-review)' in html
    assert 'Assessment Price · 116' not in html  # Never substitute experimental P.
    assert '<th class="criterion" scope="col">I5</th>' in html


def test_machine_without_session_authority_keeps_rows_secondary(tmp_path):
    status, readiness = presentation_fixture(tmp_path)
    readiness.pop('operational_summary')
    html = render_machine_review(_snapshot(),status,readiness)
    assert 'NO CURRENT MACHINE ASSESSMENT' in html
    assert 'Other / retained assessments · 3' in html
    assert 'Session eligibility not assessed' in html


def test_dashboard_aligns_density_preserves_swing_and_navigation():
    base = project_sponsor_dashboard(_snapshot(),None,(),NotificationWorkspaceSnapshot(()))
    populated = replace(base,intraday=IntradayDashboardSummary(2,3,'CURRENT_SESSION_VERIFIED'))
    html = render_dashboard(_snapshot(),populated)
    assert _dashboard_swing_card(base) == _dashboard_swing_card(populated)
    intraday = html.split('<article class="strategy-card intraday">')[1].split('</article>')[0]
    assert '<span>NOW</span><strong>2' in intraday and '<span>READY</span><strong>3' in intraday
    assert 'SUMMARY NOT YET ACTIVATED' not in intraday and 'WATCHING' not in intraday
    assert 'href="/intraday">VIEW INTRADAY' in intraday
    unknown = render_dashboard(_snapshot(),base).split('<article class="strategy-card intraday">')[1].split('</article>')[0]
    assert 'Current authority unavailable' in unknown and '<strong>—</strong>' in unknown


def test_write_visual_rehearsals(tmp_path):
    destination = os.environ.get('IWO_UX_VISUAL_OUTPUT')
    if not destination:
        return
    out = Path(destination); out.mkdir(parents=True,exist_ok=True)
    status, readiness = presentation_fixture(tmp_path)
    empty = dict(currentness='NOT_YET_ASSESSED',assessments=())
    pages = {'machine-review-empty': render_machine_review(_snapshot(),empty,dict(operational_summary=IntradayDashboardSummary(0,0,'NO_CURRENT_READINESS'))),
        'machine-review-populated': render_machine_review(_snapshot(),status,readiness)}
    pages['machine-review-criterion'] = pages['machine-review-populated'].replace('<details><summary>Criterion details', '<details open><summary>Criterion details',1)
    pages['machine-review-history'] = pages['machine-review-populated'].replace('<details><summary>Historical Chart Analyst Evidence', '<details open><summary>Historical Chart Analyst Evidence',1)
    base = project_sponsor_dashboard(_snapshot(),None,(),NotificationWorkspaceSnapshot(()))
    for name,summary in (('dashboard-zero',IntradayDashboardSummary(0,0,'NO_CURRENT_READINESS')),('dashboard-nonzero',readiness['operational_summary']),('dashboard-unavailable',IntradayDashboardSummary())):
        pages[name]=render_dashboard(_snapshot(),replace(base,intraday=summary))
    for name,html in pages.items(): (out/(name+'.html')).write_text(html)
    (out/'states.txt').write_text('A machine-review-empty; B/C/D machine-review-populated; E machine-review-history; F dashboard-zero; G dashboard-nonzero; H not applicable: authoritative WATCHING metric absent; I all dashboards omit WATCHING. Disposable source-valid WO08/WO09 examples; watch presentation marker is a test-only retained binding. No production records.\n')


def test_assessment_price_uses_exact_retained_admission_companion(tmp_path):
    from kronos.browser.intraday_wo08 import IntradayWo08Projection
    from kronos.intraday.probables_v2_persistence import ProbablesV2Store
    from kronos.intraday.assessment_observation import create_missing_assessment_observations
    from tests.unit.intraday.test_wo08_assessment import publish as publish_machine
    from tests.unit.intraday.test_assessment_observation import manifest, positive
    run, mapping, _, owner, _ = publish_machine(tmp_path/'machine')
    original = create_missing_assessment_observations(run)
    assert original.observations
    observed = positive(original.observations[0])
    companion = manifest(run,(observed,)+original.observations[1:])
    store = ProbablesV2Store(tmp_path/'probables')
    store.retain_complete(run=run,mappings=mapping.member_evidence,assessment_observations=companion)
    status = IntradayWo08Projection(owner.store,store).status_document()
    row = next(r for r in status['assessments'] if r['probable_result_identity']==observed.admission_identity)
    assert row['assessment_price']=='123.45'
    assert row['assessment_price_time']==observed.assessment_time.isoformat()
    assert row['assessment_price_source']==observed.assessment_source_identity
    assert row['assessment_price_authority']=='EXACT_PRICE_PERSISTED'
    assert 'Assessment Price · 123.45' in render_machine_review(_snapshot(),status,{})


def test_summary_real_persisted_graph_and_domain008_session(tmp_path):
    """No source/currentness mocks: complete publication, owning locks and calendar."""
    from kronos.market.calendar import MarketCalendarPublisher
    from kronos.browser.intraday_futures_control import domain008_session
    from kronos.intraday.probables_v2 import ProbablesUnavailableMemberV2, ProbableReasonV2, evaluate_probables_v2_run
    from kronos.intraday.probables_v2_persistence import ProbablesV2Store
    from kronos.application.intraday_native_selection import NativePullbackPublication
    from kronos.intraday.native_structural_selection import NativeStructuralStore
    from kronos.application.intraday_wo08 import Wo08Publication
    from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
    from tests.unit.intraday.test_wo08_experimental import START
    calendar = MarketCalendarPublisher()
    now = [START + timedelta(minutes=135)]
    session = domain008_session(calendar,'NSE-EQ-LUPIN',now[0]).schedule.session_id
    _, facts, mapping, original, _, _ = experimental_fixture(session=session)
    missing = tuple(ProbablesUnavailableMemberV2('MISSING-'+str(i),'MCX-SUBJECT-MISSING' if i==0 else 'NSE-EQ-MISSING'+str(i),
        session, original.analysis_boundary,ProbableReasonV2.MANDATORY_EVIDENCE_UNAVAILABLE,'DISCOVERY',('ISOLATED',)) for i in range(97))
    run = evaluate_probables_v2_run(source_discovery_run_identity='DISCOVERY',universe_identity='UNIVERSE',universe_version='1',
        reconciliation_identity='RECONCILIATION',reconciliation_version='1',market_session_identity=session,
        analysis_boundary=original.analysis_boundary,member_evidence=(mapping,),unavailable_members=missing,provenance=('ISOLATED',))
    native = NativePullbackPublication(NativeStructuralStore(tmp_path/'native'),clock=lambda:now[0],commissioned_at=now[0])
    native.publish(run,(mapping,),facts=(facts,),newly_published=True)
    machine = Wo08Publication(Wo08AssessmentStore(tmp_path/'machine'))
    assessments = machine.publish_run(run=run,mapping=(mapping,),native_publication=native,published_at=now[0])
    probable = ProbablesV2Store(tmp_path/'probables')
    probable.retain_complete(run=run,mappings=(mapping,))
    _,_,boundary,_ = graph(tmp_path/'boundary')
    store = Wo09Store(tmp_path/'wo09')
    boundary.wo09, boundary.probables, boundary.wo08, boundary.native = store, probable, machine.store, native.store
    boundary.calendar, boundary.clock = calendar, lambda:now[0]
    admitted = next(a for a in assessments if a.data['subject']=='NSE-EQ-LUPIN')
    readiness,_ = publish(store,admitted,origin_for(admitted),now[0])
    assert readiness.satisfied_count == 5
    missing_mcx = next(a for a in assessments if a.data['subject']=='MCX-SUBJECT-MISSING')
    absent,_ = publish(store,missing_mcx,None,now[0])
    assert absent.readiness_state.value in {'HARD_GATE','READINESS_UNAVAILABLE'}
    assert absent.exact_mcx_contract_identity is None
    before = {p:p.read_bytes() for p in tmp_path.rglob('*.json')}
    current = project_intraday_dashboard(store,boundary)
    assert (current.now,current.ready,current.state)==(1,0,'CURRENT_SESSION_VERIFIED')
    now[0] += timedelta(days=3)  # Another open session, same persisted CURRENT pointer.
    stale = project_intraday_dashboard(store,boundary)
    assert (stale.now,stale.ready,stale.state)==(0,0,'NO_CURRENT_READINESS')
    assert before == {p:p.read_bytes() for p in tmp_path.rglob('*.json')}


def mcx_options():
    from dataclasses import fields
    from tests.unit.instrument.test_active_derivative_selection import _resolve
    from tests.unit.intraday.test_discovery_runtime import _publications, _bundle
    from tests.unit.intraday.test_wo08_experimental import START
    from kronos.intraday.discovery_runtime import DiscoveryRunBoundary
    from kronos.intraday.discovery import create_machine_fact_bundle
    at = START+timedelta(minutes=135)
    subject = 'MCX-SUBJECT-GOLDM'
    binding = _resolve(at).for_subject(subject).binding
    _, reconciliation = _publications()
    member = next(m for m in reconciliation.members if m.canonical_identity==subject)
    bundle = _bundle(member,DiscoveryRunBoundary(at,binding.domain008_session_identity,'BOUNDARY'),reconciliation)
    values = {f.name:getattr(bundle,f.name) for f in fields(bundle) if f.name!='bundle_identity'}
    values['source_identities'] += (binding.binding_identity,binding.provider_snapshot_identity)
    values['provenance'] += (binding.integrity_identity,binding.domain008_session_identity)
    return dict(subject=subject,session=binding.domain008_session_identity,binding=binding,bundle=create_machine_fact_bundle(**values))


@pytest.mark.parametrize('condition',['current','missing','rolled'])
def test_summary_mcx_exact_contract_binding(tmp_path,monkeypatch,condition):
    options = mcx_options()
    store, owner, _ = summary_sources(tmp_path,monkeypatch,**options)
    binding = options['binding']
    if condition == 'missing': binding = None
    if condition == 'rolled': binding = SimpleNamespace(binding_identity='SUCCESSOR')
    monkeypatch.setattr(owner.bindings,'load_current',lambda **_: binding)
    summary = project_intraday_dashboard(store,owner)
    assert (summary.now,summary.ready) == {'current':(1,0),'missing':(None,None),'rolled':(0,0)}[condition]


def test_mcx_exact_contract_is_visible_in_primary_row(tmp_path):
    a,r,q,d = projection_fixture(tmp_path,**mcx_options())
    status = dict(currentness='SOURCE_LINEAGE_CURRENT',assessments=(dict(identity=a.identity,**a.data),))
    readiness = dict(cards=(project_card(r,q),),analysis_details={r.readiness_identity:d},
        operational_summary=IntradayDashboardSummary(1,0,'CURRENT_SESSION_VERIFIED',(r.readiness_identity,)))
    html = render_machine_review(_snapshot(),status,readiness)
    assert a.data['exact_mcx_contract_identity'] in html
    if os.environ.get('IWO_UX_VISUAL_OUTPUT'):
        (Path(os.environ['IWO_UX_VISUAL_OUTPUT'])/'machine-review-mcx.html').write_text(html)


def test_summary_nse_closed_does_not_globally_deny_open_mcx(tmp_path,monkeypatch):
    """Both actual DOMAIN008 calls use the same evening clock independently."""
    from kronos.application.intraday_evidence_currentness import IntradayPublicationBoundary
    from kronos.market.calendar import MarketCalendarPublisher
    from tests.unit.intraday.test_wo08_experimental import START
    evening = START + timedelta(hours=8)
    options = mcx_options()
    nse_store, nse, _ = summary_sources(tmp_path/'nse',monkeypatch)
    mcx_store, mcx, _ = summary_sources(tmp_path/'mcx',monkeypatch,**options)
    monkeypatch.setattr(mcx.bindings,'load_current',lambda **_:options['binding'])
    for owner in (nse,mcx):
        owner.clock = lambda:evening
        owner.calendar = MarketCalendarPublisher()
        monkeypatch.setattr(owner,'_session',IntradayPublicationBoundary._session.__get__(owner))
    assert (project_intraday_dashboard(nse_store,nse).now,project_intraday_dashboard(nse_store,nse).ready)==(0,0)
    assert (project_intraday_dashboard(mcx_store,mcx).now,project_intraday_dashboard(mcx_store,mcx).ready)==(1,0)
