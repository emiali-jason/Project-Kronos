"""WO-06HA Provider-backed source for explicit historical research facts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json

from kronos.intraday.candles import expected_candle_boundaries, provider_interval
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_operation import (
    HISTORICAL_OPERATION_IDENTITY,
    HISTORICAL_OPERATION_TIMEFRAMES,
    HistoricalEodSession,
    HistoricalOperationError,
    HistoricalOperationFailure,
    HistoricalOperationalSubject,
)
from kronos.intraday.historical_qualification import (
    HistoricalFactFamily,
    HistoricalPreviousSessionFacts,
    HistoricalQualificationFactBundle,
    create_historical_auxiliary_fact,
    create_historical_fact_bundle,
    create_historical_timeframe_facts,
    reconstruct_previous_session_facts,
)
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
)
from kronos.provider.runtime import ReadOnlyProviderLease


HISTORICAL_FACTUAL_SOURCE_IDENTITY = (
    "KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-PROVIDER-SOURCE-V0"
)
HISTORICAL_FACTUAL_SOURCE_VERSION = "0.1.0"


class HistoricalProviderFactAcquisition:
    __slots__ = ("bundle", "previous_session_facts")

    def __init__(
        self,
        *,
        bundle: HistoricalQualificationFactBundle,
        previous_session_facts: HistoricalPreviousSessionFacts,
    ) -> None:
        if (
            type(bundle) is not HistoricalQualificationFactBundle
            or type(previous_session_facts) is not HistoricalPreviousSessionFacts
            or bundle.previous_session_facts_identity
            != previous_session_facts.facts_identity
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.INTEGRITY_INVALID
            )
        self.bundle = bundle
        self.previous_session_facts = previous_session_facts


class ProviderHistoricalQualificationFactualSource:
    """Sequential exact-identity acquisition through one minimized lease."""

    def __init__(self, lease: ReadOnlyProviderLease) -> None:
        if type(lease) is not ReadOnlyProviderLease or not lease.active:
            raise HistoricalOperationError(
                HistoricalOperationFailure.CONTEXT_UNAVAILABLE
            )
        self._lease = lease
        self._records: dict[str, tuple[InstrumentRecord, ...]] = {}
        self._instrument_record_requests = 0
        self._historical_requests = 0

    @property
    def instrument_record_request_count(self) -> int:
        return self._instrument_record_requests

    @property
    def historical_request_count(self) -> int:
        return self._historical_requests

    @property
    def total_provider_request_count(self) -> int:
        return self._instrument_record_requests + self._historical_requests

    def acquire(
        self,
        *,
        subject: HistoricalOperationalSubject,
        session: HistoricalEodSession,
        requested_factual_families: tuple[HistoricalFactFamily, ...],
    ) -> HistoricalProviderFactAcquisition:
        if (
            type(subject) is not HistoricalOperationalSubject
            or type(session) is not HistoricalEodSession
            or subject.provider_symbol is None
            or subject.binding.canonical_identity is None
            or not requested_factual_families
            or any(
                type(item) is not HistoricalFactFamily
                for item in requested_factual_families
            )
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.HISTORICAL_PREREQUISITE_UNAVAILABLE
            )
        record = self._record(subject)
        candles_by_timeframe: dict[
            IntradayTimeframe, tuple[HistoricalCandle, ...]
        ] = {}
        for timeframe in HISTORICAL_OPERATION_TIMEFRAMES:
            candles_by_timeframe[timeframe] = self._candles(
                record=record,
                timeframe=timeframe,
                session=session,
            )

        daily = candles_by_timeframe[IntradayTimeframe.DAILY]
        previous_daily = tuple(
            item
            for item in daily
            if item.timestamp.astimezone(
                session.previous_schedule.windows[-1].closes_at.tzinfo
            ).date()
            == session.previous_schedule.trading_date
        )
        target_daily = tuple(
            item
            for item in daily
            if item.timestamp.astimezone(
                session.target_schedule.windows[-1].closes_at.tzinfo
            ).date()
            == session.target_schedule.trading_date
        )
        if len(previous_daily) != 1 or len(target_daily) != 1:
            raise HistoricalOperationError(
                HistoricalOperationFailure.MANDATORY_TIMEFRAME_UNAVAILABLE
            )
        if any(
            item.timestamp > session.selection.observation_boundary
            for item in (*previous_daily, *target_daily)
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.QUALIFICATION_LOOK_AHEAD_REJECTED
            )

        previous_identity = _candle_identity(
            subject=subject,
            session_identity=session.previous_schedule.session_id,
            timeframe=IntradayTimeframe.DAILY,
            candle=previous_daily[0],
        )
        previous = reconstruct_previous_session_facts(
            canonical_identity=subject.binding.canonical_identity,
            session=session.selection,
            previous_daily_candle_identity=previous_identity,
            completed_at=session.previous_schedule.windows[-1].closes_at,
            high=Decimal(str(previous_daily[0].high)),
            low=Decimal(str(previous_daily[0].low)),
            close=Decimal(str(previous_daily[0].close)),
            source_integrity_identity=_identity(
                "INTEGRITY-HISTORICAL-PROVIDER-DAILY-",
                previous_identity,
            ),
            provenance=(
                HISTORICAL_FACTUAL_SOURCE_IDENTITY,
                subject.reconciliation_member_identity,
                session.previous_schedule.source_identity,
            ),
        )

        timeframe_facts = []
        for timeframe in HISTORICAL_OPERATION_TIMEFRAMES:
            selected = (
                target_daily
                if timeframe is IntradayTimeframe.DAILY
                else candles_by_timeframe[timeframe]
            )
            identities = tuple(
                _candle_identity(
                    subject=subject,
                    session_identity=session.target_schedule.session_id,
                    timeframe=timeframe,
                    candle=item,
                )
                for item in selected
            )
            timeframe_facts.append(
                create_historical_timeframe_facts(
                    timeframe=timeframe,
                    completed_candle_identities=identities,
                    source_identities=(
                        f"DOMAIN-006:KITE:HISTORICAL:{provider_interval(timeframe).value}",
                        subject.binding.historical_provider_fact_identity,
                    ),
                    available_at=session.selection.observation_boundary,
                    completed=True,
                    provenance=(
                        HISTORICAL_FACTUAL_SOURCE_IDENTITY,
                        subject.reconciliation_member_identity,
                    ),
                )
            )

        auxiliary = tuple(
            create_historical_auxiliary_fact(
                family=family,
                source_identities=(
                    previous.facts_identity,
                    *(item.fact_set_identity for item in timeframe_facts),
                ),
                available_at=session.selection.observation_boundary,
                provenance=(
                    HISTORICAL_FACTUAL_SOURCE_IDENTITY,
                    HISTORICAL_OPERATION_IDENTITY,
                ),
            )
            for family in requested_factual_families
            if family is not HistoricalFactFamily.COMPLETED_OHLCV
        )
        bundle = create_historical_fact_bundle(
            binding=subject.binding,
            session=session.selection,
            timeframe_facts=tuple(timeframe_facts),
            previous_session_facts=previous,
            auxiliary_facts=auxiliary,
            historical_source_identities=tuple(
                f"DOMAIN-006:KITE:HISTORICAL:{provider_interval(item).value}"
                for item in HISTORICAL_OPERATION_TIMEFRAMES
            ),
            provenance=(
                HISTORICAL_FACTUAL_SOURCE_IDENTITY,
                subject.reconciliation_member_identity,
                session.target_schedule.source_identity,
            ),
        )
        return HistoricalProviderFactAcquisition(
            bundle=bundle,
            previous_session_facts=previous,
        )

    def _record(self, subject: HistoricalOperationalSubject) -> InstrumentRecord:
        if subject.exchange not in self._records:
            self._instrument_record_requests += 1
            try:
                self._records[subject.exchange] = self._lease.instrument_records(
                    subject.exchange
                )
            except Exception as error:
                raise HistoricalOperationError(
                    HistoricalOperationFailure.PROVIDER_ACQUISITION_FAILED
                ) from None
        matches = tuple(
            item
            for item in self._records[subject.exchange]
            if item.provider == "KITE"
            and item.exchange == subject.exchange
            and item.trading_symbol == subject.provider_symbol
        )
        if len(matches) != 1:
            raise HistoricalOperationError(
                HistoricalOperationFailure.HISTORICAL_CANONICAL_BINDING_UNAVAILABLE
            )
        return matches[0]

    def _candles(
        self,
        *,
        record: InstrumentRecord,
        timeframe: IntradayTimeframe,
        session: HistoricalEodSession,
    ) -> tuple[HistoricalCandle, ...]:
        start = (
            session.previous_schedule.windows[0].opens_at
            if timeframe is IntradayTimeframe.DAILY
            else session.target_schedule.windows[0].opens_at
        )
        end = session.selection.observation_boundary
        self._historical_requests += 1
        try:
            candles = tuple(
                self._lease.historical_candles(
                    HistoricalCandleRequest(
                        instrument=record,
                        start=start,
                        end=end,
                        interval=provider_interval(timeframe),
                    )
                )
            )
        except Exception:
            raise HistoricalOperationError(
                HistoricalOperationFailure.PROVIDER_ACQUISITION_FAILED
            ) from None
        if any(type(item) is not HistoricalCandle for item in candles):
            raise HistoricalOperationError(
                HistoricalOperationFailure.PROVIDER_ACQUISITION_FAILED
            )
        if timeframe is IntradayTimeframe.DAILY:
            return candles
        expected = expected_candle_boundaries(
            session.target_schedule,
            timeframe,
        )
        expected_starts = tuple(item.start for item in expected)
        actual_starts = tuple(item.timestamp for item in candles)
        if (
            not expected
            or actual_starts != expected_starts
            or any(item.end > session.selection.observation_boundary for item in expected)
        ):
            failure = (
                HistoricalOperationFailure.QUALIFICATION_LOOK_AHEAD_REJECTED
                if any(
                    item.timestamp > session.selection.observation_boundary
                    for item in candles
                )
                else HistoricalOperationFailure.INCOMPLETE_CANDLE_NOT_AUTHORIZED
            )
            raise HistoricalOperationError(failure)
        return candles


def _candle_identity(
    *,
    subject: HistoricalOperationalSubject,
    session_identity: str,
    timeframe: IntradayTimeframe,
    candle: HistoricalCandle,
) -> str:
    return _identity(
        "INTRADAY-HISTORICAL-GOVERNED-CANDLE-",
        {
            "canonical_identity": subject.binding.canonical_identity,
            "session_identity": session_identity,
            "timeframe": timeframe.value,
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "source": HISTORICAL_FACTUAL_SOURCE_IDENTITY,
        },
    )


def _identity(prefix: str, value: object) -> str:
    encoded = json.dumps(
        value,
        default=lambda item: item.isoformat()
        if isinstance(item, datetime)
        else str(item),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return prefix + sha256(encoded).hexdigest().upper()


__all__ = [
    "HISTORICAL_FACTUAL_SOURCE_IDENTITY",
    "HISTORICAL_FACTUAL_SOURCE_VERSION",
    "HistoricalProviderFactAcquisition",
    "ProviderHistoricalQualificationFactualSource",
]
