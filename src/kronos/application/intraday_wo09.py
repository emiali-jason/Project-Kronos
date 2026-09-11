"""Application seam for explicit WO-09 evaluation and persisted projections."""

from __future__ import annotations

from datetime import datetime

from kronos.application.intraday_wo09_notifications import (
    project_notification, project_reassessment_notification,
)
from kronos.intraday.visual_reconciliation_v2 import VisualReconciliationRecord
from kronos.intraday.completed_evidence import CompletedEvidenceSelection
from kronos.intraday.probables_v2 import SemanticQualificationEvidenceV2
from kronos.intraday.review_mcx_paired_answer import McxPairedImportedVisualEvidence
from kronos.intraday.review_v2 import ImportedVisualEvidenceV2
from kronos.intraday.wo09_persistence import CurrentPointer, Wo09Store
from kronos.intraday.wo09_readiness import (
    AttentionState, CriterionState, CurrentnessState, NextWoHandoff, ReadinessRecord,
    RequirementRecord, Wo09Evidence, build_wo09_evidence,
    create_next_wo_handoff, evaluate_readiness,
)
from kronos.intraday.wo09_watch import (
    WatchState, Wo09Watch, create_watch, mark_disconnect_gap, transition_watch,
)


class IntradayWo09Application:
    """Execute only on an explicit caller request; construction/restoration is inert."""

    def __init__(self, store: Wo09Store) -> None:
        if type(store) is not Wo09Store:
            raise ValueError("WO09_APPLICATION_STORE_INVALID")
        self.store = store

    def evaluate_governed(
        self, record: VisualReconciliationRecord,
        semantic: SemanticQualificationEvidenceV2,
        selection: CompletedEvidenceSelection,
        visual: ImportedVisualEvidenceV2 | McxPairedImportedVisualEvidence,
        *, created_at: datetime,
        exact_mcx_contract_identity: str | None = None,
        exact_mcx_roll_lineage: str | None = None,
        natgas_commissioning_state: str | None = None,
    ) -> tuple[ReadinessRecord, tuple[RequirementRecord, ...]]:
        evidence = build_wo09_evidence(
            record, semantic, selection, visual,
            exact_mcx_contract_identity=exact_mcx_contract_identity,
            exact_mcx_roll_lineage=exact_mcx_roll_lineage,
            natgas_commissioning_state=natgas_commissioning_state,
        )
        readiness, requirements = evaluate_readiness(
            record, evidence, created_at=created_at
        )
        self.store.retain(readiness, requirements)
        notification = project_notification(readiness)
        if notification is not None:
            self.store.retain_notification(notification)
        return readiness, requirements

    def register_reassessment_watches(self, readiness: ReadinessRecord,
                                      requirements: tuple[RequirementRecord, ...], *,
                                      at: datetime) -> tuple[Wo09Watch, ...]:
        if readiness.attention_state not in {AttentionState.NORMAL, AttentionState.HIGH}:
            return ()
        watches = tuple(create_watch(
            readiness_identity=readiness.readiness_identity,
            criterion_id=item.criterion.criterion_id,
            subject=readiness.canonical_subject_identity,
            exact_contract=readiness.exact_mcx_contract_identity,
            source_fact_identity=item.criterion.source_evidence_identity,
            governed_trigger=item.criterion.next_reassessment_trigger,
            at=at,
        ) for item in requirements if item.criterion.state is CriterionState.OUTSTANDING)
        expected = tuple(
            item.watch_identity for item in requirements
            if item.criterion.state is CriterionState.OUTSTANDING
        )
        if tuple(item.watch_identity for item in watches) != expected:
            raise ValueError("WO09_REQUIREMENT_WATCH_BINDING_INVALID")
        for watch in watches:
            self.store.retain_watch(watch)
        return watches

    def mark_disconnect_stale(self, *, at: datetime) -> tuple[Wo09Watch, ...]:
        values = tuple(mark_disconnect_gap(item, at=at) for item in self.store.load_watches())
        for item in values:
            self.store.retain_watch(item)
        return values

    def record_reassessment_event(
        self,
        readiness: ReadinessRecord,
        watch: Wo09Watch,
        *,
        at: datetime,
        governed_event_evidence_identity: str,
    ) -> Wo09Watch:
        """Retain a governed trigger and notify; never rewrite readiness."""
        pointer = self.store.load_pointer(readiness.canonical_subject_identity)
        if (
            pointer is None
            or pointer.currentness is not CurrentnessState.CURRENT
            or pointer.readiness_identity != readiness.readiness_identity
            or pointer.readiness_integrity != readiness.integrity_identity
        ):
            raise ValueError("WO09_REASSESSMENT_SOURCE_NOT_CURRENT")
        triggered = transition_watch(
            watch, WatchState.TRIGGERED, at=at, governed_reassessment=True,
            reacquisition_identity=governed_event_evidence_identity,
        )
        self.store.retain_watch(triggered)
        self.store.retain_notification(
            project_reassessment_notification(readiness, triggered, effective_at=at)
        )
        return triggered

    def mark_reassessment_due(self, subject: str, *, at: datetime) -> CurrentPointer:
        pointer = self.store.mark_currentness(subject, CurrentnessState.REASSESSMENT_DUE, updated_at=at)
        record = self.store.load_readiness(pointer.readiness_identity)
        source = project_notification(record, currentness=pointer.currentness, effective_at=at)
        if source is not None:
            self.store.retain_notification(source)
        return pointer

    def create_handoff(self, readiness: ReadinessRecord, *, created_at: datetime,
                       first_five_of_five_at: datetime | None = None) -> NextWoHandoff:
        pointer = self.store.load_pointer(readiness.canonical_subject_identity)
        if pointer is None:
            raise ValueError("WO09_HANDOFF_CURRENT_POINTER_REQUIRED")
        handoff = create_next_wo_handoff(
            readiness, created_at=created_at,
            current_readiness_identity=pointer.readiness_identity,
            current_pointer_integrity=pointer.integrity_identity,
            currentness=pointer.currentness,
            superseded_readiness_identity=pointer.superseded_readiness_identity,
            first_five_of_five_at=first_five_of_five_at,
        )
        if self.store.load_pointer(readiness.canonical_subject_identity) != pointer:
            raise ValueError("WO09_HANDOFF_CURRENT_POINTER_CHANGED")
        self.store.retain_handoff(handoff)
        return handoff

    def restore(self) -> tuple[tuple[CurrentPointer, ReadinessRecord], ...]:
        return self.store.restore_current()


__all__ = ["IntradayWo09Application"]
