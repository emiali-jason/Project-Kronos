"""Process-local orchestration for Swing progression watches."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from threading import RLock, Thread
from zoneinfo import ZoneInfo

from kronos.application.live_monitoring_e2e import (
    resolve_governed_monitoring_instrument,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.derived_timeframes import (
    DerivedBarStatus,
    derive_session_four_hour_bars,
)
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
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.progression_watch import (
    GovernedCompletedBar,
    ProgressionRequirement,
    ProgressionRequirementState,
    ProgressionWatch,
    ProgressionWatchState,
    ProgressionWatchStore,
    activate_watch,
    mark_watch_stale,
    observe_completed_bar,
)


@dataclass(frozen=True, slots=True)
class SwingProgressionWatchSnapshot:
    current_native_run_identity: str | None
    requirements: tuple[ProgressionRequirement, ...]
    watches: tuple[ProgressionWatch, ...]

    def for_instrument(self, instrument: str) -> tuple[ProgressionRequirement, ...]:
        return tuple(item for item in self.requirements if item.canonical_instrument == instrument)

    def watch_for(self, requirement_id: str) -> ProgressionWatch | None:
        return next((item for item in self.watches if item.requirement.requirement_id == requirement_id), None)


class SwingProgressionWatchWorkflow:
    """Reuse Kite monitoring without creating Readiness or trading authority."""

    def __init__(
        self,
        store: ProgressionWatchStore | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        calendar: MarketCalendarPublisher | None = None,
        instrument_resolver: Callable[[object, str, date], InstrumentRecord] = (
            resolve_governed_monitoring_instrument
        ),
        bar_loader: Callable[
            [object, InstrumentRecord, ProgressionRequirement, datetime],
            GovernedCompletedBar | None,
        ] | None = None,
    ) -> None:
        if not all(callable(item) for item in (clock, instrument_resolver)):
            raise TypeError("PROGRESSION_WATCH_DEPENDENCY_INVALID")
        self._store = store or ProgressionWatchStore()
        self._clock = clock
        self._calendar = calendar or MarketCalendarPublisher()
        self._resolver = instrument_resolver
        self._bar_loader = bar_loader or self._load_latest_completed_bar
        self._lock = RLock()
        self._run_identity: str | None = None
        self._requirements: dict[str, ProgressionRequirement] = {}
        self._watches = {item.watch_id: item for item in self._store.load()}
        self._consumers: dict[str, _ProgressionMonitoringConsumer] = {}

    def synchronize(
        self,
        native_run_identity: str | None,
        requirements: tuple[ProgressionRequirement, ...],
    ) -> SwingProgressionWatchSnapshot:
        if type(requirements) is not tuple or any(
            type(item) is not ProgressionRequirement for item in requirements
        ):
            raise TypeError("PROGRESSION_REQUIREMENTS_INVALID")
        with self._lock:
            self._run_identity = native_run_identity
            self._requirements = {item.requirement_id: item for item in requirements}
            stale = tuple(
                watch for watch in self._watches.values()
                if watch.state is ProgressionWatchState.ACTIVE
                and (
                    native_run_identity is None
                    or watch.requirement.native_run_identity != native_run_identity
                    or watch.requirement.requirement_id not in self._requirements
                )
            )
        for watch in stale:
            self._detach(watch.watch_id)
            updated = mark_watch_stale(watch)
            self._store.retain(updated)
            with self._lock:
                self._watches[watch.watch_id] = updated
        return self.snapshot()

    def snapshot(self) -> SwingProgressionWatchSnapshot:
        with self._lock:
            requirements = tuple(sorted(
                self._requirements.values(),
                key=lambda item: (item.canonical_instrument, item.condition_identity),
            ))
            watches = tuple(sorted(
                self._watches.values(), key=lambda item: (item.activated_at, item.watch_id)
            ))
            active_by_requirement = {
                item.requirement.requirement_id: item
                for item in watches
                if item.state is ProgressionWatchState.ACTIVE
            }
            projected = tuple(
                requirement
                if requirement.requirement_id not in active_by_requirement
                else _active_requirement(requirement)
                for requirement in requirements
            )
            return SwingProgressionWatchSnapshot(self._run_identity, projected, watches)

    def activate_requirement(self, requirement_id: str, capability: object) -> ProgressionWatch:
        with self._lock:
            requirement = self._requirements.get(requirement_id)
            existing = next((
                item for item in self._watches.values()
                if item.requirement.requirement_id == requirement_id
                and item.state is ProgressionWatchState.ACTIVE
            ), None)
            run_identity = self._run_identity
        if existing is not None:
            if existing.watch_id not in self._consumers:
                self._attach(existing, capability)
            return existing
        if (
            requirement is None
            or requirement.state is not ProgressionRequirementState.WATCH_AVAILABLE
            or requirement.native_run_identity != run_identity
            or getattr(capability, "active", False) is not True
        ):
            raise ValueError("PROGRESSION_WATCH_ACTIVATION_NOT_PERMITTED")
        watch = activate_watch(requirement, activated_at=self._clock())
        self._store.retain(watch)
        with self._lock:
            self._watches[watch.watch_id] = watch
        try:
            self._attach(watch, capability)
        except Exception:
            stale = mark_watch_stale(watch)
            self._store.retain(stale)
            with self._lock:
                self._watches[watch.watch_id] = stale
            raise ValueError("PROGRESSION_WATCH_MONITORING_FAILED") from None
        return watch

    def restore_active(self, capability: object) -> tuple[str, ...]:
        if getattr(capability, "active", False) is not True:
            return ()
        with self._lock:
            values = tuple(
                item for item in self._watches.values()
                if item.state is ProgressionWatchState.ACTIVE
                and item.requirement.native_run_identity == self._run_identity
                and item.requirement.requirement_id in self._requirements
            )
        restored = []
        for watch in values:
            if watch.watch_id not in self._consumers:
                self._attach(watch, capability)
            restored.append(watch.watch_id)
        return tuple(restored)

    def close_monitoring(self) -> None:
        with self._lock:
            consumers = tuple(self._consumers.values())
            self._consumers.clear()
        for consumer in consumers:
            consumer.close()

    @property
    def active_monitoring_count(self) -> int:
        with self._lock:
            return len(self._consumers)

    def observe_bar(self, watch_id: str, bar: GovernedCompletedBar) -> ProgressionWatch:
        with self._lock:
            watch = self._watches.get(watch_id)
        if watch is None:
            raise ValueError("PROGRESSION_WATCH_UNAVAILABLE")
        updated = observe_completed_bar(watch, bar)
        if updated != watch:
            self._store.retain(updated)
            with self._lock:
                self._watches[watch_id] = updated
            self._detach(watch_id, asynchronous=True)
        return updated

    def _attach(self, watch: ProgressionWatch, capability: object) -> None:
        instrument = self._resolver(
            capability, watch.requirement.canonical_instrument,
            self._clock().date(),
        )
        consumer = _ProgressionMonitoringConsumer(self, watch, capability, instrument)
        session = capability.open_monitoring_session(consumer)
        consumer.bind(session)
        with self._lock:
            if watch.watch_id in self._consumers:
                raise ValueError("PROGRESSION_WATCH_MONITORING_ALREADY_ACTIVE")
            self._consumers[watch.watch_id] = consumer
        try:
            session.subscribe((instrument,))
            session.connect()
        except Exception:
            self._detach(watch.watch_id)
            raise

    def _detach(self, watch_id: str, *, asynchronous: bool = False) -> None:
        with self._lock:
            consumer = self._consumers.pop(watch_id, None)
        if consumer is None:
            return
        if asynchronous:
            Thread(target=consumer.close, name="swing-progression-watch-close", daemon=True).start()
        else:
            consumer.close()

    def _load_latest_completed_bar(
        self,
        capability: object,
        instrument: InstrumentRecord,
        requirement: ProgressionRequirement,
        observed_at: datetime,
    ) -> GovernedCompletedBar | None:
        candles = tuple(sorted(
            capability.historical_candles(HistoricalCandleRequest(
            instrument=instrument,
            start=observed_at.astimezone(UTC) - timedelta(days=8),
            end=observed_at.astimezone(UTC),
            interval=HistoricalInterval.SIXTY_MINUTE,
            )),
            key=lambda item: item.timestamp,
        ))
        if any(type(item) is not HistoricalCandle for item in candles):
            raise ValueError("PROGRESSION_WATCH_HISTORICAL_DATA_INVALID")
        exchange = instrument.exchange
        timezone = ZoneInfo(self._calendar.publication(exchange).timezone)
        completed = []
        by_day: dict[date, list[HistoricalCandle]] = defaultdict(list)
        for candle in candles:
            day = candle.timestamp.astimezone(timezone).date()
            schedule = self._calendar.schedule(exchange, day, observed_at=observed_at)
            if schedule is None:
                continue
            local = candle.timestamp.astimezone(timezone)
            window = schedule.window_at(local)
            if window is None:
                continue
            boundary = min(local + timedelta(hours=1), window.window_close)
            if boundary <= observed_at:
                completed.append((candle, schedule, boundary))
                by_day[day].append(candle)
        if requirement.timeframe is FactualTimeframe.ONE_HOUR and completed:
            candle, schedule, boundary = completed[-1]
            return GovernedCompletedBar(
                requirement.canonical_instrument, FactualTimeframe.ONE_HOUR,
                candle.close, boundary, "KITE_NORMALIZED_HISTORICAL",
                schedule.calendar_identity, schedule.calendar_version,
                schedule.session_identity, tuple(schedule.provenance),
            )
        if requirement.timeframe is FactualTimeframe.FOUR_HOUR:
            derived = []
            for day, values in sorted(by_day.items()):
                schedule = self._calendar.schedule(exchange, day, observed_at=observed_at)
                if schedule is None:
                    continue
                derived.extend(item for item in derive_session_four_hour_bars(
                    canonical_instrument=requirement.canonical_instrument,
                    schedule=schedule,
                    sixty_minute_candles=tuple(values),
                    source_provider_identity="KITE_NORMALIZED_HISTORICAL",
                    source_market_data_boundary=candles[-1].timestamp,
                    observed_at=observed_at,
                ) if item.status is DerivedBarStatus.COMPLETE)
            if derived:
                value = derived[-1]
                return GovernedCompletedBar(
                    requirement.canonical_instrument, FactualTimeframe.FOUR_HOUR,
                    value.close, value.observation_boundary,
                    "KITE_NORMALIZED_HISTORICAL", value.calendar_identity,
                    value.calendar_version, value.session_identity or "UNAVAILABLE",
                    value.provenance,
                )
        return None


class _ProgressionMonitoringConsumer:
    def __init__(self, workflow, watch, capability, instrument):  # type: ignore[no-untyped-def]
        self.workflow = workflow
        self.watch = watch
        self.capability = capability
        self.instrument = instrument
        self.session = None
        self.closed = False
        self.last_checked_minute: datetime | None = None

    def bind(self, session) -> None:  # type: ignore[no-untyped-def]
        self.session = session

    def on_market_tick(self, tick: ProviderMarketTick) -> None:
        if self.closed:
            return
        if type(tick) is not ProviderMarketTick or tick.instrument != self.instrument:
            raise ValueError("PROGRESSION_WATCH_INSTRUMENT_BINDING_MISMATCH")
        minute = tick.received_at.replace(second=0, microsecond=0)
        if minute == self.last_checked_minute:
            return
        self.last_checked_minute = minute
        bar = self.workflow._bar_loader(
            self.capability, self.instrument, self.watch.requirement,
            tick.received_at,
        )
        if bar is not None:
            self.workflow.observe_bar(self.watch.watch_id, bar)

    def on_order_update(self, _update: ProviderOrderUpdateEvidence) -> None:
        return None

    def on_connection_state(self, _state: MonitoringConnectionState) -> None:
        # The Provider session owns reconnect. Persisted watch state is unchanged.
        return None

    def close(self) -> None:
        self.closed = True
        session, self.session = self.session, None
        if session is None:
            return
        try:
            session.unsubscribe((self.instrument,))
        finally:
            session.disconnect()


def _active_requirement(value: ProgressionRequirement) -> ProgressionRequirement:
    from dataclasses import replace
    return replace(value, state=ProgressionRequirementState.WATCH_ACTIVE)


__all__ = ["SwingProgressionWatchSnapshot", "SwingProgressionWatchWorkflow"]
