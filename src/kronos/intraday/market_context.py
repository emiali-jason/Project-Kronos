"""Intraday consumer adapter over governed DOMAIN-008 Market facts."""

from __future__ import annotations

from datetime import date, datetime

from kronos.market.schedule import (
    MarketScheduleSource,
    MarketSessionFact,
    MarketSessionService,
)


class IntradayMarketContextAdapter:
    """Consume DOMAIN-008 schedules without acquiring calendar authority."""

    def __init__(self, source: MarketScheduleSource) -> None:
        if not callable(getattr(source, "schedule_for", None)):
            raise ValueError("INTRADAY_MARKET_CONTEXT_SOURCE_INVALID")
        self._service = MarketSessionService(source)

    def session_facts(
        self,
        *,
        exchange: str,
        trading_date: date,
        observed_at: datetime,
    ) -> MarketSessionFact:
        return self._service.facts(
            exchange=exchange,
            trading_date=trading_date,
            observed_at=observed_at,
        )


__all__ = ["IntradayMarketContextAdapter"]
