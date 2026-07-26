from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kronos.configuration.settings import Settings
from kronos.provider.adapters.kite.authentication import KiteContextEvidence
from kronos.provider.exceptions.access import ProviderAccessPreconditionError
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)
from kronos.provider.kite.adapter.kite_provider import KiteProvider
from kronos.provider.kite.auth.kite_authentication import KiteAuthentication
from kronos.provider.kite.context.kite_provider_context import KiteProviderContext
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
    AuthenticationOutcomeKind,
    ContextLifecycleReason,
    ContextValidity,
    ProviderEvidenceKind,
)


_TIMEZONE = ZoneInfo("Asia/Kolkata")
_API_KEY = "test-api-key"
_API_SECRET = "test-api-secret"
_REQUEST_TOKEN = "test-request-token"
_ACCESS_TOKEN = "test-access-token"


class _MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


class _FakeAuthenticationAdapter:
    def __init__(self) -> None:
        self.exchange_error: ProviderConnectivityError | None = None
        self.context_state = KiteContextEvidence.VALID
        self.terminate_error: ProviderConnectivityError | None = None
        self.login_count = 0
        self.exchange_count = 0
        self.terminate_count = 0
        self.request_token: str | None = None

    def login_url(self) -> str:
        self.login_count += 1
        return "https://kite.zerodha.com/connect/login?v=3&api_key=redacted"

    def exchange(self, request_token: str) -> None:
        self.exchange_count += 1
        self.request_token = request_token
        if self.exchange_error is not None:
            raise self.exchange_error

    def context_evidence(self) -> KiteContextEvidence:
        return self.context_state

    def terminate(self) -> None:
        self.terminate_count += 1
        if self.terminate_error is not None:
            raise self.terminate_error


class _FakeFactory:
    def __init__(self, adapter: _FakeAuthenticationAdapter) -> None:
        self.adapter = adapter
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self,
        api_key: str,
        api_secret: str,
    ) -> _FakeAuthenticationAdapter:
        self.calls.append((api_key, api_secret))
        return self.adapter


def _settings(
    *,
    api_key: str = _API_KEY,
    api_secret: str = _API_SECRET,
) -> Settings:
    return Settings(
        provider="KITE",
        kite_api_key=api_key,
        kite_api_secret=api_secret,
        kite_access_token="",
        kite_redirect_url="https://local.test/kite/callback",
    )


