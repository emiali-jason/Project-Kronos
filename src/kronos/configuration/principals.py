"""Provider-neutral intended-principal custody contracts."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class PrincipalBindingResult(StrEnum):
    """Sanitized outcomes for protected intended-principal binding."""

    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    UNCONFIRMED = "UNCONFIRMED"
    UNAVAILABLE = "UNAVAILABLE"


class IntendedPrincipalResolutionOutcome(StrEnum):
    """Sanitized intended-principal resolution outcomes."""

    RESOLVED = "RESOLVED"
    NOT_FOUND = "NOT_FOUND"
    ACCESS_DENIED = "ACCESS_DENIED"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    SANITIZED_FAILURE = "SANITIZED_FAILURE"


@dataclass(frozen=True, slots=True)
class IntendedPrincipalResolutionResult:
    """Retain only a resolution category and optional binding outcome."""

    outcome: IntendedPrincipalResolutionOutcome
    binding_result: PrincipalBindingResult | None = None

    def __post_init__(self) -> None:
        if (
            self.outcome is IntendedPrincipalResolutionOutcome.RESOLVED
            and self.binding_result is None
        ):
            raise ValueError("RESOLVED_REQUIRES_BINDING_RESULT")
        if (
            self.outcome is not IntendedPrincipalResolutionOutcome.RESOLVED
            and self.binding_result is not None
        ):
            raise ValueError("UNRESOLVED_FORBIDS_BINDING_RESULT")


class PrincipalEvidence(Protocol):
    """Opaque minimum Provider evidence used inside one comparison."""

    def compare_expected(self, expected_principal: str) -> PrincipalBindingResult:
        """Compare without returning either principal value."""

    def close(self) -> None:
        """Release transient Provider evidence."""


class IntendedPrincipalLease(Protocol):
    """One-operation protected expected-principal custody."""

    def compare_once(self, evidence: PrincipalEvidence) -> PrincipalBindingResult:
        """Compare once inside the protected lease boundary."""

    def close(self) -> None:
        """Release the expected-principal reference."""


class IntendedPrincipalResolver(Protocol):
    """Resolve one internal registration reference through protected custody."""

    def use_resolved_once(
        self,
        registration_ref: str,
        operation: Callable[[IntendedPrincipalLease], PrincipalBindingResult],
    ) -> IntendedPrincipalResolutionResult:
        """Supply a one-operation lease without exposing the expected value."""


class IntendedPrincipalLeaseFailure(StrEnum):
    """Controlled failures for intended-principal custody."""

    INVALID_PRINCIPAL = "INVALID_PRINCIPAL"
    ALREADY_USED = "ALREADY_USED"
    CLOSED = "CLOSED"


class IntendedPrincipalLeaseError(RuntimeError):
    """A sanitized intended-principal lease failure."""

    def __init__(self, failure: IntendedPrincipalLeaseFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


class OneUseIntendedPrincipalLease:
    """In-memory one-use lease supplied by a protected resolver backend."""

    __slots__ = ("_closed", "_expected_principal", "_used")
    __hash__ = None

    def __init__(self, expected_principal: str) -> None:
        if not isinstance(expected_principal, str) or not expected_principal:
            raise IntendedPrincipalLeaseError(
                IntendedPrincipalLeaseFailure.INVALID_PRINCIPAL
            )
        self._expected_principal: str | None = expected_principal
        self._used = False
        self._closed = False

    def compare_once(self, evidence: PrincipalEvidence) -> PrincipalBindingResult:
        """Perform exactly one protected comparison and close both carriers."""

        if self._closed:
            raise IntendedPrincipalLeaseError(IntendedPrincipalLeaseFailure.CLOSED)
        if self._used:
            raise IntendedPrincipalLeaseError(
                IntendedPrincipalLeaseFailure.ALREADY_USED
            )
        expected = self._expected_principal
        if expected is None:
            raise IntendedPrincipalLeaseError(IntendedPrincipalLeaseFailure.CLOSED)

        self._used = True
        try:
            return evidence.compare_expected(expected)
        finally:
            try:
                evidence.close()
            finally:
                self.close()

    def close(self) -> None:
        """Close idempotently and release the retained reference."""

        self._expected_principal = None
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def used(self) -> bool:
        return self._used

    def __repr__(self) -> str:
        return "<IntendedPrincipalLease redacted>"

    def __str__(self) -> str:
        return "<IntendedPrincipalLease redacted>"

    def __copy__(self) -> "OneUseIntendedPrincipalLease":
        raise TypeError("INTENDED_PRINCIPAL_LEASE_COPY_PROHIBITED")

    def __deepcopy__(self, _memo: object) -> "OneUseIntendedPrincipalLease":
        raise TypeError("INTENDED_PRINCIPAL_LEASE_COPY_PROHIBITED")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("INTENDED_PRINCIPAL_LEASE_SERIALIZATION_PROHIBITED")
