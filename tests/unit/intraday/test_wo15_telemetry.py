from __future__ import annotations

from dataclasses import fields, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo15 import (
    Wo15ProgressionSemantics,
    Wo15TimingState,
    bind_completed_five_minute_evidence,
)
from kronos.intraday.wo15_telemetry import (
    WO15_ATR14_IDENTITY,
    WO15_ATR14_METHOD,
    WO15_ATR14_PERIOD,
    WO15_EXTENSION_SEVERITY,
    WO15_TELEMETRY_AUTHORITY,
    WO15_TELEMETRY_IDENTITY,
    Wo15AtrUnavailableReason,
    Wo15ResearchLocality,
    Wo15ResearchRole,
    Wo15TelemetryAvailability,
    Wo15TelemetryError,
    bind_wo15_telemetry_candle,
    build_wo15_research_telemetry,
    calculate_wo15_atr14,
    create_wo15_research_reference,
)
from kronos.intraday.wo12_k5_foundation import Wo12SetupFamily

from .test_wo15_timing import _candle, _case, _evaluate
from .test_wo15_contracts import _mcx_wo13, _session as _contract_session


def _bound(
    admission, session, source, evidence, index: int  # type: ignore[no-untyped-def]
):
    return bind_wo15_telemetry_candle(
        source=source,
        evidence=evidence,
        admission=admission,
        session=session,
        sequence_index=index,
    )


def _telemetry_case(
    tmp_path,
    *,
    direction: SemanticDirection = SemanticDirection.LONG,
    final_close: str | None = None,
    setup: Wo12SetupFamily = Wo12SetupFamily.PULLBACK_CONTINUATION,
):  # type: ignore[no-untyped-def]
    admission, session = _case(tmp_path, direction=direction, setup=setup)
    prior = []
    for index, minute in enumerate(range(5, 75, 5)):
        source, evidence = _candle(
            admission,
            session,
            minute=minute,
            close="100",
            high="102",
            low="98",
        )
        prior.append(_bound(admission, session, source, evidence, index))
    close = final_close or ("101" if direction is SemanticDirection.LONG else "99")
    source, evidence, _, result = _evaluate(
        admission,
        session,
        minute=75,
        close=close,
        semantics=Wo15ProgressionSemantics.ALIGNED,
        high="102",
        low="98",
    )
    measurement = _bound(admission, session, source, evidence, 14)
    return admission, session, result, measurement, tuple((*prior, measurement))


def _build(case, *, atr_history=None, cycle_history=None, references=()):  # type: ignore[no-untyped-def]
    admission, session, result, measurement, history = case
    return build_wo15_research_telemetry(
        admission=admission,
        session=session,
        timing_result=result,
        measurement=measurement,
        atr_history=history if atr_history is None else atr_history,
        cycle_history=(measurement,) if cycle_history is None else cycle_history,
        research_references=references,
    )


def _reference(case, role, *, available=True, facts=(("state", "OBSERVED"),)):
    admission, _, _, measurement, _ = case
    return create_wo15_research_reference(
        role=role,
        locality=Wo15ResearchLocality.LOCAL_ANALYTICAL_SUBJECT,
        availability=(
            Wo15TelemetryAvailability.AVAILABLE
            if available else Wo15TelemetryAvailability.UNAVAILABLE
        ),
        canonical_subject_identity=admission.canonical_subject_identity,
        instrument_identity=admission.instrument_identity,
        actual_contract_identity=admission.actual_contract_identity,
        roll_lineage_identity=admission.roll_lineage_identity,
        observation_boundary=measurement.candle_end,
        facts=facts if available else (),
        source_identities=(f"SOURCE-{role.value}",) if available else (),
        source_integrities=(f"INTEGRITY-{role.value}",) if available else (),
    )


def test_contract_identity_authority_and_negative_authorities(tmp_path) -> None:
    telemetry = _build(_telemetry_case(tmp_path))
    assert WO15_TELEMETRY_IDENTITY.endswith("RESEARCH-TELEMETRY-V1")
    assert telemetry.authority == WO15_TELEMETRY_AUTHORITY
    assert WO15_EXTENSION_SEVERITY == "UNCLASSIFIED"
    assert not any((
        telemetry.timing_decision_authority,
        telemetry.geometry_authority,
        telemetry.risk_authority,
        telemetry.sponsor_decision_authority,
        telemetry.execution_authority,
        telemetry.broker_authority,
    ))


