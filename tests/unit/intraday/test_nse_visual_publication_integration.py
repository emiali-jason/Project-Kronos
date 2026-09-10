"""Explicit composition and historical binding preservation across NSE publication upgrade."""
import json
from datetime import datetime

import pytest

from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.instrument.visual_identity_persistence import load_visual_identity_resolver, resolver_for_retained_publication
from kronos.intraday.review_v2 import bind_imported_visual_evidence_v2, create_question_pack_v2
from kronos.intraday.review_answer import parse_answer_pack
from kronos.intraday.review import ReviewError
from .test_probables_v2 import _opening_inputs
from .test_review_v2 import _application
from .test_review import _png
from .test_visual_contract_v2 import nse_document
from tests.unit.provider.test_shared_provider_runtime import _shared


def test_current_runtime_explicitly_composes_nse_successor_inertly(tmp_path):
    shared, provider, calls = _shared()
    runtime = create_intraday_runtime(shared, evidence_root=tmp_path.resolve())
    assert runtime.review_v2_application._visual_identity_resolver.publication.publication_version == '1.5.0'
    assert runtime.review_v2_application._chart_input.resolver.publication.publication_version == '1.5.0'
    assert provider.begin_count == 0 and provider.capability.calls == 0 and calls == []
    assert list(tmp_path.rglob('*')) == []


@pytest.mark.parametrize('version',['1.0.0','2.0.0'])
def test_v1_v2_answer_binding_preserves_recorded_publication_and_wrong_company_rejects(tmp_path, version):
    *_, mapping = _opening_inputs(subject='NSE-INDEX-BANKNIFTY')
    run, app = _application(tmp_path, mapping)
    cycle = app.create_eligible_cycles(run)[0]
    chart = app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(77))
    pack = create_question_pack_v2(app.review_store.load_handoff(cycle.handoff_identity),cycle,chart,
        question_version=version,completed_selection=mapping.completed_evidence)
    if version == '2.0.0':
        doc = nse_document(pack)
    else:
        from kronos.intraday.review_v2_transport import answer_template_v2
        # Existing V1 template construction remains the authoritative historical path.
        from kronos.intraday.review_v2 import create_question_batch_v2
        doc = json.loads(answer_template_v2(create_question_batch_v2((pack,)),(pack,)))['candidates'][0]
        for q,a in zip(pack.questions,doc['answers'],strict=True):
            a.update(answer=q.allowed_answers[0],observation_status='OBSERVED',visible_basis='Retained visual scope',visible_timeframes=list(q.timeframe_scope))
        doc['global_observation_status']='OBSERVED'
    doc['observed_visible_subject_identity']='Nifty Bank Index'
    parsed=parse_answer_pack(json.dumps(doc).encode())
    old=load_visual_identity_resolver(publication_version='1.3.0')
    current=load_visual_identity_resolver(publication_version='1.5.0')
    at=datetime.fromisoformat('2026-09-10T00:00:00+00:00')
    original=bind_imported_visual_evidence_v2(pack,parsed,imported_at=at,visual_identity_resolver=old)
    selected=resolver_for_retained_publication(current,publication_identity=original.visual_identity_publication_identity,
        publication_version=original.visual_identity_publication_version,
        publication_integrity_identity=original.visual_identity_publication_integrity_identity)
    assert bind_imported_visual_evidence_v2(pack,parsed,imported_at=at,visual_identity_resolver=selected)==original
    doc['observed_visible_subject_identity']='Adani Green Energy Limited'
    with pytest.raises(ReviewError,match='IDENTITY_MISMATCH'):
        bind_imported_visual_evidence_v2(pack,parse_answer_pack(json.dumps(doc).encode()),imported_at=at,visual_identity_resolver=current)


@pytest.mark.parametrize('symbol,label',[('ADANIGREEN','Adani Green Energy Limited'),('M&M','Mahindra & Mahindra Ltd.')])
def test_complete_synthetic_panels_pass_strict_correspondence_and_import(tmp_path,symbol,label):
    from .test_review_v2_individual_inbox import _fixture, _cycles
    from .chart_input_fixtures import retain_fixture_receipt
    from kronos.intraday.review_v2_transport import answer_template_v2
    _,app=_fixture(tmp_path,(symbol,),correspondence=False)
    current=load_visual_identity_resolver(publication_version='1.5.0')
    app._visual_identity_resolver=current
    app._chart_input.resolver=current
    cycle=_cycles(app)[symbol].cycle_identity
    chart=app.upload_chart(cycle,media_type='image/png',payload=_png(91))
    retain_fixture_receipt(app,chart,label)
    generated=app.create_individual_question_transport(cycle)
    doc=json.loads(answer_template_v2(generated.batch,generated.packs))
    doc['candidates']=[nse_document(generated.packs[0])]
    doc['candidates'][0]['observed_visible_subject_identity']=label
    for observation in doc['candidates'][0]['answers']:
        if observation['question_id'] in {'Q6','Q9'}:
            observation['answer']='NOT_OBSERVABLE'
            observation['visible_basis']='No machine-selected single anchor is established.'
    inbox=tmp_path/'answers';inbox.mkdir(exist_ok=True)
    (inbox/generated.transport.expected_answer_filename).write_text(json.dumps(doc))
    from dataclasses import asdict
    from kronos.intraday.validation import ValidationState
    panels=app._chart_input.evaluate(app.review_store.load_cycle(cycle),chart)
    assert all(x.overall is ValidationState.VALIDATED for x in panels), [asdict(x) for x in panels]
    result=app.import_expected_answer(cycle)
    assert result.imported_count==1 and result.rejected_count==0
    evidence=app.review_store.load_visual_evidence_for_pack(generated.packs[0].review_pack_identity)
    assert evidence.visual_identity_publication_version=='1.5.0'
    assert evidence.observed_visible_subject_identity==label
    assert app.import_expected_answer(cycle).already_imported_count==1
