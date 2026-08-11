"""Full-universe orchestration over the frozen Swing Zero engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandleRequest,
    HistoricalInterval,
)
from kronos.swing.daily_data import (
    SwingDailyDataset,
    SwingDailyFailure,
    SwingDailyStatus,
)
from kronos.swing.universe import SwingUniverseAssetClass
from kronos.swing.zero import (
    SWING_ZERO_POLICY_ID,
    SwingAnalysisError,
    SwingAnalysisFailure,
    SwingAssessment,
    SwingDirection,
    SwingSetup,
    SwingState,
    analyze_swing_zero,
)


class SwingMarketAssessmentFailure(StrEnum):
    """Sanitized Stage-4 failures outside the frozen analytical policy."""

    ANALYSIS_INPUT_UNAVAILABLE = "ANALYSIS_INPUT_UNAVAILABLE"
    UNEXPECTED_ANALYSIS_FAILURE = "UNEXPECTED_ANALYSIS_FAILURE"


AssessmentFailure = (
    SwingAnalysisFailure | SwingDailyFailure | SwingMarketAssessmentFailure
)


@dataclass(frozen=True, slots=True)
class SwingInstrumentAssessments:
    """Both independent Swing Zero outcomes, or one explicit failure."""

    canonical_identity: str
    asset_class: SwingUniverseAssetClass
    assessments: tuple[SwingAssessment, ...]
    failure: AssessmentFailure | None

    def __post_init__(self) -> None:
        successful = self.failure is None
        if (
            type(self.canonical_identity) is not str
            or not self.canonical_identity
            or type(self.asset_class) is not SwingUniverseAssetClass
            or type(self.assessments) is not tuple
            or any(type(item) is not SwingAssessment for item in self.assessments)
            or (successful and len(self.assessments) != 2)
            or (
                successful
                and tuple(item.setup for item in self.assessments)
                != (
                    SwingSetup.PULLBACK_CONTINUATION,
                    SwingSetup.CONSOLIDATION_BREAKOUT,
                )
            )
            or (not successful and self.assessments != ())
            or (
                not successful
                and not isinstance(
                    self.failure,
                    (
                        SwingAnalysisFailure,
                        SwingDailyFailure,
                        SwingMarketAssessmentFailure,
                    ),
                )
            )
        ):
            raise ValueError("SWING_INSTRUMENT_ASSESSMENTS_INVALID")


@dataclass(frozen=True, slots=True)
class SwingAssessmentCounts:
    """Descriptive setup-family counts with no ranking authority."""

    pullback_no_setup: int
    pullback_forming_long: int
    pullback_forming_short: int
    pullback_qualified_long: int
    pullback_qualified_short: int
    breakout_no_setup: int
    breakout_forming: int
    breakout_qualified_long: int
    breakout_qualified_short: int

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 0 for value in self.values()):
            raise ValueError("SWING_ASSESSMENT_COUNTS_INVALID")

    def values(self) -> tuple[int, ...]:
        return (
            self.pullback_no_setup,
            self.pullback_forming_long,
            self.pullback_forming_short,
            self.pullback_qualified_long,
            self.pullback_qualified_short,
            self.breakout_no_setup,
            self.breakout_forming,
            self.breakout_qualified_long,
            self.breakout_qualified_short,
        )


@dataclass(frozen=True, slots=True)
class SwingMarketAssessment:
    """Immutable full-universe result from the unchanged Swing Zero policy."""

    run_identity: str
    observation_boundary: datetime
    instruments: tuple[SwingInstrumentAssessments, ...]
    counts: SwingAssessmentCounts

    def __post_init__(self) -> None:
        identities = tuple(item.canonical_identity for item in self.instruments)
        if (
            self.run_identity
            != f"{SWING_ZERO_POLICY_ID}@{self.observation_boundary.isoformat()}"
            or self.observation_boundary.tzinfo is None
            or self.observation_boundary.utcoffset() is None
            or type(self.instruments) is not tuple
            or len(self.instruments) != 98
            or any(
                type(item) is not SwingInstrumentAssessments
                for item in self.instruments
            )
            or len(set(identities)) != len(identities)
            or type(self.counts) is not SwingAssessmentCounts
            or sum(self.counts.values()) != self.assessment_count
        ):
            raise ValueError("SWING_MARKET_ASSESSMENT_INVALID")

    @property
    def requested_count(self) -> int:
        return len(self.instruments)

    @property
    def assessed_count(self) -> int:
        return sum(item.failure is None for item in self.instruments)

    @property
    def failure_count(self) -> int:
        return self.requested_count - self.assessed_count

    @property
    def assessment_count(self) -> int:
        return sum(len(item.assessments) for item in self.instruments)


def assess_swing_market(dataset: SwingDailyDataset) -> SwingMarketAssessment:
    """Evaluate all available members without ranking or silent omission."""

    if type(dataset) is not SwingDailyDataset or dataset.requested_count != 98:
        raise ValueError("SWING_MARKET_ASSESSMENT_REQUEST_INVALID")
    ready_boundaries = tuple(
        record.observation_boundary
        for record in dataset.records
        if record.status is SwingDailyStatus.READY
        and record.observation_boundary is not None
    )
    if not ready_boundaries:
        raise ValueError("SWING_MARKET_ASSESSMENT_REQUEST_INVALID")
    common_boundary = min(ready_boundaries)

    results = tuple(
        _assess_instrument(record, common_boundary) for record in dataset.records
    )
    counts = _aggregate_counts(results)
    return SwingMarketAssessment(
        run_identity=f"{SWING_ZERO_POLICY_ID}@{common_boundary.isoformat()}",
        observation_boundary=common_boundary,
        instruments=results,
        counts=counts,
    )


def _assess_instrument(record, boundary: datetime) -> SwingInstrumentAssessments:  # type: ignore[no-untyped-def]
    if record.status is not SwingDailyStatus.READY:
        return SwingInstrumentAssessments(
            record.canonical_identity,
            record.asset_class,
            (),
            record.failure,
        )
    instrument = record._analysis_instrument
    if type(instrument) is not InstrumentRecord:
        return SwingInstrumentAssessments(
            record.canonical_identity,
            record.asset_class,
            (),
            SwingMarketAssessmentFailure.ANALYSIS_INPUT_UNAVAILABLE,
        )
    candles = tuple(
        candle for candle in record.candles if candle.timestamp <= boundary
    )
    if not candles:
        return SwingInstrumentAssessments(
            record.canonical_identity,
            record.asset_class,
            (),
            SwingMarketAssessmentFailure.ANALYSIS_INPUT_UNAVAILABLE,
        )
    try:
        assessments = analyze_swing_zero(
            HistoricalCandleRequest(
                instrument=instrument,
                start=candles[0].timestamp,
                end=boundary + timedelta(days=1),
                interval=HistoricalInterval.DAY,
            ),
            candles,
        )
    except SwingAnalysisError as error:
        return SwingInstrumentAssessments(
            record.canonical_identity,
            record.asset_class,
            (),
            error.failure,
        )
    except Exception:
        return SwingInstrumentAssessments(
            record.canonical_identity,
            record.asset_class,
            (),
            SwingMarketAssessmentFailure.UNEXPECTED_ANALYSIS_FAILURE,
        )
    return SwingInstrumentAssessments(
        record.canonical_identity,
        record.asset_class,
        assessments,
        None,
    )


def _aggregate_counts(
    instruments: tuple[SwingInstrumentAssessments, ...],
) -> SwingAssessmentCounts:
    assessments = tuple(
        assessment
        for instrument in instruments
        for assessment in instrument.assessments
    )

    def count(
        setup: SwingSetup,
        state: SwingState,
        direction: SwingDirection | None = None,
    ) -> int:
        return sum(
            assessment.setup is setup
            and assessment.state is state
            and (direction is None or assessment.direction is direction)
            for assessment in assessments
        )

    return SwingAssessmentCounts(
        pullback_no_setup=count(
            SwingSetup.PULLBACK_CONTINUATION,
            SwingState.NO_SETUP,
        ),
        pullback_forming_long=count(
            SwingSetup.PULLBACK_CONTINUATION,
            SwingState.FORMING,
            SwingDirection.LONG,
        ),
        pullback_forming_short=count(
            SwingSetup.PULLBACK_CONTINUATION,
            SwingState.FORMING,
            SwingDirection.SHORT,
        ),
        pullback_qualified_long=count(
            SwingSetup.PULLBACK_CONTINUATION,
            SwingState.QUALIFIED,
            SwingDirection.LONG,
        ),
        pullback_qualified_short=count(
            SwingSetup.PULLBACK_CONTINUATION,
            SwingState.QUALIFIED,
            SwingDirection.SHORT,
        ),
        breakout_no_setup=count(
            SwingSetup.CONSOLIDATION_BREAKOUT,
            SwingState.NO_SETUP,
        ),
        breakout_forming=count(
            SwingSetup.CONSOLIDATION_BREAKOUT,
            SwingState.FORMING,
        ),
        breakout_qualified_long=count(
            SwingSetup.CONSOLIDATION_BREAKOUT,
            SwingState.QUALIFIED,
            SwingDirection.LONG,
        ),
        breakout_qualified_short=count(
            SwingSetup.CONSOLIDATION_BREAKOUT,
            SwingState.QUALIFIED,
            SwingDirection.SHORT,
        ),
    )


__all__ = [
    "SwingAssessmentCounts",
    "SwingInstrumentAssessments",
    "SwingMarketAssessment",
    "SwingMarketAssessmentFailure",
    "assess_swing_market",
]
