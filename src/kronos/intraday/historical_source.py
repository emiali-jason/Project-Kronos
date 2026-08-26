"""WO-06HA Provider-backed source for explicit historical research facts."""

from __future__ import annotations

from datetime import datetime, timezone
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
    HistoricalFailureClassification,
    HistoricalPreviousSessionFacts,
    HistoricalProviderFailureFamily,
    HistoricalQualificationFactBundle,
    create_historical_auxiliary_fact,
    create_historical_fact_bundle,
    create_historical_failure_evidence,
    create_historical_timeframe_facts,
    reconstruct_previous_session_facts,
)
from kronos.intraday.historical_semantic import (
    GovernedHistoricalCandlePayload,
    SemanticQualificationEvidence,
    create_governed_historical_candle_payload,
    derive_semantic_qualification_evidence,
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
    __slots__ = (
        "bundle",
        "previous_session_facts",
        "candle_payloads",
        "semantic_evidence",
    )

    def __init__(
        self,
        *,
        bundle: HistoricalQualificationFactBundle,
        previous_session_facts: HistoricalPreviousSessionFacts,
        candle_payloads: tuple[GovernedHistoricalCandlePayload, ...],
        semantic_evidence: SemanticQualificationEvidence,
    ) -> None:
        if (
            type(bundle) is not HistoricalQualificationFactBundle
            or type(previous_session_facts) is not HistoricalPreviousSessionFacts
            or bundle.previous_session_facts_identity
            != previous_session_facts.facts_identity
            or not candle_payloads
            or any(
                type(item) is not GovernedHistoricalCandlePayload
                for item in candle_payloads
            )
            or type(semantic_evidence) is not SemanticQualificationEvidence
            or semantic_evidence.source_bundle_identity != bundle.bundle_identity
            or semantic_evidence.candle_payload_identities
            != tuple(item.candle_identity for item in candle_payloads)
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.INTEGRITY_INVALID
            )
        self.bundle = bundle
        self.previous_session_facts = previous_session_facts
        self.candle_payloads = candle_payloads
        self.semantic_evidence = semantic_evidence


class ProviderHistoricalQualificationFactualSource:
    """Sequential exact-identity acquisition through one minimized lease."""

    def __init__(
        self,
        lease: ReadOnlyProviderLease,
        *,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        if (
            type(lease) is not ReadOnlyProviderLease
            or not lease.active
            or not callable(clock)
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.CONTEXT_UNAVAILABLE
            )
        self._lease = lease
        self._clock = clock
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
        source_operation_identity: str,
    ) -> HistoricalProviderFactAcquisition:
        if (
            type(subject) is not HistoricalOperationalSubject
            or type(session) is not HistoricalEodSession
            or subject.provider_symbol is None
            or subject.binding.canonical_identity is None
            or not requested_factual_families
            or not isinstance(source_operation_identity, str)
            or not source_operation_identity.startswith(
                "INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-"
            )
            or any(
                type(item) is not HistoricalFactFamily
                for item in requested_factual_families
            )
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.HISTORICAL_PREREQUISITE_UNAVAILABLE
            )
        record = self._record(subject, session)
        candles_by_timeframe: dict[
            IntradayTimeframe, tuple[HistoricalCandle, ...]
        ] = {}
        for timeframe in HISTORICAL_OPERATION_TIMEFRAMES:
            candles_by_timeframe[timeframe] = self._candles(
                subject=subject,
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
                HistoricalOperationFailure.MANDATORY_TIMEFRAME_UNAVAILABLE,
                evidence=self._evidence(
                    subject=subject,
                    session=session,
                    timeframe=IntradayTimeframe.DAILY,
                    expected_count=2,
                    actual_count=len(previous_daily) + len(target_daily),
                    classifications=(
                        HistoricalFailureClassification.MISSING_EXPECTED_CANDLE
                        if len(previous_daily) + len(target_daily) < 2
                        else HistoricalFailureClassification.EXTRA_UNEXPECTED_CANDLE,
                    ),
                    mismatch_ordinal=min(
                        len(previous_daily) + len(target_daily), 1
                    ),
                ),
            )
        if any(
            item.timestamp > session.selection.observation_boundary
            for item in (*previous_daily, *target_daily)
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.QUALIFICATION_LOOK_AHEAD_REJECTED,
                evidence=self._evidence(
                    subject=subject,
                    session=session,
                    timeframe=IntradayTimeframe.DAILY,
                    expected_count=2,
                    actual_count=len(previous_daily) + len(target_daily),
                    classifications=(
                        HistoricalFailureClassification.CANDLE_AFTER_OBSERVATION_BOUNDARY,
                    ),
                    mismatch_ordinal=next(
                        index
                        for index, item in enumerate(
                            (*previous_daily, *target_daily)
                        )
                        if item.timestamp
                        > session.selection.observation_boundary
                    ),
                ),
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
        payloads = _retained_payloads(
            subject=subject,
            session=session,
            candles_by_timeframe={
                IntradayTimeframe.DAILY: target_daily,
                IntradayTimeframe.ONE_HOUR: candles_by_timeframe[
                    IntradayTimeframe.ONE_HOUR
                ],
                IntradayTimeframe.FIFTEEN_MINUTES: candles_by_timeframe[
                    IntradayTimeframe.FIFTEEN_MINUTES
                ],
                IntradayTimeframe.FIVE_MINUTES: candles_by_timeframe[
                    IntradayTimeframe.FIVE_MINUTES
                ],
            },
            source_operation_identity=source_operation_identity,
        )
        semantic = derive_semantic_qualification_evidence(
            candle_payloads=payloads,
            previous_session_facts=previous,
            source_bundle_identity=bundle.bundle_identity,
            source_operation_identity=source_operation_identity,
            provenance=(
                "KRONOS-WO-06S-SEMANTIC-EVIDENCE-001",
                HISTORICAL_FACTUAL_SOURCE_IDENTITY,
                subject.reconciliation_member_identity,
            ),
        )
        return HistoricalProviderFactAcquisition(
            bundle=bundle,
            previous_session_facts=previous,
            candle_payloads=payloads,
            semantic_evidence=semantic,
        )

    def _record(
        self,
        subject: HistoricalOperationalSubject,
        session: HistoricalEodSession,
    ) -> InstrumentRecord:
        if subject.exchange not in self._records:
            self._instrument_record_requests += 1
            try:
                self._records[subject.exchange] = self._lease.instrument_records(
                    subject.exchange
                )
            except Exception:
                raise HistoricalOperationError(
                    HistoricalOperationFailure.PROVIDER_ACQUISITION_FAILED,
                    evidence=self._evidence(
                        subject=subject,
                        session=session,
                        timeframe=None,
                        expected_count=1,
                        actual_count=None,
                        classifications=(
                            HistoricalFailureClassification.PROVIDER_ACQUISITION_FAILED,
                        ),
                        mismatch_ordinal=None,
                        provider_failure_family=(
                            HistoricalProviderFailureFamily.INSTRUMENT_RECORD_UNAVAILABLE
                        ),
                    ),
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
        subject: HistoricalOperationalSubject,
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
        expected = (
            ()
            if timeframe is IntradayTimeframe.DAILY
            else expected_candle_boundaries(session.target_schedule, timeframe)
        )
        expected_count = 2 if timeframe is IntradayTimeframe.DAILY else len(expected)
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
                HistoricalOperationFailure.PROVIDER_ACQUISITION_FAILED,
                evidence=self._evidence(
                    subject=subject,
                    session=session,
                    timeframe=timeframe,
                    expected_count=expected_count,
                    actual_count=None,
                    classifications=(
                        HistoricalFailureClassification.PROVIDER_ACQUISITION_FAILED,
                    ),
                    mismatch_ordinal=None,
                    provider_failure_family=(
                        HistoricalProviderFailureFamily.PROVIDER_REQUEST_FAILED
                    ),
                ),
            ) from None
        if any(type(item) is not HistoricalCandle for item in candles):
            raise HistoricalOperationError(
                HistoricalOperationFailure.PROVIDER_ACQUISITION_FAILED,
                evidence=self._evidence(
                    subject=subject,
                    session=session,
                    timeframe=timeframe,
                    expected_count=expected_count,
                    actual_count=len(candles),
                    classifications=(
                        HistoricalFailureClassification.PROVIDER_ACQUISITION_FAILED,
                    ),
                    mismatch_ordinal=None,
                    provider_failure_family=(
                        HistoricalProviderFailureFamily.PROVIDER_RESPONSE_INVALID
                    ),
                ),
            )
        if timeframe is IntradayTimeframe.DAILY:
            return candles
        expected_starts = tuple(item.start for item in expected)
        actual_starts = tuple(item.timestamp for item in candles)
        if (
            not expected
            or actual_starts != expected_starts
            or any(item.end > session.selection.observation_boundary for item in expected)
        ):
            classifications, mismatch_ordinal = _classify_mismatch(
                expected_starts=expected_starts,
                actual_starts=actual_starts,
                observation_boundary=session.selection.observation_boundary,
                expected_extends_beyond_boundary=any(
                    item.end > session.selection.observation_boundary
                    for item in expected
                ),
            )
            failure = (
                HistoricalOperationFailure.QUALIFICATION_LOOK_AHEAD_REJECTED
                if HistoricalFailureClassification.CANDLE_AFTER_OBSERVATION_BOUNDARY
                in classifications
                else HistoricalOperationFailure.INCOMPLETE_CANDLE_NOT_AUTHORIZED
            )
            raise HistoricalOperationError(
                failure,
                evidence=self._evidence(
                    subject=subject,
                    session=session,
                    timeframe=timeframe,
                    expected_count=len(expected_starts),
                    actual_count=len(actual_starts),
                    classifications=classifications,
                    mismatch_ordinal=mismatch_ordinal,
                ),
            )
        return candles

    def _evidence(
        self,
        *,
        subject: HistoricalOperationalSubject,
        session: HistoricalEodSession | None,
        timeframe: IntradayTimeframe | None,
        expected_count: int,
        actual_count: int | None,
        classifications: tuple[HistoricalFailureClassification, ...],
        mismatch_ordinal: int | None,
        provider_failure_family: HistoricalProviderFailureFamily | None = None,
    ):
        canonical_identity = subject.binding.canonical_identity
        if canonical_identity is None:
            raise HistoricalOperationError(
                HistoricalOperationFailure.INTEGRITY_INVALID
            )
        boundary = (
            self._clock()
            if session is None
            else session.selection.observation_boundary
        )
        return create_historical_failure_evidence(
            canonical_identity=canonical_identity,
            target_session_identity=(
                "INSTRUMENT-RECORD-RESOLUTION"
                if session is None
                else session.target_schedule.session_id
            ),
            timeframe=timeframe,
            expected_timestamp_count=expected_count,
            actual_timestamp_count=actual_count,
            classifications=classifications,
            mismatch_ordinal=mismatch_ordinal,
            observation_boundary=boundary,
            diagnosed_at=self._clock(),
            source_identity=HISTORICAL_FACTUAL_SOURCE_IDENTITY,
            provider_failure_family=provider_failure_family,
            provenance=(
                HISTORICAL_OPERATION_IDENTITY,
                subject.reconciliation_member_identity,
            ),
        )


def _retained_payloads(
    *,
    subject: HistoricalOperationalSubject,
    session: HistoricalEodSession,
    candles_by_timeframe: dict[IntradayTimeframe, tuple[HistoricalCandle, ...]],
    source_operation_identity: str,
) -> tuple[GovernedHistoricalCandlePayload, ...]:
    canonical_identity = subject.binding.canonical_identity
    if canonical_identity is None:
        raise HistoricalOperationError(HistoricalOperationFailure.INTEGRITY_INVALID)
    retained: list[GovernedHistoricalCandlePayload] = []
    for timeframe in HISTORICAL_OPERATION_TIMEFRAMES:
        candles = candles_by_timeframe[timeframe]
        if timeframe is IntradayTimeframe.DAILY:
            boundaries = {
                candles[0].timestamp: (
                    session.target_schedule.windows[0].opens_at,
                    session.target_schedule.windows[-1].closes_at,
                )
            }
        else:
            boundaries = {
                item.start: (item.start, item.end)
                for item in expected_candle_boundaries(
                    session.target_schedule, timeframe
                )
            }
        provider_source = (
            f"DOMAIN-006:KITE:HISTORICAL:{provider_interval(timeframe).value}"
        )
        for candle in candles:
            try:
                start, end = boundaries[candle.timestamp]
            except KeyError as error:
                raise HistoricalOperationError(
                    HistoricalOperationFailure.INTEGRITY_INVALID
                ) from error
            retained.append(
                create_governed_historical_candle_payload(
                    canonical_subject_identity=canonical_identity,
                    exchange=subject.exchange,
                    market_identity={
                        "NSE": "NSE_CAPITAL_MARKET",
                        "MCX": "MCX_NON_AGRI",
                    }.get(subject.exchange, subject.exchange),
                    market_session_identity=session.target_schedule.session_id,
                    timeframe=timeframe,
                    candle_start=start,
                    candle_end=end,
                    open=Decimal(str(candle.open)),
                    high=Decimal(str(candle.high)),
                    low=Decimal(str(candle.low)),
                    close=Decimal(str(candle.close)),
                    volume=candle.volume,
                    observation_boundary=session.selection.observation_boundary,
                    provider_source_identity=provider_source,
                    source_operation_identity=source_operation_identity,
                    provenance=(
                        "KRONOS-WO-06S-SEMANTIC-EVIDENCE-001",
                        HISTORICAL_FACTUAL_SOURCE_IDENTITY,
                        subject.reconciliation_member_identity,
                        session.target_schedule.source_identity,
                    ),
                )
            )
    return tuple(retained)


def _classify_mismatch(
    *,
    expected_starts: tuple[datetime, ...],
    actual_starts: tuple[datetime, ...],
    observation_boundary: datetime,
    expected_extends_beyond_boundary: bool,
) -> tuple[tuple[HistoricalFailureClassification, ...], int | None]:
    classifications: list[HistoricalFailureClassification] = []
    if not expected_starts or expected_extends_beyond_boundary:
        classifications.append(
            HistoricalFailureClassification.EXPECTED_BOUNDARY_UNAVAILABLE
        )
    if len(set(actual_starts)) != len(actual_starts):
        classifications.append(
            HistoricalFailureClassification.DUPLICATE_TIMESTAMP
        )
    if any(
        current < previous
        for previous, current in zip(actual_starts, actual_starts[1:])
    ):
        classifications.append(
            HistoricalFailureClassification.OUT_OF_ORDER_TIMESTAMP
        )
    if any(item > observation_boundary for item in actual_starts):
        classifications.append(
            HistoricalFailureClassification.CANDLE_AFTER_OBSERVATION_BOUNDARY
        )
    if set(expected_starts) - set(actual_starts):
        classifications.append(
            HistoricalFailureClassification.MISSING_EXPECTED_CANDLE
        )
    if set(actual_starts) - set(expected_starts):
        classifications.append(
            HistoricalFailureClassification.EXTRA_UNEXPECTED_CANDLE
        )
    deltas = tuple(
        actual - expected
        for expected, actual in zip(expected_starts, actual_starts)
    )
    if (
        len(expected_starts) == len(actual_starts)
        and expected_starts != actual_starts
        and deltas
        and len(set(deltas)) == 1
        and deltas[0].total_seconds() != 0
    ):
        classifications.append(HistoricalFailureClassification.TIMESTAMP_OFFSET)
    if not classifications:
        classifications.append(
            HistoricalFailureClassification.EXPECTED_BOUNDARY_UNAVAILABLE
        )
    mismatch_ordinal = next(
        (
            index
            for index, pair in enumerate(zip(expected_starts, actual_starts))
            if pair[0] != pair[1]
        ),
        min(len(expected_starts), len(actual_starts))
        if expected_starts != actual_starts
        else None,
    )
    return tuple(classifications), mismatch_ordinal


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