@pytest.mark.parametrize(
    ("direction", "close", "expected"),
    (
        (SemanticDirection.LONG, "101.25", Decimal("1.25")),
        (SemanticDirection.SHORT, "98.75", Decimal("1.25")),
        (SemanticDirection.LONG, "98.75", Decimal("-1.25")),
        (SemanticDirection.SHORT, "101.25", Decimal("-1.25")),
        (SemanticDirection.LONG, "100", Decimal("0")),
    ),
)
def test_signed_and_absolute_extension_use_completed_close_and_immutable_entry(
    tmp_path, direction, close, expected
) -> None:
    case = _telemetry_case(tmp_path, direction=direction, final_close=close)
    telemetry = _build(case)
    assert telemetry.entry_reference == Decimal("100")
    assert telemetry.completed_five_minute_close == Decimal(close)
    assert telemetry.directional_extension == expected
    assert telemetry.absolute_extension == abs(Decimal(close) - Decimal("100"))
    assert telemetry.timing_state_observed is case[2].current_state


def test_wilder_rma_atr14_seed_and_update_are_exact_decimal(tmp_path) -> None:
    case = _telemetry_case(tmp_path)
    admission, session, _, measurement, history = case
    atr = calculate_wo15_atr14(
        admission=admission,
        session=session,
        history=history,
        observation_boundary=measurement.candle_end,
    )
    assert atr.schema_identity == WO15_ATR14_IDENTITY
    assert atr.method == WO15_ATR14_METHOD
    assert atr.period == WO15_ATR14_PERIOD
    assert atr.value == Decimal("4")
    assert _build(case).normalized_directional_extension == Decimal("0.25")

    source, evidence = _candle(
        admission, session, minute=80, close="103", high="106", low="98"
    )
    later = _bound(admission, session, source, evidence, 15)
    updated = calculate_wo15_atr14(
        admission=admission,
        session=session,
        history=(*history, later),
        observation_boundary=later.candle_end,
    )
    assert updated.value == (Decimal("4") * Decimal(13) + Decimal("8")) / Decimal(14)


def test_atr_unavailable_keeps_raw_extension_available(tmp_path) -> None:
    case = _telemetry_case(tmp_path)
    telemetry = _build(case, atr_history=(case[3],))
    assert telemetry.atr14.availability is Wo15TelemetryAvailability.UNAVAILABLE
    assert telemetry.atr14.unavailable_reason is Wo15AtrUnavailableReason.INSUFFICIENT_HISTORY
    assert telemetry.directional_extension == Decimal("1")
    assert telemetry.absolute_extension == Decimal("1")
    assert telemetry.normalized_directional_extension is None
    assert telemetry.normalized_extension_availability is Wo15TelemetryAvailability.UNAVAILABLE


def test_zero_atr_is_unavailable_and_history_gap_is_not_shortened(tmp_path) -> None:
    case = _telemetry_case(tmp_path, final_close="100")
    admission, session, _, _, _ = case
    flat = []
    for index, minute in enumerate(range(5, 75, 5)):
        source, evidence = _candle(
            admission, session, minute=minute, close="100", high="100", low="100"
        )
        flat.append(_bound(admission, session, source, evidence, index))
    source, evidence, _, result = _evaluate(
        admission,
        session,
        minute=75,
        close="100",
        semantics=Wo15ProgressionSemantics.ALIGNED,
        high="100",
        low="100",
    )
    flat.append(_bound(admission, session, source, evidence, 14))
    telemetry = build_wo15_research_telemetry(
        admission=admission,
        session=session,
        timing_result=result,
        measurement=flat[-1],
        atr_history=flat,
        cycle_history=(flat[-1],),
    )
    assert telemetry.atr14.unavailable_reason is Wo15AtrUnavailableReason.NON_POSITIVE_ATR
    extended = []
    for index, minute in enumerate(range(0, 80, 5)):
        source, evidence = _candle(
            admission, session, minute=minute, close="100", high="102", low="98"
        )
        extended.append(_bound(admission, session, source, evidence, index))
    broken = tuple((*extended[:7], *extended[8:]))
    atr = calculate_wo15_atr14(
        admission=admission,
        session=session,
        history=broken,
        observation_boundary=case[3].candle_end,
    )
    assert atr.unavailable_reason is Wo15AtrUnavailableReason.HISTORY_INCOMPLETE


