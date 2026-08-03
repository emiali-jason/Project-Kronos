from __future__ import annotations

import copy
import pickle

import pytest

from kronos.configuration.principals import (
    IntendedPrincipalLeaseError,
    IntendedPrincipalLeaseFailure,
    IntendedPrincipalResolutionOutcome,
    IntendedPrincipalResolutionResult,
    OneUseIntendedPrincipalLease,
    PrincipalBindingResult,
)


EXPECTED = "EXPECTED123"
MATCHING = "EXPECTED123"
MISMATCHING = "OTHER456"


class FakePrincipalEvidence:
    def __init__(self, candidate: str | None) -> None:
        self._candidate = candidate
        self.closed = False
        self.comparisons = 0

    def compare_expected(self, expected_principal: str) -> PrincipalBindingResult:
        self.comparisons += 1
        if self._candidate is None:
            return PrincipalBindingResult.UNCONFIRMED
        if self._candidate == expected_principal:
            return PrincipalBindingResult.MATCHED
        return PrincipalBindingResult.MISMATCHED

    def close(self) -> None:
        self._candidate = None
        self.closed = True


def test_principal_binding_results_are_exact() -> None:
    assert [result.value for result in PrincipalBindingResult] == [
        "MATCHED",
        "MISMATCHED",
        "UNCONFIRMED",
        "UNAVAILABLE",
    ]


def test_intended_principal_resolution_outcomes_are_exact() -> None:
    assert [outcome.value for outcome in IntendedPrincipalResolutionOutcome] == [
        "RESOLVED",
        "NOT_FOUND",
        "ACCESS_DENIED",
        "BACKEND_UNAVAILABLE",
        "INVALID_CONFIGURATION",
        "SANITIZED_FAILURE",
    ]


def test_resolution_result_requires_binding_only_when_resolved() -> None:
    resolved = IntendedPrincipalResolutionResult(
        IntendedPrincipalResolutionOutcome.RESOLVED,
        PrincipalBindingResult.MATCHED,
    )
    missing = IntendedPrincipalResolutionResult(
        IntendedPrincipalResolutionOutcome.NOT_FOUND
    )

    assert resolved.binding_result is PrincipalBindingResult.MATCHED
    assert missing.binding_result is None
    with pytest.raises(ValueError, match="RESOLVED_REQUIRES_BINDING_RESULT"):
        IntendedPrincipalResolutionResult(
            IntendedPrincipalResolutionOutcome.RESOLVED
        )
    with pytest.raises(ValueError, match="UNRESOLVED_FORBIDS_BINDING_RESULT"):
        IntendedPrincipalResolutionResult(
            IntendedPrincipalResolutionOutcome.ACCESS_DENIED,
            PrincipalBindingResult.UNAVAILABLE,
        )


@pytest.mark.parametrize(
    ("candidate", "expected_result"),
    [
        (MATCHING, PrincipalBindingResult.MATCHED),
        (MISMATCHING, PrincipalBindingResult.MISMATCHED),
        (None, PrincipalBindingResult.UNCONFIRMED),
    ],
)
def test_intended_principal_lease_compares_once_and_closes_carriers(
    candidate: str | None,
    expected_result: PrincipalBindingResult,
) -> None:
    lease = OneUseIntendedPrincipalLease(EXPECTED)
    evidence = FakePrincipalEvidence(candidate)

    assert lease.compare_once(evidence) is expected_result
    assert evidence.comparisons == 1
    assert evidence.closed is True
    assert lease.used is True
    assert lease.closed is True
    with pytest.raises(IntendedPrincipalLeaseError) as captured:
        lease.compare_once(FakePrincipalEvidence(MATCHING))
    assert captured.value.failure is IntendedPrincipalLeaseFailure.CLOSED


def test_intended_principal_lease_closes_evidence_when_comparison_raises() -> None:
    class FailingEvidence(FakePrincipalEvidence):
        def compare_expected(
            self,
            expected_principal: str,
        ) -> PrincipalBindingResult:
            del expected_principal
            raise RuntimeError("SYNTHETIC_COMPARISON_FAILURE")

    lease = OneUseIntendedPrincipalLease(EXPECTED)
    evidence = FailingEvidence(MATCHING)

    with pytest.raises(RuntimeError, match="SYNTHETIC_COMPARISON_FAILURE"):
        lease.compare_once(evidence)

    assert evidence.closed is True
    assert lease.closed is True


def test_intended_principal_lease_closes_when_evidence_cleanup_raises() -> None:
    class CleanupFailingEvidence(FakePrincipalEvidence):
        def close(self) -> None:
            super().close()
            raise RuntimeError("SYNTHETIC_CLEANUP_FAILURE")

    lease = OneUseIntendedPrincipalLease(EXPECTED)
    evidence = CleanupFailingEvidence(MATCHING)

    with pytest.raises(RuntimeError, match="SYNTHETIC_CLEANUP_FAILURE"):
        lease.compare_once(evidence)

    assert lease.closed is True


def test_intended_principal_lease_close_is_idempotent() -> None:
    lease = OneUseIntendedPrincipalLease(EXPECTED)

    lease.close()
    lease.close()

    assert lease.closed is True
    assert lease.used is False


def test_intended_principal_lease_is_redacted_and_has_no_value_getter() -> None:
    lease = OneUseIntendedPrincipalLease(EXPECTED)

    assert repr(lease) == "<IntendedPrincipalLease redacted>"
    assert str(lease) == "<IntendedPrincipalLease redacted>"
    assert EXPECTED not in repr(lease)
    assert not hasattr(lease, "expected_principal")
    assert not hasattr(lease, "principal")
    assert not hasattr(lease, "value")


@pytest.mark.parametrize("operation", [copy.copy, copy.deepcopy, pickle.dumps])
def test_intended_principal_copy_and_serialization_are_prohibited(
    operation: object,
) -> None:
    lease = OneUseIntendedPrincipalLease(EXPECTED)

    with pytest.raises(TypeError) as captured:
        operation(lease)  # type: ignore[operator]

    assert EXPECTED not in str(captured.value)


def test_fake_resolver_supplies_one_lease_and_retains_only_sanitized_result() -> None:
    class FakeResolver:
        def __init__(self) -> None:
            self.references: list[str] = []
            self.lease: OneUseIntendedPrincipalLease | None = None

        def use_resolved_once(
            self,
            registration_ref: str,
            operation: object,
        ) -> IntendedPrincipalResolutionResult:
            self.references.append(registration_ref)
            lease = OneUseIntendedPrincipalLease(EXPECTED)
            self.lease = lease
            result = operation(lease)  # type: ignore[operator]
            return IntendedPrincipalResolutionResult(
                IntendedPrincipalResolutionOutcome.RESOLVED,
                result,
            )

    resolver = FakeResolver()
    evidence = FakePrincipalEvidence(MATCHING)

    result = resolver.use_resolved_once(
        "registration-reference",
        lambda lease: lease.compare_once(evidence),
    )

    assert resolver.references == ["registration-reference"]
    assert result == IntendedPrincipalResolutionResult(
        IntendedPrincipalResolutionOutcome.RESOLVED,
        PrincipalBindingResult.MATCHED,
    )
    assert resolver.lease is not None and resolver.lease.closed is True
    assert EXPECTED not in repr(result)
