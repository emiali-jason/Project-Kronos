"""Production WO08 authority, unavailable semantics and exact population publication."""
from datetime import timedelta
import json
from types import SimpleNamespace
import pytest
from kronos.application.intraday_wo08 import Wo08Publication
from kronos.application.intraday_native_selection import NativePullbackPublication
from kronos.intraday.native_structural_selection import NativeStructuralStore
from kronos.intraday.native_pullback_decision import build_decision, unavailable_source
from kronos.intraday.native_pullback_policy import CHECKSUM as NATIVE_CHECKSUM
from kronos.intraday.wo08_assessment import assess, Wo08Assessment, canonical, digest
from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
from kronos.intraday.probables_v2 import ProbablesUnavailableMemberV2, ProbableReasonV2, evaluate_probables_v2_run
from tests.unit.intraday.test_native_pullback_decision import source_fixture


def population(tmp_path, *, all_unavailable=False):
    source, facts, mapping, original = source_fixture()
    missing = tuple(ProbablesUnavailableMemberV2('UNAVAILABLE-'+str(i).zfill(3), 'NSE-EQ-MISSING'+str(i),
        original.market_session_identity, original.analysis_boundary,
        ProbableReasonV2.MANDATORY_EVIDENCE_UNAVAILABLE, 'DISCOVERY', ('ISOLATED',))
        for i in range(98 if all_unavailable else 97))
    mappings = () if all_unavailable else (mapping,)
    run = evaluate_probables_v2_run(source_discovery_run_identity='DISCOVERY', universe_identity='UNIVERSE',
        universe_version='1', reconciliation_identity='RECONCILIATION', reconciliation_version='1',
        market_session_identity=original.market_session_identity, analysis_boundary=original.analysis_boundary,
        member_evidence=mappings, unavailable_members=missing, provenance=('ISOLATED',))
    native = NativePullbackPublication(NativeStructuralStore(tmp_path/'native'), clock=lambda:run.analysis_boundary,
        commissioned_at=run.analysis_boundary)
    native.publish(run, mappings, facts=() if all_unavailable else (facts,), newly_published=True)
    return run, SimpleNamespace(member_evidence=mappings), native


def publish(tmp_path, *, all_unavailable=False):
    run, mapping, native = population(tmp_path, all_unavailable=all_unavailable)
    owner = Wo08Publication(Wo08AssessmentStore(tmp_path))
    records = owner.publish_run(run=run, mapping=mapping, native_publication=native, published_at=run.analysis_boundary)
    return run, mapping, native, owner, records


@pytest.mark.parametrize('direction', ['LONG', 'SHORT'])
def test_native_pullback_never_fills_uncommissioned_visual_criteria(direction):
    source, _, mapping, run = source_fixture(direction=direction)
    native = build_decision(source, created_at=run.analysis_boundary)
    record = assess(run_identity=run.run_identity, run_integrity=run.integrity_identity,
        result=run.results[0], mapping=mapping, native=native, created_at=run.analysis_boundary)
    assert record.data['criteria'][0]['state'] in {'DETERMINISTICALLY_ESTABLISHED', 'DETERMINISTICALLY_NEGATIVE'}
    assert [r['state'] for r in record.data['criteria'][1:]] == ['NOT_COMMISSIONED']*4
    assert record.data['trading_authority'] is False
    assert record.data['native_decision_identity'] == native.identity
    assert not any(k in record.data for k in ('wo07f_identity', 'answer_pack_identity', 'entry', 'stop', 'target'))


def test_opening_is_not_substituted_for_normal_15m_structure():
    from tests.unit.intraday.test_probables_v2 import _opening_inputs, _run
    mapping = _opening_inputs()[-1]
    run = _run(mapping)
    native = build_decision(unavailable_source(mapping, run.results[0], run.run_identity, 'NO_CONFIRMED_STRUCTURAL_CYCLE'),
                            created_at=run.analysis_boundary)
    record = assess(run_identity=run.run_identity, run_integrity=run.integrity_identity,
        result=run.results[0], mapping=mapping, native=native, created_at=run.analysis_boundary)
    assert record.data['criteria'][0]['state'] == 'UNAVAILABLE'
    assert record.data['criteria'][0]['reason_codes'] == ['NORMAL_15M_STRUCTURE_NOT_ESTABLISHED']


