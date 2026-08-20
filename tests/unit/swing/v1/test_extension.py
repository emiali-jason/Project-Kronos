from dataclasses import fields, replace
import copy
from datetime import timedelta
import inspect

import pytest

from kronos.swing.v1 import extension
from kronos.swing.v1.extension import (
    EXTENSION_AUTHORITY,
    EXTENSION_PIVOT_HIERARCHY_IDENTITY,
    EXTENSION_POLICY_IDENTITY,
    EXTENSION_POLICY_VERSION,
    EXTENSION_THRESHOLD_ATR,
    ExtensionAvailability,
    evaluate_completed_one_hour_extension,
    extension_native_condition_inputs,
)
from kronos.swing.v1.models import PivotCandidate, PivotKind, V1Direction
from kronos.swing.v1.mtf_facts import (
    CompletedOneHourAtrFact,
    FactualPivotSeries,
    FactualTimeframe,
    OneHourAtrAvailability,
    one_hour_atr_integrity_sha256,
)
from kronos.swing.v1.native_readiness import LevelAvailability
from kronos.swing.v1.native_review import build_native_review_requirements
from tests.unit.swing.v1.test_native_review import _evidence_run


def _atr(
    original: CompletedOneHourAtrFact,
    value: float | None,
) -> CompletedOneHourAtrFact:
    values = {
        item.name: getattr(original, item.name)
        for item in fields(original)
        if item.name != "integrity_sha256"
    }
    values.update({
        "availability": (
            OneHourAtrAvailability.AVAILABLE
            if value is not None
            else OneHourAtrAvailability.UNAVAILABLE
        ),
        "unavailable_reason": (
            None if value is not None else "INSUFFICIENT_COMPLETED_1H_HISTORY"
        ),
        "value": value,
    })
    return CompletedOneHourAtrFact(
        **values,  # type: ignore[arg-type]
        integrity_sha256=one_hour_atr_integrity_sha256(values),
    )


def _series(
    radius: int,
    hour,
    *,
    lows: tuple[float, ...],
    highs: tuple[float, ...],
) -> FactualPivotSeries:
    return FactualPivotSeries(
        f"FRACTAL_UNIQUE_EXTREME_RADIUS_{radius}",
        radius,
        tuple(
            PivotCandidate(
                PivotKind.HIGH,
                index,
                hour.source_timestamp - timedelta(hours=len(highs) - index),
                value,
            )
            for index, value in enumerate(highs)
        ),
        tuple(
            PivotCandidate(
                PivotKind.LOW,
                index,
                hour.source_timestamp - timedelta(hours=len(lows) - index),
                value,
            )
            for index, value in enumerate(lows)
        ),
    )


def _case(
    *,
    direction: V1Direction,
    close: float,
    radius_2: tuple[float, ...],
    radius_1: tuple[float, ...] = (),
    atr: float | None = 10.0,
):  # type: ignore[no-untyped-def]
    original_facts, original_run, probable = _evidence_run()
    instrument = original_facts.instrument(probable.canonical_instrument)
    hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    lows_1 = radius_1 if direction is V1Direction.LONG else ()
    highs_1 = radius_1 if direction is V1Direction.SHORT else ()
    lows_2 = radius_2 if direction is V1Direction.LONG else ()
    highs_2 = radius_2 if direction is V1Direction.SHORT else ()
    changed_hour = replace(
        hour,
        open=close,
        high=close + 1.0,
        low=max(0.0, close - 1.0),
        close=close,
        structural_measurements=(
            _series(1, hour, lows=lows_1, highs=highs_1),
            _series(2, hour, lows=lows_2, highs=highs_2),
        ),
    )
    assert instrument.one_hour_atr is not None
    changed_atr = _atr(instrument.one_hour_atr, atr)
    changed_instrument = replace(
        instrument,
        timeframes=tuple(
            changed_hour
            if item.timeframe is FactualTimeframe.ONE_HOUR
            else item
            for item in instrument.timeframes
        ),
        one_hour_atr=changed_atr,
    )
    facts = replace(
        original_facts,
        instruments=tuple(
            changed_instrument
            if item.canonical_instrument == probable.canonical_instrument
            else item
            for item in original_facts.instruments
        ),
    )
    changed_probable = replace(probable, direction=direction)
    run = replace(
        original_run,
        assessments=(changed_probable, *original_run.assessments[1:]),
    )
    requirement = build_native_review_requirements(run, facts)[0]
    return requirement, facts


