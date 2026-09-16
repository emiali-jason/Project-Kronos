"""Application boundary for MCX-CONTEXT-01 supporting evidence."""

from __future__ import annotations

from dataclasses import dataclass
from contextvars import ContextVar
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from kronos.market.calendar import MarketCalendarPublisher
from kronos.swing.v1.mcx_supporting_context import (
    ContextAvailability,
    MCX_CONTEXT_INSTRUMENT_FAMILIES,
    McxContextFamily,
    McxContextSlot,
    McxSupportingContextRecord,
    McxSupportingContextStore,
    build_context_record,
    MCX_CONTEXT_CONTRACT_ID,
    MCX_CONTEXT_CONTRACT_VERSION,
    _primitive,
)
from kronos.swing.v1.review_evidence_binding import (
    ReviewAcceptanceReceipt, ReviewMutationPrecondition, canonical,
    require, timestamp,
)
from kronos.swing.v1.review_evidence_store import (
    ReviewEvidenceStore, PreparedReadFence, capture_prepared_reads, record_prepared_read,
)
from kronos.swing.v1.mcx_supporting_context_pdf import (
    McxContextPdfTransport,
    McxContextPanelValidationError,
    McxContextQuestionPack,
    McxContextStagedImage,
)
from kronos.swing.v1.pdf_visual_review import PdfReviewTransportError


_IST = ZoneInfo("Asia/Kolkata")
_INTAKE_MUTATION = ContextVar("swing_context_intake_mutation", default=None)


@dataclass(frozen=True, slots=True)
class McxContextFamilyStatus:
    family: McxContextFamily
    availability: ContextAvailability
    revision: int | None
    imported_at: datetime | None
    image_staged: bool
    image_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class McxContextFailureStatus:
    machine_code: str
    family: McxContextFamily | None = None
    panel_id: str | None = None
    failed_field: str | None = None
    expected: str | None = None
    observed: str | None = None


@dataclass(frozen=True, slots=True)
class McxContextSlotStatus:
    slot: McxContextSlot
    families: tuple[McxContextFamilyStatus, McxContextFamilyStatus]
    question_pack: McxContextQuestionPack | None
    last_error: McxContextFailureStatus | None
    intake_precondition: str | None = None
    evidence_state: str | None = None


@dataclass(frozen=True, slots=True)
class McxSupportingContextSnapshot:
    trading_date: date
    trading_date_required: bool
    slots: tuple[McxContextSlotStatus, McxContextSlotStatus]


