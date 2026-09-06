"""Paired Review V2 intake, reference context and immutable restoration."""
from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256
import json

import pytest

from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_v2_transport import IntradayReviewV2Transport
from kronos.intraday.review_v2 import (create_chart_intake_request_v2, create_chart_revision_v2,
    create_current_chart_pointer_v2, artifact_bytes_v2, artifact_from_bytes_v2)
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.instrument.visual_identity_persistence import load_visual_identity_resolver
from kronos.instrument.visual_identity import VisualIdentitySourceContext, VisualIdentityResolutionError
from .test_probables_v2 import _opening_inputs
from .test_review_v2 import _run
from .test_review import _png
from .test_review_mcx_paired import _resolver
from instrument.test_active_derivative_selection import _resolve


def paired_fixture(tmp_path, *, family="GOLDM", visible="TEST-EXACT-NATIVE-SERIES"):
    mapping = _opening_inputs(subject=f"MCX-SUBJECT-{family}", subject_exchange="MCX")[-1]
    run = _run(mapping)
    probables = ProbablesV2Store(tmp_path / "probables")
    probables.retain_complete(run=run, mappings=(mapping,))
    review = IntradayReviewV2Store(tmp_path / "review-v2")
    transport = IntradayReviewV2Transport(question_outbox=tmp_path / "questions", answer_inbox=tmp_path / "answers")
    app = IntradayReviewV2Application(probables_store=probables, review_store=review,
        transport=transport, clock=lambda: run.analysis_boundary + timedelta(minutes=2))
    cycle = app.create_eligible_cycles(run)[0]
    binding = _resolve(cycle.analysis_boundary).for_subject(family).binding
    app._paired.bindings.retain(binding)
    app._paired.native_resolver = _resolver(binding.active_binding.derivative_contract_id,
        visible, run.analysis_boundary)
    for ordinal in (1, 2, 3):
        payload = _png(ordinal)
        request = create_chart_intake_request_v2(cycle, payload=payload, media_type="image/png", requested_at=app._clock())
        chart = create_chart_revision_v2(cycle, revision_ordinal=ordinal, payload=payload,
            media_type="image/png", received_at=app._clock(), request_identity=request.request_identity)
        review.retain_chart_request(request); review.retain_chart(chart, payload)
        review.save_current_chart(create_current_chart_pointer_v2(cycle, request, chart))
    return app, cycle, app._paired.options(cycle)


def complete_paired(app, result, native="TEST-EXACT-NATIVE-SERIES", reference="Observed listed series - not a membership claim"):
    doc = json.loads(result.answer_template_path.read_bytes())
    doc["native_observed_visible_identity"] = native
    doc["reference_observed_visible_identity"] = reference
    payload = json.dumps(doc, sort_keys=True).encode()
    (app._transport.answer_inbox / result.transport.expected_answer_filename).write_bytes(payload)
    return payload


def test_revision_four_restores_metadata_and_preserves_legacy(tmp_path):
    app, cycle, metadata = paired_fixture(tmp_path)
    before = {p.name:p.read_bytes() for p in (app.review_store.root / "chart-revisions").glob('*.json')}
    assert app.snapshot().candidates[0].chart_state == "CHART_REQUIRED"
    chart = app.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(3), paired_metadata=metadata)
    assert chart.revision_ordinal == 4
    assert chart.schema_version == "2.1.0"
    assert chart.timeframe_set == ("1D", "4H", "15M", "5M")
    assert artifact_from_bytes_v2(artifact_bytes_v2(chart)) == chart
    bundle, native, reference = app._paired.restore(cycle, chart)
    assert bundle.native_identity_binding.active_binding_identity == metadata["native_binding_identity"]
    assert bundle.reference_relationship.governed_visible_identity == metadata["reference_context_identity"]
    assert reference.listed_contract_identity is None
    assert app.review_store.load_current_chart(cycle.cycle_identity).revision_ordinal == 4
    for name, content in before.items():
        assert (app.review_store.root / "chart-revisions" / name).read_bytes() == content
        assert artifact_from_bytes_v2(content).paired_bundle_identity is None
    assert app.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(3), paired_metadata=metadata) == chart


