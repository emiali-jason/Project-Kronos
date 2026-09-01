from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.application.intraday_wo11 import IntradayWo11Application
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo10 import (
    Wo10OperationOutcome,
    Wo10OperationStage,
    create_current_wo10_pointer,
    create_wo10_batch_result,
    create_wo10_operation_provenance,
    create_wo10_reconciliation_result,
)
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
    create_current_wo12_pointer_v2,
    create_wo12_evidence_v2,
    create_wo12_request_v2,
    create_wo12_result_v2,
    create_wo13_eligibility_v2,
)
from kronos.intraday.wo13_handoff import create_wo13_step31_handoff
from kronos.intraday.wo13_pullback import construct_wo13_pullback_geometry
from kronos.intraday.wo14 import (
    WO14_AUTHORITY,
    WO14_CONTRACT_IDENTITY,
    WO14_CONTRACT_VERSION,
    Wo14AlertSeverity,
    Wo14ContractError,
    Wo14FieldAvailability,
    Wo14ObservationState,
    Wo14QuantitySemantics,
    Wo14RiskField,
    Wo14UnitSemantics,
    bind_wo13_trade_plan,
    calculate_wo14_observation,
    create_wo14_capital_reference,
    create_wo14_instrument_economics,
    create_wo14_margin_context,
    create_wo14_observation_request,
    create_wo14_portfolio_snapshot,
    create_wo14_reference_quantity,
)

from .test_wo13_application import _execute
from .test_wo10_contracts import REQUESTED_AT
from .test_wo10_index import _fixture as _index_fixture
from .test_wo13_contracts import _criterion
from .test_wo13_pullback import (
    _evidence,
    _fact,
    _facts,
    _mcx_handoff,
)
from .test_wo13_targets import _pullback
from kronos.validation.kr370 import Kr370CriterionState


def _equity(tmp_path, direction=SemanticDirection.LONG):  # type: ignore[no-untyped-def]
    _, _, executed = _execute(tmp_path, _pullback(tmp_path, direction))
    return executed.trade_plan


def _mcx(tmp_path):  # type: ignore[no-untyped-def]
    handoff = _mcx_handoff(tmp_path)
    facts = tuple(
        _fact(
            handoff,
            str(item.price),
            item.structural_role,
            source=item.source_evidence_identity,
            session="MCX-SESSION-2026-08-31",
        )
        for item in _facts(handoff)
    )
    geometry = construct_wo13_pullback_geometry(
        _evidence(
            handoff,
            qualification=(facts[0],),
            pullback=(facts[1],),
            impulse=(facts[2],),
            session="MCX-SESSION-2026-08-31",
        )
    )
    _, _, executed = _execute(tmp_path, geometry)
    return executed.trade_plan, handoff


