from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kronos.application import live_monitoring_e2e as live
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
)


_NOW = datetime(2026, 8, 13, 9, 15, tzinfo=UTC)
_RELIANCE = InstrumentRecord(
    "KITE", "NSE", "NSE", "RELIANCE", "RELIANCE", "EQ", None
)
_OTHER = InstrumentRecord(
    "KITE", "NSE", "NSE", "TCS", "TCS", "EQ", None
)


class _InstrumentProvider:
    def __init__(self, capability) -> None:  # type: ignore[no-untyped-def]
        self.capability = capability

    def retrieve(self, exchange: str):  # type: ignore[no-untyped-def]
        assert exchange == "NSE"
        return (_RELIANCE,)

    def resolve_from_records(self, records, request):  # type: ignore[no-untyped-def]
        assert records == (_RELIANCE,)
        assert request.symbol == "RELIANCE"
        return _RELIANCE


class _Session:
    def __init__(self, consumer, mode: str) -> None:  # type: ignore[no-untyped-def]
        self.consumer = consumer
        self.mode = mode
        self.state = MonitoringConnectionState.DISCONNECTED
        self.subscribed = ()
        self.unsubscribed = ()
        self.disconnected = False

    def subscribe(self, instruments) -> None:  # type: ignore[no-untyped-def]
        self.subscribed = instruments

    def connect(self) -> None:
        if self.mode == "provider_failure":
            raise RuntimeError("PROVIDER_FAILURE")
        if self.mode == "secret_failure":
            raise RuntimeError("access_token=forbidden")
        self.state = MonitoringConnectionState.CONNECTED
        self.consumer.on_connection_state(self.state)
        if self.mode in {"tick", "wrong"}:
            instrument = _RELIANCE if self.mode == "tick" else _OTHER
            self.consumer.on_market_tick(
                ProviderMarketTick(
                    instrument,
                    Decimal("1400.50"),
                    _NOW,
                    _NOW,
                    "KITE_CONNECT_WEBSOCKET",
                    "CONNECTION-1",
                    1,
                    True,
                    True,
                    True,
                )
            )

    def unsubscribe(self, instruments) -> None:  # type: ignore[no-untyped-def]
        self.unsubscribed = instruments

    def disconnect(self) -> None:
        self.disconnected = True
        self.state = MonitoringConnectionState.DISCONNECTED


class _Capability:
    active = True

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.session = None

    def open_monitoring_session(self, consumer):  # type: ignore[no-untyped-def]
        self.session = _Session(consumer, self.mode)
        return self.session


@pytest.fixture(autouse=True)
def _provider(monkeypatch):
    monkeypatch.setattr(live, "KiteInstrumentProvider", _InstrumentProvider)


def test_one_real_tick_is_bound_admitted_and_safely_closed() -> None:
    capability = _Capability("tick")
    result = live.run_live_monitoring_e2e(
        capability,
        "RELIANCE",
        timeout_seconds=0.01,
        clock=lambda: _NOW,
    )

    assert result.state is live.LiveMonitoringTestState.PASS
    assert result.market_data_received is True
    assert result.domain_002_accepted is True
    assert result.instrument == "RELIANCE"
    assert result.observed_at == _NOW
    assert capability.session.subscribed == (_RELIANCE,)
    assert capability.session.unsubscribed == (_RELIANCE,)
    assert capability.session.disconnected is True
    for forbidden in (
        "place_order", "modify_order", "cancel_order", "access_token",
        "api_secret", "instrument_token", "raw_client",
    ):
        assert not hasattr(capability, forbidden)


def test_connected_without_genuine_data_remains_pending_and_closes() -> None:
    capability = _Capability("no_data")
    result = live.run_live_monitoring_e2e(
        capability,
        "RELIANCE",
        timeout_seconds=0.001,
        clock=lambda: _NOW,
    )
    assert result.state is live.LiveMonitoringTestState.CONNECTED_NO_DATA
    assert result.market_data_received is False
    assert result.domain_002_accepted is False
    assert result.safe_reason == "NO_LIVE_MARKET_DATA"
    assert capability.session.unsubscribed == (_RELIANCE,)
    assert capability.session.disconnected is True


def test_wrong_instrument_tick_fails_closed_and_is_not_admitted() -> None:
    result = live.run_live_monitoring_e2e(
        _Capability("wrong"),
        "RELIANCE",
        timeout_seconds=0.01,
        clock=lambda: _NOW,
    )
    assert result.state is live.LiveMonitoringTestState.FAIL
    assert result.safe_reason == "INSTRUMENT_BINDING_MISMATCH"
    assert result.domain_002_accepted is False


def test_provider_failure_is_sanitized_and_cleanup_remains_safe() -> None:
    result = live.run_live_monitoring_e2e(
        _Capability("provider_failure"),
        "RELIANCE",
        timeout_seconds=0.01,
        clock=lambda: _NOW,
    )
    assert result.state is live.LiveMonitoringTestState.FAIL
    assert result.safe_reason == "PROVIDER_FAILURE"
    assert "token" not in repr(result).lower()


def test_credential_bearing_provider_failure_is_replaced_not_retained() -> None:
    result = live.run_live_monitoring_e2e(
        _Capability("secret_failure"),
        "RELIANCE",
        timeout_seconds=0.01,
        clock=lambda: _NOW,
    )
    assert result.safe_reason == "LIVE_MONITORING_FAILED"
    assert "access_token" not in repr(result)


def test_disconnected_and_invalid_instruments_fail_without_provider_contact() -> None:
    disconnected = _Capability("tick")
    disconnected.active = False
    result = live.run_live_monitoring_e2e(
        disconnected,
        "RELIANCE",
        timeout_seconds=0.01,
        clock=lambda: _NOW,
    )
    assert result.safe_reason == "KITE_DISCONNECTED"
    assert disconnected.session is None
    with pytest.raises(ValueError, match="GOVERNED_INSTRUMENT_INVALID"):
        live.run_live_monitoring_e2e(
            _Capability("tick"),
            "NOT-GOVERNED",
            timeout_seconds=0.01,
            clock=lambda: _NOW,
        )


def test_result_contract_requires_real_data_and_domain_002_for_pass() -> None:
    with pytest.raises(ValueError, match="LIVE_MONITORING_RESULT_INVALID"):
        live.LiveMonitoringTestResult(
            live.LiveMonitoringTestState.PASS,
            "RELIANCE",
            market_data_received=True,
            domain_002_accepted=False,
            observed_at=_NOW,
        )


def test_proof_module_has_no_lifecycle_or_broker_authority() -> None:
    for forbidden in (
        "evaluate_entry_timing",
        "evaluate_objective_model",
        "publish_lifecycle_event",
        "record_sponsor_decision",
        "place_order",
        "modify_order",
        "cancel_order",
    ):
        assert not hasattr(live, forbidden)
