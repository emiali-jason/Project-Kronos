from __future__ import annotations

from dataclasses import fields, replace
from datetime import timedelta
from decimal import Decimal
import json

import pytest

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.mcx_commissioning import load_mcx_commissioning_publication
from kronos.intraday.review import QUESTIONS
from kronos.intraday.review_answer import (
    ANSWER_CONTRACT_VERSION,
    ANSWER_PACK_IDENTITY,
    parse_answer_pack,
)
from kronos.intraday.review_mcx_paired import (
    MCX_PAIRED_ARCHITECTURE_IDENTITY,
    ChartSide,
    UsdinrEvidenceBinding,
    bind_native_identity,
    create_paired_chart_bundle,
    create_paired_chart_revision,
    create_paired_review_pack,
    relationship_for_subject,
)
from kronos.intraday.review_mcx_paired_answer import (
    bind_mcx_paired_import,
    parse_mcx_paired_answer,
)
from kronos.intraday.review_mcx_paired_transport import create_paired_transport
from kronos.intraday.review_v2 import (
    bind_imported_visual_evidence_v2,
    create_chart_revision_v2,
    create_question_pack_v2,
    create_review_cycle_v2,
    create_review_handoff_v2,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import (
    Wo10ContractError,
    Wo10State,
    create_wo10_reconciliation_request,
)
from kronos.intraday.wo10_evidence import (
    Wo10EvidenceReference,
    create_wo10_common_fact_bindings_from_facts,
    create_wo10_evidence_snapshot,
    create_wo10_mcx_extension,
)
from kronos.intraday.wo10_facts import (
    WO10_FACT_VERSION,
    WO10_LOCATION_FACTS_IDENTITY,
    Wo10StructuralLocationFacts,
    _identity as _fact_identity,
    build_wo10_rsi_fact,
    build_wo10_sma_facts,
    build_wo10_volume_fact,
)
from kronos.intraday.wo10_policies import (
    WO10_MCX_POLICY_CHECKSUM,
    WO10_MCX_POLICY_IDENTITY,
    WO10_MCX_POLICY_PUBLICATION_IDENTITY,
    WO10_MCX_POLICY_UNRESOLVED,
    WO10_MCX_SUBJECTS,
    WO10_MCX_USDINR_AMENDMENT_IDENTITY,
    Wo10McxPolicy,
    Wo10McxReferenceContext,
    Wo10PolicyRegistry,
    _require_mcx_commissioned,
    create_wo10_mcx_policy_evidence,
    derive_wo10_mcx_reference_context,
    wo10_equity_policy_binding,
    wo10_index_policy_binding,
    wo10_mcx_policy_binding,
)

from instrument.test_active_derivative_selection import _resolve
from .test_probables_v2 import _opening_inputs, _run
from .test_review import _png
from .test_review_mcx_paired import _resolver
from .test_wo10_equity import _reference, _semantic_fact
from .test_wo10_facts import _series


PROVENANCE = ("KRONOS-WO-10M-SLICE-6-TEST",)
SUBJECT = "MCX-SUBJECT-GOLDM"


def _single_answer(pack, visible: str):  # type: ignore[no-untyped-def]
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
        "observed_visible_subject_identity": visible,
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


def _location(boundary, active, roll_history: str) -> Wo10StructuralLocationFacts:  # type: ignore[no-untyped-def]
    values = {
        "canonical_subject_identity": SUBJECT,
        "market_family": IntradayMarketFamily.MCX,
        "observation_boundary": boundary,
        "market_session_identity": active.domain008_session_identity,
        "mapping_identity": "MAPPING-MCX-GOLDM",
        "actual_contract_identity": active.active_binding.derivative_contract_id,
        "roll_lineage_identity": roll_history,
        "context_evidence_identity": "WO10M-CONTEXT",
        "context_integrity_identity": "WO10M-CONTEXT-INTEGRITY",
        "levels": (),
        "structural_evidence_identities": (),
        "structural_evidence_integrities": (),
        "implemented_interactions": (),
        "policy_unresolved": (
            "APPROACH_TOLERANCE",
            "FAILURE_QUALIFICATION",
            "HOLD_QUALIFICATION",
            "REJECTION_QUALIFICATION",
        ),
        "schema_identity": WO10_LOCATION_FACTS_IDENTITY,
        "schema_version": WO10_FACT_VERSION,
    }
    return Wo10StructuralLocationFacts(
        evidence_identity=_fact_identity("INTRADAY-WO10-LOCATION-", values),
        integrity_identity=_fact_identity(
            "INTEGRITY-INTRADAY-WO10-LOCATION-", values
        ),
        **values,
    )


def _fixture(
    tmp_path,
    *,
    one_hour: SemanticDirection = SemanticDirection.LONG,
    fifteen: SemanticDirection = SemanticDirection.LONG,
    five: SemanticDirection = SemanticDirection.LONG,
    native_answers: dict[str, str] | None = None,
    reference_answers: dict[str, str] | None = None,
    missing_hour: bool = False,
    include_usdinr: bool = False,
    evaluate: bool = True,
):
    *_, mapping = _opening_inputs(SUBJECT, subject_exchange="MCX")
    run = _run(mapping)
    result = run.results[0]
    boundary = result.analysis_boundary
    phase = result.phase
    assert phase is not None
    handoff = create_review_handoff_v2(run, result, mapping)
    cycle = create_review_cycle_v2(handoff)

    active = _resolve(boundary).for_subject("GOLDM").binding
    assert active is not None
    roll_history = "MCX-ROLL-HISTORY:GOLDM"
    native_binding = bind_native_identity(
        cycle, active, roll_history_identity=roll_history
    )
    relationship = relationship_for_subject(SUBJECT)
    native_visible = f"MCX:{active.provider_symbol}"
    native_payload, reference_payload = _png(41), _png(73)
    native_chart = create_paired_chart_revision(
        payload=native_payload,
        side=ChartSide.NATIVE_MCX,
        review_cycle_identity=cycle.cycle_identity,
        expected_subject_identity=SUBJECT,
        expected_visible_identity=native_visible,
        venue="MCX",
        series_kind=None,
        listed_contract_identity=None,
        observation_boundary=boundary,
        media_type="image/png",
        revision_ordinal=1,
        received_at=boundary + timedelta(seconds=1),
    )
    reference_chart = create_paired_chart_revision(
        payload=reference_payload,
        side=ChartSide.INTERNATIONAL_REFERENCE,
        review_cycle_identity=cycle.cycle_identity,
        expected_subject_identity=relationship.reference_analytical_subject_identity,
        expected_visible_identity=relationship.governed_visible_identity,
        venue=relationship.venue.value,
        series_kind=relationship.series_kind,
        listed_contract_identity=None,
        observation_boundary=boundary,
        media_type="image/png",
        revision_ordinal=1,
        received_at=boundary + timedelta(seconds=2),
    )
    usdinr = (
        UsdinrEvidenceBinding(
            evidence_identity="GOVERNED-USDINR-15M",
            timeframe="15M",
            observation_boundary=boundary,
            integrity_identity="INTEGRITY-GOVERNED-USDINR-15M",
        )
        if include_usdinr else None
    )
    bundle = create_paired_chart_bundle(
        cycle=cycle,
        native_binding=native_binding,
        native_chart=native_chart,
        reference_chart=reference_chart,
        reference_relationship=relationship,
        usdinr_evidence=usdinr,
    )
    paired_pack = create_paired_review_pack(
        bundle, created_at=boundary + timedelta(seconds=3)
    )
    _, _, template = create_paired_transport(
        pack=paired_pack,
        bundle=bundle,
        native_chart_payload=native_payload,
        reference_chart_payload=reference_payload,
        generated_at=paired_pack.created_at,
    )
    document = json.loads(template)
    document["native_observed_visible_identity"] = native_visible
    for item in document["native_answers"]:
        item["answer"] = (native_answers or {}).get(item["question_id"], item["answer"])
    for item in document["reference_answers"]:
        item["answer"] = (reference_answers or {}).get(item["question_id"], item["answer"])
    answer = parse_mcx_paired_answer(json.dumps(
        document, sort_keys=True, separators=(",", ":")
    ).encode())
    paired_visual = bind_mcx_paired_import(
        pack=paired_pack,
        bundle=bundle,
        native_chart=native_chart,
        reference_chart=reference_chart,
        answer=answer,
        native_resolver=_resolver(SUBJECT, native_visible, boundary),
        reference_resolver=_resolver(
            relationship.reference_analytical_subject_identity,
            relationship.governed_visible_identity,
            boundary,
        ),
        imported_at=boundary + timedelta(seconds=4),
    )

    # The common Slice-2 envelope preserves its already-published Review V2
    # lineage while the MCX extension binds the paired successor evidence.
    chart = create_chart_revision_v2(
        cycle,
        revision_ordinal=1,
        payload=_png(91),
        media_type="image/png",
        received_at=boundary + timedelta(seconds=5),
    )
    pack = create_question_pack_v2(handoff, cycle, chart)
    imported = bind_imported_visual_evidence_v2(
        pack,
        _single_answer(pack, native_visible),
        imported_at=boundary + timedelta(seconds=6),
        visual_identity_resolver=_resolver(SUBJECT, native_visible, boundary),
    )

    daily = _semantic_fact(
        subject=SUBJECT, family="1D_CONTEXT",
        direction=SemanticDirection.NON_DIRECTIONAL, phase=phase, boundary=boundary,
    )
    hour = None if missing_hour else _semantic_fact(
        subject=SUBJECT, family="1H_REGIME",
        direction=one_hour, phase=phase, boundary=boundary,
    )
    primary = _semantic_fact(
        subject=SUBJECT, family="15M_STRUCTURE",
        direction=fifteen, phase=phase, boundary=boundary,
    )
    immediate = _semantic_fact(
        subject=SUBJECT, family="5M_PROGRESSION",
        direction=five, phase=phase, boundary=boundary,
    )
    rsi = build_wo10_rsi_fact(_series(
        15, subject=SUBJECT, family=IntradayMarketFamily.MCX,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        observation_boundary=boundary,
    ))
    railway = build_wo10_sma_facts(_series(
        205, subject=SUBJECT, family=IntradayMarketFamily.MCX,
        timeframe=IntradayTimeframe.ONE_HOUR, observation_boundary=boundary,
    ))
    volume = build_wo10_volume_fact(_series(
        21, subject=SUBJECT, family=IntradayMarketFamily.MCX,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        volumes=tuple(100 for _ in range(20)) + (10_000,),
        observation_boundary=boundary,
    ))
    location = _location(boundary, active, roll_history)
    common = create_wo10_common_fact_bindings_from_facts(
        one_day_structure=_reference(daily),
        one_hour_structure=None if hour is None else _reference(hour),
        fifteen_minute_structure=_reference(primary),
        five_minute_progression=_reference(immediate),
        rsi=rsi,
        railway_track=railway,
        structural_location=location,
        volume_telemetry=volume,
    )
    publication = load_mcx_commissioning_publication()
    extension = create_wo10_mcx_extension(
        actual_contract=Wo10EvidenceReference(
            active.binding_identity, active.integrity_identity
        ),
        commissioning_publication=Wo10EvidenceReference(
            publication.publication_identity, publication.integrity_identity
        ),
        roll_history=Wo10EvidenceReference(
            roll_history, active.integrity_identity
        ),
        reference_relationship=Wo10EvidenceReference(
            paired_visual.reference_resolution.relationship_identity,
            paired_visual.reference_resolution.relationship_integrity_identity,
        ),
        paired_visual_evidence=Wo10EvidenceReference(
            paired_visual.visual_evidence_identity,
            paired_visual.integrity_identity,
        ),
        session_reference_context=(
            None if usdinr is None else Wo10EvidenceReference(
                usdinr.evidence_identity, usdinr.integrity_identity
            )
        ),
    )
    policy = wo10_mcx_policy_binding()
    request = create_wo10_reconciliation_request(
        run=run,
        results=(result,),
        market_family=IntradayMarketFamily.MCX,
        policy=policy,
        requested_at=boundary + timedelta(minutes=1),
        sponsor_operation_identity="SPONSOR-WO10M-SLICE6-TEST",
        provenance=PROVENANCE,
    )
    snapshot = create_wo10_evidence_snapshot(
        run=run,
        result=result,
        cycle=cycle,
        chart=chart,
        review_pack=pack,
        imported_visual_evidence=imported,
        market_family=IntradayMarketFamily.MCX,
        policy=policy,
        common_facts=common,
        family_extension=extension,
        source_references=(Wo10EvidenceReference("WO10M-SOURCE", "WO10M-SOURCE-INTEGRITY"),),
        provenance=PROVENANCE,
    )
    loaded = create_wo10_mcx_policy_evidence(
        snapshot=snapshot,
        source_semantic_evidence=mapping.semantic_evidence,
        one_day_context=daily,
        one_hour_regime=hour,
        fifteen_minute_structure=primary,
        five_minute_progression=immediate,
        rsi=rsi,
        railway_track=railway,
        structural_location=location,
        volume_telemetry=volume,
        active_derivative_binding=active,
        commissioning_publication=publication,
        paired_chart_bundle=bundle,
        paired_visual_evidence=paired_visual,
    )
    decision = None
    if evaluate:
        decision = Wo10PolicyRegistry((Wo10McxPolicy((loaded,)),)).evaluate(
            request=request, evidence=snapshot
        )
    return decision, request, snapshot, loaded


def _reload(loaded, **changes):  # type: ignore[no-untyped-def]
    names = (
        "snapshot", "source_semantic_evidence", "one_day_context",
        "one_hour_regime", "fifteen_minute_structure",
        "five_minute_progression", "rsi", "railway_track",
        "structural_location", "volume_telemetry",
        "active_derivative_binding", "commissioning_publication",
        "paired_chart_bundle", "paired_visual_evidence",
    )
    values = {name: getattr(loaded, name) for name in names}
    values.update(changes)
    return create_wo10_mcx_policy_evidence(**values)


def test_publication_is_exact_deterministic_and_binds_both_authorities() -> None:
    binding = wo10_mcx_policy_binding()
    assert binding == wo10_mcx_policy_binding()
    assert binding.policy_identity == WO10_MCX_POLICY_IDENTITY
    assert binding.publication_identity == WO10_MCX_POLICY_PUBLICATION_IDENTITY
    assert binding.policy_checksum == WO10_MCX_POLICY_CHECKSUM
    assert len(WO10_MCX_POLICY_CHECKSUM) == 64
    assert WO10_MCX_USDINR_AMENDMENT_IDENTITY.endswith("USDINR-BOUNDED-AMENDMENT-V1")
    assert {status for _, status in WO10_MCX_POLICY_UNRESOLVED} == {"INFORMATIONAL_DEFERRED"}
    assert len(WO10_MCX_SUBJECTS) == 5


@pytest.mark.parametrize(("kwargs", "expected"), (
    ({"missing_hour": True}, Wo10State.CONTEXT_INCOMPLETE),
    ({"fifteen": SemanticDirection.SHORT}, Wo10State.INVALIDATED),
    ({"five": SemanticDirection.SHORT, "native_answers": {"M04": "PRESENT"}}, Wo10State.WEAKENING),
    ({"one_hour": SemanticDirection.SHORT}, Wo10State.HELD_BY_CONTRADICTION),
    ({"fifteen": SemanticDirection.NON_DIRECTIONAL}, Wo10State.WAIT_SETUP_DEVELOPMENT),
    ({"five": SemanticDirection.NON_DIRECTIONAL}, Wo10State.WAIT_IMMEDIATE_CONFIRMATION),
    ({}, Wo10State.PROMOTION_READY),
))
def test_exact_seven_state_precedence(tmp_path, kwargs, expected) -> None:  # type: ignore[no-untyped-def]
    decision, *_ = _fixture(tmp_path, **kwargs)
    assert decision.state is expected
    assert decision.inherited_direction is SemanticDirection.LONG


def test_primary_failure_cannot_be_rescued_by_reference_or_immediate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    decision, *_ = _fixture(
        tmp_path,
        fifteen=SemanticDirection.SHORT,
        five=SemanticDirection.LONG,
        reference_answers={"R03": "BULLISH", "R04": "ADVANCING"},
    )
    assert decision.state is Wo10State.INVALIDATED


def test_reference_context_is_derived_by_kronos_without_state_authority(tmp_path) -> None:  # type: ignore[no-untyped-def]
    divergent, _, _, divergent_loaded = _fixture(
        tmp_path / "divergent",
        reference_answers={"R03": "BEARISH", "R04": "DECLINING"},
    )
    supportive, _, _, supportive_loaded = _fixture(
        tmp_path / "supportive",
        reference_answers={"R03": "BULLISH", "R04": "ADVANCING"},
    )
    assert derive_wo10_mcx_reference_context(
        divergent_loaded.paired_visual_evidence, SemanticDirection.LONG
    ) is Wo10McxReferenceContext.DIVERGENT
    assert derive_wo10_mcx_reference_context(
        supportive_loaded.paired_visual_evidence, SemanticDirection.LONG
    ) is Wo10McxReferenceContext.SUPPORTIVE
    assert divergent.state is supportive.state is Wo10State.PROMOTION_READY


def test_reference_divergence_and_usdinr_have_no_independent_state_authority(tmp_path) -> None:  # type: ignore[no-untyped-def]
    divergent, *_ = _fixture(
        tmp_path / "divergent",
        reference_answers={"R03": "BEARISH", "R04": "DECLINING"},
        include_usdinr=True,
    )
    supportive, *_ = _fixture(
        tmp_path / "supportive",
        reference_answers={"R03": "BULLISH", "R04": "ADVANCING"},
    )
    assert divergent.state is supportive.state is Wo10State.PROMOTION_READY


def test_visual_four_hour_cannot_replace_machine_one_hour(tmp_path) -> None:  # type: ignore[no-untyped-def]
    held, *_ = _fixture(
        tmp_path,
        one_hour=SemanticDirection.SHORT,
        native_answers={"M02": "BULLISH"},
    )
    assert held.state is Wo10State.HELD_BY_CONTRADICTION


def test_contract_roll_and_reference_pair_mismatches_fail_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, request, snapshot, loaded = _fixture(tmp_path, evaluate=False)
    values = {
        item.name: getattr(loaded.structural_location, item.name)
        for item in fields(type(loaded.structural_location))
        if item.name not in {"evidence_identity", "integrity_identity"}
    }
    values["actual_contract_identity"] = "MCX-DERIVATIVE-CONTRACT-WRONG"
    wrong_location = Wo10StructuralLocationFacts(
        evidence_identity=_fact_identity("INTRADAY-WO10-LOCATION-", values),
        integrity_identity=_fact_identity(
            "INTEGRITY-INTRADAY-WO10-LOCATION-", values
        ),
        **values,
    )
    changed = _reload(loaded, structural_location=wrong_location)
    decision = Wo10PolicyRegistry((Wo10McxPolicy((changed,)),)).evaluate(
        request=request, evidence=snapshot
    )
    assert decision.state is Wo10State.CONTEXT_INCOMPLETE


def test_actual_contract_is_mandatory_and_families_have_no_fallback(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _, request, snapshot, loaded = _fixture(tmp_path, evaluate=False)
    incomplete = _reload(loaded, active_derivative_binding=None)
    decision = Wo10PolicyRegistry((Wo10McxPolicy((incomplete,)),)).evaluate(
        request=request, evidence=snapshot
    )
    assert decision.state is Wo10State.CONTEXT_INCOMPLETE
    registry = Wo10PolicyRegistry((Wo10McxPolicy((loaded,)),))
    with pytest.raises(Wo10ContractError, match="WO10_POLICY_UNKNOWN"):
        registry.resolve(wo10_equity_policy_binding())
    with pytest.raises(Wo10ContractError, match="WO10_POLICY_UNKNOWN"):
        registry.resolve(wo10_index_policy_binding())


def test_extreme_rsi_and_volume_do_not_reverse_or_block_native_coherence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    decision, _, _, loaded = _fixture(tmp_path)
    assert loaded.rsi.value is not None
    assert loaded.volume_telemetry.volume_ratio_to_median == Decimal("100")
    assert decision.state is Wo10State.PROMOTION_READY
    assert decision.inherited_direction is SemanticDirection.LONG


def test_natgas_is_held_before_any_analytical_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    _fixture(tmp_path, evaluate=False)
    with pytest.raises(Wo10ContractError, match="WO10_MCX_COMMISSIONING_HELD"):
        _require_mcx_commissioned("MCX-SUBJECT-NATGAS")


def test_policy_contract_has_no_downstream_or_macro_authority() -> None:
    names = {item.name for item in fields(type(wo10_mcx_policy_binding()))}
    prohibited = {
        "score", "weight", "rank", "quota", "entry", "stop", "target",
        "risk", "paper", "live", "broker", "nifty", "dxy", "yield",
        "usdcnh", "brent",
    }
    assert not names.intersection(prohibited)
    assert MCX_PAIRED_ARCHITECTURE_IDENTITY not in {"ENTRY", "RISK", "BROKER"}
