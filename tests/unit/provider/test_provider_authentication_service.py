from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import gc
import pickle
import threading

import pytest

from kronos.configuration.principals import (
    IntendedPrincipalResolutionOutcome,
    IntendedPrincipalResolutionResult,
    OneUseIntendedPrincipalLease,
    PrincipalBindingResult,
)
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)
from kronos.provider.kite.composition import OperationLedgerRecorder
from kronos.provider.kite.live_activation import (
    DurableConsumptionRecord,
    MonotonicLifecycleDeadline,
    ProvenConsumption,
    RemainingBudget,
)
from kronos.provider.models.authentication import (
    AuthenticatedContextState,
    AuthenticationAttempt,
    AuthenticationAttemptCancellationResult,
    AuthenticationAttemptState,
    AuthenticationFailureCode,
    BrowserOpenCategory,
    BrowserOpenResult,
    CallbackCategory,
    CallbackReadiness,
    GovernedAuthenticationOperation,
    ProviderAuthenticationConfiguration,
    ProviderAvailabilityState,
)
from kronos.provider.services.provider_authentication import (
    ProviderAuthenticationService,
)
from kronos.provider.services import provider_authentication as service_module


_API_KEY = "service-api-key"
_API_SECRET = "service-api-secret"
_REQUEST_TOKEN = "service-request-token"
_PROVIDER_PRINCIPAL = "PRINCIPAL123"
_REGISTRATION_REF = "registration-primary"
_CREDENTIAL_REF = "credential-primary"
_NOW = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
_PUBLICATION_SHA = "9" * 40


class _Clock:
    def __init__(self) -> None:
        self.current = _NOW

    def __call__(self) -> datetime:
        return self.current


class _RemainingBudgetSupplier:
    def __init__(self, deadline: MonotonicLifecycleDeadline) -> None:
        self.deadline = deadline
        self.monotonic_now = 0.0
        self.calls = 0
        self.events: list[str] | None = None

    def __call__(self) -> RemainingBudget:
        self.calls += 1
        if self.events is not None:
            self.events.append("budget")
        return self.deadline.remaining(monotonic_now=self.monotonic_now)


def _governed_seams() -> tuple[
    OperationLedgerRecorder,
    ProvenConsumption,
    _RemainingBudgetSupplier,
]:
    recorder = OperationLedgerRecorder()
    recorder.record(GovernedAuthenticationOperation.ACTIVATION_VALIDATION)
    consumed = recorder.snapshot().record(
        GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
    )
    recorder.adopt(consumed)
    deadline = MonotonicLifecycleDeadline(monotonic_now=0.0)
    proof = ProvenConsumption(
        record=DurableConsumptionRecord(
            coordinated_activation_identity="KRONOS-STAGE3-TEST-001",
            coordinated_governance_publication_sha=_PUBLICATION_SHA,
            consumed_at=_NOW.isoformat(),
        ),
        deadline=deadline,
        ledger=consumed,
    )
    return recorder, proof, _RemainingBudgetSupplier(deadline)


class _SecretLease:
    __slots__ = ("_secret", "close_count", "use_count")

    def __init__(self) -> None:
        self._secret: str | None = _API_SECRET
        self.use_count = 0
        self.close_count = 0

    def reveal_for_call(self, operation):  # type: ignore[no-untyped-def]
        if self._secret is None:
            raise RuntimeError("SECRET_UNAVAILABLE")
        self.use_count += 1
        secret = self._secret
        try:
            return operation(secret)
        finally:
            self.close()

    def close(self) -> None:
        if self._secret is not None:
            self._secret = None
            self.close_count += 1


class _CredentialSource:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.acquire_count = 0
        self.references: list[str] = []
        self.lease: _SecretLease | None = None

    def acquire(self, credential_ref: str) -> _SecretLease:
        self.acquire_count += 1
        self.references.append(credential_ref)
        if self.error is not None:
            raise self.error
        self.lease = _SecretLease()
        return self.lease


class _Evidence:
    __slots__ = ("_principal", "close_count", "compare_count")

    def __init__(self, principal: str = _PROVIDER_PRINCIPAL) -> None:
        self._principal: str | None = principal
        self.compare_count = 0
        self.close_count = 0

    def compare_expected(self, expected: str) -> PrincipalBindingResult:
        self.compare_count += 1
        principal = self._principal
        self._principal = None
        return (
            PrincipalBindingResult.MATCHED
            if principal == expected
            else PrincipalBindingResult.MISMATCHED
        )

    def close(self) -> None:
        self._principal = None
        self.close_count += 1


class _PrincipalResolver:
    def __init__(
        self,
        *,
        expected: str = _PROVIDER_PRINCIPAL,
        outcome: IntendedPrincipalResolutionOutcome = (
            IntendedPrincipalResolutionOutcome.RESOLVED
        ),
    ) -> None:
        self.expected = expected
        self.outcome = outcome
        self.resolve_count = 0
        self.references: list[str] = []
        self.lease: OneUseIntendedPrincipalLease | None = None
        self.resolve_entered: threading.Event | None = None
        self.resolve_release: threading.Event | None = None

    def use_resolved_once(self, registration_ref, operation):  # type: ignore[no-untyped-def]
        self.resolve_count += 1
        self.references.append(registration_ref)
        if self.resolve_entered is not None:
            self.resolve_entered.set()
        if self.resolve_release is not None:
            assert self.resolve_release.wait(1)
        if self.outcome is not IntendedPrincipalResolutionOutcome.RESOLVED:
            return IntendedPrincipalResolutionResult(self.outcome)
        self.lease = OneUseIntendedPrincipalLease(self.expected)
        binding = operation(self.lease)
        return IntendedPrincipalResolutionResult(
            IntendedPrincipalResolutionOutcome.RESOLVED,
            binding,
        )


