"""Real-chart-equivalent drawings + predeclared visual findings, not Analyst calls.

No observation is populated from machine expectations. Exact bar endpoints,
canonical session/zone and capture time are deliberately absent in positives.
"""
from dataclasses import replace
from datetime import datetime
from io import BytesIO
import json
import pytest
from PIL import Image, ImageDraw, ImageFont
from kronos.intraday.analyst_chart_observation import FIELD, parse, receipt, template
from kronos.intraday.chart_input import observation_bytes, observation_from_bytes
from kronos.intraday.review import ReviewError
from kronos.intraday.review_answer import parse_answer_pack
from .test_analyst_chart_correspondence import fresh, fresh_mcx, submit, snapshot, LABELS, synthetic_commissioning

TEMPORAL_FIELDS = ('candle_start','candle_end','latest_visible_end','trading_date',
                   'session','timezone','completion','captured_at')
SCENARIOS = ('aligned','later_day','future','forming','countdown','cropped','unreadable','wrong_timeframe','wrong_subject')


def drawing(label, scenario='aligned'):
    """Four-panel, labeled candle drawing; scenario literals precede gate results.

    This is an equivalent test presentation, not a claimed TradingView screenshot.
    No machine schedule, expectation, source candle or gate result is an input.
    """
    im=Image.new('RGB',(1600,1000),'#101820');d=ImageDraw.Draw(im)
    font=ImageFont.load_default(size=21); small=ImageFont.load_default(size=17)
    for i,frame in enumerate(('1D','1H','15M','5M')):
        x=(i%2)*800;y=(i//2)*500
        title=('Adani Green Energy Limited' if label=='Nifty Bank Index' else 'Nifty Bank Index') if scenario=='wrong_subject' and i==3 else label
        shown='4H' if scenario=='wrong_timeframe' and i==3 else frame
        day='27 Aug 2026' if i<2 else '28 Aug 2026'
        if scenario=='later_day' and i==3:day='29 Aug 2026'
        d.rectangle((x+3,y+3,x+797,y+497),outline='#677585')
        d.text((x+20,y+18),f'{title} · NSE · {shown}',font=font,fill='white')
        for n in range(5):
            yy=y+90+n*65;d.line((x+20,yy,x+720,yy),fill='#304050')
            d.text((x+732,yy-10),str(110-n*2),font=small,fill='#c5cdd6')
        for n in range(24):
            xx=x+32+n*28;yy=y+320-n*5+(n%4)*13
            color='#58c7a0' if n%3 else '#f17b79'
            d.line((xx+6,yy-18,xx+6,yy+33),fill=color,width=2)
            d.rectangle((xx,yy,xx+12,yy+17),fill=color)
        if scenario in ('future','forming','countdown') and i==3:
            d.rectangle((x+710,y+162,x+722,y+191),fill='#f17b79')
            d.text((x+610,y+380),'10:20' if scenario=='future' else '00:42 LIVE',font=small,fill='#ffc95b')
        d.text((x+28,y+453),day,font=font,fill='white')
        # Right-edge labels align with the actual last drawn candle (x+682).
        # Normal chart labels identify bar starts, not invisible bar ends.
        labels=((630,'25 Aug'),(686,'27 Aug')) if i==0 else ((540,'27 Aug'),(686,'15:00')) if i==1 else ((540,'27 Aug'),(686,'10:00')) if i==2 else ((630,'10:00'),(686,'10:10'))
        for xx,label_text in labels:
            d.text((x+xx,y+416),label_text,font=small,fill='white',anchor='mt')
        if scenario=='cropped' and i==3:d.rectangle((x+650,y+65,x+795,y+495),fill='#080b0f')
        if scenario=='unreadable' and i==3:d.rectangle((x+10,y+440,x+795,y+495),fill='#121820')
    b=BytesIO();im.save(b,format='PNG');return b.getvalue()


def context(frame, role='NATIVE'):
    # Exact text in the rendered scenario; no exact endpoints supplied.
    labels=['27 Aug 2026','25 Aug','27 Aug'] if frame=='1D' else ['27 Aug 2026','27 Aug','15:00'] if frame in ('1H','4H') else ['28 Aug 2026','27 Aug','10:00'] if frame=='15M' else ['28 Aug 2026','10:00','10:10']
    return dict(context_sufficient=True,visible_labels=labels,later_evidence='ABSENT',
        forming_evidence='ABSENT',forming_excluded=False,excluded_forming_date=None,
        other_contradiction='ABSENT',basis='Readable dates and temporal axis extend through the full right edge; visible bars fit the Review window, with no later bars or live/countdown markers.',exclusion_basis=None)


def use_visible_context(doc, paired=False):
    h=doc[FIELD] if paired else doc['candidates'][0][FIELD]
    for row in h['panels']:
        p=row['observed']
        for name in TEMPORAL_FIELDS:p[name]=None
        p['temporal_context']=context(p['timeframe'],p['role'])
    return h


def prepared(app,chart,result,doc):
    answer=parse_answer_pack(json.dumps(doc['candidates'][0]).encode())
    return receipt(answer,result.packs[0],chart,app.review_store,imported_at=app._clock())


@pytest.mark.parametrize('symbol,label',LABELS)
@pytest.mark.parametrize('scenario',SCENARIOS)
def test_equivalent_image_through_fresh_import(tmp_path,symbol,label,scenario):
    pixels=drawing(label,scenario)
    assert drawing(label,scenario)==pixels and Image.open(BytesIO(pixels)).size==(1600,1000)
    app,cycle,chart,result,doc=fresh(tmp_path,symbol,label,payload=pixels)
    h=use_visible_context(doc);p=h['panels'][-1]['observed'];c=p['temporal_context']
    if scenario=='later_day':p['trading_date']='2026-08-29';c['visible_labels']=['29 Aug 2026','10:10'];c['later_evidence']='PRESENT'
    elif scenario=='future':c['visible_labels']+=['10:20'];c['later_evidence']='PRESENT'
    elif scenario in ('forming','countdown'):c['forming_evidence']='PRESENT'
    elif scenario=='cropped':h['panels'][-1]['right_edge']='NOT_VISIBLE';c['context_sufficient']=False
    elif scenario=='unreadable':p['content']=[[k,'UNVERIFIABLE' if k=='time_axis' else v] for k,v in p['content']];c['context_sufficient']=False
    elif scenario=='wrong_timeframe':p['timeframe']='4H'
    elif scenario=='wrong_subject':p['observed_subject']='Nifty Bank Index' if symbol!=LABELS[1][0] else 'Adani Green Energy Limited'
    outcome=submit(app,cycle,result,doc)
    assert outcome.imported_count==int(scenario=='aligned'),outcome
    assert outcome.rejected_count==int(scenario!='aligned'),outcome
    if scenario=='aligned':
        value=app.review_store.load_chart_input(chart)
        assert value.schema_version=='1.1.0'
        assert all(getattr(panel,k) is None for panel in value.panels for k in TEMPORAL_FIELDS)
        comparisons=app._chart_input.evaluate(cycle,chart,receipt=value)
        assert {r.visual_temporal_state for r in comparisons}=={'CONFIRMED_COMPATIBLE'}
        assert observation_from_bytes(observation_bytes(value))==value
        frozen=snapshot(app.review_store.root)
        assert submit(app,cycle,result,doc).already_imported_count==1
        assert snapshot(app.review_store.root)==frozen
        assert [p.suffix for p in app._transport.question_outbox.iterdir()]==['.pdf']
    else:assert app.review_store.load_chart_input(chart) is None


@pytest.mark.parametrize('field,value',[
 ('context_sufficient',None),('context_sufficient',False),('visible_labels',[]),('basis',None),
 ('later_evidence','UNKNOWN'),('other_contradiction','UNKNOWN'),('forming_evidence','UNKNOWN'),
 ('later_evidence','PRESENT'),('other_contradiction','PRESENT'),('forming_evidence','PRESENT'),
 ('forming_excluded',True),('forming_excluded',None),('exclusion_basis','Unjustified exclusion'),
 ('excluded_forming_date','2026-08-29')])
def test_missing_or_contradictory_findings_fail_closed(tmp_path,field,value):
    app,cycle,chart,result,doc=fresh(tmp_path)
    h=use_visible_context(doc);h['panels'][-1]['observed']['temporal_context'][field]=value
    assert submit(app,cycle,result,doc).rejected_count==1
    assert app.review_store.load_chart_input(chart) is None


@pytest.mark.parametrize('field,value',[
 ('trading_date','2026-08-29'),('trading_date','2026-08-27'),
 ('candle_end','2026-08-28T10:20:00+05:30'),('candle_start','2026-08-28T10:15:00+05:30'),
 ('latest_visible_end','2026-08-28T10:20:00+05:30'),('latest_visible_end','2026-08-28T10:10:00+05:30'),
 ('captured_at','2026-08-28T10:00:00+05:30'),('captured_at','2026-08-28T11:00:00+05:30'),
 ('completion','INCOMPLETE')])
def test_known_visual_facts_override_claimed_compatible_context(tmp_path,field,value):
    app,cycle,chart,result,doc=fresh(tmp_path)
    h=use_visible_context(doc);h['panels'][-1]['observed'][field]=value
    value=prepared(app,chart,result,doc)
    rows=app._chart_input.evaluate(cycle,chart,receipt=value)
    assert rows[-1].visual_temporal_state=='VISIBLY_CONTRADICTED'
    assert submit(app,cycle,result,doc).rejected_count==1


@pytest.mark.parametrize('variant',['excluded','no_date','no_basis','later_day','later_bar','unknown','qualified_forming'])
def test_forming_exclusion_is_bounded_and_never_hides_future(tmp_path,variant):
    app,cycle,chart,result,doc=fresh(tmp_path);h=use_visible_context(doc)
    p=h['panels'][-1]['observed'];c=p['temporal_context']
    c.update(forming_evidence='PRESENT',forming_excluded=True,excluded_forming_date='2026-08-28',
             basis='Readable 28 Aug axis and complete right edge show a live marker only in the separated excluded region.',
             exclusion_basis='Rightmost 00:42 LIVE candle is visibly separated; preceding completed region is qualified.')
    if variant=='no_date':c['excluded_forming_date']=None
    if variant=='no_basis':c['exclusion_basis']=None
    if variant=='later_day':c['excluded_forming_date']='2026-08-29'
    if variant=='later_bar':c['later_evidence']='PRESENT'
    if variant=='unknown':c['later_evidence']='UNKNOWN'
    if variant=='qualified_forming':p['completion']='INCOMPLETE'
    assert submit(app,cycle,result,doc).imported_count==int(variant=='excluded')


def test_raw_zone_and_session_labels_are_not_machine_canonical_equalities(tmp_path):
    app,cycle,chart,result,doc=fresh(tmp_path);h=use_visible_context(doc)
    for row in h['panels']:row['observed'].update(timezone='UTC+5:30',session='NSE chart')
    assert submit(app,cycle,result,doc).imported_count==1


@pytest.mark.parametrize('field,value',[
 ('context_sufficient',1),('visible_labels',['']),('visible_labels',['date','date']),
 ('visible_labels','date'),('later_evidence','VALID'),('forming_excluded',0),
 ('excluded_forming_date','bad'),('basis',' '),('basis','x'*2001),('invented_field',True)])
def test_context_codec_is_strict(tmp_path,field,value):
    app,cycle,chart,result,doc=fresh(tmp_path);h=use_visible_context(doc)
    h['panels'][0]['observed']['temporal_context'][field]=value
    with pytest.raises(ReviewError):parse(h)


def test_new_header_cannot_be_reinterpreted_under_old_pdf(tmp_path,monkeypatch):
    from kronos.intraday import review_v2_transport as transport
    # Generate a structurally valid old-edition transport identity, then exercise
    # the current application boundary with a new header against that authority.
    with monkeypatch.context() as m:
        m.setattr(transport,'REVIEW_BATCH_TRANSPORT_V2_VERSION','2.2.0')
        app,cycle,chart,result,doc=fresh(tmp_path)
    use_visible_context(doc)
    check=app._prepare_transport_answer(result.transport,json.dumps(doc).encode())
    assert check.validation.exact_match_count==0
    assert check.rejected[0].reason=='INTRADAY_REVIEW_ANSWER_SCHEMA_INVALID'


def test_legacy_header_keeps_null_endpoints_unverifiable_and_exact_bytes(tmp_path):
    app,cycle,chart,result,doc=fresh(tmp_path)
    h=doc['candidates'][0][FIELD];h['schema_version']='1.0.0'
    for row in h['panels']:row['observed'].pop('temporal_context')
    value=prepared(app,chart,result,doc);encoded=observation_bytes(value)
    assert b'temporal_context' not in encoded
    assert observation_bytes(observation_from_bytes(encoded))==encoded
    for row in h['panels']:
        for key in TEMPORAL_FIELDS:row['observed'][key]=None
    assert submit(app,cycle,result,doc).rejected_count==1
    assert app.review_store.load_chart_input(chart) is None


@pytest.mark.parametrize('family',['GOLDM','SILVERM','COPPER','CRUDE','NATGAS'])
@pytest.mark.parametrize('variant',['aligned','reference_unknown','native_future'])
def test_five_mcx_families_new_context_preserves_asymmetric_authority(tmp_path,synthetic_commissioning,family,variant):
    app,cycle,chart,pack,result,doc=fresh_mcx(tmp_path,family)
    h=use_visible_context(doc,paired=True)
    if variant=='reference_unknown':h['panels'][0]['observed']['temporal_context']['later_evidence']='UNKNOWN'
    if variant=='native_future':h['panels'][-1]['observed']['trading_date']='2026-08-29'
    outcome=submit(app,cycle,result,doc)
    assert outcome.imported_count==int(variant=='aligned'),outcome
    if variant=='aligned':
        rows=app._chart_input.evaluate(cycle,chart,bundle=app._paired.restore(cycle,chart)[0],resolver=app._paired.native_resolver)
        assert len(rows)==8 and '1H' not in {r.timeframe for r in rows}
        assert all(r.independent_correspondence=='NOT_INDEPENDENTLY_ESTABLISHED' for r in rows if r.role=='REFERENCE')
        assert all(r.independent_correspondence=='VALIDATED' for r in rows if r.role=='NATIVE')


def test_machine_missing_source_cannot_be_replaced_by_visual_compatibility(tmp_path,monkeypatch):
    app,cycle,chart,result,doc=fresh(tmp_path);use_visible_context(doc)
    original=app._chart_input.expectations
    def no_source(*args,**kwargs):return tuple(replace(e,source=None) for e in original(*args,**kwargs))
    monkeypatch.setattr(app._chart_input,'expectations',no_source)
    assert submit(app,cycle,result,doc).rejected_count==1


@pytest.mark.parametrize('symbol,label',LABELS)
def test_pdf_protocol_and_optional_isolated_qa_artifacts(tmp_path,symbol,label):
    import os
    from pathlib import Path
    from pypdf import PdfReader
    app,cycle,chart,result,doc=fresh(tmp_path,symbol,label,payload=drawing(label))
    text=' '.join(' '.join(page.extract_text() for page in PdfReader(result.question_path).pages).split())
    for required in ('CONFIRMED_COMPATIBLE','VISIBLY_CONTRADICTED','INSUFFICIENT_VISUAL_EVIDENCE',
                     'visible_labels','excluded_forming_date','exclusion_basis','UNKNOWN',
                     'never from printed machine orientation','SELECTED_Q6_Q9_ANCHOR = NOT_ESTABLISHED','PARTIAL'):
        assert required in text
    h=json.loads(result.answer_template_path.read_bytes())['candidates'][0][FIELD]
    for row in h['panels']:
        assert all(row['observed'][k] is None for k in TEMPORAL_FIELDS)
        assert row['observed']['temporal_context']==dict(context_sufficient=None,visible_labels=[],
            later_evidence='UNKNOWN',forming_evidence='UNKNOWN',forming_excluded=None,
            excluded_forming_date=None,other_contradiction='UNKNOWN',basis=None,exclusion_basis=None)
    # Optional caller-owned QA copies; kernel test isolation forbids production
    # stores regardless of this output setting. No application authority changes.
    if output:=os.environ.get('WO07E_QUALIFICATION_OUTPUT'):
        out=Path(output);out.mkdir(parents=True,exist_ok=True)
        (out/(symbol+'.pdf')).write_bytes(result.question_path.read_bytes())
        for scenario in SCENARIOS:(out/(symbol+'-'+scenario+'.png')).write_bytes(drawing(label,scenario))


@pytest.mark.parametrize('panel_index',[0,1])
def test_current_day_cannot_replace_known_prior_completed_context(tmp_path,panel_index):
    app,cycle,chart,result,doc=fresh(tmp_path);h=use_visible_context(doc)
    # The visible date is not later than Review, but is later than the selected
    # completed Daily/hour candle. It cannot masquerade as that completed bar.
    h['panels'][panel_index]['observed']['trading_date']='2026-08-28'
    assert submit(app,cycle,result,doc).rejected_count==1


def test_known_latest_endpoint_between_source_and_review_boundary_rejects(tmp_path):
    from datetime import timedelta
    from kronos.intraday.chart_input import compare_chart_panel
    app,cycle,chart,result,doc=fresh(tmp_path);use_visible_context(doc)
    value=prepared(app,chart,result,doc)
    e=app._chart_input.expectations(cycle,chart)[-1]
    expected=replace(e,analysis_boundary=e.analysis_boundary+timedelta(minutes=3))
    observed=replace(value.panels[-1],latest_visible_end=datetime.fromisoformat('2026-08-28T10:16:00+05:30'))
    later=datetime.fromisoformat('2026-08-28T10:20:00+05:30')
    result=compare_chart_panel(expected,observed,resolver=app._visual_identity_resolver,received_at=later,observed_at=later)
    assert result.visual_temporal_state=='VISIBLY_CONTRADICTED'
    assert 'VISIBLE_SELECTED_CONTEXT_MISMATCH' in result.reasons
