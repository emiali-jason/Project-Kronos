"""Same-operation capture with deterministic Provider doubles; no live calls."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
from kronos.intraday.assessment_capture import capture_admission_observations
from kronos.intraday.assessment_observation import AssessmentPriceAuthority as Authority
from kronos.intraday.operation_accounting import ProviderRequestCounter, ProviderRequestCategory as Category
from kronos.intraday.probables_v2_persistence import ProbablesV2Store, _artifact_bytes, _artifact_from_bytes
from kronos.intraday.probables_v2 import ProbablesV2Error
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import QuoteSnapshot, OhlcValues
from tests.unit.intraday.test_assessment_observation import fixture


def instrument(symbol="RELIANCE",exchange="NSE",segment="NSE",expiry=None,kind="EQ"):
    return InstrumentRecord(provider="KITE",exchange=exchange,segment=segment,trading_symbol=symbol,
        name=symbol,instrument_type=kind,expiry=expiry,tick_size=Decimal("0.05"),lot_size=1)


def capture(run, *, fault=None, subject=None, quote_hook=None, request_override=None):
    subject_identity=run.results[0].canonical_subject_identity
    request=instrument({"NSE-INDEX-NIFTY":"NIFTY 50", "NSE-INDEX-BANKNIFTY":"NIFTY BANK"}.get(subject_identity,"RELIANCE"),
        segment="INDICES" if subject_identity.startswith("NSE-INDEX-") else "NSE")
    request=request_override or request
    now=run.analysis_boundary
    times=iter((now+timedelta(seconds=10),now+timedelta(seconds=12)))
    counter=ProviderRequestCounter(lambda:now)
    calls=[]
    def quote(record):
        calls.append(record)
        if quote_hook:quote_hook()
        if fault=="failure":raise RuntimeError("SECRET-EXCEPTION-MUST-NOT-ESCAPE")
        result=QuoteSnapshot(instrument=record,timestamp=now+timedelta(seconds=11),
            last_price=123.45,volume=100,ohlc=OhlcValues(100.,125.,99.,101.))
        if fault=="foreign":result=replace(result,instrument=instrument("FOREIGN"))
        if fault=="future":result=replace(result,timestamp=now+timedelta(days=1))
        if fault=="missing_time":object.__setattr__(result,"timestamp",None)
        if fault=="missing_price":object.__setattr__(result,"last_price",None)
        return result
    member=run.results[0]
    records={} if fault=="no_binding" else {member.universe_member_identity:(subject or member.canonical_subject_identity,request)}
    value=capture_admission_observations(run,operation_identity="KRONOS-INTRADAY-DISCOVERY-OPERATION-ISOLATED",
        records=records,quote=quote,counter=counter,clock=lambda:next(times))
    return value,counter,calls


@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_pair_after_analysis_boundary_is_provider_time_not_receipt(direction):
    run,_=fixture(direction)
    value,counter,calls=capture(run)
    item=value.observations[0]
    assert item.classification is Authority.EXACT_PRICE_PERSISTED
    assert item.assessment_time==run.analysis_boundary+timedelta(seconds=11)
    assert item.assessment_price==Decimal("123.45")
    assert item.proof.capture_completed_at==run.analysis_boundary+timedelta(seconds=12)
    assert item.assessment_time!=item.proof.capture_completed_at
    assert item.proof.observation_identity and item.proof.source_document
    assert len(calls)==counter.snapshot()["actual_provider_requests"]==1
    assert dict(counter.snapshot()["request_categories"])[Category.ASSESSMENT_OBSERVATION_REQUEST]==1
    assert _artifact_from_bytes(_artifact_bytes(value))==value


@pytest.mark.parametrize("fault",["failure","foreign","future","missing_time","missing_price","no_binding"])
def test_failure_preserves_admission_and_never_uses_candle(fault):
    run,_=fixture();before=_artifact_bytes(run)
    value,counter,calls=capture(run,fault=fault)
    assert len(value.observations)==run.diagnostics.total_probables==1
    item=value.observations[0]
    assert item.classification is Authority.PRICE_NOT_RETAINED
    assert item.assessment_price is item.assessment_time is item.proof is None
    assert item.reason=="ADMISSION_MARKET_OBSERVATION_UNAVAILABLE"
    assert "SECRET" not in repr(value)
    assert _artifact_bytes(run)==before
    assert len(calls)==counter.snapshot()["actual_provider_requests"]==(0 if fault=="no_binding" else 1)


@pytest.mark.parametrize("subject",["NSE-INDEX-NIFTY","NSE-INDEX-BANKNIFTY"])
def test_index_canonical_binding_and_wrong_subject_rejection(subject):
    run,_=fixture(subject=subject)
    value,_,_=capture(run)
    assert value.observations[0].canonical_subject_identity==subject
    assert value.observations[0].classification is Authority.EXACT_PRICE_PERSISTED
    bad,counter,calls=capture(run,subject="DERIVATIVE-PROXY")
    assert bad.observations[0].classification is Authority.PRICE_NOT_RETAINED
    assert counter.snapshot()["actual_provider_requests"]==0 and calls==[]


def invoke(app,run,mapping,callback):
    return app.refresh_analysis(source_discovery_run_identity=run.source_discovery_run_identity,
        universe_identity=run.universe_identity,universe_version=run.universe_version,
        reconciliation_identity=run.reconciliation_identity,reconciliation_version=run.reconciliation_version,
        market_session_identity=run.market_session_identity,analysis_boundary=run.analysis_boundary,
        member_evidence=(mapping,),unavailable_members=(),provenance=run.provenance,
        assessment_capture=callback)


def test_capture_before_publication_and_no_recapture_on_replay(tmp_path):
    run,mapping=fixture();store=ProbablesV2Store(tmp_path);app=IntradayProbablesV2Application(store=store)
    seen=[]
    def callback(admitted):
        assert admitted.diagnostics.total_probables==1
        assert store.load_current() is None and not store.has_run(admitted.run_identity)
        value,_,calls=capture(admitted);seen.extend(calls);return value
    published=invoke(app,run,mapping,callback)
    assert len(seen)==1 and store.load_current_run()==published
    proof=store.load_assessment_observations(published.run_identity)
    assert proof.observations[0].classification is Authority.EXACT_PRICE_PERSISTED
    before={p:p.read_bytes() for p in tmp_path.rglob("*.json")}
    restored=IntradayProbablesV2Application(store=ProbablesV2Store(tmp_path))
    invoke(restored,run,mapping,lambda _:pytest.fail("Replay must not call Provider"))
    assert before=={p:p.read_bytes() for p in tmp_path.rglob("*.json")}


def test_price_failure_publishes_same_admission(tmp_path):
    run,mapping=fixture();store=ProbablesV2Store(tmp_path);app=IntradayProbablesV2Application(store=store)
    published=invoke(app,run,mapping,lambda admitted:capture(admitted,fault="failure")[0])
    assert published.results==run.results
    assert store.load_assessment_observations(published.run_identity).observations[0].classification is Authority.PRICE_NOT_RETAINED


def test_persisted_pending_observation_reused_after_run_write_failure(tmp_path,monkeypatch):
    run,mapping=fixture();store=ProbablesV2Store(tmp_path);app=IntradayProbablesV2Application(store=store)
    monkeypatch.setattr(store,"retain_run",lambda _:(_ for _ in ()).throw(OSError("isolated")))
    with pytest.raises(RuntimeError):invoke(app,run,mapping,lambda admitted:capture(admitted)[0])
    restored=IntradayProbablesV2Application(store=ProbablesV2Store(tmp_path))
    result=invoke(restored,run,mapping,lambda _:pytest.fail("Never replace a persisted pending quote"))
    assert restored.store.load_assessment_observations(result.run_identity).observations[0].assessment_price==Decimal("123.45")


def test_source_document_tamper_rejects_even_with_outer_manifest_rehash():
    run,_=fixture();value,_,_=capture(run)
    object.__setattr__(value.observations[0].proof,"source_document","{}")
    with pytest.raises(ProbablesV2Error):value.__post_init__()


@pytest.mark.parametrize("subject,record",[
    ("NSE-INDEX-NIFTY", instrument("NIFTY ETF")),
    ("NSE-INDEX-BANKNIFTY", instrument("BANKNIFTYFUT",kind="FUT")),
    ("NSE-EQ-RELIANCE", instrument("RELIANCEFUT",kind="FUT")),
    ("MCX-SUBJECT-CRUDE", instrument("CL1!",exchange="NYMEX")),
])
def test_native_proxy_binding_cannot_capture(subject,record):
    run,_=fixture(subject=subject)
    value,counter,calls=capture(run,request_override=record)
    assert value.observations[0].classification is Authority.PRICE_NOT_RETAINED
    assert not calls and counter.snapshot()["actual_provider_requests"]==0


@pytest.mark.parametrize("hours,fifteens,hour,minute",[(0,2,10,30),(1,4,11,0),(2,8,12,0)])
def test_every_later_phase_captures_own_quote(hours,fifteens,hour,minute):
    from datetime import datetime,time
    from tests.unit.intraday.test_assessment_observation import _later_mapping,CURRENT_DAY,IST,run_mapping,create_probables_v2_methodology
    mapping=_later_mapping(fifteens,hours,boundary=datetime.combine(CURRENT_DAY,time(hour,minute),IST))
    run=run_mapping(mapping,create_probables_v2_methodology())
    value,_,calls=capture(run)
    assert len(calls)==len(value.observations)==run.diagnostics.total_probables==1
    assert value.observations[0].classification is Authority.EXACT_PRICE_PERSISTED


def test_historical_run_never_calls_new_capture_adapter(tmp_path):
    run,mapping=fixture();store=ProbablesV2Store(tmp_path);store.retain_run(run)
    app=IntradayProbablesV2Application(store=store)
    invoke(app,run,mapping,lambda _:pytest.fail("Historical admission must never acquire a later quote"))
    assert store.load_assessment_observations(run.run_identity) is None


@pytest.mark.parametrize("scenario",["complete","one_failure","no_quote_capability","no_admissions","trusted_future"])
def test_real_composition_order_population_accounting_and_restore(tmp_path,scenario):
    from collections import Counter
    from kronos.application.intraday_runtime import create_intraday_runtime
    from kronos.browser.intraday_probables_v2_control import IntradayProbablesV2OperationalControl
    from kronos.provider.contracts.market_data import HistoricalInterval
    from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
    from tests.unit.application.test_intraday_discovery_operation import _configured_shared,_authenticate
    from tests.unit.intraday.test_probables_v2_refresh_control import _payload
    from tests.unit.intraday.test_analysis_time import REQUESTED
    shared,provider,_,_=_configured_shared();_authenticate(shared)
    events=[];quotes=[];history=provider.capability.historical_candles
    for name in ("instrument_master_records","instrument_records"):
        original=getattr(provider.capability,name)
        def spy(*args,_name=name,_original=original,**kwargs):
            events.append(_name);return _original(*args,**kwargs)
        setattr(provider.capability,name,spy)
    def candles(request):
        events.append("historical_candles")
        values=history(request)
        if request.interval is HistoricalInterval.DAY:
            return tuple(replace(x,high=102.,low=98.,close=100.) for x in values)
        if scenario=="no_admissions":return values
        return tuple(replace(x,open=100.+i,high=102.+i,low=99.+i,close=101.+i) for i,x in enumerate(values))
    provider.capability.historical_candles=candles
    if scenario=="no_quote_capability":
        provider.capability.operations-=frozenset({ReadOnlyProviderOperation.QUOTE})
    def quote(record):
        # Admission was evaluated, but no current Probables publication exists yet.
        assert c.probables_v2_store.load_current() is None
        assert c.probables_v2_application.snapshot().run is None
        assert events.count("historical_candles")==465
        events.append("quote");quotes.append(record)
        if scenario=="one_failure" and len(quotes)==2:raise RuntimeError("isolated quote unavailable")
        return QuoteSnapshot(record,REQUESTED,123.45,100,OhlcValues(100.,125.,99.,101.))
    provider.capability.quote=quote
    now=REQUESTED-timedelta(minutes=1) if scenario=="trusted_future" else REQUESTED
    c=create_intraday_runtime(shared,evidence_root=tmp_path.resolve(),clock=lambda:now)
    control=IntradayProbablesV2OperationalControl(c.discovery_v2_operation,c.probables_v2_application,
        c.refresh_v2_provenance_store,clock=lambda:now,process_identity=lambda:"ASSESSMENT-OPERATION-TEST")
    payload=_payload("ADMISSION-CAPTURE",boundary=REQUESTED)
    result=control.execute_document(payload)
    if scenario=="trusted_future":
        assert result["outcome"]=="REJECTED" and not events
        assert result["failure"]=="OBSERVATION_BOUNDARY_FUTURE"
        assert c.discovery_v2_operation.last_result is None
        return
    a=c.discovery_v2_operation.last_result.accounting
    assert result["outcome"]=="SUCCESS"
    run=c.probables_v2_application.snapshot().run
    assessment=c.probables_v2_store.load_assessment_observations(run.run_identity)
    expected=0 if scenario=="no_admissions" else 93
    assert run.diagnostics.total_probables==len(assessment.observations)==expected
    assert a.governed_members==98 and a.factually_evaluable==93
    assert a.actual_provider_requests==467+expected
    assert dict(a.request_categories)[Category.ASSESSMENT_OBSERVATION_REQUEST]==expected
    assert a.benchmark_subject_requests==5+int(expected>0)
    if scenario!="no_quote_capability":assert len(events)==a.actual_provider_requests
    assert len(quotes)==(0 if scenario=="no_quote_capability" else expected)
    counts=Counter(x.classification for x in assessment.observations)
    missing=93 if scenario=="no_quote_capability" else 1 if scenario=="one_failure" else 0
    assert counts[Authority.PRICE_NOT_RETAINED]==missing
    assert counts[Authority.EXACT_PRICE_PERSISTED]==expected-missing
    assert all(x.phase=="OPENING" and x.methodology_version=="2.2.0" for x in assessment.observations)
    if expected and quotes:
        assert {x.trading_symbol for x in quotes if x.segment=="INDICES"}=={"NIFTY 50","NIFTY BANK"}
        assert all(x.expiry is None and x.exchange=="NSE" for x in quotes)
    retained={p:p.read_bytes() for p in tmp_path.rglob("*.json")}
    before=list(events)
    restored=create_intraday_runtime(shared,evidence_root=tmp_path.resolve(),clock=lambda:now)
    assert restored.probables_v2_store.load_assessment_observations(run.run_identity)==assessment
    again=IntradayProbablesV2OperationalControl(restored.discovery_v2_operation,restored.probables_v2_application,
        restored.refresh_v2_provenance_store,clock=lambda:now,process_identity=lambda:"RESTORED")
    assert again.execute_document(payload)["idempotent"] is True
    assert events==before and retained=={p:p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert shared.active_lease_count==0


def test_governed_native_mcx_record_preserved_without_reference_substitution():
    from datetime import date
    run,_=fixture(subject="MCX-SUBJECT-CRUDE")
    native=instrument("CRUDEOIL26SEPFUT",exchange="MCX",segment="MCX-FUT",expiry=date(2026,9,21),kind="FUT")
    value,counter,calls=capture(run,request_override=native)
    assert calls==[native] and counter.snapshot()["actual_provider_requests"]==1
    assert value.observations[0].classification is Authority.EXACT_PRICE_PERSISTED
    assert '"exchange":"MCX"' in value.observations[0].proof.source_document
    assert value.observations[0].canonical_subject_identity=="MCX-SUBJECT-CRUDE"