def test_completed_one_hour_long_and_short_are_exact_mirrors() -> None:
    long_requirement, long_facts = _case(
        direction=V1Direction.LONG, close=120.0, radius_2=(100.0,)
    )
    short_requirement, short_facts = _case(
        direction=V1Direction.SHORT, close=80.0, radius_2=(100.0,)
    )

    long = evaluate_completed_one_hour_extension(long_requirement, long_facts)
    short = evaluate_completed_one_hour_extension(short_requirement, short_facts)

    assert long.directional_distance == short.directional_distance == 20.0
    assert long.extension_atr == short.extension_atr == 2.0
    assert long.materially_extended is short.materially_extended is False
    assert long.anchor_price == short.anchor_price == 100.0
    assert long.timeframe is short.timeframe is FactualTimeframe.ONE_HOUR


def test_radius_2_is_preferred_and_latest_pivot_in_series_is_selected() -> None:
    requirement, facts = _case(
        direction=V1Direction.LONG,
        close=120.0,
        radius_2=(80.0, 90.0),
        radius_1=(119.0,),
    )
    result = evaluate_completed_one_hour_extension(requirement, facts)

    assert result.selected_pivot_radius == 2
    assert result.anchor_price == 90.0
    assert result.pivot_definition_identity == "FRACTAL_UNIQUE_EXTREME_RADIUS_2"
    assert result.pivot_hierarchy_identity == EXTENSION_PIVOT_HIERARCHY_IDENTITY


def test_radius_1_fallback_and_no_directional_pivot_fail_closed() -> None:
    fallback_requirement, fallback_facts = _case(
        direction=V1Direction.SHORT,
        close=90.0,
        radius_2=(),
        radius_1=(110.0,),
    )
    missing_requirement, missing_facts = _case(
        direction=V1Direction.SHORT,
        close=90.0,
        radius_2=(),
        radius_1=(),
    )

    fallback = evaluate_completed_one_hour_extension(
        fallback_requirement, fallback_facts
    )
    missing = evaluate_completed_one_hour_extension(
        missing_requirement, missing_facts
    )

    assert fallback.selected_pivot_radius == 1
    assert fallback.anchor_price == 110.0
    assert missing.availability is ExtensionAvailability.UNAVAILABLE
    assert missing.unavailable_reason == "REQUIRED_DIRECTIONAL_1H_PIVOT_UNAVAILABLE"
    assert missing.materially_extended is None


@pytest.mark.parametrize(
    ("ratio", "expected"),
    ((1.99, False), (2.0, False), (2.000001, True)),
)
def test_exact_strict_materiality_boundary(ratio: float, expected: bool) -> None:
    requirement, facts = _case(
        direction=V1Direction.LONG,
        close=100.0 + ratio * 10.0,
        radius_2=(100.0,),
    )
    result = evaluate_completed_one_hour_extension(requirement, facts)

    assert result.extension_atr == pytest.approx(ratio)
    assert result.materially_extended is expected
    assert result.threshold_atr == EXTENSION_THRESHOLD_ATR


def test_negative_directional_distance_is_not_made_absolute() -> None:
    requirement, facts = _case(
        direction=V1Direction.LONG, close=99.0, radius_2=(100.0,)
    )
    result = evaluate_completed_one_hour_extension(requirement, facts)

    assert result.availability is ExtensionAvailability.UNAVAILABLE
    assert result.unavailable_reason == "DIRECTIONAL_DISTANCE_NEGATIVE"
    assert result.directional_distance == -1.0
    assert result.extension_atr is None
    assert result.materially_extended is None


@pytest.mark.parametrize("atr", (None, 0.0))
def test_missing_or_non_positive_e01_atr_fails_closed(atr: float | None) -> None:
    requirement, facts = _case(
        direction=V1Direction.LONG,
        close=120.0,
        radius_2=(100.0,),
        atr=atr,
    )
    result = evaluate_completed_one_hour_extension(requirement, facts)

    assert result.availability is ExtensionAvailability.UNAVAILABLE
    assert result.materially_extended is None
    assert result.atr_policy_identity == "KR-370-E01-COMPLETED-1H-ATR14-POLICY"


def test_incomplete_one_hour_source_fails_closed() -> None:
    requirement, facts = _case(
        direction=V1Direction.LONG, close=120.0, radius_2=(100.0,)
    )
    instrument = facts.instrument(requirement.canonical_instrument)
    hour = instrument.fact(FactualTimeframe.ONE_HOUR)
    changed_instrument = replace(
        instrument,
        timeframes=tuple(
            replace(item, source_interval="DAY")
            if item.timeframe is FactualTimeframe.ONE_HOUR
            else item
            for item in instrument.timeframes
        ),
    )
    changed = replace(
        facts,
        instruments=tuple(
            changed_instrument
            if item.canonical_instrument == requirement.canonical_instrument
            else item
            for item in facts.instruments
        ),
    )

    result = evaluate_completed_one_hour_extension(requirement, changed)

    assert result.availability is ExtensionAvailability.UNAVAILABLE
    assert result.unavailable_reason == "INCOMPLETE_1H_EVIDENCE"


