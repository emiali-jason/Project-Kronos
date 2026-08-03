import copy
from datetime import datetime, timezone
import importlib
from pathlib import Path
import pickle

import pytest

from kronos.configuration.settings import Settings
from kronos.provider.kite.adapter.kite_provider import KiteProvider
from kronos.provider.kite.composition import (
    LiveActivationContext,
    LiveCompositionError,
    LiveCompositionFailure,
    compose_kite_authentication,
)
from kronos.provider.models.authentication import ProviderAuthenticationConfiguration


IMPLEMENTATION_SHA = "a" * 40


class _ReviewedFakeCapability:
    pass


class _Counter:
    def __init__(self, result: object | None = None) -> None:
        self.calls = 0
        self.result = result

    def __call__(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        return self.result if self.result is not None else object()


def _configuration() -> ProviderAuthenticationConfiguration:
    return ProviderAuthenticationConfiguration(
        provider="KITE",
        _api_key="ABC123",
        redirect_uri="http://127.0.0.1:8765/kite/callback",
        intended_registration_ref="primary.registration",
        credential_ref="primary.credential",
    )


def _context(
    capability: object,
    *,
    validator: object | None = None,
) -> LiveActivationContext:
    effective_validator = validator or (lambda candidate: candidate is capability)
    return LiveActivationContext.from_reviewed_capability(
        activation_capability=capability,
        capability_validator=effective_validator,  # type: ignore[arg-type]
        activation_authority_ref="CAR-017:TEST-ONLY",
        implementation_sha=IMPLEMENTATION_SHA,
        environment_ref="TEST-NONPROD",
        provider_configuration_ref="kite.primary",
        credential_ref="primary.credential",
        intended_registration_ref="primary.registration",
        composition_dependency_set_ref="car017.stage1.fakes",
    )


def _factory_counters() -> dict[str, _Counter]:
    return {
        "security": _Counter(),
        "browser": _Counter(True),
        "server": _Counter(),
        "adapter": _Counter(),
        "credential": _Counter(),
        "principal": _Counter(),
        "navigator": _Counter(),
        "service": _Counter(),
    }


def _compose(
    activation: object,
    capability: object,
    counters: dict[str, _Counter],
    *,
    configuration: object | None = None,
) -> KiteProvider:
    return compose_kite_authentication(
        activation,
        activation_capability=capability,
        configuration=configuration or _configuration(),  # type: ignore[arg-type]
        composition_dependency_set_ref="car017.stage1.fakes",
        security_runner=counters["security"],  # type: ignore[arg-type]
        browser_opener=counters["browser"],  # type: ignore[arg-type]
        server_factory=counters["server"],  # type: ignore[arg-type]
        adapter_factory=counters["adapter"],
        credential_source_factory=counters["credential"],
        intended_principal_resolver_factory=counters["principal"],
        navigator_factory=counters["navigator"],
        service_factory=counters["service"],
        clock=lambda: datetime(2026, 8, 3, tzinfo=timezone.utc),
        identity_factory=lambda: "attempt-1",
    )


def test_direct_constructor_cannot_create_activation() -> None:
    with pytest.raises(LiveCompositionError) as captured:
        LiveActivationContext()

    assert captured.value.failure is LiveCompositionFailure.INVALID_ACTIVATION


@pytest.mark.parametrize(
    "ambient",
    [
        "CONFIGURATION_VALUE",
        {"KRONOS_LIVE": "1"},
        ["--live"],
        Path("activation.flag"),
        _configuration(),
        Settings(
            provider="KITE",
            kite_api_key="",
            kite_api_secret="",
            kite_access_token="",
            kite_redirect_url="",
        ),
        importlib.import_module("kronos.provider.kite.composition"),
        lambda: None,
        _ReviewedFakeCapability,
    ],
)
def test_ambient_values_cannot_create_activation(ambient: object) -> None:
    validator = _Counter(True)

    with pytest.raises(LiveCompositionError) as captured:
        _context(ambient, validator=validator)

    assert captured.value.failure is LiveCompositionFailure.INVALID_ACTIVATION
    assert validator.calls == 0


def test_synthetic_malformed_and_wrong_provenance_are_rejected() -> None:
    capability = _ReviewedFakeCapability()

    with pytest.raises(LiveCompositionError):
        _context(capability, validator=lambda _candidate: False)
    with pytest.raises(LiveCompositionError):
        LiveActivationContext.from_reviewed_capability(
            activation_capability=capability,
            capability_validator=lambda candidate: candidate is capability,
            activation_authority_ref="",
            implementation_sha="not-a-sha",
            environment_ref="TEST",
            provider_configuration_ref="kite.primary",
            credential_ref="primary",
            intended_registration_ref="primary",
            composition_dependency_set_ref="fakes",
        )


def test_context_is_immutable_redacted_and_non_serializable() -> None:
    context = _context(_ReviewedFakeCapability())

    assert repr(context) == "<LiveActivationContext redacted>"
    assert str(context) == "<LiveActivationContext redacted>"
    assert IMPLEMENTATION_SHA not in repr(context)
    with pytest.raises(AttributeError):
        context.environment_ref = "OTHER"  # type: ignore[misc]
    with pytest.raises(TypeError):
        copy.copy(context)
    with pytest.raises(TypeError):
        copy.deepcopy(context)
    with pytest.raises((TypeError, pickle.PicklingError)):
        pickle.dumps(context)


def test_successful_import_creates_no_activation_context() -> None:
    module = importlib.import_module("kronos.provider.kite.composition")

    assert not any(
        type(value) is LiveActivationContext for value in vars(module).values()
    )


@pytest.mark.parametrize(
    "invalid_activation",
    [None, object(), "live", {"authority": "CAR-017"}, _configuration()],
)
def test_invalid_activation_rejected_before_every_factory(
    invalid_activation: object,
) -> None:
    counters = _factory_counters()

    with pytest.raises(LiveCompositionError) as captured:
        _compose(invalid_activation, object(), counters)

    assert captured.value.failure is LiveCompositionFailure.INVALID_ACTIVATION
    assert {name: counter.calls for name, counter in counters.items()} == {
        "security": 0,
        "browser": 0,
        "server": 0,
        "adapter": 0,
        "credential": 0,
        "principal": 0,
        "navigator": 0,
        "service": 0,
    }


def test_wrong_provenance_rejected_before_every_factory() -> None:
    capability = _ReviewedFakeCapability()
    context = _context(capability)
    counters = _factory_counters()

    with pytest.raises(LiveCompositionError) as captured:
        _compose(context, _ReviewedFakeCapability(), counters)

    assert captured.value.failure is LiveCompositionFailure.INVALID_ACTIVATION
    assert all(counter.calls == 0 for counter in counters.values())


def test_fake_activation_rejects_live_dependency_set_before_every_factory() -> None:
    capability = _ReviewedFakeCapability()
    context = _context(capability)
    counters = _factory_counters()

    with pytest.raises(LiveCompositionError) as captured:
        compose_kite_authentication(
            context,
            activation_capability=capability,
            configuration=_configuration(),
            security_runner=counters["security"],  # type: ignore[arg-type]
            browser_opener=counters["browser"],  # type: ignore[arg-type]
            server_factory=counters["server"],  # type: ignore[arg-type]
            adapter_factory=counters["adapter"],
            credential_source_factory=counters["credential"],
            intended_principal_resolver_factory=counters["principal"],
            navigator_factory=counters["navigator"],
            service_factory=counters["service"],
        )

    assert captured.value.failure is LiveCompositionFailure.INVALID_ACTIVATION
    assert all(counter.calls == 0 for counter in counters.values())


def test_fake_dependency_set_rejects_real_external_effect_dependencies() -> None:
    capability = _ReviewedFakeCapability()
    context = _context(capability)

    with pytest.raises(LiveCompositionError) as captured:
        compose_kite_authentication(
            context,
            activation_capability=capability,
            configuration=_configuration(),
            composition_dependency_set_ref="car017.stage1.fakes",
        )

    assert captured.value.failure is LiveCompositionFailure.INVALID_ACTIVATION


def test_incomplete_dependencies_rejected_before_every_factory() -> None:
    capability = _ReviewedFakeCapability()
    context = _context(capability)
    counters = _factory_counters()
    counters["credential"] = None  # type: ignore[assignment]

    with pytest.raises(LiveCompositionError) as captured:
        _compose(context, capability, counters)  # type: ignore[arg-type]

    assert captured.value.failure is LiveCompositionFailure.INCOMPLETE_COMPOSITION
    assert all(
        counter is None or counter.calls == 0 for counter in counters.values()
    )


def test_configuration_mismatch_rejected_before_every_factory() -> None:
    capability = _ReviewedFakeCapability()
    context = _context(capability)
    counters = _factory_counters()
    mismatch = ProviderAuthenticationConfiguration(
        provider="KITE",
        _api_key="ABC123",
        redirect_uri="http://127.0.0.1:8765/kite/callback",
        intended_registration_ref="other.registration",
        credential_ref="other.credential",
    )

    with pytest.raises(LiveCompositionError) as captured:
        _compose(context, capability, counters, configuration=mismatch)

    assert captured.value.failure is LiveCompositionFailure.CONFIGURATION_MISMATCH
    assert all(counter.calls == 0 for counter in counters.values())


def test_valid_fake_composition_wires_once_and_defers_all_effects() -> None:
    capability = _ReviewedFakeCapability()
    context = _context(capability)
    counters = _factory_counters()

    provider = _compose(context, capability, counters)

    assert isinstance(provider, KiteProvider)
    assert {name: counter.calls for name, counter in counters.items()} == {
        "security": 0,
        "browser": 0,
        "server": 0,
        "adapter": 0,
        "credential": 1,
        "principal": 1,
        "navigator": 1,
        "service": 1,
    }


def test_composition_does_not_verify_availability_or_create_second_path() -> None:
    capability = _ReviewedFakeCapability()
    context = _context(capability)
    counters = _factory_counters()
    fake_service = counters["service"]

    provider = _compose(context, capability, counters)

    assert isinstance(provider, KiteProvider)
    assert fake_service.calls == 1
    assert counters["adapter"].calls == 0
    assert counters["server"].calls == 0
    assert counters["browser"].calls == 0