class _Availability(StrEnum):
    VALID = "CONTEXT_VALID"
    INVALID = "CONTEXT_INVALID"
    UNAVAILABLE = "PROVIDER_OPERATIONALLY_UNAVAILABLE"


class _Candidate:
    __slots__ = (
        "availability_count",
        "availability_effect",
        "availability_entered",
        "availability_release",
        "dispose_count",
        "evidence",
        "principal_count",
        "capability_issue_count",
        "capability",
    )

    def __init__(self) -> None:
        self.evidence = _Evidence()
        self.principal_count = 0
        self.availability_count = 0
        self.dispose_count = 0
        self.capability_issue_count = 0
        self.capability = _ReadOnlyCapability(self)
        self.availability_effect: object = _Availability.VALID
        self.availability_entered: threading.Event | None = None
        self.availability_release: threading.Event | None = None

    def principal_evidence(self) -> _Evidence:
        self.principal_count += 1
        return self.evidence

    def verify_provider_availability(self) -> object:
        self.availability_count += 1
        if self.availability_entered is not None:
            self.availability_entered.set()
        if self.availability_release is not None:
            assert self.availability_release.wait(1)
        if isinstance(self.availability_effect, BaseException):
            raise self.availability_effect
        return self.availability_effect

    def issue_read_only_capability(self) -> object:
        self.capability_issue_count += 1
        if self.capability_issue_count != 1:
            raise RuntimeError("CAPABILITY_ALREADY_ISSUED")
        return self.capability

    def dispose_local(self) -> None:
        self.dispose_count += 1

    def __repr__(self) -> str:
        return "<_Candidate redacted>"


class _ReadOnlyCapability:
    __slots__ = ("_candidate",)

    def __init__(self, candidate: _Candidate) -> None:
        self._candidate = candidate

    @property
    def operations(self) -> frozenset[ReadOnlyProviderOperation]:
        return frozenset(ReadOnlyProviderOperation)

    @property
    def active(self) -> bool:
        return self._candidate.dispose_count == 0


class _RequestToken:
    __slots__ = ("_token", "close_count", "use_count")

    def __init__(self) -> None:
        self._token: str | None = _REQUEST_TOKEN
        self.use_count = 0
        self.close_count = 0

    def consume_for_call(self, operation: Callable[[str], object]) -> object:
        if self._token is None:
            raise RuntimeError("TOKEN_UNAVAILABLE")
        self.use_count += 1
        token = self._token
        try:
            return operation(token)
        finally:
            self.close()

    def close(self) -> None:
        if self._token is not None:
            self._token = None
            self.close_count += 1


class _CallbackResult:
    def __init__(self, category: CallbackCategory = CallbackCategory.ACCEPTED) -> None:
        self.selected_category = category
        self.token = _RequestToken()
        self.consume_count = 0
        self.close_count = 0

    def category(self) -> CallbackCategory:
        return self.selected_category

    def consume_request_token(self, operation):  # type: ignore[no-untyped-def]
        self.consume_count += 1
        try:
            return operation(self.token)
        finally:
            self.token.close()

    def close(self) -> None:
        self.close_count += 1
        self.token.close()


class _Listener:
    def __init__(self, callback: _CallbackResult) -> None:
        self.callback = callback
        self.start_count = 0
        self.receive_count = 0
        self.close_count = 0
        self._readiness = CallbackReadiness.NOT_READY
        self.receive_entered: threading.Event | None = None
        self.receive_release: threading.Event | None = None

    def start(self) -> None:
        self.start_count += 1
        self._readiness = CallbackReadiness.READY

    def readiness(self) -> CallbackReadiness:
        return self._readiness

    def receive_once(self, *, deadline: datetime) -> _CallbackResult:
        assert deadline == _NOW + timedelta(minutes=5)
        self.receive_count += 1
        if self.receive_entered is not None:
            self.receive_entered.set()
        if self.receive_release is not None:
            assert self.receive_release.wait(1)
        return self.callback

    def close(self) -> None:
        self.close_count += 1
        self._readiness = CallbackReadiness.CLOSED


class _Navigator:
    def __init__(self, category: BrowserOpenCategory = BrowserOpenCategory.OPENED) -> None:
        self.category = category
        self.open_count = 0
        self.opened_items: list[object] = []

    def open_official_login(self, request: object) -> BrowserOpenResult:
        self.open_count += 1
        self.opened_items.append(request)
        return BrowserOpenResult(self.category)


