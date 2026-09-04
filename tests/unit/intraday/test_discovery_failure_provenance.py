from __future__ import annotations

from pathlib import Path

import pytest

from kronos.application.intraday_discovery import IntradayDiscoveryApplication
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.discovery import DiscoveryError, DiscoveryFailure
from kronos.intraday.discovery_failure_provenance import (
    DISCOVERY_FAILURE_PROVENANCE_POLICY,
    DISCOVERY_FAILURE_PROVENANCE_POLICY_VERSION,
    MachineFactFailureAvailability,
    MachineFactFailureComponent,
    MachineFactFailureDetail,
    MachineFactFailureStage,
    discovery_failure_provenance_bytes,
    parse_discovery_failure_provenance,
)
from kronos.intraday.discovery_persistence import NativeDiscoveryStore
from kronos.intraday.reconciliation import (
    RECONCILIATION_IDENTITY,
    RECONCILIATION_VERSION,
)
from kronos.intraday.reconciliation_persistence import IntradayReconciliationStore
from kronos.intraday.universe import load_intraday_universe_publication
from tests.unit.intraday.test_discovery_source import _composition


def _nifty_failure(tmp_path: Path):  # type: ignore[no-untyped-def]
    execution, _, _, _, _ = _composition(
        tmp_path,
        omit_target="NIFTY 50",
        operation_identity="KRONOS-INTRADAY-DISCOVERY-OPERATION-WOA2TEST",
    )
    return execution, next(
        item
        for item in execution.failure_provenance
        if item.canonical_subject_identity == "NSE-INDEX-NIFTY"
    )


def test_nifty_missing_opening_15m_is_exact_sanitized_provenance(
    tmp_path: Path,
) -> None:
    execution, failure = _nifty_failure(tmp_path)

    assert failure.failure_stage is MachineFactFailureStage.REQUIRED_TIMEFRAME_ABSENCE
    assert (
        failure.required_component
        is MachineFactFailureComponent.CURRENT_OPENING_15M_EVIDENCE
    )
    assert failure.required_timeframe is IntradayTimeframe.FIFTEEN_MINUTES
    assert failure.expected_candle_interval == "15minute"
    assert failure.availability_failure is MachineFactFailureAvailability.NOT_COMPLETED
    assert failure.sanitized_failure_code == "COMPLETED_CANDLE_MISSING"
    assert failure.provider_symbol_binding == "NIFTY 50"
    assert failure.operation_identity == (
        "KRONOS-INTRADAY-DISCOVERY-OPERATION-WOA2TEST"
    )
    assert failure.policy_identity == DISCOVERY_FAILURE_PROVENANCE_POLICY
    assert failure.policy_version == DISCOVERY_FAILURE_PROVENANCE_POLICY_VERSION
    assert failure.discovery_run_identity == execution.run.run_identity
    assert failure.analytical_authority == "NONE"
    assert failure.probable_authority == "NONE"
    assert failure.current_pointer_authority == "NONE"


def test_failure_provenance_is_canonical_immutable_and_sanitized(
    tmp_path: Path,
) -> None:
    execution, failure = _nifty_failure(tmp_path)
    encoded = discovery_failure_provenance_bytes(failure)

    assert parse_discovery_failure_provenance(encoded) == failure
    assert failure.integrity_hash.encode() in encoded
    assert b"/Users/" not in encoded
    assert b"Authorization" not in encoded
    assert b"access_token" not in encoded

    store = NativeDiscoveryStore(tmp_path.resolve())
    assert store.load_failure_provenance_for_run(
        run_identity=execution.run.run_identity
    ) == execution.failure_provenance
    path = store.failure_provenance_path(
        run_identity=execution.run.run_identity,
        failure_identity=failure.failure_identity,
    )
    path.write_bytes(b"{}")
    with pytest.raises(
        DiscoveryError,
        match=DiscoveryFailure.PERSISTENCE_CONFLICT.value,
    ):
        store.retain_run(
            execution.run,
            bundles=execution.bundles,
            failure_provenance=execution.failure_provenance,
        )


