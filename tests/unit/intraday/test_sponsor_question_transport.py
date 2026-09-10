"""FB02/FB03: PDF-only Sponsor input and unchanged strict V2 acceptance."""
from dataclasses import asdict
from io import BytesIO
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from kronos.intraday import visual_contract_v2 as v
from kronos.intraday.review import ObservationStatus as S, ReviewError
from kronos.intraday.review_answer import parse_answer_pack
from kronos.intraday.review_mcx_paired_answer import parse_mcx_paired_answer
from kronos.intraday.review_mcx_paired_transport import create_paired_transport
from kronos.intraday.review_v2 import create_question_pack_v2
from .test_visual_contract_v2 import observation, nse_document
from .test_visual_contract_v2_integration import paired
from .test_review_v2_individual_inbox import _fixture, _cycles, _completed
from .test_review_v2 import _application
from .test_probables_v2 import _opening_inputs
from .test_review import _png


def extract_template(pdf):
    text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
    return text, json.loads(text.split('BEGIN EXACT ANSWER JSON', 1)[1].split('END EXACT ANSWER JSON', 1)[0])


def banknifty_pack(tmp_path):
    *_, mapping = _opening_inputs(subject='NSE-INDEX-BANKNIFTY')
    run, app = _application(tmp_path, mapping)
    cycle = app.create_eligible_cycles(run)[0]
    chart = app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(77))
    return create_question_pack_v2(app.review_store.load_handoff(cycle.handoff_identity), cycle, chart,
        question_version=v.VERSION, completed_selection=mapping.completed_evidence)


@pytest.mark.parametrize('state', ['invalid_observed', 'partial', 'all_four', 'partial_no_detail', 'partial_wrong_global'])
def test_exact_banknifty_q7_failure_class(tmp_path, state):
    pack = banknifty_pack(tmp_path)
    doc = nse_document(pack)
    doc['observed_visible_subject_identity'] = 'Nifty Bank Index'
    q7 = doc['answers'][6]
    if state != 'all_four':
        q7['visible_timeframes'] = ['15M', '5M']
    if state.startswith('partial'):
        q7['observation_status'] = 'PARTIAL'
        q7['status_detail'] = None if state == 'partial_no_detail' else 'Only the completed 15M and 5M scope is genuinely assessable; 1D/1H space is not established.'
        doc['global_observation_status'] = 'OBSERVED' if state == 'partial_wrong_global' else 'PARTIAL'
    if state in ('partial', 'all_four'):
        parsed = parse_answer_pack(json.dumps(doc).encode())
        assert parsed.expected_canonical_subject_identity == 'NSE-INDEX-BANKNIFTY'
        assert parsed.answers[6].visible_timeframes == tuple(q7['visible_timeframes'])
    else:
        with pytest.raises(ReviewError): parse_answer_pack(json.dumps(doc).encode())


MULTI = tuple(q for q in v.NSE_QUESTIONS + v.MCX_QUESTIONS if len(q.timeframe_scope) > 1)
@pytest.mark.parametrize('question', MULTI, ids=lambda q:q.question_id)
@pytest.mark.parametrize('mode', ['full', 'partial', 'incomplete_observed', 'missing_detail', 'reversed', 'duplicate'])
def test_all_multiscope_questions_keep_strict_scope(question, mode):
    fields = asdict(observation(question))
    fields['visible_timeframes'] = tuple(fields['visible_timeframes'])
    if mode in ('partial', 'incomplete_observed', 'missing_detail'):
        fields['visible_timeframes'] = question.timeframe_scope[-1:]
    if mode in ('partial', 'missing_detail'):
        fields['observation_status'] = S.PARTIAL
        fields['status_detail'] = 'Only this qualified scope can be assessed.' if mode == 'partial' else None
    if mode == 'reversed': fields['visible_timeframes'] = question.timeframe_scope[::-1]
    if mode == 'duplicate': fields['visible_timeframes'] = question.timeframe_scope + question.timeframe_scope[-1:]
    if mode in ('full', 'partial'):
        assert v.VisualObservationV2(**fields).visible_timeframes == fields['visible_timeframes']
    else:
        with pytest.raises(ReviewError): v.VisualObservationV2(**fields)


