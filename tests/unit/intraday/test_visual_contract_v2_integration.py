"""WO-07C existing transport/store integration and deterministic PDF fixtures."""
from dataclasses import asdict, replace
from io import BytesIO
import json
import pytest
from kronos.intraday import visual_contract_v2 as v
from kronos.intraday.review import ReviewError
from kronos.intraday.review_mcx_paired import create_paired_review_pack, artifact_bytes, artifact_from_bytes, MCX_REFERENCE_RELATIONSHIPS
from kronos.intraday.review_mcx_paired_answer import parse_mcx_paired_answer, answer_template, answer_artifact_from_bytes, bind_mcx_paired_import
from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
from kronos.intraday.review_mcx_paired_transport import create_paired_transport
from kronos.intraday.visual_review_pdf import chart_dimensions
from .test_visual_contract_v2 import observation
from .test_review_mcx_paired import _foundation, _completed_answer, _resolver
from .test_review_v2_individual_inbox import _fixture, _cycles, _completed
from .test_review import _png


def paired(tmp_path):
    cycle, active, np, rp, native, reference, bundle, old = _foundation(tmp_path)
    new = create_paired_review_pack(bundle, created_at=old.created_at, question_version=v.VERSION)
    d = json.loads(answer_template(new,bundle))
    d["native_observed_visible_identity"] = native.expected_visible_identity
    d["reference_observed_visible_identity"] = "Independent listed benchmark series"
    for key, questions in (("reference_answers",v.MCX_QUESTIONS[:5]),("native_answers",v.MCX_QUESTIONS[5:10]),("cross_market_answers",v.MCX_QUESTIONS[10:14])):
        d[key] = [asdict(observation(q,answer="NOT_OBSERVABLE" if q.question_id in {"R5","M5","X3"} else None)) for q in questions]
    d["escape_hatch_answer"] = asdict(observation(v.MCX_QUESTIONS[-1]))
    return (cycle, active, np, rp, native, reference, bundle, old, new, d)


def test_mcx_v1_v2_roundtrip_import_and_exact_contract_binding(tmp_path):
    cycle,active,np,rp,native,reference,bundle,old,new,d = paired(tmp_path)
    old_bytes = artifact_bytes(old)
    old_answer = parse_mcx_paired_answer(_completed_answer(old,bundle,native.expected_visible_identity))
    old_answer_bytes = artifact_bytes(old_answer)
    assert "cross_market_answers" not in json.loads(old_answer_bytes)
    assert answer_artifact_from_bytes(old_answer_bytes) == old_answer
    answer = parse_mcx_paired_answer(json.dumps(d).encode())
    assert answer_artifact_from_bytes(artifact_bytes(answer)) == answer
    assert artifact_from_bytes(artifact_bytes(new)) == new
    resolver = _resolver(active.active_binding.derivative_contract_id,native.expected_visible_identity,cycle.analysis_boundary)
    evidence = bind_mcx_paired_import(pack=new,bundle=bundle,native_chart=native,reference_chart=reference,
        answer=answer,native_resolver=resolver,reference_resolver=resolver,imported_at=new.created_at,supporting_reference_only=True)
    assert answer_artifact_from_bytes(artifact_bytes(evidence)) == evidence
    store = IntradayMcxPairedReviewStore(tmp_path/'paired-restored')
    store.retain_pack(new); store.retain_answer(answer, json.dumps(d).encode()); store.retain_evidence(evidence)
    assert store.load_pack(new.review_pack_identity) == new
    for pack, item in ((old,answer),(new,old_answer)):
        with pytest.raises(ReviewError):
            bind_mcx_paired_import(pack=pack,bundle=bundle,native_chart=native,reference_chart=reference,
                answer=item,native_resolver=resolver,reference_resolver=resolver,imported_at=new.created_at,supporting_reference_only=True)
    assert artifact_bytes(old) == old_bytes


@pytest.mark.parametrize("mutation", ["schema","version","set","native_side","cross_order","missing","extra","unknown_field","old_question","escape","timeframe"])
def test_mcx_v2_strict_schema_and_side_order(tmp_path,mutation):
    *_,d = paired(tmp_path)
    if mutation == "schema": d['schema_identity']='KRONOS-INTRADAY-MCX-PAIRED-ANSWER-PACK-V1'
    elif mutation == "version": d['schema_version']='1.0.0'
    elif mutation == "set": d['question_set_identity']='FOREIGN'
    elif mutation == "native_side": d['native_answers']=d['reference_answers']
    elif mutation == "cross_order": d['cross_market_answers'].reverse()
    elif mutation == "missing": d['reference_answers'].pop()
    elif mutation == "extra": d['native_answers'].append(d['native_answers'][0])
    elif mutation == "unknown_field": d['native_answers'][0]['score']=1
    elif mutation == "old_question": d['native_answers'][0]['question_id']='M01'
    elif mutation == "escape": d['escape_hatch_answer']['why_not_covered_elsewhere']='Repeated answer'
    else: d['native_answers'][1]['visible_timeframes']=['1H']
    with pytest.raises(ReviewError): parse_mcx_paired_answer(json.dumps(d).encode())


