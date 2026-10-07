"""WO07 synthetic qualification only. All stores tmp_path; no live certification.

Actual admission, isolated advisory, activation, shared hub, Kite adapter,
lifecycle and notification/Journal owners. Owning socket is a labelled mock.
"""
from contextlib import nullcontext
from dataclasses import replace
from datetime import date,timedelta
from decimal import Decimal
from types import SimpleNamespace
import pytest

from kronos.application.swing_mcx_journal import mcx_journal_handoffs
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_ux10 import SwingUx10NotificationService,Ux10NotificationStore
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import ProviderMarketTick,MonitoringSubscriptionEvidence,MonitoringConnectionState,MonitoringError
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_trade_plan import LocalMcxTradePlanStore,admit_v1_mcx_paper
from kronos.swing.v1.native_sponsor_decision import LocalSponsorDecisionStore,create_trade_plan_business_judgment,record_trade_plan_risk_result
from kronos.swing.v1.step32 import RiskState
from kronos.swing.v1.mcx_contract_lifecycle import McxContractBoundLifecycle,LocalMcxHistoricalContractStore
from kronos.swing.v1.native_active_trade_lifecycle import ActiveTradeLifecycleService,LocalActiveTradeLifecycleStore,ActiveLifecycleState,LifecycleEventType
from kronos.swing.v1.mcx_v1_advisory import LocalMcxV1AdvisoryStore
from kronos.swing.v1.mcx_v1_issuer import issue_v1_isolated_signal
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from tests.unit.swing.v1.test_mcx_kr380_issuer import _v1_fixture
from tests.unit.swing.v1.test_mcx_contract_lifecycle import _wire_monitor

def inventory(root):
    return {str(p.relative_to(root)):(p.read_bytes(),p.stat().st_mtime_ns,p.stat().st_ctime_ns)for p in root.rglob('*')if p.is_file()}

def paper_fixture(root,family,direction):
    read=_v1_fixture(family,direction);plan=read.plan
    plans=LocalMcxTradePlanStore(root/'plans');plans.retain(plan)
    judgment=create_trade_plan_business_judgment(plan,validation_identity='SYNTHETIC-WO07',created_at=plan.created_at)
    risk=record_trade_plan_risk_result(plan,judgment,RiskState.UNAVAILABLE,reason='MONETARY_FACTS_UNKNOWN',evaluated_at=plan.created_at)
    read=replace(read,risk=risk)
    outcomes=LocalMcxV1AdvisoryStore(root/'advisories')
    outcome=issue_v1_isolated_signal(lambda:read,evaluated_at=read.current.closed_at+timedelta(seconds=1),store=outcomes,commit_guard=nullcontext,guarded_recheck=lambda _:True)
    sponsor=LocalSponsorDecisionStore(root/'sponsor')
    admitted=admit_v1_mcx_paper(plan,judgment,risk,sponsor,current_plan_id=plan.trade_plan_id,decided_at=plan.created_at+timedelta(seconds=1))
    lifecycle=ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root/'lifecycle'))
    armed=lifecycle.register(admitted,plan)
    bound=McxContractBoundLifecycle(lifecycle,LocalMcxHistoricalContractStore(root/'historical'))
    instrument=InstrumentRecord('KITE','MCX','MCX-FUT',plan.contract_symbol,family.value,'FUT',date.fromisoformat(plan.expiry),Decimal('1'),1)
    bound.retain_existing(armed.position_id,instrument)
    at=outcome.confirmed_at+timedelta(seconds=2)
    tick=ProviderMarketTick(instrument,Decimal('101'if direction=='LONG'else'99'),at,at+timedelta(seconds=1),'KITE_CONNECT_WEBSOCKET','SYNTHETIC-ENTRY-CONNECTION',None,False,False,False)
    context=MonitoringSubscriptionEvidence(instrument,tick.connection_id,at-timedelta(seconds=1),MonitoringConnectionState.CONNECTED,202)
    active=bound.activate_v1_paper_at_observed_cmp(armed.position_id,plan,outcome,tick,read.schedule,plan_store=plans,sponsor_store=sponsor,outcome_store=outcomes,connection_state=MonitoringConnectionState.CONNECTED,commit_guard=nullcontext,current_readset=lambda:(plan,outcome,tick),subscription_evidence=context,current_subscription=lambda:context)
    clock=[tick.received_at+timedelta(seconds=1)]
    monitor,capability,hub=_wire_monitor(lifecycle,bound.bindings,instrument,clock)
    native=NativeReviewWorkflow(NativeReviewEvidenceStore(root/'review'),active_lifecycle_service=lifecycle,active_lifecycle_monitoring=monitor,mcx_historical_contract_store=bound.bindings)
    notifications=SwingUx10NotificationService(Ux10NotificationStore(root/'notifications'),clock=lambda:clock[0],background_runner=lambda operation,_name:operation(),retry_scheduler=lambda *_:None)
    lifecycle.set_ux10_event_listener(notifications.observe_lifecycle_event)
    control=SimpleNamespace(lifecycle=lifecycle,bound=bound,plans=plans,native_review=native)
    return control,active,instrument,plan,monitor,capability,hub,clock,notifications


