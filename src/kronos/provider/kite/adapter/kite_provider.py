"""Kite entry point for the authoritative authentication lifecycle."""

from kronos.provider.contracts.provider_authentication import (
    AuthenticationAttemptHandle,
)
from kronos.provider.kite.auth.kite_authentication import KiteAuthentication
from kronos.provider.models.authentication import (
    AuthenticationAttemptCancellationResult,
    AuthenticationOutcomeEvidence,
    ProviderAvailabilityState,
    SessionStatus,
)
from kronos.provider.models.context import AuthenticatedProviderContext


class KiteProvider:
    """Expose one supported authentication path with no lifecycle bypass."""

    __slots__ = ("__authentication",)

    def __init__(self, authentication: KiteAuthentication) -> None:
        self.__authentication = authentication

    def begin_login(self) -> AuthenticationAttemptHandle:
        return self.__authentication.begin_login()

    def complete_callback(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationOutcomeEvidence:
        return self.__authentication.complete_callback(attempt)

    def cancel_authentication_attempt(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationAttemptCancellationResult:
        return self.__authentication.cancel_authentication_attempt(attempt)

    def current_context(self) -> AuthenticatedProviderContext | None:
        return self.__authentication.current_context()

    def verify_provider_availability(self) -> ProviderAvailabilityState:
        return self.__authentication.verify_provider_availability()

    def session_status(self) -> SessionStatus:
        return self.__authentication.session_status()

    def authentication_attempt_status(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationOutcomeEvidence | None:
        return self.__authentication.authentication_attempt_status(attempt)

    def end_kronos_session(self) -> None:
        self.__authentication.end_kronos_session()


__all__ = ["KiteProvider"]
