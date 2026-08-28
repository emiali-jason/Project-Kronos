from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_discovery_operation import (
    DISCOVERY_PROBABLES_V2_REFRESH_ORCHESTRATION_IDENTITY,
)
from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.intraday.completed_evidence import EvidenceSessionRole, IntradayAnalysisPhase
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.probables_v2 import ProbablesV2Error
from kronos.intraday.probables_v2_diagnostics import (
    ProbablesV2ExceptionCategory,
    create_probables_v2_replay_envelope,
    reconstruct_v2_execution,
    replay_v2_mapping,
)
from kronos.intraday.discovery_runtime import DiscoveryRuntimeExecution
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.probables_v2_refresh import DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY
from tests.unit.intraday.test_probables_v2_refresh_control import _control, _payload


IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize(
    ("boundary", "phase"),
    (
        (datetime(2026, 8, 24, 9, 35, tzinfo=IST), IntradayAnalysisPhase.OPENING),
        (datetime(2026, 8, 24, 10, 0, tzinfo=IST), IntradayAnalysisPhase.STRUCTURE),
        (datetime(2026, 8, 24, 10, 20, tzinfo=IST), IntradayAnalysisPhase.FIRST_CURRENT_SESSION_1H),
        (datetime(2026, 8, 24, 11, 20, tzinfo=IST), IntradayAnalysisPhase.CURRENT_SESSION_ESTABLISHED),
    ),
)
def test_replay_round_trip_preserves_all_four_phases(
    tmp_path: Path, boundary: datetime, phase: IntradayAnalysisPhase
) -> None:
    _, composition, control, _, provider_requests = _control(tmp_path, boundary=boundary)
    result = control.execute_document(_payload(f"REPLAY-{phase.value}", boundary=boundary))
    reads = provider_requests[0]

    envelope = composition.probables_v2_diagnostics_store.load_envelope(
        result["replay_envelope_identity"]
    )
    mapping = replay_v2_mapping(envelope)

    assert result["outcome"] == "SUCCESS"
    assert {item.completed_evidence.phase for item in mapping.member_evidence} == {phase}
    if phase is IntradayAnalysisPhase.OPENING:
        sample = mapping.member_evidence[0]
        assert sample.completed_evidence.candles(
            IntradayTimeframe.ONE_HOUR,
            EvidenceSessionRole.CURRENT_SESSION_1H_PRIMARY,
        ) == ()
    assert provider_requests == [reads]


def test_successful_envelope_replays_exact_probables_without_provider(
    tmp_path: Path,
) -> None:
    _, composition, control, _, provider_requests = _control(tmp_path)
    result = control.execute_document(_payload("REPLAY-SUCCESS"))
    reads = provider_requests[0]
    envelope = composition.probables_v2_diagnostics_store.load_envelope(
        result["replay_envelope_identity"]
    )
    mapping = replay_v2_mapping(envelope)
    isolated = IntradayProbablesV2Application(
        store=ProbablesV2Store((tmp_path / "isolated-replay").resolve()),
        restore_current=False,
    )

    replayed = isolated.refresh_analysis(
        source_discovery_run_identity=envelope.discovery_run.run_identity,
        universe_identity=envelope.discovery_run.universe_identity,
        universe_version=envelope.discovery_run.universe_version,
        reconciliation_identity=envelope.discovery_run.reconciliation_identity,
        reconciliation_version=envelope.discovery_run.reconciliation_version,
        market_session_identity=envelope.discovery_run.market_session_identity,
        analysis_boundary=envelope.analysis_boundary,
        member_evidence=mapping.member_evidence,
        unavailable_members=mapping.unavailable_members,
        provenance=(
            DISCOVERY_PROBABLES_V2_REFRESH_ORCHESTRATION_IDENTITY,
            DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY,
            mapping.mapping_identity,
        ),
    )
    original = ProbablesV2Store(tmp_path.resolve()).load_run(
        result["resulting_probables_identity"]
    )
    provenance = composition.refresh_v2_provenance_store.load_for_request(
        "REPLAY-SUCCESS"
    )

    assert replayed == original
    assert provenance is not None
    assert provenance.replay_envelope_identity == envelope.envelope_identity
    assert provenance.failure_detail_identity is None
    assert provider_requests == [reads]


