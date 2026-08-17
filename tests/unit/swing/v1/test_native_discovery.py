from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from kronos.browser.views import render_native_discovery
from kronos.application.swing_opportunities import (
    AnalysisState,
    BrowserWorkspaceSnapshot,
    ProviderConnectionState,
)
from kronos.swing.v1.models import PivotCandidate, PivotKind, V1Direction
from kronos.swing.v1.mtf_facts import (
    CompletedTimeframeFact,
    FactualMovingAverageFacts,
    FactualPivotSeries,
    FactualTimeframe,
    FactualVolumeFacts,
)
from kronos.swing.v1.native_discovery import (
    NATIVE_DISCOVERY_AUTHORITY,
    NATIVE_DISCOVERY_POLICY_ID,
    Native1DState,
    Native1HState,
    Native1WState,
    Native4HState,
    NativeAnchor,
    NativeAnchorType,
    NativeDiscoveryEvidenceStore,
    NativeDiscoveryStatus,
    classify_native_daily,
    classify_native_four_hour,
    classify_native_one_hour,
    classify_native_weekly,
    discover_native_mtf,
)
from kronos.swing.v1 import native_discovery as native
from kronos.swing.v1.weekly_facts import (
    FactualPriceRelation,
    FactualStructureCondition,
    WeeklyFactAvailability,
    WeeklyPivotFacts,
    WeeklySmaDirection,
)
from tests.unit.application.test_swing_mtf_facts import _build as _mtf_build
from tests.unit.application.test_swing_weekly_facts import (
    _build as _weekly_build,
    _history as _weekly_history,
)


IST = ZoneInfo("Asia/Kolkata")
BOUNDARY = datetime(2026, 8, 14, 15, 30, tzinfo=IST)


def _pivots(direction: V1Direction, radius: int) -> FactualPivotSeries:
    if direction is V1Direction.LONG:
        highs, lows = (100.0, 110.0), (80.0, 90.0)
    elif direction is V1Direction.SHORT:
        highs, lows = (110.0, 100.0), (90.0, 80.0)
    else:
        highs, lows = (100.0, 110.0), (90.0, 80.0)
    if radius == 1:
        highs = tuple(item + 5.0 for item in highs)
        lows = tuple(item + 15.0 for item in lows)
    return FactualPivotSeries(
        f"FRACTAL_UNIQUE_EXTREME_RADIUS_{radius}",
        radius,
        tuple(
            PivotCandidate(
                PivotKind.HIGH,
                index,
                BOUNDARY - timedelta(days=4 - index),
                value,
            )
            for index, value in enumerate(highs)
        ),
        tuple(
            PivotCandidate(
                PivotKind.LOW,
                index + 2,
                BOUNDARY - timedelta(days=2 - index),
                value,
            )
            for index, value in enumerate(lows)
        ),
    )


def _fact(
    timeframe: FactualTimeframe,
    *,
    close: float = 120.0,
    low: float | None = None,
    high: float | None = None,
    r1: V1Direction = V1Direction.LONG,
    r2: V1Direction = V1Direction.LONG,
    moving_averages: bool = True,
    bucket: str | None = None,
) -> CompletedTimeframeFact:
    low = close - 2.0 if low is None else low
    high = close + 2.0 if high is None else high
    return CompletedTimeframeFact(
        timeframe,
        BOUNDARY,
        BOUNDARY - timedelta(hours=1),
        close,
        high,
        low,
        close,
        1_000,
        "KRONOS-MARKET-CALENDAR-V1",
        "2026.1.0",
        "REGULAR",
        "Asia/Kolkata",
        "DAY" if timeframe in {FactualTimeframe.WEEKLY, FactualTimeframe.DAILY} else "60minute",
        "KITE",
        BOUNDARY,
        ("provider=KITE", "completed=true"),
        (_pivots(r1, 1), _pivots(r2, 2)),
        (
            FactualMovingAverageFacts(205, 100.0, 95.0, 85.0, 99.0, 94.0, 84.0)
            if moving_averages
            else None
        ),
        FactualVolumeFacts(1_000, 900.0),
        bucket,
    )


@pytest.fixture(scope="module")
def weekly_foundations():  # type: ignore[no-untyped-def]
    rising, _, _ = _weekly_build(_weekly_history("rising"))
    falling, _, _ = _weekly_build(_weekly_history("falling"))
    flat, _, _ = _weekly_build(_weekly_history("flat"))
    unavailable, _, _ = _weekly_build(_weekly_history()[-100:])
    return rising, falling, flat, unavailable


