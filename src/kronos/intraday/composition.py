"""Core Slice-1 factual composition with no trading consequences."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from kronos.instrument.runtime import RuntimeInstrumentRegistry
from kronos.intraday.candles import (
    ReconciliationResult,
    reconcile_provider_candles,
)
from kronos.intraday.contracts import (
    IntradayInstrumentReference,
    IntradayRun,
    IntradayTimeframe,
    SourceProvenance,
    create_intraday_run,
)
from kronos.intraday.instrument import adapt_runtime_instrument
from kronos.intraday.market_context import IntradayMarketContextAdapter
from kronos.intraday.persistence import (
    IntradayFactualEvidence,
    LocalIntradayFactualEvidenceStore,
    create_factual_evidence,
)
from kronos.market.schedule import (
    MarketScheduleSource,
    MarketSessionFact,
    MarketSessionState,
)
from kronos.provider.contracts.market_data import HistoricalCandle


_TIMEFRAMES = (
    IntradayTimeframe.DAILY,
    IntradayTimeframe.ONE_HOUR,
    IntradayTimeframe.FIFTEEN_MINUTES,
    IntradayTimeframe.FIVE_MINUTES,
)


class CoreSlice1Failure(StrEnum):
    INSTRUMENT_UNAVAILABLE = "INSTRUMENT_UNAVAILABLE"
    MARKET_SCHEDULE_UNAVAILABLE = "MARKET_SCHEDULE_UNAVAILABLE"
    MARKET_NOT_TRADING = "MARKET_NOT_TRADING"
    DATA_INCOMPLETE = "DATA_INCOMPLETE"
    INVALID_REQUEST = "INVALID_REQUEST"


class CoreSlice1CompositionError(RuntimeError):
    def __init__(self, failure: CoreSlice1Failure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class CoreSlice1FactualComposition:
    run: IntradayRun
    instrument: IntradayInstrumentReference
    market_session: MarketSessionFact
    evidence: tuple[IntradayFactualEvidence, ...]

    def __post_init__(self) -> None:
        if (
            type(self.run) is not IntradayRun
            or type(self.instrument) is not IntradayInstrumentReference
            or type(self.market_session) is not MarketSessionFact
            or self.market_session.state
            not in {
                MarketSessionState.OPEN,
                MarketSessionState.BETWEEN_WINDOWS,
                MarketSessionState.SESSION_ENDED,
            }
            or tuple(item.reconciliation.timeframe for item in self.evidence)
            != _TIMEFRAMES
            or any(item.run != self.run for item in self.evidence)
            or any(
                item.reconciliation.instrument != self.instrument
                or item.reconciliation.result is not ReconciliationResult.COMPLETE
                for item in self.evidence
            )
        ):
            raise ValueError("CORE_SLICE_1_COMPOSITION_INVALID")


def compose_core_slice1_facts(
    *,
    instrument_registry: RuntimeInstrumentRegistry,
    canonical_instrument_id: str,
    calendar_source: MarketScheduleSource,
    exchange: str,
    trading_date: date,
    observed_at: datetime,
    run_created_at: datetime,
    provider_candles: Mapping[IntradayTimeframe, Sequence[HistoricalCandle]],
    provenance: Mapping[IntradayTimeframe, SourceProvenance],
    evidence_store: LocalIntradayFactualEvidenceStore,
) -> CoreSlice1FactualComposition:
    """Compose and persist one four-timeframe factual observation boundary."""

    if (
        type(instrument_registry) is not RuntimeInstrumentRegistry
        or not isinstance(canonical_instrument_id, str)
        or not canonical_instrument_id
        or not callable(getattr(calendar_source, "schedule_for", None))
        or type(trading_date) is not date
        or not _aware(observed_at)
        or not _aware(run_created_at)
        or run_created_at > observed_at
        or not isinstance(provider_candles, Mapping)
        or set(provider_candles) != set(_TIMEFRAMES)
        or not isinstance(provenance, Mapping)
        or set(provenance) != set(_TIMEFRAMES)
        or type(evidence_store) is not LocalIntradayFactualEvidenceStore
    ):
        raise CoreSlice1CompositionError(CoreSlice1Failure.INVALID_REQUEST)
    try:
        published = instrument_registry.require_consumable(canonical_instrument_id)
        instrument = adapt_runtime_instrument(published)
    except ValueError as error:
        raise CoreSlice1CompositionError(CoreSlice1Failure.INSTRUMENT_UNAVAILABLE) from error
    if instrument.exchange != exchange:
        raise CoreSlice1CompositionError(CoreSlice1Failure.INSTRUMENT_UNAVAILABLE)

    market = IntradayMarketContextAdapter(calendar_source).session_facts(
        exchange=exchange,
        trading_date=trading_date,
        observed_at=observed_at,
    )
    if not market.availability or market.schedule is None:
        raise CoreSlice1CompositionError(CoreSlice1Failure.MARKET_SCHEDULE_UNAVAILABLE)
    if market.state in {
        MarketSessionState.NON_TRADING_DAY,
        MarketSessionState.BEFORE_SESSION,
    }:
        raise CoreSlice1CompositionError(CoreSlice1Failure.MARKET_NOT_TRADING)

    run = create_intraday_run(
        created_at=run_created_at,
        observation_boundary=observed_at,
    )
    evidence: list[IntradayFactualEvidence] = []
    incomplete = False
    for timeframe in _TIMEFRAMES:
        supplied = provider_candles[timeframe]
        source = provenance[timeframe]
        if (
            isinstance(supplied, (str, bytes))
            or not isinstance(supplied, Sequence)
            or type(source) is not SourceProvenance
        ):
            raise CoreSlice1CompositionError(CoreSlice1Failure.INVALID_REQUEST)
        reconciliation = reconcile_provider_candles(
            instrument=instrument,
            timeframe=timeframe,
            schedule=market.schedule,
            provider_candles=supplied,
            observed_at=observed_at,
            provenance=source,
        )
        retained = create_factual_evidence(run, reconciliation)
        evidence_store.retain(retained)
        evidence.append(retained)
        incomplete = incomplete or reconciliation.result is not ReconciliationResult.COMPLETE
    if incomplete:
        raise CoreSlice1CompositionError(CoreSlice1Failure.DATA_INCOMPLETE)
    return CoreSlice1FactualComposition(
        run=run,
        instrument=instrument,
        market_session=market,
        evidence=tuple(evidence),
    )


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "CoreSlice1CompositionError",
    "CoreSlice1Failure",
    "CoreSlice1FactualComposition",
    "compose_core_slice1_facts",
]
