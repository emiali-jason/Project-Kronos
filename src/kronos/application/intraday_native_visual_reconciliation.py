"""Provider-independent WO-10 reconciliation application/control seam."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Callable

from kronos.intraday.native_visual_reconciliation import (
    CurrentReconciliationPointer,
    ReconciliationError,
    ReconciliationFailure,
    ReconciliationPointerEntry,
    ReconciliationRun,
    create_current_reconciliation_pointer,
    create_v1_reconciliation_policy,
    reconcile_native_visual_evidence,
)
from kronos.intraday.native_visual_reconciliation_persistence import (
    IntradayNativeVisualReconciliationStore,
)
from kronos.intraday.probables import ProbableState, ProbablesRun
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_persistence import IntradayReviewStore


class ReconciliationMemberState(StrEnum):
    RECONCILED = "RECONCILED"
    ALREADY_RECONCILED = "ALREADY_RECONCILED"
    SKIPPED_VISUAL_EVIDENCE_REQUIRED = "SKIPPED_VISUAL_EVIDENCE_REQUIRED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ReconciliationCandidateSnapshot:
    canonical_subject_identity: str
    inherited_direction: str
    probable_result_identity: str
    review_cycle_identity: str | None
    review_pack_identity: str | None
    visual_evidence_identity: str | None
    reconciliation_run_identity: str | None
    review_state: str
    readiness_state: str
    promotion_state: str
    remaining_conditions: tuple[tuple[str, str, str], ...]
    facts: tuple[tuple[str, str, str, str, str], ...]


@dataclass(frozen=True, slots=True)
class ReconciliationSnapshot:
    current_probables_run_identity: str | None
    policy_identity: str
    policy_version: str
    policy_checksum_sha256: str
    candidates: tuple[ReconciliationCandidateSnapshot, ...]
    provider_calls: int = 0
    discovery_operations: int = 0
    probables_operations: int = 0
    chart_analyst_calls: int = 0
    answer_imports: int = 0


@dataclass(frozen=True, slots=True)
class ReconciliationMemberResult:
    canonical_subject_identity: str
    review_cycle_identity: str | None
    state: ReconciliationMemberState
    reconciliation_run_identity: str | None = None
    review_state: str | None = None
    readiness_state: str | None = None
    promotion_state: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationBatchResult:
    members: tuple[ReconciliationMemberResult, ...]

    def count(self, state: ReconciliationMemberState) -> int:
        return sum(item.state is state for item in self.members)


class IntradayNativeVisualReconciliationApplication:
    """Reconcile only explicit, exact-current Review cycles on Sponsor command."""

    def __init__(
        self,
        *,
        current_probables: Callable[[], ProbablesRun | None],
        review_store: IntradayReviewStore,
        store: IntradayNativeVisualReconciliationStore,
    ) -> None:
        if not callable(current_probables) or type(review_store) is not IntradayReviewStore or type(store) is not IntradayNativeVisualReconciliationStore:
            raise ValueError("INTRADAY_RECONCILIATION_APPLICATION_INVALID")
        self._current_probables = current_probables
        self._review_store = review_store
        self._store = store
        self._policy = create_v1_reconciliation_policy()
        self._lock = RLock()

    @property
    def store(self) -> IntradayNativeVisualReconciliationStore:
        return self._store

    def snapshot(self) -> ReconciliationSnapshot:
        with self._lock:
            run = self._current_probables()
            pointer = self._store.load_current()
            current = pointer if run is not None and pointer is not None and pointer.probables_run_identity == run.run_identity else None
            entries = {} if current is None else {item.probable_result_identity: item for item in current.entries}
            review_pointer = self._review_store.load_current()
            review_entries = (
                {}
                if run is None or review_pointer is None or review_pointer.probables_run_identity != run.run_identity
                else {item.probable_result_identity: item for item in review_pointer.cycles}
            )
            candidates = tuple(
                self._candidate(result, review_entries.get(result.result_identity), entries.get(result.result_identity))
                for result in (() if run is None else run.results)
                if result.state in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
            )
            return ReconciliationSnapshot(
                current_probables_run_identity=None if run is None else run.run_identity,
                policy_identity=self._policy.policy_identity,
                policy_version=self._policy.policy_version,
                policy_checksum_sha256=self._policy.methodology_checksum_sha256,
                candidates=candidates,
            )

    def reconcile(self, cycle_identity: str) -> ReconciliationMemberResult:
        with self._lock:
            run = self._require_current_run()
            review_pointer = self._review_store.load_current()
            if review_pointer is None or review_pointer.probables_run_identity != run.run_identity:
                raise ReconciliationError(ReconciliationFailure.NOT_CURRENT)
            cycle_pointer = next((item for item in review_pointer.cycles if item.cycle_identity == cycle_identity), None)
            if cycle_pointer is None:
                raise ReconciliationError(ReconciliationFailure.NOT_CURRENT)
            probable = next((item for item in run.results if item.result_identity == cycle_pointer.probable_result_identity), None)
            if probable is None or probable.state not in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}:
                raise ReconciliationError(ReconciliationFailure.NOT_CURRENT)
            if cycle_pointer.active_review_pack_identity is None:
                return self._skipped(probable.canonical_subject_identity, cycle_identity)
            try:
                cycle = self._review_store.load_cycle(cycle_identity)
                pack = self._review_store.load_pack(cycle_pointer.active_review_pack_identity)
                evidence = self._load_visual_evidence(pack.review_pack_identity)
                if evidence is None:
                    return self._skipped(probable.canonical_subject_identity, cycle_identity)
            except ReviewError as error:
                raise _translate(error) from error
            current = self._pointer_for_run(run)
            existing = next((item for item in current.entries if item.probable_result_identity == probable.result_identity), None)
            if (
                existing is not None
                and existing.review_cycle_identity == cycle_identity
                and existing.review_pack_identity == pack.review_pack_identity
                and existing.visual_evidence_identity == evidence.visual_evidence_identity
            ):
                restored = self._store.load_run(existing.reconciliation_run_identity)
                self._validate_entry(existing, restored)
                return self._result(restored, ReconciliationMemberState.ALREADY_RECONCILED)
            result = reconcile_native_visual_evidence(
                policy=self._policy,
                probables_run=run,
                probable=probable,
                cycle=cycle,
                question_pack=pack,
                visual_evidence=evidence,
            )
            self._store.retain_complete(result, self._policy)
            entry = ReconciliationPointerEntry(
                probable_result_identity=probable.result_identity,
                review_cycle_identity=cycle_identity,
                review_pack_identity=pack.review_pack_identity,
                visual_evidence_identity=evidence.visual_evidence_identity,
                reconciliation_run_identity=result.run_identity,
                canonical_subject_identity=probable.canonical_subject_identity,
                inherited_direction=probable.direction.value,
            )
            retained = tuple(item for item in current.entries if item.probable_result_identity != probable.result_identity)
            self._store.save_current(create_current_reconciliation_pointer(run.run_identity, (*retained, entry)))
            return self._result(result, ReconciliationMemberState.RECONCILED)

    def reconcile_all_ready(self) -> ReconciliationBatchResult:
        with self._lock:
            run = self._require_current_run()
            review_pointer = self._review_store.load_current()
            review_entries = (
                ()
                if review_pointer is None or review_pointer.probables_run_identity != run.run_identity
                else review_pointer.cycles
            )
            by_result = {item.probable_result_identity: item for item in review_entries}
            results: list[ReconciliationMemberResult] = []
            for probable in sorted(
                (item for item in run.results if item.state in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}),
                key=lambda item: item.canonical_subject_identity,
            ):
                pointer = by_result.get(probable.result_identity)
                if pointer is None:
                    results.append(self._skipped(probable.canonical_subject_identity, None))
                    continue
                try:
                    results.append(self.reconcile(pointer.cycle_identity))
                except ReconciliationError as error:
                    results.append(ReconciliationMemberResult(
                        canonical_subject_identity=probable.canonical_subject_identity,
                        review_cycle_identity=pointer.cycle_identity,
                        state=ReconciliationMemberState.FAILED,
                        detail=error.failure.value,
                    ))
            return ReconciliationBatchResult(tuple(results))

    def _candidate(self, probable, review_entry, entry) -> ReconciliationCandidateSnapshot:  # type: ignore[no-untyped-def]
        pack_identity = None if review_entry is None else review_entry.active_review_pack_identity
        visual_identity = None
        if pack_identity is not None:
            try:
                cycle = self._review_store.load_cycle(review_entry.cycle_identity)
                pack = self._review_store.load_pack(pack_identity)
                if pack.review_cycle_identity != cycle.cycle_identity:
                    raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
                evidence = self._load_visual_evidence(pack_identity)
                visual_identity = None if evidence is None else evidence.visual_evidence_identity
            except ReviewError as error:
                raise _translate(error) from error
        if entry is None:
            return ReconciliationCandidateSnapshot(
                canonical_subject_identity=probable.canonical_subject_identity,
                inherited_direction=probable.direction.value,
                probable_result_identity=probable.result_identity,
                review_cycle_identity=None if review_entry is None else review_entry.cycle_identity,
                review_pack_identity=pack_identity,
                visual_evidence_identity=visual_identity,
                reconciliation_run_identity=None,
                review_state="NOT_ESTABLISHED",
                readiness_state="NOT_READY",
                promotion_state="NOT_PROMOTED",
                remaining_conditions=(),
                facts=(),
            )
        restored = self._store.load_run(entry.reconciliation_run_identity)
        self._validate_entry(entry, restored)
        if entry.review_pack_identity != pack_identity or entry.visual_evidence_identity != visual_identity:
            return ReconciliationCandidateSnapshot(
                canonical_subject_identity=probable.canonical_subject_identity,
                inherited_direction=probable.direction.value,
                probable_result_identity=probable.result_identity,
                review_cycle_identity=None if review_entry is None else review_entry.cycle_identity,
                review_pack_identity=pack_identity,
                visual_evidence_identity=visual_identity,
                reconciliation_run_identity=None,
                review_state="NOT_ESTABLISHED",
                readiness_state="NOT_READY",
                promotion_state="NOT_PROMOTED",
                remaining_conditions=(),
                facts=(),
            )
        return ReconciliationCandidateSnapshot(
            canonical_subject_identity=probable.canonical_subject_identity,
            inherited_direction=restored.inherited_direction,
            probable_result_identity=probable.result_identity,
            review_cycle_identity=restored.review_cycle_identity,
            review_pack_identity=restored.review_pack_identity,
            visual_evidence_identity=restored.visual_evidence_identity,
            reconciliation_run_identity=restored.run_identity,
            review_state=restored.review_state.state.value,
            readiness_state=restored.readiness.state.value,
            promotion_state=restored.promotion.state.value,
            remaining_conditions=tuple((item.condition_identity.value, item.classification.value, item.source_question_id) for item in restored.remaining_conditions),
            facts=tuple((item.question_id, item.observation_status.value, "UNAVAILABLE" if item.answer is None else item.answer, item.relationship.value, item.role.value) for item in restored.facts),
        )

    def _pointer_for_run(self, run: ProbablesRun) -> CurrentReconciliationPointer:
        pointer = self._store.load_current()
        return create_current_reconciliation_pointer(run.run_identity, ()) if pointer is None or pointer.probables_run_identity != run.run_identity else pointer

    def _load_visual_evidence(self, review_pack_identity: str):  # type: ignore[no-untyped-def]
        pointer = self._review_store.load_visual_evidence_pointer(review_pack_identity)
        if pointer is None:
            return None
        answer = self._review_store.load_answer_pack(pointer.answer_pack_identity)
        record = self._review_store.load_import_record(pointer.import_identity)
        evidence = self._review_store.load_visual_evidence(pointer.visual_evidence_identity)
        if (
            pointer.review_pack_identity != review_pack_identity
            or record.review_pack_identity != review_pack_identity
            or record.answer_pack_identity != answer.answer_pack_identity
            or record.visual_evidence_identity != evidence.visual_evidence_identity
            or evidence.review_pack_identity != review_pack_identity
            or evidence.answer_pack_identity != answer.answer_pack_identity
            or evidence.review_cycle_identity != pointer.review_cycle_identity
            or evidence.chart_revision_identity != pointer.chart_revision_identity
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)
        return evidence

    def _require_current_run(self) -> ProbablesRun:
        run = self._current_probables()
        if run is None:
            raise ReconciliationError(ReconciliationFailure.NOT_CURRENT)
        return run

    @staticmethod
    def _validate_entry(entry: ReconciliationPointerEntry, run: ReconciliationRun) -> None:
        if (
            entry.reconciliation_run_identity != run.run_identity
            or entry.probable_result_identity != run.probable_result_identity
            or entry.review_cycle_identity != run.review_cycle_identity
            or entry.review_pack_identity != run.review_pack_identity
            or entry.visual_evidence_identity != run.visual_evidence_identity
            or entry.canonical_subject_identity != run.canonical_subject_identity
            or entry.inherited_direction != run.inherited_direction
        ):
            raise ReconciliationError(ReconciliationFailure.INTEGRITY_INVALID)

    @staticmethod
    def _result(run: ReconciliationRun, state: ReconciliationMemberState) -> ReconciliationMemberResult:
        return ReconciliationMemberResult(
            canonical_subject_identity=run.canonical_subject_identity,
            review_cycle_identity=run.review_cycle_identity,
            state=state,
            reconciliation_run_identity=run.run_identity,
            review_state=run.review_state.state.value,
            readiness_state=run.readiness.state.value,
            promotion_state=run.promotion.state.value,
        )

    @staticmethod
    def _skipped(subject: str, cycle: str | None) -> ReconciliationMemberResult:
        return ReconciliationMemberResult(
            canonical_subject_identity=subject,
            review_cycle_identity=cycle,
            state=ReconciliationMemberState.SKIPPED_VISUAL_EVIDENCE_REQUIRED,
            detail=ReconciliationFailure.EVIDENCE_INCOMPLETE.value,
        )


def _translate(error: ReviewError) -> ReconciliationError:
    failure = (
        ReconciliationFailure.ARTIFACT_UNAVAILABLE
        if error.failure is ReviewFailure.ARTIFACT_UNAVAILABLE
        else ReconciliationFailure.INTEGRITY_INVALID
    )
    return ReconciliationError(failure)


__all__ = [
    "IntradayNativeVisualReconciliationApplication", "ReconciliationBatchResult",
    "ReconciliationCandidateSnapshot", "ReconciliationMemberResult",
    "ReconciliationMemberState", "ReconciliationSnapshot",
]
