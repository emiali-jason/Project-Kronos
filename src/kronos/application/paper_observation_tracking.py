"""Application boundary for ADR-0016 non-position Paper Observation Tracks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from dataclasses import asdict, replace
from decimal import Decimal
from hashlib import sha256
import json
from threading import RLock
from typing import Callable
from zoneinfo import ZoneInfo
from uuid import uuid4
from types import SimpleNamespace

_ANY_OWNER = object()

from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord, InstrumentResolutionError
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalInterval,
)
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    MonitoringError,
    MonitoringFailure,
    ProviderMarketTick,
    ProviderOrderUpdateEvidence,
)
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.paper_observation_track import (
    LocalPaperObservationTrackStore,
    PaperObservationMonitoringAuthorityV1,
    PaperObservationMonitoringApplicabilityState,
    PaperObservationMonitoringState,
    PaperObservationOutcome,
    PaperObservationRestorationProjectionV1,
    PaperObservationSourceKind,
    PaperObservationTrackProjectionV1,
    PaperObservationTrackState,
    PaperObservationTrackV1,
    create_paper_observation_track,
    make_monitoring_applicability,
    make_event,
    make_market_fact,
    make_monitoring_record,
    paper_observation_instrument_contract_identity,
    compact_replace,
    compact_projection,
    initial_compact_state,
)
from kronos.swing.v1.sponsor_observation_decision import (
    SponsorObservationDecisionResult,
)


PAPER_OBSERVATION_TRACK_OWNER_IDENTITY = "PAPER_OBSERVATION_TRACK"


def paper_monitoring_failure_reason(error: Exception) -> str:
    """Allowlisted existing vocabulary only; never retain arbitrary exceptions."""
    if isinstance(error, (MonitoringError, InstrumentResolutionError)):
        return error.failure.value
    value = str(error)
    if value in {"KITE_READ_ONLY_CAPABILITY_UNAVAILABLE", "SHARED_MONITORING_CAPABILITY_UNAVAILABLE"}:
        return "PROVIDER_CAPABILITY_NOT_ACTIVE"
    if value in {item.value for item in MonitoringFailure}:
        return value
    return "FACTUAL_MONITORING_REGISTRATION_FAILED"


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
        self._compact_modes = {}
        self._compact_states = {}
        self._compact_tracks = {}
        self._compact_fences = {}
        self._compact_live = {}
        self._compact_counters = dict(ordinary_ticks_accepted=0,
            material_transitions_retained=0, duplicate_ticks_ignored=0,
            incompatible_ticks_rejected=0, historical_replays_unverifiable=0)
        self._compact_recovery = set()
        self._compact_last_outcome = "NOT_OBSERVED"
        self._pending_owners = {}
        self._owner_bindings = {}
        self._detach_counts = dict(suspended_detached=0, closed_detached=0,
            terminal_detachments=0, stale_generation_detachments=0,
            already_detached=0, stale_callbacks_rejected=0,
            shared_subscription_retained=0, final_owner_subscription_releases=0)
        self._restoration_status: dict[str, object] = {
            "open_compatible": 0,
            "recovery_required": 0,
            "closed": 0,
            "restored": 0,
            "incompatible": 0,
            "legacy_without_applicability": 0,
            "duplicate_already_registered": 0,
            "reasons": (),
        }

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
        monitoring_authority: PaperObservationMonitoringAuthorityV1,
        authority_is_current: Callable[[], bool],
    ) -> PaperObservationTrackProjectionV1:
        if (
            type(monitoring_authority) is not PaperObservationMonitoringAuthorityV1
            or not callable(authority_is_current)
        ):
            raise TypeError("PAPER_OBSERVATION_ADMISSION_AUTHORITY_INVALID")
        candidate = create_paper_observation_track(
            decision,
            current_run_identity=current_run_identity,
            created_at=started_at,
        )
        if (
            monitoring_authority.sponsor_decision_identity
            != candidate.sponsor_decision_identity
            or monitoring_authority.native_assessment_sha256
            != candidate.native_assessment_sha256
            or monitoring_authority.direction is not candidate.direction
            or monitoring_authority.geometry_identity
            != candidate.step31_observation_identity
            or monitoring_authority.geometry_sha256
            != candidate.step31_observation_sha256
            or monitoring_authority.canonical_instrument
            != candidate.canonical_instrument
        ):
            raise ValueError("PAPER_OBSERVATION_ADMISSION_AUTHORITY_INVALID")
        try:
            existing = self._store.load_track(candidate.track_identity)
        except ValueError:
            track = candidate
        else:
            track = create_paper_observation_track(
                decision,
                current_run_identity=current_run_identity,
                created_at=existing.created_at,
            )
            if track != existing:
                raise ValueError("PAPER_OBSERVATION_TRACK_IMMUTABILITY_VIOLATION")
        applicability = make_monitoring_applicability(
            track.track_identity,
            PaperObservationMonitoringApplicabilityState.OPEN,
            "MONITORING_OPENED",
            monitoring_authority,
            track.created_at,
        )
        with self._lock:
            if not authority_is_current():
                raise ValueError("PAPER_OBSERVATION_ADMISSION_AUTHORITY_STALE")
            retained = self._store.retain_track(track, compact=True)
            self._store.append_applicability(applicability)
            if track is candidate:
                self._store.initialize_compact(initial_compact_state(track, applicability))
            if not authority_is_current():
                raise ValueError("PAPER_OBSERVATION_ADMISSION_AUTHORITY_STALE")
            self._store.publish_current_applicability(applicability)
        if not self._is_compact(retained.track_identity) and not self._store.monitoring(retained.track_identity):
            self._retain_monitoring(
                retained.track_identity,
                PaperObservationMonitoringState.NOT_ACTIVE,
                "MONITORING_CAPABILITY_NOT_YET_REGISTERED",
                started_at,
            )
        return self.projection(retained.track_identity)

    def attach_monitoring(
        self,
        track_identity: str,
        capability: object,
        instrument: InstrumentRecord,
        *,
        reconcile_on_connect: bool = False,
        current_authority: PaperObservationMonitoringAuthorityV1 | None = None,
        authority_is_current: Callable[[], bool] = lambda: True,
    ) -> PaperObservationTrackProjectionV1:
        restoration = self._store.restoration_projection(
            track_identity, current_authority
        )
        if (
            current_authority is not None
            and not restoration.applicability.automatic_restoration
        ):
            return self.projection(track_identity)
        self._attach_restoration_monitoring(
            restoration,
            capability,
            instrument,
            reconcile_on_connect=reconcile_on_connect,
            capability_is_current=authority_is_current,
        )
        return self.projection(track_identity)

    def _attach_restoration_monitoring(
        self,
        restoration: PaperObservationRestorationProjectionV1,
        capability: object,
        instrument: InstrumentRecord,
        *,
        reconcile_on_connect: bool,
        capability_is_current: Callable[[], bool] = lambda: True,
    ) -> PaperObservationRestorationProjectionV1:
        if self._is_compact(restoration.track_identity):
            return self._attach_compact_owner(restoration, capability, instrument,
                reconcile_on_connect, capability_is_current)
        if restoration.terminal:
            return restoration
        track = self._store.load_track(restoration.track_identity)
        if (
            track.integrity_sha256 != restoration.track_integrity_sha256
            or track.canonical_instrument != restoration.canonical_instrument
            or track.sponsor_decision_identity
            != restoration.sponsor_decision_identity
            or track.decision_snapshot_identity
            != restoration.decision_snapshot_identity
            or track.native_run_identity != restoration.native_run_identity
            or track.authority != restoration.track_authority
        ):
            raise ValueError("PAPER_OBSERVATION_RESTORATION_BINDING_INVALID")
        if getattr(capability, "active", False) is not True:
            self.record_monitoring_failure(
                restoration.track_identity, "PROVIDER_CAPABILITY_NOT_ACTIVE"
            )
            return self._store.restoration_projection(restoration.track_identity)
        if type(instrument) is not InstrumentRecord:
            raise TypeError("PAPER_OBSERVATION_INSTRUMENT_INVALID")
        applicability = self._store.current_applicability(restoration.track_identity)
        actual_contract = paper_observation_instrument_contract_identity(
            canonical_instrument=track.canonical_instrument,
            provider=instrument.provider,
            exchange=instrument.exchange,
            segment=instrument.segment,
            trading_symbol=instrument.trading_symbol,
            instrument_type=instrument.instrument_type,
            expiry=None if instrument.expiry is None else instrument.expiry.isoformat(),
        )
        if (
            (
                instrument.name != track.canonical_instrument
                and instrument.trading_symbol != track.canonical_instrument
            )
            or applicability is None
            or applicability.authority.instrument_contract_identity != actual_contract
        ):
            self._retain_monitoring(
                restoration.track_identity,
                PaperObservationMonitoringState.NOT_ACTIVE,
                "GOVERNED_INSTRUMENT_BINDING_INVALID",
                self._clock(),
            )
            return self._store.restoration_projection(restoration.track_identity)
        with self._lock:
            track_identity = restoration.track_identity
            if not capability_is_current():
                return self._store.restoration_projection(track_identity)
            current = self._store.restoration_projection(track_identity)
            if (
                current.track_integrity_sha256 != restoration.track_integrity_sha256
                or current.latest_event_identity != restoration.latest_event_identity
                or current.monitoring_record_identity
                != restoration.monitoring_record_identity
                or current.applicability.record_identity
                != restoration.applicability.record_identity
                or current.terminal
                or not capability_is_current()
            ):
                return current
            if track_identity in self._registrations:
                if self._consumers[track_identity]._capability is not capability:
                    self.record_monitoring_failure(track_identity, "CAPABILITY_UNAVAILABLE")
                    return self._store.restoration_projection(track_identity)
                if self._consumers[track_identity]._instrument != instrument:
                    self.record_monitoring_failure(track_identity, "GOVERNED_INSTRUMENT_BINDING_INVALID")
                    return self._store.restoration_projection(track_identity)
                self._reconcile_registration(track_identity)
                return self._store.restoration_projection(track_identity)
            hub = self._hub
            if hub is None:
                self._retain_monitoring(
                    track_identity,
                    PaperObservationMonitoringState.NOT_ACTIVE,
                    "SHARED_MONITORING_HUB_UNAVAILABLE",
                    self._clock(),
                )
                return self._store.restoration_projection(track_identity)
            if self._is_compact(track_identity):
                compact = self._compact_state(track_identity)
                if (compact.latest_observation is not None and not compact.resume_after_gap
                        and track_identity not in self._compact_fences):
                    self._compact_recovery.add(track_identity)
                    return self._store.compact_restoration_projection(track, None)
                self._compact_fences[track_identity] = (capability, capability_is_current, uuid4().hex)
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
            except Exception as error:
                if registration is not None:
                    try:
                        registration.disconnect()
                    except Exception:
                        pass
                self.record_monitoring_failure(track_identity, paper_monitoring_failure_reason(error))
                return self._store.restoration_projection(track_identity)
            self._consumers[track_identity] = consumer
            self._registrations[track_identity] = registration
            self._reconcile_registration(track_identity)
        return self._store.restoration_projection(track_identity)

    def _attach_compact_owner(self, restoration, capability, instrument, reconcile, current):
        identity = restoration.track_identity
        previous = self._registrations.get(identity)
        fence = self._compact_fences.get(identity)
        if previous is not None and fence is not None and fence[0] is not capability:
            if self._compact_generation_current(identity):
                return restoration  # A stale restoration cannot evict a newer capability.
            self.detach_monitoring(identity, "STALE_GENERATION", expected_registration=previous)
        pointer = self._store._current_applicability_path(identity)
        pointer_token = self._store._file_token(pointer)
        track = self._store.load_track(identity)
        applicable = self._store.current_applicability(identity)
        if (restoration.terminal or applicable is None
                or applicable.state is not PaperObservationMonitoringApplicabilityState.OPEN
                or getattr(capability, 'active', False) is not True or not current()):
            self.detach_monitoring(identity, "SUSPENDED", expected_registration=previous)
            return restoration
        state = self._compact_state(identity)
        verified = self._store.load_compact(identity)
        if (state.integrity_sha256 != verified.integrity_sha256
                or self._store._file_token(pointer) != pointer_token
                or state.applicability_identity != applicable.record_identity):
            self.detach_monitoring(identity, 'SUSPENDED', expected_registration=previous)
            return self._store.compact_restoration_projection(track, None)
        if (state.latest_observation is not None and not state.resume_after_gap
                and identity not in self._compact_fences):
            self._compact_recovery.add(identity)
            return self._store.compact_restoration_projection(track, None)
        contract = paper_observation_instrument_contract_identity(
            canonical_instrument=track.canonical_instrument, provider=instrument.provider,
            exchange=instrument.exchange, segment=instrument.segment,
            trading_symbol=instrument.trading_symbol, instrument_type=instrument.instrument_type,
            expiry=None if instrument.expiry is None else instrument.expiry.isoformat())
        if contract != applicable.authority.instrument_contract_identity:
            self.detach_monitoring(identity, "SUSPENDED", expected_registration=previous)
            return restoration
        generation = uuid4().hex
        with self._lock:
            if (not current() or self._store._file_token(pointer) != pointer_token
                    or self._compact_states.get(identity) is not state):
                return restoration
            if identity in self._registrations or identity in self._pending_owners:
                return restoration
            if self._hub is None:
                return restoration
            self._pending_owners[identity] = generation
        consumer = _PaperObservationTrackConsumer(self, track, capability, instrument,
            reconcile_on_connect=reconcile)
        consumer.owner_identity = identity
        registration = None
        try:
            registration = self._hub.open(capability, consumer)
            consumer._registration = registration
            registration.subscribe((instrument,))
            with self._lock:
                valid = (self._pending_owners.get(identity) == generation and current()
                    and self._store._file_token(pointer) == pointer_token
                    and self._compact_states.get(identity) is state)
                if valid:
                    self._compact_fences[identity] = (capability, current, generation)
                    self._registrations[identity] = registration
                    self._consumers[identity] = consumer
                    self._owner_bindings[identity] = (applicable.record_identity,
                        applicable.authority, instrument, generation, registration)
                self._pending_owners.pop(identity, None)
            if not valid:
                consumer._detached = True
                registration.disconnect()
                return restoration
            registration.connect()
            with self._lock:
                if self._registrations.get(identity) is registration:
                    self._compact_live[identity] = registration.active
        except Exception:
            self.detach_monitoring(identity, "SUSPENDED", expected_registration=registration)
            if registration is not None:
                registration.disconnect()
            raise
        return self._store.restoration_projection(identity)

    def _count_detach(self, name, count=1):
        self._detach_counts = self._detach_counts | {
            name: min((1 << 63) - 1, self._detach_counts[name] + count)}

    def detach_monitoring(self, identity, reason="SUSPENDED", *, expected_registration=_ANY_OWNER):
        """Fence exact owner under coordination, release shared resources outside."""
        with self._lock:
            registration = self._registrations.get(identity)
            if expected_registration is not _ANY_OWNER and registration is not expected_registration:
                self._count_detach('already_detached')
                return "ALREADY_DETACHED"
            pending = self._pending_owners.pop(identity, None)
            if registration is None:
                if pending is not None or reason in {'CLOSED', 'TERMINAL'}:
                    for mapping in (self._compact_states, self._compact_tracks, self._compact_modes,
                                    self._compact_fences, self._compact_live, self._owner_bindings):
                        mapping.pop(identity, None)
                    self._store._compact_tokens.pop(identity, None)
                    self._store._compact_open.discard(identity)
                    self._compact_recovery.discard(identity)
                self._count_detach('already_detached')
                return "ALREADY_DETACHED"
            self._registrations.pop(identity, None)
            consumer = self._consumers.pop(identity, None)
            if consumer is not None:
                consumer._detached = True
                consumer._capability = None
                consumer._instrument = None
                consumer._track = None
            for mapping in (self._owner_bindings, self._compact_fences, self._compact_live,
                            self._compact_states, self._compact_tracks, self._compact_modes):
                mapping.pop(identity, None)
            self._compact_recovery.discard(identity)
            counter = ('terminal_detachments' if reason == 'TERMINAL' else
                'closed_detached' if reason == 'CLOSED' else
                'stale_generation_detachments' if reason == 'STALE_GENERATION' else 'suspended_detached')
            self._count_detach(counter)
            self._store._compact_tokens.pop(identity, None)
            self._store._compact_open.discard(identity)
        registration.disconnect()
        return "DETACHED"

    def change_monitoring_applicability(self, identity, state, reason, *, expected_registration=None):
        if state not in {PaperObservationMonitoringApplicabilityState.SUSPENDED,
                         PaperObservationMonitoringApplicabilityState.CLOSED}:
            raise ValueError('PAPER_OBSERVATION_APPLICABILITY_TRANSITION_INVALID')
        registration = self._registrations.get(identity)
        if expected_registration is not None and registration is not expected_registration:
            return "ALREADY_DETACHED"
        previous = self._store.current_applicability(identity)
        if previous is None:  # Legacy absence is not permission to backfill.
            return self.detach_monitoring(identity, state.value, expected_registration=registration)
        if previous.state is state or previous.state is PaperObservationMonitoringApplicabilityState.CLOSED:
            return self.detach_monitoring(identity, state.value, expected_registration=registration)
        record = make_monitoring_applicability(identity, state, reason, previous.authority,
            self._clock(), predecessor_applicability_identity=previous.record_identity)
        prepared = self._store.prepare_applicability_transition(previous, record)
        with self._lock:
            if self._registrations.get(identity) is not registration:
                return "ALREADY_DETACHED"
            self._store.publish_applicability_transition(prepared)
        return self.detach_monitoring(identity,
            "TERMINAL" if reason == "TERMINAL_FACTUAL_OUTCOME_RETAINED" else state.value,
            expected_registration=registration)

    def reconcile_monitoring_owners(self, current_authority_resolver=None):
        """Explicit restoration/mutation path only; never called by GET/status."""
        for identity, registration in tuple(self._registrations.items()):
            if not self._is_compact(identity):
                continue
            try:
                if not self._compact_generation_current(identity):
                    self.detach_monitoring(identity, "STALE_GENERATION", expected_registration=registration)
                    continue
                track = self._store.load_track(identity)
                self._store.load_compact(identity)  # Invalid state detaches without authority writes.
                authority = (current_authority_resolver(track) if current_authority_resolver
                             else self._owner_bindings[identity][1])
                projection = self._store.compact_restoration_projection(track, authority, continuity_proven=True)
                if projection.terminal or not projection.applicability.automatic_restoration:
                    if (not projection.terminal
                            and projection.applicability.operation != "MONITORING_CLOSED"
                            and self._store.current_applicability(identity).state is PaperObservationMonitoringApplicabilityState.OPEN):
                        self.change_monitoring_applicability(identity,
                            PaperObservationMonitoringApplicabilityState.SUSPENDED,
                            projection.applicability.reason_codes[0], expected_registration=registration)
                    else:
                        self.detach_monitoring(identity,
                            "CLOSED" if projection.applicability.operation == "MONITORING_CLOSED" else "SUSPENDED",
                            expected_registration=registration)
            except (ValueError, OSError, KeyError):
                self.detach_monitoring(identity, "SUSPENDED", expected_registration=registration)

    def resume_monitoring(self, identity, current_authority, *, authority_is_current):
        """Explicit compatible OPEN successor; never invoked by GET/startup/Connect."""
        previous = self._store.current_applicability(identity)
        if previous is None or previous.state is not PaperObservationMonitoringApplicabilityState.SUSPENDED:
            raise ValueError('PAPER_OBSERVATION_EXPLICIT_RESUMPTION_UNAVAILABLE')
        if any(getattr(previous.authority, field) != getattr(current_authority, field)
               for field in previous.authority.__dataclass_fields__ if field != 'native_run_identity'):
            raise ValueError('PAPER_OBSERVATION_RESUMPTION_AUTHORITY_INCOMPATIBLE')
        old = self._store.load_compact(identity)
        if old.terminal or (old.latest_observation is not None and not old.resume_after_gap):
            raise ValueError('PAPER_OBSERVATION_COMPACT_RECOVERY_REQUIRED')
        record = make_monitoring_applicability(identity, PaperObservationMonitoringApplicabilityState.OPEN,
            'EXPLICIT_COMPATIBLE_RESUMPTION', previous.authority, self._clock(),
            predecessor_applicability_identity=previous.record_identity)
        applicable = self._store.prepare_applicability_transition(previous, record)
        state = compact_replace(old, applicability_identity=record.record_identity,
            applicability_sha256=record.integrity_sha256,
            monitoring_state=PaperObservationMonitoringState.NOT_ACTIVE,
            monitoring_reason='MONITORING_CAPABILITY_NOT_YET_REGISTERED')
        checkpoint = self._store.prepare_compact(old, state)
        track = self._store.load_track(identity)
        with self._lock:
            if (identity in self._registrations or identity in self._pending_owners
                    or not authority_is_current()):
                raise ValueError('PAPER_OBSERVATION_RESUMPTION_AUTHORITY_STALE')
            state = self._store.publish_compact_resumption(old, checkpoint, applicable)
            self._compact_states[identity], self._compact_tracks[identity] = state, track
            self._compact_recovery.discard(identity)
        return record

    def detachment_status(self):
        counters = dict(self._detach_counts)
        if self._hub is not None:
            release = self._hub.release_status()
            for name in ('shared_subscription_retained', 'final_owner_subscription_releases'):
                counters[name] = release[name]
        return counters | {"active_owners": len(self._owner_bindings)}

    def _reconcile_registration(self, track_identity: str) -> None:
        registration = self._registrations[track_identity]
        if self._is_compact(track_identity):
            self._compact_live[track_identity] = registration.active
            return
        current = self._store.restoration_projection(track_identity)
        # Transport repair must not erase factual ordering/gap failures.
        repairable = {
            "MONITORING_CAPABILITY_NOT_YET_REGISTERED", "PROVIDER_CAPABILITY_NOT_ACTIVE",
            "CAPABILITY_UNAVAILABLE", "PROVIDER_DISCONNECTED",
            "SHARED_MONITORING_HUB_UNAVAILABLE", "FACTUAL_MONITORING_REGISTRATION_FAILED",
            "GOVERNED_INSTRUMENT_RESOLUTION_UNAVAILABLE", "INSTRUMENT_NOT_RESOLVED",
            "SHARED_HUB_REGISTRATION_ACTIVE", "SHARED_MONITORING_CONNECTED",
            "OBSERVATION_MONITORING_INTERRUPTED",
        }
        if current.monitoring_reason not in repairable:
            return
        # An authentication marker may have overwritten an ordering/gap failure.
        # A still-connected socket from before that failure is not its resolution.
        for record in reversed(self._store.monitoring(track_identity)):
            if record.reason == "SHARED_MONITORING_CONNECTED":
                break
            if record.reason not in repairable:
                self._retain_monitoring(
                    track_identity, record.state, record.reason, self._clock()
                )
                return
        if not registration.active:
            self.record_monitoring_failure(track_identity, "OBSERVATION_MONITORING_INTERRUPTED")
            return
        state = registration.connection_state
        if state is not None:
            self.observe_connection_state(track_identity, state)
        else:
            self._retain_monitoring(
                track_identity, PaperObservationMonitoringState.ACTIVE,
                "SHARED_HUB_REGISTRATION_ACTIVE", self._clock(),
            )

    def record_monitoring_failure(self, track_identity: str, reason: str) -> None:
        """Record failure for the affected Track only, preserving immutable history."""
        current = self._store.restoration_projection(track_identity)
        if current.terminal:
            return
        state = (
            PaperObservationMonitoringState.INTERRUPTED
            if current.monitoring_state in {
                PaperObservationMonitoringState.ACTIVE, PaperObservationMonitoringState.INTERRUPTED,
            } else PaperObservationMonitoringState.NOT_ACTIVE
        )
        self._retain_monitoring(track_identity, state, reason, self._clock())

    def restore_monitoring(
        self,
        capability: object,
        resolver: Callable[[str], InstrumentRecord],
        current_authority_resolver: (
            Callable[[PaperObservationTrackV1], PaperObservationMonitoringAuthorityV1 | None]
            | None
        ) = None,
        capability_is_current: Callable[[], bool] = lambda: True,
    ) -> tuple[str, ...]:
        self.reconcile_monitoring_owners(current_authority_resolver)
        if not callable(resolver) or (
            current_authority_resolver is not None
            and not callable(current_authority_resolver)
        ) or not callable(capability_is_current):
            raise TypeError("PAPER_OBSERVATION_INSTRUMENT_RESOLVER_INVALID")
        if (
            getattr(capability, "active", False) is not True
            or not capability_is_current()
        ):
            return ()
        restored = []
        seen: set[str] = set()
        counts = {
            "open_compatible": 0,
            "recovery_required": 0,
            "closed": 0,
            "restored": 0,
            "incompatible": 0,
            "legacy_without_applicability": 0,
            "duplicate_already_registered": 0,
        }
        reasons: set[str] = set()
        for projection in self._store.restoration_projections(
            current_authority_resolver
        ):
            identity = projection.track_identity
            fence = self._compact_fences.get(identity)
            if fence is not None and fence[0] is capability and self._compact_generation_current(identity):
                track = self._compact_tracks[identity]
                projection = self._store.compact_restoration_projection(
                    track, current_authority_resolver(track) if current_authority_resolver else None,
                    continuity_proven=True)
            if projection.track_identity in seen:
                raise ValueError("PAPER_OBSERVATION_RESTORATION_IDENTITY_DUPLICATE")
            seen.add(projection.track_identity)
            if projection.terminal or projection.applicability.operation == "MONITORING_CLOSED":
                self.detach_monitoring(identity, "CLOSED",
                    expected_registration=self._registrations.get(identity))
                counts["closed"] += 1
                continue
            if not projection.applicability.automatic_restoration:
                self.detach_monitoring(identity, "SUSPENDED",
                    expected_registration=self._registrations.get(identity))
                if self._is_compact(projection.track_identity):
                    self._compact_recovery.add(projection.track_identity)
                counts["recovery_required"] += 1
                reasons.update(projection.applicability.reason_codes)
                if "APPLICABILITY_RECORD_UNAVAILABLE" in projection.applicability.reason_codes:
                    counts["legacy_without_applicability"] += 1
                else:
                    counts["incompatible"] += 1
                continue
            counts["open_compatible"] += 1
            if not capability_is_current():
                reasons.add("CAPABILITY_GENERATION_STALE")
                counts["incompatible"] += 1
                continue
            with self._lock:
                already_registered = projection.track_identity in self._registrations
            try:
                instrument = resolver(projection.canonical_instrument)
            except Exception:
                reasons.add("GOVERNED_INSTRUMENT_RESOLUTION_UNAVAILABLE")
                counts["incompatible"] += 1
                continue
            result = self._attach_restoration_monitoring(
                projection,
                capability,
                instrument,
                reconcile_on_connect=True,
                capability_is_current=capability_is_current,
            )
            if (result.monitoring_state is PaperObservationMonitoringState.ACTIVE
                    or (self._compact_live.get(projection.track_identity, False)
                        and result.monitoring_state is not PaperObservationMonitoringState.INTERRUPTED
                        and self._compact_generation_current(projection.track_identity))):
                if already_registered:
                    counts["duplicate_already_registered"] += 1
                else:
                    counts["restored"] += 1
                restored.append(projection.track_identity)
        with self._lock:
            self._restoration_status = counts | {"reasons": tuple(sorted(reasons))}
        return tuple(restored)

    def restoration_status(self) -> dict[str, object]:
        with self._lock:
            return dict(self._restoration_status)

    def mark_monitoring_unavailable(self, reason: str) -> None:
        for track_identity in tuple(self._registrations):
            projection = self._store.restoration_projection(track_identity)
            if not projection.terminal:
                state = (
                    PaperObservationMonitoringState.INTERRUPTED
                    if projection.monitoring_state in {
                        PaperObservationMonitoringState.ACTIVE,
                        PaperObservationMonitoringState.INTERRUPTED,
                    }
                    else PaperObservationMonitoringState.NOT_ACTIVE
                )
                self._retain_monitoring(
                    projection.track_identity,
                    state,
                    reason,
                    self._clock(),
                )

    def projection(self, track_identity: str) -> PaperObservationTrackProjectionV1:
        if self._is_compact(track_identity):
            state = self._compact_state(track_identity)
            projection = compact_projection(self._compact_tracks[track_identity], state)
            if (state.monitoring_state is PaperObservationMonitoringState.NOT_ACTIVE
                    and self._compact_live.get(track_identity, False)
                    and self._compact_generation_current(track_identity)):
                return replace(projection, monitoring_state=PaperObservationMonitoringState.ACTIVE,
                    monitoring_reason="SHARED_HUB_REGISTRATION_ACTIVE")
            return projection
        return self._store.projection(track_identity)

    def _is_compact(self, identity):
        if identity not in self._compact_modes:
            self._compact_modes[identity] = self._store.is_compact(identity)
        return self._compact_modes[identity]

    def _compact_state(self, identity):
        if identity not in self._compact_states:
            try:
                state = self._store.load_compact(identity)
            except ValueError:
                self._compact_recovery.add(identity)
                raise
            self._compact_tracks[identity] = self._store.load_track(identity)
            self._compact_states[identity] = state
        return self._compact_states[identity]

    def _count_compact(self, name):
        # Saturating counters are observations, never retained tick history.
        self._compact_counters = self._compact_counters | {
            name: min((1 << 63) - 1, self._compact_counters[name] + 1)}

    def compact_status(self):
        return self._compact_counters | {
            "detachment": self.detachment_status(),
            "latest_tick_disposition": self._compact_last_outcome,
            "active_compact_checkpoints": sum(not value.terminal for value in tuple(self._compact_states.values())),
            "recovery_required_tracks": len(self._compact_recovery),
            "legacy_tracks_inactive": self._restoration_status["legacy_without_applicability"],
        }

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

    def startup_projections(self):
        """Fact-free startup owner snapshot, without factual-history authority."""
        values = []
        for item in self._store.restoration_projections():
            track = self._store.load_track(item.track_identity)
            values.append(SimpleNamespace(
                track=track,
                track_state=(PaperObservationTrackState.COMPLETE if item.terminal
                             else PaperObservationTrackState.MONITORING_INTERRUPTED),
                monitoring_state=(PaperObservationMonitoringState.COMPLETE if item.terminal
                                  else PaperObservationMonitoringState.INTERRUPTED),
                monitoring_reason=(item.monitoring_reason if item.terminal else "RECOVERY_REQUIRED"),
                last_factual_observation_at=None,
            ))
        return tuple(values)

    def observe_tick(
        self, track_identity: str, tick: ProviderMarketTick
    ) -> PaperObservationTrackProjectionV1:
        if self._is_compact(track_identity):
            return self._observe_compact_tick(track_identity, tick)
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
        source_identity = _tick_source_identity(tick)
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
        previous = None if not previous_facts else previous_facts[-1]
        # A prior ordering conflict holds outcome authority until the governed
        # connection/reconciliation path explicitly restores monitoring.
        ordering_authority_held = (
            current.monitoring_state is PaperObservationMonitoringState.INTERRUPTED
            and current.monitoring_reason in {
                "ORDERED_LIVE_FACTS_UNAVAILABLE",
                "PROVIDER_SEQUENCE_CONFLICT",
            }
        )
        equal_time_order_unavailable = (
            previous is not None
            and tick.observed_at == previous.observed_at
            and (
                tick.source_sequence is None
                or previous.source_sequence is None
                or not previous.source_identity.startswith(
                    f"{tick.source}:{tick.connection_id}:"
                )
                or tick.source_sequence <= previous.source_sequence
            )
        )
        if (
            tick.ordering_deterministic is not True
            or tick.recovered is True
            or ordering_authority_held
            or (
                previous is not None
                and tick.observed_at < previous.observed_at
            )
            or equal_time_order_unavailable
            or (
                prior_connection
                and (
                    tick.source_sequence is not None
                    and prior_connection[-1].source_sequence is not None
                    and tick.source_sequence <= prior_connection[-1].source_sequence
                )
            )
        ):
            if not self._store.append_fact(fact):
                return self._store.projection(track_identity)
            self._retain_monitoring(
                track_identity,
                PaperObservationMonitoringState.INTERRUPTED,
                (
                    current.monitoring_reason
                    if ordering_authority_held
                    else "ORDERED_LIVE_FACTS_UNAVAILABLE"
                ),
                self._clock(),
            )
            return self._store.projection(track_identity)
        if not self._store.append_fact(fact):
            return self._store.projection(track_identity)
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

    def _compact_generation_current(self, identity):
        fence = self._compact_fences.get(identity)
        return fence is None or (fence[0].active is True and fence[1]())

    def _publish_compact(self, old, new, kind=None):
        generation = self._compact_fences.get(old.track_identity)
        prepared = self._store.prepare_compact(old, new, kind)
        with self._lock:
            if (self._compact_states.get(old.track_identity) is not old
                    or self._compact_fences.get(old.track_identity) is not generation
                    or (generation is not None and new.latest_observation != old.latest_observation
                        and new.monitoring_generation != generation[2])
                    or not self._compact_generation_current(old.track_identity)):
                raise ValueError("PAPER_OBSERVATION_COMPACT_GENERATION_STALE")
            try:
                published = self._store.publish_compact(old, prepared)
            except (ValueError, OSError):
                self._compact_recovery.add(old.track_identity)
                raise
            self._compact_states[old.track_identity] = published
        if kind is not None:
            self._count_compact("material_transitions_retained")
        return published

    def _compact_gap(self, state, reason):
        if state.monitoring_state is PaperObservationMonitoringState.INTERRUPTED:
            return state
        registration = self._registrations.get(state.track_identity)
        new = self._publish_compact(state, compact_replace(state,
            monitoring_state=PaperObservationMonitoringState.INTERRUPTED,
            monitoring_reason=reason, gap_count=state.gap_count + 1), "GAP_BEGAN")
        if registration is not None:
            self.change_monitoring_applicability(state.track_identity,
                PaperObservationMonitoringApplicabilityState.SUSPENDED, reason,
                expected_registration=registration)
        return new

    def _observe_owner_connection(self, owner, state):
        if type(state) is not MonitoringConnectionState:
            raise TypeError('PAPER_OBSERVATION_CONNECTION_STATE_INVALID')
        identity = owner._identity
        with self._lock:
            if self._consumers.get(identity) is not owner or owner._detached:
                self._count_detach('stale_callbacks_rejected')
                return
            current = self._compact_states.get(identity)
            if current is None:
                self._count_detach('stale_callbacks_rejected')
                return
            observational = owner._restoration_only and not owner._received_tick
            if observational:
                self._compact_live[identity] = state is MonitoringConnectionState.CONNECTED
        if not self._compact_generation_current(identity):
            self.detach_monitoring(identity, 'STALE_GENERATION', expected_registration=owner._registration)
            return
        if observational:
            if state is not MonitoringConnectionState.CONNECTED:
                self.detach_monitoring(identity, 'SUSPENDED', expected_registration=owner._registration)
            return
        try:
            if state is not MonitoringConnectionState.CONNECTED:
                self._compact_gap(current, 'OBSERVATION_MONITORING_INTERRUPTED')
            elif current.monitoring_state is PaperObservationMonitoringState.NOT_ACTIVE:
                self._publish_compact(current, compact_replace(current,
                    monitoring_state=PaperObservationMonitoringState.ACTIVE,
                    monitoring_reason='SHARED_MONITORING_CONNECTED'), 'MONITORING_OPENED')
        except (ValueError, OSError):
            self.detach_monitoring(identity, 'SUSPENDED', expected_registration=owner._registration)

    def _observe_compact_tick(self, identity, tick, *, owner=None):
        if type(tick) is not ProviderMarketTick:
            raise ValueError("PAPER_OBSERVATION_TICK_BINDING_INVALID")
        if owner is not None:
            with self._lock:
                if self._consumers.get(identity) is not owner or owner._detached:
                    self._count_detach('stale_callbacks_rejected')
                    return None
                state = self._compact_states.get(identity)
                if state is None:
                    self._count_detach('stale_callbacks_rejected')
                    return None
        else:
            state = self._compact_state(identity)
        track = self._compact_tracks[identity]
        if identity not in self._store._compact_open:
            self._compact_last_outcome = 'INAPPLICABLE_REJECTED'
            return compact_projection(track, state)
        if identity in self._compact_recovery:
            raise ValueError("PAPER_OBSERVATION_COMPACT_RECOVERY_REQUIRED")
        if state.terminal:
            self._compact_last_outcome = "TERMINAL_TRACK_IGNORED"
            return compact_projection(track, state)
        fence = self._compact_fences.get(identity)
        generation = state.monitoring_generation if fence is None else fence[2]
        contract = paper_observation_instrument_contract_identity(
            canonical_instrument=track.canonical_instrument,
            provider=tick.instrument.provider, exchange=tick.instrument.exchange,
            segment=tick.instrument.segment, trading_symbol=tick.instrument.trading_symbol,
            instrument_type=tick.instrument.instrument_type,
            expiry=None if tick.instrument.expiry is None else tick.instrument.expiry.isoformat())
        if (not self._compact_generation_current(identity)
                or contract != state.authority.instrument_contract_identity):
            self._compact_last_outcome = "INCOMPATIBLE_REJECTED"
            self._count_compact("incompatible_ticks_rejected")
            if owner is not None:
                self.detach_monitoring(identity, "STALE_GENERATION",
                    expected_registration=owner._registration)
            return compact_projection(track, state)
        encoded = _compact_observation(tick, generation)
        digest = sha256(encoded.encode()).hexdigest()
        same_generation = (generation == state.monitoring_generation
                           and tick.connection_id == state.session)
        previous_exists = state.latest_observation is not None
        if previous_exists and not same_generation and not state.resume_after_gap:
            # No sequence comparison across sessions. Continuity must have been
            # explicitly established by the governed reconciliation boundary.
            self._count_compact("incompatible_ticks_rejected")
            self._compact_last_outcome = "COMPACT_GENERATION_RECOVERY_REQUIRED"
            state = self._compact_gap(state, "COMPACT_GENERATION_RECOVERY_REQUIRED")
            return compact_projection(track, state)
        if previous_exists and same_generation:
            historical = (tick.source_sequence is not None and state.sequence is not None
                and tick.source_sequence < state.sequence)
            historical = historical or (tick.source_sequence is None
                and tick.observed_at < state.observed_at)
            if historical:
                self._compact_last_outcome = "PROVIDER_HISTORICAL_REPLAY_UNVERIFIABLE"
                self._count_compact("historical_replays_unverifiable")
                self._count_compact("incompatible_ticks_rejected")
                return compact_projection(track, state)
            equal = (tick.source_sequence is not None and tick.source_sequence == state.sequence)
            equal = equal or (tick.source_sequence is None and tick.observed_at == state.observed_at)
            if equal:
                if digest == state.observation_sha256:
                    self._compact_last_outcome = "EXACT_LATEST_REPLAY"
                    self._count_compact("duplicate_ticks_ignored")
                    return compact_projection(track, state)
                self._count_compact("incompatible_ticks_rejected")
                reason = ("PROVIDER_SEQUENCE_CONFLICT" if tick.source_sequence is not None
                          else "ORDERED_LIVE_FACTS_UNAVAILABLE")
                self._compact_last_outcome = reason
                return compact_projection(track, self._compact_gap(state, reason))
        if (state.monitoring_state is PaperObservationMonitoringState.INTERRUPTED
                or not tick.ordering_deterministic or tick.recovered
                or not tick.session_continuous or not tick.previous_interval_available
                or (state.observed_at == tick.observed_at
                    and (state.sequence is None or tick.source_sequence is None))
                or (state.observed_at is not None and tick.observed_at < state.observed_at)):
            self._compact_last_outcome = "ORDERED_LIVE_FACTS_UNAVAILABLE"
            self._count_compact("incompatible_ticks_rejected")
            return compact_projection(track, self._compact_gap(state, "ORDERED_LIVE_FACTS_UNAVAILABLE"))
        outcome = state.outcome
        entry_at, stop_at, target_at = state.entry_at, state.stop_at, state.target_at
        kind = None
        previous = (SimpleNamespace(last_price=state.reconciled_price)
                    if state.resume_after_gap and state.reconciled_price is not None
                    else state if state.last_price is not None else None)
        if entry_at is None:
            if state.entry is not None and _entry_observed(track.direction,
                    previous, tick.last_price, state.entry):
                entry_at, outcome, kind = tick.observed_at, PaperObservationOutcome.ENTRY_OBSERVED, "ENTRY_OBSERVED"
        else:
            stop_hit = _crossed(previous, tick.last_price, state.stop)
            target_hit = _crossed(previous, tick.last_price, state.target)
            if stop_hit or target_hit:
                stop_at = tick.observed_at if stop_hit else stop_at
                target_at = tick.observed_at if target_hit else target_at
                outcome = (PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED if stop_hit and target_hit
                    else PaperObservationOutcome.STOP_LEVEL_TOUCHED if stop_hit
                    else PaperObservationOutcome.TARGET_LEVEL_TOUCHED)
                kind = outcome.value
        new = compact_replace(state, latest_observation=encoded,
            observation_sha256=digest, last_price=tick.last_price, observed_at=tick.observed_at,
            sequence=tick.source_sequence, session=tick.connection_id,
            monitoring_generation=generation, entry_at=entry_at, stop_at=stop_at,
            target_at=target_at, outcome=outcome,
            high=tick.last_price if state.high is None else max(state.high, tick.last_price),
            low=tick.last_price if state.low is None else min(state.low, tick.last_price),
            coverage_start=state.coverage_start or tick.observed_at, coverage_end=tick.observed_at,
            resume_after_gap=False, reconciled_price=None)
        if new.terminal:
            new = compact_replace(new, monitoring_state=PaperObservationMonitoringState.COMPLETE,
                monitoring_reason="TERMINAL_FACTUAL_OUTCOME_RETAINED")
        elif fence is not None and state.monitoring_state is PaperObservationMonitoringState.NOT_ACTIVE:
            new = compact_replace(new, monitoring_state=PaperObservationMonitoringState.ACTIVE,
                monitoring_reason="SHARED_MONITORING_CONNECTED")
            kind = kind or "MONITORING_OPENED"
        new = self._publish_compact(state, new, kind)
        self._compact_last_outcome = "ACCEPTED"
        self._count_compact("ordinary_ticks_accepted")
        if new.terminal:
            self._complete_registration(identity)
        return compact_projection(track, new)

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
            return self.projection(track_identity)
        latest = self.projection(track_identity).last_factual_observation_at
        lower_bound = max(
            track.created_at,
            latest if latest is not None else track.created_at,
        )
        compact = self._is_compact(track_identity)
        captured_generation = self._compact_fences.get(track_identity)
        covered_through = lower_bound
        continuity_proved = True
        last_close = None
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
                if compact and (self._compact_fences.get(track_identity) is not captured_generation
                        or not self._compact_generation_current(track_identity)
                        or (captured_generation is not None and captured_generation[0] is not capability)):
                    return self.projection(track_identity)
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
                if compact and candle.timestamp != covered_through:
                    continuity_proved = False
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
                covered_through = boundary
                last_close = Decimal(str(candle.close))
                if projection.track_state is PaperObservationTrackState.COMPLETE:
                    return projection
            if (compact and continuity_proved and covered_through == observed_at
                    and last_close is not None):
                state = self._compact_state(track_identity)
                if state.monitoring_state is PaperObservationMonitoringState.INTERRUPTED:
                    self._publish_compact(state, compact_replace(state,
                        monitoring_state=PaperObservationMonitoringState.ACTIVE,
                        monitoring_reason="SHARED_MONITORING_CONNECTED",
                        resume_after_gap=True, reconciled_price=last_close), "GAP_ENDED")
        except (TypeError, ValueError, RuntimeError):
            self._retain_monitoring(
                track_identity,
                PaperObservationMonitoringState.INTERRUPTED,
                "GAP_RECONCILIATION_UNAVAILABLE",
                self._clock(),
            )
        return self.projection(track_identity)

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
            return self.projection(track_identity)
        if self._is_compact(track_identity):
            return self._reconcile_compact_candle(track, low, high, completed_at,
                interval_open, interval_close, source_identity, gap_reconciliation)
        current = self.projection(track_identity)
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
            return self.projection(track_identity)
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
        return self.projection(track_identity)

    def _reconcile_compact_candle(self, track, low, high, boundary, opened, closed,
                                  source_identity, gap_reconciliation):
        state = self._compact_state(track.track_identity)
        if state.terminal or (state.coverage_end is not None and boundary <= state.coverage_end):
            return compact_projection(track, state)
        entry_at, stop_at, target_at = state.entry_at, state.stop_at, state.target_at
        outcome = state.outcome
        hit_stop = state.stop is not None and low <= state.stop <= high
        hit_target = state.target is not None and low <= state.target <= high
        if entry_at is None:
            crossed = (state.entry is not None and opened is not None and closed is not None
                and (opened < state.entry <= closed if track.direction is V1Direction.LONG
                     else opened > state.entry >= closed))
            if crossed:
                entry_at = boundary
                outcome = (PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED if hit_stop or hit_target
                           else PaperObservationOutcome.ENTRY_OBSERVED)
        elif hit_stop or hit_target:
            outcome = (PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED if hit_stop and hit_target
                else PaperObservationOutcome.STOP_LEVEL_TOUCHED if hit_stop
                else PaperObservationOutcome.TARGET_LEVEL_TOUCHED)
        if entry_at is not None:
            stop_at = boundary if hit_stop else stop_at
            target_at = boundary if hit_target else target_at
        new = compact_replace(state, entry_at=entry_at, stop_at=stop_at, target_at=target_at,
            outcome=outcome, high=high if state.high is None else max(state.high, high),
            low=low if state.low is None else min(state.low, low), coverage_end=boundary,
            latest_reconciliation=json.dumps(dict(source_identity=source_identity,
                source_kind="GAP_RECONCILIATION" if gap_reconciliation else "COMPLETED_CANDLE",
                boundary=boundary.isoformat(), low=str(low), high=str(high),
                open=None if opened is None else str(opened), close=None if closed is None else str(closed)),
                sort_keys=True, separators=(",", ":")))
        if new.terminal:
            new = compact_replace(new, monitoring_state=PaperObservationMonitoringState.COMPLETE,
                monitoring_reason="TERMINAL_FACTUAL_OUTCOME_RETAINED")
        new = self._publish_compact(state, new, outcome.value if outcome is not state.outcome else None)
        if new.terminal:
            self._complete_registration(track.track_identity)
        return compact_projection(track, new)

    def observe_connection_state(
        self, track_identity: str, state: MonitoringConnectionState
    ) -> None:
        if type(state) is not MonitoringConnectionState:
            raise TypeError("PAPER_OBSERVATION_CONNECTION_STATE_INVALID")
        projection = self._store.restoration_projection(track_identity)
        if projection.terminal:
            return
        if state is MonitoringConnectionState.CONNECTED:
            monitoring = PaperObservationMonitoringState.ACTIVE
            reason = "SHARED_MONITORING_CONNECTED"
        else:
            monitoring = PaperObservationMonitoringState.INTERRUPTED
            reason = "OBSERVATION_MONITORING_INTERRUPTED"
        self._retain_monitoring(track_identity, monitoring, reason, self._clock())

    def close(self) -> None:
        for identity, registration in tuple(self._registrations.items()):
            self.detach_monitoring(identity, expected_registration=registration)

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
        if self._is_compact(track_identity):
            old = self._compact_state(track_identity)
            if old.terminal or (old.monitoring_state is state and old.monitoring_reason == reason):
                return
            if state is PaperObservationMonitoringState.INTERRUPTED:
                self._compact_gap(old, reason)
            elif state is PaperObservationMonitoringState.ACTIVE:
                if old.monitoring_state is PaperObservationMonitoringState.INTERRUPTED:
                    # A connected socket is not proof of continuous market coverage.
                    return
                self._publish_compact(old, compact_replace(old, monitoring_state=state,
                    monitoring_reason=reason), "MONITORING_OPENED")
            return
        with self._lock:
            current = self._store.monitoring(track_identity)
            if current and current[-1].state is state and current[-1].reason == reason:
                return
            if current and recorded_at <= current[-1].recorded_at:
                recorded_at = current[-1].recorded_at + timedelta(microseconds=1)
            self._store.append_monitoring(
                make_monitoring_record(track_identity, state, reason, recorded_at)
            )

    def _complete_registration(self, track_identity: str) -> None:
        if self._is_compact(track_identity):
            self.change_monitoring_applicability(track_identity,
                PaperObservationMonitoringApplicabilityState.CLOSED,
                "TERMINAL_FACTUAL_OUTCOME_RETAINED")
            return
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
        self._restoration_only = reconcile_on_connect
        self._received_tick = False
        self._detached = False
        self._identity = track.track_identity
        self._registration = None
        self._compact = workflow._is_compact(track.track_identity)

    def on_market_tick(self, tick: ProviderMarketTick) -> None:
        if self._detached:
            self._workflow._count_detach('stale_callbacks_rejected')
            return
        if type(tick) is not ProviderMarketTick or tick.instrument != self._instrument:
            if self._detached:
                self._workflow._count_detach('stale_callbacks_rejected')
                return
            raise ValueError("PAPER_OBSERVATION_TICK_BINDING_INVALID")
        capability = self._capability
        if self._compact and (
            self._workflow._consumers.get(self._identity) is not self
            or capability is None or not capability.active
        ):
            self._workflow._count_compact("incompatible_ticks_rejected")
            self._workflow.detach_monitoring(self._identity, 'STALE_GENERATION',
                expected_registration=self._registration)
            return
        if self._compact:
            try:
                self._workflow._observe_compact_tick(self._identity, tick, owner=self)
            except (ValueError, OSError):
                self._workflow.detach_monitoring(self._identity, "SUSPENDED",
                    expected_registration=self._registration)
                if not self._detached:
                    raise
        else:
            self._workflow.observe_tick(self._identity, tick)
        self._received_tick = True

    def on_order_update(self, _update: ProviderOrderUpdateEvidence) -> None:
        # Broker/order-update evidence is not Paper Track authority.
        return None

    def on_connection_state(self, state: MonitoringConnectionState) -> None:
        if self._detached:
            self._workflow._count_detach('stale_callbacks_rejected')
            return
        if self._compact:
            self._workflow._observe_owner_connection(self, state)
            return
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


def _compact_observation(tick, generation):
    def primitive(value):
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat()
        if isinstance(value, Decimal):
            return "0" if value == 0 else format(value.normalize(), "f")
        if isinstance(value, dict):
            return {key: primitive(item) for key, item in value.items()}
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value
    return json.dumps({"generation": generation, "tick": primitive(asdict(tick))},
                      sort_keys=True, separators=(",", ":"))


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


def _tick_source_identity(tick: ProviderMarketTick) -> str:
    """Return the immutable identity of one factual Provider observation.

    A genuine Provider sequence remains the identity key scoped by its source
    and connection.  When it is absent, KRONOS owns a clearly labelled digest
    of the governed observation timestamp and normalized price, while the
    persisted Provider sequence remains ``None``.  Thus equal timestamp/price
    is an exact replay, equal price at another time is another observation, and
    equal-time price changes remain distinct facts whose chronology is handled
    fail-closed by :meth:`observe_tick`.
    """

    if tick.source_sequence is not None:
        return f"{tick.source}:{tick.connection_id}:{tick.source_sequence}"
    observed_at = tick.observed_at.astimezone(UTC).isoformat()
    price = (
        "0"
        if tick.last_price == 0
        else format(tick.last_price.normalize(), "f")
    )
    observation_identity = sha256(
        f"{observed_at}:{price}".encode("utf-8")
    ).hexdigest()
    return (
        f"{tick.source}:{tick.connection_id}:"
        f"KRONOS_UNSEQUENCED_OBSERVATION:{observation_identity}"
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
