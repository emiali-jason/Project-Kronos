"""Kite policy facade over the authoritative authentication service."""

from dataclasses import replace
from datetime import datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from kronos.provider.contracts.authentication import AuthenticationProvider
from kronos.provider.contracts.provider_authentication import (
    AuthenticatedReadOnlyProviderCapability,
    AuthenticationAttemptHandle,
)
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


_Clock = Callable[[], datetime]
_KITE_TIMEZONE = ZoneInfo("Asia/Kolkata")


class KiteAuthentication:
    """Delegate one supported Kite path to the provider-neutral service.

    This facade owns no credential, callback, exchange, principal-binding or
    candidate-context mechanics.  Its only Provider-specific responsibility is
    Kite's documented next-day 06:00 Asia/Kolkata validity policy.
    """

    __slots__ = (
        "__clock",
        "__ended",
        "__expired",
        "__service",
        "__valid_until",
    )

    def __init__(
        self,
        service: AuthenticationProvider,
        *,
        clock: _Clock | None = None,
    ) -> None:
        self.__service = service
        self.__clock = clock or (lambda: datetime.now(tz=_KITE_TIMEZONE))
        self.__valid_until: datetime | None = None
        self.__ended = False
        self.__expired = False

    def begin_login(self) -> AuthenticationAttemptHandle:
        """Delegate one explicitly initiated Authentication Attempt."""

        handle = self.__service.begin_login()
        self.__valid_until = None
        self.__ended = False
        self.__expired = False
        return handle

    def complete_callback(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationOutcomeEvidence:
        """Delegate callback completion without creating another exchange path."""

        outcome = self.__service.complete_callback(attempt)
        if outcome.state is AuthenticationAttemptState.SUCCEEDED:
            self.__valid_until = self.__next_documented_expiry()
            self.__ended = False
            self.__expired = False
        return outcome

    def cancel_authentication_attempt(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationAttemptCancellationResult:
        """Delegate local, idempotent attempt cancellation."""

        return self.__service.cancel_authentication_attempt(attempt)

    def verify_provider_availability(self) -> ProviderAvailabilityState:
        """Run availability verification only when explicitly requested."""

        self.__apply_documented_expiry()
        if self.__expired:
            return ProviderAvailabilityState.INDETERMINATE
        return self.__service.verify_provider_availability()

    def session_status(self) -> SessionStatus:
        """Return the three separate state projections with Kite expiry applied."""

        self.__apply_documented_expiry()
        status = self.__service.session_status()
        if not self.__expired:
            return status
        return replace(
            status,
            context_state=AuthenticatedContextState.EXPIRED,
            provider_availability=ProviderAvailabilityState.INDETERMINATE,
            context_reusable=False,
        )

    def authentication_attempt_status(
        self,
        attempt: AuthenticationAttemptHandle,
    ) -> AuthenticationOutcomeEvidence | None:
        """Return only sanitized attempt evidence from the service."""

        return self.__service.authentication_attempt_status(attempt)

    def current_context(self) -> AuthenticatedProviderContext | None:
        """Return only the bound context projection, never the candidate."""

        self.__apply_documented_expiry()
        context = self.__service.current_context()
        if context is None:
            return None
        if self.__expired:
            return replace(
                context,
                validity=ContextValidity.INVALID,
                reuse_eligibility=ContextReuseEligibility.INELIGIBLE,
                valid_until=self.__valid_until,
            )
        return replace(context, valid_until=self.__valid_until)

    def authenticated_read_only_capability(
        self,
    ) -> AuthenticatedReadOnlyProviderCapability | None:
        """Delegate the opaque capability only while Kite context remains valid."""

        self.__apply_documented_expiry()
        if self.__expired or self.__ended:
            return None
        return self.__service.authenticated_read_only_capability()

    def end_kronos_session(self) -> None:
        """Dispose the local service context without Provider mutation."""

        if self.__ended or self.__expired:
            return
        self.__service.end_kronos_session()
        self.__valid_until = None
        self.__ended = True
        self.__expired = False

    def __apply_documented_expiry(self) -> None:
        valid_until = self.__valid_until
        if valid_until is None or self.__expired:
            return
        now = self.__aware_now()
        if now < valid_until:
            return
        self.__service.end_kronos_session()
        self.__expired = True

    def __next_documented_expiry(self) -> datetime:
        local_now = self.__aware_now().astimezone(_KITE_TIMEZONE)
        next_day = local_now.date() + timedelta(days=1)
        return datetime.combine(next_day, time(hour=6), tzinfo=_KITE_TIMEZONE)

    def __aware_now(self) -> datetime:
        now = self.__clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("KITE_AUTHENTICATION_CLOCK_MUST_BE_TIMEZONE_AWARE")
        return now


__all__ = ["KiteAuthentication"]
