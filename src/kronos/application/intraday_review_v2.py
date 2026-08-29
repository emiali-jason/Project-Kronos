"""Explicit Sponsor-work seam from one governed Probables V2 run to Review."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import ProbablesRunV2, ProbablesV2Error
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_v2 import (
    ReviewCycleV2,
    create_current_review_pointer_v2,
    create_review_cycle_v2,
    create_review_handoff_v2,
)
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store


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


@dataclass(frozen=True, slots=True)
class IntradayReviewV2Snapshot:
    probables_run_identity: str | None
    current_pointer_identity: str | None
    candidates: tuple[IntradayReviewV2CandidateSnapshot, ...]


class IntradayReviewV2Application:
    """No background hook: callers must explicitly supply the exact V2 run."""

    def __init__(
        self,
        *,
        probables_store: ProbablesV2Store,
        review_store: IntradayReviewV2Store,
    ) -> None:
        if (
            type(probables_store) is not ProbablesV2Store
            or type(review_store) is not IntradayReviewV2Store
        ):
            raise ValueError("INTRADAY_REVIEW_V2_APPLICATION_INVALID")
        self._probables = probables_store
        self._review = review_store

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
        return IntradayReviewV2Snapshot(
            probables_run_identity=pointer.probables_run_identity,
            current_pointer_identity=pointer.integrity_identity,
            candidates=tuple(
                IntradayReviewV2CandidateSnapshot(
                    sponsor_label=_sponsor_label(cycle.canonical_subject_identity),
                    canonical_subject_identity=cycle.canonical_subject_identity,
                    direction=cycle.direction,
                    methodology_identity=cycle.methodology_identity,
                    methodology_version=cycle.methodology_version,
                    methodology_publication_identity=(
                        cycle.methodology_publication_identity
                    ),
                    analysis_boundary=cycle.analysis_boundary,
                    phase=cycle.phase.value,
                    review_state="REVIEW_CYCLE_EXISTS",
                    chart_state="CHART_REQUIRED",
                    review_pack_state="ABSENT",
                    question_pack_state="ABSENT",
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
                )
                for cycle in cycles
            ),
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
    "IntradayReviewV2CandidateSnapshot",
    "IntradayReviewV2Snapshot",
]
