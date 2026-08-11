from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.candidate_validation import (
    SwingCandidate,
    extract_qualified_candidates,
    validate_qualified_candidates,
)
from kronos.swing.daily_data import build_swing_daily_dataset
from kronos.swing.market_assessment import assess_swing_market
from kronos.swing.universe import enabled_swing_phase1_universe
from kronos.swing.zero import SwingDirection, SwingSetup, SwingState


_KOLKATA = ZoneInfo("Asia/Kolkata")
_BOUNDARY = datetime(2026, 8, 7, tzinfo=_KOLKATA)
_NOW = datetime(2026, 8, 8, 12, 0, tzinfo=_KOLKATA)
_LONG_QUALIFIED = {
    "JUBLFOOD",
    "TCS",
    "MOTHERSON",
    "M&M",
    "BHARATFORG",
    "HINDALCO",
}
_SHORT_QUALIFIED = {"LUPIN", "AXISBANK", "SRF", "ADANIENT"}


def _instrument(identity: str) -> InstrumentRecord:
    commodity = identity in {"GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"}
    return InstrumentRecord(
        provider="KITE",
        exchange="MCX" if commodity else "NSE",
        segment="MCX-FUT" if commodity else "NSE",
        trading_symbol=f"{identity}26AUGFUT" if commodity else identity,
        name=identity,
        instrument_type="FUT" if commodity else "EQ",
        expiry=date(2026, 8, 28) if commodity else None,
    )


def _pure_long() -> list[float]:
    return [100.0 + index for index in range(19)] + [
        117.0,
        119.0,
        120.0,
        121.0,
        122.0,
        124.0,
    ]


def _pure_short() -> list[float]:
    return [200.0 - index for index in range(19)] + [
        183.0,
        181.0,
        180.0,
        179.0,
        178.0,
        176.0,
    ]


def _dual_short() -> list[float]:
    source = [100.0 + index for index in range(14)] + [
        119.0,
        119.5,
        120.0,
        120.5,
        121.0,
        121.5,
        121.0,
        121.5,
        122.0,
        122.5,
        124.0,
    ]
    return [300.0 - value for value in source]


def _forming_long() -> list[float]:
    return [100.0 + index for index in range(20)] + [
        120.0,
        121.0,
        120.0,
        121.0,
        121.5,
    ]


def _forming_short() -> list[float]:
    return [200.0 - index for index in range(20)] + [
        180.0,
        179.0,
        180.0,
        179.0,
        178.5,
    ]


def _candles(identity: str) -> tuple[HistoricalCandle, ...]:
    if identity in _LONG_QUALIFIED:
        closes = _pure_long()
    elif identity in _SHORT_QUALIFIED:
        closes = _pure_short()
    elif identity == "HDFCBANK":
        closes = _dual_short()
    elif identity == "IOC":
        closes = _forming_long()
    elif identity == "COALINDIA":
        closes = _forming_short()
    else:
        closes = [100.0] * 25
    start = _BOUNDARY - timedelta(days=len(closes) - 1)
    return tuple(
        HistoricalCandle(
            timestamp=start + timedelta(days=index),
            open=float(close),
            high=float(close + 1.0),
            low=float(close - 1.0),
            close=float(close),
            volume=1000 + index,
        )
        for index, close in enumerate(closes)
    )


def _stage4():  # type: ignore[no-untyped-def]
    dataset = build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=lambda member: _instrument(member.canonical_identity),
        historical_candles=lambda request: _candles(request.instrument.name),
        now=_NOW,
    )
    return dataset, assess_swing_market(dataset)


def test_exact_12_setup_candidates_and_11_unique_instruments_are_preserved() -> None:
    dataset, market = _stage4()

    validation = validate_qualified_candidates(market, dataset)

    assert len(validation.candidates) == 12
    assert validation.unique_instrument_count == 11
    assert validation.passed is True
    assert all(audit.passed for audit in validation.audits)


def test_hdfcbank_preserves_two_independent_short_setup_candidates() -> None:
    dataset, market = _stage4()

    validation = validate_qualified_candidates(market, dataset)
    hdfc = tuple(
        candidate
        for candidate in validation.candidates
        if candidate.canonical_identity == "HDFCBANK"
    )

    assert tuple(candidate.setup for candidate in hdfc) == (
        SwingSetup.PULLBACK_CONTINUATION,
        SwingSetup.CONSOLIDATION_BREAKOUT,
    )
    assert all(candidate.direction is SwingDirection.SHORT for candidate in hdfc)


