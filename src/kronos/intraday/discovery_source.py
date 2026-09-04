"""WO-05A Provider-backed factual source for Intraday Native Discovery."""

from __future__ import annotations

from datetime import datetime, time, timedelta
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
from kronos.intraday.discovery_failure_provenance import (
    MachineFactFailureAvailability,
    MachineFactFailureComponent,
    MachineFactFailureDetail,
    MachineFactFailureStage,
)
from kronos.intraday.discovery import DiscoveryReason
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.intraday.reconciliation import (
    Availability,
    ReconciliationMember,
    ReconciliationPublication,
)
from kronos.instrument.active_derivative import (
    ActiveDerivativeBindingArtifact,
    ActiveDerivativeResolutionSet,
    ActiveDerivativeSelectionFailure,
)
from kronos.intraday.probables_refresh import (
    DiscoveryProbablesMappingError,
    create_discovery_probables_facts,
)
from kronos.intraday.probables_v2 import ProbablesV2Error
from kronos.intraday.mcx_history import create_retained_mcx_candles
from kronos.intraday.mcx_history_persistence import McxContractHistoryStore
from kronos.intraday.probables_v2_refresh import (
    create_discovery_probables_v2_facts,
)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.schedule import (
    MarketDaySchedule,
    MarketSchedule,
    MarketWindow,
    TradingDayStatus,
)
from kronos.market.schedule_compatibility import (
    MarketScheduleCompatibilityArtifact,
    MarketScheduleCompatibilityError,
    publish_mcx_schedule_compatibility,
)
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
        active_derivative_resolutions: ActiveDerivativeResolutionSet | None = None,
        produce_probables_v2_facts: bool = False,
        mcx_history_store: McxContractHistoryStore | None = None,
    ) -> None:
        if (
            type(lease) is not ReadOnlyProviderLease
            or type(calendar_publisher) is not MarketCalendarPublisher
            or type(reconciliation) is not ReconciliationPublication
            or (
                active_derivative_resolutions is not None
                and type(active_derivative_resolutions)
                is not ActiveDerivativeResolutionSet
            )
            or type(produce_probables_v2_facts) is not bool
            or (
                mcx_history_store is not None
                and type(mcx_history_store) is not McxContractHistoryStore
            )
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
        self._active_derivative_resolutions = active_derivative_resolutions
        self._produce_probables_v2_facts = produce_probables_v2_facts
        self._mcx_history_store = mcx_history_store
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
                DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
                _failure_detail(
                    MachineFactFailureStage.BUNDLE_VALIDATION,
                    MachineFactFailureComponent.MACHINE_FACT_BUNDLE,
                    MachineFactFailureAvailability.INVALID,
                    "MACHINE_FACT_BUNDLE_INPUT_INVALID",
                ),
            )
        active_binding = self._active_binding(member)
        record = self._record(member, active_binding=active_binding)
        local = boundary.observation_boundary.astimezone(ZoneInfo("Asia/Kolkata"))
        calendar = CurrentMarketCalendarScheduleSource(
            self._calendar,
            observed_at=boundary.observation_boundary,
            canonical_instrument_id=member.canonical_identity,
        )
        try:
            schedule = (
                calendar.schedule_for(member.exchange, local.date())
                if active_binding is None
                else self._binding_schedule(active_binding, boundary.observation_boundary)
            )
            if boundary.observation_boundary not in self._session_identities:
                self._session_identities[boundary.observation_boundary] = (
                    governed_market_session_identities(
                        calendar_publisher=self._calendar,
                        reconciliation=self._reconciliation,
                        observed_at=boundary.observation_boundary,
                        active_derivative_resolutions=(
                            self._active_derivative_resolutions
                        ),
                    )
                )
        except DiscoveryMemberFactError:
            raise
        except Exception as error:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
                _failure_detail(
                    MachineFactFailureStage.SCHEDULE_SESSION_BINDING,
                    MachineFactFailureComponent.MARKET_SESSION,
                    MachineFactFailureAvailability.UNAVAILABLE,
                    "MARKET_SESSION_BINDING_FAILED",
                    provider_symbol=(
                        member.provider_symbol
                        if active_binding is None
                        else active_binding.provider_symbol
                    ),
                ),
            ) from error
        governed_session, governed_boundary = self._session_identities[
            boundary.observation_boundary
        ]
        if (
            schedule is None
            or boundary.market_session_identity != governed_session
            or boundary.market_session_boundary_identity != governed_boundary
        ):
            raise DiscoveryMemberFactError(
                DiscoveryReason.MARKET_SESSION_UNAVAILABLE,
                _failure_detail(
                    MachineFactFailureStage.SCHEDULE_SESSION_BINDING,
                    MachineFactFailureComponent.MARKET_SESSION,
                    MachineFactFailureAvailability.UNAVAILABLE,
                    "MARKET_SESSION_BINDING_UNAVAILABLE",
                    provider_symbol=(
                        member.provider_symbol
                        if active_binding is None
                        else active_binding.provider_symbol
                    ),
                ),
            )
        try:
            previous = calendar.previous_trading_schedule(member.exchange, local.date())
        except ValueError as error:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MARKET_SESSION_UNAVAILABLE,
                _failure_detail(
                    MachineFactFailureStage.SCHEDULE_SESSION_BINDING,
                    MachineFactFailureComponent.MARKET_SESSION,
                    MachineFactFailureAvailability.UNAVAILABLE,
                    "PREVIOUS_TRADING_SESSION_UNAVAILABLE",
                    provider_symbol=record.trading_symbol,
                ),
            ) from error
        schedule_compatibility: MarketScheduleCompatibilityArtifact | None = None
        if (
            active_binding is not None
            and (
                schedule.source_identity != previous.source_identity
                or schedule.source_version != previous.source_version
            )
        ):
            try:
                schedule_compatibility = publish_mcx_schedule_compatibility(
                    calendar_publisher=self._calendar,
                    contract_family=active_binding.provider_contract_family,
                    contract_expiry=active_binding.contract_expiry,
                    current_schedule=schedule,
                    previous_schedule=previous,
                    analysis_boundary=boundary.observation_boundary,
                )
            except MarketScheduleCompatibilityError as error:
                raise DiscoveryMemberFactError(
                    DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
                    _failure_detail(
                        MachineFactFailureStage.BUNDLE_VALIDATION,
                        MachineFactFailureComponent.MACHINE_FACT_BUNDLE,
                        MachineFactFailureAvailability.INVALID,
                        "DOMAIN008_SCHEDULE_COMPATIBILITY_INVALID",
                        provider_symbol=record.trading_symbol,
                    ),
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
        try:
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
                ) + (() if active_binding is None else (
                    active_binding.binding_identity,
                    active_binding.provider_snapshot_identity,
                )),
                provenance=(
                    DISCOVERY_FACTUAL_SOURCE_IDENTITY,
                    member.reconciliation_member_identity,
                ) + (() if active_binding is None else (
                    active_binding.integrity_identity,
                    active_binding.domain008_session_identity,
                )),
            )
        except Exception as error:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
                _failure_detail(
                    MachineFactFailureStage.BUNDLE_CONSTRUCTION,
                    MachineFactFailureComponent.MACHINE_FACT_BUNDLE,
                    MachineFactFailureAvailability.INVALID,
                    "MACHINE_FACT_BUNDLE_CONSTRUCTION_FAILED",
                    provider_symbol=record.trading_symbol,
                ),
            ) from error
        try:
            probables_facts = create_discovery_probables_facts(
                universe_member_identity=member.universe_member_identity,
                canonical_subject_identity=member.canonical_identity,
                universe_identity=self._universe_identity,
                universe_version=self._universe_version,
                reconciliation_identity=self._reconciliation_identity,
                reconciliation_version=self._reconciliation_version,
                discovery_bundle_identity=bundle.bundle_identity,
                observation_boundary_identity=(
                    boundary.market_session_boundary_identity
                ),
                observation_boundary=boundary.observation_boundary,
                schedule=schedule,
                previous_schedule=previous,
                completed_by_timeframe=completed_by_timeframe,
            )
        except DiscoveryProbablesMappingError:
            probables_facts = None
        probables_v2_facts = None
        diagnostic_failure_detail = None
        if self._produce_probables_v2_facts:
            try:
                previous_one_hour = self._acquire_previous_one_hour(
                    record=record,
                    schedule=previous,
                    observed_at=boundary.observation_boundary,
                )
                if active_binding is not None and self._mcx_history_store is not None:
                    retained = tuple(
                        candle
                        for timeframe, retained_schedule, candles in (
                            (IntradayTimeframe.DAILY, previous, previous_daily),
                            (IntradayTimeframe.ONE_HOUR, previous, previous_one_hour),
                            (
                                IntradayTimeframe.ONE_HOUR,
                                schedule,
                                completed_by_timeframe[IntradayTimeframe.ONE_HOUR],
                            ),
                            (
                                IntradayTimeframe.FIFTEEN_MINUTES,
                                schedule,
                                completed_by_timeframe[IntradayTimeframe.FIFTEEN_MINUTES],
                            ),
                            (
                                IntradayTimeframe.FIVE_MINUTES,
                                schedule,
                                completed_by_timeframe[IntradayTimeframe.FIVE_MINUTES],
                            ),
                        )
                        for candle in create_retained_mcx_candles(
                            active_binding=active_binding,
                            timeframe=timeframe,
                            schedule=retained_schedule,
                            candles=candles,
                            observation_boundary=boundary.observation_boundary,
                            source_operation_identity=bundle.bundle_identity,
                        )
                    )
                    self._mcx_history_store.retain_many(retained)
                probables_v2_facts = create_discovery_probables_v2_facts(
                    universe_member_identity=member.universe_member_identity,
                    canonical_subject_identity=member.canonical_identity,
                    subject_exchange=member.exchange,
                    discovery_bundle_identity=bundle.bundle_identity,
                    observation_boundary_identity=(
                        boundary.market_session_boundary_identity
                    ),
                    observation_boundary=boundary.observation_boundary,
                    current_schedule=schedule,
                    previous_schedule=previous,
                    previous_daily=previous_daily,
                    previous_one_hour=previous_one_hour,
                    current_one_hour=completed_by_timeframe[
                        IntradayTimeframe.ONE_HOUR
                    ],
                    current_fifteen_minute=completed_by_timeframe[
                        IntradayTimeframe.FIFTEEN_MINUTES
                    ],
                    current_five_minute=completed_by_timeframe[
                        IntradayTimeframe.FIVE_MINUTES
                    ],
                    schedule_compatibility=schedule_compatibility,
                )
            except DiscoveryMemberFactError as error:
                diagnostic_failure_detail = error.detail or _failure_detail(
                    MachineFactFailureStage.BUNDLE_VALIDATION,
                    MachineFactFailureComponent.MACHINE_FACT_BUNDLE,
                    MachineFactFailureAvailability.INVALID,
                    "PROBABLES_V2_FACT_BUNDLE_INVALID",
                )
                probables_v2_facts = None
            except ProbablesV2Error:
                diagnostic_failure_detail = _failure_detail(
                    MachineFactFailureStage.BUNDLE_VALIDATION,
                    MachineFactFailureComponent.MACHINE_FACT_BUNDLE,
                    MachineFactFailureAvailability.INVALID,
                    "PROBABLES_V2_FACT_BUNDLE_INVALID",
                )
                probables_v2_facts = None
        return DiscoveryFactAcquisition(
            universe_member_identity=member.universe_member_identity,
            canonical_identity=member.canonical_identity,
            bundle=bundle,
            probables_facts=probables_facts,
            probables_v2_facts=probables_v2_facts,
            diagnostic_failure_detail=diagnostic_failure_detail,
        )

    def _acquire_previous_one_hour(
        self,
        *,
        record: InstrumentRecord,
        schedule: MarketDaySchedule,
        observed_at: datetime,
    ) -> tuple[HistoricalCandle, ...]:
        self._historical_requests += 1
        interval = _interval_or_failure(
            IntradayTimeframe.ONE_HOUR,
            MachineFactFailureComponent.PRIOR_SESSION_1H_EVIDENCE,
        )
        try:
            candles = tuple(self._lease.historical_candles(HistoricalCandleRequest(
                instrument=record,
                start=schedule.windows[0].opens_at,
                end=schedule.windows[-1].closes_at - timedelta(microseconds=1),
                interval=interval,
            )))
        except Exception as error:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
                _failure_detail(
                    MachineFactFailureStage.CANDLE_ACQUISITION,
                    MachineFactFailureComponent.PRIOR_SESSION_1H_EVIDENCE,
                    MachineFactFailureAvailability.UNAVAILABLE,
                    "PROVIDER_CANDLE_ACQUISITION_FAILED",
                    timeframe=IntradayTimeframe.ONE_HOUR,
                    interval=interval.value,
                    provider_symbol=record.trading_symbol,
                ),
            ) from error
        return _completed_intraday(
            candles=candles,
            schedule=schedule,
            timeframe=IntradayTimeframe.ONE_HOUR,
            observed_at=observed_at,
            component=MachineFactFailureComponent.PRIOR_SESSION_1H_EVIDENCE,
            provider_symbol=record.trading_symbol,
        )

    def _active_binding(
        self,
        member: ReconciliationMember,
    ) -> ActiveDerivativeBindingArtifact | None:
        if member.exchange != "MCX":
            return None
        resolutions = self._active_derivative_resolutions
        if resolutions is None:
            raise DiscoveryMemberFactError(
                DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE
            )
        outcome = resolutions.for_subject(member.canonical_identity)
        if outcome.binding is not None:
            return outcome.binding
        reason = {
            ActiveDerivativeSelectionFailure.ACTIVE_BINDING_AMBIGUOUS:
                DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_AMBIGUOUS,
            ActiveDerivativeSelectionFailure.PROVIDER_CONTRACT_UNAVAILABLE:
                DiscoveryReason.PROVIDER_CONTRACT_UNAVAILABLE,
            ActiveDerivativeSelectionFailure.CANONICAL_CONTRACT_UNAVAILABLE:
                DiscoveryReason.CANONICAL_DERIVATIVE_CONTRACT_UNAVAILABLE,
        }.get(
            outcome.failure,
            DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE,
        )
        raise DiscoveryMemberFactError(reason)

    def _record(
        self,
        member: ReconciliationMember,
        *,
        active_binding: ActiveDerivativeBindingArtifact | None,
    ) -> InstrumentRecord:
        if active_binding is not None:
            return InstrumentRecord(
                provider="KITE",
                exchange=active_binding.exchange,
                segment=active_binding.segment,
                trading_symbol=active_binding.provider_symbol,
                name=active_binding.provider_contract_family,
                instrument_type=active_binding.provider_instrument_type,
                expiry=active_binding.contract_expiry,
                tick_size=active_binding.tick_size,
                lot_size=active_binding.lot_size,
            )
        if member.provider_symbol is None:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
                _failure_detail(
                    MachineFactFailureStage.PROVIDER_SYMBOL_BINDING,
                    MachineFactFailureComponent.PROVIDER_SYMBOL,
                    MachineFactFailureAvailability.UNAVAILABLE,
                    "PROVIDER_SYMBOL_UNAVAILABLE",
                    provider_symbol=member.provider_symbol,
                ),
            )
        if member.exchange not in self._records:
            try:
                self._records[member.exchange] = self._lease.instrument_records(
                    member.exchange
                )
            except Exception as error:
                raise DiscoveryMemberFactError(
                    DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
                    _failure_detail(
                        MachineFactFailureStage.PROVIDER_SYMBOL_BINDING,
                        MachineFactFailureComponent.PROVIDER_SYMBOL,
                        MachineFactFailureAvailability.UNAVAILABLE,
                        "PROVIDER_INSTRUMENT_ACQUISITION_FAILED",
                        provider_symbol=member.provider_symbol,
                    ),
                ) from error
        matches = tuple(
            item for item in self._records[member.exchange]
            if item.provider == "KITE"
            and item.exchange == member.exchange
            and item.trading_symbol == member.provider_symbol
        )
        if len(matches) != 1:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
                _failure_detail(
                    MachineFactFailureStage.PROVIDER_SYMBOL_BINDING,
                    MachineFactFailureComponent.PROVIDER_SYMBOL,
                    (
                        MachineFactFailureAvailability.UNAVAILABLE
                        if not matches
                        else MachineFactFailureAvailability.CONFLICTING
                    ),
                    (
                        "PROVIDER_RECORD_UNAVAILABLE"
                        if not matches
                        else "PROVIDER_RECORD_AMBIGUOUS"
                    ),
                    provider_symbol=member.provider_symbol,
                ),
            )
        return matches[0]

    def _binding_schedule(
        self,
        binding: ActiveDerivativeBindingArtifact,
        observed_at: datetime,
    ) -> MarketDaySchedule:
        local_date = observed_at.astimezone(ZoneInfo("Asia/Kolkata")).date()
        profile = self._calendar.mcx_contract_session_profile(
            contract_family=binding.provider_contract_family,
            contract_expiry=binding.contract_expiry,
            trading_date=local_date,
            observed_at=observed_at,
        )
        if (
            not profile.contract_eligible
            or profile.continuous_trading is None
            or profile.publication_identity
            != binding.domain008_publication_identity
            or profile.publication_version
            != binding.domain008_publication_version
            or profile.publication_sha256
            != binding.domain008_publication_sha256
            or profile.continuous_trading.session_identity
            != binding.domain008_session_identity
        ):
            raise DiscoveryMemberFactError(
                DiscoveryReason.ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE
            )
        return _market_day_schedule(profile.continuous_trading)

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
            raise DiscoveryMemberFactError(
                DiscoveryReason.MARKET_SESSION_UNAVAILABLE,
                _failure_detail(
                    MachineFactFailureStage.SCHEDULE_SESSION_BINDING,
                    MachineFactFailureComponent.MARKET_SESSION,
                    MachineFactFailureAvailability.UNAVAILABLE,
                    "ANALYSIS_BOUNDARY_OUTSIDE_SESSION",
                    timeframe=timeframe,
                ),
            )
        component = _component_for(timeframe)
        interval = _interval_or_failure(timeframe, component)
        self._historical_requests += 1
        try:
            candles = tuple(self._lease.historical_candles(HistoricalCandleRequest(
                instrument=record,
                start=start,
                end=end,
                interval=interval,
            )))
        except Exception as error:
            raise DiscoveryMemberFactError(
                DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
                _failure_detail(
                    MachineFactFailureStage.CANDLE_ACQUISITION,
                    component,
                    MachineFactFailureAvailability.UNAVAILABLE,
                    "PROVIDER_CANDLE_ACQUISITION_FAILED",
                    timeframe=timeframe,
                    interval=interval.value,
                    provider_symbol=record.trading_symbol,
                ),
            ) from error
        if timeframe is IntradayTimeframe.DAILY:
            selected = tuple(
                item for item in candles
                if item.timestamp.astimezone(ZoneInfo(previous.timezone)).date()
                == previous.trading_date
            )
            if len(selected) != 1:
                raise DiscoveryMemberFactError(
                    DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
                    _failure_detail(
                        MachineFactFailureStage.REQUIRED_TIMEFRAME_ABSENCE,
                        component,
                        MachineFactFailureAvailability.INCOMPLETE,
                        "REQUIRED_DAILY_CANDLE_MISSING",
                        timeframe=timeframe,
                        interval=interval.value,
                        provider_symbol=record.trading_symbol,
                    ),
                )
            return selected
        return _completed_intraday(
            candles=candles,
            schedule=schedule,
            timeframe=timeframe,
            observed_at=observed_at,
            allow_domain008_empty=(
                self._produce_probables_v2_facts
                and timeframe is IntradayTimeframe.ONE_HOUR
            ),
            component=component,
            provider_symbol=record.trading_symbol,
        )


