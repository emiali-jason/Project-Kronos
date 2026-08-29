"""Explicit Sponsor-work seam from one governed Probables V2 run to Review."""

from __future__ import annotations

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


__all__ = ["IntradayReviewV2Application"]