class _Adapter:
    def __init__(self, candidate: _Candidate) -> None:
        self.candidate = candidate
        self.login_count = 0
        self.exchange_count = 0
        self.exchange_effect: BaseException | None = None
        self.api_key_matched = False
        self.token_matched = False
        self.secret_matched = False
        self.exchange_entered: threading.Event | None = None
        self.exchange_release: threading.Event | None = None

    def login_url(self, redirect_uri: str) -> str:
        self.login_count += 1
        assert redirect_uri == "http://127.0.0.1:8765/kite/callback"
        return "https://kite.zerodha.com/connect/login?v=3&api_key=redacted"

    def exchange_once(self, request_token, api_secret):  # type: ignore[no-untyped-def]
        self.exchange_count += 1
        if self.exchange_effect is not None:
            raise self.exchange_effect

        def use_token(token: str) -> object:
            self.token_matched = token == _REQUEST_TOKEN

            def use_secret(secret: str) -> object:
                self.secret_matched = secret == _API_SECRET
                if self.exchange_entered is not None:
                    self.exchange_entered.set()
                if self.exchange_release is not None:
                    assert self.exchange_release.wait(1)
                return self.candidate

            return api_secret.reveal_for_call(use_secret)

        return request_token.consume_for_call(use_token)


class _Harness:
    def __init__(
        self,
        *,
        callback_category: CallbackCategory = CallbackCategory.ACCEPTED,
        browser_category: BrowserOpenCategory = BrowserOpenCategory.OPENED,
        resolution: IntendedPrincipalResolutionOutcome = (
            IntendedPrincipalResolutionOutcome.RESOLVED
        ),
        expected_principal: str = _PROVIDER_PRINCIPAL,
        credential_error: BaseException | None = None,
        governed: bool = False,
    ) -> None:
        self.clock = _Clock()
        self.callback = _CallbackResult(callback_category)
        self.listener = _Listener(self.callback)
        self.navigator = _Navigator(browser_category)
        self.credentials = _CredentialSource(credential_error)
        self.resolver = _PrincipalResolver(
            expected=expected_principal,
            outcome=resolution,
        )
        self.candidate = _Candidate()
        self.adapter = _Adapter(self.candidate)
        self.adapter_factory_count = 0
        self.identity_count = 0
        self.listener_factory_count = 0
        self.identities = iter(["attempt-1", "attempt-2", "attempt-3"])
        self.configuration = ProviderAuthenticationConfiguration(
            provider="KITE",
            _api_key=_API_KEY,
            redirect_uri="http://127.0.0.1:8765/kite/callback",
            intended_registration_ref=_REGISTRATION_REF,
            credential_ref=_CREDENTIAL_REF,
        )

        def adapter_factory(api_key: str) -> _Adapter:
            self.adapter_factory_count += 1
            self.adapter.api_key_matched = api_key == _API_KEY
            return self.adapter

        def listener_factory() -> _Listener:
            self.listener_factory_count += 1
            return self.listener

        def identity_factory() -> str:
            self.identity_count += 1
            return next(self.identities)

        self.service_arguments = {
            "credential_source": self.credentials,
            "principal_resolver": self.resolver,
            "adapter_factory": adapter_factory,
            "listener_factory": listener_factory,
            "navigator": self.navigator,
            "clock": self.clock,
            "identity_factory": identity_factory,
        }
        self.recorder: OperationLedgerRecorder | None = None
        self.proof: ProvenConsumption | None = None
        self.remaining_budget: _RemainingBudgetSupplier | None = None
        governed_arguments: dict[str, object] = {}
        if governed:
            self.recorder, self.proof, self.remaining_budget = _governed_seams()
            governed_arguments = {
                "proven_consumption": self.proof,
                "remaining_budget": self.remaining_budget,
                "operation_recorder": self.recorder,
            }
        self.service = ProviderAuthenticationService(
            self.configuration,
            **self.service_arguments,  # type: ignore[arg-type]
            **governed_arguments,  # type: ignore[arg-type]
        )


def _complete_success(harness: _Harness):  # type: ignore[no-untyped-def]
    handle = harness.service.begin_login()
    evidence = harness.service.complete_callback(handle)
    assert evidence.state is AuthenticationAttemptState.SUCCEEDED
    return handle, evidence


def test_exact_success_transition_sequence_and_operation_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transitions: list[AuthenticationAttemptState] = []
    original = AuthenticationAttempt.transition

    def tracking_transition(self, target, **arguments):  # type: ignore[no-untyped-def]
        transitions.append(target)
        return original(self, target, **arguments)

    monkeypatch.setattr(AuthenticationAttempt, "transition", tracking_transition)
    harness = _Harness()

    handle = harness.service.begin_login()

    assert transitions == [
        AuthenticationAttemptState.LISTENER_READY,
        AuthenticationAttemptState.BROWSER_OPEN_REQUESTED,
        AuthenticationAttemptState.AWAITING_CALLBACK,
    ]
    assert harness.credentials.acquire_count == 0
    assert harness.adapter.exchange_count == 0
    assert harness.candidate.principal_count == 0
    assert harness.candidate.availability_count == 0

    evidence = harness.service.complete_callback(handle)

    assert transitions == [
        AuthenticationAttemptState.LISTENER_READY,
        AuthenticationAttemptState.BROWSER_OPEN_REQUESTED,
        AuthenticationAttemptState.AWAITING_CALLBACK,
        AuthenticationAttemptState.CALLBACK_ACCEPTED,
        AuthenticationAttemptState.EXCHANGING,
        AuthenticationAttemptState.BINDING_PRINCIPAL,
        AuthenticationAttemptState.SUCCEEDED,
    ]
    assert evidence.state is AuthenticationAttemptState.SUCCEEDED
    assert evidence.binding_result is PrincipalBindingResult.MATCHED
    assert harness.listener.start_count == 1
    assert harness.listener.receive_count == 1
    assert harness.listener.close_count == 1
    assert harness.navigator.open_count == 1
    assert harness.adapter_factory_count == 1
    assert harness.adapter.login_count == 1
    assert harness.adapter.exchange_count == 1
    assert harness.credentials.acquire_count == 1
    assert harness.resolver.resolve_count == 1
    assert harness.candidate.principal_count == 1
    assert harness.candidate.availability_count == 0
    assert harness.callback.consume_count == 1
    assert harness.callback.token.use_count == 1
    assert harness.callback.token.close_count == 1
    assert harness.credentials.lease is not None
    assert harness.credentials.lease.use_count == 1
    assert harness.credentials.lease.close_count == 1
    assert harness.resolver.lease is not None
    assert harness.resolver.lease.used is True
    assert harness.resolver.lease.closed is True
    assert harness.adapter.api_key_matched is True
    assert harness.adapter.token_matched is True
    assert harness.adapter.secret_matched is True