class McxSupportingContextWorkflow:
    def __init__(
        self, store: McxSupportingContextStore, transport: McxContextPdfTransport,
        *, calendar: MarketCalendarPublisher | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        intake_store: ReviewEvidenceStore | None = None,
        publication_source=None,
    ) -> None:
        self.store = store; self.transport = transport
        self.calendar = calendar or MarketCalendarPublisher(); self._clock = clock
        self._errors: dict[McxContextSlot, McxContextFailureStatus] = {}
        self.intake_store = intake_store
        self.publication_source = publication_source

    def current_intake_state(self, slot):
        require(self.intake_store is not None and self.publication_source is not None,
                "REVIEW_PRECONDITION_INVALID")
        _, native, _, publication = self.publication_source.opportunities_bundle_projection()
        control = publication["control"]
        require(native is not None and control is not None
                and not publication["reconciliation_unavailable"], "REVIEW_BINDING_STALE")
        day, _ = self.governed_trading_date()
        pack = self.transport.store.current(day, slot)
        require(pack is None or (pack.trading_date == day and pack.slot == slot),
                "REVIEW_REQUEST_MISMATCH")
        history = self.intake_store.context_acceptance_history(day, slot)
        # The date/slot participates even before a first image or request exists.
        # Midnight rollover therefore cannot retarget a previously rendered tab.
        revisions = [day.isoformat(), slot.value, [
            None if (image := self.transport.store.current_image(day, slot, family)) is None
            else _primitive(image) for family in McxContextFamily
        ]]
        return dict(expected_committed_run_manifest=control["current_manifest"]["sha256"],
            expected_run_identity=native.run_identity, expected_candidate_identity=None,
            expected_review_cycle_identity=None if pack is None else pack.question_pack_identity,
            expected_request_identity=None if pack is None else pack.question_pack_identity,
            expected_revision_set_digest=sha256(canonical(revisions)).hexdigest(),
            expected_acceptance_receipt_id=None if not history else history[0].receipts[0].receipt_id)

    def mutate_intake(self, slot, operation, precondition, **values):
        """Explicit Browser mutation; no fallback or automatic stale retry."""
        require(type(precondition) is ReviewMutationPrecondition
                and operation in {"STAGE", "REMOVE", "GENERATE", "IMPORT"}, "REVIEW_PRECONDITION_INVALID")
        current = lambda: self.current_intake_state(slot)
        precondition.validate(current())
        guard = self.publication_source.publication_mutation_guard
        if operation == "IMPORT":
            require(not values, "REVIEW_PRECONDITION_INVALID")
            try:
                return self.upload_answer_atomic(slot, precondition=precondition,
                    current_state=current, publication_guard=guard)
            except (PdfReviewTransportError, ValueError) as error:
                self._errors[slot] = self._failure_status(error)
                raise
        day, required = self.governed_trading_date()
        require(required, "REVIEW_BINDING_STALE")
        with capture_prepared_reads() as reads:
            state = current()
            precondition.validate(state)
            require(self.governed_trading_date() == (day, True), "REVIEW_BINDING_STALE")
            prepared = self.transport.prepare_intake_publication(day, slot, operation, **values)
        fence = PreparedReadFence(tuple(reads.items()))

        def recheck(snapshot):
            fence.check()
            require(self._clock().astimezone(_IST).date() == day
                    and snapshot.control["current_manifest"]["sha256"] == state["expected_committed_run_manifest"]
                    and snapshot.manifest["run_id"] == state["expected_run_identity"], "REVIEW_BINDING_STALE")

        with self.intake_store.publication_commit_guard(guard, recheck):
            result = self.transport.commit_intake_publication(prepared)
        self._errors.pop(slot, None)
        return result

    def _records(self, *, trading_date: date, slot=None, family=None):
        historical = self.store.records(trading_date=trading_date, slot=slot, family=family)
        if self.intake_store is None:
            return historical
        accepted = []
        for selected_slot in ((slot,) if slot is not None else tuple(McxContextSlot)):
            for commit, records in self.intake_store.context_package_history(trading_date, selected_slot):
                receipt = commit.receipts[0]
                binding = receipt.binding.value
                pack = self.transport.store.load_exact(binding["question_pack_identity"])
                require(pack.trading_date == trading_date and pack.slot == selected_slot
                        and pack.question_pdf_sha256 == binding["question_pack_sha256"]
                        and timestamp(pack.created_at) == binding["request_timestamp"]
                        and sha256(Path(pack.question_path).read_bytes()).hexdigest() == pack.question_pdf_sha256,
                        "REVIEW_REQUEST_MISMATCH")
                require([(item["timeframe_or_panel_identity"], item["sha256"]) for item in receipt.body["chart_revisions"]]
                        == [(item.family.value, item.image_sha256) for item in pack.images],
                        "REVIEW_REQUEST_MISMATCH")
                accepted.extend(record for record in records if family is None or record.family == family)
        # Successor results are read from committed receipts only; they are not
        # copied into the historical sequential family store.
        require(not ({item.record_id for item in historical} & {item.record_id for item in accepted}),
                "REVIEW_PUBLICATION_CONFLICT")
        return (*historical, *accepted)

    def upload_answer_atomic(self, slot, *, precondition, current_state, publication_guard):
        """WO-07 whole-slot import; no family write before the commit pointer.

        The Browser owner supplies its exact current-state resolver and WO-05
        guard. Neither missing preconditions nor a missing guard is a fallback
        to historical upload. Parsing is outside the publication critical section.
        """
        require(self.intake_store is not None and type(precondition) is ReviewMutationPrecondition
                and callable(current_state) and callable(publication_guard), "REVIEW_PRECONDITION_INVALID")
        if self.publication_source is not None:
            require(publication_guard == self.publication_source.publication_mutation_guard,
                    "REVIEW_PRECONDITION_INVALID")
            current_state = lambda: self.current_intake_state(slot)
        day, required = self.governed_trading_date()
        require(required, "REVIEW_BINDING_STALE")
        precondition.validate(current_state())
        pack = self.transport.store.current(day, slot)
        require(pack is not None, "REVIEW_REQUEST_MISMATCH")
        captured = self.transport.capture_and_validate(pack)
        answer = captured.answer
        question_bytes = Path(pack.question_path).read_bytes()
        require(sha256(question_bytes).hexdigest() == pack.question_pdf_sha256, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        images = tuple(self.transport.store.image_bytes(item) for item in pack.images)
        history = self.intake_store.context_acceptance_history(day, slot)
        previous = history[0] if history else None
        prepared_fence = None
        expected_state = None

        def recheck(_receipts=None, request_identity=None):
            nonlocal prepared_fence, expected_state
            if prepared_fence is None:
                with capture_prepared_reads() as reads:
                    expected_state = current_state()
                    precondition.validate(expected_state)
                    require(self.governed_trading_date() == (day, True)
                            and self.transport.store.current(day, slot) == pack, "REVIEW_BINDING_STALE")
                    require(self.intake_store.context_acceptance_history(day, slot) == history,
                            "REVIEW_BINDING_STALE")
                    require(Path(pack.question_path).read_bytes() == question_bytes, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
                    record_prepared_read(Path(pack.question_path), question_bytes)
                    for revision, raw in zip(pack.images, images, strict=True):
                        require(self.transport.store.current_image(day, slot, revision.family) == revision,
                                "REVIEW_BINDING_STALE")
                        require(self.transport.store.image_bytes(revision) == raw, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
                prepared_fence = PreparedReadFence(tuple(reads.items()))
            prepared_fence.check()
            require(self._clock().astimezone(_IST).date() == day, "REVIEW_BINDING_STALE")
            require(request_identity is None or request_identity == pack.question_pack_identity,
                    "REVIEW_REQUEST_MISMATCH")

        def guarded_recheck(snapshot):
            recheck()
            require(snapshot.control["current_manifest"]["sha256"] == expected_state["expected_committed_run_manifest"]
                    and snapshot.manifest["run_id"] == expected_state["expected_run_identity"],
                    "REVIEW_BINDING_STALE")

        # Replay preserves the original time and record bytes. Any reuse in an
        # older acceptance is a conflict, not a latest-file/candidate fallback.
        for commit in history:
            receipt = commit.receipts[0]
            if receipt.body["answer"]["answer_identity"] == answer.answer_pack_identity:
                require(commit is previous
                        and receipt.body["answer"]["pdf_sha256"] == answer.answer_sha256
                        and receipt.binding.value["question_pack_identity"] == pack.question_pack_identity,
                        "REVIEW_ANSWER_IDENTITY_CONFLICT")
                recheck()
                with self.intake_store.publication_commit_guard(publication_guard, guarded_recheck):
                    prepared_fence.check()
                return previous
        if previous is not None:
            require(previous.receipts[0].binding.value["question_pack_identity"] != pack.question_pack_identity,
                    "REVIEW_PREDECESSOR_INVALID")
        accepted_at = self._now()
        records = tuple(build_context_record(
            trading_date=day, slot=slot, family=item.family,
            revision=max((old.revision for old in self._records(
                trading_date=day, slot=slot, family=item.family)), default=0) + 1,
            question_pack_identity=pack.question_pack_identity,
            answer_pack_identity=answer.answer_pack_identity,
            captured_at=answer.captured_at, imported_at=accepted_at,
            panels=item.panels, wti_brent_alignment=item.wti_brent_alignment,
            natural_gas_alignment=item.natural_gas_alignment,
        ) for item in answer.families)
        answer_path = "answer-pdfs/" + answer.answer_sha256 + ".pdf"
        artifacts = {answer_path: captured.pdf_bytes}
        charts, structured = [], []
        role = "MCX_SUPPORTING_CONTEXT"
        for image, raw in zip(pack.images, images, strict=True):
            relative = "chart-images/" + image.image_sha256
            artifacts[relative] = raw
            charts.append(dict(role=role, subject_identity=image.family.value,
                reference_market=None, reference_symbol=None,
                timeframe_or_panel_identity=image.family.value,
                revision_identity=image.image_sha256, sha256=image.image_sha256,
                retained_relative_path=relative))
        for record in records:
            raw = canonical(_primitive(record))
            checksum = sha256(raw).hexdigest()
            relative = "structured-evidence/" + checksum + ".json"
            artifacts[relative] = raw
            structured.append(dict(role=role, subject_identity=record.family.value,
                timeframe_or_family_identity=record.family.value,
                schema=MCX_CONTEXT_CONTRACT_ID, version=MCX_CONTEXT_CONTRACT_VERSION,
                sha256=checksum, retained_relative_path=relative))
        receipt = ReviewAcceptanceReceipt.create(dict(
            scope=role, binding=dict(trading_date=day.isoformat(), slot=slot.value,
                context_cycle_identity=pack.question_pack_identity,
                request_identity=pack.question_pack_identity,
                request_timestamp=timestamp(pack.created_at),
                question_pack_identity=pack.question_pack_identity,
                question_pack_sha256=pack.question_pdf_sha256, families=["METALS", "ENERGY"]),
            contracts=[dict(role=role, question_contract_identity=pack.question_schema,
                question_contract_version="1.0", answer_contract_identity=pack.answer_schema,
                answer_contract_version="1.0", structured_evidence_schema=MCX_CONTEXT_CONTRACT_ID,
                structured_evidence_version=MCX_CONTEXT_CONTRACT_VERSION)],
            chart_revisions=charts, answer=dict(answer_identity=answer.answer_pack_identity,
                pdf_sha256=answer.answer_sha256, byte_length=len(captured.pdf_bytes),
                retained_relative_path=answer_path), structured_evidence=structured,
            accepted_at=timestamp(accepted_at),
            predecessor_receipt_id=None if previous is None else previous.receipts[0].receipt_id,
        ))
        result = self.intake_store.publish_acceptance(
            (receipt,), artifacts, request_publication_identity=pack.question_pack_identity,
            expected_predecessor=None if previous is None else previous.identity,
            committed_at=timestamp(accepted_at), recheck=recheck,
            publication_guard=publication_guard, guarded_recheck=guarded_recheck,
        )
        self._errors.pop(slot, None)
        return result

    def governed_trading_date(self) -> tuple[date, bool]:
        now = self._now(); day = now.astimezone(_IST).date()
        return day, self.calendar.is_trading_date("MCX", day)

    def stage_image(
        self, *, slot: McxContextSlot, family: McxContextFamily,
        content_type: str, payload: bytes,
    ) -> McxContextStagedImage:
        require(self.publication_source is None or _INTAKE_MUTATION.get() is self,
                "REVIEW_PRECONDITION_INVALID")
        day, required = self.governed_trading_date()
        if not required: raise ValueError("MCX_CONTEXT_NON_TRADING_DATE")
        result = self.transport.stage_image(
            trading_date=day, slot=slot, family=family,
            content_type=content_type, payload=payload,
        )
        self._errors.pop(slot, None); return result

    def remove_image(
        self, *, slot: McxContextSlot, family: McxContextFamily,
    ) -> None:
        require(self.publication_source is None or _INTAKE_MUTATION.get() is self,
                "REVIEW_PRECONDITION_INVALID")
        day, required = self.governed_trading_date()
        if not required: raise ValueError("MCX_CONTEXT_NON_TRADING_DATE")
        self.transport.remove_image(trading_date=day, slot=slot, family=family)
        self._errors.pop(slot, None)

    def current_image(
        self, *, slot: McxContextSlot, family: McxContextFamily,
        image_sha256: str,
    ) -> tuple[McxContextStagedImage, bytes]:
        day, required = self.governed_trading_date()
        if not required: raise ValueError("MCX_CONTEXT_NON_TRADING_DATE")
        return self.transport.current_image_payload(
            trading_date=day, slot=slot, family=family,
            image_sha256=image_sha256,
        )

    def create_question_pack(self, slot: McxContextSlot) -> McxContextQuestionPack:
        require(self.publication_source is None, "REVIEW_PRECONDITION_INVALID")
        day, required = self.governed_trading_date()
        if not required: raise ValueError("MCX_CONTEXT_NON_TRADING_DATE")
        try: result = self.transport.generate(day, slot)
        except (PdfReviewTransportError, ValueError) as error:
            self._errors[slot] = self._failure_status(error); raise
        self._errors.pop(slot, None); return result

    def upload_answer(self, slot: McxContextSlot) -> tuple[McxSupportingContextRecord, ...]:
        require(self.publication_source is None, "REVIEW_PRECONDITION_INVALID")
        day, required = self.governed_trading_date()
        if not required: raise ValueError("MCX_CONTEXT_NON_TRADING_DATE")
        pack = self.transport.store.current(day, slot)
        if pack is None: raise ValueError("MCX_CONTEXT_QUESTION_PACK_REQUIRED")
        try:
            answer = self.transport.find_and_validate(pack); imported_at = self._now()
            existing = tuple(
                value for value in self.store.records(
                    trading_date=day, slot=slot
                )
                if value.question_pack_identity == pack.question_pack_identity
                and value.answer_pack_identity == answer.answer_pack_identity
            )
            if len(existing) == 2:
                self._errors.pop(slot, None)
                return existing
            records = tuple(build_context_record(
                trading_date=day, slot=slot, family=item.family,
                revision=self.store.next_revision(day, slot, item.family),
                question_pack_identity=pack.question_pack_identity,
                answer_pack_identity=answer.answer_pack_identity,
                captured_at=answer.captured_at, imported_at=imported_at,
                panels=item.panels, wti_brent_alignment=item.wti_brent_alignment,
                natural_gas_alignment=item.natural_gas_alignment,
            ) for item in answer.families)
            for value in records: self.store.retain(value)
        except (PdfReviewTransportError, ValueError) as error:
            self._errors[slot] = self._failure_status(error); raise
        self._errors.pop(slot, None); return records

    def snapshot(self) -> McxSupportingContextSnapshot:
        day, required = self.governed_trading_date(); slots = []
        for slot in McxContextSlot:
            families = []
            read_error = None
            try:
                slot_records = self._records(trading_date=day, slot=slot)
                pack = self.transport.store.current(day, slot)
                require(pack is None or (pack.trading_date == day and pack.slot == slot),
                        "REVIEW_REQUEST_MISMATCH")
                staged_images = {
                    family: self.transport.store.current_image(day, slot, family)
                    for family in McxContextFamily
                }
                require(all(image is None or (image.trading_date == day and image.slot == slot
                            and image.family == family) for family, image in staged_images.items()),
                        "REVIEW_BINDING_STALE")
            except (OSError, ValueError):
                if self.intake_store is None:
                    raise
                slot_records = ()
                pack = None
                staged_images = dict.fromkeys(McxContextFamily)
                read_error = McxContextFailureStatus("REVIEW_ARTIFACT_DIGEST_MISMATCH")
            for family in McxContextFamily:
                records = tuple(item for item in slot_records if item.family == family)
                latest = max(records, key=lambda item: item.revision, default=None)
                staged_image = staged_images[family]
                staged = staged_image is not None
                families.append(McxContextFamilyStatus(
                    family,
                    ContextAvailability.NOT_REQUIRED if not required else ContextAvailability.VALID if latest else ContextAvailability.NOT_PROVIDED,
                    None if latest is None else latest.revision,
                    None if latest is None else latest.imported_at,
                    staged,
                    None if staged_image is None else staged_image.image_sha256,
                ))
                error = read_error or self._errors.get(slot)
                if (
                    required
                    and latest is None
                    and error is not None
                    and (error.family is None or error.family is family)
                ):
                    families[-1] = McxContextFamilyStatus(
                        family, ContextAvailability.INVALID_INCOMPLETE,
                        None, None, staged,
                        None if staged_image is None else staged_image.image_sha256,
                    )
            slots.append(McxContextSlotStatus(
                slot, tuple(families), pack,
                read_error or self._errors.get(slot),
            ))
            if self.publication_source is not None:
                from dataclasses import replace
                try:
                    require(read_error is None, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
                    state = self.current_intake_state(slot)
                    envelope = canonical(dict(state, mutation_identity=sha256(canonical(state)).hexdigest())).decode()
                    chain = self.intake_store.context_acceptance_history(day, slot)
                    evidence = "INVALID" if self._errors.get(slot) is not None else "MISSING"
                    if chain:
                        receipt = chain[0].receipts[0]
                        pack = slots[-1].question_pack
                        matches = pack is not None and receipt.binding.value["question_pack_identity"] == pack.question_pack_identity
                        matches = matches and all(self.transport.store.current_image(day, slot, item.family) == item
                                                  for item in pack.images)
                        evidence = "ACCEPTED" if matches else "STALE"
                    slots[-1] = replace(slots[-1], intake_precondition=envelope, evidence_state=evidence)
                except (OSError, ValueError):
                    slots[-1] = replace(slots[-1], evidence_state="INVALID")
        return McxSupportingContextSnapshot(day, required, tuple(slots))  # type: ignore[arg-type]

    def context_for(
        self, canonical_instrument: str, *, assessment_boundary: datetime,
    ) -> McxSupportingContextRecord | None:
        family = MCX_CONTEXT_INSTRUMENT_FAMILIES.get(canonical_instrument)
        if family is None or assessment_boundary.tzinfo is None:
            return None
        trading_date = assessment_boundary.astimezone(_IST).date()
        try:
            governed = self.calendar.is_trading_date("MCX", trading_date)
        except ValueError:
            return None
        if not governed:
            return None
        try:
            eligible = tuple(item for item in self._records(trading_date=trading_date, family=family)
                             if item.imported_at <= assessment_boundary)
        except (OSError, ValueError):
            if self.intake_store is None:
                raise
            return None
        return max(eligible, key=lambda item: (item.imported_at, item.revision, item.record_id), default=None)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("MCX_CONTEXT_CLOCK_INVALID")
        return value

    @staticmethod
    def _failure_status(error: Exception) -> McxContextFailureStatus:
        if isinstance(error, McxContextPanelValidationError):
            failure = error.failure
            observed = failure.observed
            if len(observed) > 120:
                observed = observed[:117] + "..."
            return McxContextFailureStatus(
                failure.machine_code,
                failure.family,
                failure.panel_id,
                failure.failed_field.value,
                failure.expected,
                observed,
            )
        return McxContextFailureStatus(str(error))


__all__ = [
    "McxContextFailureStatus", "McxContextFamilyStatus",
    "McxContextSlotStatus", "McxSupportingContextSnapshot",
    "McxSupportingContextWorkflow",
]