def test_weekly_supportive_neutral_opposing_and_unavailable(weekly_foundations) -> None:  # type: ignore[no-untyped-def]
    rising, falling, flat, unavailable = weekly_foundations
    assert classify_native_weekly(rising, V1Direction.LONG)[0] is Native1WState.SUPPORTIVE
    assert classify_native_weekly(flat, V1Direction.LONG)[0] is Native1WState.NEUTRAL
    assert classify_native_weekly(falling, V1Direction.LONG)[0] is Native1WState.OPPOSING
    assert classify_native_weekly(unavailable, V1Direction.LONG)[0] is Native1WState.UNAVAILABLE


def test_weekly_crossing_is_transitional_and_pivots_are_not_required(weekly_foundations) -> None:  # type: ignore[no-untyped-def]
    rising, _, _, _ = weekly_foundations
    crossing = replace(
        rising,
        latest_close_relation=FactualPriceRelation.BELOW,
        latest_weekly_close=0.0,
    )
    no_pivots = replace(
        rising,
        radius_2_structure=WeeklyPivotFacts(
            2, None, None, None, None, None, None,
            FactualStructureCondition.INCOMPLETE,
        ),
    )
    assert classify_native_weekly(crossing, V1Direction.LONG)[0] is Native1WState.NEUTRAL
    assert classify_native_weekly(no_pivots, V1Direction.LONG)[0] is Native1WState.SUPPORTIVE


def test_weekly_missing_required_sma_is_unavailable(weekly_foundations) -> None:  # type: ignore[no-untyped-def]
    rising, _, _, _ = weekly_foundations
    missing = replace(
        rising,
        availability=WeeklyFactAvailability.UNAVAILABLE,
        unavailable_reason="INSUFFICIENT_PROVIDER_HISTORY",
        current_sma200=None,
        prior_sma200_5w=None,
        sma200_difference=None,
        sma200_direction=None,
        latest_weekly_close=None,
        latest_close_relation=None,
        radius_2_structure=None,
        radius_1_developing=None,
        observation_boundary=None,
    )
    assert classify_native_weekly(missing, V1Direction.LONG)[0] is Native1WState.UNAVAILABLE


def test_daily_bullish_and_bearish_establishment() -> None:
    bullish = classify_native_daily(_fact(FactualTimeframe.DAILY))[0:2]
    bearish = classify_native_daily(
        _fact(FactualTimeframe.DAILY, close=70.0, r1=V1Direction.SHORT, r2=V1Direction.SHORT)
    )[0:2]
    assert bullish == (Native1DState.BULLISH_SWING_REGIME, V1Direction.LONG)
    assert bearish == (Native1DState.BEARISH_SWING_REGIME, V1Direction.SHORT)


@pytest.mark.parametrize("close", (99.0, 95.0, 94.0))
def test_daily_sma_pullback_and_sma50_deterioration_preserve_regime(close: float) -> None:
    predecessor = SimpleNamespace(
        daily_state=Native1DState.BULLISH_SWING_REGIME,
        direction=V1Direction.LONG,
    )
    state, direction, reason = classify_native_daily(
        _fact(FactualTimeframe.DAILY, close=close, r1=V1Direction.SHORT, r2=V1Direction.LONG),
        predecessor,
    )
    assert (state, direction) == (Native1DState.BULLISH_SWING_REGIME, V1Direction.LONG)
    assert "STRUCTURE_INTACT" in reason[0]


def test_daily_structural_failure_requires_close_not_wick() -> None:
    predecessor = SimpleNamespace(
        daily_state=Native1DState.BULLISH_SWING_REGIME,
        direction=V1Direction.LONG,
    )
    wick = _fact(FactualTimeframe.DAILY, close=92.0, low=70.0)
    failed = _fact(FactualTimeframe.DAILY, close=89.0, low=70.0)
    assert classify_native_daily(wick, predecessor)[0] is Native1DState.BULLISH_SWING_REGIME
    assert classify_native_daily(failed, predecessor)[0] is Native1DState.NO_VALID_SWING_REGIME


def test_daily_bearish_structural_failure_is_symmetric() -> None:
    predecessor = SimpleNamespace(
        daily_state=Native1DState.BEARISH_SWING_REGIME,
        direction=V1Direction.SHORT,
    )
    fact = _fact(FactualTimeframe.DAILY, close=101.0, r1=V1Direction.LONG, r2=V1Direction.SHORT)
    assert classify_native_daily(fact, predecessor)[0] is Native1DState.NO_VALID_SWING_REGIME