@pytest.mark.parametrize('question', [v.NSE_QUESTIONS[-1], v.MCX_QUESTIONS[-1]], ids=lambda q:q.question_id)
@pytest.mark.parametrize('answer,why,valid', [('NONE',None,True),('NONE','Invented explanation',False),('MATERIAL_OBSERVATION',None,False),('MATERIAL_OBSERVATION','Separate material fact not covered by earlier questions.',True)])
def test_exact_escape_hatch_rules(question, answer, why, valid):
    fields=asdict(observation(question,answer=answer));fields['why_not_covered_elsewhere']=why
    if valid: assert v.VisualObservationV2(**fields).answer == answer
    else:
        with pytest.raises(ReviewError): v.VisualObservationV2(**fields)


def test_individual_pdf_only_roundtrip_exact_inbox_and_internal_retention(tmp_path):
    _,app=_fixture(tmp_path,('BDL',))
    cycle=_cycles(app)['BDL'].cycle_identity
    app.upload_chart(cycle,media_type='image/png',payload=_png(17))
    result=app.create_individual_question_transport(cycle)
    assert tuple(app._transport.question_outbox.iterdir()) == (result.question_path,)
    text,doc=extract_template(result.question_path.read_bytes())
    assert doc == json.loads(result.answer_template_path.read_bytes())
    assert 'accompanying prepopulated' not in text
    for required in ('Chart Analyst Answer Protocol','PARTIAL','status_detail','NOT_ESTABLISHED','SELECTED_Q6_Q9_ANCHOR = NOT_ESTABLISHED','PREVIOUS_COMPLETED_DAILY_HIGH','source '): assert required in text
    assert result.answer_template_path.is_relative_to(app.review_store.root)
    assert not list(app._transport.answer_inbox.iterdir())
    # Sponsor sees only the PDF. Complete a temporary extracted template, never
    # read the internal store to construct the Answer submitted to the inbox.
    extracted=tmp_path/'extracted-template.json';extracted.write_text(json.dumps(doc))
    answer=_completed(extracted)
    wrong=app._transport.answer_inbox/'wrong_ANSWERS.json';wrong.write_bytes(answer)
    assert app.import_expected_answer(cycle).not_found_count == 1
    expected=app._transport.answer_inbox/result.transport.expected_answer_filename;expected.write_bytes(answer)
    assert app.import_expected_answer(cycle).imported_count == 1
    assert app.import_expected_answer(cycle).already_imported_count == 1
    assert app.create_individual_question_transport(cycle) == result


def test_batch_produces_one_pdf_and_one_combined_answer(tmp_path):
    _,app=_fixture(tmp_path,('BDL','SRF','TITAN'))
    for n,c in enumerate(_cycles(app).values()):
        app.upload_chart(c.cycle_identity,media_type='image/png',payload=_png(n))
    result,=app.create_all_question_transports()
    assert list(app._transport.question_outbox.iterdir())==[result.question_path]
    assert len(extract_template(result.question_path.read_bytes())[1]['candidates'])==3
    assert app.create_all_question_transports()==(result,)
    document=json.loads(result.answer_template_path.read_bytes())
    # Historical pre-header observer fixtures remain valid under unchanged gates.
    for member in document['candidates']:
        path=tmp_path/'isolated-candidate.json'
        path.write_text(json.dumps({'candidates':[member['answer']]}))
        member['answer']=json.loads(_completed(path))['candidates'][0]
        member['global_observation_status']='OBSERVED'
    (app._transport.answer_inbox/result.transport.expected_answer_filename).write_text(json.dumps(document))
    assert app.import_all_expected_answers().imported_count==3
    assert len(list(app._transport.answer_inbox.iterdir()))==1


def test_batch_missing_chart_does_not_publish_other_candidates(tmp_path):
    _,app=_fixture(tmp_path,('BDL','SRF'))
    app.upload_chart(_cycles(app)['BDL'].cycle_identity,media_type='image/png',payload=_png(1))
    with pytest.raises(ReviewError):app.create_all_question_transports()
    assert not app._transport.question_outbox.exists()


