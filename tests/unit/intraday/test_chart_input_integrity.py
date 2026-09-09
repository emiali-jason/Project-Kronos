"""WO-07B negative persistence and operational evidence-use tests."""
from dataclasses import replace
from datetime import timedelta, date, time
import json
import pytest
from kronos.intraday.chart_input import (
    ExpectedChartPanel, compare_chart_panel, observation_bytes, observation_from_bytes,
    MCX_PANELS, content_projection,
)
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.validation import ValidationState as S, FactObservability as O
from kronos.market.derived_timeframes import derive_session_four_hour_bars
from tests.unit.intraday.test_chart_input import data, compare
from tests.unit.intraday.test_validation_panel import resolver
from tests.unit.intraday.test_review_v2_individual_inbox import _completed
from tests.unit.market.test_derived_timeframes import _schedule, _candle


def test_tampered_receipt_hash_rejected(data):
    app,_,chart,receipt=data
    app.review_store.retain_chart_input(receipt)
    path=app.review_store.root/'chart-input-observations'/(chart.chart_revision_identity+'.json')
    d=json.loads(path.read_bytes());d['observation']['observation_source_identity']='TAMPER'
    path.write_text(json.dumps(d))
    with pytest.raises(ReviewError,match='INTEGRITY_INVALID'): app.review_store.load_chart_input(chart)


@pytest.mark.parametrize('kind',('file','directory','ancestor'))
def test_symlink_receipt_path_rejects(data,tmp_path,kind):
    from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
    app,_,chart,receipt=data
    app.review_store.retain_chart_input(receipt)
    folder=app.review_store.root/'chart-input-observations';path=folder/(chart.chart_revision_identity+'.json')
    store=app.review_store
    if kind=='file':
        target=tmp_path/'copy.json';target.write_bytes(path.read_bytes());path.unlink();path.symlink_to(target)
    elif kind=='directory':
        target=tmp_path/'moved';folder.rename(target);folder.symlink_to(target,target_is_directory=True)
    else:
        target=tmp_path/'alias';target.symlink_to(store.root,target_is_directory=True);store=IntradayReviewV2Store(target)
    with pytest.raises(ReviewError): store.load_chart_input(chart)


def test_missing_receipt_after_legacy_import_does_not_rewrite_or_reimport(data):
    app,cycle,chart,receipt=data
    app.review_store.retain_chart_input(receipt)
    pack=app.create_individual_question_transport(cycle.cycle_identity)
    filename=app._transport.answer_inbox/pack.transport.expected_answer_filename
    filename.write_bytes(_completed(pack.answer_template_path))
    assert app.import_expected_answer(cycle.cycle_identity).imported_count==1
    stored=app.review_store.load_visual_evidence_for_pack(pack.batch.review_pack_identities[0])
    (app.review_store.root/'chart-input-observations'/(chart.chart_revision_identity+'.json')).unlink()
    before={str(p):p.read_bytes() for p in app.review_store.root.rglob('*') if p.is_file()}
    assert app.import_expected_answer(cycle.cycle_identity).already_imported_count==1
    assert app.review_store.load_visual_evidence_for_pack(pack.batch.review_pack_identities[0])==stored
    assert {str(p):p.read_bytes() for p in app.review_store.root.rglob('*') if p.is_file()}==before


def test_last_gate_prevents_persistence_if_receipt_disappears(data):
    app,cycle,chart,receipt=data
    app.review_store.retain_chart_input(receipt)
    transport=app.create_individual_question_transport(cycle.cycle_identity)
    payload=_completed(transport.answer_template_path)
    prepared=app._prepare_transport_answer(transport.transport,payload)
    (app.review_store.root/'chart-input-observations'/(chart.chart_revision_identity+'.json')).unlink()
    with pytest.raises(ReviewError,match='CORRESPONDENCE_UNVERIFIABLE'):
        app._persist_prepared_answer(prepared,payload)
    assert app.review_store.load_visual_evidence_for_pack(transport.batch.review_pack_identities[0]) is None


