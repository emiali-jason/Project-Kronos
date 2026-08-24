"""UX-05/06 application boundary for KR-370 to the Native Trade Window.

This workflow persists the eligibility handoff and exact ready Step-31 record.
It does not derive geometry, Risk, Sponsor decisions, KR-380 outcomes, alerts,
positions, execution, or broker actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Callable

from kronos.instrument.facts import CanonicalInstrumentContext
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState,
    ProviderMarketTick,
    ProviderOrderUpdateEvidence,
)
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalClassification,
)
from kronos.swing.v1.kr370_step31_handoff import (
    Kr370Step31EligibilityHandoff,
    LocalKr370Step31HandoffStore,
    create_kr370_step31_handoff,
)
from kronos.swing.v1.native_trade_construction import (
    AuthoritativePriceEvidence,
    LocalTradePlanStore,
    QualificationCandleEvidence,
    TradeConstructionEvidencePackage,
    TradePlanRecord,
    TradePlanStatus,
    TradeSetupIdentity,
    construct_trade_plan,
    create_trade_construction_evidence_package,
)
from kronos.swing.v1.native_entry_timing import (
    EcpcV2Blocker,
    EcpcV2Outcome,
    Kr380EntryOutcomeV2,
    Kr380V2State,
    LocalKr380V2Store,
    LocalObjectiveModelV1Store,
    LocalPortfolioStateV1Store,
    LocalRiskPermissionV1Store,
    NativeEcpcV2Context,
    ObjectiveModelRecordV1,
    PortfolioExposureFact,
    PortfolioExposureKind,
    PortfolioRuleFact,
    PortfolioStateV1,
    RiskPermissionV1,
    activate_objective_model_v1,
    create_portfolio_state_v1,
    evaluate_kr380_v2,
    evaluate_risk_permission_v1,
    produce_native_ecpc_v2,
)
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.application.swing_visual_v3 import CompletedVisualV3Review
from kronos.application.swing_native_review import NativeReviewWorkflowSnapshot
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecyclePosition,
    TradeClosureRecord,
)
from kronos.swing.v1.native_sponsor_decision import SponsorInitiationResult
from kronos.swing.v1.native_trade_journal import TradeJournalRecord
from kronos.swing.v1.step32 import (
    MonitoringAdmissionContext,
    MonitoringAdmissionRegistry,
    MonitoringObservation,
    MonitoringSubmissionType,
    ObjectiveModelState,
    RiskApproval,
    RiskState,
    build_monitoring_submission,
)


KR380_ENTRY_OUTCOME_V2_CONTRACT_ID = "KRONOS-KR-380-ENTRY-OUTCOME-V2"


class Kr380EntryTimingState(StrEnum):
    NO_TRIGGER = "NO_TRIGGER"
    FORMING = "FORMING"
    LONG_ENTRY_TRIGGERED = "LONG_ENTRY_TRIGGERED"
    SHORT_ENTRY_TRIGGERED = "SHORT_ENTRY_TRIGGERED"
    EXTENDED = "EXTENDED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class GovernedKr380EntryOutcomeReference:
    """Authority-free reference to an already-governed current KR-380 record."""

    entry_outcome_id: str
    native_run_identity: str
    canonical_instrument: str
    trade_plan_id: str
    trade_plan_sha256: str
    risk_result_id: str
    execution_context_identity: str
    monitoring_binding_id: str | None
    state: Kr380EntryTimingState
    occurred_at: datetime
    source_observation_ids: tuple[str, ...]
    source_integrity_sha256: str
    contract_identity: str = KR380_ENTRY_OUTCOME_V2_CONTRACT_ID
    contract_version: str = "2"
    owner_identity: str = "KR-380"
    state_family_identity: str = "KR380_ENTRY_OUTCOME"

    def __post_init__(self) -> None:
        if (
            not all((
                self.entry_outcome_id,
                self.native_run_identity,
                self.canonical_instrument,
                self.trade_plan_id,
                self.risk_result_id,
                self.execution_context_identity,
            ))
            or len(self.trade_plan_sha256) != 64
            or type(self.state) is not Kr380EntryTimingState
            or self.occurred_at.tzinfo is None
            or type(self.source_observation_ids) is not tuple
            or (
                self.state is not Kr380EntryTimingState.NO_TRIGGER
                and not self.monitoring_binding_id
            )
            or (
                self.monitoring_binding_id is not None
                and not self.monitoring_binding_id
            )
            or (
                self.state in {
                    Kr380EntryTimingState.LONG_ENTRY_TRIGGERED,
                    Kr380EntryTimingState.SHORT_ENTRY_TRIGGERED,
                }
                and not self.source_observation_ids
            )
            or len(self.source_integrity_sha256) != 64
            or self.contract_identity != KR380_ENTRY_OUTCOME_V2_CONTRACT_ID
            or self.contract_version != "2"
            or self.owner_identity != "KR-380"
            or self.state_family_identity != "KR380_ENTRY_OUTCOME"
        ):
            raise ValueError("KR380_ENTRY_OUTCOME_REFERENCE_INVALID")


@dataclass(frozen=True, slots=True)
class GovernedModelLifecycleReference:
    """Derivative reference to one existing KR-390 objective-model record."""

    model_trade_id: str
    native_run_identity: str
    canonical_instrument: str
    trade_plan_id: str
    trade_plan_sha256: str
    risk_result_id: str
    entry_outcome_id: str
    state: ObjectiveModelState
    monitoring_state: MonitoringConnectionState
    updated_at: datetime
    source_integrity_sha256: str
    close_reason: str | None = None

    def __post_init__(self) -> None:
        closed = self.state is ObjectiveModelState.CLOSED
        if (
            not all((
                self.model_trade_id,
                self.native_run_identity,
                self.canonical_instrument,
                self.trade_plan_id,
                self.risk_result_id,
                self.entry_outcome_id,
            ))
            or len(self.trade_plan_sha256) != 64
            or type(self.state) is not ObjectiveModelState
            or type(self.monitoring_state) is not MonitoringConnectionState
            or self.updated_at.tzinfo is None
            or len(self.source_integrity_sha256) != 64
            or closed != (self.close_reason is not None)
        ):
            raise ValueError("MODEL_LIFECYCLE_REFERENCE_INVALID")


class TradeWindowState(StrEnum):
    TRADE_CONSTRUCTION_NOT_ELIGIBLE = "TRADE_CONSTRUCTION_NOT_ELIGIBLE"
    CURRENT_TRADE_CONSTRUCTION_UNAVAILABLE = "CURRENT_TRADE_CONSTRUCTION_UNAVAILABLE"
    TRADE_PLAN_UNAVAILABLE = "TRADE_PLAN_UNAVAILABLE"
    TRADE_PLAN_READY = "TRADE_PLAN_READY"


@dataclass(frozen=True, slots=True)
class NativeTradeWindowProjection:
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    kr370_classification: str
    direction: str
    state: TradeWindowState
    reason: str
    handoff: Kr370Step31EligibilityHandoff | None
    trade_plan: TradePlanRecord | None
    risk_state: str = "RISK_UNAVAILABLE"
    risk_reason: str = "RISK EVALUATION NOT AVAILABLE"
    risk_result_id: str | None = None
    sponsor_controls_available: bool = False
    sponsor_decision_state: str = "NO DECISION RECORDED"
    sponsor_decision_id: str | None = None
    kr380_entry_timing_state: str = "NOT ESTABLISHED"
    kr380_entry_outcome_id: str | None = None
    model_lifecycle_state: str = "NOT ESTABLISHED"
    model_trade_id: str | None = None
    model_monitoring_state: str = "NOT ESTABLISHED"
    model_close_reason: str | None = None
    sponsor_position_state: str = "NO SPONSOR POSITION"
    sponsor_position_id: str | None = None
    sponsor_monitoring_state: str = "NOT APPLICABLE"
    sponsor_monitoring_reason: str = "NO ACTIVE SPONSOR POSITION"
    lifecycle_id: str | None = None
    closure_state: str = "OPEN / NOT ESTABLISHED"
    closure_id: str | None = None
    closure_reason: str | None = None
    journal_record_id: str | None = None
    continuity_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ready = self.state is TradeWindowState.TRADE_PLAN_READY
        if (
            not self.native_run_identity
            or not self.canonical_instrument
            or len(self.native_assessment_sha256) != 64
            or not self.kr370_classification
            or self.direction not in {"LONG", "SHORT"}
            or type(self.state) is not TradeWindowState
            or not self.reason
            or (self.handoff is not None and type(self.handoff) is not Kr370Step31EligibilityHandoff)
            or (self.trade_plan is not None and type(self.trade_plan) is not TradePlanRecord)
            or ready != (self.trade_plan is not None)
            or (ready and self.trade_plan.geometry_viability is not TradePlanStatus.TRADE_PLAN_READY)
            or self.risk_state not in {
                "RISK_UNAVAILABLE", "RISK_APPROVED", "RISK_CONSTRAINED", "RISK_REJECTED"
            }
            or (
                self.risk_result_id is not None
                and self.risk_state not in {
                    "RISK_UNAVAILABLE", "RISK_APPROVED",
                    "RISK_CONSTRAINED", "RISK_REJECTED",
                }
            )
            or type(self.sponsor_controls_available) is not bool
            or not self.sponsor_decision_state
            or (self.sponsor_decision_id is None) != (
                self.sponsor_decision_state == "NO DECISION RECORDED"
            )
            or not self.kr380_entry_timing_state
            or (self.kr380_entry_outcome_id is None) != (
                self.kr380_entry_timing_state == "NOT ESTABLISHED"
            )
            or not self.model_lifecycle_state
            or (self.model_trade_id is None) != (
                self.model_lifecycle_state == "NOT ESTABLISHED"
            )
            or not self.model_monitoring_state
            or (self.model_trade_id is None) != (
                self.model_monitoring_state == "NOT ESTABLISHED"
            )
            or (self.model_close_reason is not None and self.model_trade_id is None)
            or (
                (self.model_lifecycle_state == ObjectiveModelState.CLOSED.value)
                != (self.model_close_reason is not None)
            )
            or not self.sponsor_position_state
            or (self.sponsor_position_id is None) != (
                self.sponsor_position_state == "NO SPONSOR POSITION"
            )
            or (self.lifecycle_id is not None and self.sponsor_position_id is None)
            or not self.sponsor_monitoring_state
            or not self.sponsor_monitoring_reason
            or not self.closure_state
            or (self.closure_id is None) != (self.closure_state == "OPEN / NOT ESTABLISHED")
            or (self.closure_id is None) != (self.closure_reason is None)
            or type(self.continuity_warnings) is not tuple
        ):
            raise ValueError("NATIVE_TRADE_WINDOW_PROJECTION_INVALID")


class SwingTradeWindowWorkflow:
    """Coordinate exact handoff and the existing Step-31 engine only."""

    def __init__(
        self,
        handoff_store: LocalKr370Step31HandoffStore,
        trade_plan_store: LocalTradePlanStore,
        portfolio_store: LocalPortfolioStateV1Store | None = None,
        risk_store: LocalRiskPermissionV1Store | None = None,
        kr380_store: LocalKr380V2Store | None = None,
        objective_model_store: LocalObjectiveModelV1Store | None = None,
    ) -> None:
        if (
            type(handoff_store) is not LocalKr370Step31HandoffStore
            or type(trade_plan_store) is not LocalTradePlanStore
            or (
                portfolio_store is not None
                and type(portfolio_store) is not LocalPortfolioStateV1Store
            )
            or (
                risk_store is not None
                and type(risk_store) is not LocalRiskPermissionV1Store
            )
            or (
                kr380_store is not None
                and type(kr380_store) is not LocalKr380V2Store
            )
            or (
                objective_model_store is not None
                and type(objective_model_store) is not LocalObjectiveModelV1Store
            )
        ):
            raise TypeError("SWING_TRADE_WINDOW_STORE_INVALID")
        self._handoff_store = handoff_store
        self._trade_plan_store = trade_plan_store
        self._portfolio_store = portfolio_store
        self._risk_store = risk_store
        self._kr380_store = kr380_store
        self._objective_model_store = objective_model_store
        self._portfolio_state: PortfolioStateV1 | None = None
        self._shared_monitoring_hub: SharedSwingMonitoringHub | None = None
        self._monitoring_registrations: dict[str, object] = {}
        self._monitoring_consumers: dict[str, _Kr380SharedMonitoringConsumer] = {}
        self._completed: dict[tuple[str, str], CompletedVisualV3Review] = {}
        self._handoffs: dict[tuple[str, str], Kr370Step31EligibilityHandoff] = {}
        self._plans: dict[tuple[str, str], TradePlanRecord] = {}
        self._failures: dict[tuple[str, str], str] = {}
        self._risks: dict[str, RiskApproval | RiskPermissionV1] = {}
        self._production_risks: dict[str, RiskPermissionV1] = {}
        self._sponsor: dict[str, SponsorInitiationResult] = {}
        self._kr380: dict[str, GovernedKr380EntryOutcomeReference] = {}
        self._production_kr380: dict[str, GovernedKr380EntryOutcomeReference] = {}
        self._models: dict[str, GovernedModelLifecycleReference] = {}
        self._production_models: dict[str, GovernedModelLifecycleReference] = {}
        self._positions: dict[str, ActiveLifecyclePosition] = {}
        self._closures: dict[str, TradeClosureRecord] = {}
        self._journals: dict[str, TradeJournalRecord] = {}
        self._downstream_warnings: dict[str, tuple[str, ...]] = {}
        self._sponsor_controls_ready: set[str] = set()
        self._sponsor_monitoring_position_ids: set[str] = set()

    def set_shared_monitoring_hub(self, hub: SharedSwingMonitoringHub) -> None:
        """Bind the one existing factual Swing monitoring transport."""

        if type(hub) is not SharedSwingMonitoringHub:
            raise TypeError("KR380_SHARED_MONITORING_HUB_INVALID")
        self._shared_monitoring_hub = hub

    @property
    def shared_monitoring_hub(self) -> SharedSwingMonitoringHub | None:
        return self._shared_monitoring_hub

    @property
    def active_monitoring_count(self) -> int:
        return len(self._monitoring_registrations)

    def start_current_entry_monitoring(
        self,
        run_identity: str,
        canonical_instrument: str,
        *,
        capability: object,
        instrument: InstrumentRecord,
        session_identity: str,
        observation_boundary: datetime,
        ecpc_outcome: EcpcV2Outcome,
        ecpc_blockers: tuple[EcpcV2Blocker, ...],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> str:
        """Attach KR-380 to the existing shared factual monitoring session."""

        hub = self._shared_monitoring_hub
        if hub is None:
            raise ValueError("KR380_SHARED_MONITORING_HUB_UNAVAILABLE")
        if not callable(clock):
            raise TypeError("KR380_MONITORING_CLOCK_INVALID")
        key = (run_identity, canonical_instrument)
        completed = self._completed.get(key)
        handoff = self._handoffs.get(key)
        plan = self._plans.get(key)
        if (
            completed is None
            or completed.promotion is None
            or handoff is None
            or plan is None
            or type(instrument) is not InstrumentRecord
            or (
                instrument.name != canonical_instrument
                and instrument.trading_symbol != canonical_instrument
            )
        ):
            raise ValueError("CURRENT_NATIVE_ENTRY_MONITORING_INPUT_INVALID")
        current_outcome = self._production_kr380.get(plan.trade_plan_id)
        if current_outcome is not None and current_outcome.state in {
            Kr380EntryTimingState.LONG_ENTRY_TRIGGERED,
            Kr380EntryTimingState.SHORT_ENTRY_TRIGGERED,
            Kr380EntryTimingState.EXTENDED,
            Kr380EntryTimingState.FAILED,
        }:
            if current_outcome.monitoring_binding_id is None:
                raise ValueError("CURRENT_NATIVE_ENTRY_MONITORING_TERMINAL")
            return current_outcome.monitoring_binding_id
        if plan.trade_plan_id in self._monitoring_registrations:
            return self._monitoring_consumers[plan.trade_plan_id].binding_id
        risk = self._evaluate_current_risk(plan, handoff, completed, clock())
        if not risk.permits_entry:
            raise ValueError("CURRENT_NATIVE_ENTRY_MONITORING_RISK_NOT_PERMITTED")
        binding = "KR380-MONITORING-" + sha256(
            f"{plan.trade_plan_id}:{session_identity}".encode("utf-8")
        ).hexdigest()
        context = produce_native_ecpc_v2(
            plan,
            risk,
            monitoring_binding_id=binding,
            session_identity=session_identity,
            observation_boundary=observation_boundary,
            outcome=ecpc_outcome,
            blockers=ecpc_blockers,
        )
        consumer = _Kr380SharedMonitoringConsumer(
            self, plan, risk, context, instrument, clock
        )
        registration = hub.open(capability, consumer)
        registration.subscribe((instrument,))
        registration.connect()
        self._monitoring_consumers[plan.trade_plan_id] = consumer
        self._monitoring_registrations[plan.trade_plan_id] = registration
        return binding

    def close_monitoring(self) -> None:
        registrations = tuple(self._monitoring_registrations.values())
        self._monitoring_registrations.clear()
        self._monitoring_consumers.clear()
        for registration in registrations:
            registration.disconnect()

    def publish_portfolio_state(
        self,
        *,
        cycle_identity: str,
        as_of_boundary: datetime,
        objective_exposures: tuple[PortfolioExposureFact, ...],
        sponsor_exposures: tuple[PortfolioExposureFact, ...],
        rule_facts: tuple[PortfolioRuleFact, ...] = (),
        source_identities: tuple[str, ...],
        sources_complete: bool,
        provenance: tuple[str, ...],
    ) -> PortfolioStateV1:
        """Publish factual Portfolio State; missing sources never mean empty."""

        record = create_portfolio_state_v1(
            cycle_identity=cycle_identity,
            as_of_boundary=as_of_boundary,
            objective_exposures=objective_exposures,
            sponsor_exposures=sponsor_exposures,
            rule_facts=rule_facts,
            source_identities=source_identities,
            sources_complete=sources_complete,
            provenance=provenance,
        )
        if self._portfolio_store is None:
            raise ValueError("PORTFOLIO_STATE_STORE_UNAVAILABLE")
        self._portfolio_store.retain_current(record)
        self._portfolio_state = record
        return record

    def publish_current_portfolio_state(
        self,
        review: NativeReviewWorkflowSnapshot,
        *,
        native_run_identity: str,
        as_of_boundary: datetime,
    ) -> PortfolioStateV1:
        """Publish the approved minimal factual Portfolio State from owned stores."""

        if (
            type(review) is not NativeReviewWorkflowSnapshot
            or review.native_run_identity != native_run_identity
        ):
            raise ValueError("CURRENT_PORTFOLIO_SOURCE_BINDING_INVALID")
        plan_by_id = {item.trade_plan_id: item for item in self._plans.values()}
        objective = tuple(
            PortfolioExposureFact(
                "PORTFOLIO-EXPOSURE-" + sha256(
                    f"OBJECTIVE:{item.model_trade_id}".encode("utf-8")
                ).hexdigest(),
                PortfolioExposureKind.OBJECTIVE_MODEL,
                item.canonical_instrument,
                plan_by_id[item.trade_plan_id].native_direction.value,
                item.model_trade_id,
                item.model_trade_id,
            )
            for item in sorted(
                self._production_models.values(), key=lambda value: value.model_trade_id
            )
            if item.state is ObjectiveModelState.ACTIVE
            and item.trade_plan_id in plan_by_id
        )
        sponsor = tuple(
            PortfolioExposureFact(
                "PORTFOLIO-EXPOSURE-" + sha256(
                    f"SPONSOR:{item.position_id}".encode("utf-8")
                ).hexdigest(),
                (
                    PortfolioExposureKind.SPONSOR_LIVE
                    if item.mode.value == "LIVE"
                    else PortfolioExposureKind.SPONSOR_PAPER
                ),
                item.canonical_instrument,
                item.direction.value,
                item.lifecycle_id,
                item.position_id,
            )
            for item in sorted(
                review.active_lifecycle.active, key=lambda value: value.position_id
            )
        )
        sources = tuple(dict.fromkeys((
            "OBJECTIVE-MODEL-STORE",
            *(item.source_record_identity for item in objective),
            "SPONSOR-POSITION-STORE",
            *(item.source_record_identity for item in sponsor),
        )))
        cycle = "PORTFOLIO-CYCLE-" + sha256(
            f"{native_run_identity}:{'|'.join(sources)}".encode("utf-8")
        ).hexdigest()
        return self.publish_portfolio_state(
            cycle_identity=cycle,
            as_of_boundary=as_of_boundary,
            objective_exposures=objective,
            sponsor_exposures=sponsor,
            source_identities=sources,
            sources_complete=True,
            provenance=(
                native_run_identity,
                "DOMAIN-005",
                "ADR-0013",
                "OBJECTIVE-MODEL-STORE",
                "SPONSOR-POSITION-STORE",
            ),
        )

    def evaluate_current_risk(
        self,
        run_identity: str,
        canonical_instrument: str,
        *,
        evaluated_at: datetime,
    ) -> RiskPermissionV1:
        """Invoke the existing DOMAIN-007 producer for one exact current plan."""

        key = (run_identity, canonical_instrument)
        completed = self._completed.get(key)
        handoff = self._handoffs.get(key)
        plan = self._plans.get(key)
        if completed is None or handoff is None or plan is None:
            raise ValueError("CURRENT_RISK_INPUT_UNAVAILABLE")
        return self._evaluate_current_risk(plan, handoff, completed, evaluated_at)

    def _evaluate_current_risk(
        self,
        plan: TradePlanRecord,
        handoff: Kr370Step31EligibilityHandoff,
        completed: CompletedVisualV3Review,
        evaluated_at: datetime,
    ) -> RiskPermissionV1:
        if completed.promotion is None or self._risk_store is None:
            raise ValueError("CURRENT_RISK_PRODUCER_UNAVAILABLE")
        portfolio = self._portfolio_state
        current = self._production_risks.get(plan.trade_plan_id)
        if (
            current is not None
            and current.trade_plan_sha256 == plan.integrity_hash
            and current.handoff_identity == handoff.handoff_identity
            and current.kr370_source_identity == completed.promotion.integrity_sha256
            and current.portfolio_state_identity
            == (None if portfolio is None else portfolio.portfolio_state_identity)
            and current.current
        ):
            return current
        risk = evaluate_risk_permission_v1(
            plan,
            handoff,
            kr370_source_identity=completed.promotion.integrity_sha256,
            kr370_source_sha256=completed.promotion.integrity_sha256,
            portfolio_state=portfolio,
            current_trade_plan_id=plan.trade_plan_id,
            current_portfolio_cycle_identity=(
                None if portfolio is None else portfolio.cycle_identity
            ),
            evaluated_at=evaluated_at,
        )
        self._risk_store.retain_current(risk)
        self._production_risks[plan.trade_plan_id] = risk
        self._merge_production_records()
        return risk

    def current_operability_inputs(
        self, run_identity: str, canonical_instrument: str
    ) -> tuple[TradePlanRecord, RiskPermissionV1] | None:
        plan = self._plans.get((run_identity, canonical_instrument))
        if plan is None:
            return None
        risk = self._production_risks.get(plan.trade_plan_id)
        return None if risk is None else (plan, risk)

    def mark_sponsor_controls_available(self, trade_plan_id: str) -> None:
        if trade_plan_id not in {item.trade_plan_id for item in self._plans.values()}:
            raise ValueError("SPONSOR_CONTROL_PLAN_UNAVAILABLE")
        self._sponsor_controls_ready.add(trade_plan_id)

    def synchronize_sponsor_monitoring(
        self, active_position_ids: tuple[str, ...]
    ) -> None:
        if type(active_position_ids) is not tuple or any(
            not isinstance(item, str) or not item for item in active_position_ids
        ):
            raise TypeError("SPONSOR_MONITORING_IDENTITIES_INVALID")
        self._sponsor_monitoring_position_ids = set(active_position_ids)

    def restore_current_entry_monitoring(
        self,
        capability: object,
        instrument_resolver: Callable[[object, str, object], InstrumentRecord],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> tuple[str, ...]:
        """Restore current non-terminal KR-380 bindings without re-evaluation."""

        if getattr(capability, "active", False) is not True:
            return ()
        restored: list[str] = []
        for key, plan in sorted(self._plans.items()):
            outcome = self._production_kr380.get(plan.trade_plan_id)
            risk = self._production_risks.get(plan.trade_plan_id)
            completed = self._completed.get(key)
            if (
                outcome is None
                or outcome.state is not Kr380EntryTimingState.FORMING
                or risk is None
                or not risk.permits_entry
                or completed is None
            ):
                continue
            one_hour = completed.mtf_snapshot.instrument(
                plan.canonical_instrument
            ).fact(FactualTimeframe.ONE_HOUR)
            binding = "KR380-MONITORING-" + sha256(
                f"{plan.trade_plan_id}:{one_hour.session_identity}".encode("utf-8")
            ).hexdigest()
            if outcome.monitoring_binding_id != binding:
                raise ValueError("KR380_RESTART_BINDING_INVALID")
            instrument = instrument_resolver(
                capability, plan.canonical_instrument, clock().date()
            )
            self.start_current_entry_monitoring(
                *key,
                capability=capability,
                instrument=instrument,
                session_identity=one_hour.session_identity,
                observation_boundary=one_hour.observation_boundary,
                ecpc_outcome=EcpcV2Outcome.QUALIFIED,
                ecpc_blockers=(),
                clock=clock,
            )
            restored.append(plan.trade_plan_id)
        return tuple(restored)

    def evaluate_current_entry_timing(
        self,
        run_identity: str,
        canonical_instrument: str,
        *,
        session_identity: str,
        observation_boundary: datetime,
        ecpc_outcome: EcpcV2Outcome,
        ecpc_blockers: tuple[EcpcV2Blocker, ...],
        previous: MonitoringObservation | None,
        current: MonitoringObservation | None,
        evaluated_at: datetime,
        monitoring_binding_id: str | None = None,
        monitoring_state: MonitoringConnectionState = MonitoringConnectionState.DISCONNECTED,
    ) -> Kr380EntryOutcomeV2:
        """Evaluate and retain one current V2 outcome from governed facts only."""

        key = (run_identity, canonical_instrument)
        completed = self._completed.get(key)
        handoff = self._handoffs.get(key)
        plan = self._plans.get(key)
        if completed is None or completed.promotion is None or handoff is None or plan is None:
            raise ValueError("CURRENT_NATIVE_ENTRY_TIMING_INPUT_UNAVAILABLE")
        if self._risk_store is None or self._kr380_store is None:
            raise ValueError("CURRENT_NATIVE_ENTRY_TIMING_STORE_UNAVAILABLE")
        promotion = completed.promotion
        risk = self._evaluate_current_risk(plan, handoff, completed, evaluated_at)
        context: NativeEcpcV2Context | None = None
        if risk.permits_entry:
            binding = monitoring_binding_id or (
                "KR380-MONITORING-"
                + sha256(plan.trade_plan_id.encode("utf-8")).hexdigest()
            )
            context = produce_native_ecpc_v2(
                plan,
                risk,
                monitoring_binding_id=binding,
                session_identity=session_identity,
                observation_boundary=observation_boundary,
                outcome=ecpc_outcome,
                blockers=ecpc_blockers,
            )
        outcome = evaluate_kr380_v2(
            plan,
            risk,
            context,
            kr370_source_identity=promotion.integrity_sha256,
            previous=previous,
            current=current,
            evaluated_at=evaluated_at,
        )
        self._retain_production_outcome(plan, outcome, monitoring_state)
        return outcome

    def _retain_production_outcome(
        self,
        plan: TradePlanRecord,
        outcome: Kr380EntryOutcomeV2,
        monitoring_state: MonitoringConnectionState,
    ) -> None:
        if self._kr380_store is None:
            raise ValueError("CURRENT_KR380_STORE_UNAVAILABLE")
        self._kr380_store.retain_current(outcome)
        reference = _kr380_reference(plan, outcome)
        self._production_kr380[plan.trade_plan_id] = reference
        if outcome.state in {
            Kr380V2State.LONG_ENTRY_TRIGGERED,
            Kr380V2State.SHORT_ENTRY_TRIGGERED,
        }:
            if self._objective_model_store is None:
                raise ValueError("CURRENT_OBJECTIVE_MODEL_STORE_UNAVAILABLE")
            model = activate_objective_model_v1(
                plan, outcome, monitoring_state=monitoring_state
            )
            self._objective_model_store.retain_current(model)
            self._production_models[plan.trade_plan_id] = _model_reference(model)
        self._merge_production_records()

    def _restore_production_records(self, plan: TradePlanRecord) -> None:
        risk = None if self._risk_store is None else self._risk_store.load_for_plan(
            plan.trade_plan_id
        )
        portfolio = self._portfolio_state
        portfolio_current = (
            risk is not None
            and portfolio is not None
            and risk.portfolio_state_identity == portfolio.portfolio_state_identity
            and risk.portfolio_state_sha256 == portfolio.integrity_sha256
            and risk.portfolio_cycle_identity == portfolio.cycle_identity
        )
        if (
            risk is not None
            and _risk_binding(plan, risk)
            and (not risk.permits_entry or portfolio_current)
        ):
            self._production_risks[plan.trade_plan_id] = risk
        else:
            risk = None
        outcome = None if self._kr380_store is None else self._kr380_store.load_for_plan(
            plan.trade_plan_id
        )
        risk_state = None if risk is None else risk.state
        if outcome is not None:
            reference = _kr380_reference(plan, outcome)
            if _kr380_binding(
                plan,
                reference,
                None if risk is None else risk.risk_result_id,
                risk_state,
            ):
                self._production_kr380[plan.trade_plan_id] = reference
            else:
                outcome = None
        model = (
            None
            if self._objective_model_store is None
            else self._objective_model_store.load_for_plan(plan.trade_plan_id)
        )
        if model is not None and outcome is not None:
            model_reference = _model_reference(model)
            outcome_reference = self._production_kr380.get(plan.trade_plan_id)
            if _model_binding(
                plan,
                model_reference,
                outcome_reference,
                None if risk is None else risk.risk_result_id,
            ):
                self._production_models[plan.trade_plan_id] = model_reference

    def _merge_production_records(self) -> None:
        # Current production V2 takes precedence over historical/injected fixtures.
        self._risks.update(self._production_risks)
        self._kr380.update(self._production_kr380)
        self._models.update(self._production_models)

    def restore(self, completed: tuple[CompletedVisualV3Review, ...]) -> None:
        """Restore only exact persisted V3.1/KR-370 lineage and ready plans."""

        if type(completed) is not tuple or any(
            type(item) is not CompletedVisualV3Review for item in completed
        ):
            raise TypeError("SWING_TRADE_WINDOW_RESTORE_INVALID")
        self._completed = {
            (item.requirement.native_run_identity, item.requirement.canonical_instrument): item
            for item in completed
        }
        self._handoffs.clear()
        self._plans.clear()
        self._production_risks.clear()
        self._production_kr380.clear()
        self._production_models.clear()
        self._sponsor_controls_ready.clear()
        self._sponsor_monitoring_position_ids.clear()
        self._portfolio_state = (
            None
            if self._portfolio_store is None
            else self._portfolio_store.load_current_state()
        )
        requirements = tuple(item.requirement for item in completed)
        stored_plans = self._trade_plan_store.load_for_requirements(requirements)
        for review in completed:
            promotion = review.promotion
            if promotion is None:
                continue
            key = (promotion.run_identity, promotion.canonical_instrument)
            handoff = self._handoff_store.load_exact(
                promotion.run_identity,
                promotion.canonical_instrument,
                promotion.native_assessment_sha256,
                promotion.integrity_sha256,
            )
            if handoff is None:
                continue
            if not _exact_binding(review, handoff):
                raise ValueError("SWING_TRADE_WINDOW_RESTORE_BINDING_INVALID")
            self._handoffs[key] = handoff
            matches = tuple(
                plan for plan in stored_plans
                if plan.native_run_identity == promotion.run_identity
                and plan.canonical_instrument == promotion.canonical_instrument
                and plan.native_assessment_sha256 == promotion.native_assessment_sha256
                and plan.readiness_record_sha256 == handoff.v3_readiness_sha256
                and handoff.handoff_identity in plan.provenance
                and handoff.integrity_sha256 in plan.provenance
            )
            if len(matches) > 1:
                raise ValueError("SWING_TRADE_WINDOW_PLAN_RESTORE_AMBIGUOUS")
            if matches:
                plan = matches[0]
                self._plans[key] = plan
                self._restore_production_records(plan)
        self._merge_production_records()

    def synchronize_downstream(
        self,
        review: NativeReviewWorkflowSnapshot,
        *,
        kr380_outcomes: tuple[GovernedKr380EntryOutcomeReference, ...] = (),
        model_lifecycles: tuple[GovernedModelLifecycleReference, ...] = (),
    ) -> None:
        """Rebuild a derivative continuity view from authoritative records only."""

        if (
            type(review) is not NativeReviewWorkflowSnapshot
            or any(type(item) is not GovernedKr380EntryOutcomeReference for item in kr380_outcomes)
            or any(type(item) is not GovernedModelLifecycleReference for item in model_lifecycles)
        ):
            raise TypeError("SWING_TRADE_WINDOW_DOWNSTREAM_INVALID")
        self._risks = {item.candidate_id: item for item in review.risk_records}
        self._sponsor = {
            item.decision.trade_plan_id: item
            for item in review.sponsor_initiations
            if item.decision is not None
        }
        self._positions = {
            item.trade_plan_id: item for item in review.active_lifecycle.positions
        }
        self._closures = {
            item.trade_plan_id: item for item in review.active_lifecycle.closures
        }
        self._journals = {
            item.trade_plan_id: item for item in review.trade_journal.records
        }
        self._kr380 = {item.trade_plan_id: item for item in kr380_outcomes}
        self._models = {item.trade_plan_id: item for item in model_lifecycles}
        self._merge_production_records()
        self._downstream_warnings.clear()
        for plan in self._plans.values():
            warnings: list[str] = []
            risk = self._risks.get(plan.trade_plan_id)
            sponsor = self._sponsor.get(plan.trade_plan_id)
            if sponsor is not None and not _sponsor_binding(plan, sponsor):
                warnings.append("STALE_OR_MISMATCHED_SPONSOR_DECISION")
                self._sponsor.pop(plan.trade_plan_id, None)
                sponsor = None
            if risk is not None and not _risk_binding(plan, risk):
                warnings.append("STALE_OR_MISMATCHED_RISK_RECORD")
                self._risks.pop(plan.trade_plan_id, None)
                risk = None
            if risk is None and sponsor is not None and sponsor.decision is not None:
                # The persisted decision retains the exact Risk identity/state/hash.
                risk_id = sponsor.decision.risk_id
                risk_state = sponsor.decision.risk_state
            elif risk is not None:
                risk_id = risk.risk_result_id
                risk_state = risk.state
            else:
                risk_id = None
                risk_state = None
            outcome = self._kr380.get(plan.trade_plan_id)
            if outcome is not None and not _kr380_binding(plan, outcome, risk_id, risk_state):
                warnings.append("STALE_OR_MISMATCHED_KR380_ENTRY_OUTCOME")
                self._kr380.pop(plan.trade_plan_id, None)
                outcome = None
            model = self._models.get(plan.trade_plan_id)
            if model is not None and not _model_binding(plan, model, outcome, risk_id):
                warnings.append("STALE_OR_MISMATCHED_MODEL_LIFECYCLE")
                self._models.pop(plan.trade_plan_id, None)
            position = self._positions.get(plan.trade_plan_id)
            if position is not None and not _position_binding(plan, sponsor, position):
                warnings.append("STALE_OR_MISMATCHED_SPONSOR_POSITION")
                self._positions.pop(plan.trade_plan_id, None)
                position = None
            closure = self._closures.get(plan.trade_plan_id)
            if closure is not None and not _closure_binding(plan, sponsor, position, closure):
                warnings.append("STALE_OR_MISMATCHED_TRADE_CLOSURE")
                self._closures.pop(plan.trade_plan_id, None)
                closure = None
            journal = self._journals.get(plan.trade_plan_id)
            if journal is not None and not _journal_binding(plan, sponsor, position, closure, journal):
                warnings.append("STALE_OR_MISMATCHED_STEP33_JOURNAL")
                self._journals.pop(plan.trade_plan_id, None)
            if warnings:
                self._downstream_warnings[plan.trade_plan_id] = tuple(warnings)

    def construct(
        self,
        completed: CompletedVisualV3Review,
        evidence: TradeConstructionEvidencePackage,
        execution_context: CanonicalInstrumentContext,
        *,
        current_run_identity: str,
        current_analysis_boundary: datetime,
        created_at: datetime,
    ) -> NativeTradeWindowProjection:
        """Invoke the existing Step-31 geometry engine after exact eligibility."""

        promotion = completed.promotion
        if promotion is None:
            raise ValueError("KR370_PROMOTION_UNAVAILABLE")
        handoff = create_kr370_step31_handoff(
            completed.requirement,
            completed.readiness,
            promotion,
            current_run_identity=current_run_identity,
            current_analysis_boundary=current_analysis_boundary,
            created_at=created_at,
        )
        self._handoff_store.retain(handoff)
        plan = construct_trade_plan(
            completed.requirement,
            handoff,
            evidence,
            execution_context,
            created_at=created_at,
        )
        key = (handoff.native_run_identity, handoff.canonical_instrument)
        self._completed[key] = completed
        self._handoffs[key] = handoff
        if plan.geometry_viability is TradePlanStatus.TRADE_PLAN_READY:
            self._trade_plan_store.retain(plan)
            self._plans[key] = plan
            self._failures.pop(key, None)
        else:
            self._plans.pop(key, None)
            self._failures[key] = plan.unavailable_reason.value
        return self.project(*key)

    def project(
        self, run_identity: str, canonical_instrument: str
    ) -> NativeTradeWindowProjection | None:
        completed = self._completed.get((run_identity, canonical_instrument))
        if completed is None or completed.promotion is None:
            return None
        promotion = completed.promotion
        base = dict(
            native_run_identity=run_identity,
            canonical_instrument=canonical_instrument,
            native_assessment_sha256=promotion.native_assessment_sha256,
            kr370_classification=promotion.classification.value,
            direction=promotion.direction.value,
        )
        if promotion.not_evaluable_reason is not None:
            return NativeTradeWindowProjection(
                **base,
                state=TradeWindowState.TRADE_CONSTRUCTION_NOT_ELIGIBLE,
                reason="KR370_NOT_EVALUABLE",
                handoff=None,
                trade_plan=None,
            )
        if promotion.classification not in {
            Kr370AnalyticalClassification.BUY_NOW,
            Kr370AnalyticalClassification.SELL_NOW,
        }:
            return NativeTradeWindowProjection(
                **base,
                state=TradeWindowState.TRADE_CONSTRUCTION_NOT_ELIGIBLE,
                reason="KR370_CLASSIFICATION_NOT_NOW",
                handoff=None,
                trade_plan=None,
            )
        key = (run_identity, canonical_instrument)
        handoff = self._handoffs.get(key)
        if handoff is not None and not _exact_binding(completed, handoff):
            return NativeTradeWindowProjection(
                **base,
                state=TradeWindowState.CURRENT_TRADE_CONSTRUCTION_UNAVAILABLE,
                reason="STALE_OR_MISMATCHED_KR370_HANDOFF",
                handoff=None,
                trade_plan=None,
            )
        plan = self._plans.get(key)
        if plan is None:
            return NativeTradeWindowProjection(
                **base,
                state=TradeWindowState.TRADE_PLAN_UNAVAILABLE,
                reason=self._failures.get(key, "STEP31_EVALUATION_NOT_COMPLETED"),
                handoff=handoff,
                trade_plan=None,
            )
        return NativeTradeWindowProjection(
            **base,
            state=TradeWindowState.TRADE_PLAN_READY,
            reason="EXACT_PERSISTED_STEP31_GEOMETRY_AVAILABLE",
            handoff=handoff,
            trade_plan=plan,
            **self._downstream_projection(plan),
        )

    def _downstream_projection(self, plan: TradePlanRecord) -> dict[str, object]:
        risk = self._risks.get(plan.trade_plan_id)
        sponsor = self._sponsor.get(plan.trade_plan_id)
        decision = sponsor.decision if sponsor is not None else None
        risk_state = (
            risk.state.value
            if risk is not None
            else decision.risk_state.value if decision is not None
            else "RISK_UNAVAILABLE"
        )
        risk_id = (
            risk.risk_result_id
            if risk is not None
            else decision.risk_id if decision is not None
            else None
        )
        risk_reason = (
            " · ".join(risk.reason_codes)
            if isinstance(risk, RiskPermissionV1)
            else risk.reason
            if isinstance(risk, RiskApproval)
            else "PERSISTED SPONSOR DECISION RISK BINDING"
            if decision is not None
            else "RISK EVALUATION NOT AVAILABLE"
        )
        outcome = self._kr380.get(plan.trade_plan_id)
        model = self._models.get(plan.trade_plan_id)
        position = self._positions.get(plan.trade_plan_id)
        closure = self._closures.get(plan.trade_plan_id)
        journal = self._journals.get(plan.trade_plan_id)
        monitoring_active = (
            position is not None
            and position.position_id in self._sponsor_monitoring_position_ids
        )
        sponsor_state = (
            "NO DECISION RECORDED"
            if decision is None
            else f"{decision.decision.value} · {sponsor.state.value}"
        )
        timing_state = (
            "NOT ESTABLISHED" if outcome is None else outcome.state.value
        )
        model_state = "NOT ESTABLISHED" if model is None else model.state.value
        position_state = (
            "NO SPONSOR POSITION" if position is None
            else f"{position.mode.value} · {position.state.value}"
        )
        closure_state = (
            "OPEN / NOT ESTABLISHED" if closure is None else "CLOSED"
        )
        return {
            "risk_state": risk_state,
            "risk_reason": risk_reason,
            "risk_result_id": risk_id,
            "sponsor_controls_available": (
                plan.trade_plan_id in self._sponsor_controls_ready
                and risk is not None
                and risk.permits_entry
                and decision is None
            ),
            "sponsor_decision_state": sponsor_state,
            "sponsor_decision_id": None if decision is None else decision.decision_id,
            "kr380_entry_timing_state": timing_state,
            "kr380_entry_outcome_id": (
                None if outcome is None else outcome.entry_outcome_id
            ),
            "model_lifecycle_state": model_state,
            "model_trade_id": None if model is None else model.model_trade_id,
            "model_monitoring_state": (
                "NOT ESTABLISHED" if model is None else model.monitoring_state.value
            ),
            "model_close_reason": None if model is None else model.close_reason,
            "sponsor_position_state": position_state,
            "sponsor_position_id": None if position is None else position.position_id,
            "sponsor_monitoring_state": (
                "NOT APPLICABLE"
                if position is None
                else "LIVE MONITORING · SL + TARGET"
                if monitoring_active
                else "MONITORING NOT ACTIVE"
            ),
            "sponsor_monitoring_reason": (
                "NO ACTIVE SPONSOR POSITION"
                if position is None
                else "SHARED HUB REGISTRATION ACTIVE"
                if monitoring_active
                else "ACTIVE MONITORING REGISTRATION UNAVAILABLE"
            ),
            "lifecycle_id": None if position is None else position.lifecycle_id,
            "closure_state": closure_state,
            "closure_id": None if closure is None else closure.closure_id,
            "closure_reason": None if closure is None else closure.exit_reason.value,
            "journal_record_id": (
                None if journal is None else journal.journal_record_id
            ),
            "continuity_warnings": self._downstream_warnings.get(
                plan.trade_plan_id, ()
            ),
        }

    def projections(self) -> tuple[NativeTradeWindowProjection, ...]:
        values = []
        for key in sorted(self._completed):
            projection = self.project(*key)
            if projection is not None:
                values.append(projection)
        return tuple(values)


def build_current_trade_construction_evidence(
    completed: CompletedVisualV3Review,
) -> TradeConstructionEvidencePackage:
    """Compose Step-31 inputs from immutable governed facts; derive no geometry."""

    if type(completed) is not CompletedVisualV3Review or completed.promotion is None:
        raise ValueError("CURRENT_TRADE_CONSTRUCTION_SOURCE_INVALID")
    thesis = completed.requirement.thesis
    facts = completed.mtf_snapshot.instrument(thesis.canonical_instrument)
    four_hour = facts.fact(FactualTimeframe.FOUR_HOUR)
    radius_two = next(
        item for item in four_hour.structural_measurements if item.radius == 2
    )

    def digest(*values: object) -> str:
        return sha256("|".join(str(value) for value in values).encode("utf-8")).hexdigest()

    qualification_identity = (
        f"STEP31-QUALIFICATION:{thesis.canonical_instrument}:"
        f"{four_hour.observation_boundary.isoformat()}"
    )
    qualification = QualificationCandleEvidence(
        qualification_identity,
        digest(qualification_identity, four_hour.high, four_hour.low),
        Decimal(str(four_hour.high)),
        Decimal(str(four_hour.low)),
        four_hour.observation_boundary,
        True,
        "KITE_NORMALIZED_HISTORICAL:COMPLETED_4H_QUALIFICATION_CANDLE",
        tuple(dict.fromkeys((*four_hour.provenance, "DOMAIN-008"))),
    )

    def price(identity: str, value: float, boundary: datetime, source: str):
        return AuthoritativePriceEvidence(
            identity,
            digest(identity, value, boundary.isoformat()),
            Decimal(str(value)),
            boundary,
            source,
            tuple(dict.fromkeys((*four_hour.provenance, "DOMAIN-008"))),
        )

    anchor = price(
        f"STEP31-ANCHOR:{thesis.operative_anchor_identity}:"
        f"{thesis.operative_anchor_boundary.isoformat()}",
        thesis.operative_anchor_price,
        thesis.operative_anchor_boundary,
        "KITE_NORMALIZED_HISTORICAL:NATIVE_OPERATIVE_ANCHOR",
    )
    prior_high = (
        None
        if not radius_two.swing_highs
        else price(
            f"STEP31-PRIOR-HIGH:{radius_two.swing_highs[-1].timestamp.isoformat()}",
            radius_two.swing_highs[-1].value,
            radius_two.swing_highs[-1].timestamp,
            "KITE_NORMALIZED_HISTORICAL:COMPLETED_4H_DIRECTIONAL_SWING_HIGH",
        )
    )
    prior_low = (
        None
        if not radius_two.swing_lows
        else price(
            f"STEP31-PRIOR-LOW:{radius_two.swing_lows[-1].timestamp.isoformat()}",
            radius_two.swing_lows[-1].value,
            radius_two.swing_lows[-1].timestamp,
            "KITE_NORMALIZED_HISTORICAL:COMPLETED_4H_DIRECTIONAL_SWING_LOW",
        )
    )
    package_identity = "STEP31-CURRENT-PACKAGE-" + digest(
        thesis.native_run_identity,
        thesis.native_assessment_sha256,
        completed.promotion.integrity_sha256,
    )
    return create_trade_construction_evidence_package(
        package_identity=package_identity,
        native_run_identity=thesis.native_run_identity,
        canonical_instrument=thesis.canonical_instrument,
        native_assessment_sha256=thesis.native_assessment_sha256,
        setup_identity=TradeSetupIdentity.PULLBACK_CONTINUATION,
        observation_boundary=completed.promotion.analysis_boundary,
        provenance=tuple(dict.fromkeys((
            *thesis.provider_provenance,
            *thesis.calendar_provenance,
            completed.promotion.integrity_sha256,
            "SWING-V1-TRADE-CONSTRUCTION-V0",
        ))),
        qualification_candle=qualification,
        governing_structural_low=(
            anchor if thesis.direction.value == "LONG" else None
        ),
        governing_structural_high=(
            anchor if thesis.direction.value == "SHORT" else None
        ),
        prior_directional_swing_high=prior_high,
        prior_directional_swing_low=prior_low,
    )


class _Kr380SharedMonitoringConsumer:
    """Admit shared factual ticks and retain only current KR-380 V2 truth."""

    def __init__(
        self,
        workflow: SwingTradeWindowWorkflow,
        plan: TradePlanRecord,
        risk: RiskPermissionV1,
        context: NativeEcpcV2Context,
        instrument: InstrumentRecord,
        clock: Callable[[], datetime],
    ) -> None:
        self._workflow = workflow
        self._plan = plan
        self._risk = risk
        self._context = context
        self._instrument = instrument
        self._clock = clock
        self._registry = MonitoringAdmissionRegistry()
        self._previous: MonitoringObservation | None = None
        self._state = MonitoringConnectionState.DISCONNECTED
        self._terminal = False

    @property
    def binding_id(self) -> str:
        return self._context.monitoring_binding_id

    def on_market_tick(self, tick: ProviderMarketTick) -> None:
        if self._terminal:
            return
        if type(tick) is not ProviderMarketTick or tick.instrument != self._instrument:
            raise ValueError("KR380_SHARED_TICK_BINDING_INVALID")
        submission_id = "KR380-TICK-" + sha256(
            (
                f"{tick.connection_id}:{tick.observed_at.isoformat()}:"
                f"{tick.source_sequence}:{self._plan.trade_plan_id}"
            ).encode("utf-8")
        ).hexdigest()
        submission = build_monitoring_submission(
            tick,
            submission_id=submission_id,
            candidate_id=self._plan.trade_plan_id,
            monitoring_binding_id=self._context.monitoring_binding_id,
            model_trade_id=None,
            product="SWING",
            direction=self._plan.native_direction.value,
            submission_type=MonitoringSubmissionType.FACTUAL_MARKET_TICK,
            reference="STEP31_ENTRY",
            boundary=self._context.observation_boundary,
            timeframe="TICK",
            session_identity=self._context.session_identity,
            canonical_instrument=self._plan.canonical_instrument,
        )
        observation = self._registry.admit(
            submission,
            MonitoringAdmissionContext(
                candidate_id=self._plan.trade_plan_id,
                monitoring_binding_id=self._context.monitoring_binding_id,
                model_trade_id=None,
                canonical_instrument=self._plan.canonical_instrument,
                provider_instrument=(
                    f"{tick.instrument.exchange}:{tick.instrument.trading_symbol}"
                ),
                product="SWING",
                direction=self._plan.native_direction.value,
                provider_source=tick.source,
                source_connection_id=tick.connection_id,
                binding_active=True,
                boundary=self._context.observation_boundary,
                timeframe="TICK",
                session_identity=self._context.session_identity,
            ),
            clock=tick.received_at,
        )
        outcome = evaluate_kr380_v2(
            self._plan,
            self._risk,
            self._context,
            kr370_source_identity=self._risk.kr370_source_identity,
            previous=self._previous,
            current=observation,
            evaluated_at=self._clock(),
        )
        self._workflow._retain_production_outcome(
            self._plan, outcome, self._state
        )
        self._previous = observation
        self._terminal = outcome.state in {
            Kr380V2State.LONG_ENTRY_TRIGGERED,
            Kr380V2State.SHORT_ENTRY_TRIGGERED,
            Kr380V2State.EXTENDED,
            Kr380V2State.FAILED,
        }

    def on_order_update(self, _update: ProviderOrderUpdateEvidence) -> None:
        # Objective monitoring has no Sponsor-order or broker authority.
        return None

    def on_connection_state(self, state: MonitoringConnectionState) -> None:
        if type(state) is not MonitoringConnectionState:
            raise TypeError("KR380_MONITORING_CONNECTION_STATE_INVALID")
        self._state = state


def _exact_binding(
    completed: CompletedVisualV3Review,
    handoff: Kr370Step31EligibilityHandoff,
) -> bool:
    promotion = completed.promotion
    return (
        promotion is not None
        and handoff.native_run_identity == completed.requirement.native_run_identity
        and handoff.canonical_instrument == completed.requirement.canonical_instrument
        and handoff.native_assessment_sha256
        == completed.requirement.thesis.native_assessment_sha256
        and handoff.native_requirement_sha256 == completed.requirement.requirement_sha256
        and handoff.v3_readiness_sha256 == completed.readiness.result_sha256
        and handoff.review_pack_identity == promotion.review_pack_identity
        and handoff.kr370_record_integrity_sha256 == promotion.integrity_sha256
        and handoff.analysis_boundary == promotion.analysis_boundary
    )


def _kr380_reference(
    plan: TradePlanRecord, outcome: Kr380EntryOutcomeV2
) -> GovernedKr380EntryOutcomeReference:
    return GovernedKr380EntryOutcomeReference(
        entry_outcome_id=outcome.entry_outcome_id,
        native_run_identity=outcome.native_run_identity,
        canonical_instrument=outcome.canonical_instrument,
        trade_plan_id=outcome.trade_plan_id,
        trade_plan_sha256=outcome.trade_plan_sha256,
        risk_result_id=outcome.risk_result_id,
        execution_context_identity=plan.execution_context_identity,
        monitoring_binding_id=outcome.monitoring_binding_id,
        state=Kr380EntryTimingState(outcome.state.value),
        occurred_at=outcome.occurred_at,
        source_observation_ids=outcome.source_observation_ids,
        source_integrity_sha256=outcome.integrity_sha256,
    )


def _model_reference(
    model: ObjectiveModelRecordV1,
) -> GovernedModelLifecycleReference:
    return GovernedModelLifecycleReference(
        model_trade_id=model.model_trade_id,
        native_run_identity=model.native_run_identity,
        canonical_instrument=model.canonical_instrument,
        trade_plan_id=model.trade_plan_id,
        trade_plan_sha256=model.trade_plan_sha256,
        risk_result_id=model.risk_result_id,
        entry_outcome_id=model.entry_outcome_id,
        state=model.state,
        monitoring_state=model.monitoring_state,
        updated_at=model.activated_at,
        source_integrity_sha256=model.integrity_sha256,
    )


def _risk_binding(
    plan: TradePlanRecord, risk: RiskApproval | RiskPermissionV1
) -> bool:
    return (
        risk.candidate_id == plan.trade_plan_id
        and risk.candidate_digest == plan.integrity_hash
        and risk.run_id == plan.native_run_identity
    )


def _sponsor_binding(
    plan: TradePlanRecord, initiation: SponsorInitiationResult
) -> bool:
    decision = initiation.decision
    position = initiation.position
    return (
        decision is not None
        and decision.trade_plan_id == plan.trade_plan_id
        and decision.trade_plan_integrity_hash == plan.integrity_hash
        and decision.native_run_identity == plan.native_run_identity
        and decision.canonical_instrument == plan.canonical_instrument
        and decision.direction is plan.native_direction
        and (
            position is None
            or (
                position.decision_id == decision.decision_id
                and position.trade_plan_id == plan.trade_plan_id
                and position.canonical_instrument == plan.canonical_instrument
                and position.direction is plan.native_direction
            )
        )
    )


def _kr380_binding(
    plan: TradePlanRecord,
    outcome: GovernedKr380EntryOutcomeReference,
    risk_result_id: str | None,
    risk_state: RiskState | None,
) -> bool:
    direction_valid = (
        outcome.state is not Kr380EntryTimingState.LONG_ENTRY_TRIGGERED
        or plan.native_direction.value == "LONG"
    ) and (
        outcome.state is not Kr380EntryTimingState.SHORT_ENTRY_TRIGGERED
        or plan.native_direction.value == "SHORT"
    )
    risk_state_valid = (
        risk_state in {RiskState.APPROVED, RiskState.CONSTRAINED}
        or outcome.state is Kr380EntryTimingState.NO_TRIGGER
        and risk_state in {RiskState.REJECTED, RiskState.UNAVAILABLE}
    )
    return (
        risk_result_id is not None
        and risk_state_valid
        and outcome.native_run_identity == plan.native_run_identity
        and outcome.canonical_instrument == plan.canonical_instrument
        and outcome.trade_plan_id == plan.trade_plan_id
        and outcome.trade_plan_sha256 == plan.integrity_hash
        and outcome.risk_result_id == risk_result_id
        and outcome.execution_context_identity == plan.execution_context_identity
        and direction_valid
    )


def _model_binding(
    plan: TradePlanRecord,
    model: GovernedModelLifecycleReference,
    outcome: GovernedKr380EntryOutcomeReference | None,
    risk_result_id: str | None,
) -> bool:
    return (
        outcome is not None
        and risk_result_id is not None
        and model.native_run_identity == plan.native_run_identity
        and model.canonical_instrument == plan.canonical_instrument
        and model.trade_plan_id == plan.trade_plan_id
        and model.trade_plan_sha256 == plan.integrity_hash
        and model.risk_result_id == risk_result_id
        and model.entry_outcome_id == outcome.entry_outcome_id
    )


def _position_binding(
    plan: TradePlanRecord,
    sponsor: SponsorInitiationResult | None,
    position: ActiveLifecyclePosition,
) -> bool:
    decision = None if sponsor is None else sponsor.decision
    source_position = None if sponsor is None else sponsor.position
    return (
        decision is not None
        and source_position is not None
        and position.trade_plan_id == plan.trade_plan_id
        and position.trade_plan_hash == plan.integrity_hash
        and position.decision_id == decision.decision_id
        and position.position_id == source_position.position_id
        and position.canonical_instrument == plan.canonical_instrument
        and position.direction is plan.native_direction
    )


def _closure_binding(
    plan: TradePlanRecord,
    sponsor: SponsorInitiationResult | None,
    position: ActiveLifecyclePosition | None,
    closure: TradeClosureRecord,
) -> bool:
    decision = None if sponsor is None else sponsor.decision
    return (
        decision is not None
        and position is not None
        and closure.trade_plan_id == plan.trade_plan_id
        and closure.trade_plan_hash == plan.integrity_hash
        and closure.decision_id == decision.decision_id
        and closure.position_id == position.position_id
        and closure.instrument == plan.canonical_instrument
        and closure.direction is plan.native_direction
    )


def _journal_binding(
    plan: TradePlanRecord,
    sponsor: SponsorInitiationResult | None,
    position: ActiveLifecyclePosition | None,
    closure: TradeClosureRecord | None,
    journal: TradeJournalRecord,
) -> bool:
    decision = None if sponsor is None else sponsor.decision
    if (
        decision is None
        or journal.native_run_identity != plan.native_run_identity
        or journal.instrument != plan.canonical_instrument
        or journal.direction is not plan.native_direction
        or journal.native_assessment_sha256 != plan.native_assessment_sha256
        or journal.trade_plan_id != plan.trade_plan_id
        or journal.trade_plan_sha256 != plan.integrity_hash
        or journal.sponsor_decision_id != decision.decision_id
        or journal.sponsor_decision_sha256 != decision.integrity_hash
    ):
        return False
    if journal.trade_closure_id is None:
        return position is None and closure is None
    return (
        position is not None
        and closure is not None
        and journal.sponsor_position_id == position.position_id
        and journal.trade_closure_id == closure.closure_id
        and journal.trade_closure_sha256 == closure.integrity_hash
    )


__all__ = [
    "GovernedKr380EntryOutcomeReference",
    "GovernedModelLifecycleReference",
    "Kr380EntryTimingState",
    "NativeTradeWindowProjection",
    "SwingTradeWindowWorkflow",
    "TradeWindowState",
    "build_current_trade_construction_evidence",
]
