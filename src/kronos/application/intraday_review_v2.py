"""Explicit Sponsor-work seam from one governed Probables V2 run to Review."""

from __future__ import annotations

from kronos.intraday import visual_contract_v2 as visual_v2

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable

from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import (
    ProbableMemberResultV2,
    ProbablesRunV2,
    ProbablesV2Error,
)
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_answer import (
    MAX_ANSWER_BYTES,
    ChartAnalystAnswerPack,
    parse_answer_pack,
    parse_batch_answer_transport,
)
from kronos.intraday.review_v2 import (
    ChartRevisionV2,
    ImportedVisualEvidenceV2,
    ReviewCycleV2,
    ReviewHandoffV2,
    ReviewQuestionBatchV2,
    ReviewQuestionPackV2,
    create_chart_intake_request_v2,
    create_chart_revision_v2,
    create_current_chart_pointer_v2,
    create_current_review_pointer_v2,
    create_question_batch_v2,
    create_question_pack_v2,
    create_visual_evidence_pointer_v2,
    create_review_cycle_v2,
    create_review_handoff_v2,
    bind_imported_visual_evidence_v2,
)
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_v2_transport import (
    IntradayReviewV2Transport,
    ReviewBatchTransportV2,
    expected_transport_identity_v2,
)
from kronos.instrument.visual_identity import VisualIdentityResolver
from kronos.application.intraday_chart_input import IntradayChartInputGate
from kronos.application.intraday_review_v2_paired import IntradayReviewV2PairedAdapter


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
    question_transport_identity: str | None = None
    question_filename: str | None = None
    expected_answer_filename: str | None = None
    answer_pack_identity: str | None = None
    visual_evidence_identity: str | None = None
    observed_visible_subject_identity: str | None = None
    resolved_canonical_subject_identity: str | None = None
    visual_identity_relationship_identity: str | None = None
    visual_identity_publication_identity: str | None = None
    visual_identity_publication_version: str | None = None
    visual_identity_state: str = "NOT_RESOLVED"
    visual_evidence_state: str = "ABSENT"
    native_contract_identity: str | None = None
    native_binding_identity: str | None = None
    reference_context_identity: str | None = None
    paired_metadata_required: bool = False
    reference_observed_identity: str | None = None


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
class IntradayReviewV2Currentness:
    state: str
    current_probables_run_identity: str | None
    current_probables_pointer_integrity: str | None
    current_probables_publication_identity: str | None
    current_probables_analysis_boundary: datetime | None
    current_probables_candidate_population_identity: str | None
    current_probables_candidate_count: int
    current_review_probables_run_identity: str | None
    current_review_analysis_boundary: datetime | None
    current_review_candidate_count: int
    is_review_current: bool


@dataclass(frozen=True, slots=True)
class IntradayReviewV2Currentization:
    cycles: tuple[ReviewCycleV2, ...]
    retained: bool


@dataclass(frozen=True, slots=True)
class IntradayReviewV2BatchResult:
    batch: ReviewQuestionBatchV2
    transport: ReviewBatchTransportV2
    packs: tuple[ReviewQuestionPackV2, ...]
    question_path: Path
    answer_template_path: Path


@dataclass(frozen=True, slots=True)
class IntradayReviewV2PreImportValidation:
    review_batch_identity: str
    source_sha256: str
    candidate_count: int
    exact_match_count: int
    identity_mismatch_count: int
    schema_invalid_count: int
    conflict_count: int
    duplicate_count: int
    missing_count: int
    extra_count: int


@dataclass(frozen=True, slots=True)
class IntradayReviewV2ImportMemberResult:
    canonical_subject_identity: str
    state: str
    answer_pack_identity: str
    visual_evidence_identity: str
    observed_visible_subject_identity: str
    resolved_canonical_subject_identity: str
    visual_identity_relationship_identity: str
    visual_identity_publication_identity: str
    visual_identity_publication_version: str


@dataclass(frozen=True, slots=True)
class IntradayReviewV2BatchImportResult:
    operation_identity: str
    review_batch_identity: str
    source_sha256: str
    state: str
    imported_count: int
    members: tuple[IntradayReviewV2ImportMemberResult, ...]
    already_imported_count: int = 0
    rejected: tuple[IntradayReviewV2InboxMemberResult, ...] = ()


@dataclass(frozen=True, slots=True)
class IntradayReviewV2InboxMemberResult:
    canonical_subject_identity: str
    expected_answer_filename: str
    state: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class IntradayReviewV2InboxImportResult:
    mode: str
    current_review_count: int
    expected_count: int
    found_count: int
    imported_count: int
    already_imported_count: int
    not_found_count: int
    rejected_count: int
    members: tuple[IntradayReviewV2InboxMemberResult, ...]
    producer_advanced: bool = False

    @property
    def state(self) -> str:
        advanced = self.producer_advanced or any(item.reason == ReviewFailure.NOT_CURRENT.value for item in self.members)
        if advanced:
            return "PARTIAL_PRODUCER_ADVANCED" if self.imported_count else "REVIEW_NON_CURRENT"
        return "COMPLETE"


@dataclass(frozen=True, slots=True)
class _PreparedV2Import:
    validation: IntradayReviewV2PreImportValidation
    answers: tuple[ChartAnalystAnswerPack, ...]
    evidence: tuple[ImportedVisualEvidenceV2, ...]
    already_imported: tuple[bool, ...] = ()
    rejected: tuple[IntradayReviewV2InboxMemberResult, ...] = ()


