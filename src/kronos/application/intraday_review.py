"""Provider-independent application service for governed Intraday Review."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
import stat
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
from kronos.intraday.review_batch import ReviewBatchPdf, create_review_batch
from kronos.intraday.review_answer import (
    MAX_ANSWER_BYTES,
    AnswerImportRecord,
    AnswerImportState,
    ImportedVisualEvidence,
    answer_pack_filename,
    bind_imported_evidence,
    create_import_record,
    create_visual_evidence_pointer,
    parse_answer_pack,
)
from kronos.intraday.review_pdf import (
    IntradayReviewPdfTransport,
    question_pack_filename,
    review_batch_filename,
)
from kronos.intraday.review_persistence import IntradayReviewStore, validate_chart_payload


@dataclass(frozen=True, slots=True)
class IntradayReviewCandidateSnapshot:
    canonical_subject_identity: str
    direction: str
    observation_boundary: datetime
    probables_run_identity: str
    probable_result_identity: str
    one_hour_context: str
    fifteen_minute_context: str
    coherence_context: str
    participation_state: str
    review_state: str
    cycle_identity: str | None
    chart_revision_identity: str | None
    chart_revision_ordinal: int | None
    review_pack_identity: str | None
    review_pack_filename: str | None
    answer_filename: str | None
    answer_state: str
    visual_state: str
    answer_pack_identity: str | None
    visual_evidence_identity: str | None
    observed_visible_subject_identity: str | None
    visual_answers: tuple[tuple[str, str, str, str], ...]


@dataclass(frozen=True, slots=True)
class IntradayReviewSnapshot:
    current_probables_run_identity: str | None
    candidates: tuple[IntradayReviewCandidateSnapshot, ...]
    question_outbox: str
    answer_inbox: str
    current_batch_identity: str | None = None
    current_batch_filename: str | None = None
    answer_import_active: bool = True
    provider_operations: int = 0
    discovery_operations: int = 0
    probables_operations: int = 0


class IntradayReviewBatchMemberState(StrEnum):
    CREATED = "CREATED"
    REUSED = "REUSED"
    SKIPPED_CHART_REQUIRED = "SKIPPED_CHART_REQUIRED"
    FAILED = "FAILED"


class IntradayReviewBatchState(StrEnum):
    COMPLETE = "COMPLETE"
    COMPLETE_WITH_SKIPS = "COMPLETE_WITH_SKIPS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    NO_ELIGIBLE_REVIEW_PACKS = "NO_ELIGIBLE_REVIEW_PACKS"


@dataclass(frozen=True, slots=True)
class IntradayAnswerImportResult:
    canonical_subject_identity: str
    cycle_identity: str
    answer_filename: str
    state: AnswerImportState
    import_identity: str | None = None
    answer_pack_identity: str | None = None
    visual_evidence_identity: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class IntradayAnswerBatchResult:
    members: tuple[IntradayAnswerImportResult, ...]

    @property
    def eligible_candidates(self) -> int:
        return len(self.members)

    @property
    def files_discovered(self) -> int:
        return sum(item.state is not AnswerImportState.MISSING for item in self.members)

    def count(self, state: AnswerImportState) -> int:
        return sum(item.state is state for item in self.members)


@dataclass(frozen=True, slots=True)
class IntradayReviewBatchMemberResult:
    canonical_subject_identity: str
    cycle_identity: str | None
    state: IntradayReviewBatchMemberState
    review_pack_identity: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class IntradayReviewBatchResult:
    state: IntradayReviewBatchState
    probables_run_identity: str
    members: tuple[IntradayReviewBatchMemberResult, ...]
    batch_identity: str | None = None
    batch_filename: str | None = None
    batch_error: str | None = None

    @property
    def created_count(self) -> int:
        return sum(item.state is IntradayReviewBatchMemberState.CREATED for item in self.members)

    @property
    def reused_count(self) -> int:
        return sum(item.state is IntradayReviewBatchMemberState.REUSED for item in self.members)

    @property
    def skipped_count(self) -> int:
        return sum(item.state is IntradayReviewBatchMemberState.SKIPPED_CHART_REQUIRED for item in self.members)

    @property
    def failed_count(self) -> int:
        return sum(item.state is IntradayReviewBatchMemberState.FAILED for item in self.members)


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
            batch = self._restored_batch(run, current)
            return IntradayReviewSnapshot(
                current_probables_run_identity=None if run is None else run.run_identity,
                candidates=candidates,
                question_outbox=str(self._transport.question_outbox),
                answer_inbox=str(self._transport.answer_inbox),
                current_batch_identity=None if batch is None else batch.batch_identity,
                current_batch_filename=None if batch is None else review_batch_filename(batch),
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

    def create_all_question_packs(self) -> IntradayReviewBatchResult:
        with self._lock:
            run = self._require_current_run()
            pointer = self._pointer_for_run(run)
            result_map = {
                item.result_identity: item
                for item in run.results
                if item.state in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
            }
            pointer_map = {item.probable_result_identity: item for item in pointer.cycles}
            outcomes: list[IntradayReviewBatchMemberResult] = []
            entries: list[tuple[ReviewQuestionPack, bytes]] = []
            for result in sorted(result_map.values(), key=lambda item: item.canonical_subject_identity):
                item = pointer_map.get(result.result_identity)
                if item is None or item.active_chart_revision_identity is None:
                    outcomes.append(IntradayReviewBatchMemberResult(
                        canonical_subject_identity=result.canonical_subject_identity,
                        cycle_identity=None if item is None else item.cycle_identity,
                        state=IntradayReviewBatchMemberState.SKIPPED_CHART_REQUIRED,
                        detail=ReviewFailure.CHART_REQUIRED.value,
                    ))
                    continue
                reused = item.active_review_pack_identity is not None
                try:
                    pack, _ = self.create_question_pack(item.cycle_identity)
                    chart = self._store.load_chart(pack.chart_revision_identity)
                    chart_payload = self._store.load_chart_bytes(chart)
                except ReviewError as error:
                    outcomes.append(IntradayReviewBatchMemberResult(
                        canonical_subject_identity=result.canonical_subject_identity,
                        cycle_identity=item.cycle_identity,
                        state=IntradayReviewBatchMemberState.FAILED,
                        detail=error.failure.value,
                    ))
                    continue
                entries.append((pack, chart_payload))
                outcomes.append(IntradayReviewBatchMemberResult(
                    canonical_subject_identity=result.canonical_subject_identity,
                    cycle_identity=item.cycle_identity,
                    state=(
                        IntradayReviewBatchMemberState.REUSED
                        if reused
                        else IntradayReviewBatchMemberState.CREATED
                    ),
                    review_pack_identity=pack.review_pack_identity,
                ))
            failures = sum(item.state is IntradayReviewBatchMemberState.FAILED for item in outcomes)
            if not entries:
                return IntradayReviewBatchResult(
                    state=(
                        IntradayReviewBatchState.FAILED
                        if failures
                        else IntradayReviewBatchState.NO_ELIGIBLE_REVIEW_PACKS
                    ),
                    probables_run_identity=run.run_identity,
                    members=tuple(outcomes),
                )
            batch = create_review_batch(run.run_identity, tuple(pack for pack, _ in entries))
            try:
                self._store.retain_batch(batch)
                batch_path = self._transport.export_batch(batch, entries)
            except ReviewError as error:
                return IntradayReviewBatchResult(
                    state=IntradayReviewBatchState.PARTIAL,
                    probables_run_identity=run.run_identity,
                    members=tuple(outcomes),
                    batch_identity=batch.batch_identity,
                    batch_error=error.failure.value,
                )
            skipped = sum(
                item.state is IntradayReviewBatchMemberState.SKIPPED_CHART_REQUIRED
                for item in outcomes
            )
            return IntradayReviewBatchResult(
                state=(
                    IntradayReviewBatchState.PARTIAL
                    if failures
                    else IntradayReviewBatchState.COMPLETE_WITH_SKIPS
                    if skipped
                    else IntradayReviewBatchState.COMPLETE
                ),
                probables_run_identity=run.run_identity,
                members=tuple(outcomes),
                batch_identity=batch.batch_identity,
                batch_filename=batch_path.name,
            )

    def import_answer(self, cycle_identity: str) -> IntradayAnswerImportResult:
        with self._lock:
            run = self._require_current_run()
            pointer = self._pointer_for_run(run)
            item = self._cycle_pointer(pointer, cycle_identity)
            if item.active_review_pack_identity is None:
                raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE)
            pack = self._store.load_pack(item.active_review_pack_identity)
            filename = answer_pack_filename(pack)
            target = self._transport.answer_inbox / filename
            existing = self._store.load_visual_evidence_pointer(pack.review_pack_identity)
            if existing is not None and not target.exists():
                record = self._store.load_import_record(existing.import_identity)
                return self._answer_result(
                    pack, filename, AnswerImportState.ALREADY_IMPORTED, record=record,
                )
            payload: bytes | None = None
            digest: str | None = None
            try:
                payload = self._read_answer_file(target)
                digest = sha256(payload).hexdigest()
                return self._import_answer_payload(pack, filename, payload)
            except ReviewError as error:
                state = {
                    ReviewFailure.ANSWER_MISSING: AnswerImportState.MISSING,
                    ReviewFailure.ANSWER_IDENTITY_MISMATCH: AnswerImportState.IDENTITY_MISMATCH,
                    ReviewFailure.ANSWER_SCHEMA_INVALID: AnswerImportState.SCHEMA_INVALID,
                    ReviewFailure.ANSWER_CONFLICT: AnswerImportState.CONFLICT,
                }.get(error.failure, AnswerImportState.INVALID)
                return self._failure_result(pack, filename, digest, state, error.failure)

    def upload_answer(self, cycle_identity: str, *, media_type: str, payload: bytes) -> IntradayAnswerImportResult:
        with self._lock:
            run = self._require_current_run()
            item = self._cycle_pointer(self._pointer_for_run(run), cycle_identity)
            if item.active_review_pack_identity is None:
                raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE)
            pack = self._store.load_pack(item.active_review_pack_identity)
            filename = answer_pack_filename(pack)
            digest = sha256(payload).hexdigest() if type(payload) is bytes else None
            if media_type.split(";", 1)[0].strip().lower() not in {"application/json", "text/json"}:
                return self._failure_result(
                    pack, filename, digest, AnswerImportState.INVALID, ReviewFailure.ANSWER_INVALID,
                )
            try:
                return self._import_answer_payload(pack, filename, payload)
            except ReviewError as error:
                state = {
                    ReviewFailure.ANSWER_IDENTITY_MISMATCH: AnswerImportState.IDENTITY_MISMATCH,
                    ReviewFailure.ANSWER_SCHEMA_INVALID: AnswerImportState.SCHEMA_INVALID,
                    ReviewFailure.ANSWER_CONFLICT: AnswerImportState.CONFLICT,
                }.get(error.failure, AnswerImportState.INVALID)
                return self._failure_result(pack, filename, digest, state, error.failure)

    def import_all_answers(self) -> IntradayAnswerBatchResult:
        with self._lock:
            run = self._require_current_run()
            pointer = self._pointer_for_run(run)
            eligible = tuple(sorted(
                (item for item in pointer.cycles if item.active_review_pack_identity is not None),
                key=lambda item: item.canonical_subject_identity,
            ))
            return IntradayAnswerBatchResult(tuple(self.import_answer(item.cycle_identity) for item in eligible))

    def _candidate_snapshot(
        self,
        run: ProbablesRun,
        result: ProbableMemberResult,
        pointer: ReviewCyclePointer | None,
    ) -> IntradayReviewCandidateSnapshot:
        chart = None if pointer is None or pointer.active_chart_revision_identity is None else self._store.load_chart(pointer.active_chart_revision_identity)
        pack = None if pointer is None or pointer.active_review_pack_identity is None else self._store.load_pack(pointer.active_review_pack_identity)
        filename = None if pack is None else question_pack_filename(pack)
        evidence = None if pack is None else self._restore_visual_evidence(pack)
        direction = result.direction.value if result.direction is not None else "UNAVAILABLE"
        return IntradayReviewCandidateSnapshot(
            canonical_subject_identity=result.canonical_subject_identity,
            direction=direction,
            observation_boundary=result.observation_boundary,
            probables_run_identity=run.run_identity,
            probable_result_identity=result.result_identity,
            one_hour_context=direction,
            fifteen_minute_context=direction,
            coherence_context=direction,
            participation_state=result.participation_state,
            review_state="REVIEW_REQUIRED" if pointer is None else pointer.state.value,
            cycle_identity=None if pointer is None else pointer.cycle_identity,
            chart_revision_identity=None if chart is None else chart.chart_revision_identity,
            chart_revision_ordinal=None if chart is None else chart.revision_ordinal,
            review_pack_identity=None if pack is None else pack.review_pack_identity,
            review_pack_filename=filename,
            answer_filename=None if pack is None else answer_pack_filename(pack),
            answer_state="NOT_IMPORTED" if evidence is None else "IMPORTED",
            visual_state="NOT_ANALYZED" if evidence is None else evidence.global_observation_status.value,
            answer_pack_identity=None if evidence is None else evidence.answer_pack_identity,
            visual_evidence_identity=None if evidence is None else evidence.visual_evidence_identity,
            observed_visible_subject_identity=None if evidence is None else evidence.observed_visible_subject_identity,
            visual_answers=() if evidence is None else tuple(
                (
                    answer.question_id,
                    answer.observation_status.value,
                    "UNAVAILABLE" if answer.answer is None else answer.answer,
                    "UNAVAILABLE" if answer.visible_basis is None else answer.visible_basis,
                )
                for answer in evidence.answers
            ),
        )

    def _restore_visual_evidence(self, pack: ReviewQuestionPack) -> ImportedVisualEvidence | None:
        pointer = self._store.load_visual_evidence_pointer(pack.review_pack_identity)
        if pointer is None:
            return None
        answer = self._store.load_answer_pack(pointer.answer_pack_identity)
        record = self._store.load_import_record(pointer.import_identity)
        evidence = self._store.load_visual_evidence(pointer.visual_evidence_identity)
        if (
            pointer.review_cycle_identity != pack.review_cycle_identity
            or pointer.chart_revision_identity != pack.chart_revision_identity
            or record.review_pack_identity != pack.review_pack_identity
            or record.answer_pack_identity != answer.answer_pack_identity
            or record.visual_evidence_identity != evidence.visual_evidence_identity
            or evidence.review_pack_identity != pack.review_pack_identity
            or evidence.review_cycle_identity != pack.review_cycle_identity
            or evidence.chart_revision_identity != pack.chart_revision_identity
            or evidence.answer_pack_identity != answer.answer_pack_identity
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return evidence

    def _read_answer_file(self, target: Path) -> bytes:
        inbox = self._transport.answer_inbox.resolve()
        if target.parent.resolve() != inbox or target.suffix.lower() != ".json" or target.is_symlink():
            raise ReviewError(ReviewFailure.ANSWER_INVALID)
        try:
            metadata = target.lstat()
        except FileNotFoundError as error:
            raise ReviewError(ReviewFailure.ANSWER_MISSING) from error
        except OSError as error:
            raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE) from error
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= MAX_ANSWER_BYTES:
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        try:
            payload = target.read_bytes()
        except OSError as error:
            raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE) from error
        if len(payload) != metadata.st_size:
            raise ReviewError(ReviewFailure.ANSWER_INVALID)
        return payload

    def _failure_result(
        self,
        pack: ReviewQuestionPack,
        filename: str,
        digest: str | None,
        state: AnswerImportState,
        failure: ReviewFailure,
    ) -> IntradayAnswerImportResult:
        record = create_import_record(
            pack,
            answer_filename=filename,
            answer_sha256=digest,
            state=state,
            imported_at=self._clock(),
            failure=failure.value,
        )
        self._store.retain_import_record(record)
        return self._answer_result(pack, filename, state, record=record, detail=failure.value)

    def _import_answer_payload(
        self,
        pack: ReviewQuestionPack,
        filename: str,
        payload: bytes,
    ) -> IntradayAnswerImportResult:
        digest = sha256(payload).hexdigest()
        answer = parse_answer_pack(payload)
        existing = self._store.load_visual_evidence_pointer(pack.review_pack_identity)
        if existing is not None:
            prior = self._store.load_answer_pack(existing.answer_pack_identity)
            if prior.answer_pack_identity == answer.answer_pack_identity:
                record = self._store.load_import_record(existing.import_identity)
                return self._answer_result(
                    pack, filename, AnswerImportState.ALREADY_IMPORTED, record=record,
                )
            raise ReviewError(ReviewFailure.ANSWER_CONFLICT)
        evidence = bind_imported_evidence(pack, answer, imported_at=self._clock())
        record = create_import_record(
            pack,
            answer_filename=filename,
            answer_sha256=digest,
            state=AnswerImportState.IMPORTED,
            imported_at=evidence.imported_at,
            answer_pack_identity=answer.answer_pack_identity,
            visual_evidence_identity=evidence.visual_evidence_identity,
        )
        self._store.retain_answer_transport(pack.review_pack_identity, payload)
        self._store.retain_answer_pack(answer)
        self._store.retain_visual_evidence(evidence)
        self._store.retain_import_record(record)
        self._store.save_visual_evidence_pointer(create_visual_evidence_pointer(evidence, record))
        return self._answer_result(
            pack, filename, AnswerImportState.IMPORTED, record=record, evidence=evidence,
        )

    @staticmethod
    def _answer_result(
        pack: ReviewQuestionPack,
        filename: str,
        state: AnswerImportState,
        *,
        record: AnswerImportRecord,
        evidence: ImportedVisualEvidence | None = None,
        detail: str | None = None,
    ) -> IntradayAnswerImportResult:
        return IntradayAnswerImportResult(
            canonical_subject_identity=pack.expected_canonical_subject_identity,
            cycle_identity=pack.review_cycle_identity,
            answer_filename=filename,
            state=state,
            import_identity=record.import_identity,
            answer_pack_identity=record.answer_pack_identity,
            visual_evidence_identity=(
                record.visual_evidence_identity if evidence is None else evidence.visual_evidence_identity
            ),
            detail=detail,
        )

    def _restored_batch(
        self,
        run: ProbablesRun | None,
        pointer: CurrentReviewPointer | None,
    ) -> ReviewBatchPdf | None:
        if run is None or pointer is None or pointer.probables_run_identity != run.run_identity:
            return None
        packs = tuple(
            self._store.load_pack(item.active_review_pack_identity)
            for item in pointer.cycles
            if item.active_review_pack_identity is not None
        )
        if not packs:
            return None
        candidate = create_review_batch(run.run_identity, packs)
        return self._store.load_batch_if_present(candidate.batch_identity)

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
    "IntradayAnswerBatchResult",
    "IntradayAnswerImportResult",
    "IntradayReviewApplication",
    "IntradayReviewBatchMemberResult",
    "IntradayReviewBatchMemberState",
    "IntradayReviewBatchResult",
    "IntradayReviewBatchState",
    "IntradayReviewCandidateSnapshot",
    "IntradayReviewSnapshot",
]