@pytest.mark.parametrize('all_unavailable', [False, True])
def test_complete_98_manifest_restart_and_duplicate_are_read_only(tmp_path, all_unavailable):
    run, mapping, native, owner, records = publish(tmp_path, all_unavailable=all_unavailable)
    assert len(records) == 98
    pointer = owner.store.current_pointer()
    assert pointer['generation'] == 1 and pointer['run_identity'] == run.run_identity
    assert Wo08AssessmentStore(tmp_path).current_run() == records
    assert owner.store.records() == records
    before = {str(p):p.read_bytes() for p in owner.store.root.rglob('*') if p.is_file()}
    assert owner.publish_run(run=run, mapping=mapping, native_publication=native,
        published_at=run.analysis_boundary+timedelta(hours=1)) == records
    assert owner.publish_run(run=run, mapping=mapping, native_publication=native,
        published_at=run.analysis_boundary, newly_published=False) == ()
    assert before == {str(p):p.read_bytes() for p in owner.store.root.rglob('*') if p.is_file()}
    assert all(r.data['disposition'] in {'HARD_GATE', 'ASSESSMENT_UNAVAILABLE'} for r in records)


def test_constructor_and_historical_run_do_not_create_authority(tmp_path):
    store = Wo08AssessmentStore(tmp_path)
    assert store.current_pointer() is None and store.current_run() == () and store.records() == ()
    assert Wo08Publication(store).publish_run(run=None,mapping=None,native_publication=None,
        published_at=None,newly_published=False) == ()
    assert not store.root.exists()


def test_missing_mapped_source_aborts_instead_of_downgrading(tmp_path):
    run, mapping, native = population(tmp_path)
    owner = Wo08Publication(Wo08AssessmentStore(tmp_path))
    with pytest.raises(ValueError, match='MAPPING_POPULATION'):
        owner.publish_run(run=run,mapping=(),native_publication=native,published_at=run.analysis_boundary)
    assert owner.store.current_pointer() is None


def test_native_source_tamper_propagates_and_no_assessment_publishes(tmp_path):
    run, mapping, native = population(tmp_path)
    path = next((native.store.root/'sources').glob('*.json'))
    path.write_text('{}')
    owner = Wo08Publication(Wo08AssessmentStore(tmp_path))
    with pytest.raises(ValueError, match='SOURCE_INTEGRITY_INVALID'):
        owner.publish_run(run=run,mapping=mapping,native_publication=native,published_at=run.analysis_boundary)
    assert owner.store.current_pointer() is None and not owner.store.root.exists()


def test_storage_failure_has_no_current_authority_or_complete_manifest(tmp_path, monkeypatch):
    run, mapping, native = population(tmp_path)
    owner = Wo08Publication(Wo08AssessmentStore(tmp_path))
    original = owner.store._io._retain
    calls = []
    def fail(path, payload):
        calls.append(path)
        if len(calls) == 2:
            raise OSError('ISOLATED_STORAGE_FAILURE')
        return original(path,payload)
    monkeypatch.setattr(owner.store._io, '_retain', fail)
    with pytest.raises(OSError):
        owner.publish_run(run=run,mapping=mapping,native_publication=native,published_at=run.analysis_boundary)
    assert owner.store.current_pointer() is None and owner.store.records() == ()
    with pytest.raises(FileNotFoundError): owner.store.load_run(run.run_identity)


def test_missing_manifest_member_blocks_restoration(tmp_path):
    run, mapping, native, owner, records = publish(tmp_path)
    owner.store._record_path(records[-1].identity).unlink()
    with pytest.raises(FileNotFoundError): Wo08AssessmentStore(tmp_path).current_run()


def test_expectation_conflict_retains_current_and_no_rewrite(tmp_path):
    run, _, _, owner, records = publish(tmp_path)
    before = owner.store.current_pointer()
    with pytest.raises(ValueError, match='PUBLICATION_CONFLICT'):
        owner.store.publish(run,records,expected_pointer=None)
    assert owner.store.current_pointer() == before


def test_rehashed_positive_fabrication_cannot_gain_criterion_authority(tmp_path):
    *_, records = publish(tmp_path)
    d = records[0].data
    d['criteria'][2]['state'] = 'DETERMINISTICALLY_ESTABLISHED'
    core = {k:v for k,v in d.items() if k not in {'assessment_identity','integrity_sha256'}}
    d.update(assessment_identity='WO08-ASSESSMENT-'+digest(core),integrity_sha256=digest(core))
    with pytest.raises(ValueError, match='INTEGRITY_INVALID'): Wo08Assessment(canonical(d))


