"""RELIANCE-only factual runtime bootstrap for Intraday V1 Slices 0-3."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from kronos.application.intraday_workstation import (
    IntradayEvidenceBundle,
    IntradayWorkstationSnapshot,
)
from kronos.instrument.catalogue import load_canonical_instrument_catalogue
from kronos.instrument.runtime import RuntimeInstrumentRegistry
from kronos.intraday.candles import provider_interval
from kronos.intraday.composition import (
    CoreSlice1CompositionError,
    CoreSlice1Failure,
    CoreSlice1FactualComposition,
    compose_core_slice1_facts,
)
from kronos.intraday.context import build_slice1e_context
from kronos.intraday.context_persistence import LocalSlice1EContextStore
from kronos.intraday.contracts import GovernedCandle, IntradayTimeframe, SourceProvenance
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.intraday.persistence import LocalIntradayFactualEvidenceStore
from kronos.intraday.structure import (
    StructuralFact,
    barriers_from_slice1e,
    build_structural_evidence,
)
from kronos.intraday.structure_persistence import LocalStructuralEvidenceStore
from kronos.intraday.telemetry import ShadowTelemetryEvidence, build_shadow_telemetry
from kronos.intraday.telemetry_persistence import LocalShadowTelemetryStore
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import HistoricalCandle, HistoricalCandleRequest


RELIANCE = "RELIANCE"
PRESENTATION_SELECTION_POLICY = "LATEST_COMPLETED_FACT_PRESENTATION_ONLY_V1"
DEFAULT_INTRADAY_EVIDENCE_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence" / "intraday-v1"
)
_TIMEFRAMES = (
    IntradayTimeframe.DAILY,
    IntradayTimeframe.ONE_HOUR,
    IntradayTimeframe.FIFTEEN_MINUTES,
    IntradayTimeframe.FIVE_MINUTES,
)


class RelianceBootstrapAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    DATA_INCOMPLETE = "DATA_INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


class RelianceBootstrapStage(StrEnum):
    CANONICAL_CATALOGUE = "CANONICAL_CATALOGUE"
    CANONICAL_PUBLICATION = "CANONICAL_PUBLICATION"
    LEASE_ACQUISITION = "LEASE_ACQUISITION"
    PROVIDER_ASSERTION = "PROVIDER_ASSERTION"
    RUNTIME_INSTRUMENT = "RUNTIME_INSTRUMENT"
    PROVIDER_INSTRUMENT = "PROVIDER_INSTRUMENT"
    MARKET_SCHEDULE = "MARKET_SCHEDULE"
    HISTORICAL_REQUEST = "HISTORICAL_REQUEST"
    HISTORICAL_RETRIEVAL = "HISTORICAL_RETRIEVAL"
    RECONCILIATION = "RECONCILIATION"
    CONTEXT_EVIDENCE = "CONTEXT_EVIDENCE"
    STRUCTURAL_EVIDENCE = "STRUCTURAL_EVIDENCE"
    TELEMETRY = "TELEMETRY"
    PERSISTENCE = "PERSISTENCE"
    PROJECTION = "PROJECTION"


@dataclass(frozen=True, slots=True)
class HistoricalRetrievalEvidence:
    timeframe: IntradayTimeframe
    requested_start: datetime
    requested_end: datetime
    provider_interval: str
    received_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    provider: str = "KITE"
    source_identity: str = "DOMAIN-006:KITE:HISTORICAL"


@dataclass(frozen=True, slots=True)
class RelianceComparisonPack:
    """Exact Native input held for later Slice 3V factual validation."""

    canonical_instrument_id: str
    trading_date: str
    observation_boundary: datetime
    previous_high: Decimal | None
    previous_low: Decimal | None
    previous_close: Decimal | None
    levels: tuple[tuple[str, Decimal | None], ...]
    cpr: tuple[tuple[str, Decimal | None], ...]
    latest_completed: tuple[tuple[IntradayTimeframe, GovernedCandle | None], ...]
    selected_facts: tuple[StructuralFact, ...]
    five_minute_telemetry: ShadowTelemetryEvidence
    provenance: tuple[SourceProvenance, ...]
    presentation_selection_policy: str = PRESENTATION_SELECTION_POLICY


@dataclass(frozen=True, slots=True)
class RelianceBootstrapResult:
    availability: RelianceBootstrapAvailability
    detail: str
    registry: RuntimeInstrumentRegistry | None = field(repr=False)
    bundle: IntradayEvidenceBundle | None = None
    retrievals: tuple[HistoricalRetrievalEvidence, ...] = ()
    restart_verified: bool = False
    comparison_pack: RelianceComparisonPack | None = None
    stage: RelianceBootstrapStage = RelianceBootstrapStage.PROJECTION
    failure_code: str = ""
    diagnostic_at: datetime | None = None


class RelianceIntradayBootstrap:
    """Acquire one operation-scoped lease and build factual evidence once."""

    def __init__(
        self,
        *,
        acquire_lease: Callable[[], object],
        calendar_publisher: MarketCalendarPublisher | None = None,
        evidence_root: Path = DEFAULT_INTRADAY_EVIDENCE_ROOT,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if not callable(acquire_lease) or not callable(clock):
            raise ValueError("RELIANCE_BOOTSTRAP_DEPENDENCY_INVALID")
        self._acquire_lease = acquire_lease
        self._calendar = calendar_publisher or MarketCalendarPublisher()
        self._root = Path(evidence_root).expanduser()
        self._clock = clock

    def run(self) -> RelianceBootstrapResult:
        observed_at = self._clock()
        stage = RelianceBootstrapStage.CANONICAL_CATALOGUE
        unbound: RuntimeInstrumentRegistry | None = None
        active_registry: RuntimeInstrumentRegistry | None = None
        retrievals: list[HistoricalRetrievalEvidence] = []
        lease = None
        try:
            catalogue = load_canonical_instrument_catalogue()
            stage = RelianceBootstrapStage.CANONICAL_PUBLICATION
            unbound = catalogue.runtime_registry(
                provider_assertions=(), observed_at=observed_at
            )
            active_registry = unbound
            stage = RelianceBootstrapStage.LEASE_ACQUISITION
            lease = self._acquire_lease()
            stage = RelianceBootstrapStage.PROVIDER_ASSERTION
            assertions = lease.instrument_assertions(
                "NSE", source_boundary=observed_at, valid_through=lease.valid_through
            )
            stage = RelianceBootstrapStage.RUNTIME_INSTRUMENT
            registry = catalogue.runtime_registry(
                provider_assertions=assertions, observed_at=observed_at
            )
            active_registry = registry
            runtime_instrument = registry.require_consumable(RELIANCE)
            stage = RelianceBootstrapStage.PROVIDER_INSTRUMENT
            record = self._provider_record(lease.instrument_records("NSE"))
            binding = runtime_instrument.provider_binding
            if binding is None or binding.provider_symbol != record.trading_symbol:
                raise ValueError("RELIANCE_PROVIDER_BINDING_MISMATCH")

            stage = RelianceBootstrapStage.MARKET_SCHEDULE
            local = observed_at.astimezone(ZoneInfo("Asia/Kolkata"))
            source = CurrentMarketCalendarScheduleSource(
                self._calendar,
                observed_at=observed_at,
                canonical_instrument_id=(
                    runtime_instrument.canonical.canonical_instrument_id
                ),
            )
            schedule = source.schedule_for("NSE", local.date())
            if schedule is None or local < schedule.windows[0].opens_at:
                return RelianceBootstrapResult(
                    RelianceBootstrapAvailability.UNAVAILABLE,
                    "GOVERNED_TRADING_SESSION_NOT_ACTIVE",
                    registry,
                    stage=stage,
                    failure_code="GOVERNED_TRADING_SESSION_NOT_ACTIVE",
                    diagnostic_at=observed_at,
                )
            previous = source.previous_trading_schedule("NSE", local.date())
            current_end = min(local, schedule.windows[-1].closes_at)
            candles: dict[IntradayTimeframe, tuple[HistoricalCandle, ...]] = {}
            provenance: dict[IntradayTimeframe, SourceProvenance] = {}
            prior_daily: tuple[HistoricalCandle, ...] = ()
            for timeframe in _TIMEFRAMES:
                stage = RelianceBootstrapStage.HISTORICAL_REQUEST
                start = (
                    datetime.combine(previous.trading_date, time.min, ZoneInfo(previous.timezone))
                    if timeframe is IntradayTimeframe.DAILY
                    else schedule.windows[0].opens_at
                )
                request = HistoricalCandleRequest(record, start, current_end, provider_interval(timeframe))
                stage = RelianceBootstrapStage.HISTORICAL_RETRIEVAL
                received = tuple(lease.historical_candles(request))
                retrievals.append(HistoricalRetrievalEvidence(
                    timeframe, start, current_end, request.interval.value, len(received),
                    received[0].timestamp if received else None,
                    received[-1].timestamp if received else None,
                ))
                if timeframe is IntradayTimeframe.DAILY:
                    prior_daily = tuple(c for c in received if c.timestamp.astimezone(local.tzinfo).date() == previous.trading_date)
                candles[timeframe] = tuple(
                    c for c in received
                    if c.timestamp.astimezone(local.tzinfo).date() == local.date()
                )
                provenance[timeframe] = SourceProvenance(
                    "KITE", f"DOMAIN-006:KITE:HISTORICAL:{request.interval.value}",
                    observed_at, "1",
                )

            stage = RelianceBootstrapStage.PERSISTENCE
            factual_store = LocalIntradayFactualEvidenceStore(self._root / "candles")
            stage = RelianceBootstrapStage.RECONCILIATION
            composition = compose_core_slice1_facts(
                instrument_registry=registry,
                canonical_instrument_id=RELIANCE,
                calendar_source=source,
                exchange="NSE",
                trading_date=local.date(),
                observed_at=observed_at,
                run_created_at=observed_at,
                provider_candles=candles,
                provenance=provenance,
                evidence_store=factual_store,
            )
            stage = RelianceBootstrapStage.CONTEXT_EVIDENCE
            context = build_slice1e_context(
                run=composition.run,
                instrument=composition.instrument,
                current_trading_date=local.date(),
                calendar=source,
                previous_session_candles=prior_daily,
                provenance=provenance[IntradayTimeframe.DAILY],
                current_price=self._latest_close(composition),
            )
            stage = RelianceBootstrapStage.PERSISTENCE
            context_store = LocalSlice1EContextStore(self._root / "context")
            context_store.retain(context)
            stage = RelianceBootstrapStage.STRUCTURAL_EVIDENCE
            barriers = barriers_from_slice1e(context)
            structural_store = LocalStructuralEvidenceStore(self._root / "structure")
            structural = tuple(
                build_structural_evidence(
                    run=composition.run,
                    reconciliation=item.reconciliation,
                    barriers=barriers,
                )
                for item in composition.evidence
            )
            for item in structural:
                stage = RelianceBootstrapStage.PERSISTENCE
                structural_store.retain(item)
            stage = RelianceBootstrapStage.TELEMETRY
            five = next(
                item.reconciliation for item in composition.evidence
                if item.reconciliation.timeframe is IntradayTimeframe.FIVE_MINUTES
            )
            telemetry = build_shadow_telemetry(run=composition.run, reconciliation=five)
            stage = RelianceBootstrapStage.PERSISTENCE
            telemetry_store = LocalShadowTelemetryStore(self._root / "telemetry")
            telemetry_store.retain(telemetry)

            # Reconstruct every layer by explicit immutable identity before projection.
            stage = RelianceBootstrapStage.PERSISTENCE
            loaded_facts = tuple(factual_store.load(
                run_id=item.run.run_id,
                mapping_identity=item.reconciliation.instrument.mapping_identity,
                timeframe=item.reconciliation.timeframe,
                evidence_id=item.evidence_id,
            ) for item in composition.evidence)
            loaded_context = context_store.load(
                run_id=context.run.run_id,
                mapping_identity=context.instrument.mapping_identity,
                trading_date=local.date().isoformat(),
                evidence_id=context.evidence_id,
            )
            loaded_structure = tuple(structural_store.load(
                run_id=item.run.run_id,
                mapping_identity=item.instrument.mapping_identity,
                trading_date=item.trading_date.isoformat(),
                timeframe=item.timeframe,
                evidence_id=item.evidence_id,
            ) for item in structural)
            loaded_telemetry = telemetry_store.load(
                run_id=telemetry.run.run_id,
                mapping_identity=telemetry.instrument.mapping_identity,
                trading_date=telemetry.trading_date.isoformat(),
                timeframe=telemetry.timeframe,
                evidence_id=telemetry.evidence_id,
            )
            stage = RelianceBootstrapStage.PROJECTION
            reconstructed = CoreSlice1FactualComposition(
                composition.run, composition.instrument, composition.market_session, loaded_facts
            )
            pack = self._comparison_pack(
                reconstructed, loaded_context, loaded_structure, loaded_telemetry
            )
            return RelianceBootstrapResult(
                RelianceBootstrapAvailability.AVAILABLE,
                "REAL_GOVERNED_EVIDENCE_AVAILABLE",
                registry,
                IntradayEvidenceBundle(
                    reconstructed, loaded_context, loaded_structure, (loaded_telemetry,)
                ),
                tuple(retrievals),
                True,
                pack,
                stage,
                "",
                observed_at,
            )
        except CoreSlice1CompositionError as error:
            state = (
                RelianceBootstrapAvailability.DATA_INCOMPLETE
                if error.failure is CoreSlice1Failure.DATA_INCOMPLETE
                else RelianceBootstrapAvailability.UNAVAILABLE
            )
            return RelianceBootstrapResult(
                state, error.failure.value, active_registry,
                retrievals=tuple(retrievals),
                stage=stage,
                failure_code=error.failure.value,
                diagnostic_at=observed_at,
            )
        except Exception as error:
            fallback = f"{stage.value}_FAILED"
            failure = _sanitized_failure_code(error, fallback)
            return RelianceBootstrapResult(
                RelianceBootstrapAvailability.UNAVAILABLE,
                failure,
                unbound,
                retrievals=tuple(retrievals),
                stage=stage,
                failure_code=failure,
                diagnostic_at=observed_at,
            )
        finally:
            if lease is not None:
                lease.release()

    @staticmethod
    def _provider_record(records: tuple[InstrumentRecord, ...]) -> InstrumentRecord:
        matches = tuple(item for item in records if item.provider == "KITE" and item.exchange == "NSE" and item.trading_symbol == RELIANCE)
        if len(matches) != 1:
            raise ValueError("RELIANCE_PROVIDER_INSTRUMENT_UNAVAILABLE")
        return matches[0]

    @staticmethod
    def _latest_close(composition: CoreSlice1FactualComposition) -> Decimal | None:
        five = next(item for item in composition.evidence if item.reconciliation.timeframe is IntradayTimeframe.FIVE_MINUTES)
        candles = five.reconciliation.structural_candles
        return None if not candles else candles[-1].close

    @staticmethod
    def _comparison_pack(
        composition: CoreSlice1FactualComposition,
        context,
        structural,
        telemetry: ShadowTelemetryEvidence,
    ) -> RelianceComparisonPack:  # type: ignore[no-untyped-def]
        pivots = context.classic_pivots
        cpr = context.cpr
        selected = tuple(
            fact for timeframe in (
                IntradayTimeframe.ONE_HOUR,
                IntradayTimeframe.FIFTEEN_MINUTES,
                IntradayTimeframe.FIVE_MINUTES,
            )
            if (fact := _latest_fact_for_timeframe(structural, timeframe)) is not None
        )
        return RelianceComparisonPack(
            RELIANCE,
            composition.market_session.trading_date.isoformat(),
            composition.run.observation_boundary.observed_at,
            context.previous_session.high,
            context.previous_session.low,
            context.previous_session.close,
            tuple((name.upper(), getattr(pivots, name)) for name in (
                "p", "r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4"
            )),
            tuple((name.upper(), getattr(cpr, name)) for name in (
                "pivot", "bc", "tc", "upper", "lower", "width"
            )),
            tuple((
                item.reconciliation.timeframe,
                item.reconciliation.structural_candles[-1]
                if item.reconciliation.structural_candles else None,
            ) for item in composition.evidence),
            selected,
            telemetry,
            tuple(item.reconciliation.provenance for item in composition.evidence),
        )


class RelianceIntradayRuntimeWorkstation:
    """Lazy Browser projection; a GET never initiates authentication."""

    def __init__(self, bootstrap: RelianceIntradayBootstrap) -> None:
        self._bootstrap = bootstrap
        self._cached: RelianceBootstrapResult | None = None

    @property
    def last_result(self) -> RelianceBootstrapResult | None:
        return self._cached

    def snapshot(self, selected_canonical_instrument_id: str | None = None) -> IntradayWorkstationSnapshot:
        if self._cached is None or self._cached.availability is RelianceBootstrapAvailability.UNAVAILABLE:
            self._cached = self._bootstrap.run()
        result = self._cached
        selected = None if result.registry is None else result.registry.lookup(RELIANCE)
        if selected_canonical_instrument_id not in (None, "", RELIANCE):
            selected = None
        return IntradayWorkstationSnapshot(
            () if result.registry is None else result.registry.instruments,
            selected,
            result.bundle if selected is not None else None,
            result.availability.value,
            result.detail if result.availability is RelianceBootstrapAvailability.AVAILABLE else (
                f"Runtime stage: {result.stage.value}; Failure: {result.failure_code}"
            ),
        )


def latest_presentation_fact(structural_evidence):  # type: ignore[no-untyped-def]
    """Neutral latest-by-boundary selection with no analytical authority."""
    facts = tuple(fact for evidence in structural_evidence for fact in evidence.facts)
    return None if not facts else max(facts, key=lambda item: item.observation_boundary.observed_at)


def _latest_fact_for_timeframe(structural, timeframe):  # type: ignore[no-untyped-def]
    evidence = next((item for item in structural if item.timeframe is timeframe), None)
    if evidence is None or not evidence.facts:
        return None
    return max(
        evidence.facts,
        key=lambda item: (
            item.confirmation_boundary or item.end_boundary or item.start_boundary
            or item.observation_boundary.observed_at,
            item.fact_id,
        ),
    )


_FAILURE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,95}\Z")


def _sanitized_failure_code(error: Exception, fallback: str) -> str:
    failure = getattr(error, "failure", None)
    candidate = getattr(failure, "value", None)
    if isinstance(candidate, str) and _FAILURE_CODE.fullmatch(candidate):
        return candidate
    return fallback


__all__ = [
    "DEFAULT_INTRADAY_EVIDENCE_ROOT",
    "HistoricalRetrievalEvidence",
    "PRESENTATION_SELECTION_POLICY",
    "RELIANCE",
    "RelianceComparisonPack",
    "RelianceBootstrapAvailability",
    "RelianceBootstrapStage",
    "RelianceBootstrapResult",
    "RelianceIntradayBootstrap",
    "RelianceIntradayRuntimeWorkstation",
    "latest_presentation_fact",
]
