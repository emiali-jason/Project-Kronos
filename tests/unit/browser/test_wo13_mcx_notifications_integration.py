"""Notifications R3 over deployed MCX owners, with isolated stores/transport."""
from dataclasses import replace
from datetime import timedelta
from threading import Thread

import pytest

from kronos.application.notifications import NotificationWorkspaceSnapshot
from kronos.application.swing_notifications import monitoring_indicator
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecycleState, ActiveTradeLifecycleService, LocalActiveTradeLifecycleStore,
)
from kronos.swing.v1.mcx_contract_lifecycle import (
    McxContractBoundLifecycle, LocalMcxHistoricalContractStore,
)
from tests.unit.application.test_swing_mcx_v1_composition import compose, inventory
from tests.unit.application.test_swing_ux10 import ux10, Telegram
from tests.unit.browser.test_browser_notification_centre import _centre, NOW
from tests.unit.browser.test_browser_server import _request
from tests.unit.swing.v1.test_mcx_contract_lifecycle import (
    _fixture, _wire_monitor, START, FAMILY_CONTRACTS,
)


@pytest.mark.parametrize('family,symbol,next_symbol', FAMILY_CONTRACTS,
    ids=[item[0].value for item in FAMILY_CONTRACTS])
@pytest.mark.parametrize('restart', [False, True])
def test_notification_dismissal_and_recovery_preserve_exact_mcx_position(
    tmp_path, restart, monkeypatch, family, symbol, next_symbol,
):
    position, instrument, schedule, bound, root, binding_root = _fixture(
        tmp_path / 'position', family, symbol, v1=True, active_v1=True)
    clock = [START]
    monitor, capability, hub = _wire_monitor(bound.service, bound.bindings, instrument, clock)
    service = ux10(tmp_path / 'notifications')
    centre = _centre(tmp_path / 'centre', [NOW + timedelta(days=10)])
    monitor.attach(position.position_id, capability, instrument)
    retired_consumer = monitor._consumers[position.position_id]
    try:
        event = service.observe_active_trade_monitoring_activation(position)
        card, = centre.synchronize(NotificationWorkspaceSnapshot(()), service.snapshot(),
            current_run_identity=None, websocket_state='CONNECTED').records
        assert service.evidence(event.notification_id)['position_identity'] == position.position_id
        assert service.evidence(event.notification_id)['plan_identity'] == position.trade_plan_id
        assert card.source_identity == event.notification_id
        assert monitoring_indicator(monitor.notification_monitoring_evidence(position.position_id)) == 'UNAVAILABLE'
        clock[0] += timedelta(minutes=1)
        capability.tick(102)
        retained_tick, _ = monitor.latest_mcx_observation(position.position_id)
        before = inventory(tmp_path)
        evidence = monitor.notification_monitoring_evidence(position.position_id)
        assert evidence['observation']['connection_id'] == retained_tick.connection_id
        assert inventory(tmp_path) == before
        centre.dismiss(card.notification_identity, card.integrity_sha256)
        assert hub.subscription_reference_count(instrument) == 1
        assert monitor.active_position_ids == (position.position_id,)
        clock[0] += timedelta(minutes=1)
        capability.socket.on_close(capability.socket, 1006, 'isolated outage')
        clock[0] += timedelta(minutes=1)
        capability.socket.on_connect(capability.socket, {})
        assert monitoring_indicator(monitor.notification_monitoring_evidence(position.position_id)) == 'INTERRUPTED'
        assert monitor.notification_monitoring_evidence(position.position_id)['observation'] is None
        before = inventory(tmp_path)
        retired_consumer.on_market_tick(retained_tick)
        assert inventory(tmp_path) == before
        assert monitor.notification_monitoring_evidence(position.position_id)['observation'] is None
        if restart:
            monitor.close()
            bound = McxContractBoundLifecycle(
                ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root)),
                LocalMcxHistoricalContractStore(binding_root))
            monitor, capability, hub = _wire_monitor(bound.service, bound.bindings, instrument, clock)
            assert monitor.restore(capability, lambda _: pytest.fail('family-level rebind')) == (position.position_id,)
            service = ux10(tmp_path / 'notifications')
            assert service.observe_active_trade_monitoring_activation(position) is None
        clock[0] += timedelta(minutes=1)
        capability.tick(103)
        current = bound.service._require(position.position_id)
        assert current.state is ActiveLifecycleState.PAPER_ACTIVE
        assert (current.actual_entry, current.entry_timestamp, current.mcx_activation_outcome_sha256) == (
            position.actual_entry, position.entry_timestamp, position.mcx_activation_outcome_sha256)
        tick, _ = monitor.latest_mcx_observation(position.position_id)
        assert tick.instrument == instrument and tick.connection_id != retained_tick.connection_id
        projected = monitor.notification_monitoring_evidence(position.position_id)
        assert projected['observation']['connection_id'] == tick.connection_id
        consumer = monitor._consumers[position.position_id]
        with monkeypatch.context() as patch:
            patch.setattr(consumer, '_current_subscription', lambda: None)
            assert monitor.latest_mcx_observation(position.position_id) is None
            assert monitor.notification_monitoring_evidence(position.position_id)['observation'] is None
        # Notification projection is not a claim that Kite supplies trade-level continuity.
        if not tick.session_continuous or not tick.previous_interval_available:
            assert monitoring_indicator(projected) == 'INTERRUPTED'
        with pytest.raises(ValueError, match='INSTRUMENT_BINDING_MISMATCH'):
            monitor._consumers[position.position_id].on_market_tick(replace(
                tick, instrument=replace(instrument, trading_symbol=next_symbol)))
        assert monitor.notification_monitoring_evidence(position.position_id) == projected
        assert centre.synchronize(NotificationWorkspaceSnapshot(()), service.snapshot(),
            current_run_identity=None, websocket_state='CONNECTED').visible == ()
        closure = bound.manual_paper_exit_at_cmp(position.position_id, tick, schedule)
        assert closure.actual_exit == tick.last_price
        assert closure.mcx_v1_contract_symbol == instrument.trading_symbol
        assert tick.connection_id in closure.event_provenance
        assert monitoring_indicator(monitor.notification_monitoring_evidence(position.position_id)) == 'NOT_REQUIRED'
    finally:
        monitor.close()


