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
    ActivationReview,
    ActivationProvenanceKind,
    CanonicalRepositoryEvidence,
    ConsumptionOutcomeCategory,
    CoordinatedActivationValues,
    DurableConsumptionRecord,
    DurableConsumptionResult,
    LiveActivationContext,
    MonotonicLifecycleDeadline,
    ProvenConsumption,
    RemainingBudget,
    TrustedActivationReviewer,
)
from kronos.provider.models.authentication import (
    CoordinatedConsumptionState,
    GovernedAuthenticationOperation,
)
from kronos.provider.services.provider_authentication import (
    ProviderAuthenticationService,
)
from tools.provider_pilots.car017_live_authentication_launcher import (
    PreparedGovernedLaunch,
)


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


class _ConsumptionCounter(_Counter):
    def consume(self, **kwargs: object) -> object:
        return self(**kwargs)


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


def _governed_seams(
    values: CoordinatedActivationValues,
    *,
    budget: float = 300.0,
) -> tuple[OperationLedgerRecorder, ProvenConsumption, object]:
    recorder = OperationLedgerRecorder()
    recorder.record(GovernedAuthenticationOperation.ACTIVATION_VALIDATION)
    consumed_ledger = recorder.snapshot().record(
        GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
    )
    recorder.adopt(consumed_ledger)
    proof = ProvenConsumption(
        record=DurableConsumptionRecord(
            coordinated_activation_identity=values.coordinated_activation_identity,
            coordinated_governance_publication_sha=(
                values.coordinated_governance_publication_sha
            ),
            consumed_at=NOW.isoformat(),
        ),
        deadline=MonotonicLifecycleDeadline(monotonic_now=0.0),
        ledger=consumed_ledger,
    )

    def remaining_budget() -> RemainingBudget:
        return RemainingBudget(budget)

    return recorder, proof, remaining_budget


