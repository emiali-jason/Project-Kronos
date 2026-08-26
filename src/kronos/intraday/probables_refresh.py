"""Typed Discovery-to-Probables evidence mapping for one governed refresh.

This module contains no admission predicates.  It reconstructs the already
approved semantic fact contract from completed Discovery candles, then binds
those facts to the exact immutable Discovery run consumed by Probables.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json

from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.discovery import FactualEvaluability
from kronos.intraday.historical_qualification import (
    reconstruct_previous_session_facts,
    select_historical_session,
)
from kronos.intraday.historical_semantic import (
    SemanticEvidenceError,
    SemanticQualificationEvidence,
    create_governed_historical_candle_payload,
    derive_semantic_qualification_evidence,
)
from kronos.intraday.probables import (
    FactualSourceKind,
    ProbableReason,
    ProbablesMemberEvidence,
    ProbablesUnavailableMember,
)
from kronos.intraday.qualification import NarrowCprFact
from kronos.intraday.reconciliation import ReconciliationPublication
from kronos.market.schedule import MarketDaySchedule
from kronos.provider.contracts.market_data import HistoricalCandle


DISCOVERY_PROBABLES_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-DISCOVERY-PROBABLES-EVIDENCE-V1"
)
DISCOVERY_PROBABLES_MAPPING_IDENTITY = (
    "KRONOS-INTRADAY-DISCOVERY-PROBABLES-EVIDENCE-MAPPER-V1"
)
DISCOVERY_PROBABLES_CONTRACT_VERSION = "1.0.0"


class DiscoveryProbablesMappingError(ValueError):
    """Sanitized evidence-mapping or cross-run integrity failure."""


@dataclass(frozen=True, slots=True)
class DiscoveryProbablesFacts:
    facts_identity: str
    universe_member_identity: str
    canonical_subject_identity: str
    universe_identity: str
    universe_version: str
    reconciliation_identity: str
    reconciliation_version: str
    discovery_bundle_identity: str
    observation_boundary: datetime
    narrow_cpr_fact: NarrowCprFact
    semantic_evidence: SemanticQualificationEvidence
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = DISCOVERY_PROBABLES_EVIDENCE_IDENTITY
    schema_version: str = DISCOVERY_PROBABLES_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("facts_identity")
        values.pop("integrity_identity")
        if (
            not self.facts_identity.startswith("INTRADAY-DISCOVERY-PROBABLES-FACTS-")
            or not _texts((
                self.universe_member_identity,
                self.canonical_subject_identity,
                self.universe_identity,
                self.universe_version,
                self.reconciliation_identity,
                self.reconciliation_version,
                self.discovery_bundle_identity,
            ))
            or not _aware(self.observation_boundary)
            or type(self.narrow_cpr_fact) is not NarrowCprFact
            or type(self.semantic_evidence) is not SemanticQualificationEvidence
            or self.narrow_cpr_fact.canonical_subject_identity
            != self.canonical_subject_identity
            or self.narrow_cpr_fact.observation_boundary > self.observation_boundary
            or self.semantic_evidence.canonical_subject_identity
            != self.canonical_subject_identity
            or self.semantic_evidence.observation_boundary != self.observation_boundary
            or self.semantic_evidence.source_bundle_identity
            != self.discovery_bundle_identity
            or not _texts(self.provenance)
            or self.schema_identity != DISCOVERY_PROBABLES_EVIDENCE_IDENTITY
            or self.schema_version != DISCOVERY_PROBABLES_CONTRACT_VERSION
            or self.facts_identity
            != _identity("INTRADAY-DISCOVERY-PROBABLES-FACTS-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-DISCOVERY-PROBABLES-FACTS-", values)
        ):
            raise DiscoveryProbablesMappingError(
                "DISCOVERY_PROBABLES_FACTS_INVALID"
            )


@dataclass(frozen=True, slots=True)
class DiscoveryProbablesMapping:
    mapping_identity: str
    discovery_run_identity: str
    observation_boundary: datetime
    universe_identity: str
    universe_version: str
    reconciliation_identity: str
    reconciliation_version: str
    member_evidence: tuple[ProbablesMemberEvidence, ...]
    unavailable_members: tuple[ProbablesUnavailableMember, ...]
    provenance: tuple[str, ...]
    integrity_identity: str
    mapper_identity: str = DISCOVERY_PROBABLES_MAPPING_IDENTITY
    mapper_version: str = DISCOVERY_PROBABLES_CONTRACT_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("mapping_identity")
        values.pop("integrity_identity")
        identities = tuple(
            item.universe_member_identity
            for item in (*self.member_evidence, *self.unavailable_members)
        )
        if (
            not self.mapping_identity.startswith("INTRADAY-DISCOVERY-PROBABLES-MAPPING-")
            or not _texts((
                self.discovery_run_identity,
                self.universe_identity,
                self.universe_version,
                self.reconciliation_identity,
                self.reconciliation_version,
            ))
            or not _aware(self.observation_boundary)
            or not identities
            or len(set(identities)) != len(identities)
            or any(
                type(item) is not ProbablesMemberEvidence
                or item.source_run_identity != self.discovery_run_identity
                or item.observation_boundary != self.observation_boundary
                for item in self.member_evidence
            )
            or any(
                type(item) is not ProbablesUnavailableMember
                or item.observation_boundary != self.observation_boundary
                for item in self.unavailable_members
            )
            or not _texts(self.provenance)
            or self.mapper_identity != DISCOVERY_PROBABLES_MAPPING_IDENTITY
            or self.mapper_version != DISCOVERY_PROBABLES_CONTRACT_VERSION
            or self.mapping_identity
            != _identity("INTRADAY-DISCOVERY-PROBABLES-MAPPING-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-DISCOVERY-PROBABLES-MAPPING-", values)
        ):
            raise DiscoveryProbablesMappingError(
                "DISCOVERY_PROBABLES_MAPPING_INVALID"
            )


def create_discovery_probables_facts(
    *,
    universe_member_identity: str,
    canonical_subject_identity: str,
    universe_identity: str,
    universe_version: str,
    reconciliation_identity: str,
    reconciliation_version: str,
    discovery_bundle_identity: str,
    observation_boundary_identity: str,
    observation_boundary: datetime,
    schedule: MarketDaySchedule,
    previous_schedule: MarketDaySchedule,
    completed_by_timeframe: Mapping[
        IntradayTimeframe, Sequence[HistoricalCandle]
    ],
) -> DiscoveryProbablesFacts:
    """Derive typed semantics from the exact completed candles already acquired."""

    if (
        not _texts((
            universe_member_identity,
            canonical_subject_identity,
            universe_identity,
            universe_version,
            reconciliation_identity,
            reconciliation_version,
            discovery_bundle_identity,
            observation_boundary_identity,
        ))
        or not _aware(observation_boundary)
        or type(schedule) is not MarketDaySchedule
        or type(previous_schedule) is not MarketDaySchedule
        or not isinstance(completed_by_timeframe, Mapping)
        or set(completed_by_timeframe) != set(IntradayTimeframe)
    ):
        raise DiscoveryProbablesMappingError(
            "DISCOVERY_PROBABLES_FACTS_INPUT_INVALID"
        )
    retained = {
        timeframe: tuple(completed_by_timeframe[timeframe])
        for timeframe in IntradayTimeframe
    }
    if (
        len(retained[IntradayTimeframe.DAILY]) != 1
        or any(
            len(retained[timeframe]) < 2
            for timeframe in (
                IntradayTimeframe.ONE_HOUR,
                IntradayTimeframe.FIFTEEN_MINUTES,
                IntradayTimeframe.FIVE_MINUTES,
            )
        )
        or any(
            type(candle) is not HistoricalCandle
            for candles in retained.values()
            for candle in candles
        )
    ):
        raise DiscoveryProbablesMappingError(
            "DISCOVERY_PROBABLES_COMPLETED_FACTS_UNAVAILABLE"
        )

    operation_identity = f"INTRADAY-DISCOVERY-SEMANTIC:{discovery_bundle_identity}"
    provenance = (
        DISCOVERY_PROBABLES_EVIDENCE_IDENTITY,
        discovery_bundle_identity,
        "COMPLETED_GOVERNED_CANDLES_ONLY",
    )
    payloads = []
    daily = retained[IntradayTimeframe.DAILY][0]
    payloads.append(_payload(
        candle=daily,
        timeframe=IntradayTimeframe.DAILY,
        candle_start=previous_schedule.windows[0].opens_at,
        candle_end=previous_schedule.windows[-1].closes_at,
        canonical_subject_identity=canonical_subject_identity,
        market_session_identity=schedule.session_id,
        observation_boundary=observation_boundary,
        source_operation_identity=operation_identity,
        exchange=schedule.exchange,
        provenance=provenance,
    ))
    for timeframe in (
        IntradayTimeframe.ONE_HOUR,
        IntradayTimeframe.FIFTEEN_MINUTES,
        IntradayTimeframe.FIVE_MINUTES,
    ):
        boundaries = {
            item.start: item
            for item in expected_candle_boundaries(schedule, timeframe)
            if item.end <= observation_boundary.astimezone(item.end.tzinfo)
        }
        for candle in retained[timeframe][-2:]:
            boundary = boundaries.get(candle.timestamp)
            if boundary is None:
                raise DiscoveryProbablesMappingError(
                    "DISCOVERY_PROBABLES_COMPLETED_FACTS_INVALID"
                )
            payloads.append(_payload(
                candle=candle,
                timeframe=timeframe,
                candle_start=boundary.start,
                candle_end=boundary.end,
                canonical_subject_identity=canonical_subject_identity,
                market_session_identity=schedule.session_id,
                observation_boundary=observation_boundary,
                source_operation_identity=operation_identity,
                exchange=schedule.exchange,
                provenance=provenance,
            ))

    calendar = _SchedulePair(schedule, previous_schedule)
    selection = select_historical_session(
        calendar=calendar,
        exchange=schedule.exchange,
        target_trading_date=schedule.trading_date,
        observation_boundary_identity=observation_boundary_identity,
        observation_boundary=observation_boundary,
        provenance=provenance,
    )
    previous = reconstruct_previous_session_facts(
        canonical_identity=canonical_subject_identity,
        session=selection,
        previous_daily_candle_identity=payloads[0].candle_identity,
        completed_at=payloads[0].available_at,
        high=_decimal(daily.high),
        low=_decimal(daily.low),
        close=_decimal(daily.close),
        source_integrity_identity=payloads[0].integrity_identity,
        provenance=provenance,
    )
    try:
        semantic = derive_semantic_qualification_evidence(
            candle_payloads=tuple(payloads),
            previous_session_facts=previous,
            source_bundle_identity=discovery_bundle_identity,
            source_operation_identity=operation_identity,
            provenance=provenance,
        )
    except SemanticEvidenceError as error:
        raise DiscoveryProbablesMappingError(
            "DISCOVERY_PROBABLES_SEMANTIC_EVIDENCE_INVALID"
        ) from error
    values = {
        "universe_member_identity": universe_member_identity,
        "canonical_subject_identity": canonical_subject_identity,
        "universe_identity": universe_identity,
        "universe_version": universe_version,
        "reconciliation_identity": reconciliation_identity,
        "reconciliation_version": reconciliation_version,
        "discovery_bundle_identity": discovery_bundle_identity,
        "observation_boundary": observation_boundary,
        "narrow_cpr_fact": previous.narrow_cpr,
        "semantic_evidence": semantic,
        "provenance": provenance,
        "schema_identity": DISCOVERY_PROBABLES_EVIDENCE_IDENTITY,
        "schema_version": DISCOVERY_PROBABLES_CONTRACT_VERSION,
    }
    return DiscoveryProbablesFacts(
        facts_identity=_identity("INTRADAY-DISCOVERY-PROBABLES-FACTS-", values),
        integrity_identity=_identity(
            "INTEGRITY-DISCOVERY-PROBABLES-FACTS-", values
        ),
        **values,
    )


def map_discovery_execution_to_probables(
    *,
    execution: object,
    reconciliation: ReconciliationPublication,
) -> DiscoveryProbablesMapping:
    """Bind exact Discovery results to typed Probables inputs without inference."""

    from kronos.intraday.discovery_runtime import DiscoveryRuntimeExecution

    if (
        type(execution) is not DiscoveryRuntimeExecution
        or type(reconciliation) is not ReconciliationPublication
    ):
        raise DiscoveryProbablesMappingError(
            "DISCOVERY_PROBABLES_MAPPING_INPUT_INVALID"
        )
    run = execution.run
    if (
        run.universe_identity != reconciliation.universe_identity
        or run.universe_version != reconciliation.universe_version
        or run.reconciliation_identity != reconciliation.publication_identity
        or run.reconciliation_version != reconciliation.publication_version
    ):
        raise DiscoveryProbablesMappingError(
            "DISCOVERY_PROBABLES_PUBLICATION_MISMATCH"
        )
    facts = {
        item.universe_member_identity: item
        for item in execution.probables_facts
    }
    if len(facts) != len(execution.probables_facts):
        raise DiscoveryProbablesMappingError(
            "DISCOVERY_PROBABLES_DUPLICATE_FACTS"
        )
    members = {item.universe_member_identity: item for item in reconciliation.members}
    member_evidence: list[ProbablesMemberEvidence] = []
    unavailable: list[ProbablesUnavailableMember] = []
    consumed: set[str] = set()
    for result in run.results:
        member = members.get(result.universe_member_identity)
        if member is None or result.observation_boundary != run.observation_boundary:
            raise DiscoveryProbablesMappingError(
                "DISCOVERY_PROBABLES_RESULT_MISMATCH"
            )
        item = facts.get(result.universe_member_identity)
        if item is not None:
            if (
                result.evaluability is not FactualEvaluability.FACTUALLY_EVALUABLE
                or result.machine_fact_bundle_identity != item.discovery_bundle_identity
                or item.canonical_subject_identity != result.canonical_identity
                or item.observation_boundary != run.observation_boundary
                or item.universe_identity != run.universe_identity
                or item.universe_version != run.universe_version
                or item.reconciliation_identity != run.reconciliation_identity
                or item.reconciliation_version != run.reconciliation_version
            ):
                raise DiscoveryProbablesMappingError(
                    "DISCOVERY_PROBABLES_FACT_LINKAGE_MISMATCH"
                )
            member_evidence.append(ProbablesMemberEvidence(
                universe_member_identity=result.universe_member_identity,
                canonical_subject_identity=result.canonical_identity,
                market_session_identity=(
                    item.semantic_evidence.market_session_identity
                ),
                observation_boundary=run.observation_boundary,
                source_kind=FactualSourceKind.NATIVE_DISCOVERY,
                source_run_identity=run.run_identity,
                source_member_identity=result.persistence_identity,
                narrow_cpr_fact=item.narrow_cpr_fact,
                semantic_evidence=item.semantic_evidence,
                provenance=(
                    DISCOVERY_PROBABLES_MAPPING_IDENTITY,
                    item.facts_identity,
                    item.integrity_identity,
                ),
            ))
            consumed.add(result.universe_member_identity)
            continue
        reason = (
            ProbableReason.PREREQUISITE_UNAVAILABLE
            if result.evaluability is FactualEvaluability.PREREQUISITE_UNAVAILABLE
            else ProbableReason.PROVIDER_FACT_UNAVAILABLE
            if result.evaluability is FactualEvaluability.FACTUAL_FAILURE
            else ProbableReason.SEMANTIC_FACT_UNAVAILABLE
        )
        unavailable.append(ProbablesUnavailableMember(
            universe_member_identity=result.universe_member_identity,
            canonical_subject_identity=result.canonical_identity,
            market_session_identity=run.market_session_identity,
            observation_boundary=run.observation_boundary,
            reason=reason,
            source_identity=result.persistence_identity,
            provenance=(
                DISCOVERY_PROBABLES_MAPPING_IDENTITY,
                *tuple(item.value for item in result.reasons),
            ),
        ))
    if consumed != set(facts) or len(run.results) != len(reconciliation.members):
        raise DiscoveryProbablesMappingError(
            "DISCOVERY_PROBABLES_POPULATION_MISMATCH"
        )
    values = {
        "discovery_run_identity": run.run_identity,
        "observation_boundary": run.observation_boundary,
        "universe_identity": run.universe_identity,
        "universe_version": run.universe_version,
        "reconciliation_identity": run.reconciliation_identity,
        "reconciliation_version": run.reconciliation_version,
        "member_evidence": tuple(member_evidence),
        "unavailable_members": tuple(unavailable),
        "provenance": (
            DISCOVERY_PROBABLES_MAPPING_IDENTITY,
            run.integrity_identity,
        ),
        "mapper_identity": DISCOVERY_PROBABLES_MAPPING_IDENTITY,
        "mapper_version": DISCOVERY_PROBABLES_CONTRACT_VERSION,
    }
    return DiscoveryProbablesMapping(
        mapping_identity=_identity(
            "INTRADAY-DISCOVERY-PROBABLES-MAPPING-", values
        ),
        integrity_identity=_identity(
            "INTEGRITY-DISCOVERY-PROBABLES-MAPPING-", values
        ),
        **values,
    )


class _SchedulePair:
    def __init__(
        self,
        target: MarketDaySchedule,
        previous: MarketDaySchedule,
    ) -> None:
        self._target = target
        self._previous = previous

    def schedule_for(
        self,
        exchange: str,
        trading_date: date,
    ):  # type: ignore[no-untyped-def]
        if exchange == self._target.exchange and trading_date == self._target.trading_date:
            return self._target
        return None

    def previous_trading_schedule(self, exchange: str, before_date: date):  # type: ignore[no-untyped-def]
        if exchange == self._target.exchange and before_date == self._target.trading_date:
            return self._previous
        return None


def _payload(
    *,
    candle: HistoricalCandle,
    timeframe: IntradayTimeframe,
    candle_start: datetime,
    candle_end: datetime,
    canonical_subject_identity: str,
    market_session_identity: str,
    observation_boundary: datetime,
    source_operation_identity: str,
    exchange: str,
    provenance: tuple[str, ...],
):  # type: ignore[no-untyped-def]
    return create_governed_historical_candle_payload(
        canonical_subject_identity=canonical_subject_identity,
        exchange=exchange,
        market_identity=exchange,
        market_session_identity=market_session_identity,
        timeframe=timeframe,
        candle_start=candle_start,
        candle_end=candle_end,
        open=_decimal(candle.open),
        high=_decimal(candle.high),
        low=_decimal(candle.low),
        close=_decimal(candle.close),
        volume=candle.volume,
        observation_boundary=observation_boundary,
        provider_source_identity="DOMAIN-006:KITE:HISTORICAL",
        source_operation_identity=source_operation_identity,
        provenance=provenance,
    )


def _identity(prefix: str, value: object) -> str:
    encoded = json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return prefix + sha256(encoded).hexdigest().upper()


def _decimal(value: float) -> Decimal:
    if type(value) is not float:
        raise DiscoveryProbablesMappingError(
            "DISCOVERY_PROBABLES_PRICE_INVALID"
        )
    return Decimal(str(value))


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {name: _normalize(item) for name, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Sequence[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


__all__ = [
    "DISCOVERY_PROBABLES_CONTRACT_VERSION",
    "DISCOVERY_PROBABLES_EVIDENCE_IDENTITY",
    "DISCOVERY_PROBABLES_MAPPING_IDENTITY",
    "DiscoveryProbablesFacts",
    "DiscoveryProbablesMapping",
    "DiscoveryProbablesMappingError",
    "create_discovery_probables_facts",
    "map_discovery_execution_to_probables",
]