def test_one_active_attempt_per_registration_and_terminal_releases_gate() -> None:
    harness = _Harness()
    first = harness.service.begin_login()

    with pytest.raises(RuntimeError, match="ATTEMPT_ALREADY_ACTIVE"):
        harness.service.begin_login()

    assert harness.adapter.exchange_count == 0
    assert harness.service.cancel_authentication_attempt(first) is (
        AuthenticationAttemptCancellationResult.CANCELLED
    )
    second = harness.service.begin_login()
    assert second is not first


@pytest.mark.parametrize(
    ("expected", "resolution", "binding", "failure"),
    [
        (
            "OTHER456",
            IntendedPrincipalResolutionOutcome.RESOLVED,
            PrincipalBindingResult.MISMATCHED,
            AuthenticationFailureCode.PRINCIPAL_MISMATCHED,
        ),
        (
            _PROVIDER_PRINCIPAL,
            IntendedPrincipalResolutionOutcome.NOT_FOUND,
            PrincipalBindingResult.UNCONFIRMED,
            AuthenticationFailureCode.PRINCIPAL_UNCONFIRMED,
        ),
        (
            _PROVIDER_PRINCIPAL,
            IntendedPrincipalResolutionOutcome.BACKEND_UNAVAILABLE,
            PrincipalBindingResult.UNAVAILABLE,
            AuthenticationFailureCode.PRINCIPAL_BINDING_UNAVAILABLE,
        ),
    ],
)
def test_nonmatched_binding_disposes_candidate_and_never_publishes(
    expected: str,
    resolution: IntendedPrincipalResolutionOutcome,
    binding: PrincipalBindingResult,
    failure: AuthenticationFailureCode,
) -> None:
    harness = _Harness(expected_principal=expected, resolution=resolution)
    handle = harness.service.begin_login()

    evidence = harness.service.complete_callback(handle)

    assert evidence.state is AuthenticationAttemptState.FAILED
    assert evidence.binding_result is binding
    assert evidence.failure_code is failure
    assert evidence.candidate_disposed is True
    assert harness.candidate.dispose_count == 1
    assert harness.candidate.capability_issue_count == 0
    assert harness.service.authenticated_read_only_capability() is None
    assert harness.service.current_context() is None
    status = harness.service.session_status()
    assert status.context_state is AuthenticatedContextState.ABSENT
    assert status.provider_availability is ProviderAvailabilityState.NOT_VERIFIED


def test_matched_only_context_is_atomic_active_and_not_verified() -> None:
    harness = _Harness()

    handle, evidence = _complete_success(harness)
    context = harness.service.current_context()
    status = harness.service.session_status()

    assert context is not None
    assert context.attempt_id == evidence.attempt_id
    assert context.binding_result is PrincipalBindingResult.MATCHED
    assert status.attempt_state is AuthenticationAttemptState.SUCCEEDED
    assert status.context_state is AuthenticatedContextState.ACTIVE
    assert status.provider_availability is ProviderAvailabilityState.NOT_VERIFIED
    assert status.context_reusable is True
    assert harness.candidate.availability_count == 0
    capability = harness.service.authenticated_read_only_capability()
    assert capability is harness.candidate.capability
    assert capability.operations == frozenset(ReadOnlyProviderOperation)
    assert harness.candidate.capability_issue_count == 1
    with pytest.raises(RuntimeError, match="AUTHENTICATED_CONTEXT_ALREADY_ACTIVE"):
        harness.service.begin_login()
    assert harness.service.authentication_attempt_status(handle) is evidence


def test_context_construction_failure_disposes_candidate_without_partial_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()

    def fail_context(**_arguments):  # type: ignore[no-untyped-def]
        raise RuntimeError("raw context construction detail")

    monkeypatch.setattr(service_module, "AuthenticatedProviderContext", fail_context)
    handle = harness.service.begin_login()

    evidence = harness.service.complete_callback(handle)

    assert evidence.state is AuthenticationAttemptState.FAILED
    assert evidence.failure_code is AuthenticationFailureCode.INTERNAL_FAILURE
    assert evidence.candidate_disposed is True
    assert harness.candidate.dispose_count == 1
    assert harness.service.current_context() is None
    assert harness.service.session_status().context_state is (
        AuthenticatedContextState.ABSENT
    )
    assert "raw context construction detail" not in repr(evidence)