def test_canonical_mcx_and_notification_gets_preserve_fenced_owners(tmp_path, monkeypatch):
    server, _, _ = compose(tmp_path)
    server.service_actions = lambda: None
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.mcx_v1_control is server.mcx_v1_composition.control
        before = inventory(tmp_path)
        for route in ('/swing/mcx-v1', '/notifications/swing', '/notifications/status',
                      '/notifications/intraday'):
            status, _, _ = _request(server, 'GET', route)
            assert status == 200
        assert inventory(tmp_path) == before
        assert server.maintenance_admission.snapshot()['owners'] == {}
        generation = 'f' * 64
        assert server.maintenance_admission.claim(generation)
        server.service_actions = type(server).service_actions.__get__(server)
        monkeypatch.setattr(server, '_synchronize_swing_notifications_owned',
            lambda: pytest.fail('fenced server pulse admitted notification writes'))
        server.service_actions()
        assert inventory(tmp_path) == before
        assert server.maintenance_admission.snapshot()['owners'] == {}
        assert server.mcx_v1_control.worker_status()['pending'] == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        assert not thread.is_alive()


def test_native_review_monitoring_projection_delegates_exact_position_only(tmp_path):
    server, _, _ = compose(tmp_path)
    try:
        calls = []
        monitor = server.native_review._active_lifecycle_monitoring
        original = monitor.notification_monitoring_evidence
        monitor.notification_monitoring_evidence = lambda identity: calls.append(identity) or original(identity)
        before = inventory(tmp_path)
        assert server.native_review.notification_monitoring_evidence('absent-position') is None
        assert calls == ['absent-position']
        assert inventory(tmp_path) == before
        assert server.mcx_v1_control.workflow is None
    finally:
        server.server_close()


@pytest.mark.parametrize('family,symbol,_next_symbol', FAMILY_CONTRACTS,
    ids=[item[0].value for item in FAMILY_CONTRACTS])
