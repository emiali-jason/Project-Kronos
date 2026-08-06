from __future__ import annotations

from dataclasses import replace
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
GOVERNANCE_SHA = "cdaeaf1669e7182f36f9ea753315cf7992843d78"
CORRECTIVE_SHA = "d" * 40
LATEST_GOVERNANCE_SHA = "f" * 40
NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
LIVE_NOW = datetime(
    2026, 8, 6, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
)


class _Verifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, expected: object, observed: object, evidence: object) -> bool:
        self.calls += 1
        return expected is observed and evidence is not None


class _CapturingEvidenceVerifier:
    def __init__(self) -> None:
        self.evidence: object | None = None

    def verify(self, expected: object, observed: object, evidence: object) -> bool:
        self.evidence = evidence
        return expected is observed


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


class _DurableFilesystem:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.payload = b""

    def open_verified_parent_directory(
        self, _directory: str, *, expected_owner: int, expected_mode: int
    ) -> object:
        assert expected_owner == 501
        assert expected_mode == 0o700
        self.events.append("open-parent")
        return object()

    def create_exclusive_nofollow(
        self, _parent: object, _filename: str, *, mode: int
    ) -> object:
        assert mode == 0o600
        self.events.append("create-record")
        return object()

    def verify_open_file(self, _file: object, **_kwargs: object) -> None:
        self.events.append("verify-record")

    def write_all(self, _file: object, payload: bytes) -> None:
        self.payload = payload
        self.events.append("write-record")

    def flush_file(self, _file: object) -> None:
        self.events.append("flush-record")

    def fsync_file(self, _file: object) -> None:
        self.events.append("fsync-record")

    def close_file(self, _file: object) -> None:
        self.events.append("close-record")

    def fsync_directory(self, _parent: object) -> None:
        self.events.append("fsync-parent")

    def close_directory(self, _parent: object) -> None:
        self.events.append("close-parent")


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


def _environment() -> dict[str, str]:
    return {
        "KRONOS_PROVIDER": "KITE",
        "KRONOS_KITE_API_KEY": "UNITKEY",
        "KRONOS_KITE_REDIRECT_URL": "http://127.0.0.1:8765/kite/callback",
        "KRONOS_KITE_CREDENTIAL_REF": "KITE-API-SECRET-PRIMARY",
        "KRONOS_KITE_INTENDED_REGISTRATION_REF": (
            "KITE-INTENDED-PRINCIPAL-PRIMARY"
        ),
        "KRONOS_PROVIDER_CONFIGURATION_REF": (
            "ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY"
        ),
        "KRONOS_KITE_APPLICATION_REGISTRATION_REF": (
            "ZERODHA-KITE-APP-REGISTRATION-PRIMARY"
        ),
    }


def _canonical_snapshot(**changes: object) -> launcher.CanonicalRepositorySnapshot:
    historical_records = tuple(
        (ROOT / path).read_text(encoding="utf-8")
        for path in launcher._GOVERNANCE_PATHS
    )
    activation_records = tuple(
        document.replace(launcher._FROZEN_CAR018_SHA, CORRECTIVE_SHA)
        for document in historical_records
    )
    snapshot = launcher.CanonicalRepositorySnapshot(
        evidence=CanonicalRepositoryEvidence(
            branch="develop",
            head_sha=LATEST_GOVERNANCE_SHA,
            origin_develop_sha=LATEST_GOVERNANCE_SHA,
            working_tree_clean=True,
            car016_canonical=True,
            car017_canonical=True,
            car014_unexecuted=True,
        ),
        current_branch="develop",
        current_head_sha=LATEST_GOVERNANCE_SHA,
        current_origin_develop_sha=LATEST_GOVERNANCE_SHA,
        current_working_tree_clean=True,
        approved_corrective_implementation_sha=CORRECTIVE_SHA,
        corrective_parent_sha=GOVERNANCE_SHA,
        corrective_paths=launcher._CORRECTIVE_PATHS,
        activation_governance_publication_sha=LATEST_GOVERNANCE_SHA,
        activation_governance_paths=launcher._GOVERNANCE_PATHS,
        activation_governance_records=activation_records,
        historical_governance_publication_sha=GOVERNANCE_SHA,
        historical_governance_paths=launcher._GOVERNANCE_PATHS,
        historical_governance_records=historical_records,
    )
    return replace(snapshot, **changes)


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