def test_opening_nifty_relationships_and_unavailable_mcx_survive_replay(
    tmp_path: Path,
) -> None:
    boundary = datetime(2026, 8, 24, 9, 35, tzinfo=IST)
    _, composition, control, _, _ = _control(tmp_path, boundary=boundary)
    result = control.execute_document(_payload("REPLAY-NIFTY", boundary=boundary))
    envelope = composition.probables_v2_diagnostics_store.load_envelope(
        result["replay_envelope_identity"]
    )
    mapping = replay_v2_mapping(envelope)
    by_subject = {item.canonical_subject_identity: item for item in mapping.member_evidence}

    assert by_subject["NSE-INDEX-NIFTY"].nifty_relative.fact.applicability.value == "NOT_APPLICABLE"
    assert by_subject["NSE-INDEX-BANKNIFTY"].nifty_relative.fact.applicability.value == "APPLICABLE"
    assert by_subject["NSE-EQ-ADANIENT"].nifty_relative.fact.applicability.value == "APPLICABLE"
    assert {item.canonical_subject_identity for item in mapping.unavailable_members} == {
        "MCX-SUBJECT-GOLDM", "MCX-SUBJECT-SILVERM", "MCX-SUBJECT-COPPER",
        "MCX-SUBJECT-NATGAS", "MCX-SUBJECT-CRUDE",
    }
    with pytest.raises(ValueError, match="REPLAY_ENVELOPE_INVALID"):
        replace(envelope, analysis_boundary=datetime(2026, 8, 24, 9, 36, tzinfo=IST))

    execution = reconstruct_v2_execution(envelope)
    no_nifty_execution = DiscoveryRuntimeExecution(
        run=execution.run,
        bundles=execution.bundles,
        evidence=execution.evidence,
        probables_facts=execution.probables_facts,
        pre_evaluable_count=execution.pre_evaluable_count,
        prerequisite_unavailable_count=execution.prerequisite_unavailable_count,
        timeframe_fact_requests=execution.timeframe_fact_requests,
        source_operation_count=execution.source_operation_count,
        probables_v2_facts=tuple(
            item for item in execution.probables_v2_facts
            if item.canonical_subject_identity != "NSE-INDEX-NIFTY"
        ),
    )
    no_nifty_envelope = create_probables_v2_replay_envelope(
        request_identity="REPLAY-NIFTY-UNAVAILABLE",
        operation_identity=envelope.operation_identity,
        execution=no_nifty_execution,
        reconciliation=envelope.reconciliation,
        created_at=boundary,
    )
    no_nifty = replay_v2_mapping(no_nifty_envelope)
    no_nifty_subjects = {
        item.canonical_subject_identity: item for item in no_nifty.member_evidence
    }
    assert no_nifty_subjects["NSE-EQ-ADANIENT"].nifty_relative.relationship.value == "UNAVAILABLE"
    assert any(
        item.canonical_subject_identity == "NSE-INDEX-NIFTY"
        for item in no_nifty.unavailable_members
    )


@pytest.mark.parametrize(
    ("message", "category"),
    (
        ("COMPLETED_EVIDENCE_PHASE_INVALID", ProbablesV2ExceptionCategory.PHASE_SELECTION_ERROR),
        ("OPENING_SEMANTIC_INVALID", ProbablesV2ExceptionCategory.SEMANTIC_ERROR),
        ("NIFTY_CONTEXT_INVALID", ProbablesV2ExceptionCategory.NIFTY_CONTEXT_ERROR),
        ("PROBABLES_V2_SCHEMA_INVALID", ProbablesV2ExceptionCategory.SCHEMA_ERROR),
    ),
)
def test_mapping_failures_retain_envelope_typed_detail_and_no_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, message: str,
    category: ProbablesV2ExceptionCategory,
) -> None:
    _, composition, control, _, _ = _control(tmp_path)

    def fail_mapping(**_values):  # type: ignore[no-untyped-def]
        raise ProbablesV2Error(message)

    monkeypatch.setattr(
        "kronos.application.intraday_discovery_operation.map_discovery_execution_to_probables_v2",
        fail_mapping,
    )
    result = control.execute_document(_payload(f"FAIL-{category.value}"))
    detail = composition.probables_v2_diagnostics_store.load_failure(
        result["failure_detail_identity"]
    )
    provenance = composition.refresh_v2_provenance_store.load_for_request(
        f"FAIL-{category.value}"
    )

    assert result["failure"] == "PROBABLES_MAPPING_FAILURE"
    assert detail.exception_category is category
    assert detail.replay_envelope_identity == result["replay_envelope_identity"]
    assert provenance is not None and provenance.failure_detail_identity == detail.failure_identity
    assert ProbablesV2Store(tmp_path.resolve()).load_current() is None


