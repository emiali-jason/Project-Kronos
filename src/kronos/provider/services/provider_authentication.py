"""Sole provider-neutral authentication and context lifecycle coordinator."""

from __future__ import annotations

import math
import re
import threading
import time
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from kronos.configuration.credentials import SecretLease, SecureCredentialSource
from kronos.configuration.principals import (
    IntendedPrincipalResolutionOutcome,
    IntendedPrincipalResolver,
    PrincipalBindingResult,
    PrincipalEvidence,
)
from kronos.provider.contracts.provider_authentication import (
    AuthenticatedReadOnlyProviderCapability,
    AuthenticationCallbackListener,
    LoginNavigator,
    ProviderAuthenticationAdapter,
    ProviderCandidateContext,
    ReadOnlyProviderOperation,
)
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)
from kronos.provider.models.authentication import (
    AuthenticatedContextState,
    AuthenticationAttempt,
    AuthenticationAttemptCancellationResult,
    AuthenticationAttemptState,
    AuthenticationFailureCode,
    AuthenticationOutcomeEvidence,
    BrowserOpenCategory,
    BrowserOpenRequest,
    CallbackCategory,
    CallbackReadiness,
    ProviderAuthenticationConfiguration,
    ProviderAvailabilityState,
    SessionStatus,
    GovernedAuthenticationOperation,
    SanitizedOperationLedger,
)
from kronos.provider.kite.live_activation import (
    DurableConsumptionRecord,
    MonotonicLifecycleDeadline,
    ProvenConsumption,
    RemainingBudget,
)
from kronos.provider.models.context import (
    AuthenticatedProviderContext,
    ContextReuseEligibility,
    ContextValidity,
)


_Clock = Callable[[], datetime]
_IdentityFactory = Callable[[], str]
_AdapterFactory = Callable[[str], ProviderAuthenticationAdapter]
_ListenerFactory = Callable[[], AuthenticationCallbackListener]
_RemainingBudgetSupplier = Callable[[], RemainingBudget]


class ConnectionAttemptDeadline:
    """Authority-neutral lifetime and resource ownership for one admitted request.

    This context restricts execution/publication. It supplies no authentication,
    credential, principal, Provider or activation authority.
    """

    def __init__(
        self,
        generation: int,
        request_identity: str | None = None,
        timeout_seconds: float = 330.0,
        monotonic_clock: Callable[[], float] | None = None,
        timer_factory: Callable[[float, Callable[[], None]], object] | None = None,
        absolute_expires_at: float | None = None,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 330.0
        ):
            raise ValueError("CONNECTION_DEADLINE_INVALID")
        self.__clock = monotonic_clock or time.monotonic
        self.__timer_factory = timer_factory or threading.Timer
        self.__lock = threading.RLock()
        self.__generation = generation
        self.__request_identity = request_identity
        self.__accepted_at = self.monotonic_now()
        self.__total_expires_at = self.__accepted_at + float(timeout_seconds)
        if absolute_expires_at is not None:
            if (isinstance(absolute_expires_at, bool)
                    or not isinstance(absolute_expires_at, (int, float))
                    or not math.isfinite(absolute_expires_at)):
                raise ValueError("CONNECTION_DEADLINE_INVALID")
            self.__total_expires_at = min(self.__total_expires_at, absolute_expires_at)
        self.__expires_at = self.__total_expires_at
        self.__state = "ACTIVE"
        self.__worker_active = True
        self.__callbacks_active = 0
        self.__callbacks: list[Callable[[], None]] = []
        self.__resources: dict[str, object] = {}
        self.__timer: object | None = None
        self.__armed = False
        self.__timer_serial = 0

    @property
    def generation(self) -> int:
        return self.__generation

    def monotonic_now(self) -> float:
        value = float(self.__clock())
        if not math.isfinite(value):
            raise ValueError("CONNECTION_MONOTONIC_CLOCK_INVALID")
        return value

    def remaining_seconds(self) -> float:
        with self.__lock:
            return max(0.0, self.__expires_at - self.monotonic_now())

    def arm(self, on_terminal: Callable[[], None]) -> None:
        if not callable(on_terminal):
            raise TypeError("CONNECTION_TERMINAL_CALLBACK_INVALID")
        with self.__lock:
            if self.__armed:
                raise RuntimeError("CONNECTION_DEADLINE_ALREADY_ARMED")
            self.__armed = True
            self.__callbacks.append(on_terminal)
        self.__schedule()

    def add_terminal_callback(self, callback: Callable[[], None]) -> None:
        """Register only a short state transition; never blocking cleanup."""

        if not callable(callback):
            raise TypeError("CONNECTION_TERMINAL_CALLBACK_INVALID")
        with self.__lock:
            if self.__state == "ACTIVE":
                self.__callbacks.append(callback)
                callbacks = ()
            elif self.__state == "SUCCEEDED":
                callbacks = ()
            else:
                callbacks = (callback,)
                self.__callbacks_active += 1
        self.__dispatch(callbacks)

    def shorten(self, seconds: float) -> None:
        """Apply a stricter phase limit without moving either deadline later."""

        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds <= 0
        ):
            raise ValueError("CONNECTION_PHASE_DEADLINE_INVALID")
        with self.__lock:
            if self.__state != "ACTIVE":
                return
            self.__expires_at = min(
                self.__expires_at, self.monotonic_now() + float(seconds)
            )
            timer = self.__timer
            self.__timer = None
            self.__timer_serial += 1
        self.__cancel_timer(timer)
        self.__schedule()

    def require(self) -> None:
        callbacks: tuple[Callable[[], None], ...] = ()
        timer = None
        with self.__lock:
            if self.__state == "ACTIVE" and self.monotonic_now() >= self.__expires_at:
                callbacks = self.__terminalize_locked("TIMED_OUT")
                timer, self.__timer = self.__timer, None
            allowed = self.__state in {"ACTIVE", "SUCCEEDED"}
        self.__cancel_timer(timer)
        self.__dispatch(callbacks)
        if not allowed:
            raise TimeoutError("CONNECTION_ATTEMPT_TERMINAL")

    @contextmanager
    def guard(self):
        """Serialize only a short publication against expiry/cancellation."""

        callbacks: tuple[Callable[[], None], ...] = ()
        timer = None
        self.__lock.acquire()
        try:
            if self.__state == "ACTIVE" and self.monotonic_now() >= self.__expires_at:
                callbacks = self.__terminalize_locked("TIMED_OUT")
                timer, self.__timer = self.__timer, None
            if self.__state not in {"ACTIVE", "SUCCEEDED"}:
                raise TimeoutError("CONNECTION_ATTEMPT_TERMINAL")
            yield
        finally:
            self.__lock.release()
            self.__cancel_timer(timer)
            self.__dispatch(callbacks)

    def commit(self, callback: Callable[[], object]) -> object:
        with self.guard():
            if self.__state == "SUCCEEDED":
                raise RuntimeError("CONNECTION_ATTEMPT_ALREADY_COMMITTED")
            result = callback()
            self.__state = "SUCCEEDED"
            timer = self.__timer
            self.__timer = None
            self.__callbacks.clear()
        self.__cancel_timer(timer)
        return result

    def finish(self, state: str = "FAILED") -> None:
        if state not in {"FAILED", "TIMED_OUT", "CANCELLED"}:
            raise ValueError("CONNECTION_TERMINAL_STATE_INVALID")
        with self.__lock:
            if self.__state != "ACTIVE":
                return
            if self.monotonic_now() >= self.__expires_at:
                state = "TIMED_OUT"
            callbacks = self.__terminalize_locked(state)
            timer = self.__timer
            self.__timer = None
        self.__cancel_timer(timer)
        self.__dispatch(callbacks)

    def cancel(self) -> None:
        self.finish("CANCELLED")

    def worker_finished(self) -> None:
        with self.__lock:
            self.__worker_active = False

    def hold_resource(self, name: str, resource: object) -> None:
        """Retain an unresolved owner; no exception/resource payload is exposed."""

        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", name):
            name = "UNRESOLVED_RESOURCE"
        with self.__lock:
            for existing in self.__resources.values():
                if existing is resource:
                    return
            key = name
            suffix = 2
            while key in self.__resources:
                key = f"{name}:{suffix}"
                suffix += 1
            self.__resources[key] = resource

    @contextmanager
    def _cleanup_guard(self):
        """Serialize short ownership bookkeeping, including after terminality."""

        with self.__lock:
            yield

    def _resolve_pending_resource(self, resource: object) -> None:
        """Release only an owner's independently confirmed pending cleanup."""

        with self.__lock:
            for key, existing in tuple(self.__resources.items()):
                if existing is resource:
                    del self.__resources[key]

    @property
    def retry_ready(self) -> bool:
        with self.__lock:
            return (
                self.__state != "ACTIVE"
                and not self.__worker_active
                and self.__callbacks_active == 0
                and not self.__resources
            )

    def snapshot(self) -> dict[str, object]:
        """Return retained facts only; reads do not expire or reset an attempt."""

        with self.__lock:
            pending = (
                self.__worker_active
                or self.__callbacks_active > 0
                or bool(self.__resources)
            )
            return {
                "state": self.__state,
                "remaining_seconds": max(0.0, self.__expires_at - self.monotonic_now()),
                "generation": self.__generation,
                "request_identity": self.__request_identity,
                "worker_active": self.__worker_active,
                "resources_pending": bool(self.__resources),
                "cleanup_state": "PENDING" if pending else "COMPLETE",
                "unresolved_resources": tuple(sorted(self.__resources)),
            }

    def __schedule(self) -> None:
        with self.__lock:
            if not self.__armed or self.__state != "ACTIVE" or self.__timer is not None:
                return
            seconds = max(0.0, self.__expires_at - self.monotonic_now())
            self.__timer_serial += 1
            serial = self.__timer_serial
            timer = self.__timer_factory(seconds, lambda: self.__timer_fired(serial))
            self.__timer = timer
            if hasattr(timer, "daemon"):
                timer.daemon = True
        try:
            timer.start()
        except BaseException:
            self.finish("FAILED")
            raise

    def __timer_fired(self, serial: int) -> None:
        with self.__lock:
            if serial != self.__timer_serial or self.__state != "ACTIVE":
                return
            self.__timer = None
            due = self.monotonic_now() >= self.__expires_at
        if due:
            self.finish("TIMED_OUT")
        else:
            self.__schedule()

    def __terminalize_locked(self, state: str) -> tuple[Callable[[], None], ...]:
        if self.__state != "ACTIVE":
            return ()
        self.__state = state
        callbacks = tuple(self.__callbacks)
        self.__callbacks.clear()
        self.__callbacks_active += len(callbacks)
        return callbacks

    def __dispatch(self, callbacks: tuple[Callable[[], None], ...]) -> None:
        for callback in callbacks:
            try:
                callback()
            except Exception:
                # The state remains terminal. A failed owner callback is retained
                # as unresolved so it can never silently admit another attempt.
                self.hold_resource("TERMINAL_CALLBACK", callback)
            finally:
                with self.__lock:
                    self.__callbacks_active -= 1

    @staticmethod
    def __cancel_timer(timer: object | None) -> None:
        if timer is not None:
            cancel = getattr(timer, "cancel", None)
            if callable(cancel):
                cancel()


