from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timedelta
from decimal import Decimal
import json
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.candles import (
    expected_candle_boundaries,
    reconcile_provider_candles,
)
from kronos.intraday.contracts import (
    DataAvailability,
    IntradayInstrumentReference,
    IntradayTimeframe,
    SourceProvenance,
    create_intraday_run,
)
from kronos.intraday.structure import (
    ExplicitMoveDefinition,
    ExplicitRangeDefinition,
    FactualDirection,
    StructuralEvidence,
    StructuralFactType,
    barriers_from_slice1e,
    build_structural_evidence,
    project_structural_evidence,
)
from kronos.intraday.structure_persistence import LocalStructuralEvidenceStore
from kronos.market.schedule import MarketDaySchedule
from kronos.provider.contracts.market_data import HistoricalCandle
from tests.unit.intraday.test_context import _context


IST = ZoneInfo("Asia/Kolkata")
ROWS = (
    (100, 102, 99, 101),
    (101, 104, 100, 103),
    (103, 107, 102, 106),
    (106, 106, 101, 103),
    (103, 104, 97, 98),
    (98, 102, 98, 98.5),
    (101, 106, 100, 105),
    (105, 108, 104, 107),
    (107, 108, 104, 104),
    (103, 110, 101, 109),
)


def _authority(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
    *,
    timeframe: IntradayTimeframe = IntradayTimeframe.FIFTEEN_MINUTES,
    omit_index: int | None = None,
):
    boundaries = expected_candle_boundaries(schedule, timeframe)
    supplied_count = min(len(ROWS), len(boundaries))
    supplied = tuple(
        HistoricalCandle(
            boundaries[index].start, *(float(value) for value in row), 10_000 + index
        )
        for index, row in enumerate(ROWS[:supplied_count])
        if index != omit_index
    )
    if timeframe is IntradayTimeframe.DAILY:
        observed = boundaries[0].end
    else:
        current = boundaries[supplied_count - 1]
        observed = current.start + (current.end - current.start) / 2
    reconciliation = reconcile_provider_candles(
        instrument=instrument, timeframe=timeframe, schedule=schedule,
        provider_candles=supplied, observed_at=observed, provenance=provenance,
    )
    run = create_intraday_run(
        created_at=observed - timedelta(minutes=1), observation_boundary=observed
    )
    return run, reconciliation


def _barriers(
    instrument: IntradayInstrumentReference,
    provenance: SourceProvenance,
):
    previous = HistoricalCandle(
        datetime(2026, 8, 14, 0, 0, tzinfo=IST),
        100.0, 103.0, 98.0, 102.0, 1_000_000,
    )
    context = _context(
        instrument, provenance, candles=(previous,), current_price=Decimal("103")
    )
    return context, barriers_from_slice1e(context)


def _full_evidence(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
):
    run, reconciliation = _authority(instrument, schedule, provenance)
    context, barriers = _barriers(instrument, provenance)
    candles = reconciliation.structural_candles
    explicit_range = ExplicitRangeDefinition(
        range_id="OPENING-EXPLICIT-RANGE",
        high=Decimal("104"), low=Decimal("99"),
        start_boundary=candles[0].boundary.start,
        end_boundary=candles[1].boundary.end,
    )
    move = ExplicitMoveDefinition(
        move_id="OBSERVED-UP-MOVE", direction=FactualDirection.UP,
        start_candle_id=candles[0].candle_id,
        end_candle_id=candles[2].candle_id,
        retracement_end_candle_id=candles[3].candle_id,
    )
    evidence = build_structural_evidence(
        run=run, reconciliation=reconciliation, barriers=barriers,
        ranges=(explicit_range,), moves=(move,),
    )
    return context, reconciliation, evidence


def _facts(evidence: StructuralEvidence, fact_type: StructuralFactType):
    return tuple(item for item in evidence.facts if item.fact_type is fact_type)


def _value(fact, name: str) -> Decimal:
    return next(item.value for item in fact.values if item.name == name)


