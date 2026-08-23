"""WO-05A Provider-backed factual source for Intraday Native Discovery."""

from __future__ import annotations

from datetime import datetime, time
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from kronos.intraday.candles import expected_candle_boundaries, provider_interval
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.discovery import (
    FactFamily,
    FactRequirement,
    MachineFactEvidence,
    create_machine_fact_bundle,
)
from kronos.intraday.discovery_runtime import (
    DiscoveryFactAcquisition,
    DiscoveryMemberFactError,
    DiscoveryRunBoundary,
)
from kronos.intraday.discovery import DiscoveryReason
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.intraday.reconciliation import (
    Availability,
    ReconciliationMember,
    ReconciliationPublication,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.schedule import MarketDaySchedule
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
)
from kronos.provider.runtime import ReadOnlyProviderLease


DISCOVERY_FACTUAL_SOURCE_IDENTITY = (
    "KRONOS-INTRADAY-DISCOVERY-PROVIDER-FACTUAL-SOURCE-V0"
)
DISCOVERY_FACTUAL_SOURCE_VERSION = "0.1.0"
_TIMEFRAMES = (
    IntradayTimeframe.DAILY,
    IntradayTimeframe.ONE_HOUR,
    IntradayTimeframe.FIFTEEN_MINUTES,
    IntradayTimeframe.FIVE_MINUTES,
)