def test_ordinary_unavailability_changes_only_availability_projection() -> None:
    harness = _Harness()
    handle, evidence = _complete_success(harness)
    harness.candidate.availability_effect = _Availability.UNAVAILABLE

    availability = harness.service.verify_provider_availability()
    after = harness.service.authentication_attempt_status(handle)
    status = harness.service.session_status()

    assert availability is ProviderAvailabilityState.UNAVAILABLE
    assert after is evidence
    assert status.attempt_state is AuthenticationAttemptState.SUCCEEDED
    assert status.context_state is AuthenticatedContextState.ACTIVE
    assert harness.candidate.availability_count == 1


def test_explicit_availability_is_the_only_path_to_available() -> None:
    harness = _Harness()
    handle, evidence = _complete_success(harness)
    assert harness.service.session_status().provider_availability is (
        ProviderAvailabilityState.NOT_VERIFIED
    )

    result = harness.service.verify_provider_availability()

    assert result is ProviderAvailabilityState.AVAILABLE
    assert harness.candidate.availability_count == 1
    assert harness.adapter.exchange_count == 1
    assert harness.service.authentication_attempt_status(handle) is evidence


@pytest.mark.parametrize(
    "effect",
    [
        _Availability.INVALID,
        ProviderConnectivityError(ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED),
    ],
)
def test_authoritative_invalid_token_expires_context_not_attempt(effect: object) -> None:
    harness = _Harness()
    handle, evidence = _complete_success(harness)
    harness.candidate.availability_effect = effect

    result = harness.service.verify_provider_availability()

    assert result is ProviderAvailabilityState.INDETERMINATE
    assert harness.service.authentication_attempt_status(handle) is evidence
    status = harness.service.session_status()
    assert status.attempt_state is AuthenticationAttemptState.SUCCEEDED
    assert status.context_state is AuthenticatedContextState.EXPIRED
    assert status.context_reusable is False
    assert harness.candidate.dispose_count == 1


def test_cancel_is_local_idempotent_and_performs_no_exchange() -> None:
    harness = _Harness()
    handle = harness.service.begin_login()

    first = harness.service.cancel_authentication_attempt(handle)
    second = harness.service.cancel_authentication_attempt(handle)

    assert first is AuthenticationAttemptCancellationResult.CANCELLED
    assert second is AuthenticationAttemptCancellationResult.ALREADY_CANCELLED
    assert harness.listener.close_count == 1
    assert harness.credentials.acquire_count == 0
    assert harness.adapter.exchange_count == 0
    assert harness.candidate.dispose_count == 0
    evidence = harness.service.authentication_attempt_status(handle)
    assert evidence is not None
    assert evidence.state is AuthenticationAttemptState.CANCELLED


def test_end_kronos_session_is_local_idempotent_and_attempt_is_immutable() -> None:
    harness = _Harness()
    handle, evidence = _complete_success(harness)

    harness.service.end_kronos_session()
    harness.service.end_kronos_session()

    assert harness.candidate.dispose_count == 1
    assert harness.service.authenticated_read_only_capability() is None
    assert harness.candidate.availability_count == 0
    assert harness.adapter.exchange_count == 1
    assert harness.service.authentication_attempt_status(handle) is evidence
    status = harness.service.session_status()
    assert status.attempt_state is AuthenticationAttemptState.SUCCEEDED
    assert status.context_state is AuthenticatedContextState.ENDED
    assert status.context_reusable is False


@pytest.mark.parametrize(
    ("category", "failure"),
    [
        (CallbackCategory.INVALID_HOST, AuthenticationFailureCode.CALLBACK_REJECTED),
        (CallbackCategory.TOKEN_MISSING, AuthenticationFailureCode.CALLBACK_REJECTED),
        (CallbackCategory.TIMED_OUT, AuthenticationFailureCode.CALLBACK_TIMED_OUT),
    ],
)
def test_callback_terminal_failures_cleanup_without_credentials(
    category: CallbackCategory,
    failure: AuthenticationFailureCode,
) -> None:
    harness = _Harness(callback_category=category)
    handle = harness.service.begin_login()

    evidence = harness.service.complete_callback(handle)

    assert evidence.failure_code is failure
    assert evidence.state in {
        AuthenticationAttemptState.FAILED,
        AuthenticationAttemptState.TIMED_OUT,
    }
    assert harness.listener.close_count == 1
    assert harness.callback.close_count == 1
    assert harness.credentials.acquire_count == 0
    assert harness.adapter.exchange_count == 0


def test_absolute_attempt_deadline_prevents_late_accepted_callback_exchange() -> None:
    harness = _Harness()
    handle = harness.service.begin_login()
    harness.clock.current = _NOW + timedelta(minutes=5)

    evidence = harness.service.complete_callback(handle)

    assert evidence.state is AuthenticationAttemptState.TIMED_OUT
    assert evidence.failure_code is AuthenticationFailureCode.ATTEMPT_TIMED_OUT
    assert harness.credentials.acquire_count == 0
    assert harness.adapter.exchange_count == 0
    assert harness.listener.close_count == 1
    assert harness.callback.close_count == 1