def test_probables_invocation_failure_is_sanitized_and_browser_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared, composition, control, _, _ = _control(tmp_path)

    def fail_invocation(self, **_values):  # type: ignore[no-untyped-def]
        raise RuntimeError("access_token=SHOULD_NOT_SURVIVE")

    monkeypatch.setattr(IntradayProbablesV2Application, "refresh_analysis", fail_invocation)
    result = control.execute_document(_payload("FAIL-INVOKE"))
    detail = composition.probables_v2_diagnostics_store.load_failure(
        result["failure_detail_identity"]
    )
    status = control.status_document()

    assert result["failure"] == "PROBABLES_REFRESH_FAILURE"
    assert detail.exception_category is ProbablesV2ExceptionCategory.UNEXPECTED_INTERNAL_ERROR
    assert detail.sanitized_detail == "UNEXPECTED_INTERNAL_ERROR"
    assert "SHOULD_NOT_SURVIVE" not in repr(status)
    assert status["failure_detail"]["failure_identity"] == detail.failure_identity
    assert ProbablesV2Store(tmp_path.resolve()).load_current() is None
    restored = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: detail.analysis_boundary,
    ).probables_v2_application.snapshot()
    assert restored.failure_detail == detail


def test_known_probables_result_contract_failure_is_schema_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, composition, control, _, _ = _control(tmp_path)

    def fail_invocation(self, **_values):  # type: ignore[no-untyped-def]
        raise ProbablesV2Error("PROBABLES_V2_RESULT_INVALID")

    monkeypatch.setattr(IntradayProbablesV2Application, "refresh_analysis", fail_invocation)
    result = control.execute_document(_payload("FAIL-KNOWN-RESULT-CONTRACT"))
    detail = composition.probables_v2_diagnostics_store.load_failure(
        result["failure_detail_identity"]
    )

    assert result["failure"] == "PROBABLES_REFRESH_FAILURE"
    assert detail.exception_category is ProbablesV2ExceptionCategory.SCHEMA_ERROR
    assert detail.typed_reason_code == "PROBABLES_V2_SCHEMA_ERROR"
    assert detail.sanitized_detail == "PROBABLES_V2_RESULT_INVALID"


def test_replay_persistence_failure_stops_before_mapping_and_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, composition, control, _, _ = _control(tmp_path)
    invoked = {"mapping": 0}

    def fail_persistence(_value):  # type: ignore[no-untyped-def]
        raise OSError("PERSISTENCE_UNAVAILABLE")

    def observe_mapping(**_values):  # type: ignore[no-untyped-def]
        invoked["mapping"] += 1
        raise AssertionError("MAPPING_MUST_NOT_RUN")

    monkeypatch.setattr(composition.probables_v2_diagnostics_store, "retain_envelope", fail_persistence)
    monkeypatch.setattr(
        "kronos.application.intraday_discovery_operation.map_discovery_execution_to_probables_v2",
        observe_mapping,
    )
    result = control.execute_document(_payload("FAIL-REPLAY-PERSISTENCE"))
    detail = composition.probables_v2_diagnostics_store.load_failure(
        result["failure_detail_identity"]
    )

    assert result["failure"] == "PERSISTENCE_FAILURE"
    assert detail.exception_category is ProbablesV2ExceptionCategory.PERSISTENCE_ERROR
    assert invoked["mapping"] == 0
    assert ProbablesV2Store(tmp_path.resolve()).load_current() is None


def test_downstream_persistence_failure_retains_sealed_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, composition, control, _, _ = _control(tmp_path)

    def fail_probables_persistence(self, **_values):  # type: ignore[no-untyped-def]
        raise OSError("PERSISTENCE_UNAVAILABLE")

    monkeypatch.setattr(ProbablesV2Store, "retain_complete", fail_probables_persistence)
    result = control.execute_document(_payload("FAIL-DOWNSTREAM-PERSISTENCE"))
    detail = composition.probables_v2_diagnostics_store.load_failure(
        result["failure_detail_identity"]
    )
    envelope = composition.probables_v2_diagnostics_store.load_envelope(
        result["replay_envelope_identity"]
    )

    assert result["failure"] == "PROBABLES_REFRESH_FAILURE"
    assert detail.exception_category is ProbablesV2ExceptionCategory.PERSISTENCE_ERROR
    assert detail.replay_envelope_identity == envelope.envelope_identity
    assert ProbablesV2Store(tmp_path.resolve()).load_current() is None
