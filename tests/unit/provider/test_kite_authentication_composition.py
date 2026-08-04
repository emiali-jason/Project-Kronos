from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

import pytest

from kronos.configuration.settings import Settings
from kronos.provider.kite.composition import (
    GovernedKiteAuthenticationRuntime,
    LiveCompositionError,
    LiveCompositionFailure,
    OperationLedgerRecorder,
    compose_kite_authentication,
)
from kronos.provider.kite.live_activation import (
    ActivationProvenanceKind,
    CanonicalRepositoryEvidence,
    CoordinatedActivationValues,
    LiveActivationContext,
    RemainingBudget,
    TrustedActivationReviewer,
)
from kronos.provider.models.authentication import CoordinatedConsumptionState


SHA = "a" * 40
NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))


class _Verifier:
    def verify(self, expected: object, observed: object, evidence: object) -> bool:
        return expected is observed and evidence is not None


class _Counter:
    def __init__(self, result: object | None = None) -> None:
        self.calls = 0
        self.result = result
        self.args: tuple[object, ...] = ()
        self.kwargs: dict[str, object] = {}

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        self.args = args
        self.kwargs = kwargs
        return self.result if self.result is not None else object()


def _values(**changes: object) -> CoordinatedActivationValues:
    values: dict[str, object] = {
        "coordinated_activation_identity": "KRONOS-TEST-ACTIVATION-001",
        "coordinated_governance_publication_sha": SHA,
        "car016_logical_publication_ref": "CAR-016-V1.2-TEST",
        "car017_logical_publication_ref": "CAR-017-V1.2-TEST",
        "frozen_car016_implementation_sha": "b" * 40,
        "frozen_car017_implementation_sha": "c" * 40,
        "authority_effective_at": NOW - timedelta(hours=1),
        "authority_effective_timezone": "Asia/Kolkata",
        "authority_expires_at": NOW + timedelta(hours=1),
        "authority_expiry_timezone": "Asia/Kolkata",
        "authentication_attempt_timeout_seconds": 300,
        "sponsor_environment_ref": "TEST-NONPROD",
        "hostname": "test.local",
        "provider_identity": "ZERODHA_KITE",
        "operational_provider": "KITE",
        "provider_configuration_ref": "ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY",
        "application_registration_ref": "ZERODHA-KITE-APP-REGISTRATION-PRIMARY",
        "credential_ref": "KITE-API-SECRET-PRIMARY",
        "intended_principal_registration_ref": "KITE-INTENDED-PRINCIPAL-PRIMARY",
        "composition_dependency_set_ref": "CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1",
        "redirect_url": "http://127.0.0.1:8765/kite/callback",
        "attempt_cardinality": "ONE",
        "provider_availability_authority": "WITHHELD",
        "provider_availability_max_operations": 0,
        "car014_status": "UNEXECUTED",
        "consumption_state": CoordinatedConsumptionState.UNUSED,
    }
    values.update(changes)
    return CoordinatedActivationValues(**values)  # type: ignore[arg-type]


def _review(
    values: CoordinatedActivationValues | None = None,
    *,
    kind: ActivationProvenanceKind = ActivationProvenanceKind.FAKE_ONLY,
) -> tuple[object, object, CoordinatedActivationValues]:
    selected = values or _values()
    reviewer = TrustedActivationReviewer(_Verifier(), provenance_kind=kind)
    review = reviewer.review(
        expected=selected,
        observed=selected,
        repository_evidence=CanonicalRepositoryEvidence(
            branch="develop",
            head_sha=SHA,
            origin_develop_sha=SHA,
            working_tree_clean=True,
            car016_canonical=True,
            car017_canonical=True,
            car014_unexecuted=True,
        ),
        reviewed_at=NOW,
    )
    return review.context, review.capability, selected


def _configuration(**changes: object) -> object:
    values: dict[str, object] = {
        "provider": "KITE",
        "kite_api_key": "UNITKEY",
        "kite_api_secret": "",
        "kite_access_token": "",
        "kite_redirect_url": "http://127.0.0.1:8765/kite/callback",
        "kite_credential_ref": "KITE-API-SECRET-PRIMARY",
        "kite_intended_registration_ref": "KITE-INTENDED-PRINCIPAL-PRIMARY",
        "provider_configuration_ref": "ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY",
        "kite_application_registration_ref": "ZERODHA-KITE-APP-REGISTRATION-PRIMARY",
    }
    values.update(changes)
    settings = Settings(**values)  # type: ignore[arg-type]
    return settings.governed_provider_authentication_configuration()


