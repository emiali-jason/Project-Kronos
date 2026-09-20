"""Explicit Sponsor-work seam from one governed Probables V2 run to Review."""

from __future__ import annotations

from kronos.intraday import visual_contract_v2 as visual_v2

from dataclasses import dataclass, replace, fields, is_dataclass
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from functools import wraps
from threading import BoundedSemaphore, Condition, Lock
import sys
from datetime import datetime, timezone
from hashlib import sha256
import json
from mmap import ACCESS_READ, mmap
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
    CurrentChartPointerV2,
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


class IntradayPageUnavailable(RuntimeError):
    """Bounded request preparation failed; no cached success may escape."""


_CURRENT_PAGE = ContextVar("intraday_review_page", default=None)
_PAGE_MUTATION = ContextVar("intraday_review_page_mutation", default=None)


class _CurrentPageRead:
    MAX_FILES = 4096
    MAX_BYTES = 64 * 1024 * 1024
    MAX_VALUES = 8192
    MAX_VALUE_BYTES = 64 * 1024 * 1024
    MAX_OBJECTS = 250000

    def __init__(self):
        self.payloads = {}
        self.payload_digests = {}
        self.values = {}
        self.byte_count = 0
        self.value_bytes = 0
        self.objects = set()
        self.failure = None
        self.sealed = False
        self.generation = None

    @classmethod
    def from_prepared(cls, prepared):
        scope = cls()
        scope.payloads = dict(prepared.payloads)
        scope.payload_digests = dict(prepared.payload_digests)
        scope.values = dict(prepared.values)
        scope.byte_count = prepared.byte_count
        scope.value_bytes = prepared.value_bytes
        scope.sealed = True
        scope.generation = prepared
        if (
            len(scope.payloads) > cls.MAX_FILES
            or scope.byte_count > cls.MAX_BYTES
            or len(scope.values) > cls.MAX_VALUES
            or scope.value_bytes > cls.MAX_VALUE_BYTES
            or prepared.object_count > cls.MAX_OBJECTS
        ):
            scope.failure = "INTRADAY_PAGE_CAPACITY"
        return scope

    def require(self):
        if self.failure is not None:
            raise IntradayPageUnavailable(self.failure)

    def invalidate(self):
        self.failure = "INTRADAY_PAGE_SOURCE_CHANGED"
        self.payloads.clear()
        self.values.clear()
        self.objects.clear()

    def read(self, path, loader=None):
        self.require()
        if path not in self.payloads:
            if self.sealed:
                self.failure = "INTRADAY_PAGE_PREPARATION_INCOMPLETE"
            if len(self.payloads) >= self.MAX_FILES:
                self.failure = "INTRADAY_PAGE_CAPACITY"
                self.require()
            try:
                if loader is None:
                    with path.open("rb") as handle:
                        # Avoid allocating the entire remaining budget for each
                        # small artifact. Read to EOF within the exact byte cap;
                        # metadata is never a substitute for content validation.
                        remaining = self.MAX_BYTES - self.byte_count + 1
                        chunks = []
                        while remaining:
                            chunk = handle.read(min(64 * 1024, remaining))
                            if not chunk:
                                break
                            chunks.append(chunk)
                            remaining -= len(chunk)
                        value = b"".join(chunks)
                else:
                    value = loader()
            except FileNotFoundError:
                self.payloads[path] = None
            else:
                if len(value) + self.byte_count > self.MAX_BYTES:
                    self.failure = "INTRADAY_PAGE_CAPACITY"
                    self.require()
                self.payloads[path] = value
                self.byte_count += len(value)
        value = self.payloads[path]
        if value is None:
            raise FileNotFoundError(str(path))
        return value

    def exists(self, path):
        try:
            self.read(path)
            return True
        except FileNotFoundError:
            return False

    def memo(self, key, compute):
        self.require()
        if key not in self.values:
            if len(self.values) >= self.MAX_VALUES:
                self.failure = "INTRADAY_PAGE_CAPACITY"
                self.require()
            value = compute()
            self.require()
            pending = [value]
            while pending:
                item = pending.pop()
                if id(item) in self.objects:
                    continue
                self.objects.add(id(item))
                self.value_bytes += sys.getsizeof(item)
                if (len(self.objects) > self.MAX_OBJECTS
                        or self.value_bytes > self.MAX_VALUE_BYTES):
                    self.failure = "INTRADAY_PAGE_CAPACITY"
                    self.require()
                if is_dataclass(item) and not isinstance(item, type):
                    pending.extend(getattr(item, field.name) for field in fields(item))
                elif isinstance(item, (tuple, list, set, frozenset)):
                    pending.extend(item)
                elif isinstance(item, dict):
                    pending.extend(item.keys())
                    pending.extend(item.values())
            self.values[key] = value
        return self.values[key]

    def exact_bytes_match(self):
        """Revalidate all captured content without serializing page readers."""

        self.require()
        if self.generation is not None:
            return self.generation.validator.validate()
        for path, expected in self.payload_digests.items():
            if _page_authority_path(path):
                continue
            actual = _page_file_digest(path)
            if actual != expected:
                return False
        return True

    def authority_bytes_match(self):
        """Recheck mutable authority after the established owner locks are held."""

        self.require()
        for path, expected in self.payloads.items():
            if not _page_authority_path(path):
                continue
            try:
                actual = path.read_bytes()
            except FileNotFoundError:
                actual = None
            if actual != expected:
                return False
        return True

    def close(self):
        self.payloads.clear()
        self.payload_digests.clear()
        self.values.clear()
        self.objects.clear()
        self.byte_count = self.value_bytes = 0
        self.generation = None