def _index(tmp_path):  # type: ignore[no-untyped-def]
    decision, wo10_request, snapshot, _, _ = _index_fixture()
    assert decision is not None
    result = create_wo10_reconciliation_result(
        request=wo10_request,
        evidence=snapshot,
        state=decision.state,
        reasons=decision.reasons,
        provenance=("WO14-INDEX-TEST",),
    )
    batch = create_wo10_batch_result(
        request=wo10_request,
        results=(result,),
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        provenance=("WO14-INDEX-TEST",),
    )
    operation = create_wo10_operation_provenance(
        request=wo10_request,
        stage=Wo10OperationStage.BATCH_PUBLICATION,
        outcome=Wo10OperationOutcome.COMPLETED,
        started_at=REQUESTED_AT,
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        results=(result,),
        batch=batch,
        provenance=("WO14-INDEX-TEST",),
    )
    wo10 = Wo10Store((tmp_path / "wo10-index").resolve())
    for retain, value in (
        (wo10.retain_policy, wo10_request.policy),
        (wo10.retain_request, wo10_request),
        (wo10.retain_evidence_snapshot, snapshot),
        (wo10.retain_result, result),
        (wo10.retain_batch, batch),
        (wo10.retain_operation, operation),
    ):
        retain(value)
    wo10.publish_current(create_current_wo10_pointer(wo10_request, batch))
    source = create_wo11_source_batch_binding(
        batch=batch, request=wo10_request, operation=operation
    )
    wo11 = Wo11Store((tmp_path / "wo11-index").resolve())
    published = IntradayWo11Application(wo10_store=wo10, store=wo11).execute(
        create_wo11_publication_request(
            source_batches=(source,),
            requested_at=REQUESTED_AT + timedelta(minutes=2),
            sponsor_operation_identity="SPONSOR-WO14-INDEX-WO11",
            provenance=("WO14-INDEX-TEST",),
        )
    )
    member = published.members[0]
    handoff11 = create_wo11_handoff_reference(published.publication, member)
    handoff12 = create_wo12_handoff(
        publication=published.publication,
        member=member,
        wo11_handoff=handoff11,
    )
    request12 = create_wo12_request_v2(
        handoff=handoff12,
        requested_at=REQUESTED_AT + timedelta(minutes=20),
        sponsor_operation_identity="SPONSOR-WO14-INDEX-WO12",
        provenance=("ADR-0020",),
    )
    criteria = tuple(
        _criterion(item, Kr370CriterionState.SATISFIED)
        for item in Wo12CriterionIdentityV2
    )
    evidence12 = create_wo12_evidence_v2(
        request=request12,
        criteria=criteria,
        exact_binding_valid=True,
        governing_15m_structure_failed=False,
        authoritative_directional_conflict=False,
    )
    result12 = create_wo12_result_v2(
        request=request12,
        evidence=evidence12,
        created_at=request12.requested_at,
        provenance=("ADR-0020",),
    )
    eligibility = create_wo13_eligibility_v2(
        result12, provenance=("ADR-0022",)
    )
    pointer = create_current_wo12_pointer_v2(
        request12, result12, eligibility
    )
    setup = derive_wo12_structural_origin(
        canonical_subject_identity=handoff12.canonical_subject_identity,
        market_family=handoff12.market_family,
        setup_family=Wo12SetupFamily.PULLBACK_CONTINUATION,
        inherited_direction=handoff12.inherited_direction,
        analysis_boundary=handoff12.analysis_boundary,
        evidence=None,
    )
    handoff13 = create_wo13_step31_handoff(
        current_pointer=pointer,
        request=request12,
        evidence=evidence12,
        result=result12,
        eligibility=eligibility,
        wo10_snapshot=snapshot,
        setup_evidence=setup,
    )
    geometry = construct_wo13_pullback_geometry(_evidence(handoff13))
    _, _, executed = _execute(tmp_path, geometry)
    return executed.trade_plan


def _request(plan, **changes):  # type: ignore[no-untyped-def]
    values = {
        "plan": plan,
        "sponsor_operation_identity": "SPONSOR-WO14-TEST",
        "requested_at": plan.analysis_boundary,
        "evaluation_boundary": plan.analysis_boundary,
        "provenance": ("ADR-0023", "WO14-TEST"),
    }
    values.update(changes)
    return create_wo14_observation_request(**values)


def _quantity(plan, amount="500", unit=Wo14UnitSemantics.SHARES):  # type: ignore[no-untyped-def]
    return create_wo14_reference_quantity(
        quantity=Decimal(amount),
        semantics=Wo14QuantitySemantics.SPONSOR_REFERENCE_QUANTITY,
        unit_semantics=unit,
        source_identity="SPONSOR-REFERENCE-QUANTITY-V1",
        observed_at=plan.analysis_boundary,
    )


def test_contract_identity_states_and_authority_are_frozen(tmp_path) -> None:
    plan = _equity(tmp_path)
    request = _request(plan)
    observation = calculate_wo14_observation(request, plan)

    assert WO14_CONTRACT_IDENTITY == "KRONOS-INTRADAY-DOMAIN-007-RISK-OBSERVATION-V1"
    assert WO14_CONTRACT_VERSION == "1.0.0"
    assert WO14_AUTHORITY == "RISK_OBSERVATION_ONLY"
    assert tuple(item.value for item in Wo14ObservationState) == (
        "RISK_OBSERVED", "RISK_ALERT", "RISK_UNAVAILABLE"
    )
    assert observation.alert_severity is Wo14AlertSeverity.UNCLASSIFIED
    assert observation.policy.alert_predicate == "NONE"
    assert not any((
        observation.trade_permission_authority,
        observation.wo15_blocking_authority,
        observation.final_quantity_authority,
        observation.sponsor_decision_authority,
        observation.execution_authority,
        observation.broker_authority,
    ))


