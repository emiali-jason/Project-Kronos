from __future__ import annotations

from dataclasses import fields, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.application.intraday_wo11 import IntradayWo11Application
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo10 import (
    Wo10OperationOutcome,
    Wo10OperationStage,
    _identity as _wo10_identity,
    create_current_wo10_pointer,
    create_wo10_batch_result,
    create_wo10_operation_provenance,
    create_wo10_reconciliation_result,
)
from kronos.intraday.wo10_evidence import Wo10EvidenceSnapshot
from kronos.intraday.wo10_persistence import Wo10Store
from kronos.intraday.wo11 import (
    create_wo11_handoff_reference,
    create_wo11_publication_request,
    create_wo11_source_batch_binding,
)
from kronos.intraday.wo11_persistence import Wo11Store
from kronos.intraday.wo12 import create_wo12_handoff
from kronos.intraday.wo12_k5_foundation import (
    Wo12SetupFamily,
    derive_wo12_structural_origin,
)
from kronos.intraday.wo12_v2 import (
    Wo12CriterionIdentityV2,
    Wo12CriterionResultV2,
    create_current_wo12_pointer_v2,
    create_wo12_evidence_v2,
    create_wo12_request_v2,
    create_wo12_result_v2,
    create_wo13_eligibility_v2,
)
from kronos.intraday.wo13 import (
    WO13_POLICY_CHECKSUM,
    WO13_POLICY_IDENTITY,
    WO13_REQUEST_IDENTITY,
    WO13_TRADE_PLAN_IDENTITY,
    Wo13ContractError,
    Wo13FieldAvailability,
    Wo13GeometryAvailability,
    Wo13GeometryField,
    Wo13OperationOutcome,
    Wo13OperationStage,
    Wo13PolicyBinding,
    Wo13SupersessionReason,
    Wo13WarningCode,
    create_wo13_construction_request,
    create_wo13_field_availability,
    create_wo13_operation_provenance,
    create_wo13_supersession_lineage,
    create_wo13_supersession_reference,
    create_wo13_trade_plan_contract,
)
from kronos.intraday.wo13_handoff import (
    WO13_HANDOFF_IDENTITY,
    Wo13HandoffFailure,
    Wo13HandoffRejected,
    Wo13SetupFamily,
    create_wo13_step31_handoff,
)
from kronos.validation.kr370 import (
    Kr370AnalyticalClassification,
    Kr370CriterionState,
)

from .test_wo10_contracts import REQUESTED_AT
from .test_wo10_mcx import _fixture as _mcx_fixture
from .test_wo10_mcx import _location as _mcx_location
from .test_wo10_mcx import _reload as _reload_mcx
from .test_wo12 import _foundation, _rebound


def _criterion(
    identity: Wo12CriterionIdentityV2,
    state: Kr370CriterionState,
) -> Wo12CriterionResultV2:
    return Wo12CriterionResultV2(
        identity=identity,
        state=state,
        reason=f"{identity.value}_{state.value}",
        evidence_identities=(f"EVIDENCE-{identity.value}",),
        evidence_integrities=(f"INTEGRITY-{identity.value}",),
    )


def _snapshot_direction(
    snapshot: Wo10EvidenceSnapshot,
    direction: SemanticDirection,
) -> Wo10EvidenceSnapshot:
    values = {
        item.name: getattr(snapshot, item.name)
        for item in fields(Wo10EvidenceSnapshot)
        if item.name not in {"snapshot_identity", "snapshot_integrity"}
    }
    values["inherited_direction"] = direction
    return Wo10EvidenceSnapshot(
        snapshot_identity=_wo10_identity(
            "INTRADAY-WO10-EVIDENCE-SNAPSHOT-", values
        ),
        snapshot_integrity=_wo10_identity(
            "INTEGRITY-INTRADAY-WO10-EVIDENCE-SNAPSHOT-", values
        ),
        **values,
    )


