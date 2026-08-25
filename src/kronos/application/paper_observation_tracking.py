"""Application boundary for ADR-0016 non-position Paper Observation Tracks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import RLock
from typing import Callable
from zoneinfo import ZoneInfo

from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalInterval,
)
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
    ProviderOrderUpdateEvidence,
)
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.paper_observation_track import (
    LocalPaperObservationTrackStore,
    PaperObservationMonitoringState,
    PaperObservationOutcome,
    PaperObservationSourceKind,
    PaperObservationTrackProjectionV1,
    PaperObservationTrackState,
    PaperObservationTrackV1,
    create_paper_observation_track,
    make_event,
    make_market_fact,
    make_monitoring_record,
)
from kronos.swing.v1.sponsor_observation_decision import (
    SponsorObservationDecisionResult,
)


PAPER_OBSERVATION_TRACK_OWNER_IDENTITY = "PAPER_OBSERVATION_TRACK"


class PaperObservationTrackingWorkflow:
    """Persist and monitor factual path evidence without position authority."""

    def __init__(
        self,
        store: LocalPaperObservationTrackStore,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        calendar: MarketCalendarPublisher | None = None,
    ) -> None:
        if (
            type(store) is not LocalPaperObservationTrackStore
            or not callable(clock)
            or (calendar is not None and type(calendar) is not MarketCalendarPublisher)
        ):
            raise TypeError("PAPER_OBSERVATION_WORKFLOW_INVALID")
        self._store = store
        self._clock = clock
        self._calendar = calendar or MarketCalendarPublisher()
        self._hub: SharedSwingMonitoringHub | None = None
        self._registrations: dict[str, object] = {}
        self._consumers: dict[str, _PaperObservationTrackConsumer] = {}
        self._lock = RLock()

    def set_shared_monitoring_hub(self, hub: SharedSwingMonitoringHub) -> None:
        if type(hub) is not SharedSwingMonitoringHub:
            raise TypeError("PAPER_OBSERVATION_SHARED_HUB_INVALID")
        self._hub = hub

    @property
    def active_monitoring_count(self) -> int:
        return len(self._registrations)

    def start(
        self,
        decision: SponsorObservationDecisionResult,
        *,
        current_run_identity: str,
        started_at: datetime,
    ) -> PaperObservationTrackProjectionV1:
        track = create_paper_observation_track(
            decision,
            current_run_identity=current_run_identity,
            created_at=started_at,
        )
        retained = self._store.retain_track(track)
        if not self._store.monitoring(retained.track_identity):
            self._retain_monitoring(
                retained.track_identity,
                PaperObservationMonitoringState.NOT_ACTIVE,
                "MONITORING_CAPABILITY_NOT_YET_REGISTERED",
                started_at,
            )
        return self._store.projection(retained.track_identity)

    def attach_monitoring(
        self,
        track_identity: str,
        capability: object,
        instrument: InstrumentRecord,
        *,
        reconcile_on_connect: bool = False,
    ) -> PaperObservationTrackProjectionV1:
        track = self._store.load_track(track_identity)
        projection = self._store.projection(track_identity)
        if projection.track_state is PaperObservationTrackState.COMPLETE:
            return projection
        if (
            type(instrument) is not InstrumentRecord
            or (
                instrument.name != track.canonical_instrument
                and instrument.trading_symbol != track.canonical_instrument
            )
        ):
            self._retain_monitoring(
                track_identity,
                PaperObservationMonitoringState.NOT_ACTIVE,
                "GOVERNED_INSTRUMENT_BINDING_INVALID",
                self._clock(),
            )
            return self._store.projection(track_identity)
        with self._lock:
            if track_identity in self._registrations:
                return self._store.projection(track_identity)
            hub = self._hub
            if hub is None:
                self._retain_monitoring(
                    track_identity,
                    PaperObservationMonitoringState.NOT_ACTIVE,
                    "SHARED_MONITORING_HUB_UNAVAILABLE",
                    self._clock(),
                )
                return self._store.projection(track_identity)
            consumer = _PaperObservationTrackConsumer(
                self,
                track,
                capability,
                instrument,
                reconcile_on_connect=reconcile_on_connect,
            )
            registration = None
            try:
                registration = hub.open(capability, consumer)
                registration.subscribe((instrument,))
                registration.connect()
            except (TypeError, ValueError):
                if registration is not None:
                    registration.disconnect()
                self._retain_monitoring(
                    track_identity,
                    PaperObservationMonitoringState.NOT_ACTIVE,
                    "FACTUAL_MONITORING_REGISTRATION_FAILED",
                    self._clock(),
                )
                return self._store.projection(track_identity)
            self._consumers[track_identity] = consumer
            self._registrations[track_identity] = registration
            self._retain_monitoring(
                track_identity,
                PaperObservationMonitoringState.ACTIVE,
                "SHARED_HUB_REGISTRATION_ACTIVE",
                self._clock(),
            )
        return self._store.projection(track_identity)

    def restore_monitoring(
        self,
        capability: object,
        resolver: Callable[[str], InstrumentRecord],
    ) -> tuple[str, ...]:
        if not callable(resolver):
            raise TypeError("PAPER_OBSERVATION_INSTRUMENT_RESOLVER_INVALID")
        restored = []
        for track in self._store.load_all_tracks():
            projection = self._store.projection(track.track_identity)
            if projection.track_state is PaperObservationTrackState.COMPLETE:
                continue
            try:
                instrument = resolver(track.canonical_instrument)
            except (TypeError, ValueError):
                self._retain_monitoring(
                    track.track_identity,
                    PaperObservationMonitoringState.NOT_ACTIVE,
                    "GOVERNED_INSTRUMENT_RESOLUTION_UNAVAILABLE",
                    self._clock(),
                )
                continue
            result = self.attach_monitoring(
                track.track_identity,
                capability,
                instrument,
                reconcile_on_connect=True,
            )
            if result.monitoring_state is PaperObservationMonitoringState.ACTIVE:
                restored.append(track.track_identity)
        return tuple(restored)

    def mark_monitoring_unavailable(self, reason: str) -> None:
        for track in self._store.load_all_tracks():
            projection = self._store.projection(track.track_identity)
            if projection.track_state is not PaperObservationTrackState.COMPLETE:
                state = (
                    PaperObservationMonitoringState.INTERRUPTED
                    if projection.monitoring_state in {
                        PaperObservationMonitoringState.ACTIVE,
                        PaperObservationMonitoringState.INTERRUPTED,
                    }
                    else PaperObservationMonitoringState.NOT_ACTIVE
                )
                self._retain_monitoring(
                    track.track_identity,
                    state,
                    reason,
                    self._clock(),
                )

    def projection(self, track_identity: str) -> PaperObservationTrackProjectionV1:
        return self._store.projection(track_identity)

    def projection_for_decision(
        self, decision_identity: str
    ) -> PaperObservationTrackProjectionV1 | None:
        matches = tuple(
            track for track in self._store.load_all_tracks()
            if track.sponsor_decision_identity == decision_identity
        )
        if len(matches) > 1:
            raise ValueError("PAPER_OBSERVATION_DECISION_TRACK_AMBIGUOUS")
        return None if not matches else self._store.projection(matches[0].track_identity)

    def projections(self) -> tuple[PaperObservationTrackProjectionV1, ...]:
        return tuple(
            self._store.projection(item.track_identity)
            for item in self._store.load_all_tracks()
        )

    def observe_tick(
        self, track_identity: str, tick: ProviderMarketTick
    ) -> PaperObservationTrackProjectionV1:
        track = self._store.load_track(track_identity)
        if (
            type(tick) is not ProviderMarketTick
            or (
                tick.instrument.name != track.canonical_instrument
                and tick.instrument.trading_symbol != track.canonical_instrument
            )
        ):
            raise ValueError("PAPER_OBSERVATION_TICK_BINDING_INVALID")
        current = self._store.projection(track_identity)
        if current.track_state is PaperObservationTrackState.COMPLETE:
            return current
        source_identity = (
            f"{tick.source}:{tick.connection_id}:"
            f"{tick.source_sequence if tick.source_sequence is not None else 'NO_SEQUENCE'}"
        )
        fact = make_market_fact(
            track,
            last_price=tick.last_price,
            observed_at=tick.observed_at,
            received_at=tick.received_at,
            source_identity=source_identity,
            source_sequence=tick.source_sequence,
            ordering_deterministic=tick.ordering_deterministic,
            recovered=tick.recovered,
        )
        previous_facts = self._store.facts(track_identity)
        same_source = tuple(
            item for item in previous_facts
            if item.source_identity == source_identity
        )
        if same_source:
            existing = same_source[-1]
            if (
                existing.last_price == tick.last_price
                and existing.observed_at == tick.observed_at
            ):
                return current
            self._retain_monitoring(
                track_identity,
                PaperObservationMonitoringState.INTERRUPTED,
                "PROVIDER_SEQUENCE_CONFLICT",
                self._clock(),
            )
            return self._store.projection(track_identity)
        prior_connection = tuple(
            item for item in previous_facts
            if item.source_identity.startswith(
                f"{tick.source}:{tick.connection_id}:"
            )
        )
        if (
            tick.ordering_deterministic is not True
            or tick.recovered is True
            or (
                prior_connection
                and (
                    tick.observed_at < prior_connection[-1].observed_at
                    or (
                        tick.source_sequence is not None
                        and prior_connection[-1].source_sequence is not None
                        and tick.source_sequence <= prior_connection[-1].source_sequence
                    )
                )
            )
        ):
            if not self._store.append_fact(fact):
                return self._store.projection(track_identity)
            self._retain_monitoring(
                track_identity,
                PaperObservationMonitoringState.INTERRUPTED,
                "ORDERED_LIVE_FACTS_UNAVAILABLE",
                self._clock(),
            )
            return self._store.projection(track_identity)
        if not self._store.append_fact(fact):
            return self._store.projection(track_identity)
        previous = None if not previous_facts else previous_facts[-1]
        if current.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED:
            if track.observation_entry_reference is not None and _entry_observed(
                track.direction,
                previous,
                tick.last_price,
                track.observation_entry_reference,
            ):
                self._append_event(
                    track,
                    PaperObservationOutcome.ENTRY_OBSERVED,
                    tick.observed_at,
                    source_identity,
                    PaperObservationSourceKind.KITE_FACTUAL_TICK,
                    observed_price=tick.last_price,
                )
            return self._store.projection(track_identity)
        stop_hit = _crossed(previous, tick.last_price, track.stop)
        target_hit = _crossed(previous, tick.last_price, track.target)
        if stop_hit and target_hit:
            outcome = PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED
        elif stop_hit:
            outcome = PaperObservationOutcome.STOP_LEVEL_TOUCHED
        elif target_hit:
            outcome = PaperObservationOutcome.TARGET_LEVEL_TOUCHED
        else:
            return self._store.projection(track_identity)
        self._append_event(
            track,
            outcome,
            tick.observed_at,
            source_identity,
            PaperObservationSourceKind.KITE_FACTUAL_TICK,
            observed_price=tick.last_price,
        )
        self._complete_registration(track_identity)
        return self._store.projection(track_identity)

    def reconcile_gap_from_provider(
        self,
        track_identity: str,
        capability: object,
        instrument: InstrumentRecord,
        *,
        observed_at: datetime,
    ) -> PaperObservationTrackProjectionV1:
        """Reconcile only completed DOMAIN-008 hourly intervals after a gap."""

        track = self._store.load_track(track_identity)
        if (
            type(instrument) is not InstrumentRecord
            or not _aware(observed_at)
            or not callable(getattr(capability, "historical_candles", None))
        ):
            self._retain_monitoring(
                track_identity,
                PaperObservationMonitoringState.INTERRUPTED,
                "GAP_RECONCILIATION_UNAVAILABLE",
                self._clock(),
            )
            return self._store.projection(track_identity)
        latest = self._store.projection(track_identity).last_factual_observation_at
        lower_bound = max(
            track.created_at,
            latest if latest is not None else track.created_at,
        )
        try:
            candles = tuple(sorted(
                capability.historical_candles(HistoricalCandleRequest(
                    instrument=instrument,
                    start=lower_bound.astimezone(UTC) - timedelta(hours=1),
                    end=observed_at.astimezone(UTC),
                    interval=HistoricalInterval.SIXTY_MINUTE,
                )),
                key=lambda item: item.timestamp,
            ))
            if any(type(item) is not HistoricalCandle for item in candles):
                raise ValueError("PAPER_OBSERVATION_HISTORICAL_DATA_INVALID")
            timezone = ZoneInfo(self._calendar.publication(instrument.exchange).timezone)
            for candle in candles:
                local = candle.timestamp.astimezone(timezone)
                schedule = self._calendar.schedule(
                    instrument.exchange,
                    local.date(),
                    observed_at=observed_at,
                )
                if schedule is None:
                    continue
                window = schedule.window_at(local)
                if window is None:
                    continue
                boundary = min(local + timedelta(hours=1), window.window_close)
                if candle.timestamp < lower_bound or boundary > observed_at:
                    continue
                projection = self.reconcile_completed_candle(
                    track_identity,
                    low=Decimal(str(candle.low)),
                    high=Decimal(str(candle.high)),
                    completed_at=boundary,
                    source_identity=(
                        f"DOMAIN008:{schedule.calendar_identity}:"
                        f"{schedule.calendar_version}:{schedule.session_identity}:"
                        f"{candle.timestamp.isoformat()}"
                    ),
                    domain008_completed=True,
                    gap_reconciliation=True,
                    interval_open=Decimal(str(candle.open)),
                    interval_close=Decimal(str(candle.close)),
                )
                if projection.track_state is PaperObservationTrackState.COMPLETE:
                    return projection
        except (TypeError, ValueError, RuntimeError):
            self._retain_monitoring(
                track_identity,
                PaperObservationMonitoringState.INTERRUPTED,
                "GAP_RECONCILIATION_UNAVAILABLE",
                self._clock(),
            )
        return self._store.projection(track_identity)

    def reconcile_completed_candle(
        self,
        track_identity: str,
        *,
        low: Decimal,
        high: Decimal,
        completed_at: datetime,
        source_identity: str,
        domain008_completed: bool,
        gap_reconciliation: bool = False,
        interval_open: Decimal | None = None,
        interval_close: Decimal | None = None,
    ) -> PaperObservationTrackProjectionV1:
        track = self._store.load_track(track_identity)
        if (
            not domain008_completed
            or not _aware(completed_at)
            or type(low) is not Decimal
            or type(high) is not Decimal
            or not low.is_finite()
            or not high.is_finite()
            or low > high
            or (interval_open is None) != (interval_close is None)
            or (
                interval_open is not None
                and (
                    type(interval_open) is not Decimal
                    or type(interval_close) is not Decimal
                    or not interval_open.is_finite()
                    or not interval_close.is_finite()
                    or not low <= interval_open <= high
                    or not low <= interval_close <= high
                )
            )
        ):
            return self._store.projection(track_identity)
        current = self._store.projection(track_identity)
        if current.track_state is PaperObservationTrackState.COMPLETE:
            return current
        source_kind = (
            PaperObservationSourceKind.GAP_RECONCILIATION
            if gap_reconciliation else PaperObservationSourceKind.COMPLETED_CANDLE
        )
        entry = track.observation_entry_reference
        contains_entry = entry is not None and low <= entry <= high
        contains_stop = track.stop is not None and low <= track.stop <= high
        contains_target = track.target is not None and low <= track.target <= high
        if current.entry_state is PaperObservationOutcome.ENTRY_NOT_OBSERVED:
            directional_crossing = (
                contains_entry
                and interval_open is not None
                and interval_close is not None
                and (
                    interval_open < entry <= interval_close
                    if track.direction is V1Direction.LONG
                    else interval_open > entry >= interval_close
                )
            )
            if not directional_crossing:
                return current
            self._append_event(
                track,
                PaperObservationOutcome.ENTRY_OBSERVED,
                completed_at,
                source_identity,
                source_kind,
                interval_low=low,
                interval_high=high,
            )
            if contains_stop or contains_target:
                self._append_event(
                    track,
                    PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED,
                    completed_at,
                    source_identity + ":ORDERING",
                    source_kind,
                    interval_low=low,
                    interval_high=high,
                )
                self._complete_registration(track_identity)
            return self._store.projection(track_identity)
        if contains_stop and contains_target:
            outcome = PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED
        elif contains_stop:
            outcome = PaperObservationOutcome.STOP_LEVEL_TOUCHED
        elif contains_target:
            outcome = PaperObservationOutcome.TARGET_LEVEL_TOUCHED
        else:
            return current
        self._append_event(
            track,
            outcome,
            completed_at,
            source_identity,
            source_kind,
            interval_low=low,
            interval_high=high,
        )
        self._complete_registration(track_identity)
        return self._store.projection(track_identity)

    def observe_connection_state(
        self, track_identity: str, state: MonitoringConnectionState
    ) -> None:
        if type(state) is not MonitoringConnectionState:
            raise TypeError("PAPER_OBSERVATION_CONNECTION_STATE_INVALID")
        projection = self._store.projection(track_identity)
        if projection.track_state is PaperObservationTrackState.COMPLETE:
            return
        if state is MonitoringConnectionState.CONNECTED:
            monitoring = PaperObservationMonitoringState.ACTIVE
            reason = "SHARED_MONITORING_CONNECTED"
        else:
            monitoring = PaperObservationMonitoringState.INTERRUPTED
            reason = "OBSERVATION_MONITORING_INTERRUPTED"
        self._retain_monitoring(track_identity, monitoring, reason, self._clock())

    def close(self) -> None:
        with self._lock:
            registrations = tuple(self._registrations.values())
            self._registrations.clear()
            self._consumers.clear()
        for registration in registrations:
            registration.disconnect()

    def _append_event(
        self,
        track: PaperObservationTrackV1,
        outcome: PaperObservationOutcome,
        observed_at: datetime,
        source_identity: str,
        source_kind: PaperObservationSourceKind,
        *,
        observed_price: Decimal | None = None,
        interval_low: Decimal | None = None,
        interval_high: Decimal | None = None,
    ) -> None:
        event = make_event(
            track,
            outcome,
            observed_at=observed_at,
            recorded_at=self._clock(),
            source_identity=source_identity,
            source_kind=source_kind,
            observed_price=observed_price,
            interval_low=interval_low,
            interval_high=interval_high,
        )
        self._store.append_event(event)

    def _retain_monitoring(
        self,
        track_identity: str,
        state: PaperObservationMonitoringState,
        reason: str,
        recorded_at: datetime,
    ) -> None:
        current = self._store.monitoring(track_identity)
        if current and current[-1].state is state and current[-1].reason == reason:
            return
        if current and recorded_at <= current[-1].recorded_at:
            recorded_at = current[-1].recorded_at + timedelta(microseconds=1)
        self._store.append_monitoring(
            make_monitoring_record(track_identity, state, reason, recorded_at)
        )

    def _complete_registration(self, track_identity: str) -> None:
        with self._lock:
            registration = self._registrations.pop(track_identity, None)
            self._consumers.pop(track_identity, None)
        if registration is not None:
            registration.disconnect()
        self._retain_monitoring(
            track_identity,
            PaperObservationMonitoringState.COMPLETE,
            "TERMINAL_FACTUAL_OUTCOME_RETAINED",
            self._clock(),
        )


class _PaperObservationTrackConsumer:
    owner_identity = PAPER_OBSERVATION_TRACK_OWNER_IDENTITY

    def __init__(
        self,
        workflow: PaperObservationTrackingWorkflow,
        track: PaperObservationTrackV1,
        capability: object,
        instrument: InstrumentRecord,
        *,
        reconcile_on_connect: bool,
    ) -> None:
        self._workflow = workflow
        self._track = track
        self._capability = capability
        self._instrument = instrument
        self._ever_connected = reconcile_on_connect

    def on_market_tick(self, tick: ProviderMarketTick) -> None:
        if type(tick) is not ProviderMarketTick or tick.instrument != self._instrument:
            raise ValueError("PAPER_OBSERVATION_TICK_BINDING_INVALID")
        self._workflow.observe_tick(self._track.track_identity, tick)

    def on_order_update(self, _update: ProviderOrderUpdateEvidence) -> None:
        # Broker/order-update evidence is not Paper Track authority.
        return None

    def on_connection_state(self, state: MonitoringConnectionState) -> None:
        self._workflow.observe_connection_state(self._track.track_identity, state)
        if state is MonitoringConnectionState.CONNECTED:
            if self._ever_connected:
                self._workflow.reconcile_gap_from_provider(
                    self._track.track_identity,
                    self._capability,
                    self._instrument,
                    observed_at=self._workflow._clock(),
                )
            self._ever_connected = True


def _entry_observed(
    direction: V1Direction,
    previous: object,
    price: Decimal,
    entry: Decimal,
) -> bool:
    if previous is None:
        return False
    previous_price = previous.last_price
    return (
        previous_price < entry <= price
        if direction is V1Direction.LONG
        else previous_price > entry >= price
    )


def _crossed(
    previous: object, current: Decimal, level: Decimal | None
) -> bool:
    if level is None:
        return False
    if previous is None:
        return current == level
    previous_price = previous.last_price
    return min(previous_price, current) <= level <= max(previous_price, current)


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "PAPER_OBSERVATION_TRACK_OWNER_IDENTITY",
    "PaperObservationTrackingWorkflow",
]
