"""Real retained MCX plan/lifecycle joins; synthetic data confers no authority."""
from datetime import timedelta
from decimal import Decimal
from dataclasses import replace
from types import SimpleNamespace
from http.client import HTTPConnection
from threading import Thread

import pytest

from kronos.application.swing_mcx_journal import mcx_journal_handoffs
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser.server import create_browser_server
from kronos.browser.views import render_trade_journal
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.mcx_trade_plan import LocalMcxTradePlanStore
from kronos.swing.v1.mcx_contract_lifecycle import LocalMcxHistoricalContractStore, McxContractBoundLifecycle
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.native_active_trade_lifecycle import (
    LocalActiveTradeLifecycleStore, ActiveTradeLifecycleService,
    ActiveTradeLifecycleEngine, ActiveLifecycleState, _position as seal,
)
from tests.unit.swing.v1.test_mcx_kr380_issuer import _v1_fixture
from tests.unit.swing.v1.test_native_active_trade_lifecycle import _position
from tests.unit.swing.v1.test_mcx_contract_lifecycle import _wire_monitor, START
from tests.unit.application.test_swing_opportunities import _ready, _Provider
from tests.unit.application.test_swing_mcx_v1_composition import inventory
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from datetime import date


def fixture(root, family, *, active=False, live=False):
    plan = _v1_fixture(family).plan
    plans = LocalMcxTradePlanStore(root/'plans')
    plans.retain(plan)
    old, *_ = (_position(SponsorTradeChoice.LIVE,
                        actual_live_entry=Decimal('103.25'), live_lots=3)
               if live else _position())
    values = {k:getattr(old,k) for k in old.__dataclass_fields__ if k!='integrity_hash'}
    values.update(trade_plan_id=plan.trade_plan_id, trade_plan_hash=plan.integrity_hash,
                  canonical_instrument=family.value, mcx_v1_contract_symbol=plan.contract_symbol,
                  model_entry=plan.entry, stop=plan.stop, target=plan.canonical_target,
                  underlying_quantity=old.lots)
    if active and not live:
        values.update(state=ActiveLifecycleState.PAPER_ACTIVE, actual_entry=Decimal('101'),
                      entry_timestamp=START-timedelta(minutes=1), mcx_activation_outcome_sha256='a'*64)
    position=seal(values)
    lifecycle=ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root/'lifecycle'))
    lifecycle.store.retain_position(position)
    # Construct a fresh service from retained bytes, as canonical restoration does.
    lifecycle=ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root/'lifecycle'))
    historical=LocalMcxHistoricalContractStore(root/'historical')
    bound=McxContractBoundLifecycle(lifecycle,historical)
    instrument=InstrumentRecord('KITE','MCX','MCX-FUT',plan.contract_symbol,family.value,'FUT',
                                date.fromisoformat(plan.expiry),Decimal('1'),1)
    bound.retain_existing(position.position_id,instrument)
    native=NativeReviewWorkflow(NativeReviewEvidenceStore(root/'review'),
                               active_lifecycle_service=lifecycle,
                               mcx_historical_contract_store=historical)
    control=SimpleNamespace(lifecycle=lifecycle,plans=plans,bound=bound,native_review=native,close=lambda:None)
    return control,position,instrument,plan


@pytest.mark.parametrize('family',list(McxFamily))
@pytest.mark.parametrize('active',[False,True])
def test_exact_history_waiting_entered_restart_and_observational_projection(tmp_path,family,active):
    control,position,instrument,plan=fixture(tmp_path,family,active=active)
    first=mcx_journal_handoffs(control,START.date())[0]
    before=inventory(tmp_path)
    assert mcx_journal_handoffs(control,START.date())==(first,)
    html=render_trade_journal(_ready(),None,operational=(first,),
                             governed_trading_date=START.date(),selected_record_id=first.decision_identity)
    assert plan.contract_symbol in html and plan.expiry in html
    assert plan.native_run_identity in html and plan.receipt_integrity_sha256 in html
    assert plan.promotion_integrity_sha256 in html and plan.integrity_hash in html
    assert 'UNKNOWN' in html and '₹0' not in html
    assert first.entry==(Decimal('101') if active else None)
    assert ('0 WAITING · 1 ACTIVE' if active else '1 WAITING · 0 ACTIVE') in html
    assert inventory(tmp_path)==before
    interrupted,_,_=ActiveTradeLifecycleEngine.monitoring_unavailable(
        position,occurred_at=START,provider_context='isolated outage')
    control.lifecycle.store.retain_position(interrupted)
    control.lifecycle=ActiveTradeLifecycleService(control.lifecycle.store)
    control.bound=McxContractBoundLifecycle(control.lifecycle,control.bound.bindings)
    control.native_review._active_lifecycle=control.lifecycle
    row=mcx_journal_handoffs(control,START.date())[0]
    html=render_trade_journal(_ready(),None,operational=(row,),governed_trading_date=START.date())
    assert row.sponsor_position_prior_state==('PAPER_ACTIVE' if active else 'PAPER_ARMED')
    assert ('0 WAITING · 1 ACTIVE' if active else '1 WAITING · 0 ACTIVE') in html
    assert 'INTERRUPTED' in html


