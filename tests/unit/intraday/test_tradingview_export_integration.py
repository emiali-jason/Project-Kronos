"""Isolated V2 import identity gate for the seven Sponsor candidate equities."""
import json
from datetime import date,timedelta

import pytest

from kronos.instrument.visual_identity_persistence import load_visual_identity_resolver
from kronos.intraday.review_v2 import bind_imported_visual_evidence_v2,create_question_pack_v2
from kronos.intraday.review_answer import parse_answer_pack
from kronos.intraday.review import ReviewError
from tests.unit.intraday import test_probables_v2 as fixtures
from tests.unit.intraday.test_review_v2 import _application
from tests.unit.intraday.test_review import _png
from tests.unit.intraday.test_visual_contract_v2 import nse_document

CASES=[('INDIGO','InterGlobe Aviation Ltd'),('JUBLFOOD','Jubilant Foodworks Limited'),
    ('LUPIN','Lupin Limited'),('MOTHERSON','Samvardhana Motherson International Limited'),
    ('NTPC','NTPC Limited'),('VEDL','Vedanta Limited'),('YESBANK','Yes Bank Limited')]


@pytest.mark.parametrize('symbol,label',CASES)
def test_seven_v2_exact_observed_labels_bind_after_effective_and_foreign_candidate_rejects(tmp_path,monkeypatch,symbol,label):
    monkeypatch.setattr(fixtures,'CURRENT_DAY',date(2026,9,11))
    monkeypatch.setattr(fixtures,'PREVIOUS_DAY',date(2026,9,10))
    *_,mapping=fixtures._opening_inputs(subject='NSE-EQ-'+symbol)
    run,app=_application(tmp_path,mapping)
    cycle=app.create_eligible_cycles(run)[0]
    app._clock=lambda:mapping.analysis_boundary+timedelta(minutes=1)
    chart=app.upload_chart(cycle.cycle_identity,media_type='image/png',payload=_png(79))
    pack=create_question_pack_v2(app.review_store.load_handoff(cycle.handoff_identity),cycle,chart,
        question_version='2.0.0',completed_selection=mapping.completed_evidence)
    doc=nse_document(pack);doc['observed_visible_subject_identity']=label
    for a in doc['answers']:
        if a['question_id'] in ('Q6','Q9'):
            a['answer']='NOT_OBSERVABLE';a['visible_basis']='No machine-selected single anchor established.'
    resolver=load_visual_identity_resolver(publication_version='1.6.0')
    result=bind_imported_visual_evidence_v2(pack,parse_answer_pack(json.dumps(doc).encode()),
        imported_at=mapping.analysis_boundary+timedelta(minutes=2),visual_identity_resolver=resolver)
    assert result.resolved_canonical_subject_identity=='NSE-EQ-'+symbol
    assert result.observed_visible_subject_identity==label and result.visual_identity_publication_version=='1.6.0'
    doc['observed_visible_subject_identity']='Adani Green Energy Limited'
    with pytest.raises(ReviewError,match='IDENTITY_MISMATCH'):
        bind_imported_visual_evidence_v2(pack,parse_answer_pack(json.dumps(doc).encode()),
            imported_at=mapping.analysis_boundary+timedelta(minutes=2),visual_identity_resolver=resolver)
