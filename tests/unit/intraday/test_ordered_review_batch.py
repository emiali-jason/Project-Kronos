"""ADR-0036 isolated batch transport; constructed Answers are not empirical AI evidence."""
from copy import deepcopy
from datetime import timedelta
from io import BytesIO
import json
import pytest
from pypdf import PdfReader

from kronos.application.intraday_review_ordered_batch import validate_envelope
from kronos.intraday.review import ReviewError
from kronos.intraday.chart_input import CORE_CONTENT
from kronos.intraday import visual_contract_v2 as v
from kronos.instrument.visual_identity import (VisualIdentityResolver, VisualIdentitySourceContext,
    VisualIdentityRelationshipStatus, VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    create_visual_identity_relationship, create_visual_identity_publication)
from . import test_review_v2_individual_inbox as ordinary
from .test_review import _png
from .test_analyst_chart_correspondence import observed_panel, ENDPOINTS
from .test_temporal_authority_composition import unknown
from .test_sponsor_question_transport import extract_template
from instrument.test_active_derivative_selection import _resolve
from .test_review_mcx_paired import _resolver
from kronos.intraday.review_mcx_paired import relationship_for_subject

CURRENT = ('YESBANK','JUBLFOOD','VEDL','NIFTY','NTPC','INDIGO','MOTHERSON','LUPIN')


def fixture(tmp_path, monkeypatch, subjects=CURRENT):
    original = ordinary._opening_inputs
    def inputs(*, subject):
        label=subject.removeprefix('NSE-EQ-')
        if label == 'NIFTY':return original(subject='NSE-INDEX-NIFTY')
        if label in ('GOLDM','COPPER','CRUDE','SILVERM'):
            return original(subject='MCX-SUBJECT-'+label,subject_exchange='MCX')
        return original(subject=subject)
    monkeypatch.setattr(ordinary,'_opening_inputs',inputs)
    run,app=ordinary._fixture(tmp_path,subjects,correspondence=False)
    app._chart_input.clock=app._clock
    cycles=[app.review_store.load_cycle(m.cycle_identity) for m in app.review_store.load_current().cycles]
    canonical=tuple(c.canonical_subject_identity for c in cycles if not c.canonical_subject_identity.startswith('MCX'))
    if canonical:
        relationships=tuple(create_visual_identity_relationship(canonical_subject_identity=s,
            observed_visible_subject_identity=s,source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            effective_from=run.analysis_boundary-timedelta(days=1),effective_through=run.analysis_boundary+timedelta(days=1),
            status=VisualIdentityRelationshipStatus.ACTIVE,source_identity='TEST-TRADINGVIEW',provenance=('TEST',s),supersedes=None) for s in canonical)
        resolver=VisualIdentityResolver(create_visual_identity_publication(canonical_subject_identities=canonical,
            publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,publication_version='1.0.0',
            effective_from=run.analysis_boundary-timedelta(days=1),effective_through=run.analysis_boundary+timedelta(days=1),
            source_identities=('TEST-ONLY',),provenance=('TEST',),relationships=relationships,supersedes=None,
            schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1))
        app._visual_identity_resolver=resolver;app._chart_input.resolver=resolver
    for n,c in enumerate(cycles):
        paired=c.canonical_subject_identity.startswith('MCX')
        if paired:
            family=c.canonical_subject_identity.removeprefix('MCX-SUBJECT-')
            binding=_resolve(c.analysis_boundary).for_subject(family).binding
            app._paired.bindings.retain(binding)
            native_resolver = _resolver(binding.active_binding.derivative_contract_id,
                'TEST-EXACT-NATIVE-SERIES',run.analysis_boundary)
            reference = relationship_for_subject(c.canonical_subject_identity)
            reference_relationship = create_visual_identity_relationship(
                canonical_subject_identity=reference.reference_analytical_subject_identity,
                observed_visible_subject_identity='Gold Futures',
                source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
                effective_from=run.analysis_boundary-timedelta(days=1),
                effective_through=run.analysis_boundary+timedelta(days=1),
                status=VisualIdentityRelationshipStatus.ACTIVE,
                source_identity='TEST-TRADINGVIEW-REFERENCE',
                provenance=('TEST', 'REFERENCE'), supersedes=None)
            publication=create_visual_identity_publication(
                canonical_subject_identities=(binding.active_binding.derivative_contract_id,
                    reference.reference_analytical_subject_identity),
                publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
                publication_version='1.0.0',
                effective_from=run.analysis_boundary-timedelta(days=1),
                effective_through=run.analysis_boundary+timedelta(days=1),
                source_identities=('TEST-ONLY',), provenance=('TEST',),
                relationships=(*native_resolver.publication.relationships,
                    reference_relationship), supersedes=None,
                schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1)
            app._paired.native_resolver=VisualIdentityResolver(publication)
        app.upload_chart(c.cycle_identity,media_type='image/png',payload=_png(n+5),
            paired_metadata=app._paired.options(c) if paired else None)
    return app


