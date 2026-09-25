"""Live, version-selected integration of the governed Visual V3 components."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from hashlib import sha256
from threading import Condition, Lock

from kronos.application.swing_native_review import NativeReviewWorkflowSnapshot
from kronos.application.swing_visual_v3 import (
    SwingVisualV3ReviewCycle,
    chart_inputs_from_requirement,
)
from kronos.swing.v1.extension import (
    evaluate_completed_one_hour_extension,
    extension_native_condition_inputs,
)
from kronos.swing.v1.analytical_promotion_v2 import (
    LocalV2PromotionStore, V2PromotionRecord, evaluate_governed, _nse_confirmation,
)
from kronos.swing.v1.path_clearance import evaluate_one_hour_path_clearance
from kronos.swing.v1.mtf_facts import FactualTimeframe, SameRunMtfFactSnapshot
from kronos.swing.v1.native_discovery import (
    NativeProductPath, NativeDiscoveryRun, NativeDiscoveryStatus, Native1WState,
)
from kronos.swing.v1.native_review import (
    NativeIndependentLayer2Evidence,
    NativeLayer2EvidenceState,
    NativeReviewRequirement,
    build_native_review_requirements,
    _requirement,
)
from kronos.swing.v1.pdf_visual_review import PdfReviewTransportError
from kronos.swing.v1.pdf_visual_review_v3 import VisualV3ReviewPackRecord
from kronos.swing.v1.review_evidence_binding import (
    ReviewAcceptanceReceipt, ReviewEvidenceError, ReviewMutationPrecondition,
    canonical, require, strict_json, timestamp,
)
from kronos.swing.v1.review_evidence_store import (
    ReviewEvidenceStore, PreparedReadFence, capture_prepared_reads, record_prepared_read,
)
from kronos.swing.v1.pdf_visual_review_v3_live import (
    VisualV3AnswerImportRecord,
    VisualV3LiveReviewPack,
    VisualV3PdfReviewTransport,
    extract_successor_answer_pdf,
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
    visual_evidence_v3_response_from_dict,
    validate_nse_successor_answer,
    _primitive,
)


@dataclass(frozen=True, slots=True)
class SwingVisualV3LiveSnapshot:
    review_pack: VisualV3LiveReviewPack | None
    answer_imports: tuple[VisualV3AnswerImportRecord, ...]
    current_run: bool
    completed_instruments: tuple[str, ...]
    restoration_error: str | None = None


class SwingVisualV3LiveWorkflow:
    """Coordinate V3 Pack, Answer, evidence, readiness, and restart restoration."""

    def __init__(
        self,
        cycle: SwingVisualV3ReviewCycle,
        transport: VisualV3PdfReviewTransport,
        *,
        clock=lambda: datetime.now(UTC),  # type: ignore[no-untyped-def]
        recover_historical=True,
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
        self.restoration_error: str | None = None
        self._pack: VisualV3LiveReviewPack | None = None
        self._imports: tuple[VisualV3AnswerImportRecord, ...] = ()
        try:
            # This constructor is the explicit startup-restoration boundary.
            # Subsequent load_current/GET calls are strictly observational.
            pack = (transport.record_store.recover_pending_publications() if recover_historical
                    else transport.record_store.load_current())
            imports = (
                () if pack is None
                else transport.record_store.load_imports(pack.review_pack_id)
            )
        except (OSError, ValueError):
            # Retained evidence remains invalid and untouched. An unavailable
            # Review must not prevent unrelated Browser workflows from starting.
            self.restoration_error = "VISUAL_V3_RESTORATION_UNAVAILABLE"
        else:
            self._pack, self._imports = pack, imports

    def is_current_run(self, run_identity: str | None) -> bool:
        return self._pack is not None and self._pack.native_run_identity == run_identity

    def snapshot(self, run_identity: str | None) -> SwingVisualV3LiveSnapshot:
        with self.transport.record_store.cycle_lock:
            return self._snapshot(run_identity)

    def _snapshot(self, run_identity: str | None) -> SwingVisualV3LiveSnapshot:
        return SwingVisualV3LiveSnapshot(
            self._pack,
            self._imports,
            self.is_current_run(run_identity),
            tuple(
                item.requirement.canonical_instrument
                for item in self.cycle.completed_snapshot()
                if item.requirement.native_run_identity == run_identity
            ),
            self.restoration_error,
        )

    def generate(
        self,
        review: NativeReviewWorkflowSnapshot,
        facts: SameRunMtfFactSnapshot,
        chart_bytes,  # type: ignore[no-untyped-def]
        instrument: str | None = None,
    ) -> VisualV3LiveReviewPack:
        # Include preparation and the in-memory selection in the same critical
        # section as PDF/record publication (ThreadingHTTPServer callers).
        with self.transport.record_store.cycle_lock:
            return self._generate(review, facts, chart_bytes, instrument)

    def _generate(self, review, facts, chart_bytes, instrument):  # type: ignore[no-untyped-def]
        prepared, skipped = self._prepare(review, facts, chart_bytes, instrument)
        record = self.transport.generate(
            prepared,
            scope="INDIVIDUAL" if instrument is not None else "ALL_ELIGIBLE",
            skipped=() if instrument is not None else skipped,
        )
        imports = self.transport.record_store.load_imports(record.review_pack_id)
        self._pack, self._imports = record, imports
        self.restoration_error = None
        return record

    def upload(
        self,
        review: NativeReviewWorkflowSnapshot,
        facts: SameRunMtfFactSnapshot,
        chart_bytes,  # type: ignore[no-untyped-def]
    ) -> tuple[VisualV3AnswerImportRecord, ...]:
        with self.transport.record_store.cycle_lock:
            return self._upload(review, facts, chart_bytes)

    def handoff_accepted_receipt(self, store, commit_identity, receipt_identity, *,
                                 review, facts, chart_bytes, publication_guard, recheck,
                                 prepared_requests=None, restore_only=False):
        """WO07 explicit handoff. Never called from snapshot or historical restore.

        Resolve acceptance before consulting the downstream stores. MCX returns
        an immutable unsupported disposition without preparing four-frame NSE
        inputs or invoking either consumer. NSE derives its inputs exclusively
        from the retained mapping and accepted response bytes, then validates
        them against the current exact run/assessment/factual request.
        """
        require(type(store) is ReviewEvidenceStore, "REVIEW_REQUEST_MISMATCH")
        receipt = store.resolve_committed_receipt(commit_identity, receipt_identity, current=True)
        commit = store.load_acceptance(commit_identity)
        binding = receipt.binding.value
        require(receipt.binding.scope == "NATIVE_REVIEW", "REVIEW_CONTRACT_UNSUPPORTED")
        prepared_inputs = None

        def nse_inputs():
            if prepared_inputs is not None:
                return prepared_inputs
            publication = store.load_request(commit.value["request_publication_identity"])
            require(store.load_current_request() == publication, "REVIEW_BINDING_STALE")
            mapping = publication.mapping.value
            require(binding["market"] == "NSE"
                    and binding["analytical_run_identity"] == mapping["native_run_identity"]
                    and binding["committed_run_manifest_identity"] == mapping["committed_run_manifest_identity"]
                    and binding["request_identity"] == mapping["request_identity"]
                    and binding["request_timestamp"] == mapping["request_timestamp"]
                    and binding["review_pack_identity"] == mapping["review_pack_identity"]
                    and binding["review_pack_sha256"] == mapping["review_pack_sha256"],
                    "REVIEW_REQUEST_MISMATCH")
            if prepared_requests is None:
                prepared, _ = self._prepare(review, facts, chart_bytes, binding["canonical_instrument"],
                    request_timestamp=datetime.fromisoformat(mapping["request_timestamp"]),
                    question_set_version=mapping["question_set_version"])
            else:
                prepared = (prepared_requests(binding["canonical_instrument"],
                    datetime.fromisoformat(mapping["request_timestamp"])),)
            require(len(prepared) == 1, "REVIEW_ACCEPTANCE_INCOMPLETE")
            requests = prepared[0]
            requirement = requests[0].requirement
            require(requirement.thesis.product_path is NativeProductPath.NSE
                    and requirement.thesis.native_assessment_sha256 == binding["native_assessment_sha256"],
                    "REVIEW_REQUEST_MISMATCH")
            subjects = [item for item in mapping["subjects"]
                        if item["canonical_instrument"] == binding["canonical_instrument"]
                        and item["native_assessment_sha256"] == binding["native_assessment_sha256"]]
            require(len(subjects) == 1, "REVIEW_REQUEST_MISMATCH")
            for request, expected in zip(requests, subjects[0]["responses"], strict=True):
                require({key: value for key, value in expected.items()
                    if key not in {"observation_boundary", "analysis_boundary"}} == dict(timeframe=request.timeframe.value,
                    expected_chart_identity=request.chart_identity,
                    chart_revision_sha256=request.chart_revision_sha256,
                    machine_fact_integrity_sha256=request.machine_fact.integrity_sha256)
                    and datetime.fromisoformat(expected["observation_boundary"]) == request.observation_boundary
                    and datetime.fromisoformat(expected["analysis_boundary"]) == request.analysis_boundary,
                    "REVIEW_REQUEST_MISMATCH")
            require(tuple((item["role"], item["timeframe_or_family_identity"])
                    for item in receipt.body["structured_evidence"]) ==
                    tuple(("NATIVE_NSE", tf.value) for tf in VisualTimeframe),
                    "REVIEW_CONTRACT_UNSUPPORTED")
            def typed_response(raw):
                value = strict_json(raw)
                if mapping["version"] == "2.0":
                    require(value.pop("answer_pdf_sha256", None) == receipt.body["answer"]["pdf_sha256"],
                            "REVIEW_ARTIFACT_DIGEST_MISMATCH")
                    require(set(value) == set(VisualEvidenceV3Response.__dataclass_fields__),
                            "REVIEW_CONTRACT_UNSUPPORTED")
                return visual_evidence_v3_response_from_dict(value)
            responses = tuple(typed_response(raw)
                for raw in store.structured_evidence_for(commit_identity, receipt_identity))
            for request, response in zip(requests, responses, strict=True):
                response.validate_binding(request)
            pack = VisualV3ReviewPackRecord(mapping["review_pack_identity"], mapping["native_run_identity"],
                requirement.canonical_instrument, requirement.thesis.native_assessment_sha256,
                datetime.fromisoformat(mapping["request_timestamp"]),
                str(store.root / publication.value["question_pdf_artifact"]["relative_path"]),
                mapping["review_pack_sha256"],
                tuple((item.timeframe.value, item.chart_revision_sha256) for item in requests),
                tuple((item.timeframe.value, item.machine_fact.integrity_sha256) for item in requests),
                question_set_version=mapping["question_set_version"])
            return requirement, requests, responses, pack

        def identities(completed, responses):
            if completed is None or completed.promotion is None:
                return None
            require(completed.responses == responses, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
            return (completed.readiness.result_sha256, completed.promotion.integrity_sha256)

        def restore(_receipt):
            requirement, requests, responses, pack = nse_inputs()
            try:
                completed = self.cycle.restore_persisted(requirement, facts, requests, review_pack=pack)
            except ValueError as error:
                if str(error) != "VISUAL_V3_RESTORE_READINESS_MISSING":
                    raise
                return None
            return identities(completed, responses)

        def consume(_receipt):
            requirement, requests, responses, pack = nse_inputs()
            extension = evaluate_completed_one_hour_extension(requirement, facts)
            path = evaluate_one_hour_path_clearance(run_identity=requirement.native_run_identity,
                instrument=facts.instrument(requirement.canonical_instrument), direction=requirement.thesis.direction)
            for request, response in zip(requests, responses, strict=True):
                self.cycle.retain(request, response)
            # A resumed attempt uses this original acceptance time. Rebuilding
            # after partial output cannot manufacture a later result identity.
            self.cycle.complete(requirement, _v3_layer2(requirement, responses), facts, responses,
                created_at=datetime.fromisoformat(receipt.body["accepted_at"]),
                inputs=extension_native_condition_inputs(extension, requirement),
                review_pack=pack, path_clearance=path, extension=extension)
            return identities(self.cycle.completed_for(requirement.native_run_identity,
                requirement.canonical_instrument), responses)

        def exact_recheck(snapshot, accepted):
            selected = store.load_current_request() if binding["market"] == "NSE" else store.load_current_mcx_request()
            require(selected is not None and selected.identity == commit.value["request_publication_identity"],
                    "REVIEW_BINDING_STALE")
            recheck(snapshot, accepted)

        def prepare_recheck(accepted):
            nonlocal prepared_inputs
            with capture_prepared_reads() as reads:
                exact_recheck(None, accepted)
                if binding["market"] == "NSE":
                    prepared_inputs = nse_inputs()
            fence = PreparedReadFence(tuple(reads.items()))
            expected_manifest = binding["committed_run_manifest_identity"]
            expected_run = binding["analytical_run_identity"]

            def bounded_check(snapshot, _accepted):
                fence.check()
                require(snapshot.control["current_manifest"]["sha256"] == expected_manifest
                        and snapshot.manifest["run_id"] == expected_run, "REVIEW_BINDING_STALE")
            return bounded_check

        exact_recheck.prepare = prepare_recheck

        if restore_only:
            # Startup restores a selected successful output, never starts or
            # retries a consumer and never creates an attempt or receipt.
            exact_recheck(None, receipt)
            attempts = store.downstream_attempts(commit_identity, receipt_identity,
                VISUAL_QUESTION_SET_V3_ID, receipt.body["contracts"][0]["question_contract_version"])
            if attempts and attempts[0].value["state"] == "SUCCEEDED":
                require(binding["market"] == "NSE" and restore(receipt) ==
                    tuple(attempts[0].value["output_identities"]), "REVIEW_ARTIFACT_DIGEST_MISMATCH")
            return None if not attempts else attempts[0]
        return store.handoff_committed(commit_identity, receipt_identity,
            consumer_identity=VISUAL_QUESTION_SET_V3_ID,
            consumer_version=receipt.body["contracts"][0]["question_contract_version"],
            clock=lambda: timestamp(self._now()), publication_guard=publication_guard,
            recheck=exact_recheck, restore=restore, consume=consume)

    def accept_successor_answer(self, store, publication_identity, answer_pdf, *, market,
                                review, facts, chart_reader, precondition, current_state,
                                publication_guard, extracted_answer=None,
                                phase_observer=None):
        """Prepare the complete native package, then publish acceptance only.

        The Browser/application owner supplies its exact-state resolver and
        original chart reader. Incoming PDF bytes are captured once by that
        owner. This method never searches an Answers directory, calls a consumer,
        or changes historical visual/Readiness stores. Handoff is a separate
        explicit operation on the returned committed receipt.
        """
        from kronos.swing.v1.mcx_native_visual_contract import mcx_structured_evidence, mcx_comparison_evidence
        require(type(store) is ReviewEvidenceStore and market in {"NSE", "MCX"}
                and type(precondition) is ReviewMutationPrecondition
                and all(callable(fn) for fn in (chart_reader, current_state, publication_guard)),
                "REVIEW_PRECONDITION_INVALID")
        precondition.validate(current_state())
        observe = phase_observer if callable(phase_observer) else lambda _phase: None
        load = store.load_current_request if market == "NSE" else store.load_current_mcx_request
        publication = load()
        require(publication is not None and publication.identity == publication_identity,
                "REVIEW_BINDING_STALE")
        mapping = publication.mapping.value if market == "NSE" else publication.native.value
        require(review.native_run_identity == facts.run_identity == mapping["native_run_identity"],
                "REVIEW_BINDING_STALE")
        if extracted_answer is None:
            observe("extraction_started_at")
            extracted = extract_successor_answer_pdf(answer_pdf)
            observe("extraction_completed_at")
        else:
            require(type(extracted_answer) is bytes and bool(extracted_answer),
                    "REVIEW_ACCEPTANCE_INCOMPLETE")
            extracted = extracted_answer
        observe("validation_started_at")
        answer = strict_json(extracted)
        checksum = sha256(answer_pdf).hexdigest()
        successor = mapping["version"] == "2.0"
        require(not successor or len(extracted) <= 8 * 1024 * 1024, "REVIEW_ACCEPTANCE_INCOMPLETE")
        if market == "NSE":
            validated = validate_nse_successor_answer(extracted, publication.mapping)
            structured = tuple(canonical({**_primitive(response), **({"answer_pdf_sha256": checksum} if successor else {})})
                               for candidate in validated for response in candidate)
        else:
            structured = mcx_structured_evidence(extracted, publication.native, publication.reference, checksum)
            comparisons = mcx_comparison_evidence(extracted, publication.native, publication.reference, checksum) if successor else ()
        requirements = {}
        for subject in mapping["subjects"]:
            instrument = subject["canonical_instrument"]
            matches = [item for item in review.requirements if item.canonical_instrument == instrument
                and item.native_run_identity == facts.run_identity
                and item.thesis.native_assessment_sha256 == subject["native_assessment_sha256"]]
            require(len(matches) == 1, "REVIEW_REQUEST_MISMATCH")
            requirement = matches[0]
            require(requirement.thesis.product_path is (NativeProductPath.NSE if market == "NSE" else NativeProductPath.MCX),
                    "REVIEW_CONTRACT_UNSUPPORTED")
            if market == "MCX":
                require(subject["supplied_native_direction"] == requirement.thesis.direction.value,
                        "REVIEW_REQUEST_MISMATCH")
            machine = {item.chart_timeframe.value: item for item in facts.instrument(instrument).reference_facts}
            for requested in subject["responses"]:
                fact = machine.get(requested["timeframe"])
                fact_key = "machine_fact_integrity_sha256" if market == "NSE" else "native_machine_fact_integrity_sha256"
                require(fact is not None and fact.integrity_sha256 == requested[fact_key]
                        and datetime.fromisoformat(requested["analysis_boundary"]) == fact.analysis_boundary
                        and datetime.fromisoformat(requested["observation_boundary"]) ==
                        facts.instrument(instrument).fact(FactualTimeframe(requested["timeframe"])).observation_boundary,
                        "REVIEW_REQUEST_MISMATCH")
            requirements[instrument] = requirement
        history = store.native_acceptance_history(market, facts.run_identity)
        previous = history[0] if history else None
        prior = {receipt.binding.lineage_key: receipt for commit in reversed(history) for receipt in commit.receipts}
        captured_charts = {}
        prepared_fence = None

        def recheck(_receipts=None, identity=None):
            nonlocal prepared_fence
            if prepared_fence is None:
                with capture_prepared_reads() as reads:
                    precondition.validate(current_state())
                    require(load() == publication, "REVIEW_BINDING_STALE")
                    require(store.native_acceptance_history(market, facts.run_identity) == history,
                            "REVIEW_BINDING_STALE")
                    for key, captured in captured_charts.items():
                        require(chart_reader(*key) == captured, "REVIEW_BINDING_STALE")
                prepared_fence = PreparedReadFence(tuple(reads.items()))
            require(identity is None or identity == publication_identity, "REVIEW_BINDING_STALE")
            prepared_fence.check()

        def guarded_recheck(snapshot):
            recheck()
            require(snapshot.control["current_manifest"]["sha256"] == mapping["committed_run_manifest_identity"]
                    and snapshot.manifest["run_id"] == mapping["native_run_identity"], "REVIEW_BINDING_STALE")

        # Replay is a read of the exact committed package, not a new timestamp
        # or a new set of downstream evidence. Validate before returning it.
        for commit in history:
            if any(item.body["answer"]["answer_identity"] == answer["answer_identity"] for item in commit.receipts):
                require(commit == previous and commit.value["request_publication_identity"] == publication_identity
                        and all(item.body["answer"]["pdf_sha256"] == checksum for item in commit.receipts),
                        "REVIEW_ANSWER_IDENTITY_CONFLICT")
                for receipt in commit.receipts:
                    for chart in receipt.body["chart_revisions"]:
                        key = (chart["role"], receipt.binding.value["canonical_instrument"], chart["timeframe_or_panel_identity"])
                        captured_charts[key] = chart_reader(*key)
                        require(captured_charts[key][0] == chart["revision_identity"]
                                and sha256(captured_charts[key][1]).hexdigest() == chart["sha256"], "REVIEW_BINDING_STALE")
                recheck()
                observe("validation_completed_at")
                observe("acceptance_started_at")
                with store.publication_commit_guard(publication_guard, guarded_recheck):
                    prepared_fence.check()
                observe("acceptance_committed_at")
                return previous
        if previous is not None:
            require(previous.value["request_publication_identity"] != publication_identity,
                    "REVIEW_PREDECESSOR_INVALID")
        accepted_at = timestamp(self._now())
        answer_path = "answer-pdfs/" + checksum + ".pdf"
        artifacts, receipts = {answer_path: answer_pdf}, []
        decoded = tuple(strict_json(raw) for raw in structured)
        for subject in mapping["subjects"]:
            instrument = subject["canonical_instrument"]
            requirement = requirements[instrument]
            binding = dict(market=market, analytical_run_identity=facts.run_identity,
                committed_run_manifest_identity=mapping["committed_run_manifest_identity"],
                candidate_identity=requirement.requirement_sha256, canonical_instrument=instrument,
                native_assessment_sha256=requirement.thesis.native_assessment_sha256,
                review_cycle_identity=mapping["review_pack_identity"] if market == "NSE" else mapping["review_cycle_identity"],
                request_identity=mapping["request_identity"], request_timestamp=mapping["request_timestamp"],
                review_pack_identity=mapping["review_pack_identity"], review_pack_sha256=mapping["review_pack_sha256"])
            charts, evidence, contracts = [], [], []
            for raw, value in zip(structured, decoded, strict=True):
                value_binding = value if market == "NSE" else value["binding"]
                if value_binding["native_canonical_instrument"] != instrument:
                    continue
                role = "NATIVE_NSE" if market == "NSE" else value_binding["role"]
                tf = value_binding["timeframe"]
                key = (role, instrument, tf)
                revision, image = chart_reader(*key)
                captured_charts[key] = (revision, image)
                chart_sha = value_binding["chart_revision_sha256"]
                require(type(image) is bytes and sha256(image).hexdigest() == chart_sha,
                        "REVIEW_ARTIFACT_DIGEST_MISMATCH")
                if market == "MCX":
                    require(revision == value_binding["chart_revision_identity"], "REVIEW_BINDING_STALE")
                chart_path = "chart-images/" + chart_sha
                artifacts[chart_path] = image
                reference = role == "SUPPORTING_REFERENCE"
                identity = value_binding["chart_identity"] if market == "NSE" else value_binding["subject_identity"]
                charts.append(dict(role=role, subject_identity=identity,
                    reference_market=value_binding["market"] if reference else None,
                    reference_symbol=value_binding["reference_symbol"] if reference else None,
                    timeframe_or_panel_identity=tf, revision_identity=revision,
                    sha256=chart_sha, retained_relative_path=chart_path))
                sha = sha256(raw).hexdigest()
                path = "structured-evidence/" + sha + ".json"
                artifacts[path] = raw
                evidence.append(dict(role=role, subject_identity=identity, timeframe_or_family_identity=tf,
                    schema=value["schema"], version=("3.2" if successor else "3.1") if market == "NSE" else value["version"],
                    sha256=sha, retained_relative_path=path))
                if not any(item["role"] == role for item in contracts):
                    provenance = mapping if market == "NSE" else value["provenance"]
                    contracts.append(dict(role=role,
                        question_contract_identity=provenance["question_set_identity"] if market == "NSE" else provenance["question_contract_identity"],
                        question_contract_version=("3.2" if successor else "3.1") if market == "NSE" else provenance["question_contract_version"],
                        answer_contract_identity=provenance["answer_schema"] if market == "NSE" else provenance["answer_contract_identity"],
                        answer_contract_version="2.0" if successor else "1.0", structured_evidence_schema=value["schema"],
                        structured_evidence_version=("3.2" if successor else "3.1") if market == "NSE" else value["version"]))
            from kronos.swing.v1.review_evidence_binding import ReviewEvidenceBinding
            predecessor = prior.get(ReviewEvidenceBinding.create("NATIVE_REVIEW", binding).lineage_key)
            body = dict(scope="NATIVE_REVIEW", binding=binding,
                contracts=contracts, chart_revisions=charts, structured_evidence=evidence,
                answer=dict(answer_identity=answer["answer_identity"], pdf_sha256=checksum,
                    byte_length=len(answer_pdf), retained_relative_path=answer_path), accepted_at=accepted_at,
                predecessor_receipt_id=None if predecessor is None else predecessor.receipt_id)
            if successor:
                body["comparison_evidence"] = None
                if market == "MCX":
                    from kronos.swing.v1 import mcx_native_visual_contract as mcx
                    index = next(i for i, item in enumerate(mapping["subjects"])
                                 if item["canonical_instrument"] == instrument)
                    raw = comparisons[index]
                    record = strict_json(raw)
                    sha = sha256(raw).hexdigest()
                    path = "comparison-evidence/" + sha + ".json"
                    artifacts[path] = raw
                    refs = record["request_references"]
                    body["comparison_evidence"] = dict(schema=mcx.COMPARISON_EVIDENCE, version="1.0",
                        native_candidate_reference=record["native_candidate_reference"],
                        pair_binding_sha256=record["pair_binding_sha256"],
                        native_request_identity=refs["native"]["request_identity"],
                        native_request_sha256=refs["native"]["request_sha256"],
                        reference_request_identity=refs["reference"]["request_identity"],
                        reference_request_sha256=refs["reference"]["request_sha256"],
                        answer_identity=record["answer_identity"], answer_pdf_sha256=checksum,
                        sha256=sha, retained_relative_path=path)
            receipts.append(ReviewAcceptanceReceipt.create(body))
        observe("validation_completed_at")
        observe("acceptance_started_at")
        commit = store.publish_acceptance(tuple(receipts), artifacts, request_publication_identity=publication_identity,
            expected_predecessor=None if previous is None else previous.identity, committed_at=accepted_at,
            recheck=recheck, publication_guard=publication_guard, guarded_recheck=guarded_recheck)
        observe("acceptance_committed_at")
        return commit

    def _upload(self, review, facts, chart_bytes):  # type: ignore[no-untyped-def]
        record = self._require_current(review.native_run_identity)
        if self.transport.record_store.load_current() != record:
            raise PdfReviewTransportError("VISUAL_V3_REVIEW_PACK_SUPERSEDED")
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
        try:
            for candidate in answer.candidates:
                request_set = next(
                    item for item in prepared
                    if item[0].requirement.canonical_instrument == candidate.canonical_instrument
                )
                for request, response in zip(request_set, candidate.responses, strict=True):
                    self.cycle.retain(request, response)

            completion_inputs = []
            for candidate in answer.candidates:
                requirement = requirements[candidate.canonical_instrument]
                candidate_pack = next(
                    item for item in record.candidate_packs
                    if item.canonical_instrument == candidate.canonical_instrument
                )
                extension_fact = evaluate_completed_one_hour_extension(
                    requirement, facts
                )
                path_clearance_fact = evaluate_one_hour_path_clearance(
                    run_identity=requirement.native_run_identity,
                    instrument=facts.instrument(requirement.canonical_instrument),
                    direction=requirement.thesis.direction,
                )
                completion_inputs.append((
                    candidate,
                    requirement,
                    candidate_pack,
                    extension_fact,
                    path_clearance_fact,
                ))

            # All deterministic E01/E02/E03 facts are valid before any
            # Readiness or KR-370 promotion state can be retained.
            for (
                candidate,
                requirement,
                candidate_pack,
                extension_fact,
                path_clearance_fact,
            ) in completion_inputs:
                self.cycle.complete(
                    requirement,
                    _v3_layer2(requirement, candidate.responses),
                    facts,
                    candidate.responses,
                    created_at=self._now(),
                    reference=references.get(candidate.canonical_instrument),
                    inputs=extension_native_condition_inputs(
                        extension_fact, requirement
                    ),
                    review_pack=candidate_pack,
                    path_clearance=path_clearance_fact,
                    extension=extension_fact,
                )
        except (OSError, TypeError, ValueError) as error:
            failed = self.transport.record_import_failure(
                record, answer, _sanitized_post_validation_failure(error)
            )
            self._imports = (*self._imports, failed)
            raise
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
        if self.restoration_error is not None:
            raise PdfReviewTransportError(self.restoration_error)
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


@dataclass(frozen=True, slots=True)
class ProspectiveNativeReview:
    """Read-only requirements, not a retained historical Review or a new cycle."""

    native_run_identity: str
    requirements: tuple[NativeReviewRequirement, ...]
    excluded: tuple[tuple[str, str, str], ...]
    analysis_time: datetime
    continuity: object


@dataclass(slots=True)
class _NativeIntakeResponse:
    """One bounded validation scope; never survives a mutation boundary."""

    owner: object
    active: bool = True
    context: tuple | None = None
    authority: _NativePageAuthority | None = None
    values: dict = field(default_factory=dict)

    def read(self, key, load):
        require(self.active, "REVIEW_BINDING_STALE")
        if key not in self.values:
            self.values[key] = load()
        return self.values[key]


@dataclass(frozen=True, slots=True)
class _CompactNativePageState:
    """One validated current presentation generation; never mutation authority."""

    context: tuple
    authority: _NativePageAuthority
    projection: dict
    has_control: bool
    component_fence: PreparedReadFence
    current_fence: PreparedReadFence
    identity: str
    ticket: _ReviewPreparationTicket
    read_set: tuple
    revision: str


@dataclass(frozen=True, slots=True)
class _ReviewPreparationTicket:
    owner: object
    publication: tuple
    epoch: int
    attempt: int
    origin: str


@dataclass(frozen=True, slots=True)
class _ReviewPublication:
    """Single volatile publication; no analytical or mutation authority."""

    page: _CompactNativePageState | None = None
    revision: str = ""
    ticket: _ReviewPreparationTicket | None = None
    failure: str = "SWING_PAGE_PREPARATION_MISSING"
    reconciliation_failure: bool = False


@dataclass(frozen=True, slots=True)
class _NativePageAuthority:
    """Stable selected evidence authority, excluding attempt/status telemetry."""

    native: NativeDiscoveryRun
    facts: SameRunMtfFactSnapshot
    continuity: object
    current_manifest: bytes


class NativeReviewIntakeWorkflow:
    """Prospective Browser intake. Historical review transport is not a fallback.

    Batch actions carry one complete, exact envelope per candidate. No synthetic
    aggregate candidate identity replaces the existing requirement identities.
    """

    def __init__(self, application, native_review, live, store, *, v2_store=None):
        self.application, self.native_review, self.live, self.store = application, native_review, live, store
        if v2_store is not None and type(v2_store) is not LocalV2PromotionStore:
            raise TypeError("V2_PROMOTION_STORE_INVALID")
        self._v2_store = v2_store or LocalV2PromotionStore(
            self.store.root.parent.parent / "kr370-analytical-promotion-v2")
        self._v2_promotions: dict[tuple[str, str], V2PromotionRecord] = {}
        self.errors = {}
        self._prospective_cache = None
        self._page_prepare_lock = Lock()
        self._page_state_lock = Lock()
        self._page_transition_condition = Condition(Lock())
        self._page_transition_active = False
        self._page_active_readers = 0
        self._page_publication = _ReviewPublication()
        self._page_epoch = 0
        self._page_attempt = 0
        self._page_writers = 0
        self._page_scope = ContextVar("review_preparation", default=None)
        self._page_revision_builder = None

    # Compatibility accessors for existing compact-page inspection tests.
    # Production publication below replaces _page_publication exactly once.
    # As before, callers of these private accessors must own _page_state_lock.
    @property
    def _page_state(self):
        return self._page_publication.page

    @_page_state.setter
    def _page_state(self, value):
        self._page_publication = replace(self._page_publication, page=value)

    @property
    def _page_state_failure(self):
        return self._page_publication.failure

    @_page_state_failure.setter
    def _page_state_failure(self, value):
        self._page_publication = replace(self._page_publication, failure=value)

    def configure_page_revision(self, builder):
        """Composition-time registration, before requests/workers are started."""
        require(callable(builder), "SWING_PAGE_PREPARATION_INVALID")
        require(self._page_revision_builder is None,
                "SWING_PAGE_PREPARATION_INVALID")
        self._page_revision_builder = builder

    def reconciliation_snapshot(self):
        with self._page_state_lock:
            return self._page_publication

    def page_revision(self):
        return self.reconciliation_snapshot().revision

    def _preparation_publication(self):
        # Outside G. Production captures registration + immutable owner objects
        # under the application lock. Standalone workflow compositions retain
        # exact Native/MTF/continuity/manifest binding through the existing owner.
        capture = getattr(self.application, "review_reconciliation_identity", None)
        if callable(capture):
            return capture()
        _, native, continuity, status = self.application.opportunities_bundle_projection()
        facts = self.application.mtf_fact_snapshot()
        control = status["control"]
        manifest = None if control is None else control.get("current_manifest")
        return (id(native), id(facts), id(continuity), canonical(manifest))

    def _new_preparation_ticket(self, origin):
        publication = self._preparation_publication()
        with self._page_state_lock:
            self._page_attempt += 1
            ticket = _ReviewPreparationTicket(
                self, publication, self._page_epoch, self._page_attempt, origin)
        return ticket

    def _ticket_matches_locked(self, ticket):
        # Pure primitive comparisons only. G remains a leaf lock.
        return (ticket.owner is self and ticket.epoch == self._page_epoch
                and ticket.attempt == self._page_attempt
                and self._page_writers == 0)

    def _finish_page_failure(self, ticket, error, *, reconciliation=False):
        # Never invoke an owner, filesystem operation or callback while holding G.
        publication = self._preparation_publication()
        reason = self._reason(error, "SWING_PAGE_PREPARATION_UNAVAILABLE")
        with self._page_state_lock:
            if (not self._ticket_matches_locked(ticket)
                    or ticket.publication != publication):
                return False
            previous = self._page_publication
            self._page_publication = _ReviewPublication(
                revision=previous.revision, ticket=ticket, failure=reason,
                reconciliation_failure=(previous.reconciliation_failure or reconciliation))
        return True

    @contextmanager
    def reconciliation_scope(self):
        """Allocate before the ENTIRE callback, not when it reaches preparation."""
        inherited = self._page_scope.get()
        if inherited is not None:
            yield inherited
            return
        ticket = self._new_preparation_ticket("RECONCILIATION")
        token = self._page_scope.set(ticket)
        try:
            yield ticket
        except Exception as error:
            self._finish_page_failure(ticket, error, reconciliation=True)
            raise
        finally:
            self._page_scope.reset(token)

    @contextmanager
    def _page_input_write(self):
        """Invalidate BEFORE entering application -> WO-05 -> WO-07 owners."""
        with self._page_state_lock:
            self._page_epoch += 1
            self._page_writers += 1
            previous = self._page_publication
        try:
            yield
        finally:
            with self._page_state_lock:
                self._page_writers -= 1
                epoch = self._page_epoch
                idle = self._page_writers == 0
            # A rejected/no-op write need not invalidate an unchanged readable
            # page. Certify exact bytes only here, never from a GET. Do not clear
            # failure state or authorize any operation with this certification.
            if idle and previous.page is not None:
                try:
                    with self._prepared_state_response(previous.page):
                        pass
                    publication = self._preparation_publication()
                except (OSError, ValueError):
                    pass
                else:
                    ticket = previous.ticket
                    if ticket is not None and ticket.publication == publication:
                        certified = replace(previous, ticket=replace(ticket, epoch=epoch))
                        with self._page_state_lock:
                            if (self._page_publication is previous
                                    and self._page_epoch == epoch and self._page_writers == 0):
                                self._page_publication = certified

    @staticmethod
    def _page_read_set(component_fence, current_fence):
        # Explicit absent/present identity; byte fences remain authoritative.
        return tuple(sorted(
            (role, str(path), "ABSENT" if payload is None else "PRESENT",
             None if payload is None else len(payload),
             None if payload is None else sha256(payload).hexdigest())
            for role, fence in (("COMPONENT", component_fence), ("CURRENT", current_fence))
            for path, payload in fence.entries
        ))

    @contextmanager
    def _validated_response(self):
        with capture_prepared_reads() as reads:
            prepared = _NativeIntakeResponse(self)
            try:
                prepared.context = self._context(_response=prepared)
                yield prepared, reads
                PreparedReadFence(tuple(reads.items())).check()
                self.recheck_response(prepared)
            finally:
                prepared.active = False
                prepared.context = prepared.authority = None
                prepared.values.clear()

    @contextmanager
    def response(self):
        """Validate once, reuse within this response, then fence exact inputs.

        The component byte reads bracket the unchanged owning typed loaders.
        Neither file metadata nor the process-wide prospective cache substitutes
        for validation. No lock is held over projection I/O or rendering.
        """
        with self._validated_response() as (prepared, _reads):
            yield prepared

    def prepare_page_state(self) -> bool:
        """Prepare one current UI projection only at an explicit owner boundary."""

        state = self.prepare_page_generation()
        if state is None:
            return False
        return self.publish_page_generation(state)

    def prepare_page_generation(self):
        """Build one candidate without replacing the readable generation."""
        ticket = self._page_scope.get() or self._new_preparation_ticket("PAGE")
        try:
            with self._page_prepare_lock:
                with self._validated_response() as (prepared, reads):
                    projection = self.snapshot(_response=prepared)
                    context, authority = prepared.context, prepared.authority
                    has_control = self.has_control(_response=prepared)
                    # Revision calculation can read owners, so it runs outside G
                    # and inside the same captured-read/final-validation interval.
                    revision = ("" if self._page_revision_builder is None else
                        self._page_revision_builder(projection))
                    component_fence, current_fence = self._compact_page_fences(reads)
                    read_set = self._page_read_set(component_fence, current_fence)
                    identity = self._compact_page_identity(
                        context, authority, projection, has_control,
                        component_fence, current_fence)
                state = _CompactNativePageState(
                    context, authority, projection, has_control,
                    component_fence, current_fence, identity, ticket, read_set, revision)
        except (OSError, ValueError) as error:
            self._finish_page_failure(ticket, error)
            return None
        return state

    def prepared_page_projection(self, state):
        """Reuse one candidate after exact-byte and authority revalidation."""

        require(type(state) is _CompactNativePageState,
                "SWING_PAGE_PREPARATION_INVALID")
        with self._prepared_state_response(state) as prepared:
            return self.snapshot(_response=prepared)

    def publish_page_generation(self, state) -> bool:
        """Validate outside G; CAS page/revision/outcome with one assignment."""
        require(type(state) is _CompactNativePageState,
                "SWING_PAGE_PREPARATION_INVALID")
        ticket = state.ticket
        try:
            self.prepared_page_projection(state)
            require(state.read_set == self._page_read_set(
                state.component_fence, state.current_fence), "SWING_PAGE_PREPARATION_CORRUPT")
            publication = self._preparation_publication()
        except (OSError, ValueError) as error:
            self._finish_page_failure(ticket, error)
            return False
        with self._page_state_lock:
            if (not self._ticket_matches_locked(ticket)
                    or ticket.publication != publication):
                return False
            previous = self._page_publication
            # Local chart preparation cannot clear an unrelated broad failure.
            blocker = (previous.reconciliation_failure
                       and ticket.origin != "RECONCILIATION")
            self._page_publication = _ReviewPublication(
                page=state, revision=state.revision, ticket=ticket, failure="",
                reconciliation_failure=blocker)
        return True

    @contextmanager
    def successor_page_transition(self):
        """Fence current publication through coherent successor preparation."""

        with self._page_transition_condition:
            require(
                not self._page_transition_active,
                "SWING_PAGE_TRANSITION_ALREADY_ACTIVE",
            )
            self._page_transition_active = True
            while self._page_active_readers:
                self._page_transition_condition.wait()
        # The condition is released before acquiring G. Reader draining remains
        # unchanged; preparation for this successor may occur inside the scope.
        with self._page_state_lock:
            self._page_epoch += 1
        try:
            yield
        finally:
            with self._page_transition_condition:
                self._page_transition_active = False
                self._page_transition_condition.notify_all()

    @contextmanager
    def _page_reader(self):
        with self._page_transition_condition:
            while self._page_transition_active:
                self._page_transition_condition.wait()
            self._page_active_readers += 1
        try:
            yield
        finally:
            with self._page_transition_condition:
                self._page_active_readers -= 1
                if self._page_active_readers == 0:
                    self._page_transition_condition.notify_all()

    @contextmanager
    def page_response(self):
        """Serve the retained generation without reconstruction or recovery."""

        with self._page_reader():
            with self._prepared_page_response() as prepared:
                yield prepared

    @contextmanager
    def _prepared_page_response(self):
        with self._page_state_lock:
            slot = self._page_publication
            epoch = self._page_epoch
            writers = self._page_writers
        require(slot.page is not None, slot.failure or "SWING_PAGE_PREPARATION_MISSING")
        require(not writers and slot.ticket is not None and slot.ticket.epoch == epoch
                and not slot.reconciliation_failure, "REVIEW_BINDING_STALE")
        with self._prepared_state_response(slot.page) as prepared:
            yield prepared
        with self._page_state_lock:
            current = (self._page_publication is slot and self._page_epoch == epoch
                       and self._page_writers == 0)
        require(current, "REVIEW_BINDING_STALE")

    @contextmanager
    def _prepared_state_response(self, state):
        require(
            state.identity == self._compact_page_identity(
                state.context,
                state.authority,
                state.projection,
                state.has_control,
                state.component_fence,
                state.current_fence,
            ),
            "SWING_PAGE_PREPARATION_CORRUPT",
        )
        state.current_fence.check()
        self._check_compact_components(state)
        prepared = _NativeIntakeResponse(
            self,
            context=state.context,
            authority=state.authority,
            values={"snapshot": state.projection, ("has_control",): state.has_control},
        )
        try:
            self.recheck_response(prepared)
            yield prepared
            state.current_fence.check()
            self._check_compact_components(state)
            self.recheck_response(prepared)
        finally:
            prepared.active = False
            prepared.context = prepared.authority = None
            prepared.values.clear()

    @staticmethod
    def _check_compact_components(state):
        try:
            state.component_fence.check()
        except ValueError as error:
            raise ValueError("SWING_PUBLICATION_BUNDLE_INVALID") from error

    def page_state_status(self):
        """Return local preparation facts without filesystem or Provider work."""

        with self._page_state_lock:
            state = self._page_state
            failure = self._page_state_failure
        return {
            "state": "READY" if state is not None else (
                "MISSING" if failure == "SWING_PAGE_PREPARATION_MISSING" else "FAILED"
            ),
            "failure": failure,
            "retained_generations": 0 if state is None else 1,
            "retained_input_count": 0 if state is None else (
                len(state.component_fence.entries) + len(state.current_fence.entries)
            ),
            "retained_input_bytes": 0 if state is None else sum(
                0 if payload is None else len(payload)
                for fence in (state.component_fence, state.current_fence)
                for _, payload in fence.entries
            ),
        }

    def _compact_page_fences(self, reads):
        """Retain exact current controls/components, never immutable ancestry."""

        root = self.store.root
        components, current = [], []
        for path, payload in reads.items():
            try:
                relative = path.relative_to(root)
            except ValueError:
                # Native and MTF exact component bytes remain C1's final fence.
                components.append((path, payload))
                continue
            if (
                (len(relative.parts) == 1 and relative.name.startswith("current-"))
                or relative.parts[0] in {"acceptance-current", "downstream-current"}
            ):
                current.append((path, payload))
        return PreparedReadFence(tuple(components)), PreparedReadFence(tuple(current))

    @staticmethod
    def _compact_page_identity(
        context, authority, projection, has_control, component_fence, current_fence
    ):
        manifest, facts, review = context
        inputs = tuple(
            (
                str(path),
                None if payload is None else len(payload),
                None if payload is None else sha256(payload).hexdigest(),
            )
            for fence in (component_fence, current_fence)
            for path, payload in fence.entries
        )
        return sha256(repr((
            "KRONOS-SWING-COMPACT-PAGE-V1",
            manifest,
            facts.run_identity,
            review.native_run_identity,
            authority.native.run_identity,
            authority.facts.run_identity,
            id(authority.continuity),
            authority.current_manifest,
            has_control,
            projection,
            inputs,
        )).encode("utf-8")).hexdigest()

    def recheck_response(self, prepared):
        require(prepared.active and prepared.owner is self, "REVIEW_BINDING_STALE")
        _, current, current_continuity, current_status = self.application.opportunities_bundle_projection()
        try:
            current_authority = self._page_authority(
                current,
                self.application.mtf_fact_snapshot(),
                current_continuity,
                current_status,
            )
        except ValueError:
            require(False, "REVIEW_BINDING_STALE")
        authority = prepared.authority
        require(
            current_authority.native is authority.native
            and current_authority.facts is authority.facts
            and current_authority.continuity is authority.continuity
            and current_authority.current_manifest == authority.current_manifest,
            "REVIEW_BINDING_STALE",
        )

    @staticmethod
    def _page_authority(native, facts, continuity, status):
        require(type(native) is NativeDiscoveryRun, "NATIVE_DISCOVERY_RUN_INVALID")
        require(type(facts) is SameRunMtfFactSnapshot, "MTF_FACT_SNAPSHOT_INVALID")
        require(type(status) is dict, "SWING_PUBLICATION_BUNDLE_INVALID")
        control = status.get("control")
        require(type(control) is dict, "SWING_PUBLICATION_CURRENT_UNAVAILABLE")
        manifest = control.get("current_manifest")
        require(type(manifest) is dict, "SWING_PUBLICATION_BUNDLE_INVALID")
        digest = manifest.get("sha256")
        require(
            type(digest) is str
            and len(digest) == 64
            and all(character in "0123456789abcdef" for character in digest),
            "SWING_PUBLICATION_BUNDLE_INVALID",
        )
        return _NativePageAuthority(
            native,
            facts,
            continuity,
            canonical(manifest),
        )

    def _context(self, *, _response=None):
        if _response is not None:
            require(_response.active and _response.owner is self, "REVIEW_BINDING_STALE")
        if _response is not None and _response.context is not None:
            return _response.context
        workspace, native, continuity, status = self.application.opportunities_bundle_projection()
        require(status["control"] is not None, "SWING_PUBLICATION_CURRENT_UNAVAILABLE")
        manifest = status["control"].get("current_manifest")
        require(type(manifest) is dict and type(manifest.get("sha256")) is str
                and len(manifest["sha256"]) == 64
                and all(c in "0123456789abcdef" for c in manifest["sha256"]),
                "SWING_PUBLICATION_BUNDLE_INVALID")
        require(type(native) is NativeDiscoveryRun, "NATIVE_DISCOVERY_RUN_INVALID")
        facts = self.application.mtf_fact_snapshot()
        require(type(facts) is SameRunMtfFactSnapshot, "MTF_FACT_SNAPSHOT_INVALID")
        require(not status["reconciliation_unavailable"], "REVIEW_BINDING_STALE")
        require(native.run_identity == facts.run_identity
                and native.provider_source_identity == facts.provider_source_identity,
                "NATIVE_REVIEW_SAME_RUN_BINDING_INVALID")
        if _response is not None:
            _response.authority = self._page_authority(
                native, facts, continuity, status
            )
        # Use the existing exact-run store readers when supplied by production
        # composition. No latest selector, inferred root, recovery or lock file.
        for accessor, expected in (("native_discovery_evidence_store", native),
                                   ("mtf_fact_evidence_store", facts)):
            source = getattr(self.application, accessor, None)
            store = None if source is None else source()
            if store is not None:
                try:
                    if _response is not None:
                        from kronos.swing.v1.native_discovery import NativeDiscoveryEvidenceStore
                        from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
                        # These are the exact component paths used by WO-05's
                        # publication owner, not a latest/history selector.
                        if type(store) is NativeDiscoveryEvidenceStore:
                            path = store._root / "complete-runs" / (native.run_identity + ".json")
                            record_prepared_read(path, path.read_bytes())
                        elif type(store) is MtfFactEvidenceStore:
                            path = store._path(native.run_identity)
                            record_prepared_read(path, path.read_bytes())
                    retained = store.load(native.run_identity)
                except (OSError, ValueError):
                    require(False, "SWING_PUBLICATION_BUNDLE_INVALID")
                require(retained == expected, "SWING_PUBLICATION_BUNDLE_INVALID")
        # Re-read the publication projection after the separately locked factual
        # read. A concurrent publication is unavailable, never a mixed workspace.
        if _response is not None:
            self.recheck_response(_response)
        else:
            _, current, _, current_status = self.application.opportunities_bundle_projection()
            require(current == native and current_status == status, "REVIEW_BINDING_STALE")
        cached = self._prospective_cache
        if (cached is not None and cached[0] is native and cached[1] is facts
                and cached[2] is continuity and cached[3] == manifest["sha256"]):
            return manifest["sha256"], facts, cached[4]
        excluded = []
        try:
            requirements = build_native_review_requirements(native, facts)
        except ValueError:
            # Preserve the existing builder's per-assessment rules. One invalid
            # requirement must not hide valid siblings or invent new eligibility.
            values = []
            for assessment in native.assessments:
                if assessment.status is not NativeDiscoveryStatus.PROBABLE:
                    continue
                try:
                    require(assessment.weekly_state is not Native1WState.OPPOSING,
                            "NATIVE_REVIEW_OPPOSING_WEEKLY_CONTEXT_REJECTED")
                    values.append(_requirement(native, assessment, facts))
                except ValueError as error:
                    excluded.append((assessment.canonical_instrument,
                        "NSE" if assessment.product_path is NativeProductPath.NSE else "MCX",
                        self._reason(error, "NATIVE_REVIEW_ASSESSMENT_INELIGIBLE")))
            requirements = tuple(values)
        review = ProspectiveNativeReview(native.run_identity, requirements, tuple(excluded),
            getattr(workspace, "completed_at", None) or native.observed_at, continuity)
        self._prospective_cache = (native, facts, continuity, manifest["sha256"], review)
        return manifest["sha256"], facts, review

    def unavailable(self, error):
        return dict(rows=(), packages=(), error=self._reason(error, "REVIEW_BINDING_UNAVAILABLE"),
                    workspace=None)

    @staticmethod
    def _reason(error, fallback):
        # Never render unrestricted exception text, paths or incoming payloads.
        allowed = {"SWING_TRADE_WINDOW_SELECTION_STALE", "SWING_TRADE_WINDOW_SELECTION_CORRUPT",
            "SWING_TRADE_WINDOW_SELECTION_AMBIGUOUS", "SWING_TRADE_WINDOW_SELECTION_INVALID",
            "REVIEW_BINDING_STALE", "REVIEW_REQUEST_MISMATCH",
            "SWING_PUBLICATION_CURRENT_UNAVAILABLE", "SWING_PUBLICATION_BUNDLE_INVALID",
            "NATIVE_DISCOVERY_RUN_INVALID", "MTF_FACT_SNAPSHOT_INVALID",
            "NATIVE_REVIEW_SAME_RUN_BINDING_INVALID", "NATIVE_REVIEW_ASSESSMENT_INELIGIBLE",
            "NATIVE_REVIEW_OPPOSING_WEEKLY_CONTEXT_REJECTED", "REVIEW_PREDECESSOR_INVALID",
            "REVIEW_ACCEPTANCE_INCOMPLETE", "REVIEW_INTEGRITY_INVALID",
            "REVIEW_ARTIFACT_DIGEST_MISMATCH", "REVIEW_PUBLICATION_CONFLICT",
            "REVIEW_FIELD_TYPE_INVALID", "REVIEW_UNKNOWN_FIELD", "REVIEW_REQUIRED_FIELD_MISSING",
            "REVIEW_DUPLICATE_KEY", "REVIEW_JSON_INVALID", "REVIEW_TIMESTAMP_INVALID",
            "SWING_PAGE_PREPARATION_MISSING", "SWING_PAGE_PREPARATION_UNAVAILABLE",
            "SWING_PAGE_PREPARATION_CORRUPT", "V2_PROMOTION_PRESENTATION_BINDING_INVALID",
            "V2_PROMOTION_CURRENT_BINDING_INVALID", "NATIVE_ANALYSIS_DETAILS_V2_BINDING_INVALID",
            "NATIVE_ANALYSIS_DETAILS_V3_BINDING_INVALID"}
        allowed.add("REVIEW_CHART_ALREADY_CURRENT")
        return str(error) if str(error) in allowed else fallback

    def _requirements(self, market, instruments=None, *, _response=None):
        require(market in {"NSE", "MCX"}, "REVIEW_CONTRACT_UNSUPPORTED")
        _, _, review = self._context(_response=_response)
        values = tuple(sorted((item for item in review.requirements
            if item.thesis.product_path is (NativeProductPath.NSE if market == "NSE" else NativeProductPath.MCX)
            and (instruments is None or item.canonical_instrument in instruments)),
            key=lambda item: item.canonical_instrument))
        require(values and (instruments is None or tuple(item.canonical_instrument for item in values)
                == tuple(sorted(instruments))), "REVIEW_REQUEST_MISMATCH")
        return values

    def _publication(self, market, *, _response=None):
        if _response is not None:
            return _response.read(("publication", market), lambda: self._publication(market))
        require(market in {"NSE", "MCX"}, "REVIEW_CONTRACT_UNSUPPORTED")
        return self.store.load_current_request() if market == "NSE" else self.store.load_current_mcx_request()

    def has_control(self, *, _response=None):
        _, facts, _ = self._context(_response=_response)
        names = ["current-request.json", "current-mcx-request.json"]
        names.extend("acceptance-current/" + sha256(canonical(["NATIVE_REVIEW", market, facts.run_identity])).hexdigest()
                     + ".json" for market in ("NSE", "MCX"))
        if _response is not None:
            def selected():
                present = False
                for name in names:
                    path = self.store.root / name
                    try:
                        payload = path.read_bytes()
                    except FileNotFoundError:
                        payload = None
                    record_prepared_read(path, payload)
                    present = present or payload is not None
                return present
            return _response.read(("has_control",), selected)
        return any((self.store.root / name).exists() for name in names)

    def _history(self, market, run_identity, *, _response=None):
        if _response is not None:
            return _response.read(("history", market, run_identity), lambda: self._history(market, run_identity))
        """Verify retained request/PDF/role bindings for the complete pointer ancestry."""
        history = self.store.native_acceptance_history(market, run_identity)
        for commit in history:
            publication = (self.store.load_request(commit.value["request_publication_identity"]) if market == "NSE"
                           else self.store.load_mcx_request(commit.value["request_publication_identity"]))
            mapping = self._mapping(publication, market)
            require(mapping["native_run_identity"] == run_identity
                and {item.binding.value["canonical_instrument"] for item in commit.receipts}
                    == {item["canonical_instrument"] for item in mapping["subjects"]}, "REVIEW_REQUEST_MISMATCH")
            for receipt in commit.receipts:
                binding = receipt.binding.value
                subject = next(item for item in mapping["subjects"] if item["canonical_instrument"] == binding["canonical_instrument"])
                require(binding["analytical_run_identity"] == run_identity and binding["market"] == market
                    and binding["committed_run_manifest_identity"] == mapping["committed_run_manifest_identity"]
                    and binding["native_assessment_sha256"] == subject["native_assessment_sha256"]
                    and binding["request_identity"] == mapping["request_identity"]
                    and binding["request_timestamp"] == mapping["request_timestamp"]
                    and binding["review_pack_identity"] == mapping["review_pack_identity"]
                    and binding["review_pack_sha256"] == mapping["review_pack_sha256"]
                    and binding["review_cycle_identity"] == mapping.get("review_cycle_identity", mapping["review_pack_identity"]),
                    "REVIEW_REQUEST_MISMATCH")
                expected = {("NATIVE_NSE" if market == "NSE" else "NATIVE_MCX", item["timeframe"]): item
                            for item in subject["responses"]}
                if market == "MCX":
                    reference = next(item for item in publication.reference.value["subjects"]
                        if item["native_candidate_reference"] == subject["native_candidate_reference"])
                    expected.update({("SUPPORTING_REFERENCE", item["timeframe"]): item for item in reference["responses"]})
                for chart in receipt.body["chart_revisions"]:
                    requested = expected[(chart["role"], chart["timeframe_or_panel_identity"])]
                    require(chart["sha256"] == requested["chart_revision_sha256"]
                        and (market == "NSE" or chart["revision_identity"] == requested["chart_revision_identity"]),
                        "REVIEW_REQUEST_MISMATCH")
                    if chart["role"] == "SUPPORTING_REFERENCE":
                        require((chart["subject_identity"], chart["reference_market"], chart["reference_symbol"])
                            == (reference["reference_subject_identity"], reference["reference_market"], reference["reference_symbol"]),
                            "REVIEW_REQUEST_MISMATCH")
                    else:
                        require(chart["subject_identity"] == subject["canonical_instrument"]
                            and chart["reference_market"] is None and chart["reference_symbol"] is None,
                            "REVIEW_REQUEST_MISMATCH")
                    matching = [item for item in receipt.body["structured_evidence"] if item["role"] == chart["role"]
                        and item["timeframe_or_family_identity"] == chart["timeframe_or_panel_identity"]]
                    require(len(matching) == 1 and matching[0]["subject_identity"] == chart["subject_identity"],
                            "REVIEW_REQUEST_MISMATCH")
        return history

    @staticmethod
    def _mapping(publication, market):
        return publication.mapping.value if market == "NSE" else publication.native.value

    @staticmethod
    def _roles(market):
        return ("NATIVE_NSE",) if market == "NSE" else ("NATIVE_MCX", "SUPPORTING_REFERENCE")

    @staticmethod
    def _chart_binding(requirement, role):
        return dict(run_identity=requirement.native_run_identity,
            candidate_identity=requirement.requirement_sha256, instrument=requirement.canonical_instrument,
            market="NSE" if requirement.thesis.product_path is NativeProductPath.NSE else "MCX", role=role)

    def _selection(self, requirement, role, *, _response=None):
        if _response is not None:
            return _response.read(("selection", requirement.requirement_sha256, role), lambda: self._selection(requirement, role))
        return self.store.native_chart_selection(self._chart_binding(requirement, role))

    def current_state(self, market, instrument, *, _response=None):
        manifest, facts, _ = self._context(_response=_response)
        requirement = self._requirements(market, (instrument,), _response=_response)[0]
        publication = self._publication(market, _response=_response)
        mapping = None if publication is None else self._mapping(publication, market)
        history = self._history(market, facts.run_identity, _response=_response)
        receipt = next((item for commit in history for item in commit.receipts
            if item.binding.value["candidate_identity"] == requirement.requirement_sha256), None)
        revisions = [self._selection(requirement, role, _response=_response) for role in self._roles(market)]
        return dict(expected_committed_run_manifest=manifest, expected_run_identity=facts.run_identity,
            expected_candidate_identity=requirement.requirement_sha256,
            expected_review_cycle_identity=None if mapping is None else mapping.get("review_cycle_identity", mapping["review_pack_identity"]),
            expected_request_identity=None if mapping is None else mapping["request_identity"],
            expected_revision_set_digest=sha256(canonical(revisions)).hexdigest(),
            expected_acceptance_receipt_id=None if receipt is None else receipt.receipt_id)

    def expected(self, market, instruments, *, _response=None):
        # A GET emits no new UUID, cycle, request, receipt or storage object.
        return {instrument: {**self.current_state(market, instrument, _response=_response), "mutation_identity": "BROWSER-EXPLICIT-MUTATION"}
                for instrument in instruments}

    def _admit(self, market, expected, *, _return_requirements=False,
               _chart_only=False):
        require(type(expected) is dict and bool(expected), "REVIEW_PRECONDITION_INVALID")
        envelopes = {instrument: ReviewMutationPrecondition.create(value) for instrument, value in expected.items()}

        def validate(prepared):
            requirements = self._requirements(market, tuple(expected), _response=prepared)
            if not _chart_only:
                projection = self.snapshot(_response=prepared)
                rows = {(row["market"], row["instrument"]): row
                        for row in projection["rows"] if row["eligible"]}
            states = []
            for instrument, envelope in envelopes.items():
                if _chart_only:
                    # A chart belongs to one exact candidate. Another card's
                    # pointer can advance while this POST is queued, so the
                    # retained whole-page snapshot is not mutation authority.
                    current = self.current_state(market, instrument,
                        _response=prepared)
                else:
                    row = rows.get((market, instrument))
                    require(row is not None and type(row["expected"]) is dict,
                            "REVIEW_BINDING_STALE")
                    current = row["expected"].get(instrument)
                require(type(current) is dict, "REVIEW_BINDING_STALE")
                state = {key: value for key, value in current.items()
                         if key != "mutation_identity"}
                envelope.validate(state)
                states.append((state["expected_committed_run_manifest"], state["expected_run_identity"]))
            return requirements, tuple(states)

        # A published compact generation already owns exact component/current
        # byte fences and the complete mutation envelope. Reuse it when present;
        # missing preparation retains the full typed fail-closed path.
        with self._page_state_lock:
            page_state = self._page_state
        if page_state is None:
            with self._validated_response() as (prepared, reads):
                requirements, expected_publications = validate(prepared)
                fence = PreparedReadFence(tuple(reads.items()))
        elif _chart_only:
            with self._page_reader():
                # Reuse the immutable Native/MTF context, but read and fence
                # only this candidate's mutable selection and request state.
                require(page_state.identity == self._compact_page_identity(
                    page_state.context, page_state.authority,
                    page_state.projection, page_state.has_control,
                    page_state.component_fence, page_state.current_fence,
                ), "SWING_PAGE_PREPARATION_CORRUPT")
                page_state.component_fence.check()
                with capture_prepared_reads() as reads:
                    prepared = _NativeIntakeResponse(self,
                        context=page_state.context, authority=page_state.authority)
                    try:
                        self.recheck_response(prepared)
                        requirements, expected_publications = validate(prepared)
                        fence = PreparedReadFence(
                            page_state.component_fence.entries + tuple(reads.items()))
                        fence.check()
                        self.recheck_response(prepared)
                    finally:
                        prepared.active = False
                        prepared.context = prepared.authority = None
                        prepared.values.clear()
        else:
            with self._page_reader():
                with self._prepared_state_response(page_state) as prepared:
                    requirements, expected_publications = validate(prepared)
            fence = PreparedReadFence(
                page_state.component_fence.entries + page_state.current_fence.entries
            )

        def recheck(snapshot=None):
            fence.check()
            if snapshot is not None:
                for manifest, run in expected_publications:
                    require(snapshot.control["current_manifest"]["sha256"] == manifest
                            and snapshot.manifest["run_id"] == run, "REVIEW_BINDING_STALE")
        recheck()
        return (recheck, requirements) if _return_requirements else recheck

    def chart_reader(self, role, instrument, timeframe, *, _response=None):
        market = "NSE" if role == "NATIVE_NSE" else "MCX"
        require(role in self._roles(market) and timeframe in
                (("1W", "1D", "4H", "1H") if market == "NSE" else ("1D", "4H", "1H")),
                "REVIEW_CONTRACT_UNSUPPORTED")
        requirement = self._requirements(market, (instrument,), _response=_response)[0]
        selected = self._selection(requirement, role, _response=_response)
        require(selected is not None and selected["image"] is not None, "REVIEW_ACCEPTANCE_INCOMPLETE")
        image = (self.store.native_chart_bytes(selected) if _response is None else
                 _response.read(("chart", selected["selection_sha256"]),
                                lambda: self.store.native_chart_bytes(selected)))
        return selected["selection_sha256"], image

    def stage(self, market, instrument, role, expected, *, image=None,
              content_type=None, reject_exact_replay=False):
        require(set(expected) == {instrument} and role in self._roles(market), "REVIEW_PRECONDITION_INVALID")
        if image is not None:
            # Reject impossible payloads before reconstructing the large
            # authority bundle. The store repeats its cheap canonical check at
            # the write boundary; no validation or authority is bypassed.
            self.store.validate_native_chart_payload(image, content_type)
        recheck, requirements = self._admit(
            market, expected, _return_requirements=True, _chart_only=True,
        )
        requirement = requirements[0]
        if reject_exact_replay and image is not None:
            current = self._selection(requirement, role)
            if (current is not None and current["image"] == {
                    "sha256": sha256(image).hexdigest(), "content_type": content_type}):
                recheck()
                raise ReviewEvidenceError("REVIEW_CHART_ALREADY_CURRENT")
        if market == "MCX":
            bindings = {logical_role: self._chart_binding(requirement, logical_role)
                        for logical_role in self._roles(market)}
            previous = {logical_role: self._selection(requirement, logical_role)
                        for logical_role in self._roles(market)}
            with self._page_input_write():
                results = self.store.select_mcx_composite(bindings, image, content_type,
                    selected_at=timestamp(self.live._now()),
                    expected_selections={logical_role: None if previous[logical_role] is None
                        else previous[logical_role]["selection_sha256"] for logical_role in self._roles(market)},
                    publication_guard=self.application.publication_mutation_guard, recheck=recheck)
            self.errors.pop((market, instrument), None)
            return results[role]
        previous = self._selection(requirement, role)
        with self._page_input_write():
            result = self.store.select_native_chart(self._chart_binding(requirement, role), image, content_type,
                selected_at=timestamp(self.live._now()), expected_selection=None if previous is None else previous["selection_sha256"],
                publication_guard=self.application.publication_mutation_guard, recheck=recheck)
        self.errors.pop((market, instrument), None)
        return result

    def _prepared(self, instrument, requested_at):
        _, facts, review = self._context()
        matches = tuple(item for item in review.requirements
            if item.thesis.product_path is NativeProductPath.NSE
            and item.canonical_instrument == instrument)
        require(len(matches) == 1, "REVIEW_REQUEST_MISMATCH")
        requirement = matches[0]
        selected = self._selection(requirement, "NATIVE_NSE")
        image = self.store.native_chart_bytes(selected)
        return self.live.cycle.prepare(requirement, facts,
            chart_inputs_from_requirement(requirement, chart_identity=instrument,
                content_type=selected["image"]["content_type"], images=(image,) * 4),
            request_timestamp=requested_at, question_set_version="3.2")

    def generate(self, market, expected):
        from uuid import uuid4
        from kronos.swing.v1.review_evidence_binding import NseReviewRequestMapping, NSE_REQUEST_SCHEMA_V2, NSE_ANSWER_SCHEMA_V2
        from kronos.swing.v1 import mcx_native_visual_contract as mcx
        from kronos.swing.v1.pdf_visual_review_v3_live import render_nse_successor_question_pdf, render_mcx_successor_question_pdf
        from kronos.swing.v1.native_review import MCX_REFERENCE_MAPPINGS

        recheck = self._admit(market, expected)
        manifest, facts, _ = self._context()
        requirements = self._requirements(market, tuple(expected))
        previous = self._publication(market)
        now = self.live._now()
        pack_id = "KRONOS-V3-REVIEW-" + uuid4().hex.upper()
        request_id = "SWING-REVIEW-REQUEST-" + uuid4().hex.upper()
        common = dict(request_identity=request_id, request_sha256="0" * 64,
            review_pack_identity=pack_id, review_pack_sha256="0" * 64,
            native_run_identity=facts.run_identity, committed_run_manifest_identity=manifest,
            request_timestamp=timestamp(now))
        if market == "NSE":
            prepared = tuple(self._prepared(item.canonical_instrument, now) for item in requirements)
            subjects = [dict(subject_reference="SUBJECT-" + uuid4().hex.upper(),
                canonical_instrument=requests[0].requirement.canonical_instrument,
                native_assessment_sha256=requests[0].requirement.thesis.native_assessment_sha256,
                chart_revision_sha256=requests[0].chart_revision_sha256,
                responses=[dict(timeframe=item.timeframe.value, expected_chart_identity=item.chart_identity,
                    chart_revision_sha256=item.chart_revision_sha256,
                    machine_fact_integrity_sha256=item.machine_fact.integrity_sha256,
                    observation_boundary=timestamp(item.observation_boundary), analysis_boundary=timestamp(item.analysis_boundary))
                    for item in requests]) for requests in prepared]
            mapping = NseReviewRequestMapping.create(dict(**common, schema=NSE_REQUEST_SCHEMA_V2, version="2.0",
                question_set_identity=VISUAL_QUESTION_SET_V3_ID, question_set_version="3.2",
                answer_schema=NSE_ANSWER_SCHEMA_V2, answer_version="2.0", subjects=subjects))
            mapping, pdf = render_nse_successor_question_pdf(mapping, prepared)
            with self._page_input_write():
                return self.store.publish_nse_request(mapping, pdf, publication_timestamp=timestamp(now),
                    expected_predecessor=None if previous is None else previous.identity, recheck=lambda *_: recheck(),
                    publication_guard=self.application.publication_mutation_guard, guarded_recheck=recheck)
        common.update(request_bundle_identity="SWING-REVIEW-BUNDLE-" + uuid4().hex.upper(),
                      review_cycle_identity=pack_id)
        native_subjects, reference_subjects, images = [], [], {}
        for requirement in requirements:
            instrument = requirement.canonical_instrument
            reference_identity, reference_market, reference_symbol = MCX_REFERENCE_MAPPINGS[instrument]
            candidate_reference = requirement.requirement_sha256
            base = dict(native_candidate_reference=candidate_reference,
                native_assessment_sha256=requirement.thesis.native_assessment_sha256,
                supplied_native_direction=requirement.thesis.direction.value)
            for role in self._roles(market):
                revision, image = self.chart_reader(role, instrument, "1D")
                checksum = sha256(image).hexdigest()
                images[checksum] = image
                responses = []
                for tf in ("1D", "4H", "1H"):
                    response = dict(timeframe=tf, expected_chart_identity=instrument if role == "NATIVE_MCX" else reference_symbol,
                        chart_revision_identity=revision, chart_revision_sha256=checksum)
                    if role == "NATIVE_MCX":
                        fact = next(item for item in facts.instrument(instrument).reference_facts if item.chart_timeframe.value == tf)
                        response.update(native_machine_fact_integrity_sha256=fact.integrity_sha256,
                            governed_reference_period=fact.reference_period_type.value,
                            governed_reference_basis_availability=fact.availability.value,
                            observation_boundary=timestamp(facts.instrument(instrument).fact(FactualTimeframe(tf)).observation_boundary),
                            analysis_boundary=timestamp(fact.analysis_boundary))
                    responses.append(response)
                subject = dict(**base, subject_reference="SUBJECT-" + uuid4().hex.upper(), responses=responses)
                if role == "NATIVE_MCX":
                    native_subjects.append(dict(**subject, canonical_instrument=instrument))
                else:
                    reference_subjects.append(dict(**subject, native_canonical_instrument=instrument,
                        reference_subject_identity=reference_identity, reference_market=reference_market, reference_symbol=reference_symbol))
        native = mcx.McxNativeReviewRequestMapping.create(dict(**common,
            schema=mcx.NATIVE_REQUEST_SCHEMA_V2, version="2.0",
            question_contract_identity=mcx.NATIVE_QUESTIONS_V2, question_contract_version="2.0",
            answer_contract_identity=mcx.NATIVE_ANSWER_V2, answer_contract_version="2.0", subjects=native_subjects))
        reference = mcx.McxReferenceReviewRequestMapping.create(dict(common,
            request_identity="SWING-REVIEW-REQUEST-" + uuid4().hex.upper(),
            schema=mcx.REFERENCE_REQUEST_SCHEMA_V2, version="2.0",
            question_contract_identity=mcx.REFERENCE_QUESTIONS_V2, question_contract_version="2.0",
            answer_contract_identity=mcx.REFERENCE_ANSWER_V2, answer_contract_version="2.0", subjects=reference_subjects))
        native, reference, pdf = render_mcx_successor_question_pdf(native, reference, images)
        with self._page_input_write():
            return self.store.publish_mcx_request(native, reference, pdf, publication_timestamp=timestamp(now),
                expected_predecessor=None if previous is None else previous.identity, recheck=lambda *_: recheck(),
                publication_guard=self.application.publication_mutation_guard, guarded_recheck=recheck)

    @staticmethod
    def extract_answer(pdf):
        """Extract one staged PDF exactly once at the durable owner boundary."""
        require(type(pdf) is bytes and pdf.startswith(b"%PDF-")
                and len(pdf) <= 128 * 1024 * 1024,
                "REVIEW_ACCEPTANCE_INCOMPLETE")
        return extract_successor_answer_pdf(pdf)

    def bulk_admission(self, market, expected):
        """Capture the exact current request/Pack fence before durable staging."""
        recheck = self._admit(market, expected)
        publication = self._publication(market)
        require(publication is not None, "REVIEW_REQUEST_MISMATCH")
        mapping = self._mapping(publication, market)
        require(set(expected) == {item["canonical_instrument"]
                                  for item in mapping["subjects"]},
                "REVIEW_PRECONDITION_INVALID")
        recheck()
        return {
            "request_identity": mapping["request_identity"],
            "review_pack_identity": mapping["review_pack_identity"],
            "publication_identity": publication.identity,
        }

    def validate_selected_answer(self, market, expected, pdf):
        """Validate selected bytes against current authority without admitting them.

        This is an observational preflight, not the ADR-0058 upload action. It
        creates no batch, Answer copy, receipt, acceptance, or downstream work.
        The exact current publication is fenced on both sides of PDF extraction
        and closed-contract validation so a result can never mix generations.
        """
        recheck = self._admit(market, expected)
        publication = self._publication(market)
        require(publication is not None, "REVIEW_REQUEST_MISMATCH")
        mapping = self._mapping(publication, market)
        require(set(expected) == {item["canonical_instrument"]
                                  for item in mapping["subjects"]},
                "REVIEW_PRECONDITION_INVALID")
        extracted = self.extract_answer(pdf)
        if market == "NSE":
            validate_nse_successor_answer(extracted, publication.mapping)
        else:
            self.store.validate_mcx_answer_for_publication(
                extracted, publication.identity
            )
        recheck()
        return {
            "request_identity": mapping["request_identity"],
            "review_pack_identity": mapping["review_pack_identity"],
            "publication_identity": publication.identity,
        }

    def accept_answer(self, market, expected, pdf, *, extracted_answer=None,
                      phase_observer=None):
        recheck = self._admit(market, expected)
        publication = self._publication(market)
        require(publication is not None, "REVIEW_REQUEST_MISMATCH")
        mapping = self._mapping(publication, market)
        require(set(expected) == {item["canonical_instrument"] for item in mapping["subjects"]},
                "REVIEW_PRECONDITION_INVALID")
        _, facts, review = self._context()
        first = next(iter(expected))
        def state():
            recheck()
            return self.current_state(market, first)
        with self._page_input_write():
            commit = self.live.accept_successor_answer(self.store, publication.identity, pdf, market=market,
                review=review, facts=facts, chart_reader=self.chart_reader,
                precondition=ReviewMutationPrecondition.create(expected[first]), current_state=state,
                publication_guard=self.application.publication_mutation_guard,
                extracted_answer=extracted_answer, phase_observer=phase_observer)
        return commit

    def import_answer(self, market, expected, pdf):
        commit = self.accept_answer(market, expected, pdf)
        for receipt in commit.receipts:
            self.handoff(commit, receipt)
            self.errors.pop((market, receipt.binding.value["canonical_instrument"]), None)
        self.errors.pop((market, None), None)
        return commit

    @staticmethod
    def filenames(mapping):
        # Exact request-owned filename, never a newest-file selector.
        from re import fullmatch
        identity = mapping["review_pack_identity"]
        require(fullmatch(r"KRONOS-V3-REVIEW-[A-F0-9]{32}", identity) is not None, "REVIEW_REQUEST_MISMATCH")
        return identity + "_QUESTIONS.pdf", identity + "_ANSWERS.pdf"

    def question_bytes(self, market, identity):
        publication = self._publication(market)
        require(publication is not None and publication.identity == identity, "REVIEW_BINDING_STALE")
        relative = (publication.value["question_pdf_artifact"]["relative_path"] if market == "NSE"
                    else publication.value["question_pdf_relative_path"])
        payload = (self.store.root / relative).read_bytes()
        require(sha256(payload).hexdigest() == self._mapping(publication, market)["review_pack_sha256"],
                "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        return payload

    def export_question(self, market, publication):
        """Explicit output copy only. Committed artifact remains authority."""
        import os
        import tempfile
        from pathlib import Path
        mapping = self._mapping(publication, market)
        configuration = self.live.transport.configuration
        configuration.ensure_directories()
        path = configuration.question_directory / self.filenames(mapping)[0]
        payload = self.question_bytes(market, publication.identity)
        if path.exists():
            require(not path.is_symlink() and path.read_bytes() == payload, "REVIEW_PUBLICATION_CONFLICT")
            return path
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".prepared-", delete=False) as stream:
            pending = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            try:
                os.link(pending, path)
            except FileExistsError:
                require(not path.is_symlink() and path.read_bytes() == payload, "REVIEW_PUBLICATION_CONFLICT")
        finally:
            pending.unlink(missing_ok=True)
        return path

    def answer_bytes_from_directory(self, market, expected):
        self.bulk_admission(market, expected)
        publication = self._publication(market)
        require(publication is not None, "REVIEW_REQUEST_MISMATCH")
        directory = self.live.transport.configuration.answer_directory
        filename = self.filenames(self._mapping(publication, market))[1]
        path = directory / filename
        require(not directory.is_symlink() and path.is_file() and not path.is_symlink(), "REVIEW_ACCEPTANCE_INCOMPLETE")
        with path.open("rb") as stream:
            pdf = stream.read(128 * 1024 * 1024 + 1)
        require(len(pdf) <= 128 * 1024 * 1024, "REVIEW_ACCEPTANCE_INCOMPLETE")
        return pdf

    def answer_bytes_for_review_pack(self, review_pack_identity):
        """Read one exact retained Answer filename without rebinding current authority."""
        from re import fullmatch
        require(
            type(review_pack_identity) is str
            and fullmatch(r"KRONOS-V3-REVIEW-[A-F0-9]{32}", review_pack_identity)
            is not None,
            "REVIEW_REQUEST_MISMATCH",
        )
        directory = self.live.transport.configuration.answer_directory
        path = directory / (review_pack_identity + "_ANSWERS.pdf")
        require(
            not directory.is_symlink() and path.is_file() and not path.is_symlink(),
            "REVIEW_ACCEPTANCE_INCOMPLETE",
        )
        with path.open("rb") as stream:
            pdf = stream.read(128 * 1024 * 1024 + 1)
        require(len(pdf) <= 128 * 1024 * 1024,
                "REVIEW_ACCEPTANCE_INCOMPLETE")
        return pdf

    def import_from_directory(self, market, expected):
        return self.import_answer(market, expected,
                                  self.answer_bytes_from_directory(market, expected))

    def snapshot(self, *, _response=None):
        """Observational projection; invalid selected graphs do not fall back."""
        if _response is None:
            try:
                with self.response() as prepared:
                    return self.snapshot(_response=prepared)
            except (OSError, ValueError) as error:
                return self.unavailable(error)
        if "snapshot" in _response.values:
            return _response.values["snapshot"]
        from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
        from kronos.swing.v1.native_review import MCX_REFERENCE_MAPPINGS
        try:
            manifest, facts, review = self._context(_response=_response)
        except (OSError, ValueError) as error:
            return dict(rows=(), packages=(), error=self._reason(error, "REVIEW_BINDING_UNAVAILABLE"),
                        workspace=None)
        rows, packages = [], []
        for market in ("NSE", "MCX"):
            requirements = tuple(item for item in review.requirements if item.thesis.product_path is
                (NativeProductPath.NSE if market == "NSE" else NativeProductPath.MCX))
            if not requirements:
                continue
            try:
                publication = self._publication(market, _response=_response)
                history = self._history(market, facts.run_identity, _response=_response)
                latest = {}
                for commit in history:
                    for receipt in commit.receipts:
                        latest.setdefault(receipt.binding.value["candidate_identity"], (commit, receipt))
                for requirement in requirements:
                    instrument = requirement.canonical_instrument
                    selected = {role: self._selection(requirement, role, _response=_response) for role in self._roles(market)}
                    evidence, downstream, receipt_id = "MISSING", "NOT_RUN", None
                    supported_result = None
                    retained = latest.get(requirement.requirement_sha256)
                    if retained is not None:
                        commit, receipt = retained
                        receipt_id = receipt.receipt_id
                        try:
                            self._verify_receipt_current(receipt, _response=_response)
                            evidence = "ACCEPTED"
                        except ReviewEvidenceError as error:
                            evidence = "STALE" if error.code in {"REVIEW_BINDING_STALE", "REVIEW_ACCEPTANCE_INCOMPLETE"} else "INVALID"
                        attempts = self.store.downstream_attempts(commit.identity, receipt_id,
                            VISUAL_QUESTION_SET_V3_ID,
                            receipt.body["contracts"][0]["question_contract_version"])
                        if attempts:
                            downstream = attempts[0].value["state"]
                            completed = self.live.cycle.completed_for(facts.run_identity, instrument) if market == "NSE" else None
                            if (evidence == "ACCEPTED" and downstream == "SUCCEEDED" and completed is not None
                                    and completed.promotion is not None and completed.review_pack is not None
                                    and completed.review_pack.review_pack_id == receipt.binding.value["review_pack_identity"]
                                    and [completed.readiness.result_sha256, completed.promotion.integrity_sha256]
                                        == attempts[0].value["output_identities"]):
                                supported_result = (completed.readiness.readiness.value, completed.promotion.classification.value)
                    error = self.errors.get((market, instrument)) or self.errors.get((market, None))
                    if error and evidence == "MISSING":
                        evidence = "INVALID"
                    predecessors = tuple(item.receipt_id for previous in history for item in previous.receipts
                        if item.binding.value["candidate_identity"] == requirement.requirement_sha256 and item.receipt_id != receipt_id)
                    rows.append(dict(instrument=instrument, market=market, selected=selected,
                        expected=self.expected(market, (instrument,), _response=_response), evidence=evidence, downstream=downstream,
                        receipt_id=receipt_id, replaced=predecessors, error=error, supported_result=supported_result,
                        direction=requirement.thesis.direction.value,
                        reference=None if market == "NSE" else MCX_REFERENCE_MAPPINGS[instrument],
                        complete=all(value is not None and value["image"] is not None for value in selected.values())))
                    rows[-1].update(eligible=True, run_identity=facts.run_identity,
                        assessment_sha256=requirement.thesis.native_assessment_sha256,
                        requirement_sha256=requirement.requirement_sha256,
                        question_ready=self._question_current(publication, market, manifest, requirement, selected))
                if publication is not None:
                    mapping = self._mapping(publication, market)
                    instruments = tuple(item["canonical_instrument"] for item in mapping["subjects"])
                    current = bool(instruments) and all(any(row["instrument"] == instrument
                        and row["market"] == market and row["question_ready"] for row in rows)
                        for instrument in instruments)
                    packages.append(dict(market=market, identity=publication.identity,
                        question_filename=self.filenames(mapping)[0], answer_filename=self.filenames(mapping)[1],
                        expected=self.expected(market, instruments, _response=_response) if current else None))
            except (OSError, ValueError) as error:
                rows = [item for item in rows if item["market"] != market]
                rows.extend(dict(instrument=item.canonical_instrument, market=market, selected={}, expected=None,
                    evidence="INVALID", downstream="UNAVAILABLE", receipt_id=None, replaced=(),
                    error=self._reason(error, "REVIEW_RESTORATION_UNAVAILABLE"), reference=None,
                    direction=item.thesis.direction.value,
                    complete=False, supported_result=None, eligible=True, question_ready=False,
                    run_identity=facts.run_identity, assessment_sha256=item.thesis.native_assessment_sha256,
                    requirement_sha256=item.requirement_sha256) for item in requirements)
        rows.extend(dict(instrument=instrument, market=market, eligible=False, expected=None,
            evidence="MISSING", error=reason, selected={}, replaced=(), complete=False,
            direction=None,
            question_ready=False, run_identity=facts.run_identity, assessment_sha256=None,
            requirement_sha256=None) for instrument, market, reason in review.excluded)
        continuity_rows = (() if review.continuity is None else review.continuity.contribution.rows)
        for row in rows:
            row["continuity"] = next((item for item in continuity_rows
                if item.canonical_instrument == row["instrument"]), None)
        result = dict(rows=tuple(rows), packages=tuple(packages), error=None,
            workspace=dict(run_identity=facts.run_identity, manifest=manifest,
                analysis_time=review.analysis_time, state="CURRENT", population=len(rows),
                eligible=len(review.requirements), excluded=len(review.excluded),
                nse=sum(row["market"] == "NSE" and row["eligible"] for row in rows),
                mcx=sum(row["market"] == "MCX" and row["eligible"] for row in rows)))
        _response.values["snapshot"] = result
        return result

    def _question_current(self, publication, market, manifest, requirement, selected):
        """Question-ready is exact current chart/request binding, not PDF presence."""
        if publication is None:
            return False
        mapping = self._mapping(publication, market)
        if (mapping["native_run_identity"] != requirement.native_run_identity
                or mapping["committed_run_manifest_identity"] != manifest):
            return False
        subject = next((item for item in mapping["subjects"]
            if item["canonical_instrument"] == requirement.canonical_instrument
            and item["native_assessment_sha256"] == requirement.thesis.native_assessment_sha256), None)
        if subject is None:
            return False
        by_role = {"NATIVE_NSE" if market == "NSE" else "NATIVE_MCX": subject}
        if market == "MCX":
            if subject["native_candidate_reference"] != requirement.requirement_sha256:
                return False
            by_role["SUPPORTING_REFERENCE"] = next((item for item in publication.reference.value["subjects"]
                if item["native_candidate_reference"] == requirement.requirement_sha256), None)
        for role, requested in by_role.items():
            chart = selected.get(role)
            if chart is None or chart["image"] is None or requested is None:
                return False
            if any(response["chart_revision_sha256"] != chart["image"]["sha256"]
                   or (market == "MCX" and response["chart_revision_identity"] != chart["selection_sha256"])
                   for response in requested["responses"]):
                return False
        return True

    def downstream_applicable(self, completed, *, _response=None):
        """Receipt selection cannot borrow a prior cycle's successful output."""
        if completed is None:
            return False
        try:
            _, facts, _ = self._context(_response=_response)
            if completed.requirement.native_run_identity != facts.run_identity or not self.has_control(_response=_response):
                return True  # Original historical loader and binding remain intact.
            row = next((item for item in self.snapshot(_response=_response)["rows"]
                if item["instrument"] == completed.requirement.canonical_instrument), None)
            return (row is not None and row["evidence"] == "ACCEPTED" and row["downstream"] == "SUCCEEDED"
                and row["supported_result"] is not None and completed == self.live.cycle.completed_for(
                    facts.run_identity, completed.requirement.canonical_instrument))
        except (OSError, ValueError):
            if _response is not None:
                raise
            return False

    def _verify_receipt_current(self, receipt, *, _response=None):
        value = receipt.binding.value
        manifest, facts, review = self._context(_response=_response)
        market, instrument = value["market"], value["canonical_instrument"]
        product = NativeProductPath.NSE if market == "NSE" else NativeProductPath.MCX
        matches = tuple(item for item in review.requirements
            if item.thesis.product_path is product
            and item.canonical_instrument == instrument)
        require(len(matches) == 1, "REVIEW_REQUEST_MISMATCH")
        requirement = matches[0]
        require(value["committed_run_manifest_identity"] == manifest
            and value["analytical_run_identity"] == facts.run_identity
            and value["candidate_identity"] == requirement.requirement_sha256
            and value["native_assessment_sha256"] == requirement.thesis.native_assessment_sha256,
            "REVIEW_BINDING_STALE")
        publication = self._publication(market, _response=_response)
        require(publication is not None, "REVIEW_BINDING_STALE")
        mapping = self._mapping(publication, market)
        require(value["request_identity"] == mapping["request_identity"]
            and value["review_pack_identity"] == mapping["review_pack_identity"]
            and value["review_pack_sha256"] == mapping["review_pack_sha256"]
            and value["review_cycle_identity"] == mapping.get("review_cycle_identity", mapping["review_pack_identity"]),
            "REVIEW_BINDING_STALE")
        # One governed composite selection supplies every timeframe for a role.
        # Validate every retained chart row, while reading and hashing that
        # immutable composite only once.  Startup performs this validation both
        # before projection and again at the guarded handoff boundary; repeated
        # multi-megabyte reads are not an additional integrity check.
        composites = {}
        for chart in receipt.body["chart_revisions"]:
            role = chart["role"]
            if role not in composites:
                require(role in self._roles(market), "REVIEW_CONTRACT_UNSUPPORTED")
                selected = self._selection(requirement, role, _response=_response)
                require(selected is not None and selected["image"] is not None,
                        "REVIEW_ACCEPTANCE_INCOMPLETE")
                image = (self.store.native_chart_bytes(selected) if _response is None else
                    _response.read(("chart", selected["selection_sha256"]),
                        lambda: self.store.native_chart_bytes(selected)))
                revision = selected["selection_sha256"]
                composites[role] = revision, sha256(image).hexdigest()
            revision, image_sha256 = composites[role]
            require(revision == chart["revision_identity"] and image_sha256 == chart["sha256"],
                    "REVIEW_BINDING_STALE")

    def handoff(self, commit, receipt, *, restore_only=False, expected=None):
        _, facts, review = self._context()
        admission = None if expected is None else self._admit(receipt.binding.value["market"], expected)
        def recheck(snapshot, accepted):
            if admission is not None:
                admission(snapshot)
            self._verify_receipt_current(accepted)
            if snapshot is not None:
                require(snapshot.control["current_manifest"]["sha256"] == accepted.binding.value["committed_run_manifest_identity"],
                        "REVIEW_BINDING_STALE")
        with self._page_input_write():
            result = self.live.handoff_accepted_receipt(self.store, commit.identity, receipt.receipt_id,
                review=review, facts=facts, chart_bytes=None, prepared_requests=self._prepared,
                publication_guard=self.application.publication_mutation_guard, recheck=recheck, restore_only=restore_only)
            if restore_only:
                self._restore_v2_for_receipt(receipt)
            elif receipt.binding.value["market"] == "MCX" or (
                result is not None and result.value["state"] == "SUCCEEDED"
            ):
                self._publish_v2_for_receipt(commit, receipt, facts)
        return result

    def _v2_current(self, source):
        try:
            manifest, facts, _ = self._context()
            accepted = source["acceptance"]
            receipt = self.store.resolve_committed_receipt(
                accepted["commit_identity"], accepted["receipt_identity"], current=True)
            return bool(
                manifest == source["committed_run_manifest_identity"]
                and facts.run_identity == source["native_run_identity"]
                and receipt.value["integrity_sha256"] == accepted["receipt_integrity_sha256"]
                and receipt.binding.value["canonical_instrument"] == source["canonical_instrument"]
                and receipt.binding.value["native_assessment_sha256"] == source["native_assessment_sha256"]
            )
        except (KeyError, OSError, ValueError):
            return False

    def v2_for(self, run_identity: str, canonical_instrument: str) -> V2PromotionRecord | None:
        record = self._v2_promotions.get((run_identity, canonical_instrument))
        if record is None:
            return None
        if (self._v2_current(record.value["source"]) is not True
                or not self._v2_confirmation_current(record)):
            raise ValueError("V2_PROMOTION_CURRENT_BINDING_INVALID")
        return record

    def _v2_confirmation_current(self, record: V2PromotionRecord) -> bool:
        value = record.value
        source = value["source"]
        if source["market"] != "NSE":
            return True
        reader = getattr(self.application, "relative_context_run", None)
        try:
            current = reader() if callable(reader) else None
            return _nse_confirmation(source, current) == value["confirmation"]
        except (KeyError, TypeError, ValueError):
            return False

    def _restore_v2_for_receipt(self, receipt) -> None:
        binding = receipt.binding.value
        root = self._v2_store.root / binding["analytical_run_identity"]
        if not root.exists():
            return
        matches = []
        for path in sorted(root.glob("*.json")):
            candidate = V2PromotionRecord(self._v2_store._read(path))
            source = candidate.value["source"]
            if (source["acceptance"]["receipt_identity"] == receipt.receipt_id
                    and source["canonical_instrument"] == binding["canonical_instrument"]
                    and source["native_assessment_sha256"] == binding["native_assessment_sha256"]):
                loaded = self._v2_store.load_exact(
                    source, candidate.value["input_sha256"], current=self._v2_current)
                if loaded is not None:
                    matches.append(loaded)
        require(len(matches) <= 1, "V2_OUTPUT_AMBIGUOUS")
        if matches:
            record = matches[0]
            require(self._v2_confirmation_current(record), "V2_SOURCE_STALE")
            self._v2_promotions[(binding["analytical_run_identity"],
                                 binding["canonical_instrument"])] = record
            if binding["market"] == "NSE":
                self.live.cycle.attach_v2(record)

    def _publish_v2_for_receipt(self, commit, receipt, facts) -> None:
        binding = receipt.binding.value
        market = binding["market"]
        requirement = self._requirements(market, (binding["canonical_instrument"],))[0]
        path_clearance = evaluate_one_hour_path_clearance(
            run_identity=requirement.native_run_identity,
            instrument=facts.instrument(requirement.canonical_instrument),
            direction=requirement.thesis.direction)
        extension = evaluate_completed_one_hour_extension(requirement, facts)
        completed = (self.live.cycle.completed_for(
            requirement.native_run_identity, requirement.canonical_instrument)
            if market == "NSE" else None)
        if market == "NSE" and completed is None:
            raise ValueError("V2_COMPLETED_REVIEW_MISSING")
        request = (self.store.load_request(
            commit.value["request_publication_identity"]).mapping
            if market == "NSE" else None)
        context_reader = getattr(self.application, "relative_context_run", None)
        record = evaluate_governed(
            requirement=requirement, facts=facts, path_clearance=path_clearance,
            extension=extension, store=self.store, commit_identity=commit.identity,
            receipt_identity=receipt.receipt_id,
            current_manifest=lambda: self._context()[0],
            created_at=datetime.fromisoformat(receipt.body["accepted_at"]),
            visual=None if completed is None else completed.responses,
            relative_context=(context_reader() if market == "NSE" and callable(context_reader)
                              else None),
            nse_request=request)
        self._v2_store.retain(record, current=self._v2_current)
        require(self._v2_confirmation_current(record), "V2_PUBLICATION_CHANGED")
        self._v2_promotions[(requirement.native_run_identity,
                             requirement.canonical_instrument)] = record
        if market == "NSE":
            self.live.cycle.attach_v2(record)

    def restore(self):
        # Read/verify the whole committed graph first, before any memory projection.
        for market in ("NSE", "MCX"):
            try:
                # One bounded read scope preserves exact typed validation and
                # byte fencing while reusing common context and composite bytes
                # across the complete market graph. It closes before any
                # in-memory downstream restoration begins.
                with self.response() as prepared:
                    facts = prepared.context[1]
                    history = self._history(
                        market, facts.run_identity, _response=prepared)
                    if not history:
                        continue
                    commit = history[0]
                    for receipt in commit.receipts:
                        self._verify_receipt_current(receipt, _response=prepared)
                for receipt in commit.receipts:
                    self.handoff(commit, receipt, restore_only=True)
            except (OSError, ValueError):
                self.errors[(market, None)] = "REVIEW_RESTORATION_UNAVAILABLE"


def _sanitized_post_validation_failure(error: BaseException) -> str:
    if str(error) == "COMPLETED_ONE_HOUR_EXTENSION_FACT_INVALID":
        return "COMPLETED_1H_EXTENSION_FACT_INVALID"
    return "POST_VALIDATION_PROCESSING_FAILED"


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
