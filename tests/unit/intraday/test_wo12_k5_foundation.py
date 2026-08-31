from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from kronos.intraday.contracts import (
    IntradayInstrumentReference,
    IntradayTimeframe,
    SourceProvenance,
)
from kronos.intraday.historical_semantic import (
    SemanticAvailability,
    SemanticDirection,
    SemanticFactFamily,
    create_governed_historical_candle_payload,
    create_semantic_qualification_fact,
)
from kronos.intraday.mcx_history import (
    MCX_HISTORY_AUTHORITY,
    MCX_HISTORY_CANDLE_IDENTITY,
    MCX_HISTORY_CANDLE_VERSION,
    RetainedMcxContractCandle,
    _identity as _mcx_identity,
)
from kronos.intraday.structure import (
    ExplicitMoveDefinition,
    FactualDirection,
    build_structural_evidence,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo12_k5_foundation import (
    WO12_ATR_IDENTITY,
    WO12_ATR_PERIOD,
    WO12_FORWARD_HORIZONS,
    WO12_K5_RESEARCH_AUTHORITY,
    WO12_K5_THRESHOLD_AUTHORITY,
    WO12_PULLBACK_ORIGIN_METHOD,
    Wo12ForwardOutcome,
    Wo12SetupFamily,
    _origin_fact,
    calculate_wo12_wilder_atr,
    create_k5_measurement_from_foundation,
    derive_wo12_structural_origin,
    reconstruct_wo12_forward_outcomes,
)
from kronos.market.schedule import MarketDaySchedule

from .test_structure import _authority, _full_evidence
from .test_wo12 import _foundation


IST = ZoneInfo("Asia/Kolkata")
SUBJECT = "NIFTY"
SESSION = "NSE-20260817-REGULAR"
ORIGINAL_BOUNDARY = datetime(2026, 8, 17, 9, 15, tzinfo=IST)
FINAL_BOUNDARY = datetime(2026, 8, 17, 15, 30, tzinfo=IST)


def _candle(index: int, *, subject: str = SUBJECT, session: str = SESSION):  # type: ignore[no-untyped-def]
    start = ORIGINAL_BOUNDARY + timedelta(minutes=15 * index)
    close = Decimal(100 + index)
    return create_governed_historical_candle_payload(
        canonical_subject_identity=subject,
        exchange="NSE",
        market_identity="NSE_CAPITAL_MARKET",
        market_session_identity=session,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        candle_start=start,
        candle_end=start + timedelta(minutes=15),
        open=close,
        high=close + Decimal("2"),
        low=close - Decimal("1"),
        close=close,
        volume=1_000 + index,
        observation_boundary=FINAL_BOUNDARY,
        provider_source_identity="DOMAIN-006:KITE:HISTORICAL",
        source_operation_identity="WO12-K5-FACT-FOUNDATION-TEST",
        provenance=("WO12-K5-FACT-FOUNDATION-TEST",),
    )


def _terminal_fact(boundary: datetime, direction: SemanticDirection):  # type: ignore[no-untyped-def]
    return create_semantic_qualification_fact(
        family=SemanticFactFamily.FIFTEEN_MINUTE_STRUCTURE,
        canonical_subject_identity=SUBJECT,
        market_session_identity=SESSION,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        availability=SemanticAvailability.AVAILABLE,
        direction=direction,
        attributes=(("completion", "COMPLETED_GOVERNED_15M"),),
        values=(),
        source_evidence_identities=(f"STRUCTURE-{boundary.isoformat()}",),
        available_at=boundary,
        observation_boundary=boundary,
        policy_identity="WO06S_GOVERNED_15M_STRUCTURE",
        source_operation_identity="WO12-K5-OUTCOME-TEST",
        provenance=("WO12-K5-FACT-FOUNDATION-TEST",),
    )


def _mcx_candle(index: int, contract: str) -> RetainedMcxContractCandle:
    start = datetime(2026, 8, 17, 10, 0, tzinfo=IST) + timedelta(minutes=15 * index)
    values = {
        "canonical_subject_identity": "MCX-SUBJECT-GOLDM",
        "canonical_contract_identity": contract,
        "provider_record_identity": f"PROVIDER-INSTRUMENT-RECORD-GOLDM-{contract}-{index}",
        "historical_binding_identity": f"ACTIVE-DERIVATIVE-BINDING-GOLDM-{contract}",
        "domain008_session_identity": "MCX-SESSION-20260817",
        "calendar_identity": "KRONOS-MARKET-CALENDAR-V1/TEST",
        "calendar_version": "1",
        "timeframe": IntradayTimeframe.FIFTEEN_MINUTES,
        "source_timestamp": start,
        "candle_start": start,
        "candle_end": start + timedelta(minutes=15),
        "completion_boundary": start + timedelta(minutes=15),
        "open": Decimal("100"),
        "high": Decimal("102"),
        "low": Decimal("99"),
        "close": Decimal("101"),
        "volume": 1_000,
        "observation_boundary": FINAL_BOUNDARY,
        "source_operation_identity": "WO12-K5-MCX-ROLL-TEST",
        "provider_source_identity": "DOMAIN-006:KITE:HISTORICAL",
        "provenance": ("TEST-GOVERNED-FACT", "SENSITIVE_PROVIDER_LOCATOR_EXCLUDED"),
        "authority": MCX_HISTORY_AUTHORITY,
        "contract_identity": MCX_HISTORY_CANDLE_IDENTITY,
        "contract_version": MCX_HISTORY_CANDLE_VERSION,
    }
    return RetainedMcxContractCandle(
        candle_identity=_mcx_identity("INTRADAY-MCX-CONTRACT-CANDLE-", values),
        integrity_identity=_mcx_identity("INTEGRITY-INTRADAY-MCX-CONTRACT-CANDLE-", values),
        **values,
    )


def test_pullback_and_breakout_origins_bind_only_explicit_governed_structure(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    _, _, evidence = _full_evidence(instrument, schedule, provenance)
    boundary = evidence.observation_boundary.observed_at

    pullback = derive_wo12_structural_origin(
        canonical_subject_identity=instrument.canonical_instrument_id,
        market_family=IntradayMarketFamily.NSE_INDEX,
        setup_family=Wo12SetupFamily.PULLBACK_CONTINUATION,
        inherited_direction=SemanticDirection.LONG,
        analysis_boundary=boundary,
        evidence=evidence,
    )
    breakout = derive_wo12_structural_origin(
        canonical_subject_identity=instrument.canonical_instrument_id,
        market_family=IntradayMarketFamily.NSE_INDEX,
        setup_family=Wo12SetupFamily.RANGE_BREAKOUT,
        inherited_direction=SemanticDirection.LONG,
        analysis_boundary=boundary,
        evidence=evidence,
    )

    assert pullback.availability is SemanticAvailability.AVAILABLE
    assert pullback.origin_value == Decimal("99.0")
    assert pullback.governing_structure_identity == "OBSERVED-UP-MOVE"
    assert len(pullback.source_fact_identities) == 1
    assert breakout.availability is SemanticAvailability.AVAILABLE
    assert breakout.origin_value == Decimal("104")
    assert breakout.governing_structure_identity == "OPENING-EXPLICIT-RANGE"
    assert len(breakout.source_fact_identities) >= 2
    assert pullback.threshold_authority == WO12_K5_THRESHOLD_AUTHORITY


def test_origin_is_unavailable_when_explicit_governed_lineage_is_ambiguous(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    run, reconciliation = _authority(instrument, schedule, provenance)
    candles = reconciliation.structural_candles
    evidence = build_structural_evidence(
        run=run,
        reconciliation=reconciliation,
        moves=(
            ExplicitMoveDefinition(
                move_id="MOVE-A",
                direction=FactualDirection.UP,
                start_candle_id=candles[0].candle_id,
                end_candle_id=candles[2].candle_id,
            ),
            ExplicitMoveDefinition(
                move_id="MOVE-B",
                direction=FactualDirection.UP,
                start_candle_id=candles[1].candle_id,
                end_candle_id=candles[2].candle_id,
            ),
        ),
    )

    origin = derive_wo12_structural_origin(
        canonical_subject_identity=SUBJECT,
        market_family=IntradayMarketFamily.NSE_INDEX,
        setup_family=Wo12SetupFamily.PULLBACK_CONTINUATION,
        inherited_direction=SemanticDirection.LONG,
        analysis_boundary=run.observation_boundary.observed_at,
        evidence=evidence,
    )

    assert origin.availability is SemanticAvailability.UNAVAILABLE
    assert origin.origin_value is None
    assert origin.source_fact_identities == ()
    assert origin.reason == "EXPLICIT_DIRECTIONAL_MOVE_AMBIGUOUS"


def test_wilder_atr_uses_exact_seed_and_recursive_rma() -> None:
    candles = tuple(_candle(index) for index in range(16))
    fact = calculate_wo12_wilder_atr(
        canonical_subject_identity=SUBJECT,
        market_family=IntradayMarketFamily.NSE_INDEX,
        market_session_identity=SESSION,
        analysis_boundary=candles[-1].candle_end,
        candles=candles,
    )

    # Every candle has a true range of 3; gaps do not exceed that range.
    assert fact.availability is SemanticAvailability.AVAILABLE
    assert fact.atr_value == Decimal("3")
    assert fact.period == WO12_ATR_PERIOD
    assert fact.calculation_identity == WO12_ATR_IDENTITY
    assert fact.completed_candle_count == 16


def test_atr_warmup_and_future_candles_fail_closed_without_lookahead() -> None:
    candles = tuple(_candle(index) for index in range(15))
    under_warmup = calculate_wo12_wilder_atr(
        canonical_subject_identity=SUBJECT,
        market_family=IntradayMarketFamily.NSE_INDEX,
        market_session_identity=SESSION,
        analysis_boundary=candles[12].candle_end,
        candles=candles,
    )
    at_boundary = calculate_wo12_wilder_atr(
        canonical_subject_identity=SUBJECT,
        market_family=IntradayMarketFamily.NSE_INDEX,
        market_session_identity=SESSION,
        analysis_boundary=candles[13].candle_end,
        candles=candles,
    )
    without_future = calculate_wo12_wilder_atr(
        canonical_subject_identity=SUBJECT,
        market_family=IntradayMarketFamily.NSE_INDEX,
        market_session_identity=SESSION,
        analysis_boundary=candles[13].candle_end,
        candles=candles[:14],
    )

    assert under_warmup.availability is SemanticAvailability.UNAVAILABLE
    assert under_warmup.reason == "ATR_14_WARMUP_INCOMPLETE"
    assert at_boundary == without_future


def test_incomplete_governed_candle_cannot_enter_atr(
    instrument: IntradayInstrumentReference,
    schedule: MarketDaySchedule,
    provenance: SourceProvenance,
) -> None:
    _, reconciliation = _authority(instrument, schedule, provenance)
    incomplete = reconciliation.observations[-1]
    candles = tuple(_candle(index) for index in range(14))

    baseline = calculate_wo12_wilder_atr(
        canonical_subject_identity=SUBJECT,
        market_family=IntradayMarketFamily.NSE_INDEX,
        market_session_identity=SESSION,
        analysis_boundary=candles[-1].candle_end,
        candles=candles,
    )
    supplied = calculate_wo12_wilder_atr(
        canonical_subject_identity=SUBJECT,
        market_family=IntradayMarketFamily.NSE_INDEX,
        market_session_identity=SESSION,
        analysis_boundary=candles[-1].candle_end,
        candles=(*candles, incomplete),  # type: ignore[arg-type]
    )

    assert incomplete.completion.value == "INCOMPLETE"
    assert supplied == baseline


def test_forward_outcomes_use_separate_completed_15m_horizons() -> None:
    candles = tuple(_candle(index) for index in range(12))
    facts = (
        _terminal_fact(candles[3].candle_end, SemanticDirection.LONG),
        _terminal_fact(candles[7].candle_end, SemanticDirection.SHORT),
        _terminal_fact(candles[11].candle_end, SemanticDirection.NON_DIRECTIONAL),
    )

    outcomes = reconstruct_wo12_forward_outcomes(
        canonical_subject_identity=SUBJECT,
        market_family=IntradayMarketFamily.NSE_INDEX,
        inherited_direction=SemanticDirection.LONG,
        original_analysis_boundary=ORIGINAL_BOUNDARY,
        market_session_identity=SESSION,
        future_candles=candles,
        future_structure_facts=facts,
    )

    assert tuple(item.horizon_completed_15m_bars for item in outcomes) == WO12_FORWARD_HORIZONS
    assert tuple(item.outcome for item in outcomes) == (
        Wo12ForwardOutcome.CONTINUED,
        Wo12ForwardOutcome.FAILED,
        Wo12ForwardOutcome.INDETERMINATE,
    )
    assert all(item.authority == WO12_K5_RESEARCH_AUTHORITY for item in outcomes)
    assert all(item.availability is SemanticAvailability.AVAILABLE for item in outcomes)


def test_forward_outcomes_do_not_bridge_gap_or_session() -> None:
    candles = tuple(_candle(index) for index in range(12))
    gapped = (candles[0], *candles[2:])
    outcomes = reconstruct_wo12_forward_outcomes(
        canonical_subject_identity=SUBJECT,
        market_family=IntradayMarketFamily.NSE_INDEX,
        inherited_direction=SemanticDirection.LONG,
        original_analysis_boundary=ORIGINAL_BOUNDARY,
        market_session_identity=SESSION,
        future_candles=gapped,
        future_structure_facts=(),
    )
    next_session = tuple(
        _candle(index, session="NSE-20260818-REGULAR") for index in range(12)
    )
    session_outcomes = reconstruct_wo12_forward_outcomes(
        canonical_subject_identity=SUBJECT,
        market_family=IntradayMarketFamily.NSE_INDEX,
        inherited_direction=SemanticDirection.LONG,
        original_analysis_boundary=ORIGINAL_BOUNDARY,
        market_session_identity=SESSION,
        future_candles=next_session,
        future_structure_facts=(),
    )

    assert all(item.availability is SemanticAvailability.UNAVAILABLE for item in outcomes)
    assert outcomes[0].reason == "FORWARD_15M_CONTINUITY_GAP"
    assert all(item.reason == "FORWARD_COMPLETED_15M_HORIZON_INCOMPLETE" for item in session_outcomes)


def test_natgas_is_held_and_has_no_atr_or_outcome_authority() -> None:
    atr = calculate_wo12_wilder_atr(
        canonical_subject_identity="MCX-SUBJECT-NATGAS",
        market_family=IntradayMarketFamily.MCX,
        market_session_identity="MCX-SESSION-20260817",
        analysis_boundary=FINAL_BOUNDARY,
        candles=(),
    )
    outcomes = reconstruct_wo12_forward_outcomes(
        canonical_subject_identity="MCX-SUBJECT-NATGAS",
        market_family=IntradayMarketFamily.MCX,
        inherited_direction=SemanticDirection.LONG,
        original_analysis_boundary=ORIGINAL_BOUNDARY,
        market_session_identity="MCX-SESSION-20260817",
        future_candles=(),
        future_structure_facts=(),
    )

    assert atr.availability is SemanticAvailability.UNAVAILABLE
    assert atr.reason == "HELD_MCX_SUBJECT"
    assert all(item.reason == "HELD_MCX_SUBJECT" for item in outcomes)
    assert all(item.outcome is Wo12ForwardOutcome.INDETERMINATE for item in outcomes)


def test_mcx_atr_and_outcome_never_bridge_actual_contract_roll() -> None:
    contract_a = "MCX-FUT-GOLDM-2026-08-31"
    contract_b = "MCX-FUT-GOLDM-2026-09-30"
    candles = tuple(
        _mcx_candle(index, contract_a if index < 13 else contract_b)
        for index in range(14)
    )
    atr = calculate_wo12_wilder_atr(
        canonical_subject_identity="MCX-SUBJECT-GOLDM",
        market_family=IntradayMarketFamily.MCX,
        market_session_identity="MCX-SESSION-20260817",
        analysis_boundary=FINAL_BOUNDARY,
        candles=candles,
    )
    outcomes = reconstruct_wo12_forward_outcomes(
        canonical_subject_identity="MCX-SUBJECT-GOLDM",
        market_family=IntradayMarketFamily.MCX,
        inherited_direction=SemanticDirection.LONG,
        original_analysis_boundary=candles[9].candle_end,
        market_session_identity="MCX-SESSION-20260817",
        future_candles=candles[10:],
        future_structure_facts=(),
    )

    assert atr.availability is SemanticAvailability.UNAVAILABLE
    assert atr.reason == "MCX_CONTRACT_ROLL_CROSSING"
    assert outcomes[0].availability is SemanticAvailability.UNAVAILABLE
    assert outcomes[0].reason == "MCX_CONTRACT_ROLL_CROSSING"


def test_new_origin_and_atr_feed_frozen_k5_formula_without_consequence(tmp_path) -> None:
    _, _, handoff, _ = _foundation(tmp_path)
    start = handoff.analysis_boundary - timedelta(minutes=15 * 14)
    candles = tuple(
        create_governed_historical_candle_payload(
            canonical_subject_identity=handoff.canonical_subject_identity,
            exchange="NSE",
            market_identity="NSE_CAPITAL_MARKET",
            market_session_identity="WO12-K5-FORMULA-SESSION",
            timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
            candle_start=start + timedelta(minutes=15 * index),
            candle_end=start + timedelta(minutes=15 * (index + 1)),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=1_000,
            observation_boundary=handoff.analysis_boundary,
            provider_source_identity="DOMAIN-006:KITE:HISTORICAL",
            source_operation_identity="WO12-K5-FORMULA-TEST",
            provenance=("WO12-K5-FACT-FOUNDATION-TEST",),
        )
        for index in range(14)
    )
    atr = calculate_wo12_wilder_atr(
        canonical_subject_identity=handoff.canonical_subject_identity,
        market_family=handoff.market_family,
        market_session_identity="WO12-K5-FORMULA-SESSION",
        analysis_boundary=handoff.analysis_boundary,
        candles=candles,
    )
    origin = _origin_fact(
        canonical_subject_identity=handoff.canonical_subject_identity,
        market_family=handoff.market_family,
        setup_family=Wo12SetupFamily.PULLBACK_CONTINUATION,
        inherited_direction=handoff.inherited_direction,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        analysis_boundary=handoff.analysis_boundary,
        availability=SemanticAvailability.AVAILABLE,
        origin_value=Decimal("95"),
        origin_boundary=start,
        origin_type="DIRECTIONAL_IMPULSE_LEG_START",
        calculation_identity=WO12_PULLBACK_ORIGIN_METHOD,
        governing_structure_identity="EXPLICIT-MOVE-FORMULA-TEST",
        source_fact_identities=("STRUCTURAL-FACT-FORMULA-TEST",),
        source_fact_integrities=("INTEGRITY-STRUCTURAL-FACT-FORMULA-TEST",),
        provenance=("COMPLETED_GOVERNED_15M_STRUCTURE_ONLY",),
        reason="EXACT_GOVERNED_15M_STRUCTURAL_ORIGIN_BOUND",
    )
    measurement = create_k5_measurement_from_foundation(
        handoff=handoff,
        origin=origin,
        atr=atr,
        completed_close=Decimal("110"),
    )

    assert measurement is not None
    assert measurement.extension_atr_multiple == Decimal("5")
    assert measurement.threshold_status == WO12_K5_THRESHOLD_AUTHORITY


def test_fact_foundation_contains_no_material_extension_threshold() -> None:
    import kronos.intraday.wo12_k5_foundation as foundation

    source = foundation.__file__
    assert source is not None
    text = open(source, encoding="utf-8").read()
    assert "WO12_K5_THRESHOLD_AUTHORITY = \"POLICY_UNRESOLVED\"" in text
    assert "MATERIAL_EXTENSION_THRESHOLD =" not in text
    assert "score" not in text.lower()
    assert "rank" not in text.lower()