"""WO08 labelled synthetic qualification; temporary stores and mock socket only.

Uses actual deployed admission/exit/control/monitoring owners. No production fills.
"""
from contextlib import nullcontext
from datetime import date,timedelta
from decimal import Decimal
from hashlib import sha256
from dataclasses import replace
from types import SimpleNamespace
import json
import pytest

from kronos.application.swing_mcx_v1_operations import SwingMcxV1OperationalControl
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_mcx_journal import mcx_journal_handoffs
from kronos.application.swing_ux10 import SwingUx10NotificationService,Ux10NotificationStore
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.instrument_master_persistence import ProviderInstrumentSnapshotStore
from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
from kronos.swing.v1.mcx_trade_plan import LocalMcxTradePlanStore
from kronos.swing.v1.mcx_v1_advisory import LocalMcxV1AdvisoryStore
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_contract_lifecycle import LocalMcxHistoricalContractStore,McxContractBoundLifecycle
from kronos.swing.v1.mcx_live_attestation import LocalMcxLiveFillAttestationStore,McxLiveFillAttestation,admit_v1_mcx_manual_live
from kronos.swing.v1.mcx_broker_fill_evidence import LocalMcxBrokerFillEvidenceStore
from kronos.swing.v1.native_sponsor_decision import LocalSponsorDecisionStore,create_trade_plan_business_judgment,record_trade_plan_risk_result
from kronos.swing.v1.native_active_trade_lifecycle import ActiveLifecycleState,ActiveTradeLifecycleService,LocalActiveTradeLifecycleStore,TradeExitReason
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.step32 import RiskState
from tests.unit.swing.v1.test_mcx_kr380_issuer import _v1_fixture
from tests.unit.swing.v1.test_mcx_contract_lifecycle import _wire_monitor

def owner(root,parts):
    control,pos,instrument,plan,monitor,capability,hub,clock,notifications=parts
    result=SwingMcxV1OperationalControl(None,None,control.native_review,control.plans,
        LocalSponsorDecisionStore(root/'sponsor'),control.lifecycle,control.bound.bindings,
        LocalMcxV1AdvisoryStore(root/'advisories'),ProviderInstrumentSnapshotStore(root/'master'),
        MtfFactEvidenceStore(root/'mtf'),lambda:pytest.fail('Provider acquisition prohibited'),
        MarketCalendarPublisher(),LocalMcxLiveFillAttestationStore(root/'attestations'),
        LocalMcxBrokerFillEvidenceStore(root/'broker'),capability)
    return result

def live_fixture(root,family,direction):
    plan=_v1_fixture(family,direction).plan
    plans=LocalMcxTradePlanStore(root/'plans');plans.retain(plan)
    judgment=create_trade_plan_business_judgment(plan,validation_identity='SYNTHETIC-WO08',created_at=plan.created_at)
    risk=record_trade_plan_risk_result(plan,judgment,RiskState.UNAVAILABLE,reason='UNKNOWN_MONETARY_FACTS',evaluated_at=plan.created_at)
    outcomes=LocalMcxV1AdvisoryStore(root/'advisories')
    attestations=LocalMcxLiveFillAttestationStore(root/'attestations');broker=LocalMcxBrokerFillEvidenceStore(root/'broker')
    sponsor=LocalSponsorDecisionStore(root/'sponsor');entry_bytes=b'LABELLED SYNTHETIC SPONSOR ENTRY'
    at=plan.created_at+timedelta(seconds=2)
    entry=McxLiveFillAttestation.create(plan,contract_symbol=plan.contract_symbol,expiry=plan.expiry,lots=3,provider_order_quantity=None,entry_outcome=None,
        fill_price=Decimal('101'if direction=='LONG'else'99'),fill_at=at,broker_evidence_id='SYNTHETIC-ENTRY',broker_evidence_sha256=sha256(entry_bytes).hexdigest(),attested_at=at+timedelta(seconds=1),v1_manual=True)
    admitted=admit_v1_mcx_manual_live(plan,judgment,risk,None,outcomes,entry,attestations,broker,entry_bytes,sponsor,current_plan_id=plan.trade_plan_id,decided_at=entry.attested_at)
    lifecycle=ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root/'lifecycle'));pos=lifecycle.register(admitted,plan)
    historical=LocalMcxHistoricalContractStore(root/'historical');bound=McxContractBoundLifecycle(lifecycle,historical)
    instrument=InstrumentRecord('KITE','MCX','MCX-FUT',plan.contract_symbol,family.value,'FUT',date.fromisoformat(plan.expiry),Decimal('1'),1);bound.retain_existing(pos.position_id,instrument)
    clock=[at+timedelta(seconds=3)];monitor,capability,hub=_wire_monitor(lifecycle,historical,instrument,clock)
    native=NativeReviewWorkflow(NativeReviewEvidenceStore(root/'review'),active_lifecycle_service=lifecycle,active_lifecycle_monitoring=monitor,mcx_historical_contract_store=historical)
    notifications=SwingUx10NotificationService(Ux10NotificationStore(root/'notifications'),clock=lambda:clock[0],background_runner=lambda op,_name:op(),retry_scheduler=lambda *_:None)
    lifecycle.set_ux10_event_listener(notifications.observe_lifecycle_event)
    return SimpleNamespace(lifecycle=lifecycle,bound=bound,plans=plans,native_review=native),pos,instrument,plan,monitor,capability,hub,clock,notifications

