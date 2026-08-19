"""Additive application boundary for future Swing Visual V3 review cycles.

Historical V2 Review Packs continue through ``NativeReviewWorkflow``.  This
boundary prepares and retains only explicitly versioned V3 evidence and binds
it to the same immutable Native run and MTF machine-fact snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kronos.swing.v1.mtf_facts import FactualTimeframe, SameRunMtfFactSnapshot
from kronos.swing.v1.native_readiness import NativeConditionInputs
from kronos.swing.v1.native_readiness_v3 import (
    NativeLayer2ReadinessRecordV3,
    NativeLayer2ReadinessV3Store,
    create_native_readiness_record_v3,
)
from kronos.swing.v1.pdf_visual_review_v3 import VisualV3ReviewPackRecord
from kronos.swing.v1.native_review import (
    McxReferenceResult,
    NativeIndependentLayer2Evidence,
    NativeReviewRequirement,
)
from kronos.swing.v1.visual_evidence_v2 import VisualTimeframe
from kronos.swing.v1.visual_evidence_v3 import (
    LocalVisualEvidenceV3Store,
    VisualEvidenceV3Request,
    VisualEvidenceV3Response,
    build_visual_evidence_v3_request,
)


@dataclass(frozen=True, slots=True)
class VisualV3ChartInput:
    timeframe: VisualTimeframe
    observation_boundary: datetime
    chart_identity: str
    content_type: str
    original_image: bytes

    def __post_init__(self) -> None:
        if (
            type(self.timeframe) is not VisualTimeframe
            or not _aware(self.observation_boundary)
            or not self.chart_identity
            or self.content_type not in {"image/png", "image/jpeg", "image/webp"}
            or type(self.original_image) is not bytes
            or not self.original_image
        ):
            raise ValueError("VISUAL_V3_CHART_INPUT_INVALID")


@dataclass(frozen=True, slots=True)
class CompletedVisualV3Review:
    """Exact governed inputs for one completed future V3 Sponsor cycle."""

    requirement: NativeReviewRequirement
    mtf_snapshot: SameRunMtfFactSnapshot
    responses: tuple[VisualEvidenceV3Response, ...]
    readiness: NativeLayer2ReadinessRecordV3
    review_pack: VisualV3ReviewPackRecord | None = None

    def __post_init__(self) -> None:
        instrument = self.requirement.canonical_instrument
        run_identity = self.requirement.native_run_identity
        if (
            type(self.requirement) is not NativeReviewRequirement
            or type(self.mtf_snapshot) is not SameRunMtfFactSnapshot
            or self.mtf_snapshot.run_identity != run_identity
            or type(self.responses) is not tuple
            or len(self.responses) != len(VisualTimeframe)
            or tuple(item.timeframe for item in self.responses)
            != tuple(VisualTimeframe)
            or any(
                item.native_run_identity != run_identity
                or item.native_canonical_instrument != instrument
                or item.native_assessment_sha256
                != self.requirement.thesis.native_assessment_sha256
                for item in self.responses
            )
            or type(self.readiness) is not NativeLayer2ReadinessRecordV3
            or self.readiness.run_identity != run_identity
            or self.readiness.canonical_instrument != instrument
            or self.readiness.native_assessment_sha256
            != self.requirement.thesis.native_assessment_sha256
            or (
                self.review_pack is not None
                and (
                    type(self.review_pack) is not VisualV3ReviewPackRecord
                    or self.review_pack.native_run_identity != run_identity
                    or self.review_pack.canonical_instrument != instrument
                    or self.review_pack.native_assessment_sha256
                    != self.requirement.thesis.native_assessment_sha256
                )
            )
        ):
            raise ValueError("COMPLETED_VISUAL_V3_REVIEW_INVALID")
        facts = self.mtf_snapshot.instrument(instrument).reference_facts
        if any(
            response.machine_fact_integrity_sha256 != fact.integrity_sha256
            or response.analysis_boundary != fact.analysis_boundary
            for response, fact in zip(self.responses, facts, strict=True)
        ):
            raise ValueError("COMPLETED_VISUAL_V3_REVIEW_BINDING_INVALID")


class SwingVisualV3ReviewCycle:
    """Prepare, retain, and reconcile one explicit V3 review cycle."""

    def __init__(
        self,
        evidence_store: LocalVisualEvidenceV3Store,
        readiness_store: NativeLayer2ReadinessV3Store,
    ) -> None:
        self._evidence_store = evidence_store
        self._readiness_store = readiness_store
        self._completed: dict[tuple[str, str], CompletedVisualV3Review] = {}

    def prepare(
        self,
        requirement: NativeReviewRequirement,
        mtf_snapshot: SameRunMtfFactSnapshot,
        charts: tuple[VisualV3ChartInput, ...],
        *,
        request_timestamp: datetime,
    ) -> tuple[VisualEvidenceV3Request, ...]:
        if (
            type(charts) is not tuple
            or tuple(item.timeframe for item in charts) != tuple(VisualTimeframe)
        ):
            raise ValueError("VISUAL_V3_CHART_SET_INVALID")
        return tuple(
            build_visual_evidence_v3_request(
                requirement,
                mtf_snapshot,
                timeframe=chart.timeframe,
                observation_boundary=chart.observation_boundary,
                chart_identity=chart.chart_identity,
                content_type=chart.content_type,
                original_image=chart.original_image,
                request_timestamp=request_timestamp,
            )
            for chart in charts
        )

    def retain(
        self,
        request: VisualEvidenceV3Request,
        response: VisualEvidenceV3Response,
    ) -> None:
        self._evidence_store.retain(request, response)

    def complete(
        self,
        requirement: NativeReviewRequirement,
        layer2: NativeIndependentLayer2Evidence,
        mtf_snapshot: SameRunMtfFactSnapshot,
        responses: tuple[VisualEvidenceV3Response, ...],
        *,
        created_at: datetime,
        reference: McxReferenceResult | None = None,
        inputs: NativeConditionInputs = NativeConditionInputs(),
        review_pack: VisualV3ReviewPackRecord | None = None,
    ) -> NativeLayer2ReadinessRecordV3:
        record = create_native_readiness_record_v3(
            requirement,
            layer2,
            mtf_snapshot,
            responses,
            created_at=created_at,
            reference=reference,
            inputs=inputs,
        )
        self._readiness_store.retain(record)
        completed = CompletedVisualV3Review(
            requirement, mtf_snapshot, responses, record, review_pack
        )
        self._completed[(record.run_identity, record.canonical_instrument)] = completed
        return record

    def restore_completed(self, review: CompletedVisualV3Review) -> None:
        """Restore an already-persisted exact V3 cycle without reinterpretation."""

        if type(review) is not CompletedVisualV3Review:
            raise TypeError("COMPLETED_VISUAL_V3_REVIEW_INVALID")
        self._completed[(
            review.readiness.run_identity,
            review.readiness.canonical_instrument,
        )] = review

    def completed_for(
        self, run_identity: str, canonical_instrument: str
    ) -> CompletedVisualV3Review | None:
        return self._completed.get((run_identity, canonical_instrument))

    def completed_snapshot(self) -> tuple[CompletedVisualV3Review, ...]:
        return tuple(
            self._completed[key]
            for key in sorted(self._completed)
        )


def chart_inputs_from_requirement(
    requirement: NativeReviewRequirement,
    *,
    chart_identity: str,
    content_type: str,
    images: tuple[bytes, ...],
) -> tuple[VisualV3ChartInput, ...]:
    """Bind the four supplied charts to the requirement's factual boundaries."""

    if len(images) != len(FactualTimeframe):
        raise ValueError("VISUAL_V3_CHART_SET_INVALID")
    by_timeframe = {
        VisualTimeframe(item.timeframe.value): item.observation_boundary
        for item in requirement.thesis.timeframe_facts
    }
    return tuple(
        VisualV3ChartInput(
            timeframe,
            by_timeframe[timeframe],
            chart_identity,
            content_type,
            image,
        )
        for timeframe, image in zip(VisualTimeframe, images, strict=True)
    )


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "CompletedVisualV3Review",
    "SwingVisualV3ReviewCycle",
    "VisualV3ChartInput",
    "chart_inputs_from_requirement",
]