def _page_once(method):
    @wraps(method)
    def selected(self, *args, **kwargs):
        active = _CURRENT_PAGE.get()
        if active is None or active[0] is not self:
            return method(self, *args, **kwargs)
        return active[1].memo((method, args, tuple(kwargs.items())),
                              lambda: method(self, *args, **kwargs))
    return selected


def _prepares_page_generation(method):
    """Refresh derived page state once after the outer canonical mutation."""

    @wraps(method)
    def selected(self, *args, **kwargs):
        active = _PAGE_MUTATION.get()
        outer = active is None or active[0] is not self
        token = _PAGE_MUTATION.set((self, 1 if outer else active[1] + 1))
        try:
            return method(self, *args, **kwargs)
        finally:
            _PAGE_MUTATION.reset(token)
            if outer:
                self.prepare_page_generation()

    return selected


@dataclass(frozen=True, slots=True, weakref_slot=True)
class _PreparedPageGeneration:
    payloads: tuple[tuple[Path, bytes | None], ...]
    payload_digests: tuple[tuple[Path, tuple[int, bytes] | None], ...]
    values: tuple[tuple[object, object], ...]
    byte_count: int
    value_bytes: int
    object_count: int
    current_pointer_identity: str | None
    validator: object


def _preparation_failure(error: BaseException) -> str:
    if isinstance(error, IntradayPageUnavailable):
        return str(error)
    if isinstance(error, ReviewError):
        return error.failure.value
    return "INTRADAY_PAGE_PREPARATION_FAILED"


def _page_authority_path(path: Path) -> bool:
    return path.name.startswith("CURRENT-") or any(
        part in {
            "current",
            "current-charts",
            "current-imports",
            "current-visual-evidence",
        }
        for part in path.parts
    )


def _page_file_digest(path: Path) -> tuple[int, bytes] | None:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            if not size:
                return 0, sha256(b"").digest()
            with mmap(handle.fileno(), 0, access=ACCESS_READ) as payload:
                return size, sha256(payload).digest()
    except FileNotFoundError:
        return None


class _PageExactValidator:
    """Coalesce only overlapping requests; every wave hashes every source."""

    MAX_WORKERS = 4

    def __init__(self, payload_digests):
        self._items = tuple(
            (path, expected)
            for path, expected in payload_digests
            if not _page_authority_path(path)
        )
        self._condition = Condition()
        self._running = False
        self._last_result = False

    def validate(self):
        with self._condition:
            if self._running:
                while self._running:
                    self._condition.wait()
                return self._last_result
            self._running = True
        try:
            workers = min(self.MAX_WORKERS, len(self._items))
            if not workers:
                result = True
            else:
                chunks = tuple(self._items[index::workers] for index in range(workers))
                with ThreadPoolExecutor(
                    max_workers=workers,
                    thread_name_prefix="kronos-intraday-page-integrity",
                ) as pool:
                    result = all(pool.map(_page_digest_chunk_matches, chunks))
        finally:
            with self._condition:
                self._last_result = locals().get("result", False)
                self._running = False
                self._condition.notify_all()
        return result


