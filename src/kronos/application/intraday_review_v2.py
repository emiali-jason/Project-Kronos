"""Explicit Sponsor-work seam from one governed Probables V2 run to Review."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Callable

from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import ProbablesRunV2, ProbablesV2Error
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_v2 import (
    ChartRevisionV2,
    ReviewCycleV2,
    ReviewQuestionBatchV2,
    ReviewQuestionPackV2,
    create_chart_intake_request_v2,
    create_chart_revision_v2,
    create_current_chart_pointer_v2,
    create_current_review_pointer_v2,
    create_question_batch_v2,
    create_question_pack_v2,
    create_review_cycle_v2,
    create_review_handoff_v2,
)
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_v2_transport import (
    IntradayReviewV2Transport,
    ReviewBatchTransportV2,
    expected_transport_identity_v2,
)


@dataclass(frozen=True, slots=True)
class IntradayReviewV2CandidateSnapshot:
    sponsor_label: str
    canonical_subject_identity: str
    direction: str
    methodology_identity: str
    methodology_version: str
    methodology_publication_identity: str
    analysis_boundary: datetime
    phase: str
    review_state: str
    chart_state: str
    review_pack_state: str
    question_pack_state: str
    answer_state: str
    cycle_identity: str
    probable_result_identity: str
    nifty_applicability: str | None
    mcx_commissioning_state: str | None
    chart_revision_identity: str | None
    chart_revision_ordinal: int | None
    chart_payload_sha256: str | None


@dataclass(frozen=True, slots=True)
class IntradayReviewV2Snapshot:
    probables_run_identity: str | None
    current_pointer_identity: str | None
    candidates: tuple[IntradayReviewV2CandidateSnapshot, ...]
    review_batch_identity: str | None = None
    question_transport_identity: str | None = None
    question_filename: str | None = None
    expected_answer_filename: str | None = None


@dataclass(frozen=True, slots=True)
class IntradayReviewV2BatchResult:
    batch: ReviewQuestionBatchV2
    transport: ReviewBatchTransportV2
    packs: tuple[ReviewQuestionPackV2, ...]
    question_path: Path
    answer_template_path: Path


class IntradayReviewV2Application:
    """No background hook: callers must explicitly supply the exact V2 run."""

    def __init__(
        self,
        *,
        probables_store: ProbablesV2Store,
        review_store: IntradayReviewV2Store,
        transport: IntradayReviewV2Transport | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if (
            type(probables_store) is not ProbablesV2Store
            or type(review_store) is not IntradayReviewV2Store
            or transport is not None and type(transport) is not IntradayReviewV2Transport
            or not callable(clock)
        ):
            raise ValueError("INTRADAY_REVIEW_V2_APPLICATION_INVALID")
        self._probables = probables_store
        self._review = review_store
        self._transport = transport or IntradayReviewV2Transport()
        self._clock = clock
        self._lock = RLock()

    @property
    def review_store(self) -> IntradayReviewV2Store:
        return self._review

    @property
    def probables_store(self) -> ProbablesV2Store:
        return self._probables

    def create_eligible_cycles_for_run_identity(
        self,
        *,
        probables_run_identity: str,
        methodology_identity: str,
        methodology_version: str,
        methodology_publication_identity: str,
        methodology_checksum: str,
    ) -> tuple[ReviewCycleV2, ...]:
        """Load one explicit run and reject any expected-lineage mismatch."""

        try:
            run = self._probables.load_run(probables_run_identity)
        except (ProbablesV2Error, ValueError) as error:
            raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE) from error
        expected = (
            methodology_identity,
            methodology_version,
            methodology_publication_identity,
            methodology_checksum,
        )
        actual = (
            run.methodology.methodology_identity,
            run.methodology.methodology_version,
            run.methodology.publication_identity,
            run.methodology.payload_checksum,
        )
        if actual != expected:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        if not any(
            result.state in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
            for result in run.results
        ):
            raise ReviewError(ReviewFailure.NOT_ELIGIBLE)
        return self.create_eligible_cycles(run)

    def snapshot(self) -> IntradayReviewV2Snapshot:
        """Project persisted Phase-A facts without creating or advancing Review."""

        pointer = self._review.load_current()
        if pointer is None:
            return IntradayReviewV2Snapshot(None, None, ())
        cycles = tuple(
            sorted(
                (self._review.load_cycle(item.cycle_identity) for item in pointer.cycles),
                key=lambda item: _sponsor_label(item.canonical_subject_identity).casefold(),
            )
        )
        packs: list[ReviewQuestionPackV2] = []
        for cycle in cycles:
            active = self._review.load_current_chart(cycle.cycle_identity)
            if active is None:
                continue
            chart = self._review.load_chart(active.chart_revision_identity)
            handoff = self._review.load_handoff(cycle.handoff_identity)
            expected = create_question_pack_v2(handoff, cycle, chart)
            try:
                retained = self._review.load_pack(expected.review_pack_identity)
            except ReviewError as error:
                if error.failure is not ReviewFailure.ARTIFACT_UNAVAILABLE:
                    raise
                continue
            if retained != expected:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            packs.append(retained)
        batch = None
        transport = None
        if packs and len(packs) == len(cycles):
            expected_batch = create_question_batch_v2(tuple(packs))
            try:
                batch = self._review.load_batch(expected_batch.batch_identity)
                transport = self._review.load_transport(
                    expected_transport_identity_v2(expected_batch)
                )
            except ReviewError as error:
                if error.failure is not ReviewFailure.ARTIFACT_UNAVAILABLE:
                    raise
                batch = None
                transport = None
            if batch is not None and batch != expected_batch:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        ready_pack_ids = {item.review_pack_identity for item in packs}
        return IntradayReviewV2Snapshot(
            probables_run_identity=pointer.probables_run_identity,
            current_pointer_identity=pointer.integrity_identity,
            candidates=tuple(
                self._candidate_snapshot(cycle, ready_pack_ids, transport is not None)
                for cycle in cycles
            ),
            review_batch_identity=None if batch is None else batch.batch_identity,
            question_transport_identity=(
                None if transport is None else transport.transport_identity
            ),
            question_filename=None if transport is None else transport.question_filename,
            expected_answer_filename=(
                None if transport is None else transport.expected_answer_filename
            ),
        )

    def _candidate_snapshot(
        self,
        cycle: ReviewCycleV2,
        ready_pack_ids: set[str] | None = None,
        transport_ready: bool = False,
    ) -> IntradayReviewV2CandidateSnapshot:
        active = self._review.load_current_chart(cycle.cycle_identity)
        pack_ready = False
        if active is not None and ready_pack_ids is not None:
            chart = self._review.load_chart(active.chart_revision_identity)
            handoff = self._review.load_handoff(cycle.handoff_identity)
            pack_ready = (
                create_question_pack_v2(handoff, cycle, chart).review_pack_identity
                in ready_pack_ids
            )
        return IntradayReviewV2CandidateSnapshot(
            sponsor_label=_sponsor_label(cycle.canonical_subject_identity),
            canonical_subject_identity=cycle.canonical_subject_identity,
            direction=cycle.direction,
            methodology_identity=cycle.methodology_identity,
            methodology_version=cycle.methodology_version,
            methodology_publication_identity=cycle.methodology_publication_identity,
            analysis_boundary=cycle.analysis_boundary,
            phase=cycle.phase.value,
            review_state="REVIEW_CYCLE_EXISTS",
            chart_state="CHART_REQUIRED" if active is None else "CHART_READY",
            review_pack_state="READY" if pack_ready else "ABSENT",
            question_pack_state=(
                "TRANSPORT_READY" if pack_ready and transport_ready else "ABSENT"
            ),
            answer_state=cycle.answer_state.value,
            cycle_identity=cycle.cycle_identity,
            probable_result_identity=cycle.probable_result_identity,
            nifty_applicability=(
                None
                if cycle.nifty_applicability is None
                else cycle.nifty_applicability.value
            ),
            mcx_commissioning_state=(
                None
                if cycle.mcx_commissioning is None
                else cycle.mcx_commissioning.state.value
            ),
            chart_revision_identity=(
                None if active is None else active.chart_revision_identity
            ),
            chart_revision_ordinal=(
                None if active is None else active.revision_ordinal
            ),
            chart_payload_sha256=(
                None if active is None else active.payload_sha256
            ),
        )

    def upload_chart(
        self,
        cycle_identity: str,
        *,
        media_type: str,
        payload: bytes,
    ) -> ChartRevisionV2:
        """Retain one exact-cycle chart without mutating the Review Cycle."""

        with self._lock:
            pointer = self._review.load_current()
            if pointer is None:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            cycle_pointer = next(
                (item for item in pointer.cycles if item.cycle_identity == cycle_identity),
                None,
            )
            if cycle_pointer is None:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            cycle = self._review.load_cycle(cycle_identity)
            if (
                cycle.probables_run_identity != pointer.probables_run_identity
                or cycle.probable_result_identity
                != cycle_pointer.probable_result_identity
                or cycle.canonical_subject_identity
                != cycle_pointer.canonical_subject_identity
                or cycle.direction != cycle_pointer.direction
            ):
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)

            request = create_chart_intake_request_v2(
                cycle,
                payload=payload,
                media_type=media_type,
                requested_at=self._clock(),
            )
            self._review.retain_chart_request(request)
            active_pointer = self._review.load_current_chart(cycle_identity)
            if (
                active_pointer is not None
                and active_pointer.payload_sha256 == sha256(payload).hexdigest()
                and active_pointer.media_type == media_type
            ):
                return self._review.load_chart(
                    active_pointer.chart_revision_identity
                )

            chart = create_chart_revision_v2(
                cycle,
                revision_ordinal=(
                    1 if active_pointer is None
                    else active_pointer.revision_ordinal + 1
                ),
                payload=payload,
                media_type=media_type,
                received_at=self._clock(),
                request_identity=request.request_identity,
            )
            current = create_current_chart_pointer_v2(cycle, request, chart)
            self._review.retain_chart(chart, payload)
            self._review.save_current_chart(current)
            return chart

    def create_combined_question_transport(self) -> IntradayReviewV2BatchResult:
        """Create exact V2 packs and one immutable combined Question transport."""

        with self._lock:
            pointer = self._review.load_current()
            if pointer is None or not pointer.cycles:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            entries: list[tuple[ReviewQuestionPackV2, bytes]] = []
            for cycle_pointer in pointer.cycles:
                cycle = self._review.load_cycle(cycle_pointer.cycle_identity)
                active = self._review.load_current_chart(cycle.cycle_identity)
                if active is None:
                    raise ReviewError(ReviewFailure.CHART_REQUIRED)
                chart = self._review.load_chart(active.chart_revision_identity)
                handoff = self._review.load_handoff(cycle.handoff_identity)
                pack = create_question_pack_v2(handoff, cycle, chart)
                entries.append((pack, self._review.load_chart_bytes(chart)))
            ordered = tuple(sorted(
                entries,
                key=lambda item: item[0].expected_canonical_subject_identity,
            ))
            packs = tuple(pack for pack, _ in ordered)
            for pack in packs:
                self._review.retain_pack(pack)
            batch = create_question_batch_v2(packs)
            self._review.retain_batch(batch)
            transport, question_path, answer_path = self._transport.export(
                batch, ordered
            )
            self._review.retain_transport(
                transport, question_path.read_bytes(), answer_path.read_bytes()
            )
            return IntradayReviewV2BatchResult(
                batch=batch,
                transport=transport,
                packs=packs,
                question_path=question_path,
                answer_template_path=answer_path,
            )

    def create_eligible_cycles(self, run: ProbablesRunV2) -> tuple[ReviewCycleV2, ...]:
        """Retain cycles only after exact persisted V2 lineage has been proven."""
        if type(run) is not ProbablesRunV2:
            raise ReviewError(ReviewFailure.INPUT_INVALID)
        try:
            persisted = self._probables.load_run(run.run_identity)
        except (ProbablesV2Error, ValueError) as error:
            raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE) from error
        if persisted != run:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)

        existing = self._review.cycles_for_run(run.run_identity)
        if existing:
            return existing

        cycles: list[ReviewCycleV2] = []
        for result in run.results:
            if result.state not in {
                ProbableState.LONG_PROBABLE,
                ProbableState.SHORT_PROBABLE,
            }:
                continue
            if result.source_mapping_identity is None:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            try:
                persisted_result = self._probables.load_result(result.result_identity)
                mapping = self._probables.load_mapping(result.source_mapping_identity)
                selection = self._probables.load_selection(
                    result.completed_evidence_selection_identity or ""
                )
                semantic = self._probables.load_semantic(
                    result.semantic_evidence_identity or ""
                )
            except (ProbablesV2Error, ValueError) as error:
                raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE) from error
            if (
                persisted_result != result
                or mapping.completed_evidence != selection
                or mapping.semantic_evidence != semantic
            ):
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            if result.nifty_relative_evidence_identity is not None:
                try:
                    nifty = self._probables.load_nifty(
                        result.nifty_relative_evidence_identity
                    )
                except (ProbablesV2Error, ValueError) as error:
                    raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE) from error
                if mapping.nifty_relative != nifty:
                    raise ReviewError(ReviewFailure.INTEGRITY_INVALID)

            handoff = create_review_handoff_v2(run, result, mapping)
            cycle = create_review_cycle_v2(handoff)
            self._review.retain_handoff(handoff)
            self._review.retain_cycle(cycle)
            cycles.append(cycle)

        retained = tuple(sorted(cycles, key=lambda item: item.probable_result_identity))
        self._review.save_current(create_current_review_pointer_v2(run, retained))
        return retained


def _sponsor_label(canonical_subject_identity: str) -> str:
    for prefix in ("NSE-EQ-", "NSE-INDEX-", "MCX-SUBJECT-"):
        if canonical_subject_identity.startswith(prefix):
            return canonical_subject_identity.removeprefix(prefix)
    return canonical_subject_identity


__all__ = [
    "IntradayReviewV2Application",
    "IntradayReviewV2BatchResult",
    "IntradayReviewV2CandidateSnapshot",
    "IntradayReviewV2Snapshot",
]
