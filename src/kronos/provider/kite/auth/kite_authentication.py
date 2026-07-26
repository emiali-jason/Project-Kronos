"""Kite implementation of the Provider-owned Authentication Activity."""

from collections.abc import Callable
from datetime import datetime, time, timedelta
from typing import Protocol
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from kronos.configuration.exceptions import ConfigurationError
from kronos.configuration.settings import Settings
from kronos.provider.adapters.kite.authentication import (
    KiteAuthenticationAdapter,
    KiteContextEvidence,
    create_kite_authentication_adapter,
)
from kronos.provider.contracts.authentication import AuthenticationProvider
from kronos.provider.exceptions.access import (
    ProviderAccessPreconditionCode,
    ProviderAccessPreconditionError,
)
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)
from kronos.provider.models.access import ProviderOperationalAvailability
from kronos.provider.models.configuration import ConfigurationBoundaryInput
from kronos.provider.models.context import (
    AuthenticationOutcome,
    AuthenticationOutcomeKind,
    ContextLifecycleReason,
    ProviderProvenance,
)


class _AuthenticationAdapterFactory(Protocol):
    def __call__(self, api_key: str, api_secret: str) -> KiteAuthenticationAdapter: ...


class _RedirectHandler(Protocol):
    def __call__(self, login_url: str, registered_redirect_url: str) -> str: ...


_Clock = Callable[[], datetime]
_KITE_TIMEZONE = ZoneInfo("Asia/Kolkata")


