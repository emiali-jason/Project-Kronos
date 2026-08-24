from dataclasses import replace
from decimal import Decimal

import pytest

from kronos.instrument.facts import InstrumentContextStatus
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_trade_construction import (
    TradePlanStatus,
    construct_trade_plan,
    create_trade_construction_evidence_package,
)
from kronos.swing.v1.step31_observation import (
    LocalStep31ObservationStore,
    STEP31_OBSERVATION_CONTRACT_ID,
    STEP31_OBSERVATION_POLICY_ID,
    Step31FactAvailability,
    Step31GeometryStatus,
    Step31ObservationHardFailure,
    Step31ObservationWarning,
    Step31RiskRewardState,
    Step31WarningSeverity,
    construct_step31_observation,
    create_sponsor_observation_handoff,
)
from tests.unit.swing.v1.test_kr370_step31_handoff import (
    NOW,
    _completed,
    _context,
    _evidence,
    _handoff,
    _price,
)


def _package(completed, **changes):  # type: ignore[no-untyped-def]
    base = _evidence(completed)
    values = dict(
        package_identity=base.package_identity,
        native_run_identity=base.native_run_identity,
        canonical_instrument=base.canonical_instrument,
        native_assessment_sha256=base.native_assessment_sha256,
        setup_identity=base.setup_identity,
        observation_boundary=base.observation_boundary,
        provenance=base.provenance,
        qualification_candle=base.qualification_candle,
        governing_structural_low=base.governing_structural_low,
        governing_structural_high=base.governing_structural_high,
        prior_directional_swing_high=base.prior_directional_swing_high,
        prior_directional_swing_low=base.prior_directional_swing_low,
        original_range_high=base.original_range_high,
        original_range_low=base.original_range_low,
        material_barriers=base.material_barriers,
    )
    values.update(changes)
    return create_trade_construction_evidence_package(**values)


def _observe(completed, evidence, *, plan=False):  # type: ignore[no-untyped-def]
    handoff = _handoff(completed)
    context = _context(completed.requirement.canonical_instrument)
    conventional = (
        construct_trade_plan(
            completed.requirement, handoff, evidence, context, created_at=NOW
        )
        if plan else None
    )
    if conventional is not None and conventional.geometry_viability is not TradePlanStatus.TRADE_PLAN_READY:
        conventional = None
    return construct_step31_observation(
        completed.requirement,
        handoff,
        evidence,
        context,
        created_at=NOW,
        conventional_plan=conventional,
    )


