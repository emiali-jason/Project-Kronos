"""Application seam for explicit WO-09 evaluation and persisted projections."""

from __future__ import annotations

from datetime import datetime

from kronos.intraday.evidence_currentness import require_original_first_five

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

    def __init__(self, store: Wo09Store, *, eligibility=None) -> None:
        if type(store) is not Wo09Store:
            raise ValueError("WO09_APPLICATION_STORE_INVALID")
        self.store = store
        self.eligibility = eligibility

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
        from kronos.application.intraday_evidence_currentness import require_boundary
        boundary = require_boundary(self.eligibility)
        expected = boundary.capture_readiness(record=record, semantic=semantic, selection=selection,
            visual=visual, created_at=created_at, exact_mcx_contract_identity=exact_mcx_contract_identity,
            exact_mcx_roll_lineage=exact_mcx_roll_lineage, natgas_commissioning_state=natgas_commissioning_state)
        evidence = build_wo09_evidence(
            record, semantic, selection, visual,
            exact_mcx_contract_identity=exact_mcx_contract_identity,
            exact_mcx_roll_lineage=exact_mcx_roll_lineage,
            natgas_commissioning_state=natgas_commissioning_state,
        )
        readiness, requirements = evaluate_readiness(
            record, evidence, created_at=created_at
        )
        with boundary.final_readiness(expected) as mutation:
            mutation.retain_readiness(readiness, requirements)
        self.store.notify_publication(mutation.notices)
        notification = project_notification(readiness)
        if notification is not None:
            self.store.retain_notification(notification)
        return readiness, requirements

    def evaluate_wo08(self, assessment, *, created_at):
        """Ordinary Analysis is the only prospective observation producer."""
        from kronos.application.intraday_evidence_currentness import require_boundary
        from kronos.intraday.wo09_machine_readiness import evaluate_machine_readiness
        from kronos.intraday.wo08_experimental import ExperimentalWo08Assessment
        boundary = require_boundary(self.eligibility)
        experimental = type(assessment) is ExperimentalWo08Assessment
        observed_at = boundary.clock() if experimental else created_at
        expected = boundary.capture_wo08(assessment=assessment, created_at=observed_at)
        if experimental:
            with boundary.final_readiness(expected) as mutation:
                coordinator = getattr(self, 'experimental_watches', None)
                if coordinator is not None:
                    coordinator.before_analysis(expected.readiness)
                origin = boundary.experimental_origin(assessment)
                boundary.verify_retained_first_five(assessment, origin)
                readiness, requirements = mutation.retain_experimental(assessment, origin,
                    observed_at=boundary.clock())
        else:
            readiness, requirements = evaluate_machine_readiness(assessment, created_at=created_at)
            with boundary.final_readiness(expected) as mutation:
                mutation.retain_readiness(readiness, requirements)
        self.store.notify_publication(mutation.notices)
        if experimental:
            notification = project_notification(readiness)
            if notification is not None:
                self.store.retain_notification(notification)
            coordinator = getattr(self, 'experimental_watches', None)
            if coordinator is not None:
                coordinator.after_analysis(readiness, requirements)
        return readiness, requirements

    def register_reassessment_watches(self, readiness: ReadinessRecord,
                                      requirements: tuple[RequirementRecord, ...], *,
                                      at: datetime) -> tuple[Wo09Watch, ...]:
        from kronos.application.intraday_experimental_watch import is_experimental, watch_eligible
        experimental = is_experimental(readiness)
        if experimental:
            readiness.__post_init__()
            if not watch_eligible(readiness, at=at):
                return ()
            pointer = self.store.load_pointer(readiness.canonical_subject_identity)
            if (pointer is None or pointer.currentness is not CurrentnessState.CURRENT
                    or pointer.readiness_identity != readiness.readiness_identity
                    or pointer.readiness_integrity != readiness.integrity_identity):
                raise ValueError("WO09_WATCH_SOURCE_NOT_CURRENT")
            if requirements != self.store.load_requirements(readiness.readiness_identity):
                raise ValueError("WO09_REQUIREMENT_WATCH_BINDING_INVALID")
            existing = self.store.load_watches(readiness.readiness_identity)
            if existing:
                return tuple(w for w in existing if w.state is WatchState.ACTIVE)
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
            **(dict(policy_identity=readiness.policy_identity, policy_version=readiness.policy_version)
               if experimental else {}),
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
        from kronos.application.intraday_experimental_watch import is_experimental
        # Experimental hints are never notification or criterion-completion events.
        # The separately governed Analysis publication owns READY notifications.
        if not is_experimental(readiness):
            self.store.retain_notification(
                project_reassessment_notification(readiness, triggered, effective_at=at)
            )
        return triggered

    def mark_reassessment_due(self, subject: str, *, at: datetime) -> CurrentPointer:
        expected = self.store.expectation(subject)
        pointer = self.store.mark_currentness(subject, CurrentnessState.REASSESSMENT_DUE, updated_at=at, expected=expected)
        record = self.store.load_readiness(pointer.readiness_identity)
        source = project_notification(record, currentness=pointer.currentness, effective_at=at)
        if source is not None:
            self.store.retain_notification(source)
        return pointer

    def create_handoff(self, readiness: ReadinessRecord, *, created_at: datetime,
                       first_five_of_five_at: datetime | None = None) -> NextWoHandoff:
        from kronos.intraday.wo09_experimental import ExperimentalReadinessRecord
        from kronos.application.intraday_evidence_currentness import require_boundary
        if type(readiness) is ExperimentalReadinessRecord:
            boundary = require_boundary(self.eligibility)
            assessment = boundary.wo08.load(readiness.wo08_identity)
            # Capture full source expectation once. First-five and readiness must
            # already be durably published; a retained orphan fact is insufficient.
            with boundary._sources(readiness):
                generations = boundary._source(readiness, 'handoff')
                boundary._session(readiness, 'handoff')
                expected = self.store.expectation(readiness.canonical_subject_identity)
            from kronos.application.intraday_evidence_currentness import PublicationExpectation
            scope = PublicationExpectation('readiness', assessment.identity, readiness, generations, expected)
            with boundary.final_readiness(scope) as mutation:
                pointer = expected.pointer
                if pointer is None:
                    raise ValueError('WO09_HANDOFF_CURRENT_POINTER_REQUIRED')
                self.store.verify_first_five(readiness)
                handoff = create_next_wo_handoff(readiness, created_at=boundary.clock(),
                    current_readiness_identity=pointer.readiness_identity,
                    current_pointer_integrity=pointer.integrity_identity, currentness=pointer.currentness,
                    superseded_readiness_identity=pointer.superseded_readiness_identity,
                    first_five_of_five_at=first_five_of_five_at)
                mutation.retain_handoff(handoff)
            return handoff
        pointer = self.store.load_pointer(readiness.canonical_subject_identity)
        if pointer is None:
            raise ValueError('WO09_HANDOFF_CURRENT_POINTER_REQUIRED')
        handoff = create_next_wo_handoff(readiness, created_at=created_at,
            current_readiness_identity=pointer.readiness_identity,
            current_pointer_integrity=pointer.integrity_identity, currentness=pointer.currentness,
            superseded_readiness_identity=pointer.superseded_readiness_identity,
            first_five_of_five_at=first_five_of_five_at)
        require_original_first_five()
        self.store.retain_handoff(handoff, expected=self.store.expectation(readiness.canonical_subject_identity))
        return handoff

    def restore(self) -> tuple[tuple[CurrentPointer, ReadinessRecord], ...]:
        return self.store.restore_current()


__all__ = ["IntradayWo09Application"]
