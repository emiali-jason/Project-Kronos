"""Disposable normal Analysis rehearsal; actual owners and fake Provider only."""
from datetime import date,datetime,timedelta
import pytest
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.application.intraday_discovery_operation import DiscoveryOperationState
from kronos.provider.contracts.market_data import HistoricalCandle,HistoricalInterval
from tests.unit.application.test_intraday_discovery_operation import _configured_shared,_request_at,IST
from tests.unit.provider.test_shared_provider_runtime import _authenticate
from tests.unit.instrument.test_active_derivative_selection import _rows
from tests.unit.intraday.test_native_pullback_policy import BARS


def configured_experimental_runtime(tmp_path,direction):
    clock_value=[datetime(2026,9,11,12,2,tzinfo=IST)]
    stage=['I2_PENDING']
    calls=[]
    shared,provider,_,_=_configured_shared()
    from decimal import Decimal
    from kronos.provider.contracts.instrument_master import ProviderInstrumentMasterSourceRecord
    nse=provider.capability.instrument_records('NSE')
    master=tuple(ProviderInstrumentMasterSourceRecord(provider='KITE',provider_instrument_token=200000+i,
        exchange_token=1200000+i,trading_symbol=r.trading_symbol,name=r.name,last_price=Decimal(0),
        expiry=None,strike=Decimal(0),tick_size=Decimal('0.05'),lot_size=1,instrument_type=r.instrument_type,
        segment=r.segment,exchange=r.exchange) for i,r in enumerate(nse)) + _rows() + (
        ProviderInstrumentMasterSourceRecord('KITE',500000,None,'LUPIN26SEPFUT','LUPIN',None,
            date(2026,9,29),None,Decimal('.05'),100,'FUT','NFO-FUT','NFO'),)
    def master_records():
        calls.append(('INSTRUMENT_MASTER',))
        return master
    provider.capability.instrument_master_records=master_records
    _authenticate(shared)
    def raw(at,row):
        h,l,c=row
        if direction=='SHORT':h,l,c=300-l,300-h,300-c
        return HistoricalCandle(at,float(c),float(h),float(l),float(c),1000)
    def historical(request):
        calls.append(request)
        selected=request.instrument.exchange=='MCX' or request.instrument.trading_symbol=='LUPIN'
        if request.interval is HistoricalInterval.DAY:
            return (raw(request.start,(125,85,105) if selected else (102,98,100)),)
        minutes={HistoricalInterval.SIXTY_MINUTE:60,HistoricalInterval.FIFTEEN_MINUTE:15,HistoricalInterval.FIVE_MINUTE:5}[request.interval]
        end=request.end;start=request.start
        count=int((end-start).total_seconds()//(minutes*60))
        result=[]
        for i in range(count+1):
            at=start+timedelta(minutes=minutes*i)
            if minutes==60:row=(112+i*3,100+i*3,110+i*3)
            elif minutes==15:row=BARS[i] if i<len(BARS) else (114+i-8,105+i-8,112+i-8)
            else:
                row=(108,102,106)
                if i==count-2:row=(115,110,113 if stage[0]=='I2_PENDING' else 114)
                elif i==count-1:row=(117,114,116)
            if not selected: row=(102,98,100)
            result.append(raw(at,row))
        return tuple(result)
    provider.capability.historical_candles=historical
    # Commission the producer just before the requested analysis boundary.
    now=[clock_value[0]-timedelta(seconds=1)]
    runtime=create_intraday_runtime(shared,evidence_root=tmp_path/'evidence',clock=lambda:now[0])
    now[0]=clock_value[0]
    from tests.unit.intraday.test_wo10_futures import raw_quotes,config
    from kronos.provider.adapters.kite.full_quote import normalize_full_quotes
    def full_quotes(instruments,*,request_identity,timeout):
        calls.append(('FULL_QUOTES',request_identity,tuple(x.trading_symbol for x in instruments)))
        return normalize_full_quotes(raw_quotes(instruments,now=now[0]),instruments)
    provider.capability.full_quotes=full_quotes
    # Isolated operational authorization, as supplied by the Browser in production.
    # The real publication boundary and every retained source guard remain intact.
    runtime.futures_application.operational_guard=lambda:provider.capability.active
    source=runtime.futures_application.acquisition_source
    source.configuration_source=lambda handoff:config(effective_at=now[0],expires_at=now[0]+timedelta(hours=1))
    from kronos.intraday.wo14 import create_wo14_instrument_economics
    def economics(handoff,binding):
        if binding is None:return None
        contract=binding.active_binding.derivative_contract_id
        return create_wo14_instrument_economics(economics_version='1.0.0',
            canonical_subject_identity=handoff.canonical_subject_identity,instrument_identity=contract,
            actual_contract_identity=contract,roll_lineage_identity=binding.binding_identity,
            lot_size=binding.lot_size,contract_multiplier=Decimal(1),tick_size=binding.tick_size,tick_value=None,
            observed_at=now[0],source_identities=(binding.binding_identity,),source_integrities=(binding.integrity_identity,))
    source.economics_source=economics
    return runtime,shared,now,stage,calls


@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_normal_analysis_experimental_population_progression_and_restart(tmp_path,direction,monkeypatch,request):
    runtime,shared,now,stage,calls=configured_experimental_runtime(tmp_path,direction)
    import traceback
    errors=[]
    def capture(fn):
        def wrapped(*args,**kwargs):
            try:return fn(*args,**kwargs)
            except Exception:
                errors.append(traceback.format_exc());raise
        return wrapped
    monkeypatch.setattr(runtime.wo08_publication,'publish_run',capture(runtime.wo08_publication.publish_run))
    monkeypatch.setattr(runtime.wo09_application,'evaluate_wo08',capture(runtime.wo09_application.evaluate_wo08))
    result=runtime.discovery_v2_operation.execute(_request_at('EXPERIMENTAL-FOUR-'+direction,now[0]))
    assert not errors, '\n'.join(errors)
    assert result.state is DiscoveryOperationState.COMPLETE,str(result)
    assessments=runtime.wo08_store.current_run()
    assert len(assessments)==98
    assert all(a.data['methodology_version']=='0.1.0' for a in assessments)
    candidates=[a for a in assessments if [c['state'] for c in a.data['criteria']]==['SATISFIED','OUTSTANDING','SATISFIED','SATISFIED','SATISFIED']]
    assert candidates,[(a.data['subject'],a.data['probables_state'],a.data['hard_gate'],[c['state'] for c in a.data['criteria']]) for a in assessments]
    assert {a.data['market_family'] for a in candidates}=={'NSE','MCX'}
    natgas=next(a for a in assessments if a.data['subject']=='MCX-SUBJECT-NATGAS')
    assert natgas.data['hard_gate']=='NATGAS_COMMISSIONING_HELD'
    readiness=runtime.wo09_application.restore()
    assert len(readiness)==98
    assert any(r.satisfied_count==4 for _,r in readiness)
    from decimal import Decimal
    from datetime import date
    from kronos.provider.contracts.instrument import InstrumentRecord
    from kronos.provider.contracts.monitoring import ProviderMarketTick
    from kronos.application.intraday_experimental_watch import BINDING,HINT
    coordinator=runtime.wo09_application.experimental_watches
    bindings=coordinator.store.records(BINDING)
    assert bindings and {b['instrument']['exchange'] for b in bindings}=={'NSE','MCX'}
    requests_before=len(calls)
    before_readiness=runtime.wo09_application.restore()
    now[0]+=timedelta(seconds=1)
    for b in bindings:
        raw=dict(b['instrument'])
        raw['expiry']=None if raw['expiry'] is None else date.fromisoformat(raw['expiry'])
        raw['tick_size']=None if raw['tick_size'] is None else Decimal(raw['tick_size'])
        instrument=InstrumentRecord(**raw)
        price=Decimal(b['hint_levels']['I2'])+(Decimal('.1') if direction=='LONG' else Decimal('-.1'))
        hints=coordinator.on_tick(ProviderMarketTick(instrument,price,now[0],now[0],
            'KITE_CONNECT_WEBSOCKET','ISOLATED-CONTINUOUS-CONNECTION',1,True,True,True))
        assert hints and all(h['state']=='ADVISORY_WAKE_HINT' for h in hints)
    assert len(coordinator.store.records(HINT))==len(bindings)
    assert runtime.wo09_application.restore()==before_readiness
    assert len(calls)==requests_before
    # Ordinary next Analysis is explicitly requested; watches never acquire it.
    stage[0]='COMPLETE';now[0]+=timedelta(minutes=5)
    later=runtime.discovery_v2_operation.execute(_request_at('EXPERIMENTAL-FIVE-'+direction,now[0]))
    assert later.state is DiscoveryOperationState.COMPLETE,later
    assert len(calls)>requests_before
    latest=runtime.wo09_application.restore()
    positive=[r for _,r in latest if r.satisfied_count==5]
    assert positive
    assert all(r.first_five_document is not None for r in positive)
    from kronos.intraday.wo09_watch import WatchState
    assert any(w.state is WatchState.TRIGGERED and w.reacquisition_identity for w in coordinator.store.watch_history())
    assert {r.market_family for r in positive}=={'NSE','MCX'}
    assert not runtime.wo09_store.handoffs.exists()
    assert runtime.futures_application.store.records('WO10_OPPORTUNITY_V1')==()
    from kronos.intraday.native_structural_selection import NativeStructuralLoader
    from kronos.intraday.wo10_native_adapter import adapt_native
    paper_intakes=[]
    native_handoffs=[]
    for market in ('NSE','MCX'):
        readiness=next(r for r in positive if r.market_family==market)
        handoff=runtime.wo09_application.create_handoff(readiness,created_at=now[0])
        native=NativeStructuralLoader(runtime.probables_v2_application.native_selection.store).load(handoff,now=now[0])
        adapter,_,_=adapt_native(native,handoff,readiness,runtime.wo09_store.load_pointer(readiness.canonical_subject_identity),now=now[0])
        assert adapter.canonical_subject_identity==readiness.canonical_subject_identity
        assert handoff.authority=='EXPERIMENTAL_PAPER_ONLY'
        native_handoffs.append(handoff)
        authority=runtime.futures_application.acquisition_source.authority(handoff)
        if market=='NSE':
            from dataclasses import replace
            underlying=authority['underlying']
            assert underlying.resolve(authority['master'],handoff,now[0]).trading_symbol=='LUPIN'
            with pytest.raises(ValueError,match='SOURCE_CONFLICT'):
                replace(underlying,canonical_subject_identity=next(m.canonical_identity
                    for m in underlying.reconciliation.members if m.exchange=='NSE'
                    and m.canonical_identity!=underlying.canonical_subject_identity
                    and m.provider_symbol and m.provider_directive_identities)).resolve(authority['master'],handoff,now[0])
            from tests.unit.intraday.test_wo10_futures import master
            wrong_master,_=master()
            with pytest.raises(ValueError,match='SOURCE_CONFLICT'):
                underlying.resolve(wrong_master,handoff,now[0])
        comparison=runtime.futures_application.construct_current(handoff_identity=handoff.handoff_identity,
            request_identity='ISOLATED-EXPLICIT-CONSTRUCT-'+market+'-'+direction)
        assert comparison.schema=='WO10_SPONSOR_COMPARISON_V1',comparison.data
        assert comparison.data['executability']=='EXECUTABLE',comparison.data
        selection=runtime.futures_application.select(comparison.identity,choice='SELECTED_FUTURE',lots=1,
            session=runtime.lifecycle_application.session_source(readiness.canonical_subject_identity,now[0]),
            action_identity='ISOLATED-EXPLICIT-SELECT-'+market+'-'+direction)
        selected=next(h for h in runtime.futures_application.store.records('WO10_SELECTED_TRADE_HANDOFF_V1')
            if h.data['selection_identity']==selection.identity)
        track=runtime.lifecycle_application.action(handoff_identity=selected.identity,
            action='ACTIVATE_PAPER' if market=='NSE' else 'OBSERVE',
            action_identity='ISOLATED-EXPLICIT-PAPER-'+market+'-'+direction)
        assert track.data['lots']==1 and track.data['entry'] is None
        assert track.data['truth_class']==('PAPER_POSITION' if market=='NSE' else 'PAPER_OBSERVATION')
        paper_intakes.append(track)
    assert len(runtime.lifecycle_application.store.restore())==2
    assert len([c for c in calls if isinstance(c,tuple) and c[0]=='FULL_QUOTES'])==2
    runtime.research_application.publication_root=tmp_path/'Statistics'
    research_publication=runtime.research_application.update(operation_identity='ISOLATED-EXPLICIT-RESEARCH-'+direction)
    assert research_publication.outcome=='PUBLISHED',research_publication
    associations=runtime.research_store.records('WO12_WO08_EXPERIMENTAL_ASSOCIATION_V1')
    assert len(associations)==196
    assert any(a.data['selective_watch_history'] and a.data['advisory_wake_hints'] for a in associations)
    assert any(a.data['first_five_provenance'] for a in associations)
    assert all(a.data['live_control_authority']=='NONE' for a in associations)
    before=len(calls)
    watch_records=coordinator.store.records()
    watch_history=coordinator.store.watch_history()
    restored=create_intraday_runtime(shared,evidence_root=tmp_path/'evidence',clock=lambda:now[0])
    assert restored.wo09_application.restore()==latest
    assert restored.wo08_store.current_run()==runtime.wo08_store.current_run()
    assert len(calls)==before
    assert restored.wo09_application.experimental_watches.store.records()==watch_records
    assert restored.wo09_application.experimental_watches.store.watch_history()==watch_history
    assert restored.lifecycle_application.store.restore()==tuple(paper_intakes) or set(
        r.identity for r in restored.lifecycle_application.store.restore())==set(r.identity for r in paper_intakes)
    for handoff in native_handoffs:
        # Restart has no operation-local last snapshot; exact retained Discovery is sufficient.
        assert restored.futures_application.acquisition_source.authority(handoff)['master'].snapshot_identity
    assert len(calls)==before
    assert shared.active_lease_count==0
    fresh_boundary=now[0];now[0]+=timedelta(seconds=301)
    with pytest.raises(ValueError,match='NOT_CURRENT_FIVE'):
        runtime.wo09_application.create_handoff(positive[0],created_at=fresh_boundary)

    if request.config.option.xmlpath:
        import json
        from pathlib import Path
        output=Path(request.config.option.xmlpath)
        summary=dict(result='DISPOSABLE_PRODUCTION_SHAPED_REHEARSAL_PASS',direction=direction,
            initial_probables_run=result.probables_run_identity,successor_probables_run=later.probables_run_identity,
            population_per_analysis=98,experimental_assessment_count=196,current_readiness_count=len(latest),
            method='KRONOS-INTRADAY-WO08-EXPERIMENTAL-PULLBACK-PAPER/0.1.0',
            source_valid_four_subjects=[a.data['subject'] for a in candidates],
            source_valid_five_subjects=[r.canonical_subject_identity for r in positive],
            markets=sorted({r.market_family for r in positive}),
            watch_bindings=len(bindings),advisory_wake_hints=len(coordinator.store.records(HINT)),
            triggered_watch_events=sum(w.state is WatchState.TRIGGERED for w in watch_history),
            tick_promoted_readiness=False,provider_calls_from_wake=0,
            fake_ordinary_provider_calls=len(calls),real_provider_calls=0,
            first_five_times={r.canonical_subject_identity:r.first_five_of_five_at.isoformat() for r in positive},
            explicit_paper_handoffs=2,typed_native_wo10_intakes=2,guarded_futures_comparisons=2,
            explicit_future_selections=2,wo11_paper_intakes=[r.data['truth_class'] for r in paper_intakes],
            automatic_positions=0,broker_trading_actions=0,backdated_stale_handoff='REJECTED',
            research_associations=len(associations),research_publication=research_publication.outcome,watch_and_first_five_restart='EXACT_RETAINED_READBACK',
            original_assessment_price='UNMODIFIED_BY_EXPERIMENTAL_METHOD',
            terminal_eod_business_validation='NOT_YET_EXERCISED',natgas='HELD',
            predictive_usefulness='NOT_ESTABLISHED',live_broker_authority='NONE')
        with output.with_name(output.stem+'-'+direction.lower()+'-summary.json').open('x') as file:
            json.dump(summary,file,indent=2);file.write('\n')