def test_valid_long_preserves_conventional_plan_and_green_geometry(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    observation = _observe(completed, _evidence(completed), plan=True)

    assert observation.contract_identity == STEP31_OBSERVATION_CONTRACT_ID
    assert observation.policy_identity == STEP31_OBSERVATION_POLICY_ID
    assert (observation.entry, observation.stop, observation.canonical_target) == (
        Decimal("100.00"), Decimal("90.00"), Decimal("120.00")
    )
    assert (observation.risk_per_unit, observation.reward_per_unit,
            observation.risk_reward_ratio) == (
        Decimal("10.00"), Decimal("20.00"), Decimal("2")
    )
    assert observation.warnings == ()
    assert observation.severity is Step31WarningSeverity.GREEN
    assert observation.geometry_status is Step31GeometryStatus.COMPLETE_FAVOURABLE
    assert observation.conventional_trade_plan_id is not None
    assert "NO_RISK_SPONSOR_EXECUTION_OR_BROKER_AUTHORITY" in observation.authority


def test_valid_short_preserves_inverse_geometry(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path, direction=V1Direction.SHORT)
    observation = _observe(completed, _evidence(completed), plan=True)

    assert (observation.entry, observation.stop, observation.canonical_target) == (
        Decimal("95.00"), Decimal("110.00"), Decimal("80.00")
    )
    assert observation.risk_reward_ratio == Decimal("1")
    assert observation.severity is Step31WarningSeverity.GREEN


def test_warning_long_retains_negative_reward_and_no_trade_plan(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    boundary = completed.promotion.analysis_boundary
    evidence = _package(
        completed,
        prior_directional_swing_high=_price("WARNING-TARGET", "95", boundary),
    )
    observation = _observe(completed, evidence)

    assert (observation.entry, observation.stop, observation.canonical_target) == (
        Decimal("100.00"), Decimal("90.00"), Decimal("95.00")
    )
    assert observation.reward_per_unit == Decimal("-5.00")
    assert observation.risk_reward_ratio is None
    assert observation.risk_reward_state is Step31RiskRewardState.INVALID
    assert observation.warnings == (
        Step31ObservationWarning.TARGET_BELOW_ENTRY,
        Step31ObservationWarning.NON_POSITIVE_REWARD,
    )
    assert observation.severity is Step31WarningSeverity.RED
    assert observation.geometry_status is Step31GeometryStatus.COMPLETE_WARNING
    assert observation.conventional_trade_plan_id is None


def test_warning_short_retains_negative_reward(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path, direction=V1Direction.SHORT)
    boundary = completed.promotion.analysis_boundary
    base = _evidence(completed)
    candle = replace(base.qualification_candle, high=Decimal("105"), low=Decimal("100"))
    evidence = _package(
        completed,
        qualification_candle=candle,
        prior_directional_swing_low=_price("WARNING-TARGET", "105", boundary),
    )
    observation = _observe(completed, evidence)

    assert (observation.entry, observation.stop, observation.canonical_target) == (
        Decimal("100.00"), Decimal("110.00"), Decimal("105.00")
    )
    assert observation.reward_per_unit == Decimal("-5.00")
    assert observation.warnings == (
        Step31ObservationWarning.TARGET_ABOVE_ENTRY,
        Step31ObservationWarning.NON_POSITIVE_REWARD,
    )


def test_target_and_stop_unavailable_remain_separate_advisory_facts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    target_missing = _observe(
        completed, _package(completed, prior_directional_swing_high=None)
    )
    assert target_missing.target_availability is Step31FactAvailability.UNAVAILABLE
    assert target_missing.stop_availability is Step31FactAvailability.AVAILABLE
    assert target_missing.risk_per_unit == Decimal("10.00")
    assert target_missing.reward_per_unit is None
    assert target_missing.risk_reward_state is Step31RiskRewardState.UNAVAILABLE
    assert target_missing.warnings == (Step31ObservationWarning.TARGET_UNAVAILABLE,)

    stop_missing = _observe(
        completed, _package(completed, governing_structural_low=None)
    )
    assert stop_missing.stop_availability is Step31FactAvailability.UNAVAILABLE
    assert stop_missing.target_availability is Step31FactAvailability.AVAILABLE
    assert stop_missing.risk_per_unit is None
    assert stop_missing.reward_per_unit == Decimal("20.00")
    assert stop_missing.warnings == (
        Step31ObservationWarning.STOP_UNAVAILABLE,
        Step31ObservationWarning.STRUCTURAL_GEOMETRY_WARNING,
    )
    assert stop_missing.severity is Step31WarningSeverity.AMBER

    base = _evidence(completed)
    entry_missing = _observe(
        completed,
        _package(
            completed,
            qualification_candle=replace(base.qualification_candle, completed=False),
        ),
    )
    assert entry_missing.entry_availability is Step31FactAvailability.UNAVAILABLE
    assert entry_missing.entry_authority_source is None
    assert entry_missing.risk_reward_state is Step31RiskRewardState.UNAVAILABLE
    assert Step31ObservationWarning.ENTRY_UNAVAILABLE in entry_missing.warnings


def test_hard_binding_staleness_and_execution_context_fail_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    requirement = completed.requirement
    handoff = _handoff(completed)
    evidence = _evidence(completed)
    context = _context(requirement.canonical_instrument)

    foreign = _package(completed, canonical_instrument="FOREIGN")
    with pytest.raises(Step31ObservationHardFailure, match="EVIDENCE_BINDING_INVALID"):
        construct_step31_observation(
            requirement, handoff, foreign,
            context, created_at=NOW,
        )
    stale = _package(
        completed,
        observation_boundary=evidence.observation_boundary.replace(microsecond=1),
    )
    with pytest.raises(Step31ObservationHardFailure, match="EVIDENCE_STALE"):
        construct_step31_observation(
            requirement, handoff, stale, context, created_at=NOW,
        )
    untrusted = replace(
        context,
        tick_size=None,
        lot_size=None,
        price_precision=None,
        status=InstrumentContextStatus.INCOMPLETE,
    )
    with pytest.raises(Step31ObservationHardFailure, match="EXECUTION_CONTEXT_UNTRUSTED"):
        construct_step31_observation(
            requirement, handoff, evidence, untrusted, created_at=NOW,
        )


def test_real_mcx_clone_is_red_observation_not_trade_or_risk_authority(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    boundary = completed.promotion.analysis_boundary
    base = _evidence(completed)
    candle = replace(
        base.qualification_candle,
        high=Decimal("3211.4"),
        low=Decimal("3100.0"),
    )
    evidence = _package(
        completed,
        qualification_candle=candle,
        governing_structural_low=_price("MCX-STOP", "2892.1", boundary),
        prior_directional_swing_high=_price("MCX-TARGET", "3023.7", boundary),
    )
    context = replace(
        _context(completed.requirement.canonical_instrument),
        tick_size=Decimal("0.1"),
        price_precision=1,
        exchange="MCX",
        segment="MCX",
        instrument_type="FUT",
    )
    observation = construct_step31_observation(
        completed.requirement, _handoff(completed), evidence, context, created_at=NOW
    )

    assert (observation.entry, observation.stop, observation.canonical_target) == (
        Decimal("3211.4"), Decimal("2892.1"), Decimal("3023.7")
    )
    assert observation.reward_per_unit == Decimal("-187.7")
    assert observation.severity is Step31WarningSeverity.RED
    assert observation.conventional_trade_plan_id is None
    sponsor = create_sponsor_observation_handoff(
        observation,
        risk_state="RISK_UNAVAILABLE",
        risk_evidence_identity=None,
    )
    assert sponsor.risk_state == "RISK_UNAVAILABLE"
    assert sponsor.conventional_trade_plan_id is None
    assert sponsor.warnings == observation.warnings


def test_observation_store_is_immutable_restart_safe_and_rejects_corruption(tmp_path) -> None:  # type: ignore[no-untyped-def]
    completed = _completed(tmp_path)
    record = _observe(completed, _evidence(completed), plan=True)
    store = LocalStep31ObservationStore(tmp_path / "observations")
    path = store.retain(record)
    assert store.retain(record) == path
    assert store.load_for_requirements((completed.requirement,)) == (record,)

    path.write_text(path.read_text().replace('"severity":"GREEN"', '"severity":"RED"'))
    with pytest.raises(ValueError, match="STORED_RECORD_INVALID"):
        store.load_for_requirements((completed.requirement,))