def test_production_verifier_accepts_exact_distinct_contexts_and_manifest() -> None:
    snapshot = _canonical_snapshot()
    expected = launcher.expected_activation_context(snapshot)
    observed = launcher.observed_activation_context(
        expected=expected,
        repository_evidence=snapshot.evidence,
        configuration=_configuration(),  # type: ignore[arg-type]
        hostname="Imrans-Mac-mini.local",
    )
    verifier = launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot)

    assert expected is not observed
    assert expected.exactly_matches(observed)
    assert verifier.verify(expected, observed, snapshot.evidence) is True


def test_current_activation_context_uses_latest_governance_publication_sha() -> None:
    snapshot = _canonical_snapshot()

    assert (
        launcher.expected_activation_context(snapshot).coordinated_governance_publication_sha
        == LATEST_GOVERNANCE_SHA
    )


def test_trusted_reviewer_receives_current_repository_evidence() -> None:
    snapshot = _canonical_snapshot()
    expected = launcher.expected_activation_context(snapshot)
    verifier = _CapturingEvidenceVerifier()
    reviewer = TrustedActivationReviewer(
        verifier,  # type: ignore[arg-type]
        provenance_kind=ActivationProvenanceKind.CANONICAL_LIVE,
    )

    reviewer.review(
        expected=expected,
        observed=expected,
        repository_evidence=snapshot.evidence,
        reviewed_at=LIVE_NOW,
    )

    assert verifier.evidence is snapshot.evidence
    assert snapshot.evidence.head_sha == LATEST_GOVERNANCE_SHA
    assert snapshot.evidence.origin_develop_sha == LATEST_GOVERNANCE_SHA


def test_production_verifier_rejects_non_governance_publication_manifest() -> None:
    snapshot = _canonical_snapshot(
        activation_governance_paths=(
            "tools/provider_pilots/car017_live_authentication_launcher.py",
        )
    )
    expected = launcher.expected_activation_context(snapshot)
    verifier = launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot)

    assert verifier.verify(expected, expected, snapshot.evidence) is False


def test_head_cannot_substitute_for_governance_publication_sha() -> None:
    snapshot = _canonical_snapshot()
    substituted = replace(
        launcher.expected_activation_context(snapshot),
        coordinated_governance_publication_sha=CORRECTIVE_SHA,
    )
    substituted_evidence = replace(
        snapshot.evidence,
        head_sha=CORRECTIVE_SHA,
        origin_develop_sha=CORRECTIVE_SHA,
    )

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        substituted,
        substituted,
        substituted_evidence,
    ) is False


def test_historical_sha_cannot_substitute_in_current_activation_context() -> None:
    snapshot = _canonical_snapshot()
    substituted = replace(
        launcher.expected_activation_context(snapshot),
        coordinated_governance_publication_sha=GOVERNANCE_SHA,
    )

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        substituted, substituted, snapshot.evidence
    ) is False


def test_historical_sha_cannot_substitute_in_current_repository_evidence() -> None:
    snapshot = _canonical_snapshot()
    expected = launcher.expected_activation_context(snapshot)
    historical_evidence = replace(
        snapshot.evidence,
        head_sha=GOVERNANCE_SHA,
        origin_develop_sha=GOVERNANCE_SHA,
    )

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, historical_evidence
    ) is False


def test_wrong_governance_publication_sha_is_rejected() -> None:
    wrong = "e" * 40
    snapshot = _canonical_snapshot(
        historical_governance_publication_sha=wrong,
        evidence=replace(
            _canonical_snapshot().evidence,
            head_sha=wrong,
            origin_develop_sha=wrong,
        ),
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected,
        expected,
        snapshot.evidence,
    ) is False


def test_wrong_corrective_implementation_sha_is_rejected() -> None:
    snapshot = _canonical_snapshot(approved_corrective_implementation_sha="e" * 40)
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected,
        expected,
        snapshot.evidence,
    ) is False


def test_missing_approved_corrective_implementation_sha_is_rejected() -> None:
    snapshot = _canonical_snapshot(approved_corrective_implementation_sha="")
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_corrective_sha_absent_from_activation_records_is_rejected() -> None:
    snapshot = _canonical_snapshot()
    records = tuple(
        document.replace(CORRECTIVE_SHA, "MISSING")
        for document in snapshot.activation_governance_records
    )
    altered = replace(snapshot, activation_governance_records=records)
    expected = launcher.expected_activation_context(altered)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(altered).verify(
        expected, expected, altered.evidence
    ) is False


