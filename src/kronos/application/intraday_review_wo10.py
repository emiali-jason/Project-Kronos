"""WO-BR2 current Review selection into the existing WO-10 contract.

Binding only; ADR-0019 leaves every consequence with WO-10. This module
neither invokes WO-10 nor retains evidence. Execution stays with its control.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_answer import MAX_ANSWER_BYTES, parse_answer_pack
from kronos.intraday.review_v2 import bind_imported_visual_evidence_v2, create_question_pack_v2
from kronos.intraday.wo10 import (
    Wo10ReconciliationRequest, create_wo10_reconciliation_request, market_family_for_subject,
)
from kronos.intraday.wo10_policies import (
    wo10_equity_policy_binding, wo10_index_policy_binding, wo10_mcx_policy_binding,
)
from kronos.intraday.universe import IntradayMarketFamily

ADAPTER_IDENTITY = "KRONOS-INTRADAY-CURRENT-REVIEW-WO10-ADAPTER-V1"


@dataclass(frozen=True, slots=True)
class CurrentReviewReconciliation:
    current_review_pointer: str
    candidate_count: int
    chart_ready_count: int
    answer_ready_count: int
    requests: tuple[Wo10ReconciliationRequest, ...]

    def status_document(self) -> dict[str, object]:
        return {
            "adapter_identity": ADAPTER_IDENTITY,
            "current_review_pointer": self.current_review_pointer,
            "candidate_count": self.candidate_count,
            "chart_ready_count": self.chart_ready_count,
            "answer_ready_count": self.answer_ready_count,
            "eligible_count": len(self.requests),
        }


def select_current_review(*, store, run, pointer, resolver) -> CurrentReviewReconciliation:
    """Caller serializes Review changes and validates exact currentness first."""
    results = {item.result_identity: item for item in run.results}
    requests = []
    chart_count = answer_count = 0
    policies = {
        IntradayMarketFamily.NSE_EQUITY: wo10_equity_policy_binding,
        IntradayMarketFamily.NSE_INDEX: wo10_index_policy_binding,
        IntradayMarketFamily.MCX: wo10_mcx_policy_binding,
    }
    for member in pointer.cycles:
        cycle = store.load_cycle(member.cycle_identity)
        handoff = store.load_handoff(cycle.handoff_identity)
        active = store.load_current_chart(cycle.cycle_identity)
        if active is None:
            continue
        chart = store.load_chart(active.chart_revision_identity)
        store.load_chart_bytes(chart)
        chart_count += 1
        expected = create_question_pack_v2(handoff, cycle, chart)
        try:
            pack = store.load_pack(expected.review_pack_identity)
        except ReviewError as error:
            if error.failure is ReviewFailure.ARTIFACT_UNAVAILABLE:
                continue
            raise
        if pack != expected:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        visual = store.load_visual_evidence_for_pack(pack.review_pack_identity)
        if visual is None:
            continue
        # Exact canonical per-candidate Answer retained by the import seam.
        # No scan, timestamp selection or historical Answer fallback.
        answer_path = store.root / "answer-transports" / (
            pack.review_pack_identity + "-" + visual.answer_source_sha256 + ".json"
        )
        if not answer_path.exists():
            continue
        if answer_path.is_symlink() or answer_path.stat().st_size > MAX_ANSWER_BYTES:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        payload = answer_path.read_bytes()
        if sha256(payload).hexdigest() != visual.answer_source_sha256:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        answer = parse_answer_pack(payload)
        # Reuse the governed import binding, including DOMAIN-001 publication,
        # raw visual identity, boundary, methodology and Answer integrity.
        if resolver is None or bind_imported_visual_evidence_v2(
            pack, answer, imported_at=visual.imported_at, visual_identity_resolver=resolver,
        ) != visual:
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)
        answer_count += 1
        result = results[cycle.probable_result_identity]
        family = market_family_for_subject(result.canonical_subject_identity)
        policy = policies[family]()
        sources = (
            ADAPTER_IDENTITY, pointer.integrity_identity, run.run_identity,
            run.integrity_identity, result.result_identity, result.integrity_identity,
            handoff.handoff_identity, handoff.integrity_identity,
            cycle.cycle_identity, cycle.integrity_identity,
            chart.chart_revision_identity, chart.integrity_identity, chart.payload_sha256,
            pack.review_pack_identity, pack.integrity_identity,
            answer.answer_pack_identity, answer.source_sha256,
            visual.visual_evidence_identity, visual.integrity_identity,
            policy.policy_identity, policy.policy_version, policy.publication_identity,
            policy.integrity_identity,
        )
        operation = "CURRENT-REVIEW-WO10-" + sha256(
            json.dumps(sources, separators=(",", ":")).encode()
        ).hexdigest().upper()
        requests.append(create_wo10_reconciliation_request(
            run=run, results=(result,), market_family=family, policy=policy,
            requested_at=visual.imported_at, sponsor_operation_identity=operation,
            provenance=sources,
        ))
    return CurrentReviewReconciliation(
        pointer.integrity_identity, len(pointer.cycles), chart_count, answer_count, tuple(requests),
    )


def request_document(request: Wo10ReconciliationRequest) -> dict[str, object]:
    return json.loads(json.dumps(asdict(request), default=lambda value: value.isoformat()))
