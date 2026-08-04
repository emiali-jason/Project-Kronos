"""Provider-neutral authentication lifecycle and sanitized evidence models."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias

from kronos.configuration.principals import PrincipalBindingResult


AttemptId: TypeAlias = str
ProviderId: TypeAlias = str
RegistrationRef: TypeAlias = str


class AuthenticationAttemptState(StrEnum):
    CREATED = "CREATED"
    LISTENER_READY = "LISTENER_READY"
    BROWSER_OPEN_REQUESTED = "BROWSER_OPEN_REQUESTED"
    AWAITING_CALLBACK = "AWAITING_CALLBACK"
    CALLBACK_ACCEPTED = "CALLBACK_ACCEPTED"
    EXCHANGING = "EXCHANGING"
    BINDING_PRINCIPAL = "BINDING_PRINCIPAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class AuthenticatedContextState(StrEnum):
    ABSENT = "ABSENT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    ENDED = "ENDED"


class ProviderAvailabilityState(StrEnum):
    NOT_VERIFIED = "NOT_VERIFIED"
    VERIFYING = "VERIFYING"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INDETERMINATE = "INDETERMINATE"


class CallbackCategory(StrEnum):
    ACCEPTED = "ACCEPTED"
    PROVIDER_REJECTED = "PROVIDER_REJECTED"
    INVALID_METHOD = "INVALID_METHOD"
    INVALID_PATH = "INVALID_PATH"
    INVALID_HOST = "INVALID_HOST"
    TOKEN_MISSING = "TOKEN_MISSING"
    TOKEN_MULTIPLE = "TOKEN_MULTIPLE"
    DUPLICATE = "DUPLICATE"
    TIMED_OUT = "TIMED_OUT"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"


class AuthenticationAttemptCancellationResult(StrEnum):
    CANCELLED = "CANCELLED"
    ALREADY_CANCELLED = "ALREADY_CANCELLED"
    ALREADY_TERMINAL = "ALREADY_TERMINAL"
    NO_ACTIVE_ATTEMPT = "NO_ACTIVE_ATTEMPT"


class AuthenticationFailureCode(StrEnum):
    CONFIGURATION_INELIGIBLE = "CONFIGURATION_INELIGIBLE"
    ATTEMPT_ALREADY_ACTIVE = "ATTEMPT_ALREADY_ACTIVE"
    CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
    LOGIN_INITIATION_FAILED = "LOGIN_INITIATION_FAILED"
    CALLBACK_REJECTED = "CALLBACK_REJECTED"
    CALLBACK_TIMED_OUT = "CALLBACK_TIMED_OUT"
    TOKEN_EXCHANGE_REJECTED = "TOKEN_EXCHANGE_REJECTED"
    TOKEN_EXCHANGE_UNAVAILABLE = "TOKEN_EXCHANGE_UNAVAILABLE"
    PRINCIPAL_MISMATCHED = "PRINCIPAL_MISMATCHED"
    PRINCIPAL_UNCONFIRMED = "PRINCIPAL_UNCONFIRMED"
    PRINCIPAL_BINDING_UNAVAILABLE = "PRINCIPAL_BINDING_UNAVAILABLE"
    ACCESS_TOKEN_INVALID_OR_EXPIRED = "ACCESS_TOKEN_INVALID_OR_EXPIRED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    ATTEMPT_TIMED_OUT = "ATTEMPT_TIMED_OUT"
    LOCAL_CLEANUP_FAILED = "LOCAL_CLEANUP_FAILED"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


class CallbackReadiness(StrEnum):
    NOT_READY = "NOT_READY"
    READY = "READY"
    CLOSED = "CLOSED"


class BrowserOpenCategory(StrEnum):
    OPENED = "OPENED"
    DECLINED = "DECLINED"
    FAILED = "FAILED"


class AuthenticationModelFailure(StrEnum):
    BLANK_IDENTITY = "BLANK_IDENTITY"
    NAIVE_TIMESTAMP = "NAIVE_TIMESTAMP"
    INVALID_DEADLINE = "INVALID_DEADLINE"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    TERMINAL_ATTEMPT = "TERMINAL_ATTEMPT"
    PREMATURE_TIMEOUT = "PREMATURE_TIMEOUT"
    INVALID_OPERATION_COUNT = "INVALID_OPERATION_COUNT"
    OPERATION_CARDINALITY_EXCEEDED = "OPERATION_CARDINALITY_EXCEEDED"
    PROVIDER_AVAILABILITY_WITHHELD = "PROVIDER_AVAILABILITY_WITHHELD"


class AuthenticationModelError(ValueError):
    """Controlled lifecycle-model failure with no raw state attached."""

    def __init__(self, failure: AuthenticationModelFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class CoordinatedConsumptionState(StrEnum):
    """Sanitized coordinated-authority states."""

    UNUSED = "UNUSED"
    CONSUMED = "CONSUMED"
    CONSUMPTION_STATE_UNCERTAIN = "CONSUMPTION_STATE_UNCERTAIN"


class ConsumptionOutcomeCategory(StrEnum):
    """Mutually exclusive durable-consumption outcomes."""

    PRE_CONSUMPTION_VALIDATION_FAILED = "PRE_CONSUMPTION_VALIDATION_FAILED"
    POST_CONFIRMATION_CONSUMPTION_UNCERTAIN = (
        "POST_CONFIRMATION_CONSUMPTION_UNCERTAIN"
    )
    CONSUMED = "CONSUMED"


class RuntimeTerminationCategory(StrEnum):
    """Cleanup boundary after durable consumption has been proven."""

    PROVEN_CONSUMPTION_RUNTIME_TERMINATION = (
        "PROVEN_CONSUMPTION_RUNTIME_TERMINATION"
    )


class GovernedAuthenticationOperation(StrEnum):
    """Only operations admitted by the sanitized cardinality ledger."""

    ACTIVATION_VALIDATION = "ACTIVATION_VALIDATION"
    AUTHORITY_CONSUMPTION = "AUTHORITY_CONSUMPTION"
    ATTEMPT_RESERVATION = "ATTEMPT_RESERVATION"
    LISTENER_CONSTRUCTION = "LISTENER_CONSTRUCTION"
    LISTENER_BIND = "LISTENER_BIND"
    LOGIN_URL_GENERATION = "LOGIN_URL_GENERATION"
    BROWSER_LAUNCH = "BROWSER_LAUNCH"
    TERMINAL_CALLBACK = "TERMINAL_CALLBACK"
    API_SECRET_RETRIEVAL = "API_SECRET_RETRIEVAL"
    SESSION_EXCHANGE = "SESSION_EXCHANGE"
    INTENDED_PRINCIPAL_RETRIEVAL = "INTENDED_PRINCIPAL_RETRIEVAL"
    PRINCIPAL_PROFILE_VERIFICATION = "PRINCIPAL_PROFILE_VERIFICATION"
    CONTEXT_ESTABLISHMENT = "CONTEXT_ESTABLISHMENT"
    LOCAL_CLEANUP = "LOCAL_CLEANUP"
    PROVIDER_AVAILABILITY_VERIFICATION = "PROVIDER_AVAILABILITY_VERIFICATION"


@dataclass(frozen=True, slots=True)
class SanitizedOperationCount:
    """One non-sensitive operation count with bounded cardinality."""

    operation: GovernedAuthenticationOperation
    count: int

    def __post_init__(self) -> None:
        if type(self.operation) is not GovernedAuthenticationOperation or type(
            self.count
        ) is not int or self.count < 0:
            raise AuthenticationModelError(
                AuthenticationModelFailure.INVALID_OPERATION_COUNT
            )
        maximum = (
            0
            if self.operation
            is GovernedAuthenticationOperation.PROVIDER_AVAILABILITY_VERIFICATION
            else 1
        )
        if self.count > maximum:
            failure = (
                AuthenticationModelFailure.PROVIDER_AVAILABILITY_WITHHELD
                if maximum == 0
                else AuthenticationModelFailure.OPERATION_CARDINALITY_EXCEEDED
            )
            raise AuthenticationModelError(failure)


@dataclass(frozen=True, slots=True, repr=False)
class SanitizedOperationLedger:
    """Immutable, non-serializable count-only authentication evidence."""

    counts: tuple[SanitizedOperationCount, ...]

    def __post_init__(self) -> None:
        if type(self.counts) is not tuple:
            raise AuthenticationModelError(
                AuthenticationModelFailure.INVALID_OPERATION_COUNT
            )
        expected = tuple(GovernedAuthenticationOperation)
        if tuple(item.operation for item in self.counts) != expected:
            raise AuthenticationModelError(
                AuthenticationModelFailure.INVALID_OPERATION_COUNT
            )

    @classmethod
    def empty(cls) -> "SanitizedOperationLedger":
        return cls(
            tuple(
                SanitizedOperationCount(operation=operation, count=0)
                for operation in GovernedAuthenticationOperation
            )
        )

    def count_for(self, operation: GovernedAuthenticationOperation) -> int:
        if type(operation) is not GovernedAuthenticationOperation:
            raise AuthenticationModelError(
                AuthenticationModelFailure.INVALID_OPERATION_COUNT
            )
        return self.counts[tuple(GovernedAuthenticationOperation).index(operation)].count

    def record(
        self,
        operation: GovernedAuthenticationOperation,
    ) -> "SanitizedOperationLedger":
        """Return a new snapshot after one bounded operation."""

        current = self.count_for(operation)
        replacement = SanitizedOperationCount(operation=operation, count=current + 1)
        return SanitizedOperationLedger(
            tuple(
                replacement if item.operation is operation else item
                for item in self.counts
            )
        )

    def __repr__(self) -> str:
        return "<SanitizedOperationLedger counts-only>"

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("SANITIZED_OPERATION_LEDGER_SERIALIZATION_PROHIBITED")


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class ProviderAuthenticationConfiguration:
    """Non-serializable authentication configuration with bounded API-key use."""

    provider: ProviderId
    _api_key: str = field(repr=False)
    redirect_uri: str
    intended_registration_ref: RegistrationRef
    credential_ref: str

    def __post_init__(self) -> None:
        values = (
            self.provider,
            self._api_key,
            self.redirect_uri,
            self.intended_registration_ref,
            self.credential_ref,
        )
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise AuthenticationModelError(AuthenticationModelFailure.BLANK_IDENTITY)

    def use_api_key(self, operation: Callable[[str], None]) -> None:
        """Supply the API key without adding a public value getter."""

        operation(self._api_key)

    def __repr__(self) -> str:
        return "<ProviderAuthenticationConfiguration redacted>"

    def __str__(self) -> str:
        return "<ProviderAuthenticationConfiguration redacted>"

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("AUTHENTICATION_CONFIGURATION_SERIALIZATION_PROHIBITED")


@dataclass(frozen=True, slots=True)
class SessionStatus:
    attempt_state: AuthenticationAttemptState | None
    context_state: AuthenticatedContextState
    provider_availability: ProviderAvailabilityState
    failure_code: AuthenticationFailureCode | None
    attempt_active: bool
    context_reusable: bool


@dataclass(frozen=True, slots=True, repr=False)
class AuthenticationOutcomeEvidence:
    """Approved retained evidence with no Provider or credential material."""

    attempt_id: AttemptId
    provider: ProviderId
    intended_registration_ref: RegistrationRef
    state: AuthenticationAttemptState
    binding_result: PrincipalBindingResult | None
    failure_code: AuthenticationFailureCode | None
    callback_consumed: bool
    candidate_disposed: bool
    completed_at: datetime

    def __post_init__(self) -> None:
        _require_nonblank(self.attempt_id, self.provider, self.intended_registration_ref)
        _require_aware(self.completed_at)

    def __repr__(self) -> str:
        return "<AuthenticationOutcomeEvidence sanitized>"


@dataclass(frozen=True, slots=True, repr=False, eq=False)
class BrowserOpenRequest:
    official_login_url: str

    def __post_init__(self) -> None:
        _require_nonblank(self.official_login_url)

    def __repr__(self) -> str:
        return "<BrowserOpenRequest redacted>"

    def __str__(self) -> str:
        return "<BrowserOpenRequest redacted>"

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("BROWSER_OPEN_REQUEST_SERIALIZATION_PROHIBITED")


@dataclass(frozen=True, slots=True)
class BrowserOpenResult:
    category: BrowserOpenCategory


_TERMINAL_STATES = frozenset(
    {
        AuthenticationAttemptState.SUCCEEDED,
        AuthenticationAttemptState.FAILED,
        AuthenticationAttemptState.CANCELLED,
        AuthenticationAttemptState.TIMED_OUT,
    }
)

_NEXT_STATE = {
    AuthenticationAttemptState.CREATED: AuthenticationAttemptState.LISTENER_READY,
    AuthenticationAttemptState.LISTENER_READY: (
        AuthenticationAttemptState.BROWSER_OPEN_REQUESTED
    ),
    AuthenticationAttemptState.BROWSER_OPEN_REQUESTED: (
        AuthenticationAttemptState.AWAITING_CALLBACK
    ),
    AuthenticationAttemptState.AWAITING_CALLBACK: (
        AuthenticationAttemptState.CALLBACK_ACCEPTED
    ),
    AuthenticationAttemptState.CALLBACK_ACCEPTED: AuthenticationAttemptState.EXCHANGING,
    AuthenticationAttemptState.EXCHANGING: (
        AuthenticationAttemptState.BINDING_PRINCIPAL
    ),
    AuthenticationAttemptState.BINDING_PRINCIPAL: AuthenticationAttemptState.SUCCEEDED,
}


@dataclass(slots=True, repr=False, eq=False)
class AuthenticationAttempt:
    """Service-private mutable aggregate for one bounded attempt."""

    attempt_id: AttemptId
    provider: ProviderId
    intended_registration_ref: RegistrationRef
    created_at: datetime
    started_at: datetime
    expires_at: datetime
    listener_ref: str
    state: AuthenticationAttemptState = AuthenticationAttemptState.CREATED
    callback_consumed: bool = False
    exchange_started: bool = False
    candidate_created: bool = False
    candidate_disposed: bool = False
    terminal_code: AuthenticationFailureCode | None = None
    binding_result: PrincipalBindingResult | None = None

    def __post_init__(self) -> None:
        _require_nonblank(
            self.attempt_id,
            self.provider,
            self.intended_registration_ref,
            self.listener_ref,
        )
        _require_aware(self.created_at, self.started_at, self.expires_at)
        if self.started_at < self.created_at or self.expires_at <= self.started_at:
            raise AuthenticationModelError(AuthenticationModelFailure.INVALID_DEADLINE)
        if self.state is not AuthenticationAttemptState.CREATED:
            raise AuthenticationModelError(AuthenticationModelFailure.INVALID_TRANSITION)

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL_STATES

    def transition(
        self,
        target: AuthenticationAttemptState,
        *,
        at: datetime,
        failure_code: AuthenticationFailureCode | None = None,
    ) -> None:
        """Apply one canonical transition with terminal and deadline enforcement."""

        _require_aware(at)
        if self.terminal:
            raise AuthenticationModelError(AuthenticationModelFailure.TERMINAL_ATTEMPT)

        if target is AuthenticationAttemptState.TIMED_OUT:
            if at < self.expires_at:
                raise AuthenticationModelError(
                    AuthenticationModelFailure.PREMATURE_TIMEOUT
                )
        elif at >= self.expires_at:
            raise AuthenticationModelError(AuthenticationModelFailure.INVALID_TRANSITION)
        elif target not in (
            _NEXT_STATE.get(self.state),
            AuthenticationAttemptState.FAILED,
            AuthenticationAttemptState.CANCELLED,
        ):
            raise AuthenticationModelError(AuthenticationModelFailure.INVALID_TRANSITION)

        if target is AuthenticationAttemptState.SUCCEEDED and (
            self.binding_result is not PrincipalBindingResult.MATCHED
            or not self.candidate_created
        ):
            raise AuthenticationModelError(AuthenticationModelFailure.INVALID_TRANSITION)
        if target in (
            AuthenticationAttemptState.FAILED,
            AuthenticationAttemptState.TIMED_OUT,
        ) and failure_code is None:
            raise AuthenticationModelError(AuthenticationModelFailure.INVALID_TRANSITION)

        self.state = target
        if target is AuthenticationAttemptState.CALLBACK_ACCEPTED:
            self.callback_consumed = True
        if target is AuthenticationAttemptState.EXCHANGING:
            self.exchange_started = True
        if target in _TERMINAL_STATES:
            self.terminal_code = failure_code

    def sanitized_evidence(self, *, completed_at: datetime) -> AuthenticationOutcomeEvidence:
        """Project current or terminal state without sensitive carriers."""

        return AuthenticationOutcomeEvidence(
            attempt_id=self.attempt_id,
            provider=self.provider,
            intended_registration_ref=self.intended_registration_ref,
            state=self.state,
            binding_result=self.binding_result,
            failure_code=self.terminal_code,
            callback_consumed=self.callback_consumed,
            candidate_disposed=self.candidate_disposed,
            completed_at=completed_at,
        )

    def __repr__(self) -> str:
        return "<AuthenticationAttempt redacted>"

    def __str__(self) -> str:
        return "<AuthenticationAttempt redacted>"

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("AUTHENTICATION_ATTEMPT_SERIALIZATION_PROHIBITED")


def _require_nonblank(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise AuthenticationModelError(AuthenticationModelFailure.BLANK_IDENTITY)


def _require_aware(*values: datetime) -> None:
    if any(value.tzinfo is None or value.utcoffset() is None for value in values):
        raise AuthenticationModelError(AuthenticationModelFailure.NAIVE_TIMESTAMP)