class IntradayReviewV2Application:
    """No background hook: callers must explicitly supply the exact V2 run."""

    def __init__(
        self,
        *,
        probables_store: ProbablesV2Store,
        review_store: IntradayReviewV2Store,
        transport: IntradayReviewV2Transport | None = None,
        visual_identity_resolver: VisualIdentityResolver | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if (
            type(probables_store) is not ProbablesV2Store
            or type(review_store) is not IntradayReviewV2Store
            or transport is not None and type(transport) is not IntradayReviewV2Transport
            or visual_identity_resolver is not None
            and type(visual_identity_resolver) is not VisualIdentityResolver
            or not callable(clock)
        ):
            raise ValueError("INTRADAY_REVIEW_V2_APPLICATION_INVALID")
        self._probables = probables_store
        self._review = review_store
        self._transport = transport or IntradayReviewV2Transport()
        self._visual_identity_resolver = visual_identity_resolver
        self._clock = clock
        self._lock = review_store.workspace_lock
        self._chart_input = IntradayChartInputGate(review_store, probables_store, visual_identity_resolver, clock=lambda: self._clock())
        self._paired = IntradayReviewV2PairedAdapter(review_store, self._transport, chart_input=self._chart_input)

    @property
    def review_store(self) -> IntradayReviewV2Store:
        return self._review

    @property
    def probables_store(self) -> ProbablesV2Store:
        return self._probables

    def current_reconciliation(self):
        """Read-only exact-pointer contract adaptation; never invokes WO-10."""
        from kronos.application.intraday_review_wo10 import select_current_review

        with self._lock:
            probables_pointer, run = self._load_current_probables()
            pointer = self._review.load_current()
            if run is None or pointer is None or pointer.probables_run_identity != run.run_identity:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            if not self._review_cycles_match_run(run, self._cycles_for_pointer(pointer)):
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            selected = select_current_review(
                store=self._review, run=run, pointer=pointer,
                resolver=self._visual_identity_resolver,
            )
            if self._probables.load_current() != probables_pointer or self._review.load_current() != pointer:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            return selected

    def reconcile_current_ready(self, control):
        """Explicit current-only dispatch; retain WO-10's per-request semantics."""
        from kronos.application.intraday_review_wo10 import request_document

        with self._lock:
            selected = self.current_reconciliation()
            outcomes = []
            source_changed = False
            if control is not None:
                for request in selected.requests:
                    try:
                        if self.current_reconciliation() != selected:
                            raise ReviewError(ReviewFailure.NOT_CURRENT)
                    except (ReviewError, OSError):
                        source_changed = True
                        break
                    outcomes.append(control.execute_document(request_document(request)))
            succeeded = sum(item.get("outcome") in {"COMPLETED", "RETAINED"} for item in outcomes)
            return {
                **selected.status_document(),
                "outcome": (
                    "SOURCE_CHANGED" if source_changed else "GATED" if not outcomes
                    else "COMPLETED" if succeeded == len(outcomes) else "PARTIAL_FAILURE"
                ),
                "invocation_count": len(outcomes),
                "success_count": succeeded,
                "failure_count": len(outcomes) - succeeded,
                "not_dispatched_count": len(selected.requests) - len(outcomes),
                "results": outcomes,
            }

    def maintain_current_review(self):
        """Explicit reference-safe maintenance after current Review restoration.

        Neither GET nor startup invokes this path. Failure is separate from
        currentization and never makes a valid current Review unsuccessful.
        """
        from kronos.intraday.review_v2_gc import collect_review_components, ReviewGCResult
        with self._lock:
            try:
                if not self.currentness().is_review_current:
                    return ReviewGCResult(status="GC_DEFERRED_NOT_CURRENT")
                self.snapshot()
                return collect_review_components(self._review, self._transport)
            except (ReviewError, OSError, ValueError):
                return ReviewGCResult(status="GC_DEFERRED_INTEGRITY_OR_IO")

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

    def current_probables_run(self) -> ProbablesRunV2 | None:
        """Reload the explicit current Probables pointer and its full lineage."""

        _, run = self._load_current_probables()
        return run

    def currentness(self) -> IntradayReviewV2Currentness:
        """Compare exact governed identities; timestamps have no authority."""

        with self._lock, self._probables.current_generation_guard():
            return self._currentness_locked()

    def _currentness_locked(self) -> IntradayReviewV2Currentness:
        probables_pointer, run = self._load_current_probables()
        review_pointer = self._review.load_current()
        review_cycles = self._cycles_for_pointer(review_pointer)
        if probables_pointer is None or run is None:
            return IntradayReviewV2Currentness(
                state="NO_CURRENT_PROBABLES",
                current_probables_run_identity=None,
                current_probables_pointer_integrity=None,
                current_probables_publication_identity=None,
                current_probables_analysis_boundary=None,
                current_probables_candidate_population_identity=None,
                current_probables_candidate_count=0,
                current_review_probables_run_identity=(
                    None
                    if review_pointer is None
                    else review_pointer.probables_run_identity
                ),
                current_review_analysis_boundary=(
                    None if not review_cycles else review_cycles[0].analysis_boundary
                ),
                current_review_candidate_count=len(review_cycles),
                is_review_current=False,
            )
        eligible = _eligible_results(run)
        is_current = (
            review_pointer is not None
            and review_pointer.probables_run_identity == run.run_identity
            and self._review_cycles_match_run(run, review_cycles)
        )
        if (
            review_pointer is not None
            and review_pointer.probables_run_identity == run.run_identity
            and not is_current
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return IntradayReviewV2Currentness(
            state=(
                "REVIEW_CURRENT"
                if is_current
                else "NO_REVIEW_CANDIDATES"
                if not eligible
                else "REVIEW_ABSENT"
                if review_pointer is None
                else "NEW_PROBABLES_AVAILABLE"
            ),
            current_probables_run_identity=run.run_identity,
            current_probables_pointer_integrity=(
                probables_pointer.integrity_identity
            ),
            current_probables_publication_identity=(
                run.methodology.publication_identity
            ),
            current_probables_analysis_boundary=run.analysis_boundary,
            current_probables_candidate_population_identity=(
                _candidate_population_identity(run)
            ),
            current_probables_candidate_count=len(eligible),
            current_review_probables_run_identity=(
                None
                if review_pointer is None
                else review_pointer.probables_run_identity
            ),
            current_review_analysis_boundary=(
                None if not review_cycles else review_cycles[0].analysis_boundary
            ),
            current_review_candidate_count=len(review_cycles),
            is_review_current=is_current,
        )

    def workspace_state(self) -> str:
        currentness = self.currentness()
        if currentness.is_review_current:
            return "CURRENT_REVIEW_LOADED"
        return ("NO_REVIEW_LOADED" if currentness.current_review_probables_run_identity is None
                else "REVIEW_NON_CURRENT")

    def _require_current_workspace(self, run_identity=None, cycle_identity=None):
        currentness = self.currentness()
        pointer = self._review.load_current()
        if (not currentness.is_review_current or pointer is None
            or pointer.probables_run_identity != currentness.current_probables_run_identity
            or (run_identity is not None and pointer.probables_run_identity != run_identity)
            or (cycle_identity is not None and cycle_identity not in
                {item.cycle_identity for item in pointer.cycles})):
            raise ReviewError(ReviewFailure.NOT_CURRENT)
        return pointer

    def currentize_eligible_cycles_for_run_identity(
        self,
        *,
        probables_run_identity: str,
        methodology_identity: str,
        methodology_version: str,
        methodology_publication_identity: str,
        methodology_checksum: str,
    ) -> IntradayReviewV2Currentization:
        """Currentize Review only from the explicit current Probables pointer."""

        with self._lock:
            pointer, run = self._load_current_probables()
            if pointer is None or run is None:
                raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE)
            expected = (
                probables_run_identity,
                methodology_identity,
                methodology_version,
                methodology_publication_identity,
                methodology_checksum,
            )
            actual = (
                pointer.run_identity,
                run.methodology.methodology_identity,
                run.methodology.methodology_version,
                run.methodology.publication_identity,
                run.methodology.payload_checksum,
            )
            if actual != expected:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            review_pointer = self._review.load_current()
            if (
                review_pointer is not None
                and review_pointer.probables_run_identity == run.run_identity
            ):
                cycles = self._cycles_for_pointer(review_pointer)
                if not self._review_cycles_match_run(run, cycles):
                    raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
                with self._probables.current_generation_guard():
                    self._require_current_workspace(run.run_identity)
                    return IntradayReviewV2Currentization(cycles, True)
            cycles = self._retain_eligible_cycles(run)
            current_pointer, current_run = self._load_current_probables()
            if (
                current_pointer is None
                or current_run is None
                or current_pointer.run_identity != pointer.run_identity
                or current_run != run
            ):
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            self._publish_current_review(run, cycles)
            return IntradayReviewV2Currentization(cycles, False)

    def snapshot(self) -> IntradayReviewV2Snapshot:
        """Project persisted Phase-A facts without creating or advancing Review."""

        with self._lock, self._probables.current_generation_guard():
            if not self.currentness().is_review_current:
                return IntradayReviewV2Snapshot(None, None, ())
            return self._loaded_snapshot()

    def _loaded_snapshot(self) -> IntradayReviewV2Snapshot:
        pointer = self._require_current_workspace()
        cycles = tuple(
            sorted(
                (self._review.load_cycle(item.cycle_identity) for item in pointer.cycles),
                key=lambda item: _sponsor_label(item.canonical_subject_identity).casefold(),
            )
        )
        packs: list[ReviewQuestionPackV2] = []
        individual_transports: dict[str, ReviewBatchTransportV2] = {}
        for cycle in cycles:
            retained = self._load_retained_current_pack(cycle)
            if retained is not None:
                packs.append(retained)
                individual = self._load_retained_transport((retained,))
                if individual is not None:
                    individual_transports[cycle.cycle_identity] = individual
        batch = None
        transport = None
        if packs and len(packs) == len(cycles):
            expected_batch = create_question_batch_v2(tuple(packs))
            transport = self._load_retained_transport(tuple(packs))
            if transport is not None:
                batch = self._review.load_batch(expected_batch.batch_identity)
        ready_pack_ids = {item.review_pack_identity for item in packs}
        return IntradayReviewV2Snapshot(
            probables_run_identity=pointer.probables_run_identity,
            current_pointer_identity=pointer.integrity_identity,
            candidates=tuple(
                self._candidate_snapshot(
                    cycle,
                    ready_pack_ids,
                    individual_transports.get(cycle.cycle_identity),
                )
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
        transport: ReviewBatchTransportV2 | None = None,
    ) -> IntradayReviewV2CandidateSnapshot:
        active = self._review.load_current_chart(cycle.cycle_identity)
        pack_ready = False
        retained_pack = self._load_retained_current_pack(cycle) if active is not None else None
        if retained_pack is not None and ready_pack_ids is not None:
            pack_ready = retained_pack.review_pack_identity in ready_pack_ids
        evidence = self._review.load_visual_evidence_for_pack(retained_pack.review_pack_identity) if pack_ready else None
        candidate = IntradayReviewV2CandidateSnapshot(
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
                "TRANSPORT_READY" if pack_ready and transport is not None
                else "CREATED" if pack_ready else "ABSENT"
            ),
            answer_state="IMPORTED" if evidence is not None else cycle.answer_state.value,
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
            question_transport_identity=(
                None if transport is None else transport.transport_identity
            ),
            question_filename=(
                None if transport is None else transport.question_filename
            ),
            expected_answer_filename=(
                None if transport is None else transport.expected_answer_filename
            ),
            answer_pack_identity=(
                None if evidence is None else evidence.answer_pack_identity
            ),
            visual_evidence_identity=(
                None if evidence is None else evidence.visual_evidence_identity
            ),
            observed_visible_subject_identity=(
                None if evidence is None else evidence.observed_visible_subject_identity
            ),
            resolved_canonical_subject_identity=(
                None if evidence is None else evidence.resolved_canonical_subject_identity
            ),
            visual_identity_relationship_identity=(
                None
                if evidence is None
                else evidence.visual_identity_relationship_identity
            ),
            visual_identity_publication_identity=(
                None
                if evidence is None
                else evidence.visual_identity_publication_identity
            ),
            visual_identity_publication_version=(
                None
                if evidence is None
                else evidence.visual_identity_publication_version
            ),
            visual_identity_state="MATCH" if evidence is not None else "NOT_RESOLVED",
            visual_evidence_state="READY" if evidence is not None else "ABSENT",
        )

        if not cycle.canonical_subject_identity.startswith("MCX-SUBJECT-"):
            return candidate
        options = {}
        try:
            options = self._paired.options(cycle)
        except ReviewError:
            pass
        candidate = replace(candidate, paired_metadata_required=True,
            chart_state="CHART_REQUIRED", **options)
        if active is None:
            return candidate
        chart = self._review.load_chart(active.chart_revision_identity)
        if chart.paired_bundle_identity is None:
            return candidate
        self._paired.restore(cycle, chart)
        candidate = replace(candidate, chart_state="CHART_READY", paired_metadata_required=False)
        retained = self._paired.retained(cycle, chart)
        if retained is None:
            return candidate
        pack, transport = retained[3:5]
        evidence = self._paired.retained_evidence(pack, chart)
        return replace(candidate, review_pack_state="READY", question_pack_state="TRANSPORT_READY",
            question_transport_identity=transport.transport_identity,
            question_filename=transport.question_filename, expected_answer_filename=transport.expected_answer_filename,
            answer_state="IMPORTED" if evidence else "NOT_IMPORTED",
            answer_pack_identity=evidence.answer_pack_identity if evidence else None,
            visual_evidence_identity=evidence.visual_evidence_identity if evidence else None,
            visual_identity_state="MATCH" if evidence else "NOT_RESOLVED",
            visual_evidence_state="READY" if evidence else "ABSENT",
            observed_visible_subject_identity=evidence.native_observed_visible_identity if evidence else None,
            resolved_canonical_subject_identity=cycle.canonical_subject_identity if evidence else None,
            reference_observed_identity=evidence.reference_observed_visible_identity if evidence else None)

    def _review_selection(self, cycle):
        handoff = self._review.load_handoff(cycle.handoff_identity)
        return self._probables.load_selection(handoff.completed_evidence_selection_identity)

    def _load_retained_current_pack(
        self, cycle: ReviewCycleV2,
    ) -> ReviewQuestionPackV2 | None:
        if cycle.canonical_subject_identity.startswith("MCX-SUBJECT-"):
            return None
        active = self._review.load_current_chart(cycle.cycle_identity)
        if active is None:
            return None
        # Probe only the two exact governed identities for this current chart.
        # A newly retained V2 pack supersedes the V1 working pack, never its evidence.
        for version in (visual_v2.VERSION, "1.0.0"):
            expected = create_question_pack_v2(
                self._review.load_handoff(cycle.handoff_identity), cycle,
                self._review.load_chart(active.chart_revision_identity), question_version=version, completed_selection=self._review_selection(cycle))
            try:
                retained = self._review.load_pack(expected.review_pack_identity)
            except ReviewError as error:
                if error.failure is ReviewFailure.ARTIFACT_UNAVAILABLE:
                    continue
                raise
            if retained != expected:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            return retained
        return None

    def _load_retained_transport(
        self, packs: tuple[ReviewQuestionPackV2, ...], *, current_edition_only: bool = False,
    ) -> ReviewBatchTransportV2 | None:
        expected_batch = create_question_batch_v2(packs)
        modern = all(pack.question_set_version == visual_v2.VERSION for pack in packs)
        versions = ("2.3.0",) if current_edition_only and modern else ("2.3.0", "2.2.0", "2.1.0", "2.0.0")
        for version in versions:
            try:
                batch = self._review.load_batch(expected_batch.batch_identity)
                transport = self._review.load_transport(
                    expected_transport_identity_v2(expected_batch, version=version))
            except ReviewError as error:
                if error.failure is ReviewFailure.ARTIFACT_UNAVAILABLE:
                    continue
                raise
            if batch != expected_batch or transport.review_batch_identity != batch.batch_identity:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            return transport
        return None

    def validate_combined_answer(
        self, payload: bytes,
    ) -> IntradayReviewV2PreImportValidation:
        """Validate one exact combined V2 Answer without persistence."""

        with self._lock:
            return self._prepare_combined_answer(payload).validation

    def import_combined_answer(
        self, payload: bytes,
    ) -> IntradayReviewV2BatchImportResult:
        """Persist one prevalidated combined Answer as candidate-isolated evidence."""

        with self._lock:
            prepared = self._prepare_combined_answer(payload)
            prepared = self._persist_prepared_answer(prepared, payload)
            members = []
            for evidence, already in zip(prepared.evidence, prepared.already_imported, strict=True):
                members.append(IntradayReviewV2ImportMemberResult(
                    canonical_subject_identity=evidence.expected_canonical_subject_identity,
                    state="ALREADY_IMPORTED" if already else "IMPORTED",
                    answer_pack_identity=evidence.answer_pack_identity,
                    visual_evidence_identity=evidence.visual_evidence_identity,
                    observed_visible_subject_identity=evidence.observed_visible_subject_identity,
                    resolved_canonical_subject_identity=evidence.resolved_canonical_subject_identity,
                    visual_identity_relationship_identity=evidence.visual_identity_relationship_identity,
                    visual_identity_publication_identity=evidence.visual_identity_publication_identity,
                    visual_identity_publication_version=evidence.visual_identity_publication_version,
                ))
            operation_values = {
                "review_batch_identity": prepared.validation.review_batch_identity,
                "source_sha256": prepared.validation.source_sha256,
                "visual_evidence_identities": tuple(
                    item.visual_evidence_identity for item in members
                ),
            }
            operation_identity = (
                "INTRADAY-V2-ANSWER-IMPORT-OPERATION-"
                + sha256(json.dumps(
                    operation_values,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()).hexdigest().upper()
            )
            return IntradayReviewV2BatchImportResult(
                operation_identity=operation_identity,
                review_batch_identity=prepared.validation.review_batch_identity,
                source_sha256=prepared.validation.source_sha256,
                state=("ALREADY_IMPORTED" if prepared.evidence and all(prepared.already_imported)
                       else "PARTIAL_PRODUCER_ADVANCED" if prepared.rejected or not self.currentness().is_review_current
                       else "IMPORTED"),
                imported_count=sum(not value for value in prepared.already_imported),
                already_imported_count=sum(prepared.already_imported),
                rejected=prepared.rejected,
                members=tuple(members),
            )

    def _current_cycle_chart(self, cycle_identity):
        cycle = self._review.load_cycle(cycle_identity)
        active = self._review.load_current_chart(cycle_identity)
        if active is None:
            raise ReviewError(ReviewFailure.CHART_REQUIRED)
        return cycle, self._review.load_chart(active.chart_revision_identity)

    def _import_paired_expected(self, cycle, chart):
        with self._probables.current_generation_guard():
            return self._paired.import_expected(cycle, chart, self._clock(),
                require_current=lambda: self._require_current_workspace(
                    cycle.probables_run_identity, cycle.cycle_identity))

    def _include_paired_imports(self, result, cycles):
        members = {item.canonical_subject_identity: item for item in result.members}
        for cycle in cycles:
            if not cycle.canonical_subject_identity.startswith("MCX-SUBJECT-"):
                continue
            active = self._review.load_current_chart(cycle.cycle_identity)
            if active is None:
                continue
            chart = self._review.load_chart(active.chart_revision_identity)
            if chart.paired_bundle_identity is None or self._paired.retained(cycle, chart) is None:
                continue
            paired = self._import_paired_expected(cycle, chart)
            members.update({item.canonical_subject_identity: item for item in paired.members})
        values = tuple(members.values())
        return replace(result, members=values, expected_count=len(values),
            found_count=sum(x.state != "NOT_FOUND" for x in values),
            imported_count=sum(x.state == "IMPORTED" for x in values),
            already_imported_count=sum(x.state == "ALREADY_IMPORTED" for x in values),
            not_found_count=sum(x.state == "NOT_FOUND" for x in values),
            rejected_count=sum(x.state == "REJECTED" for x in values),
            producer_advanced=not self.currentness().is_review_current)

    def import_expected_answer(
        self, cycle_identity: str,
    ) -> IntradayReviewV2InboxImportResult:
        """Import only one current candidate's exact expected inbox file."""

        with self._lock:
            cycle, chart = self._current_cycle_chart(cycle_identity)
            if cycle.canonical_subject_identity.startswith("MCX-SUBJECT-"):
                return self._import_paired_expected(cycle, chart)
            pack = self._load_retained_current_pack(cycle)
            if pack is None:
                raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE)
            transport = self._load_retained_transport((pack,))
            if transport is None:
                raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE)
            return self._import_inbox_transport(transport, current_review_count=1)

    def import_all_expected_answers(self) -> IntradayReviewV2InboxImportResult:
        """Import exact current Answers on Sponsor request; never poll the inbox."""

        with self._lock:
            pointer = self._require_current_workspace()
            if pointer is None:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            cycles = tuple(
                self._review.load_cycle(item.cycle_identity) for item in pointer.cycles
            )
            packs = tuple(
                pack for cycle in cycles
                if (pack := self._load_retained_current_pack(cycle)) is not None
            )
            # Existing governed combined mode has precedence only when its exact
            # expected file is present. Otherwise independent current Answers
            # are considered, so partial availability remains useful.
            combined = self._current_run_combined_transport(cycles)
            if combined is not None:
                try:
                    payload = self._transport.read_expected_answer(
                        combined.expected_answer_filename
                    )
                except ReviewError as error:
                    return IntradayReviewV2InboxImportResult(
                        mode="COMBINED",
                        current_review_count=len(cycles),
                        expected_count=len(cycles),
                        found_count=len(cycles),
                        imported_count=0,
                        already_imported_count=0,
                        not_found_count=0,
                        rejected_count=len(cycles),
                        members=tuple(
                            IntradayReviewV2InboxMemberResult(
                                item.canonical_subject_identity,
                                combined.expected_answer_filename,
                                "REJECTED",
                                error.failure.value,
                            ) for item in cycles
                        ),
                    )
                if payload is not None:
                    return self._include_paired_imports(self._import_inbox_transport(
                        combined, current_review_count=len(cycles), payload=payload, mode="COMBINED"), cycles)
            totals = {
                "expected_count": 0,
                "found_count": 0,
                "imported_count": 0,
                "already_imported_count": 0,
                "not_found_count": 0,
                "rejected_count": 0,
            }
            members: list[IntradayReviewV2InboxMemberResult] = []
            for pack in packs:
                transport = self._load_retained_transport((pack,))
                if transport is None:
                    continue
                result = self._import_inbox_transport(
                    transport, current_review_count=len(cycles)
                )
                for name in totals:
                    totals[name] += getattr(result, name)
                members.extend(result.members)
            return self._include_paired_imports(IntradayReviewV2InboxImportResult(
                mode="INDIVIDUAL",
                current_review_count=len(cycles),
                members=tuple(members),
                producer_advanced=not self.currentness().is_review_current,
                **totals,
            ), cycles)

    def _current_run_combined_transport(self, cycles):
        """Unique retained full-population transport; stale members reject individually.

        No filename, mtime or directory-order preference is used. Multiple
        matching transports are ambiguous and fail closed.
        """
        # Mixed batches retain one ordinary NSE transport plus independent paired
        # transports. Select the exact current NSE population deterministically.
        nse_cycles = tuple(cycle for cycle in cycles
                           if not cycle.canonical_subject_identity.startswith("MCX-SUBJECT-"))
        current_packs = tuple(self._load_retained_current_pack(cycle) for cycle in nse_cycles)
        if current_packs and all(pack is not None for pack in current_packs):
            current = self._load_retained_transport(current_packs)
            if current is not None:
                return current
        expected = {item.cycle_identity: item.canonical_subject_identity for item in cycles}
        matches = []
        for path in (self._review.root / "question-batches").glob("*.json"):
            batch = self._review.load_batch(path.stem)
            if (not cycles or batch.probables_run_identity != cycles[0].probables_run_identity
                or dict(zip(batch.review_cycle_identities, batch.candidate_identities, strict=True)) != expected):
                continue
            transport = self._load_retained_transport(tuple(
                self._review.load_pack(identity) for identity in batch.review_pack_identities))
            if transport is None:
                continue
            if transport.review_batch_identity != batch.batch_identity:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            matches.append(transport)
        if len(matches) > 1:
            raise ReviewError(ReviewFailure.ANSWER_CONFLICT)
        return matches[0] if matches else None

    def _import_inbox_transport(
        self,
        transport: ReviewBatchTransportV2,
        *,
        current_review_count: int,
        payload: bytes | None = None,
        mode: str = "INDIVIDUAL",
    ) -> IntradayReviewV2InboxImportResult:
        filename = transport.expected_answer_filename
        candidate_count = transport.candidate_count
        candidate_names = tuple(
            self._review.load_batch(transport.review_batch_identity).candidate_identities
        )
        try:
            supplied = (
                payload if payload is not None
                else self._transport.read_expected_answer(filename)
            )
            if supplied is None:
                return IntradayReviewV2InboxImportResult(
                    mode=mode,
                    current_review_count=current_review_count,
                    expected_count=candidate_count,
                    found_count=0,
                    imported_count=0,
                    already_imported_count=0,
                    not_found_count=candidate_count,
                    rejected_count=0,
                    members=tuple(
                        IntradayReviewV2InboxMemberResult(
                            item, filename, "NOT_FOUND"
                        ) for item in candidate_names
                    ),
                )
            prepared = self._prepare_transport_answer(transport, supplied)
            if prepared.evidence:
                prepared = self._persist_prepared_answer(prepared, supplied)
            members = tuple(
                IntradayReviewV2InboxMemberResult(
                    evidence.expected_canonical_subject_identity,
                    filename,
                    "ALREADY_IMPORTED" if already else "IMPORTED",
                )
                for evidence, already in zip(
                    prepared.evidence, prepared.already_imported, strict=True
                )
            )
            members += tuple(replace(item, expected_answer_filename=filename) for item in prepared.rejected)
            already_count = sum(prepared.already_imported)
            return IntradayReviewV2InboxImportResult(
                mode=mode,
                current_review_count=current_review_count,
                expected_count=candidate_count,
                found_count=candidate_count,
                imported_count=len(prepared.evidence) - already_count,
                already_imported_count=already_count,
                not_found_count=0,
                rejected_count=len(prepared.rejected),
                producer_advanced=not self.currentness().is_review_current,
                members=members,
            )
        except ReviewError as error:
            return IntradayReviewV2InboxImportResult(
                mode=mode,
                current_review_count=current_review_count,
                expected_count=candidate_count,
                found_count=candidate_count,
                imported_count=0,
                already_imported_count=0,
                not_found_count=0,
                rejected_count=candidate_count,
                members=tuple(
                    IntradayReviewV2InboxMemberResult(
                        item, filename, "REJECTED", error.failure.value
                    ) for item in candidate_names
                ),
            )

    def _prepare_transport_answer(
        self, transport: ReviewBatchTransportV2, payload: bytes,
    ) -> _PreparedV2Import:
        if (
            type(payload) is not bytes
            or not 0 < len(payload) <= MAX_ANSWER_BYTES
            or self._visual_identity_resolver is None
            or self._review.load_transport(transport.transport_identity) != transport
        ):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        batch = self._review.load_batch(transport.review_batch_identity)
        answer_transport = parse_batch_answer_transport(payload)
        if (
            answer_transport.review_batch_identity != batch.batch_identity
            or answer_transport.probables_run_identity != batch.probables_run_identity
        ):
            raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
        current_members = {identity: self._review.load_cycle(identity)
                           for identity in batch.review_cycle_identities}
        packs: list[ReviewQuestionPackV2] = []
        for cycle_identity, pack_identity, candidate_identity in zip(
            batch.review_cycle_identities,
            batch.review_pack_identities,
            batch.candidate_identities,
            strict=True,
        ):
            member = current_members.get(cycle_identity)
            if member is None or member.canonical_subject_identity != candidate_identity:
                raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
            pack = self._review.load_pack(pack_identity)
            if (pack.review_cycle_identity != cycle_identity
                or pack.expected_canonical_subject_identity != candidate_identity
                or pack.probables_run_identity != batch.probables_run_identity):
                raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
            packs.append(pack)
        if create_question_batch_v2(tuple(packs)) != batch:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        documents = answer_transport.candidate_documents
        identities = tuple(item.get("review_pack_identity") for item in documents)
        if (any(type(item) is not str for item in identities)
            or len(identities) != len(set(identities))
            or set(identities) != set(batch.review_pack_identities)):
            raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
        pack_by_identity = {item.review_pack_identity: item for item in packs}
        prepared, rejected, parsed = [], [], []
        schema_invalid = 0
        for document in documents:
            try:
                parsed.append(parse_answer_pack(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()))
            except ReviewError as error:
                schema_invalid += 1
                pack = pack_by_identity[document["review_pack_identity"]]
                rejected.append(IntradayReviewV2InboxMemberResult(pack.expected_canonical_subject_identity,
                    transport.expected_answer_filename, "REJECTED", error.failure.value))
        imported_at = self._clock()
        for answer in parsed:
            pack = pack_by_identity[answer.review_pack_identity]
            try:
                # The generic V2 pack cannot qualify paired MCX contract evidence.
                # Retained generic packs remain available only for exact transport
                # accounting and history, never as a native acceptance fallback.
                if pack.expected_canonical_subject_identity.startswith("MCX-SUBJECT-"):
                    raise ReviewError(ReviewFailure.CHART_INVALID)
                existing = self._review.load_visual_evidence_for_pack(
                    pack.review_pack_identity
                )
                if existing is not None:
                    if existing.answer_pack_identity != answer.answer_pack_identity:
                        raise ReviewError(ReviewFailure.ANSWER_CONFLICT)
                    prepared.append((answer, existing, True))
                    continue
                self._require_current_workspace(pack.probables_run_identity, pack.review_cycle_identity)
                if self._current_pack(pack.review_cycle_identity, require_retained=True) != pack:
                    raise ReviewError(ReviewFailure.NOT_CURRENT)
                evidence = bind_imported_visual_evidence_v2(
                    pack,
                    answer,
                    imported_at=imported_at,
                    visual_identity_resolver=self._visual_identity_resolver,
                )
                from kronos.intraday.analyst_chart_observation import receipt as prepare_receipt
                header = json.loads(answer.chart_observation_header) if answer.chart_observation_header else None
                if header and header["schema_version"] == "1.1.0" and transport.schema_version != "2.3.0":
                    raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
                chart = self._review.load_chart(pack.chart_revision_identity)
                observation = prepare_receipt(answer, pack, chart, self._review, imported_at=imported_at)
                self._chart_input.require(
                    self._review.load_cycle(pack.review_cycle_identity),
                    self._review.load_chart(pack.chart_revision_identity),
                    observed_native=answer.observed_visible_subject_identity, visual_answers=answer.answers, receipt=observation,
                )
                prepared.append((answer, evidence, False))
            except ReviewError as error:
                rejected.append(IntradayReviewV2InboxMemberResult(
                    pack.expected_canonical_subject_identity,
                    transport.expected_answer_filename,
                    "REJECTED",
                    error.failure.value,
                ))
        ordered = tuple(sorted(
            prepared, key=lambda item: item[1].expected_canonical_subject_identity
        ))
        validation = IntradayReviewV2PreImportValidation(
            review_batch_identity=batch.batch_identity,
            source_sha256=answer_transport.source_sha256,
            candidate_count=len(documents),
            exact_match_count=len(ordered),
            identity_mismatch_count=len(rejected) - schema_invalid,
            schema_invalid_count=schema_invalid,
            conflict_count=0,
            duplicate_count=0,
            missing_count=0,
            extra_count=0,
        )
        return _PreparedV2Import(
            validation=validation,
            answers=tuple(item[0] for item in ordered),
            evidence=tuple(item[1] for item in ordered),
            already_imported=tuple(item[2] for item in ordered),
            rejected=tuple(rejected),
        )

    def _persist_prepared_answer(
        self, prepared: _PreparedV2Import, payload: bytes,
    ) -> _PreparedV2Import:
        accepted = []
        rejected = list(prepared.rejected)
        for answer, evidence, already in zip(
            prepared.answers, prepared.evidence, prepared.already_imported, strict=True
        ):
            if already:
                accepted.append((answer, evidence, True))
                continue
            try:
                with self._probables.current_generation_guard():
                    pack = self._review.load_pack(evidence.review_pack_identity)
                    from kronos.intraday.analyst_chart_observation import receipt as prepare_receipt
                    chart = self._review.load_chart(pack.chart_revision_identity)
                    observation = prepare_receipt(answer, pack, chart, self._review, imported_at=evidence.imported_at)
                    self._chart_input.require(
                        self._review.load_cycle(pack.review_cycle_identity),
                        self._review.load_chart(pack.chart_revision_identity),
                        observed_native=answer.observed_visible_subject_identity, visual_answers=answer.answers, receipt=observation,
                    )
                    self._require_current_workspace(pack.probables_run_identity, pack.review_cycle_identity)
                    if self._current_pack(pack.review_cycle_identity, require_retained=True) != pack:
                        raise ReviewError(ReviewFailure.NOT_CURRENT)
                    if observation is not None:
                        self._review.retain_chart_input(observation)
                    self._review.retain_batch_answer_transport(
                        prepared.validation.review_batch_identity, payload)
                    self._review.retain_answer_transport(
                        evidence.review_pack_identity,
                        json.dumps(_answer_document(answer), sort_keys=True, separators=(",", ":")).encode(),
                    )
                    self._review.retain_visual_evidence(evidence)
                    self._review.save_visual_evidence_pointer(create_visual_evidence_pointer_v2(evidence))
                    accepted.append((answer, evidence, False))
            except ReviewError as error:
                if error.failure is not ReviewFailure.NOT_CURRENT:
                    raise
                rejected.append(IntradayReviewV2InboxMemberResult(
                    evidence.expected_canonical_subject_identity, "", "REJECTED", error.failure.value))
        # There is no batch currentization. Each accepted member is immutable;
        # the caller reports partial completion and currentness at final return.
        return replace(prepared, answers=tuple(x[0] for x in accepted),
                       evidence=tuple(x[1] for x in accepted),
                       already_imported=tuple(x[2] for x in accepted), rejected=tuple(rejected))

    def _current_pack(
        self, cycle_identity: str, *, require_retained: bool,
    ) -> ReviewQuestionPackV2:
        pointer = self._review.load_current()
        if pointer is None or not any(
            item.cycle_identity == cycle_identity for item in pointer.cycles
        ):
            raise ReviewError(ReviewFailure.NOT_CURRENT)
        cycle = self._review.load_cycle(cycle_identity)
        active = self._review.load_current_chart(cycle_identity)
        if active is None:
            raise ReviewError(ReviewFailure.CHART_REQUIRED)
        expected = create_question_pack_v2(
            self._review.load_handoff(cycle.handoff_identity),
            cycle,
            self._review.load_chart(active.chart_revision_identity), question_version=visual_v2.VERSION, completed_selection=self._review_selection(cycle),
        )
        if not require_retained:
            return expected
        retained = self._load_retained_current_pack(cycle)
        if retained is None:
            raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE)
        return retained

    def _prepare_combined_answer(self, payload: bytes) -> _PreparedV2Import:
        if (
            type(payload) is not bytes
            or not 0 < len(payload) <= MAX_ANSWER_BYTES
            or self._visual_identity_resolver is None
        ):
            raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
        transport_answer = parse_batch_answer_transport(payload)
        batch = self._review.load_batch(transport_answer.review_batch_identity)
        packs = tuple(self._review.load_pack(identity) for identity in batch.review_pack_identities)
        if create_question_batch_v2(packs) != batch:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        if transport_answer.probables_run_identity != batch.probables_run_identity:
            raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)

        documents = transport_answer.candidate_documents
        parsed_answers = tuple(
            parse_answer_pack(json.dumps(
                document, sort_keys=True, separators=(",", ":")
            ).encode())
            for document in documents
        )
        raw_pack_ids = tuple(item.review_pack_identity for item in parsed_answers)
        duplicate_count = len(raw_pack_ids) - len(set(raw_pack_ids))
        expected_ids = set(batch.review_pack_identities)
        received_ids = set(raw_pack_ids)
        missing_count = len(expected_ids - received_ids)
        extra_count = len(received_ids - expected_ids)
        if duplicate_count or missing_count or extra_count:
            raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
        pack_by_identity = {item.review_pack_identity: item for item in packs}
        imported_at = self._clock()
        answers = []
        evidence = []
        for answer in parsed_answers:
            pack = pack_by_identity.get(answer.review_pack_identity)
            if pack is None:
                raise ReviewError(ReviewFailure.ANSWER_IDENTITY_MISMATCH)
            existing = self._review.load_visual_evidence_for_pack(pack.review_pack_identity)
            if existing is not None:
                if existing.answer_pack_identity != answer.answer_pack_identity:
                    raise ReviewError(ReviewFailure.ANSWER_CONFLICT)
                answers.append(answer)
                evidence.append(existing)
                continue
            self._require_current_workspace(pack.probables_run_identity, pack.review_cycle_identity)
            if self._current_pack(pack.review_cycle_identity, require_retained=True) != pack:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            if pack.expected_canonical_subject_identity.startswith("MCX-SUBJECT-"):
                raise ReviewError(ReviewFailure.CHART_INVALID)
            bound = bind_imported_visual_evidence_v2(
                pack,
                answer,
                imported_at=imported_at,
                visual_identity_resolver=self._visual_identity_resolver,
            )
            from kronos.intraday.analyst_chart_observation import receipt as prepare_receipt
            chart = self._review.load_chart(pack.chart_revision_identity)
            observation = prepare_receipt(answer, pack, chart, self._review, imported_at=imported_at)
            self._chart_input.require(
                self._review.load_cycle(pack.review_cycle_identity),
                self._review.load_chart(pack.chart_revision_identity),
                observed_native=answer.observed_visible_subject_identity, visual_answers=answer.answers, receipt=observation,
            )
            answers.append(answer)
            evidence.append(bound)
        ordered = tuple(sorted(
            zip(answers, evidence, strict=True),
            key=lambda item: item[1].expected_canonical_subject_identity,
        ))
        validation = IntradayReviewV2PreImportValidation(
            review_batch_identity=batch.batch_identity,
            source_sha256=transport_answer.source_sha256,
            candidate_count=len(ordered),
            exact_match_count=len(ordered),
            identity_mismatch_count=0,
            schema_invalid_count=0,
            conflict_count=0,
            duplicate_count=0,
            missing_count=0,
            extra_count=0,
        )
        return _PreparedV2Import(
            validation=validation,
            answers=tuple(item[0] for item in ordered),
            evidence=tuple(item[1] for item in ordered),
            already_imported=tuple(self._review.load_visual_evidence_for_pack(item[1].review_pack_identity) is not None
                                   for item in ordered),
        )

    def upload_chart(
        self,
        cycle_identity: str,
        *,
        media_type: str,
        payload: bytes,
        paired_metadata: dict[str, str] | None = None,
    ) -> ChartRevisionV2:
        """Retain one exact-cycle chart without mutating the Review Cycle."""

        with self._lock, self._probables.current_generation_guard():
            pointer = self._require_current_workspace()
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

            is_mcx = cycle.canonical_subject_identity.startswith("MCX-SUBJECT-")
            if is_mcx:
                self._paired.validate_metadata(cycle, paired_metadata)
            elif paired_metadata is not None:
                raise ReviewError(ReviewFailure.CHART_INVALID)
            request = create_chart_intake_request_v2(
                cycle,
                payload=payload,
                media_type=media_type,
                requested_at=self._clock(),
            )
            self._require_current_workspace(cycle.probables_run_identity, cycle_identity)
            self._review.retain_chart_request(request)
            active_pointer = self._review.load_current_chart(cycle_identity)
            if (
                active_pointer is not None
                and active_pointer.payload_sha256 == sha256(payload).hexdigest()
                and active_pointer.media_type == media_type
                and (not is_mcx or self._review.load_chart(active_pointer.chart_revision_identity).paired_bundle_identity is not None)
            ):
                retained = self._review.load_chart(active_pointer.chart_revision_identity)
                if not is_mcx:
                    return retained
                bundle, _, _ = self._paired.restore(cycle, retained)
                if (bundle.native_identity_binding.active_binding_identity == paired_metadata["native_binding_identity"]
                    and bundle.native_identity_binding.actual_derivative_contract_identity == paired_metadata["native_contract_identity"]
                    and bundle.reference_relationship.governed_visible_identity == paired_metadata["reference_context_identity"]):
                    return retained

            ordinal = 1 if active_pointer is None else active_pointer.revision_ordinal + 1
            received_at = self._clock()
            bundle = (self._paired.prepare(cycle, paired_metadata, payload, media_type, ordinal, received_at)
                      if is_mcx else None)
            chart = create_chart_revision_v2(
                cycle,
                revision_ordinal=(
                    1 if active_pointer is None
                    else active_pointer.revision_ordinal + 1
                ),
                payload=payload,
                media_type=media_type,
                received_at=received_at,
                paired_bundle_identity=bundle.bundle_identity if bundle else None,
                request_identity=request.request_identity,
            )
            current = create_current_chart_pointer_v2(cycle, request, chart)
            self._require_current_workspace(cycle.probables_run_identity, cycle_identity)
            self._review.retain_chart(chart, payload)
            self._review.save_current_chart(current)
            return chart

    def create_all_question_transports(self) -> tuple:
        """Sponsor batch action: one exact individual PDF/Answer identity per cycle."""
        with self._lock, self._probables.current_generation_guard():
            pointer = self._require_current_workspace()
            if pointer is None or not pointer.cycles:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            # Preserve batch chart prerequisites before publishing any member.
            for member in pointer.cycles:
                active = self._review.load_current_chart(member.cycle_identity)
                if active is None:
                    raise ReviewError(ReviewFailure.CHART_REQUIRED)
                self._review.load_chart_bytes(self._review.load_chart(active.chart_revision_identity))
            return tuple(self.create_individual_question_transport(member.cycle_identity)
                         for member in pointer.cycles)

    def create_combined_question_transport(self) -> IntradayReviewV2BatchResult:
        """Create exact V2 packs and one immutable combined Question transport."""

        with self._lock, self._probables.current_generation_guard():
            pointer = self._require_current_workspace()
            if pointer is None or not pointer.cycles:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            entries: list[tuple[ReviewQuestionPackV2, bytes]] = []
            paired_results = []
            for cycle_pointer in pointer.cycles:
                cycle = self._review.load_cycle(cycle_pointer.cycle_identity)
                active = self._review.load_current_chart(cycle.cycle_identity)
                if active is None:
                    raise ReviewError(ReviewFailure.CHART_REQUIRED)
                chart = self._review.load_chart(active.chart_revision_identity)
                if cycle.canonical_subject_identity.startswith("MCX-SUBJECT-"):
                    paired_results.append(self._paired.create(cycle, chart, require_current=lambda: self._require_current_workspace(
                        cycle.probables_run_identity, cycle.cycle_identity)))
                    continue
                handoff = self._review.load_handoff(cycle.handoff_identity)
                pack = create_question_pack_v2(handoff, cycle, chart, question_version=visual_v2.VERSION, completed_selection=self._review_selection(cycle))
                entries.append((pack, self._review.load_chart_bytes(chart)))
            return self._create_question_transport(tuple(entries)) if entries else paired_results[0]

    def create_individual_question_transport(
        self, cycle_identity: str,
    ) -> IntradayReviewV2BatchResult:
        """Create one exact-current candidate transport using batch primitives."""

        with self._lock, self._probables.current_generation_guard():
            pointer = self._require_current_workspace()
            if pointer is None:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            member = next(
                (item for item in pointer.cycles if item.cycle_identity == cycle_identity),
                None,
            )
            if member is None:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            cycle = self._review.load_cycle(cycle_identity)
            if (
                cycle.probables_run_identity != pointer.probables_run_identity
                or cycle.probable_result_identity != member.probable_result_identity
                or cycle.canonical_subject_identity != member.canonical_subject_identity
                or cycle.direction != member.direction
            ):
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            active = self._review.load_current_chart(cycle_identity)
            if active is None:
                raise ReviewError(ReviewFailure.CHART_REQUIRED)
            chart = self._review.load_chart(active.chart_revision_identity)
            if cycle.canonical_subject_identity.startswith("MCX-SUBJECT-"):
                return self._paired.create(cycle, chart, require_current=lambda: self._require_current_workspace(
                        cycle.probables_run_identity, cycle.cycle_identity))
            pack = create_question_pack_v2(
                self._review.load_handoff(cycle.handoff_identity), cycle, chart, question_version=visual_v2.VERSION, completed_selection=self._review_selection(cycle)
            )
            return self._create_question_transport(
                ((pack, self._review.load_chart_bytes(chart)),)
            )

    def _create_question_transport(
        self, entries: tuple[tuple[ReviewQuestionPackV2, bytes], ...],
    ) -> IntradayReviewV2BatchResult:
        ordered = tuple(sorted(
            entries,
            key=lambda item: item[0].expected_canonical_subject_identity,
        ))
        packs = tuple(pack for pack, _ in ordered)
        for pack in packs:
            self._require_current_workspace(pack.probables_run_identity, pack.review_cycle_identity)
        for pack in packs:
            self._review.retain_pack(pack)
        batch = create_question_batch_v2(packs)
        self._review.retain_batch(batch)
        transport = self._load_retained_transport(packs, current_edition_only=True)
        if transport is not None:
            question_path = self._transport.export_retained(
                transport, self._review.load_transport_question_pdf(transport),
                self._review.load_transport_answer_template(transport))
        else:
            transport, question_path, template = self._transport.export(batch, ordered)
            self._review.retain_transport(transport, question_path.read_bytes(), template)
        answer_path = self._review.transport_answer_template_path(transport)
        return IntradayReviewV2BatchResult(
            batch=batch,
            transport=transport,
            packs=packs,
            question_path=question_path,
            answer_template_path=answer_path,
        )

    def create_eligible_cycles(self, run: ProbablesRunV2) -> tuple[ReviewCycleV2, ...]:
        """Retain cycles only after exact persisted V2 lineage has been proven."""
        with self._lock:
            if type(run) is not ProbablesRunV2:
                raise ReviewError(ReviewFailure.INPUT_INVALID)
            try:
                persisted = self._probables.load_run(run.run_identity)
            except (ProbablesV2Error, ValueError) as error:
                raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE) from error
            if persisted != run:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)

            retained = self._retain_eligible_cycles(run)
            self._publish_current_review(run, retained)
            return retained

    def _retain_eligible_cycles(
        self, run: ProbablesRunV2
    ) -> tuple[ReviewCycleV2, ...]:
        existing = self._review.cycles_for_run(run.run_identity)
        if existing:
            if not self._review_cycles_match_run(run, existing):
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            return existing

        cycles: list[ReviewCycleV2] = []
        for result in run.results:
            if result.state not in {
                ProbableState.LONG_PROBABLE,
                ProbableState.SHORT_PROBABLE,
            }:
                continue
            handoff, cycle = self._build_cycle(run, result)
            self._review.retain_handoff(handoff)
            self._review.retain_cycle(cycle)
            cycles.append(cycle)

        retained = tuple(sorted(cycles, key=lambda item: item.probable_result_identity))
        if not self._review_cycles_match_run(run, retained):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        for cycle in retained:
            if self._review.load_cycle(cycle.cycle_identity) != cycle:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return retained

    def _publish_current_review(
        self, run: ProbablesRunV2, retained: tuple[ReviewCycleV2, ...]
    ) -> None:
        with self._probables.current_generation_guard():
            _, current_run = self._load_current_probables()
            if current_run != run:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            pointer = create_current_review_pointer_v2(run, retained)
            self._review.save_current(pointer)
            if self._review.load_current() != pointer:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)

    def _load_current_probables(self):  # type: ignore[no-untyped-def]
        try:
            pointer = self._probables.load_current()
            run = self._probables.load_current_run()
        except (ProbablesV2Error, ValueError) as error:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error
        if (pointer is None) != (run is None):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        if pointer is not None and run is not None and (
            pointer.run_identity != run.run_identity
            or pointer.analysis_boundary != run.analysis_boundary
            or pointer.methodology_publication_identity
            != run.methodology.publication_identity
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return pointer, run

    def _build_cycle(
        self,
        run: ProbablesRunV2,
        result: ProbableMemberResultV2,
    ) -> tuple[ReviewHandoffV2, ReviewCycleV2]:
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
        return handoff, create_review_cycle_v2(handoff)

    def _review_cycles_match_run(
        self, run: ProbablesRunV2, cycles: tuple[ReviewCycleV2, ...]
    ) -> bool:
        eligible = _eligible_results(run)
        if tuple(item.probable_result_identity for item in cycles) != tuple(
            item.result_identity for item in eligible
        ):
            return False
        try:
            return all(
                self._build_cycle(run, result)
                == (
                    self._review.load_handoff(cycle.handoff_identity),
                    cycle,
                )
                for result, cycle in zip(eligible, cycles, strict=True)
            )
        except ReviewError:
            return False

    def _cycles_for_pointer(self, pointer):  # type: ignore[no-untyped-def]
        if pointer is None:
            return ()
        return tuple(
            self._review.load_cycle(item.cycle_identity)
            for item in pointer.cycles
        )


def _sponsor_label(canonical_subject_identity: str) -> str:
    for prefix in ("NSE-EQ-", "NSE-INDEX-", "MCX-SUBJECT-"):
        if canonical_subject_identity.startswith(prefix):
            return canonical_subject_identity.removeprefix(prefix)
    return canonical_subject_identity


def _eligible_results(run: ProbablesRunV2) -> tuple[ProbableMemberResultV2, ...]:
    return tuple(
        sorted(
            (
                item
                for item in run.results
                if item.state in {
                    ProbableState.LONG_PROBABLE,
                    ProbableState.SHORT_PROBABLE,
                }
            ),
            key=lambda item: item.result_identity,
        )
    )


def _candidate_population_identity(run: ProbablesRunV2) -> str:
    values = tuple(
        (
            item.result_identity,
            item.canonical_subject_identity,
            item.direction.value if item.direction is not None else None,
        )
        for item in _eligible_results(run)
    )
    return "INTRADAY-REVIEW-V2-CANDIDATE-POPULATION-" + sha256(
        json.dumps(values, separators=(",", ":")).encode()
    ).hexdigest().upper()


def _answer_document(answer: ChartAnalystAnswerPack) -> dict[str, object]:
    return {
        **({"chart_observation_header": json.loads(answer.chart_observation_header)} if answer.chart_observation_header is not None else {}),
        "schema_identity": answer.schema_identity,
        "schema_version": answer.schema_version,
        "question_set_identity": answer.question_set_identity,
        "question_set_version": answer.question_set_version,
        "review_pack_identity": answer.review_pack_identity,
        "review_cycle_identity": answer.review_cycle_identity,
        "review_request_identity": answer.review_request_identity,
        "chart_revision_identity": answer.chart_revision_identity,
        "expected_canonical_subject_identity": answer.expected_canonical_subject_identity,
        "observed_visible_subject_identity": answer.observed_visible_subject_identity,
        "proposed_direction": answer.proposed_direction,
        "global_observation_status": answer.global_observation_status.value,
        "answers": [{
            "question_id": item.question_id,
            "observation_status": item.observation_status.value,
            "answer": item.answer,
            "visible_timeframes": list(item.visible_timeframes),
            "visible_basis": item.visible_basis,
            "status_detail": item.status_detail,
            "why_not_covered_elsewhere": item.why_not_covered_elsewhere,
        } for item in answer.answers],
    }


__all__ = [
    "IntradayReviewV2Application",
    "IntradayReviewV2BatchResult",
    "IntradayReviewV2PreImportValidation",
    "IntradayReviewV2ImportMemberResult",
    "IntradayReviewV2BatchImportResult",
    "IntradayReviewV2InboxImportResult",
    "IntradayReviewV2InboxMemberResult",
    "IntradayReviewV2CandidateSnapshot",
    "IntradayReviewV2Snapshot",
]