def test_excursion_path_and_explicit_bar_latency(tmp_path) -> None:
    case = _telemetry_case(tmp_path)
    admission, session, _, _, atr_history = case
    cycle = []
    previous = None
    for index, (minute, close) in enumerate(((65, "99"), (70, "100"), (75, "101"))):
        source, evidence, _, result = _evaluate(
            admission,
            session,
            minute=minute,
            close=close,
            semantics=Wo15ProgressionSemantics.ALIGNED,
            previous=previous,
            high="102",
            low="98",
        )
        cycle.append(_bound(admission, session, source, evidence, index))
        previous = result
    telemetry = build_wo15_research_telemetry(
        admission=admission,
        session=session,
        timing_result=result,
        measurement=cycle[-1],
        atr_history=atr_history,
        cycle_history=cycle,
    )
    assert telemetry.maximum_favourable_extension == Decimal("1")
    assert telemetry.maximum_adverse_distance == Decimal("1")
    assert telemetry.maximum_extension_before_qualification == Decimal("1")
    assert telemetry.qualification_path is result.qualification_path
    assert telemetry.latency.bars_first_evaluation_to_qualification == 2
    assert telemetry.latency.bars_first_evaluation_to_interaction == 0


def test_partial_context_references_and_wo14_are_non_consequential(tmp_path) -> None:
    case = _telemetry_case(tmp_path)
    before = (case[2].result_identity, case[2].current_state, case[2].qualification_path)
    references = (
        _reference(case, Wo15ResearchRole.VOLUME_5M),
        _reference(case, Wo15ResearchRole.RSI14_5M, available=False),
        _reference(case, Wo15ResearchRole.SMA_RAILWAY_5M),
        _reference(case, Wo15ResearchRole.LEVEL_CONTEXT),
        _reference(case, Wo15ResearchRole.SESSION_PHASE),
        _reference(case, Wo15ResearchRole.WO14_AUDIT_CONTEXT,
                   facts=(("risk_state", "RISK_ALERT"),)),
    )
    telemetry = _build(case, references=references)
    assert len(telemetry.research_references) == 6
    assert telemetry.research_references[1].availability is Wo15TelemetryAvailability.UNAVAILABLE
    assert (case[2].result_identity, case[2].current_state, case[2].qualification_path) == before
    without_risk = _build(case, references=references[:-1])
    assert without_risk.timing_state_observed is telemetry.timing_state_observed


def test_reference_market_context_is_separate_and_cannot_supply_local_atr(tmp_path) -> None:
    case = _telemetry_case(tmp_path)
    reference = create_wo15_research_reference(
        role=Wo15ResearchRole.REFERENCE_MARKET_CONTEXT,
        locality=Wo15ResearchLocality.SEPARATE_REFERENCE_CONTEXT,
        availability=Wo15TelemetryAvailability.AVAILABLE,
        canonical_subject_identity="COMEX-GOLD-REFERENCE",
        observation_boundary=case[3].candle_end,
        facts=(("relationship", "OBSERVED"),),
        source_identities=("REFERENCE-SOURCE",),
        source_integrities=("REFERENCE-INTEGRITY",),
    )
    telemetry = _build(case, atr_history=(case[3],), references=(reference,))
    assert telemetry.research_references == (reference,)
    assert telemetry.atr14.availability is Wo15TelemetryAvailability.UNAVAILABLE


def test_direct_and_retest_resumption_paths_are_preserved_without_ranking(tmp_path) -> None:
    direct = _telemetry_case(tmp_path / "direct", setup=Wo12SetupFamily.RANGE_BREAKOUT)
    direct_telemetry = _build(direct)
    assert direct_telemetry.qualification_path.value == "DIRECT_ACCEPTANCE"

    admission, session = _case(
        tmp_path / "retest", setup=Wo12SetupFamily.RANGE_BREAKOUT
    )
    observations = []
    previous = None
    inputs = (
        (5, "100", "101", "99.5", Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING),
        (10, "100.5", "101", "100.1", Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING),
        (15, "100", "101", "99.5", Wo15ProgressionSemantics.NON_DIRECTIONAL_FORMING),
        (20, "101.01", "102", "100.5", Wo15ProgressionSemantics.ALIGNED),
    )
    for index, (minute, close, high, low, semantics) in enumerate(inputs):
        source, evidence, _, result = _evaluate(
            admission, session, minute=minute, close=close, high=high, low=low,
            semantics=semantics, previous=previous,
        )
        observations.append(_bound(admission, session, source, evidence, index))
        previous = result
    telemetry = build_wo15_research_telemetry(
        admission=admission, session=session, timing_result=result,
        measurement=observations[-1], atr_history=(observations[-1],),
        cycle_history=observations,
    )
    assert telemetry.qualification_path.value == "RETEST_RESUMPTION"
    assert telemetry.retest_occurred


def test_mcx_telemetry_preserves_exact_contract_and_roll_lineage(tmp_path) -> None:
    *_, admission = _mcx_wo13(tmp_path)
    session = _contract_session(admission)
    source, evidence, _, result = _evaluate(
        admission, session, minute=5, close="101",
        semantics=Wo15ProgressionSemantics.ALIGNED, high="102", low="98",
    )
    measurement = _bound(admission, session, source, evidence, 0)
    telemetry = build_wo15_research_telemetry(
        admission=admission, session=session, timing_result=result,
        measurement=measurement, atr_history=(measurement,),
        cycle_history=(measurement,),
    )
    assert telemetry.actual_contract_identity == admission.actual_contract_identity
    assert telemetry.roll_lineage_identity == admission.roll_lineage_identity
    assert telemetry.market_family.value == "MCX"


