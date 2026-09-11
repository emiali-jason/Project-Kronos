"""Application seam for explicit WO-07F visual reconciliation actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.intraday.review import ReviewError
from kronos.intraday.review_mcx_paired_persistence import (
    IntradayMcxPairedReviewStore,
)
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.visual_contract_v2 import VisualObservationV2
from kronos.intraday.visual_reconciliation_v2 import (
    AnchorState,
    GovernedAnchorContext,
    NativeMarketAuthority,
    POLICY_IDENTITY,
    POLICY_VERSION,
    Q10Classification,
    ReconciliationPrerequisites,
    VisualReconciliationInput,
    VisualReconciliationOutcome,
    create_reconciliation_record,
    evaluate_visual_reconciliation,
)
from kronos.intraday.visual_reconciliation_v2_persistence import VisualReconciliationStore


@dataclass(frozen=True, slots=True)
class CandidateReconciliationStatus:
    canonical_subject_identity: str
    review_cycle_identity: str
    visual_evidence_identity: str | None
    readiness: str
    reconciliation_identity: str | None
    outcome: str | None
    reason_codes: tuple[str, ...]
    downstream_eligibility: str | None


@dataclass(frozen=True, slots=True)
class CurrentReconciliationStatus:
    current_review_pointer: str | None
    policy_identity: str
    policy_version: str
    candidate_count: int
    eligible_count: int
    reconciled_count: int
    candidates: tuple[CandidateReconciliationStatus, ...]

    def document(self) -> dict[str, object]:
        return {
            "current_review_pointer": self.current_review_pointer,
            "policy_identity": self.policy_identity,
            "policy_version": self.policy_version,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
            "reconciled_count": self.reconciled_count,
            "candidates": tuple(
                {
                    "canonical_subject_identity": item.canonical_subject_identity,
                    "review_cycle_identity": item.review_cycle_identity,
                    "visual_evidence_identity": item.visual_evidence_identity,
                    "readiness": item.readiness,
                    "reconciliation_identity": item.reconciliation_identity,
                    "outcome": item.outcome,
                    "reason_codes": item.reason_codes,
                    "downstream_eligibility": item.downstream_eligibility,
                }
                for item in self.candidates
            ),
        }


class IntradayVisualReconciliationV2Application:
    """Read exact accepted evidence and persist only on Sponsor action."""

    def __init__(
        self,
        *,
        review: IntradayReviewV2Application,
        review_store: IntradayReviewV2Store,
        paired_store: IntradayMcxPairedReviewStore,
        store: VisualReconciliationStore,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if (
            type(review) is not IntradayReviewV2Application
            or type(review_store) is not IntradayReviewV2Store
            or type(paired_store) is not IntradayMcxPairedReviewStore
            or type(store) is not VisualReconciliationStore
            or not callable(clock)
        ):
            raise ValueError("WO07F_APPLICATION_INVALID")
        self._review = review
        self._review_store = review_store
        self._paired_store = paired_store
        self._store = store
        self._clock = clock
        self._lock = review_store.workspace_lock

    @property
    def store(self) -> VisualReconciliationStore:
        return self._store

    def status(self) -> CurrentReconciliationStatus:
        """Restore exact current results without evaluating or writing."""

        with self._lock:
            snapshot = self._review.snapshot()
            candidates = []
            eligible = 0
            reconciled = 0
            for candidate in snapshot.candidates:
                record = self._store.restore_current(candidate.cycle_identity)
                if record is not None and (
                    record.visual_evidence_identity != candidate.visual_evidence_identity
                    or record.chart_revision_identity != candidate.chart_revision_identity
                    or record.probables_run_identity != snapshot.probables_run_identity
                ):
                    record = None
                ready = candidate.visual_evidence_identity is not None
                if ready:
                    eligible += 1
                if record is not None:
                    reconciled += 1
                candidates.append(
                    CandidateReconciliationStatus(
                        canonical_subject_identity=candidate.canonical_subject_identity,
                        review_cycle_identity=candidate.cycle_identity,
                        visual_evidence_identity=candidate.visual_evidence_identity,
                        readiness="READY" if ready else "EVIDENCE_REQUIRED",
                        reconciliation_identity=(
                            None if record is None else record.reconciliation_identity
                        ),
                        outcome=None if record is None else record.outcome.value,
                        reason_codes=(
                            ()
                            if record is None
                            else tuple(item.reason_code for item in record.reasons)
                        ),
                        downstream_eligibility=(
                            None
                            if record is None
                            else record.downstream_eligibility.value
                        ),
                    )
                )
            return CurrentReconciliationStatus(
                current_review_pointer=snapshot.current_pointer_identity,
                policy_identity=POLICY_IDENTITY,
                policy_version=POLICY_VERSION,
                candidate_count=len(snapshot.candidates),
                eligible_count=eligible,
                reconciled_count=reconciled,
                candidates=tuple(candidates),
            )

    def evaluate_current_read_only(self) -> tuple[dict[str, object], ...]:
        """Qualification projection: evaluate retained evidence without persistence."""

        with self._lock:
            snapshot = self._review.snapshot()
            results = []
            for candidate in snapshot.candidates:
                if candidate.visual_evidence_identity is None:
                    results.append(
                        {
                            "canonical_subject_identity": candidate.canonical_subject_identity,
                            "outcome": VisualReconciliationOutcome.NOT_RECONCILABLE.value,
                            "reason_codes": ("ANSWER_NOT_ACCEPTED",),
                        }
                    )
                    continue
                decision = evaluate_visual_reconciliation(
                    self._input(candidate.cycle_identity)
                )
                results.append(
                    {
                        "canonical_subject_identity": candidate.canonical_subject_identity,
                        "outcome": decision.outcome.value,
                        "reason_codes": tuple(
                            item.reason_code for item in decision.reasons
                        ),
                        "downstream_eligibility": decision.downstream_eligibility.value,
                    }
                )
            return tuple(results)

    def reconcile_all_ready(self) -> dict[str, object]:
        """Explicit candidate-isolated batch; it never invokes WO-10."""

        with self._lock, self._review.probables_store.current_generation_guard():
            before = self._review.snapshot()
            results: list[dict[str, object]] = []
            for candidate in before.candidates:
                if candidate.visual_evidence_identity is None:
                    results.append(
                        {
                            "canonical_subject_identity": candidate.canonical_subject_identity,
                            "state": "NOT_RECONCILABLE",
                            "reason": "ANSWER_NOT_ACCEPTED",
                        }
                    )
                    continue
                try:
                    value = self._input(candidate.cycle_identity)
                    record = create_reconciliation_record(
                        value, created_at=self._clock()
                    )
                    record, state = self._store.retain(record)
                    results.append(
                        {
                            "canonical_subject_identity": candidate.canonical_subject_identity,
                            "state": state,
                            "reconciliation_identity": record.reconciliation_identity,
                            "outcome": record.outcome.value,
                            "reason_codes": tuple(
                                item.reason_code for item in record.reasons
                            ),
                            "downstream_eligibility": record.downstream_eligibility.value,
                        }
                    )
                except (ReviewError, ValueError, OSError) as error:
                    results.append(
                        {
                            "canonical_subject_identity": candidate.canonical_subject_identity,
                            "state": "NOT_RECONCILABLE",
                            "reason": str(error),
                        }
                    )
            after = self._review.snapshot()
            source_changed = (
                after.current_pointer_identity != before.current_pointer_identity
                or tuple(item.cycle_identity for item in after.candidates)
                != tuple(item.cycle_identity for item in before.candidates)
            )
            success = sum(
                item["state"] in {"RECONCILED", "ALREADY_RECONCILED"}
                for item in results
            )
            return {
                "outcome": (
                    "SOURCE_CHANGED"
                    if source_changed
                    else "COMPLETED"
                    if success == len(results) and results
                    else "PARTIAL"
                ),
                "policy_identity": POLICY_IDENTITY,
                "policy_version": POLICY_VERSION,
                "candidate_count": len(results),
                "success_count": success,
                "failure_count": len(results) - success,
                "results": tuple(results),
            }

    def _input(self, cycle_identity: str) -> VisualReconciliationInput:
        cycle = self._review_store.load_cycle(cycle_identity)
        current = self._review_store.load_current_chart(cycle_identity)
        if current is None:
            raise ValueError("WO07F_CHART_REVISION_NOT_BOUND")
        chart = self._review_store.load_chart(current.chart_revision_identity)
        if cycle.canonical_subject_identity.startswith("MCX-SUBJECT-"):
            return self._mcx_input(cycle, chart)
        return self._nse_input(cycle, chart)

    def _nse_input(self, cycle, chart) -> VisualReconciliationInput:
        evidence = self._find_nse_evidence(cycle, chart)
        observation = self._review_store.load_chart_input(chart)
        if observation is None:
            raise ValueError("WO07F_CORRESPONDENCE_NOT_CONFIRMED")
        observations = tuple(evidence.answers)
        q10 = next(item for item in observations if item.question_id == "Q10")
        return VisualReconciliationInput(
            canonical_subject_identity=cycle.canonical_subject_identity,
            proposed_direction=cycle.direction,
            probables_run_identity=cycle.probables_run_identity,
            probable_result_identity=cycle.probable_result_identity,
            review_cycle_identity=cycle.cycle_identity,
            review_pack_identity=evidence.review_pack_identity,
            chart_revision_identity=chart.chart_revision_identity,
            answer_pack_identity=evidence.answer_pack_identity,
            answer_source_sha256=evidence.answer_source_sha256,
            visual_evidence_identity=evidence.visual_evidence_identity,
            correspondence_identity=observation.identity,
            machine_evidence_identities=_machine_evidence(cycle),
            observations=observations,
            anchor=GovernedAnchorContext(AnchorState.NOT_ESTABLISHED),
            q10_classification=(
                Q10Classification.NOT_APPLICABLE
                if q10.answer == "NONE"
                else Q10Classification.NOT_DETERMINISTICALLY_CLASSIFIABLE
            ),
        )

    def _find_nse_evidence(self, cycle, chart):
        matches = []
        directory = self._review_store.root / "visual-evidence"
        for path in directory.glob("*.json") if directory.exists() else ():
            evidence = self._review_store.load_visual_evidence(path.stem)
            if (
                evidence.review_cycle_identity == cycle.cycle_identity
                and evidence.chart_revision_identity == chart.chart_revision_identity
            ):
                matches.append(evidence)
        if len(matches) != 1:
            raise ValueError("WO07F_ACCEPTED_ANSWER_NOT_UNIQUE")
        evidence = matches[0]
        if any(type(item) is not VisualObservationV2 for item in evidence.answers):
            raise ValueError("WO07F_VISUAL_CONTRACT_V2_REQUIRED")
        return evidence

    def _mcx_input(self, cycle, chart) -> VisualReconciliationInput:
        matches = []
        directory = self._paired_store.root / "imported-visual-evidence"
        for path in directory.glob("*.json") if directory.exists() else ():
            evidence = self._paired_store.load_evidence(path.stem)
            if (
                evidence.review_cycle_identity == cycle.cycle_identity
                and evidence.paired_bundle_identity == chart.paired_bundle_identity
            ):
                matches.append(evidence)
        if len(matches) != 1:
            raise ValueError("WO07F_ACCEPTED_ANSWER_NOT_UNIQUE")
        evidence = matches[0]
        native = tuple(evidence.native_answers)
        reference = tuple(evidence.reference_answers) + tuple(
            evidence.cross_market_answers or ()
        ) + (evidence.escape_hatch_answer,)
        if any(type(item) is not VisualObservationV2 for item in native + reference):
            raise ValueError("WO07F_VISUAL_CONTRACT_V2_REQUIRED")
        if evidence.chart_correspondence is None:
            raise ValueError("WO07F_CORRESPONDENCE_NOT_CONFIRMED")
        correspondence_identity = "|".join(
            item[4] for item in evidence.chart_correspondence if item[4] is not None
        )
        if not correspondence_identity:
            raise ValueError("WO07F_CORRESPONDENCE_NOT_CONFIRMED")
        escape = evidence.escape_hatch_answer
        return VisualReconciliationInput(
            canonical_subject_identity=cycle.canonical_subject_identity,
            proposed_direction=cycle.direction,
            probables_run_identity=cycle.probables_run_identity,
            probable_result_identity=cycle.probable_result_identity,
            review_cycle_identity=cycle.cycle_identity,
            review_pack_identity=evidence.review_pack_identity,
            chart_revision_identity=chart.chart_revision_identity,
            answer_pack_identity=evidence.answer_pack_identity,
            answer_source_sha256=evidence.answer_source_sha256,
            visual_evidence_identity=evidence.visual_evidence_identity,
            correspondence_identity=correspondence_identity,
            machine_evidence_identities=_machine_evidence(cycle)
            + (
                evidence.actual_derivative_contract_identity,
                evidence.active_binding_identity,
            ),
            observations=native,
            prerequisites=ReconciliationPrerequisites(
                native_mcx_contract_bound=bool(
                    evidence.actual_derivative_contract_identity
                    and evidence.active_binding_identity
                )
            ),
            anchor=GovernedAnchorContext(AnchorState.NOT_ESTABLISHED),
            q10_classification=(
                Q10Classification.NOT_APPLICABLE
                if escape.answer == "NONE"
                else Q10Classification.NOT_DETERMINISTICALLY_CLASSIFIABLE
            ),
            native_market=NativeMarketAuthority.MCX,
            supporting_reference_observations=reference,
            supporting_reference_authority=evidence.reference_role,
            supporting_reference_independence=(
                evidence.reference_independent_correspondence
            ),
            natgas_commissioning_state=(
                "HELD"
                if cycle.canonical_subject_identity == "MCX-SUBJECT-NATGAS"
                else None
            ),
        )


def _machine_evidence(cycle) -> tuple[str, ...]:
    return (
        cycle.probable_result_identity,
        cycle.completed_evidence_selection_identity,
        cycle.completed_evidence_integrity_identity,
        cycle.semantic_evidence_identity,
        cycle.semantic_evidence_integrity_identity,
        cycle.source_discovery_run_identity,
        cycle.source_discovery_result_identity,
    )


__all__ = [
    "CandidateReconciliationStatus",
    "CurrentReconciliationStatus",
    "IntradayVisualReconciliationV2Application",
]
