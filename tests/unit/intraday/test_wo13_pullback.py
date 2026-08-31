from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import inspect

import pytest

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13 import (
    WO13_POLICY_CHECKSUM,
    Wo13FieldAvailability,
    Wo13GeometryAvailability,
    Wo13GeometryField,
    Wo13WarningCode,
)
from kronos.intraday.wo13_geometry import (
    Wo13ForwardTargetState,
    Wo13GeometryRejected,
    Wo13PriceAuthority,
    Wo13StructuralRole,
    create_wo13_structural_price_fact,
)
from kronos.intraday.wo13_handoff import (
    Wo13SetupFamily,
    create_wo13_step31_handoff,
)
from kronos.intraday.wo13_pullback import (
    WO13_PULLBACK_ENTRY_CONDITION_IDENTITY,
    WO13_PULLBACK_EVIDENCE_IDENTITY,
    WO13_PULLBACK_FACT_REFERENCE_IDENTITY,
    WO13_PULLBACK_GEOMETRY_IDENTITY,
    Wo13PullbackEntryConditionCode,
    Wo13PullbackFailure,
    Wo13PullbackInvalidationCode,
    Wo13PullbackRejected,
    construct_wo13_pullback_geometry,
    create_wo13_pullback_fact_reference,
    create_wo13_pullback_geometry_evidence,
)
from kronos.intraday.wo12_k5_foundation import Wo12SetupFamily

from .test_wo13_contracts import _handoff, _mcx_artifacts


SESSION = "NSE-SESSION-2026-08-31"


def _authority(family: IntradayMarketFamily) -> Wo13PriceAuthority:
    return {
        IntradayMarketFamily.NSE_EQUITY: Wo13PriceAuthority.NSE_EQUITY_UNDERLYING,
        IntradayMarketFamily.NSE_INDEX: Wo13PriceAuthority.NSE_INDEX_UNDERLYING,
        IntradayMarketFamily.MCX: Wo13PriceAuthority.MCX_ACTIVE_CONTRACT,
    }[family]


def _fact(
    handoff,
    price: str,
    role: Wo13StructuralRole,
    *,
    source: str | None = None,
    subject: str | None = None,
    family: IntradayMarketFamily | None = None,
    boundary=None,
    timeframe: IntradayTimeframe = IntradayTimeframe.FIFTEEN_MINUTES,
    structure: str | None = None,
    session: str = SESSION,
    instrument: str | None = None,
    contract: str | None = None,
    roll: str | None = None,
):  # type: ignore[no-untyped-def]
    family = family or handoff.market_family
    source = source or f"SOURCE:{role.value}:{price}"
    return create_wo13_structural_price_fact(
        canonical_subject_identity=subject or handoff.canonical_subject_identity,
        market_family=family,
        timeframe=timeframe,
        price=price,
        structural_role=role,
        price_authority=_authority(family),
        structure_identity=structure or handoff.setup_evidence_identity,
        source_evidence_identity=source,
        source_evidence_integrity=f"INTEGRITY:{source}",
        analysis_boundary=boundary or handoff.analysis_boundary,
        instrument_identity=instrument or handoff.instrument_identity,
        actual_contract_identity=(
            contract if contract is not None else handoff.actual_contract_identity
        ),
        roll_lineage_identity=(
            roll if roll is not None else handoff.roll_lineage_identity
        ),
        market_session_identity=session,
    )


def _facts(handoff):  # type: ignore[no-untyped-def]
    if handoff.inherited_direction is SemanticDirection.LONG:
        return (
            _fact(handoff, "100", Wo13StructuralRole.QUALIFICATION_CANDLE_HIGH),
            _fact(handoff, "96", Wo13StructuralRole.PULLBACK_STRUCTURAL_LOW),
            _fact(handoff, "112", Wo13StructuralRole.PRIOR_IMPULSE_HIGH),
        )
    return (
        _fact(handoff, "100", Wo13StructuralRole.QUALIFICATION_CANDLE_LOW),
        _fact(handoff, "104", Wo13StructuralRole.PULLBACK_STRUCTURAL_HIGH),
        _fact(handoff, "88", Wo13StructuralRole.PRIOR_IMPULSE_LOW),
    )