def test_current_head_cannot_stand_in_for_latest_activation_governance() -> None:
    snapshot = _canonical_snapshot(
        current_head_sha=CORRECTIVE_SHA,
        current_origin_develop_sha=CORRECTIVE_SHA,
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_current_head_must_equal_latest_activation_governance_publication() -> None:
    snapshot = _canonical_snapshot(
        current_head_sha="e" * 40,
        current_origin_develop_sha="e" * 40,
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_approved_corrective_sha_cannot_be_substituted_with_ambient_head() -> None:
    snapshot = _canonical_snapshot(
        approved_corrective_implementation_sha=LATEST_GOVERNANCE_SHA,
        corrective_parent_sha=GOVERNANCE_SHA,
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_corrective_parent_mismatch_is_rejected() -> None:
    snapshot = _canonical_snapshot(corrective_parent_sha="e" * 40)
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_corrective_manifest_mismatch_is_rejected() -> None:
    snapshot = _canonical_snapshot(corrective_paths=launcher._CORRECTIVE_PATHS[:-1])
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_activation_governance_publication_sha_mismatch_is_rejected() -> None:
    snapshot = _canonical_snapshot(activation_governance_publication_sha="e" * 40)
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_governance_manifest_missing_required_file_is_rejected() -> None:
    snapshot = _canonical_snapshot(
        activation_governance_paths=launcher._GOVERNANCE_PATHS[:-1]
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected,
        expected,
        snapshot.evidence,
    ) is False


def test_governance_manifest_with_unexpected_fifth_file_is_rejected() -> None:
    snapshot = _canonical_snapshot(
        activation_governance_paths=(
            *launcher._GOVERNANCE_PATHS,
            "docs/governance/reviews/UNEXPECTED.md",
        )
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected,
        expected,
        snapshot.evidence,
    ) is False


def test_historical_governance_manifest_is_verified_independently() -> None:
    snapshot = _canonical_snapshot(
        historical_governance_paths=launcher._GOVERNANCE_PATHS[:-1]
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_record_specific_metadata_and_register_rows_are_required() -> None:
    snapshot = _canonical_snapshot()
    expected = launcher.expected_activation_context(snapshot)
    records = list(snapshot.activation_governance_records)
    records[0] = records[0].replace("**Version:** 1.2", "**Version:** 9.9", 1)
    altered_car = replace(snapshot, activation_governance_records=tuple(records))
    assert launcher.ProductionCanonicalActivationEvidenceVerifier(altered_car).verify(
        expected,
        expected,
        altered_car.evidence,
    ) is False

    records = list(snapshot.activation_governance_records)
    records[3] = records[3].replace(
        "Controlled Amendment: `CAR-017-V1.2-CA1`",
        "Controlled Amendment: `CAR-017-V1.2-WRONG`",
        1,
    )
    altered_register = replace(snapshot, activation_governance_records=tuple(records))
    assert launcher.ProductionCanonicalActivationEvidenceVerifier(
        altered_register
    ).verify(expected, expected, altered_register.evidence) is False


def test_snapshot_reads_four_independent_repository_identities() -> None:
    calls: list[tuple[str, ...]] = []
    historical_records = {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in launcher._GOVERNANCE_PATHS
    }
    activation_records = {
        path: document.replace(launcher._FROZEN_CAR018_SHA, CORRECTIVE_SHA)
        for path, document in historical_records.items()
    }

    def git_output(arguments: tuple[str, ...]) -> str:
        calls.append(arguments)
        if arguments == ("branch", "--show-current"):
            return "develop\n"
        if arguments == ("rev-parse", "HEAD"):
            return f"{LATEST_GOVERNANCE_SHA}\n"
        if arguments == ("rev-parse", "origin/develop"):
            return f"{LATEST_GOVERNANCE_SHA}\n"
        if arguments == ("status", "--porcelain"):
            return ""
        if arguments == ("rev-parse", f"{CORRECTIVE_SHA}^"):
            return f"{GOVERNANCE_SHA}\n"
        if arguments[0] == "diff-tree" and arguments[-1] == LATEST_GOVERNANCE_SHA:
            return "\n".join(launcher._GOVERNANCE_PATHS) + "\n"
        if arguments[0] == "diff-tree" and arguments[-1] == CORRECTIVE_SHA:
            return "\n".join(launcher._CORRECTIVE_PATHS) + "\n"
        if arguments[0] == "diff-tree":
            return "\n".join(launcher._GOVERNANCE_PATHS) + "\n"
        if arguments[0] == "show":
            commit, path = arguments[1].split(":", 1)
            return (
                activation_records[path]
                if commit == LATEST_GOVERNANCE_SHA
                else historical_records[path]
            )
        raise AssertionError(arguments)

    snapshot = launcher.canonical_repository_snapshot(
        ROOT,
        activation_governance_publication_sha=LATEST_GOVERNANCE_SHA,
        git_output=git_output,
    )

    assert snapshot.current_head_sha == LATEST_GOVERNANCE_SHA
    assert snapshot.evidence.head_sha == LATEST_GOVERNANCE_SHA
    assert snapshot.evidence.origin_develop_sha == LATEST_GOVERNANCE_SHA
    assert snapshot.activation_governance_publication_sha == LATEST_GOVERNANCE_SHA
    assert snapshot.approved_corrective_implementation_sha == CORRECTIVE_SHA
    assert snapshot.historical_governance_publication_sha == GOVERNANCE_SHA
    assert (
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        GOVERNANCE_SHA,
    ) in calls


def test_post_correction_committed_state_preflight_passes_and_is_inert() -> None:
    events: list[str] = []
    presented: list[str] = []
    filesystem = _DurableFilesystem(events)

    def gui_main(**_kwargs: object) -> None:
        events.append("gui")

    prepared = launcher.execute_governed_launcher(
        repository_root=ROOT,
        environment=_environment(),
        hostname="Imrans-Mac-mini.local",
        reviewed_at=LIVE_NOW,
        runtime=launcher.RuntimeVersionEvidence(
            python=(3, 13, 14), tkinter="9.0", kite_sdk="5.2.0"
        ),
        snapshot=_canonical_snapshot(),
        sponsor_home="/fake-sponsor-home",
        sponsor_user_id=501,
        durable_state=(True, True),
        port_ready_without_bind=True,
        preflight_presenter=presented.append,
        confirmation=lambda: True,
        gui_main=gui_main,
        worker_submit=lambda _operation: None,
        monotonic=lambda: 100.0,
        consumed_at=lambda: LIVE_NOW,
        composition_factory=lambda *_args, **_kwargs: events.append("compose"),
        filesystem=filesystem,
    )

    assert events == ["gui"]
    assert filesystem.payload == b""
    assert presented[0].startswith("GOVERNED LIVE PREFLIGHT EVIDENCE PACKAGE")
    assert "Overall: READY FOR FINAL SPONSOR CONFIRMATION" in presented[0]
    assert presented[1].startswith("SANITIZED GOVERNED TERMINAL EVIDENCE")
    assert prepared.operation_ledger().count_for(
        GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
    ) == 0


def test_operational_path_consumes_before_exact_live_composition() -> None:
    events: list[str] = []
    filesystem = _DurableFilesystem(events)
    received: dict[str, object] = {}

    def composition(_activation: object, **kwargs: object) -> object:
        events.append("compose")
        received.update(kwargs)
        return object()

    def gui_main(**kwargs: object) -> None:
        events.append("gui")
        confirmation = kwargs["confirmation"]
        compose = kwargs["composition_factory"]
        assert callable(confirmation) and confirmation() is True
        events.append("confirmed")
        assert callable(compose)
        compose(kwargs["activation"])

    prepared = launcher.execute_governed_launcher(
        repository_root=ROOT,
        environment=_environment(),
        hostname="Imrans-Mac-mini.local",
        reviewed_at=LIVE_NOW,
        runtime=launcher.RuntimeVersionEvidence(
            python=(3, 13, 14), tkinter="9.0", kite_sdk="5.2.0"
        ),
        snapshot=_canonical_snapshot(),
        sponsor_home="/fake-sponsor-home",
        sponsor_user_id=501,
        durable_state=(True, True),
        port_ready_without_bind=True,
        preflight_presenter=lambda _evidence: None,
        confirmation=lambda: True,
        gui_main=gui_main,
        worker_submit=lambda _operation: None,
        monotonic=lambda: 100.0,
        consumed_at=lambda: LIVE_NOW,
        composition_factory=composition,
        filesystem=filesystem,
    )

    assert events[:2] == ["gui", "confirmed"]
    assert events.index("confirmed") < events.index("open-parent")
    assert events.index("fsync-parent") < events.index("compose")
    assert type(received["proven_consumption"]) is ProvenConsumption
    assert received["activation_capability"]._is_live_capable() is True
    assert received["operation_recorder"].snapshot() is (
        received["proven_consumption"].ledger
    )
    assert prepared.operation_ledger().count_for(
        GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
    ) == 1
    assert prepared.operation_ledger().count_for(
        GovernedAuthenticationOperation.PROVIDER_AVAILABILITY_VERIFICATION
    ) == 0


@pytest.mark.parametrize(
    ("durable_state", "port_ready"),
    (((False, False), True), ((True, False), True), ((True, True), False)),
)
def test_failed_preflight_never_launches_or_consumes(
    durable_state: tuple[bool, bool], port_ready: bool
) -> None:
    events: list[str] = []
    filesystem = _DurableFilesystem(events)

    with pytest.raises(RuntimeError, match="GOVERNED_RUNTIME_PREFLIGHT_FAILED"):
        launcher.execute_governed_launcher(
            repository_root=ROOT,
            environment=_environment(),
            hostname="Imrans-Mac-mini.local",
            reviewed_at=LIVE_NOW,
            runtime=launcher.RuntimeVersionEvidence(
                python=(3, 13, 14), tkinter="9.0", kite_sdk="5.2.0"
            ),
            snapshot=_canonical_snapshot(),
            sponsor_home="/fake-sponsor-home",
            sponsor_user_id=501,
            durable_state=durable_state,
            port_ready_without_bind=port_ready,
            preflight_presenter=lambda _evidence: None,
            confirmation=lambda: True,
            gui_main=lambda **_kwargs: events.append("gui"),
            worker_submit=lambda _operation: None,
            monotonic=lambda: 100.0,
            consumed_at=lambda: LIVE_NOW,
            composition_factory=lambda *_args, **_kwargs: events.append("compose"),
            filesystem=filesystem,
        )

    assert events == []
    assert filesystem.payload == b""


def test_terminal_evidence_is_presented_when_gui_terminates_with_failure() -> None:
    presented: list[str] = []

    def gui_main(**_kwargs: object) -> None:
        raise RuntimeError("SYNTHETIC_GUI_FAILURE")

    with pytest.raises(RuntimeError, match="SYNTHETIC_GUI_FAILURE"):
        launcher.execute_governed_launcher(
            repository_root=ROOT,
            environment=_environment(),
            hostname="Imrans-Mac-mini.local",
            reviewed_at=LIVE_NOW,
            runtime=launcher.RuntimeVersionEvidence(
                python=(3, 13, 14), tkinter="9.0", kite_sdk="5.2.0"
            ),
            snapshot=_canonical_snapshot(),
            sponsor_home="/fake-sponsor-home",
            sponsor_user_id=501,
            durable_state=(True, True),
            port_ready_without_bind=True,
            preflight_presenter=presented.append,
            confirmation=lambda: True,
            gui_main=gui_main,
            worker_submit=lambda _operation: None,
            monotonic=lambda: 100.0,
            consumed_at=lambda: LIVE_NOW,
            filesystem=_DurableFilesystem([]),
        )

    assert len(presented) == 2
    assert presented[1].startswith("SANITIZED GOVERNED TERMINAL EVIDENCE")


def test_main_routes_through_operational_assembly(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    snapshot = _canonical_snapshot()
    sponsor = type("Sponsor", (), {"pw_dir": "/fake", "pw_uid": 501})()
    monkeypatch.setattr(
        launcher,
        "canonical_repository_snapshot",
        lambda _root, **_kwargs: snapshot,
    )
    monkeypatch.setenv(
        "KRONOS_ACTIVATION_GOVERNANCE_PUBLICATION_SHA",
        LATEST_GOVERNANCE_SHA,
    )
    monkeypatch.setattr(launcher.pwd, "getpwuid", lambda _uid: sponsor)
    monkeypatch.setattr(launcher, "runtime_version_evidence", lambda: object())
    monkeypatch.setattr(launcher, "_durable_state", lambda *_args: (True, True))
    monkeypatch.setattr(launcher, "_port_ready_without_bind", lambda: True)

    def execute(**_kwargs: object) -> object:
        calls.append("execute-governed-launcher")
        return object()

    monkeypatch.setattr(launcher, "execute_governed_launcher", execute)

    assert launcher.main() == 0
    assert calls == ["execute-governed-launcher"]