def _artifacts(
    tmp_path,
    *,
    direction: SemanticDirection = SemanticDirection.LONG,
    satisfied: int = 4,
    setup: Wo12SetupFamily = Wo12SetupFamily.PULLBACK_CONTINUATION,
    minute: int = 20,
):  # type: ignore[no-untyped-def]
    wo10, _, handoff, _ = _foundation(tmp_path)
    snapshot = wo10.load_evidence_snapshot(handoff.wo10_evidence_identity)
    if direction is SemanticDirection.SHORT:
        prior_integrity = snapshot.snapshot_integrity
        snapshot = _snapshot_direction(snapshot, direction)
        handoff = _rebound(
            handoff,
            inherited_direction=direction,
            wo10_evidence_identity=snapshot.snapshot_identity,
            wo10_evidence_integrity=snapshot.snapshot_integrity,
            source_integrities=tuple(sorted(
                snapshot.snapshot_integrity if item == prior_integrity else item
                for item in handoff.source_integrities
            )),
        )
    request = create_wo12_request_v2(
        handoff=handoff,
        requested_at=REQUESTED_AT + timedelta(minutes=minute),
        sponsor_operation_identity=f"SPONSOR-WO13-SLICE1-{minute}",
        provenance=("ADR-0022",),
    )
    criteria = tuple(
        _criterion(
            identity,
            Kr370CriterionState.SATISFIED
            if index < satisfied
            else Kr370CriterionState.UNSATISFIED,
        )
        for index, identity in enumerate(Wo12CriterionIdentityV2)
    )
    evidence = create_wo12_evidence_v2(
        request=request,
        criteria=criteria,
        exact_binding_valid=True,
        governing_15m_structure_failed=False,
        authoritative_directional_conflict=False,
    )
    result = create_wo12_result_v2(
        request=request,
        evidence=evidence,
        created_at=request.requested_at,
        provenance=("ADR-0022",),
    )
    eligibility = create_wo13_eligibility_v2(
        result, provenance=("ADR-0022",)
    )
    pointer = create_current_wo12_pointer_v2(request, result, eligibility)
    setup_evidence = derive_wo12_structural_origin(
        canonical_subject_identity=handoff.canonical_subject_identity,
        market_family=handoff.market_family,
        setup_family=setup,
        inherited_direction=direction,
        analysis_boundary=handoff.analysis_boundary,
        evidence=None,
    )
    return pointer, request, evidence, result, eligibility, snapshot, setup_evidence


def _handoff(tmp_path, **changes):  # type: ignore[no-untyped-def]
    values = _artifacts(tmp_path, **changes)
    return create_wo13_step31_handoff(
        current_pointer=values[0], request=values[1], evidence=values[2],
        result=values[3], eligibility=values[4], wo10_snapshot=values[5],
        setup_evidence=values[6],
    )