def _evidence(
    handoff,
    *,
    qualification=None,
    pullback=None,
    impulse=None,
    qualification_references=None,
    pullback_references=None,
    impulse_references=None,
    session: str = SESSION,
):  # type: ignore[no-untyped-def]
    defaults = _facts(handoff)
    qualification = (defaults[0],) if qualification is None else tuple(qualification)
    pullback = (defaults[1],) if pullback is None else tuple(pullback)
    impulse = (defaults[2],) if impulse is None else tuple(impulse)
    qualification_references = (
        tuple(create_wo13_pullback_fact_reference(item) for item in qualification)
        if qualification_references is None
        else tuple(qualification_references)
    )
    pullback_references = (
        tuple(create_wo13_pullback_fact_reference(item) for item in pullback)
        if pullback_references is None
        else tuple(pullback_references)
    )
    impulse_references = (
        tuple(create_wo13_pullback_fact_reference(item) for item in impulse)
        if impulse_references is None
        else tuple(impulse_references)
    )
    return create_wo13_pullback_geometry_evidence(
        handoff=handoff,
        market_session_identity=session,
        qualification_references=qualification_references,
        qualification_candles=qualification,
        pullback_references=pullback_references,
        governing_pullback_structures=pullback,
        prior_impulse_references=impulse_references,
        prior_impulse_extremes=impulse,
    )


def _missing(component, handoff):  # type: ignore[no-untyped-def]
    facts = _facts(handoff)
    reference = create_wo13_pullback_fact_reference(facts[component])
    kwargs = {
        "qualification": (facts[0],),
        "pullback": (facts[1],),
        "impulse": (facts[2],),
    }
    keys = ("qualification", "pullback", "impulse")
    kwargs[keys[component]] = ()
    kwargs[f"{keys[component]}_references"] = (reference,)
    return _evidence(handoff, **kwargs)


def _mcx_handoff(tmp_path):  # type: ignore[no-untyped-def]
    values = _mcx_artifacts(tmp_path)
    return create_wo13_step31_handoff(
        current_pointer=values[0],
        request=values[1],
        evidence=values[2],
        result=values[3],
        eligibility=values[4],
        wo10_snapshot=values[5],
        setup_evidence=values[6],
        mcx_evidence=values[7],
    )


def test_contract_identities_policy_and_setup_are_frozen(tmp_path) -> None:
    handoff = _handoff(tmp_path)
    evidence = _evidence(handoff)
    geometry = construct_wo13_pullback_geometry(evidence)

    assert evidence.schema_identity == WO13_PULLBACK_EVIDENCE_IDENTITY
    assert evidence.qualification_references[0].schema_identity == (
        WO13_PULLBACK_FACT_REFERENCE_IDENTITY
    )
    assert geometry.schema_identity == WO13_PULLBACK_GEOMETRY_IDENTITY
    assert geometry.entry_condition is not None
    assert geometry.entry_condition.schema_identity == WO13_PULLBACK_ENTRY_CONDITION_IDENTITY
    assert evidence.policy_checksum == WO13_POLICY_CHECKSUM
    assert handoff.setup_family is Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION


def test_long_happy_path_uses_exact_governed_15m_structure(tmp_path) -> None:
    handoff = _handoff(tmp_path, direction=SemanticDirection.LONG)
    geometry = construct_wo13_pullback_geometry(_evidence(handoff))

    assert geometry.entry_reference.selected_fact.price == Decimal("100")
    assert geometry.stop.selected_fact.price == Decimal("96")
    assert geometry.thesis_invalidation_reference.selected_fact.price == Decimal("96")
    assert geometry.setup_native_target.selected_fact.price == Decimal("112")
    assert geometry.risk_distance == Decimal("4")
    assert geometry.calculation.warnings == ()


def test_short_happy_path_is_exactly_symmetric(tmp_path) -> None:
    handoff = _handoff(tmp_path, direction=SemanticDirection.SHORT)
    geometry = construct_wo13_pullback_geometry(_evidence(handoff))

    assert geometry.entry_reference.selected_fact.price == Decimal("100")
    assert geometry.stop.selected_fact.price == Decimal("104")
    assert geometry.thesis_invalidation_reference.selected_fact.price == Decimal("104")
    assert geometry.setup_native_target.selected_fact.price == Decimal("88")
    assert geometry.risk_distance == Decimal("4")


