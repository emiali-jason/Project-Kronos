from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import inspect
from zoneinfo import ZoneInfo

import pytest

from kronos.configuration.principals import PrincipalBindingResult
from kronos.provider.contracts.authentication import AuthenticationProvider
from kronos.provider.kite.adapter.kite_provider import KiteProvider
from kronos.provider.kite.auth.kite_authentication import KiteAuthentication
from kronos.provider.models.authentication import (
    AuthenticatedContextState,
    AuthenticationAttemptCancellationResult,
    AuthenticationAttemptState,
    AuthenticationOutcomeEvidence,
    ProviderAvailabilityState,
    SessionStatus,
)
from kronos.provider.models.context import (
    AuthenticatedProviderContext,
    ContextReuseEligibility,
    ContextValidity,
)


_TIMEZONE = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=_TIMEZONE)


class _Clock:
    def __init__(self, current: datetime = _NOW) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def _evidence(
    state: AuthenticationAttemptState = AuthenticationAttemptState.SUCCEEDED,
) -> AuthenticationOutcomeEvidence:
    return AuthenticationOutcomeEvidence(
        attempt_id="attempt-1",
        provider="KITE",
        intended_registration_ref="registration-primary",
        state=state,
        binding_result=(
            PrincipalBindingResult.MATCHED
            if state is AuthenticationAttemptState.SUCCEEDED
            else None
        ),
        failure_code=None,
        callback_consumed=True,
        candidate_disposed=False,
        completed_at=_NOW,
    )


def _active_context() -> AuthenticatedProviderContext:
    return AuthenticatedProviderContext(
        validity=ContextValidity.VALID,
        reuse_eligibility=ContextReuseEligibility.ELIGIBLE,
        provider="KITE",
        context_id="attempt-1",
        attempt_id="attempt-1",
        binding_result=PrincipalBindingResult.MATCHED,
    )


class _FakeAuthoritativeService:
    def __init__(self) -> None:
        self.handle = object()
        self.outcome = _evidence()
        self.context: AuthenticatedProviderContext | None = None
        self.availability = ProviderAvailabilityState.NOT_VERIFIED
        self.begin_count = 0
        self.complete_count = 0
        self.cancel_count = 0
        self.verify_count = 0
        self.end_count = 0
        self.attempt_status_count = 0
        self.last_attempt: object | None = None
        self.read_only_capability = object()

    def begin_login(self) -> object:
        self.begin_count += 1
        return self.handle

    def complete_callback(self, attempt: object) -> AuthenticationOutcomeEvidence:
        self.complete_count += 1
        self.last_attempt = attempt
        if self.outcome.state is AuthenticationAttemptState.SUCCEEDED:
            self.context = _active_context()
        return self.outcome

    def cancel_authentication_attempt(
        self,
        attempt: object,
    ) -> AuthenticationAttemptCancellationResult:
        self.cancel_count += 1
        self.last_attempt = attempt
        return AuthenticationAttemptCancellationResult.CANCELLED

    def verify_provider_availability(self) -> ProviderAvailabilityState:
        self.verify_count += 1
        self.availability = ProviderAvailabilityState.AVAILABLE
        return self.availability

    def session_status(self) -> SessionStatus:
        return SessionStatus(
            attempt_state=self.outcome.state,
            context_state=(
                AuthenticatedContextState.ACTIVE
                if self.context is not None
                and self.context.validity is ContextValidity.VALID
                else AuthenticatedContextState.ENDED
                if self.context is not None
                else AuthenticatedContextState.ABSENT
            ),
            provider_availability=self.availability,
            failure_code=None,
            attempt_active=False,
            context_reusable=(
                self.context is not None
                and self.context.validity is ContextValidity.VALID
            ),
        )

    def authentication_attempt_status(
        self,
        attempt: object,
    ) -> AuthenticationOutcomeEvidence | None:
        self.attempt_status_count += 1
        self.last_attempt = attempt
        return self.outcome

    def current_context(self) -> AuthenticatedProviderContext | None:
        return self.context

    def authenticated_read_only_capability(self) -> object | None:
        return self.read_only_capability if self.context is not None else None

    def end_kronos_session(self) -> None:
        self.end_count += 1
        self.availability = ProviderAvailabilityState.NOT_VERIFIED
        if self.context is not None:
            self.context = replace(
                self.context,
                validity=ContextValidity.TERMINATED,
                reuse_eligibility=ContextReuseEligibility.INELIGIBLE,
            )


def _provider(
    *,
    service: _FakeAuthoritativeService | None = None,
    clock: _Clock | None = None,
) -> tuple[KiteProvider, _FakeAuthoritativeService, _Clock]:
    selected_service = service or _FakeAuthoritativeService()
    selected_clock = clock or _Clock()
    authentication = KiteAuthentication(
        selected_service,  # type: ignore[arg-type]
        clock=selected_clock,
    )
    return KiteProvider(authentication), selected_service, selected_clock


def test_supported_path_delegates_begin_and_complete_once() -> None:
    provider, service, _ = _provider()

    handle = provider.begin_login()
    outcome = provider.complete_callback(handle)

    assert handle is service.handle
    assert outcome is service.outcome
    assert service.begin_count == 1
    assert service.complete_count == 1
    assert service.last_attempt is handle