def _mcx_artifacts(tmp_path):  # type: ignore[no-untyped-def]
    decision, wo10_request, snapshot, loaded = _mcx_fixture(tmp_path)
    assert decision is not None
    wo10_result = create_wo10_reconciliation_result(
        request=wo10_request,
        evidence=snapshot,
        state=decision.state,
        reasons=decision.reasons,
        provenance=("WO13-MCX-TEST",),
    )
    batch = create_wo10_batch_result(
        request=wo10_request,
        results=(wo10_result,),
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        provenance=("WO13-MCX-TEST",),
    )
    operation = create_wo10_operation_provenance(
        request=wo10_request,
        stage=Wo10OperationStage.BATCH_PUBLICATION,
        outcome=Wo10OperationOutcome.COMPLETED,
        started_at=REQUESTED_AT,
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        results=(wo10_result,),
        batch=batch,
        provenance=("WO13-MCX-TEST",),
    )
    wo10 = Wo10Store((tmp_path / "wo10-store").resolve())
    for retain, value in (
        (wo10.retain_policy, wo10_request.policy),
        (wo10.retain_request, wo10_request),
        (wo10.retain_evidence_snapshot, snapshot),
        (wo10.retain_result, wo10_result),
        (wo10.retain_batch, batch),
        (wo10.retain_operation, operation),
    ):
        retain(value)
    wo10.publish_current(create_current_wo10_pointer(wo10_request, batch))
    source = create_wo11_source_batch_binding(
        batch=batch, request=wo10_request, operation=operation
    )
    wo11 = Wo11Store((tmp_path / "wo11-store").resolve())
    published = IntradayWo11Application(wo10_store=wo10, store=wo11).execute(
        create_wo11_publication_request(
            source_batches=(source,),
            requested_at=REQUESTED_AT + timedelta(minutes=2),
            sponsor_operation_identity="SPONSOR-WO13-MCX-WO11",
            provenance=("WO13-MCX-TEST",),
        )
    )
    member = published.members[0]
    wo11_handoff = create_wo11_handoff_reference(published.publication, member)
    handoff = create_wo12_handoff(
        publication=published.publication,
        member=member,
        wo11_handoff=wo11_handoff,
    )
    request = create_wo12_request_v2(
        handoff=handoff,
        requested_at=REQUESTED_AT + timedelta(minutes=20),
        sponsor_operation_identity="SPONSOR-WO13-MCX-WO12",
        provenance=("ADR-0022",),
    )
    criteria = tuple(
        _criterion(item, Kr370CriterionState.SATISFIED)
        for item in Wo12CriterionIdentityV2
    )
    evidence = create_wo12_evidence_v2(
        request=request, criteria=criteria, exact_binding_valid=True,
        governing_15m_structure_failed=False,
        authoritative_directional_conflict=False,
    )
    result = create_wo12_result_v2(
        request=request, evidence=evidence, created_at=request.requested_at,
        provenance=("ADR-0022",),
    )
    eligibility = create_wo13_eligibility_v2(result, provenance=("ADR-0022",))
    pointer = create_current_wo12_pointer_v2(request, result, eligibility)
    setup = derive_wo12_structural_origin(
        canonical_subject_identity=handoff.canonical_subject_identity,
        market_family=handoff.market_family,
        setup_family=Wo12SetupFamily.PULLBACK_CONTINUATION,
        inherited_direction=handoff.inherited_direction,
        analysis_boundary=handoff.analysis_boundary,
        evidence=None,
    )
    return pointer, request, evidence, result, eligibility, snapshot, setup, loaded


def _unavailable_fields():
    return tuple(
        create_wo13_field_availability(
            item,
            Wo13FieldAvailability.UNAVAILABLE,
            reason="NOT_CONSTRUCTED_IN_SLICE1",
        )
        for item in Wo13GeometryField
    )


def _empty_plan(request):  # type: ignore[no-untyped-def]
    return create_wo13_trade_plan_contract(
        request=request,
        entry_reference=None,
        entry_condition=None,
        stop=None,
        stop_structural_basis=None,
        thesis_invalidation_reference=None,
        thesis_invalidation_event=None,
        setup_native_target=None,
        canonical_target=None,
        target_structural_basis=None,
        constraining_objective=None,
        risk_distance=None,
        reward_distance=None,
        model_rr=None,
        geometry_availability=Wo13GeometryAvailability.GEOMETRY_UNAVAILABLE,
        field_availability=_unavailable_fields(),
        warnings=(),
        supersession=None,
        provenance=("WO13-SLICE1-CONTRACT-ONLY",),
    )


def test_contract_identities_policy_and_bounded_vocabularies_are_frozen() -> None:
    assert WO13_HANDOFF_IDENTITY == "KRONOS-INTRADAY-WO13-STEP31-HANDOFF-V1"
    assert WO13_REQUEST_IDENTITY == "KRONOS-INTRADAY-WO13-TRADE-CONSTRUCTION-REQUEST-V1"
    assert WO13_TRADE_PLAN_IDENTITY == "KRONOS-INTRADAY-WO13-TRADE-PLAN-V1"
    assert WO13_POLICY_IDENTITY == "KRONOS-INTRADAY-WO13-STEP31-TRADE-CONSTRUCTION-POLICY-V1"
    assert WO13_POLICY_CHECKSUM == "c5ea70a5af50af251088785a58a39da4e824b5cc6058c11c98e880fce0fb0e6b"
    assert tuple(item.value for item in Wo13GeometryAvailability) == (
        "GEOMETRY_COMPLETE", "GEOMETRY_PARTIAL", "GEOMETRY_UNAVAILABLE"
    )
    assert tuple(item.value for item in Wo13FieldAvailability) == (
        "AVAILABLE", "UNAVAILABLE", "AMBIGUOUS", "INCOMPLETE"
    )
    assert "RR_UNFAVOURABLE" not in {item.value for item in Wo13WarningCode}
    assert Wo13PolicyBinding().model_rr_gate == "NONE"
    with pytest.raises(Wo13ContractError, match="WO13_POLICY_BINDING_INVALID"):
        Wo13PolicyBinding(policy_checksum="0" * 64)


