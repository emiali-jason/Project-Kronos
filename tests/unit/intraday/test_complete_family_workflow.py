"""Isolated constructed V2 workflow; not empirical Analyst or production evidence."""
from dataclasses import asdict,replace
from datetime import date
import json
import pytest
from kronos.instrument.visual_identity_persistence import load_visual_identity_resolver
from kronos.intraday.review import ReviewError
from kronos.intraday.analyst_chart_observation import FIELD,template
from kronos.intraday.review_mcx_paired import artifact_bytes
from kronos.intraday.review_mcx_paired_answer import answer_artifact_from_bytes
from .test_analyst_chart_correspondence import observed_panel,submit,snapshot
from .test_review_v2_paired_generic import synthetic_commissioning
from .test_review_v2_paired_intake import complete_paired
from . import test_probables_v2 as base
from . import test_mcx_asymmetric_correspondence as legacy
from tests.unit.instrument.test_complete_visual_identity import CASES


@pytest.fixture
def current_dates(monkeypatch):
 monkeypatch.setattr(base,'CURRENT_DAY',date(2026,9,11))
 monkeypatch.setattr(base,'PREVIOUS_DAY',date(2026,9,10))
 monkeypatch.setattr(legacy,'PREVIOUS_DAY',date(2026,9,10))


def fresh(tmp_path,case):
 fam,native,reference,venue,_=case
 app,cycle,chart,bundle,unused,old,rows=legacy.fixture(tmp_path,fam,retain_observation=False)
 app._paired.native_resolver=load_visual_identity_resolver(publication_version='1.7.0')
 result=app.create_individual_question_transport(cycle.cycle_identity)
 assert result.transport.schema_version=='1.4.0'
 complete_paired(app,result,reference=reference)
 doc=json.loads((app._transport.answer_inbox/result.transport.expected_answer_filename).read_text())
 doc['native_observed_visible_identity']=native
 pack=app._paired.retained(cycle,chart)[3];h=template(pack,paired=True)
 ends=(('1D','2026-09-10','10:00','16:30'),('4H','2026-09-10','10:00','14:00'),('15M','2026-09-11','10:00','10:15'),('5M','2026-09-11','10:10','10:15'))
 for i,row in enumerate(h['panels']):
  if i<4:obs=observed_panel('REFERENCE',('1D','4H','15M','5M')[i],reference,venue,currency='USD',series=None)
  else:
   frame,day,start,end=ends[i-4];obs=observed_panel('NATIVE',frame,native,'MCX',day,start,end,currency='INR')
  obs['captured_at']='2026-09-11T10:16:00+05:30'
  row.update(panel_state='PRESENT',right_edge='EXACT',observed=obs)
 doc[FIELD]=h
 return app,cycle,chart,bundle,pack,result,doc


@pytest.mark.parametrize('case',CASES,ids=lambda r:r[0])
def test_five_family_fresh_import_restoration_and_no_expiry_claim(tmp_path,current_dates,synthetic_commissioning,case):
 app,cycle,chart,bundle,pack,result,doc=fresh(tmp_path,case)
 before_contract=bundle.native_identity_binding.actual_derivative_contract_identity
 outcome=submit(app,cycle,result,doc)
 from kronos.intraday.analyst_chart_observation import receipt as prepare
 from kronos.intraday.review_mcx_paired_answer import parse_mcx_paired_answer
 observed=prepare(parse_mcx_paired_answer(json.dumps(doc).encode()),pack,chart,app.review_store,imported_at=app._clock(),paired=True)
 comparisons=app._chart_input.evaluate(cycle,chart,bundle=bundle,resolver=app._paired.native_resolver,receipt=observed)
 assert outcome.imported_count==1,(outcome,[asdict(x) for x in comparisons])
 e=app._paired.retained_evidence(pack,chart)
 assert e.actual_derivative_contract_identity==before_contract
 assert e.native_resolution.canonical_subject_identity==cycle.canonical_subject_identity
 assert e.native_resolution.publication_version=='1.7.0'
 assert e.reference_resolution is None and e.reference_independent_correspondence=='NOT_INDEPENDENTLY_ESTABLISHED'
 assert e.reference_role=='SUPPORTING_VISUAL_CONTEXT_ONLY'
 assert all(x[2]=='FAMILY_VISUAL_MACHINE_TEMPORAL_CORRESPONDENCE' for x in e.chart_correspondence if x[0]=='NATIVE')
 assert answer_artifact_from_bytes(artifact_bytes(e))==e
 frozen=snapshot(app.review_store.root)
 assert submit(app,cycle,result,doc).already_imported_count==1
 assert snapshot(app.review_store.root)==frozen
 assert app.current_reconciliation().requests==()  # no new WO-07F or trade authority
 assert len(list(app._transport.question_outbox.glob('*.pdf')))==2 # preserved old + distinct successor
 assert not list(app._transport.question_outbox.glob('*.json'))


@pytest.mark.parametrize('case',CASES,ids=lambda r:r[0])
@pytest.mark.parametrize('fault',['wrong_family','wrong_venue','role_swap','timeframe','cropped','future','forming','wrong_revision','unsupported_label','wrong_reference'])
def test_each_family_fail_closed(tmp_path,current_dates,synthetic_commissioning,case,fault):
 app,cycle,chart,bundle,pack,result,doc=fresh(tmp_path,case)
 h=doc[FIELD];p=h['panels'][4]['observed']
 if fault=='wrong_family':p['observed_subject']='Silver Mini Futures' if case[0]!='SILVERM' else 'Gold Mini Futures'
 elif fault=='wrong_venue':p['venue']='COMEX'
 elif fault=='role_swap':p['role']='REFERENCE'
 elif fault=='timeframe':p['timeframe']='5M'
 elif fault=='cropped':h['panels'][4]['panel_state']='UNREADABLE'
 elif fault=='future':h['panels'][-1]['observed']['latest_visible_end']='2026-09-11T10:20:00+05:30'
 elif fault=='forming':p['completion']='INCOMPLETE'
 elif fault=='wrong_revision':h['chart_binding_identity']='FOREIGN'
 elif fault=='unsupported_label':doc['native_observed_visible_identity']='UNSUPPORTED'
 elif fault=='wrong_reference':h['panels'][0]['observed']['observed_subject']='UNKNOWN REFERENCE'
 outcome=submit(app,cycle,result,doc)
 assert outcome.rejected_count==1 and outcome.imported_count==0,outcome
 assert app.review_store.load_chart_input(chart) is None


@pytest.mark.parametrize('case',CASES,ids=lambda r:r[0])
@pytest.mark.parametrize('field',['native_contract_identity','native_binding_identity'])
def test_wrong_machine_metadata_cannot_be_overridden_by_family(tmp_path,current_dates,synthetic_commissioning,case,field):
 app,cycle,*_=fresh(tmp_path,case)
 metadata=app._paired.options(cycle);metadata[field]='WRONG'
 with pytest.raises(ReviewError):app._paired.validate_metadata(cycle,metadata)


def test_natgas_commissioning_remains_held():
 from kronos.intraday.mcx_commissioning import load_mcx_commissioning_publication
 assert load_mcx_commissioning_publication().subject('MCX-SUBJECT-NATGAS').state.value=='HELD'