class ProviderDiscoveryFactualSource:
    """Acquire four completed factual windows through one operation lease."""

    def __init__(
        self,
        *,
        lease: ReadOnlyProviderLease,
        calendar_publisher: MarketCalendarPublisher,
        universe_identity: str,
        universe_version: str,
        reconciliation_identity: str,
        reconciliation_version: str,
        reconciliation: ReconciliationPublication,
    ) -> None:
        if (
            type(lease) is not ReadOnlyProviderLease
            or type(calendar_publisher) is not MarketCalendarPublisher
            or type(reconciliation) is not ReconciliationPublication
            or not all(_text(item) for item in (
                universe_identity,
                universe_version,
                reconciliation_identity,
                reconciliation_version,
            ))
        ):
            raise ValueError("DISCOVERY_FACTUAL_SOURCE_DEPENDENCY_INVALID")
        self._lease = lease
        self._calendar = calendar_publisher
        self._universe_identity = universe_identity
        self._universe_version = universe_version
        self._reconciliation_identity = reconciliation_identity
        self._reconciliation_version = reconciliation_version
        self._reconciliation = reconciliation
        self._records: dict[str, tuple[InstrumentRecord, ...]] = {}
        self._session_identities: dict[datetime, tuple[str, str]] = {}
        self._historical_requests = 0

    @property
    def historical_request_count(self) -> int:
        return self._historical_requests

    def acquire(
        self,
        *,
        member: ReconciliationMember,
        boundary: DiscoveryRunBoundary,
    ) -> DiscoveryFactAcquisition:
        if type(member) is not ReconciliationMember or type(boundary) is not DiscoveryRunBoundary:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE
            )
        record = self._record(member)
        local = boundary.observation_boundary.astimezone(ZoneInfo("Asia/Kolkata"))
        calendar = CurrentMarketCalendarScheduleSource(
            self._calendar,
            observed_at=boundary.observation_boundary,
            canonical_instrument_id=member.canonical_identity,
        )
        schedule = calendar.schedule_for(member.exchange, local.date())
        if boundary.observation_boundary not in self._session_identities:
            self._session_identities[boundary.observation_boundary] = (
                governed_market_session_identities(
                    calendar_publisher=self._calendar,
                    reconciliation=self._reconciliation,
                    observed_at=boundary.observation_boundary,
                )
            )
        governed_session, governed_boundary = self._session_identities[
            boundary.observation_boundary
        ]
        if (
            schedule is None
            or boundary.market_session_identity != governed_session
            or boundary.market_session_boundary_identity != governed_boundary
        ):
            raise DiscoveryMemberFactError(DiscoveryReason.MARKET_SESSION_UNAVAILABLE)
        try:
            previous = calendar.previous_trading_schedule(member.exchange, local.date())
        except ValueError as error:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MARKET_SESSION_UNAVAILABLE
            ) from error

        evidence: list[MachineFactEvidence] = [MachineFactEvidence(
            family=FactFamily.MARKET_SESSION_BOUNDARY,
            requirement=FactRequirement.MANDATORY,
            evidence_identity=_identity("DISCOVERY-SESSION", {
                "session": schedule.session_id,
                "boundary": boundary.market_session_boundary_identity,
            }),
            fact_version=schedule.source_version,
            observed_at=boundary.observation_boundary,
            timeframe=None,
            completed_candle=None,
        )]
        completed_by_timeframe: dict[IntradayTimeframe, tuple[HistoricalCandle, ...]] = {}
        for timeframe in _TIMEFRAMES:
            completed = self._acquire_timeframe(
                record=record,
                timeframe=timeframe,
                schedule=schedule,
                previous=previous,
                observed_at=boundary.observation_boundary,
            )
            completed_by_timeframe[timeframe] = completed
            fact_identity = _candle_evidence_identity(
                member=member,
                timeframe=timeframe,
                schedule=schedule if timeframe is not IntradayTimeframe.DAILY else previous,
                observed_at=boundary.observation_boundary,
                candles=completed,
            )
            evidence.extend((
                MachineFactEvidence(
                    family=FactFamily.GOVERNED_COMPLETED_OHLCV,
                    requirement=FactRequirement.MANDATORY,
                    evidence_identity=fact_identity,
                    fact_version=DISCOVERY_FACTUAL_SOURCE_VERSION,
                    observed_at=boundary.observation_boundary,
                    timeframe=timeframe,
                    completed_candle=True,
                ),
                MachineFactEvidence(
                    family=FactFamily.CANDLE_COMPLETENESS_RECONCILIATION,
                    requirement=FactRequirement.MANDATORY,
                    evidence_identity=_identity("DISCOVERY-COMPLETENESS", {
                        "factual_evidence": fact_identity,
                        "completed_count": len(completed),
                    }),
                    fact_version=DISCOVERY_FACTUAL_SOURCE_VERSION,
                    observed_at=boundary.observation_boundary,
                    timeframe=timeframe,
                    completed_candle=True,
                ),
            ))

        previous_daily = completed_by_timeframe[IntradayTimeframe.DAILY]
        evidence.extend((
            _optional_fact(
                FactFamily.PREVIOUS_SESSION_HLC_PDH_PDL,
                member,
                boundary,
                previous_daily,
            ),
            _optional_fact(
                FactFamily.CLASSIC_PIVOTS_CPR,
                member,
                boundary,
                previous_daily,
            ),
        ))
        for timeframe in _TIMEFRAMES:
            evidence.append(_optional_fact(
                FactFamily.STRUCTURAL_COMPARISONS,
                member,
                boundary,
                completed_by_timeframe[timeframe],
                timeframe=timeframe,
            ))
        evidence.append(_optional_fact(
            FactFamily.VOLUME_OBSERVATIONS,
            member,
            boundary,
            completed_by_timeframe[IntradayTimeframe.FIVE_MINUTES],
            timeframe=IntradayTimeframe.FIVE_MINUTES,
        ))
        bundle = create_machine_fact_bundle(
            canonical_identity=member.canonical_identity,
            universe_identity=self._universe_identity,
            universe_version=self._universe_version,
            reconciliation_identity=self._reconciliation_identity,
            reconciliation_version=self._reconciliation_version,
            market_session_identity=boundary.market_session_identity,
            market_session_boundary_identity=boundary.market_session_boundary_identity,
            observation_boundary=boundary.observation_boundary,
            evidence=tuple(evidence),
            source_identities=tuple(
                f"DOMAIN-006:KITE:HISTORICAL:{provider_interval(item).value}"
                for item in _TIMEFRAMES
            ),
            provenance=(
                DISCOVERY_FACTUAL_SOURCE_IDENTITY,
                member.reconciliation_member_identity,
            ),
        )
        return DiscoveryFactAcquisition(
            universe_member_identity=member.universe_member_identity,
            canonical_identity=member.canonical_identity,
            bundle=bundle,
        )

    def _record(self, member: ReconciliationMember) -> InstrumentRecord:
        if member.provider_symbol is None:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE
            )
        if member.exchange not in self._records:
            self._records[member.exchange] = self._lease.instrument_records(member.exchange)
        matches = tuple(
            item for item in self._records[member.exchange]
            if item.provider == "KITE"
            and item.exchange == member.exchange
            and item.trading_symbol == member.provider_symbol
        )
        if len(matches) != 1:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE
            )
        return matches[0]

    def _acquire_timeframe(
        self,
        *,
        record: InstrumentRecord,
        timeframe: IntradayTimeframe,
        schedule: MarketDaySchedule,
        previous: MarketDaySchedule,
        observed_at: datetime,
    ) -> tuple[HistoricalCandle, ...]:
        if timeframe is IntradayTimeframe.DAILY:
            start = datetime.combine(
                previous.trading_date,
                time.min,
                ZoneInfo(previous.timezone),
            )
        else:
            start = schedule.windows[0].opens_at
        end = min(
            observed_at.astimezone(schedule.windows[-1].closes_at.tzinfo),
            schedule.windows[-1].closes_at,
        )
        if start >= end:
            raise DiscoveryMemberFactError(DiscoveryReason.MARKET_SESSION_UNAVAILABLE)
        self._historical_requests += 1
        candles = tuple(self._lease.historical_candles(HistoricalCandleRequest(
            instrument=record,
            start=start,
            end=end,
            interval=provider_interval(timeframe),
        )))
        if timeframe is IntradayTimeframe.DAILY:
            selected = tuple(
                item for item in candles
                if item.timestamp.astimezone(ZoneInfo(previous.timezone)).date()
                == previous.trading_date
            )
            if len(selected) != 1:
                raise DiscoveryMemberFactError(
                    DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE
                )
            return selected
        return _completed_intraday(
            candles=candles,
            schedule=schedule,
            timeframe=timeframe,
            observed_at=observed_at,
        )


