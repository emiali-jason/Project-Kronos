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
    Wo13WarningCode,
)
from kronos.intraday.wo13_geometry import (
    Wo13GeometryRejected,
    Wo13PriceAuthority,
    Wo13StructuralRole,
    create_wo13_structural_price_fact,
)
from kronos.intraday.wo13_handoff import (
    Wo13SetupFamily,
    create_wo13_step31_handoff,
)
from kronos.intraday.wo13_breakout import (
    WO13_BREAKOUT_ENTRY_CONDITION_IDENTITY,
    WO13_BREAKOUT_EVIDENCE_IDENTITY,
    WO13_BREAKOUT_FACT_REFERENCE_IDENTITY,
    WO13_BREAKOUT_GEOMETRY_IDENTITY,
    Wo13BreakoutEntryConditionCode,
    Wo13BreakoutFailure,
    Wo13BreakoutInvalidationCode,
    Wo13BreakoutRejected,
    construct_wo13_breakout_geometry,
    create_wo13_breakout_fact_reference,
    create_wo13_breakout_geometry_evidence,
)
from kronos.intraday.wo12_k5_foundation import Wo12SetupFamily

from .test_wo13_contracts import _handoff, _mcx_artifacts


SESSION = "NSE-SESSION-2026-08-31"
RANGE_IDENTITY = "GOVERNED-RANGE:NSE-EQ-RELIANCE:2026-08-31:1"


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
    default_structure = (
        RANGE_IDENTITY
        if role in {Wo13StructuralRole.RANGE_HIGH, Wo13StructuralRole.RANGE_LOW}
        else handoff.setup_evidence_identity
    )
    return create_wo13_structural_price_fact(
        canonical_subject_identity=subject or handoff.canonical_subject_identity,
        market_family=family,
        timeframe=timeframe,
        price=price,
        structural_role=role,
        price_authority=_authority(family),
        structure_identity=structure or default_structure,
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
    qualification_role = (
        Wo13StructuralRole.QUALIFICATION_CANDLE_LOW
        if handoff.inherited_direction is SemanticDirection.LONG
        else Wo13StructuralRole.QUALIFICATION_CANDLE_HIGH
    )
    return (
        _fact(handoff, "110", Wo13StructuralRole.RANGE_HIGH),
        _fact(handoff, "100", Wo13StructuralRole.RANGE_LOW),
        _fact(
            handoff,
            "106" if handoff.inherited_direction is SemanticDirection.LONG else "104",
            qualification_role,
        ),
    )


def _reference(handoff, fact):  # type: ignore[no-untyped-def]
    return create_wo13_breakout_fact_reference(
        fact=fact,
        breakout_cycle_identity=handoff.setup_evidence_identity,
        breakout_direction=handoff.inherited_direction,
    )


def _evidence(
    handoff,
    *,
    range_high=None,
    range_low=None,
    qualification=None,
    range_high_references=None,
    range_low_references=None,
    qualification_references=None,
    session: str = SESSION,
    range_identity: str = RANGE_IDENTITY,
    direction=None,
):  # type: ignore[no-untyped-def]
    defaults = _facts(handoff)
    range_high = (defaults[0],) if range_high is None else tuple(range_high)
    range_low = (defaults[1],) if range_low is None else tuple(range_low)
    qualification = (defaults[2],) if qualification is None else tuple(qualification)
    range_high_references = (
        tuple(_reference(handoff, item) for item in range_high)
        if range_high_references is None
        else tuple(range_high_references)
    )
    range_low_references = (
        tuple(_reference(handoff, item) for item in range_low)
        if range_low_references is None
        else tuple(range_low_references)
    )
    qualification_references = (
        tuple(_reference(handoff, item) for item in qualification)
        if qualification_references is None
        else tuple(qualification_references)
    )
    return create_wo13_breakout_geometry_evidence(
        handoff=handoff,
        breakout_direction=direction or handoff.inherited_direction,
        market_session_identity=session,
        original_range_identity=range_identity,
        range_high_references=range_high_references,
        range_high_facts=range_high,
        range_low_references=range_low_references,
        range_low_facts=range_low,
        qualification_references=qualification_references,
        qualification_candles=qualification,
    )


def _breakout_handoff(tmp_path, direction=SemanticDirection.LONG):  # type: ignore[no-untyped-def]
    return _handoff(
        tmp_path,
        direction=direction,
        setup=Wo12SetupFamily.RANGE_BREAKOUT,
    )


def _mcx_handoff(tmp_path):  # type: ignore[no-untyped-def]
    values = _mcx_artifacts(tmp_path)
    values = list(values)
    setup = values[6]
    from kronos.intraday.wo12_k5_foundation import derive_wo12_structural_origin

    values[6] = derive_wo12_structural_origin(
        canonical_subject_identity=setup.canonical_subject_identity,
        market_family=setup.market_family,
        setup_family=Wo12SetupFamily.RANGE_BREAKOUT,
        inherited_direction=setup.inherited_direction,
        analysis_boundary=setup.analysis_boundary,
        evidence=None,
    )
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
    handoff = _breakout_handoff(tmp_path)
    evidence = _evidence(handoff)
    geometry = construct_wo13_breakout_geometry(evidence)

    assert evidence.schema_identity == WO13_BREAKOUT_EVIDENCE_IDENTITY
    assert evidence.range_high_references[0].schema_identity == (
        WO13_BREAKOUT_FACT_REFERENCE_IDENTITY
    )
    assert geometry.schema_identity == WO13_BREAKOUT_GEOMETRY_IDENTITY
    assert geometry.entry_condition is not None
    assert geometry.entry_condition.schema_identity == WO13_BREAKOUT_ENTRY_CONDITION_IDENTITY
    assert evidence.policy_checksum == WO13_POLICY_CHECKSUM
    assert handoff.setup_family is Wo13SetupFamily.INTRADAY_RANGE_BREAKOUT


def test_long_happy_path_uses_original_range_and_exact_candle(tmp_path) -> None:
    geometry = construct_wo13_breakout_geometry(
        _evidence(_breakout_handoff(tmp_path, SemanticDirection.LONG))
    )

    assert geometry.range_width.range_width == Decimal("10")
    assert geometry.entry_reference.selected_fact.price == Decimal("110")
    assert geometry.stop.selected_fact.price == Decimal("106")
    assert geometry.thesis_invalidation_reference.selected_fact.price == Decimal("110")
    assert geometry.setup_native_target.selected_fact.price == Decimal("120")
    assert geometry.risk_distance == Decimal("4")


def test_short_happy_path_is_exactly_symmetric(tmp_path) -> None:
    geometry = construct_wo13_breakout_geometry(
        _evidence(_breakout_handoff(tmp_path, SemanticDirection.SHORT))
    )

    assert geometry.range_width.range_width == Decimal("10")
    assert geometry.entry_reference.selected_fact.price == Decimal("100")
    assert geometry.stop.selected_fact.price == Decimal("104")
    assert geometry.thesis_invalidation_reference.selected_fact.price == Decimal("100")
    assert geometry.setup_native_target.selected_fact.price == Decimal("90")
    assert geometry.risk_distance == Decimal("4")


@pytest.mark.parametrize(
    ("direction", "condition", "invalidation"),
    (
        (
            SemanticDirection.LONG,
            Wo13BreakoutEntryConditionCode.DIRECTIONAL_BREAKOUT_ABOVE_ORIGINAL_RANGE_HIGH,
            Wo13BreakoutInvalidationCode.COMPLETED_GOVERNED_15M_CLOSE_BACK_AT_OR_INSIDE_LONG_RANGE,
        ),
        (
            SemanticDirection.SHORT,
            Wo13BreakoutEntryConditionCode.DIRECTIONAL_BREAKOUT_BELOW_ORIGINAL_RANGE_LOW,
            Wo13BreakoutInvalidationCode.COMPLETED_GOVERNED_15M_CLOSE_BACK_AT_OR_INSIDE_SHORT_RANGE,
        ),
    ),
)
def test_entry_and_invalidation_define_geometry_without_timing(
    tmp_path, direction, condition, invalidation
) -> None:  # type: ignore[no-untyped-def]
    geometry = construct_wo13_breakout_geometry(
        _evidence(_breakout_handoff(tmp_path, direction))
    )

    assert geometry.entry_condition.condition_code is condition
    assert geometry.entry_condition.trigger_evaluation_performed is False
    assert geometry.entry_condition.retest_required is False
    assert geometry.thesis_invalidation_event.event_code == invalidation.value


def test_stop_and_invalidation_are_separate_and_may_have_different_prices(tmp_path) -> None:
    geometry = construct_wo13_breakout_geometry(
        _evidence(_breakout_handoff(tmp_path))
    )
    stop = geometry.stop.selected_fact
    invalidation = geometry.thesis_invalidation_reference.selected_fact

    assert stop.price == Decimal("106")
    assert invalidation.price == Decimal("110")
    assert stop.fact_identity != invalidation.fact_identity
    assert stop.structural_role is Wo13StructuralRole.STOP_REFERENCE_SOURCE
    assert invalidation.structural_role is Wo13StructuralRole.THESIS_INVALIDATION_REFERENCE


def test_entry_and_stop_have_no_buffers(tmp_path) -> None:
    handoff = _breakout_handoff(tmp_path)
    high, _, candle = _facts(handoff)
    geometry = construct_wo13_breakout_geometry(_evidence(handoff))

    assert geometry.entry_reference.selected_fact.price == high.price
    assert geometry.stop.selected_fact.price == candle.price
    assert geometry.calculation.tick_normalization_applied is False


def test_measured_objective_is_exactly_one_range_width(tmp_path) -> None:
    geometry = construct_wo13_breakout_geometry(
        _evidence(_breakout_handoff(tmp_path))
    )

    assert geometry.setup_native_target.selected_fact.price == Decimal("120")
    assert geometry.setup_native_target.selected_fact.price != Decimal("125")
    assert geometry.setup_native_target.selected_fact.price != Decimal("130")
    assert geometry.native_target_candidate.directional_distance == Decimal("10")


def test_canonical_target_reward_and_rr_wait_for_slice5(tmp_path) -> None:
    geometry = construct_wo13_breakout_geometry(
        _evidence(_breakout_handoff(tmp_path))
    )

    assert geometry.canonical_target.availability is Wo13FieldAvailability.UNAVAILABLE
    assert geometry.reward_distance is None
    assert geometry.model_rr is None
    assert geometry.geometry_availability is Wo13GeometryAvailability.GEOMETRY_PARTIAL
    assert geometry.target_constraint_selection_pending is True
    assert geometry.target_constraint_selection_authority is False


@pytest.mark.parametrize("component", ("high", "low"))
def test_missing_original_range_boundary_is_incomplete(tmp_path, component: str) -> None:
    handoff = _breakout_handoff(tmp_path)
    high, low, candle = _facts(handoff)
    kwargs = {
        "range_high": (high,),
        "range_low": (low,),
        "qualification": (candle,),
    }
    fact = high if component == "high" else low
    kwargs[f"range_{component}"] = ()
    kwargs[f"range_{component}_references"] = (_reference(handoff, fact),)
    geometry = construct_wo13_breakout_geometry(_evidence(handoff, **kwargs))
    resolution = geometry.range_high if component == "high" else geometry.range_low

    assert resolution.availability is Wo13FieldAvailability.INCOMPLETE
    assert geometry.range_width is None
    assert geometry.entry_reference.selected_fact is None
    assert geometry.setup_native_target.selected_fact is None


def test_missing_qualification_candle_leaves_stop_and_risk_incomplete(tmp_path) -> None:
    handoff = _breakout_handoff(tmp_path)
    candle = _facts(handoff)[2]
    geometry = construct_wo13_breakout_geometry(
        _evidence(
            handoff,
            qualification=(),
            qualification_references=(_reference(handoff, candle),),
        )
    )

    assert geometry.qualification_candle.availability is Wo13FieldAvailability.INCOMPLETE
    assert geometry.stop.selected_fact is None
    assert geometry.risk_distance is None


@pytest.mark.parametrize("component", ("high", "low", "qualification"))
def test_ambiguous_component_is_never_selected_by_recency(tmp_path, component: str) -> None:
    handoff = _breakout_handoff(tmp_path)
    high, low, candle = _facts(handoff)
    original = {"high": high, "low": low, "qualification": candle}[component]
    second = _fact(
        handoff,
        str(original.price + Decimal("1")),
        original.structural_role,
        source=f"SOURCE:AMBIGUOUS:{component}",
    )
    key = f"range_{component}" if component in {"high", "low"} else component
    geometry = construct_wo13_breakout_geometry(
        _evidence(handoff, **{key: (original, second)})
    )
    resolution = {
        "high": geometry.range_high,
        "low": geometry.range_low,
        "qualification": geometry.qualification_candle,
    }[component]

    assert resolution.availability is Wo13FieldAvailability.AMBIGUOUS
    assert resolution.selected_fact is None


def test_invalid_range_fails_closed_without_repair(tmp_path) -> None:
    handoff = _breakout_handoff(tmp_path)
    high = _fact(handoff, "100", Wo13StructuralRole.RANGE_HIGH)
    low = _fact(handoff, "100", Wo13StructuralRole.RANGE_LOW)
    geometry = construct_wo13_breakout_geometry(
        _evidence(handoff, range_high=(high,), range_low=(low,))
    )

    assert geometry.range_width is None
    assert geometry.range_failure is Wo13BreakoutFailure.RANGE_INVALID
    assert geometry.entry_reference.selected_fact is None
    assert geometry.setup_native_target.selected_fact is None


@pytest.mark.parametrize(
    ("change", "failure"),
    (
        ("subject", Wo13BreakoutFailure.FACT_CONTEXT_MISMATCH),
        ("boundary", Wo13BreakoutFailure.FACT_CONTEXT_MISMATCH),
        ("instrument", Wo13BreakoutFailure.FACT_CONTEXT_MISMATCH),
        ("range", Wo13BreakoutFailure.ORIGINAL_RANGE_IDENTITY_MISMATCH),
        ("session", Wo13BreakoutFailure.FACT_SESSION_MISMATCH),
        ("timeframe", Wo13BreakoutFailure.FACT_TIMEFRAME_MISMATCH),
    ),
)
def test_foreign_range_high_fails_exact_binding(
    tmp_path, change: str, failure: Wo13BreakoutFailure
) -> None:
    handoff = _breakout_handoff(tmp_path)
    kwargs = {}
    if change == "subject":
        kwargs["subject"] = "NSE-EQ-TCS"
    elif change == "boundary":
        kwargs["boundary"] = handoff.analysis_boundary + timedelta(minutes=15)
    elif change == "instrument":
        kwargs["instrument"] = "INSTRUMENT:NSE:TCS"
    elif change == "range":
        kwargs["structure"] = "FOREIGN-RANGE"
    elif change == "session":
        kwargs["session"] = "NSE-SESSION-2026-08-28"
    else:
        kwargs["timeframe"] = IntradayTimeframe.DAILY
    foreign = _fact(handoff, "110", Wo13StructuralRole.RANGE_HIGH, **kwargs)

    with pytest.raises(Wo13BreakoutRejected) as rejected:
        _evidence(handoff, range_high=(foreign,))
    assert rejected.value.failure is failure


def test_foreign_breakout_cycle_and_direction_fail_closed(tmp_path) -> None:
    handoff = _breakout_handoff(tmp_path)
    fact = _facts(handoff)[2]
    foreign_cycle = create_wo13_breakout_fact_reference(
        fact=fact,
        breakout_cycle_identity="FOREIGN-WO12-CYCLE",
        breakout_direction=handoff.inherited_direction,
    )
    with pytest.raises(Wo13BreakoutRejected) as rejected:
        _evidence(handoff, qualification=(fact,), qualification_references=(foreign_cycle,))
    assert rejected.value.failure is Wo13BreakoutFailure.FACT_CYCLE_MISMATCH

    with pytest.raises(Wo13BreakoutRejected) as rejected:
        _evidence(handoff, direction=SemanticDirection.SHORT)
    assert rejected.value.failure is Wo13BreakoutFailure.BREAKOUT_DIRECTION_MISMATCH


def test_fact_not_named_by_exact_reference_is_rejected(tmp_path) -> None:
    handoff = _breakout_handoff(tmp_path)
    fact = _facts(handoff)[2]
    other = _fact(
        handoff,
        "105",
        Wo13StructuralRole.QUALIFICATION_CANDLE_LOW,
        source="SOURCE:OTHER-QUALIFICATION",
    )
    with pytest.raises(Wo13BreakoutRejected) as rejected:
        _evidence(
            handoff,
            qualification=(fact,),
            qualification_references=(_reference(handoff, other),),
        )
    assert rejected.value.failure is Wo13BreakoutFailure.FACT_BINDING_MISMATCH


def test_pullback_handoff_is_rejected(tmp_path) -> None:
    handoff = _handoff(tmp_path, setup=Wo12SetupFamily.PULLBACK_CONTINUATION)

    with pytest.raises(Wo13BreakoutRejected) as rejected:
        create_wo13_breakout_geometry_evidence(
            handoff=handoff,
            breakout_direction=handoff.inherited_direction,
            market_session_identity=SESSION,
            original_range_identity=RANGE_IDENTITY,
        )
    assert rejected.value.failure is Wo13BreakoutFailure.SETUP_FAMILY_UNSUPPORTED


@pytest.mark.parametrize(
    ("direction", "stop"),
    (
        (SemanticDirection.LONG, "111"),
        (SemanticDirection.SHORT, "99"),
    ),
)
def test_invalid_directional_stop_is_preserved_and_not_repaired(
    tmp_path, direction, stop
) -> None:  # type: ignore[no-untyped-def]
    handoff = _breakout_handoff(tmp_path, direction)
    high, low, _ = _facts(handoff)
    role = (
        Wo13StructuralRole.QUALIFICATION_CANDLE_LOW
        if direction is SemanticDirection.LONG
        else Wo13StructuralRole.QUALIFICATION_CANDLE_HIGH
    )
    candle = _fact(handoff, stop, role, source="SOURCE:INVALID-STOP")
    geometry = construct_wo13_breakout_geometry(
        _evidence(handoff, range_high=(high,), range_low=(low,), qualification=(candle,))
    )

    assert geometry.stop.selected_fact.price == Decimal(stop)
    assert geometry.risk_distance is None
    assert geometry.calculation.warnings == (
        Wo13WarningCode.NON_POSITIVE_RISK,
        Wo13WarningCode.INVALID_DIRECTIONAL_GEOMETRY,
    )


def test_later_retest_cannot_move_entry_stop_or_target(tmp_path) -> None:
    geometry = construct_wo13_breakout_geometry(
        _evidence(_breakout_handoff(tmp_path))
    )
    public = inspect.signature(construct_wo13_breakout_geometry).parameters

    assert "retest" not in public
    assert geometry.entry_reference.selected_fact.price == Decimal("110")
    assert geometry.stop.selected_fact.price == Decimal("106")
    assert geometry.setup_native_target.selected_fact.price == Decimal("120")


def test_identity_is_deterministic_and_changes_with_range_source(tmp_path) -> None:
    handoff = _breakout_handoff(tmp_path)
    first = construct_wo13_breakout_geometry(_evidence(handoff))
    same = construct_wo13_breakout_geometry(_evidence(handoff))
    high = _fact(
        handoff,
        "111",
        Wo13StructuralRole.RANGE_HIGH,
        source="SOURCE:CHANGED-RANGE-HIGH",
    )
    changed = construct_wo13_breakout_geometry(
        _evidence(handoff, range_high=(high,))
    )

    assert first == same
    assert first.geometry_identity == same.geometry_identity
    assert first.geometry_identity != changed.geometry_identity
    assert first.evidence.evidence_identity != changed.evidence.evidence_identity


def test_evidence_and_geometry_corruption_fail_closed(tmp_path) -> None:
    evidence = _evidence(_breakout_handoff(tmp_path))
    geometry = construct_wo13_breakout_geometry(evidence)

    with pytest.raises(Wo13BreakoutRejected):
        replace(evidence, evidence_integrity="CORRUPT")
    with pytest.raises(Wo13BreakoutRejected):
        replace(geometry, geometry_integrity="CORRUPT")


def test_mcx_geometry_is_exact_active_contract_and_roll_local(tmp_path) -> None:
    handoff = _mcx_handoff(tmp_path)
    session = "MCX-SESSION-2026-08-31"
    high = _fact(handoff, "110", Wo13StructuralRole.RANGE_HIGH, session=session)
    low = _fact(handoff, "100", Wo13StructuralRole.RANGE_LOW, session=session)
    candle = _fact(
        handoff,
        "106",
        Wo13StructuralRole.QUALIFICATION_CANDLE_LOW,
        session=session,
    )
    geometry = construct_wo13_breakout_geometry(
        _evidence(
            handoff,
            range_high=(high,),
            range_low=(low,),
            qualification=(candle,),
            session=session,
        )
    )

    for fact in (
        geometry.entry_reference.selected_fact,
        geometry.stop.selected_fact,
        geometry.setup_native_target.selected_fact,
    ):
        assert fact.actual_contract_identity == handoff.actual_contract_identity
        assert fact.roll_lineage_identity == handoff.roll_lineage_identity


@pytest.mark.parametrize("change", ("contract", "roll"))
def test_mcx_cross_contract_or_cross_roll_range_is_rejected(tmp_path, change: str) -> None:
    handoff = _mcx_handoff(tmp_path)
    fact = _fact(
        handoff,
        "110",
        Wo13StructuralRole.RANGE_HIGH,
        session="MCX-SESSION-2026-08-31",
        **{change: f"FOREIGN-{change.upper()}"},
    )
    with pytest.raises(Wo13BreakoutRejected) as rejected:
        _evidence(
            handoff,
            range_high=(fact,),
            session="MCX-SESSION-2026-08-31",
        )
    assert rejected.value.failure is Wo13BreakoutFailure.FACT_CONTEXT_MISMATCH


def test_context_and_reference_prices_have_no_geometry_authority(tmp_path) -> None:
    handoff = _breakout_handoff(tmp_path)
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
                price="110",
                structural_role=Wo13StructuralRole.RANGE_HIGH,
                price_authority=authority,
                structure_identity=RANGE_IDENTITY,
                source_evidence_identity=f"SOURCE:{authority.value}",
                source_evidence_integrity=f"INTEGRITY:{authority.value}",
                analysis_boundary=handoff.analysis_boundary,
                instrument_identity=handoff.instrument_identity,
                market_session_identity=SESSION,
            )


