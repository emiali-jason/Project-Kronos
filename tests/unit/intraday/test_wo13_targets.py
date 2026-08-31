from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import inspect

import pytest

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo13 import Wo13FieldAvailability, Wo13GeometryAvailability
from kronos.intraday.wo13_geometry import (
    Wo13StructuralRole,
    Wo13TargetCandidateKind,
    create_wo13_structural_price_fact,
    create_wo13_target_candidate,
)
from kronos.intraday.wo13_targets import (
    WO13_ELIGIBLE_TARGET_CONSTRAINT_ROLES,
    WO13_TARGET_CONSTRAINT_POPULATION_IDENTITY,
    WO13_TARGET_SELECTION_IDENTITY,
    Wo13TargetPopulationCompleteness,
    Wo13TargetSelectionDisposition,
    Wo13TargetSelectionFailure,
    Wo13TargetSelectionRejected,
    create_wo13_target_constraint_population,
    finalize_wo13_canonical_target,
)
from kronos.intraday.wo12_k5_foundation import Wo12SetupFamily

from .test_wo13_breakout import (
    _breakout_handoff,
    _evidence as _breakout_evidence,
)
from .test_wo13_contracts import _handoff
from .test_wo13_pullback import (
    _evidence as _pullback_evidence,
    _fact as _pullback_fact,
)
from kronos.intraday.wo13_pullback import construct_wo13_pullback_geometry
from kronos.intraday.wo13_breakout import construct_wo13_breakout_geometry


def _pullback(tmp_path, direction=SemanticDirection.LONG):  # type: ignore[no-untyped-def]
    handoff = _handoff(tmp_path, direction=direction)
    return construct_wo13_pullback_geometry(_pullback_evidence(handoff))


def _pullback_with_prices(
    tmp_path,
    direction: SemanticDirection,
    *,
    stop: str,
    native: str,
):  # type: ignore[no-untyped-def]
    handoff = _handoff(tmp_path, direction=direction)
    qualification_role = (
        Wo13StructuralRole.QUALIFICATION_CANDLE_HIGH
        if direction is SemanticDirection.LONG
        else Wo13StructuralRole.QUALIFICATION_CANDLE_LOW
    )
    stop_role = (
        Wo13StructuralRole.PULLBACK_STRUCTURAL_LOW
        if direction is SemanticDirection.LONG
        else Wo13StructuralRole.PULLBACK_STRUCTURAL_HIGH
    )
    native_role = (
        Wo13StructuralRole.PRIOR_IMPULSE_HIGH
        if direction is SemanticDirection.LONG
        else Wo13StructuralRole.PRIOR_IMPULSE_LOW
    )
    return construct_wo13_pullback_geometry(
        _pullback_evidence(
            handoff,
            qualification=(_pullback_fact(handoff, "100", qualification_role),),
            pullback=(_pullback_fact(handoff, stop, stop_role),),
            impulse=(_pullback_fact(handoff, native, native_role),),
        )
    )


def _breakout(tmp_path, direction=SemanticDirection.LONG):  # type: ignore[no-untyped-def]
    handoff = _breakout_handoff(tmp_path, direction)
    return construct_wo13_breakout_geometry(_breakout_evidence(handoff))


def _constraint(
    geometry,
    price: str,
    role: Wo13StructuralRole = Wo13StructuralRole.GOVERNED_STRUCTURAL_BARRIER,
    *,
    source: str | None = None,
):  # type: ignore[no-untyped-def]
    entry = geometry.entry_reference.selected_fact
    source = source or f"TARGET:{role.value}:{price}"
    fact = create_wo13_structural_price_fact(
        canonical_subject_identity=entry.canonical_subject_identity,
        market_family=entry.market_family,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        price=price,
        structural_role=role,
        price_authority=entry.price_authority,
        structure_identity=f"STRUCTURE:{source}",
        source_evidence_identity=source,
        source_evidence_integrity=f"INTEGRITY:{source}",
        analysis_boundary=entry.analysis_boundary,
        instrument_identity=entry.instrument_identity,
        actual_contract_identity=entry.actual_contract_identity,
        roll_lineage_identity=entry.roll_lineage_identity,
        market_session_identity=entry.market_session_identity,
    )
    return create_wo13_target_candidate(
        entry_reference=entry,
        candidate=fact,
        direction=geometry.evidence.handoff.inherited_direction,
        kind=Wo13TargetCandidateKind.STRUCTURAL_CONSTRAINT,
    )


def _finalize(geometry, candidates=(), *, completeness=None):  # type: ignore[no-untyped-def]
    population = create_wo13_target_constraint_population(
        setup_geometry=geometry,
        candidates=candidates,
        completeness=(
            completeness
            if completeness is not None
            else Wo13TargetPopulationCompleteness.COMPLETE
        ),
    )
    return finalize_wo13_canonical_target(
        setup_geometry=geometry,
        candidate_population=population,
    )