def _completed_intraday(
    *,
    candles: tuple[HistoricalCandle, ...],
    schedule: MarketDaySchedule,
    timeframe: IntradayTimeframe,
    observed_at: datetime,
) -> tuple[HistoricalCandle, ...]:
    if any(
        current.timestamp <= previous.timestamp
        for previous, current in zip(candles, candles[1:])
    ):
        raise DiscoveryMemberFactError(DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE)
    expected = expected_candle_boundaries(schedule, timeframe)
    eligible = tuple(
        item for item in expected
        if item.end <= observed_at.astimezone(item.end.tzinfo)
    )
    supplied = {item.timestamp: item for item in candles}
    if len(supplied) != len(candles):
        raise DiscoveryMemberFactError(DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE)
    completed = tuple(supplied[item.start] for item in eligible if item.start in supplied)
    expected_starts = {item.start for item in expected}
    if (
        not eligible
        or len(completed) != len(eligible)
        or any(item.timestamp not in expected_starts for item in candles)
    ):
        raise DiscoveryMemberFactError(
            DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE
        )
    return completed


def governed_market_session_identities(
    *,
    calendar_publisher: MarketCalendarPublisher,
    reconciliation: ReconciliationPublication,
    observed_at: datetime,
) -> tuple[str, str]:
    """Bind one operation to all governed subject-scoped DOMAIN-008 sessions."""

    if (
        type(calendar_publisher) is not MarketCalendarPublisher
        or type(reconciliation) is not ReconciliationPublication
        or not isinstance(observed_at, datetime)
        or observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise ValueError("DISCOVERY_MARKET_SESSION_REQUEST_INVALID")
    local = observed_at.astimezone(ZoneInfo("Asia/Kolkata"))
    sessions: list[tuple[object, ...]] = []
    for member in reconciliation.members:
        if member.dimensions.machine_fact_consumability is not Availability.AVAILABLE:
            continue
        source = CurrentMarketCalendarScheduleSource(
            calendar_publisher,
            observed_at=observed_at,
            canonical_instrument_id=member.canonical_identity,
        )
        schedule = source.schedule_for(member.exchange, local.date())
        if schedule is None:
            raise ValueError("DISCOVERY_MARKET_SESSION_UNAVAILABLE")
        sessions.append((
            member.universe_member_identity,
            schedule.session_id,
            tuple((item.opens_at, item.closes_at) for item in schedule.windows),
        ))
    if not sessions:
        raise ValueError("DISCOVERY_MARKET_SESSION_UNAVAILABLE")
    session_identity = _identity("DISCOVERY-MARKET-SESSIONS", tuple(sessions))
    boundary_identity = _identity("DISCOVERY-MARKET-BOUNDARY", {
        "observed_at": observed_at,
        "sessions": tuple(sessions),
    })
    return session_identity, boundary_identity


def _optional_fact(
    family: FactFamily,
    member: ReconciliationMember,
    boundary: DiscoveryRunBoundary,
    candles: tuple[HistoricalCandle, ...],
    *,
    timeframe: IntradayTimeframe | None = None,
) -> MachineFactEvidence:
    return MachineFactEvidence(
        family=family,
        requirement=FactRequirement.OPTIONAL_TELEMETRY,
        evidence_identity=_identity("DISCOVERY-FACT", {
            "family": family.value,
            "canonical": member.canonical_identity,
            "boundary": boundary.observation_boundary,
            "candles": _candle_values(candles),
        }),
        fact_version=DISCOVERY_FACTUAL_SOURCE_VERSION,
        observed_at=boundary.observation_boundary,
        timeframe=timeframe,
        completed_candle=True if timeframe is not None else None,
    )


def _candle_evidence_identity(
    *,
    member: ReconciliationMember,
    timeframe: IntradayTimeframe,
    schedule: MarketDaySchedule,
    observed_at: datetime,
    candles: tuple[HistoricalCandle, ...],
) -> str:
    return _identity("DISCOVERY-CANDLES", {
        "canonical": member.canonical_identity,
        "timeframe": timeframe.value,
        "schedule": schedule.session_id,
        "observed_at": observed_at,
        "candles": _candle_values(candles),
    })


def _candle_values(candles: tuple[HistoricalCandle, ...]) -> tuple[tuple[object, ...], ...]:
    return tuple((
        item.timestamp,
        item.open,
        item.high,
        item.low,
        item.close,
        item.volume,
    ) for item in candles)


def _identity(prefix: str, payload: object) -> str:
    encoded = json.dumps(
        payload,
        default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"{prefix}-{sha256(encoded).hexdigest()}"


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


__all__ = [
    "DISCOVERY_FACTUAL_SOURCE_IDENTITY",
    "DISCOVERY_FACTUAL_SOURCE_VERSION",
    "ProviderDiscoveryFactualSource",
    "governed_market_session_identities",
]