@pytest.mark.parametrize(
    ("direction", "condition", "invalidation"),
    (
        (
            SemanticDirection.LONG,
            Wo13PullbackEntryConditionCode.DIRECTIONAL_INTERACTION_ABOVE_ENTRY_REFERENCE,
            Wo13PullbackInvalidationCode.COMPLETED_GOVERNED_15M_FAILURE_BELOW_PULLBACK_LOW,
        ),
        (
            SemanticDirection.SHORT,
            Wo13PullbackEntryConditionCode.DIRECTIONAL_INTERACTION_BELOW_ENTRY_REFERENCE,
            Wo13PullbackInvalidationCode.COMPLETED_GOVERNED_15M_FAILURE_ABOVE_PULLBACK_HIGH,
        ),
    ),
)
def test_entry_and_invalidation_semantics_do_not_evaluate_timing(
    tmp_path, direction, condition, invalidation
) -> None:  # type: ignore[no-untyped-def]
    geometry = construct_wo13_pullback_geometry(
        _evidence(_handoff(tmp_path, direction=direction))
    )

    assert geometry.entry_condition is not None
    assert geometry.entry_condition.condition_code is condition
    assert geometry.entry_condition.trigger_evaluation_performed is False
    assert geometry.entry_condition.entry_timing_authority is False
    assert geometry.thesis_invalidation_event is not None
    assert geometry.thesis_invalidation_event.event_code == invalidation.value


def test_stop_and_invalidation_are_distinct_semantic_facts(tmp_path) -> None:
    geometry = construct_wo13_pullback_geometry(_evidence(_handoff(tmp_path)))
    stop = geometry.stop.selected_fact
    invalidation = geometry.thesis_invalidation_reference.selected_fact

    assert stop is not None and invalidation is not None
    assert stop.price == invalidation.price
    assert stop.fact_identity != invalidation.fact_identity
    assert stop.structural_role is Wo13StructuralRole.STOP_REFERENCE_SOURCE
    assert invalidation.structural_role is Wo13StructuralRole.THESIS_INVALIDATION_REFERENCE


def test_no_entry_or_stop_buffer_is_applied(tmp_path) -> None:
    handoff = _handoff(tmp_path)
    qualification, pullback, impulse = _facts(handoff)
    geometry = construct_wo13_pullback_geometry(
        _evidence(handoff, qualification=(qualification,), pullback=(pullback,), impulse=(impulse,))
    )

    assert geometry.entry_reference.selected_fact.price == qualification.price
    assert geometry.stop.selected_fact.price == pullback.price
    assert geometry.calculation.tick_normalization_applied is False


def test_native_target_is_prior_impulse_not_a_measured_move(tmp_path) -> None:
    geometry = construct_wo13_pullback_geometry(_evidence(_handoff(tmp_path)))

    assert geometry.setup_native_target.selected_fact.price == Decimal("112")
    assert geometry.prior_impulse_target.selected_fact.structural_role is (
        Wo13StructuralRole.SETUP_NATIVE_TARGET
    )
    assert Decimal("116") != geometry.setup_native_target.selected_fact.price


def test_canonical_target_reward_and_rr_wait_for_slice5(tmp_path) -> None:
    geometry = construct_wo13_pullback_geometry(_evidence(_handoff(tmp_path)))

    assert geometry.canonical_target.availability is Wo13FieldAvailability.UNAVAILABLE
    assert geometry.reward_distance is None
    assert geometry.model_rr is None
    assert geometry.geometry_availability is Wo13GeometryAvailability.GEOMETRY_PARTIAL
    assert geometry.target_constraint_selection_pending is True
    assert geometry.target_constraint_selection_authority is False


@pytest.mark.parametrize(
    ("component", "field"),
    (
        (0, Wo13GeometryField.ENTRY_REFERENCE),
        (1, Wo13GeometryField.STOP),
        (2, Wo13GeometryField.SETUP_NATIVE_TARGET),
    ),
)
def test_missing_exact_pullback_component_remains_incomplete(
    tmp_path, component: int, field: Wo13GeometryField
) -> None:
    geometry = construct_wo13_pullback_geometry(
        _missing(component, _handoff(tmp_path))
    )
    resolved = {
        Wo13GeometryField.ENTRY_REFERENCE: geometry.entry_reference,
        Wo13GeometryField.STOP: geometry.stop,
        Wo13GeometryField.SETUP_NATIVE_TARGET: geometry.setup_native_target,
    }[field]

    assert resolved.selected_fact is None
    assert resolved.availability is Wo13FieldAvailability.INCOMPLETE
    assert geometry.geometry_availability is not Wo13GeometryAvailability.GEOMETRY_COMPLETE
    if component in {0, 1}:
        assert geometry.risk_distance is None


