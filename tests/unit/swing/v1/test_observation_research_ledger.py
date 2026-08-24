from dataclasses import replace
from datetime import timedelta

import pytest

from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.observation_research_ledger import (
    LocalObservationResearchLedgerStore,
    OBSERVATION_RESEARCH_AUTHORITY,
    ObservationLinkKind,
    ObservationResearchLedgerService,
    ObservationResearchQueryV1,
    ObservationResearchRecordV1,
)
from kronos.swing.v1.sponsor_observation_decision import (
    LocalSponsorObservationDecisionStore,
    SponsorActivationDisposition,
    SponsorObservationReason,
)
from kronos.swing.v1.step31_observation import Step31WarningSeverity
from tests.unit.swing.v1.test_kr370_step31_handoff import NOW, _completed
from tests.unit.swing.v1.test_sponsor_observation_decision import (
    _green,
    _record,
    _red,
)
from tests.unit.swing.v1.test_step31_observation import _observe, _package


def _service(tmp_path, result):  # type: ignore[no-untyped-def]
    decisions = LocalSponsorObservationDecisionStore(tmp_path / "decisions")
    decisions.retain(result)
    service = ObservationResearchLedgerService(
        LocalObservationResearchLedgerStore(tmp_path / "research"), decisions
    )
    service.retain_observation(result)
    return service


def _amber(tmp_path):  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    observation = _observe(
        completed, _package(completed, governing_structural_low=None)
    )
    return completed, observation


@pytest.mark.parametrize(
    ("severity", "choice", "disposition", "risk_state", "acknowledged"),
    (
        ("GREEN", SponsorTradeChoice.PAPER, SponsorActivationDisposition.ACTIVATED, "RISK_APPROVED", False),
        ("GREEN", SponsorTradeChoice.LIVE, SponsorActivationDisposition.ACTIVATED, "RISK_APPROVED", False),
        ("GREEN", SponsorTradeChoice.IGNORE, SponsorActivationDisposition.NOT_APPLICABLE_IGNORE, "RISK_UNAVAILABLE", False),
        ("AMBER", SponsorTradeChoice.PAPER, SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE, "RISK_UNAVAILABLE", False),
        ("AMBER", SponsorTradeChoice.LIVE, SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE, "RISK_UNAVAILABLE", False),
        ("AMBER", SponsorTradeChoice.IGNORE, SponsorActivationDisposition.NOT_APPLICABLE_IGNORE, "RISK_UNAVAILABLE", False),
        ("RED", SponsorTradeChoice.PAPER, SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE, "RISK_UNAVAILABLE", True),
        ("RED", SponsorTradeChoice.LIVE, SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE, "RISK_UNAVAILABLE", True),
        ("RED", SponsorTradeChoice.IGNORE, SponsorActivationDisposition.NOT_APPLICABLE_IGNORE, "RISK_UNAVAILABLE", False),
    ),
)
def test_all_decisions_are_first_class_without_outcome_or_position_dependency(
    tmp_path, severity, choice, disposition, risk_state, acknowledged  # type: ignore[no-untyped-def]
) -> None:
    completed, observation = {
        "GREEN": _green,
        "AMBER": _amber,
        "RED": _red,
    }[severity](tmp_path)
    changes = {}
    if disposition is SponsorActivationDisposition.ACTIVATED:
        changes = dict(
            risk_identity="RISK-ACTIVATED",
            existing_sponsor_decision_identity="SPONSOR-DECISION-ACTIVATED",
            sponsor_position_identity="SPONSOR-POSITION-ACTIVATED",
        )
    result = _record(
        completed, observation, choice, disposition,
        risk_state=risk_state, acknowledged=acknowledged,
        sponsor_reason=(
            SponsorObservationReason.STEP31_WARNING if acknowledged else None
        ),
        **changes,
    )
    service = _service(tmp_path, result)
    snapshot = service.snapshot()

    assert len(snapshot) == 1
    assert snapshot[0].record.choice is choice
    assert snapshot[0].source.snapshot.step31_severity.value == severity
    assert not snapshot[0].objective_outcome_available
    assert not snapshot[0].sponsor_position_outcome_available
    assert snapshot[0].record.authority == OBSERVATION_RESEARCH_AUTHORITY