@pytest.mark.parametrize('family',list(McxFamily))
def test_real_subscription_reconnect_exit_and_exact_history(tmp_path,family):
    control,position,instrument,plan=fixture(tmp_path,family,active=True)
    clock=[START]
    monitor,capability,hub=_wire_monitor(control.lifecycle,control.bound.bindings,instrument,clock)
    control.native_review._active_lifecycle_monitoring=monitor
    try:
        monitor.attach(position.position_id,capability,instrument)
        clock[0]+=timedelta(minutes=1);capability.tick(102)
        first=mcx_journal_handoffs(control,START.date())[0]
        assert first.current_ltp==Decimal('102')
        capability.socket.on_close(capability.socket,1006,'isolated outage')
        row=mcx_journal_handoffs(control,START.date())[0]
        assert row.current_ltp is None and row.entry==Decimal('101') and row.monitoring_state=='INTERRUPTED'
        clock[0]+=timedelta(minutes=1);capability.socket.on_connect(capability.socket,{})
        clock[0]+=timedelta(minutes=1);capability.tick(103)
        row=mcx_journal_handoffs(control,START.date())[0]
        assert row.current_ltp==Decimal('103') and row.entry==Decimal('101')
        tick,_=monitor.latest_mcx_observation(position.position_id)
        schedule=monitor._calendar.schedule('MCX',START.date(),observed_at=clock[0])
        closure=control.bound.manual_paper_exit_at_cmp(position.position_id,tick,schedule)
        row=mcx_journal_handoffs(control,START.date())[0]
        assert row.exit==closure.actual_exit==Decimal('103')
        assert row.position_gross_pnl is None and row.monetary_pnl_state=='UNKNOWN'
        assert row.instrument==plan.contract_symbol and row.monitoring_state=='NOT_REQUIRED'
        history=mcx_journal_handoffs(control,START.date()+timedelta(days=1))[0]
        html=render_trade_journal(_ready(),None,operational=(history,),
                                 governed_trading_date=START.date()+timedelta(days=1),
                                 selected_record_id=history.decision_identity)
        assert 'EXITED HISTORY' in html and plan.contract_symbol in html
    finally:
        monitor.close()


@pytest.mark.parametrize('family',list(McxFamily))
def test_real_browser_mcx_journal_get_and_missing_plan_are_write_free(tmp_path,family):
    control,position,instrument,plan=fixture(tmp_path,family)
    app=SwingOpportunitiesApplication(_Provider,initial_snapshot=_ready())
    app.current_swing_trading_date=lambda:START.date()
    server=create_browser_server(app,port=0,native_review=control.native_review)
    server.mcx_v1_control=control
    server._next_swing_journal_reconciliation=float('inf')
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    def get():
        c=HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        c.request('GET','/journal?record='+position.decision_id)
        r=c.getresponse();result=(r.status,r.read().decode());c.close();return result
    try:
        before=inventory(tmp_path)
        for _ in range(2):
            status,body=get();assert status==200
            assert plan.contract_symbol in body and 'WAITING FOR ENTRY' in body
        assert inventory(tmp_path)==before
        # Interrupt retained source availability, rather than fabricate empty records.
        original=control.plans.load
        control.plans.load=lambda _:(_ for _ in ()).throw(OSError('isolated unavailable'))
        before=inventory(tmp_path)
        status,body=get()
        assert status==200 and 'SWING JOURNAL SOURCE UNAVAILABLE' in body
        assert 'NO CURRENT POSITIONS' not in body
        assert inventory(tmp_path)==before
        control.plans.load=original
    finally:
        server.shutdown();thread.join(2);server.server_close()