@pytest.mark.parametrize(
    ("direction", "expected"),
    ((SemanticDirection.LONG, Decimal("4")),
     (SemanticDirection.SHORT, Decimal("4"))),
)
def test_equity_long_short_reference_quantity_arithmetic(
    tmp_path, direction, expected
) -> None:  # type: ignore[no-untyped-def]
    plan = _equity(tmp_path, direction)
    quantity = _quantity(plan)
    observation = calculate_wo14_observation(
        _request(plan, reference_quantity=quantity), plan
    )

    assert observation.state is Wo14ObservationState.RISK_OBSERVED
    assert observation.structural_risk_per_price_unit == expected
    assert observation.risk_per_share == expected
    assert observation.monetary_risk_per_tradable_unit == expected
    assert observation.loss_at_stop == expected * Decimal("500")
    assert observation.reference_notional == plan.entry_reference * Decimal("500")


def test_equity_without_quantity_preserves_independent_facts(tmp_path) -> None:
    plan = _equity(tmp_path)
    observation = calculate_wo14_observation(_request(plan), plan)
    availability = {item.field: item for item in observation.field_availability}

    assert observation.state is Wo14ObservationState.RISK_OBSERVED
    assert observation.risk_per_share == Decimal("4")
    assert observation.reference_quantity is None
    assert observation.loss_at_stop is None
    assert observation.reference_notional is None
    assert availability[Wo14RiskField.LOSS_AT_STOP].availability is Wo14FieldAvailability.UNAVAILABLE


def test_index_underlying_point_risk_is_observed_without_vehicle_selection(tmp_path) -> None:
    plan = _index(tmp_path)
    observation = calculate_wo14_observation(_request(plan), plan)

    assert observation.underlying_point_risk == Decimal("4")
    assert observation.monetary_risk_per_tradable_unit is None
    assert observation.state is Wo14ObservationState.RISK_UNAVAILABLE
    assert "INDEX_EXECUTION_VEHICLE_UNAVAILABLE" in observation.unavailable_reasons
    assert observation.reference_quantity is None


def test_poor_model_rr_and_large_reference_loss_never_emit_alert(tmp_path) -> None:
    plan = _equity(tmp_path)
    observation = calculate_wo14_observation(
        _request(plan, reference_quantity=_quantity(plan, "1000000")), plan
    )
    assert observation.loss_at_stop == Decimal("4000000")
    assert observation.state is Wo14ObservationState.RISK_OBSERVED
    assert observation.alert_severity is Wo14AlertSeverity.UNCLASSIFIED


def test_capital_portfolio_and_margin_facts_are_arithmetic_not_thresholds(tmp_path) -> None:
    plan = _equity(tmp_path)
    quantity = _quantity(plan, "500")
    capital = create_wo14_capital_reference(
        amount=Decimal("100000"), currency="INR",
        source_identity="SPONSOR-CAPITAL-SNAPSHOT",
        observed_at=plan.analysis_boundary,
    )
    portfolio = create_wo14_portfolio_snapshot(
        existing_open_risk=Decimal("3000"), currency="INR",
        source_identity="PORTFOLIO-RISK-SNAPSHOT",
        observed_at=plan.analysis_boundary,
    )
    margin = create_wo14_margin_context(
        margin_amount=Decimal("25000"), currency="INR",
        source_identity="MARGIN-CONTEXT-SNAPSHOT",
        observed_at=plan.analysis_boundary,
    )
    observation = calculate_wo14_observation(
        _request(
            plan,
            reference_quantity=quantity,
            capital_reference=capital,
            portfolio_snapshot=portfolio,
            margin_context=margin,
        ),
        plan,
    )

    assert observation.loss_at_stop == Decimal("2000")
    assert observation.capital_at_risk_fraction == Decimal("0.02")
    assert observation.existing_open_risk == Decimal("3000")
    assert observation.aggregate_open_risk_after_reference == Decimal("5000")
    assert observation.margin_context == Decimal("25000")
    assert observation.state is Wo14ObservationState.RISK_OBSERVED


def test_currency_mismatch_preserves_inputs_but_not_false_aggregation(tmp_path) -> None:
    plan = _equity(tmp_path)
    capital = create_wo14_capital_reference(
        amount=Decimal("100000"), currency="USD",
        source_identity="FOREIGN-CAPITAL-SNAPSHOT",
        observed_at=plan.analysis_boundary,
    )
    portfolio = create_wo14_portfolio_snapshot(
        existing_open_risk=Decimal("3000"), currency="USD",
        source_identity="FOREIGN-PORTFOLIO-SNAPSHOT",
        observed_at=plan.analysis_boundary,
    )
    observation = calculate_wo14_observation(
        _request(
            plan,
            reference_quantity=_quantity(plan),
            capital_reference=capital,
            portfolio_snapshot=portfolio,
        ),
        plan,
    )

    assert observation.capital_reference == Decimal("100000")
    assert observation.existing_open_risk == Decimal("3000")
    assert observation.capital_at_risk_fraction is None
    assert observation.aggregate_open_risk_after_reference is None
    assert "CAPITAL_CURRENCY_MISMATCH" in observation.unavailable_reasons
    assert "PORTFOLIO_CURRENCY_MISMATCH" in observation.unavailable_reasons