def _configuration(
    *,
    provider: str = "KITE",
    eligible: bool = True,
    valid: bool = True,
) -> ConfigurationBoundaryInput:
    return ConfigurationBoundaryInput(
        runtime=RuntimeConfiguration(provider, "test-operational-context"),
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


def _redirect_handler(_login_url: str, redirect_url: str) -> str:
    return f"{redirect_url}?status=success&request_token={_REQUEST_TOKEN}&action=login"


def _provider(
    *,
    adapter: _FakeAuthenticationAdapter | None = None,
    clock: _MutableClock | None = None,
    redirect_handler: object = _redirect_handler,
    settings: Settings | None = None,
) -> tuple[KiteProvider, _FakeAuthenticationAdapter, _MutableClock, _FakeFactory]:
    selected_adapter = adapter or _FakeAuthenticationAdapter()
    selected_clock = clock or _MutableClock(
        datetime(2026, 7, 26, 12, 0, tzinfo=_TIMEZONE)
    )
    factory = _FakeFactory(selected_adapter)
    authentication = KiteAuthentication(
        settings or _settings(),
        redirect_handler,  # type: ignore[arg-type]
        adapter_factory=factory,  # type: ignore[arg-type]
        clock=selected_clock,
    )
    provider = KiteProvider(authentication, KiteProviderContext())
    return provider, selected_adapter, selected_clock, factory


def test_official_flow_establishes_context_only_after_verified_exchange() -> None:
    provider, adapter, _, factory = _provider()

    outcome = provider.authenticate(_configuration())
    context = provider.current_context()

    assert outcome.kind is AuthenticationOutcomeKind.SUCCESS
    assert outcome.verified is True
    assert outcome.valid_until == datetime(
        2026,
        7,
        27,
        6,
        0,
        tzinfo=_TIMEZONE,
    )
    assert adapter.login_count == 1
    assert adapter.exchange_count == 1
    assert adapter.request_token == _REQUEST_TOKEN
    assert factory.calls == [(_API_KEY, _API_SECRET)]
    assert context is not None
    assert context.validity is ContextValidity.VALID
    assert context.provenance == outcome.provenance
    assert context.context_id == outcome.provenance.activity_id
    assert provider.availability().operational is ProviderOperationalAvailability.AVAILABLE
    assert provider.usability(_configuration()).state is ProviderUsabilityState.USABLE


def test_provider_rejection_is_distinct_and_establishes_no_context() -> None:
    adapter = _FakeAuthenticationAdapter()
    adapter.exchange_error = ProviderConnectivityError(
        ProviderErrorCode.AUTHENTICATION_REJECTED
    )
    provider, _, _, _ = _provider(adapter=adapter)

    outcome = provider.authenticate(_configuration())

    assert outcome.kind is AuthenticationOutcomeKind.REJECTED
    assert outcome.reason is ContextLifecycleReason.PROVIDER_DECISION
    assert provider.current_context() is None
    assert provider.availability().operational is ProviderOperationalAvailability.AVAILABLE


def test_transport_failure_is_failure_and_operational_unavailability() -> None:
    adapter = _FakeAuthenticationAdapter()
    adapter.exchange_error = ProviderConnectivityError(
        ProviderErrorCode.CONNECTION_FAILURE
    )
    provider, _, _, _ = _provider(adapter=adapter)

    outcome = provider.authenticate(_configuration())

    assert outcome.kind is AuthenticationOutcomeKind.FAILED
    assert (
        outcome.reason
        is ContextLifecycleReason.PROVIDER_OPERATIONALLY_UNAVAILABLE
    )
    assert provider.current_context() is None
    assert provider.availability().operational is ProviderOperationalAvailability.UNAVAILABLE


@pytest.mark.parametrize(
    "configuration",
    [
        _configuration(provider="OTHER"),
        _configuration(eligible=False),
        _configuration(valid=False),
    ],
)
def test_configuration_precondition_failure_produces_no_activity(
    configuration: ConfigurationBoundaryInput,
) -> None:
    provider, adapter, _, factory = _provider()

    with pytest.raises(ProviderAccessPreconditionError):
        provider.authenticate(configuration)

    assert adapter.login_count == 0
    assert adapter.exchange_count == 0
    assert factory.calls == []
    assert provider.evidence() == ()


@pytest.mark.parametrize(
    "redirect_result",
    [
        None,
        "",
        "https://local.test/kite/callback",
        "https://wrong.test/kite/callback?request_token=anything",
    ],
)
def test_invalid_or_incomplete_redirect_is_failure(
    redirect_result: object,
) -> None:
    provider, adapter, _, _ = _provider(
        redirect_handler=lambda _login, _redirect: redirect_result
    )

    outcome = provider.authenticate(_configuration())

    assert outcome.kind is AuthenticationOutcomeKind.FAILED
    assert outcome.reason is ContextLifecycleReason.AUTHENTICATION_INCOMPLETE
    assert adapter.exchange_count == 0
    assert provider.current_context() is None


def test_documented_expiry_invalidates_and_preserves_correlation() -> None:
    provider, _, clock, _ = _provider()
    provider.authenticate(_configuration())
    original = provider.current_context()
    assert original is not None

    clock.current = datetime(2026, 7, 27, 6, 0, tzinfo=_TIMEZONE)
    expired = provider.current_context()

    assert expired is not None
    assert expired.validity is ContextValidity.INVALID
    assert expired.context_id == original.context_id
    assert expired.provider == original.provider
    assert expired.provenance == original.provenance
    assert provider.evidence()[-1].reason is ContextLifecycleReason.CONTEXT_EXPIRED
    assert provider.usability(_configuration()).state is ProviderUsabilityState.UNUSABLE


def test_invalid_token_evidence_invalidates_existing_context() -> None:
    adapter = _FakeAuthenticationAdapter()
    provider, _, _, _ = _provider(adapter=adapter)
    provider.authenticate(_configuration())
    original = provider.current_context()
    assert original is not None
    adapter.context_state = KiteContextEvidence.INVALID

    evidence = provider.validate_context()
    invalid = provider.current_context()

    assert evidence is not None
    assert evidence.kind is ProviderEvidenceKind.CONTEXT_INVALIDATED
    assert evidence.reason is ContextLifecycleReason.INVALID_PROVIDER_TOKEN
    assert evidence.provenance == original.provenance
    assert invalid is not None
    assert invalid.validity is ContextValidity.INVALID
    assert invalid.context_id == original.context_id


def test_operational_unavailability_does_not_masquerade_as_invalidation() -> None:
    adapter = _FakeAuthenticationAdapter()
    provider, _, _, _ = _provider(adapter=adapter)
    provider.authenticate(_configuration())
    adapter.context_state = KiteContextEvidence.UNAVAILABLE

    assert provider.validate_context() is None
    context = provider.current_context()

    assert context is not None
    assert context.validity is ContextValidity.VALID
    assert provider.availability().operational is ProviderOperationalAvailability.UNAVAILABLE
    assert provider.usability(_configuration()).state is ProviderUsabilityState.UNUSABLE


def test_deliberate_logout_terminates_provider_and_local_context() -> None:
    provider, adapter, _, _ = _provider()
    provider.authenticate(_configuration())
    original = provider.current_context()
    assert original is not None

    evidence = provider.terminate_context()
    terminated = provider.current_context()

    assert adapter.terminate_count == 1
    assert evidence is not None
    assert evidence.kind is ProviderEvidenceKind.CONTEXT_TERMINATED
    assert evidence.provenance == original.provenance
    assert terminated is not None
    assert terminated.validity is ContextValidity.TERMINATED
    assert terminated.context_id == original.context_id
    assert terminated.provenance == original.provenance


def test_failed_provider_logout_invalidates_but_does_not_claim_termination() -> None:
    adapter = _FakeAuthenticationAdapter()
    adapter.terminate_error = ProviderConnectivityError(
        ProviderErrorCode.CONNECTION_FAILURE
    )
    provider, _, _, _ = _provider(adapter=adapter)
    provider.authenticate(_configuration())

    evidence = provider.terminate_context()
    context = provider.current_context()

    assert evidence is not None
    assert evidence.kind is ProviderEvidenceKind.CONTEXT_INVALIDATED
    assert context is not None
    assert context.validity is ContextValidity.INVALID
    assert ProviderEvidenceKind.CONTEXT_TERMINATED not in {
        item.kind for item in provider.evidence()
    }


def test_lifecycle_evidence_has_stable_non_sensitive_correlation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider, _, _, _ = _provider()
    outcome = provider.authenticate(_configuration())
    provider.invalidate_context(ContextLifecycleReason.PROVIDER_SIDE_INVALIDATION)

    evidence = provider.evidence()
    activity_ids = {item.provenance.activity_id for item in evidence}
    rendered = repr(
        (
            outcome,
            provider.current_context(),
            provider.availability(),
            provider.usability(_configuration()),
            evidence,
        )
    )

    assert len(activity_ids) == 1
    for sensitive in (_API_SECRET, _REQUEST_TOKEN, _ACCESS_TOKEN):
        assert sensitive not in rendered
        assert sensitive not in caplog.text