def test_contract_identities_and_complete_empty_population_are_frozen(tmp_path) -> None:
    result = _finalize(_pullback(tmp_path))
    assert result.schema_identity == WO13_TARGET_SELECTION_IDENTITY
    assert result.candidate_population.schema_identity == (
        WO13_TARGET_CONSTRAINT_POPULATION_IDENTITY
    )
    assert result.disposition is Wo13TargetSelectionDisposition.SETUP_NATIVE
    assert result.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE


def test_exact_eligible_constraint_role_vocabulary_is_frozen() -> None:
    assert WO13_ELIGIBLE_TARGET_CONSTRAINT_ROLES == (
        Wo13StructuralRole.PDH,
        Wo13StructuralRole.PDL,
        Wo13StructuralRole.SESSION_STRUCTURAL_HIGH,
        Wo13StructuralRole.SESSION_STRUCTURAL_LOW,
        Wo13StructuralRole.PIVOT_RESISTANCE,
        Wo13StructuralRole.PIVOT_SUPPORT,
        Wo13StructuralRole.GOVERNED_STRUCTURAL_BARRIER,
    )


def test_long_nearest_forward_constraint_uses_price_not_role_order(tmp_path) -> None:
    geometry = _pullback_with_prices(
        tmp_path, SemanticDirection.LONG, stop="95", native="120"
    )
    candidates = (
        _constraint(geometry, "110", Wo13StructuralRole.PDH),
        _constraint(geometry, "105", Wo13StructuralRole.PIVOT_RESISTANCE),
        _constraint(geometry, "108", Wo13StructuralRole.SESSION_STRUCTURAL_HIGH),
    )
    result = _finalize(geometry, candidates)
    assert result.canonical_target.selected_fact.price == Decimal("105")
    assert result.constraining_candidates[0].structural_role is (
        Wo13StructuralRole.PIVOT_RESISTANCE
    )


def test_short_nearest_forward_constraint_is_exactly_symmetric(tmp_path) -> None:
    geometry = _pullback_with_prices(
        tmp_path, SemanticDirection.SHORT, stop="105", native="80"
    )
    result = _finalize(
        geometry,
        tuple(_constraint(geometry, value) for value in ("95", "90", "89")),
    )
    assert result.canonical_target.selected_fact.price == Decimal("95")


@pytest.mark.parametrize(
    ("direction", "prices", "expected"),
    (
        (SemanticDirection.LONG, ("90", "100", "104", "110", "112", "125"), "104"),
        (SemanticDirection.SHORT, ("110", "100", "96", "90", "88", "70"), "96"),
    ),
)
def test_strict_between_ignores_behind_at_entry_at_native_and_beyond(
    tmp_path, direction, prices, expected
) -> None:  # type: ignore[no-untyped-def]
    geometry = _pullback_with_prices(
        tmp_path,
        direction,
        stop="95" if direction is SemanticDirection.LONG else "105",
        native="120" if direction is SemanticDirection.LONG else "80",
    )
    result = _finalize(
        geometry, tuple(_constraint(geometry, item) for item in prices)
    )
    assert result.canonical_target.selected_fact.price == Decimal(expected)


def test_no_nearer_constraint_keeps_native_target(tmp_path) -> None:
    geometry = _pullback_with_prices(
        tmp_path, SemanticDirection.LONG, stop="95", native="120"
    )
    result = _finalize(
        geometry,
        (_constraint(geometry, "95"), _constraint(geometry, "125")),
    )
    assert result.disposition is Wo13TargetSelectionDisposition.SETUP_NATIVE
    assert result.canonical_target.selected_fact.price == Decimal("120")
    assert result.constraining_candidates == ()


