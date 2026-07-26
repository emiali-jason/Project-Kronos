import pytest

from kronos.provider.exceptions.access import (
    ProviderAccessPreconditionCode,
    ProviderAccessPreconditionError,
)
from kronos.provider.models.access import (
    ProviderOperationalAvailability,
    ProviderUsabilityState,
)
from kronos.provider.models.configuration import (
    ConfigurationBoundaryInput,
    ConfigurationEligibility,
    ConfigurationEligibilityState,
    OperationalConfigurationValidity,
    OperationalConfigurationValidityState,
    RuntimeConfiguration,
)
from kronos.provider.models.context import (
    AuthenticationOutcome,
    AuthenticationOutcomeKind,
    ContextLifecycleReason,
    ContextValidity,
    ProviderEvidenceKind,
    ProviderProvenance,
)
from kronos.provider.services.access import ProviderContextService


def _configuration(
    *,
    provider: str = "KITE",
    eligible: bool = True,
    valid: bool = True,
) -> ConfigurationBoundaryInput:
    return ConfigurationBoundaryInput(
        runtime=RuntimeConfiguration(provider, "unit-context"),
        eligibility=ConfigurationEligibility(
            ConfigurationEligibilityState.ELIGIBLE
            if eligible
            else ConfigurationEligibilityState.INELIGIBLE
        ),
        validity=OperationalConfigurationValidity(
            OperationalConfigurationValidityState.VALID
            if valid
            else OperationalConfigurationValidityState.INVALID
        ),
    )


def _success(configuration: ConfigurationBoundaryInput) -> AuthenticationOutcome:
    return AuthenticationOutcome(
        AuthenticationOutcomeKind.SUCCESS,
        ProviderProvenance(configuration.runtime.provider, "activity-1"),
        verified=True,
    )


def test_verified_success_establishes_one_bounded_context_and_evidence() -> None:
    service = ProviderContextService("KITE", _success)

    outcome = service.authenticate(_configuration())
    context = service.current_context()

    assert outcome.kind is AuthenticationOutcomeKind.SUCCESS
    assert context is not None
    assert context.validity is ContextValidity.VALID
    assert context.context_id == outcome.provenance.activity_id
    assert [item.kind for item in service.evidence()] == [
        ProviderEvidenceKind.AUTHENTICATION_ACTIVITY,
        ProviderEvidenceKind.AUTHENTICATION_OUTCOME,
        ProviderEvidenceKind.CONTEXT_ESTABLISHED,
    ]


def test_unverified_success_is_prohibited() -> None:
    with pytest.raises(ValueError, match="verified provider evidence"):
        AuthenticationOutcome(
            AuthenticationOutcomeKind.SUCCESS,
            ProviderProvenance("KITE", "activity-unverified"),
        )


@pytest.mark.parametrize(
    ("configuration", "expected_code"),
    [
        (
            _configuration(provider="OTHER"),
            ProviderAccessPreconditionCode.PROVIDER_MISMATCH,
        ),
        (
            _configuration(eligible=False),
            ProviderAccessPreconditionCode.CONFIGURATION_INELIGIBLE,
        ),
        (
            _configuration(valid=False),
            ProviderAccessPreconditionCode.CONFIGURATION_INELIGIBLE,
        ),
    ],
)
def test_configuration_precondition_failure_is_not_authentication_rejection(
    configuration: ConfigurationBoundaryInput,
    expected_code: ProviderAccessPreconditionCode,
) -> None:
    called = False

    def activity(_configuration: ConfigurationBoundaryInput) -> AuthenticationOutcome:
        nonlocal called
        called = True
        return _success(_configuration)

    service = ProviderContextService("KITE", activity)

    with pytest.raises(ProviderAccessPreconditionError) as captured:
        service.authenticate(configuration)

    assert captured.value.code is expected_code
    assert called is False
    assert service.current_context() is None
    assert service.evidence() == ()


def test_rejection_and_failure_never_establish_context() -> None:
    rejected = ProviderContextService(
        "KITE",
        lambda configuration: AuthenticationOutcome(
            AuthenticationOutcomeKind.REJECTED,
            ProviderProvenance(configuration.runtime.provider, "activity-rejected"),
            ContextLifecycleReason.PROVIDER_DECISION,
        ),
    )
    failed = ProviderContextService(
        "KITE",
        lambda configuration: AuthenticationOutcome(
            AuthenticationOutcomeKind.FAILED,
            ProviderProvenance(configuration.runtime.provider, "activity-failed"),
            ContextLifecycleReason.PROVIDER_OPERATIONALLY_UNAVAILABLE,
        ),
    )

    assert rejected.authenticate(_configuration()).kind is AuthenticationOutcomeKind.REJECTED
    assert failed.authenticate(_configuration()).kind is AuthenticationOutcomeKind.FAILED
    assert rejected.current_context() is None
    assert failed.current_context() is None
    assert (
        failed.availability().operational
        is ProviderOperationalAvailability.UNAVAILABLE
    )


def test_invalidation_and_termination_preserve_context_correlation() -> None:
    service = ProviderContextService("KITE", _success)
    service.authenticate(_configuration())
    original = service.current_context()
    assert original is not None

    invalidated = service.invalidate_context()
    invalid_context = service.current_context()
    assert invalidated is not None
    assert invalid_context is not None
    assert invalid_context.context_id == original.context_id
    assert invalid_context.provenance == original.provenance
    assert invalid_context.validity is ContextValidity.INVALID
    assert invalidated.provenance == original.provenance

    terminated = service.terminate_context(ContextLifecycleReason.EXPLICIT_TERMINATION)
    terminated_context = service.current_context()
    assert terminated is not None
    assert terminated_context is not None
    assert terminated_context.context_id == original.context_id
    assert terminated_context.provenance == original.provenance
    assert terminated_context.validity is ContextValidity.TERMINATED
    assert terminated.provenance == original.provenance


def test_usability_requires_configuration_context_and_operational_availability() -> None:
    service = ProviderContextService("KITE", _success)

    assert (
        service.availability().operational
        is ProviderOperationalAvailability.NOT_ESTABLISHED
    )
    assert (
        service.usability(_configuration()).state
        is ProviderUsabilityState.UNUSABLE
    )

    service.authenticate(_configuration())

    assert (
        service.availability().operational
        is ProviderOperationalAvailability.AVAILABLE
    )
    assert service.usability(_configuration()).state is ProviderUsabilityState.USABLE
    assert (
        service.usability(_configuration(valid=False)).state
        is ProviderUsabilityState.UNUSABLE
    )