_connection_deadline: ContextVar[ConnectionAttemptDeadline | None] = ContextVar(
    "kronos_connection_attempt_deadline", default=None
)


def current_connection_deadline() -> ConnectionAttemptDeadline | None:
    return _connection_deadline.get()


@contextmanager
def connection_deadline_scope(deadline: ConnectionAttemptDeadline | None):
    token = _connection_deadline.set(deadline)
    try:
        yield deadline
    finally:
        _connection_deadline.reset(token)


class _OperationLedgerRecorder(Protocol):
    def record(self, operation: GovernedAuthenticationOperation) -> None: ...

    def snapshot(self) -> SanitizedOperationLedger: ...


class _StartableCallbackListener(AuthenticationCallbackListener, Protocol):
    def start(self) -> None:
        """Bind and become ready without opening a browser."""


class _AvailabilityCandidate(ProviderCandidateContext, Protocol):
    def verify_provider_availability(self) -> object:
        """Perform one separately initiated availability verification."""


class _AttemptHandle:
    """Opaque identity capability issued by one service instance."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<AuthenticationAttemptHandle redacted>"

    __str__ = __repr__

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("AUTHENTICATION_ATTEMPT_HANDLE_SERIALIZATION_PROHIBITED")


class _AttemptRecord:
    __slots__ = (
        "adapter",
        "attempt",
        "callback_result",
        "candidate",
        "completion_started",
        "handle",
        "listener",
        "monotonic_expires_at",
        "secret_lease",
        "terminal_evidence",
    )

    def __init__(self, handle: _AttemptHandle, attempt: AuthenticationAttempt) -> None:
        self.handle = handle
        self.attempt = attempt
        self.monotonic_expires_at = float("inf")
        self.listener: _StartableCallbackListener | None = None
        self.adapter: ProviderAuthenticationAdapter | None = None
        self.callback_result: object | None = None
        self.completion_started = False
        self.secret_lease: SecretLease | None = None
        self.candidate: ProviderCandidateContext | None = None
        self.terminal_evidence: AuthenticationOutcomeEvidence | None = None

    def __repr__(self) -> str:
        return "<_AttemptRecord redacted>"


class ProtectedPrincipalBindingVerifier:
    """Resolve expected identity through one protected comparison operation."""

    __slots__ = ("__resolver", "__cleanup_failure")

    def __init__(
        self,
        resolver: IntendedPrincipalResolver,
        *,
        cleanup_failure: Callable[[PrincipalEvidence], None] | None = None,
    ) -> None:
        self.__resolver = resolver
        self.__cleanup_failure = cleanup_failure

    def bind_attempt(self, deadline: object) -> None:
        bind = getattr(self.__resolver, "bind_attempt", None)
        if callable(bind):
            bind(deadline)

    def verify_principal_binding(
        self,
        evidence: PrincipalEvidence,
        intended_registration_ref: str,
    ) -> PrincipalBindingResult:
        def compare(lease: object) -> PrincipalBindingResult:
            compare_once = getattr(lease, "compare_once", None)
            if not callable(compare_once):
                raise RuntimeError("INTENDED_PRINCIPAL_LEASE_INVALID")
            result = compare_once(evidence)
            if not isinstance(result, PrincipalBindingResult):
                raise RuntimeError("PRINCIPAL_BINDING_RESULT_INVALID")
            return result

        try:
            resolution = self.__resolver.use_resolved_once(
                intended_registration_ref,
                compare,
            )
        except Exception:
            return PrincipalBindingResult.UNAVAILABLE
        finally:
            try:
                evidence.close()
            except Exception:
                if self.__cleanup_failure is not None:
                    self.__cleanup_failure(evidence)

        try:
            if resolution.outcome is IntendedPrincipalResolutionOutcome.RESOLVED:
                return resolution.binding_result or PrincipalBindingResult.UNAVAILABLE
            if resolution.outcome in {
                IntendedPrincipalResolutionOutcome.NOT_FOUND,
                IntendedPrincipalResolutionOutcome.INVALID_CONFIGURATION,
            }:
                return PrincipalBindingResult.UNCONFIRMED
        except Exception:
            return PrincipalBindingResult.UNAVAILABLE
        return PrincipalBindingResult.UNAVAILABLE


class ProviderAuthenticationService:
    """Authoritative coordinator for one Provider registration."""

    __slots__ = (
        "__active_handle",
        "__adapter_factory",
        "__availability",
        "__binding_verifier",
        "__candidate",
        "__clock",
        "__configuration",
        "__context",
        "__context_state",
        "__credential_source",
        "__identity_factory",
        "__latest_handle",
        "__lifetime",
        "__listener_factory",
        "__lock",
        "__navigator",
        "__ordinary_deadline",
        "__helper_deadline",
        "__monotonic_clock",
        "__inflight",
        "__operation_recorder",
        "__proven_consumption",
        "__remaining_budget",
        "__governed",
        "__governed_cleanup_recorded",
        "__records",
        "__read_only_capability",
        "__unresolved_cleanup",
        "__cleanup_in_progress",
    )

    def __init__(
        self,
        configuration: ProviderAuthenticationConfiguration,
        *,
        credential_source: SecureCredentialSource,
        principal_resolver: IntendedPrincipalResolver,
        adapter_factory: _AdapterFactory,
        listener_factory: _ListenerFactory,
        navigator: LoginNavigator,
        clock: _Clock,
        identity_factory: _IdentityFactory,
        attempt_lifetime: timedelta = timedelta(minutes=5),
        proven_consumption: ProvenConsumption | None = None,
        remaining_budget: _RemainingBudgetSupplier | None = None,
        operation_recorder: _OperationLedgerRecorder | None = None,
        ordinary_deadline: ConnectionAttemptDeadline | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        if attempt_lifetime <= timedelta(0):
            raise ValueError("ATTEMPT_LIFETIME_INVALID")
        governed_inputs = (
            proven_consumption,
            remaining_budget,
            operation_recorder,
        )
        governed = all(value is not None for value in governed_inputs)
        if any(value is not None for value in governed_inputs) and not governed:
            raise ValueError("GOVERNED_AUTHENTICATION_SEAMS_INCOMPLETE")
        if governed:
            if (
                type(proven_consumption) is not ProvenConsumption
                or type(proven_consumption.record) is not DurableConsumptionRecord
                or type(proven_consumption.deadline) is not MonotonicLifecycleDeadline
                or type(proven_consumption.ledger) is not SanitizedOperationLedger
                or not callable(remaining_budget)
                or not callable(getattr(operation_recorder, "record", None))
                or not callable(getattr(operation_recorder, "snapshot", None))
                or operation_recorder.snapshot() is not proven_consumption.ledger
                or proven_consumption.ledger.count_for(
                    GovernedAuthenticationOperation.ACTIVATION_VALIDATION
                )
                != 1
                or proven_consumption.ledger.count_for(
                    GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
                )
                != 1
                or proven_consumption.ledger.count_for(
                    GovernedAuthenticationOperation.PROVIDER_AVAILABILITY_VERIFICATION
                )
                != 0
            ):
                raise ValueError("GOVERNED_CONSUMPTION_PROOF_INVALID")
            budget = remaining_budget()
            if type(budget) is not RemainingBudget:
                raise ValueError("GOVERNED_DEADLINE_INVALID")
            budget.require_available()
        self.__ordinary_deadline = ordinary_deadline
        self.__helper_deadline = ordinary_deadline
        self.__monotonic_clock = (
            ordinary_deadline.monotonic_now if ordinary_deadline is not None
            else monotonic_clock or time.monotonic
        )
        self.__inflight = 0
        self.__configuration = configuration
        self.__credential_source = credential_source
        self.__binding_verifier = ProtectedPrincipalBindingVerifier(
            principal_resolver,
            cleanup_failure=(
                None if ordinary_deadline is None
                else lambda evidence: ordinary_deadline.hold_resource(
                    "PRINCIPAL_EVIDENCE", evidence
                )
            ),
        )
        self.__adapter_factory = adapter_factory
        self.__listener_factory = listener_factory
        self.__navigator = navigator
        self.__clock = clock
        self.__identity_factory = identity_factory
        self.__lifetime = attempt_lifetime
        self.__governed = governed
        self.__proven_consumption = proven_consumption
        self.__remaining_budget = remaining_budget
        self.__operation_recorder = operation_recorder
        self.__governed_cleanup_recorded = False
        self.__lock = threading.RLock()
        # Keep failed owners even without an ordinary deadline (governed use).
        # Only PENDING disposal may resolve later; FAILED is sticky quarantine.
        self.__unresolved_cleanup: dict[int, tuple[str, object, bool]] = {}
        self.__cleanup_in_progress: set[int] = set()
        self.__records: dict[_AttemptHandle, _AttemptRecord] = {}
        self.__active_handle: _AttemptHandle | None = None
        self.__latest_handle: _AttemptHandle | None = None
        self.__context: AuthenticatedProviderContext | None = None
        self.__candidate: _AvailabilityCandidate | None = None
        self.__read_only_capability: (
            AuthenticatedReadOnlyProviderCapability | None
        ) = None
        self.__context_state = AuthenticatedContextState.ABSENT
        self.__availability = ProviderAvailabilityState.NOT_VERIFIED

    def begin_login(self) -> _AttemptHandle:
        """Begin one bounded attempt through listener-ready browser initiation."""

        governed_seconds = self.__governed_before(
            GovernedAuthenticationOperation.ATTEMPT_RESERVATION
        )
        deadline = self.__ordinary_deadline
        remaining_seconds = None
        if deadline is not None:
            deadline.require()
            remaining_seconds = deadline.remaining_seconds()
        helper_pending = (
            self.__helper_deadline is not None
            and self.__helper_deadline.snapshot()["resources_pending"]
        )
        with self.__lock:
            if (self.__active_handle is not None or self.__inflight
                    or self.__unresolved_cleanup or helper_pending):
                raise RuntimeError(AuthenticationFailureCode.ATTEMPT_ALREADY_ACTIVE.value)
            if self.__context_state is AuthenticatedContextState.ACTIVE:
                raise RuntimeError("AUTHENTICATED_CONTEXT_ALREADY_ACTIVE")
            now = self.__aware_now()
            monotonic_started_at = self.__monotonic_clock()
            handle = _AttemptHandle()
            attempt_lifetime = (
                timedelta(seconds=governed_seconds)
                if governed_seconds is not None
                else self.__lifetime
            )
            if remaining_seconds is not None:
                attempt_lifetime = min(
                    attempt_lifetime, timedelta(seconds=remaining_seconds)
                )
            if attempt_lifetime <= timedelta(0):
                raise TimeoutError("CONNECTION_ATTEMPT_TERMINAL")
            attempt = AuthenticationAttempt(
                attempt_id=self.__identity_factory(),
                provider=self.__configuration.provider,
                intended_registration_ref=self.__configuration.intended_registration_ref,
                created_at=now,
                started_at=now,
                expires_at=now + attempt_lifetime,
                listener_ref="LOOPBACK_CALLBACK",
            )
            record = _AttemptRecord(handle, attempt)
            record.monotonic_expires_at = (
                monotonic_started_at + attempt_lifetime.total_seconds()
            )
            self.__records[handle] = record
            self.__active_handle = handle
            self.__latest_handle = handle
            self.__inflight += 1

        try:
            # Authority-neutral helper custody also covers callers without an
            # ordinary runtime deadline. Governed activation proofs stay separate.
            self.__helper_deadline = deadline or ConnectionAttemptDeadline(
                generation=0,
                monotonic_clock=self.__monotonic_clock,
                absolute_expires_at=record.monotonic_expires_at,
            )
            for owner in (self.__navigator, self.__credential_source,
                          self.__binding_verifier):
                bind = getattr(owner, "bind_attempt", None)
                if callable(bind):
                    bind(self.__helper_deadline)
            if deadline is not None:
                deadline.add_terminal_callback(lambda: self.__ordinary_terminal(record))
                attempt_remaining = record.monotonic_expires_at - self.__monotonic_clock()
                if attempt_remaining <= 0:
                    deadline.finish("TIMED_OUT")
                else:
                    deadline.shorten(attempt_remaining)
            if not self.__continue_record(record):
                return handle
            self.__require_governed_budget()
            listener = self.__listener_factory()
            if not self.__adopt_resource(record, "listener", listener):
                self.__dispose_resource("listener", listener)
                return handle
            bind_deadline = getattr(listener, "bind_deadline", None)
            if callable(bind_deadline):
                # The real callback worker inherits the already-running attempt
                # deadline before browser opening or receive_once can block.
                bind_deadline(
                    record.monotonic_expires_at,
                    monotonic_clock=self.__monotonic_clock,
                )
            start = getattr(listener, "start", None)
            if not callable(start):
                raise RuntimeError("CALLBACK_LISTENER_NOT_STARTABLE")
            start()
            if not self.__continue_record(record):
                # start() can finish after cancellation closed the original
                # listener; close the returned owner again before abandoning it.
                if record.listener is not listener:
                    self.__dispose_resource("listener", listener)
                return handle
            if listener.readiness() is not CallbackReadiness.READY:
                raise RuntimeError("CALLBACK_LISTENER_NOT_READY")
            if not self.__transition(record, AuthenticationAttemptState.LISTENER_READY):
                return handle

            adapter_box: list[ProviderAuthenticationAdapter] = []
            with connection_deadline_scope(self.__helper_deadline):
                self.__configuration.use_api_key(
                    lambda api_key: adapter_box.append(self.__adapter_factory(api_key))
                )
            if len(adapter_box) != 1:
                raise RuntimeError("ADAPTER_CONSTRUCTION_INVALID")
            adapter = adapter_box.pop()
            if not self.__adopt_resource(record, "adapter", adapter):
                self.__dispose_resource("adapter", adapter)
                return handle
            login_url = adapter.login_url(self.__configuration.redirect_uri)
            if not self.__transition(record, AuthenticationAttemptState.BROWSER_OPEN_REQUESTED):
                return handle
            browser_result = self.__navigator.open_official_login(BrowserOpenRequest(login_url))
            del login_url
            if not self.__continue_record(record):
                return handle
            if browser_result.category is not BrowserOpenCategory.OPENED:
                self.__cancel_record(record)
                return handle
            self.__transition(record, AuthenticationAttemptState.AWAITING_CALLBACK)
        except Exception:
            if not record.attempt.terminal:
                self.__fail_record(record, AuthenticationFailureCode.LOGIN_INITIATION_FAILED)
        finally:
            if record.attempt.terminal:
                self.__cleanup_record(record, dispose_candidate=True, operations_complete=True)
            with self.__lock:
                self.__inflight -= 1
        return handle

    def complete_callback(self, attempt: object) -> AuthenticationOutcomeEvidence:
        """Complete the first callback and terminalize the attempt exactly once."""

        self.__governed_before(GovernedAuthenticationOperation.TERMINAL_CALLBACK)
        record = self.__record_for(attempt)
        with self.__lock:
            already_terminal = record.terminal_evidence is not None
            if already_terminal:
                operations_complete = self.__inflight == 0
                valid_state = False
            else:
                if record.completion_started:
                    raise RuntimeError("AUTHENTICATION_CALLBACK_ALREADY_IN_PROGRESS")
                valid_state = record.attempt.state is AuthenticationAttemptState.AWAITING_CALLBACK
                if valid_state:
                    record.completion_started = True
                    self.__inflight += 1
        if already_terminal:
            # A timer can terminalize the record between begin returning and
            # callback entry. The terminal result does not release its owners.
            self.__cleanup_record(
                record,
                dispose_candidate=record.attempt.state is not AuthenticationAttemptState.SUCCEEDED,
                operations_complete=operations_complete,
            )
            return self.__required_terminal_evidence(record)
        if not valid_state:
            self.__fail_record(record, AuthenticationFailureCode.INTERNAL_FAILURE)
            return self.__required_terminal_evidence(record)
        try:
            self.__complete_record(record)
        finally:
            self.__cleanup_record(
                record,
                dispose_candidate=record.attempt.state is not AuthenticationAttemptState.SUCCEEDED,
                operations_complete=True,
            )
            with self.__lock:
                self.__inflight -= 1
        return self.__required_terminal_evidence(record)

    def __complete_record(self, record: _AttemptRecord) -> AuthenticationOutcomeEvidence:
        if not self.__continue_record(record):
            return self.__required_terminal_evidence(record)
        listener = record.listener
        if listener is None:
            self.__fail_record(record, AuthenticationFailureCode.INTERNAL_FAILURE)
            return self.__required_terminal_evidence(record)
        try:
            # Preserve the existing wall deadline while preventing a backward
            # wall-clock change from increasing the transport allowance.
            remaining = max(0.0, record.monotonic_expires_at - self.__monotonic_clock())
            callback_deadline = (
                min(record.attempt.expires_at,
                    self.__aware_now() + timedelta(seconds=remaining))
                if self.__ordinary_deadline is not None
                else record.attempt.expires_at
            )
            callback = listener.receive_once(deadline=callback_deadline)
            if not self.__adopt_resource(record, "callback_result", callback):
                self.__dispose_resource("callback", callback)
                return self.__required_terminal_evidence(record)
        except Exception:
            self.__fail_record(record, AuthenticationFailureCode.CALLBACK_REJECTED)
            return self.__required_terminal_evidence(record)
        if not self.__continue_record(record):
            return self.__required_terminal_evidence(record)
        try:
            category = callback.category()
        except Exception:
            self.__fail_record(record, AuthenticationFailureCode.CALLBACK_REJECTED)
            return self.__required_terminal_evidence(record)
        if category is CallbackCategory.TIMED_OUT:
            self.__timeout_record(record, AuthenticationFailureCode.CALLBACK_TIMED_OUT)
            return self.__required_terminal_evidence(record)
        if category is not CallbackCategory.ACCEPTED:
            self.__fail_record(record, AuthenticationFailureCode.CALLBACK_REJECTED)
            return self.__required_terminal_evidence(record)
        if not self.__transition(record, AuthenticationAttemptState.CALLBACK_ACCEPTED):
            return self.__required_terminal_evidence(record)
        try:
            secret_lease = self.__credential_source.acquire(self.__configuration.credential_ref)
            if not self.__adopt_resource(record, "secret_lease", secret_lease):
                self.__dispose_resource("credential", secret_lease)
                return self.__required_terminal_evidence(record)
        except Exception:
            self.__fail_record(record, AuthenticationFailureCode.CREDENTIAL_UNAVAILABLE)
            return self.__required_terminal_evidence(record)
        if not self.__transition(record, AuthenticationAttemptState.EXCHANGING):
            return self.__required_terminal_evidence(record)
        adapter = record.adapter
        if adapter is None:
            self.__fail_record(record, AuthenticationFailureCode.INTERNAL_FAILURE)
            return self.__required_terminal_evidence(record)
        try:
            candidate = callback.consume_request_token(
                lambda token: adapter.exchange_once(token, secret_lease)
            )
        except Exception as error:
            self.__fail_record(record, _exchange_failure(error))
            return self.__required_terminal_evidence(record)
        finally:
            # Cancellation may already have extracted the recorded lease. A
            # late returned/acquired lease still has one local owner here.
            with self.__lock:
                owned_lease = record.secret_lease
                record.secret_lease = None
            if owned_lease is not None:
                self.__dispose_resource("credential", owned_lease)
        try:
            valid_candidate = _candidate_contract(candidate)
        except Exception:
            valid_candidate = False
        if not valid_candidate:
            # An invalid handoff may still own an SDK resource. Failed or absent
            # disposal retains it instead of silently dropping the returned owner.
            self.__dispose_resource("candidate", candidate)
            self.__fail_record(record, AuthenticationFailureCode.INTERNAL_FAILURE)
            return self.__required_terminal_evidence(record)
        with self.__lock:
            record.attempt.candidate_created = True
            # Successful candidate creation transfers SDK custody out of the
            # pre-exchange adapter. Candidate disposal now owns that resource.
            record.adapter = None
        if not self.__adopt_resource(record, "candidate", candidate):
            self.__dispose_candidate(record, candidate)
            return self.__required_terminal_evidence(record)
        if not self.__transition(record, AuthenticationAttemptState.BINDING_PRINCIPAL):
            return self.__required_terminal_evidence(record)
        try:
            evidence = candidate.principal_evidence()
            if not self.__continue_record(record):
                self.__dispose_resource("principal_evidence", evidence)
                return self.__required_terminal_evidence(record)
            binding = self.__binding_verifier.verify_principal_binding(
                evidence, self.__configuration.intended_registration_ref
            )
        except Exception as error:
            self.__fail_record(record, _principal_failure(error))
            return self.__required_terminal_evidence(record)
        if not self.__continue_record(record):
            return self.__required_terminal_evidence(record)
        with self.__lock:
            record.attempt.binding_result = binding
        if binding is not PrincipalBindingResult.MATCHED:
            self.__fail_record(record, _binding_failure(binding))
            return self.__required_terminal_evidence(record)
        try:
            self.__governed_before(GovernedAuthenticationOperation.CONTEXT_ESTABLISHMENT)
            context = AuthenticatedProviderContext(
                validity=ContextValidity.VALID,
                reuse_eligibility=ContextReuseEligibility.ELIGIBLE,
                provider=self.__configuration.provider,
                context_id=record.attempt.attempt_id,
                attempt_id=record.attempt.attempt_id,
                binding_result=PrincipalBindingResult.MATCHED,
            )
            if not self.__continue_record(record):
                return self.__required_terminal_evidence(record)
            read_only_capability = candidate.issue_read_only_capability()
            if not _read_only_capability_contract(read_only_capability):
                raise TypeError
            deadline = self.__ordinary_deadline
            with (deadline.guard() if deadline is not None else nullcontext()):
                with self.__lock:
                    if record.attempt.terminal:
                        return self.__required_terminal_evidence(record)
                    now = self.__aware_now()
                    if self.__record_expired_locked(record, now):
                        self.__mark_terminal_locked(
                            record, AuthenticationAttemptState.TIMED_OUT,
                            AuthenticationFailureCode.ATTEMPT_TIMED_OUT,
                        )
                    else:
                        retain = getattr(candidate, "retain_session", None)
                        if callable(retain):
                            retain()
                        record.attempt.transition(AuthenticationAttemptState.SUCCEEDED, at=now)
                        self.__context = context
                        self.__candidate = candidate  # type: ignore[assignment]
                        self.__read_only_capability = read_only_capability
                        self.__context_state = AuthenticatedContextState.ACTIVE
                        self.__availability = ProviderAvailabilityState.NOT_VERIFIED
                        record.candidate = None
                        self.__finalize_record(record)
        except Exception:
            self.__fail_record(record, AuthenticationFailureCode.INTERNAL_FAILURE)
        return self.__required_terminal_evidence(record)

    def cancel_authentication_attempt(
        self,
        attempt: object,
    ) -> AuthenticationAttemptCancellationResult:
        record = self.__lookup_record(attempt)
        if record is None:
            return AuthenticationAttemptCancellationResult.NO_ACTIVE_ATTEMPT
        if record.attempt.state is AuthenticationAttemptState.CANCELLED:
            return AuthenticationAttemptCancellationResult.ALREADY_CANCELLED
        if record.attempt.terminal:
            return AuthenticationAttemptCancellationResult.ALREADY_TERMINAL
        self.__cancel_record(record)
        return AuthenticationAttemptCancellationResult.CANCELLED

    def verify_provider_availability(self) -> ProviderAvailabilityState:
        """Perform one explicit availability operation without changing attempt."""

        if self.__governed:
            raise RuntimeError("PROVIDER_AVAILABILITY_VERIFICATION_WITHHELD")

        with self.__lock:
            candidate = self.__candidate
            if (
                candidate is None
                or self.__context_state is not AuthenticatedContextState.ACTIVE
            ):
                self.__availability = ProviderAvailabilityState.INDETERMINATE
                return self.__availability
            if self.__availability is ProviderAvailabilityState.VERIFYING:
                return self.__availability
            self.__availability = ProviderAvailabilityState.VERIFYING

        verify = getattr(candidate, "verify_provider_availability", None)
        if not callable(verify):
            with self.__lock:
                self.__availability = ProviderAvailabilityState.INDETERMINATE
                return self.__availability
        try:
            result = verify()
        except Exception as error:
            code = error.code if isinstance(error, ProviderConnectivityError) else None
            if code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED:
                return self.__expire_context(candidate)
            with self.__lock:
                if (
                    self.__candidate is not candidate
                    or self.__context_state is not AuthenticatedContextState.ACTIVE
                ):
                    return self.__availability
                self.__availability = (
                    ProviderAvailabilityState.UNAVAILABLE
                    if _provider_unavailable_code(code)
                    else ProviderAvailabilityState.INDETERMINATE
                )
                return self.__availability

        category = getattr(result, "name", None) or getattr(result, "value", None)
        if category in {"VALID", "CONTEXT_VALID"}:
            with self.__lock:
                if (
                    self.__candidate is not candidate
                    or self.__context_state is not AuthenticatedContextState.ACTIVE
                ):
                    return self.__availability
                self.__availability = ProviderAvailabilityState.AVAILABLE
                return self.__availability
        if category in {"INVALID", "CONTEXT_INVALID"}:
            return self.__expire_context(candidate)
        if category in {
            "UNAVAILABLE",
            "PROVIDER_OPERATIONALLY_UNAVAILABLE",
        }:
            with self.__lock:
                if (
                    self.__candidate is not candidate
                    or self.__context_state is not AuthenticatedContextState.ACTIVE
                ):
                    return self.__availability
                self.__availability = ProviderAvailabilityState.UNAVAILABLE
                return self.__availability
        with self.__lock:
            if (
                self.__candidate is not candidate
                or self.__context_state is not AuthenticatedContextState.ACTIVE
            ):
                return self.__availability
            self.__availability = ProviderAvailabilityState.INDETERMINATE
            return self.__availability

    def session_status(self) -> SessionStatus:
        with self.__lock:
            record = (
                self.__records.get(self.__latest_handle)
                if self.__latest_handle is not None
                else None
            )
            return SessionStatus(
                attempt_state=record.attempt.state if record is not None else None,
                context_state=self.__context_state,
                provider_availability=self.__availability,
                failure_code=(
                    record.attempt.terminal_code if record is not None else None
                ),
                attempt_active=(
                    record is not None and not record.attempt.terminal
                ),
                context_reusable=(
                    self.__context_state is AuthenticatedContextState.ACTIVE
                ),
            )

    def authentication_attempt_status(
        self,
        attempt: object,
    ) -> AuthenticationOutcomeEvidence | None:
        record = self.__lookup_record(attempt)
        if record is None:
            return None
        if record.terminal_evidence is not None:
            return record.terminal_evidence
        return record.attempt.sanitized_evidence(completed_at=self.__aware_now())

    def current_context(self) -> AuthenticatedProviderContext | None:
        """Return only the sanitized context projection, never its candidate."""

        deadline = self.__ordinary_deadline
        if deadline is not None:
            try:
                deadline.require()
            except TimeoutError:
                return None
        return self.__context

    def authenticated_read_only_capability(
        self,
    ) -> AuthenticatedReadOnlyProviderCapability | None:
        """Return only the matched, active opaque capability handoff."""

        deadline = self.__ordinary_deadline
        if deadline is not None:
            try:
                deadline.require()
            except TimeoutError:
                return None
        with self.__lock:
            capability = self.__read_only_capability
            if (
                capability is None
                or self.__context_state is not AuthenticatedContextState.ACTIVE
                or not capability.active
            ):
                return None
            return capability

    @contextmanager
    def __local_cleanup_operation(self):
        """Fence admission before extracting an owner for local disposal."""

        deadline = self.__ordinary_deadline
        owner = object()
        guard = deadline._cleanup_guard() if deadline is not None else nullcontext()
        with guard:
            with self.__lock:
                operations_complete = self.__inflight == 0
                self.__inflight += 1
                if deadline is not None:
                    deadline.hold_resource("LOCAL_CLEANUP", owner)
        try:
            yield operations_complete
        finally:
            guard = deadline._cleanup_guard() if deadline is not None else nullcontext()
            with guard:
                with self.__lock:
                    self.__inflight -= 1
                    if deadline is not None:
                        deadline._resolve_pending_resource(owner)

    def end_kronos_session(self) -> None:
        """End and dispose the local context without a Provider mutation."""

        with self.__local_cleanup_operation() as operations_complete:
            self.__record_governed_cleanup_once()

            with self.__lock:
                pending_cleanup = tuple(
                    (name, resource)
                    for name, resource, pending in self.__unresolved_cleanup.values()
                    if pending and name in {"adapter", "candidate", "listener"}
                )
                record = self.__records.get(self.__latest_handle)
                if record is not None and not record.attempt.terminal:
                    self.__mark_terminal_locked(
                        record, AuthenticationAttemptState.CANCELLED, None
                    )
                candidate = self.__candidate
                context = self.__context
                self.__candidate = None
                self.__read_only_capability = None
                self.__availability = ProviderAvailabilityState.NOT_VERIFIED
                if context is not None:
                    self.__context_state = AuthenticatedContextState.ENDED
                    self.__context = AuthenticatedProviderContext(
                        validity=ContextValidity.TERMINATED,
                        reuse_eligibility=ContextReuseEligibility.INELIGIBLE,
                        provider=context.provider,
                        context_id=context.context_id,
                        provenance=context.provenance,
                        valid_until=context.valid_until,
                        attempt_id=context.attempt_id,
                        binding_result=context.binding_result,
                    )
                elif self.__context_state is not AuthenticatedContextState.ENDED:
                    self.__context_state = AuthenticatedContextState.ABSENT
            if record is not None:
                if record.attempt.state is not AuthenticationAttemptState.SUCCEEDED:
                    self.__finish_ordinary(
                        "TIMED_OUT" if record.attempt.state is AuthenticationAttemptState.TIMED_OUT
                        else "CANCELLED"
                    )
                # End also owns a terminal attempt's still-retained resources. This
                # covers expiry between begin returning and callback entry.
                self.__cleanup_record(
                    record, dispose_candidate=True,
                    operations_complete=operations_complete,
                )
            if candidate is not None:
                self.__dispose_resource("candidate", candidate)

            # An explicit later End may finish disposal after an SDK read drains.
            # FAILED owners are never selected for another external close attempt.
            for name, resource in pending_cleanup:
                self.__dispose_resource(name, resource)

    def __record_for(self, attempt: object) -> _AttemptRecord:
        record = self.__lookup_record(attempt)
        if record is None:
            raise RuntimeError("AUTHENTICATION_ATTEMPT_HANDLE_UNKNOWN")
        return record

    def __lookup_record(self, attempt: object) -> _AttemptRecord | None:
        try:
            record = self.__records.get(attempt)  # type: ignore[arg-type]
        except TypeError:
            record = None
        return record

    def __record_expired_locked(self, record: _AttemptRecord, now: datetime) -> bool:
        return (
            now >= record.attempt.expires_at
            or self.__monotonic_clock() >= record.monotonic_expires_at
        )

    def __continue_record(self, record: _AttemptRecord) -> bool:
        deadline = self.__ordinary_deadline
        if deadline is not None:
            try:
                deadline.require()
            except TimeoutError:
                self.__ordinary_terminal(record)
        with self.__lock:
            if record.attempt.terminal:
                return False
            expired = self.__record_expired_locked(record, self.__aware_now())
        if expired:
            self.__timeout_record(record, AuthenticationFailureCode.ATTEMPT_TIMED_OUT)
            return False
        return True

    def __adopt_resource(self, record: _AttemptRecord, attribute: str, resource: object) -> bool:
        self.__continue_record(record)
        with self.__lock:
            if record.attempt.terminal:
                return False
            setattr(record, attribute, resource)
            return True

    def __ordinary_terminal(self, record: _AttemptRecord) -> None:
        """Timer callback: mark state only; the worker retains cleanup custody."""

        deadline = self.__ordinary_deadline
        if deadline is None:
            return
        state = deadline.snapshot()["state"]
        if state in {"ACTIVE", "SUCCEEDED"}:
            return
        with self.__lock:
            if record.attempt.terminal:
                return
            if state == "CANCELLED":
                target = AuthenticationAttemptState.CANCELLED
                failure = None
            elif state == "TIMED_OUT":
                target = AuthenticationAttemptState.TIMED_OUT
                failure = AuthenticationFailureCode.ATTEMPT_TIMED_OUT
            else:
                target = AuthenticationAttemptState.FAILED
                failure = AuthenticationFailureCode.INTERNAL_FAILURE
            self.__mark_terminal_locked(record, target, failure)

    def __transition(self, record: _AttemptRecord, state: AuthenticationAttemptState) -> bool:
        if not self.__continue_record(record):
            return False
        with self.__lock:
            if record.attempt.terminal:
                return False
            now = self.__aware_now()
            if self.__record_expired_locked(record, now):
                self.__mark_terminal_locked(
                    record, AuthenticationAttemptState.TIMED_OUT,
                    AuthenticationFailureCode.ATTEMPT_TIMED_OUT,
                )
                expired = True
            else:
                record.attempt.transition(state, at=now)
                expired = False
        if expired:
            self.__finish_ordinary("TIMED_OUT")
            self.__cleanup_record(record, dispose_candidate=True)
            return False
        return True

    def __mark_terminal_locked(
        self,
        record: _AttemptRecord,
        state: AuthenticationAttemptState,
        failure: AuthenticationFailureCode | None,
    ) -> None:
        if record.attempt.terminal:
            return
        # This optional callback seam only invalidates local state/token
        # carriers. It must never perform socket work or join a worker.
        for owner in (record.listener, self.__navigator):
            invalidate = getattr(owner, "invalidate_pending", None)
            if callable(invalidate):
                invalidate()
        now = self.__aware_now()
        expired = self.__record_expired_locked(record, now)
        if state is AuthenticationAttemptState.TIMED_OUT or expired:
            if state is not AuthenticationAttemptState.TIMED_OUT or failure is None:
                failure = AuthenticationFailureCode.ATTEMPT_TIMED_OUT
            state = AuthenticationAttemptState.TIMED_OUT
            # The public aggregate retains its wall-clock compatibility deadline.
            # A monotonic expiry can occur before that wall clock reaches it.
            now = max(now, record.attempt.expires_at)
        record.attempt.transition(state, at=now, failure_code=failure)
        self.__finalize_record(record)

    def __finish_ordinary(self, state: str) -> None:
        deadline = self.__ordinary_deadline
        if deadline is not None:
            deadline.finish(state)
        helper_deadline = self.__helper_deadline
        if helper_deadline is not None and helper_deadline is not deadline:
            helper_deadline.finish(state)

    def __fail_record(self, record: _AttemptRecord, failure: AuthenticationFailureCode) -> None:
        with self.__local_cleanup_operation() as operations_complete:
            with self.__lock:
                if record.attempt.terminal:
                    return
                expired = self.__record_expired_locked(record, self.__aware_now())
                self.__mark_terminal_locked(
                    record,
                    AuthenticationAttemptState.TIMED_OUT if expired else AuthenticationAttemptState.FAILED,
                    AuthenticationFailureCode.ATTEMPT_TIMED_OUT if expired else failure,
                )
            self.__finish_ordinary("TIMED_OUT" if expired else "FAILED")
            self.__cleanup_record(
                record, dispose_candidate=True, operations_complete=operations_complete,
            )

    def __timeout_record(self, record: _AttemptRecord, failure: AuthenticationFailureCode) -> None:
        with self.__local_cleanup_operation() as operations_complete:
            with self.__lock:
                if record.attempt.terminal:
                    return
                self.__mark_terminal_locked(record, AuthenticationAttemptState.TIMED_OUT, failure)
            self.__finish_ordinary("TIMED_OUT")
            self.__cleanup_record(
                record, dispose_candidate=True, operations_complete=operations_complete,
            )

    def __cancel_record(self, record: _AttemptRecord) -> None:
        with self.__local_cleanup_operation() as operations_complete:
            with self.__lock:
                if record.attempt.terminal:
                    return
                expired = self.__record_expired_locked(record, self.__aware_now())
                self.__mark_terminal_locked(
                    record,
                    AuthenticationAttemptState.TIMED_OUT if expired else AuthenticationAttemptState.CANCELLED,
                    AuthenticationFailureCode.ATTEMPT_TIMED_OUT if expired else None,
                )
            self.__finish_ordinary("TIMED_OUT" if expired else "CANCELLED")
            self.__cleanup_record(
                record, dispose_candidate=True, operations_complete=operations_complete,
            )

    def __finalize_record(self, record: _AttemptRecord) -> None:
        if record.terminal_evidence is None:
            record.terminal_evidence = record.attempt.sanitized_evidence(completed_at=self.__aware_now())
        if self.__active_handle is record.handle:
            self.__active_handle = None

    def __cleanup_record(
        self,
        record: _AttemptRecord,
        *,
        dispose_candidate: bool,
        operations_complete: bool = False,
    ) -> None:
        self.__record_governed_cleanup_once()
        # Extract under a short lock. A concurrently returned late resource is
        # either rejected by adoption or taken by the worker's final cleanup.
        with self.__lock:
            callback = record.callback_result
            record.callback_result = None
            lease = record.secret_lease
            record.secret_lease = None
            listener = record.listener
            record.listener = None
            candidate = record.candidate if dispose_candidate else None
            if candidate is not None:
                record.candidate = None
            adapter = None
            if operations_complete or not self.__inflight:
                adapter = record.adapter
                record.adapter = None
        if callback is not None:
            self.__dispose_resource("callback", callback)
        if lease is not None:
            self.__dispose_resource("credential", lease)
        if listener is not None:
            disposed = self.__dispose_resource("listener", listener)
            if not disposed:
                with self.__lock:
                    unresolved = self.__unresolved_cleanup.get(id(listener))
                    if unresolved is not None and unresolved[2] and record.listener is None:
                        record.listener = listener
        if candidate is not None:
            self.__dispose_candidate(record, candidate)
        if adapter is not None and not record.attempt.candidate_created:
            self.__dispose_resource("adapter", adapter)

    def __dispose_candidate(self, record: _AttemptRecord, candidate: object) -> None:
        disposed = self.__dispose_resource("candidate", candidate)
        with self.__lock:
            if disposed:
                record.attempt.candidate_disposed = True
            else:
                unresolved = self.__unresolved_cleanup.get(id(candidate))
                if unresolved is not None and unresolved[2] and record.candidate is None:
                    # An SDK operation still owns this resource. The returning
                    # worker's final cleanup continues disposal after it drains.
                    record.candidate = candidate
            if record.terminal_evidence is not None:
                record.terminal_evidence = record.attempt.sanitized_evidence(
                    completed_at=record.terminal_evidence.completed_at
                )

    def __dispose_resource(self, name: str, resource: object) -> bool:
        deadline = self.__ordinary_deadline
        identity = id(resource)
        # Publication takes deadline then service; ownership accounting uses
        # that same order. Publish custody BEFORE entering a possibly blocked
        # physical close, so no new attempt can accumulate behind that call.
        guard = deadline._cleanup_guard() if deadline is not None else nullcontext()
        with guard:
            with self.__lock:
                previous = self.__unresolved_cleanup.get(identity)
                if previous is not None and not previous[2]:
                    return False
                if identity in self.__cleanup_in_progress:
                    return False
                was_pending = previous is not None
                self.__unresolved_cleanup[identity] = (name, resource, True)
                self.__cleanup_in_progress.add(identity)
                if deadline is not None:
                    deadline.hold_resource(name.upper(), resource)

        method_name = "dispose_local" if name in {"adapter", "candidate"} else "close"
        succeeded = False
        try:
            method = getattr(resource, method_name, None)
            if callable(method):
                method()
                if name == "listener":
                    category = getattr(resource, "cleanup_category", None)
                    if callable(category):
                        result = category()
                        if getattr(result, "value", result) != "SUCCESS":
                            raise RuntimeError("CALLBACK_CLEANUP_UNCONFIRMED")
                succeeded = True
        except Exception:
            pass
        guard = deadline._cleanup_guard() if deadline is not None else nullcontext()
        with guard:
            with self.__lock:
                cleanup_state = None
                if name in {"adapter", "candidate", "listener"}:
                    try:
                        cleanup_state = getattr(resource, "local_cleanup_state", None)
                    except Exception:
                        pass
                self.__cleanup_in_progress.remove(identity)
                # A concurrent direct close can finish after a PENDING call
                # raises; COMPLETE confirms physical cleanup in that race.
                if cleanup_state == "COMPLETE":
                    succeeded = True
                elif cleanup_state in {"PENDING", "FAILED"}:
                    succeeded = False
                elif was_pending:
                    succeeded = False
                if succeeded:
                    del self.__unresolved_cleanup[identity]
                    if deadline is not None:
                        deadline._resolve_pending_resource(resource)
                    return True
                self.__unresolved_cleanup[identity] = (
                    name, resource, cleanup_state == "PENDING"
                )
                return False

    def __required_terminal_evidence(
        self,
        record: _AttemptRecord,
    ) -> AuthenticationOutcomeEvidence:
        evidence = record.terminal_evidence
        if evidence is None:
            raise RuntimeError("AUTHENTICATION_ATTEMPT_NOT_TERMINAL")
        return evidence

    def __expire_context(
        self,
        expected_candidate: _AvailabilityCandidate,
    ) -> ProviderAvailabilityState:
        with self.__local_cleanup_operation():
            with self.__lock:
                if (
                    self.__candidate is not expected_candidate
                    or self.__context_state is not AuthenticatedContextState.ACTIVE
                ):
                    return self.__availability
                context = self.__context
                candidate = self.__candidate
                self.__candidate = None
                self.__read_only_capability = None
                self.__context_state = AuthenticatedContextState.EXPIRED
                self.__availability = ProviderAvailabilityState.INDETERMINATE
                if context is not None:
                    self.__context = AuthenticatedProviderContext(
                        validity=ContextValidity.INVALID,
                        reuse_eligibility=ContextReuseEligibility.INELIGIBLE,
                        provider=context.provider,
                        context_id=context.context_id,
                        provenance=context.provenance,
                        valid_until=context.valid_until,
                        attempt_id=context.attempt_id,
                        binding_result=context.binding_result,
                    )
                availability = self.__availability
            if candidate is not None:
                self.__dispose_resource("candidate", candidate)
            return availability

    def __aware_now(self) -> datetime:
        now = self.__clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("AUTHENTICATION_CLOCK_MUST_BE_TIMEZONE_AWARE")
        return now

    def __governed_before(
        self,
        operation: GovernedAuthenticationOperation,
    ) -> float | None:
        seconds = self.__require_governed_budget()
        if seconds is None:
            return None
        recorder = self.__operation_recorder
        if recorder is None:
            raise RuntimeError("GOVERNED_OPERATION_LEDGER_UNAVAILABLE")
        try:
            recorder.record(operation)
        except Exception:
            raise RuntimeError("GOVERNED_OPERATION_CARDINALITY_REJECTED") from None
        return seconds

    def __require_governed_budget(self) -> float | None:
        if not self.__governed:
            return None
        if type(self.__proven_consumption) is not ProvenConsumption:
            raise RuntimeError("GOVERNED_CONSUMPTION_PROOF_UNAVAILABLE")
        supplier = self.__remaining_budget
        if supplier is None:
            raise RuntimeError("GOVERNED_DEADLINE_UNAVAILABLE")
        try:
            budget = supplier()
            if type(budget) is not RemainingBudget:
                raise TypeError
            return budget.require_available()
        except Exception:
            raise RuntimeError("GOVERNED_DEADLINE_EXHAUSTED") from None

    def __record_governed_cleanup_once(self) -> None:
        if not self.__governed or self.__governed_cleanup_recorded:
            return
        self.__governed_cleanup_recorded = True
        recorder = self.__operation_recorder
        if recorder is None:
            return
        try:
            recorder.record(GovernedAuthenticationOperation.LOCAL_CLEANUP)
        except Exception:
            return


def _candidate_contract(candidate: object) -> bool:
    return (
        callable(getattr(candidate, "principal_evidence", None))
        and callable(getattr(candidate, "issue_read_only_capability", None))
        and callable(getattr(candidate, "dispose_local", None))
    )


def _read_only_capability_contract(capability: object) -> bool:
    try:
        return (
            capability.operations == frozenset(ReadOnlyProviderOperation)
            and capability.active is True
            and not any(
                hasattr(capability, name)
                for name in (
                    "api_secret",
                    "access_token",
                    "client",
                    "sdk_client",
                    "place_order",
                    "modify_order",
                    "cancel_order",
                )
            )
        )
    except Exception:
        return False


def _exchange_failure(error: Exception) -> AuthenticationFailureCode:
    if isinstance(error, ProviderConnectivityError):
        if error.code is ProviderErrorCode.AUTHENTICATION_REJECTED:
            return AuthenticationFailureCode.TOKEN_EXCHANGE_REJECTED
        if error.code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED:
            return AuthenticationFailureCode.ACCESS_TOKEN_INVALID_OR_EXPIRED
        if _provider_unavailable_code(error.code):
            return AuthenticationFailureCode.TOKEN_EXCHANGE_UNAVAILABLE
    return AuthenticationFailureCode.INTERNAL_FAILURE


def _principal_failure(error: Exception) -> AuthenticationFailureCode:
    if (
        isinstance(error, ProviderConnectivityError)
        and error.code is ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED
    ):
        return AuthenticationFailureCode.ACCESS_TOKEN_INVALID_OR_EXPIRED
    return AuthenticationFailureCode.PRINCIPAL_BINDING_UNAVAILABLE


def _binding_failure(binding: PrincipalBindingResult) -> AuthenticationFailureCode:
    return {
        PrincipalBindingResult.MISMATCHED: AuthenticationFailureCode.PRINCIPAL_MISMATCHED,
        PrincipalBindingResult.UNCONFIRMED: AuthenticationFailureCode.PRINCIPAL_UNCONFIRMED,
        PrincipalBindingResult.UNAVAILABLE: (
            AuthenticationFailureCode.PRINCIPAL_BINDING_UNAVAILABLE
        ),
    }.get(binding, AuthenticationFailureCode.INTERNAL_FAILURE)


def _provider_unavailable_code(code: ProviderErrorCode | None) -> bool:
    return code in {
        ProviderErrorCode.NETWORK_TIMEOUT,
        ProviderErrorCode.CONNECTION_FAILURE,
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.PROVIDER_SERVICE_FAILURE,
    }


__all__ = [
    "ConnectionAttemptDeadline",
    "connection_deadline_scope",
    "current_connection_deadline",
    "ProtectedPrincipalBindingVerifier",
    "ProviderAuthenticationService",
]
