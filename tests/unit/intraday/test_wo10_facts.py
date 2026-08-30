from __future__ import annotations

from dataclasses import fields, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.candles import expected_candle_boundaries, reconcile_provider_candles
from kronos.intraday.context import build_slice1e_context
from kronos.intraday.contracts import (
    DataAvailability,
    IntradayInstrumentReference,
    IntradayTimeframe,
    SourceProvenance,
    create_intraday_run,
    instrument_mapping_identity,
)
from kronos.intraday.historical_semantic import (
    SemanticEvidenceError,
    create_governed_historical_candle_payload,
)
from kronos.intraday.structure import (
    StructuralFactType,
    barriers_from_slice1e,
    build_structural_evidence,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import Wo10ContractError
from kronos.intraday.wo10_evidence import create_wo10_common_fact_bindings_from_facts
from kronos.intraday.wo10_facts import (
    WO10_RSI_CALCULATION_IDENTITY,
    WO10_SMA_CALCULATION_IDENTITY,
    WO10_VOLUME_LOOKBACK_IDENTITY,
    Wo10ExactChange,
    Wo10PriceRelationship,
    Wo10RecentSeparation,
    Wo10RsiCondition,
    Wo10SessionPositionedCandle,
    Wo10SmaSlope,
    Wo10SmaStack,
    bind_wo10_event_volume,
    build_wo10_rsi_fact,
    build_wo10_same_time_volume_fact,
    build_wo10_sma_facts,
    build_wo10_structural_location_facts,
    build_wo10_volume_fact,
    classify_wo10_rsi,
    create_wo10_candle_series,
)
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.provider.contracts.market_data import HistoricalCandle


IST = ZoneInfo("Asia/Kolkata")
BOUNDARY = datetime(2026, 8, 30, 12, 0, tzinfo=IST)
START = datetime(2026, 1, 1, 9, 15, tzinfo=IST)


def _instrument(
    subject: str = "NSE-EQ-TEST",
    *,
    exchange: str = "NSE",
    segment: str = "NSE",
    instrument_type: str = "EQ",
    symbol: str = "TEST",
    token: int = 101,
) -> IntradayInstrumentReference:
    values = {
        "canonical_instrument_id": subject,
        "exchange": exchange,
        "segment": segment,
        "instrument_type": instrument_type,
        "provider": "KITE",
        "provider_symbol": symbol,
        "provider_instrument_token": token,
        "tick_size": Decimal("0.05"),
        "lot_size": 1,
        "price_precision": 2,
    }
    return IntradayInstrumentReference(
        **values,
        mapping_identity=instrument_mapping_identity(**values),
    )


def _payloads(
    count: int,
    *,
    subject: str = "NSE-EQ-TEST",
    timeframe: IntradayTimeframe = IntradayTimeframe.ONE_HOUR,
    closes: tuple[Decimal, ...] | None = None,
    volumes: tuple[int, ...] | None = None,
    provider_source_identity: str = "KITE-INSTRUMENT-101",
    observation_boundary: datetime = BOUNDARY,
) -> tuple:
    retained_closes = closes or tuple(Decimal(index) for index in range(1, count + 1))
    retained_volumes = volumes or tuple(100 + index for index in range(count))
    result = []
    for index, (close, volume) in enumerate(zip(retained_closes, retained_volumes)):
        start = START + index * timeframe.duration
        end = start + timeframe.duration
        result.append(create_governed_historical_candle_payload(
            canonical_subject_identity=subject,
            exchange="MCX" if subject.startswith("MCX-") else "NSE",
            market_identity="MCX" if subject.startswith("MCX-") else "NSE",
            market_session_identity=f"SESSION-{start:%Y%m%d}",
            timeframe=timeframe,
            candle_start=start,
            candle_end=end,
            open=close,
            high=close + Decimal(1),
            low=max(Decimal(0), close - Decimal(1)),
            close=close,
            volume=volume,
            observation_boundary=observation_boundary,
            provider_source_identity=provider_source_identity,
            source_operation_identity="WO10-SLICE2-FIXTURE",
            provenance=("WO10-SLICE2-TEST",),
        ))
    return tuple(result)


def _series(
    count: int,
    *,
    subject: str = "NSE-EQ-TEST",
    family: IntradayMarketFamily = IntradayMarketFamily.NSE_EQUITY,
    timeframe: IntradayTimeframe = IntradayTimeframe.ONE_HOUR,
    closes: tuple[Decimal, ...] | None = None,
    volumes: tuple[int, ...] | None = None,
    provider_source_identity: str = "KITE-INSTRUMENT-101",
    observation_boundary: datetime = BOUNDARY,
):
    candles = _payloads(
        count,
        subject=subject,
        timeframe=timeframe,
        closes=closes,
        volumes=volumes,
        provider_source_identity=provider_source_identity,
        observation_boundary=observation_boundary,
    )
    mcx = family is IntradayMarketFamily.MCX
    return create_wo10_candle_series(
        canonical_subject_identity=subject,
        market_family=family,
        timeframe=timeframe,
        observation_boundary=observation_boundary,
        mapping_identity=f"MAPPING-{subject}",
        candles=candles,
        actual_contract_identity=("MCX-CONTRACT-GOLDM-202609" if mcx else None),
        roll_lineage_identity=("MCX-ROLL-LINEAGE-GOLDM-V1" if mcx else None),
    )


@pytest.mark.parametrize(
    ("timeframe", "value", "expected"),
    (
        (IntradayTimeframe.ONE_HOUR, Decimal("70"), Wo10RsiCondition.OVERBOUGHT),
        (IntradayTimeframe.ONE_HOUR, Decimal("30"), Wo10RsiCondition.OVERSOLD),
        (IntradayTimeframe.FIFTEEN_MINUTES, Decimal("70"), Wo10RsiCondition.OVERBOUGHT),
        (IntradayTimeframe.FIFTEEN_MINUTES, Decimal("30"), Wo10RsiCondition.OVERSOLD),
        (IntradayTimeframe.FIVE_MINUTES, Decimal("80"), Wo10RsiCondition.OVERBOUGHT),
        (IntradayTimeframe.FIVE_MINUTES, Decimal("20"), Wo10RsiCondition.OVERSOLD),
        (IntradayTimeframe.FIVE_MINUTES, Decimal("50"), Wo10RsiCondition.MIDRANGE),
    ),
)
def test_rsi_exact_thresholds_and_equality(
    timeframe: IntradayTimeframe,
    value: Decimal,
    expected: Wo10RsiCondition,
) -> None:
    assert classify_wo10_rsi(timeframe, value) is expected


def test_rsi_uses_governed_wilder_14_completed_candles_and_fails_closed() -> None:
    fact = build_wo10_rsi_fact(_series(15))
    insufficient = build_wo10_rsi_fact(_series(14))

    assert fact.value == Decimal(100)
    assert fact.condition is Wo10RsiCondition.OVERBOUGHT
    assert fact.calculation_identity == WO10_RSI_CALCULATION_IDENTITY
    assert len(fact.source_candle_identities) == 15
    assert insufficient.availability is DataAvailability.UNAVAILABLE
    assert insufficient.value is None
    assert insufficient.condition is Wo10RsiCondition.UNAVAILABLE

    with pytest.raises(SemanticEvidenceError, match="SEMANTIC_CANDLE_PAYLOAD_INVALID"):
        replace(_payloads(1)[0], completion_state="INCOMPLETE")


def test_rsi_contract_cannot_express_reversal_or_direction_semantics() -> None:
    names = {item.name for item in fields(type(build_wo10_rsi_fact(_series(15))))}
    assert names.isdisjoint({
        "direction", "long", "short", "reversal", "promotion", "entry",
        "stop", "target", "risk", "paper", "live", "broker",
    })


def test_sma_20_50_200_exact_values_price_stack_slope_and_change_facts() -> None:
    facts = build_wo10_sma_facts(_series(205))
    by_period = {item.period: item for item in facts.averages}

    assert by_period[20].value == Decimal("195.5")
    assert by_period[50].value == Decimal("180.5")
    assert by_period[200].value == Decimal("105.5")
    assert all(item.price_relationship is Wo10PriceRelationship.ABOVE for item in facts.averages)
    assert all(item.slope is Wo10SmaSlope.RISING for item in facts.averages)
    assert all(item.numerical_slope == Decimal(5) for item in facts.averages)
    assert facts.stack is Wo10SmaStack.BULLISH
    assert facts.recent_separation is Wo10RecentSeparation.ALL_ABOVE
    assert facts.calculation_identity == WO10_SMA_CALCULATION_IDENTITY
    assert all(item.exact_change is Wo10ExactChange.UNCHANGED for item in facts.pair_changes)


def test_sma_partial_history_preserves_values_and_marks_missing_slope_or_period() -> None:
    facts = build_wo10_sma_facts(_series(200))
    by_period = {item.period: item for item in facts.averages}

    assert by_period[20].value_availability is DataAvailability.AVAILABLE
    assert by_period[50].value_availability is DataAvailability.AVAILABLE
    assert by_period[200].value_availability is DataAvailability.AVAILABLE
    assert by_period[200].slope is Wo10SmaSlope.UNAVAILABLE
    assert facts.stack is Wo10SmaStack.BULLISH
    assert facts.policy_unresolved == (
        "MATERIAL_CRISSCROSS_THRESHOLD",
        "MATERIAL_SEPARATION_THRESHOLD",
    )


def test_sma_crisscross_is_exact_and_has_no_score_or_promotion_consequence() -> None:
    closes = tuple(Decimal(100 + (-1 if index % 2 else 1) * 10) for index in range(60))
    facts = build_wo10_sma_facts(_series(60, closes=closes))
    names = {item.name for item in fields(type(facts))}

    assert facts.crisscross20_count > 0
    assert facts.recent_separation is Wo10RecentSeparation.MIXED_OR_AT
    assert names.isdisjoint({"score", "weight", "rank", "promotion", "entry", "trade"})


class _PreviousCalendar:
    def __init__(self, schedule: MarketDaySchedule) -> None:
        self.schedule = schedule

    def previous_trading_schedule(self, exchange: str, before_date: date):
        assert exchange == self.schedule.exchange
        return self.schedule


def _location_fixture(
    subject: str = "NSE-EQ-TEST",
    *,
    exchange: str = "NSE",
    family: IntradayMarketFamily = IntradayMarketFamily.NSE_EQUITY,
):
    current_date = date(2026, 8, 17)
    previous_date = date(2026, 8, 14)
    current_schedule = MarketDaySchedule(
        exchange=exchange,
        trading_date=current_date,
        session_id=f"{exchange}-20260817",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(MarketWindow(
            datetime(2026, 8, 17, 9, 15, tzinfo=IST),
            datetime(2026, 8, 17, 15, 30, tzinfo=IST),
        ),),
        source_identity="WO10-CURRENT-SCHEDULE",
        source_version="1.0.0",
    )
    previous_schedule = MarketDaySchedule(
        exchange=exchange,
        trading_date=previous_date,
        session_id=f"{exchange}-20260814",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(MarketWindow(
            datetime(2026, 8, 14, 9, 15, tzinfo=IST),
            datetime(2026, 8, 14, 15, 30, tzinfo=IST),
        ),),
        source_identity="WO10-PREVIOUS-SCHEDULE",
        source_version="1.0.0",
    )
    instrument = _instrument(
        subject,
        exchange=exchange,
        segment="MCX" if family is IntradayMarketFamily.MCX else "NSE",
        instrument_type="FUT" if family is IntradayMarketFamily.MCX else "EQ",
        symbol="GOLDM26SEP" if family is IntradayMarketFamily.MCX else "TEST",
    )
    provenance = SourceProvenance(
        provider="KITE",
        source_identity="KITE-WO10-LOCATION",
        retrieved_at=datetime(2026, 8, 17, 10, 0, tzinfo=IST),
        source_version="1.0.0",
    )
    observed = datetime(2026, 8, 17, 10, 0, tzinfo=IST)
    run = create_intraday_run(
        created_at=observed - timedelta(minutes=1), observation_boundary=observed
    )
    context = build_slice1e_context(
        run=run,
        instrument=instrument,
        current_trading_date=current_date,
        calendar=_PreviousCalendar(previous_schedule),
        previous_session_candles=(HistoricalCandle(
            datetime(2026, 8, 14, 0, 0, tzinfo=IST),
            100.0, 110.0, 90.0, 106.0, 1_000,
        ),),
        provenance=provenance,
        current_price=Decimal(104),
    )
    boundaries = expected_candle_boundaries(current_schedule, IntradayTimeframe.FIFTEEN_MINUTES)
    candles = tuple(HistoricalCandle(
        boundaries[index].start,
        float(close),
        float(close + 1),
        float(close - 1),
        float(close),
        100 + index,
    ) for index, close in enumerate((Decimal(101), Decimal(102), Decimal(103))))
    reconciliation = reconcile_provider_candles(
        instrument=instrument,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        schedule=current_schedule,
        provider_candles=candles,
        observed_at=observed,
        provenance=provenance,
    )
    structural = build_structural_evidence(
        run=run,
        reconciliation=reconciliation,
        barriers=barriers_from_slice1e(context),
    )
    return context, structural


def test_structural_location_reuses_exact_prior_session_and_interaction_facts() -> None:
    context, structural = _location_fixture()
    location = build_wo10_structural_location_facts(
        context=context, structural_evidence=(structural,)
    )
    levels = {item.reference_name: item for item in location.levels}

    assert levels["PDH"].reference_value == Decimal("110.0")
    assert levels["PDL"].reference_value == Decimal("90.0")
    assert levels["PREVIOUS_CLOSE"].reference_value == Decimal("106.0")
    assert levels["P"].reference_value == Decimal("102.0")
    assert levels["R4"].reference_value == Decimal("162.0")
    assert levels["S4"].reference_value == Decimal("42.0")
    assert levels["CPR_UPPER"].reference_value == Decimal("104.0")
    assert levels["CPR_UPPER"].relationship is Wo10PriceRelationship.AT
    assert StructuralFactType.EXACT_BOUNDARY_TOUCH.value in location.implemented_interactions
    assert StructuralFactType.BOUNDARY_BREAK_ABOVE.value in location.implemented_interactions
    assert location.policy_unresolved == (
        "APPROACH_TOLERANCE",
        "FAILURE_QUALIFICATION",
        "HOLD_QUALIFICATION",
        "REJECTION_QUALIFICATION",
    )


def test_structural_location_rejects_cross_mapping_and_mcx_requires_roll_lineage() -> None:
    equity_context, equity_structure = _location_fixture()
    mcx_context, _ = _location_fixture(
        "MCX-SUBJECT-GOLDM", exchange="MCX", family=IntradayMarketFamily.MCX
    )
    with pytest.raises(Wo10ContractError, match="LINEAGE_MISMATCH"):
        build_wo10_structural_location_facts(
            context=mcx_context,
            structural_evidence=(equity_structure,),
            actual_contract_identity="MCX-CONTRACT-GOLDM-202609",
            roll_lineage_identity="MCX-ROLL-LINEAGE-GOLDM-V1",
        )
    with pytest.raises(Wo10ContractError, match="STRUCTURAL_LOCATION_INVALID"):
        build_wo10_structural_location_facts(context=mcx_context)

    location = build_wo10_structural_location_facts(
        context=mcx_context,
        actual_contract_identity="MCX-CONTRACT-GOLDM-202609",
        roll_lineage_identity="MCX-ROLL-LINEAGE-GOLDM-V1",
    )
    assert location.actual_contract_identity == "MCX-CONTRACT-GOLDM-202609"
    assert equity_context.instrument.mapping_identity != mcx_context.instrument.mapping_identity


def test_volume_uses_governed_20_completed_baseline_median_mean_ratios_percentile() -> None:
    fact = build_wo10_volume_fact(
        _series(21, volumes=tuple(range(1, 22)))
    )

    assert fact.availability is DataAvailability.AVAILABLE
    assert fact.current_volume == Decimal(21)
    assert fact.rolling_median_volume == Decimal("10.5")
    assert fact.rolling_mean_volume == Decimal("10.5")
    assert fact.volume_ratio_to_median == Decimal(2)
    assert fact.volume_ratio_to_mean == Decimal(2)
    assert fact.volume_percentile == Decimal(1)
    assert fact.lookback_identity == WO10_VOLUME_LOOKBACK_IDENTITY
    assert fact.consequence == "POLICY_UNRESOLVED_NO_THRESHOLD"


def test_volume_insufficient_history_fails_closed_without_threshold_consequence() -> None:
    fact = build_wo10_volume_fact(_series(20))
    assert fact.availability is DataAvailability.UNAVAILABLE
    assert fact.current_volume is None
    assert fact.comparison_count == 0


def test_same_time_volume_binds_exact_calendar_position_and_historical_set() -> None:
    raw = _payloads(
        4, timeframe=IntradayTimeframe.FIFTEEN_MINUTES, volumes=(25, 10, 20, 30)
    )
    candles = tuple(create_governed_historical_candle_payload(
        canonical_subject_identity=item.canonical_subject_identity,
        exchange=item.exchange,
        market_identity=item.market_identity,
        market_session_identity=f"SESSION-{index}",
        timeframe=item.timeframe,
        candle_start=item.candle_start,
        candle_end=item.candle_end,
        open=item.open,
        high=item.high,
        low=item.low,
        close=item.close,
        volume=item.volume,
        observation_boundary=item.observation_boundary,
        provider_source_identity=item.provider_source_identity,
        source_operation_identity=item.source_operation_identity,
        provenance=item.provenance,
    ) for index, item in enumerate(raw))
    positioned = tuple(Wo10SessionPositionedCandle(
        item,
        calendar_identity="DOMAIN-008-NSE-CALENDAR-V1",
        session_position_identity="NSE-15M-WINDOW-03",
    ) for index, item in enumerate(candles))
    fact = build_wo10_same_time_volume_fact(
        current=positioned[0],
        historical=positioned[1:],
        market_family=IntradayMarketFamily.NSE_EQUITY,
        historical_session_set_identity="NSE-THREE-SESSION-SET-TEST",
        lookback_identity="GOVERNED-SUPPLIED-HISTORICAL-SESSION-SET-V1",
    )

    assert fact.same_time_session_median == Decimal(20)
    assert fact.same_time_session_ratio == Decimal("1.25")
    assert fact.same_time_session_percentile == Decimal(2) / Decimal(3)
    assert fact.session_position_identity == "NSE-15M-WINDOW-03"
    assert fact.comparison_count == 3


def test_event_volume_binds_existing_structural_event_without_detecting_one() -> None:
    _, structural = _location_fixture()
    event = next(
        item for item in structural.facts
        if item.fact_type is StructuralFactType.BOUNDARY_BREAK_ABOVE
    )
    volume = build_wo10_volume_fact(_series(
        21,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        volumes=tuple(range(1, 22)),
        observation_boundary=event.observation_boundary.observed_at,
    ))
    binding = bind_wo10_event_volume(volume, event)

    assert binding.structural_event_identity == event.fact_id
    assert binding.structural_event_type is StructuralFactType.BOUNDARY_BREAK_ABOVE
    assert binding.consequence == "FACTUAL_BINDING_ONLY"
    assert binding.volume_source_candle_identities
    assert binding.event_source_candle_identities


def test_family_neutral_facts_and_mcx_contract_local_roll_safety() -> None:
    for subject, family in (
        ("NSE-EQ-TEST", IntradayMarketFamily.NSE_EQUITY),
        ("NSE-INDEX-NIFTY", IntradayMarketFamily.NSE_INDEX),
        ("MCX-SUBJECT-GOLDM", IntradayMarketFamily.MCX),
    ):
        series = _series(205, subject=subject, family=family)
        assert build_wo10_sma_facts(series).market_family is family
        assert build_wo10_rsi_fact(series).market_family is family
        assert build_wo10_volume_fact(series).market_family is family

    mcx = list(_payloads(2, subject="MCX-SUBJECT-GOLDM"))
    mcx[1] = create_governed_historical_candle_payload(
        canonical_subject_identity="MCX-SUBJECT-GOLDM",
        exchange="MCX",
        market_identity="MCX",
        market_session_identity="MCX-OTHER-SESSION",
        timeframe=IntradayTimeframe.ONE_HOUR,
        candle_start=mcx[1].candle_start,
        candle_end=mcx[1].candle_end,
        open=mcx[1].open,
        high=mcx[1].high,
        low=mcx[1].low,
        close=mcx[1].close,
        volume=mcx[1].volume,
        observation_boundary=BOUNDARY,
        provider_source_identity="KITE-INSTRUMENT-SUCCESSOR-CONTRACT",
        source_operation_identity="WO10-SLICE2-FIXTURE",
        provenance=("WO10-SLICE2-TEST",),
    )
    with pytest.raises(Wo10ContractError, match="CANDLE_SERIES_INVALID"):
        create_wo10_candle_series(
            canonical_subject_identity="MCX-SUBJECT-GOLDM",
            market_family=IntradayMarketFamily.MCX,
            timeframe=IntradayTimeframe.ONE_HOUR,
            observation_boundary=BOUNDARY,
            mapping_identity="MCX-MAPPING",
            candles=mcx,
            actual_contract_identity="MCX-CONTRACT-GOLDM-202609",
            roll_lineage_identity="MCX-ROLL-LINEAGE-GOLDM-V1",
        )


def test_slice1_common_evidence_contract_accepts_typed_slice2_artifacts() -> None:
    series = _series(205)
    rsi = build_wo10_rsi_fact(series)
    sma = build_wo10_sma_facts(series)
    volume = build_wo10_volume_fact(series)
    bindings = create_wo10_common_fact_bindings_from_facts(
        one_day_structure=None,
        one_hour_structure=None,
        fifteen_minute_structure=None,
        five_minute_progression=None,
        rsi=rsi,
        railway_track=sma,
        structural_location=None,
        volume_telemetry=volume,
    )

    assert bindings.rsi.evidence_identity == rsi.evidence_identity
    assert bindings.railway_track.evidence_identity == sma.evidence_identity
    assert bindings.volume_telemetry.evidence_identity == volume.evidence_identity


def test_factual_artifacts_are_deterministic_and_material_inputs_change_identity() -> None:
    first = build_wo10_sma_facts(_series(205))
    second = build_wo10_sma_facts(_series(205))
    changed_closes = tuple(Decimal(index) for index in range(1, 205)) + (Decimal(999),)
    changed = build_wo10_sma_facts(_series(205, closes=changed_closes))

    assert first == second
    assert first.evidence_identity == second.evidence_identity
    assert first.integrity_identity == second.integrity_identity
    assert changed.evidence_identity != first.evidence_identity
    assert changed.integrity_identity != first.integrity_identity


def test_slice2_contracts_have_no_classifier_or_later_authority_fields() -> None:
    artifacts = (
        build_wo10_rsi_fact(_series(205)),
        build_wo10_sma_facts(_series(205)),
        build_wo10_volume_fact(_series(205)),
    )
    forbidden = {
        "state", "score", "weight", "rank", "quota", "promotion", "entry",
        "stop", "sl", "target", "rr", "risk", "paper", "live", "broker",
        "trade_construction",
    }
    for artifact in artifacts:
        assert {item.name.lower() for item in fields(type(artifact))}.isdisjoint(forbidden)