def _compose(
    activation: object,
    capability: object,
    values: CoordinatedActivationValues,
    counters: dict[str, _Counter],
    *,
    configuration: object | None = None,
    budget: float = 300.0,
    recorder: OperationLedgerRecorder | None = None,
    proof: ProvenConsumption | None = None,
    remaining_budget: object | None = None,
    service_factory: object | None = None,
    identity_factory: object | None = None,
) -> GovernedKiteAuthenticationRuntime:
    default_recorder, default_proof, default_budget = _governed_seams(
        values,
        budget=budget,
    )
    return compose_kite_authentication(
        activation,
        proven_consumption=proof or default_proof,
        activation_capability=capability,
        activation_values=values,
        configuration=configuration or _configuration(),  # type: ignore[arg-type]
        operation_recorder=recorder or default_recorder,
        remaining_budget=remaining_budget or default_budget,  # type: ignore[arg-type]
        security_runner=counters["security"],  # type: ignore[arg-type]
        browser_opener=counters["browser"],  # type: ignore[arg-type]
        server_factory=counters["server"],  # type: ignore[arg-type]
        adapter_factory=counters["adapter"],
        credential_source_factory=counters["credential"],
        intended_principal_resolver_factory=counters["principal"],
        navigator_factory=counters["navigator"],
        service_factory=service_factory or counters["service"],  # type: ignore[arg-type]
        clock=lambda: NOW,
        identity_factory=identity_factory or (lambda: "attempt-1"),  # type: ignore[arg-type]
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
    recorder, proof, remaining_budget = _governed_seams(values)

    with pytest.raises(LiveCompositionError, match="INVALID_ACTIVATION"):
        compose_kite_authentication(
            context,
            proven_consumption=proof,
            activation_capability=capability,
            activation_values=values,
            configuration=_configuration(),  # type: ignore[arg-type]
            operation_recorder=recorder,
            remaining_budget=remaining_budget,  # type: ignore[arg-type]
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


def test_exact_proof_deadline_supplier_and_ledger_reach_service_unchanged() -> None:
    context, capability, values = _review()
    counters = _counters()
    recorder, proof, remaining_budget = _governed_seams(values)

    runtime = _compose(
        context,
        capability,
        values,
        counters,
        recorder=recorder,
        proof=proof,
        remaining_budget=remaining_budget,
    )

    assert isinstance(runtime, GovernedKiteAuthenticationRuntime)
    service_arguments = counters["service"].kwargs
    assert service_arguments["proven_consumption"] is proof
    assert service_arguments["remaining_budget"] is remaining_budget
    assert service_arguments["operation_recorder"] is recorder
    assert recorder.snapshot() is proof.ledger


def test_launcher_forwards_exact_durable_consumption_proof_to_composition() -> None:
    context, capability, values = _review()
    recorder = OperationLedgerRecorder()
    recorder.record(GovernedAuthenticationOperation.ACTIVATION_VALIDATION)
    consumed_ledger = recorder.snapshot().record(
        GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
    )
    proof = ProvenConsumption(
        record=DurableConsumptionRecord(
            coordinated_activation_identity=values.coordinated_activation_identity,
            coordinated_governance_publication_sha=(
                values.coordinated_governance_publication_sha
            ),
            consumed_at=NOW.isoformat(),
        ),
        deadline=MonotonicLifecycleDeadline(monotonic_now=0.0),
        ledger=consumed_ledger,
    )
    consumption = _ConsumptionCounter(
        DurableConsumptionResult(ConsumptionOutcomeCategory.CONSUMED, proof)
    )
    composition = _Counter()
    prepared = PreparedGovernedLaunch(
        review=ActivationReview(context, capability),
        values=values,
        configuration=_configuration(),
        consumption=consumption,  # type: ignore[arg-type]
        consumed_at=lambda: NOW,
        monotonic=lambda: 1.0,
        composition_factory=composition,
        recorder=recorder,
    )

    prepared.compose_after_confirmation(context)

    assert composition.kwargs["proven_consumption"] is proof
    assert composition.kwargs["operation_recorder"] is recorder
    assert recorder.snapshot() is proof.ledger
    remaining_budget = composition.kwargs["remaining_budget"]
    assert callable(remaining_budget)
    assert remaining_budget().seconds == 299.0


def test_substituted_proof_is_rejected_before_every_factory() -> None:
    context, capability, values = _review()
    counters = _counters()
    recorder, _, remaining_budget = _governed_seams(values)
    _, substituted, _ = _governed_seams(values)

    with pytest.raises(LiveCompositionError, match="INVALID_ACTIVATION"):
        _compose(
            context,
            capability,
            values,
            counters,
            recorder=recorder,
            proof=substituted,
            remaining_budget=remaining_budget,
        )

    assert all(counter.calls == 0 for counter in counters.values())


def test_malformed_proof_cannot_be_reconstructed_from_other_seams() -> None:
    context, capability, values = _review()
    counters = _counters()
    recorder, _, remaining_budget = _governed_seams(values)

    with pytest.raises(LiveCompositionError, match="INVALID_ACTIVATION"):
        compose_kite_authentication(
            context,
            proven_consumption=object(),  # type: ignore[arg-type]
            activation_capability=capability,
            activation_values=values,
            configuration=_configuration(),  # type: ignore[arg-type]
            operation_recorder=recorder,
            remaining_budget=remaining_budget,  # type: ignore[arg-type]
            security_runner=counters["security"],  # type: ignore[arg-type]
            browser_opener=counters["browser"],  # type: ignore[arg-type]
            server_factory=counters["server"],  # type: ignore[arg-type]
            adapter_factory=counters["adapter"],
            credential_source_factory=counters["credential"],
            intended_principal_resolver_factory=counters["principal"],
            navigator_factory=counters["navigator"],
            service_factory=counters["service"],
        )

    assert all(counter.calls == 0 for counter in counters.values())


def test_proof_with_substituted_deadline_fails_before_every_factory() -> None:
    context, capability, values = _review()
    counters = _counters()
    recorder, proof, remaining_budget = _governed_seams(values)
    malformed = ProvenConsumption(
        record=proof.record,
        deadline=object(),  # type: ignore[arg-type]
        ledger=proof.ledger,
    )

    with pytest.raises(LiveCompositionError, match="INVALID_ACTIVATION"):
        _compose(
            context,
            capability,
            values,
            counters,
            recorder=recorder,
            proof=malformed,
            remaining_budget=remaining_budget,
        )

    assert all(counter.calls == 0 for counter in counters.values())


def test_proof_precedes_attempt_identity_listener_and_all_external_effects() -> None:
    context, capability, values = _review()
    counters = _counters()
    recorder, proof, remaining_budget = _governed_seams(values)
    identity = _Counter("attempt-1")
    runtime = _compose(
        context,
        capability,
        values,
        counters,
        recorder=recorder,
        proof=proof,
        remaining_budget=remaining_budget,
        service_factory=ProviderAuthenticationService,
        identity_factory=identity,
    )

    assert identity.calls == 0
    assert counters["server"].calls == 0
    runtime.begin_login()

    ledger = runtime.operation_ledger()
    assert identity.calls == 1
    assert counters["server"].calls == 1
    assert ledger.count_for(GovernedAuthenticationOperation.ATTEMPT_RESERVATION) == 1
    assert ledger.count_for(GovernedAuthenticationOperation.LISTENER_CONSTRUCTION) == 1
    assert ledger.count_for(GovernedAuthenticationOperation.LISTENER_BIND) == 1
    assert ledger.count_for(GovernedAuthenticationOperation.LOCAL_CLEANUP) == 1
    assert counters["security"].calls == 0
    assert counters["browser"].calls == 0
    assert counters["adapter"].calls == 0

    with pytest.raises(RuntimeError, match="GOVERNED_OPERATION_CARDINALITY_REJECTED"):
        runtime.begin_login()
    assert ledger.count_for(GovernedAuthenticationOperation.ATTEMPT_RESERVATION) == 1


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
