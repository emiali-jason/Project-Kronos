"""TE-04A contract/schema qualification; synthetic and kernel-isolated only."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import pytest

from kronos.theta.contracts import SUBJECTS, digest, encode, validate_answer
from kronos.theta.contracts_v3 import (
    combined_answer_schema, combined_answer_template, make_question_v3, make_question_batch_v3,
    replay_disposition, validate_answer_v3, validate_combined_answer, validate_question_v3)
from kronos.theta.schema_v3 import (
    ANSWER, BATCH, QUESTION, MAX_CHILD_BYTES, MAX_COMBINED_BYTES, MAX_DEPTH,
    RESEARCH_SECTIONS, RELATIONSHIPS, V3Error, producer_instructions, schema_document, validate_shape)
from tests.unit.theta.v3_fixture import T0, RECEIPT, synthetic_contracts
from tests.unit.theta.test_workflow import workflow, NOW, valid_answer
from tests.unit.theta.test_question_packs import packs, commission, question, complete_answer


@pytest.fixture
def contracts():
    return synthetic_contracts()


def validate(c):
    q,b,a=c
    return validate_combined_answer(encode(a),batch=b,questions=q,received_at=RECEIPT)


def test_complete_independent_subjects_cutoffs_and_lossless_values(contracts):
    q,b,a=contracts; before=deepcopy(contracts); result=validate(contracts)
    assert result.complete and len(result.children)==5 and contracts==before
    assert len({c.answer['information_cutoff'] for c in result.children})==5
    for c in result.children:
        assert c.answer==a['answers'][c.subject]
        assert c.answer['forecasts']['E1']['lower']=='-10.00'
        assert c.answer['forecasts']['E2']['upper']=='120.000'
        assert validate_answer_v3(c.representation.raw_bytes,q[c.subject],received_at=RECEIPT)==c.answer


def test_schema_template_instructions_and_every_object_closed(contracts):
    q,b,a=contracts; schema=combined_answer_schema(b,q); validate_shape(a,schema)
    template=combined_answer_template(b,q)
    assert set(template['answers'])==set(SUBJECTS)
    with pytest.raises(V3Error): validate_shape(template,schema)
    result=validate_combined_answer(encode(template|{'answer_package_id':'SYNTHETIC-BLANK'}),batch=b,questions=q,received_at=RECEIPT)
    assert all(c.failure_code for c in result.children)
    text=producer_instructions()
    assert all(value in text for value in RELATIONSHIPS)
    assert 'do not optimize' in text.lower() and 'Kite/Provider' in text and 'NOT_EVALUABLE forecast branch' in text
    def closed(s):
        if s.get('type')=='object':
            assert s['additionalProperties'] is False and set(s['required'])==set(s['properties'])
            for child in s['properties'].values(): closed(child)
        if 'items' in s: closed(s['items'])
        for child in s.get('anyOf',[]): closed(child)
    closed(schema)


@pytest.mark.parametrize('field',['schema_identity','schema_version','answer_package_id','cycle_id','question_batch_id','question_batch_sha256','answers'])
def test_envelope_required(contracts,field):
    contracts[2].pop(field)
    with pytest.raises(V3Error): validate(contracts)


@pytest.mark.parametrize('mutation',['extra','sixth','missing','cycle','batch','version'])
def test_global_envelope_failure(contracts,mutation):
    a=contracts[2]
    if mutation=='extra': a['private']='forbidden'
    elif mutation=='sixth': a['answers']['GLOBAL_MACRO']=deepcopy(a['answers']['GOLDM'])
    elif mutation=='missing': a['answers'].pop('COPPER')
    elif mutation=='cycle': a['cycle_id']='OTHER'
    elif mutation=='batch': a['question_batch_sha256']='0'*64
    else: a['schema_version']='3.0.0'
    with pytest.raises(V3Error): validate(contracts)


BINDING_PATHS=[
    ('schema_identity',),('schema_version',),('question_id',),('question_sha256',),('information_cutoff',),
    ('binding','subject'),('binding','canonical_subject'),('binding','cycle_id'),
    *[('binding',kind,key) for kind in ('commodity_chart','macro_chart') for key in ('chart_id','revision_id','sha256')],
    *[('binding',kind,key) for kind in ('methodology','target_authority') for key in ('identity','version','sha256')],
    ('forecasts','E1','target','underlying_future'),('forecasts','E2','target','option_expiry'),
]
@pytest.mark.parametrize('path',BINDING_PATHS)
def test_child_binding_failure_isolated(contracts,path):
    c=contracts[2]['answers']['COPPER']
    for p in path[:-1]: c=c[p]
    key=path[-1]
    c[key]='0'*64 if key.endswith('sha256') else '2026-11-26' if key=='option_expiry' else '9.0.0' if key in {'version','schema_version'} else '2026-10-12T08:01:00+00:00' if key=='information_cutoff' else 'GOLDM' if key=='subject' else 'FOREIGN'
    result=validate(contracts)
    assert not result.complete and [c.subject for c in result.children if c.failure_code]==['COPPER']


@pytest.mark.parametrize('field',list(ANSWER['properties']))
@pytest.mark.parametrize('action',['missing','extra'])
def test_child_closed_fields(contracts,field,action):
    c=contracts[2]['answers']['GOLDM']
    if action=='missing': c.pop(field)
    else: c[field+'-extra']='forbidden'
    assert [c.subject for c in validate(contracts).children if c.failure_code]==['GOLDM']


@pytest.mark.parametrize('bad',['100.00','120.000','130',100.0,True,'NaN','Infinity','1e2',' 100','+100','01'])
def test_strict_ranges_and_decimal_strings(contracts,bad):
    f=contracts[2]['answers']['GOLDM']['forecasts']['E1']; f.update(lower=bad,upper='100.00')
    assert validate(contracts).children[0].failure_code


@pytest.mark.parametrize('bad',['-0.1','100.1','NaN',True,82.0])
def test_confidence(contracts,bad):
    contracts[2]['answers']['GOLDM']['forecasts']['E2']['confidence_pct']=bad
    assert validate(contracts).children[0].failure_code


@pytest.mark.parametrize('path',[
    ('evidence_items',0,'source_ids'),('evidence_items',0,'observation_ids'),('evidence_items',0,'assumption_ids'),
    ('relationships',0,'limitation_ids'),('scheduled_events',0,'evidence_ids'),('sources',0,'linked_evidence_ids'),
    ('assumptions',0,'supporting_evidence_ids'),('limitations',0,'supporting_evidence_ids'),
])
def test_reference_resolution(contracts,path):
    r=contracts[2]['answers']['COPPER']['research']
    for key in path[:-1]: r=r[key]
    r[path[-1]]=['FOREIGN-REFERENCE']
    assert [c.subject for c in validate(contracts).children if c.failure_code]==['COPPER']


@pytest.mark.parametrize('family',['relationships','assumptions','limitations'])
def test_typed_reference_resolution(contracts,family):
    r=contracts[2]['answers']['COPPER']['research'][family][0]
    r['references' if family=='relationships' else 'affected_references'][0]['identity']='FOREIGN'
    assert validate(contracts).children[2].failure_code=='THETA_V3_REFERENCE'


@pytest.mark.parametrize('field',['published_at','available_at','accessed_at'])
def test_source_chronology(contracts,field):
    contracts[2]['answers']['COPPER']['research']['sources'][0][field]=(RECEIPT+timedelta(hours=1)).isoformat()
    assert validate(contracts).children[2].failure_code=='THETA_V3_CHRONOLOGY'


def test_later_retrieval_and_separate_availability_publication(contracts):
    s=contracts[2]['answers']['GOLDM']['research']['sources'][0]
    s['published_at']=(T0-timedelta(minutes=10)).isoformat()
    assert validate(contracts).complete
    s['published_at']=None
    assert validate(contracts).complete


@pytest.mark.parametrize('family',['relationships','chart_observations','scheduled_events'])
def test_unavailable_must_not_fabricate(contracts,family):
    r=contracts[2]['answers']['GOLDM']['research'][family][0]
    if family=='relationships': r['relationship_type']='UNRESOLVED_CONTRADICTION'
    else: r['availability']='UNAVAILABLE'
    assert validate(contracts).children[0].failure_code=='THETA_V3_AVAILABILITY'


def test_explicit_unavailable_and_not_applicable(contracts):
    r=contracts[2]['answers']['GOLDM']['research']
    r['bullish_evidence']={'availability':'NOT_APPLICABLE','classification':None,'text':None,'reason':'SYNTHETIC no claimed support','evidence_ids':[]}
    r['chart_observations'][0].update(availability='UNAVAILABLE',observation_text=None,classification=None,
        unavailable_reason='SYNTHETIC unreadable observation',visible_as_of=T0.isoformat())
    r['scheduled_events'][0].update(availability='UNAVAILABLE',scheduled_window=None,schedule_source_id=None,
        schedule_known_at=None,possible_impact=None)
    assert validate(contracts).complete


@pytest.mark.parametrize('mutation',['duplicate','lineage','cycle','event_source','event_time','observation_time','horizon','macro','verdict','url'])
def test_graph_adversaries(contracts,mutation):
    c=contracts[2]['answers']['COPPER']; r=c['research']
    if mutation=='duplicate': r['sources'][0]['source_id']='CLAIM-1'
    elif mutation=='lineage': r['sources'][0]['lineage']['original_information_id']='MADE-UP'
    elif mutation=='cycle': r['sources'][0]['lineage']={'status':'KNOWN','original_information_id':'ORIGIN','derivative_source_ids':['SOURCE-1']}
    elif mutation=='event_source': r['scheduled_events'][0]['schedule_source_id']='MISSING'
    elif mutation=='event_time': r['scheduled_events'][0]['schedule_known_at']=RECEIPT.isoformat()
    elif mutation=='observation_time': r['chart_observations'][0]['visible_as_of']=RECEIPT.isoformat()
    elif mutation=='horizon': r['evidence_items'][0]['horizons']=['E2']
    elif mutation=='macro': r['chart_observations'][0]['role']='MACRO'
    elif mutation=='verdict': c['quality_score']='99'
    else: r['sources'][0]['url']='file:///private/sensitive'
    assert [c.subject for c in validate(contracts).children if c.failure_code]==['COPPER']


@pytest.mark.parametrize('field',['instrument_token','api_key','session','positions','margin','intended_strikes','option_expression','quality_score','promotion_state'])
def test_private_and_verdict_fields_rejected(contracts,field):
    contracts[2]['answers']['GOLDM']['binding'][field]='SYNTHETIC FORBIDDEN'
    assert validate(contracts).children[0].failure_code


@pytest.mark.parametrize('url',['https://user:secret@example.com/x','https://example.com/x?access_token=SYNTHETIC','http://127.0.0.1:8947/','http://localhost:8948/','https://[invalid/x'])
def test_private_urls_fail_closed(contracts,url):
    contracts[2]['answers']['GOLDM']['research']['sources'][0]['url']=url
    assert validate(contracts).children[0].failure_code=='THETA_V3_PROVIDER_NEUTRAL'


@pytest.mark.parametrize('raw',[b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'{"x":1e400}',b'{} trailing',b'\xff',b'{"x":"\\ud800"}'])
def test_raw_json_failures(contracts,raw):
    q,b,_=contracts
    with pytest.raises(V3Error): validate_combined_answer(raw,batch=b,questions=q,received_at=RECEIPT)


def test_nested_duplicates_and_depth(contracts):
    q,b,a=contracts
    raw=encode(a).replace(b'"confidence_pct":"82.00"',b'"confidence_pct":"82.00","confidence_pct":"82.00"',1)
    with pytest.raises(V3Error,match='DUPLICATE_KEY'): validate_combined_answer(raw,batch=b,questions=q,received_at=RECEIPT)
    raw=b'{"x":'+b'['*(MAX_DEPTH+1)+b'0'+b']'*(MAX_DEPTH+1)+b'}'
    with pytest.raises(V3Error,match='SIZE'): validate_combined_answer(raw,batch=b,questions=q,received_at=RECEIPT)


def test_exact_child_bytes_unicode_escapes_and_hashes(contracts):
    q,b,a=contracts
    a['answers']['GOLDM']['research']['commodity_research']['text']='SYNTHETIC ₹ ⛄ { } and quote "'
    raw=json.dumps(a,indent=3,ensure_ascii=False).encode()+b'\n'
    result=validate_combined_answer(raw,batch=b,questions=q,received_at=RECEIPT)
    assert result.complete and result.raw_sha256==digest(raw) and result.canonical_sha256==digest(encode(a))
    assert result.raw_sha256!=result.canonical_sha256
    for c in result.children:
        p=c.representation
        assert raw[p.start:p.end]==p.raw_bytes and json.loads(p.raw_bytes)==c.answer
        assert p.raw_sha256==digest(p.raw_bytes) and p.canonical_sha256==digest(encode(c.answer))
        assert p.raw_bytes!=encode(c.answer)
    escaped=json.dumps(a,ensure_ascii=True).encode().replace(b'"GOLDM":',b'"\\u0047OLDM":',1)
    assert validate_combined_answer(escaped,batch=b,questions=q,received_at=RECEIPT).complete


def test_replay_and_duplicate_answer_identity(contracts):
    result=validate(contracts)
    args=dict(original_identity=result.answer_package_id,original_raw_sha256=result.raw_sha256,
              candidate_identity=result.answer_package_id,candidate_raw_sha256=result.raw_sha256)
    assert replay_disposition(**args)=='IDENTICAL_REPLAY'
    with pytest.raises(V3Error,match='IDENTITY_CONFLICT'): replay_disposition(**(args|{'candidate_raw_sha256':'0'*64}))
    assert replay_disposition(**(args|{'candidate_identity':'NEW-ID'}))=='NEW_IDENTITY'
    contracts[2]['answers']['COPPER']['answer_id']=contracts[2]['answers']['GOLDM']['answer_id']
    assert [c.subject for c in validate(contracts).children if c.failure_code]==['GOLDM','COPPER']


def test_bounds_without_truncation(contracts):
    text='x'*16001; contracts[2]['answers']['COPPER']['research']['commodity_research']['text']=text
    assert validate(contracts).children[2].failure_code
    assert contracts[2]['answers']['COPPER']['research']['commodity_research']['text']==text
    q,b,a=synthetic_contracts()
    with pytest.raises(V3Error,match='SIZE'):
        validate_answer_v3(encode(a['answers']['COPPER'])+b' '*MAX_CHILD_BYTES,q['COPPER'],received_at=RECEIPT)
    with pytest.raises(V3Error,match='SIZE'):
        validate_combined_answer(b' '*MAX_COMBINED_BYTES+b'1',batch=b,questions=q,received_at=RECEIPT)


@pytest.mark.parametrize('version',['1.0.0','2.0.0'])
def test_legacy_compatibility(workflow,packs,version):
    if version=='1.0.0':
        identity=workflow.create_question(('GOLDM',)); q=workflow.store.question(identity); a=valid_answer(workflow,identity)
    else:
        q=question(packs,commission(packs,('GOLDM',))); a=complete_answer(packs,q)
    for f in a['forecasts']: f.update(lower='100.000',upper='100.000')
    raw=json.dumps(a,indent=2).encode(); before=deepcopy(q)
    assert validate_answer(raw,q,received_at=NOW+timedelta(hours=3))==a and q==before and q['schema_version']==version
    assert raw==json.dumps(a,indent=2).encode()
    with pytest.raises(V3Error): validate_answer_v3(raw,q,received_at=NOW+timedelta(hours=3))


def test_no_silent_question_upgrade_or_private_authority(contracts):
    q,b,a=contracts; old=deepcopy(q['GOLDM'])
    with pytest.raises(V3Error): validate_question_v3(old|{'schema_version':'2.0.0'})
    with pytest.raises(V3Error): make_question_batch_v3({s:v for s,v in q.items() if s!='COPPER'})
    binding=deepcopy(old['binding']); binding['methodology']['identity']='KITE-PRIVATE'
    with pytest.raises(V3Error,match='PROVIDER_NEUTRAL'):
        make_question_v3(binding=binding,targets=old['targets'],created_at=old['created_at'],
            authority_valid_through=old['authority_valid_through'],methodology_instructions=old['methodology_instructions'],synthetic=True)
    assert q['GOLDM']==old


def test_write_synthetic_artifacts(request,contracts):
    destination=request.config.getoption('--theta-v3-contract-output')
    if destination is None: return
    from kronos.theta.store import directory,write_at
    p=Path(destination)
    assert p.is_absolute() and p.name=='theta-te04a-contract'
    q,b,a=contracts; raw=json.dumps(a,indent=2,ensure_ascii=False).encode()
    result=validate_combined_answer(raw,batch=b,questions=q,received_at=RECEIPT)
    assert result.complete
    files={'SYNTHETIC_QUESTIONS_V3.json':encode(q),'SYNTHETIC_QUESTION_BATCH_V3.json':encode(b),
        'SYNTHETIC_COMBINED_ANSWER_SCHEMA.json':encode(combined_answer_schema(b,q)),
        'SYNTHETIC_COMBINED_ANSWER_TEMPLATE.json':json.dumps(combined_answer_template(b,q),indent=2).encode(),
        'SYNTHETIC_COMPLETED_ANSWER.json':raw,'QUESTION_V3_SCHEMA.json':encode(schema_document(QUESTION)),
        'QUESTION_BATCH_V3_SCHEMA.json':encode(schema_document(BATCH)),
        'ASTRA_PRODUCER_INSTRUCTIONS.txt':('SYNTHETIC - NOT FOR GENUINE FORECASTING\n\n'+producer_instructions()).encode(),
        'SYNTHETIC_REPRESENTATION_PROOF.json':encode({'raw_sha256':result.raw_sha256,'canonical_sha256':result.canonical_sha256,
            'children':{c.subject:{'raw_sha256':c.representation.raw_sha256,'canonical_sha256':c.representation.canonical_sha256,
                                  'start':c.representation.start,'end':c.representation.end} for c in result.children}})}
    files['manifest.json']=encode({name:digest(payload) for name,payload in files.items()})
    with directory(p,create=True) as fd:
        for name,payload in files.items(): write_at(fd,name,payload)


@pytest.mark.parametrize('confidence',['0','0.00','100','100.000'])
def test_confidence_endpoints_remain_valid(contracts,confidence):
    contracts[2]['answers']['GOLDM']['forecasts']['E1']['confidence_pct']=confidence
    assert validate(contracts).complete


@pytest.mark.parametrize('mutation',['reversed','missing_horizon','third_horizon','null_forecast','wrong_date','expired','future_analysis','naive_receipt','null_child','array_child'])
def test_forecasts_and_receipt_boundaries(contracts,mutation):
    q,b,a=contracts; c=a['answers']['COPPER']
    receipt=RECEIPT
    if mutation=='reversed': c['forecasts']['E1'],c['forecasts']['E2']=c['forecasts']['E2'],c['forecasts']['E1']
    elif mutation=='missing_horizon': c['forecasts'].pop('E2')
    elif mutation=='third_horizon': c['forecasts']['E3']=deepcopy(c['forecasts']['E2'])
    elif mutation=='null_forecast': c['forecasts']['E1']=None
    elif mutation=='wrong_date': c['forecasts']['E1']['target']['option_expiry']='2026-10-26'
    elif mutation=='expired': receipt=RECEIPT+timedelta(days=30)
    elif mutation=='future_analysis': c['analyzed_at']=(RECEIPT+timedelta(hours=1)).isoformat()
    elif mutation=='naive_receipt': receipt=RECEIPT.replace(tzinfo=None)
    elif mutation=='null_child': a['answers']['COPPER']=None
    else: a['answers']['COPPER']=[]
    if mutation=='naive_receipt':
        with pytest.raises(V3Error): validate_combined_answer(encode(a),batch=b,questions=q,received_at=receipt)
    else:
        result=validate_combined_answer(encode(a),batch=b,questions=q,received_at=receipt)
        assert result.children[2].failure_code
        if mutation!='expired': assert sum(c.failure_code is not None for c in result.children)==1


@pytest.mark.parametrize('timestamp',['2026-10-12T08:00:00.0000001+00:00','2026-10-12T08:00:60+00:00','2026-10-12T08:00:00','2026-10-12T08:00:00Z\n'])
def test_timestamp_precision_and_format_not_coerced(contracts,timestamp):
    contracts[2]['answers']['GOLDM']['research']['sources'][0]['available_at']=timestamp
    assert validate(contracts).children[0].failure_code


def test_private_archive_locator_and_duplicate_references(contracts):
    s=contracts[2]['answers']['GOLDM']['research']['sources'][0]
    s['archive_version_locator']='https://example.com/archive?api_key=SYNTHETIC'
    assert validate(contracts).children[0].failure_code=='THETA_V3_PROVIDER_NEUTRAL'
    s['archive_version_locator']=None
    contracts[2]['answers']['GOLDM']['forecasts']['E1']['material_evidence_ids']=['CLAIM-1','CLAIM-1']
    assert validate(contracts).children[0].failure_code


def test_schema_exact_patterns_do_not_accept_trailing_newlines():
    import re
    from kronos.theta.schema_v3 import DECIMAL,ID,TIME
    for definition,value in ((DECIMAL,'100\n'),(ID,'PUBLIC-ID\n'),(TIME,'2026-10-12T08:00:00Z\n')):
        assert re.search(definition['pattern'],value) is None
        with pytest.raises(V3Error): validate_shape(value,definition)


def test_unknown_relationship_and_array_bounds(contracts):
    r=contracts[2]['answers']['GOLDM']['research']
    r['relationships'][0]['relationship_type']='STRONG'
    assert validate(contracts).children[0].failure_code
    r['relationships'][0]['relationship_type']='ALIGNMENT'
    r['sources']=[deepcopy(r['sources'][0]) for _ in range(201)]
    assert validate(contracts).children[0].failure_code


def test_fully_valid_known_lineage_and_macro_observation(contracts):
    r=contracts[2]['answers']['GOLDM']['research']
    s=deepcopy(r['sources'][0])
    s.update(source_id='SOURCE-2',linked_evidence_ids=[])
    s['lineage']={'status':'KNOWN','original_information_id':'SYNTHETIC-ORIGIN','derivative_source_ids':['SOURCE-1']}
    r['sources'].append(s)
    observation=deepcopy(r['chart_observations'][0])
    observation.update(observation_id='MACRO-OBS',role='MACRO',chart_reference=deepcopy(contracts[2]['answers']['GOLDM']['binding']['macro_chart']))
    r['chart_observations'].append(observation)
    assert validate(contracts).complete
