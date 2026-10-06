"""Isolated Sponsor-approved supporting observations, never reference equivalence."""
from copy import deepcopy

import pytest

from kronos.swing.v1 import mcx_native_visual_contract as mcx
from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError, canonical
from tests.unit.swing.v1.test_mcx_native_visual_contract import successor_mappings, successor_answer
from tests.unit.browser.test_swing_review_intake_binding import native_intake


def observation_mappings(family='CRUDEOIL'):
    native, old_reference = successor_mappings((family,))
    value = old_reference.value
    value.update(schema='KRONOS-SWING-MCX-REFERENCE-REVIEW-REQUEST-V3', version='2.1',
                 question_contract_identity='KRONOS-SWING-MCX-REFERENCE-VISUAL-QUESTIONS-V3',
                 question_contract_version='2.1',
                 answer_contract_identity='KRONOS-SWING-MCX-REFERENCE-VISUAL-ANSWER-V3',
                 answer_contract_version='2.1')
    return native, mcx.McxReferenceReviewRequestMapping.create(value)


def observation_answer(native, reference, label='CLX2026'):
    answer = successor_answer(native, reference)
    root = answer['supporting_reference_answer']
    root.update(schema='KRONOS-SWING-MCX-REFERENCE-VISUAL-ANSWER-V3', version='2.1')
    for response in root['subjects'][0]['responses']:
        response.update(question_set_identity='KRONOS-SWING-MCX-REFERENCE-VISUAL-QUESTIONS-V3', question_set_version='2.1')
        obs = response['observations'][0]
        obs.update(observation_status='PARTIAL', ambiguity_reason='Readable dated label; continuous correspondence unestablished.')
        obs['result'].update(observed_identity=label, observed_market='NYMEX', readability='READABLE', identity_correspondence='UNDETERMINED')
    m1,m2,m3 = answer['comparison_answer']['subjects'][0]['observations']
    for obs in (m1,m2,m3):
        obs.update(observation_status='PARTIAL',ambiguity_reason='Reference correspondence unresolved.')
    m1['result'].update(mapping_state='UNDETERMINED',coverage_state='PARTIAL')
    for row in m2['result']['by_timeframe']:
        row.update(relationship='NOT_COMPARABLE')
    m3['result'].update(relationship_to_native_direction='NOT_ESTABLISHED',
                        affected_timeframes=['1D','4H','1H'],limitations=['CONTRACT_IDENTITY_UNCLEAR'])
    return answer


@pytest.mark.parametrize('family,label',[('CRUDEOIL','CLX2026'),('NATURALGAS','NGX2026')])
def test_readable_reference_is_retained_without_equivalence(family,label):
    native,reference=observation_mappings(family)
    answer=observation_answer(native,reference,label)
    request=mcx.mcx_question_pack_from_mappings(native,reference)
    assert mcx.validate_mcx_answer(canonical(answer),request)==answer
    records=mcx.mcx_structured_evidence(canonical(answer),native,reference,'f'*64)
    import json
    reference_records=[json.loads(raw) for raw in records if json.loads(raw)['binding']['role']==mcx.REFERENCE_ROLE]
    assert len(reference_records)==3
    for record in reference_records:
        assert record['version']=='2.1'
        q1=record['response']['observations'][0]['result']
        assert q1['observed_identity']==label and q1['readability']=='READABLE'
        assert q1['identity_correspondence']=='UNDETERMINED'
        assert record['binding']['reference_symbol']!=label


def test_original_v2_does_not_silently_accept_readable_unresolved_reference():
    native,reference=successor_mappings(('CRUDEOIL',))
    answer=successor_answer(native,reference)
    q1=answer['supporting_reference_answer']['subjects'][0]['responses'][0]['observations'][0]
    q1.update(observation_status='PARTIAL',ambiguity_reason='Unestablished dated identity.')
    q1['result'].update(observed_identity='CLX2026',identity_correspondence='UNDETERMINED')
    with pytest.raises(ReviewEvidenceError,match='MCX_IDENTITY_UNAVAILABLE'):
        mcx.validate_mcx_answer(canonical(answer),mcx.mcx_question_pack_from_mappings(native,reference))


@pytest.mark.parametrize('mutation',['venue','unknown_venue','timeframe','wrong_family','native_unresolved',
                                    'native_wrong_family','forced_matched','chart','revision','request',
                                    'agreement','direction','relabel_version'])