@pytest.mark.parametrize("relationship",MCX_REFERENCE_RELATIONSHIPS,ids=lambda r:r.canonical_mcx_subject_identity)
def test_benchmarks_reuse_exact_registry(relationship):
    from kronos.intraday.review_mcx_paired import relationship_for_subject
    assert relationship_for_subject(relationship.canonical_mcx_subject_identity) == relationship
    assert relationship.venue.value in {"COMEX","NYMEX"}
    assert relationship.governed_visible_identity.endswith('1!')
    # No listed-series alias or constituent relationship is constructed.
    assert not hasattr(relationship,'listed_constituent')


def test_individual_v2_import_replay_restoration_and_noncurrent(tmp_path):
    from .test_review_v2 import _retain_later_current_run
    from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
    _, app = _fixture(tmp_path,('BDL',))
    cycle = _cycles(app)['BDL'].cycle_identity
    chart=app.upload_chart(cycle,media_type='image/png',payload=_png(19))
    transport=app.create_individual_question_transport(cycle)
    assert transport.packs[0].question_set_version == v.VERSION
    expected=app._transport.answer_inbox/transport.transport.expected_answer_filename
    expected.write_bytes(_completed(transport.answer_template_path))
    assert app.import_expected_answer(cycle).imported_count == 1
    assert app.import_expected_answer(cycle).already_imported_count == 1
    pack=transport.packs[0]
    evidence=app.review_store.load_visual_evidence_for_pack(pack.review_pack_identity)
    assert IntradayReviewV2Store(app.review_store.root).load_visual_evidence_for_pack(pack.review_pack_identity)==evidence
    before={p.relative_to(app.review_store.root):p.read_bytes() for p in app.review_store.root.rglob('*') if p.is_file()}
    _retain_later_current_run(app)
    assert app.import_expected_answer(cycle).already_imported_count == 1
    with pytest.raises(ReviewError): app.create_individual_question_transport(cycle)
    for name,payload in before.items(): assert (app.review_store.root/name).read_bytes()==payload
    altered=json.loads(expected.read_bytes());altered['candidates'][0]['answers'][0]['visible_basis']='Different evidence'
    expected.write_text(json.dumps(altered))
    assert app.import_expected_answer(cycle).rejected_count == 1


def test_aspect_ratio_and_nse_pdf_orientation(tmp_path):
    from pypdf import PdfReader
    _,app=_fixture(tmp_path,('M&M',))
    cycle=_cycles(app)['M&M'].cycle_identity
    app.upload_chart(cycle,media_type='image/png',payload=composite(1))
    result=app.create_individual_question_transport(cycle)
    assert result == app.create_individual_question_transport(cycle)
    text=' '.join(p.extract_text() for p in PdfReader(result.question_path).pages)
    assert 'M&M' in text and 'Analysis boundary:' in text
    assert result.transport.expected_answer_filename in text
    assert v.NSE_QUESTION_SET in text and 'Q10' in text
    for width,height in [(1920,1080),(3840,1080),(800,1200)]:
        w,h=chart_dimensions(width,height)
        assert w/h == pytest.approx(width/height)
    assert json.loads(result.answer_template_path.read_bytes())['schema_identity']==v.NSE_BATCH_ANSWER_SCHEMA


def composite(rows=2):
    from PIL import Image, ImageDraw
    im=Image.new('RGB',(2000,rows*420),'#f3f6fa');d=ImageDraw.Draw(im)
    for row in range(rows):
        for col,tf in enumerate(('1D','4H' if rows==2 else '1H','15M','5M')):
            x,y=col*500,row*420
            d.rectangle((x+5,y+5,x+495,y+415),outline='#64748b',width=2)
            d.text((x+20,y+20),f'SYNTHETIC QUALIFICATION | {"REFERENCE" if row==0 and rows==2 else "NATIVE"} | {tf}',fill='black')
            for i in range(22):
                cx=x+25+i*20;cy=y+230-(i%7)*13
                d.line((cx,cy-22,cx,cy+22),fill='#147d64',width=2)
                d.rectangle((cx-4,cy-8,cx+4,cy+10),fill='#147d64')
            d.text((x+20,y+380),'CONSTRUCTED FIXTURE - NO MARKET / ANALYST CLAIM',fill='#334155')
    stream=BytesIO();im.save(stream,format='PNG');return stream.getvalue()