def test_daily_reversal_developing_both_directions() -> None:
    bullish = _fact(
        FactualTimeframe.DAILY, close=100.0, low=80.0,
        r1=V1Direction.LONG, r2=V1Direction.SHORT,
    )
    bearish = _fact(
        FactualTimeframe.DAILY, close=80.0, high=110.0,
        r1=V1Direction.SHORT, r2=V1Direction.LONG,
    )
    assert classify_native_daily(bullish)[0] is Native1DState.BULLISH_REVERSAL_DEVELOPING
    assert classify_native_daily(bearish)[0] is Native1DState.BEARISH_REVERSAL_DEVELOPING


def test_daily_complete_nonqualifying_and_unavailable() -> None:
    mixed = _fact(FactualTimeframe.DAILY, close=97.0, r1=V1Direction.NONE, r2=V1Direction.NONE)
    unavailable = _fact(FactualTimeframe.DAILY, moving_averages=False)
    assert classify_native_daily(mixed)[0] is Native1DState.NO_VALID_SWING_REGIME
    assert classify_native_daily(unavailable)[0] is Native1DState.UNAVAILABLE


def test_four_hour_developing_pullback_and_session_remainder_are_valid() -> None:
    daily = _fact(FactualTimeframe.DAILY)
    four = _fact(
        FactualTimeframe.FOUR_HOUR, close=104.0,
        r1=V1Direction.SHORT, r2=V1Direction.LONG,
        bucket="SESSION_REMAINDER",
    )
    state, anchor, _ = classify_native_four_hour(
        daily, four, Native1DState.BULLISH_SWING_REGIME, V1Direction.LONG
    )
    assert state is Native4HState.DEVELOPING_PULLBACK
    assert anchor is not None


def test_four_hour_structural_hold_uses_exact_interaction_and_supportive_close() -> None:
    daily = _fact(FactualTimeframe.DAILY)
    four = _fact(
        FactualTimeframe.FOUR_HOUR, close=96.0, low=94.0, high=97.0,
        r1=V1Direction.SHORT, bucket="FULL_DURATION",
    )
    state, anchor, _ = classify_native_four_hour(
        daily, four, Native1DState.BULLISH_SWING_REGIME, V1Direction.LONG
    )
    assert state is Native4HState.STRUCTURAL_HOLD
    assert anchor is not None and anchor.price in {90.0, 95.0, 100.0}


@pytest.mark.parametrize("previous", (None, Native4HState.STRUCTURAL_HOLD))
def test_four_hour_direct_or_post_hold_resumption(previous: Native4HState | None) -> None:
    daily = _fact(FactualTimeframe.DAILY)
    four = _fact(
        FactualTimeframe.FOUR_HOUR, close=106.0,
        r1=V1Direction.SHORT, r2=V1Direction.LONG,
        bucket="FULL_DURATION",
    )
    assert classify_native_four_hour(
        daily, four, Native1DState.BULLISH_SWING_REGIME,
        V1Direction.LONG, previous,
    )[0] is Native4HState.RESUMPTION_DEVELOPING


def test_four_hour_continuation_deterioration_failure_and_fallback() -> None:
    daily = _fact(FactualTimeframe.DAILY)
    continuation = _fact(FactualTimeframe.FOUR_HOUR, close=116.0, bucket="FULL_DURATION")
    deterioration = _fact(FactualTimeframe.FOUR_HOUR, close=100.0, bucket="FULL_DURATION")
    failure = _fact(FactualTimeframe.FOUR_HOUR, close=89.0, bucket="FULL_DURATION")
    fallback = _fact(
        FactualTimeframe.FOUR_HOUR, close=112.0,
        r1=V1Direction.NONE, r2=V1Direction.LONG, bucket="FULL_DURATION",
    )
    args = (daily, Native1DState.BULLISH_SWING_REGIME, V1Direction.LONG)
    assert classify_native_four_hour(args[0], continuation, *args[1:])[0] is Native4HState.CONTINUATION_DEVELOPING
    assert classify_native_four_hour(args[0], deterioration, *args[1:])[0] is Native4HState.DETERIORATING
    assert classify_native_four_hour(args[0], failure, *args[1:])[0] is Native4HState.FAILED
    assert classify_native_four_hour(args[0], fallback, *args[1:])[0] is Native4HState.NO_CURRENT_OPPORTUNITY


