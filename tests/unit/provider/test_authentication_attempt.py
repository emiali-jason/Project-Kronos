from __future__ import annotations

import inspect
import pickle
from datetime import UTC, datetime, timedelta

import pytest

from kronos.configuration.principals import PrincipalBindingResult
from kronos.provider.contracts import provider_authentication as contracts
from kronos.provider.models.authentication import (
    AuthenticatedContextState,
    AuthenticationAttempt,
    AuthenticationAttemptState,
    AuthenticationFailureCode,
    AuthenticationModelError,
    AuthenticationModelFailure,
    BrowserOpenRequest,
    ProviderAuthenticationConfiguration,
    ProviderAvailabilityState,
    SessionStatus,
)
from kronos.provider.models.context import (
    AuthenticatedProviderContext,
    ContextReuseEligibility,
    ContextValidity,
)


CREATED_AT = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)
STARTED_AT = CREATED_AT + timedelta(seconds=1)
EXPIRES_AT = STARTED_AT + timedelta(minutes=4)


def _attempt() -> AuthenticationAttempt:
    return AuthenticationAttempt(
        attempt_id="attempt-internal-reference",
        provider="KITE",
        intended_registration_ref="registration-reference",
        created_at=CREATED_AT,
        started_at=STARTED_AT,
        expires_at=EXPIRES_AT,
        listener_ref="listener-reference",
    )


def _advance_to(
    attempt: AuthenticationAttempt,
    state: AuthenticationAttemptState,
) -> None:
    sequence = [
        AuthenticationAttemptState.LISTENER_READY,
        AuthenticationAttemptState.BROWSER_OPEN_REQUESTED,
        AuthenticationAttemptState.AWAITING_CALLBACK,
        AuthenticationAttemptState.CALLBACK_ACCEPTED,
        AuthenticationAttemptState.EXCHANGING,
        AuthenticationAttemptState.BINDING_PRINCIPAL,
        AuthenticationAttemptState.SUCCEEDED,
    ]
    for index, target in enumerate(sequence, start=1):
        if target is AuthenticationAttemptState.SUCCEEDED:
            attempt.candidate_created = True
            attempt.binding_result = PrincipalBindingResult.MATCHED
        attempt.transition(target, at=STARTED_AT + timedelta(seconds=index))
        if target is state:
            return


def test_attempt_states_are_exact_and_exclude_context_lifecycle_terms() -> None:
    assert [state.value for state in AuthenticationAttemptState] == [
        "CREATED",
        "LISTENER_READY",
        "BROWSER_OPEN_REQUESTED",
        "AWAITING_CALLBACK",
        "CALLBACK_ACCEPTED",
        "EXCHANGING",
        "BINDING_PRINCIPAL",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
    ]
    assert "EXPIRED" not in AuthenticationAttemptState.__members__
    assert "ENDED" not in AuthenticationAttemptState.__members__


def test_context_and_availability_states_are_independent_and_exact() -> None:
    assert [state.value for state in AuthenticatedContextState] == [
        "ABSENT",
        "ACTIVE",
        "EXPIRED",
        "ENDED",
    ]
    assert [state.value for state in ProviderAvailabilityState] == [
        "NOT_VERIFIED",
        "VERIFYING",
        "AVAILABLE",
        "UNAVAILABLE",
        "INDETERMINATE",
    ]
    status = SessionStatus(
        attempt_state=AuthenticationAttemptState.SUCCEEDED,
        context_state=AuthenticatedContextState.ACTIVE,
        provider_availability=ProviderAvailabilityState.NOT_VERIFIED,
        failure_code=None,
        attempt_active=False,
        context_reusable=True,
    )
    assert status.attempt_state is AuthenticationAttemptState.SUCCEEDED
    assert status.context_state is AuthenticatedContextState.ACTIVE
    assert status.provider_availability is ProviderAvailabilityState.NOT_VERIFIED


def test_provider_authentication_configuration_is_redacted_and_nonserializable() -> None:
    marker = "SYNTHETIC_API_KEY_MARKER"
    configuration = ProviderAuthenticationConfiguration(
        provider="KITE",
        _api_key=marker,
        redirect_uri="http://127.0.0.1:8765/kite/callback",
        intended_registration_ref="registration-reference",
        credential_ref="credential-reference",
    )
    captured: list[str] = []

    configuration.use_api_key(captured.append)

    assert captured == [marker]
    assert repr(configuration) == "<ProviderAuthenticationConfiguration redacted>"
    assert str(configuration) == "<ProviderAuthenticationConfiguration redacted>"
    assert marker not in repr(configuration)
    assert not hasattr(configuration, "api_key")
    with pytest.raises(TypeError):
        pickle.dumps(configuration)


