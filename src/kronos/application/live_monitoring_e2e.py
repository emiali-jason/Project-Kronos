"""Bounded Sponsor-triggered proof of the factual Kite monitoring path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from collections.abc import Callable
from enum import StrEnum
import re
from threading import Event

from kronos.provider.contracts.instrument import (
    InstrumentKind,
    InstrumentRecord,
    InstrumentResolutionRequest,
)
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
    ProviderOrderUpdateEvidence,
)
from kronos.provider.kite.instruments.kite_instrument_provider import (
    KiteInstrumentProvider,
)
from kronos.swing.universe import (
    SwingUniverseAssetClass,
    SwingUniverseMember,
    enabled_swing_phase1_universe,
)
class LiveMonitoringTestState(StrEnum):
    NOT_TESTED = "NOT TESTED"
    TESTING = "TESTING"
    PASS = "PASS"
    FAIL = "FAIL"
    CONNECTED_NO_DATA = "CONNECTED — NO LIVE MARKET DATA"


@dataclass(frozen=True, slots=True)
class LiveMonitoringTestResult:
    state: LiveMonitoringTestState
    instrument: str | None = None
    provider: str = "KITE"
    market_data_received: bool = False
    domain_002_accepted: bool = False
    observed_at: datetime | None = None
    safe_reason: str = ""

    def __post_init__(self) -> None:
        if (
            type(self.state) is not LiveMonitoringTestState
            or (
                self.instrument is not None
                and re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.instrument) is None
            )
            or self.provider != "KITE"
            or type(self.market_data_received) is not bool
            or type(self.domain_002_accepted) is not bool
            or (
                self.observed_at is not None
                and (
                    self.observed_at.tzinfo is None
                    or self.observed_at.utcoffset() is None
                )
            )
            or (self.safe_reason and re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", self.safe_reason) is None)
            or (self.state is LiveMonitoringTestState.PASS)
            != (self.market_data_received and self.domain_002_accepted)
        ):
            raise ValueError("LIVE_MONITORING_RESULT_INVALID")


def governed_live_monitoring_instruments() -> tuple[str, ...]:
    return tuple(item.canonical_identity for item in enabled_swing_phase1_universe())


def run_live_monitoring_e2e(
    capability: object,
    canonical_instrument: str,
    *,
    timeout_seconds: float = 15.0,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> LiveMonitoringTestResult:
    """Wait for one genuine tick, prove DOMAIN-002 admission, then clean up."""

    member = _member(canonical_instrument)
    if getattr(capability, "active", False) is not True:
        return _failure(canonical_instrument, "KITE_DISCONNECTED")
    if type(timeout_seconds) is not float or not 0.0 < timeout_seconds <= 60.0:
        raise ValueError("LIVE_MONITORING_TIMEOUT_INVALID")
    instrument = _resolve(capability, member, clock().date())
    consumer = _ProofConsumer(member, instrument, clock)
    session = None
    cleanup_failed = False
    try:
        session = capability.open_monitoring_session(consumer)
        session.subscribe((instrument,))
        session.connect()
        received = consumer.completed.wait(timeout_seconds)
        if not received:
            if session.state in {
                MonitoringConnectionState.CONNECTED,
                MonitoringConnectionState.CONTEXT_INCOMPLETE,
                MonitoringConnectionState.RECONNECTING,
            }:
                result = LiveMonitoringTestResult(
                    LiveMonitoringTestState.CONNECTED_NO_DATA,
                    canonical_instrument,
                    safe_reason="NO_LIVE_MARKET_DATA",
                )
            else:
                result = _failure(canonical_instrument, "WEBSOCKET_NOT_CONNECTED")
        elif session.state not in {
            MonitoringConnectionState.CONNECTED,
            MonitoringConnectionState.CONTEXT_INCOMPLETE,
        }:
            result = _failure(canonical_instrument, "WEBSOCKET_NOT_CONNECTED")
        elif consumer.failure:
            result = _failure(canonical_instrument, consumer.failure)
        else:
            observation = consumer.observation
            if observation is None:
                result = _failure(canonical_instrument, "DOMAIN_002_NOT_ACCEPTED")
            else:
                result = LiveMonitoringTestResult(
                    LiveMonitoringTestState.PASS,
                    canonical_instrument,
                    market_data_received=True,
                    domain_002_accepted=True,
                    observed_at=observation.observed_at,
                )
    except Exception as error:
        result = _failure(canonical_instrument, _safe_failure(error))
    finally:
        if session is not None:
            try:
                session.unsubscribe((instrument,))
                session.disconnect()
            except Exception:
                cleanup_failed = True
    return _failure(canonical_instrument, "MONITORING_CLEANUP_FAILED") if cleanup_failed else result


class _ProofConsumer:
    def __init__(
        self,
        member: SwingUniverseMember,
        instrument: InstrumentRecord,
        clock: Callable[[], datetime],
    ) -> None:
        self.member = member
        self.instrument = instrument
        self.clock = clock
        self.completed = Event()
        self.observation: object | None = None
        self.failure = ""
        from kronos.swing.v1.step32 import MonitoringAdmissionRegistry

        self.registry = MonitoringAdmissionRegistry()

    def on_market_tick(self, tick: ProviderMarketTick) -> None:
        from kronos.swing.v1.step32 import (
            MonitoringAdmissionContext,
            MonitoringSubmissionType,
            build_monitoring_submission,
        )

        try:
            if type(tick) is not ProviderMarketTick or tick.instrument != self.instrument:
                raise ValueError("INSTRUMENT_BINDING_MISMATCH")
            binding = f"LIVE-E2E-{self.member.canonical_identity}"
            submission = build_monitoring_submission(
                tick,
                submission_id=f"{binding}-{tick.observed_at.isoformat()}",
                candidate_id=binding,
                monitoring_binding_id=binding,
                model_trade_id=None,
                product=self.member.asset_class.value,
                direction="NOT_APPLICABLE",
                submission_type=MonitoringSubmissionType.FACTUAL_MARKET_TICK,
                reference="LIVE-KITE-E2E",
                boundary=tick.observed_at,
                timeframe="TICK",
                session_identity=tick.connection_id,
                canonical_instrument=self.member.canonical_identity,
            )
            context = MonitoringAdmissionContext(
                binding,
                binding,
                None,
                self.member.canonical_identity,
                f"{self.instrument.exchange}:{self.instrument.trading_symbol}",
                self.member.asset_class.value,
                "NOT_APPLICABLE",
                tick.source,
                tick.connection_id,
                True,
                tick.observed_at,
                "TICK",
                tick.connection_id,
            )
            self.observation = self.registry.admit(submission, context, clock=self.clock())
        except Exception as error:
            self.failure = _safe_failure(error)
        finally:
            self.completed.set()

    def on_order_update(self, _update: ProviderOrderUpdateEvidence) -> None:
        """Order updates are intentionally outside this market-data proof."""

    def on_connection_state(self, _state: MonitoringConnectionState) -> None:
        """The session state is inspected by the orchestration timeout path."""


def _member(identity: str) -> SwingUniverseMember:
    matches = tuple(
        item for item in enabled_swing_phase1_universe()
        if item.canonical_identity == identity
    )
    if len(matches) != 1:
        raise ValueError("GOVERNED_INSTRUMENT_INVALID")
    return matches[0]


def _resolve(capability: object, member: SwingUniverseMember, as_of) -> InstrumentRecord:  # type: ignore[no-untyped-def]
    provider = KiteInstrumentProvider(capability)  # type: ignore[arg-type]
    if member.asset_class is SwingUniverseAssetClass.NSE_EQUITY:
        exchange, kind = "NSE", InstrumentKind.NSE_EQUITY
    elif member.asset_class is SwingUniverseAssetClass.NSE_INDEX:
        exchange, kind = "NSE", InstrumentKind.NSE_INDEX
    else:
        exchange, kind = "MCX", InstrumentKind.MCX_FUTURE
    return provider.resolve_from_records(
        provider.retrieve(exchange),
        InstrumentResolutionRequest(kind, member.canonical_identity, as_of),
    )


def _safe_failure(error: Exception) -> str:
    value = str(error)
    return value if re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", value) else "LIVE_MONITORING_FAILED"


def _failure(instrument: str, reason: str) -> LiveMonitoringTestResult:
    return LiveMonitoringTestResult(
        LiveMonitoringTestState.FAIL,
        instrument,
        safe_reason=reason,
    )


__all__ = [
    "LiveMonitoringTestResult",
    "LiveMonitoringTestState",
    "governed_live_monitoring_instruments",
    "run_live_monitoring_e2e",
]