def test_exact_mcx_contract_economics_and_lot_arithmetic(tmp_path) -> None:
    plan, handoff = _mcx(tmp_path)
    economics = create_wo14_instrument_economics(
        economics_version="MCX-ECONOMICS-TEST-V1",
        canonical_subject_identity=plan.canonical_subject_identity,
        instrument_identity=plan.instrument_identity,
        actual_contract_identity=plan.actual_contract_identity,
        roll_lineage_identity=handoff.roll_lineage_identity,
        lot_size=handoff.lot_size,
        contract_multiplier=Decimal("1"),
        tick_size=Decimal(handoff.tick_size),
        tick_value=None,
        observed_at=plan.analysis_boundary,
        source_identities=("DOMAIN-001-MCX-ECONOMICS",),
        source_integrities=("INTEGRITY-DOMAIN-001-MCX-ECONOMICS",),
    )
    quantity = _quantity(plan, "2", Wo14UnitSemantics.LOTS)
    observation = calculate_wo14_observation(
        _request(
            plan,
            instrument_economics=economics,
            reference_quantity=quantity,
        ),
        plan,
    )
    expected = Decimal("4") * Decimal(handoff.lot_size)

    assert observation.state is Wo14ObservationState.RISK_OBSERVED
    assert observation.monetary_risk_per_tradable_unit == expected
    assert observation.loss_at_stop == expected * 2
    assert observation.plan_binding.actual_contract_identity == plan.actual_contract_identity


def test_mcx_missing_or_wrong_contract_economics_fails_closed(tmp_path) -> None:
    plan, handoff = _mcx(tmp_path)
    missing = calculate_wo14_observation(_request(plan), plan)
    assert missing.state is Wo14ObservationState.RISK_UNAVAILABLE
    assert missing.structural_risk_per_price_unit == Decimal("4")
    assert "MCX_INSTRUMENT_ECONOMICS_UNAVAILABLE" in missing.unavailable_reasons

    economics = create_wo14_instrument_economics(
        economics_version="MCX-ECONOMICS-TEST-V1",
        canonical_subject_identity=plan.canonical_subject_identity,
        instrument_identity=plan.instrument_identity,
        actual_contract_identity="MCX-CONTRACT-FOREIGN",
        roll_lineage_identity=handoff.roll_lineage_identity,
        lot_size=handoff.lot_size,
        contract_multiplier=Decimal("1"),
        tick_size=Decimal(handoff.tick_size),
        tick_value=None,
        observed_at=plan.analysis_boundary,
        source_identities=("DOMAIN-001-MCX-ECONOMICS",),
        source_integrities=("INTEGRITY-DOMAIN-001-MCX-ECONOMICS",),
    )
    wrong = calculate_wo14_observation(
        _request(plan, instrument_economics=economics), plan
    )
    assert wrong.state is Wo14ObservationState.RISK_UNAVAILABLE
    assert wrong.monetary_risk_per_tradable_unit is None
    assert "MCX_INSTRUMENT_ECONOMICS_MISMATCH" in wrong.unavailable_reasons


def test_changed_plan_binding_and_invalid_quantity_never_gain_authority(tmp_path) -> None:
    plan = _equity(tmp_path)
    request = _request(plan)
    with pytest.raises(Wo14ContractError):
        replace(request, plan_binding=replace(
            bind_wo13_trade_plan(plan), trade_plan_integrity="FOREIGN"
        ))
    with pytest.raises(Wo14ContractError, match="WO14_REFERENCE_QUANTITY_INVALID"):
        create_wo14_reference_quantity(
            quantity=Decimal("1.5"),
            semantics=Wo14QuantitySemantics.SPONSOR_REFERENCE_QUANTITY,
            unit_semantics=Wo14UnitSemantics.SHARES,
            source_identity="REFERENCE",
            observed_at=plan.analysis_boundary,
        )


def test_contract_exposes_alert_state_but_normal_calculator_does_not(tmp_path) -> None:
    plan = _equity(tmp_path)
    assert Wo14ObservationState("RISK_ALERT") is Wo14ObservationState.RISK_ALERT
    assert calculate_wo14_observation(_request(plan), plan).state is not Wo14ObservationState.RISK_ALERT