def test_four_hour_unavailable_and_absent_daily_regime_do_not_manufacture_failure() -> None:
    daily = _fact(FactualTimeframe.DAILY)
    incomplete = replace(
        _fact(FactualTimeframe.FOUR_HOUR, bucket="FULL_DURATION"),
        structural_measurements=(
            FactualPivotSeries("FRACTAL_UNIQUE_EXTREME_RADIUS_1", 1, (), ()),
            _pivots(V1Direction.LONG, 2),
        ),
    )
    assert classify_native_four_hour(
        daily, incomplete, Native1DState.BULLISH_SWING_REGIME, V1Direction.LONG
    )[0] is Native4HState.UNAVAILABLE
    assert classify_native_four_hour(
        daily, incomplete, Native1DState.NO_VALID_SWING_REGIME, V1Direction.NONE
    ) == (
        Native4HState.UNAVAILABLE,
        None,
        ("VALID_DIRECTIONAL_DAILY_CONTEXT_UNAVAILABLE",),
    )


def test_daily_structural_failure_invalidates_four_hour_without_overloading_failed() -> None:
    predecessor = SimpleNamespace(
        daily_state=Native1DState.BULLISH_SWING_REGIME,
        direction=V1Direction.LONG,
    )
    failed_daily = _fact(FactualTimeframe.DAILY, close=89.0, low=70.0)
    daily_state, direction, daily_reasons = classify_native_daily(
        failed_daily,
        predecessor,
    )

    assert daily_reasons == ("DAILY_RADIUS2_STRUCTURAL_FAILURE",)
    assert classify_native_four_hour(
        failed_daily,
        _fact(FactualTimeframe.FOUR_HOUR, bucket="FULL_DURATION"),
        daily_state,
        direction,
    )[0] is Native4HState.UNAVAILABLE


def test_one_hour_progression_states() -> None:
    anchor = NativeAnchor(NativeAnchorType.FOUR_HOUR_RADIUS_2_STRUCTURE, 90.0, BOUNDARY)
    def classify(close: float, direction: V1Direction = V1Direction.LONG) -> Native1HState:
        return classify_native_one_hour(
            _fact(FactualTimeframe.ONE_HOUR, close=close, r1=direction),
            Native4HState.STRUCTURAL_HOLD,
            V1Direction.LONG,
            anchor,
        )[0]
    assert classify(116.0) is Native1HState.PROGRESSING
    assert classify(112.0) is Native1HState.STALLING
    assert classify(94.0, V1Direction.NONE) is Native1HState.DETERIORATING
    assert classify(102.0, V1Direction.NONE) is Native1HState.NEUTRAL
    assert classify(90.0) is Native1HState.FAILING
    assert classify_native_one_hour(
        _fact(FactualTimeframe.ONE_HOUR), Native4HState.UNAVAILABLE,
        V1Direction.LONG, None,
    )[0] is Native1HState.UNAVAILABLE


@pytest.mark.parametrize(
    ("exchange", "weekly", "four", "hour", "expected"),
    (
        ("NSE", Native1WState.SUPPORTIVE, Native4HState.STRUCTURAL_HOLD, Native1HState.PROGRESSING, NativeDiscoveryStatus.PROBABLE),
        ("NSE", Native1WState.NEUTRAL, Native4HState.DEVELOPING_PULLBACK, Native1HState.NEUTRAL, NativeDiscoveryStatus.FORMING_WATCH),
        ("NSE", Native1WState.OPPOSING, Native4HState.STRUCTURAL_HOLD, Native1HState.PROGRESSING, NativeDiscoveryStatus.UNAVAILABLE),
        ("NSE", Native1WState.UNAVAILABLE, Native4HState.STRUCTURAL_HOLD, Native1HState.PROGRESSING, NativeDiscoveryStatus.UNAVAILABLE),
        ("NSE", Native1WState.SUPPORTIVE, Native4HState.DETERIORATING, Native1HState.NEUTRAL, NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY),
        ("NSE", Native1WState.SUPPORTIVE, Native4HState.STRUCTURAL_HOLD, Native1HState.DETERIORATING, NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY),
        ("NSE", Native1WState.SUPPORTIVE, Native4HState.STRUCTURAL_HOLD, Native1HState.STALLING, NativeDiscoveryStatus.PROBABLE),
        ("NSE", Native1WState.SUPPORTIVE, Native4HState.STRUCTURAL_HOLD, Native1HState.NEUTRAL, NativeDiscoveryStatus.PROBABLE),
        ("MCX", Native1WState.NOT_APPLICABLE, Native4HState.STRUCTURAL_HOLD, Native1HState.NEUTRAL, NativeDiscoveryStatus.PROBABLE),
    ),
)
def test_native_composition_precedence(
    exchange: str,
    weekly: Native1WState,
    four: Native4HState,
    hour: Native1HState,
    expected: NativeDiscoveryStatus,
) -> None:
    assert native._compose(
        exchange,
        weekly,
        Native1DState.BULLISH_SWING_REGIME,
        four,
        hour,
        V1Direction.LONG,
    )[0] is expected


