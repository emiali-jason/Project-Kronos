"""Provider-neutral secure-credential contracts and one-use custody."""

from collections.abc import Callable
from enum import StrEnum
from typing import Protocol, TypeVar


_ResultT = TypeVar("_ResultT")


class CredentialRetrievalOutcome(StrEnum):
    """Sanitized outcomes produced by a secure-credential backend."""

    FOUND = "FOUND"
    MISSING = "MISSING"
    ACCESS_DENIED = "ACCESS_DENIED"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    TIMED_OUT = "TIMED_OUT"
    MALFORMED = "MALFORMED"


class SecretLeaseFailure(StrEnum):
    """Controlled failures for the one-operation secret lease."""

    INVALID_SECRET = "INVALID_SECRET"
    ALREADY_USED = "ALREADY_USED"
    CLOSED = "CLOSED"
    SECRET_RETURNED = "SECRET_RETURNED"


class SecretLeaseError(RuntimeError):
    """A sanitized lease failure containing no secret material."""

    def __init__(self, failure: SecretLeaseFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class SecretLease(Protocol):
    """One-operation access to a protected secret."""

    def reveal_for_call(
        self,
        operation: Callable[[str], _ResultT],
    ) -> _ResultT:
        """Supply the secret to one bounded operation."""

    def close(self) -> None:
        """Release the ordinary Python reference held by the lease."""


class SecureCredentialSource(Protocol):
    """Provider-neutral protected-credential retrieval boundary."""

    def acquire(self, credential_ref: str) -> SecretLease:
        """Acquire one lease for a non-sensitive credential reference."""


class OneUseSecretLease:
    """In-memory one-use lease used by protected credential backends."""

    __slots__ = ("_closed", "_secret", "_used")
    __hash__ = None

    def __init__(self, secret: str) -> None:
        if not isinstance(secret, str) or not secret:
            raise SecretLeaseError(SecretLeaseFailure.INVALID_SECRET)
        self._secret: str | None = secret
        self._used = False
        self._closed = False

    def reveal_for_call(
        self,
        operation: Callable[[str], _ResultT],
    ) -> _ResultT:
        """Invoke one operation and close the lease on every exit path."""

        if self._closed:
            raise SecretLeaseError(SecretLeaseFailure.CLOSED)
        if self._used:
            raise SecretLeaseError(SecretLeaseFailure.ALREADY_USED)
        secret = self._secret
        if secret is None:
            raise SecretLeaseError(SecretLeaseFailure.CLOSED)

        self._used = True
        try:
            result = operation(secret)
            if result is secret or (isinstance(result, str) and result == secret):
                raise SecretLeaseError(SecretLeaseFailure.SECRET_RETURNED)
            return result
        finally:
            self.close()

    def close(self) -> None:
        """Close idempotently and release the retained reference."""

        self._secret = None
        self._closed = True

    @property
    def closed(self) -> bool:
        """Expose lifecycle state without exposing secret material."""

        return self._closed

    @property
    def used(self) -> bool:
        """Expose operation cardinality without exposing secret material."""

        return self._used

    def __repr__(self) -> str:
        return "<SecretLease redacted>"

    def __str__(self) -> str:
        return "<SecretLease redacted>"

    def __copy__(self) -> "OneUseSecretLease":
        raise TypeError("SECRET_LEASE_COPY_PROHIBITED")

    def __deepcopy__(self, _memo: object) -> "OneUseSecretLease":
        raise TypeError("SECRET_LEASE_COPY_PROHIBITED")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("SECRET_LEASE_SERIALIZATION_PROHIBITED")