@pytest.mark.parametrize('family',list(McxFamily))
@pytest.mark.parametrize('direction',['LONG','SHORT'])
@pytest.mark.parametrize('level',['STOP','TARGET'])
def test_live_touch_requires_action_and_attested_fill_closes_once(tmp_path,family,direction,level):
    parts=live_fixture(tmp_path,family,direction);c,pos,instrument,plan,monitor,cap,hub,clock,notifications=parts
    op=owner(tmp_path,parts);monitor.attach(pos.position_id,cap,instrument)
    try:
        clock[0]+=timedelta(seconds=2);cap.tick(100)
        clock[0]+=timedelta(seconds=2);touch=plan.stop if level=='STOP'else plan.canonical_target;cap.tick(float(touch))
        current=c.lifecycle._require(pos.position_id);snap=c.lifecycle.snapshot()
        assert current.state is ActiveLifecycleState.LIVE_ACTIVE and not snap.closures and len(snap.notifications)==1
        assert 'ACTION REQUIRED' in snap.notifications[0].message
        assert any(n.source_event_identity in {e.event_id for e in snap.events} for n in notifications.snapshot().records)
        assert current.actual_entry==pos.actual_entry and current.lots==3
        at=clock[0]+timedelta(seconds=2);evidence=b'LABELLED SYNTHETIC ACTUAL EXIT';price=touch+Decimal('0.5')
        kwargs=dict(position_id=pos.position_id,expected_hash=current.integrity_hash,contract=plan.contract_symbol,expiry=plan.expiry,lots=3,fill_price=price,fill_at=at,evidence_id='SYNTHETIC-EXIT',evidence_sha256=sha256(evidence).hexdigest(),evidence_bytes=evidence,reason=TradeExitReason.SPONSOR_MANUAL_EXIT,attested_at=at+timedelta(seconds=1))
        before=inventory(tmp_path)
        with pytest.raises(ValueError,match='ATTESTATION_UNAVAILABLE'):
            c.bound.record_live_exit(pos.position_id,actual_exit=price,exit_timestamp=at,reason=TradeExitReason.SPONSOR_MANUAL_EXIT)
        for field,value in [('contract','WRONG26NOVFUT'),('expiry','2026-11-30'),('lots',2),('expected_hash','b'*64),('evidence_bytes',b'CONFLICT')]:
            with pytest.raises(ValueError):op.record_manual_live_exit(**{**kwargs,field:value})
            assert inventory(tmp_path)==before
        closure=op.record_manual_live_exit(**kwargs)
        assert closure.actual_exit==price and closure.exit_timestamp==at and closure.mcx_v1_contract_symbol==plan.contract_symbol and closure.gross_pnl is None
        assert c.lifecycle._require(pos.position_id).state is ActiveLifecycleState.CLOSED
        assert op.live_attestations.load_exit(pos.position_id).fill_price==price
        assert len(c.lifecycle.snapshot().closures)==1
        retained=inventory(tmp_path)
        assert op.record_manual_live_exit(**{**kwargs,'attested_at':at+timedelta(seconds=9)})==closure
        assert inventory(tmp_path)==retained
        with pytest.raises(ValueError,match='REPLAY_CONFLICT'):
            op.record_manual_live_exit(**{**kwargs,'fill_price':price+1})
        assert inventory(tmp_path)==retained
        row,=mcx_journal_handoffs(op,at.date())
        assert row.exit==price and row.completion_timestamp==at and row.position_lots==3 and row.monetary_pnl_state=='UNKNOWN'
        assert not any(hasattr(op,name)for name in ('place_order','modify_order','cancel_order'))
    finally:monitor.close();op.close()


