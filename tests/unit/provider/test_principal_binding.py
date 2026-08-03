import gc

import pytest

from kronos.configuration.principals import (
    IntendedPrincipalResolutionOutcome,
    IntendedPrincipalResolutionResult,
    OneUseIntendedPrincipalLease,
    PrincipalBindingResult,
)
from kronos.provider.services.provider_authentication import (
    ProtectedPrincipalBindingVerifier,
)


class _Evidence:
    __slots__ = ("closed", "compare_count", "_principal")

    def __init__(self, principal: str) -> None:
        self._principal: str | None = principal
        self.compare_count = 0
        self.closed = False

    def compare_expected(self, expected: str) -> PrincipalBindingResult:
        self.compare_count += 1
        principal = self._principal
        self._principal = None
        if principal is None:
            return PrincipalBindingResult.UNCONFIRMED
        return (
            PrincipalBindingResult.MATCHED
            if principal == expected
            else PrincipalBindingResult.MISMATCHED
        )

    def close(self) -> None:
        self._principal = None
        self.closed = True


class _Resolver:
    def __init__(
        self,
        *,
        expected: str = "EXPECTED123",
        outcome: IntendedPrincipalResolutionOutcome = (
            IntendedPrincipalResolutionOutcome.RESOLVED
        ),
        error: BaseException | None = None,
    ) -> None:
        self.expected = expected
        self.outcome = outcome
        self.error = error
        self.resolve_count = 0
        self.registration_refs: list[str] = []
        self.last_lease: OneUseIntendedPrincipalLease | None = None

    def use_resolved_once(self, registration_ref, operation):  # type: ignore[no-untyped-def]
        self.resolve_count += 1
        self.registration_refs.append(registration_ref)
        if self.error is not None:
            raise self.error
        if self.outcome is not IntendedPrincipalResolutionOutcome.RESOLVED:
            return IntendedPrincipalResolutionResult(self.outcome)
        lease = OneUseIntendedPrincipalLease(self.expected)
        self.last_lease = lease
        binding = operation(lease)
        return IntendedPrincipalResolutionResult(
            IntendedPrincipalResolutionOutcome.RESOLVED,
            binding,
        )


@pytest.mark.parametrize(
    ("provider_principal", "expected", "binding"),
    [
        ("EXPECTED123", "EXPECTED123", PrincipalBindingResult.MATCHED),
        ("OTHER456", "EXPECTED123", PrincipalBindingResult.MISMATCHED),
    ],
)
def test_binding_occurs_once_inside_protected_lease(
    provider_principal: str,
    expected: str,
    binding: PrincipalBindingResult,
) -> None:
    resolver = _Resolver(expected=expected)
    verifier = ProtectedPrincipalBindingVerifier(resolver)
    evidence = _Evidence(provider_principal)

    result = verifier.verify_principal_binding(evidence, "registration-ref")

    assert result is binding
    assert resolver.resolve_count == 1
    assert resolver.registration_refs == ["registration-ref"]
    assert resolver.last_lease is not None
    assert resolver.last_lease.used is True
    assert resolver.last_lease.closed is True
    assert evidence.compare_count == 1
    assert evidence.closed is True
    assert provider_principal not in gc.get_referents(evidence)
    assert expected not in gc.get_referents(resolver.last_lease)


@pytest.mark.parametrize(
    ("resolution", "binding"),
    [
        (
            IntendedPrincipalResolutionOutcome.NOT_FOUND,
            PrincipalBindingResult.UNCONFIRMED,
        ),
        (
            IntendedPrincipalResolutionOutcome.INVALID_CONFIGURATION,
            PrincipalBindingResult.UNCONFIRMED,
        ),
        (
            IntendedPrincipalResolutionOutcome.ACCESS_DENIED,
            PrincipalBindingResult.UNAVAILABLE,
        ),
        (
            IntendedPrincipalResolutionOutcome.BACKEND_UNAVAILABLE,
            PrincipalBindingResult.UNAVAILABLE,
        ),
        (
            IntendedPrincipalResolutionOutcome.SANITIZED_FAILURE,
            PrincipalBindingResult.UNAVAILABLE,
        ),
    ],
)
def test_resolution_failures_are_fail_closed_and_close_evidence(
    resolution: IntendedPrincipalResolutionOutcome,
    binding: PrincipalBindingResult,
) -> None:
    resolver = _Resolver(outcome=resolution)
    evidence = _Evidence("TRANSIENT123")

    result = ProtectedPrincipalBindingVerifier(resolver).verify_principal_binding(
        evidence,
        "registration-ref",
    )

    assert result is binding
    assert resolver.resolve_count == 1
    assert evidence.compare_count == 0
    assert evidence.closed is True
    assert "TRANSIENT123" not in gc.get_referents(evidence)


def test_raw_resolver_exception_is_sanitized_and_evidence_is_closed() -> None:
    resolver = _Resolver(error=RuntimeError("raw protected-store material"))
    evidence = _Evidence("TRANSIENT123")

    result = ProtectedPrincipalBindingVerifier(resolver).verify_principal_binding(
        evidence,
        "registration-ref",
    )

    assert result is PrincipalBindingResult.UNAVAILABLE
    assert evidence.closed is True
    assert "raw protected-store material" not in repr(result)
