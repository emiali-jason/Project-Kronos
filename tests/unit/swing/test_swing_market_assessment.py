from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from kronos.provider.contracts.instrument import (
    InstrumentRecord,
    InstrumentResolutionError,
    InstrumentResolutionFailure,
)
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing import market_assessment as market
from kronos.swing.daily_data import build_swing_daily_dataset
from kronos.swing.market_assessment import (
    SwingInstrumentAssessments,
    SwingMarketAssessment,
    assess_swing_market,
)
from kronos.swing.universe import enabled_swing_phase1_universe
from kronos.swing.zero import (
    SWING_ZERO_POLICY_ID,
    SwingAnalysisError,
    SwingAnalysisFailure,
    SwingDirection,
    SwingSetup,
    SwingState,
)


_KOLKATA = ZoneInfo("Asia/Kolkata")
_NOW = datetime(2026, 8, 10, 12, 0, tzinfo=_KOLKATA)


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


def _candles(
    *,
    count: int = 30,
    end_date: date = date(2026, 8, 9),
    closes: tuple[float, ...] | None = None,
) -> tuple[HistoricalCandle, ...]:
    if closes is None:
        closes = (100.0,) * count
    start_date = end_date - timedelta(days=len(closes) - 1)
    return tuple(
        HistoricalCandle(
            timestamp=datetime.combine(
                start_date + timedelta(days=index),
                datetime.min.time(),
                tzinfo=_KOLKATA,
            ),
            open=float(close),
            high=float(close + 1.0),
            low=float(close - 1.0),
            close=float(close),
            volume=1000 + index,
        )
        for index, close in enumerate(closes)
    )


def _dataset(
    *,
    resolve=None,  # type: ignore[no-untyped-def]
    historical=None,  # type: ignore[no-untyped-def]
):
    return build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=resolve or (lambda member: _instrument(member.canonical_identity)),
        historical_candles=historical or (lambda _request: _candles()),
        now=_NOW,
    )


def test_all_98_members_produce_exactly_196_independent_assessments() -> None:
    result = assess_swing_market(_dataset())

    assert result.requested_count == 98
    assert result.assessed_count == 98
    assert result.failure_count == 0
    assert result.assessment_count == 196
    assert all(
        tuple(assessment.setup for assessment in item.assessments)
        == (
            SwingSetup.PULLBACK_CONTINUATION,
            SwingSetup.CONSOLIDATION_BREAKOUT,
        )
        for item in result.instruments
    )


def test_ordering_and_repeated_evaluation_are_deterministic() -> None:
    dataset = _dataset()
    first = assess_swing_market(dataset)
    second = assess_swing_market(dataset)

    expected = tuple(
        member.canonical_identity for member in enabled_swing_phase1_universe()
    )
    assert tuple(item.canonical_identity for item in first.instruments) == expected
    assert first == second
    assert hash(first) == hash(second)
    assert first.run_identity == (
        f"{SWING_ZERO_POLICY_ID}@{first.observation_boundary.isoformat()}"
    )


def test_zero_qualified_is_legitimate_and_forming_is_not_promoted() -> None:
    result = assess_swing_market(_dataset())
    counts = result.counts

    assert counts.pullback_no_setup == 98
    assert counts.pullback_forming_long == 0
    assert counts.pullback_forming_short == 0
    assert counts.pullback_qualified_long == 0
    assert counts.pullback_qualified_short == 0
    assert counts.breakout_no_setup == 0
    assert counts.breakout_forming == 98
    assert counts.breakout_qualified_long == 0
    assert counts.breakout_qualified_short == 0
    assert all(
        item.assessments[1].state is SwingState.FORMING
        and item.assessments[1].direction is SwingDirection.NONE
        for item in result.instruments
    )


def test_one_stage3_failure_remains_explicit_and_does_not_stop_market_run() -> None:
    def resolve(member):  # type: ignore[no-untyped-def]
        if member.canonical_identity == "RELIANCE":
            raise InstrumentResolutionError(InstrumentResolutionFailure.NO_MATCH)
        return _instrument(member.canonical_identity)

    result = assess_swing_market(_dataset(resolve=resolve))
    failed = next(
        item for item in result.instruments if item.canonical_identity == "RELIANCE"
    )

    assert result.requested_count == 98
    assert result.assessed_count == 97
    assert result.failure_count == 1
    assert result.assessment_count == 194
    assert failed.assessments == ()
    assert failed.failure is not None


def test_typed_swing_analysis_failure_is_preserved_per_instrument(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    original = market.analyze_swing_zero
    calls = 0

    def analyze(request, candles):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SwingAnalysisError(SwingAnalysisFailure.INVALID_REQUEST)
        return original(request, candles)

    monkeypatch.setattr(market, "analyze_swing_zero", analyze)
    result = assess_swing_market(_dataset())

    assert result.assessed_count == 97
    assert result.failure_count == 1
    assert result.instruments[1].failure is SwingAnalysisFailure.INVALID_REQUEST
    assert result.instruments[1].assessments == ()


def test_common_completed_boundary_is_used_without_mutating_stage3_candles() -> None:
    original_sequences = {}

    def historical(request):  # type: ignore[no-untyped-def]
        end_date = (
            date(2026, 8, 8)
            if request.instrument.exchange == "MCX"
            else date(2026, 8, 9)
        )
        candles = _candles(end_date=end_date)
        original_sequences[request.instrument.trading_symbol] = candles
        return candles

    dataset = _dataset(historical=historical)
    before = tuple(record.candles for record in dataset.records)
    result = assess_swing_market(dataset)

    assert result.observation_boundary.date() == date(2026, 8, 8)
    assert all(
        assessment.observation_boundary == result.observation_boundary
        for item in result.instruments
        for assessment in item.assessments
    )
    assert tuple(record.candles for record in dataset.records) == before
    assert original_sequences


def test_same_engine_and_result_shape_apply_across_all_asset_classes() -> None:
    result = assess_swing_market(_dataset())
    examples = {}
    for item in result.instruments:
        examples.setdefault(item.asset_class, item)

    assert len(examples) == 3
    assert all(type(item) is SwingInstrumentAssessments for item in examples.values())
    assert all(len(item.assessments) == 2 for item in examples.values())
    assert all(
        assessment.rule_set_version == SWING_ZERO_POLICY_ID
        for item in examples.values()
        for assessment in item.assessments
    )


def test_market_result_and_existing_assessments_remain_immutable() -> None:
    result = assess_swing_market(_dataset())

    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.instruments = ()  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.instruments[0].assessments[0].state = SwingState.QUALIFIED  # type: ignore[misc]
    assert not hasattr(result, "__dict__")
    assert not hasattr(result.instruments[0], "__dict__")


def test_no_ranking_winner_selection_or_trade_plan_values_are_created() -> None:
    result = assess_swing_market(_dataset())
    public_fields = {field.name for field in fields(SwingMarketAssessment)}

    assert public_fields == {
        "run_identity",
        "observation_boundary",
        "instruments",
        "counts",
    }
    assert not hasattr(result, "ranking")
    assert not hasattr(result, "winner")
    assert not hasattr(result, "selected_instruments")
    for item in result.instruments:
        for assessment in item.assessments:
            assert assessment.entry_zone is None
            assert assessment.invalidation is None
            assert assessment.stop is None
            assert assessment.targets is None
            assert assessment.risk_reward is None