def _component_for(timeframe: IntradayTimeframe) -> MachineFactFailureComponent:
    return {
        IntradayTimeframe.DAILY: (
            MachineFactFailureComponent.PREVIOUS_COMPLETED_DAILY_EVIDENCE
        ),
        IntradayTimeframe.ONE_HOUR: (
            MachineFactFailureComponent.CURRENT_SESSION_1H_EVIDENCE
        ),
        IntradayTimeframe.FIFTEEN_MINUTES: (
            MachineFactFailureComponent.CURRENT_OPENING_15M_EVIDENCE
        ),
        IntradayTimeframe.FIVE_MINUTES: (
            MachineFactFailureComponent.CURRENT_CONSTITUENT_5M_EVIDENCE
        ),
    }[timeframe]


def _interval_or_failure(
    timeframe: IntradayTimeframe,
    component: MachineFactFailureComponent,
):  # type: ignore[no-untyped-def]
    try:
        return provider_interval(timeframe)
    except Exception as error:
        raise DiscoveryMemberFactError(
            DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
            _failure_detail(
                MachineFactFailureStage.INTERVAL_SELECTION,
                component,
                MachineFactFailureAvailability.UNAVAILABLE,
                "PROVIDER_INTERVAL_UNAVAILABLE",
                timeframe=timeframe,
            ),
        ) from error