def test_credential_failure_is_terminal_before_exchange() -> None:
    harness = _Harness(credential_error=RuntimeError("raw credential detail"))
    handle = harness.service.begin_login()

    evidence = harness.service.complete_callback(handle)

    assert evidence.failure_code is AuthenticationFailureCode.CREDENTIAL_UNAVAILABLE
    assert harness.credentials.acquire_count == 1
    assert harness.adapter.exchange_count == 0
    assert harness.callback.close_count == 1
    assert "raw credential detail" not in repr(evidence)


def test_exchange_failure_closes_token_secret_and_does_not_retry() -> None:
    harness = _Harness()
    harness.adapter.exchange_effect = ProviderConnectivityError(
        ProviderErrorCode.CONNECTION_FAILURE
    )
    handle = harness.service.begin_login()

    evidence = harness.service.complete_callback(handle)

    assert evidence.failure_code is AuthenticationFailureCode.TOKEN_EXCHANGE_UNAVAILABLE
    assert harness.adapter.exchange_count == 1
    assert harness.callback.token.close_count == 1
    assert harness.credentials.lease is not None
    assert harness.credentials.lease.close_count == 1
    assert harness.candidate.principal_count == 0


def test_browser_decline_cancels_before_credentials_or_exchange() -> None:
    harness = _Harness(browser_category=BrowserOpenCategory.DECLINED)

    handle = harness.service.begin_login()
    evidence = harness.service.authentication_attempt_status(handle)

    assert evidence is not None
    assert evidence.state is AuthenticationAttemptState.CANCELLED
    assert harness.listener.close_count == 1
    assert harness.credentials.acquire_count == 0
    assert harness.adapter.exchange_count == 0


def test_unknown_handle_discloses_no_attempt_and_performs_no_operation() -> None:
    harness = _Harness()
    unknown = object()

    assert harness.service.authentication_attempt_status(unknown) is None
    assert harness.service.cancel_authentication_attempt(unknown) is (
        AuthenticationAttemptCancellationResult.NO_ACTIVE_ATTEMPT
    )
    assert harness.listener.start_count == 0
    assert harness.service.authentication_attempt_status([]) is None
    assert harness.service.cancel_authentication_attempt([]) is (
        AuthenticationAttemptCancellationResult.NO_ACTIVE_ATTEMPT
    )


def test_handle_and_retained_service_state_expose_no_sensitive_values() -> None:
    harness = _Harness()
    handle, evidence = _complete_success(harness)

    rendered = repr(handle) + repr(evidence) + repr(harness.service.current_context())
    for marker in (_API_KEY, _API_SECRET, _REQUEST_TOKEN, _PROVIDER_PRINCIPAL):
        assert marker not in rendered
        assert marker not in gc.get_referents(handle)
    with pytest.raises(TypeError):
        pickle.dumps(handle)


def test_duplicate_complete_is_rejected_before_second_listener_or_exchange() -> None:
    harness = _Harness()
    entered = threading.Event()
    release = threading.Event()
    harness.listener.receive_entered = entered
    harness.listener.receive_release = release
    handle = harness.service.begin_login()
    results: list[object] = []

    worker = threading.Thread(
        target=lambda: results.append(harness.service.complete_callback(handle))
    )
    worker.start()
    assert entered.wait(1)

    with pytest.raises(
        RuntimeError,
        match="AUTHENTICATION_CALLBACK_ALREADY_IN_PROGRESS",
    ):
        harness.service.complete_callback(handle)

    release.set()
    worker.join(1)
    assert not worker.is_alive()
    assert len(results) == 1
    assert harness.listener.receive_count == 1
    assert harness.adapter.exchange_count == 1


def test_cancel_during_exchange_disposes_late_candidate_without_publication() -> None:
    harness = _Harness()
    entered = threading.Event()
    release = threading.Event()
    harness.adapter.exchange_entered = entered
    harness.adapter.exchange_release = release
    handle = harness.service.begin_login()
    results: list[object] = []

    worker = threading.Thread(
        target=lambda: results.append(harness.service.complete_callback(handle))
    )
    worker.start()
    assert entered.wait(1)

    assert harness.service.cancel_authentication_attempt(handle) is (
        AuthenticationAttemptCancellationResult.CANCELLED
    )
    release.set()
    worker.join(1)

    assert not worker.is_alive()
    assert harness.adapter.exchange_count == 1
    assert harness.candidate.dispose_count == 1
    assert harness.candidate.principal_count == 0
    assert harness.service.current_context() is None
    evidence = harness.service.authentication_attempt_status(handle)
    assert evidence is not None
    assert evidence.state is AuthenticationAttemptState.CANCELLED
    assert evidence.candidate_disposed is True


def test_cancel_during_callback_wait_prevents_credential_and_exchange() -> None:
    harness = _Harness()
    entered = threading.Event()
    release = threading.Event()
    harness.listener.receive_entered = entered
    harness.listener.receive_release = release
    handle = harness.service.begin_login()
    results: list[object] = []

    worker = threading.Thread(
        target=lambda: results.append(harness.service.complete_callback(handle))
    )
    worker.start()
    assert entered.wait(1)
    assert harness.service.cancel_authentication_attempt(handle) is (
        AuthenticationAttemptCancellationResult.CANCELLED
    )
    release.set()
    worker.join(1)

    assert not worker.is_alive()
    assert harness.credentials.acquire_count == 0
    assert harness.adapter.exchange_count == 0
    assert harness.callback.close_count == 1
    assert harness.listener.close_count == 1
    assert len(results) == 1


