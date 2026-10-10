"""Projection-only Browser view models for persisted WO-09 authority."""

from __future__ import annotations

from dataclasses import dataclass, replace

from kronos.intraday.wo09_readiness import (
    CriterionState, CurrentnessState, ReadinessRecord, ReadinessState,
    RequirementRecord,
)
from kronos.intraday.wo09_persistence import Wo09Store

WO09_PRODUCT_ROUTE = "/intraday/wo09"


class IntradayWo09Projection:
    """Read persisted authority only; no evaluation path is exposed to Browser."""

    def __init__(self, store: Wo09Store, *, machine_successor: bool = False) -> None:
        if type(store) is not Wo09Store:
            raise ValueError("WO09_BROWSER_STORE_INVALID")
        if type(machine_successor) is not bool:
            raise ValueError("WO09_BROWSER_SUCCESSOR_MODE_INVALID")
        self.store = store
        self.machine_successor = machine_successor

    def status_document(self) -> dict[str, object]:
        cards = []
        details = {}
        historical_cards = []
        historical_details = {}
        for pointer, record in self.store.restore_current():
            requirements = self.store.load_requirements(record.readiness_identity)
            card = project_card(record, requirements, currentness=pointer.currentness)
            detail = project_analysis_details(record, requirements)
            if self.machine_successor and record.source_authority == "WO07F":
                # The retained pointer is evidence of its original publication, not
                # new-work authority after retirement of the visual production path.
                historical_cards.append(replace(card,
                    monitorability_state="HISTORICAL_ONLY", attention_state="NONE",
                    next_action="HISTORICAL_EVIDENCE_ONLY"))
                detail["F. WHAT HAPPENS NEXT"] = "HISTORICAL_EVIDENCE_ONLY"
                historical_details[record.readiness_identity] = detail
            else:
                cards.append(card)
                details[record.readiness_identity] = detail
        active = active_attention_cards(tuple(cards))
        return {
            "authority_owner": "INTRADAY_WO09",
            "cards": tuple(cards),
            "active_attention": active,
            "analysis_details": details,
            "historical_cards": tuple(historical_cards),
            "historical_analysis_details": historical_details,
            "provider_calls": 0,
            "calculations": 0,
        }


@dataclass(frozen=True, slots=True)
class Wo09SponsorCard:
    readiness_identity: str
    instrument: str
    direction: str
    wo07f_state: str
    readiness_state: str
    score: str
    outstanding_count: str
    highest_priority_outstanding: tuple[str, ...]
    requirements: tuple[dict[str, object], ...]
    monitorability_state: str
    attention_state: str
    next_action: str
    analysis_details_action: str = "VIEW ANALYSIS DETAILS"
    source_authority: str = "WO07F"
    assessment_state: str | None = None
    probables_run_identity: str | None = None
    analysis_boundary: str | None = None
    created_at: str | None = None


def project_card(record: ReadinessRecord, requirements: tuple[RequirementRecord, ...], *,
                 currentness: CurrentnessState | None = None) -> Wo09SponsorCard:
    from kronos.intraday.wo09_machine_readiness import MachineReadinessRecord
    if type(record) not in {ReadinessRecord, MachineReadinessRecord} or any(type(item) is not RequirementRecord for item in requirements):
        raise ValueError("WO09_BROWSER_PROJECTION_INPUT_INVALID")
    if {item.readiness_identity for item in requirements} != {record.readiness_identity}:
        raise ValueError("WO09_BROWSER_BINDING_INVALID")
    effective_currentness = record.currentness if currentness is None else currentness
    if type(effective_currentness) is not CurrentnessState:
        raise ValueError("WO09_BROWSER_CURRENTNESS_INVALID")
    pending = tuple(
        item for item in requirements
        if item.criterion.state in {CriterionState.OUTSTANDING, CriterionState.UNAVAILABLE}
    )
    outstanding = tuple(
        item for item in pending if item.criterion.state is CriterionState.OUTSTANDING
    )
    return Wo09SponsorCard(
        readiness_identity=record.readiness_identity,
        source_authority=record.source_authority,
        probables_run_identity=record.probables_run_identity,
        analysis_boundary=record.analysis_boundary.isoformat(),
        created_at=record.created_at.isoformat(),
        assessment_state=getattr(record, "assessment_disposition", None),
        instrument=record.canonical_subject_identity, direction=record.direction,
        wo07f_state="HISTORICAL_ONLY" if record.wo07f_outcome is None else record.wo07f_outcome.value,
        readiness_state=record.readiness_state.value,
        score="NOT_APPLICABLE" if record.satisfied_count is None else f"{record.satisfied_count} / 5",
        outstanding_count="NOT_APPLICABLE" if record.outstanding_count is None else str(record.outstanding_count),
        highest_priority_outstanding=tuple(item.criterion.criterion_id.value for item in outstanding[:2]),
        requirements=tuple({
            "criterion": item.criterion.criterion_id.value,
            "state": item.criterion.state.value,
            "current": item.criterion.current_value,
            "required": item.criterion.required_value,
            "gap": item.criterion.gap,
            "monitorability": tuple(value.value for value in item.criterion.monitorability),
        } for item in pending),
        monitorability_state=effective_currentness.value,
        attention_state=record.attention_state.value,
        next_action=(
            "GOVERNED_REASSESSMENT_REQUIRED"
            if effective_currentness is not CurrentnessState.CURRENT
            else _next_action(record)
        ),
    )


