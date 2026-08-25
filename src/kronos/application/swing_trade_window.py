"""UX-05/06 application boundary for KR-370 to the Native Trade Window.

This workflow persists the eligibility handoff, the strict ready Step-31 Trade
Plan where available, and the separate advisory observation-phase evidence.
It does not derive Risk, Sponsor decisions, alerts, positions, execution, or
broker actions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Callable

from kronos.instrument.facts import CanonicalInstrumentContext
from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.application.paper_observation_tracking import (
    PaperObservationTrackingWorkflow,
)
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
from kronos.swing.v1.step31_observation import (
    LocalStep31ObservationStore,
    Step31ObservationEvidence,
    Step31SponsorObservationHandoff,
    construct_step31_observation,
    create_sponsor_observation_handoff,
)
from kronos.swing.v1.sponsor_observation_decision import (
    JournalObservationHandoffV1,
    LocalSponsorObservationDecisionStore,
    SponsorActivationDisposition,
    SponsorObservationDecisionResult,
    SponsorObservationReason,
    journal_observation_handoff,
    record_sponsor_observation_decision,
    transition_sponsor_observation_activation,
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
from kronos.swing.v1.native_sponsor_decision import (
    SponsorInitiationResult,
    SponsorTradeChoice,
)
from kronos.swing.v1.native_trade_journal import TradeJournalRecord
from kronos.swing.v1.observation_research_ledger import (
    LocalObservationResearchLedgerStore,
    ObservationLinkKind,
    ObservationResearchLedgerService,
    ObservationResearchProjectionV1,
    ObservationResearchQueryV1,
)
from kronos.swing.v1.paper_observation_track import (
    LocalPaperObservationTrackStore,
    PaperObservationTrackProjectionV1,
)
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
TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_SCHEMA = (
    "KRONOS-SWING-TRADE-PLAN-CONSTRUCTION-DIAGNOSTIC-V1"
)
TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_AUTHORITY = (
    "OPERABILITY_DIAGNOSTIC_ONLY_NO_DOMAIN_OR_EXECUTION_AUTHORITY"
)
TRADE_PLAN_CONSTRUCTION_SAFE_FAILURES = {
    "TRADE_PLAN_REQUEST_INVALID": "The construction request was not accepted.",
    "CURRENT_NATIVE_RUN_MISMATCH": "The selected analysis run is no longer current.",
    "CURRENT_NATIVE_ASSESSMENT_MISMATCH": "The selected opportunity is not bound to the current assessment.",
    "KITE_READ_ONLY_CAPABILITY_UNAVAILABLE": "Connect Kite before constructing the Trade Plan.",
    "GOVERNED_INSTRUMENT_INVALID": "The governed instrument context is unavailable.",
    "CURRENT_TRADE_CONSTRUCTION_SOURCE_INVALID": "Current governed construction evidence is unavailable.",
    "KR370_PROMOTION_UNAVAILABLE": "The current KR-370 promotion record is unavailable.",
    "ENTRY_AUTHORITY_UNAVAILABLE": "A governed Entry cannot be established from the current evidence.",
    "STOP_AUTHORITY_UNAVAILABLE": "A governed Stop cannot be established from the current evidence.",
    "INVALIDATION_AUTHORITY_UNAVAILABLE": "A governed thesis-invalidation reference cannot be established.",
    "TARGET_AUTHORITY_UNAVAILABLE": "A governed Target cannot be established from the current evidence.",
    "CURRENT_QUOTE_REQUIRED_BUT_UNAVAILABLE": "A required factual current quote is unavailable.",
    "EVIDENCE_BINDING_INVALID": "The Trade Construction evidence binding is invalid.",
    "EVIDENCE_STALE": "The Trade Construction evidence is no longer current.",
    "GEOMETRY_INVALID": "No valid governed trade geometry is available for this opportunity.",
    "MATERIAL_BARRIER_ELIMINATES_POSITIVE_REWARD": "A governed material barrier eliminates positive reward.",
    "EXECUTION_CONTEXT_INCOMPLETE": "The governed execution context is incomplete.",
    "STEP31_OBSERVATION_INPUT_INVALID": "The observation input is malformed.",
    "STEP31_OBSERVATION_HANDOFF_BINDING_INVALID": "The current KR-370 handoff binding is invalid.",
    "STEP31_OBSERVATION_EVIDENCE_BINDING_INVALID": "The observation evidence binding is invalid.",
    "STEP31_OBSERVATION_EVIDENCE_STALE": "The observation evidence is no longer current.",
    "STEP31_OBSERVATION_EXECUTION_CONTEXT_UNTRUSTED": "The canonical execution context is unavailable or untrusted.",
    "STEP31_OBSERVATION_TRADE_PLAN_BINDING_INVALID": "The conventional Trade Plan does not match the observation evidence.",
    "STEP31_OBSERVATION_CURRENT_BINDING_MISMATCH": "A different Step-31 observation is already bound to this evidence cycle.",
    "PORTFOLIO_STATE_SOURCE_INCOMPLETE": "Current Portfolio State evidence is incomplete.",
    "CURRENT_RISK_INPUT_UNAVAILABLE": "The governed Risk input is unavailable.",
    "CURRENT_NATIVE_ENTRY_TIMING_INPUT_UNAVAILABLE": "The governed entry-timing input is unavailable.",
    "OTHER_GOVERNED_UNAVAILABLE_REASON": "Step-31 returned a governed unavailable outcome.",
    "TRADE_PLAN_CONSTRUCTION_UNAVAILABLE": (
        "The current governed evidence could not complete Trade Plan construction."
    ),
}


class TradePlanConstructionStage(StrEnum):
    REQUEST_PARSE = "REQUEST_PARSE"
    CURRENT_BINDING = "CURRENT_BINDING"
    PROVIDER_CAPABILITY = "PROVIDER_CAPABILITY"
    EXECUTION_CONTEXT = "EXECUTION_CONTEXT"
    EVIDENCE_PACKAGE = "EVIDENCE_PACKAGE"
    UX05_HANDOFF = "UX05_HANDOFF"
    STEP31 = "STEP31"
    PORTFOLIO_STATE = "PORTFOLIO_STATE"
    DOMAIN007_RISK = "DOMAIN007_RISK"
    ECPC_KR380 = "ECPC_KR380"


class TradePlanConstructionAttemptResult(StrEnum):
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"


@dataclass(frozen=True, slots=True)
class TradePlanConstructionAttemptDiagnostic:
    attempt_identity: str
    run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    attempt_timestamp: datetime
    stage: TradePlanConstructionStage
    safe_failure_code: str | None
    safe_bounded_reason: str | None
    result: TradePlanConstructionAttemptResult
    integrity_sha256: str
    schema: str = TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_SCHEMA
    authority: str = TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_AUTHORITY

    def __post_init__(self) -> None:
        failed = self.result is TradePlanConstructionAttemptResult.FAILED
        if (
            re.fullmatch(r"[0-9a-f]{64}", self.attempt_identity) is None
            or not is_swing_analysis_run_id(self.run_identity)
            or re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.canonical_instrument) is None
            or re.fullmatch(r"[0-9a-f]{64}", self.native_assessment_sha256) is None
            or self.attempt_timestamp.tzinfo is None
            or type(self.stage) is not TradePlanConstructionStage
            or failed != (self.safe_failure_code is not None)
            or failed != (self.safe_bounded_reason is not None)
            or (
                failed
                and TRADE_PLAN_CONSTRUCTION_SAFE_FAILURES.get(
                    self.safe_failure_code or ""
                ) != self.safe_bounded_reason
            )
            or type(self.result) is not TradePlanConstructionAttemptResult
            or self.schema != TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_SCHEMA
            or self.authority != TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_AUTHORITY
            or self.integrity_sha256 != _construction_diagnostic_integrity(self)
        ):
            raise ValueError("TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_INVALID")


class LocalTradePlanConstructionDiagnosticStore:
    """Append-only local store for bounded construction-attempt evidence."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def retain(self, record: TradePlanConstructionAttemptDiagnostic) -> None:
        path = self.root / f"{record.attempt_identity}.json"
        payload = _construction_diagnostic_dict(record)
        try:
            with path.open("x", encoding="utf-8") as target:
                json.dump(payload, target, sort_keys=True, separators=(",", ":"))
                target.flush()
                os.fsync(target.fileno())
            os.chmod(path, 0o600)
        except FileExistsError:
            if json.loads(path.read_text(encoding="utf-8")) != payload:
                raise ValueError("TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_IMMUTABILITY_VIOLATION")
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_PERSISTENCE_FAILED") from error

    def load(self) -> tuple[TradePlanConstructionAttemptDiagnostic, ...]:
        records = []
        for path in sorted(self.root.glob("*.json")):
            try:
                records.append(_construction_diagnostic_from_dict(
                    json.loads(path.read_text(encoding="utf-8"))
                ))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return tuple(sorted(
            records, key=lambda item: (item.attempt_timestamp, item.attempt_identity)
        ))


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
    STEP31_OBSERVATION_AVAILABLE = "STEP31_OBSERVATION_AVAILABLE"
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
    step31_observation: Step31ObservationEvidence | None = None
    risk_state: str = "RISK_UNAVAILABLE"
    risk_reason: str = "RISK EVALUATION NOT AVAILABLE"
    risk_result_id: str | None = None
    sponsor_controls_available: bool = False
    sponsor_observation_controls_available: bool = False
    sponsor_observation_decision_state: str = "NO OBSERVATION DECISION RECORDED"
    sponsor_observation_choice: str | None = None
    sponsor_observation_decision_id: str | None = None
    sponsor_observation_snapshot_id: str | None = None
    activation_disposition: str = "NOT ESTABLISHED"
    activation_reason: str = "NO OBSERVATION DECISION RECORDED"
    warning_acknowledged: bool = False
    paper_observation_track_start_available: bool = False
    paper_observation_track_id: str | None = None
    paper_observation_track_state: str = "NOT AVAILABLE"
    paper_observation_monitoring_state: str = "NOT ACTIVE"
    paper_observation_monitoring_reason: str = "NO PAPER OBSERVATION TRACK"
    paper_observation_entry_state: str = "ENTRY NOT OBSERVED"
    paper_observation_outcome_state: str = "OUTCOME NOT ESTABLISHED"
    paper_observation_entry_reference: Decimal | None = None
    paper_observation_stop: Decimal | None = None
    paper_observation_target: Decimal | None = None
    paper_observation_created_at: datetime | None = None
    paper_observation_last_fact_at: datetime | None = None
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
    latest_construction_attempt: TradePlanConstructionAttemptDiagnostic | None = None
    last_updated_at: datetime | None = None

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
            or (
                self.step31_observation is not None
                and type(self.step31_observation) is not Step31ObservationEvidence
            )
            or ready != (self.trade_plan is not None)
            or (
                self.state is TradeWindowState.STEP31_OBSERVATION_AVAILABLE
                and self.step31_observation is None
            )
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
            or type(self.sponsor_observation_controls_available) is not bool
            or not self.sponsor_observation_decision_state
            or (
                self.sponsor_observation_choice is not None
                and self.sponsor_observation_choice not in {"PAPER", "LIVE", "IGNORE"}
            )
            or (self.sponsor_observation_decision_id is None)
            != (self.sponsor_observation_snapshot_id is None)
            or (self.sponsor_observation_decision_id is None)
            != (self.activation_disposition == "NOT ESTABLISHED")
            or not self.activation_reason
            or type(self.warning_acknowledged) is not bool
            or type(self.paper_observation_track_start_available) is not bool
            or (self.paper_observation_track_id is None) != (
                self.paper_observation_track_state
                in {"NOT AVAILABLE", "AVAILABLE", "NOT REQUIRED"}
            )
            or not self.paper_observation_track_state
            or not self.paper_observation_monitoring_state
            or not self.paper_observation_monitoring_reason
            or not self.paper_observation_entry_state
            or not self.paper_observation_outcome_state
            or any(
                value is not None and (
                    type(value) is not Decimal or not value.is_finite()
                )
                for value in (
                    self.paper_observation_entry_reference,
                    self.paper_observation_stop,
                    self.paper_observation_target,
                )
            )
            or any(
                value is not None and value.tzinfo is None
                for value in (
                    self.paper_observation_created_at,
                    self.paper_observation_last_fact_at,
                )
            )
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
            or (
                self.last_updated_at is not None
                and self.last_updated_at.tzinfo is None
            )
            or (
                self.latest_construction_attempt is not None
                and (
                    type(self.latest_construction_attempt)
                    is not TradePlanConstructionAttemptDiagnostic
                    or self.latest_construction_attempt.run_identity
                    != self.native_run_identity
                    or self.latest_construction_attempt.canonical_instrument
                    != self.canonical_instrument
                    or self.latest_construction_attempt.native_assessment_sha256
                    != self.native_assessment_sha256
                )
            )
        ):
            raise ValueError("NATIVE_TRADE_WINDOW_PROJECTION_INVALID")


