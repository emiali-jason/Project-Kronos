"""Limited historical reads; real immutable stores in disposable test roots only."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from kronos.application.intraday_machine_history import IntradayMachineHistory, MachineHistoryError
from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.wo09_persistence import Wo09Store
from tests.unit.intraday.test_wo08_assessment import publish


def inventory(root):
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def history_fixture(root, *, experimental=False, price=False, source_options=None):
    if not experimental:
        run, mapping, _, owner, records = publish(root)
        store = owner.store
        mappings = mapping.member_evidence
    else:
        from tests.unit.intraday.test_wo08_experimental import experimental_fixture
        from kronos.intraday.probables_v2 import ProbablesUnavailableMemberV2, ProbableReasonV2, evaluate_probables_v2_run
        from kronos.intraday.native_pullback_decision import source_document, build_decision
        from kronos.intraday.wo08_experimental import assess_experimental
        _, facts, mapping, original, _, _ = experimental_fixture(**(source_options or {}))
        missing = tuple(ProbablesUnavailableMemberV2('UNAVAILABLE-'+str(i).zfill(3),
            'NSE-EQ-MISSING'+str(i), original.market_session_identity, original.analysis_boundary,
            ProbableReasonV2.MANDATORY_EVIDENCE_UNAVAILABLE, 'DISCOVERY', ('ISOLATED',)) for i in range(97))
        run = evaluate_probables_v2_run(source_discovery_run_identity='DISCOVERY', universe_identity='UNIVERSE',
            universe_version='1', reconciliation_identity='RECONCILIATION', reconciliation_version='1',
            market_session_identity=original.market_session_identity, analysis_boundary=original.analysis_boundary,
            member_evidence=(mapping,), unavailable_members=missing, provenance=('ISOLATED',))
        records = []
        for result in run.results:
            mapped = result.source_mapping_identity is not None
            source = source_document(facts, mapping, result, run.run_identity,
                mcx_binding=(source_options or {}).get('binding'), machine_bundle=(source_options or {}).get('bundle')) if mapped else None
            native = build_decision(source, created_at=run.analysis_boundary) if mapped else None
            records.append(assess_experimental(run_identity=run.run_identity, run_integrity=run.integrity_identity,
                result=result, mapping=mapping if mapped else None, native=native,
                native_source=source, created_at=run.analysis_boundary))
        records = tuple(records)
        store = Wo08AssessmentStore(root)
        store.publish(run, records)
        mappings = (mapping,)
    probables = ProbablesV2Store(root)
    companion = None
    if price:
        from kronos.intraday.assessment_observation import create_missing_assessment_observations
        from tests.unit.intraday.test_assessment_observation import manifest, positive
        blank = create_missing_assessment_observations(run)
        companion = manifest(run, tuple(positive(x) for x in blank.observations))
    probables.retain_complete(run=run, mappings=mappings, assessment_observations=companion)
    readiness = Wo09Store(root)
    recent = [dict(run_identity=run.run_identity, boundary=run.analysis_boundary.isoformat(),
                   result='Success', duration_microseconds=82000000)]
    reader = IntradayMachineHistory(assessments=store, probables=probables, readiness=readiness,
                                  recent_attempts=lambda: tuple(recent))
    return SimpleNamespace(reader=reader, run=run, records=records, store=store, probables=probables,
                           readiness=readiness, recent=recent)


def retain_positive(f):
    from tests.unit.intraday.test_wo09_experimental import publish as retain, origin_for
    a = next(r for r in f.records if r.data['disposition'] == 'ASSESSMENT_ESTABLISHED')
    record, _ = retain(f.readiness, a, origin_for(a), f.run.analysis_boundary+timedelta(seconds=1))
    assert record.satisfied_count == 5
    return a, record


def test_constructor_inert_exact_dependencies_and_no_fallback(tmp_path, monkeypatch):
    stores = (Wo08AssessmentStore(tmp_path), ProbablesV2Store(tmp_path), Wo09Store(tmp_path))
    before = inventory(tmp_path)
    reader = IntradayMachineHistory(assessments=stores[0], probables=stores[1], readiness=stores[2],
        recent_attempts=lambda: (_ for _ in ()).throw(AssertionError('constructor must not read')))
    assert (reader.assessments, reader.probables, reader.readiness) == stores
    assert inventory(tmp_path) == before
    with pytest.raises(TypeError, match='DEPENDENCIES_REQUIRED'):
        IntradayMachineHistory(assessments=object(), probables=stores[1], readiness=stores[2], recent_attempts=lambda:())


@pytest.mark.parametrize('size,lengths', [(25,[25,25,25,23]), (50,[50,48]), (1,[1]*98)])
def test_complete_population_pagination_order_restart_and_no_writes(tmp_path, size, lengths):
    f = history_fixture(tmp_path)
    before = inventory(tmp_path)
    one = f.reader.page(run=f.run.run_identity, page_size=size)
    pages = [f.reader.page(run=f.run.run_identity, page_size=size, page=i+1, population=one['population'])
             for i in range(len(lengths))]
    assert [len(p['rows']) for p in pages] == lengths
    assert [r['identity'] for p in pages for r in p['rows']] == [r.identity for r in f.records]
    assert all(p['total']==98 and p['history_only'] and p['new_work_authority']=='NONE' for p in pages)
    f.recent.clear()
    (f.store.root/'current.json').write_bytes(b'corrupt mutable alias, never history authority')
    before = inventory(tmp_path)
    restarted = IntradayMachineHistory(assessments=Wo08AssessmentStore(tmp_path),
        probables=ProbablesV2Store(tmp_path), readiness=Wo09Store(tmp_path), recent_attempts=lambda:())
    restored = restarted.page(run=f.run.run_identity)
    assert restored['selected_outside_recent_five'] and restored['total']==98
    assert [r['identity'] for r in restored['rows']]==[r.identity for r in f.records[:25]]
    assert inventory(tmp_path)==before


@pytest.mark.parametrize('field,value', [('page',0),('page',True),('page_size',0),('page_size',51),
    ('run','../bad'),('run',''),('population','bad'),('page',5)])
def test_invalid_selection_is_bounded(tmp_path, field, value):
    f=history_fixture(tmp_path);args=dict(run=f.run.run_identity);args[field]=value
    with pytest.raises(MachineHistoryError) as e:f.reader.page(**args)
    assert e.value.status==400


def test_fingerprint_requires_expectation_and_never_recaptures(tmp_path):
    f=history_fixture(tmp_path);one=f.reader.page(run=f.run.run_identity)
    with pytest.raises(MachineHistoryError,match='POPULATION_REQUIRED'):f.reader.page(run=f.run.run_identity,page=2)
    for args in [dict(population='0'*64),dict(population=one['population'],page_size=50)]:
        with pytest.raises(MachineHistoryError) as e:f.reader.page(run=f.run.run_identity,**args)
        assert e.value.status==409
    # Loss of optional companion changes the bound fingerprint, even though the run still validates.
    f.probables._path('assessments',f.run.run_identity).unlink()
    with pytest.raises(MachineHistoryError,match='POPULATION_CHANGED'):
        f.reader.page(run=f.run.run_identity,page=2,population=one['population'])


@pytest.mark.parametrize('failure,status', [('missing',404),('corrupt',422),('storage',503)])
def test_complete_run_failure_never_returns_partial_population(tmp_path,monkeypatch,failure,status):
    f=history_fixture(tmp_path)
    if failure=='missing':f.store._record_path(f.records[-1].identity).unlink()
    elif failure=='corrupt':f.store._record_path(f.records[-1].identity).write_bytes(b'{}')
    else:monkeypatch.setattr(f.store,'load_run',lambda _:(_ for _ in ()).throw(OSError('private path')))
    before=inventory(tmp_path)
    with pytest.raises(MachineHistoryError) as e:f.reader.page(run=f.run.run_identity)
    assert e.value.status==status and 'private path' not in str(e.value)
    assert inventory(tmp_path)==before


@pytest.mark.parametrize('count',[0,1,5])
def test_recent_bound_and_independent_exact_selection(tmp_path,count):
    f=history_fixture(tmp_path);f.recent[:]=[dict(f.recent[0],result='Failed',run_identity=None)]*count
    assert len(f.reader.page()['recent']['entries'])==count
    assert f.reader.page(run=f.run.run_identity)['total']==98


@pytest.mark.parametrize('error,reason', [(FileNotFoundError(),'MISSING'),(ValueError(),'INVALID'),(OSError(),'STORAGE_UNAVAILABLE')])
def test_recent_unavailable_is_not_empty_history(tmp_path,error,reason):
    f=history_fixture(tmp_path);f.reader.recent_attempts=lambda:(_ for _ in ()).throw(error)
    d=f.reader.page(run=f.run.run_identity)
    assert reason in d['recent']['unavailable'] and d['total']==98


def test_recent_over_bound_and_unlinked_readiness(tmp_path):
    f=history_fixture(tmp_path);f.recent*=6
    assert f.reader.page()['recent']['unavailable']=='RECENT_ANALYSIS_EVIDENCE_INVALID'
    d=f.reader.page(run=f.run.run_identity)
    assert d['readiness_detail'] is None
    assert all(r['original_readiness']=='ORIGINAL_READINESS_NOT_LINKED' for r in d['rows'])


def test_price_companion_exact_original_proof_and_scope_order(tmp_path,monkeypatch):
    f=history_fixture(tmp_path,price=True);held=[]
    @contextmanager
    def scope():
        held.append(True)
        try:yield
        finally:held.pop()
    monkeypatch.setattr(f.store,'page_read_scope',scope)
    original=f.probables.load_assessment_observations
    def companion(run):
        assert not held
        return original(run)
    monkeypatch.setattr(f.probables,'load_assessment_observations',companion)
    row=next(r for r in f.reader.page(run=f.run.run_identity)['rows'] if r['assessment_price'])
    assert row['assessment_price']=='123.45'
    assert row['assessment_price_source']=='ISOLATED-DESIGNATED-OBSERVATION'
    assert row['assessment_price_time']!=(f.run.analysis_boundary.isoformat())


@pytest.mark.parametrize('case,expected,status',[('valid','VALIDATED_EXACT_HISTORICAL_READINESS',200),
    ('absent','EXACT_READINESS_EVIDENCE_MISSING',200),('proof_missing','EXACT_READINESS_REQUIRED_PROOF_NOT_ESTABLISHED',200),
    ('proof_unequal','EXACT_READINESS_REQUIRED_PROOF_NOT_ESTABLISHED',200),('proof_corrupt','EXACT_READINESS_EVIDENCE_INVALID',422),
    ('record_corrupt','EXACT_READINESS_EVIDENCE_INVALID',422),('path_mismatch','EXACT_READINESS_EVIDENCE_INVALID',422),
    ('lineage','EXACT_READINESS_LINEAGE_MISMATCH',422),('storage','EXACT_READINESS_STORAGE_UNAVAILABLE',503)])
def test_real_readiness_reader_missing_unequal_corrupt_and_exact_lineage(tmp_path,monkeypatch,case,expected,status):
    f=history_fixture(tmp_path,experimental=True);a,r=retain_positive(f)
    path=f.readiness.readiness/(r.readiness_identity+'.json')
    proof_path=f.readiness.first_five/(r.first_five_document['claim_identity']+'.json')
    identity=r.readiness_identity;selected=a.identity
    if case=='absent':path.unlink()
    elif case=='proof_missing':proof_path.unlink()
    elif case=='proof_unequal':
        from kronos.intraday.wo09_experimental import observe_first_five
        from tests.unit.intraday.test_wo09_experimental import origin_for
        from kronos.intraday.wo09_readiness import artifact_bytes
        unequal=observe_first_five(a,origin_for(a),observed_at=r.created_at+timedelta(seconds=1))
        proof_path.write_bytes(artifact_bytes(unequal))
        assert f.readiness.load_first_five(unequal.claim_identity)==unequal
        assert unequal.document!=r.first_five_document
    elif case=='proof_corrupt':proof_path.write_bytes(b'{}')
    elif case=='record_corrupt':path.write_bytes(b'{}')
    elif case=='path_mismatch':
        identity='INTRADAY-WO09-EXPERIMENTAL-'+'A'*64
        (f.readiness.readiness/(identity+'.json')).write_bytes(path.read_bytes())
    elif case=='lineage':selected=f.records[-1].identity
    elif case=='storage':monkeypatch.setattr(f.readiness,'load_readiness',lambda _:(_ for _ in ()).throw(OSError('private path')))
    before=inventory(tmp_path)
    d=f.reader.page(run=f.run.run_identity,assessment=selected,readiness=identity)
    assert d['readiness_http_status']==status and d['readiness_detail']['state']==expected
    assert d['total']==98 and len(d['rows'])==25 and inventory(tmp_path)==before
    if case=='valid':
        assert d['readiness_detail']['original']['currentness'].value=='CURRENT'
        assert d['readiness_detail']['new_work_authority']=='NONE'
    else:assert 'original' not in d['readiness_detail']
    if case.startswith('proof_') and case!='proof_corrupt':
        assert set(d['readiness_detail'])=={'identity','state','limitation','new_work_authority'}


def test_history_get_never_enumerates_or_uses_current_authority(tmp_path,monkeypatch):
    f=history_fixture(tmp_path)
    def forbidden(*_,**__):raise AssertionError('authority or estate scan forbidden')
    for owner,names in [(f.store,['records','current_pointer','current_run']),
                        (f.readiness,['load_pointer','load_requirements','load_notifications','load_watches','restore_current']),
                        (f.probables,['load_current_run'])]:
        for name in names:monkeypatch.setattr(owner,name,forbidden)
    assert f.reader.page(run=f.run.run_identity)['total']==98


@pytest.mark.parametrize('family',['GOLDM','NATGAS'])
def test_exact_mcx_contract_roll_and_held_evidence_are_preserved(tmp_path,family):
    from dataclasses import fields
    from tests.unit.instrument.test_active_derivative_selection import _resolve
    from tests.unit.intraday.test_discovery_runtime import _publications,_bundle
    from tests.unit.intraday.test_native_pullback_policy import START
    from kronos.intraday.discovery_runtime import DiscoveryRunBoundary
    from kronos.intraday.discovery import create_machine_fact_bundle
    boundary=START+timedelta(minutes=135);subject='MCX-SUBJECT-'+family
    binding=_resolve(boundary).for_subject(subject).binding
    _,reconciliation=_publications()
    member=next(m for m in reconciliation.members if m.canonical_identity==subject)
    bundle=_bundle(member,DiscoveryRunBoundary(boundary,binding.domain008_session_identity,'BOUNDARY'),reconciliation)
    values={x.name:getattr(bundle,x.name) for x in fields(bundle) if x.name!='bundle_identity'}
    values['source_identities']+=(binding.binding_identity,binding.provider_snapshot_identity)
    values['provenance']+=(binding.integrity_identity,binding.domain008_session_identity)
    bundle=create_machine_fact_bundle(**values)
    f=history_fixture(tmp_path,experimental=True,source_options=dict(subject=subject,
        session=binding.domain008_session_identity,binding=binding,bundle=bundle))
    row=next(r for r in f.reader.page(run=f.run.run_identity)['rows'] if r['subject']==subject)
    assert row['exact_mcx_contract_identity']==binding.active_binding.derivative_contract_id
    assert row['exact_mcx_roll_lineage']==binding.binding_identity
    assert row['session_identity']==binding.domain008_session_identity
    if family=='NATGAS':assert row['hard_gate']=='NATGAS_COMMISSIONING_HELD'


def test_real_prepared_recent_reader_keeps_attempt_accounting_binding(tmp_path,monkeypatch):
    from tests.unit.browser.test_iwo06c_observability import history_fixture as timed,clone
    runtime,control,record,accounting=timed(tmp_path/'timed')
    runtime.discovery_v2_operation.accounting_store.retain(accounting)
    control._store.retain(record)
    f=history_fixture(tmp_path/'population');f.reader.recent_attempts=control.analysis_history_document
    def forbidden(*_,**__):raise AssertionError('whole history scan/restore forbidden')
    monkeypatch.setattr(control._store,'restore_latest',forbidden)
    entries=f.reader.recent()['entries']
    assert any(x['duration_microseconds']==82000000 for x in entries)
    # Missing linked accounting makes navigation unavailable, never inferred from other timing.
    runtime.discovery_v2_operation.accounting_store._path(accounting.accounting_identity).unlink()
    d=f.reader.page(run=f.run.run_identity)
    assert d['recent']['unavailable']=='RECENT_ANALYSIS_EVIDENCE_INVALID' and d['total']==98


def test_selected_historical_run_unchanged_by_current_supersession(tmp_path):
    from tests.unit.intraday.test_wo08_assessment import later_unavailable_run
    from kronos.intraday.wo08_assessment import assess
    f=history_fixture(tmp_path)
    original=f.reader.page(run=f.run.run_identity)
    later=later_unavailable_run(f.run)
    records=tuple(assess(run_identity=later.run_identity,run_integrity=later.integrity_identity,
        result=r,mapping=None,native=None,created_at=later.analysis_boundary) for r in later.results)
    f.store.publish(later,records)
    f.recent[:]=[dict(run_identity=later.run_identity,result='Success')]
    old=f.reader.page(run=f.run.run_identity,population=original['population'])
    assert old['rows']==original['rows'] and old['selected_outside_recent_five']
    assert f.reader.page(run=later.run_identity)['run_identity']==later.run_identity


@pytest.mark.parametrize('payload',[b'[]',b'null',b'42',b'"not a record"'])
def test_non_object_member_json_returns_bounded_422_not_partial_history(tmp_path,payload):
    from kronos.browser.intraday_machine_history import history_response
    from tests.unit.browser.test_product_route_isolation import _snapshot
    f=history_fixture(tmp_path)
    f.store._record_path(f.records[-1].identity).write_bytes(payload)
    before=inventory(tmp_path)
    response=history_response(f.reader,{'run':[f.run.run_identity]},_snapshot)
    assert response.status.value==422
    assert 'MACHINE_HISTORY_SELECTED_RUN_INVALID' in response.body
    assert 'Complete validated assessment population' not in response.body
    assert 'original_readiness' not in response.body and str(tmp_path) not in response.body
    assert inventory(tmp_path)==before