def test_same_price_confluence_is_one_target_with_all_provenance(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    candidates = (
        _constraint(geometry, "108", Wo13StructuralRole.PDH),
        _constraint(geometry, "108", Wo13StructuralRole.PIVOT_RESISTANCE),
        _constraint(geometry, "108", Wo13StructuralRole.GOVERNED_STRUCTURAL_BARRIER),
    )
    result = _finalize(geometry, candidates)
    assert result.canonical_target.selected_fact.price == Decimal("108")
    assert len(result.canonical_target.facts) == 1
    assert len(result.constraining_candidates) == 3
    assert len(result.confluence_candidates) == 3


def test_native_price_confluence_does_not_create_second_target(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    candidate = _constraint(geometry, "112", Wo13StructuralRole.PDH)
    result = _finalize(geometry, (candidate,))
    assert result.disposition is Wo13TargetSelectionDisposition.SETUP_NATIVE
    assert result.canonical_target.selected_fact == geometry.setup_native_target.selected_fact
    assert result.constraining_candidates == ()
    assert result.confluence_candidates == (candidate,)
    assert not hasattr(result, "target_2")


def test_exact_duplicates_are_deduplicated_deterministically(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    candidate = _constraint(geometry, "105")
    first = _finalize(geometry, (candidate, candidate))
    second = _finalize(geometry, (candidate,))
    assert first == second
    assert first.selection_identity == second.selection_identity


def test_candidate_order_cannot_change_identity_or_selection(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    candidates = (_constraint(geometry, "105"), _constraint(geometry, "110"))
    assert _finalize(geometry, candidates) == _finalize(
        geometry, tuple(reversed(candidates))
    )


def test_reward_and_rr_finalize_without_quality_gate(tmp_path) -> None:
    geometry = _pullback_with_prices(
        tmp_path, SemanticDirection.LONG, stop="95", native="120"
    )
    result = _finalize(geometry, (_constraint(geometry, "110"),))
    assert result.risk_distance == Decimal("5")
    assert result.reward_distance == Decimal("10")
    assert result.model_rr == Decimal("2")
    assert result.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE


def test_short_reward_and_rr_use_symmetric_arithmetic(tmp_path) -> None:
    geometry = _pullback_with_prices(
        tmp_path, SemanticDirection.SHORT, stop="105", native="80"
    )
    result = _finalize(geometry, (_constraint(geometry, "90"),))
    assert result.risk_distance == Decimal("5")
    assert result.reward_distance == Decimal("10")
    assert result.model_rr == Decimal("2")


def test_poor_rr_remains_complete_and_does_not_rewrite_target(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    result = _finalize(geometry, (_constraint(geometry, "102"),))
    assert result.model_rr == Decimal("0.5")
    assert result.canonical_target.selected_fact.price == Decimal("102")
    assert result.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE
    assert result.calculation.warnings == ()


def test_high_rr_has_no_special_promotion_or_target_change(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    result = _finalize(geometry)
    assert result.model_rr == Decimal("3")
    assert result.canonical_target.selected_fact.price == Decimal("112")
    assert result.disposition is Wo13TargetSelectionDisposition.SETUP_NATIVE


def test_incomplete_known_population_stays_partial(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    result = _finalize(
        geometry,
        (_constraint(geometry, "105"),),
        completeness=Wo13TargetPopulationCompleteness.INCOMPLETE,
    )
    assert result.disposition is Wo13TargetSelectionDisposition.INCOMPLETE
    assert result.canonical_target.availability is Wo13FieldAvailability.INCOMPLETE
    assert result.geometry_availability is Wo13GeometryAvailability.GEOMETRY_PARTIAL
    assert result.reward_distance is None
    assert result.model_rr is None


def test_missing_native_target_cannot_be_replaced_by_constraint(tmp_path) -> None:
    handoff = _handoff(tmp_path)
    qualification, pullback, impulse = (
        _pullback_fact(handoff, "100", Wo13StructuralRole.QUALIFICATION_CANDLE_HIGH),
        _pullback_fact(handoff, "96", Wo13StructuralRole.PULLBACK_STRUCTURAL_LOW),
        _pullback_fact(handoff, "112", Wo13StructuralRole.PRIOR_IMPULSE_HIGH),
    )
    from kronos.intraday.wo13_pullback import create_wo13_pullback_fact_reference

    evidence = _pullback_evidence(
        handoff,
        qualification=(qualification,),
        pullback=(pullback,),
        impulse=(),
        impulse_references=(create_wo13_pullback_fact_reference(impulse),),
    )
    geometry = construct_wo13_pullback_geometry(evidence)
    result = _finalize(geometry, (_constraint(geometry, "105"),))
    assert result.canonical_target.availability is Wo13FieldAvailability.INCOMPLETE
    assert result.geometry_availability is Wo13GeometryAvailability.GEOMETRY_PARTIAL


def test_nonforward_native_target_fails_closed_without_rescue(tmp_path) -> None:
    handoff = _handoff(tmp_path)
    behind = _pullback_fact(handoff, "95", Wo13StructuralRole.PRIOR_IMPULSE_HIGH)
    geometry = construct_wo13_pullback_geometry(
        _pullback_evidence(handoff, impulse=(behind,))
    )
    population = create_wo13_target_constraint_population(
        setup_geometry=geometry,
        candidates=(_constraint(geometry, "102"),),
    )
    with pytest.raises(Wo13TargetSelectionRejected) as failure:
        finalize_wo13_canonical_target(
            setup_geometry=geometry,
            candidate_population=population,
        )
    assert failure.value.failure is Wo13TargetSelectionFailure.NATIVE_TARGET_NOT_FORWARD


def test_same_authoritative_source_with_conflicting_prices_fails_closed(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    candidates = (
        _constraint(geometry, "105", source="ONE-AUTHORITATIVE-FACT"),
        _constraint(geometry, "106", source="ONE-AUTHORITATIVE-FACT"),
    )
    with pytest.raises(Wo13TargetSelectionRejected) as failure:
        create_wo13_target_constraint_population(
            setup_geometry=geometry,
            candidates=candidates,
        )
    assert failure.value.failure is Wo13TargetSelectionFailure.CANDIDATE_SOURCE_CONFLICT


def test_generic_untyped_target_constraint_is_not_an_eligible_input_role(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    candidate = _constraint(
        geometry,
        "105",
        role=Wo13StructuralRole.TARGET_CONSTRAINT,
    )
    with pytest.raises(Wo13TargetSelectionRejected) as failure:
        create_wo13_target_constraint_population(
            setup_geometry=geometry,
            candidates=(candidate,),
        )
    assert failure.value.failure is Wo13TargetSelectionFailure.POPULATION_INVALID


def test_foreign_current_session_barrier_is_rejected(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    entry = geometry.entry_reference.selected_fact
    fact = create_wo13_structural_price_fact(
        canonical_subject_identity=entry.canonical_subject_identity,
        market_family=entry.market_family,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        price="105",
        structural_role=Wo13StructuralRole.SESSION_STRUCTURAL_HIGH,
        price_authority=entry.price_authority,
        structure_identity="FOREIGN-SESSION-STRUCTURE",
        source_evidence_identity="FOREIGN-SESSION-STRUCTURE",
        source_evidence_integrity="INTEGRITY-FOREIGN-SESSION-STRUCTURE",
        analysis_boundary=entry.analysis_boundary,
        instrument_identity=entry.instrument_identity,
        market_session_identity="FOREIGN-SESSION",
    )
    candidate = create_wo13_target_candidate(
        entry_reference=entry,
        candidate=fact,
        direction=geometry.evidence.handoff.inherited_direction,
        kind=Wo13TargetCandidateKind.STRUCTURAL_CONSTRAINT,
    )
    with pytest.raises(Wo13TargetSelectionRejected):
        create_wo13_target_constraint_population(
            setup_geometry=geometry,
            candidates=(candidate,),
        )


def test_cross_setup_population_is_rejected(tmp_path) -> None:
    pullback = _pullback(tmp_path / "pullback")
    breakout = _breakout(tmp_path / "breakout")
    population = create_wo13_target_constraint_population(
        setup_geometry=pullback,
        candidates=(_constraint(pullback, "105"),),
    )
    with pytest.raises(Wo13TargetSelectionRejected) as failure:
        finalize_wo13_canonical_target(
            setup_geometry=breakout,
            candidate_population=population,
        )
    assert failure.value.failure is Wo13TargetSelectionFailure.POPULATION_BINDING_MISMATCH


@pytest.mark.parametrize("builder", (_pullback, _breakout))
@pytest.mark.parametrize("direction", (SemanticDirection.LONG, SemanticDirection.SHORT))
def test_pullback_and_breakout_finalize_without_mutating_slice_geometry(
    tmp_path, builder, direction
) -> None:  # type: ignore[no-untyped-def]
    geometry = builder(tmp_path, direction)
    before = (
        geometry.entry_reference,
        geometry.stop,
        geometry.thesis_invalidation_reference,
        geometry.setup_native_target,
        geometry.geometry_identity,
        geometry.geometry_integrity,
    )
    result = _finalize(geometry)
    assert result.geometry_availability is Wo13GeometryAvailability.GEOMETRY_COMPLETE
    assert before == (
        geometry.entry_reference,
        geometry.stop,
        geometry.thesis_invalidation_reference,
        geometry.setup_native_target,
        geometry.geometry_identity,
        geometry.geometry_integrity,
    )


def test_selection_identity_changes_on_material_candidate_change(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    first = _finalize(geometry, (_constraint(geometry, "105"),))
    same = _finalize(geometry, (_constraint(geometry, "105"),))
    changed = _finalize(geometry, (_constraint(geometry, "106"),))
    assert first == same
    assert first.selection_identity == same.selection_identity
    assert first.selection_identity != changed.selection_identity


def test_selection_corruption_is_rejected(tmp_path) -> None:
    result = _finalize(_pullback(tmp_path))
    with pytest.raises(Wo13TargetSelectionRejected):
        replace(result, selection_integrity="CORRUPT")


def test_slice5_surface_contains_no_rr_gate_target_ladder_or_downstream_authority() -> None:
    import kronos.intraday.wo13_targets as module

    source = inspect.getsource(module).lower()
    assert "target_2" not in source
    assert "target 2" not in source
    assert "rr_threshold" not in source
    assert "current_ltp" not in source
    assert "five_minute" not in source
    assert "kronos.provider" not in source
    assert "def persist" not in source
