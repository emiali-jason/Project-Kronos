from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    MonitoringError,
    MonitoringFailure,
    ProviderMarketTick,
    RecoveredMarketInterval,
)
from kronos.provider.adapters.kite.monitoring import KiteReadOnlyMonitoringSession


_NOW = datetime.fromisoformat("2026-08-13T12:00:00+05:30")
_NSE = InstrumentRecord("KITE", "NSE", "NSE", "RELIANCE", "RELIANCE", "EQ", None)
_MCX = InstrumentRecord("KITE", "MCX", "MCX-FUT", "GOLDM26AUGFUT", "GOLDM", "FUT", datetime(2026, 8, 28).date())
_REFERENCE = InstrumentRecord("KITE", "COMEX", "COMEX-FUT", "GCZ26", "GOLD", "FUT", datetime(2026, 12, 28).date())


class _Socket:
    MODE_FULL = "full"

    def __init__(self) -> None:
        self.on_connect = None
        self.on_ticks = None
        self.on_order_update = None
        self.on_close = None
        self.on_error = None
        self.on_reconnect = None
        self.on_noreconnect = None
        self.subscribed: list[list[int]] = []
        self.unsubscribed: list[list[int]] = []
        self.modes: list[tuple[str, list[int]]] = []
        self.closed = False

    def connect(self, *, threaded: bool) -> None:
        assert threaded is True
        self.on_connect(self, {})

    def subscribe(self, tokens: list[int]) -> None:
        self.subscribed.append(tokens)

    def unsubscribe(self, tokens: list[int]) -> None:
        self.unsubscribed.append(tokens)

    def set_mode(self, mode: str, tokens: list[int]) -> None:
        self.modes.append((mode, tokens))

    def close(self) -> None:
        self.closed = True


class _Consumer:
    def __init__(self) -> None:
        self.ticks = []
        self.orders = []
        self.states = []

    def on_market_tick(self, tick) -> None:  # type: ignore[no-untyped-def]
        self.ticks.append(tick)

    def on_order_update(self, update) -> None:  # type: ignore[no-untyped-def]
        self.orders.append(update)

    def on_connection_state(self, state) -> None:  # type: ignore[no-untyped-def]
        self.states.append(state)


def _session(records=(_NSE, _MCX)):  # type: ignore[no-untyped-def]
    socket = _Socket()
    consumer = _Consumer()
    tokens = {_NSE: 101, _MCX: 202}
    session = KiteReadOnlyMonitoringSession(
        api_key="non-secret-api-key",
        access_token="protected-session-token",
        token_resolver=tokens.get,
        consumer=consumer,
        clock=lambda: _NOW + timedelta(minutes=10),
        socket_factory=lambda _api_key, _access_token: socket,
    )
    session.subscribe(records)
    return session, socket, consumer


def _tick(token: int, price: float, minute: int = 1):
    return {
        "instrument_token": token,
        "last_price": price,
        "timestamp": (_NOW + timedelta(minutes=minute)).replace(tzinfo=None),
    }


def test_market_connection_subscription_nse_and_mcx_binding() -> None:
    session, socket, consumer = _session()
    session.connect()
    socket.on_ticks(socket, [_tick(101, 1400.5), _tick(202, 73500.0)])

    assert session.state is MonitoringConnectionState.CONNECTED
    assert socket.subscribed == [[101, 202]]
    assert socket.modes == [("full", [101, 202])]
    assert [item.instrument for item in consumer.ticks] == [_NSE, _MCX]
    assert all(item.source == "KITE_CONNECT_WEBSOCKET" for item in consumer.ticks)
    assert all(not hasattr(item, "instrument_token") for item in consumer.ticks)


def test_subscription_lifecycle_unsubscribes_stale_and_closed_responsibilities() -> None:
    session, socket, _consumer = _session()
    session.connect()
    session.unsubscribe((_NSE,))
    session.unsubscribe((_MCX,))

    assert session.subscriptions == ()
    assert socket.unsubscribed == [[101], [202]]


def test_wrong_or_reference_instrument_is_rejected() -> None:
    session, socket, _consumer = _session((_NSE,))
    session.connect()
    with pytest.raises(MonitoringError) as wrong_token:
        socket.on_ticks(socket, [_tick(999, 1.0)])
    with pytest.raises(MonitoringError) as reference:
        session.subscribe((_REFERENCE,))
    assert wrong_token.value.failure is MonitoringFailure.INSTRUMENT_BINDING_MISMATCH
    assert reference.value.failure is MonitoringFailure.INSTRUMENT_NOT_RESOLVED


