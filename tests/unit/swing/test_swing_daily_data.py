from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime, timedelta
import inspect
from zoneinfo import ZoneInfo

import pytest

from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import (
    InstrumentRecord,
    InstrumentResolutionError,
    InstrumentResolutionFailure,
)
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalDataError,
    HistoricalDataFailure,
    HistoricalInterval,
)
from kronos.swing.daily_data import (
    MINIMUM_COMPLETED_DAILY_CANDLES,
    OPERATIONAL_DAILY_HISTORY_DEPTH,
    SwingDailyDataset,
    SwingDailyFailure,
    SwingDailySeries,
    SwingDailyStatus,
    build_swing_daily_dataset,
)
from kronos.swing.universe import (
    SwingUniverseAssetClass,
    enabled_swing_phase1_universe,
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


def _candles(count: int, *, include_current: bool = False) -> tuple[HistoricalCandle, ...]:
    end_date = _NOW.date() if include_current else _NOW.date() - timedelta(days=1)
    start_date = end_date - timedelta(days=count - 1)
    return tuple(
        HistoricalCandle(
            timestamp=datetime.combine(
                start_date + timedelta(days=index),
                datetime.min.time(),
                tzinfo=_KOLKATA,
            ),
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=1000,
        )
        for index in range(count)
    )


def _dataset(
    candles=_candles(40),  # type: ignore[no-untyped-def]
    *,
    resolve=None,  # type: ignore[no-untyped-def]
) -> SwingDailyDataset:
    return build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=resolve or (lambda member: _instrument(member.canonical_identity)),
        historical_candles=lambda _request: candles,
        now=_NOW,
    )


def test_all_98_members_are_requested_in_canonical_order() -> None:
    requested: list[str] = []

    def resolve(member):  # type: ignore[no-untyped-def]
        requested.append(member.canonical_identity)
        return _instrument(member.canonical_identity)

    dataset = _dataset(resolve=resolve)

    expected = tuple(
        member.canonical_identity for member in enabled_swing_phase1_universe()
    )
    assert tuple(requested) == expected
    assert tuple(record.canonical_identity for record in dataset.records) == expected
    assert dataset.requested_count == 98
    assert dataset.ready_count == 98
    assert dataset.unavailable_count == 0


def test_operational_depth_is_30_and_latest_completed_candles_are_retained() -> None:
    supplied = _candles(40)
    dataset = _dataset(supplied)

    assert MINIMUM_COMPLETED_DAILY_CANDLES == 25
    assert OPERATIONAL_DAILY_HISTORY_DEPTH == 30
    assert dataset.history_depth == 30
    assert all(record.candles == supplied[-30:] for record in dataset.records)


def test_exact_25_completed_daily_candles_are_ready() -> None:
    dataset = _dataset(_candles(25))

    assert dataset.ready_count == 98
    assert all(len(record.candles) == 25 for record in dataset.records)


def test_current_incomplete_trading_day_is_excluded() -> None:
    supplied = _candles(31, include_current=True)
    dataset = _dataset(supplied)

    assert dataset.ready_count == 98
    assert all(len(record.candles) == 30 for record in dataset.records)
    assert all(
        record.observation_boundary.astimezone(_KOLKATA).date()
        < _NOW.astimezone(_KOLKATA).date()
        for record in dataset.records
        if record.observation_boundary is not None
    )


def test_domain_008_excludes_same_day_before_close_and_includes_it_after_close() -> None:
    publisher = MarketCalendarPublisher()
    trading_date = date(2026, 8, 14)
    calendar_reference = datetime(2026, 8, 14, 23, 59, tzinfo=_KOLKATA)
    nse = publisher.schedule("NSE", trading_date, observed_at=calendar_reference)
    mcx = publisher.schedule("MCX", trading_date, observed_at=calendar_reference)
    assert nse is not None and nse.session_close is not None
    assert mcx is not None and mcx.session_close is not None
    before = min(nse.session_close, mcx.session_close) - timedelta(minutes=1)
    after = max(nse.session_close, mcx.session_close) + timedelta(minutes=1)

    def supplied(request):  # type: ignore[no-untyped-def]
        exchange = request.instrument.exchange
        publication = publisher.publication(exchange)
        days = tuple(
            day
            for day in sorted(publication.trading_dates)
            if day <= trading_date
        )[-31:]
        return tuple(
            HistoricalCandle(
                datetime.combine(day, datetime.min.time(), tzinfo=_KOLKATA),
                100.0,
                102.0,
                99.0,
                101.0,
                1000,
            )
            for day in days
        )

    before_dataset = build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=lambda member: _instrument(member.canonical_identity),
        historical_candles=supplied,
        now=before,
        market_calendar_publisher=publisher,
    )
    after_dataset = build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=lambda member: _instrument(member.canonical_identity),
        historical_candles=supplied,
        now=after,
        market_calendar_publisher=publisher,
    )

    assert all(
        record.observation_boundary is not None
        and record.observation_boundary.astimezone(_KOLKATA).date() < trading_date
        for record in before_dataset.records
    )
    assert all(
        record.observation_boundary is not None
        and record.observation_boundary.astimezone(_KOLKATA).date() == trading_date
        for record in after_dataset.records
    )