@pytest.mark.parametrize('family',list(McxFamily))
@pytest.mark.parametrize('failure',['plan_bytes','wrong_future','geometry'])
def test_changed_or_wrong_historical_sources_reject_without_repair(tmp_path,family,failure):
    control,position,instrument,plan=fixture(tmp_path,family)
    if failure=='plan_bytes':
        path=control.plans._path(plan)
        path.write_bytes(path.read_bytes().replace(plan.receipt_integrity_sha256.encode(),b'0'*64))
    elif failure=='geometry':
        values={k:getattr(position,k) for k in position.__dataclass_fields__ if k!='integrity_hash'}
        values['target']=position.target+Decimal('1')
        control.lifecycle.store.retain_position(seal(values))
        control.lifecycle=ActiveTradeLifecycleService(control.lifecycle.store)
        control.bound=McxContractBoundLifecycle(control.lifecycle,control.bound.bindings)
    else:
        alternate=replace(instrument,trading_symbol=family.value+'26NOVFUT')
        if alternate==instrument:
            alternate=replace(instrument,trading_symbol=family.value+'26DECFUT')
        other=LocalMcxHistoricalContractStore(tmp_path/'other-contract')
        McxContractBoundLifecycle(control.lifecycle,other).retain_existing(position.position_id,alternate)
        control.bound=McxContractBoundLifecycle(control.lifecycle,other)
    before=inventory(tmp_path)
    with pytest.raises(ValueError):
        mcx_journal_handoffs(control,START.date())
    assert inventory(tmp_path)==before


@pytest.mark.parametrize('family',list(McxFamily))
def test_retained_live_price_time_and_whole_lots_are_not_modelled_or_reentered(tmp_path,family):
    # This is a synthetic retained position, not a broker fill or admission proof.
    control,position,_,plan=fixture(tmp_path,family,live=True)
    before=inventory(tmp_path)
    row=mcx_journal_handoffs(control,START.date())[0]
    assert row.mode.value=='LIVE' and row.position_lots==3
    assert row.entry==Decimal('103.25') and row.entry!=plan.entry
    assert row.actual_entry_at==position.entry_timestamp
    assert row.instrument==plan.contract_symbol and row.exact_contract_expiry==plan.expiry
    html=render_trade_journal(_ready(),None,operational=(row,),
                             governed_trading_date=START.date(),selected_record_id=row.decision_identity)
    assert '103.25' in html and 'LIVE TRADES' in html and 'UNKNOWN' in html
    assert mcx_journal_handoffs(control,START.date())==(row,)
    assert inventory(tmp_path)==before


@pytest.mark.parametrize('family',list(McxFamily))
def test_cached_connected_cannot_certify_expired_capability_and_dismissal_is_presentation_only(tmp_path,family):
    from tests.unit.application.test_swing_ux10 import ux10
    from tests.unit.browser.test_browser_notification_centre import _centre, NOW
    from kronos.application.notifications import NotificationWorkspaceSnapshot
    control,position,instrument,plan=fixture(tmp_path,family,active=True)
    clock=[START]
    monitor,capability,hub=_wire_monitor(control.lifecycle,control.bound.bindings,instrument,clock)
    control.native_review._active_lifecycle_monitoring=monitor
    notifications=ux10(tmp_path/'notifications')
    centre=_centre(tmp_path/'centre',[NOW+timedelta(days=10)])
    try:
        monitor.attach(position.position_id,capability,instrument)
        clock[0]+=timedelta(minutes=1);capability.tick(102)
        event=notifications.observe_active_trade_monitoring_activation(position)
        card,=centre.synchronize(NotificationWorkspaceSnapshot(()),notifications.snapshot(),
                                current_run_identity=None,websocket_state='CONNECTED').records
        before=mcx_journal_handoffs(control,START.date())
        centre.dismiss(card.notification_identity,card.integrity_sha256)
        assert mcx_journal_handoffs(control,START.date())==before
        assert notifications.evidence(event.notification_id)['position_identity']==position.position_id
        assert hub.subscription_reference_count(instrument)==1
        capability.active=False
        row=mcx_journal_handoffs(control,START.date())[0]
        assert row.current_ltp is None and row.monitoring_state=='UNKNOWN'
        assert row.entry==Decimal('101') and row.sponsor_position_identity==position.position_id
    finally:
        monitor.close()
