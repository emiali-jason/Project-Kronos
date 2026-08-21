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
    sponsor_controls_available: bool = False
    kr380_entry_timing_state: str = "NOT ESTABLISHED"

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
            or self.sponsor_controls_available
            or self.kr380_entry_timing_state != "NOT ESTABLISHED"
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
        )

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


__all__ = [
    "NativeTradeWindowProjection",
    "SwingTradeWindowWorkflow",
    "TradeWindowState",
]