@pytest.mark.parametrize("component", (0, 1, 2))
def test_ambiguous_component_is_never_resolved_by_recency(tmp_path, component: int) -> None:
    handoff = _handoff(tmp_path)
    facts = list(_facts(handoff))
    first = facts[component]
    second = _fact(
        handoff,
        str(first.price + Decimal("1")),
        first.structural_role,
        source=f"SOURCE:AMBIGUOUS:{component}",
    )
    key = ("qualification", "pullback", "impulse")[component]
    evidence = _evidence(handoff, **{key: (first, second)})
    geometry = construct_wo13_pullback_geometry(evidence)
    resolved = (
        geometry.entry_reference,
        geometry.stop,
        geometry.setup_native_target,
    )[component]

    assert resolved.availability is Wo13FieldAvailability.AMBIGUOUS
    assert resolved.selected_fact is None


@pytest.mark.parametrize(
    ("change", "failure"),
    (
        ("subject", Wo13PullbackFailure.FACT_CONTEXT_MISMATCH),
        ("boundary", Wo13PullbackFailure.FACT_CONTEXT_MISMATCH),
        ("instrument", Wo13PullbackFailure.FACT_CONTEXT_MISMATCH),
        ("cycle", Wo13PullbackFailure.FACT_CYCLE_MISMATCH),
        ("session", Wo13PullbackFailure.FACT_SESSION_MISMATCH),
        ("timeframe", Wo13PullbackFailure.FACT_TIMEFRAME_MISMATCH),
    ),
)
def test_foreign_entry_facts_fail_the_exact_binding(
    tmp_path, change: str, failure: Wo13PullbackFailure
) -> None:
    handoff = _handoff(tmp_path)
    kwargs = {}
    if change == "subject":
        kwargs["subject"] = "NSE-EQ-TCS"
    elif change == "boundary":
        kwargs["boundary"] = handoff.analysis_boundary + timedelta(minutes=15)
    elif change == "instrument":
        kwargs["instrument"] = "INSTRUMENT:NSE:TCS"
    elif change == "cycle":
        kwargs["structure"] = "FOREIGN-WO12-CYCLE"
    elif change == "session":
        kwargs["session"] = "NSE-SESSION-2026-08-28"
    else:
        kwargs["timeframe"] = IntradayTimeframe.DAILY
    foreign = _fact(
        handoff,
        "100",
        Wo13StructuralRole.QUALIFICATION_CANDLE_HIGH,
        **kwargs,
    )

    with pytest.raises(Wo13PullbackRejected) as rejected:
        _evidence(handoff, qualification=(foreign,))
    assert rejected.value.failure is failure


def test_fact_not_named_by_exact_reference_is_rejected(tmp_path) -> None:
    handoff = _handoff(tmp_path)
    fact = _facts(handoff)[0]
    other = _fact(
        handoff,
        "101",
        Wo13StructuralRole.QUALIFICATION_CANDLE_HIGH,
        source="SOURCE:OTHER-QUALIFICATION",
    )

    with pytest.raises(Wo13PullbackRejected) as rejected:
        _evidence(
            handoff,
            qualification=(fact,),
            qualification_references=(create_wo13_pullback_fact_reference(other),),
        )
    assert rejected.value.failure is Wo13PullbackFailure.FACT_BINDING_MISMATCH


def test_range_breakout_handoff_is_rejected(tmp_path) -> None:
    handoff = _handoff(tmp_path, setup=Wo12SetupFamily.RANGE_BREAKOUT)

    with pytest.raises(Wo13PullbackRejected) as rejected:
        create_wo13_pullback_geometry_evidence(
            handoff=handoff,
            market_session_identity=SESSION,
        )
    assert rejected.value.failure is Wo13PullbackFailure.SETUP_FAMILY_UNSUPPORTED