def test_success_exposes_only_matched_bound_context() -> None:
    provider, service, _ = _provider()

    provider.complete_callback(provider.begin_login())
    context = provider.current_context()

    assert service.context is not None
    assert context is not None
    assert context.validity is ContextValidity.VALID
    assert context.binding_result is PrincipalBindingResult.MATCHED
    assert context.attempt_id == service.outcome.attempt_id
    assert provider.authenticated_read_only_capability() is (
        service.read_only_capability
    )


def test_success_does_not_automatically_verify_availability() -> None:
    provider, service, _ = _provider()

    provider.complete_callback(provider.begin_login())

    assert provider.session_status().provider_availability is (
        ProviderAvailabilityState.NOT_VERIFIED
    )
    assert service.verify_count == 0


def test_availability_verification_requires_separate_explicit_call() -> None:
    provider, service, _ = _provider()
    provider.complete_callback(provider.begin_login())

    result = provider.verify_provider_availability()

    assert result is ProviderAvailabilityState.AVAILABLE
    assert service.verify_count == 1
    assert service.complete_count == 1


def test_failed_attempt_publishes_no_context_and_performs_no_verification() -> None:
    service = _FakeAuthoritativeService()
    service.outcome = _evidence(AuthenticationAttemptState.FAILED)
    provider, _, _ = _provider(service=service)

    provider.complete_callback(provider.begin_login())

    assert provider.current_context() is None
    assert provider.authenticated_read_only_capability() is None
    assert service.verify_count == 0


def test_cancel_delegates_locally_without_completion_or_verification() -> None:
    provider, service, _ = _provider()
    handle = provider.begin_login()

    result = provider.cancel_authentication_attempt(handle)

    assert result is AuthenticationAttemptCancellationResult.CANCELLED
    assert service.cancel_count == 1
    assert service.complete_count == 0
    assert service.verify_count == 0


def test_attempt_status_is_only_the_service_sanitized_projection() -> None:
    provider, service, _ = _provider()
    handle = provider.begin_login()

    status = provider.authentication_attempt_status(handle)

    assert status is service.outcome
    assert service.attempt_status_count == 1
    assert service.last_attempt is handle


def test_end_kronos_session_delegates_one_local_disposal() -> None:
    provider, service, _ = _provider()
    provider.complete_callback(provider.begin_login())

    provider.end_kronos_session()

    assert service.end_count == 1
    assert service.verify_count == 0
    context = provider.current_context()
    assert context is not None
    assert context.validity is ContextValidity.TERMINATED
    assert context.reuse_eligibility is ContextReuseEligibility.INELIGIBLE
    assert provider.authenticated_read_only_capability() is None


def test_repeated_end_is_local_and_never_verifies_provider() -> None:
    provider, service, _ = _provider()
    provider.complete_callback(provider.begin_login())

    provider.end_kronos_session()
    provider.end_kronos_session()

    assert service.end_count == 1
    assert service.verify_count == 0


def test_kite_success_receives_next_day_0600_asia_kolkata_expiry() -> None:
    provider, _, _ = _provider()

    provider.complete_callback(provider.begin_login())
    context = provider.current_context()

    assert context is not None
    assert context.valid_until == datetime(2026, 8, 4, 6, 0, tzinfo=_TIMEZONE)


def test_kite_expiry_disposes_locally_and_projects_expired_state() -> None:
    provider, service, clock = _provider()
    provider.complete_callback(provider.begin_login())

    clock.current = datetime(2026, 8, 4, 6, 0, tzinfo=_TIMEZONE)
    status = provider.session_status()
    context = provider.current_context()

    assert service.end_count == 1
    assert service.verify_count == 0
    assert status.context_state is AuthenticatedContextState.EXPIRED
    assert status.provider_availability is ProviderAvailabilityState.INDETERMINATE
    assert status.context_reusable is False
    assert context is not None
    assert context.validity is ContextValidity.INVALID
    assert context.reuse_eligibility is ContextReuseEligibility.INELIGIBLE
    assert provider.authenticated_read_only_capability() is None


def test_expiry_cleanup_is_idempotent_and_blocks_availability_call() -> None:
    provider, service, clock = _provider()
    provider.complete_callback(provider.begin_login())
    clock.current = datetime(2026, 8, 4, 6, 1, tzinfo=_TIMEZONE)

    provider.current_context()
    provider.session_status()
    availability = provider.verify_provider_availability()

    assert service.end_count == 1
    assert service.verify_count == 0
    assert availability is ProviderAvailabilityState.INDETERMINATE


def test_naive_kite_clock_fails_closed_before_setting_expiry() -> None:
    provider, _, _ = _provider(clock=_Clock(datetime(2026, 8, 3, 12, 0)))

    with pytest.raises(
        ValueError,
        match="KITE_AUTHENTICATION_CLOCK_MUST_BE_TIMEZONE_AWARE",
    ):
        provider.complete_callback(provider.begin_login())


def test_legacy_synchronous_authentication_contract_is_absent() -> None:
    assert "authenticate" not in AuthenticationProvider.__dict__
    assert not hasattr(KiteAuthentication, "authenticate")
    assert not hasattr(KiteProvider, "authenticate")


def test_supported_modules_have_no_exchange_context_or_remote_logout_bypass() -> None:
    sources = "\n".join(
        (
            inspect.getsource(KiteAuthentication),
            inspect.getsource(KiteProvider),
        )
    )

    assert "exchange(" not in sources
    assert "exchange_once(" not in sources
    assert ".establish(" not in sources
    assert "adopt_authenticated_context" not in sources
    assert "invalidate_access_token" not in sources
    assert "terminate_authenticated_context" not in sources
