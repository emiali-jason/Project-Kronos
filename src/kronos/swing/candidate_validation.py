"""Independent Stage-5 audit and extraction of qualified Swing candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.daily_data import SwingDailyDataset, SwingDailyStatus
from kronos.swing.market_assessment import SwingMarketAssessment
from kronos.swing.zero import (
    SWING_ZERO_POLICY_ID,
    SwingAssessment,
    SwingDirection,
    SwingSetup,
    SwingState,
    SwingTrend,
)


_SMA_PERIOD = 20
_SMA_SLOPE_BARS = 5
_PULLBACK_WINDOW = 5
_ATR_PERIOD = 14
_CONSOLIDATION_WINDOW = 10
_CONSOLIDATION_ATR_MULTIPLE = 2.5


@dataclass(frozen=True, slots=True)
class SwingCandidate:
    """One frozen QUALIFIED assessment eligible for later comparison."""

    canonical_identity: str
    setup: SwingSetup
    direction: SwingDirection
    observation_boundary: datetime
    rule_set_version: str
    assessment: SwingAssessment

    def __post_init__(self) -> None:
        if (
            type(self.canonical_identity) is not str
            or not self.canonical_identity
            or type(self.setup) is not SwingSetup
            or self.setup is SwingSetup.NONE
            or type(self.direction) is not SwingDirection
            or self.direction is SwingDirection.NONE
            or self.observation_boundary.tzinfo is None
            or self.observation_boundary.utcoffset() is None
            or self.rule_set_version != SWING_ZERO_POLICY_ID
            or type(self.assessment) is not SwingAssessment
            or self.assessment.setup is not self.setup
            or self.assessment.direction is not self.direction
            or self.assessment.state is not SwingState.QUALIFIED
            or self.assessment.observation_boundary != self.observation_boundary
            or self.assessment.rule_set_version != self.rule_set_version
        ):
            raise ValueError("SWING_CANDIDATE_INVALID")


@dataclass(frozen=True, slots=True)
class SwingPredicateAudit:
    """Independent predicate results for one extracted candidate."""

    candidate: SwingCandidate
    predicate_results: tuple[tuple[str, bool], ...]

    def __post_init__(self) -> None:
        if (
            type(self.candidate) is not SwingCandidate
            or type(self.predicate_results) is not tuple
            or not self.predicate_results
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or not item[0]
                or type(item[1]) is not bool
                for item in self.predicate_results
            )
        ):
            raise ValueError("SWING_PREDICATE_AUDIT_INVALID")

    @property
    def passed(self) -> bool:
        return all(result for _, result in self.predicate_results)


@dataclass(frozen=True, slots=True)
class SwingFormingAudit:
    """One deterministic representative of a non-candidate FORMING state."""

    canonical_identity: str
    setup: SwingSetup
    direction: SwingDirection
    missing_event: str
    passed: bool

    def __post_init__(self) -> None:
        if (
            type(self.canonical_identity) is not str
            or not self.canonical_identity
            or type(self.setup) is not SwingSetup
            or type(self.direction) is not SwingDirection
            or type(self.missing_event) is not str
            or not self.missing_event
            or type(self.passed) is not bool
        ):
            raise ValueError("SWING_FORMING_AUDIT_INVALID")


@dataclass(frozen=True, slots=True)
class SwingCandidateValidation:
    """Protected Stage-5 result with no comparison or selection authority."""

    observation_boundary: datetime
    candidates: tuple[SwingCandidate, ...]
    audits: tuple[SwingPredicateAudit, ...]
    forming_audits: tuple[SwingFormingAudit, ...]
    forming_leakage: int
    no_setup_leakage: int

    def __post_init__(self) -> None:
        identities = tuple(
            (candidate.canonical_identity, candidate.setup)
            for candidate in self.candidates
        )
        if (
            self.observation_boundary.tzinfo is None
            or self.observation_boundary.utcoffset() is None
            or type(self.candidates) is not tuple
            or any(type(item) is not SwingCandidate for item in self.candidates)
            or len(set(identities)) != len(identities)
            or type(self.audits) is not tuple
            or tuple(audit.candidate for audit in self.audits) != self.candidates
            or type(self.forming_audits) is not tuple
            or any(type(item) is not SwingFormingAudit for item in self.forming_audits)
            or type(self.forming_leakage) is not int
            or self.forming_leakage < 0
            or type(self.no_setup_leakage) is not int
            or self.no_setup_leakage < 0
        ):
            raise ValueError("SWING_CANDIDATE_VALIDATION_INVALID")

    @property
    def unique_instrument_count(self) -> int:
        return len({candidate.canonical_identity for candidate in self.candidates})

    @property
    def passed(self) -> bool:
        return (
            all(audit.passed for audit in self.audits)
            and all(audit.passed for audit in self.forming_audits)
            and self.forming_leakage == 0
            and self.no_setup_leakage == 0
        )


def extract_qualified_candidates(
    market: SwingMarketAssessment,
) -> tuple[SwingCandidate, ...]:
    """Deterministically retain every setup-level QUALIFIED assessment."""

    if type(market) is not SwingMarketAssessment:
        raise ValueError("SWING_CANDIDATE_EXTRACTION_INVALID")
    return tuple(
        SwingCandidate(
            canonical_identity=item.canonical_identity,
            setup=assessment.setup,
            direction=assessment.direction,
            observation_boundary=assessment.observation_boundary,
            rule_set_version=assessment.rule_set_version,
            assessment=assessment,
        )
        for item in market.instruments
        for assessment in item.assessments
        if assessment.state is SwingState.QUALIFIED
    )


def validate_qualified_candidates(
    market: SwingMarketAssessment,
    dataset: SwingDailyDataset,
) -> SwingCandidateValidation:
    """Audit QUALIFIED and representative FORMING states from one boundary."""

    if (
        type(market) is not SwingMarketAssessment
        or type(dataset) is not SwingDailyDataset
        or market.requested_count != dataset.requested_count
    ):
        raise ValueError("SWING_CANDIDATE_VALIDATION_REQUEST_INVALID")
    records = {record.canonical_identity: record for record in dataset.records}
    if tuple(records) != tuple(item.canonical_identity for item in market.instruments):
        raise ValueError("SWING_CANDIDATE_VALIDATION_REQUEST_INVALID")

    candidates = extract_qualified_candidates(market)
    audits = tuple(
        _audit_candidate(
            candidate,
            _candles_at_boundary(
                records[candidate.canonical_identity],
                market.observation_boundary,
            ),
        )
        for candidate in candidates
    )
    forming_audits = _forming_representatives(market, records)
    return SwingCandidateValidation(
        observation_boundary=market.observation_boundary,
        candidates=candidates,
        audits=audits,
        forming_audits=forming_audits,
        forming_leakage=sum(
            candidate.assessment.state is SwingState.FORMING
            for candidate in candidates
        ),
        no_setup_leakage=sum(
            candidate.assessment.state is SwingState.NO_SETUP
            for candidate in candidates
        ),
    )


def _candles_at_boundary(record, boundary: datetime) -> tuple[HistoricalCandle, ...]:  # type: ignore[no-untyped-def]
    if record.status is not SwingDailyStatus.READY:
        return ()
    return tuple(candle for candle in record.candles if candle.timestamp <= boundary)


def _audit_candidate(
    candidate: SwingCandidate,
    candles: tuple[HistoricalCandle, ...],
) -> SwingPredicateAudit:
    if len(candles) < 25:
        return SwingPredicateAudit(candidate, (("completed_history_available", False),))
    if candidate.setup is SwingSetup.PULLBACK_CONTINUATION:
        results = _audit_pullback(candidate, candles)
    else:
        results = _audit_breakout(candidate, candles)
    return SwingPredicateAudit(candidate, results)


def _audit_pullback(
    candidate: SwingCandidate,
    candles: tuple[HistoricalCandle, ...],
) -> tuple[tuple[str, bool], ...]:
    assessment = candidate.assessment
    current = candles[-1]
    previous = candles[-2]
    current_sma = _sma(candles, len(candles) - 1, _SMA_PERIOD)
    prior_sma = _sma(
        candles,
        len(candles) - 1 - _SMA_SLOPE_BARS,
        _SMA_PERIOD,
    )
    trend = _trend(current.close, current_sma, prior_sma)
    preceding_indexes = tuple(
        range(len(candles) - _PULLBACK_WINDOW - 1, len(candles) - 1)
    )
    long = candidate.direction is SwingDirection.LONG
    orderly = _orderly_pullback(candles, preceding_indexes, bullish=long)
    confirmation = (
        current.close > previous.high if long else current.close < previous.low
    )
    expected_trend = SwingTrend.BULLISH if long else SwingTrend.BEARISH
    expected_evidence = (
        f"current_close={_number(current.close)}",
        f"current_sma20={_number(current_sma)}",
        f"sma20_five_bars_earlier={_number(prior_sma)}",
        f"trend={expected_trend.value}",
        f"preceding_pullback_{'bullish' if long else 'bearish'}=true",
        f"previous_day_{'high' if long else 'low'}="
        f"{_number(previous.high if long else previous.low)}",
        f"continuation={'above_previous_day_high' if long else 'below_previous_day_low'}",
    )
    expected_why = (
        "Bullish trend continued above the previous-day high after an orderly "
        "preceding five-bar pullback."
        if long
        else "Bearish trend continued below the previous-day low after an orderly "
        "preceding five-bar pullback."
    )
    return (
        ("current_boundary_exact", current.timestamp == candidate.observation_boundary),
        ("trend_direction", trend is expected_trend),
        ("preceding_five_excludes_current", preceding_indexes[-1] == len(candles) - 2),
        ("preceding_five_orderly", orderly),
        ("confirmation_beyond_previous_extreme", confirmation),
        ("trend_valid_on_confirmation_boundary", trend is expected_trend),
        ("evidence_exact", assessment.evidence_for == expected_evidence),
        ("why_exact", assessment.why == expected_why),
        ("qualified_has_no_missing_event", assessment.next_required_event is None),
        ("qualified_has_no_recorded_risk", assessment.evidence_against_or_risks == ()),
    )


def _audit_breakout(
    candidate: SwingCandidate,
    candles: tuple[HistoricalCandle, ...],
) -> tuple[tuple[str, bool], ...]:
    assessment = candidate.assessment
    current = candles[-1]
    preceding = candles[-(_CONSOLIDATION_WINDOW + 1) : -1]
    range_high = max(candle.high for candle in preceding)
    range_low = min(candle.low for candle in preceding)
    range_width = range_high - range_low
    atr = _atr(candles, len(candles) - 2, _ATR_PERIOD)
    consolidated = range_width <= _CONSOLIDATION_ATR_MULTIPLE * atr
    current_sma = _sma(candles, len(candles) - 1, _SMA_PERIOD)
    prior_sma = _sma(
        candles,
        len(candles) - 1 - _SMA_SLOPE_BARS,
        _SMA_PERIOD,
    )
    trend = _trend(current.close, current_sma, prior_sma)
    expected_evidence = (
        f"current_close={_number(current.close)}",
        f"current_sma20={_number(current_sma)}",
        f"sma20_five_bars_earlier={_number(prior_sma)}",
        f"trend={trend.value}",
        f"range_high={_number(range_high)}",
        f"range_low={_number(range_low)}",
        f"range_width={_number(range_width)}",
        f"preceding_atr14={_number(atr)}",
        f"consolidation={'true' if consolidated else 'false'}",
        "breakout=below_range",
    )
    return (
        ("current_boundary_exact", current.timestamp == candidate.observation_boundary),
        ("preceding_ten_exact", len(preceding) == _CONSOLIDATION_WINDOW),
        ("preceding_ten_excludes_current", current not in preceding),
        ("range_high_preceding_only", range_high == max(item.high for item in preceding)),
        ("range_low_preceding_only", range_low == min(item.low for item in preceding)),
        ("atr14_ends_at_preceding_candle", atr == _atr(candles[:-1], len(candles) - 2, _ATR_PERIOD)),
        ("consolidation_threshold", consolidated),
        ("short_breakout", current.close < range_low),
        ("evidence_exact", assessment.evidence_for == expected_evidence),
        (
            "why_exact",
            assessment.why
            == "The completed close broke below the preceding ten-bar consolidation range.",
        ),
        ("qualified_has_no_missing_event", assessment.next_required_event is None),
        ("qualified_has_no_recorded_risk", assessment.evidence_against_or_risks == ()),
    )


def _forming_representatives(
    market: SwingMarketAssessment,
    records: dict[str, object],
) -> tuple[SwingFormingAudit, ...]:
    targets = (
        (SwingSetup.PULLBACK_CONTINUATION, SwingDirection.LONG),
        (SwingSetup.PULLBACK_CONTINUATION, SwingDirection.SHORT),
        (SwingSetup.CONSOLIDATION_BREAKOUT, SwingDirection.NONE),
    )
    representatives = []
    for setup, direction in targets:
        match = next(
            (
                (item.canonical_identity, assessment)
                for item in market.instruments
                for assessment in item.assessments
                if assessment.state is SwingState.FORMING
                and assessment.setup is setup
                and assessment.direction is direction
            ),
            None,
        )
        if match is None:
            continue
        identity, assessment = match
        candles = _candles_at_boundary(records[identity], market.observation_boundary)
        representatives.append(_audit_forming(identity, assessment, candles))
    return tuple(representatives)


def _audit_forming(
    identity: str,
    assessment: SwingAssessment,
    candles: tuple[HistoricalCandle, ...],
) -> SwingFormingAudit:
    if assessment.setup is SwingSetup.PULLBACK_CONTINUATION:
        bullish = assessment.direction is SwingDirection.LONG
        indexes = tuple(range(len(candles) - _PULLBACK_WINDOW, len(candles)))
        trend = _trend(
            candles[-1].close,
            _sma(candles, len(candles) - 1, _SMA_PERIOD),
            _sma(candles, len(candles) - 1 - _SMA_SLOPE_BARS, _SMA_PERIOD),
        )
        expected_trend = SwingTrend.BULLISH if bullish else SwingTrend.BEARISH
        event = (
            "Completed Daily close above previous-day high"
            if bullish
            else "Completed Daily close below previous-day low"
        )
        passed = (
            trend is expected_trend
            and _orderly_pullback(candles, indexes, bullish=bullish)
            and assessment.next_required_event == event
            and assessment.evidence_against_or_risks
            == ("continuation_confirmation_absent",)
        )
    else:
        preceding = candles[-(_CONSOLIDATION_WINDOW + 1) : -1]
        high = max(candle.high for candle in preceding)
        low = min(candle.low for candle in preceding)
        width = high - low
        atr = _atr(candles, len(candles) - 2, _ATR_PERIOD)
        event = "Completed Daily close outside prior ten-bar range"
        passed = (
            width <= _CONSOLIDATION_ATR_MULTIPLE * atr
            and low <= candles[-1].close <= high
            and assessment.next_required_event == event
            and assessment.evidence_against_or_risks
            == ("completed_breakout_absent",)
        )
    return SwingFormingAudit(identity, assessment.setup, assessment.direction, event, passed)


def _trend(close: float, current_sma: float, prior_sma: float) -> SwingTrend:
    if close > current_sma and current_sma > prior_sma:
        return SwingTrend.BULLISH
    if close < current_sma and current_sma < prior_sma:
        return SwingTrend.BEARISH
    return SwingTrend.NEUTRAL


def _orderly_pullback(
    candles: tuple[HistoricalCandle, ...],
    indexes: tuple[int, ...],
    *,
    bullish: bool,
) -> bool:
    closes = tuple(candles[index].close for index in indexes)
    previous = tuple(candles[index - 1].close for index in indexes)
    averages = tuple(_sma(candles, index, _SMA_PERIOD) for index in indexes)
    if bullish:
        return any(close < prior for close, prior in zip(closes, previous)) and all(
            close >= average for close, average in zip(closes, averages)
        )
    return any(close > prior for close, prior in zip(closes, previous)) and all(
        close <= average for close, average in zip(closes, averages)
    )


def _sma(candles: tuple[HistoricalCandle, ...], end: int, period: int) -> float:
    start = end - period + 1
    return sum(candle.close for candle in candles[start : end + 1]) / period


def _atr(candles, end: int, period: int) -> float:  # type: ignore[no-untyped-def]
    ranges = []
    for index in range(end - period + 1, end + 1):
        candle = candles[index]
        previous_close = candles[index - 1].close
        ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
    return sum(ranges) / period


def _number(value: float) -> str:
    return format(value, ".10g")


__all__ = [
    "SwingCandidate",
    "SwingCandidateValidation",
    "SwingFormingAudit",
    "SwingPredicateAudit",
    "extract_qualified_candidates",
    "validate_qualified_candidates",
]