@pytest.mark.parametrize(
    ("direction", "stop"),
    (
        (SemanticDirection.LONG, "101"),
        (SemanticDirection.SHORT, "99"),
    ),
)
def test_directionally_invalid_stop_is_preserved_and_not_repaired(
    tmp_path, direction, stop
) -> None:  # type: ignore[no-untyped-def]
    handoff = _handoff(tmp_path, direction=direction)
    facts = _facts(handoff)
    role = (
        Wo13StructuralRole.PULLBACK_STRUCTURAL_LOW
        if direction is SemanticDirection.LONG
        else Wo13StructuralRole.PULLBACK_STRUCTURAL_HIGH
    )
    changed = _fact(handoff, stop, role, source="SOURCE:INVALID-STOP")
    geometry = construct_wo13_pullback_geometry(
        _evidence(handoff, qualification=(facts[0],), pullback=(changed,), impulse=(facts[2],))
    )

    assert geometry.stop.selected_fact.price == Decimal(stop)
    assert geometry.risk_distance is None
    assert geometry.calculation.warnings == (
        Wo13WarningCode.NON_POSITIVE_RISK,
        Wo13WarningCode.INVALID_DIRECTIONAL_GEOMETRY,
    )


@pytest.mark.parametrize(
    ("direction", "target", "state"),
    (
        (SemanticDirection.LONG, "99", Wo13ForwardTargetState.BEHIND_ENTRY),
        (SemanticDirection.LONG, "100", Wo13ForwardTargetState.AT_ENTRY),
        (SemanticDirection.SHORT, "101", Wo13ForwardTargetState.BEHIND_ENTRY),
        (SemanticDirection.SHORT, "100", Wo13ForwardTargetState.AT_ENTRY),
    ),
)
def test_non_forward_prior_impulse_is_preserved_but_not_available_as_target(
    tmp_path, direction, target, state
) -> None:  # type: ignore[no-untyped-def]
    handoff = _handoff(tmp_path, direction=direction)
    facts = _facts(handoff)
    role = (
        Wo13StructuralRole.PRIOR_IMPULSE_HIGH
        if direction is SemanticDirection.LONG
        else Wo13StructuralRole.PRIOR_IMPULSE_LOW
    )
    impulse = _fact(handoff, target, role, source="SOURCE:NON-FORWARD-TARGET")
    geometry = construct_wo13_pullback_geometry(
        _evidence(handoff, qualification=(facts[0],), pullback=(facts[1],), impulse=(impulse,))
    )

    assert geometry.native_target_candidate is not None
    assert geometry.native_target_candidate.forward_state is state
    assert geometry.prior_impulse_target.selected_fact.price == Decimal(target)
    assert geometry.setup_native_target.selected_fact is None
    assert geometry.setup_native_target.availability is Wo13FieldAvailability.INCOMPLETE


def test_identity_is_deterministic_and_changes_with_material_geometry(tmp_path) -> None:
    handoff = _handoff(tmp_path)
    first = construct_wo13_pullback_geometry(_evidence(handoff))
    same = construct_wo13_pullback_geometry(_evidence(handoff))
    facts = _facts(handoff)
    changed_impulse = _fact(
        handoff,
        "113",
        Wo13StructuralRole.PRIOR_IMPULSE_HIGH,
        source="SOURCE:CHANGED-IMPULSE",
    )
    changed = construct_wo13_pullback_geometry(
        _evidence(
            handoff,
            qualification=(facts[0],),
            pullback=(facts[1],),
            impulse=(changed_impulse,),
        )
    )

    assert first == same
    assert first.geometry_identity == same.geometry_identity
    assert first.geometry_identity != changed.geometry_identity
    assert first.evidence.evidence_identity != changed.evidence.evidence_identity


def test_evidence_and_geometry_corruption_fail_closed(tmp_path) -> None:
    evidence = _evidence(_handoff(tmp_path))
    geometry = construct_wo13_pullback_geometry(evidence)

    with pytest.raises(Wo13PullbackRejected):
        replace(evidence, evidence_integrity="CORRUPT")
    with pytest.raises(Wo13PullbackRejected):
        replace(geometry, geometry_integrity="CORRUPT")