def test_exact_queries_exports_restart_and_late_objective_link(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed, observation = _green(tmp_path)
    result = _record(
        completed, observation, SponsorTradeChoice.PAPER,
        SponsorActivationDisposition.ACTIVATED,
        risk_state="RISK_APPROVED", risk_identity="RISK-1",
        existing_sponsor_decision_identity="SPONSOR-DECISION-1",
        sponsor_position_identity="SPONSOR-POSITION-1",
    )
    service = _service(tmp_path, result)
    snapshot = result.snapshot
    frozen_decision_evidence = (
        snapshot.native_run_identity, snapshot.step31_severity,
        snapshot.step31_warnings, snapshot.risk_identity, snapshot.risk_state,
    )
    common = dict(
        decision_identity=result.decision.decision_identity,
        native_run_identity=snapshot.native_run_identity,
        canonical_instrument=snapshot.canonical_instrument,
        native_assessment_sha256=snapshot.native_assessment_sha256,
        trade_plan_identity=snapshot.conventional_trade_plan_identity,
        trade_plan_sha256=snapshot.conventional_trade_plan_sha256,
    )
    link = service.append_link(
        **common,
        kind=ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME,
        source_contract_identity="KRONOS-SWING-OBJECTIVE-MODEL-TRADE-V1",
        source_contract_version="1",
        source_record_identity="OBJECTIVE-MODEL-1",
        source_integrity_sha256="a" * 64,
        source_state="CLOSED",
        source_timestamp=NOW + timedelta(hours=2),
    )
    assert service.append_link(
        **common,
        kind=ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME,
        source_contract_identity="KRONOS-SWING-OBJECTIVE-MODEL-TRADE-V1",
        source_contract_version="1",
        source_record_identity="OBJECTIVE-MODEL-1",
        source_integrity_sha256="a" * 64,
        source_state="CLOSED",
        source_timestamp=NOW + timedelta(hours=2),
    ) == link
    with pytest.raises(ValueError, match="DUPLICATE_OR_CORRUPT_LINK"):
        service.append_link(
            **common,
            kind=ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME,
            source_contract_identity="KRONOS-SWING-OBJECTIVE-MODEL-TRADE-V1",
            source_contract_version="1",
            source_record_identity="OBJECTIVE-MODEL-1",
            source_integrity_sha256="b" * 64,
            source_state="CLOSED",
            source_timestamp=NOW + timedelta(hours=2),
        )

    query = ObservationResearchQueryV1(
        choices=(SponsorTradeChoice.PAPER,),
        dispositions=(SponsorActivationDisposition.ACTIVATED,),
        severities=(Step31WarningSeverity.GREEN,),
        kr370_states=("BUY_NOW",),
        risk_states=("RISK_APPROVED",),
        objective_outcome_available=True,
        sponsor_position_outcome_available=False,
    )
    assert len(service.snapshot(query)) == 1
    assert '"objective_outcome_available":"AVAILABLE"' in service.export_json(query)
    exported = service.export_csv(query)
    assert "UNAVAILABLE" in exported
    for field in (
        "entry", "stop", "target", "risk_reward_ratio", "sponsor_reason",
        "objective_kr380_state", "objective_kr390_identity",
        "objective_kr390_state", "objective_outcome",
        "sponsor_position_outcome", "mcx_supporting_context_identity",
    ):
        assert field in exported.splitlines()[0]
    assert (
        service.snapshot()[0].source.snapshot.native_run_identity,
        service.snapshot()[0].source.snapshot.step31_severity,
        service.snapshot()[0].source.snapshot.step31_warnings,
        service.snapshot()[0].source.snapshot.risk_identity,
        service.snapshot()[0].source.snapshot.risk_state,
    ) == frozen_decision_evidence

    restored = ObservationResearchLedgerService(service.store, service.decisions)
    assert restored.snapshot(query) == service.snapshot(query)


def test_position_and_outcome_require_exact_activated_position(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed, observation = _green(tmp_path)
    result = _record(
        completed, observation, SponsorTradeChoice.LIVE,
        SponsorActivationDisposition.ACTIVATED,
        risk_state="RISK_APPROVED", risk_identity="RISK-2",
        existing_sponsor_decision_identity="SPONSOR-DECISION-2",
        sponsor_position_identity="SPONSOR-POSITION-2",
    )
    service = _service(tmp_path, result)
    snapshot = result.snapshot
    common = dict(
        decision_identity=result.decision.decision_identity,
        native_run_identity=snapshot.native_run_identity,
        canonical_instrument=snapshot.canonical_instrument,
        native_assessment_sha256=snapshot.native_assessment_sha256,
        trade_plan_identity=snapshot.conventional_trade_plan_identity,
        trade_plan_sha256=snapshot.conventional_trade_plan_sha256,
    )
    with pytest.raises(ValueError, match="POSITION_BINDING_INVALID"):
        service.append_link(
            **common, kind=ObservationLinkKind.SPONSOR_POSITION,
            source_contract_identity="KRONOS-SWING-V1-SPONSOR-POSITION-V0",
            source_contract_version="0", source_record_identity="WRONG",
            source_integrity_sha256="b" * 64, source_state="LIVE_ACTIVE",
            source_timestamp=NOW, sponsor_position_identity="WRONG",
        )

    service.append_link(
        **common, kind=ObservationLinkKind.SPONSOR_POSITION,
        source_contract_identity="KRONOS-SWING-V1-SPONSOR-POSITION-V0",
        source_contract_version="0", source_record_identity="SPONSOR-POSITION-2",
        source_integrity_sha256="b" * 64, source_state="LIVE_ACTIVE",
        source_timestamp=NOW, sponsor_position_identity="SPONSOR-POSITION-2",
    )
    service.append_link(
        **common, kind=ObservationLinkKind.SPONSOR_POSITION_OUTCOME,
        source_contract_identity="KRONOS-SWING-V1-TRADE-CLOSURE-V1",
        source_contract_version="1", source_record_identity="CLOSURE-2",
        source_integrity_sha256="c" * 64, source_state="CLOSED",
        source_timestamp=NOW + timedelta(days=1),
        sponsor_position_identity="SPONSOR-POSITION-2",
    )
    assert service.snapshot()[0].sponsor_position_outcome_available


@pytest.mark.parametrize(
    ("choice", "disposition", "risk_state", "activated"),
    (
        (SponsorTradeChoice.IGNORE, SponsorActivationDisposition.NOT_APPLICABLE_IGNORE, "RISK_UNAVAILABLE", False),
        (SponsorTradeChoice.PAPER, SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE, "RISK_UNAVAILABLE", False),
        (SponsorTradeChoice.LIVE, SponsorActivationDisposition.BLOCKED_RISK_UNAVAILABLE, "RISK_UNAVAILABLE", False),
        (SponsorTradeChoice.PAPER, SponsorActivationDisposition.ACTIVATED, "RISK_APPROVED", True),
        (SponsorTradeChoice.LIVE, SponsorActivationDisposition.ACTIVATED, "RISK_APPROVED", True),
    ),
)
def test_objective_model_remains_independent_for_ignored_blocked_and_activated_choices(
    tmp_path, choice, disposition, risk_state, activated  # type: ignore[no-untyped-def]
) -> None:
    completed, observation = _green(tmp_path)
    changes = (
        dict(
            risk_identity="RISK-INDEPENDENCE",
            existing_sponsor_decision_identity="SPONSOR-DECISION-INDEPENDENCE",
            sponsor_position_identity="SPONSOR-POSITION-INDEPENDENCE",
        ) if activated else {}
    )
    result = _record(
        completed, observation, choice, disposition,
        risk_state=risk_state, **changes,
    )
    service = _service(tmp_path, result)
    snapshot = result.snapshot
    common = dict(
        decision_identity=result.decision.decision_identity,
        native_run_identity=snapshot.native_run_identity,
        canonical_instrument=snapshot.canonical_instrument,
        native_assessment_sha256=snapshot.native_assessment_sha256,
        trade_plan_identity=snapshot.conventional_trade_plan_identity,
        trade_plan_sha256=snapshot.conventional_trade_plan_sha256,
    )
    service.append_link(
        **common, kind=ObservationLinkKind.KR380_ENTRY_OUTCOME,
        source_contract_identity="KRONOS-KR-380-ENTRY-OUTCOME-V2",
        source_contract_version="2", source_record_identity="KR380-INDEPENDENCE",
        source_integrity_sha256="e" * 64,
        source_state="LONG_ENTRY_TRIGGERED", source_timestamp=NOW,
    )
    service.append_link(
        **common, kind=ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME,
        source_contract_identity="KRONOS-SWING-OBJECTIVE-MODEL-TRADE-V1",
        source_contract_version="1", source_record_identity="MODEL-INDEPENDENCE",
        source_integrity_sha256="f" * 64, source_state="CLOSED",
        source_timestamp=NOW + timedelta(days=1),
    )
    projected = service.snapshot()[0]
    assert projected.record.choice is choice
    assert projected.record.activation_disposition is disposition
    assert projected.objective_outcome_available
    assert not projected.sponsor_position_outcome_available
    assert (projected.source.activation.sponsor_position_identity is not None) is activated


def test_corrupt_mismatched_and_duplicate_links_fail_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed, observation = _red(tmp_path)
    result = _record(
        completed, observation, SponsorTradeChoice.IGNORE,
        SponsorActivationDisposition.NOT_APPLICABLE_IGNORE,
    )
    service = _service(tmp_path, result)
    snapshot = result.snapshot
    with pytest.raises(ValueError, match="BINDING_INVALID"):
        service.append_link(
            decision_identity=result.decision.decision_identity,
            kind=ObservationLinkKind.KR380_ENTRY_OUTCOME,
            source_contract_identity="KRONOS-KR-380-ENTRY-OUTCOME-V2",
            source_contract_version="2", source_record_identity="KR380-1",
            source_integrity_sha256="d" * 64, source_state="NO_TRIGGER",
            source_timestamp=NOW, native_run_identity=snapshot.native_run_identity,
            canonical_instrument="FOREIGN",
            native_assessment_sha256=snapshot.native_assessment_sha256,
            trade_plan_identity=None, trade_plan_sha256=None,
        )


def test_store_handles_representative_observation_horizon_deterministically(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = LocalObservationResearchLedgerStore(tmp_path / "capacity")
    for index in range(300):
        values = dict(
            record_identity=f"OBSERVATION-RESEARCH-{index:04d}",
            snapshot_identity=f"SNAPSHOT-{index:04d}", snapshot_sha256="1" * 64,
            decision_identity=f"DECISION-{index:04d}", decision_sha256="2" * 64,
            activation_identity=f"ACTIVATION-{index:04d}", activation_sha256="3" * 64,
            native_run_identity=f"SWING-RUN-{index:032X}",
            canonical_instrument=f"INSTRUMENT {index}", native_assessment_sha256="4" * 64,
            choice=SponsorTradeChoice.IGNORE,
            activation_disposition=SponsorActivationDisposition.NOT_APPLICABLE_IGNORE,
            decision_timestamp=NOW + timedelta(seconds=index), integrity_sha256="",
        )
        from kronos.swing.v1.observation_research_ledger import _values_digest
        store.retain_record(ObservationResearchRecordV1(**(
            values | {"integrity_sha256": _values_digest(values)}
        )))
    restored = store.load_records()
    assert len(restored) == 300
    assert len({item.record_identity for item in restored}) == 300