def test_wrong_run_and_direction_bindings_fail_closed() -> None:
    requirement, facts = _case(
        direction=V1Direction.LONG, close=121.0, radius_2=(100.0,)
    )
    wrong_run = copy.deepcopy(facts)
    object.__setattr__(
        wrong_run, "run_identity", "SWING-RUN-FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
    )
    with pytest.raises(ValueError, match="EXTENSION_SAME_RUN_BINDING_INVALID"):
        evaluate_completed_one_hour_extension(requirement, wrong_run)

    fact = evaluate_completed_one_hour_extension(requirement, facts)
    wrong_direction = replace(
        requirement,
        thesis=replace(requirement.thesis, direction=V1Direction.SHORT),
    )
    with pytest.raises(ValueError, match="EXTENSION_NATIVE_INPUT_BINDING_INVALID"):
        extension_native_condition_inputs(fact, wrong_direction)


def test_tampered_e01_atr_integrity_fails_closed() -> None:
    requirement, facts = _case(
        direction=V1Direction.LONG, close=121.0, radius_2=(100.0,)
    )
    instrument = facts.instrument(requirement.canonical_instrument)
    assert instrument.one_hour_atr is not None
    tampered_atr = copy.deepcopy(instrument.one_hour_atr)
    object.__setattr__(tampered_atr, "value", 11.0)
    changed_instrument = replace(instrument, one_hour_atr=tampered_atr)
    changed = replace(
        facts,
        instruments=tuple(
            changed_instrument
            if item.canonical_instrument == requirement.canonical_instrument
            else item
            for item in facts.instruments
        ),
    )

    with pytest.raises(ValueError, match="EXTENSION_ATR_INTEGRITY_INVALID"):
        evaluate_completed_one_hour_extension(requirement, changed)


def test_native_input_is_exact_bound_and_unavailable_remains_explicit() -> None:
    available_requirement, available_facts = _case(
        direction=V1Direction.LONG, close=121.0, radius_2=(100.0,)
    )
    unavailable_requirement, unavailable_facts = _case(
        direction=V1Direction.LONG, close=121.0, radius_2=()
    )
    available = evaluate_completed_one_hour_extension(
        available_requirement, available_facts
    )
    unavailable = evaluate_completed_one_hour_extension(
        unavailable_requirement, unavailable_facts
    )

    projected = extension_native_condition_inputs(available, available_requirement)
    unavailable_projected = extension_native_condition_inputs(
        unavailable, unavailable_requirement
    )
    assert projected.extension is not None
    assert projected.extension.materially_beyond_recent_structure
    assert projected.extension.structural_context.level_availability is LevelAvailability.AVAILABLE
    assert unavailable_projected.extension is not None
    assert not unavailable_projected.extension.materially_beyond_recent_structure
    assert (
        unavailable_projected.extension.structural_context.level_availability
        is LevelAvailability.LEVEL_UNAVAILABLE
    )
    wrong = replace(
        available_requirement,
        thesis=replace(
            available_requirement.thesis,
            native_assessment_sha256="f" * 64,
        ),
    )
    with pytest.raises(ValueError, match="EXTENSION_NATIVE_INPUT_BINDING_INVALID"):
        extension_native_condition_inputs(available, wrong)


def test_fact_integrity_policy_and_authority_are_immutable() -> None:
    requirement, facts = _case(
        direction=V1Direction.SHORT, close=79.0, radius_2=(100.0,)
    )
    result = evaluate_completed_one_hour_extension(requirement, facts)

    assert result.policy_identity == EXTENSION_POLICY_IDENTITY
    assert result.policy_version == EXTENSION_POLICY_VERSION
    assert result.authority == EXTENSION_AUTHORITY
    assert result.provenance
    with pytest.raises(
        ValueError, match="COMPLETED_ONE_HOUR_EXTENSION_FACT_INVALID"
    ):
        replace(result, materially_extended=False)


def test_e03_has_no_sponsor_watch_intraday_pine_or_execution_authority() -> None:
    source = inspect.getsource(extension)
    forbidden = (
        "kronos.application.intraday",
        "BUY_READY",
        "SELL_READY",
        "POTENTIAL_SETUP",
        "NO_SETUP",
        "Telegram",
        "OpenAI",
        "KRONOS_FUTURES",
        "KRONOS_NSE",
    )
    assert all(item not in source for item in forbidden)
    assert EXTENSION_AUTHORITY == "DETERMINISTIC_NUMERICAL_FACT_ONLY"
