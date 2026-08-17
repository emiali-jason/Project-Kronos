from dataclasses import fields
from datetime import date, datetime, timedelta
from decimal import Decimal
import inspect
from zoneinfo import ZoneInfo

from kronos.application import swing_mtf_facts
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_mtf_facts import (
    _completed_hourly,
    build_same_run_mtf_fact_snapshot,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.schedule import (
    AuthoritativeMarketScheduleFacts,
    MarketAvailability,
    MarketSessionWindow,
    NseMarketScheduleAdapter,
    ScheduleFreshness,
    ScheduleIntegrity,
)
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalInterval,
)
from kronos.swing.daily_data import (
    SwingDailyDataset,
    SwingDailySeries,
    SwingDailyStatus,
)
from kronos.swing.universe import (
    SwingUniverseAssetClass,
    enabled_swing_phase1_universe,
)
from kronos.swing.v1.mtf_facts import (
    FactualTimeframe,
    MTF_FACT_AUTHORITY,
    MtfFactEvidenceStore,
)


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 8, 14, 23, 59, tzinfo=IST)
RUN_ID = "SWING-RUN-0123456789ABCDEF0123456789ABCDEF"


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
    return HistoricalCandle(
        timestamp, price, price + 1.0, price - 1.0, price + 0.25, 100 + offset
    )


def _trading_dates(
    publisher: MarketCalendarPublisher,
    exchange: str,
    count: int,
) -> tuple[date, ...]:
    days = []
    cursor = NOW.date()
    while len(days) < count:
        if publisher.is_trading_date(exchange, cursor):
            days.append(cursor)
        cursor -= timedelta(days=1)
    return tuple(reversed(days))


def _daily_history(
    publisher: MarketCalendarPublisher,
    exchange: str,
) -> tuple[HistoricalCandle, ...]:
    publication = publisher.publication(exchange)
    days = tuple(
        day for day in sorted(publication.trading_dates) if day <= NOW.date()
    )
    return tuple(
        _candle(datetime(day.year, day.month, day.day, tzinfo=IST), index)
        for index, day in enumerate(days)
    )


def _hourly_history(
    publisher: MarketCalendarPublisher,
    exchange: str,
) -> tuple[HistoricalCandle, ...]:
    result = []
    for day in _trading_dates(publisher, exchange, 30):
        schedule = publisher.schedule(exchange, day, observed_at=NOW)
        assert schedule is not None
        assert schedule.session_open is not None
        assert schedule.session_close is not None
        cursor = schedule.session_open
        while cursor < schedule.session_close:
            result.append(_candle(cursor, len(result)))
            cursor += timedelta(hours=1)
    return tuple(result)


def _dataset(publisher: MarketCalendarPublisher) -> SwingDailyDataset:
    records = []
    for member in enabled_swing_phase1_universe():
        exchange = (
            "MCX"
            if member.asset_class is SwingUniverseAssetClass.MCX_COMMODITY
            else "NSE"
        )
        complete_days = _trading_dates(publisher, exchange, 30)
        candles = tuple(
            _candle(datetime(day.year, day.month, day.day, tzinfo=IST), index)
            for index, day in enumerate(complete_days)
        )
        records.append(SwingDailySeries(
            member.canonical_identity,
            member.asset_class,
            SwingDailyStatus.READY,
            candles,
            candles[-1].timestamp,
            None,
            _instrument(member.canonical_identity, exchange),
        ))
    return SwingDailyDataset(30, tuple(records))


def _build(short_nse_identity: str | None = None):  # type: ignore[no-untyped-def]
    publisher = MarketCalendarPublisher()
    dataset = _dataset(publisher)
    daily = {
        exchange: _daily_history(publisher, exchange)
        for exchange in ("NSE", "MCX")
    }
    hourly = {
        exchange: _hourly_history(publisher, exchange)
        for exchange in ("NSE", "MCX")
    }
    requests = []

    def retrieve(request):  # type: ignore[no-untyped-def]
        requests.append(request)
        result = (
            daily[request.instrument.exchange]
            if request.interval is HistoricalInterval.DAY
            else hourly[request.instrument.exchange]
        )
        if (
            short_nse_identity is not None
            and request.instrument.trading_symbol == short_nse_identity
            and request.interval is HistoricalInterval.DAY
        ):
            return result[-100:]
        return result

    snapshot = build_same_run_mtf_fact_snapshot(
        run_identity=RUN_ID,
        daily_dataset=dataset,
        historical_candles=retrieve,
        calendar_publisher=publisher,
        observed_at=NOW,
    )
    return snapshot, requests