def _failure_detail(
    stage: MachineFactFailureStage,
    component: MachineFactFailureComponent,
    availability: MachineFactFailureAvailability,
    code: str,
    *,
    timeframe: IntradayTimeframe | None = None,
    interval: str | None = None,
    provider_symbol: str | None = None,
) -> MachineFactFailureDetail:
    return MachineFactFailureDetail(
        stage=stage,
        component=component,
        required_timeframe=timeframe,
        expected_candle_interval=interval,
        availability_failure=availability,
        sanitized_failure_code=code,
        provider_symbol_binding=provider_symbol,
    )


def _completed_intraday(
    *,
    candles: tuple[HistoricalCandle, ...],
    schedule: MarketDaySchedule,
    timeframe: IntradayTimeframe,
    observed_at: datetime,
    allow_domain008_empty: bool = False,
    component: MachineFactFailureComponent | None = None,
    provider_symbol: str | None = None,
) -> tuple[HistoricalCandle, ...]:
    component = component or _component_for(timeframe)
    interval = _interval_or_failure(timeframe, component)
    if type(allow_domain008_empty) is not bool:
        raise DiscoveryMemberFactError(
            DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
            _failure_detail(
                MachineFactFailureStage.COMPLETION_VALIDATION,
                component,
                MachineFactFailureAvailability.INVALID,
                "COMPLETION_POLICY_INVALID",
                timeframe=timeframe,
                interval=interval.value,
                provider_symbol=provider_symbol,
            ),
        )
    if any(
        current.timestamp <= previous.timestamp
        for previous, current in zip(candles, candles[1:])
    ):
        raise DiscoveryMemberFactError(
            DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
            _failure_detail(
                MachineFactFailureStage.COMPLETION_VALIDATION,
                component,
                MachineFactFailureAvailability.INVALID,
                "CANDLE_TIMESTAMP_ORDER_INVALID",
                timeframe=timeframe,
                interval=interval.value,
                provider_symbol=provider_symbol,
            ),
        )
    expected = expected_candle_boundaries(schedule, timeframe)
    eligible = tuple(
        item for item in expected
        if item.end <= observed_at.astimezone(item.end.tzinfo)
    )
    supplied = {item.timestamp: item for item in candles}
    if len(supplied) != len(candles):
        raise DiscoveryMemberFactError(
            DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
            _failure_detail(
                MachineFactFailureStage.COMPLETION_VALIDATION,
                component,
                MachineFactFailureAvailability.CONFLICTING,
                "CANDLE_TIMESTAMP_DUPLICATE",
                timeframe=timeframe,
                interval=interval.value,
                provider_symbol=provider_symbol,
            ),
        )
    completed = tuple(supplied[item.start] for item in eligible if item.start in supplied)
    expected_starts = {item.start for item in expected}
    if (
        (not eligible and not allow_domain008_empty)
        or len(completed) != len(eligible)
        or any(item.timestamp not in expected_starts for item in candles)
    ):
        raise DiscoveryMemberFactError(
            DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE,
            _failure_detail(
                (
                    MachineFactFailureStage.REQUIRED_TIMEFRAME_ABSENCE
                    if not eligible or len(completed) != len(eligible)
                    else MachineFactFailureStage.COMPLETION_VALIDATION
                ),
                component,
                (
                    MachineFactFailureAvailability.NOT_COMPLETED
                    if not eligible or len(completed) != len(eligible)
                    else MachineFactFailureAvailability.INVALID
                ),
                (
                    "NO_COMPLETED_CANDLE_BOUNDARY"
                    if not eligible
                    else "COMPLETED_CANDLE_MISSING"
                    if len(completed) != len(eligible)
                    else "CANDLE_BOUNDARY_UNEXPECTED"
                ),
                timeframe=timeframe,
                interval=interval.value,
                provider_symbol=provider_symbol,
            ),
        )
    return completed