@pytest.mark.parametrize(
    "field",
    [
        "provider",
        "_api_key",
        "redirect_uri",
        "intended_registration_ref",
        "credential_ref",
    ],
)
def test_provider_authentication_configuration_rejects_blank_fields(field: str) -> None:
    values = {
        "provider": "KITE",
        "_api_key": "SYNTHETIC_API_KEY_MARKER",
        "redirect_uri": "http://127.0.0.1:8765/kite/callback",
        "intended_registration_ref": "registration-reference",
        "credential_ref": "credential-reference",
    }
    values[field] = " "

    with pytest.raises(AuthenticationModelError) as captured:
        ProviderAuthenticationConfiguration(**values)
    assert captured.value.failure is AuthenticationModelFailure.BLANK_IDENTITY


def test_attempt_follows_the_only_success_transition_sequence() -> None:
    attempt = _attempt()

    _advance_to(attempt, AuthenticationAttemptState.SUCCEEDED)

    assert attempt.state is AuthenticationAttemptState.SUCCEEDED
    assert attempt.callback_consumed is True
    assert attempt.exchange_started is True
    assert attempt.terminal is True


@pytest.mark.parametrize(
    ("candidate_created", "binding_result"),
    [
        (False, None),
        (True, None),
        (True, PrincipalBindingResult.MISMATCHED),
        (True, PrincipalBindingResult.UNCONFIRMED),
        (True, PrincipalBindingResult.UNAVAILABLE),
    ],
)
def test_success_requires_a_created_candidate_and_matched_binding(
    candidate_created: bool,
    binding_result: PrincipalBindingResult | None,
) -> None:
    attempt = _attempt()
    _advance_to(attempt, AuthenticationAttemptState.BINDING_PRINCIPAL)
    attempt.candidate_created = candidate_created
    attempt.binding_result = binding_result

    with pytest.raises(AuthenticationModelError) as captured:
        attempt.transition(
            AuthenticationAttemptState.SUCCEEDED,
            at=STARTED_AT + timedelta(seconds=8),
        )
    assert captured.value.failure is AuthenticationModelFailure.INVALID_TRANSITION


@pytest.mark.parametrize(
    "terminal",
    [AuthenticationAttemptState.FAILED, AuthenticationAttemptState.TIMED_OUT],
)
def test_failure_and_timeout_require_a_sanitized_failure_code(
    terminal: AuthenticationAttemptState,
) -> None:
    attempt = _attempt()
    at = EXPIRES_AT if terminal is AuthenticationAttemptState.TIMED_OUT else STARTED_AT

    with pytest.raises(AuthenticationModelError) as captured:
        attempt.transition(terminal, at=at)
    assert captured.value.failure is AuthenticationModelFailure.INVALID_TRANSITION


@pytest.mark.parametrize(
    "terminal",
    [
        AuthenticationAttemptState.SUCCEEDED,
        AuthenticationAttemptState.FAILED,
        AuthenticationAttemptState.CANCELLED,
        AuthenticationAttemptState.TIMED_OUT,
    ],
)
def test_terminal_attempt_never_reactivates(
    terminal: AuthenticationAttemptState,
) -> None:
    attempt = _attempt()
    if terminal is AuthenticationAttemptState.SUCCEEDED:
        _advance_to(attempt, terminal)
    elif terminal is AuthenticationAttemptState.TIMED_OUT:
        attempt.transition(
            terminal,
            at=EXPIRES_AT,
            failure_code=AuthenticationFailureCode.ATTEMPT_TIMED_OUT,
        )
    else:
        attempt.transition(
            terminal,
            at=STARTED_AT + timedelta(seconds=1),
            failure_code=(
                AuthenticationFailureCode.INTERNAL_FAILURE
                if terminal is AuthenticationAttemptState.FAILED
                else None
            ),
        )

    with pytest.raises(AuthenticationModelError) as captured:
        attempt.transition(
            AuthenticationAttemptState.LISTENER_READY,
            at=STARTED_AT + timedelta(seconds=2),
        )
    assert captured.value.failure is AuthenticationModelFailure.TERMINAL_ATTEMPT


def test_attempt_rejects_skipped_and_expired_non_timeout_transitions() -> None:
    attempt = _attempt()

    with pytest.raises(AuthenticationModelError) as skipped:
        attempt.transition(
            AuthenticationAttemptState.AWAITING_CALLBACK,
            at=STARTED_AT + timedelta(seconds=1),
        )
    assert skipped.value.failure is AuthenticationModelFailure.INVALID_TRANSITION

    with pytest.raises(AuthenticationModelError) as expired:
        attempt.transition(AuthenticationAttemptState.LISTENER_READY, at=EXPIRES_AT)
    assert expired.value.failure is AuthenticationModelFailure.INVALID_TRANSITION