def test_observation_path_rejects_invalid_or_authoritative_claims(mutation):
    n,r=observation_mappings()
    a=observation_answer(n,r)
    resp=a['supporting_reference_answer']['subjects'][0]['responses'][0]
    q=resp['observations'][0]['result']
    if mutation=='venue': q['observed_market']='COMEX'
    elif mutation=='unknown_venue': q['observed_market']='UNKNOWN'
    elif mutation=='timeframe': q['observed_timeframe']='4H'
    elif mutation=='wrong_family': q['observed_identity']='NGX2026'
    elif mutation=='native_unresolved': a['subjects'][0]['responses'][0]['observations'][0]['result']['identity_correspondence']='UNDETERMINED'
    elif mutation=='native_wrong_family': a['subjects'][0]['responses'][0]['observations'][0]['result']['observed_identity']='NATURALGAS'
    elif mutation=='forced_matched': q['identity_correspondence']='MATCHED'
    elif mutation=='chart': resp['chart_identity']='NYMEX:NG1!'
    elif mutation=='revision': resp['chart_revision_sha256']='0'*64
    elif mutation=='request': a['supporting_reference_answer']['request_reference']['request_sha256']='0'*64
    elif mutation=='agreement': a['comparison_answer']['subjects'][0]['observations'][1]['result']['by_timeframe'][0]['relationship']='AGREES'
    elif mutation=='direction': a['comparison_answer']['subjects'][0]['observations'][2]['result']['relationship_to_native_direction']='SUPPORTS'
    else: a['supporting_reference_answer']['version']='2.0'
    with pytest.raises(ReviewEvidenceError):
        mcx.validate_mcx_answer(canonical(a),mcx.mcx_question_pack_from_mappings(n,r))


@pytest.mark.parametrize('native_intake',['NSE','GOLDM','SILVERM','COPPER','CRUDEOIL','NATURALGAS'],indirect=True)
def test_real_owner_generation_pdf_import_restart_and_downstream(native_intake,tmp_path):
    from io import BytesIO
    import json
    from hashlib import sha256
    from pypdf import PdfReader
    from tests.unit.browser.test_swing_review_intake_binding import _native_market, _stage_native, _native_answer, _inventory
    from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf
    from kronos.application.swing_visual_v3_live import NativeReviewIntakeWorkflow
    from kronos.swing.v1.analytical_promotion_v2 import evaluate_governed
    from tests.unit.swing.v1.test_analytical_promotion import _path, _extension
    from tests.unit.swing.v1.test_analytical_promotion_v2 import NOW

    w=native_intake
    market=_native_market(w)
    family=w._requirements(market)[0].canonical_instrument
    _stage_native(w,market,family)
    p=w.generate(market,w.expected(market,(family,)))
    answer=_native_answer(w,market,p)
    if market=='MCX':
        assert p.native.value['version']=='2.0' and p.reference.value['version']=='2.1'
        pdf=(w.store.root/p.value['question_pdf_relative_path']).read_bytes()
        text='\n'.join(page.extract_text() or '' for page in PdfReader(BytesIO(pdf)).pages)
        assert 'REFERENCE-VISUAL-QUESTIONS-V3' in text and 'UNDETERMINED' in text
        assert 'KRONOS owns' in text and 'NOT_ESTABLISHED' in text
        if family in ('CRUDEOIL','NATURALGAS'):
            label={'CRUDEOIL':'CLX2026','NATURALGAS':'NGX2026'}[family]
            unresolved=observation_answer(p.native,p.reference,label)
            answer['supporting_reference_answer']=unresolved['supporting_reference_answer']
            answer['comparison_answer']=unresolved['comparison_answer']
    path=tmp_path/'SYNTHETIC-NOT-CHART-ANALYST-ANSWER.pdf'
    _answer_pdf(path,answer)
    expected=w.expected(market,(family,))
    commit=w.import_answer(market,expected,path.read_bytes())
    receipt=commit.receipts[0]
    before=_inventory(tmp_path)
    assert w.import_answer(market,w.expected(market,(family,)),path.read_bytes())==commit
    cold=NativeReviewIntakeWorkflow(w.application,w.native_review,w.live,w.store)
    cold.restore()
    assert cold.store.load_acceptance(commit.identity)==commit
    assert _inventory(tmp_path)==before

    if market=='MCX':
        assert receipt.body['contracts'][1]['answer_contract_version']=='2.1'
        assert receipt.body['contracts'][0]['answer_contract_version']=='2.0'
        refs=[json.loads((w.store.root/item['retained_relative_path']).read_bytes())
              for item in receipt.body['structured_evidence'] if item['role']==mcx.REFERENCE_ROLE]
        assert all(r['schema']==mcx.REFERENCE_EVIDENCE_V3 for r in refs)
        if family in ('CRUDEOIL','NATURALGAS'):
            assert all(r['response']['observations'][0]['result']['observed_identity']==label for r in refs)
    req=w._requirements(market,(family,))[0]
    _,facts,_=w._context()
    completed=w.live.cycle.completed_for(facts.run_identity,family) if market=='NSE' else None
    result=evaluate_governed(requirement=req,facts=facts,
        path_clearance=_path(facts,req,True),extension=_extension(facts,req,False),store=w.store,
        commit_identity=commit.identity,receipt_identity=receipt.receipt_id,
        current_manifest=lambda:'a'*64,created_at=NOW,
        visual=completed.responses if completed else None,nse_request=p.mapping if market=='NSE' else None)
    assert result.value['authority_flags']['execution'] is False
    if family in ('CRUDEOIL','NATURALGAS'):
        assert result.value['confirmation']['state']=='WITHHELD'
        assert 'MCX_MAPPING_NOT_MATCHED' in result.value['confirmation']['reason_codes']
    assert _inventory(tmp_path)==before