def exit_kwargs(parts):
    control, position, instrument, plan, monitor, capability, hub, clock, _ = parts
    evidence = b'LABELLED SYNTHETIC EXIT; NO BROKER EXECUTION'
    at = clock[0] + timedelta(seconds=2)
    return dict(position_id=position.position_id,
                expected_hash=control.lifecycle._require(position.position_id).integrity_hash,
                contract=instrument.trading_symbol, expiry=instrument.expiry.isoformat(),
                lots=position.lots, fill_price=Decimal('102'), fill_at=at,
                evidence_id='SYNTHETIC-EXIT', evidence_sha256=sha256(evidence).hexdigest(),
                evidence_bytes=evidence, reason=TradeExitReason.SPONSOR_MANUAL_EXIT,
                attested_at=at + timedelta(seconds=1))


@pytest.mark.parametrize('mode', ['PAPER', 'LIVE'])
def test_other_consumer_and_unrelated_position_survive_dedicated_exit(tmp_path, mode):
    from tests.unit.application.test_shared_monitoring import Consumer
    parts = (paper_fixture if mode == 'PAPER' else live_fixture)(
        tmp_path / 'exiting', McxFamily.CRUDEOIL, 'LONG')
    other = paper_fixture(tmp_path / 'unrelated', McxFamily.NATURALGAS, 'SHORT')
    c, pos, instrument, plan, monitor, cap, hub, clock, _ = parts
    op = owner(tmp_path / 'exiting', parts)
    monitor.attach(pos.position_id, cap, instrument)
    other[4].attach(other[1].position_id, other[5], other[2])
    consumer = Consumer()
    registration = hub.open(cap, consumer)
    registration.subscribe((instrument,)); registration.connect()
    try:
        clock[0] += timedelta(seconds=2); cap.tick(100)
        unrelated_before = inventory(tmp_path / 'unrelated')
        kwargs = exit_kwargs(parts)
        if mode == 'PAPER':
            closure = op.paper_exit(pos.position_id, kwargs['expected_hash'])
        else:
            closure = op.record_manual_live_exit(**kwargs)
        assert not monitor.active_position_ids
        assert hub.subscription_reference_count(instrument) == 1
        assert hub.active_session_count == 1 and not cap.socket.closed
        assert registration.active and other[4].active_position_ids == (other[1].position_id,)
        assert inventory(tmp_path / 'unrelated') == unrelated_before
        release_counts = hub.status_document()['release_counts']
        if mode == 'LIVE':
            retained = inventory(tmp_path / 'exiting')
            assert op.record_manual_live_exit(**kwargs) == closure
            with pytest.raises(ValueError, match='REPLAY_CONFLICT'):
                op.record_manual_live_exit(**{**kwargs, 'fill_price': Decimal('103')})
            assert inventory(tmp_path / 'exiting') == retained
        else:
            with pytest.raises(ValueError, match='STALE'):
                op.paper_exit(pos.position_id, kwargs['expected_hash'])
        assert hub.status_document()['release_counts'] == release_counts
        assert len(c.lifecycle.snapshot().closures) == 1
        registration.disconnect()
        assert hub.subscription_reference_count(instrument) == 0 and cap.socket.closed
        assert other[6].active_session_count == 1 and not other[5].socket.closed
    finally:
        registration.disconnect(); monitor.close(); other[4].close(); op.close()


