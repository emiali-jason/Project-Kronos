"""Provider-neutral contracts for authentication and context establishment."""

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
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
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    LtpSnapshot,
    OhlcSnapshot,
    QuoteSnapshot,
)
from kronos.provider.contracts.monitoring import (
    MonitoringConsumer,
    ReadOnlyMonitoringSession,
)


class AuthenticationAttemptHandle(Protocol):
    """Opaque, non-serializable service capability."""


class ReadOnlyProviderOperation(StrEnum):
    """The complete bounded operation set of an authenticated read-only handle."""

    INSTRUMENTS = "instruments"
    HISTORICAL_DATA = "historical_data"
    QUOTE = "quote"
    LTP = "ltp"
    OHLC = "ohlc"
    MONITORING = "monitoring"


class AuthenticatedReadOnlyProviderCapability(Protocol):
    """Opaque matched-principal capability; it exposes no Provider client or token."""

    @property
    def operations(self) -> frozenset[ReadOnlyProviderOperation]:
        """Return the immutable read-only operation boundary."""

    @property
    def active(self) -> bool:
        """Whether the owning authenticated context remains locally usable."""

    def instrument_records(self, exchange: str) -> tuple[InstrumentRecord, ...]:
        """Return normalized records; raw Provider records never cross this seam."""

    def historical_candles(
        self,
        request: HistoricalCandleRequest,
    ) -> tuple[HistoricalCandle, ...]:
        """Return normalized candles using only private Provider identity."""

    def quote(self, instrument: InstrumentRecord) -> QuoteSnapshot:
        """Return a normalized quote without exposing Provider identity."""

    def ltp(self, instrument: InstrumentRecord) -> LtpSnapshot:
        """Return a normalized last price without exposing Provider identity."""

    def ohlc(self, instrument: InstrumentRecord) -> OhlcSnapshot:
        """Return normalized OHLC values without exposing Provider identity."""

    def open_monitoring_session(
        self,
        consumer: MonitoringConsumer,
    ) -> ReadOnlyMonitoringSession:
        """Open one opaque factual market/order-evidence stream."""


class CanonicalActivationEvidenceVerifier(Protocol):
    """Trusted boundary for canonical repository and governance evidence."""

    def verify(
        self,
        expected_context: object,
        observed_context: object,
        repository_evidence: object,
    ) -> bool:
        """Return true only for exact canonical, synchronized evidence."""


class DurableConsumptionFilesystem(Protocol):
    """Descriptor-only durable-consumption filesystem boundary.

    Implementations must not provide a path-based creation or reopen fallback.
    """

    def open_verified_parent_directory(
        self,
        directory: str,
        *,
        expected_owner: int,
        expected_mode: int,
    ) -> object:
        """Safely create if absent, then open and verify the exact parent."""

    def create_exclusive_nofollow(
        self,
        parent_descriptor: object,
        filename: str,
        *,
        mode: int,
    ) -> object:
        """Create one file relative to the parent with O_EXCL/no-follow semantics."""

    def verify_open_file(
        self,
        file_descriptor: object,
        *,
        expected_owner: int,
        expected_mode: int,
        expected_link_count: int,
    ) -> None:
        """Verify regular-file, owner, mode and link count through the descriptor."""

    def write_all(self, file_descriptor: object, payload: bytes) -> None:
        """Write the complete payload or fail; short writes are prohibited."""

    def flush_file(self, file_descriptor: object) -> None:
        """Flush language/runtime buffers without closing the descriptor."""

    def fsync_file(self, file_descriptor: object) -> None:
        """Synchronize file contents durably."""

    def close_file(self, file_descriptor: object) -> None:
        """Close the created file descriptor safely."""

    def fsync_directory(self, parent_descriptor: object) -> None:
        """Synchronize the verified parent directory after creation."""

    def close_directory(self, parent_descriptor: object) -> None:
        """Dispose the parent descriptor without mutating the record path."""


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

    def issue_read_only_capability(self) -> AuthenticatedReadOnlyProviderCapability:
        """Issue one opaque capability after the service proves principal MATCHED."""

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

    def authenticated_read_only_capability(
        self,
    ) -> AuthenticatedReadOnlyProviderCapability | None:
        """Return the active matched-only capability without exposing credentials."""

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
    "AuthenticatedReadOnlyProviderCapability",
    "AuthenticationAttemptHandle",
    "AuthenticationCallbackListener",
    "CanonicalActivationEvidenceVerifier",
    "CallbackAcceptanceResult",
    "DurableConsumptionFilesystem",
    "IntendedPrincipalResolver",
    "LoginNavigator",
    "OneUseRequestToken",
    "PrincipalBindingVerifier",
    "ProviderAuthenticationAdapter",
    "ProviderAuthenticationService",
    "ProviderCandidateContext",
    "ReadOnlyProviderOperation",
]