def test_receipt_cannot_cover_only_selected_panels(data):
    app,cycle,chart,receipt=data
    app.review_store.retain_chart_input(replace(receipt,panels=receipt.panels[:1]))
    with pytest.raises(ReviewError,match='CORRESPONDENCE_INVALID'):
        app._chart_input.require(cycle,chart,observed_native='NSE-EQ-M&M')


def test_answer_cannot_copy_different_label_from_same_governed_subject(data):
    app,cycle,chart,receipt=data
    app.review_store.retain_chart_input(receipt)
    with pytest.raises(ReviewError,match='ANSWER_IDENTITY_MISMATCH'):
        app._chart_input.require(cycle,chart,observed_native='M&M')


@pytest.mark.parametrize('family,target,label,venue,series',(
 ('CRUDE','REFERENCE-SUBJECT-NYMEX-CRUDE-OIL','Light Crude Oil Futures','NYMEX','CLV2026'),
 ('NATGAS','REFERENCE-SUBJECT-NYMEX-NATURAL-GAS','Natural Gas Futures','NYMEX','NGV2026'),
))
def test_reference_context_independent_of_listed_membership(data,family,target,label,venue,series):
    from kronos.intraday.review_mcx_paired import relationship_for_subject
    app,cycle,chart,receipt=data
    governed=relationship_for_subject('MCX-SUBJECT-'+family)
    assert governed.reference_analytical_subject_identity==target
    r=resolver(target,label)
    at=r.publication.effective_from+timedelta(hours=1)
    expected=ExpectedChartPanel('REFERENCE','5M',target,target,venue,at,at,None,None,'USD')
    p=replace(receipt.panels[-1],role='REFERENCE',observed_subject=label,latest_visible_end=at,
              observed_series=series,venue=venue,currency='USD')
    def run(panel):
        return compare_chart_panel(expected,panel,resolver=r,received_at=chart.received_at,observed_at=receipt.observed_at)
    assert run(p).identity is S.VALIDATED
    assert run(p).overall is S.UNVERIFIABLE  # no reference source/schedule fabricated
    assert all(rel.observed_visible_subject_identity != series for rel in r.publication.relationships)
    assert run(replace(p,venue='MCX')).identity is S.NOT_VALIDATED
    assert run(replace(p,currency='INR')).identity is S.NOT_VALIDATED
    assert run(replace(p,observed_subject='FOREIGN COMMODITY')).identity is S.UNVERIFIABLE
    assert run(replace(p,role='NATIVE')).identity is S.NOT_VALIDATED
    # RSI is observable only, with no overbought/oversold interpretation here.
    assert content_projection(replace(p,content=p.content+(('rsi',O.NOT_VISIBLE),)))[-2][0]=='rsi'


@pytest.mark.parametrize('closing', (time(13,15),time(12,15)))
def test_existing_governed_four_hour_or_shortened_remainder_adapter(data,closing):
    # Explicit synthetic MCX schedule. Reuse DOMAIN-008-normalized fixture and
    # the existing Market derived-timeframe engine; do not introduce a 4H clock.
    schedule=replace(_schedule(date(2026,9,4),time(9,15),closing),exchange='MCX',market_identity='MCX')
    at=schedule.session_close
    subject='MCX-SUBJECT-CRUDE';contract='MCX-FUT-CRUDE-2026-09-21';label='CRUDEOILU2026'
    hours=int((schedule.session_close-schedule.session_open).total_seconds()/3600)
    bars=derive_session_four_hour_bars(canonical_instrument=subject,schedule=schedule,
        sixty_minute_candles=tuple(_candle(schedule.session_open+timedelta(hours=i),100.0) for i in range(hours)),
        source_provider_identity='TEST-ONLY',source_market_data_boundary=at,observed_at=at)
    source=bars[0]
    expected=ExpectedChartPanel('NATIVE','4H',subject,contract,'MCX',at,at,source,schedule,'INR')
    p=replace(data[3].panels[-1],timeframe='4H',observed_subject=label,venue='MCX',currency='INR',
        trading_date=schedule.trading_date,session=schedule.session_type,timezone=schedule.timezone,
        candle_start=source.derived_start,candle_end=source.derived_end,
        latest_visible_end=source.derived_end,captured_at=at)
    r=resolver(contract,label)
    result=compare_chart_panel(expected,p,resolver=r,received_at=at,observed_at=at)
    assert result.temporal is S.VALIDATED
    assert source.tradingview_equivalence_claimed is False
    wrong=compare_chart_panel(expected,replace(p,timeframe='1H'),resolver=r,received_at=at,observed_at=at)
    assert wrong.overall is S.NOT_VALIDATED


