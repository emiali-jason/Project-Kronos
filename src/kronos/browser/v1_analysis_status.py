"""Sanitized presentation state for the Sponsor's 4E analysis batch."""

from __future__ import annotations

from dataclasses import dataclass

from kronos.application.swing_v1_review import (
    ChartAnalysisState,
    V1ReviewWorkflowSnapshot,
)


_DISPLAY_STATUS = {
    ChartAnalysisState.CHARTS_REQUIRED: "WAITING",
    ChartAnalysisState.READY_TO_ANALYZE: "WAITING",
    ChartAnalysisState.ANALYZING_CHART_CONTEXT: "ANALYZING",
    ChartAnalysisState.ANALYSIS_COMPLETE: "ANALYZED",
    ChartAnalysisState.CONTEXT_INCOMPLETE: "CONTEXT INCOMPLETE",
    ChartAnalysisState.CHART_ANALYSIS_UNAVAILABLE: "ANALYSIS FAILED",
}


@dataclass(frozen=True, slots=True)
class V1BatchAnalysisStatus:
    label: str
    total: int
    analyzed: int
    incomplete: int
    failed: int
    analyzing: int

    @property
    def finished(self) -> int:
        return self.analyzed + self.incomplete + self.failed

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.finished == self.total


def instrument_analysis_status(state: ChartAnalysisState) -> str:
    if type(state) is not ChartAnalysisState:
        raise TypeError("V1_ANALYSIS_STATUS_INVALID")
    return _DISPLAY_STATUS[state]


def batch_analysis_status(
    review: V1ReviewWorkflowSnapshot,
) -> V1BatchAnalysisStatus:
    if type(review) is not V1ReviewWorkflowSnapshot:
        raise TypeError("V1_ANALYSIS_STATUS_INVALID")
    states = tuple(item.state for item in review.analyses)
    total = len(states)
    analyzed = states.count(ChartAnalysisState.ANALYSIS_COMPLETE)
    incomplete = states.count(ChartAnalysisState.CONTEXT_INCOMPLETE)
    failed = states.count(ChartAnalysisState.CHART_ANALYSIS_UNAVAILABLE)
    analyzing = states.count(ChartAnalysisState.ANALYZING_CHART_CONTEXT)
    finished = analyzed + incomplete + failed
    if analyzing:
        label = f"ANALYZING {finished} / {total}"
    elif total and finished == total:
        parts = [f"{analyzed} / {total} ANALYZED"]
        if incomplete:
            parts.append(f"{incomplete} INCOMPLETE")
        if failed:
            parts.append(f"{failed} FAILED")
        label = " — ".join(parts)
    else:
        label = f"WAITING {finished} / {total}" if total else "WAITING"
    return V1BatchAnalysisStatus(
        label=label,
        total=total,
        analyzed=analyzed,
        incomplete=incomplete,
        failed=failed,
        analyzing=analyzing,
    )


def analysis_status_payload(review: V1ReviewWorkflowSnapshot) -> dict[str, object]:
    batch = batch_analysis_status(review)
    batch_label = (
        review.batch_preflight_failure.value
        if review.batch_preflight_failure is not None
        else batch.label
    )
    return {
        "batch": batch_label,
        "finished": batch.finished,
        "total": batch.total,
        "complete": batch.complete,
        "instruments": [
            {
                "instrument": item.canonical_instrument,
                "status": instrument_analysis_status(item.state),
            }
            for item in review.analyses
        ],
    }


__all__ = [
    "V1BatchAnalysisStatus",
    "analysis_status_payload",
    "batch_analysis_status",
    "instrument_analysis_status",
]