def test_cancel_during_binding_disposes_candidate_and_cannot_publish() -> None:
    harness = _Harness()
    entered = threading.Event()
    release = threading.Event()
    harness.resolver.resolve_entered = entered
    harness.resolver.resolve_release = release
    handle = harness.service.begin_login()
    results: list[object] = []

    worker = threading.Thread(
        target=lambda: results.append(harness.service.complete_callback(handle))
    )
    worker.start()
    assert entered.wait(1)
    assert harness.service.cancel_authentication_attempt(handle) is (
        AuthenticationAttemptCancellationResult.CANCELLED
    )
    release.set()
    worker.join(1)

    assert not worker.is_alive()
    assert harness.adapter.exchange_count == 1
    assert harness.candidate.principal_count == 1
    assert harness.candidate.dispose_count == 1
    assert harness.service.current_context() is None
    evidence = harness.service.authentication_attempt_status(handle)
    assert evidence is not None
    assert evidence.state is AuthenticationAttemptState.CANCELLED
    assert evidence.candidate_disposed is True


def test_end_session_during_availability_cannot_restore_ended_context() -> None:
    harness = _Harness()
    _complete_success(harness)
    entered = threading.Event()
    release = threading.Event()
    harness.candidate.availability_entered = entered
    harness.candidate.availability_release = release
    results: list[object] = []

    worker = threading.Thread(
        target=lambda: results.append(
            harness.service.verify_provider_availability()
        )
    )
    worker.start()
    assert entered.wait(1)
    harness.service.end_kronos_session()
    release.set()
    worker.join(1)

    assert not worker.is_alive()
    assert results == [ProviderAvailabilityState.NOT_VERIFIED]
    status = harness.service.session_status()
    assert status.context_state is AuthenticatedContextState.ENDED
    assert status.provider_availability is ProviderAvailabilityState.NOT_VERIFIED
    assert harness.candidate.dispose_count == 1


def test_end_session_without_context_remains_absent() -> None:
    harness = _Harness()

    harness.service.end_kronos_session()

    status = harness.service.session_status()
    assert status.context_state is AuthenticatedContextState.ABSENT
    assert harness.candidate.dispose_count == 0


def test_governed_service_retains_exact_proof_before_attempt_or_listener() -> None:
    harness = _Harness(governed=True)

    assert harness.proof is not None
    assert harness.recorder is not None
    assert harness.remaining_budget is not None
    assert (
        getattr(
            harness.service,
            "_ProviderAuthenticationService__proven_consumption",
        )
        is harness.proof
    )
    assert harness.recorder.snapshot() is harness.proof.ledger
    assert harness.remaining_budget.deadline is harness.proof.deadline
    assert harness.identity_count == 0
    assert harness.listener_factory_count == 0
    assert harness.listener.start_count == 0


def test_invalid_governed_seams_fail_before_identity_and_listener() -> None:
    harness = _Harness()
    recorder, proof, remaining_budget = _governed_seams()
    other_recorder, other_proof, _ = _governed_seams()
    cases = (
        {"proven_consumption": proof},
        {
            "remaining_budget": remaining_budget,
            "operation_recorder": recorder,
        },
        {
            "proven_consumption": proof,
            "operation_recorder": recorder,
        },
        {
            "proven_consumption": object(),
            "remaining_budget": remaining_budget,
            "operation_recorder": recorder,
        },
        {
            "proven_consumption": other_proof,
            "remaining_budget": remaining_budget,
            "operation_recorder": recorder,
        },
        {
            "proven_consumption": proof,
            "remaining_budget": remaining_budget,
            "operation_recorder": other_recorder,
        },
    )

    for governed_arguments in cases:
        with pytest.raises(ValueError):
            ProviderAuthenticationService(
                harness.configuration,
                **harness.service_arguments,  # type: ignore[arg-type]
                **governed_arguments,  # type: ignore[arg-type]
            )

    assert harness.identity_count == 0
    assert harness.listener_factory_count == 0
    assert harness.listener.start_count == 0


def test_one_deadline_checks_budget_before_each_service_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness()
    recorder, proof, remaining_budget = _governed_seams()
    events: list[str] = []
    remaining_budget.events = events
    original_receive = harness.listener.receive_once
    original_context = service_module.AuthenticatedProviderContext

    def identity_factory() -> str:
        events.append("identity")
        harness.identity_count += 1
        return "attempt-governed"

    def listener_factory() -> _Listener:
        events.append("listener")
        harness.listener_factory_count += 1
        return harness.listener

    def receive_once(*, deadline: datetime) -> _CallbackResult:
        events.append("callback")
        return original_receive(deadline=deadline)

    def context_factory(**arguments):  # type: ignore[no-untyped-def]
        events.append("context")
        return original_context(**arguments)

    harness.listener.receive_once = receive_once  # type: ignore[method-assign]
    monkeypatch.setattr(service_module, "AuthenticatedProviderContext", context_factory)
    arguments = dict(harness.service_arguments)
    arguments["identity_factory"] = identity_factory
    arguments["listener_factory"] = listener_factory
    service = ProviderAuthenticationService(
        harness.configuration,
        **arguments,  # type: ignore[arg-type]
        proven_consumption=proof,
        remaining_budget=remaining_budget,
        operation_recorder=recorder,
    )

    assert events == ["budget"]
    events.clear()
    handle = service.begin_login()
    assert events == ["budget", "identity", "budget", "listener"]
    events.clear()

    evidence = service.complete_callback(handle)

    assert evidence.state is AuthenticationAttemptState.SUCCEEDED
    assert events == ["budget", "callback", "budget", "context"]
    assert remaining_budget.calls == 5
    assert remaining_budget.deadline is proof.deadline


