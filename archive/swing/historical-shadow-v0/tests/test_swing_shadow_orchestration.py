from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from kronos.application.swing_shadow import (
    _weekly_candles,
    build_same_run_shadow_mtf,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import HistoricalCandle, HistoricalInterval
from kronos.swing.daily_data import SwingDailyDataset, SwingDailySeries, SwingDailyStatus
from kronos.swing.universe import SwingUniverseAssetClass, enabled_swing_phase1_universe
from kronos.swing.v1.models import ProbableClassification, V1Direction, V1Setup


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 8, 14, 23, 59, tzinfo=IST)


def _instrument(identity: str, exchange: str) -> InstrumentRecord:
    return InstrumentRecord(
        provider="KITE",
        exchange=exchange,
        segment="MCX" if exchange == "MCX" else "NSE",
        trading_symbol=identity,
        name=identity,
        instrument_type="FUT" if exchange == "MCX" else "EQ",
        expiry=date(2026, 8, 28) if exchange == "MCX" else None,
        tick_size=Decimal("0.05"),
        lot_size=1,
    )


def _candle(timestamp: datetime, offset: int) -> HistoricalCandle:
    price = 100.0 + offset * 0.1
    return HistoricalCandle(timestamp, price, price + 1.0, price - 1.0, price + 0.25, 100 + offset)


def _trading_dates(publisher: MarketCalendarPublisher, exchange: str, count: int) -> tuple[date, ...]:
    days = []
    cursor = date(2026, 8, 13)
    while len(days) < count:
        if publisher.is_trading_date(exchange, cursor):
            days.append(cursor)
        cursor -= timedelta(days=1)
    return tuple(reversed(days))


def _hourly(publisher: MarketCalendarPublisher, exchange: str) -> tuple[HistoricalCandle, ...]:
    candles = []
    for day in _trading_dates(publisher, exchange, 30):
        schedule = publisher.schedule(exchange, day, observed_at=NOW)
        assert schedule is not None and schedule.session_open is not None and schedule.session_close is not None
        cursor = schedule.session_open
        while cursor < schedule.session_close:
            candles.append(_candle(cursor, len(candles)))
            cursor += timedelta(hours=1)
    return tuple(candles)


def _daily_history(
    publisher: MarketCalendarPublisher,
    exchange: str,
) -> tuple[HistoricalCandle, ...]:
    publication = publisher.publication(exchange)
    days = tuple(
        day
        for day in sorted(publication.trading_dates)
        if day <= date(2026, 8, 13)
    )
    return tuple(
        _candle(datetime(day.year, day.month, day.day, tzinfo=IST), index)
        for index, day in enumerate(days)
    )


def test_same_run_shadow_fetches_60minute_for_same_98_and_uses_calendar_derivations() -> None:
    publisher = MarketCalendarPublisher()
    records = []
    layer1 = []
    for member in enabled_swing_phase1_universe():
        exchange = "MCX" if member.asset_class is SwingUniverseAssetClass.MCX_COMMODITY else "NSE"
        instrument = _instrument(member.canonical_identity, exchange)
        days = _trading_dates(publisher, exchange, 30)
        daily = tuple(
            _candle(datetime(day.year, day.month, day.day, tzinfo=IST), index)
            for index, day in enumerate(days)
        )
        records.append(SwingDailySeries(
            member.canonical_identity,
            member.asset_class,
            SwingDailyStatus.READY,
            daily,
            daily[-1].timestamp,
            None,
            instrument,
        ))
        assessments = (
            (
                SimpleNamespace(
                    classification=ProbableClassification.PROBABLE_CANDIDATE,
                    setup=V1Setup.PULLBACK_CONTINUATION,
                    direction=V1Direction.LONG,
                ),
                SimpleNamespace(
                    classification=ProbableClassification.PROBABLE_CANDIDATE,
                    setup=V1Setup.CONSOLIDATION_BREAKOUT,
                    direction=V1Direction.LONG,
                ),
            )
            if member.canonical_identity == "BDL"
            else ()
        )
        layer1.append(SimpleNamespace(
            canonical_identity=member.canonical_identity,
            assessments=assessments,
        ))
    dataset = SwingDailyDataset(30, tuple(records))
    hourly = {exchange: _hourly(publisher, exchange) for exchange in ("NSE", "MCX")}
    daily_history = {
        exchange: _daily_history(publisher, exchange)
        for exchange in ("NSE", "MCX")
    }
    requests = []

    def historical(request):  # type: ignore[no-untyped-def]
        requests.append(request)
        return (
            hourly[request.instrument.exchange]
            if request.interval is HistoricalInterval.SIXTY_MINUTE
            else daily_history[request.instrument.exchange]
        )

    run = build_same_run_shadow_mtf(
        run_identity="SWING-RUN-0123456789ABCDEF0123456789ABCDEF",
        daily_dataset=dataset,
        v1_layer1_run=SimpleNamespace(instruments=tuple(layer1)),
        historical_candles=historical,
        calendar_publisher=publisher,
        observed_at=NOW,
    )

    assert len(run.assessments) == 98
    assert {item.canonical_instrument for item in run.assessments} == {
        item.canonical_identity for item in enabled_swing_phase1_universe()
    }
    assert sum(
        request.interval is HistoricalInterval.SIXTY_MINUTE
        for request in requests
    ) == 98
    assert sum(request.interval is HistoricalInterval.DAY for request in requests) == 98
    assert len(requests) == 196
    assert all(len(record.candles) == 30 for record in dataset.records)
    day_requests = tuple(
        request
        for request in requests
        if request.interval is HistoricalInterval.DAY
    )
    assert all(
        request.start.astimezone(IST).date()
        == publisher.publication(request.instrument.exchange).coverage_start
        for request in day_requests
    )
    assert run.run_identity == "SWING-RUN-0123456789ABCDEF0123456789ABCDEF"
    assert all(item.control.reason.startswith("UNCHANGED_DAILY_LAYER1") for item in run.assessments)
    assert all(item.authority == "SHADOW_VALIDATION_ONLY" for item in run.assessments)
    assert all(item.weekly.completed and item.four_hour.completed and item.one_hour.completed for item in run.assessments)
    bdl = next(item for item in run.assessments if item.canonical_instrument == "BDL")
    assert bdl.control.candidate is True
    assert tuple(item.setup for item in bdl.control.probable_identities) == (
        V1Setup.PULLBACK_CONTINUATION,
        V1Setup.CONSOLIDATION_BREAKOUT,
    )


def test_weekly_shadow_uses_separate_history_beyond_daily_control_depth() -> None:
    publisher = MarketCalendarPublisher()
    history = _daily_history(publisher, "NSE")
    weekly = _weekly_candles(
        "NSE",
        "BDL",
        history,
        publisher,
        NOW,
    )
    assert len(history) > 30
    assert len(weekly) >= 30
    assert weekly[-1].timestamp.date() == date(2026, 8, 7)
