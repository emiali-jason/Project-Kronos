"""Provider-neutral contracts for authentication and context establishment."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from kronos.configuration.credentials import SecretLease
from kronos.configuration.principals import (
    IntendedPrincipalResolver,
    PrincipalBindingResult,
    PrincipalEvidence,
)
from kronos.provider.models.authentication import (
    AuthenticationAttemptCancellationResult,
    AuthenticationOutcomeEvidence,
    BrowserOpenRequest,
    BrowserOpenResult,
    CallbackCategory,
    CallbackReadiness,
    ProviderAvailabilityState,
    SessionStatus,
)
from kronos.provider.models.context import AuthenticatedProviderContext


class AuthenticationAttemptHandle(Protocol):
    """Opaque, non-serializable service capability."""


class OneUseRequestToken(Protocol):
    """Single-use callback token boundary with no raw-value getter."""

    def consume_for_call(self, operation: Callable[[str], object]) -> object:
        """Supply the token to one bounded operation."""

    def close(self) -> None:
        """Invalidate the token carrier."""


class CallbackAcceptanceResult(Protocol):
    """Sanitized callback result that controls one token carrier."""

    def category(self) -> CallbackCategory:
        """Return the sanitized callback category."""

    def consume_request_token(
        self,
        operation: Callable[[OneUseRequestToken], object],
    ) -> object:
        """Supply one token carrier to one bounded operation."""

    def close(self) -> None:
        """Close callback and token state."""


class AuthenticationCallbackListener(Protocol):
    """Provider-neutral bounded callback transport."""

    def readiness(self) -> CallbackReadiness:
        """Expose readiness without exposing a socket."""

    def receive_once(self, *, deadline: datetime) -> CallbackAcceptanceResult:
        """Receive one terminal callback result."""

    def close(self) -> None:
        """Close the transport idempotently."""


class ProviderCandidateContext(Protocol):
    """Opaque unpublished context restricted to principal verification."""

    def principal_evidence(self) -> PrincipalEvidence:
        """Produce minimum transient evidence once."""

    def dispose_local(self) -> None:
        """Release local resources without a Provider operation."""


class ProviderAuthenticationAdapter(Protocol):
    """Provider-specific translation behind provider-neutral types."""

    def login_url(self, redirect_uri: str) -> str:
        """Construct the official Provider login URL."""

    def exchange_once(
        self,
        request_token: OneUseRequestToken,
        api_secret: SecretLease,
    ) -> ProviderCandidateContext:
        """Perform one bounded session exchange."""


class PrincipalBindingVerifier(Protocol):
    """Fail-closed principal-binding boundary."""

    def verify_principal_binding(
        self,
        evidence: PrincipalEvidence,
        intended_registration_ref: str,
    ) -> PrincipalBindingResult:
        """Resolve and compare through protected custody."""


class LoginNavigator(Protocol):
    """Injected browser-opening boundary."""

    def open_official_login(self, request: BrowserOpenRequest) -> BrowserOpenResult:
        """Request navigation without exposing browser exceptions."""


class ProviderAuthenticationService(Protocol):
    """Sole provider-neutral authentication lifecycle coordinator."""

    def begin_login(self) -> AuthenticationAttemptHandle:
        """Begin one explicitly initiated attempt."""

    def complete_callback(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationOutcomeEvidence:
        """Complete one callback and return sanitized evidence."""

    def cancel_authentication_attempt(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationAttemptCancellationResult:
        """Cancel locally and idempotently."""

    def verify_provider_availability(self) -> ProviderAvailabilityState:
        """Run one separately initiated availability projection."""

    def session_status(self) -> SessionStatus:
        """Return the three sanitized state projections."""

    def authentication_attempt_status(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationOutcomeEvidence | None:
        """Return current or terminal sanitized evidence."""

    def end_kronos_session(self) -> None:
        """Dispose local session state without Provider mutation."""


class AuthenticatedContextPublisher(Protocol):
    """Atomic matched-only candidate publication boundary."""

    def establish_authenticated_context(
        self,
        candidate: ProviderCandidateContext,
        binding: PrincipalBindingResult,
    ) -> AuthenticatedProviderContext:
        """Publish only a candidate proven MATCHED."""


__all__ = [
    "AuthenticatedContextPublisher",
    "AuthenticationAttemptHandle",
    "AuthenticationCallbackListener",
    "CallbackAcceptanceResult",
    "IntendedPrincipalResolver",
    "LoginNavigator",
    "OneUseRequestToken",
    "PrincipalBindingVerifier",
    "ProviderAuthenticationAdapter",
    "ProviderAuthenticationService",
    "ProviderCandidateContext",
]