def test_slice4_surface_has_no_ltp_5m_rr_retest_or_target_winner_inputs() -> None:
    parameters = set(inspect.signature(create_wo13_breakout_geometry_evidence).parameters)
    parameters |= set(inspect.signature(construct_wo13_breakout_geometry).parameters)
    assert {
        "ltp",
        "current_ltp",
        "five_minute_candles",
        "retest",
        "atr",
        "desired_rr",
        "target_constraints",
        "quantity",
        "capital",
    }.isdisjoint(parameters)


def test_slice4_result_has_no_downstream_or_pullback_authority(tmp_path) -> None:
    geometry = construct_wo13_breakout_geometry(
        _evidence(_breakout_handoff(tmp_path))
    )

    assert not any((
        geometry.pullback_authority,
        geometry.target_constraint_selection_authority,
        geometry.persistence_authority,
        geometry.runtime_authority,
        geometry.risk_authority,
        geometry.entry_timing_authority,
        geometry.sponsor_decision_authority,
        geometry.execution_authority,
        geometry.broker_authority,
    ))


def test_task_owned_module_contains_no_persistence_runtime_or_provider_calls() -> None:
    import kronos.intraday.wo13_breakout as module

    source = inspect.getsource(module)
    assert "nearest" not in source.lower()
    assert "target 2" not in source.lower()
    assert "kronos.provider" not in source
    assert "browser" not in source.lower()
    assert "wo13_persistence" not in source
    assert "def persist" not in source