def test_mcx_pdf_single_composite_and_template(tmp_path):
    from pypdf import PdfReader
    from .test_review_v2_paired_intake import paired_fixture
    app,cycle,metadata=paired_fixture(tmp_path)
    app.upload_chart(cycle.cycle_identity,media_type='image/png',payload=composite(),paired_metadata=metadata)
    result=app.create_individual_question_transport(cycle.cycle_identity)
    reader=PdfReader(result.question_path)
    text=' '.join(p.extract_text() for p in reader.pages)
    assert 'TOP = INTERNATIONAL' in text and 'BOTTOM = NATIVE' in text
    assert 'USDINR FUTURES' in text and 'NOT_ESTABLISHED' in text and v.MCX_QUESTION_SET in text
    assert result.transport.expected_answer_filename in text
    assert sum(len(p.images) for p in reader.pages)==1
    assert not any('1H' in q['visible_timeframes'] for q in json.loads(result.answer_template_path.read_bytes())['native_answers'])


def test_batch_schema_failure_keeps_lawful_member_and_replay(tmp_path):
    _,app=_fixture(tmp_path,('BDL','SRF'))
    for n,c in enumerate(app.snapshot().candidates):
        app.upload_chart(c.cycle_identity,media_type='image/png',payload=_png(40+n))
    result=app.create_combined_question_transport()
    d=json.loads(_completed(result.answer_template_path))
    d['candidates'][1]['answers'][0]['answer']='UNAUTHORIZED_ENUM'
    expected=app._transport.answer_inbox/result.transport.expected_answer_filename
    expected.write_text(json.dumps(d))
    partial=app.import_all_expected_answers()
    assert (partial.imported_count,partial.rejected_count)==(1,1)
    retained=app.review_store.load_visual_evidence_for_pack(result.packs[0].review_pack_identity)
    replay=app.import_all_expected_answers()
    assert (replay.already_imported_count,replay.rejected_count)==(1,1)
    assert app.review_store.load_visual_evidence_for_pack(result.packs[0].review_pack_identity)==retained
    assert app.review_store.load_visual_evidence_for_pack(result.packs[1].review_pack_identity) is None


def test_new_pack_does_not_rewrite_retained_v1(tmp_path):
    from kronos.intraday.review_v2 import create_question_pack_v2
    _,app=_fixture(tmp_path,('BDL',))
    cycle=app.review_store.load_cycle(_cycles(app)['BDL'].cycle_identity)
    chart=app.upload_chart(cycle.cycle_identity,media_type='image/png',payload=_png(49))
    handoff=app.review_store.load_handoff(cycle.handoff_identity)
    old=create_question_pack_v2(handoff,cycle,chart)
    prior=app._create_question_transport(((old,app.review_store.load_chart_bytes(chart)),))
    before={p:p.read_bytes() for p in app.review_store.root.rglob('*') if p.is_file()}
    assert app._load_retained_current_pack(cycle)==old
    modern=app.create_individual_question_transport(cycle.cycle_identity)
    assert modern.packs[0].question_set_version=='2.0.0'
    assert modern.transport.expected_answer_filename!=prior.transport.expected_answer_filename
    assert app._load_retained_current_pack(cycle)==modern.packs[0]
    assert all(p.read_bytes()==payload for p,payload in before.items())
    assert app.review_store.load_pack(old.review_pack_identity)==old


@pytest.mark.parametrize('change',['missing','tampered','foreign'])
def test_v2_pack_restore_fails_closed(tmp_path,change):
    _,app=_fixture(tmp_path,('BDL',));cycle=_cycles(app)['BDL'].cycle_identity
    app.upload_chart(cycle,media_type='image/png',payload=_png(50))
    result=app.create_individual_question_transport(cycle)
    pack=result.packs[0]
    path=next(p for p in (app.review_store.root/'question-packs').glob('*.json') if pack.review_pack_identity in p.name)
    if change=='missing': path.unlink()
    elif change=='tampered': path.write_bytes(path.read_bytes().replace(b'PREVIOUS_COMPLETED_DAILY_HIGH',b'INVENTED_LEVEL'))
    else: path.write_bytes(b'{}')
    with pytest.raises(ReviewError): app.review_store.load_pack(pack.review_pack_identity)
    assert app.review_store.load_current_chart(cycle) is not None