def _counters() -> dict[str, _Counter]:
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
    values: CoordinatedActivationValues,
    counters: dict[str, _Counter],
    *,
    configuration: object | None = None,
    budget: float = 300.0,
) -> GovernedKiteAuthenticationRuntime:
    return compose_kite_authentication(
        activation,
        activation_capability=capability,
        activation_values=values,
        configuration=configuration or _configuration(),  # type: ignore[arg-type]
        operation_recorder=OperationLedgerRecorder(),
        remaining_budget=lambda: RemainingBudget(budget),
        security_runner=counters["security"],  # type: ignore[arg-type]
        browser_opener=counters["browser"],  # type: ignore[arg-type]
        server_factory=counters["server"],  # type: ignore[arg-type]
        adapter_factory=counters["adapter"],
        credential_source_factory=counters["credential"],
        intended_principal_resolver_factory=counters["principal"],
        navigator_factory=counters["navigator"],
        service_factory=counters["service"],
        clock=lambda: NOW,
        identity_factory=lambda: "attempt-1",
    )


def test_stage1_context_is_the_only_activation_type() -> None:
    context, _, _ = _review()

    assert type(context) is LiveActivationContext
    assert repr(context) == "<LiveActivationContext redacted>"
    assert not hasattr(LiveActivationContext, "from_reviewed_capability")


@pytest.mark.parametrize("activation", [None, object(), "live", {}, Settings])
def test_invalid_activation_rejected_before_every_factory(activation: object) -> None:
    _, capability, values = _review()
    counters = _counters()

    with pytest.raises(LiveCompositionError, match="INVALID_ACTIVATION"):
        _compose(activation, capability, values, counters)

    assert all(counter.calls == 0 for counter in counters.values())


def test_wrong_capability_rejected_before_every_factory() -> None:
    context, _, values = _review()
    counters = _counters()

    with pytest.raises(LiveCompositionError, match="INVALID_ACTIVATION"):
        _compose(context, object(), values, counters)

    assert all(counter.calls == 0 for counter in counters.values())


def test_mismatched_activation_values_rejected_before_every_factory() -> None:
    context, capability, _ = _review()
    other = _values(coordinated_activation_identity="KRONOS-TEST-ACTIVATION-002")
    counters = _counters()

    with pytest.raises(LiveCompositionError, match="INVALID_ACTIVATION"):
        _compose(context, capability, other, counters)

    assert all(counter.calls == 0 for counter in counters.values())


@pytest.mark.parametrize(
    "changes",
    [
        {"provider_configuration_ref": "OTHER"},
        {"kite_application_registration_ref": "OTHER"},
        {"kite_credential_ref": "OTHER"},
        {"kite_intended_registration_ref": "OTHER"},
    ],
)
def test_configuration_identity_mismatch_fails_before_factories(
    changes: dict[str, object],
) -> None:
    context, capability, values = _review()
    counters = _counters()
    try:
        configuration = _configuration(**changes)
    except Exception:
        assert all(counter.calls == 0 for counter in counters.values())
        return

    with pytest.raises(LiveCompositionError, match="CONFIGURATION_MISMATCH"):
        _compose(context, capability, values, counters, configuration=configuration)
    assert all(counter.calls == 0 for counter in counters.values())


def test_fake_review_cannot_enable_default_live_dependencies() -> None:
    context, capability, values = _review()

    with pytest.raises(LiveCompositionError, match="INVALID_ACTIVATION"):
        compose_kite_authentication(
            context,
            activation_capability=capability,
            activation_values=values,
            configuration=_configuration(),  # type: ignore[arg-type]
            operation_recorder=OperationLedgerRecorder(),
            remaining_budget=lambda: RemainingBudget(300.0),
        )


def test_valid_fake_composition_wires_once_and_defers_all_effects() -> None:
    context, capability, values = _review()
    counters = _counters()

    runtime = _compose(context, capability, values, counters)

    assert isinstance(runtime, GovernedKiteAuthenticationRuntime)
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


def test_deadline_exhaustion_precedes_every_factory() -> None:
    context, capability, values = _review()
    counters = _counters()

    with pytest.raises(LiveCompositionError, match="DEADLINE_EXHAUSTED"):
        _compose(context, capability, values, counters, budget=0.0)

    assert all(counter.calls == 0 for counter in counters.values())


def test_ambient_values_cannot_override_identity_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KRONOS_PROVIDER_IDENTITY_REF", "OTHER")
    monkeypatch.setenv("KRONOS_COMPOSITION_DEPENDENCY_SET_REF", "OTHER")
    context, capability, values = _review()
    counters = _counters()

    runtime = _compose(context, capability, values, counters)

    assert isinstance(runtime, GovernedKiteAuthenticationRuntime)
    assert os.environ["KRONOS_PROVIDER_IDENTITY_REF"] == "OTHER"


def test_provider_availability_is_unreachable_from_governed_runtime() -> None:
    context, capability, values = _review()
    runtime = _compose(context, capability, values, _counters())

    with pytest.raises(LiveCompositionError, match="INVALID_ACTIVATION"):
        runtime.verify_provider_availability()
    assert runtime.operation_ledger().count_for(
        next(
            operation
            for operation in runtime.operation_ledger().counts
            if operation.operation.value == "PROVIDER_AVAILABILITY_VERIFICATION"
        ).operation
    ) == 0
