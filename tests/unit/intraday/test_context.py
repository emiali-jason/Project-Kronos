from __future__ import annotations

from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal
import json
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.context import (
    CLASSIC_PIVOT_POINTS_V1,
    CPR_V1,
    PREVIOUS_SESSION_FACTS_V1,
    CprRelationship,
    ReferenceRelationship,
    Slice1EContext,
    build_slice1e_context,
)
from kronos.intraday.context_persistence import LocalSlice1EContextStore
from kronos.intraday.contracts import (
    DataAvailability,
    IntradayInstrumentReference,
    SourceProvenance,
    create_intraday_run,
)
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.provider.contracts.market_data import HistoricalCandle


IST = ZoneInfo("Asia/Kolkata")
CURRENT_DATE = date(2026, 8, 17)


class _Calendar:
    def __init__(self, schedule: MarketDaySchedule | None) -> None:
        self.schedule = schedule
        self.requests: list[tuple[str, date]] = []

    def previous_trading_schedule(
        self, exchange: str, before_date: date
    ) -> MarketDaySchedule | None:
        self.requests.append((exchange, before_date))
        return self.schedule


def _schedule(day: date = date(2026, 8, 14), *, special: bool = False) -> MarketDaySchedule:
    return MarketDaySchedule(
        exchange="NSE", trading_date=day, session_id=f"NSE-{day:%Y%m%d}",
        timezone="Asia/Kolkata", status=TradingDayStatus.TRADING,
        windows=(MarketWindow(
            datetime(day.year, day.month, day.day, 9, 15, tzinfo=IST),
            datetime(day.year, day.month, day.day, 15, 30, tzinfo=IST),
        ),),
        source_identity="GOVERNED-CALENDAR|MARKET-CALENDAR-ABC",
        source_version="2026.08.17", special_session=special,
    )


def _context(
    instrument: IntradayInstrumentReference,
    provenance: SourceProvenance,
    *,
    candles: tuple[HistoricalCandle, ...] | None = None,
    current_price: Decimal | None = Decimal("104"),
    prior_cpr=None,
) -> Slice1EContext:
    schedule = _schedule()
    run = create_intraday_run(
        created_at=datetime(2026, 8, 17, 9, 59, tzinfo=IST),
        observation_boundary=datetime(2026, 8, 17, 10, 0, tzinfo=IST),
    )
    supplied = candles if candles is not None else (
        HistoricalCandle(
            datetime(2026, 8, 14, 0, 0, tzinfo=IST),
            100.0, 110.0, 90.0, 106.0, 1_000_000,
        ),
    )
    calendar = _Calendar(schedule)
    result = build_slice1e_context(
        run=run, instrument=instrument, current_trading_date=CURRENT_DATE,
        calendar=calendar, previous_session_candles=supplied,
        provenance=provenance, current_price=current_price, prior_cpr=prior_cpr,
    )
    assert calendar.requests == [("NSE", CURRENT_DATE)]
    return result


def test_previous_session_classic_pivots_cpr_and_exact_price_relationships(
    instrument: IntradayInstrumentReference,
    provenance: SourceProvenance,
) -> None:
    result = _context(instrument, provenance)

    assert result.previous_session.evidence_family == PREVIOUS_SESSION_FACTS_V1
    assert result.previous_session.previous_schedule.trading_date == date(2026, 8, 14)
    assert (result.previous_session.pdh, result.previous_session.pdl) == (
        Decimal("110.0"), Decimal("90.0")
    )
    pivots = result.classic_pivots
    assert pivots.evidence_family == CLASSIC_PIVOT_POINTS_V1
    assert (pivots.p, pivots.r1, pivots.r2, pivots.r3, pivots.r4) == (
        Decimal("102.0"), Decimal("114.0"), Decimal("122.0"),
        Decimal("142.0"), Decimal("162.0"),
    )
    assert (pivots.s1, pivots.s2, pivots.s3, pivots.s4) == (
        Decimal("94.0"), Decimal("82.0"), Decimal("62.0"), Decimal("42.0")
    )
    assert result.cpr.evidence_family == CPR_V1
    assert (result.cpr.pivot, result.cpr.bc, result.cpr.tc) == (
        Decimal("102.0"), Decimal("100.0"), Decimal("104.0")
    )
    assert (result.cpr.lower, result.cpr.upper, result.cpr.width) == (
        Decimal("100.0"), Decimal("104.0"), Decimal("4.0")
    )
    relationships = {item.reference_identity: item.relationship for item in result.price_relationships}
    assert relationships["CPR_UPPER"] is ReferenceRelationship.AT
    assert relationships["PDH"] is ReferenceRelationship.BELOW
    assert relationships["P"] is ReferenceRelationship.ABOVE


