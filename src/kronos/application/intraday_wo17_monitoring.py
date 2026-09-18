"""Intraday-owned adapter over the commissioned shared read-only monitor."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock, Thread
from typing import Callable

from kronos.application.intraday_wo17 import (
    IntradayWo17Application,
    IntradayWo17RestorationService,
    Wo17OperationRequest,
    create_wo17_operation_request,
)
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo17_closure import (
    close_wo17_paper_position,
    create_wo17_closure_machine,
    record_wo17_assessment_events,
    record_wo17_monitoring_event,
)
from kronos.intraday.wo17_lifecycle import (
    Wo17LifecycleMachine,
    Wo17MonitoringAvailability,
    create_wo17_lifecycle_machine,
    create_wo17_lifecycle_observation,
    interrupt_wo17_lifecycle,
    observe_wo17_lifecycle,
    recover_wo17_lifecycle,
)
from kronos.intraday.wo17_persistence import RestoredWo17State
from kronos.intraday.wo17_position import (
    Wo17EntryContinuity,
    Wo17PositionState,
    apply_paper_observation,
    create_wo17_entry_observation,
    interrupt_paper_entry_sequence,
    recover_paper_entry_sequence,
)
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
    ProviderOrderUpdateEvidence,
)


_MAX_QUEUED_WORK = 64
_MAX_QUEUED_BYTES = 32 * 1024


def _start_thread(operation, name):
    Thread(target=operation, name=name, daemon=True).start()


@dataclass(frozen=True, slots=True)
class Wo17MonitoringBinding:
    """Explicit bridge from canonical lineage to one Provider instrument."""

    canonical_subject_identity: str
    instrument_identity: str
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    provider_instrument: InstrumentRecord

    def __post_init__(self) -> None:
        if (
            not self.canonical_subject_identity
            or not self.instrument_identity
            or type(self.provider_instrument) is not InstrumentRecord
            or self.provider_instrument.provider != "KITE"
        ):
            raise ValueError("WO17_MONITORING_BINDING_INVALID")


@dataclass(slots=True)
class _AttachedPosition:
    restored: RestoredWo17State
    binding: Wo17MonitoringBinding
    registration: object
    ready: bool = False


class IntradayWo17MonitoringCoordinator:
    """Translate exact shared Provider ticks into published WO-17 engines."""

    owner_identity = "INTRADAY-WO17-LIFECYCLE-MONITORING"

    def __init__(
        self,
        application: IntradayWo17Application,
        restoration: IntradayWo17RestorationService,
        acquire_monitoring_lease: Callable[[], object | None],
        *,
        clock: Callable[[], datetime],
        background_runner: Callable[[Callable[[], None], str], object] = _start_thread,
    ) -> None:
        if (
            type(application) is not IntradayWo17Application
            or type(restoration) is not IntradayWo17RestorationService
            or not callable(acquire_monitoring_lease)
            or not callable(clock)
            or not callable(background_runner)
        ):
            raise ValueError("WO17_MONITORING_CONFIGURATION_INVALID")
        self._application = application
        self._restoration_service = restoration
        self._acquire_lease = acquire_monitoring_lease
        self._clock = clock
        self._background_runner = background_runner
        self._hub: SharedSwingMonitoringHub | None = None
        self._attached: dict[str, _AttachedPosition] = {}
        self._lock = RLock()
        self._state = MonitoringConnectionState.DISCONNECTED
        self._latest_failure: str | None = None
        self._provider_calls = 0
        self._monitoring_operations = 0
        self._order_updates_ignored = 0
        self._work_lock = RLock()
        self._work_queue = deque()
        self._pending_work = set()
        self._work_queued_bytes = 0
        self._work_generation = 0
        self._work_active = False
        self._work_state = "IDLE"
        self._work_failure: str | None = None
        self._work_cancel_requested = False
        self._continuity_gap_required = False
        self._continuity_state = "COMPLETE"
        self._coalesced_work = 0
        self._saturation_count = 0
        self._rejected_work = 0
        self._completed_work = 0

    def set_shared_monitoring_hub(self, hub: SharedSwingMonitoringHub) -> None:
        if type(hub) is not SharedSwingMonitoringHub:
            raise ValueError("WO17_SHARED_MONITORING_HUB_INVALID")
        with self._lock:
            if self._hub is not None and self._hub is not hub:
                raise ValueError("WO17_SHARED_MONITORING_HUB_CONFLICT")
            self._hub = hub

    def set_monitoring_capability_supplier(
        self, supplier: Callable[[], object | None]
    ) -> None:
        """Bind to the exact capability already owned by the shared runtime."""

        if not callable(supplier):
            raise ValueError("WO17_MONITORING_CAPABILITY_SUPPLIER_INVALID")
        with self._lock:
            if self._attached:
                raise ValueError("WO17_MONITORING_ALREADY_ATTACHED")
            self._acquire_lease = supplier

    def attach(
        self,
        binding: Wo17MonitoringBinding,
        *,
        attached_at: datetime,
    ) -> None:
        """Explicitly attach one restored non-closed position; never on startup."""

        if type(binding) is not Wo17MonitoringBinding or not _aware(attached_at):
            raise ValueError("WO17_MONITORING_ATTACH_INVALID")
        if self._work_cancelled():
            raise ValueError("WO17_MONITORING_CANCELLED")
        restored = self._application.store.restore_current(
            binding.canonical_subject_identity
        )
        if restored is None:
            raise ValueError("WO17_POSITION_UNAVAILABLE")
        self._validate_binding(restored, binding)
        if restored.pointer.non_closed is not True:
            raise ValueError("WO17_POSITION_NOT_MONITORABLE")
        with self._lock:
            if binding.canonical_subject_identity in self._attached:
                existing = self._attached[binding.canonical_subject_identity]
                if existing.binding == binding:
                    return
                raise ValueError("WO17_MONITORING_BINDING_CONFLICT")
            hub = self._hub
        if hub is None:
            raise ValueError("WO17_SHARED_MONITORING_UNAVAILABLE")

        capability = self._acquire_lease()
        if capability is None or getattr(capability, "active", False) is not True:
            raise ValueError("WO17_MONITORING_CAPABILITY_UNAVAILABLE")
        registration = hub.open(capability, self)
        registration.subscribe((binding.provider_instrument,))
        attached = _AttachedPosition(restored, binding, registration)
        with self._lock:
            self._attached[binding.canonical_subject_identity] = attached
            self._provider_calls += 1
        if self._dispose_cancelled_attachment(attached):
            raise ValueError("WO17_MONITORING_CANCELLED")
        try:
            registration.connect()
        except Exception:
            if self._dispose_cancelled_attachment(attached):
                raise ValueError("WO17_MONITORING_CANCELLED") from None
            with self._lock:
                self._attached.pop(binding.canonical_subject_identity, None)
                self._latest_failure = "WO17_MONITORING_CONNECT_FAILED"
            registration.disconnect()
            raise ValueError("WO17_MONITORING_CONNECT_FAILED") from None
        if self._dispose_cancelled_attachment(attached):
            raise ValueError("WO17_MONITORING_CANCELLED")
        with self._lock:
            if hub.connection_state is not None:
                self._state = hub.connection_state
        try:
            attached.restored = self._enter_recovery(restored, attached_at)
            attached.ready = True
        except Exception:
            if self._dispose_cancelled_attachment(attached):
                raise ValueError("WO17_MONITORING_CANCELLED") from None
            with self._lock:
                self._attached.pop(binding.canonical_subject_identity, None)
                self._latest_failure = "WO17_MONITORING_RECOVERY_FAILED"
            registration.disconnect()
            raise ValueError("WO17_MONITORING_RECOVERY_FAILED") from None
        if self._dispose_cancelled_attachment(attached):
            raise ValueError("WO17_MONITORING_CANCELLED")

    def on_market_tick(self, tick: ProviderMarketTick) -> None:
        if type(tick) is not ProviderMarketTick:
            return
        with self._lock:
            matches = tuple(
                item
                for item in self._attached.values()
                if item.ready and item.binding.provider_instrument == tick.instrument
            )
        if len(matches) != 1:
            if matches:
                self._fail("WO17_MONITORING_INSTRUMENT_AMBIGUOUS")
            return
        if (
            tick.source_sequence is None
            or not tick.ordering_deterministic
            or not tick.session_continuous
        ):
            self._fail("WO17_MONITORING_ORDERING_UNAVAILABLE")
            return
        attached = matches[0]
        self._admit_work(
            "TICK",
            (attached.binding.canonical_subject_identity, attached, tick),
            _work_size(tick),
            _tick_key(attached, tick),
        )

    def on_order_update(self, update: ProviderOrderUpdateEvidence) -> None:
        if type(update) is ProviderOrderUpdateEvidence:
            with self._lock:
                self._order_updates_ignored += 1

    def on_connection_state(self, state: MonitoringConnectionState) -> None:
        if type(state) is not MonitoringConnectionState:
            return
        with self._lock:
            self._state = state
            attached = tuple(item for item in self._attached.values() if item.ready)
        if state in {
            MonitoringConnectionState.DISCONNECTED,
            MonitoringConnectionState.RECONNECTING,
            MonitoringConnectionState.CONTEXT_INCOMPLETE,
            MonitoringConnectionState.CONNECTED,
        }:
            self._admit_work(
                "CONNECTION",
                (state, attached),
                _work_size(state) + len(attached) * 32,
                (
                    "CONNECTION",
                    state.value,
                    tuple(
                        (item.binding.canonical_subject_identity, id(item))
                        for item in attached
                    ),
                ),
            )

    def status_document(self) -> dict[str, object]:
        work = self.work_status()
        with self._lock:
            attached = tuple(self._attached.values())
            return {
                "state": self._state.value,
                "bindings": [
                    {
                        "canonical_subject_identity": item.binding.canonical_subject_identity,
                        "instrument_identity": item.binding.instrument_identity,
                        "actual_contract_identity": item.binding.actual_contract_identity,
                        "roll_lineage_identity": item.binding.roll_lineage_identity,
                        "provider_symbol": item.binding.provider_instrument.trading_symbol,
                    }
                    for item in attached
                ],
                "provider_calls": self._provider_calls,
                "monitoring_operations": self._monitoring_operations,
                "order_updates_ignored": self._order_updates_ignored,
                "autonomous_operations": 0,
                "latest_failure": self._latest_failure,
                "broker_operations": 0,
                "notification_deliveries": 0,
                "work": work,
            }

    def work_status(self) -> dict[str, object]:
        """Return worker ownership without entering the persistence owner."""

        with self._work_lock:
            return {
                "state": self._work_state,
                "generation": self._work_generation if self._work_active else None,
                "owned_workers": int(self._work_active),
                "maximum_workers": 1,
                "queued_items": len(self._work_queue),
                "maximum_queued_items": _MAX_QUEUED_WORK,
                "queued_bytes": self._work_queued_bytes,
                "maximum_queued_bytes": _MAX_QUEUED_BYTES,
                "maximum_live_items": _MAX_QUEUED_WORK + 1,
                "retained_work_generations": 0,
                "maximum_retained_work_generations": 0,
                "coalesced_work": self._coalesced_work,
                "saturation_count": self._saturation_count,
                "rejected_work": self._rejected_work,
                "completed_work": self._completed_work,
                "continuity": self._continuity_state,
                "failure": self._work_failure,
            }

    def shutdown(self) -> None:
        """Fence new work; an in-process operation remains owned until return."""

        with self._work_lock:
            self._work_cancel_requested = True
            if self._work_active:
                self._work_state = "CANCELLATION_REQUESTED"
            else:
                self._rejected_work += len(self._work_queue)
                self._work_queue.clear()
                self._pending_work.clear()
                self._work_queued_bytes = 0
                self._work_state = "TERMINATED"
        with self._lock:
            attached = tuple(self._attached.values())
            self._attached.clear()
        for item in attached:
            item.ready = False
            item.registration.disconnect()

    def _work_cancelled(self) -> bool:
        with self._work_lock:
            return self._work_cancel_requested

    def _dispose_cancelled_attachment(self, attached: _AttachedPosition) -> bool:
        if not self._work_cancelled():
            return False
        subject = attached.binding.canonical_subject_identity
        with self._lock:
            if self._attached.get(subject) is attached:
                self._attached.pop(subject, None)
        attached.ready = False
        attached.registration.disconnect()
        return True

    def _admit_work(self, kind, value, accounted_bytes, key) -> bool:
        dispatch = None
        with self._work_lock:
            if self._work_cancel_requested or self._work_state == "FAILED":
                self._rejected_work += 1
                return False
            if key in self._pending_work:
                self._coalesced_work += 1
                return True
            if (
                len(self._work_queue) >= _MAX_QUEUED_WORK
                or self._work_queued_bytes + accounted_bytes > _MAX_QUEUED_BYTES
            ):
                self._saturation_count += 1
                self._rejected_work += 1
                self._continuity_gap_required = True
                self._continuity_state = "GAP_PENDING"
                self._work_failure = "WO17_MONITORING_QUEUE_SATURATED"
                self._fail(self._work_failure)
                return False
            self._work_queue.append((kind, value, accounted_bytes, key))
            self._pending_work.add(key)
            self._work_queued_bytes += accounted_bytes
            if not self._work_active:
                self._work_generation += 1
                generation = self._work_generation
                self._work_active = True
                self._work_state = "RUNNING"
                dispatch = lambda: self._drain_work(generation)
        if dispatch is not None:
            try:
                self._background_runner(dispatch, "kronos-intraday-wo17")
            except Exception:
                self._worker_failed("WO17_MONITORING_WORKER_DISPATCH_FAILED")
                return False
        return True

    def _drain_work(self, generation: int) -> None:
        try:
            while True:
                with self._work_lock:
                    if generation != self._work_generation:
                        self._discard_queued_locked()
                        return
                    if self._work_cancel_requested:
                        self._discard_queued_locked()
                        self._work_state = "CANCELLATION_REQUESTED"
                        break
                    if self._work_queue:
                        kind, value, accounted_bytes, key = self._work_queue.popleft()
                        self._work_queued_bytes -= accounted_bytes
                    elif self._continuity_gap_required:
                        self._continuity_gap_required = False
                        kind, value, key = "GAP", None, None
                    else:
                        self._work_active = False
                        self._work_state = "IDLE"
                        return
                if kind == "TICK":
                    subject, attached, tick = value
                    with self._lock:
                        current = self._attached.get(subject)
                    if current is attached and attached.ready:
                        self._apply_tick(attached, tick)
                    else:
                        with self._work_lock:
                            self._rejected_work += 1
                elif kind == "CONNECTION":
                    state, attached_items = value
                    recovering = state is MonitoringConnectionState.CONNECTED
                    for attached in attached_items:
                        subject = attached.binding.canonical_subject_identity
                        with self._lock:
                            current = self._attached.get(subject)
                        if current is attached and attached.ready:
                            if not self._transition_availability(
                                attached, recovering=recovering
                            ):
                                raise RuntimeError(
                                    self._latest_failure
                                    or "WO17_MONITORING_TRANSITION_FAILED"
                                )
                else:
                    self._retain_queue_gap()
                with self._work_lock:
                    if key is not None:
                        self._pending_work.discard(key)
                    if kind == "GAP":
                        self._continuity_state = "GAP_RETAINED"
                    self._completed_work += 1
        except BaseException as error:
            if self._work_cancelled():
                with self._work_lock:
                    self._discard_queued_locked()
                    self._work_active = False
                    self._work_state = "TERMINATED"
                    self._continuity_state = "INCOMPLETE"
                return
            code = (
                _sanitized(error)
                if isinstance(error, Exception)
                else "WO17_MONITORING_WORKER_FAILED"
            )
            self._worker_failed(code)
            return
        with self._work_lock:
            self._work_active = False
            self._work_state = "TERMINATED"

    def _discard_queued_locked(self) -> None:
        self._rejected_work += len(self._work_queue)
        self._work_queue.clear()
        self._pending_work.clear()
        self._work_queued_bytes = 0

    def _worker_failed(self, code: str) -> None:
        with self._work_lock:
            self._discard_queued_locked()
            self._work_active = False
            self._work_state = "FAILED"
            self._work_failure = code
            self._continuity_state = "INCOMPLETE"
        self._fail(code)

    def _retain_queue_gap(self) -> None:
        with self._lock:
            attached = tuple(item for item in self._attached.values() if item.ready)
        for item in attached:
            if not self._transition_availability(item, recovering=False):
                raise RuntimeError(
                    self._latest_failure or "WO17_MONITORING_TRANSITION_FAILED"
                )

    def _validate_binding(
        self, restored: RestoredWo17State, binding: Wo17MonitoringBinding
    ) -> None:
        lineage = restored.snapshot.lineage
        if (
            lineage.canonical_subject_identity != binding.canonical_subject_identity
            or lineage.instrument_identity != binding.instrument_identity
            or lineage.actual_contract_identity != binding.actual_contract_identity
            or lineage.roll_lineage_identity != binding.roll_lineage_identity
        ):
            raise ValueError("WO17_MONITORING_LINEAGE_MISMATCH")
        if lineage.market_family is IntradayMarketFamily.MCX:
            if (
                binding.actual_contract_identity is None
                or binding.roll_lineage_identity is None
                or binding.provider_instrument.exchange != "MCX"
                or binding.provider_instrument.instrument_type != "FUT"
            ):
                raise ValueError("WO17_MONITORING_MCX_BINDING_INVALID")
        elif binding.actual_contract_identity is not None or binding.roll_lineage_identity is not None:
            raise ValueError("WO17_MONITORING_NSE_BINDING_INVALID")

    def _enter_recovery(
        self, restored: RestoredWo17State, attached_at: datetime
    ) -> RestoredWo17State:
        position = restored.position
        lifecycle = restored.lifecycle
        if position.state is Wo17PositionState.PAPER_ARMED:
            if position.continuity is Wo17EntryContinuity.RECOVERING:
                return restored
            if position.continuity is Wo17EntryContinuity.AVAILABLE:
                position = interrupt_paper_entry_sequence(
                    position, occurred_at=attached_at
                ).current
                attached_at += timedelta(microseconds=1)
            if position.continuity is not Wo17EntryContinuity.INTERRUPTED:
                raise ValueError("WO17_MONITORING_RECOVERY_STATE_INVALID")
            recovered = recover_paper_entry_sequence(
                position, recovered_at=attached_at
            ).current
            return self._persist(restored, position=recovered, lifecycle=None)
        if position.state in {Wo17PositionState.PAPER_ACTIVE, Wo17PositionState.LIVE_ACTIVE}:
            lifecycle = lifecycle or create_wo17_lifecycle_machine(position)
            closure = restored.closure or create_wo17_closure_machine(position)
            if lifecycle.monitoring_availability is Wo17MonitoringAvailability.RECOVERING:
                return restored
            if lifecycle.monitoring_availability is Wo17MonitoringAvailability.AVAILABLE:
                interrupted = interrupt_wo17_lifecycle(
                    lifecycle, occurred_at=attached_at
                )
                lifecycle = interrupted.current
                closure = record_wo17_monitoring_event(closure, interrupted).current
                attached_at += timedelta(microseconds=1)
            if lifecycle.monitoring_availability is not Wo17MonitoringAvailability.INTERRUPTED:
                raise ValueError("WO17_MONITORING_RECOVERY_STATE_INVALID")
            recovered = recover_wo17_lifecycle(
                lifecycle,
                recovered_at=attached_at,
            )
            closure = record_wo17_monitoring_event(closure, recovered).current
            return self._persist(
                restored,
                position=position,
                lifecycle=recovered.current,
                closure=closure,
            )
        return restored

    def _transition_availability(
        self, attached: _AttachedPosition, *, recovering: bool
    ) -> bool:
        try:
            if self._work_cancelled():
                raise ValueError("WO17_MONITORING_CANCELLED")
            restored = self._application.store.restore_current(
                attached.binding.canonical_subject_identity
            )
            if restored is None:
                raise ValueError("WO17_POSITION_UNAVAILABLE")
            self._validate_binding(restored, attached.binding)
            position = restored.position
            occurred_at = max(
                self._clock(), position.last_transition_at + timedelta(microseconds=1)
            )
            if position.state is Wo17PositionState.PAPER_ARMED:
                if recovering:
                    if position.continuity is not Wo17EntryContinuity.INTERRUPTED:
                        return True
                    position = recover_paper_entry_sequence(
                        position, recovered_at=occurred_at
                    ).current
                else:
                    if position.continuity not in {
                        Wo17EntryContinuity.AVAILABLE,
                        Wo17EntryContinuity.RECOVERING,
                    }:
                        return True
                    position = interrupt_paper_entry_sequence(
                        position, occurred_at=occurred_at
                    ).current
                attached.restored = self._persist(
                    restored, position=position, lifecycle=None
                )
                return True
            if position.state not in {
                Wo17PositionState.PAPER_ACTIVE,
                Wo17PositionState.LIVE_ACTIVE,
            }:
                return True
            lifecycle = restored.lifecycle or create_wo17_lifecycle_machine(position)
            closure = restored.closure or create_wo17_closure_machine(position)
            occurred_at = max(
                occurred_at, lifecycle.last_transition_at + timedelta(microseconds=1)
            )
            if recovering:
                if lifecycle.monitoring_availability is not Wo17MonitoringAvailability.INTERRUPTED:
                    return True
                transition = recover_wo17_lifecycle(
                    lifecycle, recovered_at=occurred_at
                )
            else:
                if lifecycle.monitoring_availability not in {
                    Wo17MonitoringAvailability.AVAILABLE,
                    Wo17MonitoringAvailability.RECOVERING,
                }:
                    return True
                transition = interrupt_wo17_lifecycle(
                    lifecycle, occurred_at=occurred_at
                )
            closure = record_wo17_monitoring_event(closure, transition).current
            attached.restored = self._persist(
                restored,
                position=position,
                lifecycle=transition.current,
                closure=closure,
            )
            return True
        except Exception as error:
            self._fail(_sanitized(error))
            return False

    def _apply_tick(self, attached: _AttachedPosition, tick: ProviderMarketTick) -> None:
        if self._work_cancelled():
            raise ValueError("WO17_MONITORING_CANCELLED")
        restored = self._application.store.restore_current(
            attached.binding.canonical_subject_identity
        )
        if restored is None:
            raise ValueError("WO17_POSITION_UNAVAILABLE")
        self._validate_binding(restored, attached.binding)
        sequence_identity = f"{tick.connection_id}-{tick.source_sequence}"
        position = restored.position
        if position.state is Wo17PositionState.PAPER_ARMED:
            observation = create_wo17_entry_observation(
                snapshot=restored.snapshot,
                provider_identity="DOMAIN-006-KITE-READ-ONLY",
                observed_price=tick.last_price,
                observed_at=tick.observed_at,
                source_sequence_identity=sequence_identity,
                source_sequence=tick.source_sequence,
                provenance=("ADR-0027", "WO-17-SLICE-6", tick.source),
            )
            position = apply_paper_observation(position, observation).current
            lifecycle = (
                create_wo17_lifecycle_machine(position)
                if position.state is Wo17PositionState.PAPER_ACTIVE
                else None
            )
            closure = (
                create_wo17_closure_machine(position)
                if lifecycle is not None
                else None
            )
            current = self._persist(
                restored, position=position, lifecycle=lifecycle, closure=closure
            )
        elif position.state in {Wo17PositionState.PAPER_ACTIVE, Wo17PositionState.LIVE_ACTIVE}:
            lifecycle = restored.lifecycle or create_wo17_lifecycle_machine(position)
            observation = create_wo17_lifecycle_observation(
                machine=lifecycle,
                provider_identity="DOMAIN-006-KITE-READ-ONLY",
                observed_price=tick.last_price,
                observed_at=tick.observed_at,
                source_sequence_identity=sequence_identity,
                source_sequence=tick.source_sequence,
                provenance=("ADR-0027", "WO-17-SLICE-6", tick.source),
            )
            transition = observe_wo17_lifecycle(lifecycle, observation)
            closure = restored.closure or create_wo17_closure_machine(position)
            if transition.assessment is not None and transition.assessment.observed_events:
                closure = record_wo17_assessment_events(
                    closure, transition.current, transition.assessment
                ).current
                if (
                    position.state is Wo17PositionState.PAPER_ACTIVE
                    and not transition.assessment.ordering_unresolved
                    and (
                        transition.assessment.stop_observed
                        or transition.assessment.target_observed
                    )
                ):
                    closure = close_wo17_paper_position(
                        closure, transition.current, transition.assessment
                    ).current
            current = self._persist(
                restored,
                position=position,
                lifecycle=transition.current,
                closure=closure,
            )
        else:
            return
        attached.restored = current
        with self._lock:
            self._monitoring_operations += 1

    def _persist(
        self,
        restored: RestoredWo17State,
        *,
        position: object,
        lifecycle: Wo17LifecycleMachine | None,
        closure: object | None = None,
    ) -> RestoredWo17State:
        if self._work_cancelled():
            raise ValueError("WO17_MONITORING_CANCELLED")
        requested_at = max(
            self._clock(),
            position.last_transition_at,
            datetime.min.replace(tzinfo=position.last_transition_at.tzinfo),
            *(() if lifecycle is None else (lifecycle.last_transition_at,)),
            *(() if closure is None else (closure.last_transition_at,)),
        )
        request: Wo17OperationRequest = create_wo17_operation_request(
            snapshot=restored.snapshot,
            position=position,
            lifecycle=lifecycle,
            closure=closure,
            live_exit_attestation=restored.live_exit_attestation,
            pre_entry_invalidation=restored.pre_entry_invalidation,
            requested_at=requested_at,
            provenance=("ADR-0027", "WO-17-SLICE-6-MONITORING"),
        )
        result = self._application.execute(request)
        if not hasattr(result, "pointer"):
            raise ValueError("WO17_MONITORING_BUSY")
        current = self._application.store.restore_current(
            request.canonical_subject_identity
        )
        if current is None:
            raise ValueError("WO17_MONITORING_RESTORE_FAILED")
        return current

    def _fail(self, code: str) -> None:
        with self._lock:
            self._latest_failure = code


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _sanitized(error: Exception) -> str:
    value = error.args[0] if error.args else None
    if type(value) is str and len(value) <= 128 and all(
        character.isupper() or character.isdigit() or character == "_"
        for character in value
    ):
        return value
    return "WO17_MONITORING_OPERATION_FAILED"


def _work_size(value: object) -> int:
    """Bound the retained representation of a small monitoring fact."""

    return len(repr(value).encode("utf-8"))


def _tick_key(attached: _AttachedPosition, tick: ProviderMarketTick) -> tuple:
    return (
        "TICK",
        attached.binding.canonical_subject_identity,
        id(attached),
        tick.connection_id,
        tick.source_sequence,
        tick.observed_at,
        tick.last_price,
    )


__all__ = [
    "IntradayWo17MonitoringCoordinator",
    "Wo17MonitoringBinding",
]