def test_same_run_factual_mtf_snapshot_uses_fresh_same_98_provider_histories() -> None:
    snapshot, requests = _build()

    assert snapshot.run_identity == RUN_ID
    assert len(snapshot.instruments) == 98
    assert tuple(item.canonical_instrument for item in snapshot.instruments) == tuple(
        member.canonical_identity for member in enabled_swing_phase1_universe()
    )
    assert len(requests) == 196
    assert sum(item.interval is HistoricalInterval.DAY for item in requests) == 98
    assert sum(
        item.interval is HistoricalInterval.SIXTY_MINUTE for item in requests
    ) == 98
    assert all(item.end == NOW.astimezone(item.end.tzinfo) for item in requests)
    assert all(
        item.start.astimezone(IST).date()
        == MarketCalendarPublisher().publication(item.instrument.exchange).coverage_start
        for item in requests
        if item.interval is HistoricalInterval.DAY
    )
    assert all(
        item.start == item.end - timedelta(days=60)
        for item in requests
        if item.interval is HistoricalInterval.SIXTY_MINUTE
    )
    assert snapshot.quote_context is None
    assert all(
        tuple(fact.timeframe for fact in instrument.timeframes)
        == tuple(FactualTimeframe)
        for instrument in snapshot.instruments
    )
    assert all(
        fact.authority == MTF_FACT_AUTHORITY
        and fact.observation_boundary <= NOW
        and fact.exchange_timezone == "Asia/Kolkata"
        and fact.calendar_identity
        and fact.calendar_version
        and fact.session_identity
        and fact.provenance
        for instrument in snapshot.instruments
        for fact in instrument.timeframes
    )


def test_snapshot_records_completed_derived_week_and_shortened_four_hour_remainder() -> None:
    snapshot, _ = _build()
    nse = snapshot.instrument("RELIANCE")
    mcx = snapshot.instrument("GOLDM")

    assert nse.fact(FactualTimeframe.WEEKLY).observation_boundary <= NOW
    assert mcx.fact(FactualTimeframe.WEEKLY).observation_boundary <= NOW
    assert nse.fact(FactualTimeframe.FOUR_HOUR).bucket_class == "SESSION_REMAINDER"
    assert mcx.fact(FactualTimeframe.FOUR_HOUR).bucket_class in {
        "FULL_DURATION", "SESSION_REMAINDER"
    }


def test_snapshot_retains_exact_ma_and_explanatory_volume_facts() -> None:
    snapshot, _ = _build()
    reliance = snapshot.instrument("RELIANCE")
    goldm = snapshot.instrument("GOLDM")

    assert reliance.fact(FactualTimeframe.WEEKLY).moving_averages.sma200 is not None
    assert reliance.fact(FactualTimeframe.DAILY).moving_averages.sma50 is not None
    assert goldm.fact(FactualTimeframe.DAILY).moving_averages.sma50 is not None
    for instrument in (reliance, goldm):
        for timeframe in FactualTimeframe:
            fact = instrument.fact(timeframe)
            assert fact.moving_averages is not None
            assert fact.volume_facts is not None
            assert fact.volume_facts.current == fact.volume
            assert fact.volume_facts.authority == "FACTUAL_EXPLANATORY_ONLY"


def test_one_nse_weekly_unavailable_does_not_abort_same_98_factual_snapshot() -> None:
    snapshot, _ = _build("RELIANCE")

    unavailable = snapshot.instrument("RELIANCE").nse_weekly_foundation
    available = snapshot.instrument("INFY").nse_weekly_foundation
    assert unavailable is not None
    assert unavailable.availability.value == "UNAVAILABLE"
    assert available is not None
    assert available.availability.value == "AVAILABLE"
    assert len(snapshot.instruments) == 98