@pytest.mark.parametrize('price,kind', [(88, 'STOP_LEVEL_TOUCHED'), (122, 'TARGET_LEVEL_TOUCHED')])
@pytest.mark.parametrize('delivery', ['SENT', 'DELIVERY_UNCERTAIN', 'DISCONNECTED'])
def test_each_mcx_family_admitted_lifecycle_navigation_and_delivery(
    tmp_path, family, symbol, _next_symbol, price, kind, delivery,
):
    """Real retained lifecycle events; mock transport never proves live acceptance."""
    from kronos.application.swing_native_review import NativeReviewWorkflow
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
    from kronos.browser.server import create_browser_server
    from kronos.integrations.telegram import TelegramDeliveryResult, TelegramDeliveryState
    from kronos.swing.v1.native_review import NativeReviewEvidenceStore
    from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
    from tests.unit.application.test_swing_opportunities import _Provider, _ready

    position, instrument, _, bound, root, bindings = _fixture(
        tmp_path / 'position', family, symbol, v1=True, active_v1=True)
    clock = [START]
    monitor, capability, _ = _wire_monitor(bound.service, bound.bindings, instrument, clock)
    telegram = Telegram(enabled=delivery != 'DISCONNECTED')
    service = ux10(tmp_path / 'notifications', telegram)
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / 'review'),
        active_lifecycle_service=bound.service, active_lifecycle_monitoring=monitor,
        mcx_historical_contract_store=bound.bindings)
    server = create_browser_server(SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready()),
        port=0, native_review=native, ux10_notifications=service,
        notification_centre=_centre(tmp_path / 'centre', [NOW + timedelta(days=10)]),
        v1_review=SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path / 'charts')))
    server.service_actions = lambda: None
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        native.attach_lifecycle_monitoring(position.position_id, capability, instrument)
        activation = service.observe_active_trade_monitoring_activation(position)
        assert activation.instrument == family.value
        server.synchronize_swing_notifications()
        active_card, = server.swing_notification_status().records
        assert server.swing_notification_indicators(server.swing_notification_status())[
            active_card.notification_identity] == 'UNAVAILABLE'
        clock[0] += timedelta(minutes=1)
        capability.tick(102)
        observation = monitor.notification_monitoring_evidence(position.position_id)['observation']
        assert observation and observation['connection_id']

        # Exercise the actual shared owner's callbacks, not a fabricated per-family incident.
        clock[0] += timedelta(minutes=1)
        capability.socket.on_close(capability.socket, 1006, 'isolated outage')
        clock[0] += timedelta(minutes=1)
        capability.socket.on_connect(capability.socket, {})
        assert monitor.notification_monitoring_evidence(position.position_id)['observation'] is None
        incidents = [r for r in service.snapshot().records if r.family.value == 'SYSTEM_CONNECTIVITY']
        assert incidents and {r.instrument for r in incidents} == {'SWING MONITORING'}
        assert {service.evidence(r.notification_id)['owner_identity'] for r in incidents} == {
            'SHARED-SWING-MONITORING'}
        clock[0] += timedelta(minutes=1)
        capability.tick(103)
        assert bound.service._require(position.position_id).state is ActiveLifecycleState.PAPER_ACTIVE

        if delivery == 'DELIVERY_UNCERTAIN':
            telegram.results.append(TelegramDeliveryResult(
                TelegramDeliveryState.FAILED_RETRYABLE, 'TELEGRAM_TRANSPORT_UNAVAILABLE'))
        clock[0] += timedelta(minutes=1)
        capability.tick(price)
        touch, = [r for r in service.snapshot().records if r.notification_type.value == kind]
        source = service.evidence(touch.notification_id)
        lifecycle_event, = [e for e in bound.service.snapshot().events if e.event_id == touch.source_event_identity]
        assert source['position_identity'] == position.position_id
        assert source['plan_identity'] == position.trade_plan_id
        assert source['source_integrity'] == lifecycle_event.integrity_hash
        assert touch.instrument == family.value and touch.browser_delivery_state.value == 'SENT'
        assert touch.telegram_delivery_state.value == (
            'PENDING' if delivery == 'DISCONNECTED' else delivery)
        assert 'NOT A FILL' in touch.action
        # Identity is resolved through the retained position and exact historical future.
        assert bound.bindings.load(source['position_identity']).instrument == instrument
        assert bound.service._require(position.position_id).mcx_v1_contract_symbol == symbol
        server.synchronize_swing_notifications()
        before = inventory(tmp_path)
        route = '/notifications/swing/evidence/UX10_EVENT/' + touch.notification_id
        status, _, html = _request(server, 'GET', route)
        assert status == 200
        assert touch.source_event_identity in html and position.position_id in html
        assert position.trade_plan_id in html and family.value in html
        missing = _request(server, 'GET', '/notifications/swing/evidence/UX10_EVENT/' + 'f' * 64)[2]
        assert 'UPSTREAM EVIDENCE UNAVAILABLE' in missing
        assert inventory(tmp_path) == before
        restored = ux10(tmp_path / 'notifications', telegram)
        count = len(telegram.messages)
        assert restored.observe_lifecycle_event(lifecycle_event) is None
        restored.retry_pending()
        assert len(telegram.messages) == count  # SENT/uncertain never resend; disconnected never sends.
        retained = next(r for r in restored.snapshot().records if r.notification_id == touch.notification_id)
        assert retained == touch
        assert bound.service._require(position.position_id).state is ActiveLifecycleState.CLOSED
        assert monitoring_indicator(monitor.notification_monitoring_evidence(position.position_id)) == 'NOT_REQUIRED'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        assert not thread.is_alive()