def completed(result):
    document=json.loads(result.answer_template_path.read_bytes())
    for m in document['candidates']:
        a=m['answer']
        if m['candidate_kind']=='MCX_PAIRED':
            a['native_observed_visible_identity']='TEST-EXACT-NATIVE-SERIES'
            a['reference_observed_visible_identity']='Gold Futures'
            for row in a['chart_observation_header']['panels']:
                row.update(panel_state='PRESENT', right_edge='EXACT')
                role, timeframe = row['slot_role'], row['slot_timeframe']
                row['observed'].update(role=role, timeframe=timeframe,
                    observed_subject=('Gold Futures' if role=='REFERENCE' else
                                      'TEST-EXACT-NATIVE-SERIES'),
                    observed_series=('Gold Futures' if role=='REFERENCE' else None),
                    venue=('COMEX' if role=='REFERENCE' else 'MCX'),
                    currency=('USD' if role=='REFERENCE' else 'INR'),
                    entire_panel_observed=True, opinion_overlays_present=False,
                    content=[[key,'EXACT'] for key in CORE_CONTENT])
            continue
        a['observed_visible_subject_identity']=m['canonical_subject_identity']
        a['global_observation_status']='OBSERVED';m['global_observation_status']='OBSERVED'
        for q,item in zip(v.NSE_QUESTIONS,a['answers'],strict=True):
            item.update(observation_status='OBSERVED',answer='NOT_OBSERVABLE' if q.question_id in ('Q6','Q9') else q.allowed_answers[0],
                visible_timeframes=list(q.timeframe_scope),visible_basis='Constructed qualified chart observation.',status_detail=None,why_not_covered_elsewhere=None)
        for row,(tf,day,start,end) in zip(a['chart_observation_header']['panels'],ENDPOINTS,strict=True):
            row.update(panel_state='PRESENT',right_edge='EXACT',observed=observed_panel('NATIVE',tf,m['canonical_subject_identity'],'NSE',day,start,end))
        unknown({'candidates':[a]})
    return document


def submit(app,result,doc):
    (app._transport.answer_inbox/result.transport.expected_answer_filename).write_text(json.dumps(doc))
    return app.import_all_expected_answers()


def test_current_eight_one_pdf_one_json_and_idempotency(tmp_path,monkeypatch):
    app=fixture(tmp_path,monkeypatch)
    result,=app.create_all_question_transports()
    assert list(app._transport.question_outbox.iterdir())==[result.question_path]
    assert not list(app._transport.answer_inbox.iterdir())
    text,template=extract_template(result.question_path.read_bytes())
    assert template==json.loads(result.answer_template_path.read_bytes())
    assert len(template['candidates'])==8
    assert [m['canonical_subject_identity'] for m in template['candidates']]==[m.canonical_subject_identity for m in app.review_store.load_current().cycles]
    assert {m['canonical_subject_identity'].split('-')[-1] for m in template['candidates']}==set(CURRENT)
    assert text.count('BEGIN EXACT ANSWER JSON')==1
    assert all(m['canonical_subject_identity'] in text for m in template['candidates'])
    assert app.create_all_question_transports()==(result,)
    assert app.snapshot().expected_answer_filename==result.transport.expected_answer_filename
    doc=completed(result);outcome=submit(app,result,doc)
    assert outcome.imported_count==8 and outcome.rejected_count==0,outcome
    assert outcome.state=='COMPLETE'
    assert [m.canonical_subject_identity for m in outcome.members]==[m['canonical_subject_identity'] for m in doc['candidates']]
    assert len(list(app._transport.answer_inbox.iterdir()))==1
    assert submit(app,result,doc).already_imported_count==8
    assert len(list(app._transport.question_outbox.iterdir()))==1