def test_native_receipt_relationship_does_not_backdate_pixels(data):
    app,cycle,chart,receipt=data
    r=resolver('MCX-FUT-CRUDE-2026-09-21','CRUDEOILU2026')
    at=r.publication.effective_from+timedelta(hours=1)
    e=ExpectedChartPanel('NATIVE','5M','MCX-SUBJECT-CRUDE','MCX-FUT-CRUDE-2026-09-21',
        'MCX',at-timedelta(days=1),at,None,None,'INR')
    p=replace(receipt.panels[-1],observed_subject='CRUDEOILU2026',venue='MCX',currency='INR',latest_visible_end=at)
    result=compare_chart_panel(e,p,resolver=r,received_at=at,observed_at=at)
    assert result.identity is S.VALIDATED and result.temporal is S.NOT_VALIDATED
    assert compare_chart_panel(e,replace(p,observed_subject='CRUDEOILM2026'),resolver=r,received_at=at,observed_at=at).identity is S.UNVERIFIABLE


def test_future_observer_timestamp_cannot_be_imported(data):
    app,cycle,chart,receipt=data
    app.review_store.retain_chart_input(replace(receipt, observed_at=app._clock()+timedelta(days=1)))
    with pytest.raises(ReviewError,match='CORRESPONDENCE_UNVERIFIABLE'):
        app._chart_input.require(cycle,chart,observed_native='NSE-EQ-M&M')


@pytest.mark.parametrize('change', ('future_boundary', 'foreign_exchange', 'tampered'))
def test_governed_source_must_be_available_exact_and_intact(data, change):
    from kronos.intraday.historical_semantic import create_governed_historical_candle_payload
    from dataclasses import asdict
    app, cycle, chart, _ = data
    expected = app._chart_input.expectations(cycle, chart)[-1]
    source = expected.source
    if change == 'tampered':
        import copy
        source = copy.copy(source)
        object.__setattr__(source, 'integrity_identity', 'TAMPERED')
    else:
        values = asdict(source)
        for field in ('candle_identity', 'integrity_identity', 'schema_identity',
                      'schema_version', 'completion_state', 'available_at'):
            values.pop(field)
        if change == 'future_boundary':
            values['observation_boundary'] = cycle.analysis_boundary + timedelta(minutes=5)
        else:
            values['exchange'] = 'BSE'
        source = create_governed_historical_candle_payload(**values)
    assert compare(data, expected=replace(expected, source=source)).temporal is not S.VALIDATED


def test_source_store_failure_is_bounded_and_non_destructive(data, monkeypatch):
    app, cycle, chart, receipt = data
    app.review_store.retain_chart_input(receipt)
    before = app.review_store.load_current()
    def unavailable(_):
        raise ValueError('untrusted source detail')
    monkeypatch.setattr(app.probables_store, 'load_selection', unavailable)
    with pytest.raises(ReviewError, match='INTEGRITY_INVALID'):
        app._chart_input.require(cycle, chart, observed_native='NSE-EQ-M&M')
    assert app.review_store.load_current() == before


@pytest.mark.parametrize('mutation', ('whitespace', 'duplicate_key'))
def test_receipt_noncanonical_bytes_do_not_restore(data, mutation):
    app, _, chart, receipt = data
    app.review_store.retain_chart_input(receipt)
    path = app.review_store.root / 'chart-input-observations' / (chart.chart_revision_identity + '.json')
    payload = path.read_bytes()
    if mutation == 'whitespace':
        payload = b' ' + payload
    else:
        payload = payload.replace(b'{', b'{"observation_identity":"ignored",', 1)
    path.write_bytes(payload)
    with pytest.raises(ReviewError, match='INTEGRITY_INVALID'):
        app.review_store.load_chart_input(chart)
