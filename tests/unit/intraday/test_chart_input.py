"""WO-07B deterministic correspondence qualification; no operational requests."""
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import pytest

from kronos.application.intraday_chart_input import IntradayChartInputGate
from kronos.intraday.chart_input import (
    ChartInputObservation, ObservedChartPanel, CORE_CONTENT, OPTIONAL_CONTENT,
    ContentRequirement, content_projection, compare_chart_panel,
    observation_bytes, observation_from_bytes, NSE_PANELS, MCX_PANELS,
)
from kronos.intraday.validation import ValidationState as S, FactObservability as O
from kronos.intraday.contracts import CandleCompletion
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from tests.unit.intraday.test_review_v2_individual_inbox import _fixture, _completed
from tests.unit.intraday.chart_input_fixtures import fixture_receipt
from tests.unit.intraday.test_review import _png
from tests.unit.intraday.test_validation_panel import resolver


@pytest.fixture
def data(tmp_path):
    _, app = _fixture(tmp_path, ('M&M',), correspondence=False)
    cycle = app.review_store.load_cycle(app.snapshot().candidates[0].cycle_identity)
    chart = app.upload_chart(cycle.cycle_identity, media_type='image/png', payload=_png(1))
    receipt = fixture_receipt(app, chart)
    return app, cycle, chart, receipt


def compare(data, panel=None, expected=None, identity_resolver=None):
    app, cycle, chart, receipt = data
    e = expected or app._chart_input.expectations(cycle, chart)[-1]
    o = panel or receipt.panels[-1]
    return compare_chart_panel(e, o, resolver=identity_resolver or app._visual_identity_resolver,
                              received_at=chart.received_at, observed_at=receipt.observed_at)


def test_all_four_expected_panels_are_source_bound_and_valid(data):
    app, cycle, chart, receipt = data
    app.review_store.retain_chart_input(receipt)
    results = app._chart_input.require(cycle, chart, observed_native='NSE-EQ-M&M')
    assert tuple((r.role,r.timeframe) for r in results) == NSE_PANELS
    assert all(r.overall is S.VALIDATED and r.source_identity for r in results)
    assert all(r.visual_relationship_identity for r in results)
    # 10:15 Opening/Structure fixtures retain earlier completed Daily/1H.
    assert receipt.panels[0].candle_end < cycle.analysis_boundary


@pytest.mark.parametrize('field,value,reason', (
    ('observed_subject','NSE-EQ-MANDM','VISUAL_RELATIONSHIP'),
    ('observed_subject','NSE-EQ-M AND M','VISUAL_RELATIONSHIP'),
    ('observed_subject','NSE-EQ-M_M','VISUAL_RELATIONSHIP'),
    ('observed_subject','NSE-EQ-FOREIGN','VISUAL_RELATIONSHIP'),
    ('observed_subject',None,'VISUAL_IDENTITY'),
    ('venue','BSE','VISUAL_SUBJECT'),
    ('timeframe','15M','PANEL_ROLE'),
    ('role','REFERENCE','PANEL_ROLE'),
    ('session','AUCTION','SESSION_MISMATCH'),
    ('timezone','UTC','TIMEZONE_MISMATCH'),
    ('candle_end',None,'TEMPORAL_EVIDENCE_MISSING'),
    ('captured_at',None,'TEMPORAL_EVIDENCE_MISSING'),
    ('completion',None,'TEMPORAL_EVIDENCE_MISSING'),
    ('completion',CandleCompletion.INCOMPLETE,'OBSERVED_CANDLE_INCOMPLETE'),
    ('latest_visible_end',None,'NO_FUTURE_EVIDENCE_NOT_PROVEN'),
    ('entire_panel_observed',False,'FULL_PANEL_COVERAGE_NOT_PROVEN'),
    ('opinion_overlays_present',True,'OPINION_OVERLAY_EXCLUDED'),
    ('opinion_overlays_present',None,'OPINION_OVERLAY_ABSENCE_NOT_PROVEN'),
))
def test_conservative_identity_time_and_content(data, field, value, reason):
    result = compare(data, replace(data[3].panels[-1], **{field:value}))
    assert result.overall is not S.VALIDATED
    assert any(reason in r for r in result.reasons)


@pytest.mark.parametrize('minutes', (1,5,10,30))
def test_future_evidence_anywhere_in_full_panel_fails(data, minutes):
    _,cycle,_,receipt = data
    result = compare(data,replace(receipt.panels[-1],latest_visible_end=cycle.analysis_boundary+timedelta(minutes=minutes)))
    assert result.temporal is S.NOT_VALIDATED
    assert 'VISIBLE_EVIDENCE_AFTER_ANALYSIS_BOUNDARY' in result.reasons


@pytest.mark.parametrize('delta', (-timedelta(minutes=5),timedelta(minutes=5)))
def test_stale_or_later_endpoint_cannot_match(data, delta):
    panel=data[3].panels[-1]
    result=compare(data,replace(panel,candle_end=panel.candle_end+delta))
    assert result.temporal is S.NOT_VALIDATED


def test_wrong_day_and_capture_chronology(data):
    p=data[3].panels[-1]
    assert compare(data,replace(p,trading_date=p.trading_date-timedelta(days=1))).temporal is S.NOT_VALIDATED
    assert compare(data,replace(p,captured_at=data[2].received_at+timedelta(seconds=1))).temporal is S.UNVERIFIABLE
    assert compare(data,p).temporal is S.VALIDATED  # later receipt is not itself contamination