@pytest.mark.parametrize('mutation',['missing','extra','duplicate','order','cycle','chart','pack','identity','run','pointer','batch','version','extra_key','nested_cycle','nested_chart','header_chart'])
def test_structural_binding_failure_before_any_import(tmp_path,monkeypatch,mutation):
    app=fixture(tmp_path,monkeypatch,('LUPIN','NTPC'))
    result,=app.create_all_question_transports();doc=completed(result);members=doc['candidates']
    if mutation=='missing':members.pop()
    elif mutation=='extra':members.append(deepcopy(members[0]))
    elif mutation=='duplicate':members[1]=deepcopy(members[0])
    elif mutation=='order':members.reverse()
    elif mutation in ('cycle','chart','pack','identity'):
        key={'cycle':'review_cycle_identity','chart':'chart_revision_identity','pack':'review_pack_identity','identity':'canonical_subject_identity'}[mutation]
        members[-1][key]='FOREIGN'
    elif mutation in ('run','pointer','batch','version'):
        key={'run':'probables_run_identity','pointer':'review_pointer_identity','batch':'batch_identity','version':'schema_version'}[mutation];doc[key]='FOREIGN'
    elif mutation=='extra_key':doc['unexpected']=True
    elif mutation.startswith('nested_'):members[-1]['answer'][{'nested_cycle':'review_cycle_identity','nested_chart':'chart_revision_identity'}[mutation]]='FOREIGN'
    else:members[-1]['answer']['chart_observation_header']['chart_binding_identity']='FOREIGN'
    outcome=submit(app,result,doc)
    assert outcome.imported_count==0 and outcome.rejected_count==2,outcome
    assert outcome.state=='REJECTED'
    assert not list((app.review_store.root/'visual-evidence').glob('*.json'))


def test_partial_failure_replay_conflict_and_raw_retention(tmp_path,monkeypatch):
    app=fixture(tmp_path,monkeypatch,('LUPIN','NTPC'));result,=app.create_all_question_transports();doc=completed(result)
    doc['candidates'][1]['answer']['answers'][6]['visible_timeframes']=['15M','5M']
    outcome=submit(app,result,doc)
    assert (outcome.imported_count,outcome.rejected_count,outcome.state)==(1,1,'PARTIAL'),outcome
    assert submit(app,result,doc).already_imported_count==1
    doc['candidates'][0]['answer']['answers'][0]['visible_basis']='Different qualified observation.'
    outcome=submit(app,result,doc)
    assert outcome.rejected_count==2
    assert outcome.members[0].reason=='INTRADAY_REVIEW_ANSWER_CONFLICT'
    assert len(list((result.answer_template_path.parent/'attempts').glob('*.json')))==2


@pytest.mark.parametrize('field,value',[('context_sufficient',False),('later_evidence','PRESENT'),('other_contradiction','PRESENT')])
def test_batch_does_not_weaken_temporal_gate(tmp_path,monkeypatch,field,value):
    app=fixture(tmp_path,monkeypatch,('LUPIN',));result,=app.create_all_question_transports();doc=completed(result)
    doc['candidates'][0]['answer']['chart_observation_header']['panels'][0]['observed']['temporal_context'][field]=value
    outcome=submit(app,result,doc);assert outcome.rejected_count==1 and outcome.imported_count==0


def test_stale_chart_and_no_individual_file_fallback(tmp_path,monkeypatch):
    app=fixture(tmp_path,monkeypatch,('LUPIN',));result,=app.create_all_question_transports()
    # An unrelated individual file must not be read by the commissioned batch.
    c=app.review_store.load_current().cycles[0]
    individual=app.create_individual_question_transport(c.cycle_identity)
    (app._transport.answer_inbox/individual.transport.expected_answer_filename).write_bytes(ordinary._completed(individual.answer_template_path))
    assert app.import_all_expected_answers().not_found_count==1
    doc=completed(result);app.upload_chart(c.cycle_identity,media_type='image/png',payload=_png(97))
    assert submit(app,result,doc).rejected_count==1


@pytest.mark.parametrize('family',['GOLDM','CRUDE','COPPER','SILVERM'])
def test_mixed_nse_index_mcx_one_transport_protocol_and_partial(tmp_path,monkeypatch,family):
    app=fixture(tmp_path,monkeypatch,('LUPIN','NIFTY',family));result,=app.create_all_question_transports()
    text,template=extract_template(result.question_path.read_bytes())
    assert len(template['candidates'])==3
    assert {m['candidate_kind'] for m in template['candidates']}=={'NSE','MCX_PAIRED'}
    for required in ('R5 requires','Q10: NONE','X5: NONE','NOT_INDEPENDENTLY_ESTABLISHED','Native contract:','Review cycle:'):assert required in text
    assert len(list(app._transport.question_outbox.iterdir()))==1
    outcome=submit(app,result,completed(result))
    assert (outcome.imported_count,outcome.rejected_count,outcome.state)==(2,1,'PARTIAL'),outcome
    assert outcome.members[-1].state=='REJECTED' or any(m.state=='REJECTED' and m.canonical_subject_identity.startswith('MCX') for m in outcome.members)