def test_daily_failure_and_mcx_insufficient_history_block() -> None:
    assert native._compose(
        "NSE", Native1WState.SUPPORTIVE,
        Native1DState.NO_VALID_SWING_REGIME,
        Native4HState.STRUCTURAL_HOLD, Native1HState.PROGRESSING,
        V1Direction.NONE,
    )[0] is NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY
    assert native._compose(
        "MCX", Native1WState.NOT_APPLICABLE,
        Native1DState.UNAVAILABLE,
        Native4HState.UNAVAILABLE, Native1HState.UNAVAILABLE,
        V1Direction.NONE,
    )[0] is NativeDiscoveryStatus.UNAVAILABLE


def test_reference_markets_are_absent_from_native_discovery_authority() -> None:
    source = Path(native.__file__).read_text(encoding="utf-8")
    assert "COMEX" not in source
    assert "NYMEX" not in source
    assert "classify_probable_from_existing_evidence" not in source
    assert "measure_shadow_timeframe" not in source


@pytest.fixture(scope="module")
def native_run():  # type: ignore[no-untyped-def]
    snapshot, _ = _mtf_build()
    return discover_native_mtf(snapshot)


def test_native_composition_is_same_98_and_mcx_has_no_weekly_gate(native_run) -> None:  # type: ignore[no-untyped-def]
    assert len(native_run.assessments) == 98
    mcx = tuple(item for item in native_run.assessments if item.product_path.value.startswith("MCX"))
    assert len(mcx) == 5
    assert all(item.weekly_state is Native1WState.NOT_APPLICABLE for item in mcx)
    assert all(item.authority == NATIVE_DISCOVERY_AUTHORITY for item in native_run.assessments)
    assert native_run.policy_identity == NATIVE_DISCOVERY_POLICY_ID


def test_native_persistence_restores_exact_levels_and_run_binding(tmp_path: Path, native_run) -> None:  # type: ignore[no-untyped-def]
    store = NativeDiscoveryEvidenceStore(tmp_path)
    store.retain(native_run)
    restored = store.load(native_run.run_identity)
    assert restored == native_run
    assert restored.assessments[0].factual_levels == native_run.assessments[0].factual_levels
    with pytest.raises(ValueError, match="IMMUTABLE"):
        store.retain(replace(native_run, result_sha256="f" * 64))


def test_browser_compares_daily_control_with_native_mtf(native_run) -> None:  # type: ignore[no-untyped-def]
    snapshot = BrowserWorkspaceSnapshot(
        ProviderConnectionState.CONNECTED,
        AnalysisState.READY,
        98,
        swing_analysis_run_identity=native_run.run_identity,
    )
    rendered = render_native_discovery(snapshot, native_run)
    assert "DAILY CONTROL" in rendered
    assert "KRONOS NATIVE MTF" in rendered
    assert "NO READINESS OR EXECUTION AUTHORITY" in rendered
    assert native_run.assessments[0].canonical_instrument in rendered


def test_browser_does_not_display_failed_for_absent_directional_daily_context(native_run) -> None:  # type: ignore[no-untyped-def]
    assessment = replace(
        native_run.assessments[0],
        direction=V1Direction.NONE,
        daily_state=Native1DState.NO_VALID_SWING_REGIME,
        four_hour_state=Native4HState.UNAVAILABLE,
        one_hour_state=Native1HState.UNAVAILABLE,
        status=NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY,
        context_kind=None,
        opportunity_identity=None,
        operative_anchor=None,
        reason_codes=(
            "NO_APPROVED_DAILY_REGIME_OR_REVERSAL_PREDICATE",
            "VALID_DIRECTIONAL_DAILY_CONTEXT_UNAVAILABLE",
        ),
        result_sha256="f" * 64,
    )
    discovery = replace(
        native_run,
        assessments=(assessment, *native_run.assessments[1:]),
        result_sha256="e" * 64,
    )
    snapshot = BrowserWorkspaceSnapshot(
        ProviderConnectionState.CONNECTED,
        AnalysisState.READY,
        98,
        swing_analysis_run_identity=native_run.run_identity,
    )

    rendered = render_native_discovery(snapshot, discovery)
    card = rendered.split(
        f"<summary><strong>{assessment.canonical_instrument}</strong>",
        maxsplit=1,
    )[1].split("</details>", maxsplit=1)[0]

    assert "<span>4H</span><strong>UNAVAILABLE</strong>" in card
    assert "<span>4H</span><strong>FAILED</strong>" not in card
