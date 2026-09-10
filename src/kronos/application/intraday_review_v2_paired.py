"""Review V2 adapter to the existing paired MCX engine; no analytical authority."""
from __future__ import annotations

from kronos.intraday import visual_contract_v2 as visual_v2

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json

from kronos.application.intraday_review_mcx_paired import IntradayMcxPairedReviewApplication
from kronos.instrument.active_derivative_persistence import ActiveDerivativeBindingStore
from kronos.instrument.active_derivative import ActiveDerivativeSelectionError
from kronos.instrument.visual_identity import VisualIdentityResolutionError, VISUAL_IDENTITY_NATIVE_CONTRACT_VERSION
from kronos.instrument.visual_identity_persistence import load_visual_identity_resolver
from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_mcx_paired import (
    ChartSide, create_paired_chart_revision, create_paired_chart_bundle,
    create_paired_review_pack, bind_native_identity, relationship_for_subject,
)
from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
from kronos.intraday.review_mcx_paired_transport import create_paired_transport
from kronos.intraday.review_mcx_paired_answer import parse_mcx_paired_answer, bind_mcx_paired_import
from kronos.intraday.review_v2 import ChartRevisionV2, ReviewCycleV2


@dataclass(frozen=True, slots=True)
class PairedQuestionResult:
    transport: object
    question_path: Path
    answer_template_path: Path


