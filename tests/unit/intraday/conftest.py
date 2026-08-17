from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.contracts import IntradayInstrumentReference, SourceProvenance
from kronos.intraday.instrument import InstrumentExecutionMetadata, adapt_instrument_reference
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.provider.contracts.instrument import InstrumentRecord


IST = ZoneInfo("Asia/Kolkata")
TRADING_DATE = date(2026, 8, 17)


@pytest.fixture
def instrument() -> IntradayInstrumentReference:
    return adapt_instrument_reference(
        canonical_instrument_id="NIFTY",
        provider_record=InstrumentRecord(
            provider="KITE",
            exchange="NSE",
            segment="INDICES",
            trading_symbol="NIFTY 50",
            name="NIFTY 50",
            instrument_type="EQ",
            expiry=None,
        ),
        execution_metadata=InstrumentExecutionMetadata(
            provider_instrument_token=256265,
            tick_size=Decimal("0.05"),
            lot_size=1,
            price_precision=2,
        ),
    )


@pytest.fixture
def schedule() -> MarketDaySchedule:
    return MarketDaySchedule(
        exchange="NSE",
        trading_date=TRADING_DATE,
        session_id="NSE-20260817-REGULAR",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(
            MarketWindow(
                datetime(2026, 8, 17, 9, 15, tzinfo=IST),
                datetime(2026, 8, 17, 15, 30, tzinfo=IST),
            ),
        ),
        source_identity="GOVERNED-SCHEDULE-FIXTURE",
        source_version="2026.08.17",
    )


@pytest.fixture
def provenance() -> SourceProvenance:
    return SourceProvenance(
        provider="KITE",
        source_identity="KITE-HISTORICAL:NIFTY:2026-08-17",
        retrieved_at=datetime(2026, 8, 17, 10, 1, tzinfo=IST),
        source_version="KITE-HISTORICAL-V1",
    )
