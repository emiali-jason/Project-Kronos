"""Contract-local retained 4H correspondence; no acquisition or admission authority."""
from dataclasses import replace
from datetime import timedelta
from zoneinfo import ZoneInfo

from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.mcx_history import McxHistoryError
from kronos.market.derived_timeframes import (
    derive_session_four_hour_bars, DerivedBarStatus, DerivedBucketClass,
)
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.provider.contracts.market_data import HistoricalCandle


def native_four_hour(*, cycle, binding, selection, history, calendar):
    """Use the last full governed bucket in selected current/prior context.

    Missing latest bucket membership fails closed; it cannot fall back to an
    older complete bucket. Reference records never enter the native selection.
    """
    try:
        retained = history.load_contract(
            canonical_subject_identity=cycle.canonical_subject_identity,
            canonical_contract_identity=binding.active_binding.derivative_contract_id)
    except McxHistoryError as error:
        if str(error) == "MCX_HISTORY_CONTRACT_UNAVAILABLE":
            return None, None
        raise
    hourly = tuple(x for x in retained if x.timeframe is IntradayTimeframe.ONE_HOUR)
    for item in hourly:
        item.__post_init__()
        if (item.canonical_subject_identity != cycle.canonical_subject_identity
            or item.canonical_contract_identity != binding.active_binding.derivative_contract_id
            or item.provider_record_identity != binding.provider_record_identity):
            raise McxHistoryError("MCX_CHART_SOURCE_BINDING_INVALID")
    # Context dates come from the exact Review selection, not current wall time.
    days = sorted({x.candle.candle_start.astimezone(ZoneInfo("Asia/Kolkata")).date()
                   for x in selection.selected_candles
                   if x.candle.timeframe in (IntradayTimeframe.DAILY, IntradayTimeframe.ONE_HOUR)})
    candidates = []
    for day in days:
        profile = calendar.instrument_session_profile("MCX", day,
            canonical_instrument_id=cycle.canonical_subject_identity,
            observed_at=cycle.analysis_boundary)
        if profile is None:
            return None, None
        schedule = profile.continuous_trading
        daily = MarketDaySchedule(schedule.exchange, day, schedule.session_identity,
            schedule.timezone, TradingDayStatus.TRADING,
            tuple(MarketWindow(w.window_open, w.window_close) for w in schedule.windows),
            schedule.source_identity, schedule.calendar_version)
        lawful = {(b.start, b.end) for b in
                  expected_candle_boundaries(daily, IntradayTimeframe.ONE_HOUR)}
        rows = tuple(x for x in hourly if x.candle_start.astimezone(ZoneInfo(schedule.timezone)).date() == day
                     and x.observation_boundary <= cycle.analysis_boundary)
        if len({x.candle_start for x in rows}) != len(rows):
            raise McxHistoryError("MCX_CHART_DUPLICATE_CONSTITUENT")
        for x in rows:
            if ((x.candle_start, x.candle_end) not in lawful
                or x.source_timestamp != x.candle_start
                or x.domain008_session_identity != schedule.session_identity
                or x.calendar_identity != schedule.calendar_identity
                or x.calendar_version != schedule.calendar_version):
                raise McxHistoryError("MCX_CHART_CONSTITUENT_SESSION_INVALID")
        sources = {x.provider_source_identity for x in rows}
        if len(sources) > 1:
            raise McxHistoryError("MCX_CHART_MIXED_SOURCE")
        bars = derive_session_four_hour_bars(
            canonical_instrument=cycle.canonical_subject_identity, schedule=schedule,
            sixty_minute_candles=tuple(HistoricalCandle(x.candle_start, float(x.open),
                float(x.high), float(x.low), float(x.close), x.volume) for x in rows),
            source_provider_identity=next(iter(sources), "SOURCE_NOT_RETAINED"),
            source_market_data_boundary=max((x.observation_boundary for x in rows), default=cycle.analysis_boundary),
            observed_at=cycle.analysis_boundary)
        by_start = {x.candle_start:x for x in rows}
        for bar in bars:
            if bar.bucket_class is not DerivedBucketClass.FULL_DURATION or bar.actual_duration != timedelta(hours=4):
                continue
            members = tuple(by_start[start] for start, _ in bar.constituent_boundaries if start in by_start)
            # Include immutable contract/candle/integrity identities in the derived proof.
            bar = replace(bar, provenance=bar.provenance + (binding.binding_identity,
                binding.integrity_identity, binding.active_binding.derivative_contract_id,
                binding.provider_record_identity, *(v for x in members for v in
                (x.candle_identity, x.integrity_identity, x.historical_binding_identity, x.source_operation_identity))))
            candidates.append((bar, schedule))
    if not candidates:
        return None, None
    bar, schedule = max(candidates, key=lambda pair: pair[0].derived_end)
    return (bar, schedule) if bar.status is DerivedBarStatus.COMPLETE else (None, schedule)
