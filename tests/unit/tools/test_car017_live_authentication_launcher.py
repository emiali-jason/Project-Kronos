from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

import pytest

from kronos.configuration.settings import Settings
from kronos.provider.kite.live_activation import (
    ActivationProvenanceKind,
    CanonicalRepositoryEvidence,
    CoordinatedActivationValues,
    DurableConsumptionRecord,
    DurableConsumptionResult,
    MonotonicLifecycleDeadline,
    ProvenConsumption,
    TrustedActivationReviewer,
)
from kronos.provider.models.authentication import (
    ConsumptionOutcomeCategory,
    CoordinatedConsumptionState,
    GovernedAuthenticationOperation,
    SanitizedOperationLedger,
)
from tools.provider_pilots import car017_live_authentication_launcher as launcher


ROOT = Path(__file__).resolve().parents[3]
SHA = "a" * 40
NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))


class _Verifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, expected: object, observed: object, evidence: object) -> bool:
        self.calls += 1
        return expected is observed and evidence is not None


class _Consumption:
    def __init__(self, *, consumed: bool = True) -> None:
        self.calls = 0
        self.consumed = consumed
        self.kwargs: dict[str, object] = {}

    def consume(self, **kwargs: object) -> DurableConsumptionResult:
        self.calls += 1
        self.kwargs = kwargs
        if not self.consumed:
            return DurableConsumptionResult(
                ConsumptionOutcomeCategory.POST_CONFIRMATION_CONSUMPTION_UNCERTAIN,
                None,
            )
        ledger = kwargs["ledger"]
        assert type(ledger) is SanitizedOperationLedger
        return DurableConsumptionResult(
            ConsumptionOutcomeCategory.CONSUMED,
            ProvenConsumption(
                record=DurableConsumptionRecord(
                    coordinated_activation_identity="KRONOS-TEST-LAUNCH-001",
                    coordinated_governance_publication_sha=SHA,
                    consumed_at=NOW.isoformat(),
                ),
                deadline=MonotonicLifecycleDeadline(monotonic_now=100.0),
                ledger=ledger.record(
                    GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
                ),
            ),
        )


def _values() -> CoordinatedActivationValues:
    return CoordinatedActivationValues(
        coordinated_activation_identity="KRONOS-TEST-LAUNCH-001",
        coordinated_governance_publication_sha=SHA,
        car016_logical_publication_ref="CAR-016-V1.2-TEST",
        car017_logical_publication_ref="CAR-017-V1.2-TEST",
        frozen_car016_implementation_sha="b" * 40,
        frozen_car017_implementation_sha="c" * 40,
        authority_effective_at=NOW - timedelta(hours=1),
        authority_effective_timezone="Asia/Kolkata",
        authority_expires_at=NOW + timedelta(hours=1),
        authority_expiry_timezone="Asia/Kolkata",
        authentication_attempt_timeout_seconds=300,
        sponsor_environment_ref="TEST-NONPROD",
        hostname="test.local",
        provider_identity="ZERODHA_KITE",
        operational_provider="KITE",
        provider_configuration_ref="ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY",
        application_registration_ref="ZERODHA-KITE-APP-REGISTRATION-PRIMARY",
        credential_ref="KITE-API-SECRET-PRIMARY",
        intended_principal_registration_ref="KITE-INTENDED-PRINCIPAL-PRIMARY",
        composition_dependency_set_ref="CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1",
        redirect_url="http://127.0.0.1:8765/kite/callback",
        attempt_cardinality="ONE",
        provider_availability_authority="WITHHELD",
        provider_availability_max_operations=0,
        car014_status="UNEXECUTED",
        consumption_state=CoordinatedConsumptionState.UNUSED,
    )


def _request(values: CoordinatedActivationValues) -> launcher.GovernedLaunchRequest:
    return launcher.GovernedLaunchRequest(
        expected=values,
        observed=values,
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
        runtime=launcher.RuntimeVersionEvidence(
            python=(3, 13, 14), tkinter="9.0", kite_sdk="5.2.0"
        ),
    )


