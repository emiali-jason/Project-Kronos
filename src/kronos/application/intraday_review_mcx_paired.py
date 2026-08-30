"""Explicit, inert-by-default application boundary for MCX paired Review."""

from __future__ import annotations

from datetime import datetime

from kronos.instrument.active_derivative import ActiveDerivativeBindingArtifact
from kronos.instrument.visual_identity import VisualIdentityResolver
from kronos.intraday.review_mcx_paired import (
    McxPairedChartBundle, McxPairedChartRevision, McxPairedReviewPack,
    bind_native_identity, create_paired_chart_bundle, create_paired_review_pack,
    relationship_for_subject,
)
from kronos.intraday.review_mcx_paired_answer import (
    McxPairedAnswerPack, McxPairedImportedVisualEvidence,
    bind_mcx_paired_import, parse_mcx_paired_answer,
)
from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
from kronos.intraday.review_mcx_paired_transport import (
    McxPairedReviewTransport, create_paired_transport,
)
from kronos.intraday.review_v2 import ReviewCycleV2


class IntradayMcxPairedReviewApplication:
    """No polling or background invocation; every capability is caller-driven."""

    def __init__(self, *, store: IntradayMcxPairedReviewStore) -> None:
        if type(store) is not IntradayMcxPairedReviewStore:
            raise ValueError("MCX_PAIRED_REVIEW_APPLICATION_INVALID")
        self._store = store

    def construct_bundle(
        self, *, cycle: ReviewCycleV2, active_binding: ActiveDerivativeBindingArtifact,
        roll_history_identity: str, native_chart: McxPairedChartRevision,
        reference_chart: McxPairedChartRevision,
    ) -> McxPairedChartBundle:
        native = bind_native_identity(cycle, active_binding, roll_history_identity=roll_history_identity)
        bundle = create_paired_chart_bundle(
            cycle=cycle, native_binding=native, native_chart=native_chart,
            reference_chart=reference_chart,
            reference_relationship=relationship_for_subject(cycle.canonical_subject_identity),
        )
        self._store.retain_bundle(bundle)
        return bundle

    def create_review_pack(self, bundle: McxPairedChartBundle, *, created_at: datetime) -> McxPairedReviewPack:
        pack = create_paired_review_pack(bundle, created_at=created_at)
        self._store.retain_pack(pack)
        return pack

    def create_question_transport(
        self, *, pack: McxPairedReviewPack, bundle: McxPairedChartBundle,
        native_chart_payload: bytes, reference_chart_payload: bytes,
        generated_at: datetime,
    ) -> tuple[McxPairedReviewTransport, bytes, bytes]:
        result = create_paired_transport(
            pack=pack, bundle=bundle, native_chart_payload=native_chart_payload,
            reference_chart_payload=reference_chart_payload, generated_at=generated_at,
        )
        self._store.retain_transport(*result)
        return result

    def import_answer(
        self, *, payload: bytes, pack: McxPairedReviewPack,
        bundle: McxPairedChartBundle, native_chart: McxPairedChartRevision,
        reference_chart: McxPairedChartRevision,
        native_resolver: VisualIdentityResolver,
        reference_resolver: VisualIdentityResolver,
        imported_at: datetime,
    ) -> tuple[McxPairedAnswerPack, McxPairedImportedVisualEvidence]:
        answer = parse_mcx_paired_answer(payload)
        evidence = bind_mcx_paired_import(
            pack=pack, bundle=bundle, native_chart=native_chart,
            reference_chart=reference_chart, answer=answer,
            native_resolver=native_resolver, reference_resolver=reference_resolver,
            imported_at=imported_at,
        )
        self._store.retain_answer(answer, payload)
        self._store.retain_evidence(evidence)
        return answer, evidence


__all__ = ["IntradayMcxPairedReviewApplication"]