def test_full_population_required_and_symlinks_rejected(tmp_path):
    source, _, mapping, run = source_fixture()
    native = build_decision(source,created_at=run.analysis_boundary)
    record = assess(run_identity=run.run_identity,run_integrity=run.integrity_identity,
        result=run.results[0],mapping=mapping,native=native,created_at=run.analysis_boundary)
    store = Wo08AssessmentStore(tmp_path)
    with pytest.raises(ValueError,match='COMPLETE_POPULATION'):
        store.publish(run,(record,))
    other = tmp_path/'other';other.mkdir()
    store.root.symlink_to(other,target_is_directory=True)
    with pytest.raises(ValueError,match='SYMLINK'): store.current_pointer()


def later_unavailable_run(run):
    boundary = run.analysis_boundary + timedelta(minutes=15)
    missing = tuple(ProbablesUnavailableMemberV2(r.universe_member_identity, r.canonical_subject_identity,
        r.market_session_identity, boundary, ProbableReasonV2.MANDATORY_EVIDENCE_UNAVAILABLE,
        'DISCOVERY-LATER', ('ISOLATED',)) for r in run.results)
    return evaluate_probables_v2_run(source_discovery_run_identity='DISCOVERY-LATER',
        universe_identity=run.universe_identity, universe_version=run.universe_version,
        reconciliation_identity=run.reconciliation_identity, reconciliation_version=run.reconciliation_version,
        market_session_identity=run.market_session_identity, analysis_boundary=boundary,
        member_evidence=(), unavailable_members=missing, provenance=('ISOLATED',))


def records_for_unavailable(run):
    return tuple(assess(run_identity=run.run_identity,run_integrity=run.integrity_identity,
        result=r,mapping=None,native=None,created_at=run.analysis_boundary) for r in run.results)


def test_later_population_advances_generation_preserving_history(tmp_path):
    run, _, _, owner, original = publish(tmp_path)
    pointer = owner.store.current_pointer()
    later = later_unavailable_run(run)
    fresh = records_for_unavailable(later)
    owner.store.publish(later,fresh,expected_pointer=pointer)
    new = owner.store.current_pointer()
    assert new['generation'] == 2 and new['previous_pointer_integrity'] == pointer['integrity_sha256']
    assert owner.store.current_run() == fresh and owner.store.load_run(run.run_identity) == original
    with pytest.raises(ValueError,match='NOT_NEWER'):
        owner.store.publish(run,original,expected_pointer=new)
    assert owner.store.current_pointer() == new


def test_later_storage_failure_preserves_prior_pointer(tmp_path,monkeypatch):
    run, _, _, owner, original = publish(tmp_path)
    pointer = owner.store.current_pointer()
    later = later_unavailable_run(run)
    retain = owner.store._io._retain
    def fail(path,payload):
        if path.parent.name == 'runs':
            raise OSError('ISOLATED_MANIFEST_FAILURE')
        return retain(path,payload)
    monkeypatch.setattr(owner.store._io,'_retain',fail)
    with pytest.raises(OSError): owner.store.publish(later,records_for_unavailable(later),expected_pointer=pointer)
    assert owner.store.current_pointer() == pointer and owner.store.current_run() == original
    assert owner.store.records() == original


def test_shared_read_guard_blocks_another_store_publication(tmp_path):
    from threading import Thread,Event
    run, _, _, owner, original = publish(tmp_path)
    later = later_unavailable_run(run)
    records = records_for_unavailable(later)
    started,done = Event(),Event()
    errors = []
    second = Wo08AssessmentStore(tmp_path)
    def write():
        started.set()
        try: second.publish(later,records)
        except Exception as exc: errors.append(exc)
        finally: done.set()
    with owner.store.page_read_scope():
        thread = Thread(target=write);thread.start();assert started.wait(5)
        assert not done.wait(0.05)
        assert owner.store.current_run() == original
    thread.join(10)
    assert done.is_set() and errors == []
    assert owner.store.current_run() == records


