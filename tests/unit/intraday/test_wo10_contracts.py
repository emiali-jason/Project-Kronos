from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timedelta
import json

import pytest

from kronos.instrument.visual_identity import (
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    VisualIdentityRelationshipStatus,
    VisualIdentityResolver,
    VisualIdentitySourceContext,
    create_visual_identity_publication,
    create_visual_identity_relationship,
)
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.native_visual_reconciliation import AnalyticalPromotionState
from kronos.intraday.probables_v2 import ProbableMemberResultV2, ProbablesRunV2
from kronos.intraday.review import QUESTIONS
from kronos.intraday.review_answer import (
    ANSWER_CONTRACT_VERSION,
    ANSWER_PACK_IDENTITY,
    parse_answer_pack,
)
from kronos.intraday.review_v2 import (
    ChartRevisionV2,
    ImportedVisualEvidenceV2,
    ReviewCycleV2,
    ReviewQuestionPackV2,
    bind_imported_visual_evidence_v2,
    create_chart_revision_v2,
    create_question_pack_v2,
    create_review_cycle_v2,
    create_review_handoff_v2,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import (
    WO10_BATCH_RESULT_IDENTITY,
    WO10_CONTRACT_VERSION,
    WO10_CURRENT_POINTER_IDENTITY,
    WO10_OPERATION_PROVENANCE_IDENTITY,
    WO10_REQUEST_IDENTITY,
    WO10_RESULT_IDENTITY,
    WO10_STATE_PRECEDENCE,
    CurrentWo10ReconciliationPointer,
    Wo10BatchResult,
    Wo10ContractError,
    Wo10OperationOutcome,
    Wo10OperationProvenance,
    Wo10OperationStage,
    Wo10ReasonCode,
    Wo10ReasonScope,
    Wo10ReconciliationRequest,
    Wo10ReconciliationResult,
    Wo10State,
    create_current_wo10_pointer,
    create_wo10_batch_result,
    create_wo10_operation_provenance,
    create_wo10_policy_binding,
    create_wo10_reconciliation_request,
    create_wo10_reconciliation_result,
    market_family_for_subject,
)
from kronos.intraday.wo10_evidence import (
    WO10_EVIDENCE_SNAPSHOT_IDENTITY,
    WO10_EVIDENCE_SNAPSHOT_VERSION,
    Wo10CommonFactBindings,
    Wo10EvidenceReference,
    Wo10EvidenceSnapshot,
    create_wo10_common_fact_bindings,
    create_wo10_equity_extension,
    create_wo10_evidence_snapshot,
    create_wo10_index_extension,
    create_wo10_mcx_extension,
)
from kronos.intraday.wo10_policies import (
    Wo10PolicyDecision,
    Wo10PolicyRegistry,
)

from .test_probables_v2 import _opening_inputs, _run
from .test_review import _png


PROVENANCE = ("KRONOS-WO-10-SLICE-1-TEST",)
REQUESTED_AT = datetime.fromisoformat("2026-08-30T10:00:00+05:30")


def _answer(pack: ReviewQuestionPackV2, observed: str):  # type: ignore[no-untyped-def]
    document = {
        "schema_identity": ANSWER_PACK_IDENTITY,
        "schema_version": ANSWER_CONTRACT_VERSION,
        "question_set_identity": pack.question_set_identity,
        "question_set_version": pack.question_set_version,
        "review_pack_identity": pack.review_pack_identity,
        "review_cycle_identity": pack.review_cycle_identity,
        "review_request_identity": pack.review_request_identity,
        "chart_revision_identity": pack.chart_revision_identity,
        "expected_canonical_subject_identity": pack.expected_canonical_subject_identity,
        "observed_visible_subject_identity": observed,
        "proposed_direction": pack.proposed_direction,
        "global_observation_status": "OBSERVED",
        "answers": [{
            "question_id": question.question_id,
            "observation_status": "OBSERVED",
            "answer": question.allowed_answers[0],
            "visible_timeframes": list(question.timeframe_scope),
            "visible_basis": "Visible completed chart evidence.",
            "status_detail": None,
            "why_not_covered_elsewhere": None,
        } for question in QUESTIONS],
    }
    return parse_answer_pack(json.dumps(document).encode())


def _resolver(
    canonical_subject_identity: str,
    observed: str,
    boundary: datetime,
) -> VisualIdentityResolver:
    relationship = create_visual_identity_relationship(
        canonical_subject_identity=canonical_subject_identity,
        observed_visible_subject_identity=observed,
        source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
        effective_from=boundary - timedelta(days=1),
        effective_through=boundary + timedelta(days=1),
        status=VisualIdentityRelationshipStatus.ACTIVE,
        source_identity="WO10-SLICE1-TEST-TRADINGVIEW",
        provenance=PROVENANCE,
        supersedes=None,
    )
    return VisualIdentityResolver(create_visual_identity_publication(
        canonical_subject_identities=(canonical_subject_identity,),
        publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
        publication_version="1.0.0",
        effective_from=boundary - timedelta(days=1),
        effective_through=boundary + timedelta(days=1),
        source_identities=("WO10-SLICE1-TEST-ADR-0018",),
        provenance=PROVENANCE,
        relationships=(relationship,),
        supersedes=None,
        schema_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    ))


def _v2_lineage(
    subject: str = "NSE-EQ-RELIANCE",
    exchange: str = "NSE",
) -> tuple[
    ProbablesRunV2,
    ProbableMemberResultV2,
    ReviewCycleV2,
    ChartRevisionV2,
    ReviewQuestionPackV2,
    ImportedVisualEvidenceV2,
]:
    *_, mapping = _opening_inputs(subject=subject, subject_exchange=exchange)
    run = _run(mapping)
    result = run.results[0]
    handoff = create_review_handoff_v2(run, result, mapping)
    cycle = create_review_cycle_v2(handoff)
    chart = create_chart_revision_v2(
        cycle,
        revision_ordinal=1,
        payload=_png(17),
        media_type="image/png",
        received_at=run.analysis_boundary + timedelta(seconds=1),
    )
    pack = create_question_pack_v2(handoff, cycle, chart)
    observed = f"Visible {subject}"
    visual = bind_imported_visual_evidence_v2(
        pack,
        _answer(pack, observed),
        imported_at=run.analysis_boundary + timedelta(seconds=2),
        visual_identity_resolver=_resolver(subject, observed, run.analysis_boundary),
    )
    return run, result, cycle, chart, pack, visual


def _policy(family: IntradayMarketFamily):  # type: ignore[no-untyped-def]
    suffix, checksum_character = {
        IntradayMarketFamily.NSE_EQUITY: ("E", "a"),
        IntradayMarketFamily.NSE_INDEX: ("I", "b"),
        IntradayMarketFamily.MCX: ("M", "c"),
    }[family]
    return create_wo10_policy_binding(
        policy_identity=f"KRONOS-INTRADAY-WO10{suffix}-POLICY-V1",
        policy_version="1.0.0",
        publication_identity=f"INTRADAY-WO10{suffix}-POLICY-PUBLICATION-TEST",
        policy_checksum=checksum_character * 64,
        supported_market_family=family,
    )


def _extension(family: IntradayMarketFamily):  # type: ignore[no-untyped-def]
    if family is IntradayMarketFamily.NSE_EQUITY:
        return create_wo10_equity_extension(
            nifty_fifteen_minute_context=None,
            nifty_one_hour_context=None,
            nifty_relationship=None,
        )
    if family is IntradayMarketFamily.NSE_INDEX:
        return create_wo10_index_extension(
            weekly_structural_map=None,
            daily_structural_map=None,
            underlying_authority=None,
        )
    return create_wo10_mcx_extension(
        actual_contract=None,
        commissioning_publication=None,
        roll_history=None,
        reference_relationship=None,
        paired_visual_evidence=None,
        session_reference_context=None,
    )


def _facts() -> Wo10CommonFactBindings:
    return create_wo10_common_fact_bindings(
        one_day_structure=None,
        one_hour_structure=None,
        fifteen_minute_structure=None,
        five_minute_progression=None,
        rsi=None,
        railway_track=None,
        structural_location=None,
        volume_telemetry=None,
    )


def _bundle(
    subject: str = "NSE-EQ-RELIANCE",
    exchange: str = "NSE",
):  # type: ignore[no-untyped-def]
    run, probable, cycle, chart, pack, visual = _v2_lineage(subject, exchange)
    family = market_family_for_subject(subject)
    policy = _policy(family)
    request = create_wo10_reconciliation_request(
        run=run,
        results=(probable,),
        market_family=family,
        policy=policy,
        requested_at=REQUESTED_AT,
        sponsor_operation_identity="SPONSOR-WO10-SLICE1-TEST",
        provenance=PROVENANCE,
    )
    source = Wo10EvidenceReference(
        evidence_identity="WO10-SLICE1-SOURCE-EVIDENCE",
        evidence_integrity="INTEGRITY-WO10-SLICE1-SOURCE-EVIDENCE",
    )
    evidence = create_wo10_evidence_snapshot(
        run=run,
        result=probable,
        cycle=cycle,
        chart=chart,
        review_pack=pack,
        imported_visual_evidence=visual,
        market_family=family,
        policy=policy,
        common_facts=_facts(),
        family_extension=_extension(family),
        source_references=(source,),
        provenance=PROVENANCE,
    )
    reason = Wo10ReasonCode(
        scope=Wo10ReasonScope.COMMON,
        code="GOVERNED_EVIDENCE_COHERENT",
        policy_identity=policy.policy_identity,
    )
    result = create_wo10_reconciliation_result(
        request=request,
        evidence=evidence,
        state=Wo10State.PROMOTION_READY,
        reasons=(reason,),
        provenance=PROVENANCE,
    )
    return run, probable, request, evidence, result


def test_seven_state_vocabulary_and_precedence_are_exact() -> None:
    expected = (
        "CONTEXT_INCOMPLETE",
        "INVALIDATED",
        "WEAKENING",
        "HELD_BY_CONTRADICTION",
        "WAIT_SETUP_DEVELOPMENT",
        "WAIT_IMMEDIATE_CONFIRMATION",
        "PROMOTION_READY",
    )
    assert tuple(item.value for item in Wo10State) == expected
    assert tuple(item.value for item in WO10_STATE_PRECEDENCE) == expected


def test_existing_governed_market_family_is_reused_and_unknown_fails_closed() -> None:
    assert market_family_for_subject("NSE-EQ-RELIANCE") is IntradayMarketFamily.NSE_EQUITY
    assert market_family_for_subject("NSE-INDEX-BANKNIFTY") is IntradayMarketFamily.NSE_INDEX
    assert market_family_for_subject("MCX-SUBJECT-GOLDM") is IntradayMarketFamily.MCX
    with pytest.raises(Wo10ContractError, match="WO10_MARKET_FAMILY_UNKNOWN"):
        market_family_for_subject("UNKNOWN-SUBJECT")
    with pytest.raises(ValueError):
        IntradayMarketFamily("UNKNOWN")


def test_request_requires_explicit_native_v2_bindings_and_is_deterministic() -> None:
    run, probable, request, _, _ = _bundle()
    duplicate = create_wo10_reconciliation_request(
        run=run,
        results=(probable,),
        market_family=request.market_family,
        policy=request.policy,
        requested_at=request.requested_at,
        sponsor_operation_identity=request.sponsor_operation_identity,
        provenance=request.provenance,
    )
    assert request == duplicate
    assert request.schema_identity == WO10_REQUEST_IDENTITY
    assert request.schema_version == WO10_CONTRACT_VERSION
    assert request.probables_run_identity == run.run_identity
    assert request.probable_bindings[0].probable_result_identity == probable.result_identity

    with pytest.raises(Wo10ContractError, match="WO10_REQUEST_INPUT_INVALID"):
        create_wo10_reconciliation_request(
            run=run,
            results=(),
            market_family=request.market_family,
            policy=request.policy,
            requested_at=request.requested_at,
            sponsor_operation_identity=request.sponsor_operation_identity,
            provenance=request.provenance,
        )


def test_direction_is_inherited_and_mutation_is_rejected() -> None:
    _, probable, request, _, result = _bundle()
    assert result.inherited_direction is probable.direction is SemanticDirection.LONG
    with pytest.raises(Wo10ContractError, match="WO10_RESULT_INVALID"):
        replace(result, inherited_direction=SemanticDirection.SHORT)
    changed = replace(
        request.probable_bindings[0],
        inherited_direction=SemanticDirection.SHORT,
    )
    with pytest.raises(Wo10ContractError, match="WO10_REQUEST_INVALID"):
        replace(request, probable_bindings=(changed,))


def test_evidence_snapshot_binds_native_v2_lineage_without_v1_wrappers() -> None:
    run, probable, _, evidence, _ = _bundle()
    assert type(run) is ProbablesRunV2
    assert type(probable) is ProbableMemberResultV2
    assert evidence.schema_identity == WO10_EVIDENCE_SNAPSHOT_IDENTITY
    assert evidence.schema_version == WO10_EVIDENCE_SNAPSHOT_VERSION
    assert evidence.probables_run_identity == run.run_identity
    assert evidence.probable_result_identity == probable.result_identity
    assert evidence.review_cycle_identity.startswith("INTRADAY-REVIEW-V2-CYCLE-")
    assert evidence.chart_revision_identity.startswith("INTRADAY-CHART-REVISION-V2-")
    assert evidence.review_pack_identity.startswith("INTRADAY-REVIEW-PACK-V2-")
    assert evidence.imported_visual_evidence_identity.startswith(
        "INTRADAY-VISUAL-EVIDENCE-V2-"
    )


def test_family_extensions_are_discriminated_and_arbitrary_dicts_rejected() -> None:
    run, probable, cycle, chart, pack, visual = _v2_lineage()
    family = IntradayMarketFamily.NSE_EQUITY
    source = Wo10EvidenceReference("SOURCE", "INTEGRITY-SOURCE")
    with pytest.raises(Wo10ContractError, match="WO10_EVIDENCE_SNAPSHOT_INPUT_INVALID"):
        create_wo10_evidence_snapshot(
            run=run,
            result=probable,
            cycle=cycle,
            chart=chart,
            review_pack=pack,
            imported_visual_evidence=visual,
            market_family=family,
            policy=_policy(family),
            common_facts=_facts(),
            family_extension=create_wo10_index_extension(
                weekly_structural_map=None,
                daily_structural_map=None,
                underlying_authority=None,
            ),
            source_references=(source,),
            provenance=PROVENANCE,
        )
    with pytest.raises(Wo10ContractError):
        replace(_extension(family), nifty_relationship={"untyped": "escape"})


def test_material_evidence_and_state_changes_change_identity() -> None:
    run, probable, request, evidence, result = _bundle()
    source = Wo10EvidenceReference("DIFFERENT-SOURCE", "INTEGRITY-DIFFERENT-SOURCE")
    *_, cycle, chart, pack, visual = _v2_lineage()
    changed_evidence = create_wo10_evidence_snapshot(
        run=run,
        result=probable,
        cycle=cycle,
        chart=chart,
        review_pack=pack,
        imported_visual_evidence=visual,
        market_family=request.market_family,
        policy=request.policy,
        common_facts=_facts(),
        family_extension=_extension(request.market_family),
        source_references=(source,),
        provenance=PROVENANCE,
    )
    assert changed_evidence.snapshot_identity != evidence.snapshot_identity
    changed_result = create_wo10_reconciliation_result(
        request=request,
        evidence=evidence,
        state=Wo10State.WAIT_IMMEDIATE_CONFIRMATION,
        reasons=(Wo10ReasonCode(
            Wo10ReasonScope.COMMON,
            "IMMEDIATE_CONFIRMATION_REQUIRED",
            request.policy.policy_identity,
        ),),
        provenance=PROVENANCE,
    )
    assert changed_result.result_identity != result.result_identity


def test_batch_is_candidate_isolated_ordered_and_population_accounted() -> None:
    _, _, request, _, result = _bundle()
    batch = create_wo10_batch_result(
        request=request,
        results=(result,),
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        provenance=PROVENANCE,
    )
    assert batch.schema_identity == WO10_BATCH_RESULT_IDENTITY
    assert batch.requested_population == batch.published_population == 1
    assert tuple(item.state for item in batch.state_counts) == WO10_STATE_PRECEDENCE
    assert sum(item.count for item in batch.state_counts) == 1
    assert batch.result_bindings[0].result_identity == result.result_identity


def test_mixed_family_batch_is_rejected() -> None:
    _, _, equity_request, _, equity_result = _bundle()
    _, _, _, _, index_result = _bundle("NSE-INDEX-BANKNIFTY")
    with pytest.raises(Wo10ContractError, match="WO10_BATCH_INPUT_INVALID"):
        create_wo10_batch_result(
            request=equity_request,
            results=(equity_result, index_result),
            completed_at=REQUESTED_AT + timedelta(minutes=1),
            provenance=PROVENANCE,
        )


def test_current_pointer_is_exact_and_has_no_latest_fallback() -> None:
    _, _, request, _, result = _bundle()
    batch = create_wo10_batch_result(
        request=request,
        results=(result,),
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        provenance=PROVENANCE,
    )
    pointer = create_current_wo10_pointer(request, batch)
    assert pointer.schema_identity == WO10_CURRENT_POINTER_IDENTITY
    assert pointer.probables_run_identity == request.probables_run_identity
    assert pointer.batch_identity == batch.batch_identity
    assert pointer.result_bindings == batch.result_bindings


def test_operation_provenance_supports_started_completed_and_failed() -> None:
    _, _, request, _, result = _bundle()
    batch = create_wo10_batch_result(
        request=request,
        results=(result,),
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        provenance=PROVENANCE,
    )
    started = create_wo10_operation_provenance(
        request=request,
        stage=Wo10OperationStage.REQUEST,
        outcome=Wo10OperationOutcome.STARTED,
        started_at=REQUESTED_AT,
        provenance=PROVENANCE,
    )
    completed = create_wo10_operation_provenance(
        request=request,
        stage=Wo10OperationStage.BATCH_PUBLICATION,
        outcome=Wo10OperationOutcome.COMPLETED,
        started_at=REQUESTED_AT,
        completed_at=REQUESTED_AT + timedelta(minutes=1),
        backend_identity="KRONOS-BACKEND-TEST",
        process_identity="PROCESS-TEST",
        results=(result,),
        batch=batch,
        provenance=PROVENANCE,
    )
    failed = create_wo10_operation_provenance(
        request=request,
        stage=Wo10OperationStage.POLICY,
        outcome=Wo10OperationOutcome.FAILED,
        started_at=REQUESTED_AT,
        failed_at=REQUESTED_AT + timedelta(seconds=1),
        failure_reason="POLICY_UNRESOLVED",
        provenance=PROVENANCE,
    )
    assert started.schema_identity == WO10_OPERATION_PROVENANCE_IDENTITY
    assert completed.batch_identity == batch.batch_identity
    assert failed.failure_reason == "POLICY_UNRESOLVED"


class _StubPolicy:
    def __init__(self, binding, *, flip: bool = False):  # type: ignore[no-untyped-def]
        self._binding = binding
        self._flip = flip

    @property
    def binding(self):  # type: ignore[no-untyped-def]
        return self._binding

    def evaluate(self, *, request, evidence):  # type: ignore[no-untyped-def]
        direction = (
            SemanticDirection.SHORT
            if self._flip
            else evidence.inherited_direction
        )
        return Wo10PolicyDecision(
            canonical_subject_identity=evidence.canonical_subject_identity,
            inherited_direction=direction,
            state=Wo10State.PROMOTION_READY,
            reasons=(Wo10ReasonCode(
                Wo10ReasonScope.COMMON,
                "GOVERNED_EVIDENCE_COHERENT",
                request.policy.policy_identity,
            ),),
        )


def test_policy_registry_has_no_default_or_cross_family_fallback() -> None:
    _, _, request, evidence, _ = _bundle()
    policy = _StubPolicy(request.policy)
    registry = Wo10PolicyRegistry((policy,))
    assert registry.resolve(request.policy) is policy
    assert registry.evaluate(request=request, evidence=evidence).state is Wo10State.PROMOTION_READY

    unknown = _policy(IntradayMarketFamily.NSE_INDEX)
    with pytest.raises(Wo10ContractError, match="WO10_POLICY_UNKNOWN"):
        registry.resolve(unknown)
    with pytest.raises(Wo10ContractError, match="WO10_POLICY_UNKNOWN"):
        Wo10PolicyRegistry(()).resolve(request.policy)


def test_policy_registry_rejects_direction_mutation() -> None:
    _, _, request, evidence, _ = _bundle()
    registry = Wo10PolicyRegistry((_StubPolicy(request.policy, flip=True),))
    with pytest.raises(Wo10ContractError, match="WO10_POLICY_DECISION_BINDING_INVALID"):
        registry.evaluate(request=request, evidence=evidence)


def test_reason_codes_are_machine_bounded_family_aware_and_non_scoring() -> None:
    policy = _policy(IntradayMarketFamily.NSE_EQUITY)
    reason = Wo10ReasonCode(
        Wo10ReasonScope.EQUITY,
        "RELATIVE_CONTEXT_UNAVAILABLE",
        policy.policy_identity,
    )
    assert reason.scope is Wo10ReasonScope.EQUITY
    with pytest.raises(Wo10ContractError, match="WO10_REASON_CODE_INVALID"):
        Wo10ReasonCode(Wo10ReasonScope.COMMON, "ENTRY_READY", policy.policy_identity)
    with pytest.raises(Wo10ContractError, match="WO10_REASON_CODE_INVALID"):
        Wo10ReasonCode(Wo10ReasonScope.COMMON, "WEIGHT_SCORE", policy.policy_identity)


def test_contracts_have_no_kr370_trade_risk_score_or_broker_fields() -> None:
    contract_types = (
        Wo10ReconciliationRequest,
        Wo10EvidenceSnapshot,
        Wo10ReconciliationResult,
        Wo10BatchResult,
        CurrentWo10ReconciliationPointer,
        Wo10OperationProvenance,
    )
    prohibited = {
        "buy_now", "sell_now", "buy_ready", "sell_ready", "entry", "stop",
        "target", "rr", "risk", "paper", "live", "broker", "score", "rank",
        "weight", "quota", "trade_construction", "execution_eligibility",
    }
    for contract in contract_types:
        names = {item.name.lower() for item in fields(contract)}
        assert not prohibited.intersection(names)


def test_historical_v1_state_family_remains_unchanged() -> None:
    assert tuple(item.value for item in AnalyticalPromotionState) == (
        "NOT_PROMOTED",
        "PROMOTED",
    )