@pytest.mark.parametrize('family,_symbol,_next_symbol', FAMILY_CONTRACTS,
    ids=[item[0].value for item in FAMILY_CONTRACTS])
@pytest.mark.parametrize('direction', ['LONG', 'SHORT'])
def test_each_mcx_family_native_v2_progression_preserves_receipt_and_replay(
    tmp_path, family, _symbol, _next_symbol, direction,
):
    from kronos.swing.v1.analytical_promotion_v2 import create_record, _validate_mcx
    from kronos.swing.v1.native_review import MCX_REFERENCE_MAPPINGS
    from tests.unit.swing.v1.test_analytical_promotion_v2 import source, criteria, mcx

    selected = source(market='MCX', instrument=family.value, direction=direction)
    confirmation = mcx()
    reference_name, market, symbol = MCX_REFERENCE_MAPPINGS[family.value]
    market = market.value  # Closed wire schema requires a plain string, not an enum.
    confirmation['mcx_binding']['payload']['registered_mapping'] = dict(
        native_family=family.value, reference_name=reference_name,
        reference_market=market, reference_symbol=symbol)
    for visual in selected['acceptance']['visual_bindings']:
        if visual['role'] == 'SUPPORTING_REFERENCE':
            visual['reference_market'] = market
            visual['reference_symbol'] = symbol
    state, reasons = _validate_mcx(confirmation['mcx_binding'], selected)
    confirmation.update(state=state, reason_codes=reasons)
    ready = create_record(source=selected, criteria=criteria(4),
        confirmation=confirmation, created_at=NOW)
    now = create_record(source=selected, criteria=criteria(5),
        confirmation=confirmation, created_at=NOW + timedelta(seconds=1))
    assert [r['role'] for r in now.value['source']['acceptance']['request_bindings']] == [
        'NATIVE_MCX', 'SUPPORTING_REFERENCE']
    telegram = Telegram()
    service = ux10(tmp_path, telegram)
    assert service.observe_promotions((ready,)) == ()
    service = ux10(tmp_path, telegram)
    event, = service.observe_promotions((now,))
    assert event.notification_type.value == 'ANALYTICAL_NOW_CONFIRMED'
    assert event.instrument == family.value and event.direction == direction
    assert event.source_event_identity == now.value['integrity_sha256']
    evidence = service.evidence(event.notification_id)
    assert evidence['predecessor_identity'] == ready.value['integrity_sha256']
    assert evidence['assessment_identity'] == selected['native_assessment_sha256']
    assert evidence['run_identity'] == selected['native_run_identity']
    assert 'NO ENTRY OR EXECUTION AUTHORITY' in event.action
    assert len(telegram.messages) == 1
    restored = ux10(tmp_path, telegram)
    before = inventory(tmp_path)
    assert restored.observe_promotions((ready, now)) == ()
    assert inventory(tmp_path) == before and len(telegram.messages) == 1