@pytest.mark.parametrize('key', CORE_CONTENT)
@pytest.mark.parametrize('state', (O.NOT_VISIBLE,O.UNVERIFIABLE,O.APPROXIMATE,O.NOT_APPLICABLE))
def test_missing_unreadable_cropped_core_is_not_qualified(data,key,state):
    p=data[3].panels[-1]
    p=replace(p,content=tuple((k,state if k==key else v) for k,v in p.content))
    assert compare(data,p).core_content is S.UNVERIFIABLE


@pytest.mark.parametrize('key',OPTIONAL_CONTENT)
@pytest.mark.parametrize('state',(O.EXACT,O.NOT_VISIBLE,O.UNVERIFIABLE,O.NOT_APPLICABLE))
def test_optional_overlays_do_not_invalidate_candles(data,key,state):
    p=replace(data[3].panels[-1],content=data[3].panels[-1].content+((key,state),))
    assert compare(data,p).overall is S.VALIDATED
    rows=content_projection(p,(key,))
    assert next(r for r in rows if r[0]==key)==(key,ContentRequirement.QUESTION_REQUIRED,state)


@pytest.mark.parametrize('subject,label', (
 ('NSE-EQ-M&M','M&M'), ('NSE-INDEX-NIFTY','Nifty 50 Index'),
 ('NSE-INDEX-BANKNIFTY','Nifty Bank Index'), ('NSE-EQ-BDL','Bharat Dynamics Ltd.'),
))
def test_exact_identity_matrix_uses_governed_synthetic_relationship(data,subject,label):
    app,cycle,chart,receipt=data
    # Identity test does not fabricate a matching source: temporal remains unproven
    # for foreign subjects. The exact relationship is independently qualified.
    e=replace(app._chart_input.expectations(cycle,chart)[-1],canonical_subject=subject,visual_target=subject,source=None)
    r=resolver(subject,label)
    e=replace(e,relationship_boundary=r.publication.effective_from+timedelta(seconds=1))
    result=compare(data,replace(receipt.panels[-1],observed_subject=label),e,r)
    assert result.identity is S.VALIDATED
    assert result.temporal is S.UNVERIFIABLE
    for wrong in (label.lower(),label+' ',label.replace('&','AND')):
        if wrong==label or wrong.endswith(' '): continue
        assert compare(data,replace(receipt.panels[-1],observed_subject=wrong),e,r).identity is not S.VALIDATED


def test_missing_source_and_valid_relationship_do_not_prove_temporal(data):
    app,cycle,chart,receipt=data
    e=replace(app._chart_input.expectations(cycle,chart)[-1],source=None)
    result=compare(data,expected=e)
    assert result.identity is S.VALIDATED and result.temporal is S.UNVERIFIABLE


def test_import_blocks_missing_proof_without_changing_review(data):
    app,cycle,chart,receipt=data
    transport=app.create_individual_question_transport(cycle.cycle_identity)
    app._transport.answer_inbox.joinpath(transport.transport.expected_answer_filename).write_bytes(_completed(transport.answer_template_path))
    before=app.review_store.load_current()
    result=app.import_expected_answer(cycle.cycle_identity)
    assert result.imported_count==0 and result.members[0].reason==ReviewFailure.CHART_CORRESPONDENCE_UNVERIFIABLE.value
    assert app.review_store.load_current()==before
    assert app.review_store.load_current_chart(cycle.cycle_identity).chart_revision_identity==chart.chart_revision_identity
    app.review_store.retain_chart_input(receipt)
    assert app.import_expected_answer(cycle.cycle_identity).imported_count==1
    assert app.import_expected_answer(cycle.cycle_identity).already_imported_count==1


def test_restoration_immutable_receipt_and_legacy_replay(data):
    app,cycle,chart,receipt=data
    app.review_store.retain_chart_input(receipt)
    assert app.review_store.retain_chart_input(receipt)==receipt.identity
    restored=IntradayReviewV2Store(app.review_store.root)
    assert restored.load_chart_input(chart)==receipt
    assert observation_from_bytes(observation_bytes(receipt))==receipt
    altered=replace(receipt,observation_source_identity='DIFFERENT')
    with pytest.raises(ReviewError,match='PERSISTENCE_CONFLICT'):
        restored.retain_chart_input(altered)
    assert restored.load_chart_input(chart)==receipt


@pytest.mark.parametrize('field',('chart_revision_identity','review_cycle_identity','probables_run_identity','probable_result_identity','chart_payload_sha256'))
def test_foreign_receipt_cannot_bind(data,field):
    app,_,_,receipt=data
    value='0'*64 if field=='chart_payload_sha256' else 'FOREIGN'
    with pytest.raises(ReviewError): app.review_store.retain_chart_input(replace(receipt,**{field:value}))


def test_unknown_fields_and_duplicate_panels_reject(data):
    receipt=data[3]
    d=json.loads(observation_bytes(receipt));d['invented']='anything'
    with pytest.raises(ValueError): observation_from_bytes(json.dumps(d).encode())
    with pytest.raises(ValueError): replace(receipt,panels=receipt.panels+(receipt.panels[0],))


def test_content_model_does_not_freeze_questions_or_index_volume(data):
    p=replace(data[3].panels[0],content=data[3].panels[0].content+(('volume',O.NOT_APPLICABLE),))
    assert compare(data,p,replace(data[0]._chart_input.expectations(data[1],data[2])[0])).overall is S.VALIDATED
    assert all(k not in CORE_CONTENT for k in ('cpr','rsi','sma','vwap','volume'))
    assert tuple(t for r,t in MCX_PANELS if r=='NATIVE')==('1D','4H','15M','5M')
    assert '1H' not in [t for _,t in MCX_PANELS]