def test_17_august_daily_completion_uses_each_authoritative_exchange_close() -> None:
    publisher = MarketCalendarPublisher()
    trading_date = date(2026, 8, 17)

    def supplied(request):  # type: ignore[no-untyped-def]
        publication = publisher.publication(request.instrument.exchange)
        days = tuple(
            day for day in sorted(publication.trading_dates) if day <= trading_date
        )[-31:]
        return tuple(
            HistoricalCandle(
                datetime.combine(day, datetime.min.time(), tzinfo=_KOLKATA),
                100.0, 102.0, 99.0, 101.0, 1000,
            )
            for day in days
        )

    after_nse = build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=lambda member: _instrument(member.canonical_identity),
        historical_candles=supplied,
        now=datetime(2026, 8, 17, 16, 0, tzinfo=_KOLKATA),
        market_calendar_publisher=publisher,
    )
    after_mcx = build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=lambda member: _instrument(member.canonical_identity),
        historical_candles=supplied,
        now=datetime(2026, 8, 17, 23, 31, tzinfo=_KOLKATA),
        market_calendar_publisher=publisher,
    )

    for record in after_nse.records:
        assert record.observation_boundary is not None
        expected = (
            date(2026, 8, 14)
            if record.asset_class is SwingUniverseAssetClass.MCX_COMMODITY
            else trading_date
        )
        assert record.observation_boundary.astimezone(_KOLKATA).date() == expected
    assert all(
        record.observation_boundary is not None
        and record.observation_boundary.astimezone(_KOLKATA).date() == trading_date
        for record in after_mcx.records
    )


@pytest.mark.parametrize("mode", ("duplicate", "non_monotonic"))
def test_duplicate_or_non_monotonic_candles_fail_safely(mode: str) -> None:
    supplied = list(_candles(30))
    if mode == "duplicate":
        supplied[10] = supplied[9]
    else:
        supplied[10], supplied[11] = supplied[11], supplied[10]

    dataset = _dataset(tuple(supplied))

    assert dataset.ready_count == 0
    assert all(
        record.failure is SwingDailyFailure.MALFORMED_CANDLE_SEQUENCE
        for record in dataset.records
    )


def test_fewer_than_25_completed_candles_are_visible_unavailable_results() -> None:
    dataset = _dataset(_candles(24))

    assert dataset.requested_count == 98
    assert dataset.ready_count == 0
    assert dataset.unavailable_count == 98
    assert all(
        record.failure is SwingDailyFailure.INSUFFICIENT_COMPLETED_HISTORY
        for record in dataset.records
    )


def test_one_resolution_failure_does_not_remove_or_destroy_other_members() -> None:
    def resolve(member):  # type: ignore[no-untyped-def]
        if member.canonical_identity == "RELIANCE":
            raise InstrumentResolutionError(InstrumentResolutionFailure.NO_MATCH)
        return _instrument(member.canonical_identity)

    dataset = _dataset(resolve=resolve)
    failed = next(
        record for record in dataset.records if record.canonical_identity == "RELIANCE"
    )

    assert dataset.requested_count == 98
    assert dataset.ready_count == 97
    assert dataset.unavailable_count == 1
    assert failed.status is SwingDailyStatus.UNAVAILABLE
    assert failed.failure is SwingDailyFailure.INSTRUMENT_UNAVAILABLE


def test_one_provider_failure_is_sanitized_and_preserves_dataset_cardinality() -> None:
    calls = 0

    def historical(_request):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 3:
            raise HistoricalDataError(HistoricalDataFailure.PROVIDER_FAILURE)
        return _candles(30)

    dataset = build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=lambda member: _instrument(member.canonical_identity),
        historical_candles=historical,
        now=_NOW,
    )

    assert dataset.requested_count == 98
    assert dataset.ready_count == 97
    assert dataset.records[2].failure is SwingDailyFailure.HISTORICAL_DATA_UNAVAILABLE


def test_equities_indices_and_futures_share_one_swing_record_shape() -> None:
    dataset = _dataset()
    by_class = {
        asset_class: next(
            record for record in dataset.records if record.asset_class is asset_class
        )
        for asset_class in SwingUniverseAssetClass
    }

    assert all(type(record) is SwingDailySeries for record in by_class.values())
    assert all(
        tuple(field.name for field in fields(record))
        == (
            "canonical_identity",
            "asset_class",
            "status",
            "candles",
            "observation_boundary",
            "failure",
            "_analysis_instrument",
        )
        for record in by_class.values()
    )


def test_futures_provider_contract_does_not_replace_canonical_identity() -> None:
    dataset = _dataset()
    goldm = next(
        record for record in dataset.records if record.canonical_identity == "GOLDM"
    )

    assert goldm.canonical_identity == "GOLDM"
    assert "26AUGFUT" not in repr(goldm)


def test_dataset_and_records_are_frozen_slotted_and_provider_token_free() -> None:
    dataset = _dataset()
    record = dataset.records[0]

    with pytest.raises((FrozenInstanceError, AttributeError)):
        dataset.records = ()  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, AttributeError)):
        record.status = SwingDailyStatus.UNAVAILABLE  # type: ignore[misc]
    assert not hasattr(dataset, "__dict__")
    assert not hasattr(record, "__dict__")
    field_names = {field.name for field in fields(SwingDailySeries)}
    assert field_names.isdisjoint(
        {"instrument_token", "provider_token", "raw_client", "access_token"}
    )
    source = inspect.getsource(SwingDailySeries)
    assert "instrument_token" not in source
    assert "access_token" not in source


def test_identical_inputs_produce_equal_datasets() -> None:
    first = _dataset()
    second = _dataset()

    assert first == second
    assert hash(first) == hash(second)


def test_every_historical_request_is_daily_and_uses_one_fixed_window() -> None:
    requests = []

    dataset = build_swing_daily_dataset(
        enabled_swing_phase1_universe(),
        resolve_instrument=lambda member: _instrument(member.canonical_identity),
        historical_candles=lambda request: requests.append(request) or _candles(30),
        now=_NOW,
    )

    assert dataset.ready_count == 98
    assert len(requests) == 98
    assert {request.interval for request in requests} == {HistoricalInterval.DAY}
    assert len({(request.start, request.end) for request in requests}) == 1
    assert requests[0].end - requests[0].start == timedelta(days=120)
