"""UX-05/06 application boundary for KR-370 to the Native Trade Window.

This workflow persists the eligibility handoff and exact ready Step-31 record.
It does not derive geometry, Risk, Sponsor decisions, KR-380 outcomes, alerts,
positions, execution, or broker actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kronos.instrument.facts import CanonicalInstrumentContext
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalClassification,
)
from kronos.swing.v1.kr370_step31_handoff import (
    Kr370Step31EligibilityHandoff,
    LocalKr370Step31HandoffStore,
    create_kr370_step31_handoff,
)
from kronos.swing.v1.native_trade_construction import (
    LocalTradePlanStore,
    TradeConstructionEvidencePackage,
    TradePlanRecord,
    TradePlanStatus,
    construct_trade_plan,
)
from kronos.application.swing_visual_v3 import CompletedVisualV3Review
from kronos.application.swing_native_review import NativeReviewWorkflowSnapshot
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecyclePosition,
    TradeClosureRecord,
)
from kronos.swing.v1.native_sponsor_decision import SponsorInitiationResult
from kronos.swing.v1.native_trade_journal import TradeJournalRecord
from kronos.swing.v1.step32 import ObjectiveModelState, RiskApproval, RiskState


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
    monitoring_binding_id: str
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
                self.monitoring_binding_id,
            ))
            or len(self.trade_plan_sha256) != 64
            or type(self.state) is not Kr380EntryTimingState
            or self.occurred_at.tzinfo is None
            or type(self.source_observation_ids) is not tuple
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
            or (self.risk_result_id is None) != (self.risk_state == "RISK_UNAVAILABLE")
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
    ) -> None:
        if (
            type(handoff_store) is not LocalKr370Step31HandoffStore
            or type(trade_plan_store) is not LocalTradePlanStore
        ):
            raise TypeError("SWING_TRADE_WINDOW_STORE_INVALID")
        self._handoff_store = handoff_store
        self._trade_plan_store = trade_plan_store
        self._completed: dict[tuple[str, str], CompletedVisualV3Review] = {}
        self._handoffs: dict[tuple[str, str], Kr370Step31EligibilityHandoff] = {}
        self._plans: dict[tuple[str, str], TradePlanRecord] = {}
        self._failures: dict[tuple[str, str], str] = {}
        self._risks: dict[str, RiskApproval] = {}
        self._sponsor: dict[str, SponsorInitiationResult] = {}
        self._kr380: dict[str, GovernedKr380EntryOutcomeReference] = {}
        self._models: dict[str, GovernedModelLifecycleReference] = {}
        self._positions: dict[str, ActiveLifecyclePosition] = {}
        self._closures: dict[str, TradeClosureRecord] = {}
        self._journals: dict[str, TradeJournalRecord] = {}
        self._downstream_warnings: dict[str, tuple[str, ...]] = {}

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
                self._plans[key] = matches[0]

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
        outcome = self._kr380.get(plan.trade_plan_id)
        model = self._models.get(plan.trade_plan_id)
        position = self._positions.get(plan.trade_plan_id)
        closure = self._closures.get(plan.trade_plan_id)
        journal = self._journals.get(plan.trade_plan_id)
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
            "risk_result_id": risk_id,
            "sponsor_controls_available": False,
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


def _risk_binding(plan: TradePlanRecord, risk: RiskApproval) -> bool:
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
    return (
        risk_result_id is not None
        and risk_state in {RiskState.APPROVED, RiskState.CONSTRAINED}
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
]