def test_candidate_extraction_is_qualified_only_with_zero_leakage() -> None:
    dataset, market = _stage4()

    validation = validate_qualified_candidates(market, dataset)

    assert all(
        candidate.assessment.state is SwingState.QUALIFIED
        for candidate in validation.candidates
    )
    assert validation.forming_leakage == 0
    assert validation.no_setup_leakage == 0


def test_forming_long_short_and_breakout_missing_events_are_independently_audited() -> None:
    dataset, market = _stage4()

    validation = validate_qualified_candidates(market, dataset)

    assert tuple(
        (audit.setup, audit.direction, audit.missing_event, audit.passed)
        for audit in validation.forming_audits
    ) == (
        (
            SwingSetup.PULLBACK_CONTINUATION,
            SwingDirection.LONG,
            "Completed Daily close above previous-day high",
            True,
        ),
        (
            SwingSetup.PULLBACK_CONTINUATION,
            SwingDirection.SHORT,
            "Completed Daily close below previous-day low",
            True,
        ),
        (
            SwingSetup.CONSOLIDATION_BREAKOUT,
            SwingDirection.NONE,
            "Completed Daily close outside prior ten-bar range",
            True,
        ),
    )


def test_pullback_and_breakout_audits_prove_exclusion_boundaries() -> None:
    dataset, market = _stage4()

    validation = validate_qualified_candidates(market, dataset)
    pullback = validation.audits[0]
    breakout = next(
        audit
        for audit in validation.audits
        if audit.candidate.setup is SwingSetup.CONSOLIDATION_BREAKOUT
    )

    assert dict(pullback.predicate_results)["preceding_five_excludes_current"] is True
    assert dict(pullback.predicate_results)["confirmation_beyond_previous_extreme"] is True
    assert dict(breakout.predicate_results)["preceding_ten_excludes_current"] is True
    assert dict(breakout.predicate_results)["atr14_ends_at_preceding_candle"] is True
    assert dict(breakout.predicate_results)["short_breakout"] is True


def test_independent_audit_rejects_corrupted_published_evidence() -> None:
    dataset, market = _stage4()
    target_index = next(
        index
        for index, item in enumerate(market.instruments)
        if item.canonical_identity == "HDFCBANK"
    )
    target = market.instruments[target_index]
    corrupted = replace(
        target.assessments[1],
        evidence_for=target.assessments[1].evidence_for + ("range_low=wrong",),
    )
    changed_item = replace(target, assessments=(target.assessments[0], corrupted))
    changed_instruments = (
        market.instruments[:target_index]
        + (changed_item,)
        + market.instruments[target_index + 1 :]
    )
    changed_market = replace(market, instruments=changed_instruments)

    validation = validate_qualified_candidates(changed_market, dataset)
    breakout = next(
        audit
        for audit in validation.audits
        if audit.candidate.canonical_identity == "HDFCBANK"
        and audit.candidate.setup is SwingSetup.CONSOLIDATION_BREAKOUT
    )

    assert breakout.passed is False
    assert dict(breakout.predicate_results)["evidence_exact"] is False
    assert validation.passed is False


def test_extraction_is_deterministic_preserves_original_objects_and_mutates_nothing() -> None:
    dataset, market = _stage4()
    candles_before = tuple(record.candles for record in dataset.records)
    instruments_before = market.instruments

    first = extract_qualified_candidates(market)
    second = extract_qualified_candidates(market)

    assert first == second
    assert hash(first) == hash(second)
    original = next(
        assessment
        for item in market.instruments
        for assessment in item.assessments
        if item.canonical_identity == first[0].canonical_identity
        and assessment.setup is first[0].setup
    )
    assert first[0].assessment is original
    assert tuple(record.candles for record in dataset.records) == candles_before
    assert market.instruments is instruments_before


def test_candidate_is_immutable_and_contains_no_comparison_or_trade_plan_fields() -> None:
    _, market = _stage4()
    candidate = extract_qualified_candidates(market)[0]

    with pytest.raises((FrozenInstanceError, AttributeError)):
        candidate.direction = SwingDirection.SHORT  # type: ignore[misc]
    assert {field.name for field in fields(SwingCandidate)} == {
        "canonical_identity",
        "setup",
        "direction",
        "observation_boundary",
        "rule_set_version",
        "assessment",
    }
    for forbidden in (
        "rank",
        "score",
        "confidence",
        "quality_percentage",
        "priority",
        "entry",
        "stop",
        "target",
        "risk_reward",
    ):
        assert not hasattr(candidate, forbidden)


def test_extraction_rejects_non_market_input() -> None:
    with pytest.raises(ValueError, match="SWING_CANDIDATE_EXTRACTION_INVALID"):
        extract_qualified_candidates(object())  # type: ignore[arg-type]