def test_identity_is_deterministic_and_material_facts_change_it(tmp_path) -> None:
    case = _telemetry_case(tmp_path)
    first = _build(case)
    second = _build(case)
    assert first.telemetry_identity == second.telemetry_identity
    changed_case = _telemetry_case(tmp_path / "changed", final_close="101.5")
    changed = _build(changed_case)
    assert first.telemetry_identity != changed.telemetry_identity


def test_corruption_fails_closed_without_altering_timing_result(tmp_path) -> None:
    case = _telemetry_case(tmp_path)
    telemetry = _build(case)
    with pytest.raises(Wo15TelemetryError, match="WO15_RESEARCH_TELEMETRY_INVALID"):
        replace(telemetry, directional_extension=Decimal("999"))
    assert case[2].current_state is Wo15TimingState.TIMING_QUALIFIED


def test_cross_plan_cycle_boundary_and_local_reference_are_rejected(tmp_path) -> None:
    case_a = _telemetry_case(tmp_path / "a")
    case_b = _telemetry_case(tmp_path / "b", direction=SemanticDirection.SHORT)
    with pytest.raises(Wo15TelemetryError, match="LINEAGE_MISMATCH"):
        build_wo15_research_telemetry(
            admission=case_a[0], session=case_a[1], timing_result=case_b[2],
            measurement=case_a[3], atr_history=case_a[4], cycle_history=(case_a[3],)
        )

    result = case_a[2]
    forged = object.__new__(type(result))
    for field in fields(result):
        object.__setattr__(
            forged, field.name,
            "FOREIGN-CYCLE" if field.name == "timing_cycle_id" else getattr(result, field.name)
        )
    with pytest.raises(Wo15TelemetryError, match="LINEAGE_MISMATCH"):
        build_wo15_research_telemetry(
            admission=case_a[0], session=case_a[1], timing_result=forged,
            measurement=case_a[3], atr_history=case_a[4], cycle_history=(case_a[3],)
        )

    foreign = create_wo15_research_reference(
        role=Wo15ResearchRole.VOLUME_5M,
        locality=Wo15ResearchLocality.LOCAL_ANALYTICAL_SUBJECT,
        availability=Wo15TelemetryAvailability.AVAILABLE,
        canonical_subject_identity="FOREIGN-SUBJECT",
        instrument_identity="FOREIGN-INSTRUMENT",
        observation_boundary=case_a[3].candle_end,
        facts=(("state", "OBSERVED"),),
        source_identities=("FOREIGN-SOURCE",),
        source_integrities=("FOREIGN-INTEGRITY",),
    )
    with pytest.raises(Wo15TelemetryError, match="REFERENCE_LINEAGE_MISMATCH"):
        _build(case_a, references=(foreign,))

    later_source, later_evidence = _candle(
        case_a[0], case_a[1], minute=80, close="102", high="103", low="99"
    )
    later = _bound(case_a[0], case_a[1], later_source, later_evidence, 15)
    with pytest.raises(Wo15TelemetryError, match="LINEAGE_MISMATCH"):
        build_wo15_research_telemetry(
            admission=case_a[0], session=case_a[1], timing_result=case_a[2],
            measurement=later, atr_history=(*case_a[4], later), cycle_history=(later,)
        )


def test_contract_and_roll_mismatch_rejected_at_candle_adapter(tmp_path) -> None:
    admission, session, _, _, _ = _telemetry_case(tmp_path)
    source, _ = _candle(admission, session, minute=80, close="101")
    wrong = bind_completed_five_minute_evidence(
        source=source,
        market_family=admission.market_family,
        instrument_identity="FOREIGN-INSTRUMENT",
        actual_contract_identity=admission.actual_contract_identity,
        roll_lineage_identity=admission.roll_lineage_identity,
    )
    with pytest.raises(Wo15TelemetryError, match="LINEAGE_MISMATCH"):
        bind_wo15_telemetry_candle(
            source=source, evidence=wrong, admission=admission, session=session,
            sequence_index=15,
        )


def test_no_provider_persistence_runtime_or_browser_imports() -> None:
    import kronos.intraday.wo15_telemetry as module

    names = set(module.__dict__)
    assert not any(name.startswith(("Kite", "Browser", "Runtime", "Repository")) for name in names)
