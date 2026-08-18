"""Intraday consumer adapter over governed DOMAIN-008 Market facts."""

from __future__ import annotations

from datetime import date, datetime

from kronos.market.calendar import (
    MarketCalendarPublisher,
    MarketInstrumentSessionProfile,
)
from kronos.market.schedule import MarketSchedule

from kronos.market.schedule import (
    MarketScheduleSource,
    MarketDaySchedule,
    MarketWindow,
    MarketSessionFact,
    MarketSessionService,
    TradingDayStatus,
)


class CurrentMarketCalendarScheduleSource:
    """Intraday-owned compatibility adapter over current DOMAIN-008 facts."""

    def __init__(
        self,
        publisher: MarketCalendarPublisher,
        *,
        observed_at: datetime,
        canonical_instrument_id: str | None = None,
    ) -> None:
        if (
            type(publisher) is not MarketCalendarPublisher
            or observed_at.tzinfo is None
            or (
                canonical_instrument_id is not None
                and (
                    not canonical_instrument_id
                    or canonical_instrument_id != canonical_instrument_id.strip()
                )
            )
        ):
            raise ValueError("INTRADAY_MARKET_CALENDAR_ADAPTER_INVALID")
        self.publisher = publisher
        self.observed_at = observed_at
        self.canonical_instrument_id = canonical_instrument_id

    def schedule_for(self, exchange: str, trading_date: date) -> MarketDaySchedule | None:
        if self.canonical_instrument_id is None:
            schedule = self.publisher.schedule(
                exchange, trading_date, observed_at=self.observed_at
            )
        else:
            profile = self.session_profile_for(exchange, trading_date)
            schedule = None if profile is None else profile.continuous_trading
        return None if schedule is None else self._adapt(schedule)

    def session_profile_for(
        self,
        exchange: str,
        trading_date: date,
    ) -> MarketInstrumentSessionProfile | None:
        if self.canonical_instrument_id is None:
            raise ValueError("INTRADAY_MARKET_SUBJECT_UNAVAILABLE")
        return self.publisher.instrument_session_profile(
            exchange,
            trading_date,
            canonical_instrument_id=self.canonical_instrument_id,
            observed_at=self.observed_at,
        )

    def previous_trading_schedule(self, exchange: str, trading_date: date) -> MarketDaySchedule:
        publication = self.publisher.publication(exchange)
        candidates = tuple(day for day in publication.trading_dates if day < trading_date)
        if not candidates:
            raise ValueError("INTRADAY_PREVIOUS_TRADING_SESSION_UNAVAILABLE")
        schedule = self.schedule_for(exchange, max(candidates))
        if schedule is None:
            raise ValueError("INTRADAY_PREVIOUS_TRADING_SESSION_UNAVAILABLE")
        return schedule

    @staticmethod
    def _adapt(schedule: MarketSchedule) -> MarketDaySchedule:
        return MarketDaySchedule(
            exchange=schedule.exchange,
            trading_date=schedule.trading_date,
            timezone=schedule.timezone,
            status=TradingDayStatus.TRADING,
            session_id=schedule.session_identity,
            special_session=schedule.session_type.startswith("SPECIAL_"),
            windows=tuple(MarketWindow(item.window_open, item.window_close) for item in schedule.windows),
            source_identity=schedule.source_identity,
            source_version=schedule.calendar_version,
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


__all__ = ["CurrentMarketCalendarScheduleSource", "IntradayMarketContextAdapter"]
