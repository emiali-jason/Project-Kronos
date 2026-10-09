"""Fixed uncached Intraday source guards and WO09 publication coordination.

Ephemeral expectations compare evidence; they never grant analytical authority.
The WO09 mutation controller is PROCESS_LOCAL. Reads remain lock-free for notice
consumers; only final operational publication enters the ordered owner scopes.
"""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from kronos.intraday.evidence_currentness import (
    NewWorkAction, EligibilityReason, NewWorkNotEligible,
)
from kronos.intraday.wo09_readiness import build_wo09_evidence, evaluate_readiness, create_next_wo_handoff
from kronos.intraday.wo09_persistence import Wo09Store, Wo09PublicationExpectation
from kronos.intraday.wo10_futures_store import FuturesStore
from kronos.intraday.wo10_futures_contract import digest, require
from kronos.intraday.wo10_construction import validate_intake


@dataclass(frozen=True)
class PublicationExpectation:
    operation: str
    source_identity: str
    readiness: object
    generations: tuple
    wo09: Wo09PublicationExpectation
    inputs: tuple = ()


class IntradayPublicationBoundary:
    def __init__(self, *, review, probables, paired, bindings, reconciliation,
                 ordered_batch, wo09, futures, calendar, clock):
        from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
        from kronos.intraday.probables_v2_persistence import ProbablesV2Store
        from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
        from kronos.instrument.active_derivative_persistence import ActiveDerivativeBindingStore
        from kronos.intraday.visual_reconciliation_v2_persistence import VisualReconciliationStore
        from kronos.application import intraday_review_ordered_batch
        expected = (IntradayReviewV2Store, ProbablesV2Store,
                    IntradayMcxPairedReviewStore, ActiveDerivativeBindingStore,
                    VisualReconciliationStore, Wo09Store, FuturesStore)
        values = (review, probables, paired, bindings, reconciliation, wo09, futures)
        if (any(type(v) is not t for v,t in zip(values, expected, strict=True))
                or ordered_batch is not intraday_review_ordered_batch
                or calendar is None or not callable(clock)):
            raise TypeError("INTRADAY_PUBLICATION_DEPENDENCIES_REQUIRED")
        self.review, self.probables, self.paired = review, probables, paired
        self.bindings, self.reconciliation = bindings, reconciliation
        self.ordered_batch, self.wo09, self.futures = ordered_batch, wo09, futures
        self.calendar, self.clock = calendar, clock

    @contextmanager
    def _sources(self):
        # None resets page caches. No page preparation or arbitrary supplied
        # callback/assessor runs while these producer guards are held.
        with ExitStack() as stack:
            for owner in (self.review, self.probables, self.paired, self.bindings,
                          self.reconciliation, self.ordered_batch):
                stack.enter_context(owner.page_read_scope(None))
            yield

    @staticmethod
    def _deny(reason, operation):
        raise NewWorkNotEligible(reason, action=(NewWorkAction.LIFECYCLE_PRE_ENTRY
            if operation == "lifecycle" else NewWorkAction.READINESS_HANDOFF))

    def _source(self, readiness, operation):
        # Every loader retains its own corruption/storage exception. An absent
        # required pointer is not interchangeable with corrupt evidence.
        pp = self.probables.load_current()
        rp = self.review.load_current()
        if pp is None or rp is None:
            self._deny(EligibilityReason.SOURCE_LINEAGE_NOT_ESTABLISHED, operation)
        if pp.run_identity != readiness.probables_run_identity or rp.probables_run_identity != pp.run_identity:
            self._deny(EligibilityReason.SOURCE_SUPERSEDED, operation)
        run = self.probables.load_current_run()
        result = self.probables.load_result(readiness.probable_result_identity)
        if result not in run.results:
            raise ValueError("WO09_GOVERNED_SOURCE_BINDING_INVALID")
        member = next((m for m in rp.cycles if m.canonical_subject_identity == readiness.canonical_subject_identity), None)
        if member is None:
            self._deny(EligibilityReason.SOURCE_LINEAGE_NOT_ESTABLISHED, operation)
        if member.cycle_identity != readiness.review_cycle_identity or member.probable_result_identity != result.result_identity:
            self._deny(EligibilityReason.SOURCE_SUPERSEDED, operation)
        cycle = self.review.load_cycle(member.cycle_identity)
        semantic = self.probables.load_semantic(cycle.semantic_evidence_identity)
        selection = self.probables.load_selection(cycle.completed_evidence_selection_identity)
        if (result.canonical_subject_identity != readiness.canonical_subject_identity
                or result.semantic_evidence_identity != semantic.evidence_identity
                or result.completed_evidence_selection_identity != selection.selection_identity
                or semantic.integrity_identity != cycle.semantic_evidence_integrity_identity
                or selection.integrity_identity != cycle.completed_evidence_integrity_identity):
            raise ValueError("WO09_GOVERNED_SOURCE_BINDING_INVALID")
        chart_pointer = self.review.load_current_chart(cycle.cycle_identity)
        reconciliation_pointer = self.reconciliation.load_current(cycle.cycle_identity)
        if chart_pointer is None or reconciliation_pointer is None:
            self._deny(EligibilityReason.SOURCE_LINEAGE_NOT_ESTABLISHED, operation)
        if (chart_pointer.chart_revision_identity != readiness.chart_revision_identity
                or reconciliation_pointer.reconciliation_identity != readiness.wo07f_identity):
            self._deny(EligibilityReason.SOURCE_SUPERSEDED, operation)
        chart = self.review.load_chart(chart_pointer.chart_revision_identity)
        self.review.load_chart_bytes(chart)
        reconciled = self.reconciliation.load(readiness.wo07f_identity)
        if readiness.market_family == "MCX":
            visual = self.paired.load_evidence(readiness.visual_evidence_identity)
            pack = self.paired.load_pack(visual.review_pack_identity)
            answer = self.paired.load_answer(visual.answer_pack_identity)
            binding = self.bindings.load_current(canonical_subject_id=readiness.canonical_subject_identity)
            if binding is None:
                self._deny(EligibilityReason.SOURCE_LINEAGE_NOT_ESTABLISHED, operation)
            if (binding.binding_identity != readiness.exact_mcx_roll_lineage
                    or binding.active_binding.derivative_contract_id != readiness.exact_mcx_contract_identity):
                self._deny(EligibilityReason.SOURCE_SUPERSEDED, operation)
        else:
            visual = self.review.load_visual_evidence(readiness.visual_evidence_identity)
            pack = self.review.load_pack(visual.review_pack_identity)
            retained = self.review.load_visual_evidence_for_pack(pack.review_pack_identity)
            if retained != visual:
                self._deny(EligibilityReason.SOURCE_SUPERSEDED, operation)
            answer = visual.answer_source_sha256
            binding = None
        evidence = build_wo09_evidence(reconciled, semantic, selection, visual,
            exact_mcx_contract_identity=readiness.exact_mcx_contract_identity,
            exact_mcx_roll_lineage=readiness.exact_mcx_roll_lineage)
        if (reconciled.integrity_identity != readiness.wo07f_integrity
                or visual.integrity_identity != readiness.visual_evidence_integrity
                or evidence.machine_evidence_integrity != readiness.machine_evidence_integrity):
            raise ValueError("WO09_GOVERNED_SOURCE_BINDING_INVALID")
        return (digest(pp), digest(rp), digest(run), digest(result), digest(cycle),
                digest(semantic), digest(selection), digest(chart_pointer), digest(chart),
                digest(pack), digest(answer), digest(visual), digest(reconciliation_pointer),
                digest(reconciled), digest(binding))

    def _session(self, readiness, operation):
        # Reuse commissioned DOMAIN-008 interpretation, without adding a TTL or
        # making a closed NSE session a global MCX denial.
        from kronos.browser.intraday_futures_control import domain008_session
        from kronos.intraday.wo10_futures_market import require_session
        binding = None
        if readiness.market_family == "MCX":
            binding = self.bindings.load_current(canonical_subject_id=readiness.canonical_subject_identity)
        contract = None if binding is None else dict(name=binding.provider_contract_family,
            expiry=binding.contract_expiry.isoformat())
        now = self.clock()
        session = domain008_session(self.calendar, readiness.canonical_subject_identity, now, contract=contract)
        require_session(session, now, exchange=readiness.market_family)
        if session.schedule.session_id != readiness.session_identity:
            self._deny(EligibilityReason.HISTORICAL_SESSION, operation)
        return now

    def capture_readiness(self, *, record, semantic, selection, visual, created_at,
                          exact_mcx_contract_identity=None, exact_mcx_roll_lineage=None,
                          natgas_commissioning_state=None):
        kwargs = dict(exact_mcx_contract_identity=exact_mcx_contract_identity,
            exact_mcx_roll_lineage=exact_mcx_roll_lineage,
            natgas_commissioning_state=natgas_commissioning_state)
        evidence = build_wo09_evidence(record, semantic, selection, visual, **kwargs)
        readiness, _ = evaluate_readiness(record, evidence, created_at=created_at)
        with self._sources():
            generations = self._source(readiness, "readiness")
            expected = self.wo09.expectation(readiness.canonical_subject_identity)
            return PublicationExpectation("readiness", record.reconciliation_identity,
                readiness, generations, expected, (record, semantic, selection, visual, created_at,
                exact_mcx_contract_identity, exact_mcx_roll_lineage, natgas_commissioning_state))

    def _capture(self, operation, identity):
        with self._sources():
            selected = None
            if operation == "lifecycle":
                selected = self.futures.load(identity)
                selected_data = require(selected, "WO10_SELECTED_TRADE_HANDOFF_V1")
                comparison = self.futures.load(selected_data["selection"]["comparison_identity"])
                data = require(comparison, "WO10_SPONSOR_COMPARISON_V1")
                handoff = self.wo09.load_handoff(data["handoff_identity"])
            else:
                handoff = self.wo09.load_handoff(identity)
            readiness = self.wo09.load_readiness(handoff.readiness_identity)
            generations = self._source(readiness, operation)
            now = self._session(readiness, operation)
            expected = self.wo09.expectation(readiness.canonical_subject_identity)
            if operation == "futures":
                validate_intake(handoff, readiness, expected.pointer, now=now, session_identity=readiness.session_identity)
            else:
                # WO10's quote/intake freshness is not a lifecycle timing TTL.
                # Validate the retained handoff's original complete graph against
                # the current pointer; arming freshness remains in intake, while
                # later pre-entry timing retains its commissioned WO11 rules.
                p = expected.pointer
                if p is None:
                    self._deny(EligibilityReason.SOURCE_LINEAGE_NOT_ESTABLISHED, operation)
                bound = create_next_wo_handoff(readiness, created_at=handoff.created_at,
                    current_readiness_identity=p.readiness_identity, current_pointer_integrity=p.integrity_identity,
                    currentness=p.currentness, superseded_readiness_identity=p.superseded_readiness_identity,
                    first_five_of_five_at=handoff.first_five_of_five_at)
                if bound != handoff:
                    raise ValueError("WO11_HANDOFF_GRAPH_MISMATCH")
            if selected is not None:
                generations += self._selected_graph(selected)
            return PublicationExpectation(operation, identity, readiness, generations, expected)

    def _selected_graph(self, selected):
        data = require(selected, "WO10_SELECTED_TRADE_HANDOFF_V1")
        selection = self.futures.load(data["selection_identity"])
        if require(selection, "WO10_SPONSOR_SELECTION_V1") != data["selection"]:
            raise ValueError("WO11_SELECTED_FUTURE_REQUIRED")
        comparison = self.futures.load(data["selection"]["comparison_identity"])
        cd = require(comparison, "WO10_SPONSOR_COMPARISON_V1")
        if self.futures.current(cd["subject"]) != comparison:
            self._deny(EligibilityReason.SOURCE_SUPERSEDED, "lifecycle")
        values = [selected, selection, comparison]
        for key in ("plan", "snapshot", "expression"):
            item = self.futures.load(cd[key + "_identity"])
            if item.data != data[key]:
                raise ValueError("WO11_HANDOFF_GRAPH_MISMATCH")
            values.append(item)
        return tuple(digest(v) for v in values)

    def capture_futures(self, *, handoff_identity):
        return self._capture("futures", handoff_identity)

    def capture_lifecycle(self, *, handoff_identity):
        return self._capture("lifecycle", handoff_identity)

    @contextmanager
    def _final(self, expected, operation):
        if type(expected) is not PublicationExpectation or expected.operation != operation:
            raise TypeError("INTRADAY_PUBLICATION_EXPECTATION_REQUIRED")
        with self._sources():
            generations = self._source(expected.readiness, operation)
            if generations != expected.generations[:len(generations)]:
                self._deny(EligibilityReason.SOURCE_SUPERSEDED, operation)
            now = None if operation == "readiness" else self._session(expected.readiness, operation)
            with self.wo09.transaction(expected=expected.wo09) as mutation:
                if operation == "readiness":
                    yield mutation
                else:
                    with self.futures.transaction():
                        handoff = self.wo09.load_handoff(expected.source_identity) if operation == "futures" else None
                        if handoff is not None:
                            validate_intake(handoff, expected.readiness, expected.wo09.pointer,
                                now=now, session_identity=expected.readiness.session_identity)
                        else:
                            current = self.futures.load(expected.source_identity)
                            if generations + self._selected_graph(current) != expected.generations:
                                self._deny(EligibilityReason.SOURCE_SUPERSEDED, operation)
                        yield mutation

    def final_readiness(self, expected):
        return self._final(expected, "readiness")

    def final_futures(self, expected):
        return self._final(expected, "futures")

    def final_lifecycle(self, expected):
        return self._final(expected, "lifecycle")


def require_boundary(eligibility):
    if type(eligibility) is not IntradayPublicationBoundary:
        raise NewWorkNotEligible(EligibilityReason.ELIGIBILITY_AUTHORITY_UNAVAILABLE,
                                 action=NewWorkAction.LIFECYCLE_PRE_ENTRY)
    return eligibility