class KiteAuthentication(AuthenticationProvider):
    """Execute the official Kite login flow behind the Provider boundary."""

    __slots__ = (
        "__adapter",
        "__adapter_factory",
        "__api_key",
        "__api_secret",
        "__availability",
        "__clock",
        "__configuration_valid",
        "__configured_provider",
        "__redirect_url",
        "__redirect_handler",
    )

    def __init__(
        self,
        settings: Settings,
        redirect_handler: _RedirectHandler,
        adapter_factory: _AuthenticationAdapterFactory = (
            create_kite_authentication_adapter
        ),
        clock: _Clock | None = None,
    ) -> None:
        try:
            settings.validate_kite_authentication()
        except ConfigurationError:
            self.__configuration_valid = False
        else:
            self.__configuration_valid = True
        self.__configured_provider = settings.provider
        self.__api_key = settings.kite_api_key
        self.__api_secret: str | None = settings.kite_api_secret
        self.__redirect_url = settings.kite_redirect_url
        self.__redirect_handler = redirect_handler
        self.__adapter_factory = adapter_factory
        self.__clock = clock or (lambda: datetime.now(tz=_KITE_TIMEZONE))
        self.__adapter: KiteAuthenticationAdapter | None = None
        self.__availability = ProviderOperationalAvailability.NOT_ESTABLISHED

    def authenticate(
        self,
        configuration: ConfigurationBoundaryInput,
    ) -> AuthenticationOutcome:
        """Produce one verified Outcome for one official Kite login activity."""

        self.__validate_preconditions(configuration)
        provenance = ProviderProvenance(
            provider=configuration.runtime.provider,
            activity_id=uuid4().hex,
        )

        try:
            api_secret = self.__api_secret
            self.__api_secret = None
            if api_secret is None:
                raise ValueError("authentication material is no longer available")
            adapter = self.__adapter_factory(self.__api_key, api_secret)
            del api_secret
            login_url = adapter.login_url()
            redirect_url = self.__redirect_handler(
                login_url,
                self.__redirect_url,
            )
            request_token = self.__request_token(redirect_url)
            adapter.exchange(request_token)
        except ProviderConnectivityError as error:
            return self.__provider_failure(error.code, provenance)
        except (TypeError, ValueError):
            return AuthenticationOutcome(
                kind=AuthenticationOutcomeKind.FAILED,
                provenance=provenance,
                reason=ContextLifecycleReason.AUTHENTICATION_INCOMPLETE,
            )
        except Exception:
            return AuthenticationOutcome(
                kind=AuthenticationOutcomeKind.FAILED,
                provenance=provenance,
                reason=ContextLifecycleReason.AUTHENTICATION_TECHNICAL_FAILURE,
            )

        self.__adapter = adapter
        self.__availability = ProviderOperationalAvailability.AVAILABLE
        return AuthenticationOutcome(
            kind=AuthenticationOutcomeKind.SUCCESS,
            provenance=provenance,
            verified=True,
            valid_until=self.__next_documented_expiry(),
        )

    def operational_availability(self) -> ProviderOperationalAvailability:
        """Return availability evidenced by the latest context-bound operation."""

        return self.__availability

    def context_evidence(self) -> KiteContextEvidence:
        """Obtain authoritative provider evidence for the current context."""

        adapter = self.__adapter
        if adapter is None:
            return KiteContextEvidence.INVALID
        try:
            evidence = adapter.context_evidence()
        except ProviderConnectivityError:
            self.__availability = ProviderOperationalAvailability.AVAILABLE
            raise
        if evidence is KiteContextEvidence.UNAVAILABLE:
            self.__availability = ProviderOperationalAvailability.UNAVAILABLE
        else:
            self.__availability = ProviderOperationalAvailability.AVAILABLE
        return evidence

    def terminate_authenticated_context(self) -> None:
        """Invalidate the provider-side API session for deliberate termination."""

        adapter = self.__adapter
        if adapter is None:
            return
        try:
            adapter.terminate()
        except ProviderConnectivityError as error:
            self.__availability = (
                ProviderOperationalAvailability.UNAVAILABLE
                if _is_operational_failure(error.code)
                else ProviderOperationalAvailability.AVAILABLE
            )
            raise
        self.__availability = ProviderOperationalAvailability.AVAILABLE
        self.__adapter = None

    def context_expired(self, valid_until: datetime | None) -> bool:
        """Apply Kite's documented next-day 06:00 context expiry."""

        if valid_until is None:
            return False
        now = self.__clock()
        if now.tzinfo is None:
            raise ValueError("Kite authentication clock must be timezone-aware")
        return now >= valid_until

    def __validate_preconditions(
        self,
        configuration: ConfigurationBoundaryInput,
    ) -> None:
        if configuration.runtime.provider.upper() != "KITE":
            raise ProviderAccessPreconditionError(
                ProviderAccessPreconditionCode.PROVIDER_MISMATCH
            )
        if not configuration.usable:
            raise ProviderAccessPreconditionError(
                ProviderAccessPreconditionCode.CONFIGURATION_INELIGIBLE
            )
        if (
            not self.__configuration_valid
            or self.__configured_provider.upper() != "KITE"
            or self.__api_secret is None
        ):
            raise ProviderAccessPreconditionError(
                ProviderAccessPreconditionCode.CONFIGURATION_INELIGIBLE
            )

    def __request_token(self, redirect_url: str) -> str:
        expected = urlsplit(self.__redirect_url)
        actual = urlsplit(redirect_url)
        if (
            actual.scheme,
            actual.netloc,
            actual.path,
        ) != (
            expected.scheme,
            expected.netloc,
            expected.path,
        ):
            raise ValueError("authentication redirect did not match registered boundary")

        query = parse_qs(actual.query, keep_blank_values=True)
        if query.get("status") == ["error"]:
            raise ProviderConnectivityError(
                ProviderErrorCode.AUTHENTICATION_REJECTED
            )
        tokens = query.get("request_token", [])
        if len(tokens) != 1 or not tokens[0]:
            raise ValueError("authentication redirect was incomplete")
        return tokens[0]

    def __provider_failure(
        self,
        code: ProviderErrorCode,
        provenance: ProviderProvenance,
    ) -> AuthenticationOutcome:
        if code in {
            ProviderErrorCode.AUTHENTICATION_REJECTED,
            ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED,
        }:
            self.__availability = ProviderOperationalAvailability.AVAILABLE
            return AuthenticationOutcome(
                kind=AuthenticationOutcomeKind.REJECTED,
                provenance=provenance,
                reason=ContextLifecycleReason.PROVIDER_DECISION,
            )
        if _is_operational_failure(code):
            self.__availability = ProviderOperationalAvailability.UNAVAILABLE
            reason = ContextLifecycleReason.PROVIDER_OPERATIONALLY_UNAVAILABLE
        else:
            self.__availability = ProviderOperationalAvailability.AVAILABLE
            reason = ContextLifecycleReason.AUTHENTICATION_TECHNICAL_FAILURE
        return AuthenticationOutcome(
            kind=AuthenticationOutcomeKind.FAILED,
            provenance=provenance,
            reason=reason,
        )

    def __next_documented_expiry(self) -> datetime:
        now = self.__clock()
        if now.tzinfo is None:
            raise ValueError("Kite authentication clock must be timezone-aware")
        local_now = now.astimezone(_KITE_TIMEZONE)
        next_day = local_now.date() + timedelta(days=1)
        return datetime.combine(next_day, time(hour=6), tzinfo=_KITE_TIMEZONE)


def _is_operational_failure(code: ProviderErrorCode) -> bool:
    return code in {
        ProviderErrorCode.NETWORK_TIMEOUT,
        ProviderErrorCode.CONNECTION_FAILURE,
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.PROVIDER_SERVICE_FAILURE,
    }