def test_reference_v3_preserves_genuinely_missing_identity_exception():
    n,r=observation_mappings()
    a=observation_answer(n,r)
    obs=a['supporting_reference_answer']['subjects'][0]['responses'][0]['observations'][0]
    obs.update(observation_status='UNAVAILABLE',ambiguity_reason='Identity genuinely unreadable in synthetic panel.')
    obs['result'].update(observed_identity=None,readability='UNREADABLE')
    assert mcx.validate_mcx_answer(canonical(a),mcx.mcx_question_pack_from_mappings(n,r))==a


@pytest.mark.parametrize('field,value',[('observed_market','CME'),('observed_timeframe','1W')])
def test_partial_identity_cannot_hide_visible_wrong_venue_or_frame(field,value):
    n,r=observation_mappings();a=observation_answer(n,r)
    obs=a['supporting_reference_answer']['subjects'][0]['responses'][0]['observations'][0]
    obs.update(observation_status='UNAVAILABLE',ambiguity_reason='Synthetic unavailable symbol; other field visibly conflicts.')
    obs['result'].update(observed_identity=None,readability='PARTIAL')
    obs['result'][field]=value
    with pytest.raises(ReviewEvidenceError):
        mcx.validate_mcx_answer(canonical(a),mcx.mcx_question_pack_from_mappings(n,r))


@pytest.mark.parametrize('missing',['observed_market','observed_timeframe'])
def test_partial_identity_preserves_genuinely_missing_field_without_normalizing(missing):
    n,r=observation_mappings();a=observation_answer(n,r)
    obs=a['supporting_reference_answer']['subjects'][0]['responses'][0]['observations'][0]
    obs.update(observation_status='UNAVAILABLE',ambiguity_reason='Synthetic field genuinely not readable.')
    obs['result'].update(readability='PARTIAL')
    obs['result'][missing]=None
    result=mcx.validate_mcx_answer(canonical(a),mcx.mcx_question_pack_from_mappings(n,r))
    retained=result['supporting_reference_answer']['subjects'][0]['responses'][0]['observations'][0]['result']
    assert retained==obs['result'] and retained['observed_identity']=='CLX2026'


@pytest.mark.parametrize('fault',['wrong_family','changed_request','changed_revision','stale_manifest'])
@pytest.mark.parametrize('native_intake',['CRUDEOIL'],indirect=True)
def test_real_import_rejection_has_no_durable_acceptance(native_intake,tmp_path,fault):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from tests.unit.browser.test_swing_review_intake_binding import _stage_native, _native_answer, _inventory
    from tests.unit.browser.test_swing_visual_v3_live import _answer_pdf
    w=native_intake
    _stage_native(w,'MCX','CRUDEOIL')
    p=w.generate('MCX',w.expected('MCX',('CRUDEOIL',)))
    a=_native_answer(w,'MCX',p)
    unresolved=observation_answer(p.native,p.reference)
    a['supporting_reference_answer']=unresolved['supporting_reference_answer']
    a['comparison_answer']=unresolved['comparison_answer']
    if fault=='wrong_family': a['supporting_reference_answer']['subjects'][0]['responses'][0]['observations'][0]['result']['observed_identity']='NGX2026'
    elif fault=='changed_request': a['supporting_reference_answer']['request_reference']['request_identity']='FOREIGN'
    elif fault=='changed_revision': a['supporting_reference_answer']['subjects'][0]['responses'][0]['chart_revision_sha256']='f'*64
    else:
        @contextmanager
        def changed():
            yield SimpleNamespace(control={'current_manifest':{'sha256':'b'*64}},manifest={'run_id':p.native.value['native_run_identity']})
        w.application.publication_mutation_guard=changed
    path=tmp_path/'SYNTHETIC-REJECTED-ANSWER.pdf'
    _answer_pdf(path,a)
    expected=w.expected('MCX',('CRUDEOIL',))
    before=_inventory(w.store.root)
    with pytest.raises(ReviewEvidenceError):
        w.import_answer('MCX',expected,path.read_bytes())
    assert _inventory(w.store.root)==before
    assert w.store.native_acceptance_history('MCX',p.native.value['native_run_identity'])==()
