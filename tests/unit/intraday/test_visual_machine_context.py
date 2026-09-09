"""Offline exact USDINR futures context; fixtures confer no production authority."""
from dataclasses import replace
from datetime import datetime, date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
import pytest
from kronos.intraday.visual_machine_context import usdinr_futures_context
from kronos.instrument.semantic_v2 import create_active_derivative_binding, create_provider_mapping_directive_v2
from kronos.intraday.historical_semantic import create_governed_historical_candle_payload
from kronos.intraday.contracts import IntradayTimeframe
from kronos.market.schedule import (MarketSchedule, MarketAvailability, ScheduleFreshness, ScheduleIntegrity, MARKET_SCHEDULE_CONTRACT_ID, MARKET_SCHEDULE_CONTRACT_VERSION)
from tests.unit.provider.test_instrument_master_snapshot import _source, _snapshot


def fixture():
    boundary=datetime(2026,8,28,12,tzinfo=ZoneInfo('Asia/Kolkata'))
    record=_snapshot((_source(19999,'USDINR26SEPFUT',exchange='CDS',segment='CDS-FUT',name='USDINR',instrument_type='FUT',expiry=date(2026,9,28)),)).records[0]
    directive=create_provider_mapping_directive_v2(directive_identity='TEST-USDINR-DIRECTIVE',directive_version='1.0.0',canonical_object_id='TEST-USDINR-CONTRACT',provider='KITE',provider_record_identity=record.provider_record_identity,provider_symbol=record.trading_symbol,classification_mapping_identity='TEST-CDS-FUT',effective_from=boundary-timedelta(days=1),effective_through=boundary+timedelta(days=30),source_identity='TEST-GOVERNED-CURRENCY-SOURCE',provenance=('TEST-ONLY',),supersedes=None)
    binding=create_active_derivative_binding(binding_identity='TEST-USDINR-BINDING',binding_version='1.0.0',subject_id='TEST-USDINR-SUBJECT',derivative_contract_id='TEST-USDINR-CONTRACT',effective_from=directive.effective_from,effective_through=directive.effective_through,contract_expiry=record.expiry,provider_reference_identity=directive.directive_identity,source_identity='TEST-GOVERNED-CURRENCY-SOURCE',provenance=('TEST-ONLY',),supersedes=None)
    schedule=MarketSchedule(contract_identity=MARKET_SCHEDULE_CONTRACT_ID,contract_version=MARKET_SCHEDULE_CONTRACT_VERSION,identity='TEST-CDS-SCHEDULE',market_identity='CDS',exchange='CDS',trading_date=boundary.date(),calendar_identity='TEST-CDS-CALENDAR',calendar_version='1.0.0',session_identity='TEST-CDS-SESSION',session_type='CONTINUOUS',session_open=boundary.replace(hour=9),session_close=boundary.replace(hour=17),timezone='Asia/Kolkata',market_availability=MarketAvailability.OPEN,as_of=boundary,source_identity='TEST-CALENDAR',source_boundary=boundary,freshness_status=ScheduleFreshness.CURRENT,integrity_status=ScheduleIntegrity.VALID,provenance=('TEST-ONLY',))
    candle=create_governed_historical_candle_payload(canonical_subject_identity=binding.derivative_contract_id,exchange='CDS',market_identity='CDS',market_session_identity=schedule.session_identity,timeframe=IntradayTimeframe.FIVE_MINUTES,candle_start=boundary-timedelta(minutes=5),candle_end=boundary,open=Decimal('83'),high=Decimal('84'),low=Decimal('82'),close=Decimal('83.5'),volume=10,observation_boundary=boundary,provider_source_identity=directive.directive_identity,source_operation_identity='TEST-OFFLINE-OPERATION',provenance=('TEST-ONLY',))
    return dict(boundary=boundary,record=record,directive=directive,binding=binding,schedule=schedule,candle=candle)


def test_exact_futures_source_and_expiry_context():
    inputs=fixture();value=usdinr_futures_context(**inputs)
    assert value.state=='AVAILABLE'
    assert dict(value.facts)['instrument']=='USDINR FUTURES'
    assert dict(value.facts)['expiry']=='2026-09-28'
    assert value==usdinr_futures_context(**inputs)
    assert value.integrity_identity==usdinr_futures_context(**inputs).integrity_identity
    assert value.authority=='MACHINE_CONTEXT_RESEARCH_ONLY'
    assert not any(key in dict(value.facts) for key in ('score','vote','spot','trade_gate'))


@pytest.mark.parametrize('missing',['record','binding','directive','schedule','candle'])
def test_missing_currency_does_not_acquire_or_reject_mcx(missing):
    values=fixture();values[missing]=None
    assert usdinr_futures_context(**values).state=='NOT_ESTABLISHED'


@pytest.mark.parametrize('mutation',['wrong_contract','wrong_source','wrong_expiry','future','stale','expired','spot','wrong_currency','wrong_session','tamper'])
def test_currency_context_fails_closed(mutation):
    values=fixture()
    if mutation=='future': values['boundary']-=timedelta(minutes=1)
    elif mutation=='expired': values['boundary']+=timedelta(days=40)
    else:
        target=values['binding'] if mutation in {'wrong_contract','wrong_expiry','stale'} else values['record'] if mutation in {'spot','wrong_currency'} else values['candle']
        fields={'wrong_contract':('derivative_contract_id','FOREIGN'),'wrong_expiry':('contract_expiry',date(2026,6,1)),'stale':('effective_through',values['boundary']-timedelta(minutes=1)),'spot':('instrument_type','SPOT'),'wrong_currency':('name','EURINR'),'wrong_session':('market_session_identity','FOREIGN'),'tamper':('integrity_identity','TAMPERED'),'wrong_source':('provider_source_identity','LATER-QUOTE')}
        field,value=fields[mutation]
        object.__setattr__(target,field,value)
    assert usdinr_futures_context(**values).state=='NOT_ESTABLISHED'


@pytest.mark.parametrize('field,value,reason',[
    ('canonical_subject_identity','FOREIGN-CONTRACT','EXACT_CONTRACT_OR_SOURCE_MISMATCH'),
    ('provider_source_identity','FOREIGN-SOURCE','EXACT_CONTRACT_OR_SOURCE_MISMATCH'),
    ('market_session_identity','FOREIGN-SESSION','COMPLETED_SESSION_EVIDENCE_UNAVAILABLE'),
    ('candle_start',None,'COMPLETED_CANDLE_INTERVAL_MISMATCH'),
])
def test_valid_integrity_wrong_source_or_interval_rejected(field,value,reason):
    import inspect
    from dataclasses import asdict
    values=fixture();raw=asdict(values['candle'])
    kwargs={k:raw[k] for k in inspect.signature(create_governed_historical_candle_payload).parameters}
    kwargs[field]=values['boundary']-timedelta(minutes=4) if value is None else value
    values['candle']=create_governed_historical_candle_payload(**kwargs)
    result=usdinr_futures_context(**values)
    assert result.state=='NOT_ESTABLISHED' and result.reason==reason


@pytest.mark.parametrize("field,value", [("market_availability", MarketAvailability.UNAVAILABLE), ("market_identity", "FOREIGN-MARKET")])
def test_unavailable_or_foreign_market_schedule_rejected(field,value):
    values=fixture();values["schedule"]=replace(values["schedule"], **{field:value})
    assert usdinr_futures_context(**values).state=="NOT_ESTABLISHED"