def test_completed_candle_relationships_capture_rising_falling_and_exact_equality(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    _, _, evidence = _full_evidence(instrument, schedule, provenance)

    assert _facts(evidence, StructuralFactType.HIGHER_HIGH)
    assert _facts(evidence, StructuralFactType.LOWER_HIGH)
    assert _facts(evidence, StructuralFactType.HIGHER_LOW)
    assert _facts(evidence, StructuralFactType.LOWER_LOW)
    assert _facts(evidence, StructuralFactType.EQUAL_HIGH)
    assert _facts(evidence, StructuralFactType.EQUAL_LOW)


def test_candidate_local_high_and_low_use_only_immediate_neighbour_relations(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    _, reconciliation, evidence = _full_evidence(instrument, schedule, provenance)
    highs = _facts(evidence, StructuralFactType.CANDIDATE_LOCAL_HIGH)
    lows = _facts(evidence, StructuralFactType.CANDIDATE_LOCAL_LOW)

    assert any(_value(item, "pivot_price") == Decimal("107.0") for item in highs)
    assert any(_value(item, "pivot_price") == Decimal("97.0") for item in lows)
    high = next(item for item in highs if _value(item, "pivot_price") == Decimal("107.0"))
    assert high.policy_version == "IMMEDIATE_NEIGHBOUR_RELATION_V1"
    assert len(high.source_candle_ids) == 3
    assert high.confirmation_boundary == reconciliation.structural_candles[3].boundary.end


def test_explicit_range_measures_boundaries_breaks_and_returns_without_qualification(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    _, _, evidence = _full_evidence(instrument, schedule, provenance)
    summary = _facts(evidence, StructuralFactType.RANGE_SUMMARY)[0]

    assert _value(summary, "range_high") == Decimal("104")
    assert _value(summary, "range_low") == Decimal("99")
    assert _value(summary, "range_width") == Decimal("5")
    assert _value(summary, "highest_high") == Decimal("104.0")
    assert _value(summary, "lowest_low") == Decimal("99.0")
    assert _facts(evidence, StructuralFactType.BOUNDARY_BREAK_ABOVE)
    assert _facts(evidence, StructuralFactType.BOUNDARY_BREAK_BELOW)
    assert len(_facts(evidence, StructuralFactType.RETURN_INSIDE)) >= 2


def test_explicit_move_and_retracement_are_measurements_not_validity_decisions(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    _, _, evidence = _full_evidence(instrument, schedule, provenance)
    move = _facts(evidence, StructuralFactType.DIRECTIONAL_MOVE_MEASUREMENT)[0]
    retracement = _facts(evidence, StructuralFactType.RETRACEMENT_MEASUREMENT)[0]

    assert move.direction is FactualDirection.UP
    assert _value(move, "move_magnitude") == Decimal("8.0")
    assert _value(move, "candle_count") == Decimal(3)
    assert _value(retracement, "retracement_magnitude") == Decimal("6.0")
    assert _value(retracement, "retracement_percentage") == Decimal("75.00")


def test_unresolvable_explicit_move_is_preserved_as_unavailable_not_inferred(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    run, reconciliation = _authority(instrument, schedule, provenance)
    definition = ExplicitMoveDefinition(
        move_id="MISSING-END-MOVE", direction=FactualDirection.UP,
        start_candle_id=reconciliation.structural_candles[0].candle_id,
        end_candle_id="GOVERNED-CANDLE-NOT-PRESENT",
    )
    evidence = build_structural_evidence(
        run=run, reconciliation=reconciliation, moves=(definition,)
    )
    fact = _facts(evidence, StructuralFactType.DIRECTIONAL_MOVE_MEASUREMENT)[0]

    assert fact.availability is DataAvailability.UNAVAILABLE
    assert dict((item.name, item.value) for item in fact.attributes)["unavailability_reason"] == (
        "SOURCE_CANDLE_UNAVAILABLE"
    )


def test_slice1e_barriers_preserve_lineage_and_exact_behaviour_sequences(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    _, _, evidence = _full_evidence(instrument, schedule, provenance)
    by_name = {item.reference_name: item for item in evidence.barriers}
    referenced_names = {
        next(attribute.value for attribute in fact.attributes if attribute.name == "reference_name")
        for fact in evidence.facts
        if fact.source_reference_ids
    }

    assert {"PDH", "PDL", "P", "R1", "R2", "R3", "R4", "S1", "S2", "S3", "S4",
            "CPR_UPPER", "CPR_LOWER", "CPR_PIVOT"} <= set(by_name)
    assert by_name["R1"].price == Decimal("104.0")
    assert by_name["S1"].price == Decimal("99.0")
    assert by_name["R1"].origin_session_id == "NSE-20260814"
    assert {"R1", "S1", "PDH", "PDL", "CPR_UPPER", "CPR_LOWER"} <= referenced_names
    assert _facts(evidence, StructuralFactType.CLOSE_AT_BOUNDARY)
    assert _facts(evidence, StructuralFactType.EXACT_BOUNDARY_TOUCH)
    assert _facts(evidence, StructuralFactType.CLOSE_BACK_THROUGH)
    assert _facts(evidence, StructuralFactType.RETEST_FROM_ABOVE)
    assert _facts(evidence, StructuralFactType.RETEST_FROM_BELOW)
    assert all("SUPPORT" not in item.fact_type.value and "RESISTANCE" not in item.fact_type.value
               for item in evidence.facts)


def test_incomplete_current_candle_has_no_structural_authority(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    _, reconciliation, evidence = _full_evidence(instrument, schedule, provenance)
    incomplete = reconciliation.observations[-1]

    assert incomplete not in reconciliation.structural_candles
    assert incomplete.candle_id not in evidence.governed_candle_ids
    assert all(incomplete.candle_id not in item.source_candle_ids for item in evidence.facts)


def test_incomplete_reconciliation_fails_closed_without_structural_facts(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    run, reconciliation = _authority(instrument, schedule, provenance, omit_index=2)
    evidence = build_structural_evidence(run=run, reconciliation=reconciliation)

    assert evidence.availability is DataAvailability.INCOMPLETE
    assert evidence.facts == ()
    assert evidence.governed_candle_ids == ()


def test_structural_persistence_is_idempotent_restart_safe_and_tamper_evident(
    tmp_path,
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    _, _, evidence = _full_evidence(instrument, schedule, provenance)
    store = LocalStructuralEvidenceStore(tmp_path / "structure")
    store.retain(evidence)
    store.retain(evidence)

    loaded = LocalStructuralEvidenceStore(store.root).load(
        run_id=evidence.run.run_id, mapping_identity=instrument.mapping_identity,
        trading_date=evidence.trading_date.isoformat(), timeframe=evidence.timeframe,
        evidence_id=evidence.evidence_id,
    )
    assert loaded == evidence

    path = next(store.root.rglob("*.json"))
    document = json.loads(path.read_bytes())
    document["evidence"]["facts"][0]["fact"]["values"][0]["value"] = "999"
    path.write_text(json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True))
    with pytest.raises(ValueError, match="UNAVAILABLE_OR_INVALID"):
        store.load(
            run_id=evidence.run.run_id, mapping_identity=instrument.mapping_identity,
            trading_date=evidence.trading_date.isoformat(), timeframe=evidence.timeframe,
            evidence_id=evidence.evidence_id,
        )


def test_projection_groups_timeframes_and_carries_slice1e_context_without_conclusion(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    context, _, fifteen = _full_evidence(instrument, schedule, provenance)
    other_evidence = []
    for timeframe in (
        IntradayTimeframe.DAILY,
        IntradayTimeframe.ONE_HOUR,
        IntradayTimeframe.FIVE_MINUTES,
    ):
        run, reconciliation = _authority(
            instrument, schedule, provenance, timeframe=timeframe
        )
        other_evidence.append(build_structural_evidence(run=run, reconciliation=reconciliation))
    projection = project_structural_evidence(
        (*other_evidence, fifteen), slice1e_context=context
    )

    assert tuple(item[0] for item in projection.evidence_by_timeframe) == (
        IntradayTimeframe.DAILY, IntradayTimeframe.ONE_HOUR,
        IntradayTimeframe.FIFTEEN_MINUTES, IntradayTimeframe.FIVE_MINUTES,
    )
    assert projection.slice1e_context is context
    assert projection.canonical_instrument_id == instrument.canonical_instrument_id


def test_structural_contract_cannot_express_trading_consequences(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    _, _, evidence = _full_evidence(instrument, schedule, provenance)
    contract_fields = {item.name for item in fields(StructuralEvidence)}
    forbidden = {
        "native_candidate_state", "probable", "discovery_result", "readiness",
        "entry", "stop", "invalidation", "target", "risk_reward_eligibility",
        "risk", "paper_eligibility", "live_eligibility",
    }

    assert contract_fields.isdisjoint(forbidden)
    assert all(item.fact_type.value not in {
        "BREAKOUT_VALID", "PULLBACK_VALID", "SETUP_READY",
        "SUPPORT_CONFIRMED", "RESISTANCE_CONFIRMED",
    } for item in evidence.facts)