def test_decimal_calculation_is_unrounded_and_not_tick_normalized(
    instrument: IntradayInstrumentReference,
    provenance: SourceProvenance,
) -> None:
    candle = HistoricalCandle(
        datetime(2026, 8, 14, 0, 0, tzinfo=IST), 10.0, 11.0, 8.0, 10.0, 100
    )
    result = _context(instrument, provenance, candles=(candle,), current_price=None)

    assert result.classic_pivots.p == Decimal("9.666666666666666666666666667")
    assert result.classic_pivots.p % instrument.tick_size != 0
    assert result.price_relationships == ()


def test_incomplete_or_unavailable_previous_session_fails_all_dependents_closed(
    instrument: IntradayInstrumentReference,
    provenance: SourceProvenance,
) -> None:
    result = _context(instrument, provenance, candles=())

    assert result.previous_session.availability is DataAvailability.INCOMPLETE
    assert result.previous_session.high is None
    assert result.classic_pivots.availability is DataAvailability.UNAVAILABLE
    assert result.cpr.availability is DataAvailability.UNAVAILABLE
    assert result.price_relationships == ()

    unavailable = build_slice1e_context(
        run=result.run, instrument=instrument, current_trading_date=CURRENT_DATE,
        calendar=_Calendar(None), previous_session_candles=(), provenance=provenance,
    )
    assert unavailable.previous_session.availability is DataAvailability.UNAVAILABLE
    assert unavailable.previous_session.previous_schedule is None

    before_prior_close = create_intraday_run(
        created_at=datetime(2026, 8, 14, 9, 59, tzinfo=IST),
        observation_boundary=datetime(2026, 8, 14, 10, 0, tzinfo=IST),
    )
    partial = build_slice1e_context(
        run=before_prior_close, instrument=instrument, current_trading_date=CURRENT_DATE,
        calendar=_Calendar(_schedule()),
        previous_session_candles=(HistoricalCandle(
            datetime(2026, 8, 14, 0, 0, tzinfo=IST),
            100.0, 110.0, 90.0, 106.0, 100,
        ),),
        provenance=provenance,
    )
    assert partial.previous_session.availability is DataAvailability.INCOMPLETE
    assert partial.classic_pivots.availability is DataAvailability.UNAVAILABLE


def test_current_to_prior_cpr_relationship_uses_frozen_kr280_policy(
    instrument: IntradayInstrumentReference,
    provenance: SourceProvenance,
) -> None:
    prior = _context(instrument, provenance, current_price=None).cpr
    current = _context(instrument, provenance, current_price=None, prior_cpr=prior)

    assert current.cpr.relationship_to_prior is CprRelationship.UNCHANGED
    assert current.cpr.relationship_policy == "KR-280-CPR-RELATIONSHIP-V1"


def test_context_contract_has_no_trading_consequence_fields(
    instrument: IntradayInstrumentReference,
    provenance: SourceProvenance,
) -> None:
    first = _context(instrument, provenance, current_price=Decimal("103"))
    changed_candle = HistoricalCandle(
        datetime(2026, 8, 14, 0, 0, tzinfo=IST), 100.0, 120.0, 80.0, 90.0, 100
    )
    second = _context(
        instrument, provenance, candles=(changed_candle,), current_price=Decimal("105"),
        prior_cpr=first.cpr,
    )
    names = {field.name for field in fields(Slice1EContext)}

    assert names.isdisjoint({
        "candidate_state", "probable", "discovery_consequence", "readiness",
        "entry", "stop", "invalidation", "target", "risk_reward_eligibility",
        "risk", "paper_eligibility", "live_eligibility", "role_reversal",
    })
    assert first.classic_pivots.values != second.classic_pivots.values
    assert first.cpr.width != second.cpr.width
    assert first.cpr.relationship_to_prior != second.cpr.relationship_to_prior
    assert first.evidence_id != second.evidence_id


def test_slice1e_store_is_deterministic_restart_safe_and_detects_tampering(
    tmp_path,
    instrument: IntradayInstrumentReference,
    provenance: SourceProvenance,
) -> None:
    evidence = _context(instrument, provenance)
    store = LocalSlice1EContextStore(tmp_path / "slice1e")
    store.retain(evidence)
    store.retain(evidence)

    loaded = LocalSlice1EContextStore(store.root).load(
        run_id=evidence.run.run_id,
        mapping_identity=instrument.mapping_identity,
        trading_date=CURRENT_DATE.isoformat(), evidence_id=evidence.evidence_id,
    )
    assert loaded == evidence

    path = next(store.root.rglob("*.json"))
    document = json.loads(path.read_bytes())
    document["evidence"]["classic_pivots"]["r1"] = "999"
    path.write_text(json.dumps(document, indent=2, sort_keys=True))
    with pytest.raises(ValueError, match="UNAVAILABLE_OR_INVALID"):
        store.load(
            run_id=evidence.run.run_id, mapping_identity=instrument.mapping_identity,
            trading_date=CURRENT_DATE.isoformat(), evidence_id=evidence.evidence_id,
        )