def test_timeout_requires_the_deadline_and_records_controlled_failure() -> None:
    attempt = _attempt()

    with pytest.raises(AuthenticationModelError) as premature:
        attempt.transition(
            AuthenticationAttemptState.TIMED_OUT,
            at=EXPIRES_AT - timedelta(microseconds=1),
        )
    assert premature.value.failure is AuthenticationModelFailure.PREMATURE_TIMEOUT

    attempt.transition(
        AuthenticationAttemptState.TIMED_OUT,
        at=EXPIRES_AT,
        failure_code=AuthenticationFailureCode.ATTEMPT_TIMED_OUT,
    )
    assert attempt.state is AuthenticationAttemptState.TIMED_OUT
    assert attempt.terminal_code is AuthenticationFailureCode.ATTEMPT_TIMED_OUT


def test_naive_timestamps_and_invalid_deadlines_are_rejected() -> None:
    with pytest.raises(AuthenticationModelError) as naive:
        AuthenticationAttempt(
            attempt_id="attempt",
            provider="KITE",
            intended_registration_ref="registration",
            created_at=CREATED_AT.replace(tzinfo=None),
            started_at=STARTED_AT,
            expires_at=EXPIRES_AT,
            listener_ref="listener",
        )
    assert naive.value.failure is AuthenticationModelFailure.NAIVE_TIMESTAMP

    with pytest.raises(AuthenticationModelError) as invalid:
        AuthenticationAttempt(
            attempt_id="attempt",
            provider="KITE",
            intended_registration_ref="registration",
            created_at=CREATED_AT,
            started_at=STARTED_AT,
            expires_at=STARTED_AT,
            listener_ref="listener",
        )
    assert invalid.value.failure is AuthenticationModelFailure.INVALID_DEADLINE


def test_attempt_and_evidence_representations_do_not_display_identity() -> None:
    attempt = _attempt()
    evidence = attempt.sanitized_evidence(completed_at=STARTED_AT)

    assert repr(attempt) == "<AuthenticationAttempt redacted>"
    assert str(attempt) == "<AuthenticationAttempt redacted>"
    assert repr(evidence) == "<AuthenticationOutcomeEvidence sanitized>"
    assert attempt.attempt_id not in repr(attempt)
    assert attempt.attempt_id not in repr(evidence)
    with pytest.raises(TypeError):
        pickle.dumps(attempt)


def test_browser_request_is_redacted_and_nonserializable() -> None:
    url = "https://example.invalid/login?synthetic=marker"
    request = BrowserOpenRequest(url)

    assert repr(request) == "<BrowserOpenRequest redacted>"
    assert str(request) == "<BrowserOpenRequest redacted>"
    assert url not in repr(request)
    with pytest.raises(TypeError):
        pickle.dumps(request)


def test_authenticated_context_accepts_only_matched_sanitized_provenance() -> None:
    context = AuthenticatedProviderContext(
        validity=ContextValidity.VALID,
        reuse_eligibility=ContextReuseEligibility.ELIGIBLE,
        provider="KITE",
        context_id="context-reference",
        attempt_id="attempt-reference",
        binding_result=PrincipalBindingResult.MATCHED,
    )

    assert context.attempt_id == "attempt-reference"
    assert context.binding_result is PrincipalBindingResult.MATCHED
    assert not hasattr(context, "principal")
    assert not hasattr(context, "token")


@pytest.mark.parametrize(
    ("attempt_id", "binding"),
    [
        ("attempt-reference", None),
        (None, PrincipalBindingResult.MATCHED),
        (" ", PrincipalBindingResult.MATCHED),
        ("attempt-reference", PrincipalBindingResult.MISMATCHED),
        ("attempt-reference", PrincipalBindingResult.UNCONFIRMED),
        ("attempt-reference", PrincipalBindingResult.UNAVAILABLE),
    ],
)
def test_authenticated_context_rejects_incomplete_or_nonmatched_provenance(
    attempt_id: str | None,
    binding: PrincipalBindingResult | None,
) -> None:
    with pytest.raises(ValueError):
        AuthenticatedProviderContext(
            validity=ContextValidity.VALID,
            reuse_eligibility=ContextReuseEligibility.ELIGIBLE,
            attempt_id=attempt_id,
            binding_result=binding,
        )


def test_provider_neutral_stage1_modules_have_no_external_effect_imports() -> None:
    sources = "\n".join(
        inspect.getsource(module)
        for module in (
            contracts,
            __import__(
                "kronos.provider.models.authentication",
                fromlist=["authentication"],
            ),
            __import__("kronos.configuration.credentials", fromlist=["credentials"]),
            __import__("kronos.configuration.principals", fromlist=["principals"]),
        )
    )

    for prohibited in (
        "import kiteconnect",
        "from kiteconnect",
        "import tkinter",
        "import subprocess",
        "import socket",
        "import webbrowser",
        "import requests",
    ):
        assert prohibited not in sources