@pytest.mark.parametrize(
    ("direction", "classification"),
    (
        (SemanticDirection.LONG, Kr370AnalyticalClassification.BUY_NOW),
        (SemanticDirection.SHORT, Kr370AnalyticalClassification.SELL_NOW),
    ),
)
def test_exact_current_buy_and_sell_now_are_admitted_deterministically(
    tmp_path, direction, classification
) -> None:  # type: ignore[no-untyped-def]
    handoff = _handoff(tmp_path, direction=direction)
    assert handoff.wo12_classification is classification
    assert handoff.inherited_direction is direction
    assert handoff == _handoff(tmp_path, direction=direction)


@pytest.mark.parametrize("satisfied", (3, 2, 1, 0))
def test_every_non_now_classification_is_rejected(tmp_path, satisfied: int) -> None:
    values = _artifacts(tmp_path, satisfied=satisfied)
    with pytest.raises(Wo13HandoffRejected) as failure:
        create_wo13_step31_handoff(
            current_pointer=values[0], request=values[1], evidence=values[2],
            result=values[3], eligibility=values[4], wo10_snapshot=values[5],
            setup_evidence=values[6],
        )
    assert failure.value.failure is Wo13HandoffFailure.WO12_NOT_NOW


def test_exact_pointer_currentness_rejects_a_superseded_now_result(tmp_path) -> None:
    old = _artifacts(tmp_path / "old", minute=20)
    current = _artifacts(tmp_path / "current", minute=21)
    with pytest.raises(Wo13HandoffRejected) as failure:
        create_wo13_step31_handoff(
            current_pointer=current[0], request=old[1], evidence=old[2],
            result=old[3], eligibility=old[4], wo10_snapshot=old[5],
            setup_evidence=old[6],
        )
    assert failure.value.failure is Wo13HandoffFailure.WO12_SUPERSEDED


def test_subject_direction_family_boundary_and_instrument_are_exact_bound(tmp_path) -> None:
    values = _artifacts(tmp_path)
    wrong_direction = _snapshot_direction(values[5], SemanticDirection.SHORT)
    with pytest.raises(Wo13HandoffRejected) as failure:
        create_wo13_step31_handoff(
            current_pointer=values[0], request=values[1], evidence=values[2],
            result=values[3], eligibility=values[4], wo10_snapshot=wrong_direction,
            setup_evidence=values[6],
        )
    assert failure.value.failure is Wo13HandoffFailure.DIRECTION_MISMATCH

    changed = {
        item.name: getattr(values[5], item.name)
        for item in fields(Wo10EvidenceSnapshot)
        if item.name not in {"snapshot_identity", "snapshot_integrity"}
    }
    changed["source_mapping_identity"] = "FOREIGN-INSTRUMENT-MAPPING"
    foreign = Wo10EvidenceSnapshot(
        snapshot_identity=_wo10_identity("INTRADAY-WO10-EVIDENCE-SNAPSHOT-", changed),
        snapshot_integrity=_wo10_identity("INTEGRITY-INTRADAY-WO10-EVIDENCE-SNAPSHOT-", changed),
        **changed,
    )
    with pytest.raises(Wo13HandoffRejected) as failure:
        create_wo13_step31_handoff(
            current_pointer=values[0], request=values[1], evidence=values[2],
            result=values[3], eligibility=values[4], wo10_snapshot=foreign,
            setup_evidence=values[6],
        )
    assert failure.value.failure is Wo13HandoffFailure.SOURCE_EVIDENCE_INVALID


