"""Live, version-selected integration of the governed Visual V3 components."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from kronos.application.swing_native_review import NativeReviewWorkflowSnapshot
from kronos.application.swing_visual_v3 import (
    SwingVisualV3ReviewCycle,
    chart_inputs_from_requirement,
)
from kronos.swing.v1.mtf_facts import FactualTimeframe, SameRunMtfFactSnapshot
from kronos.swing.v1.native_readiness import NativeConditionInputs
from kronos.swing.v1.native_review import (
    NativeIndependentLayer2Evidence,
    NativeLayer2EvidenceState,
    NativeReviewRequirement,
)
from kronos.swing.v1.pdf_visual_review import PdfReviewTransportError
from kronos.swing.v1.pdf_visual_review_v3_live import (
    VisualV3AnswerImportRecord,
    VisualV3LiveReviewPack,
    VisualV3PdfReviewTransport,
)
from kronos.swing.v1.visual_evidence_v2 import (
    VisualEvidenceSubjectKind,
    VisualObservationStatus,
    VisualTimeframe,
)
from kronos.swing.v1.visual_evidence_v3 import (
    VISUAL_QUESTION_SET_V3_ID,
    VISUAL_QUESTION_SET_V3_VERSION,
    VisualEvidenceV3Request,
    VisualEvidenceV3Response,
    VisualQuestionV3,
)


@dataclass(frozen=True, slots=True)
class SwingVisualV3LiveSnapshot:
    review_pack: VisualV3LiveReviewPack | None
    answer_imports: tuple[VisualV3AnswerImportRecord, ...]
    current_run: bool
    completed_instruments: tuple[str, ...]


class SwingVisualV3LiveWorkflow:
    """Coordinate V3 Pack, Answer, evidence, readiness, and restart restoration."""

    def __init__(
        self,
        cycle: SwingVisualV3ReviewCycle,
        transport: VisualV3PdfReviewTransport,
        *,
        clock=lambda: datetime.now(UTC),  # type: ignore[no-untyped-def]
    ) -> None:
        if (
            type(cycle) is not SwingVisualV3ReviewCycle
            or type(transport) is not VisualV3PdfReviewTransport
            or not callable(clock)
        ):
            raise TypeError("VISUAL_V3_LIVE_WORKFLOW_DEPENDENCY_INVALID")
        self.cycle = cycle
        self.transport = transport
        self._clock = clock
        self._pack = transport.record_store.load_current()
        self._imports = (
            () if self._pack is None
            else transport.record_store.load_imports(self._pack.review_pack_id)
        )

    def is_current_run(self, run_identity: str | None) -> bool:
        return self._pack is not None and self._pack.native_run_identity == run_identity

    def snapshot(self, run_identity: str | None) -> SwingVisualV3LiveSnapshot:
        return SwingVisualV3LiveSnapshot(
            self._pack,
            self._imports,
            self.is_current_run(run_identity),
            tuple(
                item.requirement.canonical_instrument
                for item in self.cycle.completed_snapshot()
                if item.requirement.native_run_identity == run_identity
            ),
        )

    def generate(
        self,
        review: NativeReviewWorkflowSnapshot,
        facts: SameRunMtfFactSnapshot,
        chart_bytes,  # type: ignore[no-untyped-def]
        instrument: str | None = None,
    ) -> VisualV3LiveReviewPack:
        prepared, skipped = self._prepare(review, facts, chart_bytes, instrument)
        record = self.transport.generate(
            prepared,
            scope="INDIVIDUAL" if instrument is not None else "ALL_ELIGIBLE",
            skipped=() if instrument is not None else skipped,
        )
        self._pack = record
        self._imports = ()
        return record

    def upload(
        self,
        review: NativeReviewWorkflowSnapshot,
        facts: SameRunMtfFactSnapshot,
        chart_bytes,  # type: ignore[no-untyped-def]
    ) -> tuple[VisualV3AnswerImportRecord, ...]:
        record = self._require_current(review.native_run_identity)
        prepared, _ = self._prepare_for_record(review, facts, chart_bytes, record)
        try:
            answer = self.transport.find_and_validate_answer(record, prepared)
        except PdfReviewTransportError as error:
            rejected = self.transport.record_rejection(record, str(error))
            self._imports = (*self._imports, rejected)
            raise
        if not answer.candidates:
            return self._imports

        requirements = {
            item.canonical_instrument: item for item in review.requirements
        }
        references = {
            item.requirement.mcx_canonical_instrument: item
            for item in review.reference_results
        }
        hashes = []
        for candidate in answer.candidates:
            requirement = requirements[candidate.canonical_instrument]
            request_set = next(
                item for item in prepared
                if item[0].requirement.canonical_instrument == candidate.canonical_instrument
            )
            for request, response in zip(request_set, candidate.responses, strict=True):
                response.validate_binding(request)
            hashes.extend(item.evidence_sha256 for item in candidate.responses)

        # The full Answer has passed before any governed V3 evidence is written.
        for candidate in answer.candidates:
            requirement = requirements[candidate.canonical_instrument]
            request_set = next(
                item for item in prepared
                if item[0].requirement.canonical_instrument == candidate.canonical_instrument
            )
            for request, response in zip(request_set, candidate.responses, strict=True):
                self.cycle.retain(request, response)
            candidate_pack = next(
                item for item in record.candidate_packs
                if item.canonical_instrument == candidate.canonical_instrument
            )
            self.cycle.complete(
                requirement,
                _v3_layer2(requirement, candidate.responses),
                facts,
                candidate.responses,
                created_at=self._now(),
                reference=references.get(candidate.canonical_instrument),
                inputs=NativeConditionInputs(),
                review_pack=candidate_pack,
            )
        imported = self.transport.record_import(record, answer, tuple(hashes))
        self._imports = (*self._imports, imported)
        return self._imports

    def restore(
        self,
        review: NativeReviewWorkflowSnapshot,
        facts: SameRunMtfFactSnapshot,
        chart_bytes,  # type: ignore[no-untyped-def]
    ) -> None:
        if not self.is_current_run(review.native_run_identity):
            return
        record = self._require_current(review.native_run_identity)
        if not any(item.consumed for item in self._imports):
            return
        prepared, _ = self._prepare_for_record(review, facts, chart_bytes, record)
        requirements = {
            item.canonical_instrument: item for item in review.requirements
        }
        for request_set in prepared:
            instrument = request_set[0].requirement.canonical_instrument
            candidate_pack = next(
                item for item in record.candidate_packs
                if item.canonical_instrument == instrument
            )
            restored = self.cycle.restore_persisted(
                requirements[instrument],
                facts,
                request_set,
                review_pack=candidate_pack,
            )
            if restored is None:
                raise ValueError("VISUAL_V3_RESTART_EVIDENCE_MISSING")

    def _prepare(
        self,
        review: NativeReviewWorkflowSnapshot,
        facts: SameRunMtfFactSnapshot,
        chart_bytes,  # type: ignore[no-untyped-def]
        instrument: str | None,
        *,
        request_timestamp: datetime | None = None,
        question_set_version: str = VISUAL_QUESTION_SET_V3_VERSION,
    ) -> tuple[
        tuple[tuple[VisualEvidenceV3Request, ...], ...],
        tuple[tuple[str, str], ...],
    ]:
        if (
            review.native_run_identity is None
            or facts.run_identity != review.native_run_identity
        ):
            raise PdfReviewTransportError("VISUAL_V3_SAME_RUN_BINDING_INVALID")
        if instrument is not None and not any(
            item.canonical_instrument == instrument for item in review.requirements
        ):
            raise PdfReviewTransportError("NATIVE_REVIEW_REQUIREMENT_UNAVAILABLE")
        prepared = []
        skipped = []
        prepared_at = self._now() if request_timestamp is None else request_timestamp
        for requirement in sorted(
            review.requirements, key=lambda value: value.canonical_instrument
        ):
            if instrument is not None and requirement.canonical_instrument != instrument:
                continue
            package = next((
                item for item in review.chart_packages
                if item.binding.subject_kind == "NATIVE"
                and item.binding.native_run_identity == requirement.native_run_identity
                and item.binding.native_assessment_sha256
                == requirement.thesis.native_assessment_sha256
            ), None)
            if (
                package is None
                or package.missing_required_timeframes
                or len(package.active_revisions) != 1
            ):
                if instrument is not None:
                    raise PdfReviewTransportError(
                        f"REQUIRED_CHART_MISSING:{requirement.canonical_instrument}"
                    )
                skipped.append((requirement.canonical_instrument, "CHART REQUIRED"))
                continue
            revision = package.active_revisions[0]
            image = chart_bytes(revision)
            charts = chart_inputs_from_requirement(
                requirement,
                chart_identity=requirement.canonical_instrument,
                content_type=revision.content_type,
                images=(image, image, image, image),
            )
            prepared.append(self.cycle.prepare(
                requirement,
                facts,
                charts,
                request_timestamp=prepared_at,
                question_set_version=question_set_version,
            ))
        if not prepared:
            raise PdfReviewTransportError("REQUIRED_CHART_MISSING")
        return tuple(prepared), tuple(skipped)

    def _prepare_for_record(
        self,
        review: NativeReviewWorkflowSnapshot,
        facts: SameRunMtfFactSnapshot,
        chart_bytes,  # type: ignore[no-untyped-def]
        record: VisualV3LiveReviewPack,
    ) -> tuple[
        tuple[tuple[VisualEvidenceV3Request, ...], ...],
        tuple[tuple[str, str], ...],
    ]:
        prepared, skipped = self._prepare(
            review,
            facts,
            chart_bytes,
            (
                record.candidate_packs[0].canonical_instrument
                if record.scope == "INDIVIDUAL" else None
            ),
            request_timestamp=record.created_at,
            question_set_version=record.question_set_version,
        )
        expected = {
            item.canonical_instrument: item for item in record.candidate_packs
        }
        selected = tuple(
            requests for requests in prepared
            if requests[0].requirement.canonical_instrument in expected
        )
        if len(selected) != len(expected):
            raise PdfReviewTransportError("VISUAL_V3_REVIEW_PACK_SUPERSEDED")
        for requests in selected:
            pack = expected[requests[0].requirement.canonical_instrument]
            if (
                tuple((item.timeframe.value, item.chart_revision_sha256) for item in requests)
                != pack.chart_revisions
                or tuple((item.timeframe.value, item.machine_fact.integrity_sha256) for item in requests)
                != pack.machine_fact_bindings
            ):
                raise PdfReviewTransportError("VISUAL_V3_REVIEW_PACK_SUPERSEDED")
        return selected, skipped

    def _require_current(self, run_identity: str | None) -> VisualV3LiveReviewPack:
        if self._pack is None:
            raise PdfReviewTransportError("VISUAL_V3_REVIEW_PACK_UNAVAILABLE")
        if self._pack.native_run_identity != run_identity:
            raise PdfReviewTransportError("VISUAL_V3_REVIEW_PACK_SUPERSEDED")
        return self._pack

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("VISUAL_V3_LIVE_CLOCK_INVALID")
        return value


def _v3_layer2(
    requirement: NativeReviewRequirement,
    responses: tuple[VisualEvidenceV3Response, ...],
) -> NativeIndependentLayer2Evidence:
    """Bind Q1 chart validity without inventing support or contradiction."""

    by_timeframe = {item.timeframe: item for item in responses}
    states = []
    for factual in FactualTimeframe:
        visual = VisualTimeframe(factual.value)
        response = by_timeframe.get(visual)
        validation = None if response is None else next(
            item for item in response.observations
            if item.question_id is VisualQuestionV3.VISUAL_CHART_VALIDATION
        )
        states.append((
            factual,
            NativeLayer2EvidenceState.MIXED
            if validation is not None
            and validation.observation_status is VisualObservationStatus.OBSERVED
            else NativeLayer2EvidenceState.UNAVAILABLE,
        ))
    return NativeIndependentLayer2Evidence(
        requirement.native_run_identity,
        requirement.canonical_instrument,
        tuple(states),
        NativeLayer2EvidenceState.UNAVAILABLE,
        tuple(dict.fromkeys((
            VISUAL_QUESTION_SET_V3_ID,
            *(item.evidence_sha256 for item in responses),
        ))),
    )


__all__ = ["SwingVisualV3LiveSnapshot", "SwingVisualV3LiveWorkflow"]