@pytest.mark.parametrize("change", [None, {}, {"native_binding_identity":"FOREIGN"},
    {"native_contract_identity":"MCX-FUT-FOREIGN"}, {"reference_context_identity":"UNKNOWN"},
    {"reference_context_identity":"NYMEX:CL1!"}])
def test_invalid_metadata_cannot_move_current_pointer(tmp_path, change):
    app, cycle, metadata = paired_fixture(tmp_path)
    supplied = None if change is None else ({} if not change else {**metadata, **change})
    before = app.review_store.load_current_chart(cycle.cycle_identity)
    with pytest.raises(ReviewError):
        app.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(9), paired_metadata=supplied)
    assert app.review_store.load_current_chart(cycle.cycle_identity) == before


def test_paired_answer_observation_needs_no_constituent_authority(tmp_path):
    app, cycle, metadata = paired_fixture(tmp_path)
    chart = app.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(4), paired_metadata=metadata)
    result = app.create_individual_question_transport(cycle.cycle_identity)
    assert result == app.create_individual_question_transport(cycle.cycle_identity)
    document = json.loads(result.answer_template_path.read_bytes())
    assert document['schema_identity'] == 'KRONOS-INTRADAY-MCX-PAIRED-ANSWER-PACK-V1'
    assert document['reference_observed_visible_identity'].startswith('REPLACE_')
    complete_paired(app, result, reference="CLV2026 (observed only)")
    outcome = app.import_expected_answer(cycle.cycle_identity)
    assert (outcome.imported_count, outcome.rejected_count) == (1, 0)
    pack = app._paired.retained(cycle, chart)[3]
    evidence = app._paired.store.load_evidence_for_pack(pack.review_pack_identity)
    assert evidence.reference_resolution is None
    assert evidence.reference_constituent_relationship == "NOT_ESTABLISHED"
    assert evidence.reference_role == "SUPPORTING_ONLY"
    assert evidence.reference_observed_visible_identity == "CLV2026 (observed only)"
    assert evidence.native_resolution.canonical_subject_identity == metadata['native_contract_identity']
    assert app.import_expected_answer(cycle.cycle_identity).already_imported_count == 1
    assert app.snapshot().candidates[0].answer_state == 'IMPORTED'


@pytest.mark.parametrize('native', ['TEST-WRONG-JUNE-SERIES', 'COMEX:GC1!', 'MCX-SUBJECT-GOLDM'])
def test_native_visual_truth_cannot_be_overridden_by_metadata(tmp_path, native):
    app, cycle, metadata = paired_fixture(tmp_path)
    app.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(4), paired_metadata=metadata)
    result = app.create_individual_question_transport(cycle.cycle_identity)
    complete_paired(app, result, native=native)
    outcome = app.import_expected_answer(cycle.cycle_identity)
    assert outcome.rejected_count == 1
    assert outcome.imported_count == 0


def test_failed_persistence_keeps_previous_pointer(tmp_path, monkeypatch):
    app, cycle, metadata = paired_fixture(tmp_path)
    before = app.review_store.load_current_chart(cycle.cycle_identity)
    def fail(*args): raise OSError('TEST_ONLY')
    monkeypatch.setattr(app.review_store, 'retain_chart', fail)
    with pytest.raises(OSError):
        app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(4), paired_metadata=metadata)
    assert app.review_store.load_current_chart(cycle.cycle_identity) == before


def test_tampered_chart_or_bundle_is_not_restored(tmp_path):
    app, cycle, metadata = paired_fixture(tmp_path)
    chart = app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(4), paired_metadata=metadata)
    with pytest.raises(ReviewError): replace(chart, paired_bundle_identity='INTRADAY-MCX-PAIRED-CHART-BUNDLE-FOREIGN')
    bundle = app._paired.restore(cycle, chart)[0]
    with pytest.raises(ReviewError): replace(bundle, canonical_mcx_subject_identity='MCX-SUBJECT-CRUDE')


@pytest.mark.parametrize('observed', ['CRUDEOILM2026', 'CRUDEOILU2027', 'CRUDEOIL26SEPFUT', 'MCX-FUT-CRUDE-2026-09-21', 'CRUDEOILU2026 '])
def test_native_publication_exact_negatives(observed):
    resolver = load_visual_identity_resolver(publication_version='1.4.0')
    with pytest.raises(VisualIdentityResolutionError):
        resolver.resolve(observed_visible_subject_identity=observed,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=datetime.fromisoformat('2026-09-06T03:45:00+00:00'))


