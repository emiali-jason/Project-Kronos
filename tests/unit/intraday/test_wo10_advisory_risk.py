"""Final Sponsor authority: factual Risk and warnings cannot grant or veto trades."""
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal as D
import json
import pytest
from kronos.intraday.wo10_futures_contract import record,require,Record,digest,encoded,LEGACY_CHECKSUM,LEGACY_BOUNDARY,VERSION,POLICY_VERSION
from kronos.intraday.wo10_futures_risk import risk_advisory
from tests.unit.intraday.test_wo10_futures import fixture,config,NOW,session


def files(root):
    return {str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}

@pytest.mark.parametrize('amount,lots,state,excess,percent',[
    ('2000',4,'WITHIN_REFERENCE','-400','-20'),('2000',5,'WITHIN_REFERENCE','0','0'),
    ('2000',6,'ABOVE_REFERENCE','400','20'),('100',1,'ABOVE_REFERENCE','300','300'),
    ('0',1,'ABOVE_REFERENCE','400',None), (None,999,'REFERENCE_NOT_CONFIGURED',None,None)])
def test_quantity_advisory_exact_and_never_caps(tmp_path,amount,lots,state,excess,percent):
    app,kw=fixture(tmp_path);kw['configuration']=None if amount is None else config(risk_reference_amount=amount)
    c=app.evaluate(**kw);before=files(tmp_path)
    a=app.preview_risk(c.identity,lots=lots).data
    assert files(tmp_path)==before
    assert a['risk_warning_state']==state
    assert D(a['selected_monetary_risk'])==D(400)*lots
    assert (None if a['difference_from_risk_reference'] is None else D(a['difference_from_risk_reference']))==(None if excess is None else D(excess))
    assert (None if a['percentage_difference_from_risk_reference'] is None else D(a['percentage_difference_from_risk_reference']))==(None if percent is None else D(percent))
    selected=app.select(c.identity,choice='SELECTED_FUTURE',lots=lots,session=session(),action_identity='s')
    assert selected.data['advisory_risk']==a
    handoff,=app.store.records('WO10_SELECTED_TRADE_HANDOFF_V1')
    assert handoff.data['advisory_risk']==a
    assert handoff.data['authority']=='SELECTED_TRADE_ONLY_NO_ACTIVATION'
    assert 'maximum_permitted_lots' not in selected.payload_json+handoff.payload_json
    assert app.store.records('WO10_RISK_PERMISSION_V1')==()
    assert len(kw['provider'].calls)==1

@pytest.mark.parametrize('state',['missing','stale','invalid'])
def test_reference_unavailable_is_not_a_veto(tmp_path,state):
    app,kw=fixture(tmp_path)
    if state=='missing':kw['configuration']=None
    elif state=='stale':kw['configuration']=config(effective_at=NOW-timedelta(hours=2),expires_at=NOW-timedelta(hours=1))
    else:kw['configuration']=record('WO10_RISK_REFERENCE_V1',currency='USD',risk_reference_amount='100',source_identity='bad',effective_at=NOW,expires_at=NOW+timedelta(hours=1))
    c=app.evaluate(**kw)
    assert app.decision_state(c,now=NOW,session=session())=='EXECUTABLE'
    selected=app.select(c.identity,choice='SELECTED_FUTURE',lots=10,session=session(),action_identity='s')
    assert selected.data['advisory_risk']['risk_warning_state']=='REFERENCE_NOT_CONFIGURED'

@pytest.mark.parametrize('field',['maximum_permitted_lots','maximum_monetary_risk_per_trade','existing_open_risk','maximum_aggregate_open_risk','global_max_lots','available_margin'])
def test_permission_inputs_not_accepted(field):
    with pytest.raises(ValueError,match='FIELDS_INVALID'):config(**{field:1})

@pytest.mark.parametrize('schema',['WO10_RISK_PERMISSION_V1','WO10_RISK_CONFIGURATION_V1'])
def test_historical_permission_bytes_readable_but_never_current(tmp_path,schema):
    from kronos.intraday.wo10_futures_store import FuturesStore
    base=asdict(record('WO10_OPPORTUNITY_V1',subject='HISTORICAL'))
    base.update(schema=schema,policy_version=VERSION,policy_checksum=LEGACY_CHECKSUM,effective_authority_boundary=LEGACY_BOUNDARY)
    material={k:v for k,v in base.items() if k not in {'identity','integrity'}}
    checksum=digest(material);base.update(identity=schema+'-'+checksum,integrity=checksum)
    old=Record(**base);store=FuturesStore(tmp_path);store.retain(old);before=files(tmp_path)
    assert store.load(old.identity)==old
    with pytest.raises(ValueError,match='HISTORICAL_AUTHORITY'):require(old,schema)
    with pytest.raises(ValueError,match='HISTORICAL_SCHEMA'):record(schema,state='APPROVED')
    assert files(tmp_path)==before
    assert POLICY_VERSION!='1.0.0'

@pytest.mark.parametrize('change',[None, 'new-reference'])
def test_reference_change_cannot_hide_a_trade_veto(tmp_path,change):
    from tests.unit.intraday.test_wo10_successor_races import wired
    app,kw,inputs,authority=wired(tmp_path)
    c=app.construct_current(handoff_identity=kw['adapter'].wo09.handoff_identity,request_identity='c')
    authority['configuration']=None if change is None else config(risk_reference_amount='1')
    assert app.decision_state(c,now=NOW,session=session())=='EXECUTABLE'
    assert app.select(c.identity,choice='SELECTED_FUTURE',lots=100,session=session(),action_identity='s')


def test_stale_reference_between_snapshot_and_selection_is_advisory(tmp_path):
    app,kw=fixture(tmp_path);kw['configuration']=config(expires_at=NOW+timedelta(seconds=1));c=app.evaluate(**kw)
    app.clock=lambda:NOW+timedelta(seconds=2)
    selected=app.select(c.identity,choice='SELECTED_FUTURE',lots=100,session=session(app.clock()),action_identity='s')
    assert selected.data['advisory_risk']['risk_reference_amount'] is None
    assert 'RISK_REFERENCE_STALE' in selected.data['advisory_risk']['reasons']
