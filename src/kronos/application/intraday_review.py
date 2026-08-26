"""Provider-independent application service for governed Intraday Review."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Callable

from kronos.intraday.probables import ProbableMemberResult, ProbableState, ProbablesRun
from kronos.intraday.review import (
    ChartRevision,
    CurrentReviewPointer,
    ReviewCycle,
    ReviewCyclePointer,
    ReviewError,
    ReviewFailure,
    ReviewQuestionPack,
    ReviewState,
    create_chart_revision,
    create_current_pointer,
    create_question_pack,
    create_review_cycle,
    create_review_handoff,
)
from kronos.intraday.review_pdf import IntradayReviewPdfTransport
from kronos.intraday.review_persistence import IntradayReviewStore, validate_chart_payload


@dataclass(frozen=True, slots=True)
class IntradayReviewCandidateSnapshot:
    canonical_subject_identity: str
    direction: str
    observation_boundary: datetime
    probables_run_identity: str
    probable_result_identity: str
    review_state: str
    cycle_identity: str | None
    chart_revision_identity: str | None
    chart_revision_ordinal: int | None
    review_pack_identity: str | None
    review_pack_filename: str | None


@dataclass(frozen=True, slots=True)
class IntradayReviewSnapshot:
    current_probables_run_identity: str | None
    candidates: tuple[IntradayReviewCandidateSnapshot, ...]
    question_outbox: str
    answer_inbox: str
    answer_import_active: bool = False
    provider_operations: int = 0
    discovery_operations: int = 0
    probables_operations: int = 0


class IntradayReviewApplication:
    """Bind exact-current persisted Probables to immutable visual-review evidence."""

    def __init__(
        self,
        *,
        current_probables: Callable[[], ProbablesRun | None],
        store: IntradayReviewStore,
        transport: IntradayReviewPdfTransport,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not callable(current_probables) or type(store) is not IntradayReviewStore or type(transport) is not IntradayReviewPdfTransport or not callable(clock):
            raise ValueError("INTRADAY_REVIEW_APPLICATION_INVALID")
        self._current_probables = current_probables
        self._store = store
        self._transport = transport
        self._clock = clock
        self._lock = RLock()

    def snapshot(self) -> IntradayReviewSnapshot:
        with self._lock:
            run = self._current_probables()
            pointer = self._store.load_current()
            current = None if run is None or pointer is None or pointer.probables_run_identity != run.run_identity else pointer
            pointers = {} if current is None else {item.probable_result_identity: item for item in current.cycles}
            candidates = tuple(
                self._candidate_snapshot(run, result, pointers.get(result.result_identity))
                for result in (() if run is None else run.results)
                if result.state in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
            )
            return IntradayReviewSnapshot(
                current_probables_run_identity=None if run is None else run.run_identity,
                candidates=candidates,
                question_outbox=str(self._transport.question_outbox),
                answer_inbox=str(self._transport.answer_inbox),
            )

    def start_review(self, probable_result_identity: str) -> ReviewCycle:
        with self._lock:
            run, result = self._current_result(probable_result_identity)
            pointer = self._pointer_for_run(run)
            existing = next((item for item in pointer.cycles if item.probable_result_identity == result.result_identity), None)
            if existing is not None:
                return self._store.load_cycle(existing.cycle_identity)
            handoff = create_review_handoff(run, result, created_at=self._clock())
            cycle = create_review_cycle(handoff)
            self._store.retain_handoff(handoff)
            self._store.retain_cycle(cycle)
            cycle_pointer = ReviewCyclePointer(
                cycle_identity=cycle.cycle_identity,
                probable_result_identity=result.result_identity,
                canonical_subject_identity=result.canonical_subject_identity,
                direction=cycle.direction,
                state=ReviewState.CHART_REQUIRED,
                active_chart_revision_identity=None,
                active_review_pack_identity=None,
            )
            self._store.save_current(create_current_pointer(run.run_identity, (*pointer.cycles, cycle_pointer)))
            return cycle

    def upload_chart(self, cycle_identity: str, *, media_type: str, payload: bytes) -> ChartRevision:
        with self._lock:
            validate_chart_payload(media_type, payload)
            run = self._require_current_run()
            pointer = self._pointer_for_run(run)
            item = self._cycle_pointer(pointer, cycle_identity)
            cycle = self._store.load_cycle(item.cycle_identity)
            if cycle.probables_run_identity != run.run_identity:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            digest = sha256(payload).hexdigest()
            active = None if item.active_chart_revision_identity is None else self._store.load_chart(item.active_chart_revision_identity)
            if active is not None and active.payload_sha256 == digest and active.media_type == media_type:
                return active
            chart = create_chart_revision(
                cycle,
                revision_ordinal=1 if active is None else active.revision_ordinal + 1,
                payload=payload,
                media_type=media_type,
                received_at=self._clock(),
            )
            self._store.retain_chart(chart, payload)
            updated = replace(
                item,
                state=ReviewState.CHART_READY,
                active_chart_revision_identity=chart.chart_revision_identity,
                active_review_pack_identity=None,
            )
            self._store.save_current(_replace_cycle(pointer, updated))
            return chart

    def create_question_pack(self, cycle_identity: str) -> tuple[ReviewQuestionPack, Path]:
        with self._lock:
            run = self._require_current_run()
            pointer = self._pointer_for_run(run)
            item = self._cycle_pointer(pointer, cycle_identity)
            if item.active_chart_revision_identity is None:
                raise ReviewError(ReviewFailure.CHART_REQUIRED)
            cycle = self._store.load_cycle(item.cycle_identity)
            chart = self._store.load_chart(item.active_chart_revision_identity)
            if item.active_review_pack_identity is None:
                handoff = self._store.load_handoff(cycle.handoff_identity)
                pack = create_question_pack(handoff, cycle, chart)
                self._store.retain_pack(pack)
                updated = replace(
                    item,
                    state=ReviewState.QUESTION_PACK_CREATED,
                    active_review_pack_identity=pack.review_pack_identity,
                )
                self._store.save_current(_replace_cycle(pointer, updated))
            else:
                pack = self._store.load_pack(item.active_review_pack_identity)
                if pack.chart_revision_identity != chart.chart_revision_identity:
                    raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            exported = self._transport.export(pack, self._store.load_chart_bytes(chart))
            return pack, exported

    def _candidate_snapshot(
        self,
        run: ProbablesRun,
        result: ProbableMemberResult,
        pointer: ReviewCyclePointer | None,
    ) -> IntradayReviewCandidateSnapshot:
        chart = None if pointer is None or pointer.active_chart_revision_identity is None else self._store.load_chart(pointer.active_chart_revision_identity)
        pack = None if pointer is None or pointer.active_review_pack_identity is None else self._store.load_pack(pointer.active_review_pack_identity)
        filename = None
        if pack is not None:
            from kronos.intraday.review_pdf import question_pack_filename

            filename = question_pack_filename(pack)
        return IntradayReviewCandidateSnapshot(
            canonical_subject_identity=result.canonical_subject_identity,
            direction=result.direction.value if result.direction is not None else "UNAVAILABLE",
            observation_boundary=result.observation_boundary,
            probables_run_identity=run.run_identity,
            probable_result_identity=result.result_identity,
            review_state="REVIEW_REQUIRED" if pointer is None else pointer.state.value,
            cycle_identity=None if pointer is None else pointer.cycle_identity,
            chart_revision_identity=None if chart is None else chart.chart_revision_identity,
            chart_revision_ordinal=None if chart is None else chart.revision_ordinal,
            review_pack_identity=None if pack is None else pack.review_pack_identity,
            review_pack_filename=filename,
        )

    def _current_result(self, identity: str) -> tuple[ProbablesRun, ProbableMemberResult]:
        run = self._require_current_run()
        result = next((item for item in run.results if item.result_identity == identity), None)
        if result is None:
            raise ReviewError(ReviewFailure.NOT_CURRENT)
        if result.state not in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}:
            raise ReviewError(ReviewFailure.NOT_ELIGIBLE)
        return run, result

    def _require_current_run(self) -> ProbablesRun:
        run = self._current_probables()
        if run is None:
            raise ReviewError(ReviewFailure.NOT_CURRENT)
        return run

    def _pointer_for_run(self, run: ProbablesRun) -> CurrentReviewPointer:
        pointer = self._store.load_current()
        return create_current_pointer(run.run_identity, ()) if pointer is None or pointer.probables_run_identity != run.run_identity else pointer

    @staticmethod
    def _cycle_pointer(pointer: CurrentReviewPointer, cycle_identity: str) -> ReviewCyclePointer:
        item = next((value for value in pointer.cycles if value.cycle_identity == cycle_identity), None)
        if item is None:
            raise ReviewError(ReviewFailure.CYCLE_UNAVAILABLE)
        return item


def _replace_cycle(pointer: CurrentReviewPointer, replacement: ReviewCyclePointer) -> CurrentReviewPointer:
    return create_current_pointer(
        pointer.probables_run_identity,
        tuple(replacement if item.cycle_identity == replacement.cycle_identity else item for item in pointer.cycles),
    )


__all__ = [
    "IntradayReviewApplication",
    "IntradayReviewCandidateSnapshot",
    "IntradayReviewSnapshot",
]