def test_disconnect_reconnect_first_tick_preserves_gap_and_requires_reconciliation() -> None:
    session, socket, consumer = _session((_NSE,))
    session.connect()
    socket.on_ticks(socket, [_tick(101, 1399.0)])
    socket.on_close(socket, 1006, "sanitized")
    assert session.state is MonitoringConnectionState.RECONNECTING
    assert session.last_disconnect is not None
    assert session.last_disconnect.affected_instruments == (_NSE,)

    socket.on_connect(socket, {})
    socket.on_ticks(socket, [_tick(101, 1405.0, 5)])
    first = consumer.ticks[-1]
    assert session.state is MonitoringConnectionState.CONTEXT_INCOMPLETE
    assert session.last_disconnect.reconnected_at == _NOW + timedelta(minutes=10)
    assert session.last_disconnect.first_post_reconnect_observation_at == first.observed_at
    assert first.previous_interval_available is False
    assert first.session_continuous is False
    assert first.ordering_deterministic is False


def test_observation_context_requires_applied_subscription_and_new_connection():
    session, socket, consumer = _session((_MCX,))
    assert session.observation_context(_MCX) is None
    session.connect()
    initial = session.observation_context(_MCX)
    assert initial.instrument == _MCX
    assert initial.state is MonitoringConnectionState.CONNECTED
    socket.on_close(socket, 1006, "fixture")
    assert session.observation_context(_MCX) is None
    socket.on_connect(socket, {})
    recovered = session.observation_context(_MCX)
    assert recovered.connection_id != initial.connection_id
    assert recovered.state is MonitoringConnectionState.CONTEXT_INCOMPLETE
    assert session.observation_context(_NSE) is None
    assert socket.subscribed == [[202], [202]]
    socket.on_noreconnect(socket)
    assert session.observation_context(_MCX) is None
    assert consumer.states[-1] is MonitoringConnectionState.CONTEXT_INCOMPLETE


def test_failed_resubscription_cannot_certify_observation_context():
    session, socket, _ = _session((_MCX,))
    session.connect()
    socket.on_close(socket, 1006, "fixture")
    def failed_mode(*_args):
        raise RuntimeError("isolated subscription failure")
    socket.set_mode = failed_mode
    with pytest.raises(MonitoringError):
        socket.on_connect(socket, {})
    assert session.state is MonitoringConnectionState.CONTEXT_INCOMPLETE
    assert session.observation_context(_MCX) is None


def test_interrupted_subscription_completion_cannot_restore_stale_proof():
    from threading import Event, Thread
    session, socket, _ = _session((_MCX,))
    session.connect()
    socket.on_close(socket, 1006, "fixture")
    entered, release = Event(), Event()
    errors = []
    def paused_mode(*_args):
        entered.set()
        assert release.wait(2)
    socket.set_mode = paused_mode
    def reconnect():
        try:
            socket.on_connect(socket, {})
        except BaseException as error:
            errors.append(error)
    thread = Thread(target=reconnect)
    thread.start()
    try:
        assert entered.wait(2)
        assert session.observation_context(_MCX) is None
        socket.on_close(socket, 1006, "second interruption")
    finally:
        release.set()
        thread.join(2)
    assert not thread.is_alive() and not errors
    assert session.state is MonitoringConnectionState.RECONNECTING
    assert session.observation_context(_MCX) is None


def test_authoritative_recovery_clears_gap_and_irrecoverable_interval_fails_closed() -> None:
    session, socket, consumer = _session((_NSE,))
    session.connect()
    socket.on_close(socket, 1006, "sanitized")
    socket.on_connect(socket, {})
    recovered_tick = ProviderMarketTick(
        _NSE,
        Decimal("1401"),
        _NOW + timedelta(minutes=2),
        _NOW + timedelta(minutes=3),
        "KITE_CONNECT_WEBSOCKET",
        "RECOVERY-1",
        1,
        True,
        True,
        True,
        True,
    )
    interval = RecoveredMarketInterval(
        _NSE,
        _NOW + timedelta(minutes=1),
        _NOW + timedelta(minutes=4),
        (recovered_tick,),
        "KITE_HISTORICAL_PROVIDER",
        "minute",
        True,
    )
    session.recover_interval(interval)
    assert session.state is MonitoringConnectionState.CONNECTED
    assert consumer.ticks[-1] is recovered_tick

    socket.on_close(socket, 1006, "sanitized")
    socket.on_connect(socket, {})
    with pytest.raises(MonitoringError) as error:
        session.recover_interval(
            RecoveredMarketInterval(
                _NSE,
                interval.started_at,
                interval.ended_at,
                interval.observations,
                interval.source,
                interval.granularity,
                False,
            )
        )
    assert error.value.failure is MonitoringFailure.RECONCILIATION_REQUIRED
    assert session.state is MonitoringConnectionState.CONTEXT_INCOMPLETE