class IntradayReviewV2PairedAdapter:
    def __init__(self, review_store, transport, *, native_resolver=None, chart_input=None):
        self.review = review_store
        self.transport = transport
        self.bindings = ActiveDerivativeBindingStore(review_store.root.parent / "active-derivative-bindings")
        self.store = IntradayMcxPairedReviewStore(review_store.root.parent / "review-mcx-paired-v1")
        self.engine = IntradayMcxPairedReviewApplication(store=self.store)
        self.native_resolver = native_resolver
        self.chart_input = chart_input

    def options(self, cycle: ReviewCycleV2) -> dict[str, str]:
        try:
            binding = self.bindings.load_current(canonical_subject_id=cycle.canonical_subject_identity)
            if binding is None:
                raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE)
            bind_native_identity(cycle, binding, roll_history_identity=binding.integrity_identity)
            reference = relationship_for_subject(cycle.canonical_subject_identity)
            return {"native_binding_identity": binding.binding_identity,
                    "native_contract_identity": binding.active_binding.derivative_contract_id,
                    "reference_context_identity": reference.governed_visible_identity}
        except (ActiveDerivativeSelectionError, ValueError) as error:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error

    def validate_metadata(self, cycle, metadata):
        if type(metadata) is not dict or metadata != self.options(cycle):
            raise ReviewError(ReviewFailure.CHART_INVALID)
        try:
            return self.bindings.load(binding_identity=metadata["native_binding_identity"])
        except (ActiveDerivativeSelectionError, ValueError) as error:
            raise ReviewError(ReviewFailure.CHART_INVALID) from error

    def prepare(self, cycle, metadata, payload, media_type, ordinal, received_at):
        binding = self.validate_metadata(cycle, metadata)
        if received_at > binding.expiry_eligibility_boundary:
            raise ReviewError(ReviewFailure.CHART_INVALID)
        reference = relationship_for_subject(cycle.canonical_subject_identity)
        common = dict(review_cycle_identity=cycle.cycle_identity,
                      observation_boundary=cycle.analysis_boundary, media_type=media_type,
                      revision_ordinal=ordinal, received_at=received_at)
        native_chart = create_paired_chart_revision(payload=payload, side=ChartSide.NATIVE_MCX,
            expected_subject_identity=cycle.canonical_subject_identity,
            expected_visible_identity=binding.active_binding.derivative_contract_id,
            venue="MCX", series_kind=None, listed_contract_identity=None, **common)
        reference_chart = create_paired_chart_revision(payload=payload, side=ChartSide.INTERNATIONAL_REFERENCE,
            expected_subject_identity=reference.reference_analytical_subject_identity,
            expected_visible_identity=reference.governed_visible_identity, venue=reference.venue.value,
            series_kind=reference.series_kind, listed_contract_identity=None, **common)
        native = bind_native_identity(cycle, binding, roll_history_identity=binding.integrity_identity)
        bundle = create_paired_chart_bundle(cycle=cycle, native_binding=native,
            native_chart=native_chart, reference_chart=reference_chart, reference_relationship=reference)
        # All metadata validation precedes persistence. The caller publishes its
        # current chart pointer only after every immutable artifact is retained.
        self.store.retain_chart(native_chart, payload)
        self.store.retain_chart(reference_chart, payload)
        self.store.retain_bundle(bundle)
        return bundle

    def restore(self, cycle, chart):
        if chart.paired_bundle_identity is None:
            raise ReviewError(ReviewFailure.CHART_REQUIRED)
        bundle = self.store.load_bundle(chart.paired_bundle_identity)
        native = self.store.load_chart(bundle.native_chart_revision_identity)
        reference = self.store.load_chart(bundle.reference_chart_revision_identity)
        try:
            binding = self.bindings.load(binding_identity=bundle.native_identity_binding.active_binding_identity)
        except (ActiveDerivativeSelectionError, ValueError) as error:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error
        expected_native = bind_native_identity(cycle, binding, roll_history_identity=binding.integrity_identity)
        expected_bundle = create_paired_chart_bundle(cycle=cycle, native_binding=expected_native,
            native_chart=native, reference_chart=reference,
            reference_relationship=relationship_for_subject(cycle.canonical_subject_identity))
        if (bundle != expected_bundle or chart.review_cycle_identity != cycle.cycle_identity
            or any(item.payload_sha256 != chart.payload_sha256
                   or item.revision_ordinal != chart.revision_ordinal
                   or item.received_at != chart.received_at for item in (native, reference))):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        self.review.load_chart_bytes(chart)  # validate retained payload, not only the manifest
        return bundle, native, reference

    def _selection(self, cycle):
        handoff = self.review.load_handoff(cycle.handoff_identity)
        selection = self.chart_input.probables.load_selection(handoff.completed_evidence_selection_identity)
        if selection.integrity_identity != handoff.completed_evidence_integrity_identity:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        return selection

    def expected(self, cycle, chart):
        bundle, native, reference = self.restore(cycle, chart)
        pack = create_paired_review_pack(bundle, created_at=chart.received_at, question_version=visual_v2.VERSION, completed_selection=self._selection(cycle))
        payload = self.review.load_chart_bytes(chart)
        transport, pdf, template = create_paired_transport(pack=pack, bundle=bundle,
            native_chart_payload=payload, reference_chart_payload=payload,
            generated_at=chart.received_at, supporting_reference_only=True)
        return bundle, native, reference, pack, transport, pdf, template

    def create(self, cycle, chart, *, require_current):
        retained = self.retained(cycle, chart)
        if retained is not None and retained[3].question_set_version == visual_v2.VERSION and retained[4].schema_version == "1.3.0":
            bundle, native, reference, pack, transport, _, _ = retained
            pdf = self.store.load_bytes("question-pdfs", transport.transport_identity, ".pdf")
            template = self.store.load_bytes("answer-templates", transport.transport_identity)
        else:
            bundle, native, reference, pack, transport, pdf, template = self.expected(cycle, chart)
        require_current()
        self.store.retain_pack(pack)
        self.store.retain_transport(transport, pdf, template)
        self.store.retain_transport_pointer(transport)
        question = self.transport.export_paired(transport, pdf, template)
        return PairedQuestionResult(transport, question, self.store.transport_answer_template_path(transport))

    def retained(self, cycle, chart):
        bundle, native, reference = self.restore(cycle, chart)
        for version in (visual_v2.VERSION, "1.0.0"):
            pack = create_paired_review_pack(bundle, created_at=chart.received_at, question_version=version, completed_selection=self._selection(cycle))
            try:
                retained_pack = self.store.load_pack(pack.review_pack_identity)
                transport = self.store.load_transport_for_pack(pack.review_pack_identity)
                if (retained_pack != pack or transport.paired_bundle_identity != bundle.bundle_identity
                    or transport.generated_at != chart.received_at):
                    raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            except ReviewError as error:
                if error.failure is ReviewFailure.ARTIFACT_UNAVAILABLE:
                    continue
                raise
            return bundle, native, reference, pack, transport, None, None
        return None

    def retained_evidence(self, pack, chart):
        evidence = self.store.load_evidence_for_pack(pack.review_pack_identity)
        if evidence is not None:
            from kronos.intraday.analyst_chart_observation import verify_retained
            answer = self.store.load_answer(evidence.answer_pack_identity)
            if answer.source_sha256 != evidence.answer_source_sha256:
                raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
            verify_retained(answer, pack, chart, self.review, imported_at=evidence.imported_at, paired=True)
        return evidence

    def import_expected(self, cycle, chart, imported_at, *, require_current):
        from kronos.application.intraday_review_v2 import IntradayReviewV2InboxImportResult, IntradayReviewV2InboxMemberResult
        retained = self.retained(cycle, chart)
        if retained is None:
            raise ReviewError(ReviewFailure.ARTIFACT_UNAVAILABLE)
        bundle, native, reference, pack, transport, _, _ = retained
        filename = transport.expected_answer_filename
        state, reason, found = "NOT_FOUND", None, 0
        try:
            payload = self.transport.read_expected_answer(filename)
            if payload is not None:
                found = 1
                parsed = parse_mcx_paired_answer(payload)
                existing = self.retained_evidence(pack, chart)
                if existing is not None:
                    if existing.answer_pack_identity != parsed.answer_pack_identity:
                        raise ReviewError(ReviewFailure.ANSWER_CONFLICT)
                    state = "ALREADY_IMPORTED"
                else:
                    require_current()
                    resolver = self.native_resolver or load_visual_identity_resolver(publication_version=VISUAL_IDENTITY_NATIVE_CONTRACT_VERSION)
                    # Preserve envelope/native-identity failure precedence. This
                    # pure comparison writes no Answer or evidence.
                    bind_mcx_paired_import(pack=pack, bundle=bundle,
                        native_chart=native, reference_chart=reference, answer=parsed,
                        native_resolver=resolver, reference_resolver=resolver,
                        imported_at=imported_at, supporting_reference_only=True)
                    if self.chart_input is None:
                        raise ReviewError(ReviewFailure.CHART_CORRESPONDENCE_UNVERIFIABLE)
                    from kronos.intraday.analyst_chart_observation import receipt as prepare_receipt
                    header = json.loads(parsed.chart_observation_header) if parsed.chart_observation_header else None
                    if header and header["schema_version"] == "1.1.0" and transport.schema_version != "1.3.0":
                        raise ReviewError(ReviewFailure.ANSWER_SCHEMA_INVALID)
                    observation = prepare_receipt(parsed, pack, chart, self.review, imported_at=imported_at, paired=True)
                    correspondence = self.chart_input.require(cycle, chart, bundle=bundle, resolver=resolver, receipt=observation,
                        observed_native=parsed.native_observed_visible_identity,
                        observed_reference=parsed.reference_observed_visible_identity,
                        visual_answers=(*parsed.reference_answers, *parsed.native_answers, *(parsed.cross_market_answers or ()), parsed.escape_hatch_answer))
                    require_current()
                    if observation is not None:
                        self.review.retain_chart_input(observation)
                    _, evidence = self.engine.import_answer(payload=payload, pack=pack, bundle=bundle,
                        native_chart=native, reference_chart=reference, native_resolver=resolver,
                        reference_resolver=resolver, imported_at=imported_at, supporting_reference_only=True,
                        chart_correspondence=tuple((r.role, r.timeframe, r.authority, r.independent_correspondence, r.source_identity) for r in correspondence))
                    self.store.retain_evidence_pointer(evidence)
                    state = "IMPORTED"
        except (ReviewError, VisualIdentityResolutionError) as error:
            state, reason = "REJECTED", error.failure.value
            found = 1
        return IntradayReviewV2InboxImportResult(mode="INDIVIDUAL_PAIRED", current_review_count=1,
            expected_count=1, found_count=found, imported_count=int(state == "IMPORTED"),
            already_imported_count=int(state == "ALREADY_IMPORTED"), not_found_count=int(not found),
            rejected_count=int(state == "REJECTED"),
            members=(IntradayReviewV2InboxMemberResult(cycle.canonical_subject_identity, filename, state, reason),))
