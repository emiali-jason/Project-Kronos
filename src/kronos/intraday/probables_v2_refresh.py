"""Discovery-to-Probables V2 mapping over exact completed Provider facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json

from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.completed_evidence import (
    CompletedEvidenceSelection,
    CompletedEvidenceError,
    IntradayAnalysisPhase,
    build_completed_evidence_selection,
)
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.discovery import FactualEvaluability
from kronos.intraday.historical_qualification import (
    HistoricalPreviousSessionFacts,
    reconstruct_previous_session_facts,
    select_historical_session,
)
from kronos.intraday.historical_semantic import (
    GovernedHistoricalCandlePayload,
    SemanticDirection,
    create_governed_historical_candle_payload,
)
from kronos.intraday.nifty_relative_context import build_nifty_relative_context
from kronos.intraday.opening_semantic import build_opening_semantic_evidence
from kronos.intraday.probables_v2 import (
    DiscoveryProbablesEvidenceV2,
    ProbableReasonV2,
    ProbablesUnavailableMemberV2,
    ProbablesV2Error,
    build_semantic_qualification_evidence_v2,
    create_discovery_probables_evidence_v2,
)
from kronos.intraday.reconciliation import ReconciliationPublication
from kronos.market.schedule import MarketDaySchedule
from kronos.market.schedule_compatibility import (
    MarketScheduleCompatibilityArtifact,
)
from kronos.provider.contracts.market_data import HistoricalCandle


DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY = (
    "KRONOS-INTRADAY-DISCOVERY-PROBABLES-EVIDENCE-MAPPER-V2"
)
DISCOVERY_PROBABLES_V2_REFRESH_VERSION = "2.0.0"


@dataclass(frozen=True, slots=True)
class DiscoveryProbablesV2Facts:
    """Exact completed inputs retained in-memory for one V2 mapping boundary."""

    facts_identity: str
    universe_member_identity: str
    canonical_subject_identity: str
    subject_exchange: str
    discovery_bundle_identity: str
    observation_boundary: datetime
    current_schedule: MarketDaySchedule
    previous_schedule: MarketDaySchedule
    previous_session_facts: HistoricalPreviousSessionFacts
    previous_daily: tuple[GovernedHistoricalCandlePayload, ...]
    previous_one_hour: tuple[GovernedHistoricalCandlePayload, ...]
    current_one_hour: tuple[GovernedHistoricalCandlePayload, ...]
    current_fifteen_minute: tuple[GovernedHistoricalCandlePayload, ...]
    current_five_minute: tuple[GovernedHistoricalCandlePayload, ...]
    provenance: tuple[str, ...]
    integrity_identity: str

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("facts_identity")
        values.pop("integrity_identity")
        payloads = (
            *self.previous_daily,
            *self.previous_one_hour,
            *self.current_one_hour,
            *self.current_fifteen_minute,
            *self.current_five_minute,
        )
        if (
            not self.facts_identity.startswith("INTRADAY-DISCOVERY-PROBABLES-V2-FACTS-")
            or not _texts((
                self.universe_member_identity,
                self.canonical_subject_identity,
                self.subject_exchange,
                self.discovery_bundle_identity,
            ))
            or not _aware(self.observation_boundary)
            or type(self.current_schedule) is not MarketDaySchedule
            or type(self.previous_schedule) is not MarketDaySchedule
            or type(self.previous_session_facts) is not HistoricalPreviousSessionFacts
            or len(self.previous_daily) != 1
            or len(self.previous_one_hour) < 2
            or any(type(item) is not GovernedHistoricalCandlePayload for item in payloads)
            or any(
                item.canonical_subject_identity != self.canonical_subject_identity
                or item.observation_boundary != self.observation_boundary
                for item in payloads
            )
            or not _texts(self.provenance)
            or self.facts_identity
            != _identity("INTRADAY-DISCOVERY-PROBABLES-V2-FACTS-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-DISCOVERY-PROBABLES-V2-FACTS-", values)
        ):
            raise ProbablesV2Error("DISCOVERY_PROBABLES_V2_FACTS_INVALID")


@dataclass(frozen=True, slots=True)
class DiscoveryProbablesV2FactsV2(DiscoveryProbablesV2Facts):
    """Successor facts retaining exact DOMAIN-008 schedule compatibility."""

    schedule_compatibility: MarketScheduleCompatibilityArtifact

    def __post_init__(self) -> None:
        DiscoveryProbablesV2Facts.__post_init__(self)
        if (
            type(self.schedule_compatibility)
            is not MarketScheduleCompatibilityArtifact
            or self.schedule_compatibility.analysis_boundary
            != self.observation_boundary
            or self.schedule_compatibility.current_session_identity
            != self.current_schedule.session_id
            or self.schedule_compatibility.previous_session_identity
            != self.previous_schedule.session_id
        ):
            raise ProbablesV2Error("DISCOVERY_PROBABLES_V2_FACTS_INVALID")


DiscoveryProbablesV2FactSet = DiscoveryProbablesV2Facts | DiscoveryProbablesV2FactsV2


def is_discovery_probables_v2_facts(value: object) -> bool:
    return type(value) in {DiscoveryProbablesV2Facts, DiscoveryProbablesV2FactsV2}


@dataclass(frozen=True, slots=True)
class DiscoveryProbablesV2Mapping:
    mapping_identity: str
    discovery_run_identity: str
    observation_boundary: datetime
    member_evidence: tuple[DiscoveryProbablesEvidenceV2, ...]
    unavailable_members: tuple[ProbablesUnavailableMemberV2, ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    mapper_identity: str = DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY
    mapper_version: str = DISCOVERY_PROBABLES_V2_REFRESH_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("mapping_identity")
        values.pop("integrity_identity")
        population = (
            *(item.universe_member_identity for item in self.member_evidence),
            *(item.universe_member_identity for item in self.unavailable_members),
        )
        if (
            not self.mapping_identity.startswith("INTRADAY-DISCOVERY-PROBABLES-V2-REFRESH-")
            or not _text(self.discovery_run_identity)
            or not _aware(self.observation_boundary)
            or not population
            or len(population) != len(set(population))
            or not _texts(self.provenance)
            or self.mapper_identity != DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY
            or self.mapper_version != DISCOVERY_PROBABLES_V2_REFRESH_VERSION
            or self.mapping_identity
            != _identity("INTRADAY-DISCOVERY-PROBABLES-V2-REFRESH-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-DISCOVERY-PROBABLES-V2-REFRESH-", values)
        ):
            raise ProbablesV2Error("DISCOVERY_PROBABLES_V2_REFRESH_INVALID")


def create_discovery_probables_v2_facts(
    *,
    universe_member_identity: str,
    canonical_subject_identity: str,
    subject_exchange: str,
    discovery_bundle_identity: str,
    observation_boundary_identity: str,
    observation_boundary: datetime,
    current_schedule: MarketDaySchedule,
    previous_schedule: MarketDaySchedule,
    previous_daily: Sequence[HistoricalCandle],
    previous_one_hour: Sequence[HistoricalCandle],
    current_one_hour: Sequence[HistoricalCandle],
    current_fifteen_minute: Sequence[HistoricalCandle],
    current_five_minute: Sequence[HistoricalCandle],
    schedule_compatibility: MarketScheduleCompatibilityArtifact | None = None,
) -> DiscoveryProbablesV2FactSet:
    """Create the exact cross-session candle surface required by V2."""

    if (
        not _texts((
            universe_member_identity,
            canonical_subject_identity,
            subject_exchange,
            discovery_bundle_identity,
            observation_boundary_identity,
        ))
        or not _aware(observation_boundary)
        or type(current_schedule) is not MarketDaySchedule
        or type(previous_schedule) is not MarketDaySchedule
    ):
        raise ProbablesV2Error("DISCOVERY_PROBABLES_V2_FACTS_INPUT_INVALID")
    raw = {
        "previous_daily": tuple(previous_daily),
        "previous_one_hour": tuple(previous_one_hour),
        "current_one_hour": tuple(current_one_hour),
        "current_fifteen_minute": tuple(current_fifteen_minute),
        "current_five_minute": tuple(current_five_minute),
    }
    if (
        len(raw["previous_daily"]) != 1
        or len(raw["previous_one_hour"]) < 2
        or any(type(item) is not HistoricalCandle for values in raw.values() for item in values)
    ):
        raise ProbablesV2Error("DISCOVERY_PROBABLES_V2_COMPLETED_FACTS_UNAVAILABLE")
    operation = f"INTRADAY-DISCOVERY-V2-SEMANTIC:{discovery_bundle_identity}"
    provenance = (
        DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY,
        discovery_bundle_identity,
        "COMPLETED_GOVERNED_CANDLES_ONLY",
    )
    daily_payloads = (_daily_payload(
        raw["previous_daily"][0], canonical_subject_identity, previous_schedule,
        observation_boundary, operation, provenance,
    ),)
    prior_hour_payloads = _intraday_payloads(
        raw["previous_one_hour"], IntradayTimeframe.ONE_HOUR,
        canonical_subject_identity, previous_schedule, observation_boundary,
        operation, provenance,
    )
    current_hour_payloads = _intraday_payloads(
        raw["current_one_hour"], IntradayTimeframe.ONE_HOUR,
        canonical_subject_identity, current_schedule, observation_boundary,
        operation, provenance,
    )
    current_fifteen_payloads = _intraday_payloads(
        raw["current_fifteen_minute"], IntradayTimeframe.FIFTEEN_MINUTES,
        canonical_subject_identity, current_schedule, observation_boundary,
        operation, provenance,
    )
    current_five_payloads = _intraday_payloads(
        raw["current_five_minute"], IntradayTimeframe.FIVE_MINUTES,
        canonical_subject_identity, current_schedule, observation_boundary,
        operation, provenance,
    )
    session = select_historical_session(
        calendar=_SchedulePair(current_schedule, previous_schedule),
        exchange=current_schedule.exchange,
        target_trading_date=current_schedule.trading_date,
        observation_boundary_identity=observation_boundary_identity,
        observation_boundary=observation_boundary,
        provenance=provenance,
    )
    daily = raw["previous_daily"][0]
    previous = reconstruct_previous_session_facts(
        canonical_identity=canonical_subject_identity,
        session=session,
        previous_daily_candle_identity=daily_payloads[0].candle_identity,
        completed_at=daily_payloads[0].available_at,
        high=_decimal(daily.high), low=_decimal(daily.low), close=_decimal(daily.close),
        source_integrity_identity=daily_payloads[0].integrity_identity,
        provenance=provenance,
    )
    values = {
        "universe_member_identity": universe_member_identity,
        "canonical_subject_identity": canonical_subject_identity,
        "subject_exchange": subject_exchange,
        "discovery_bundle_identity": discovery_bundle_identity,
        "observation_boundary": observation_boundary,
        "current_schedule": current_schedule,
        "previous_schedule": previous_schedule,
        "previous_session_facts": previous,
        "previous_daily": daily_payloads,
        "previous_one_hour": prior_hour_payloads,
        "current_one_hour": current_hour_payloads,
        "current_fifteen_minute": current_fifteen_payloads,
        "current_five_minute": current_five_payloads,
        "provenance": provenance,
    }
    if schedule_compatibility is not None:
        values["schedule_compatibility"] = schedule_compatibility
        fact_type = DiscoveryProbablesV2FactsV2
    else:
        fact_type = DiscoveryProbablesV2Facts
    return fact_type(
        facts_identity=_identity("INTRADAY-DISCOVERY-PROBABLES-V2-FACTS-", values),
        integrity_identity=_identity("INTEGRITY-DISCOVERY-PROBABLES-V2-FACTS-", values),
        **values,
    )


def map_discovery_execution_to_probables_v2(
    *, execution: object, reconciliation: ReconciliationPublication,
) -> DiscoveryProbablesV2Mapping:
    """Bind one exact Discovery execution to phase-aware V2 inputs."""

    from kronos.intraday.discovery_runtime import DiscoveryRuntimeExecution

    if type(execution) is not DiscoveryRuntimeExecution or type(reconciliation) is not ReconciliationPublication:
        raise ProbablesV2Error("DISCOVERY_PROBABLES_V2_MAPPING_INPUT_INVALID")
    run = execution.run
    facts = {item.universe_member_identity: item for item in execution.probables_v2_facts}
    if len(facts) != len(execution.probables_v2_facts):
        raise ProbablesV2Error("DISCOVERY_PROBABLES_V2_DUPLICATE_FACTS")
    members = {item.universe_member_identity: item for item in reconciliation.members}
    results = {item.universe_member_identity: item for item in run.results}
    selections: dict[str, CompletedEvidenceSelection] = {}
    for identity, item in facts.items():
        try:
            selections[identity] = build_completed_evidence_selection(
                canonical_subject_identity=item.canonical_subject_identity,
                analysis_boundary=run.observation_boundary,
                current_schedule=item.current_schedule,
                previous_schedule=item.previous_schedule,
                previous_daily=item.previous_daily,
                previous_one_hour=item.previous_one_hour,
                current_one_hour=item.current_one_hour,
                current_fifteen_minute=item.current_fifteen_minute,
                current_five_minute=item.current_five_minute,
                provenance=(DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY, item.facts_identity),
                schedule_compatibility=(
                    item.schedule_compatibility
                    if type(item) is DiscoveryProbablesV2FactsV2
                    else None
                ),
            )
        except CompletedEvidenceError:
            continue
    benchmark_identity = next((
        identity for identity, item in facts.items()
        if item.canonical_subject_identity == "NSE-INDEX-NIFTY"
    ), None)
    benchmark_selection = None if benchmark_identity is None else selections.get(benchmark_identity)
    member_evidence: list[DiscoveryProbablesEvidenceV2] = []
    unavailable: list[ProbablesUnavailableMemberV2] = []
    for result in run.results:
        item = facts.get(result.universe_member_identity)
        selection = selections.get(result.universe_member_identity)
        member = members.get(result.universe_member_identity)
        if (
            member is None or item is None or selection is None
            or result.evaluability is not FactualEvaluability.FACTUALLY_EVALUABLE
            or result.machine_fact_bundle_identity != (None if item is None else item.discovery_bundle_identity)
        ):
            unavailable.append(ProbablesUnavailableMemberV2(
                universe_member_identity=result.universe_member_identity,
                canonical_subject_identity=result.canonical_identity,
                market_session_identity=run.market_session_identity,
                analysis_boundary=run.observation_boundary,
                reason=(ProbableReasonV2.SOURCE_DISCOVERY_UNAVAILABLE if item is None else ProbableReasonV2.MANDATORY_EVIDENCE_UNAVAILABLE),
                source_identity=run.run_identity,
                provenance=(
                    DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY,
                    result.persistence_identity,
                    *tuple(value.value for value in result.reasons),
                ),
            ))
            continue
        provenance = (DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY, item.facts_identity, item.integrity_identity)
        nifty = None
        opening = None
        if selection.phase is IntradayAnalysisPhase.OPENING:
            subject_candle = selection.candles(IntradayTimeframe.FIFTEEN_MINUTES)[0]
            benchmark_candle = None
            benchmark_open = None
            if benchmark_selection is not None and benchmark_selection.phase is IntradayAnalysisPhase.OPENING:
                benchmark_candle = benchmark_selection.candles(IntradayTimeframe.FIFTEEN_MINUTES)[0]
                benchmark_open = benchmark_candle.open
            direction = (
                SemanticDirection.LONG if subject_candle.close > subject_candle.open
                else SemanticDirection.SHORT if subject_candle.close < subject_candle.open
                else SemanticDirection.NON_DIRECTIONAL
            )
            nifty = build_nifty_relative_context(
                canonical_subject_identity=item.canonical_subject_identity,
                subject_exchange=item.subject_exchange,
                opening_direction=direction.value,
                analysis_boundary=run.observation_boundary,
                subject_candle=subject_candle,
                benchmark_candle=benchmark_candle,
                subject_session_open=subject_candle.open,
                benchmark_session_open=benchmark_open,
                provenance=provenance,
            )
            opening = build_opening_semantic_evidence(
                selection=selection,
                narrow_cpr_fact=item.previous_session_facts.narrow_cpr,
                nifty_relative_evidence=nifty,
                provenance=provenance,
            )
        semantic = build_semantic_qualification_evidence_v2(
            selection=selection,
            narrow_cpr_fact=item.previous_session_facts.narrow_cpr,
            opening_semantic=opening,
            nifty_relative=nifty,
            provenance=provenance,
        )
        member_evidence.append(create_discovery_probables_evidence_v2(
            universe_member_identity=result.universe_member_identity,
            source_discovery_run_identity=run.run_identity,
            source_discovery_member_identity=result.persistence_identity,
            market_session_identity=selection.current_market_session_identity,
            completed_evidence=selection,
            semantic_evidence=semantic,
            opening_semantic=opening,
            nifty_relative=nifty,
            provenance=provenance,
        ))
    if len(run.results) != len(reconciliation.members) or set(results) != set(members):
        raise ProbablesV2Error("DISCOVERY_PROBABLES_V2_POPULATION_MISMATCH")
    values = {
        "discovery_run_identity": run.run_identity,
        "observation_boundary": run.observation_boundary,
        "member_evidence": tuple(member_evidence),
        "unavailable_members": tuple(unavailable),
        "provenance": (DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY, run.integrity_identity),
        "mapper_identity": DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY,
        "mapper_version": DISCOVERY_PROBABLES_V2_REFRESH_VERSION,
    }
    return DiscoveryProbablesV2Mapping(
        mapping_identity=_identity("INTRADAY-DISCOVERY-PROBABLES-V2-REFRESH-", values),
        integrity_identity=_identity("INTEGRITY-DISCOVERY-PROBABLES-V2-REFRESH-", values),
        **values,
    )


def _daily_payload(candle: HistoricalCandle, subject: str, schedule: MarketDaySchedule, boundary: datetime, operation: str, provenance: tuple[str, ...]) -> GovernedHistoricalCandlePayload:
    return _payload(candle, IntradayTimeframe.DAILY, schedule.windows[0].opens_at, schedule.windows[-1].closes_at, subject, schedule, boundary, operation, provenance)


def _intraday_payloads(candles: Sequence[HistoricalCandle], timeframe: IntradayTimeframe, subject: str, schedule: MarketDaySchedule, boundary: datetime, operation: str, provenance: tuple[str, ...]) -> tuple[GovernedHistoricalCandlePayload, ...]:
    expected = {item.start: item for item in expected_candle_boundaries(schedule, timeframe)}
    retained = []
    for candle in candles:
        item = expected.get(candle.timestamp)
        if item is None or item.end > boundary.astimezone(item.end.tzinfo):
            raise ProbablesV2Error("DISCOVERY_PROBABLES_V2_COMPLETED_FACTS_INVALID")
        retained.append(_payload(candle, timeframe, item.start, item.end, subject, schedule, boundary, operation, provenance))
    return tuple(retained)


def _payload(candle: HistoricalCandle, timeframe: IntradayTimeframe, start: datetime, end: datetime, subject: str, schedule: MarketDaySchedule, boundary: datetime, operation: str, provenance: tuple[str, ...]) -> GovernedHistoricalCandlePayload:
    return create_governed_historical_candle_payload(
        canonical_subject_identity=subject, exchange=schedule.exchange,
        market_identity=schedule.exchange, market_session_identity=schedule.session_id,
        timeframe=timeframe, candle_start=start, candle_end=end,
        open=_decimal(candle.open), high=_decimal(candle.high), low=_decimal(candle.low), close=_decimal(candle.close),
        volume=candle.volume, observation_boundary=boundary,
        provider_source_identity="DOMAIN-006:KITE:HISTORICAL",
        source_operation_identity=operation, provenance=provenance,
    )


class _SchedulePair:
    def __init__(self, current: MarketDaySchedule, previous: MarketDaySchedule) -> None:
        self._current = current
        self._previous = previous

    def schedule_for(self, exchange: str, trading_date: date):  # type: ignore[no-untyped-def]
        return self._current if exchange == self._current.exchange and trading_date == self._current.trading_date else None

    def previous_trading_schedule(self, exchange: str, before_date: date):  # type: ignore[no-untyped-def]
        return self._previous if exchange == self._current.exchange and before_date == self._current.trading_date else None


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as error:
        raise ProbablesV2Error("DISCOVERY_PROBABLES_V2_PRICE_INVALID") from error


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":")).encode()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {name: _normalize(item) for name, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Sequence[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


__all__ = [
    "DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY",
    "DISCOVERY_PROBABLES_V2_REFRESH_VERSION",
    "DiscoveryProbablesV2Facts",
    "DiscoveryProbablesV2FactsV2",
    "DiscoveryProbablesV2FactSet",
    "DiscoveryProbablesV2Mapping",
    "create_discovery_probables_v2_facts",
    "is_discovery_probables_v2_facts",
    "map_discovery_execution_to_probables_v2",
]