def _configuration() -> object:
    return Settings(
        provider="KITE",
        kite_api_key="UNITKEY",
        kite_api_secret="",
        kite_access_token="",
        kite_redirect_url="http://127.0.0.1:8765/kite/callback",
        kite_credential_ref="KITE-API-SECRET-PRIMARY",
        kite_intended_registration_ref="KITE-INTENDED-PRINCIPAL-PRIMARY",
        provider_configuration_ref="ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY",
        kite_application_registration_ref="ZERODHA-KITE-APP-REGISTRATION-PRIMARY",
    ).governed_provider_authentication_configuration()


def _prepare(
    *,
    consumption: _Consumption | None = None,
    composition: object | None = None,
) -> tuple[launcher.PreparedGovernedLaunch, _Consumption, list[str]]:
    values = _values()
    events: list[str] = []
    selected_consumption = consumption or _Consumption()

    def compose(*_args: object, **_kwargs: object) -> object:
        events.append("compose")
        return composition or object()

    prepared = launcher.prepare_governed_launch(
        _request(values),
        reviewer=TrustedActivationReviewer(
            _Verifier(), provenance_kind=ActivationProvenanceKind.FAKE_ONLY
        ),
        consumption=selected_consumption,  # type: ignore[arg-type]
        configuration_loader=lambda: _configuration(),  # type: ignore[return-value]
        consumed_at=lambda: NOW,
        monotonic=lambda: 100.0,
        composition_factory=compose,
    )
    return prepared, selected_consumption, events


def test_direct_import_is_silent_and_effect_free() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import tools.provider_pilots.car017_live_authentication_launcher"],
        cwd=ROOT,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_preflight_constructs_no_runtime_dependency_and_does_not_consume() -> None:
    prepared, consumption, events = _prepare()

    assert consumption.calls == 0
    assert events == []
    assert prepared.operation_ledger().count_for(
        GovernedAuthenticationOperation.ACTIVATION_VALIDATION
    ) == 1


def test_confirmation_precedes_consumption_and_composition() -> None:
    prepared, consumption, events = _prepare()

    def gui_main(**kwargs: object) -> None:
        events.append("gui")
        confirmation = kwargs["confirmation"]
        composition = kwargs["composition_factory"]
        activation = kwargs["activation"]
        assert callable(confirmation) and confirmation() is True
        events.append("confirmed")
        assert callable(composition)
        composition(activation)

    launcher.launch_prepared(
        prepared,
        gui_main=gui_main,
        confirmation=lambda: True,
        worker_submit=lambda _operation: None,
    )

    assert consumption.calls == 1
    assert consumption.kwargs["sponsor_confirmed"] is True
    assert events == ["gui", "confirmed", "compose"]
    assert prepared.operation_ledger().count_for(
        GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
    ) == 1


def test_uncertain_consumption_stops_before_composition() -> None:
    prepared, consumption, events = _prepare(consumption=_Consumption(consumed=False))

    with pytest.raises(RuntimeError, match="POST_CONFIRMATION_CONSUMPTION_UNCERTAIN"):
        prepared.compose_after_confirmation(prepared.activation)

    assert consumption.calls == 1
    assert events == []


def test_runtime_mismatch_fails_before_configuration_and_consumption() -> None:
    values = _values()
    request = launcher.GovernedLaunchRequest(
        expected=values,
        observed=values,
        repository_evidence=_request(values).repository_evidence,
        reviewed_at=NOW,
        runtime=launcher.RuntimeVersionEvidence(
            python=(3, 13, 13), tkinter="9.0", kite_sdk="5.2.0"
        ),
    )
    config_calls = 0

    def config() -> object:
        nonlocal config_calls
        config_calls += 1
        return _configuration()

    with pytest.raises(RuntimeError, match="GOVERNED_RUNTIME_PREFLIGHT_FAILED"):
        launcher.prepare_governed_launch(
            request,
            reviewer=TrustedActivationReviewer(
                _Verifier(), provenance_kind=ActivationProvenanceKind.FAKE_ONLY
            ),
            consumption=_Consumption(),  # type: ignore[arg-type]
            configuration_loader=config,  # type: ignore[arg-type]
            consumed_at=lambda: NOW,
        )
    assert config_calls == 0


def test_launcher_source_has_no_dotenv_or_provider_availability_call() -> None:
    source = Path(launcher.__file__).read_text()

    assert "load_dotenv" not in source
    assert "verify_provider_availability(" not in source
    assert "invalidate_access_token" not in source