def test_governed_success_has_exact_service_cardinality_and_no_second_path() -> None:
    harness = _Harness(governed=True)
    handle, evidence = _complete_success(harness)
    assert harness.recorder is not None

    ledger = harness.recorder.snapshot()
    expected_counts = {
        GovernedAuthenticationOperation.ATTEMPT_RESERVATION: 1,
        GovernedAuthenticationOperation.TERMINAL_CALLBACK: 1,
        GovernedAuthenticationOperation.CONTEXT_ESTABLISHMENT: 1,
        GovernedAuthenticationOperation.LOCAL_CLEANUP: 1,
        GovernedAuthenticationOperation.PROVIDER_AVAILABILITY_VERIFICATION: 0,
    }
    for operation, expected in expected_counts.items():
        assert ledger.count_for(operation) == expected
    assert evidence.binding_result is PrincipalBindingResult.MATCHED
    assert harness.service.current_context() is not None
    assert harness.identity_count == 1
    assert harness.listener_factory_count == 1
    assert harness.listener.start_count == 1
    assert harness.listener.receive_count == 1
    assert harness.navigator.open_count == 1
    assert harness.adapter.login_count == 1
    assert harness.adapter.exchange_count == 1
    assert harness.candidate.principal_count == 1
    assert harness.candidate.availability_count == 0

    with pytest.raises(RuntimeError, match="GOVERNED_OPERATION_CARDINALITY_REJECTED"):
        harness.service.complete_callback(handle)
    with pytest.raises(RuntimeError, match="GOVERNED_OPERATION_CARDINALITY_REJECTED"):
        harness.service.begin_login()
    with pytest.raises(RuntimeError, match="PROVIDER_AVAILABILITY_VERIFICATION_WITHHELD"):
        harness.service.verify_provider_availability()

    assert harness.listener.receive_count == 1
    assert harness.adapter.exchange_count == 1
    assert harness.candidate.principal_count == 1
    assert harness.candidate.availability_count == 0
    assert harness.recorder.snapshot().count_for(
        GovernedAuthenticationOperation.PROVIDER_AVAILABILITY_VERIFICATION
    ) == 0


@pytest.mark.parametrize("terminal_path", ["failure", "timeout", "cancel", "success"])
def test_governed_terminal_paths_cleanup_locally_once(terminal_path: str) -> None:
    callback_category = (
        CallbackCategory.INVALID_HOST
        if terminal_path == "failure"
        else CallbackCategory.ACCEPTED
    )
    harness = _Harness(callback_category=callback_category, governed=True)
    handle = harness.service.begin_login()

    if terminal_path == "cancel":
        result = harness.service.cancel_authentication_attempt(handle)
        assert result is AuthenticationAttemptCancellationResult.CANCELLED
    else:
        if terminal_path == "timeout":
            harness.clock.current = _NOW + timedelta(minutes=5)
        evidence = harness.service.complete_callback(handle)
        if terminal_path == "success":
            assert evidence.state is AuthenticationAttemptState.SUCCEEDED
            harness.service.end_kronos_session()
            harness.service.end_kronos_session()
        elif terminal_path == "timeout":
            assert evidence.state is AuthenticationAttemptState.TIMED_OUT
        else:
            assert evidence.state is AuthenticationAttemptState.FAILED

    assert harness.recorder is not None
    assert harness.recorder.snapshot().count_for(
        GovernedAuthenticationOperation.LOCAL_CLEANUP
    ) == 1
    assert harness.listener.close_count == 1
    assert harness.candidate.availability_count == 0
    assert not hasattr(harness.candidate, "invalidate_access_token")


def test_governed_terminal_state_retains_no_raw_transient_material() -> None:
    harness = _Harness(governed=True)
    handle, evidence = _complete_success(harness)
    assert harness.proof is not None
    assert harness.recorder is not None

    rendered = "".join(
        (
            repr(handle),
            repr(evidence),
            repr(harness.proof),
            repr(harness.recorder.snapshot()),
            repr(harness.service.current_context()),
        )
    )
    for marker in (_API_SECRET, _REQUEST_TOKEN, _PROVIDER_PRINCIPAL):
        assert marker not in rendered
    assert harness.callback.token._token is None
    assert harness.credentials.lease is not None
    assert harness.credentials.lease._secret is None
    assert harness.candidate.evidence._principal is None
    assert harness.callback.close_count == 1
    assert harness.credentials.lease.close_count == 1
    assert harness.candidate.evidence.close_count >= 1