def test_setup_family_is_inherited_from_governed_origin_and_changes_identity(tmp_path) -> None:
    pullback = _handoff(
        tmp_path / "pullback", setup=Wo12SetupFamily.PULLBACK_CONTINUATION
    )
    breakout = _handoff(
        tmp_path / "breakout", setup=Wo12SetupFamily.RANGE_BREAKOUT
    )
    assert pullback.setup_family is Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION
    assert breakout.setup_family is Wo13SetupFamily.INTRADAY_RANGE_BREAKOUT
    assert pullback.handoff_identity != breakout.handoff_identity


def test_mcx_handoff_preserves_exact_active_contract_economics_and_roll(tmp_path) -> None:
    values = _mcx_artifacts(tmp_path)
    handoff = create_wo13_step31_handoff(
        current_pointer=values[0], request=values[1], evidence=values[2],
        result=values[3], eligibility=values[4], wo10_snapshot=values[5],
        setup_evidence=values[6], mcx_evidence=values[7],
    )
    active = values[7].active_derivative_binding
    assert active is not None
    assert handoff.actual_contract_identity == active.active_binding.derivative_contract_id
    assert handoff.provider_symbol == active.provider_symbol
    assert handoff.active_binding_identity == active.binding_identity
    assert handoff.active_binding_integrity == active.integrity_identity
    assert handoff.contract_expiry == active.contract_expiry
    assert handoff.tick_size == str(active.tick_size)
    assert handoff.lot_size == active.lot_size
    assert handoff.roll_lineage_identity == values[7].structural_location.roll_lineage_identity


def test_mcx_wrong_contract_or_roll_lineage_fails_closed(tmp_path) -> None:
    values = _mcx_artifacts(tmp_path)
    missing_active = _reload_mcx(values[7], active_derivative_binding=None)
    with pytest.raises(Wo13HandoffRejected) as failure:
        create_wo13_step31_handoff(
            current_pointer=values[0], request=values[1], evidence=values[2],
            result=values[3], eligibility=values[4], wo10_snapshot=values[5],
            setup_evidence=values[6], mcx_evidence=missing_active,
        )
    assert failure.value.failure is Wo13HandoffFailure.MCX_ACTIVE_CONTRACT_MISMATCH

    active = values[7].active_derivative_binding
    assert active is not None
    wrong_location = _mcx_location(
        values[3].analysis_boundary, active, "MCX-ROLL-HISTORY:FOREIGN"
    )
    wrong_roll = _reload_mcx(values[7], structural_location=wrong_location)
    with pytest.raises(Wo13HandoffRejected) as failure:
        create_wo13_step31_handoff(
            current_pointer=values[0], request=values[1], evidence=values[2],
            result=values[3], eligibility=values[4], wo10_snapshot=values[5],
            setup_evidence=values[6], mcx_evidence=wrong_roll,
        )
    assert failure.value.failure is Wo13HandoffFailure.MCX_ROLL_LINEAGE_MISMATCH


def test_trade_plan_contract_preserves_separate_fields_and_no_geometry_defaults(tmp_path) -> None:
    handoff = _handoff(tmp_path)
    request = create_wo13_construction_request(
        handoff=handoff,
        sponsor_operation_identity="SPONSOR-WO13-SLICE1-CONTRACT",
        requested_at=REQUESTED_AT + timedelta(minutes=30),
        provenance=("ADR-0022",),
    )
    plan = _empty_plan(request)
    inventory = {item.name for item in fields(type(plan))}
    assert plan.geometry_availability is Wo13GeometryAvailability.GEOMETRY_UNAVAILABLE
    assert plan.entry_reference is plan.stop is plan.canonical_target is None
    assert plan.risk_distance is plan.reward_distance is plan.model_rr is None
    assert "entry_zone" not in inventory
    assert "target_2" not in inventory
    assert {"stop", "thesis_invalidation_reference", "thesis_invalidation_event"} <= inventory
    assert "canonical_target" in inventory
    assert not any((plan.risk_authority, plan.entry_timing_authority,
                    plan.sponsor_decision_authority, plan.execution_authority,
                    plan.broker_authority))
    assert plan == _empty_plan(request)