class SwingTradeWindowWorkflow:
    """Coordinate exact handoff and versioned Step-31 evidence only."""

    def __init__(
        self,
        handoff_store: LocalKr370Step31HandoffStore,
        trade_plan_store: LocalTradePlanStore,
        portfolio_store: LocalPortfolioStateV1Store | None = None,
        risk_store: LocalRiskPermissionV1Store | None = None,
        kr380_store: LocalKr380V2Store | None = None,
        objective_model_store: LocalObjectiveModelV1Store | None = None,
        diagnostic_store: LocalTradePlanConstructionDiagnosticStore | None = None,
        observation_store: LocalStep31ObservationStore | None = None,
        sponsor_observation_store: LocalSponsorObservationDecisionStore | None = None,
        observation_research_ledger: ObservationResearchLedgerService | None = None,
        paper_observation_store: LocalPaperObservationTrackStore | None = None,
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
            or (
                diagnostic_store is not None
                and type(diagnostic_store)
                is not LocalTradePlanConstructionDiagnosticStore
            )
            or (
                observation_store is not None
                and type(observation_store) is not LocalStep31ObservationStore
            )
            or (
                sponsor_observation_store is not None
                and type(sponsor_observation_store)
                is not LocalSponsorObservationDecisionStore
            )
            or (
                observation_research_ledger is not None
                and type(observation_research_ledger)
                is not ObservationResearchLedgerService
            )
            or (
                paper_observation_store is not None
                and type(paper_observation_store) is not LocalPaperObservationTrackStore
            )
        ):
            raise TypeError("SWING_TRADE_WINDOW_STORE_INVALID")
        self._handoff_store = handoff_store
        self._trade_plan_store = trade_plan_store
        self._portfolio_store = portfolio_store
        self._risk_store = risk_store
        self._kr380_store = kr380_store
        self._objective_model_store = objective_model_store
        self._diagnostic_store = diagnostic_store
        self._observation_store = observation_store or LocalStep31ObservationStore(
            trade_plan_store.root.parent / "step31-observation-v1"
        )
        self._sponsor_observation_store = (
            sponsor_observation_store
            or LocalSponsorObservationDecisionStore(
                trade_plan_store.root.parent / "sponsor-observation-decision-v1"
            )
        )
        self._observation_research = (
            observation_research_ledger
            or ObservationResearchLedgerService(
                LocalObservationResearchLedgerStore(
                    trade_plan_store.root.parent / "observation-research-ledger-v1"
                ),
                self._sponsor_observation_store,
            )
        )
        self._paper_observation_tracking = PaperObservationTrackingWorkflow(
            paper_observation_store
            or LocalPaperObservationTrackStore(
                trade_plan_store.root.parent / "paper-observation-track-v1"
            )
        )
        self._portfolio_state: PortfolioStateV1 | None = None
        self._shared_monitoring_hub: SharedSwingMonitoringHub | None = None
        self._monitoring_registrations: dict[str, object] = {}
        self._monitoring_consumers: dict[str, _Kr380SharedMonitoringConsumer] = {}
        self._completed: dict[tuple[str, str], CompletedVisualV3Review] = {}
        self._handoffs: dict[tuple[str, str], Kr370Step31EligibilityHandoff] = {}
        self._plans: dict[tuple[str, str], TradePlanRecord] = {}
        self._observations: dict[tuple[str, str], Step31ObservationEvidence] = {}
        self._observation_decisions: dict[
            tuple[str, str], SponsorObservationDecisionResult
        ] = {}
        self._failures: dict[tuple[str, str], str] = {}
        restored_diagnostics = () if diagnostic_store is None else diagnostic_store.load()
        self._construction_attempts: dict[
            tuple[str, str], tuple[TradePlanConstructionAttemptDiagnostic, ...]
        ] = {}
        for item in restored_diagnostics:
            key = (item.run_identity, item.canonical_instrument)
            self._construction_attempts[key] = (*self._construction_attempts.get(key, ()), item)
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
        self._paper_observation_tracking.set_shared_monitoring_hub(hub)

    @property
    def shared_monitoring_hub(self) -> SharedSwingMonitoringHub | None:
        return self._shared_monitoring_hub

    @property
    def active_monitoring_count(self) -> int:
        return (
            len(self._monitoring_registrations)
            + self._paper_observation_tracking.active_monitoring_count
        )

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
        self._paper_observation_tracking.close()

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
                ecpc_outcome=EcpcV2Outcome.PENDING,
                ecpc_blockers=(EcpcV2Blocker.EXECUTION_CONFIRMATION_PENDING,),
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
        self._observations.clear()
        self._observation_decisions.clear()
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
        stored_observations = self._observation_store.load_for_requirements(requirements)
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
            observation_matches = tuple(
                record for record in stored_observations
                if record.native_run_identity == promotion.run_identity
                and record.canonical_instrument == promotion.canonical_instrument
                and record.native_assessment_sha256 == promotion.native_assessment_sha256
                and record.v3_readiness_sha256 == handoff.v3_readiness_sha256
                and record.kr370_handoff_identity == handoff.handoff_identity
                and record.kr370_handoff_integrity_sha256 == handoff.integrity_sha256
            )
            if len(observation_matches) > 1:
                raise ValueError("SWING_TRADE_WINDOW_OBSERVATION_RESTORE_AMBIGUOUS")
            if observation_matches:
                observation = observation_matches[0]
                if (
                    observation.conventional_trade_plan_id is not None
                    and (
                        not matches
                        or matches[0].trade_plan_id
                        != observation.conventional_trade_plan_id
                        or matches[0].integrity_hash
                        != observation.conventional_trade_plan_sha256
                    )
                ):
                    raise ValueError("SWING_TRADE_WINDOW_OBSERVATION_PLAN_BINDING_INVALID")
                self._observations[key] = observation
        restored_decisions = self._sponsor_observation_store.for_current_observations(
            tuple(self._observations.values())
        )
        self._observation_decisions = {
            (item.snapshot.native_run_identity, item.snapshot.canonical_instrument): item
            for item in restored_decisions
        }
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
        self._synchronize_observation_research_links()

    def _synchronize_observation_research_links(self) -> None:
        """Link only already-governed downstream records to observations."""

        for result in self._observation_decisions.values():
            snapshot = result.snapshot
            plan_id = snapshot.conventional_trade_plan_identity
            plan_hash = snapshot.conventional_trade_plan_sha256
            if plan_id is None or plan_hash is None:
                continue
            common = dict(
                decision_identity=result.decision.decision_identity,
                native_run_identity=snapshot.native_run_identity,
                canonical_instrument=snapshot.canonical_instrument,
                native_assessment_sha256=snapshot.native_assessment_sha256,
                trade_plan_identity=plan_id,
                trade_plan_sha256=plan_hash,
            )
            outcome = self._kr380.get(plan_id)
            if outcome is not None:
                self._observation_research.append_link(
                    **common,
                    kind=ObservationLinkKind.KR380_ENTRY_OUTCOME,
                    source_contract_identity=outcome.contract_identity,
                    source_contract_version=outcome.contract_version,
                    source_record_identity=outcome.entry_outcome_id,
                    source_integrity_sha256=outcome.source_integrity_sha256,
                    source_state=outcome.state.value,
                    source_timestamp=outcome.occurred_at,
                )
            model = self._models.get(plan_id)
            if model is not None:
                kind = (
                    ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME
                    if model.state is ObjectiveModelState.CLOSED
                    else ObservationLinkKind.KR390_OBJECTIVE_MODEL
                )
                self._observation_research.append_link(
                    **common,
                    kind=kind,
                    source_contract_identity="KRONOS-SWING-OBJECTIVE-MODEL-TRADE-V1",
                    source_contract_version="1",
                    source_record_identity=model.model_trade_id,
                    source_integrity_sha256=model.source_integrity_sha256,
                    source_state=model.state.value,
                    source_timestamp=model.updated_at,
                )
            sponsor = self._sponsor.get(plan_id)
            position = None if sponsor is None else sponsor.position
            if (
                position is not None
                and result.activation.sponsor_position_identity == position.position_id
            ):
                self._observation_research.append_link(
                    **common,
                    kind=ObservationLinkKind.SPONSOR_POSITION,
                    source_contract_identity=position.contract_identity,
                    source_contract_version=position.contract_version,
                    source_record_identity=position.position_id,
                    source_integrity_sha256=position.integrity_hash,
                    source_state=position.state.value,
                    source_timestamp=position.created_at,
                    sponsor_position_identity=position.position_id,
                )
            closure = self._closures.get(plan_id)
            if (
                closure is not None
                and result.activation.sponsor_position_identity == closure.position_id
            ):
                self._observation_research.append_link(
                    **common,
                    kind=ObservationLinkKind.SPONSOR_POSITION_OUTCOME,
                    source_contract_identity=closure.contract_identity,
                    source_contract_version=closure.contract_version,
                    source_record_identity=closure.closure_id,
                    source_integrity_sha256=closure.integrity_hash,
                    source_state="CLOSED",
                    source_timestamp=closure.created_at,
                    sponsor_position_identity=closure.position_id,
                )

    def construct(
        self,
        completed: CompletedVisualV3Review,
        evidence: TradeConstructionEvidencePackage,
        execution_context: CanonicalInstrumentContext,
        *,
        current_run_identity: str,
        current_analysis_boundary: datetime,
        created_at: datetime,
        stage_listener: Callable[[TradePlanConstructionStage], None] | None = None,
    ) -> NativeTradeWindowProjection:
        """Publish strict plan and advisory evidence after exact eligibility."""

        promotion = completed.promotion
        if promotion is None:
            raise ValueError("KR370_PROMOTION_UNAVAILABLE")
        if stage_listener is not None:
            stage_listener(TradePlanConstructionStage.UX05_HANDOFF)
        key = (promotion.run_identity, promotion.canonical_instrument)
        handoff = self._handoffs.get(key)
        if handoff is None:
            handoff = create_kr370_step31_handoff(
                completed.requirement,
                completed.readiness,
                promotion,
                current_run_identity=current_run_identity,
                current_analysis_boundary=current_analysis_boundary,
                created_at=created_at,
            )
            self._handoff_store.retain(handoff)
        elif not _exact_binding(completed, handoff):
            raise ValueError("SWING_TRADE_WINDOW_HANDOFF_BINDING_INVALID")
        if stage_listener is not None:
            stage_listener(TradePlanConstructionStage.STEP31)
        existing_observation = self._observations.get(key)
        if existing_observation is not None:
            if (
                type(evidence) is TradeConstructionEvidencePackage
                and type(execution_context) is CanonicalInstrumentContext
                and existing_observation.kr370_handoff_identity == handoff.handoff_identity
                and existing_observation.kr370_handoff_integrity_sha256
                == handoff.integrity_sha256
                and existing_observation.evidence_package_sha256 == evidence.package_sha256
                and existing_observation.execution_context_identity == execution_context.identity
            ):
                return self.project(*key)
            raise ValueError("STEP31_OBSERVATION_CURRENT_BINDING_MISMATCH")
        plan = construct_trade_plan(
            completed.requirement,
            handoff,
            evidence,
            execution_context,
            created_at=created_at,
        )
        observation = construct_step31_observation(
            completed.requirement,
            handoff,
            evidence,
            execution_context,
            created_at=created_at,
            conventional_plan=(
                plan
                if plan.geometry_viability is TradePlanStatus.TRADE_PLAN_READY
                else None
            ),
        )
        self._completed[key] = completed
        self._handoffs[key] = handoff
        if plan.geometry_viability is TradePlanStatus.TRADE_PLAN_READY:
            self._trade_plan_store.retain(plan)
            self._plans[key] = plan
            self._failures.pop(key, None)
        else:
            self._plans.pop(key, None)
            self._failures.pop(key, None)
        self._observation_store.retain(observation)
        self._observations[key] = observation
        return self.project(*key)

    def retain_construction_attempt(
        self,
        *,
        attempt_identity: str,
        run_identity: str,
        canonical_instrument: str,
        native_assessment_sha256: str,
        attempt_timestamp: datetime,
        stage: TradePlanConstructionStage,
        result: TradePlanConstructionAttemptResult,
        safe_failure_code: str | None = None,
        safe_bounded_reason: str | None = None,
    ) -> TradePlanConstructionAttemptDiagnostic:
        values = dict(
            attempt_identity=attempt_identity,
            run_identity=run_identity,
            canonical_instrument=canonical_instrument,
            native_assessment_sha256=native_assessment_sha256,
            attempt_timestamp=attempt_timestamp,
            stage=stage,
            safe_failure_code=safe_failure_code,
            safe_bounded_reason=safe_bounded_reason,
            result=result,
            integrity_sha256="",
        )
        record = TradePlanConstructionAttemptDiagnostic(**(
            values | {"integrity_sha256": _construction_diagnostic_integrity_values(values)}
        ))
        if self._diagnostic_store is not None:
            self._diagnostic_store.retain(record)
        key = (run_identity, canonical_instrument)
        current = self._construction_attempts.get(key, ())
        if any(item.attempt_identity == attempt_identity for item in current):
            raise ValueError("TRADE_PLAN_CONSTRUCTION_ATTEMPT_DUPLICATE")
        self._construction_attempts[key] = (*current, record)
        return record

    def latest_construction_attempt(
        self,
        run_identity: str,
        canonical_instrument: str,
        native_assessment_sha256: str | None = None,
    ) -> TradePlanConstructionAttemptDiagnostic | None:
        records = self._construction_attempts.get((run_identity, canonical_instrument), ())
        if native_assessment_sha256 is not None:
            records = tuple(
                item for item in records
                if item.native_assessment_sha256 == native_assessment_sha256
            )
        return None if not records else records[-1]

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
            latest_construction_attempt=self.latest_construction_attempt(
                run_identity, canonical_instrument, promotion.native_assessment_sha256
            ),
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
        observation = self._observations.get(key)
        if plan is None and observation is not None:
            return NativeTradeWindowProjection(
                **base,
                state=TradeWindowState.STEP31_OBSERVATION_AVAILABLE,
                reason="STEP31_OBSERVATION_AVAILABLE",
                handoff=handoff,
                trade_plan=None,
                step31_observation=observation,
                **(
                    {"last_updated_at": observation.created_at}
                    | self._observation_projection(key)
                ),
            )
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
            step31_observation=observation,
            **(
                self._downstream_projection(plan)
                | {"last_updated_at": (
                    observation.created_at if observation is not None else plan.created_at
                )}
                | self._observation_projection(key)
            ),
        )

    def record_sponsor_observation_choice(
        self,
        run_identity: str,
        canonical_instrument: str,
        native_assessment_sha256: str,
        observation_evidence_id: str,
        choice: SponsorTradeChoice,
        disposition: SponsorActivationDisposition,
        *,
        current_run_identity: str,
        decided_at: datetime,
        warning_acknowledged: bool,
        sponsor_reason: SponsorObservationReason | None = None,
        risk_identity: str | None = None,
        risk_state: str = "RISK_UNAVAILABLE",
        existing_sponsor_decision_identity: str | None = None,
        sponsor_position_identity: str | None = None,
        mcx_supporting_context_identity: str | None = None,
        mcx_supporting_context_sha256: str | None = None,
    ) -> SponsorObservationDecisionResult:
        """Retain Sponsor judgment without granting activation authority."""

        key = (run_identity, canonical_instrument)
        completed = self._completed.get(key)
        observation = self._observations.get(key)
        projection = self.project(*key)
        if (
            completed is None
            or observation is None
            or projection is None
            or projection.native_assessment_sha256 != native_assessment_sha256
            or observation.observation_evidence_id != observation_evidence_id
            or current_run_identity != run_identity
            or projection.risk_state != risk_state
            or projection.risk_result_id != risk_identity
        ):
            raise ValueError("SPONSOR_OBSERVATION_CURRENT_BINDING_INVALID")
        existing = self._observation_decisions.get(key)
        if existing is not None:
            if (
                existing.decision.choice is choice
                and existing.decision.warning_acknowledged is warning_acknowledged
                and existing.decision.sponsor_reason is sponsor_reason
                and existing.snapshot.step31_observation_identity
                == observation_evidence_id
            ):
                # Repair only the same prospective request if the linked-ledger
                # write was interrupted after the authoritative decision write.
                self._observation_research.retain_observation(existing)
                return existing
            raise ValueError("SPONSOR_OBSERVATION_DECISION_ALREADY_FINAL")
        handoff = create_sponsor_observation_handoff(
            observation,
            risk_state=risk_state,
            risk_evidence_identity=risk_identity,
        )
        result = record_sponsor_observation_decision(
            completed.promotion,
            observation,
            handoff,
            choice,
            disposition,
            current_run_identity=current_run_identity,
            decided_at=decided_at,
            warning_acknowledged=warning_acknowledged,
            sponsor_reason=sponsor_reason,
            risk_identity=risk_identity,
            risk_state=risk_state,
            existing_sponsor_decision_identity=existing_sponsor_decision_identity,
            sponsor_position_identity=sponsor_position_identity,
            mcx_supporting_context_identity=mcx_supporting_context_identity,
            mcx_supporting_context_sha256=mcx_supporting_context_sha256,
        )
        retained = self._sponsor_observation_store.retain(result)
        self._observation_research.retain_observation(retained)
        self._observation_decisions[key] = retained
        return retained

    def sponsor_observation_decisions(
        self,
    ) -> tuple[SponsorObservationDecisionResult, ...]:
        return tuple(
            self._observation_decisions[key]
            for key in sorted(self._observation_decisions)
        )

    def finalize_sponsor_observation_activation(
        self,
        run_identity: str,
        canonical_instrument: str,
        decision_identity: str,
        choice: SponsorTradeChoice,
        *,
        disposition: SponsorActivationDisposition,
        existing_sponsor_decision_identity: str | None,
        sponsor_position_identity: str | None,
        recorded_at: datetime,
    ) -> SponsorObservationDecisionResult:
        """Retain one terminal activation result after separate Sponsor entry."""

        key = (run_identity, canonical_instrument)
        current = self._observation_decisions.get(key)
        if (
            current is None
            or current.decision.decision_identity != decision_identity
            or current.decision.choice is not choice
        ):
            raise ValueError("SPONSOR_ACTIVATION_CURRENT_BINDING_INVALID")
        if current.activation.disposition is disposition:
            return current
        transitioned = transition_sponsor_observation_activation(
            current,
            disposition,
            existing_sponsor_decision_identity=existing_sponsor_decision_identity,
            sponsor_position_identity=sponsor_position_identity,
            recorded_at=recorded_at,
        )
        retained = self._sponsor_observation_store.transition_activation(transitioned)
        self._observation_decisions[key] = retained
        return retained

    def journal_observation_handoffs(
        self,
    ) -> tuple[JournalObservationHandoffV1, ...]:
        return tuple(
            journal_observation_handoff(item)
            for item in self.sponsor_observation_decisions()
        )

    def observation_research_snapshot(
        self, query: ObservationResearchQueryV1 | None = None
    ) -> tuple[ObservationResearchProjectionV1, ...]:
        """Return a read-only deterministic research projection."""

        return self._observation_research.snapshot(query)

    def observation_research_export_json(
        self, query: ObservationResearchQueryV1 | None = None
    ) -> str:
        return self._observation_research.export_json(query)

    def observation_research_export_csv(
        self, query: ObservationResearchQueryV1 | None = None
    ) -> str:
        return self._observation_research.export_csv(query)

    def start_paper_observation_track(
        self,
        run_identity: str,
        canonical_instrument: str,
        native_assessment_sha256: str,
        decision_identity: str,
        *,
        current_run_identity: str,
        started_at: datetime,
    ) -> PaperObservationTrackProjectionV1:
        """Start one explicit non-position Track from the exact blocked decision."""

        key = (run_identity, canonical_instrument)
        result = self._observation_decisions.get(key)
        if (
            result is None
            or current_run_identity != run_identity
            or result.snapshot.native_assessment_sha256 != native_assessment_sha256
            or result.decision.decision_identity != decision_identity
        ):
            raise ValueError("PAPER_OBSERVATION_TRACK_CURRENT_BINDING_INVALID")
        return self._paper_observation_tracking.start(
            result,
            current_run_identity=current_run_identity,
            started_at=started_at,
        )

    def attach_paper_observation_monitoring(
        self,
        track_identity: str,
        capability: object,
        instrument: InstrumentRecord,
    ) -> PaperObservationTrackProjectionV1:
        return self._paper_observation_tracking.attach_monitoring(
            track_identity, capability, instrument
        )

    def restore_paper_observation_monitoring(
        self,
        capability: object,
        resolver: Callable[[str], InstrumentRecord],
    ) -> tuple[str, ...]:
        return self._paper_observation_tracking.restore_monitoring(
            capability, resolver
        )

    def mark_paper_observation_monitoring_unavailable(self, reason: str) -> None:
        self._paper_observation_tracking.mark_monitoring_unavailable(reason)

    def paper_observation_projections(
        self,
    ) -> tuple[PaperObservationTrackProjectionV1, ...]:
        return self._paper_observation_tracking.projections()

    @staticmethod
    def _paper_projection_values(
        track: PaperObservationTrackProjectionV1,
    ) -> dict[str, object]:
        return {
            "paper_observation_track_start_available": False,
            "paper_observation_track_id": track.track.track_identity,
            "paper_observation_track_state": track.track_state.value,
            "paper_observation_monitoring_state": track.monitoring_state.value,
            "paper_observation_monitoring_reason": track.monitoring_reason,
            "paper_observation_entry_state": track.entry_state.value,
            "paper_observation_outcome_state": track.outcome_state.value,
            "paper_observation_entry_reference": (
                track.track.observation_entry_reference
            ),
            "paper_observation_stop": track.track.stop,
            "paper_observation_target": track.track.target,
            "paper_observation_created_at": track.created_at,
            "paper_observation_last_fact_at": track.last_factual_observation_at,
        }

    def _observation_projection(
        self, key: tuple[str, str]
    ) -> dict[str, object]:
        result = self._observation_decisions.get(key)
        if result is None:
            return {
                "sponsor_observation_controls_available": (
                    key in self._observations
                ),
            }
        paper_values: dict[str, object]
        if result.decision.choice is not SponsorTradeChoice.PAPER:
            paper_values = {
                "paper_observation_track_state": "NOT AVAILABLE",
                "paper_observation_monitoring_reason": (
                    "PAPER DECISION REQUIRED"
                ),
            }
        elif result.activation.disposition is SponsorActivationDisposition.ACTIVATED:
            paper_values = {
                "paper_observation_track_state": "NOT REQUIRED",
                "paper_observation_monitoring_reason": (
                    "GOVERNED SPONSOR POSITION ACTIVATED"
                ),
            }
        elif not result.activation.disposition.value.startswith("BLOCKED_"):
            paper_values = {
                "paper_observation_track_state": "NOT AVAILABLE",
                "paper_observation_monitoring_reason": (
                    "BLOCKED PAPER ACTIVATION REQUIRED"
                ),
            }
        else:
            track = self._paper_observation_tracking.projection_for_decision(
                result.decision.decision_identity
            )
            paper_values = (
                {
                    "paper_observation_track_start_available": True,
                    "paper_observation_track_state": "AVAILABLE",
                    "paper_observation_monitoring_reason": (
                        "EXPLICIT SPONSOR START REQUIRED"
                    ),
                    "paper_observation_entry_reference": result.snapshot.entry,
                    "paper_observation_stop": result.snapshot.stop,
                    "paper_observation_target": result.snapshot.target,
                }
                if track is None
                else self._paper_projection_values(track)
            )
        return {
            "sponsor_observation_controls_available": False,
            "sponsor_observation_decision_state": (
                result.decision.choice.value + " · RECORDED"
            ),
            "sponsor_observation_choice": result.decision.choice.value,
            "sponsor_observation_decision_id": result.decision.decision_identity,
            "sponsor_observation_snapshot_id": result.snapshot.snapshot_identity,
            "activation_disposition": result.activation.disposition.value,
            "activation_reason": result.activation.reason,
            "warning_acknowledged": result.decision.warning_acknowledged,
            "risk_state": result.snapshot.risk_state,
            "risk_reason": (
                "DECISION-TIME RISK STATE PRESERVED"
            ),
            "risk_result_id": result.snapshot.risk_identity,
            "last_updated_at": max(
                result.decision.decision_timestamp,
                result.activation.recorded_at,
            ),
        } | paper_values

    def sponsor_observation_handoff(
        self, run_identity: str, canonical_instrument: str
    ) -> Step31SponsorObservationHandoff | None:
        """Expose bounded observation lineage for the future Sponsor decision step."""

        projection = self.project(run_identity, canonical_instrument)
        if projection is None or projection.step31_observation is None:
            return None
        return create_sponsor_observation_handoff(
            projection.step31_observation,
            risk_state=projection.risk_state,
            risk_evidence_identity=projection.risk_result_id,
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


def _construction_diagnostic_dict(
    record: TradePlanConstructionAttemptDiagnostic,
) -> dict[str, object]:
    values = asdict(record)
    values["stage"] = record.stage.value
    values["result"] = record.result.value
    values["attempt_timestamp"] = record.attempt_timestamp.isoformat()
    return values


def _construction_diagnostic_from_dict(
    value: object,
) -> TradePlanConstructionAttemptDiagnostic:
    if type(value) is not dict:
        raise ValueError("TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_INVALID")
    values = dict(value)
    values["stage"] = TradePlanConstructionStage(values["stage"])
    values["result"] = TradePlanConstructionAttemptResult(values["result"])
    values["attempt_timestamp"] = datetime.fromisoformat(values["attempt_timestamp"])
    return TradePlanConstructionAttemptDiagnostic(**values)


def _construction_diagnostic_integrity(
    record: TradePlanConstructionAttemptDiagnostic,
) -> str:
    values = asdict(record)
    values["integrity_sha256"] = ""
    return _construction_diagnostic_integrity_values(values)


def _construction_diagnostic_integrity_values(
    values: dict[str, object],
) -> str:
    material = dict(values)
    material.setdefault("schema", TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_SCHEMA)
    material.setdefault("authority", TRADE_PLAN_CONSTRUCTION_DIAGNOSTIC_AUTHORITY)
    material["integrity_sha256"] = ""
    return sha256(json.dumps(
        material,
        sort_keys=True,
        default=_construction_diagnostic_json_default,
        separators=(",", ":"),
    ).encode()).hexdigest()


def _construction_diagnostic_json_default(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError


__all__ = [
    "GovernedKr380EntryOutcomeReference",
    "GovernedModelLifecycleReference",
    "Kr380EntryTimingState",
    "NativeTradeWindowProjection",
    "LocalTradePlanConstructionDiagnosticStore",
    "SwingTradeWindowWorkflow",
    "TradePlanConstructionAttemptDiagnostic",
    "TradePlanConstructionAttemptResult",
    "TRADE_PLAN_CONSTRUCTION_SAFE_FAILURES",
    "TradePlanConstructionStage",
    "TradeWindowState",
    "build_current_trade_construction_evidence",
]