def test_native_publication_has_no_historical_backdating():
    resolver = load_visual_identity_resolver(publication_version='1.4.0')
    start = datetime.fromisoformat('2026-09-06T03:42:35.870569+00:00')
    def resolve(boundary):
        return resolver.resolve(observed_visible_subject_identity='CRUDEOILU2026',
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            governed_observation_boundary=boundary)
    with pytest.raises(VisualIdentityResolutionError): resolve(start-timedelta(microseconds=1))
    assert resolve(start).canonical_subject_identity == 'MCX-FUT-CRUDE-2026-09-21'
    assert len(resolver.publication.relationships) == 1
    assert any('SPONSOR' in p for p in resolver.publication.relationships[0].provenance)
    with pytest.raises(VisualIdentityResolutionError):
        resolve(datetime.fromisoformat('2026-09-21T18:00:00.000001+00:00'))


def test_paired_snapshot_is_read_only_and_does_not_regenerate_pdf(tmp_path, monkeypatch):
    app, cycle, metadata = paired_fixture(tmp_path)
    app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(4), paired_metadata=metadata)
    app.create_individual_question_transport(cycle.cycle_identity)
    def forbidden(*a, **k): raise AssertionError('GET_MUST_NOT_GENERATE_OR_READ_INBOX')
    monkeypatch.setattr('kronos.application.intraday_review_v2_paired.create_paired_transport', forbidden)
    monkeypatch.setattr(app._transport, 'read_expected_answer', forbidden)
    assert app.snapshot().candidates[0].question_pack_state == 'TRANSPORT_READY'


def test_expired_native_binding_cannot_append_revision(tmp_path):
    app, cycle, metadata = paired_fixture(tmp_path)
    binding = app._paired.validate_metadata(cycle, metadata)
    app._clock = lambda: binding.expiry_eligibility_boundary + timedelta(microseconds=1)
    previous = app.review_store.load_current_chart(cycle.cycle_identity)
    with pytest.raises(ReviewError):
        app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(4), paired_metadata=metadata)
    assert app.review_store.load_current_chart(cycle.cycle_identity) == previous


def test_old_paired_answer_cannot_follow_replaced_chart(tmp_path):
    app, cycle, metadata = paired_fixture(tmp_path)
    app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(4), paired_metadata=metadata)
    old = app.create_individual_question_transport(cycle.cycle_identity)
    complete_paired(app, old)
    app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(5), paired_metadata=metadata)
    new = app.create_individual_question_transport(cycle.cycle_identity)
    assert old.transport.expected_answer_filename != new.transport.expected_answer_filename
    result = app.import_expected_answer(cycle.cycle_identity)
    assert result.not_found_count == 1 and result.imported_count == 0


def test_native_relationship_identity_restores_and_tamper_rejects():
    from kronos.instrument.visual_identity import encode_visual_identity_publication, parse_visual_identity_publication
    resolver = load_visual_identity_resolver(publication_version='1.4.0')
    original = resolver.publication
    restored = parse_visual_identity_publication(encode_visual_identity_publication(original), canonical_subject_identities=('MCX-FUT-CRUDE-2026-09-21',))
    assert restored.relationships == original.relationships
    doc = json.loads(encode_visual_identity_publication(original))
    doc['relationships'][0]['observed_visible_subject_identity'] = 'CRUDEOILM2026'
    with pytest.raises(VisualIdentityResolutionError):
        parse_visual_identity_publication(json.dumps(doc).encode(), canonical_subject_identities=('MCX-FUT-CRUDE-2026-09-21',))