def test_geometry_availability_cannot_be_declared_complete_without_fields(tmp_path) -> None:
    request = create_wo13_construction_request(
        handoff=_handoff(tmp_path), sponsor_operation_identity="SPONSOR-WO13-INVARIANT",
        requested_at=REQUESTED_AT + timedelta(minutes=31), provenance=("ADR-0022",),
    )
    with pytest.raises(Wo13ContractError, match="WO13_TRADE_PLAN_INVALID"):
        create_wo13_trade_plan_contract(
            request=request, entry_reference=None, entry_condition=None, stop=None,
            stop_structural_basis=None, thesis_invalidation_reference=None,
            thesis_invalidation_event=None, setup_native_target=None,
            canonical_target=None, target_structural_basis=None,
            constraining_objective=None, risk_distance=None, reward_distance=None,
            model_rr=None,
            geometry_availability=Wo13GeometryAvailability.GEOMETRY_COMPLETE,
            field_availability=_unavailable_fields(), warnings=(), supersession=None,
            provenance=("ADR-0022",),
        )


def test_warning_provenance_and_supersession_contracts_have_no_decision_authority(tmp_path) -> None:
    request = create_wo13_construction_request(
        handoff=_handoff(tmp_path), sponsor_operation_identity="SPONSOR-WO13-PROVENANCE",
        requested_at=REQUESTED_AT + timedelta(minutes=32), provenance=("ADR-0022",),
    )
    plan = _empty_plan(request)
    started = create_wo13_operation_provenance(
        request=request, stage=Wo13OperationStage.REQUEST_VALIDATION,
        outcome=Wo13OperationOutcome.STARTED, started_at=request.requested_at,
        provenance=("WO13-SLICE1",),
    )
    reference = create_wo13_supersession_reference(
        predecessor_trade_plan_identity="WO13-PLAN-PREVIOUS",
        predecessor_trade_plan_integrity="INTEGRITY-WO13-PLAN-PREVIOUS",
        source_wo12_request_identity=request.handoff.wo12_request_identity,
        source_wo12_result_identity=request.handoff.wo12_result_identity,
        reason=Wo13SupersessionReason.NEW_EXACT_ELIGIBLE_WO12_CYCLE,
        supersession_boundary=request.handoff.analysis_boundary,
    )
    lineage = create_wo13_supersession_lineage(
        predecessor_trade_plan_identity=reference.predecessor_trade_plan_identity,
        predecessor_trade_plan_integrity=reference.predecessor_trade_plan_integrity,
        successor_trade_plan_identity=plan.trade_plan_identity,
        successor_trade_plan_integrity=plan.trade_plan_integrity,
        source_wo12_request_identity=reference.source_wo12_request_identity,
        source_wo12_result_identity=reference.source_wo12_result_identity,
        reason=reference.reason,
        supersession_boundary=reference.supersession_boundary,
    )
    assert started.stage is Wo13OperationStage.REQUEST_VALIDATION
    assert lineage.predecessor_trade_plan_identity != lineage.successor_trade_plan_identity
    assert tuple(item.value for item in Wo13WarningCode) == (
        "NON_POSITIVE_RISK", "NON_POSITIVE_REWARD",
        "INVALID_DIRECTIONAL_GEOMETRY", "NON_FINITE_VALUE",
        "TICK_NORMALIZATION_FAILURE",
    )


def test_contract_surface_has_no_index_option_or_slice2_geometry_engine() -> None:
    names = {item.name for item in fields(__import__(
        "kronos.intraday.wo13", fromlist=["Wo13TradePlan"]
    ).Wo13TradePlan)}
    assert names.isdisjoint({
        "option_strike", "option_expiry", "option_premium", "option_type",
        "entry_lower_bound", "entry_upper_bound", "range_width",
    })