def test_mcx_pdf_embeds_exact_envelope_and_multiscope_protocol(tmp_path):
    cycle,active,np,rp,native,reference,bundle,old,pack,doc=paired(tmp_path)
    transport,pdf,template=create_paired_transport(pack=pack,bundle=bundle,native_chart_payload=np,reference_chart_payload=rp,generated_at=pack.created_at,supporting_reference_only=True)
    text,extracted=extract_template(pdf)
    assert extracted==json.loads(template)
    assert 'global_observation_status' not in extracted
    for required in ('R5 requires 4H/15M/5M','M5 requires 15M/5M','X1-X5','BOTH roles','NOT_INDEPENDENTLY_ESTABLISHED','X5: NONE','why_not_covered_elsewhere'):assert required in text
    assert '1H' not in text
    assert parse_mcx_paired_answer(json.dumps(doc).encode()).question_set_version==v.VERSION
    doc['cross_market_answers'][0].update(observation_status='PARTIAL',visible_timeframes=['15M','5M'],status_detail='Both roles assessed only on completed 15M/5M.')
    assert parse_mcx_paired_answer(json.dumps(doc).encode()).cross_market_answers[0].observation_status is S.PARTIAL
    doc['cross_market_answers'][0]['observation_status']='OBSERVED'
    with pytest.raises(ReviewError):parse_mcx_paired_answer(json.dumps(doc).encode())


def test_pdf_fixture_export_for_visual_qualification(tmp_path):
    import os
    target=os.environ.get('WO07E_PDF_FIXTURES')
    if not target: return
    output=Path(target);output.mkdir(parents=True,exist_ok=True)
    _,app=_fixture(tmp_path,('BDL',));cycle=_cycles(app)['BDL'].cycle_identity
    app.upload_chart(cycle,media_type='image/png',payload=_png(19))
    result=app.create_individual_question_transport(cycle)
    (output/'nse-question.pdf').write_bytes(result.question_path.read_bytes())
    _,_,np,rp,_,_,bundle,_,pack,_=paired(tmp_path)
    _,pdf,_=create_paired_transport(pack=pack,bundle=bundle,native_chart_payload=np,reference_chart_payload=rp,generated_at=pack.created_at,supporting_reference_only=True)
    (output/'mcx-question.pdf').write_bytes(pdf)


from .test_mcx_asymmetric_correspondence import fixture as mcx_fixture
from .test_review_v2_paired_generic import synthetic_commissioning
from kronos.intraday.review_mcx_paired import MCX_REFERENCE_RELATIONSHIPS


@pytest.mark.parametrize('family', [r.canonical_mcx_subject_identity.removeprefix('MCX-SUBJECT-') for r in MCX_REFERENCE_RELATIONSHIPS])
def test_five_family_pdf_only_transport_real_gate(tmp_path, synthetic_commissioning, family):
    app,cycle,chart,bundle,receipt,result,rows=mcx_fixture(tmp_path,family)
    assert tuple(app._transport.question_outbox.iterdir()) == (result.question_path,)
    text,doc=extract_template(result.question_path.read_bytes())
    assert doc == json.loads(result.answer_template_path.read_bytes())
    assert doc['canonical_mcx_subject_identity'] == cycle.canonical_subject_identity
    assert 'NOT_INDEPENDENTLY_ESTABLISHED' in text
    batch, = app.create_all_question_transports()
    assert len(extract_template(batch.question_path.read_bytes())[1]["candidates"]) == 1
    assert app.import_expected_answer(cycle.cycle_identity).imported_count==1
    evidence=app._paired.store.load_evidence_for_pack(result.transport.review_pack_identity)
    assert all(row[3]=='NOT_INDEPENDENTLY_ESTABLISHED' and row[4] is None
               for row in evidence.chart_correspondence if row[0]=='REFERENCE')
    assert all(row[3]=='VALIDATED' and row[4] for row in evidence.chart_correspondence if row[0]=='NATIVE')
    assert app.import_expected_answer(cycle.cycle_identity).already_imported_count==1