def test_mixed_batch_create_and_import_exact_nse_and_paired_answers(tmp_path, monkeypatch):
    from . import test_review_v2_individual_inbox as ordinary
    opening = ordinary._opening_inputs
    def mixed_inputs(*, subject):
        return opening(subject='MCX-SUBJECT-GOLDM', subject_exchange='MCX') if subject == 'NSE-EQ-CRUDE' else opening(subject=subject)
    monkeypatch.setattr(ordinary, '_opening_inputs', mixed_inputs)
    run, app = ordinary._fixture(tmp_path, subjects=('BDL', 'CRUDE'))
    cycles = [app.review_store.load_cycle(c.cycle_identity) for c in app.snapshot().candidates]
    mcx = next(c for c in cycles if c.canonical_subject_identity.startswith('MCX-SUBJECT-'))
    binding = _resolve(mcx.analysis_boundary).for_subject('GOLDM').binding
    app._paired.bindings.retain(binding)
    app._paired.native_resolver = _resolver(binding.active_binding.derivative_contract_id, 'TEST-EXACT-NATIVE-SERIES', run.analysis_boundary)
    for cycle in cycles:
        app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(1),
            paired_metadata=app._paired.options(cycle) if cycle == mcx else None)
    batch = app.create_combined_question_transport()
    assert batch.transport.candidate_count == 1
    (app._transport.answer_inbox / batch.transport.expected_answer_filename).write_bytes(ordinary._completed(batch.answer_template_path))
    # Partial combined availability must import its NSE member before MCX exists.
    partial = app.import_all_expected_answers()
    assert partial.imported_count == 1 and partial.not_found_count == 1
    paired = app.create_individual_question_transport(mcx.cycle_identity)
    complete_paired(app, paired)
    result = app.import_all_expected_answers()
    assert result.expected_count == 2 and result.found_count == 2
    assert result.imported_count == 1 and result.already_imported_count == 1
    assert result.rejected_count == 0
    # Imported paired Review evidence does not silently enter the generic WO-10 adapter.
    selected = app.current_reconciliation()
    assert len(selected.requests) == 1
    from kronos.browser.intraday_views import _review_v2_projection
    page = _review_v2_projection(app.snapshot(), run, {
        'currentness_state':'REVIEW_CURRENT', 'reconciliation':selected.status_document()})
    assert 'Answer ready: 2 / 2' in page
    assert 'Reconcile eligible: 1 / 2' in page


@pytest.mark.parametrize('mime', ['image/png', 'image/jpeg'])
def test_browser_paired_metadata_uses_one_validated_chart_route(tmp_path, mime):
    from kronos.browser.intraday_review_v2_control import IntradayReviewV2OperationalControl
    from kronos.intraday.review_v2_operation_persistence import ReviewV2OperationProvenanceStore
    from kronos.browser.product_routes import BrowserPostRequest
    from tests.unit.browser.test_intraday_review_workflow import _routes
    from tests.unit.browser.test_product_route_isolation import _snapshot
    from tests.unit.browser.test_intraday_chart_clipboard import _image
    app, cycle, metadata = paired_fixture(tmp_path / 'paired')
    _, _, _, routes = _routes(tmp_path / 'browser')
    routes._review_v2_control = IntradayReviewV2OperationalControl(app, ReviewV2OperationProvenanceStore(app.review_store.root))
    route = '/control/intraday-review/v2/chart'
    payload = _image('JPEG' if mime.endswith('jpeg') else 'PNG')
    query = {'cycle':[cycle.cycle_identity], **{k:[v] for k,v in metadata.items()}}
    response = routes.handle_post(BrowserPostRequest(route, query, mime, payload), _snapshot)
    assert response.status == 200
    current = app.review_store.load_current_chart(cycle.cycle_identity)
    assert current.revision_ordinal == 4
    for field, values in [('native_contract_identity',['FOREIGN']), ('reference_context_identity',['UNKNOWN']),
                          ('native_binding_identity',[metadata['native_binding_identity'], metadata['native_binding_identity']])]:
        invalid = {**query, field:values}
        rejected = routes.handle_post(BrowserPostRequest(route, invalid, mime, payload), _snapshot)
        assert rejected.status >= 400 and 'Traceback' not in rejected.body
        assert app.review_store.load_current_chart(cycle.cycle_identity) == current


@pytest.mark.parametrize('action,mime,missing', [('paste','image/png',False), ('paste','image/jpeg',False),
    ('file','image/png',False), ('file','image/jpeg',False), ('paste','image/png',True), ('file','image/png',True)])
