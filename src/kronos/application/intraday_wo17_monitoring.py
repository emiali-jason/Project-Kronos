"""Intraday-owned adapter over the commissioned shared read-only monitor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
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
    ) -> None:
        if (
            type(application) is not IntradayWo17Application
            or type(restoration) is not IntradayWo17RestorationService
            or not callable(acquire_monitoring_lease)
            or not callable(clock)
        ):
            raise ValueError("WO17_MONITORING_CONFIGURATION_INVALID")
        self._application = application
        self._restoration_service = restoration
        self._acquire_lease = acquire_monitoring_lease
        self._clock = clock
        self._hub: SharedSwingMonitoringHub | None = None
        self._attached: dict[str, _AttachedPosition] = {}
        self._lock = RLock()
        self._state = MonitoringConnectionState.DISCONNECTED
        self._latest_failure: str | None = None
        self._provider_calls = 0
        self._monitoring_operations = 0
        self._order_updates_ignored = 0

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
        try:
            registration.connect()
        except Exception:
            with self._lock:
                self._attached.pop(binding.canonical_subject_identity, None)
                self._latest_failure = "WO17_MONITORING_CONNECT_FAILED"
            registration.disconnect()
            raise ValueError("WO17_MONITORING_CONNECT_FAILED") from None
        with self._lock:
            if hub.connection_state is not None:
                self._state = hub.connection_state
        try:
            attached.restored = self._enter_recovery(restored, attached_at)
            attached.ready = True
        except Exception:
            with self._lock:
                self._attached.pop(binding.canonical_subject_identity, None)
                self._latest_failure = "WO17_MONITORING_RECOVERY_FAILED"
            registration.disconnect()
            raise ValueError("WO17_MONITORING_RECOVERY_FAILED") from None

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
        try:
            self._apply_tick(matches[0], tick)
        except Exception as error:
            self._fail(_sanitized(error))

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
        }:
            for item in attached:
                self._transition_availability(item, recovering=False)
        elif state is MonitoringConnectionState.CONNECTED:
            for item in attached:
                self._transition_availability(item, recovering=True)

    def status_document(self) -> dict[str, object]:
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
            }

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
    ) -> None:
        try:
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
                        return
                    position = recover_paper_entry_sequence(
                        position, recovered_at=occurred_at
                    ).current
                else:
                    if position.continuity not in {
                        Wo17EntryContinuity.AVAILABLE,
                        Wo17EntryContinuity.RECOVERING,
                    }:
                        return
                    position = interrupt_paper_entry_sequence(
                        position, occurred_at=occurred_at
                    ).current
                attached.restored = self._persist(
                    restored, position=position, lifecycle=None
                )
                return
            if position.state not in {
                Wo17PositionState.PAPER_ACTIVE,
                Wo17PositionState.LIVE_ACTIVE,
            }:
                return
            lifecycle = restored.lifecycle or create_wo17_lifecycle_machine(position)
            closure = restored.closure or create_wo17_closure_machine(position)
            occurred_at = max(
                occurred_at, lifecycle.last_transition_at + timedelta(microseconds=1)
            )
            if recovering:
                if lifecycle.monitoring_availability is not Wo17MonitoringAvailability.INTERRUPTED:
                    return
                transition = recover_wo17_lifecycle(
                    lifecycle, recovered_at=occurred_at
                )
            else:
                if lifecycle.monitoring_availability not in {
                    Wo17MonitoringAvailability.AVAILABLE,
                    Wo17MonitoringAvailability.RECOVERING,
                }:
                    return
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
        except Exception as error:
            self._fail(_sanitized(error))

    def _apply_tick(self, attached: _AttachedPosition, tick: ProviderMarketTick) -> None:
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


__all__ = [
    "IntradayWo17MonitoringCoordinator",
    "Wo17MonitoringBinding",
]