def test_provider_exception_is_reduced_to_bounded_candle_acquisition_code(
    tmp_path: Path,
) -> None:
    execution, _, _, _, _ = _composition(
        tmp_path,
        historical_error_target="NIFTY 50",
    )
    failure = next(
        item
        for item in execution.failure_provenance
        if item.canonical_subject_identity == "NSE-INDEX-NIFTY"
    )
    encoded = discovery_failure_provenance_bytes(failure)

    assert failure.failure_stage is MachineFactFailureStage.CANDLE_ACQUISITION
    assert failure.required_component is (
        MachineFactFailureComponent.PREVIOUS_COMPLETED_DAILY_EVIDENCE
    )
    assert failure.sanitized_failure_code == "PROVIDER_CANDLE_ACQUISITION_FAILED"
    assert b"SENSITIVE_VALUE" not in encoded
    assert b"/sensitive/" not in encoded


def test_old_run_restores_without_detailed_failure_provenance(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    execution, _, _, _, _ = _composition(old_root)
    store = NativeDiscoveryStore(old_root.resolve())
    assert store.load_failure_provenance_for_run(
        run_identity=execution.run.run_identity
    ) == ()

    universe = load_intraday_universe_publication()
    reconciliation = IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version=RECONCILIATION_VERSION,
    )
    restored = IntradayDiscoveryApplication(
        universe=universe,
        reconciliation=reconciliation,
        store=store,
        last_successful_run_identity=execution.run.run_identity,
    ).snapshot("NIFTY")
    assert restored.selected_member is not None
    assert restored.selected_member.failure_provenance is None


def test_new_failure_provenance_restores_without_becoming_analysis(
    tmp_path: Path,
) -> None:
    execution, failure = _nifty_failure(tmp_path)
    universe = load_intraday_universe_publication()
    reconciliation = IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version=RECONCILIATION_VERSION,
    )
    snapshot = IntradayDiscoveryApplication(
        universe=universe,
        reconciliation=reconciliation,
        store=NativeDiscoveryStore(tmp_path.resolve()),
        last_successful_run_identity=execution.run.run_identity,
    ).snapshot("NIFTY")

    assert snapshot.selected_member is not None
    assert snapshot.selected_member.failure_provenance == failure
    assert snapshot.selected_member.machine_fact_bundle is None
    assert snapshot.selected_member.machine_facts_available is False
    assert snapshot.candidate_admitted_count == 0


def test_stage_vocabulary_is_exact_and_bounded() -> None:
    assert {item.value for item in MachineFactFailureStage} == {
        "SCHEDULE_SESSION_BINDING",
        "PROVIDER_SYMBOL_BINDING",
        "CANDLE_ACQUISITION",
        "INTERVAL_SELECTION",
        "COMPLETION_VALIDATION",
        "REQUIRED_TIMEFRAME_ABSENCE",
        "BUNDLE_CONSTRUCTION",
        "BUNDLE_VALIDATION",
        "PERSISTENCE",
    }
    detail = MachineFactFailureDetail(
        stage=MachineFactFailureStage.PERSISTENCE,
        component=MachineFactFailureComponent.FAILURE_PROVENANCE_ARTIFACT,
        required_timeframe=None,
        expected_candle_interval=None,
        availability_failure=MachineFactFailureAvailability.PERSISTENCE_FAILED,
        sanitized_failure_code="FAILURE_PROVENANCE_PERSISTENCE_FAILED",
    )
    assert detail.provider_symbol_binding is None


def test_unknown_or_conflicting_contract_bytes_fail_closed(tmp_path: Path) -> None:
    _, failure = _nifty_failure(tmp_path)
    encoded = discovery_failure_provenance_bytes(failure)
    with pytest.raises(ValueError, match="DISCOVERY_FAILURE_PROVENANCE_INVALID"):
        parse_discovery_failure_provenance(encoded[:-1] + b',"raw_error":"secret"}')
    conflicting = encoded.replace(
        b'"sanitized_failure_code":"COMPLETED_CANDLE_MISSING"',
        b'"sanitized_failure_code":"DIFFERENT"',
    )
    with pytest.raises(ValueError, match="DISCOVERY_FAILURE_PROVENANCE_INVALID"):
        parse_discovery_failure_provenance(conflicting)