def test_existing_transport_reexport_never_rewrites_retained_pdf(tmp_path):
    _,app=_fixture(tmp_path,('BDL',))
    cycle=_cycles(app)['BDL'].cycle_identity
    app.upload_chart(cycle,media_type='image/png',payload=_png(21))
    first=app.create_individual_question_transport(cycle)
    before={p.relative_to(app.review_store.root):p.read_bytes() for p in app.review_store.root.rglob('*') if p.is_file()}
    first.question_path.unlink()  # External fixture copy only, not retained evidence.
    result=app.create_individual_question_transport(cycle)
    assert result == first
    assert result.question_path.read_bytes()==app.review_store.load_transport_question_pdf(result.transport)
    assert before == {p.relative_to(app.review_store.root):p.read_bytes() for p in app.review_store.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('old_version', ['2.0.0', '2.2.0'])
def test_existing_nse_pack_gets_successor_without_rewriting_history(tmp_path, monkeypatch, old_version):
    from kronos.intraday import review_v2_transport as transport_module
    _, app = _fixture(tmp_path, ('BDL',))
    cycle = _cycles(app)['BDL'].cycle_identity
    app.upload_chart(cycle, media_type='image/png', payload=_png(22))
    with monkeypatch.context() as patch:
        patch.setattr(transport_module, 'REVIEW_BATCH_TRANSPORT_V2_VERSION', old_version)
        old = app.create_individual_question_transport(cycle)
    before = {p: p.read_bytes() for p in app.review_store.root.rglob('*') if p.is_file()}
    assert old.transport.schema_version == old_version
    current = app.create_individual_question_transport(cycle)
    assert current.transport.schema_version == '2.3.0'
    assert current.transport.review_pack_identities == old.transport.review_pack_identities
    assert current.transport.review_batch_identity == old.transport.review_batch_identity
    assert current.transport.expected_answer_filename != old.transport.expected_answer_filename
    assert current.answer_template_path.read_bytes() == old.answer_template_path.read_bytes()
    assert all(p.read_bytes() == data for p, data in before.items())
    assert app.review_store.load_transport(old.transport.transport_identity) == old.transport
    assert app.create_individual_question_transport(cycle) == current
    inbox = app._transport.answer_inbox
    (inbox / old.transport.expected_answer_filename).write_bytes(_completed(old.answer_template_path))
    assert app.import_expected_answer(cycle).not_found_count == 1
    (inbox / current.transport.expected_answer_filename).write_bytes(_completed(current.answer_template_path))
    assert app.import_expected_answer(cycle).imported_count == 1


@pytest.mark.parametrize('old_version', ['1.0.0', '1.2.0'])
def test_existing_mcx_pack_gets_successor_without_rewriting_history(tmp_path, synthetic_commissioning, monkeypatch, old_version):
    from kronos.intraday import review_mcx_paired_transport as transport_module
    from .test_review_v2_paired_intake import complete_paired
    with monkeypatch.context() as patch:
        patch.setattr(transport_module, 'MCX_PAIRED_TRANSPORT_VERSION', old_version)
        app, cycle, chart, bundle, receipt, old, rows = mcx_fixture(tmp_path)
    store = app._paired.store
    before = {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
    assert old.transport.schema_version == old_version
    current = app.create_individual_question_transport(cycle.cycle_identity)
    assert current.transport.schema_version == '1.3.0'
    assert current.transport.review_pack_identity == old.transport.review_pack_identity
    assert current.transport.expected_answer_filename != old.transport.expected_answer_filename
    assert current.answer_template_path.read_bytes() == old.answer_template_path.read_bytes()
    assert all(p.read_bytes() == data for p, data in before.items())
    assert store.load_transport(old.transport.transport_identity) == old.transport
    assert store.load_transport_for_pack(current.transport.review_pack_identity) == current.transport
    assert app.create_individual_question_transport(cycle.cycle_identity) == current
    # The fixture left a valid old-edition Answer: exact lookup must not use it.
    assert app.import_expected_answer(cycle.cycle_identity).not_found_count == 1
    complete_paired(app, current, reference='TEST-LISTED-GOLDM')
    assert app.import_expected_answer(cycle.cycle_identity).imported_count == 1