def _page_digest_chunk_matches(items):
    return all(_page_file_digest(path) == expected for path, expected in items)


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
        if self.mode == "ORDERED_BATCH":
            if self.rejected_count:
                return "PARTIAL" if self.imported_count or self.already_imported_count else "REJECTED"
            if self.not_found_count:
                return "NOT_FOUND"
        return "COMPLETE"


@dataclass(frozen=True, slots=True)
class _PreparedV2Import:
    validation: IntradayReviewV2PreImportValidation
    answers: tuple[ChartAnalystAnswerPack, ...]
    evidence: tuple[ImportedVisualEvidenceV2, ...]
    already_imported: tuple[bool, ...] = ()
    rejected: tuple[IntradayReviewV2InboxMemberResult, ...] = ()


@dataclass(frozen=True)
class _CurrentCandidateRead:
    """One request's validated typed inputs for a current Review candidate."""

    cycle: ReviewCycleV2
    active_chart: CurrentChartPointerV2 | None
    retained_pack: ReviewQuestionPackV2 | None
    transport: ReviewBatchTransportV2 | None
    evidence: ImportedVisualEvidenceV2 | None


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
        self._page_slots = BoundedSemaphore(4)
        self._page_preparation_lock = Lock()
        self._page_generation_lock = Lock()
        self._page_generation = None
        self._page_generation_failure = "INTRADAY_PAGE_NOT_PREPARED"
        self._page_reconciliation_store = None
        self._chart_input = IntradayChartInputGate(review_store, probables_store, visual_identity_resolver, clock=lambda: self._clock())
        from kronos.instrument.visual_identity import uses_family_visual_authority
        self._paired = IntradayReviewV2PairedAdapter(review_store, self._transport, chart_input=self._chart_input,
            native_resolver=visual_identity_resolver if uses_family_visual_authority(visual_identity_resolver) else None)
        self._probables.bind_page_preparation(self.prepare_page_generation)
        self.prepare_page_generation()

    def bind_page_reconciliation(self, store):
        """Composition-only owner registration; it neither restores nor evaluates."""
        self._page_reconciliation_store = store
        self.prepare_page_generation()

    @contextmanager
    def _owner_page_scope(self, scope):
        """Enter the established lock order for capture or exact revalidation."""

        with ExitStack() as stack:
            stack.enter_context(self._review.page_read_scope(scope))
            stack.enter_context(self._probables.page_read_scope(scope))
            stack.enter_context(self._paired.store.page_read_scope(scope))
            stack.enter_context(self._paired.bindings.page_read_scope(scope))
            if self._page_reconciliation_store is not None:
                stack.enter_context(self._page_reconciliation_store.page_read_scope(scope))
            from kronos.application.intraday_review_ordered_batch import page_read_scope
            stack.enter_context(page_read_scope(scope))
            yield

    def prepare_page_generation(self):
        """Prepare one bounded derived generation at an explicit owner boundary."""

        with self._page_preparation_lock:
            scope = _CurrentPageRead()
            token = _CURRENT_PAGE.set((self, scope))
            generation = None
            failure = None
            try:
                with self._owner_page_scope(scope):
                    snapshot = self.snapshot()
                    self.currentness()
                    self.current_probables_run()
                    if snapshot.current_pointer_identity is not None:
                        if self._page_reconciliation_store is None:
                            self.current_reconciliation()
                        else:
                            for candidate in snapshot.candidates:
                                self._page_reconciliation_store.restore_current(
                                    candidate.cycle_identity
                                )
                    scope.require()
                    payload_digests = tuple(
                        (
                            path,
                            None
                            if payload is None
                            else (len(payload), sha256(payload).digest()),
                        )
                        for path, payload in scope.payloads.items()
                    )
                    # Typed page values and exact non-authority digests are the
                    # retained generation.  Keep raw bytes only for mutable
                    # authority records whose comparison must occur under the
                    # existing owner guards; retaining every immutable source
                    # duplicates the large current evidence in memory.
                    authority_payloads = tuple(
                        (path, payload)
                        for path, payload in scope.payloads.items()
                        if _page_authority_path(path)
                    )
                    generation = _PreparedPageGeneration(
                        payloads=authority_payloads,
                        payload_digests=payload_digests,
                        values=tuple(scope.values.items()),
                        byte_count=scope.byte_count,
                        value_bytes=scope.value_bytes,
                        object_count=len(scope.objects),
                        current_pointer_identity=snapshot.current_pointer_identity,
                        validator=_PageExactValidator(payload_digests),
                    )
            except (IntradayPageUnavailable, ReviewError, OSError, ValueError) as error:
                failure = _preparation_failure(error)
            finally:
                _CURRENT_PAGE.reset(token)
                scope.close()
            with self._page_generation_lock:
                self._page_generation = generation
                self._page_generation_failure = failure
            return generation

    @contextmanager
    def page_read_scope(self):
        active = _CURRENT_PAGE.get()
        if active is not None and active[0] is self:
            yield active[1]
            return
        if not self._page_slots.acquire(blocking=False):
            raise IntradayPageUnavailable("INTRADAY_PAGE_CAPACITY")
        with self._page_generation_lock:
            prepared = self._page_generation
            failure = self._page_generation_failure
        if prepared is None:
            self._page_slots.release()
            raise IntradayPageUnavailable(
                failure or "INTRADAY_PAGE_PREPARATION_FAILED"
            )
        try:
            scope = _CurrentPageRead.from_prepared(prepared)
            token = _CURRENT_PAGE.set((self, scope))
            matched = False
            try:
                matched = scope.exact_bytes_match()
                if matched:
                    with self._owner_page_scope(scope):
                        matched = scope.authority_bytes_match()
                        if not matched:
                            pass
                        else:
                            yield scope
                            scope.require()
                            return
            finally:
                _CURRENT_PAGE.reset(token)
                scope.close()

            # A changed byte must still traverse the owning integrity validators
            # so callers retain their precise corruption reason. Even a valid
            # successor remains fenced because GET cannot prepare it.
            scope = _CurrentPageRead()
            token = _CURRENT_PAGE.set((self, scope))
            try:
                with self._owner_page_scope(scope):
                    yield scope
                    scope.require()
                    raise IntradayPageUnavailable("INTRADAY_PAGE_SOURCE_CHANGED")
            finally:
                _CURRENT_PAGE.reset(token)
                scope.close()
        finally:
            self._page_slots.release()

    @property
    def review_store(self) -> IntradayReviewV2Store:
        return self._review

    @property
    def probables_store(self) -> ProbablesV2Store:
        return self._probables

    @_page_once
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

    @_prepares_page_generation
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

    @_page_once
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

    def _require_current_workspace(self, run_identity=None, cycle_identity=None, *, currentness=None):
        currentness = self.currentness() if currentness is None else currentness
        pointer = self._review.load_current()
        if (not currentness.is_review_current or pointer is None
            or pointer.probables_run_identity != currentness.current_probables_run_identity
            or (run_identity is not None and pointer.probables_run_identity != run_identity)
            or (cycle_identity is not None and cycle_identity not in
                {item.cycle_identity for item in pointer.cycles})):
            raise ReviewError(ReviewFailure.NOT_CURRENT)
        return pointer

    @_prepares_page_generation
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

    @_page_once
    def snapshot(self) -> IntradayReviewV2Snapshot:
        """Project persisted Phase-A facts without creating or advancing Review."""

        with self._lock, self._probables.current_generation_guard():
            currentness = self._currentness_locked()
            if not currentness.is_review_current:
                return IntradayReviewV2Snapshot(None, None, ())
            pointer = self._require_current_workspace(currentness=currentness)
            return self._loaded_snapshot(pointer)

    def _loaded_snapshot(self, pointer) -> IntradayReviewV2Snapshot:
        # Display and batch transport share the governed retained Review order.
        cycles = tuple(self._review.load_cycle(item.cycle_identity) for item in pointer.cycles)
        packs: list[ReviewQuestionPackV2] = []
        candidate_reads: list[_CurrentCandidateRead] = []
        for cycle in cycles:
            active = self._review.load_current_chart(cycle.cycle_identity)
            retained = self._load_retained_current_pack(cycle, active=active)
            individual = None
            evidence = None
            if retained is not None:
                packs.append(retained)
                individual = self._load_retained_transport((retained,))
                evidence = self._review.load_visual_evidence_for_pack(
                    retained.review_pack_identity
                )
            candidate_reads.append(
                _CurrentCandidateRead(cycle, active, retained, individual, evidence)
            )
        batch = None
        transport = None
        if packs and len(packs) == len(cycles):
            expected_batch = create_question_batch_v2(tuple(packs))
            transport = self._load_retained_transport(tuple(packs))
            if transport is not None:
                batch = self._review.load_batch(expected_batch.batch_identity)
        from kronos.application.intraday_review_ordered_batch import load
        ordered_batch = load(self, pointer, require_current=False)
        if ordered_batch is not None:
            _, transport, _ = ordered_batch
            batch = None
        return IntradayReviewV2Snapshot(
            probables_run_identity=pointer.probables_run_identity,
            current_pointer_identity=pointer.integrity_identity,
            candidates=tuple(
                self._candidate_snapshot(candidate_read)
                for candidate_read in candidate_reads
            ),
            review_batch_identity=(transport.transport_identity if ordered_batch is not None
                                   else None if batch is None else batch.batch_identity),
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
        current: _CurrentCandidateRead,
    ) -> IntradayReviewV2CandidateSnapshot:
        cycle = current.cycle
        active = current.active_chart
        retained_pack = current.retained_pack
        transport = current.transport
        evidence = current.evidence
        pack_ready = retained_pack is not None
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
        self,
        cycle: ReviewCycleV2,
        *,
        active: CurrentChartPointerV2 | None | object = ...,
    ) -> ReviewQuestionPackV2 | None:
        if cycle.canonical_subject_identity.startswith("MCX-SUBJECT-"):
            return None
        if active is ...:
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

    @_prepares_page_generation
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

    @_prepares_page_generation
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

    @_prepares_page_generation
    def import_all_expected_answers(self) -> IntradayReviewV2InboxImportResult:
        """Import exact current Answers on Sponsor request; never poll the inbox."""

        with self._lock:
            pointer = self._require_current_workspace()
            if pointer is None:
                raise ReviewError(ReviewFailure.NOT_CURRENT)
            from kronos.application.intraday_review_ordered_batch import import_expected
            ordered = import_expected(self, pointer)
            if ordered is not None:
                return ordered
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

    @_prepares_page_generation
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

    @_prepares_page_generation
    def create_all_question_transports(self) -> tuple:
        """Compile one ordered mixed-family Sponsor PDF and one Answer binding."""
        from kronos.application.intraday_review_ordered_batch import create
        return (create(self),)

    @_prepares_page_generation
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

    @_prepares_page_generation
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
        self, entries: tuple[tuple[ReviewQuestionPackV2, bytes], ...], *, export=True,
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
        if transport is not None and not export:
            question_path = self._review.root / "question-pdfs" / (transport.transport_identity + ".pdf")
        elif transport is not None:
            question_path = self._transport.export_retained(
                transport, self._review.load_transport_question_pdf(transport),
                self._review.load_transport_answer_template(transport))
        else:
            transport, question_path, template = self._transport.export(batch, ordered, internal_directory=None if export else self._review.root / "batch-components")
            self._review.retain_transport(transport, question_path.read_bytes(), template)
        answer_path = self._review.transport_answer_template_path(transport)
        return IntradayReviewV2BatchResult(
            batch=batch,
            transport=transport,
            packs=packs,
            question_path=question_path,
            answer_template_path=answer_path,
        )

    @_prepares_page_generation
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

    @_page_once
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