def test_order_update_is_normalized_as_separate_factual_evidence() -> None:
    session, socket, consumer = _session((_NSE,))
    session.connect()
    socket.on_order_update(
        socket,
        {
            "order_id": "ORDER-1",
            "exchange": "NSE",
            "tradingsymbol": "RELIANCE",
            "status": "COMPLETE",
            "transaction_type": "BUY",
            "filled_quantity": 2,
            "average_price": 1401.25,
            "exchange_timestamp": (_NOW + timedelta(minutes=1)).replace(tzinfo=None),
        },
    )
    evidence = consumer.orders[0]
    assert evidence.instrument is _NSE
    assert evidence.filled_quantity == Decimal("2")
    assert evidence.average_price == Decimal("1401.25")
    assert not hasattr(evidence, "model_trade_state")


def test_restart_restores_only_explicit_active_subscriptions() -> None:
    first, _, _ = _session((_NSE,))
    active = first.subscriptions
    restarted, socket, _ = _session(active)
    restarted.connect()
    assert restarted.subscriptions == (_NSE,)
    assert socket.subscribed == [[101]]


def test_monitoring_session_exposes_no_broker_or_secret_capability() -> None:
    session, _socket, _consumer = _session((_NSE,))
    for name in (
        "place_order",
        "modify_order",
        "cancel_order",
        "access_token",
        "api_secret",
        "instrument_token",
        "raw_client",
        "webhook",
        "pine",
    ):
        assert not hasattr(session, name)
    assert repr(session) == "<KiteReadOnlyMonitoringSession redacted>"


def test_local_provider_e2e_reaches_domain_002_and_kr380_without_pine_or_webhook() -> None:
    from kronos.swing.v1.step32 import (
        EntryOutcomeState,
        MonitoringAdmissionContext,
        MonitoringAdmissionRegistry,
        MonitoringSubmissionType,
        build_monitoring_submission,
        evaluate_entry_timing,
    )
    from tests.unit.swing.v1.test_step32_lifecycle import (
        _BOUNDARY,
        _candidate,
        _lifecycle,
        _risk,
    )

    candidate = _candidate()
    risk = _risk(candidate)
    lifecycle = _lifecycle(candidate, risk)
    session, socket, consumer = _session((_NSE,))
    session.connect()
    socket.on_ticks(socket, [_tick(101, 99.0, 1), _tick(101, 100.05, 2)])
    registry = MonitoringAdmissionRegistry()
    context = MonitoringAdmissionContext(
        candidate.candidate_id,
        lifecycle.monitoring_binding_id,
        None,
        candidate.canonical_instrument,
        "NSE:RELIANCE",
        candidate.product,
        candidate.direction,
        "KITE_CONNECT_WEBSOCKET",
        consumer.ticks[0].connection_id,
        True,
        _BOUNDARY,
        "DAILY",
        "NSE-20260813",
    )
    observations = []
    for index, tick in enumerate(consumer.ticks, start=1):
        submission = build_monitoring_submission(
            tick,
            submission_id=f"LOCAL-E2E-{index}",
            candidate_id=candidate.candidate_id,
            monitoring_binding_id=lifecycle.monitoring_binding_id,
            model_trade_id=None,
            product=candidate.product,
            direction=candidate.direction,
            submission_type=MonitoringSubmissionType.ENTRY_LEVEL_CROSSED,
            reference="ENTRY-REFERENCE",
            boundary=_BOUNDARY,
            timeframe="DAILY",
            session_identity="NSE-20260813",
        )
        observations.append(registry.admit(submission, context))

    outcome = evaluate_entry_timing(
        candidate,
        risk,
        lifecycle,
        observations[0],
        observations[1],
    )
    assert outcome.state is EntryOutcomeState.ENTRY_TRIGGERED
    assert all(item.provenance[-1] == "DOMAIN-002" for item in observations)


def test_applied_subscription_evidence_exposes_actual_token_without_changing_tick_contract():
    session, socket, consumer = _session()
    session.connect()
    assert session.observation_context(_NSE).provider_instrument_token == 101
    assert session.observation_context(_MCX).provider_instrument_token == 202
    socket.on_ticks(socket, [_tick(101, 1400.5)])
    assert not hasattr(consumer.ticks[0], 'instrument_token')
    session.unsubscribe((_MCX,))
    assert session.observation_context(_MCX) is None


@pytest.mark.parametrize('token', [0, -1, True, '202'])
def test_optional_subscription_token_rejects_invalid_values_and_preserves_legacy_constructor(token):
    from kronos.provider.contracts.monitoring import MonitoringSubscriptionEvidence
    legacy = MonitoringSubscriptionEvidence(_NSE, 'connection', _NOW,
                                            MonitoringConnectionState.CONNECTED)
    assert legacy.provider_instrument_token is None
    with pytest.raises(ValueError, match='MONITORING_SUBSCRIPTION_EVIDENCE_INVALID'):
        MonitoringSubscriptionEvidence(_MCX, 'connection', _NOW,
            MonitoringConnectionState.CONNECTED, token)