def test_duplicate_json_keys_rejected(tmp_path,monkeypatch):
    app=fixture(tmp_path,monkeypatch,('LUPIN',));result,=app.create_all_question_transports()
    raw=json.dumps(completed(result));raw=raw.replace('{','{"schema_version":"1.0.0",',1)
    (app._transport.answer_inbox/result.transport.expected_answer_filename).write_text(raw)
    assert app.import_all_expected_answers().rejected_count==1

from .test_complete_family_workflow import fresh as family_fresh, current_dates
from .test_review_v2_paired_generic import synthetic_commissioning
from tests.unit.instrument.test_complete_visual_identity import CASES


@pytest.mark.parametrize('case',CASES,ids=lambda c:c[0])
def test_five_family_successful_batch_import_exact_authority(tmp_path,current_dates,synthetic_commissioning,case):
    app,cycle,chart,bundle,pack,individual,answer=family_fresh(tmp_path,case)
    before=set(app._transport.question_outbox.iterdir())
    result,=app.create_all_question_transports()
    assert set(app._transport.question_outbox.iterdir())-before=={result.question_path}
    doc=json.loads(result.answer_template_path.read_bytes())
    unknown(answer,paired=True)
    doc['candidates'][0]['answer']=answer
    doc['candidates'][0]['global_observation_status']='OBSERVED'
    outcome=submit(app,result,doc)
    assert outcome.imported_count==1,outcome
    evidence=app._paired.retained_evidence(pack,chart)
    assert evidence.reference_independent_correspondence=='NOT_INDEPENDENTLY_ESTABLISHED'
    assert evidence.reference_role=='SUPPORTING_VISUAL_CONTEXT_ONLY'
    assert evidence.actual_derivative_contract_identity==bundle.native_identity_binding.actual_derivative_contract_identity
    assert evidence.native_resolution.canonical_subject_identity==cycle.canonical_subject_identity
    assert submit(app,result,doc).already_imported_count==1
    answer['native_answers'][0]['visible_basis']='Conflicting new independent description.'
    assert submit(app,result,doc).rejected_count==1


def test_mixed_batch_preserves_per_candidate_result(tmp_path,monkeypatch):
    app=fixture(tmp_path,monkeypatch,('LUPIN','NIFTY','GOLDM'));result,=app.create_all_question_transports();doc=completed(result)
    m=next(m for m in doc['candidates'] if m['candidate_kind']=='MCX_PAIRED');a=m['answer']
    a['native_observed_visible_identity']='TEST-EXACT-NATIVE-SERIES'
    a['reference_observed_visible_identity']='Gold Futures'
    m['global_observation_status']='OBSERVED'
    for q,item in zip(v.MCX_QUESTIONS,[*a['reference_answers'],*a['native_answers'],*a['cross_market_answers'],a['escape_hatch_answer']],strict=True):
        item.update(observation_status='OBSERVED',answer='NOT_OBSERVABLE' if q.question_id in ('R5','M5','X3') else q.allowed_answers[0],
            visible_timeframes=list(q.timeframe_scope),visible_basis='Constructed completed paired observation.',status_detail=None,why_not_covered_elsewhere=None)
    for i,row in enumerate(a['chart_observation_header']['panels']):
        tf=('1D','4H','15M','5M')[i%4]
        obs=observed_panel('REFERENCE' if i<4 else 'NATIVE',tf,'Gold Futures' if i<4 else 'TEST-EXACT-NATIVE-SERIES',
            'COMEX' if i<4 else 'MCX',currency='USD' if i<4 else 'INR')
        row.update(panel_state='PRESENT',right_edge='EXACT',observed=obs)
    unknown(a,paired=True)
    outcome=submit(app,result,doc)
    assert (outcome.imported_count,outcome.rejected_count)==(2,1),outcome
    assert outcome.members[1].reason=='INTRADAY_CHART_CORRESPONDENCE_UNVERIFIABLE'


@pytest.mark.parametrize('malformation',[None,[],123,True,'INVALID'])
def test_malformed_candidate_keeps_earlier_success_truthful(tmp_path,monkeypatch,malformation):
    app=fixture(tmp_path,monkeypatch,('LUPIN','NTPC'));result,=app.create_all_question_transports();doc=completed(result)
    doc['candidates'][1]['answer']['answers']=malformation
    outcome=submit(app,result,doc)
    assert outcome.imported_count==1 and outcome.rejected_count==1,outcome


def test_current_display_matches_exact_batch_order(tmp_path,monkeypatch):
    app=fixture(tmp_path,monkeypatch);result,=app.create_all_question_transports()
    doc=json.loads(result.answer_template_path.read_bytes())
    assert [m.canonical_subject_identity for m in app.snapshot().candidates]==[m['canonical_subject_identity'] for m in doc['candidates']]