@pytest.mark.parametrize('field', ['run_identity','run_integrity','manifest_identity','manifest_integrity','generation'])
def test_pointer_tampering_fails_closed(tmp_path,field):
    *_, owner, records = publish(tmp_path)
    path = owner.store.root/'current.json'
    d=json.loads(path.read_bytes());d[field]='TAMPERED'
    path.write_bytes(canonical(d))
    with pytest.raises(ValueError,match='POINTER'): owner.store.current_run()


@pytest.mark.parametrize('family',['GOLDM','SILVERM','COPPER','CRUDE','NATGAS'])
def test_all_five_mcx_families_bind_exact_contract_and_natgas_held(family):
    from tests.unit.intraday.test_native_pullback_mcx import mcx_source
    source, _, mapping, run, binding, _ = mcx_source(family)
    native = build_decision(source,created_at=run.analysis_boundary)
    item = assess(run_identity=run.run_identity,run_integrity=run.integrity_identity,
        result=run.results[0],mapping=mapping,native=native,created_at=run.analysis_boundary)
    assert item.data['market_family'] == 'MCX'
    assert item.data['exact_mcx_contract_identity'] == binding.active_binding.derivative_contract_id
    assert item.data['exact_mcx_roll_lineage'] == binding.binding_identity
    assert [c['state'] for c in item.data['criteria'][1:]] == ['NOT_COMMISSIONED']*4
    if family == 'NATGAS': assert item.data['hard_gate'] == 'NATGAS_COMMISSIONING_HELD'
    assert all(term not in item.payload for term in (b'NYMEX',b'COMEX',b'WO07F_RECONCILED'))


def test_exact_existing_i1_positive_retains_sources_and_no_overall_promotion():
    from datetime import datetime,time
    from tests.unit.intraday.test_probables_v2 import _later_mapping,_run,CURRENT_DAY,IST
    mapping = _later_mapping(3,0,boundary=datetime.combine(CURRENT_DAY,time(10,45),IST))
    run = _run(mapping)
    native = build_decision(unavailable_source(mapping,run.results[0],run.run_identity,'NO_CONFIRMED_STRUCTURAL_CYCLE'),
        created_at=run.analysis_boundary)
    item = assess(run_identity=run.run_identity,run_integrity=run.integrity_identity,
        result=run.results[0],mapping=mapping,native=native,created_at=run.analysis_boundary)
    i1 = item.data['criteria'][0]
    assert i1['state'] == 'DETERMINISTICALLY_ESTABLISHED'
    assert i1['source_fact_identities'] == [mapping.semantic_evidence.fact(f).fact_identity for f in ('1H_REGIME','15M_STRUCTURE')]
    assert item.data['disposition'] == 'ASSESSMENT_UNAVAILABLE'


def test_native_companion_symlink_is_rejected_without_authority(tmp_path):
    run,mapping,native=population(tmp_path)
    path=native.store.root/'runs'/(run.run_identity+'.json')
    other=tmp_path/'copied-companion.json';other.write_bytes(path.read_bytes())
    path.unlink();path.symlink_to(other)
    owner=Wo08Publication(Wo08AssessmentStore(tmp_path))
    with pytest.raises(ValueError,match='SYMLINK'):
        owner.publish_run(run=run,mapping=mapping,native_publication=native,published_at=run.analysis_boundary)
    assert owner.store.current_pointer() is None and not owner.store.root.exists()


def test_validation_reuse_never_hides_changed_assessment_bytes(tmp_path):
    *_,owner,records=publish(tmp_path)
    original=records[0]
    assert owner.store.load(original.identity)==original
    path=owner.store._record_path(original.identity)
    changed=original.data;changed['criteria'][0]['current_value']='TAMPERED'
    path.write_bytes(canonical(changed))
    with pytest.raises(ValueError,match='INTEGRITY'):owner.store.load(original.identity)
    with pytest.raises(ValueError,match='INTEGRITY'):owner.store.current_run()


def test_validation_reuse_never_hides_changed_manifest_bytes(tmp_path):
    run,_,_,owner,_=publish(tmp_path)
    assert len(owner.store.current_run())==98
    path=owner.store._manifest_path(run.run_identity)
    d=json.loads(path.read_bytes());d['result_identities'].reverse()
    path.write_bytes(canonical(d))
    with pytest.raises(ValueError,match='INTEGRITY'):owner.store.current_run()
