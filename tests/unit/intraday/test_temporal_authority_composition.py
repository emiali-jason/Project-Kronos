"""ADR-0035 deterministic authority composition; no real Analyst/market operations."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
import pytest
from kronos.intraday.chart_input import _machine_source_context, compare_chart_panel
from kronos.intraday.validation import ValidationState as S
from kronos.intraday.analyst_chart_observation import FIELD, receipt
from kronos.intraday.review_mcx_paired_answer import parse_mcx_paired_answer
from .test_analyst_chart_correspondence import fresh, submit, snapshot, synthetic_commissioning
from .test_visual_temporal import use_visible_context, prepared, TEMPORAL_FIELDS
from .test_complete_family_workflow import fresh as family_fresh, current_dates
from tests.unit.instrument.test_complete_visual_identity import CASES


def unknown(doc, paired=False):
    h=use_visible_context(doc,paired=paired)
    for row in h['panels']:
        if row['slot_role']=='NATIVE':
            row['observed']['temporal_context'].update(forming_evidence='UNKNOWN',
                forming_excluded=None,excluded_forming_date=None,exclusion_basis=None,
                basis='Readable dates, temporal axis and full right edge allow contradiction checking; no later bars or affirmative live marker is visible. Static pixels do not independently prove candle completion.')
    return h


@pytest.mark.parametrize('panel_index',range(4))
def test_machine_complete_unknown_without_visual_endpoints_passes(tmp_path,panel_index):
    app,cycle,chart,result,doc=fresh(tmp_path);h=unknown(doc)
    value=prepared(app,chart,result,doc)
    expected=app._chart_input.expectations(cycle,chart)
    assert all(_machine_source_context(e)[0] is S.VALIDATED for e in expected)
    assert all(getattr(value.panels[panel_index],k) is None for k in TEMPORAL_FIELDS)
    rows=app._chart_input.evaluate(cycle,chart,receipt=value)
    assert all(r.overall is S.VALIDATED and r.visual_temporal_state=='CONFIRMED_COMPATIBLE' for r in rows)
    assert submit(app,cycle,result,doc).imported_count==1
    retained=app.review_store.load_chart_input(chart)
    assert all(p.temporal_context.forming_evidence=='UNKNOWN' and p.completion is None for p in retained.panels)
    before=snapshot(app.review_store.root)
    assert submit(app,cycle,result,doc).already_imported_count==1
    assert snapshot(app.review_store.root)==before


@pytest.mark.parametrize('failure',[
    'false','null','labels','basis','later_unknown','other_unknown','later_present','other_present',
    'forming','cropped','axis','identity_unreadable','wrong_subject','wrong_timeframe',
    'wrong_revision','wrong_cycle','unknown_excluded','unknown_date','unknown_basis','partial_panel',
    'future_endpoint','wrong_date'])
def test_unknown_never_bypasses_required_visual_checks(tmp_path,failure):
    app,cycle,chart,result,doc=fresh(tmp_path);h=unknown(doc);row=h['panels'][-1];p=row['observed'];c=p['temporal_context']
    if failure=='false':c['context_sufficient']=False
    elif failure=='null':c['context_sufficient']=None
    elif failure=='labels':c['visible_labels']=[]
    elif failure=='basis':c['basis']=None
    elif failure.startswith('later_'):c['later_evidence']=failure.split('_')[1].upper()
    elif failure.startswith('other_'):c['other_contradiction']=failure.split('_')[1].upper()
    elif failure=='forming':c['forming_evidence']='PRESENT';c['forming_excluded']=False
    elif failure=='cropped':row['right_edge']='NOT_VISIBLE'
    elif failure in ('axis','identity_unreadable'):
        field='time_axis' if failure=='axis' else 'identity'
        p['content']=[[k,'UNVERIFIABLE' if k==field else v] for k,v in p['content']]
    elif failure=='wrong_subject':p['observed_subject']='Nifty Bank Index'
    elif failure=='wrong_timeframe':p['timeframe']='4H'
    elif failure=='wrong_revision':h['chart_binding_identity']='FOREIGN'
    elif failure=='wrong_cycle':h['review_cycle_identity']='FOREIGN'
    elif failure=='unknown_excluded':c['forming_excluded']=True
    elif failure=='unknown_date':c['excluded_forming_date']='2026-08-28'
    elif failure=='unknown_basis':c['exclusion_basis']='Invented exclusion'
    elif failure=='partial_panel':p['entire_panel_observed']=False
    elif failure=='future_endpoint':p['candle_end']='2026-08-28T10:20:00+05:30'
    elif failure=='wrong_date':p['trading_date']='2026-08-29'
    assert submit(app,cycle,result,doc).rejected_count==1
    assert app.review_store.load_chart_input(chart) is None


@pytest.mark.parametrize('failure',['missing','completion','integrity','schedule','calendar','session','availability'])
def test_unknown_cannot_replace_machine_authority(tmp_path,monkeypatch,failure):
    app,cycle,chart,result,doc=fresh(tmp_path);unknown(doc)
    original=app._chart_input.expectations
    def broken(*args,**kwargs):
        rows=list(original(*args,**kwargs));e=rows[-1]
        if failure=='missing':e=replace(e,source=None)
        elif failure=='schedule':e=replace(e,schedule=None)
        elif failure=='calendar':e=replace(e,schedule=replace(e.schedule,source_boundary=e.analysis_boundary+timedelta(days=1)))
        elif failure=='session':e=replace(e,schedule=replace(e.schedule,session_identity='WRONG-SESSION'))
        else:
            # Deliberate corrupt retained object; production must revalidate it.
            source=deepcopy(e.source)
            field,value={'completion':('completion_state','INCOMPLETE'),
                'integrity':('candle_identity','TAMPERED'),
                'availability':('available_at',e.analysis_boundary+timedelta(days=1))}[failure]
            object.__setattr__(source,field,value);e=replace(e,source=source)
        rows[-1]=e;return tuple(rows)
    monkeypatch.setattr(app._chart_input,'expectations',broken)
    value=prepared(app,chart,result,doc)
    rows=app._chart_input.evaluate(cycle,chart,receipt=value)
    assert rows[-1].overall is not S.VALIDATED
    assert rows[-1].visual_temporal_state!='CONFIRMED_COMPATIBLE'
    assert submit(app,cycle,result,doc).rejected_count==1


def test_explicit_false_is_not_reinterpreted_from_completion_only_prose(tmp_path):
    app,cycle,chart,result,doc=fresh(tmp_path);h=unknown(doc)
    for row in h['panels']:
        row['observed']['temporal_context'].update(context_sufficient=False,
            basis='Full readable context and right edge; false solely because static pixels cannot prove completion.')
    raw=json.dumps(doc);assert submit(app,cycle,result,doc).rejected_count==1
    assert json.dumps(doc)==raw
    assert app.review_store.load_chart_input(chart) is None


@pytest.mark.parametrize('frame',['1D','1H'])
def test_opening_keeps_prior_completed_higher_timeframe(tmp_path,frame):
    app,cycle,chart,result,doc=fresh(tmp_path);unknown(doc)
    # Existing Opening fixture has prior Daily/hour, current first 15M/5M.
    e=next(e for e in app._chart_input.expectations(cycle,chart) if e.timeframe==frame)
    assert e.source.candle_end.date()<cycle.analysis_boundary.date()
    assert _machine_source_context(e)[0] is S.VALIDATED
    assert submit(app,cycle,result,doc).imported_count==1


@pytest.mark.parametrize('case',CASES,ids=lambda x:x[0])
@pytest.mark.parametrize('reference_unknown',[False,True])
def test_mcx_machine_native_unknown_preserves_reference_boundary(tmp_path,current_dates,synthetic_commissioning,case,reference_unknown):
    app,cycle,chart,bundle,pack,result,doc=family_fresh(tmp_path,case)
    h=unknown(doc,paired=True)
    # Independent literal scenario dates; optional exact observations are null.
    for row in h['panels']:
        row['observed']['temporal_context']['visible_labels']=['10 Sep 2026','11 Sep 2026','10:00']
    if reference_unknown:
        h['panels'][0]['observed']['temporal_context'].update(forming_evidence='UNKNOWN',forming_excluded=None)
    answer=parse_mcx_paired_answer(json.dumps(doc).encode())
    value=receipt(answer,pack,chart,app.review_store,imported_at=app._clock(),paired=True)
    rows=app._chart_input.evaluate(cycle,chart,bundle=bundle,resolver=app._paired.native_resolver,receipt=value)
    assert all(r.overall is S.VALIDATED for r in rows if r.role=='NATIVE')
    assert all(r.independent_correspondence=='NOT_INDEPENDENTLY_ESTABLISHED' and r.authority=='SUPPORTING_VISUAL_CONTEXT_ONLY' for r in rows if r.role=='REFERENCE')
    outcome=submit(app,cycle,result,doc)
    assert outcome.imported_count==int(not reference_unknown)
    assert outcome.rejected_count==int(reference_unknown)


def test_pdf_protocol_distinguishes_context_from_completion(tmp_path):
    from pypdf import PdfReader
    app,cycle,chart,result,doc=fresh(tmp_path)
    text=' '.join(' '.join(p.extract_text() for p in PdfReader(result.question_path).pages).split())
    for literal in ('VISIBLE CONTRADICTION checking','Static pixels need not prove that metadata',
        'forming_evidence=UNKNOWN','context_sufficient=false solely','16 distinct','NOT_INDEPENDENTLY_ESTABLISHED'):
        assert literal in text
    import os
    if out:=os.environ.get('WO07E_QUALIFICATION_OUTPUT'):
        from pathlib import Path
        p=Path(out);p.mkdir(parents=True,exist_ok=True);(p/'temporal-authority-question.pdf').write_bytes(result.question_path.read_bytes())
    assert [p.suffix for p in app._transport.question_outbox.iterdir()]==['.pdf']
