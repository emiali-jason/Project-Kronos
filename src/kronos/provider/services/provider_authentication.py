"""Sole provider-neutral authentication and context lifecycle coordinator."""

from __future__ import annotations

import threading
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
    AuthenticationCallbackListener,
    LoginNavigator,
    ProviderAuthenticationAdapter,
    ProviderCandidateContext,
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
        "secret_lease",
        "terminal_evidence",
    )

    def __init__(self, handle: _AttemptHandle, attempt: AuthenticationAttempt) -> None:
        self.handle = handle
        self.attempt = attempt
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

    __slots__ = ("__resolver",)

    def __init__(self, resolver: IntendedPrincipalResolver) -> None:
        self.__resolver = resolver

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
                pass

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
        "__operation_recorder",
        "__proven_consumption",
        "__remaining_budget",
        "__governed",
        "__governed_cleanup_recorded",
        "__records",
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
        self.__configuration = configuration
        self.__credential_source = credential_source
        self.__binding_verifier = ProtectedPrincipalBindingVerifier(
            principal_resolver
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
        self.__records: dict[_AttemptHandle, _AttemptRecord] = {}
        self.__active_handle: _AttemptHandle | None = None
        self.__latest_handle: _AttemptHandle | None = None
        self.__context: AuthenticatedProviderContext | None = None
        self.__candidate: _AvailabilityCandidate | None = None
        self.__context_state = AuthenticatedContextState.ABSENT
        self.__availability = ProviderAvailabilityState.NOT_VERIFIED

    def begin_login(self) -> _AttemptHandle:
        """Begin one bounded attempt through listener-ready browser initiation."""

        governed_seconds = self.__governed_before(
            GovernedAuthenticationOperation.ATTEMPT_RESERVATION
        )
        with self.__lock:
            if self.__active_handle is not None:
                raise RuntimeError(AuthenticationFailureCode.ATTEMPT_ALREADY_ACTIVE.value)
            if self.__context_state is AuthenticatedContextState.ACTIVE:
                raise RuntimeError("AUTHENTICATED_CONTEXT_ALREADY_ACTIVE")
            now = self.__aware_now()
            handle = _AttemptHandle()
            attempt_lifetime = (
                timedelta(seconds=governed_seconds)
                if governed_seconds is not None
                else self.__lifetime
            )
            attempt = AuthenticationAttempt(
                attempt_id=self.__identity_factory(),
                provider=self.__configuration.provider,
                intended_registration_ref=(
                    self.__configuration.intended_registration_ref
                ),
                created_at=now,
                started_at=now,
                expires_at=now + attempt_lifetime,
                listener_ref="LOOPBACK_CALLBACK",
            )
            record = _AttemptRecord(handle, attempt)
            self.__records[handle] = record
            self.__active_handle = handle
            self.__latest_handle = handle

        try:
            self.__require_governed_budget()
            listener = self.__listener_factory()
            start = getattr(listener, "start", None)
            if not callable(start):
                raise RuntimeError("CALLBACK_LISTENER_NOT_STARTABLE")
            record.listener = listener  # type: ignore[assignment]
            start()
            if listener.readiness() is not CallbackReadiness.READY:
                raise RuntimeError("CALLBACK_LISTENER_NOT_READY")
            if not self.__transition(
                record,
                AuthenticationAttemptState.LISTENER_READY,
            ):
                return handle

            adapter_box: list[ProviderAuthenticationAdapter] = []
            self.__configuration.use_api_key(
                lambda api_key: adapter_box.append(self.__adapter_factory(api_key))
            )
            if len(adapter_box) != 1:
                raise RuntimeError("ADAPTER_CONSTRUCTION_INVALID")
            adapter = adapter_box.pop()
            record.adapter = adapter
            login_url = adapter.login_url(self.__configuration.redirect_uri)
            if not self.__transition(
                record,
                AuthenticationAttemptState.BROWSER_OPEN_REQUESTED,
            ):
                return handle
            browser_result = self.__navigator.open_official_login(
                BrowserOpenRequest(login_url)
            )
            if browser_result.category is not BrowserOpenCategory.OPENED:
                self.__cancel_record(record)
                return handle
            self.__transition(record, AuthenticationAttemptState.AWAITING_CALLBACK)
        except Exception:
            if not record.attempt.terminal:
                self.__fail_record(
                    record,
                    AuthenticationFailureCode.LOGIN_INITIATION_FAILED,
                )
        return handle

    def complete_callback(
        self,
        attempt: object,
    ) -> AuthenticationOutcomeEvidence:
        """Complete the first callback and terminalize the attempt exactly once."""

        self.__governed_before(GovernedAuthenticationOperation.TERMINAL_CALLBACK)
        record = self.__record_for(attempt)
        with self.__lock:
            if record.terminal_evidence is not None:
                return record.terminal_evidence
            if record.completion_started:
                raise RuntimeError("AUTHENTICATION_CALLBACK_ALREADY_IN_PROGRESS")
            if record.attempt.state is not AuthenticationAttemptState.AWAITING_CALLBACK:
                self.__fail_record(record, AuthenticationFailureCode.INTERNAL_FAILURE)
                return self.__required_terminal_evidence(record)
            record.completion_started = True

        listener = record.listener
        if listener is None:
            self.__fail_record(record, AuthenticationFailureCode.INTERNAL_FAILURE)
            return self.__required_terminal_evidence(record)

        try:
            callback = listener.receive_once(deadline=record.attempt.expires_at)
            record.callback_result = callback
        except Exception:
            self.__fail_record(record, AuthenticationFailureCode.CALLBACK_REJECTED)
            return self.__required_terminal_evidence(record)

        if record.attempt.terminal:
            self.__cleanup_record(record, dispose_candidate=True)
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

        if not self.__transition(
            record,
            AuthenticationAttemptState.CALLBACK_ACCEPTED,
        ):
            return self.__required_terminal_evidence(record)
        try:
            secret_lease = self.__credential_source.acquire(
                self.__configuration.credential_ref
            )
            record.secret_lease = secret_lease
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
            try:
                secret_lease.close()
            except Exception:
                pass
            record.secret_lease = None

        if record.attempt.terminal:
            if _candidate_contract(candidate):
                record.candidate = candidate
                record.attempt.candidate_created = True
                self.__cleanup_record(record, dispose_candidate=True)
            return self.__required_terminal_evidence(record)

        if not _candidate_contract(candidate):
            self.__fail_record(record, AuthenticationFailureCode.INTERNAL_FAILURE)
            return self.__required_terminal_evidence(record)
        record.candidate = candidate
        record.attempt.candidate_created = True
        if not self.__transition(
            record,
            AuthenticationAttemptState.BINDING_PRINCIPAL,
        ):
            return self.__required_terminal_evidence(record)

        try:
            evidence = candidate.principal_evidence()
            binding = self.__binding_verifier.verify_principal_binding(
                evidence,
                self.__configuration.intended_registration_ref,
            )
        except Exception as error:
            self.__fail_record(record, _principal_failure(error))
            return self.__required_terminal_evidence(record)

        if record.attempt.terminal:
            self.__cleanup_record(record, dispose_candidate=True)
            return self.__required_terminal_evidence(record)

        record.attempt.binding_result = binding
        if binding is not PrincipalBindingResult.MATCHED:
            self.__fail_record(record, _binding_failure(binding))
            return self.__required_terminal_evidence(record)

        try:
            self.__governed_before(
                GovernedAuthenticationOperation.CONTEXT_ESTABLISHMENT
            )
            context = AuthenticatedProviderContext(
                validity=ContextValidity.VALID,
                reuse_eligibility=ContextReuseEligibility.ELIGIBLE,
                provider=self.__configuration.provider,
                context_id=record.attempt.attempt_id,
                attempt_id=record.attempt.attempt_id,
                binding_result=PrincipalBindingResult.MATCHED,
            )
            transitioned = self.__transition(
                record,
                AuthenticationAttemptState.SUCCEEDED,
            )
        except Exception:
            self.__fail_record(record, AuthenticationFailureCode.INTERNAL_FAILURE)
            return self.__required_terminal_evidence(record)
        if not transitioned:
            self.__cleanup_record(record, dispose_candidate=True)
            return self.__required_terminal_evidence(record)

        with self.__lock:
            self.__context = context
            self.__candidate = candidate  # type: ignore[assignment]
            self.__context_state = AuthenticatedContextState.ACTIVE
            self.__availability = ProviderAvailabilityState.NOT_VERIFIED
            record.candidate = None
            self.__finalize_record(record)
        self.__cleanup_record(record, dispose_candidate=False)
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

        return self.__context

    def end_kronos_session(self) -> None:
        """End and dispose the local context without a Provider mutation."""

        self.__record_governed_cleanup_once()

        with self.__lock:
            candidate = self.__candidate
            context = self.__context
            self.__candidate = None
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
        if candidate is not None:
            try:
                candidate.dispose_local()
            except Exception:
                pass

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

    def __transition(
        self,
        record: _AttemptRecord,
        state: AuthenticationAttemptState,
    ) -> bool:
        with self.__lock:
            if record.attempt.terminal:
                return False
            now = self.__aware_now()
            if now >= record.attempt.expires_at:
                self.__timeout_record(
                    record,
                    AuthenticationFailureCode.ATTEMPT_TIMED_OUT,
                )
                return False
            record.attempt.transition(state, at=now)
            return record.attempt.state is state

    def __fail_record(
        self,
        record: _AttemptRecord,
        failure: AuthenticationFailureCode,
    ) -> None:
        with self.__lock:
            if record.attempt.terminal:
                return
            now = self.__aware_now()
            if now >= record.attempt.expires_at:
                record.attempt.transition(
                    AuthenticationAttemptState.TIMED_OUT,
                    at=now,
                    failure_code=AuthenticationFailureCode.ATTEMPT_TIMED_OUT,
                )
            else:
                record.attempt.transition(
                    AuthenticationAttemptState.FAILED,
                    at=now,
                    failure_code=failure,
                )
            self.__finalize_record(record)
        self.__cleanup_record(record, dispose_candidate=True)

    def __timeout_record(
        self,
        record: _AttemptRecord,
        failure: AuthenticationFailureCode,
    ) -> None:
        with self.__lock:
            if record.attempt.terminal:
                return
            now = max(self.__aware_now(), record.attempt.expires_at)
            record.attempt.transition(
                AuthenticationAttemptState.TIMED_OUT,
                at=now,
                failure_code=failure,
            )
            self.__finalize_record(record)
        self.__cleanup_record(record, dispose_candidate=True)

    def __cancel_record(self, record: _AttemptRecord) -> None:
        with self.__lock:
            if record.attempt.terminal:
                return
            now = self.__aware_now()
            if now >= record.attempt.expires_at:
                record.attempt.transition(
                    AuthenticationAttemptState.TIMED_OUT,
                    at=now,
                    failure_code=AuthenticationFailureCode.ATTEMPT_TIMED_OUT,
                )
            else:
                record.attempt.transition(
                    AuthenticationAttemptState.CANCELLED,
                    at=now,
                )
            self.__finalize_record(record)
        self.__cleanup_record(record, dispose_candidate=True)

    def __finalize_record(self, record: _AttemptRecord) -> None:
        if record.terminal_evidence is None:
            record.terminal_evidence = record.attempt.sanitized_evidence(
                completed_at=self.__aware_now()
            )
        if self.__active_handle is record.handle:
            self.__active_handle = None

    def __cleanup_record(
        self,
        record: _AttemptRecord,
        *,
        dispose_candidate: bool,
    ) -> None:
        self.__record_governed_cleanup_once()
        callback = record.callback_result
        record.callback_result = None
        if callback is not None:
            try:
                callback.close()
            except Exception:
                pass
        lease = record.secret_lease
        record.secret_lease = None
        if lease is not None:
            try:
                lease.close()
            except Exception:
                pass
        listener = record.listener
        record.listener = None
        if listener is not None:
            try:
                listener.close()
            except Exception:
                pass
        record.adapter = None
        candidate = record.candidate
        if dispose_candidate and candidate is not None:
            record.candidate = None
            try:
                candidate.dispose_local()
            except Exception:
                pass
            record.attempt.candidate_disposed = True
            if record.terminal_evidence is not None:
                record.terminal_evidence = record.attempt.sanitized_evidence(
                    completed_at=record.terminal_evidence.completed_at
                )

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
        with self.__lock:
            if (
                self.__candidate is not expected_candidate
                or self.__context_state is not AuthenticatedContextState.ACTIVE
            ):
                return self.__availability
            context = self.__context
            candidate = self.__candidate
            self.__candidate = None
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
            try:
                candidate.dispose_local()
            except Exception:
                pass
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
    return callable(getattr(candidate, "principal_evidence", None)) and callable(
        getattr(candidate, "dispose_local", None)
    )


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
    "ProtectedPrincipalBindingVerifier",
    "ProviderAuthenticationService",
]