def governed_market_session_identities(
    *,
    calendar_publisher: MarketCalendarPublisher,
    reconciliation: ReconciliationPublication,
    observed_at: datetime,
    active_derivative_resolutions: ActiveDerivativeResolutionSet | None = None,
) -> tuple[str, str]:
    """Bind one operation to all governed subject-scoped DOMAIN-008 sessions."""

    if (
        type(calendar_publisher) is not MarketCalendarPublisher
        or type(reconciliation) is not ReconciliationPublication
        or (
            active_derivative_resolutions is not None
            and type(active_derivative_resolutions)
            is not ActiveDerivativeResolutionSet
        )
        or not isinstance(observed_at, datetime)
        or observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise ValueError("DISCOVERY_MARKET_SESSION_REQUEST_INVALID")
    local = observed_at.astimezone(ZoneInfo("Asia/Kolkata"))
    sessions: list[tuple[object, ...]] = []
    for member in reconciliation.members:
        active_binding = None
        if member.exchange == "MCX" and active_derivative_resolutions is not None:
            outcome = active_derivative_resolutions.for_subject(
                member.canonical_identity
            )
            active_binding = outcome.binding
        if (
            member.dimensions.machine_fact_consumability is not Availability.AVAILABLE
            and active_binding is None
        ):
            continue
        source = CurrentMarketCalendarScheduleSource(
            calendar_publisher,
            observed_at=observed_at,
            canonical_instrument_id=member.canonical_identity,
        )
        if active_binding is None:
            schedule = source.schedule_for(member.exchange, local.date())
        else:
            profile = calendar_publisher.mcx_contract_session_profile(
                contract_family=active_binding.provider_contract_family,
                contract_expiry=active_binding.contract_expiry,
                trading_date=local.date(),
                observed_at=observed_at,
            )
            schedule = (
                None
                if not profile.contract_eligible
                or profile.continuous_trading is None
                else _market_day_schedule(profile.continuous_trading)
            )
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


def _market_day_schedule(value: MarketSchedule) -> MarketDaySchedule:
    return MarketDaySchedule(
        exchange=value.exchange,
        trading_date=value.trading_date,
        session_id=value.session_identity,
        timezone=value.timezone,
        status=TradingDayStatus.TRADING,
        windows=tuple(
            MarketWindow(item.window_open, item.window_close)
            for item in value.windows
        ),
        source_identity=value.source_identity,
        source_version=value.calendar_version,
        special_session="EXPIRY" in value.session_type,
    )


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