@pytest.mark.parametrize('mode', ['PAPER', 'LIVE'])
def test_cleanup_failure_is_propagated_and_retired_transport_remains_owned(tmp_path, monkeypatch, mode):
    from tests.unit.application.test_shared_monitoring import Consumer
    parts = (paper_fixture if mode == 'PAPER' else live_fixture)(
        tmp_path, McxFamily.CRUDEOIL, 'LONG')
    c, pos, instrument, plan, monitor, cap, hub, clock, _ = parts
    op = owner(tmp_path, parts); monitor.attach(pos.position_id, cap, instrument)
    clock[0] += timedelta(seconds=2); cap.tick(100)
    kwargs = exit_kwargs(parts)
    captured = []
    op._research_capture = lambda kind, value: captured.append((kind, value))
    def fail(_session):
        raise OSError('SYNTHETIC-TRANSPORT-CLEANUP-FAILURE')
    monkeypatch.setattr(type(cap.session), 'disconnect', fail)
    try:
        with pytest.raises(OSError, match='SYNTHETIC-TRANSPORT-CLEANUP-FAILURE'):
            if mode == 'PAPER': op.paper_exit(pos.position_id, kwargs['expected_hash'])
            else: op.record_manual_live_exit(**kwargs)
        closure, = c.lifecycle.snapshot().closures
        assert captured == [('CLOSURE', closure)]
        assert c.lifecycle._require(pos.position_id).state is ActiveLifecycleState.CLOSED
        assert not monitor.active_position_ids
        status = hub.status_document()
        assert status['transport_cleanup']['state'] == 'FAILED'
        assert status['transport_cleanup']['retired_session_owned']
        assert status['session_count'] == 1 and not cap.socket.closed
        retained = inventory(tmp_path)
        if mode == 'LIVE':
            # Immutable closure replay does not clear or certify failed transport cleanup.
            assert op.record_manual_live_exit(**kwargs) == closure
            assert inventory(tmp_path) == retained
        blocked = hub.open(cap, Consumer()); blocked.subscribe((instrument,))
        with pytest.raises(ValueError, match='CLEANUP_UNRESOLVED'): blocked.connect()
        blocked.disconnect()
        assert hub.status_document()['transport_cleanup']['state'] == 'FAILED'
        assert len(c.lifecycle.snapshot().closures) == 1
    finally:
        monitor.close(); op.close()


def test_manual_live_transport_retirement_runs_without_outer_operation_lock(tmp_path, monkeypatch):
    from threading import Event, Thread
    parts = live_fixture(tmp_path, McxFamily.CRUDEOIL, 'LONG')
    op = owner(tmp_path, parts); pos = parts[1]
    parts[4].attach(pos.position_id, parts[5], parts[2])
    original = op.native_review.detach_lifecycle_monitoring
    joined = []
    def retire(identity):
        acquired = Event()
        def inspect():
            with op._lock: acquired.set()
        thread = Thread(target=inspect); thread.start()
        try:
            assert acquired.wait(2), 'transport cleanup retained outer operation lock'
        finally:
            thread.join(2); joined.append(not thread.is_alive())
        original(identity)
    monkeypatch.setattr(op.native_review, 'detach_lifecycle_monitoring', retire)
    try:
        op.record_manual_live_exit(**exit_kwargs(parts))
        assert joined == [True] and not parts[4].active_position_ids
    finally:
        parts[4].close(); op.close()

@pytest.mark.parametrize('mode',['PAPER','LIVE'])
@pytest.mark.parametrize('family',list(McxFamily))
@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_canonical_manual_closure_retires_monitor_without_another_tick(tmp_path,mode,family,direction):
    parts=(paper_fixture(tmp_path,family,direction) if mode=='PAPER'else live_fixture(tmp_path,family,direction))
    c,pos,instrument,plan,monitor,cap,hub,clock,_=parts;op=owner(tmp_path,parts)
    monitor.attach(pos.position_id,cap,instrument)
    try:
        clock[0]+=timedelta(seconds=2);cap.tick(100)
        current=c.lifecycle._require(pos.position_id)
        if mode=='PAPER':closure=op.paper_exit(pos.position_id,current.integrity_hash)
        else:
            evidence=b'LABELLED SYNTHETIC EXIT';at=clock[0]+timedelta(seconds=2)
            closure=op.record_manual_live_exit(position_id=pos.position_id,expected_hash=current.integrity_hash,contract=plan.contract_symbol,expiry=plan.expiry,lots=3,fill_price=Decimal('102'),fill_at=at,evidence_id='SYNTHETIC-EXIT',evidence_sha256=sha256(evidence).hexdigest(),evidence_bytes=evidence,reason=TradeExitReason.SPONSOR_MANUAL_EXIT,attested_at=at+timedelta(seconds=1))
        print('WO08_CLOSURE_CLEANUP_EVIDENCE',json.dumps(dict(mode=mode,position_state=c.lifecycle._require(pos.position_id).state.value,closure_id=closure.closure_id,active_monitor_ids=monitor.active_position_ids,session_count=hub.active_session_count,subscription_refs=hub.subscription_reference_count(instrument),transport_closed=cap.socket.closed)))
        assert not monitor.active_position_ids,'TERMINAL_POSITION_RETAINS_MONITOR_OWNER'
        assert hub.active_session_count==0 and hub.subscription_reference_count(instrument)==0 and cap.socket.closed
    finally:monitor.close();op.close()
