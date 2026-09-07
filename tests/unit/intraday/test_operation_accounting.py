"""WO-05B accounting verified against independently spied Provider doubles."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import timedelta, timezone
import json
from pathlib import Path

import pytest

from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.browser.intraday_probables_v2_control import IntradayProbablesV2OperationalControl
from kronos.browser.intraday_discovery_control import IntradayDiscoveryOperationalControl
from kronos.intraday.operation_accounting import (
    ProviderRequestCategory as Category, ProviderRequestCounter,
    accounting_document, accounting_bytes, restore_accounting, create_operation_accounting,
)
from kronos.intraday.operation_accounting_persistence import DiscoveryOperationAccountingStore
from kronos.intraday.refresh_v2 import _identity
from kronos.intraday.refresh_v2_persistence import _encoded, _decoded
from kronos.provider.contracts.market_data import HistoricalInterval
from tests.unit.application.test_intraday_discovery_operation import (
    SEMANTIC_BOUNDARY as NOW, _configured_shared, _authenticate,
)
from tests.unit.intraday.test_probables_v2_refresh_control import _payload


def _operation(tmp_path, *, fail=None, remove_symbol=None, authenticated=True, clock=None):
    shared, runtime, _, _ = _configured_shared()
    events = []
    for name in ("instrument_master_records", "instrument_records", "historical_candles"):
        original = getattr(runtime.capability, name)
        def spy(*args, _name=name, _original=original, **kwargs):
            events.append((_name, args[0] if args else None))
            if fail is not None and fail(_name, args[0] if args else None):
                raise RuntimeError("ISOLATED-PROVIDER-FAILURE")
            result = _original(*args, **kwargs)
            if _name == "instrument_records" and remove_symbol:
                result = tuple(x for x in result if x.trading_symbol != remove_symbol)
            return result
        setattr(runtime.capability, name, spy)
    if authenticated:
        _authenticate(shared)
    clock = clock or (lambda: NOW)
    composition = create_intraday_runtime(shared, evidence_root=tmp_path.resolve(), clock=clock)
    control = IntradayProbablesV2OperationalControl(composition.discovery_v2_operation,
        composition.probables_v2_application, composition.refresh_v2_provenance_store,
        clock=clock, process_identity=lambda: "ACCOUNTING-TEST")
    return shared, composition, control, events


def _run(tmp_path, **kwargs):
    shared,c,control,events = _operation(tmp_path,**kwargs)
    result = control.execute_document(_payload("ACCOUNTING"))
    account = c.discovery_v2_operation.last_result.accounting
    assert account is not None
    assert account.actual_provider_requests == len(events)
    return shared,c,control,events,result,account


def _history(events):
    return [arg for name,arg in events if name == "historical_candles"]


def test_success_separates_real_requests_nominal_coverage_and_population(tmp_path):
    _,c,_,events,response,a = _run(tmp_path)
    assert response["outcome"] == "SUCCESS"
    assert (a.governed_members,a.nse_index_focus_members,a.nominal_evaluation_members) == (98,93,98)
    assert a.nominal_timeframe_coverage == 392
    assert (a.factually_evaluable,a.factual_failures,a.prerequisite_unavailable,a.not_reached_members) == (93,5,0,0)
    assert len(_history(events)) == 465
    assert a.actual_provider_requests == 467
    assert dict(a.request_categories) == {Category.CURRENT_SESSION_CANDLE_REQUEST:279,
        Category.PREVIOUS_SESSION_DAILY_REQUEST:93, Category.PREVIOUS_SESSION_INTRADAY_REQUEST:93,
        Category.INSTRUMENT_BINDING_REQUEST:2, Category.ASSESSMENT_OBSERVATION_REQUEST:0}
    assert sum(n for _,n in a.request_categories) == len(events)
    assert c.discovery_v2_operation.last_result.historical_request_count == 465
    assert response["operation_accounting"]["actual_provider_requests"] == 467


@pytest.mark.parametrize("index", [0,46,92], ids=["first","middle","last"])
def test_early_member_failure_counts_only_attempted_invocations(tmp_path,index):
    _,c,control,events = _operation(tmp_path)
    members=[x for x in c.discovery_v2_operation._reconciliation.members if x.exchange == "NSE"]
    symbol=members[index].provider_symbol
    # Rebuild an isolated fixture with failure at the same governed subject.
    _,c,control,events = _operation(tmp_path / "failed",
        fail=lambda name,arg:name=="historical_candles" and arg.instrument.trading_symbol==symbol)
    response=control.execute_document(_payload("FAIL-MEMBER"))
    a=c.discovery_v2_operation.last_result.accounting
    assert response["outcome"] == "SUCCESS"
    assert a.actual_provider_requests == len(events) == 463
    assert a.nominal_timeframe_coverage == 392 and a.governed_members == 98
    assert (a.factually_evaluable,a.factual_failures)==(92,6)
    assert len([x for x in _history(events) if x.instrument.trading_symbol==symbol]) == 1


@pytest.mark.parametrize("interval,expected", [
    (HistoricalInterval.DAY,463),(HistoricalInterval.SIXTY_MINUTE,464),
    (HistoricalInterval.FIFTEEN_MINUTE,465),(HistoricalInterval.FIVE_MINUTE,466),
])
def test_timeframe_failure_short_circuit_is_truthful(tmp_path,interval,expected):
    _,c,_,_,_,a=_run(tmp_path,fail=lambda n,q:n=="historical_candles"
        and q.instrument.trading_symbol=="RELIANCE" and q.interval is interval)
    assert a.actual_provider_requests==expected
    assert a.factual_failures==6


def test_prior_hour_failure_is_counted_without_relabeling_factual_bundle(tmp_path):
    _,c,_,events,_,a=_run(tmp_path,fail=lambda n,q:n=="historical_candles"
        and q.instrument.trading_symbol=="RELIANCE" and q.interval is HistoricalInterval.SIXTY_MINUTE
        and q.start.date()<NOW.date())
    assert a.actual_provider_requests == len(events) == 467
    assert dict(a.request_categories)[Category.PREVIOUS_SESSION_INTRADAY_REQUEST]==93
    # Prior-context mapping failure is downstream of the existing mandatory bundle.
    assert a.factually_evaluable==93
    run=c.probables_v2_application.snapshot().run
    reliance=next(x for x in run.results if x.canonical_subject_identity=="RELIANCE")
    assert reliance.state.value=="UNAVAILABLE"


def test_nifty_acquired_once_as_member_and_reused_in_opening_mapping(tmp_path):
    boundary=NOW.replace(hour=9,minute=30)
    _,c,control,events=_operation(tmp_path,clock=lambda:boundary)
    response=control.execute_document(_payload("BENCHMARK",boundary=boundary))
    assert response["outcome"]=="SUCCESS"
    a=c.discovery_v2_operation.last_result.accounting
    nifty=next(x.provider_symbol for x in c.discovery_v2_operation._reconciliation.members
        if x.canonical_identity=="NSE-INDEX-NIFTY")
    assert a.benchmark_subject_requests==len([q for q in _history(events) if q.instrument.trading_symbol==nifty])==5
    assert a.actual_provider_requests==467  # No per-equity benchmark re-acquisition.


def test_benchmark_failure_is_one_failed_member_attempt(tmp_path):
    _,c,_,_,_,a=_run(tmp_path,fail=lambda n,q:n=="historical_candles"
        and q.instrument.trading_symbol=="NIFTY 50")
    assert a.benchmark_subject_requests==1
    assert a.actual_provider_requests==463


def test_missing_instrument_binding_has_no_member_history_calls(tmp_path):
    _,_,_,events,_,a=_run(tmp_path,remove_symbol="RELIANCE")
    assert a.actual_provider_requests==462
    assert not any(q.instrument.trading_symbol=="RELIANCE" for q in _history(events))
    assert a.factual_failures==6 and a.governed_members==98


def test_master_failure_and_repeated_uncached_lookup_attempts(tmp_path):
    _,_,_,events,_,a=_run(tmp_path / "master",fail=lambda n,q:n=="instrument_master_records")
    assert len(events)==a.actual_provider_requests==1
    assert a.not_reached_members==98 and a.factually_evaluable==0
    _,_,_,events,_,a=_run(tmp_path / "lookup",fail=lambda n,q:n=="instrument_records")
    assert a.actual_provider_requests==len(events)==94
    assert dict(a.request_categories)[Category.INSTRUMENT_BINDING_REQUEST]==94
    assert a.factual_failures==98


def test_provider_unavailable_has_known_zero(tmp_path):
    _,_,_,events,_,a=_run(tmp_path,authenticated=False)
    assert a.actual_provider_requests==0 and events==[]
    assert a.provider_acquisition_started_at is None
    assert a.not_reached_members==98


def test_future_rejection_persists_known_zero_without_start(tmp_path):
    _,c,control,events=_operation(tmp_path,clock=lambda:NOW-timedelta(minutes=1))
    result=control.execute_document(_payload("FUTURE"))
    assert result["failure"]=="OBSERVATION_BOUNDARY_FUTURE"
    a=result["operation_accounting"]
    assert a["availability"]=="RETAINED" and a["actual_provider_requests"]==0
    assert a["operation_started_at"] is None and a["operation_duration_microseconds"] is None
    assert a["not_reached_members"]==98 and events==[]


def test_failure_after_acquisition_preserves_actual_counts_and_population(tmp_path,monkeypatch):
    _,c,control,events=_operation(tmp_path)
    def broken(*args,**kwargs): raise OSError("ISOLATED-WRITE-FAILURE")
    monkeypatch.setattr(c.discovery_v2_operation._store,"retain_run",broken)
    result=control.execute_document(_payload("LATE-FAILURE"))
    a=c.discovery_v2_operation.last_result.accounting
    assert result["outcome"]=="FAILED"
    assert a.actual_provider_requests==len(events)==467
    assert (a.factually_evaluable,a.factual_failures,a.not_reached_members)==(93,5,0)
    assert a.discovery_run_identity is None
    assert c.discovery_v2_operation.last_result.historical_request_count==0  # Old field kept unchanged.


def test_v2_restoration_and_idempotent_replay_have_identical_accounting(tmp_path):
    shared,c,control,events,response,a=_run(tmp_path)
    before=list(events)
    blobs={p:p.read_bytes() for p in tmp_path.rglob("*.json")}
    restored=create_intraday_runtime(shared,evidence_root=tmp_path.resolve(),clock=lambda:NOW)
    successor=IntradayProbablesV2OperationalControl(restored.discovery_v2_operation,
        restored.probables_v2_application,restored.refresh_v2_provenance_store,
        clock=lambda:NOW,process_identity=lambda:"RESTORED")
    assert successor.status_document()["operation_accounting"]==accounting_document(a)
    assert successor.execute_document(_payload("ACCOUNTING"))=={**response,"idempotent":True}
    assert events==before
    assert all(p.read_bytes()==v for p,v in blobs.items())


def test_legacy_operation_and_restored_status_are_accounted(tmp_path):
    shared,c,_,events=_operation(tmp_path)
    control=IntradayDiscoveryOperationalControl(c.discovery_operation,c.discovery_application)
    result=control.execute_document({"request_identity":"LEGACY","observation_boundary":NOW.isoformat()})
    a=c.discovery_operation.last_result.accounting
    assert result["operation_accounting"]==accounting_document(a)
    assert a.actual_provider_requests==len(events)==374
    assert dict(a.request_categories)[Category.PREVIOUS_SESSION_INTRADAY_REQUEST]==0
    restored=create_intraday_runtime(shared,evidence_root=tmp_path.resolve(),clock=lambda:NOW)
    status=IntradayDiscoveryOperationalControl(restored.discovery_operation,restored.discovery_application).status_document()
    assert status["last_operation_accounting"]==accounting_document(a)


def _values():
    return dict(operation_identity="KRONOS-INTRADAY-DISCOVERY-OPERATION-FIXTURE",operation_kind="V2",
        analysis_boundary=NOW,trusted_admission_time=NOW,operation_started_at=NOW,
        provider_acquisition_started_at=None,operation_completed_at=NOW+timedelta(seconds=2),
        discovery_run_identity=None,governed_members=2,nse_index_focus_members=2,
        nominal_evaluation_members=2,nominal_timeframe_coverage=8,
        factually_evaluable=0,factual_failures=0,prerequisite_unavailable=0,not_reached_members=2,
        actual_provider_requests=0,request_categories=tuple((c,0) for c in Category),benchmark_subject_requests=0)


def test_exact_duration_is_timezone_aware_and_distinct_from_analysis_age():
    a=create_operation_accounting(**_values())
    assert a.operation_duration_microseconds==2000000
    assert restore_accounting(accounting_bytes(a))==a
    b=create_operation_accounting(**{**_values(),"operation_started_at":NOW.astimezone(timezone.utc)})
    assert b.operation_duration_microseconds==2000000


@pytest.mark.parametrize("changes", [
    {"actual_provider_requests":-1},{"nominal_timeframe_coverage":-1},
    {"factually_evaluable":3},{"actual_provider_requests":1},
    {"operation_completed_at":NOW-timedelta(microseconds=1)},
    {"operation_started_at":NOW.replace(tzinfo=None)},
    {"provider_acquisition_started_at":NOW-timedelta(seconds=1)},
    {"actual_provider_requests":None},
])
def test_invalid_counts_and_timing_fail_closed(changes):
    with pytest.raises(ValueError): create_operation_accounting(**{**_values(),**changes})


def test_zero_is_distinct_from_unknown():
    zero=create_operation_accounting(**_values())
    unknown=create_operation_accounting(**{**_values(),"actual_provider_requests":None,
        "request_categories":None,"benchmark_subject_requests":None})
    assert accounting_document(zero)["actual_provider_requests"]==0
    assert accounting_document(unknown)["actual_provider_requests"] is None
    assert accounting_document(None)["availability"]=="NOT_RETAINED"


def test_store_integrity_no_clobber_and_containment(tmp_path):
    a=create_operation_accounting(**_values()); store=DiscoveryOperationAccountingStore(tmp_path.resolve())
    p=store.retain(a); original=p.read_bytes()
    assert store.retain(a)==p and p.read_bytes()==original
    assert store.load(a.accounting_identity)==a
    with pytest.raises(ValueError): store.load("../foreign")
    data=json.loads(original);data["actual_provider_requests"]=99;p.write_text(json.dumps(data))
    with pytest.raises(ValueError): store.load(a.accounting_identity)
    with pytest.raises(ValueError): store.retain(a)


@pytest.mark.parametrize("version",["1.0.0","1.1.0","1.2.0"])
def test_historical_provenance_restores_without_retrospective_counts(tmp_path,version):
    _,c,control,_=_operation(tmp_path,authenticated=False)
    control.execute_document(_payload("OLD"))
    values=json.loads(_encoded(c.refresh_v2_provenance_store.load_for_request("OLD")))
    values.pop("operation_accounting_identity");values["contract_version"]=version
    if version!="1.2.0": values.pop("trusted_admission_time")
    core={k:v for k,v in values.items() if k not in {"provenance_identity","integrity_identity"}}
    if version=="1.0.0":
        core.pop("replay_envelope_identity");core.pop("failure_detail_identity")
    values["provenance_identity"]=_identity("INTRADAY-PROBABLES-V2-REQUEST-PROVENANCE-",core)
    values["integrity_identity"]=_identity("INTEGRITY-INTRADAY-PROBABLES-V2-REQUEST-PROVENANCE-",core)
    encoded=(json.dumps(values,sort_keys=True,separators=(",",":"))+"\n").encode()
    restored=_decoded(encoded)
    assert restored.operation_accounting_identity is None and _encoded(restored)==encoded
    assert control._accounting_document(restored)["actual_provider_requests"] is None


def test_independent_counters_count_each_attempt_including_failure():
    a,b=ProviderRequestCounter(lambda:NOW),ProviderRequestCounter(lambda:NOW)
    def invoke(counter):
        for _ in range(3):
            with pytest.raises(RuntimeError):
                counter.invoke(Category.CURRENT_SESSION_CANDLE_REQUEST,
                    lambda:(_ for _ in ()).throw(RuntimeError("FAIL")))
        return counter.snapshot()["actual_provider_requests"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(invoke,[a,b]))==[3,3]


def test_accounting_persistence_failure_is_unknown_not_fake_zero(tmp_path,monkeypatch):
    _,c,control,events=_operation(tmp_path)
    monkeypatch.setattr(c.discovery_v2_operation.accounting_store,"retain",
        lambda *a:(_ for _ in ()).throw(OSError("ISOLATED-DISK-FAILURE")))
    result=control.execute_document(_payload("NO-RECEIPT"))
    assert result["outcome"]=="SUCCESS" and len(events)==467
    assert result["operation_accounting"]["availability"]=="NOT_RETAINED"
    assert result["operation_accounting"]["actual_provider_requests"] is None


def test_failing_telemetry_clock_does_not_change_acquisition_behavior():
    calls=[]
    def broken_clock(): raise RuntimeError("CLOCK-FAILURE")
    counter=ProviderRequestCounter(broken_clock)
    assert counter.invoke(Category.INSTRUMENT_BINDING_REQUEST,lambda:calls.append("INVOKED")) is None
    assert calls==["INVOKED"] and counter.snapshot()["actual_provider_requests"] == 1
    assert counter.snapshot()["provider_acquisition_started_at"] is None
    a=create_operation_accounting(**(_values() | counter.snapshot()))
    assert restore_accounting(accounting_bytes(a)) == a
    assert accounting_document(a)["provider_acquisition_start_availability"] == "NOT_RETAINED"


def test_operation_timestamps_and_duration_restore_exactly(tmp_path):
    tick=[0]
    def clock():
        tick[0]+=1
        return NOW+timedelta(microseconds=tick[0])
    _,c,control,events=_operation(tmp_path,clock=clock)
    response=control.execute_document(_payload("TIMING"))
    a=c.discovery_v2_operation.last_result.accounting
    record=c.refresh_v2_provenance_store.load_for_request("TIMING")
    assert record.received_at <= a.trusted_admission_time <= a.operation_started_at
    assert a.operation_started_at <= a.provider_acquisition_started_at <= a.operation_completed_at
    assert a.operation_completed_at <= record.operation_completed_at
    assert a.operation_duration_microseconds>0
    assert c.discovery_v2_operation.accounting_store.load(a.accounting_identity)==a
    assert response["request_received_at"]==record.received_at.isoformat()
    assert response["control_returned_at"]==record.operation_completed_at.isoformat()
    assert response["operation_accounting"]["response_sent_at"]=="NOT_RETAINED"


def test_browser_api_uses_persisted_accounting_and_bounded_labels(tmp_path):
    from kronos.browser.intraday_routes import IntradayBrowserRoutes
    from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
    from tests.unit.browser.test_product_route_isolation import _snapshot
    _,c,control,events=_operation(tmp_path,authenticated=False)
    routes=IntradayBrowserRoutes(c.workstation,probables_v2_control=control)
    result=routes.handle_post(BrowserPostRequest(path="/control/intraday-discovery/v2",
        query={},content_type="application/json",body=json.dumps(_payload("API")).encode()),_snapshot)
    payload=json.loads(result.body)
    account=payload["operation_accounting"]
    assert account["actual_provider_requests"]==0 and account["nominal_timeframe_coverage"]==392
    assert account["provider_request_boundary"]=="DOMAIN_006_ACQUISITION_API_INVOCATION"
    status=routes.handle_get(BrowserGetRequest("/control/intraday-discovery/v2/status",{}),_snapshot)
    assert json.loads(status.body)["operation_accounting"]==account and events==[]


@pytest.mark.parametrize("first", [None, NOW.replace(tzinfo=None)])
def test_later_invocation_cannot_fabricate_missing_first_request_time(first):
    ticks=iter((first,NOW))
    counter=ProviderRequestCounter(lambda:next(ticks))
    for _ in range(2):
        counter.invoke(Category.INSTRUMENT_BINDING_REQUEST,lambda:None)
    assert counter.snapshot()["actual_provider_requests"] == 2
    assert counter.snapshot()["provider_acquisition_started_at"] is None
    assert next(ticks) == NOW


@pytest.mark.parametrize("unknown",[False,True])
def test_pre_assessment_accounting_bytes_restore_without_new_category(unknown):
    from kronos.intraday.operation_accounting import DiscoveryOperationAccounting, _identity as accounting_identity
    values=_values()
    values.update(contract_identity="KRONOS-INTRADAY-DISCOVERY-OPERATION-ACCOUNTING",contract_version="1.0.0",
        request_categories=tuple((c,0) for c in Category if c is not Category.ASSESSMENT_OBSERVATION_REQUEST))
    if unknown:values.update(actual_provider_requests=None,request_categories=None,benchmark_subject_requests=None)
    old=DiscoveryOperationAccounting(accounting_identity=accounting_identity("INTRADAY-OPERATION-ACCOUNTING-",values),
        integrity_identity=accounting_identity("INTEGRITY-INTRADAY-OPERATION-ACCOUNTING-",values),**values)
    payload=accounting_bytes(old)
    assert b"ASSESSMENT_OBSERVATION_REQUEST" not in payload
    assert accounting_bytes(restore_accounting(payload))==payload
    assert restore_accounting(payload).actual_provider_requests==(None if unknown else 0)