def test_mcx_geometry_is_exact_active_contract_and_roll_local(tmp_path) -> None:
    handoff = _mcx_handoff(tmp_path)
    session = "MCX-SESSION-2026-08-31"
    facts = _facts(handoff)
    facts = tuple(
        _fact(
            handoff,
            str(item.price),
            item.structural_role,
            source=item.source_evidence_identity,
            session=session,
        )
        for item in facts
    )
    geometry = construct_wo13_pullback_geometry(
        _evidence(
            handoff,
            qualification=(facts[0],),
            pullback=(facts[1],),
            impulse=(facts[2],),
            session=session,
        )
    )

    for field in (
        geometry.entry_reference,
        geometry.stop,
        geometry.setup_native_target,
    ):
        assert field.selected_fact.actual_contract_identity == handoff.actual_contract_identity
        assert field.selected_fact.roll_lineage_identity == handoff.roll_lineage_identity


@pytest.mark.parametrize("change", ("contract", "roll"))
def test_mcx_cross_contract_or_cross_roll_fact_is_rejected(tmp_path, change: str) -> None:
    handoff = _mcx_handoff(tmp_path)
    kwargs = {change: f"FOREIGN-{change.upper()}"}
    fact = _fact(
        handoff,
        "100",
        Wo13StructuralRole.QUALIFICATION_CANDLE_HIGH,
        session="MCX-SESSION-2026-08-31",
        **kwargs,
    )

    with pytest.raises(Wo13PullbackRejected) as rejected:
        _evidence(
            handoff,
            qualification=(fact,),
            session="MCX-SESSION-2026-08-31",
        )
    assert rejected.value.failure is Wo13PullbackFailure.FACT_CONTEXT_MISMATCH


def test_context_prices_have_no_independent_geometry_authority(tmp_path) -> None:
    handoff = _handoff(tmp_path)
    for authority in (
        Wo13PriceAuthority.SMA_CONTEXT,
        Wo13PriceAuthority.COMEX_REFERENCE,
        Wo13PriceAuthority.NYMEX_REFERENCE,
        Wo13PriceAuthority.USDINR_REFERENCE,
        Wo13PriceAuthority.OPTION_PREMIUM,
    ):
        with pytest.raises(Wo13GeometryRejected):
            create_wo13_structural_price_fact(
                canonical_subject_identity=handoff.canonical_subject_identity,
                market_family=handoff.market_family,
                timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
                price="95",
                structural_role=Wo13StructuralRole.PULLBACK_STRUCTURAL_LOW,
                price_authority=authority,
                structure_identity=handoff.setup_evidence_identity,
                source_evidence_identity=f"SOURCE:{authority.value}",
                source_evidence_integrity=f"INTEGRITY:{authority.value}",
                analysis_boundary=handoff.analysis_boundary,
                instrument_identity=handoff.instrument_identity,
                market_session_identity=SESSION,
            )


def test_slice3_surface_has_no_ltp_5m_rr_or_target_winner_inputs() -> None:
    evidence_parameters = set(
        inspect.signature(create_wo13_pullback_geometry_evidence).parameters
    )
    construction_parameters = set(
        inspect.signature(construct_wo13_pullback_geometry).parameters
    )

    prohibited = {
        "ltp",
        "current_ltp",
        "five_minute_candles",
        "atr",
        "desired_rr",
        "target_constraints",
        "quantity",
        "capital",
    }
    assert prohibited.isdisjoint(evidence_parameters | construction_parameters)


def test_slice3_result_has_no_downstream_authority(tmp_path) -> None:
    geometry = construct_wo13_pullback_geometry(_evidence(_handoff(tmp_path)))

    assert not any((
        geometry.range_breakout_authority,
        geometry.target_constraint_selection_authority,
        geometry.persistence_authority,
        geometry.runtime_authority,
        geometry.risk_authority,
        geometry.entry_timing_authority,
        geometry.sponsor_decision_authority,
        geometry.execution_authority,
        geometry.broker_authority,
    ))


def test_task_owned_module_contains_no_range_persistence_runtime_or_provider_calls() -> None:
    import kronos.intraday.wo13_pullback as module

    source = inspect.getsource(module)
    assert "calculate_wo13_range_width" not in source
    assert "RANGE_HIGH" not in source
    assert "RANGE_LOW" not in source
    assert "nearest" not in source.lower()
    assert "kronos.provider" not in source
    assert "browser" not in source.lower()
    assert "wo13_persistence" not in source
    assert "def persist" not in source