def test_incomplete_one_hour_candle_is_excluded_until_governed_boundary() -> None:
    publisher = MarketCalendarPublisher()
    schedule = publisher.schedule("NSE", NOW.date(), observed_at=NOW)
    assert schedule is not None and schedule.session_open is not None
    candle = _candle(schedule.session_open, 1)
    before_boundary = schedule.session_open + timedelta(minutes=59)
    after_boundary = schedule.session_open + timedelta(hours=1, minutes=1)

    assert _completed_hourly(
        "NSE", (candle,), publisher, before_boundary
    ) == ()
    completed = _completed_hourly(
        "NSE", (candle,), publisher, after_boundary
    )
    assert len(completed) == 1
    assert completed[0][2] == schedule.session_open + timedelta(hours=1)


def test_multi_window_hourly_completion_excludes_closed_gap_without_missing_evidence() -> None:
    day = NOW.date()
    windows = (
        MarketSessionWindow(
            "NSE-MULTI:WINDOW:1", 1,
            datetime(day.year, day.month, day.day, 9, 15, tzinfo=IST),
            datetime(day.year, day.month, day.day, 10, 15, tzinfo=IST),
        ),
        MarketSessionWindow(
            "NSE-MULTI:WINDOW:2", 2,
            datetime(day.year, day.month, day.day, 11, 30, tzinfo=IST),
            datetime(day.year, day.month, day.day, 12, 30, tzinfo=IST),
        ),
    )
    schedule = NseMarketScheduleAdapter().normalize(AuthoritativeMarketScheduleFacts(
        market_identity="NSE_CAPITAL_MARKET",
        exchange="NSE",
        trading_date=day,
        calendar_identity="NSE-MULTI",
        calendar_version="1",
        session_identity="NSE-MULTI-DATE",
        session_type="SPECIAL_LIVE_DR",
        session_open=None,
        session_close=None,
        timezone="Asia/Kolkata",
        market_availability=MarketAvailability.CLOSED,
        as_of=windows[-1].window_close,
        source_identity="DOMAIN-008",
        source_boundary=windows[-1].window_close,
        freshness_status=ScheduleFreshness.CURRENT,
        integrity_status=ScheduleIntegrity.VALID,
        provenance=("NSE-OFFICIAL-SPECIAL-SESSION",),
        windows=windows,
    ))

    class _Publisher:
        @staticmethod
        def publication(exchange):  # type: ignore[no-untyped-def]
            assert exchange == "NSE"
            return type("Publication", (), {"timezone": "Asia/Kolkata"})()

        @staticmethod
        def schedule(exchange, trading_date, *, observed_at):  # type: ignore[no-untyped-def]
            assert exchange == "NSE" and trading_date == day and observed_at == windows[-1].window_close
            return schedule

    candles = (
        _candle(windows[0].window_open, 1),
        _candle(datetime(day.year, day.month, day.day, 10, 30, tzinfo=IST), 2),
        _candle(windows[1].window_open, 3),
    )
    completed = _completed_hourly(
        "NSE", candles, _Publisher(), windows[-1].window_close  # type: ignore[arg-type]
    )

    assert tuple(item[0].timestamp for item in completed) == (
        windows[0].window_open,
        windows[1].window_open,
    )
    assert tuple(item[2] for item in completed) == (
        windows[0].window_close,
        windows[1].window_close,
    )


def test_factual_snapshot_has_no_shadow_pine_or_candidate_authority() -> None:
    source = inspect.getsource(swing_mtf_facts)
    forbidden = (
        "_form_probable(",
        "measure_shadow_timeframe(",
        "structural_evidence(",
        "from kronos.swing.v1.shadow_mtf",
    )
    assert all(item not in source for item in forbidden)
    assert {
        "setup", "direction", "classification", "candidate", "readiness"
    }.isdisjoint({item.name for item in fields(swing_mtf_facts.CompletedTimeframeFact)})


def test_factual_snapshot_is_restart_safe_and_immutable(tmp_path) -> None:
    snapshot, _ = _build()
    store = MtfFactEvidenceStore(tmp_path)

    first = store.retain(snapshot)
    assert first == store.retain(snapshot)
    assert store.load(RUN_ID) == snapshot
    assert store.latest() == snapshot
    assert (
        store.load(RUN_ID).instrument("RELIANCE").nse_weekly_foundation
        == snapshot.instrument("RELIANCE").nse_weekly_foundation
    )
    assert first.stat().st_mode & 0o777 == 0o600

    restarted = SwingOpportunitiesApplication(lambda: object())
    restarted.restore_mtf_fact_snapshot(store.load(RUN_ID))
    assert restarted.mtf_fact_snapshot() == snapshot