def project_analysis_details(record: ReadinessRecord, requirements: tuple[RequirementRecord, ...]) -> dict[str, object]:
    """Seven progressive-disclosure sections with no domain calculation."""
    by_id = {item.criterion.criterion_id.value: item.criterion for item in requirements}
    if record.source_authority == "WO08":
        return {
            "A. MACHINE WO08 ASSESSMENT": {
                "identity": record.wo08_identity, "integrity": record.wo08_integrity,
                "disposition": record.assessment_disposition,
                "methodology": record.methodology_identity, "version": record.methodology_version,
                "failure_stage": record.failure_stage, "failure_reason": record.failure_reason,
                "criteria": {key: {"state": value.state.value, "current": value.current_value}
                             for key, value in by_id.items()},
            },
            "B. WO09 READINESS": {"state": record.readiness_state.value,
                "satisfied": record.satisfied_count, "outstanding": record.outstanding_count},
            "C. AUTHORITY BOUNDARY": "Chart Analyst is not required. No trade, PAPER or broker authority.",
            "D. HISTORICAL VISUAL EVIDENCE": "Retained separately; retired for new Intraday production.",
            "E. EVIDENCE LINEAGE": {"readiness_identity": record.readiness_identity,
                "probables_run_identity": record.probables_run_identity,
                "probable_result_identity": record.probable_result_identity,
                "machine_evidence_identities": record.machine_evidence_identities,
                "analysis_boundary": record.analysis_boundary.isoformat(),
                "session_identity": record.session_identity},
        }
    return {
        "A. WHAT NATIVE / MACHINE ANALYSIS SAYS": {
            "criteria": {key: value.current_value for key, value in by_id.items() if value.authority == "MACHINE"},
            "machine_evidence_identities": record.machine_evidence_identities,
            "machine_evidence_integrity": record.machine_evidence_integrity,
            "analysis_boundary": record.analysis_boundary.isoformat(),
            "session_identity": record.session_identity,
            "exact_mcx_contract_identity": record.exact_mcx_contract_identity,
            "exact_mcx_roll_lineage": record.exact_mcx_roll_lineage,
        },
        "B. WHAT CHART ANALYST SAYS": {
            "criteria": {
                key: value.current_value
                for key, value in by_id.items() if value.authority != "MACHINE"
            },
            "visual_evidence_identity": record.visual_evidence_identity,
            "visual_evidence_integrity": record.visual_evidence_integrity,
        },
        "C. WHAT WO-07F RECONCILED": {
            "outcome": record.wo07f_outcome.value,
            "identity": record.wo07f_identity,
            "integrity": record.wo07f_integrity,
            "correspondence_identity": record.correspondence_identity,
        },
        "D. WHAT WO-09 READINESS SAYS": {"state": record.readiness_state.value, "satisfied": record.satisfied_count, "outstanding": record.outstanding_count},
        "E. REQUIREMENTS TO PROGRESS": tuple(
            {
                "criterion": key, "state": value.state.value,
                "required": value.required_value, "gap": value.gap,
                "monitorability": tuple(item.value for item in value.monitorability),
                "next_reassessment_trigger": value.next_reassessment_trigger,
            }
            for key, value in by_id.items()
            if value.state in {CriterionState.OUTSTANDING, CriterionState.UNAVAILABLE}
        ),
        "F. WHAT HAPPENS NEXT": _next_action(record),
        "G. TECHNICAL EVIDENCE": {
            "policy": record.policy_identity, "version": record.policy_version,
            "policy_checksum": record.policy_checksum,
            "readiness_identity": record.readiness_identity,
            "readiness_integrity": record.integrity_identity,
            "probables_run_identity": record.probables_run_identity,
            "probable_result_identity": record.probable_result_identity,
            "review_cycle_identity": record.review_cycle_identity,
            "review_pack_identity": record.review_pack_identity,
            "chart_revision_identity": record.chart_revision_identity,
            "answer_pack_identity": record.answer_pack_identity,
            "answer_source_sha256": record.answer_source_sha256,
        },
    }


def active_attention_cards(cards: tuple[Wo09SponsorCard, ...]) -> tuple[Wo09SponsorCard, ...]:
    return tuple(card for card in cards if card.attention_state != "NONE")


def _next_action(record: ReadinessRecord) -> str:
    if record.readiness_state in {ReadinessState.BUY_NOW, ReadinessState.SELL_NOW}:
        return "NEXT_WO_HANDOFF_AVAILABLE"
    if record.readiness_state is ReadinessState.NO_FOCUS:
        return "RETAIN_FOR_RESEARCH_NO_ACTIVE_ATTENTION"
    if record.readiness_state is ReadinessState.HARD_GATE:
        return f"HARD_GATE:{record.hard_gate.value}"
    if record.readiness_state is ReadinessState.READINESS_UNAVAILABLE:
        return "REASSESS_WHEN_REQUIRED_EVIDENCE_AVAILABLE"
    return "GOVERNED_REASSESSMENT_REQUIRED"


__all__ = ["IntradayWo09Projection", "WO09_PRODUCT_ROUTE", "Wo09SponsorCard", "active_attention_cards", "project_analysis_details", "project_card"]
