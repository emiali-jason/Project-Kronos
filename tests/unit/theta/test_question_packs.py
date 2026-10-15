"""TE-02 synthetic qualification only; no Provider, broker or genuine targets."""

from dataclasses import replace
from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlencode
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
import pytest
import reportlab

from kronos.theta.contracts import (PROSPECTIVE_VERSION, SUBJECTS, ThetaError,
    answer_template, digest, encode, validate_answer)
from kronos.theta.question_pack import COMMODITY, pack_name, render_transport
from kronos.theta.store import ThetaStore, directory, write_at
from kronos.theta.workflow import ThetaWorkflow
from tests.unit.theta.test_chart_intake import inventory, receive
from tests.unit.theta.test_rehearsal import request, running
from tests.unit.theta.test_workflow import NOW, authority, place, valid_answer


def composite(subject):
    """Deterministic readable fixture, never actual TradingView/market evidence."""
    macro = subject=='GLOBAL_MACRO'
    image=Image.new('RGB',(2400,1440),'#0a1e2e')
    draw=ImageDraw.Draw(image)
    font_path=Path(reportlab.__file__).parent/'fonts/Vera.ttf'
    title=ImageFont.truetype(str(font_path),36)
    label=ImageFont.truetype(str(font_path),26)
    small=ImageFont.truetype(str(font_path),22)
    draw.text((30,20),'SYNTHETIC - NOT FOR GENUINE FORECASTING | '+subject,font=title,fill='#ffd780')
    names=['DXY','US 10Y','US 30Y','USD/INR','Nasdaq-100','USD/CNH','CSI 300','Dow Jones'] if macro else [
        COMMODITY[subject][0].split(' + ')[0]+' | '+t for t in ('1D','4H','1H')]+[
        COMMODITY[subject][0].split(' + ')[1]+' | '+t for t in ('1D','4H','1H')]
    columns=4 if macro else 3
    width=2340//columns
    for index,name in enumerate(names):
        x=30+(index%columns)*width; y=100+(index//columns)*650
        draw.rectangle((x,y,x+width-20,y+600),outline='#54809d',width=3)
        draw.text((x+14,y+16),name,font=label,fill='white')
        draw.text((x+14,y+60),'Illustrative candles only - no real prices',font=small,fill='#aac0d0')
        for n in range(12):
            px=x+35+n*(width-140)//12; py=y+300+((n*31+index*19+len(subject)*7)%160)-80
            draw.line((px,py-35,px,py+45),fill='#6fdfb3',width=3)
            draw.rectangle((px-7,py-5,px+7,py+22),fill='#6fdfb3')
        for n in range(4):
            draw.text((x+width-106,y+170+n*92),str(100+n*5+index),font=small,fill='#aac0d0')
        draw.text((x+14,y+550),'Synthetic fixture | exact original',font=small,fill='#ffd780')
    stream=BytesIO(); image.save(stream,format='PNG'); return stream.getvalue()


@pytest.fixture
def packs(tmp_path):
    root=tmp_path.resolve()
    workflow=ThetaWorkflow(ThetaStore(root/'evidence'),inbox=root/'answers',outbox=root/'questions',
                           authority_provider=authority,clock=lambda:NOW,qualification_mode=True)
    for subject in (*SUBJECTS,'GLOBAL_MACRO'):
        workflow.intake_chart(subject=subject,label='SYNTHETIC '+subject,
            information_cutoff=(NOW-timedelta(hours=1)).isoformat(),media_type='image/png',payload=composite(subject))
    return workflow


def commission(packs, subjects=SUBJECTS):
    result=packs.commission_questions(subjects)
    assert all(s['status']=='READY' for s in result['states'].values()),result
    return result


def question(packs, result, subject='GOLDM'):
    return packs.store.question(result['states'][subject]['question_id'])


def complete_answer(packs,q):
    answer=valid_answer(packs,q['question_id'])
    answer['analyzed_at']=(NOW+timedelta(hours=2)).isoformat()
    for forecast in answer['forecasts']:
        source=forecast['sources'][0]
        source.update(published_at=(NOW-timedelta(hours=1)).isoformat(),
                      available_at=(NOW-timedelta(hours=1)).isoformat(),
                      accessed_at=(NOW+timedelta(hours=1)).isoformat())
    return answer


def validate(packs,q,answer):
    return validate_answer(encode(answer),q,received_at=NOW+timedelta(hours=3))


def manifest_valid(binary):
    with ZipFile(BytesIO(binary)) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        assert set(archive.namelist())==set(manifest)|{'manifest.json'}
        assert all(digest(archive.read(name))==value for name,value in manifest.items())
        return {name:archive.read(name) for name in archive.namelist()}


def test_independent_questions_bind_cycle_revisions_macro_targets_and_exact_template(packs):
    result=commission(packs)
    assert result['complete'] and len({s['question_id'] for s in result['states'].values()})==5
    workspace=packs.chart_workspace()
    cards={c['subject']:c for c in workspace['cards']}
    for subject in SUBJECTS:
        q=question(packs,result,subject)
        assert q['schema_version']==PROSPECTIVE_VERSION and q['subjects']==[subject]
        assert q['cycle_id']==workspace['cycle_id'] and q['information_cutoff']==NOW.isoformat()
        assert q['charts']==[cards[subject]['chart']] and q['macro_chart']==cards['GLOBAL_MACRO']['chart']
        assert [b['revision_id'] for b in q['chart_bindings']]==[cards[subject]['revision_id'],cards['GLOBAL_MACRO']['revision_id']]
        assert [(t['subject'],t['horizon']) for t in q['targets']]==[(subject,'E1'),(subject,'E2')]
        files=manifest_valid(packs.transport(q['question_id'],'zip'))
        assert json.loads(files['question.json'])==q and len(json.loads(files['answer-template.json'])['forecasts'])==2
        assert sorted(digest(value) for name,value in files.items() if name.startswith('charts/'))==sorted([cards[subject]['chart']['sha256'],cards['GLOBAL_MACRO']['chart']['sha256']])
        assert q['synthetic'] and 'GLOBAL_MACRO' not in q['subjects']
        assert validate(packs,q,complete_answer(packs,q))
        with pytest.raises(ThetaError):
            validate(packs,q,answer_template(q))


def test_combined_transport_preserves_five_identities_and_one_exact_macro(packs):
    result=commission(packs)
    files=manifest_valid(packs.transport(result['batch_id'],'zip'))
    assert len([n for n in files if n.startswith('shared/')])==1
    retained=json.loads(files['transport.json'])
    assert retained['complete'] and retained['batch_id']==result['batch_id']
    for subject in SUBJECTS:
        q=json.loads(files[f'individual/{subject}/question.json'])
        assert q['question_id']==result['states'][subject]['question_id']
        assert json.loads(files[f'individual/{subject}/answer-template.json'])['question_id']==q['question_id']
        assert files[f'individual/{subject}/charts/{subject}.png']==packs.chart_bytes(q['charts'][0]['sha256'])


def test_repeated_commissioning_reuses_frozen_t0_and_exact_retained_binary(packs):
    first=commission(packs); before=inventory(packs)
    outputs={p.name:p.read_bytes() for p in packs.outbox.iterdir()}
    packs.clock=lambda:NOW+timedelta(hours=4)
    second=commission(packs)
    assert second==first and inventory(packs)==before
    assert {p.name:p.read_bytes() for p in packs.outbox.iterdir()}==outputs
    assert question(packs,second)['information_cutoff']==NOW.isoformat()


@pytest.mark.parametrize('mutation',[
    lambda a:a.update(information_cutoff=(NOW+timedelta(minutes=1)).isoformat()),
    lambda a:a.update(schema_version='1.0.0'),
    lambda a:a['forecasts'][0]['sources'][0].update(available_at=(NOW+timedelta(seconds=1)).isoformat()),
    lambda a:a['forecasts'][0]['sources'][0].update(published_at=(NOW+timedelta(seconds=1)).isoformat()),
    lambda a:a['forecasts'][0]['sources'][0].update(available_at=None),
    lambda a:a['forecasts'][0]['sources'][0].update(accessed_at=(NOW+timedelta(hours=3)).isoformat()),
    lambda a:a['forecasts'][0]['sources'][0].pop('available_at'),
])
def test_prospective_temporal_contract_excludes_later_information_and_false_retrieval(packs,mutation):
    q=question(packs,commission(packs,('GOLDM',)))
    answer=complete_answer(packs,q); mutation(answer)
    with pytest.raises(ThetaError): validate(packs,q,answer)


def test_unknown_publication_needs_supported_availability_and_truthful_retrieval(packs):
    q=question(packs,commission(packs,('GOLDM',)))
    answer=complete_answer(packs,q)
    for forecast in answer['forecasts']:
        forecast['sources'][0].update(published_at=None,evidence='Synthetic archived availability assertion at/before T0')
    assert validate(packs,q,answer)==answer


def test_historical_answer_semantics_are_unchanged(packs):
    identity=packs.create_question(('GOLDM',)); q=packs.store.question(identity)
    answer=valid_answer(packs,identity)
    assert 'available_at' not in answer['forecasts'][0]['sources'][0]
    assert validate(packs,q,answer)==answer
    answer['forecasts'][0]['sources'][0]['accessed_at']=(NOW+timedelta(minutes=1)).isoformat()
    answer['analyzed_at']=(NOW+timedelta(hours=1)).isoformat()
    with pytest.raises(ThetaError): validate(packs,q,answer)
    assert packs.store.question(identity)==q


@pytest.mark.parametrize('role',['GOLDM','GLOBAL_MACRO'])
def test_replace_chart_recomputes_readiness_without_rewriting_history(packs,role):
    first=commission(packs)
    old={s:question(packs,first,s) for s in SUBJECTS}
    old_bytes={s:packs.transport(q['question_id'],'zip') for s,q in old.items()}
    packs.clock=lambda:NOW+timedelta(minutes=1)
    receive(packs,role,payload=composite(role)+b'\x00')
    affected=SUBJECTS if role=='GLOBAL_MACRO' else ('GOLDM',)
    assert all(r['status']!='ANSWER_PENDING' for r in packs.summary() if r['subject'] in affected)
    assert not packs.question_batch()['current']
    second=commission(packs)
    for subject in SUBJECTS:
        assert (second['states'][subject]['question_id']!=first['states'][subject]['question_id'])==(subject in affected)
        assert packs.store.question(old[subject]['question_id'])==old[subject]
        assert packs.transport(old[subject]['question_id'],'zip')==old_bytes[subject]


@pytest.mark.parametrize('damage',['missing','corrupt','foreign_binding','authority_missing','methodology_missing','render_failure'])
def test_commodity_failure_is_isolated_and_partial_transport_is_explicit(packs,damage,monkeypatch):
    if damage=='missing':
        with packs.store.transaction():
            selection=packs.store.current(); selection['subjects'].pop('COPPER'); packs.store.select(selection)
    elif damage=='corrupt':
        c=next(c for c in packs.chart_workspace()['cards'] if c['subject']=='COPPER')
        (packs.store.root/'blobs'/c['chart']['sha256']).write_bytes(b'SYNTHETIC CORRUPTION')
    elif damage=='foreign_binding':
        with packs.store.transaction():
            selection=packs.store.current(); selection['subjects']['COPPER']=selection['subjects']['GOLDM'].copy(); packs.store.select(selection)
    elif damage in {'authority_missing','methodology_missing'}:
        def owner(subjects,now):
            result=authority(subjects,now)
            if subjects==('COPPER',):
                if damage=='authority_missing': raise ValueError('private error must not escape')
                from dataclasses import replace
                return replace(result,methodology_reference='')
            return result
        packs.authority_provider=owner
    else:
        from kronos.theta import packs as module
        original=module.render_transport
        def render(q,charts):
            if q['subjects']==['COPPER']: raise ValueError('private rendering failure')
            return original(q,charts)
        monkeypatch.setattr(module,'render_transport',render)
    result=packs.commission_questions(SUBJECTS)
    assert result['states']['COPPER']['status']=='BLOCKED'
    assert all(result['states'][s]['status']=='READY' for s in SUBJECTS if s!='COPPER')
    assert not result['complete'] and 'PARTIAL' in packs.transport_filename(result['batch_id'],'zip')
    files=manifest_valid(packs.transport(result['batch_id'],'zip'))
    assert not any(n.startswith('individual/COPPER/') for n in files)
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('failure',['macro_missing','no_authority','not_qualification'])
def test_mandatory_input_absence_does_not_publish_a_genuine_pack(packs,failure):
    if failure=='macro_missing':
        with packs.store.transaction():
            selection=packs.store.current(); selection.pop('macro'); packs.store.select(selection)
    elif failure=='no_authority': packs.authority_provider=None
    else: packs.qualification_mode=False
    result=packs.commission_questions(SUBJECTS)
    assert result['batch_id'] is None and all(s['status']=='BLOCKED' for s in result['states'].values())
    assert not packs.outbox.exists() and not (packs.store.root/'questions').exists()


def test_publication_no_clobber_symlink_and_historical_outputs(packs,tmp_path):
    result=commission(packs); q=question(packs,result)
    outputs={p.name:p.read_bytes() for p in packs.outbox.iterdir()}
    name=pack_name(q,'zip'); (packs.outbox/name).write_bytes(b'UNRELATED EXISTING BYTES')
    again=packs.commission_questions(('GOLDM',))
    assert again['states']['GOLDM']['status']=='BLOCKED' and (packs.outbox/name).read_bytes()==b'UNRELATED EXISTING BYTES'
    assert all((packs.outbox/n).read_bytes()==v for n,v in outputs.items() if n!=name)
    outside=tmp_path.resolve()/'outside'; outside.mkdir()
    link=tmp_path.resolve()/'linked-outbox'; link.symlink_to(outside,target_is_directory=True)
    packs.outbox=link
    assert packs.commission_questions(('SILVERM',))['states']['SILVERM']['status']=='BLOCKED'
    assert not list(outside.iterdir())


def test_safe_path_contract_and_individual_output_names(packs):
    from kronos.theta.store import DEFAULT_OUTBOX, DEFAULT_INBOX
    assert DEFAULT_OUTBOX.parts[-4:]==('Project-KRONOS','KRONOS REVIEW PACK','Theta Earners','KRONOS QUESTIONS')
    assert DEFAULT_INBOX.parts[-4:]==('Project-KRONOS','KRONOS REVIEW PACK','Theta Earners','CHATGPT ANSWERS')
    assert DEFAULT_OUTBOX.parent.name==DEFAULT_INBOX.parent.name=='Theta Earners'
    result=commission(packs)
    for subject in SUBJECTS:
        q=question(packs,result,subject)
        for kind in ('pdf','zip','template'):
            name=packs.transport_filename(q['question_id'],kind)
            assert name.startswith('SYNTHETIC_THETA_') and subject in name and len(name)<=160
            assert (packs.outbox/name).read_bytes()==packs.transport(q['question_id'],kind)


def test_pdf_mandate_readability_layout_images_and_deterministic_render(packs):
    result=commission(packs,('COPPER',)); q=question(packs,result,'COPPER')
    binary=packs.transport(q['question_id'],'pdf')
    reader=PdfReader(BytesIO(binary),strict=True)
    text='\n'.join(p.extract_text() for p in reader.pages)
    for value in ('SYNTHETIC - NOT FOR GENUINE FORECASTING','COPPER','ASTRA-ULTRA',
                  'Research depth before response speed','Chart assessment T1-T8','especially deep Copper',
                  'Do not manufacture research volume','independently','no-touch','NOT_EVALUABLE',
                  'frozen','available_at','accessed_at','counterevidence'):
        assert value.lower() in text.lower()
    assert len([p for p in reader.pages if p.mediabox.width>p.mediabox.height])==2
    assert len([image for page in reader.pages for image in page.images])==2
    assert '/private/' not in text and '/Users/' not in text
    charts={c['sha256']:packs.chart_bytes(c['sha256']) for c in [q['charts'][0],q['macro_chart']]}
    assert render_transport(q,charts)[0]==binary


def test_real_browser_question_post_five_independent_packs_readonly_views_and_origin_guard(packs):
    with running(packs) as server:
        before=request(server,'GET','/theta-earners')[2]
        assert request(server,'POST','/theta-earners/question',value={'subject':list(SUBJECTS)},origin='http://foreign.invalid')[0]==403
        status,_,body=request(server,'POST','/theta-earners/question',value={'subject':list(SUBJECTS)})
        assert status==200 and b'QUESTION PACK READY' in body and b'OPEN QUESTION PACK' in body
        assert b'required for TE-02 Question packs' in body and b'no new Question gate' not in body
        result=packs.question_batch()['batch']
        assert len({v['question_id'] for v in result['states'].values()})==5
        assert request(server,'GET','/theta-earners')[2]==before
        for subject,state in result['states'].items():
            for kind,content_type in (('pdf','application/pdf'),('zip','application/zip'),('template','application/json')):
                status,headers,payload=request(server,'GET','/theta-earners/question-pack?'+urlencode({'question':state['question_id'],'kind':kind}))
                assert status==200 and headers['Content-Type']==content_type and payload==packs.transport(state['question_id'],kind)
        assert b'/private/var/folders/' not in body and b'data-upload-url=' in body


def test_restart_restores_exact_pack_and_no_mtime_or_orphan_authority(packs):
    result=commission(packs); before=inventory(packs)
    restored=ThetaWorkflow(ThetaStore(packs.store.root),inbox=packs.inbox,outbox=packs.outbox,clock=lambda:NOW)
    assert restored.question_batch()['batch']['batch_id']==result['batch_id']
    assert inventory(restored)==before
    assert restored.transport(result['batch_id'],'zip')==packs.transport(result['batch_id'],'zip')


@pytest.mark.parametrize('change',['target','methodology'])
def test_changed_governed_authority_creates_new_question_without_historical_rewrite(packs,change):
    first=commission(packs,('GOLDM',)); old=question(packs,first)
    binary=packs.transport(old['question_id'],'zip')
    def updated(subjects,now):
        bundle=authority(subjects,now)
        if change=='target':
            return replace(bundle,targets=tuple(replace(t,settlement_reference=t.settlement_reference+'_REVISED') for t in bundle.targets))
        return replace(bundle,methodology_reference=bundle.methodology_reference+'_REVISED')
    packs.authority_provider=updated
    packs.clock=lambda:NOW+timedelta(minutes=1)
    new=question(packs,commission(packs,('GOLDM',)))
    assert new['question_id']!=old['question_id'] and new['information_cutoff']!=old['information_cutoff']
    assert packs.store.question(old['question_id'])==old and packs.transport(old['question_id'],'zip')==binary


def test_prospective_answer_acceptance_and_immutable_replay_are_version_aware(packs):
    q=question(packs,commission(packs,('GOLDM',)))
    answer=complete_answer(packs,q)
    packs.clock=lambda:NOW+timedelta(hours=3)
    with directory(packs.inbox,create=True): pass
    place(packs,q['question_id'],answer)
    packs.import_answer(q['question_id'])
    before=inventory(packs)
    assert packs.detail(q['question_id'])['answer']==answer
    with running(packs) as server:
        status,_,body=request(server,'GET','/theta-earners/detail?'+urlencode({'question':q['question_id'],'subject':'GOLDM'}))
        assert status==200 and b'Analysis completed:' in body and b'Analysis T0:' not in body
        assert b'Available: 2026-10-11T09:00:00+00:00' in body
    packs.import_answer(q['question_id'])
    assert inventory(packs)==before
    assert packs.summary()[0]['status']=='ACCEPTED_EXTERNAL_EVIDENCE'
    receive(packs,'GLOBAL_MACRO',payload=composite('GLOBAL_MACRO')+b'\x00')
    before=inventory(packs)
    packs.import_answer(q['question_id'])
    assert inventory(packs)==before and packs.detail(q['question_id'])['answer']==answer
    assert not packs.detail(q['question_id'])['current_subjects']
    assert packs.summary()[0]['status']=='QUESTION_INPUT_CHANGED'


def test_changed_macro_prevents_current_acceptance_of_old_prospective_answer(packs):
    q=question(packs,commission(packs,('GOLDM',)))
    answer=complete_answer(packs,q)
    packs.clock=lambda:NOW+timedelta(hours=3)
    receive(packs,'GLOBAL_MACRO',payload=composite('GLOBAL_MACRO')+b'\x00')
    with directory(packs.inbox,create=True): pass
    place(packs,q['question_id'],answer)
    with pytest.raises(ThetaError): packs.import_answer(q['question_id'])
    assert not (packs.store.root/'accepted').exists()
    assert packs.summary()[0]['status']=='QUESTION_INPUT_CHANGED'


def test_corrupt_retained_transport_is_not_recreated_from_current_inputs(packs):
    from kronos.theta.store import unseal
    q=question(packs,commission(packs,('GOLDM',)))
    record=unseal(packs.store.load('transports',q['question_id']+'.json'))
    (packs.store.root/'blobs'/record['pdf_sha256']).write_bytes(b'SYNTHETIC DAMAGED PDF')
    before=inventory(packs)
    with pytest.raises(ThetaError): packs.transport(q['question_id'],'pdf')
    assert packs.commission_questions(('GOLDM',))['states']['GOLDM']['status']=='BLOCKED'
    assert inventory(packs)==before


def test_publication_conflict_preflight_does_not_publish_other_missing_outputs(packs):
    q=question(packs,commission(packs,('GOLDM',)))
    pdf=pack_name(q,'pdf'); template=pack_name(q,'template'); archive=pack_name(q,'zip')
    (packs.outbox/pdf).unlink(); (packs.outbox/template).unlink()
    (packs.outbox/archive).write_bytes(b'EXISTING FOREIGN CONTENT')
    assert packs.commission_questions(('GOLDM',))['states']['GOLDM']['status']=='BLOCKED'
    assert not (packs.outbox/pdf).exists() and not (packs.outbox/template).exists()
    assert (packs.outbox/archive).read_bytes()==b'EXISTING FOREIGN CONTENT'


def test_emit_synthetic_sponsor_artifacts(packs,request):
    from tests.unit.theta.conftest import qualification_output
    output=qualification_output(request)
    if output is None: return
    result=commission(packs)
    with directory(output,create=True) as fd:
        for subject in SUBJECTS:
            q=question(packs,result,subject)
            for kind in ('pdf','zip','template'):
                write_at(fd,packs.transport_filename(q['question_id'],kind),packs.transport(q['question_id'],kind))
        write_at(fd,packs.transport_filename(result['batch_id'],'zip'),packs.transport(result['batch_id'],'zip'))
        metadata={'result':result,'batch':packs.question_batch()['batch'],
                  'files':{p.name:digest(p.read_bytes()) for p in packs.outbox.iterdir()},
                  'questions':{s:question(packs,result,s) for s in SUBJECTS}}
        write_at(fd,'te02-synthetic-artifact-manifest.json',encode(metadata))