def test_paste_and_file_send_identical_governed_metadata(action, mime, missing):
    import shutil, subprocess
    from kronos.browser.intraday_views import _review_v2_chart_script
    node = shutil.which('node')
    assert node is not None
    script = _review_v2_chart_script().removeprefix('<script>').removesuffix('</script>')
    harness = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const listeners={},requests=[],feedback={hidden:true,textContent:''};
const native={value:'MCX-FUT-TEST',selectedOptions:[{dataset:{binding:'ACTIVE-DERIVATIVE-BINDING-TEST'}}]};
const reference={value:MISSING?'':'TEST:CONTINUOUS'};
const card={id:'review-candidate-TEST',querySelector:s=>s.includes('native')?native:reference};
const target={id:'chart-1',dataset:{uploadUrl:'/control/intraday-review/v2/chart?cycle=CYCLE-1',mcxPaired:'true'},attrs:{},
 addEventListener:(n,f)=>listeners[n]=f,focus:()=>document.activeElement=target,
 getAttribute:n=>target.attrs[n],setAttribute:(n,v)=>target.attrs[n]=v,removeAttribute:n=>delete target.attrs[n],
 hasAttribute:n=>n==='data-review-v2-chart',closest:()=>card};
const file={type:MIME,size:100},input={dataset:{target:'chart-1'},files:[file],addEventListener:(n,f)=>listeners['file-'+n]=f};
const document={activeElement:target,getElementById:id=>id==='chart-1'?target:feedback,
 querySelectorAll:s=>s==='[data-review-v2-chart]'?[target]:[input]};
const context={document,URL,Set,Array,location:{href:'http://localhost/intraday/review',origin:'http://localhost',pathname:'/intraday/review',search:'',reload(){}},history:{replaceState(){}},
 fetch:async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({outcome:'CHART_RECEIVED',cycle_identity:'CYCLE-1'})};}};
vm.runInNewContext(SCRIPT,context);
if(ACTION==='file')listeners['file-change']();else listeners.paste({preventDefault(){},clipboardData:{items:[{kind:'file',type:MIME,getAsFile:()=>file}]}});
setImmediate(()=>{assert.equal(requests.length,MISSING?0:1);if(!MISSING){const q=new URL(requests[0].url,'http://localhost').searchParams;
 assert.equal(q.get('native_contract_identity'),'MCX-FUT-TEST');assert.equal(q.get('native_binding_identity'),'ACTIVE-DERIVATIVE-BINDING-TEST');
 assert.equal(q.get('reference_context_identity'),'TEST:CONTINUOUS');assert.equal(requests[0].options.body,file);}});
'''.replace('SCRIPT',json.dumps(script)).replace('ACTION',json.dumps(action)).replace('MIME',json.dumps(mime)).replace('MISSING',json.dumps(missing))
    result=subprocess.run([node,'-e',harness],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr



def test_unobserved_reference_placeholder_is_not_visual_evidence(tmp_path):
    app, cycle, metadata = paired_fixture(tmp_path)
    app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(4), paired_metadata=metadata)
    result = app.create_individual_question_transport(cycle.cycle_identity)
    complete_paired(app, result, reference='REPLACE_WITH_EXACT_OBSERVED_REFERENCE_IDENTITY')
    outcome = app.import_expected_answer(cycle.cycle_identity)
    assert outcome.rejected_count == 1 and outcome.imported_count == 0
    assert outcome.members[0].reason == ReviewFailure.ANSWER_SCHEMA_INVALID.value



@pytest.mark.parametrize('wrong_target', ['MCX-SUBJECT-CRUDE', 'MCX-FUT-WRONG-CONTRACT'])
def test_resolved_native_identity_must_match_metadata_contract(tmp_path, wrong_target):
    app, cycle, metadata = paired_fixture(tmp_path)
    app._paired.native_resolver = _resolver(wrong_target, 'TEST-EXACT-NATIVE-SERIES', cycle.analysis_boundary)
    app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(4), paired_metadata=metadata)
    pack = app.create_individual_question_transport(cycle.cycle_identity)
    complete_paired(app, pack)
    outcome = app.import_expected_answer(cycle.cycle_identity)
    assert outcome.rejected_count == 1 and outcome.imported_count == 0
    assert outcome.members[0].reason == ReviewFailure.ANSWER_IDENTITY_MISMATCH.value
