from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timedelta
from decimal import Decimal
import json
import re

import pytest

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.nifty_relative_context import (
    NiftyRelationship,
    build_nifty_relative_context,
)
from kronos.intraday.probables_v2 import (
    SemanticEvidenceRoleV2,
    SemanticQualificationFactV2,
    _identity as _v2_identity,
)
from kronos.intraday.review import QUESTIONS
from kronos.intraday.review_answer import (
    ANSWER_CONTRACT_VERSION,
    ANSWER_PACK_IDENTITY,
    parse_answer_pack,
)
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
    create_wo10_equity_extension,
    create_wo10_evidence_snapshot,
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
    WO10_EQUITY_POLICY_CHECKSUM,
    WO10_EQUITY_POLICY_IDENTITY,
    WO10_EQUITY_POLICY_PUBLICATION_IDENTITY,
    WO10_EQUITY_POLICY_UNRESOLVED,
    WO10_EQUITY_POLICY_VERSION,
    Wo10EquityPolicy,
    Wo10PolicyRegistry,
    create_wo10_equity_policy_evidence,
    wo10_equity_policy_binding,
)

from .test_probables_v2 import _later_mapping, _run
from .test_review import _png
from .test_wo10_contracts import _policy, _resolver
from .test_wo10_facts import _payloads, _series


PROVENANCE = ("KRONOS-WO-10E-SLICE-3-TEST",)
REQUESTED_AT = datetime.fromisoformat("2026-08-30T14:00:00+05:30")
BOUNDARY = datetime.fromisoformat("2026-08-28T12:00:00+05:30")
SUBJECT = "NSE-EQ-RELIANCE"


def _answer(pack, overrides: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    selected = overrides or {}
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
        "observed_visible_subject_identity": "Visible RELIANCE",
        "proposed_direction": pack.proposed_direction,
        "global_observation_status": "OBSERVED",
        "answers": [{
            "question_id": question.question_id,
            "observation_status": "OBSERVED",
            "answer": selected.get(question.question_id, question.allowed_answers[0]),
            "visible_timeframes": list(question.timeframe_scope),
            "visible_basis": "Visible completed chart evidence.",
            "status_detail": None,
            "why_not_covered_elsewhere": None,
        } for question in QUESTIONS],
    }
    return parse_answer_pack(json.dumps(document).encode())


def _semantic_fact(
    *,
    subject: str,
    family: str,
    direction: SemanticDirection,
    phase,
    boundary: datetime,
) -> SemanticQualificationFactV2:
    values = {
        "family": family,
        "canonical_subject_identity": subject,
        "analysis_boundary": boundary,
        "phase": phase,
        "availability": (
            "UNAVAILABLE" if direction is SemanticDirection.UNAVAILABLE else "AVAILABLE"
        ),
        "direction": direction,
        "evidence_role": SemanticEvidenceRoleV2.INFORMATIONAL,
        "source_evidence_identities": (f"SOURCE-{subject}-{family}",),
        "attributes": (("policy_input", "EXACT_COMPLETED_FACT"),),
        "schema_identity": "KRONOS-INTRADAY-SEMANTIC-QUALIFICATION-FACT-V2",
        "schema_version": "2.0.0",
    }
    return SemanticQualificationFactV2(
        fact_identity=_v2_identity("INTRADAY-SEMANTIC-V2-FACT-", values),
        integrity_identity=_v2_identity(
            "INTEGRITY-INTRADAY-SEMANTIC-V2-FACT-", values
        ),
        **values,
    )


def _reference(value) -> Wo10EvidenceReference:  # type: ignore[no-untyped-def]
    identity = getattr(value, "evidence_identity", None) or value.fact_identity
    return Wo10EvidenceReference(identity, value.integrity_identity)


def _location(boundary: datetime) -> Wo10StructuralLocationFacts:
    values = {
        "canonical_subject_identity": SUBJECT,
        "market_family": IntradayMarketFamily.NSE_EQUITY,
        "observation_boundary": boundary,
        "market_session_identity": "NSE-20260828",
        "mapping_identity": "MAPPING-NSE-EQ-RELIANCE",
        "actual_contract_identity": None,
        "roll_lineage_identity": None,
        "context_evidence_identity": "WO10E-CONTEXT",
        "context_integrity_identity": "WO10E-CONTEXT-INTEGRITY",
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
    *,
    one_hour: SemanticDirection = SemanticDirection.LONG,
    fifteen: SemanticDirection = SemanticDirection.LONG,
    five: SemanticDirection = SemanticDirection.LONG,
    visual: dict[str, str] | None = None,
    missing_hour: bool = False,
    nifty_conflicting: bool = False,
):
    mapping = _later_mapping(8, 2, boundary=BOUNDARY)
    run = _run(mapping)
    result = run.results[0]
    handoff = create_review_handoff_v2(run, result, mapping)
    cycle = create_review_cycle_v2(handoff)
    chart = create_chart_revision_v2(
        cycle,
        revision_ordinal=1,
        payload=_png(71),
        media_type="image/png",
        received_at=BOUNDARY + timedelta(seconds=1),
    )
    pack = create_question_pack_v2(handoff, cycle, chart)
    imported = bind_imported_visual_evidence_v2(
        pack,
        _answer(pack, visual),
        imported_at=BOUNDARY + timedelta(seconds=2),
        visual_identity_resolver=_resolver(SUBJECT, "Visible RELIANCE", BOUNDARY),
    )
    phase = result.phase
    assert phase is not None
    daily_fact = _semantic_fact(
        subject=SUBJECT,
        family="1D_CONTEXT",
        direction=SemanticDirection.NON_DIRECTIONAL,
        phase=phase,
        boundary=BOUNDARY,
    )
    hour_fact = None if missing_hour else _semantic_fact(
        subject=SUBJECT,
        family="1H_REGIME",
        direction=one_hour,
        phase=phase,
        boundary=BOUNDARY,
    )
    fifteen_fact = _semantic_fact(
        subject=SUBJECT,
        family="15M_STRUCTURE",
        direction=fifteen,
        phase=phase,
        boundary=BOUNDARY,
    )
    five_fact = _semantic_fact(
        subject=SUBJECT,
        family="5M_PROGRESSION",
        direction=five,
        phase=phase,
        boundary=BOUNDARY,
    )
    nifty_fifteen = _semantic_fact(
        subject="NSE-INDEX-NIFTY",
        family="15M_STRUCTURE",
        direction=SemanticDirection.SHORT if nifty_conflicting else SemanticDirection.LONG,
        phase=phase,
        boundary=BOUNDARY,
    )
    nifty_hour = _semantic_fact(
        subject="NSE-INDEX-NIFTY",
        family="1H_REGIME",
        direction=SemanticDirection.SHORT if nifty_conflicting else SemanticDirection.LONG,
        phase=phase,
        boundary=BOUNDARY,
    )
    subject_candle = _payloads(
        1,
        subject=SUBJECT,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        closes=(Decimal("101"),),
        observation_boundary=BOUNDARY,
    )[0]
    nifty_candle = _payloads(
        1,
        subject="NSE-INDEX-NIFTY",
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        closes=(Decimal("105") if nifty_conflicting else Decimal("100.5"),),
        provider_source_identity="KITE-INSTRUMENT-NIFTY",
        observation_boundary=BOUNDARY,
    )[0]
    nifty_relationship = build_nifty_relative_context(
        canonical_subject_identity=SUBJECT,
        subject_exchange="NSE",
        opening_direction="LONG",
        analysis_boundary=BOUNDARY,
        subject_candle=subject_candle,
        benchmark_candle=nifty_candle,
        subject_session_open=Decimal("100"),
        benchmark_session_open=Decimal("100"),
        provenance=PROVENANCE,
    )
    rsi = build_wo10_rsi_fact(_series(
        15,
        subject=SUBJECT,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        observation_boundary=BOUNDARY,
    ))
    railway = build_wo10_sma_facts(_series(
        205,
        subject=SUBJECT,
        observation_boundary=BOUNDARY,
    ))
    volume = build_wo10_volume_fact(_series(
        21,
        subject=SUBJECT,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        volumes=tuple(100 for _ in range(20)) + (10_000,),
        observation_boundary=BOUNDARY,
    ))
    location = _location(BOUNDARY)
    common = create_wo10_common_fact_bindings_from_facts(
        one_day_structure=_reference(daily_fact),
        one_hour_structure=None if hour_fact is None else _reference(hour_fact),
        fifteen_minute_structure=_reference(fifteen_fact),
        five_minute_progression=_reference(five_fact),
        rsi=rsi,
        railway_track=railway,
        structural_location=location,
        volume_telemetry=volume,
    )
    extension = create_wo10_equity_extension(
        nifty_fifteen_minute_context=_reference(nifty_fifteen),
        nifty_one_hour_context=_reference(nifty_hour),
        nifty_relationship=_reference(nifty_relationship),
    )
    policy = wo10_equity_policy_binding()
    request = create_wo10_reconciliation_request(
        run=run,
        results=(result,),
        market_family=IntradayMarketFamily.NSE_EQUITY,
        policy=policy,
        requested_at=REQUESTED_AT,
        sponsor_operation_identity="SPONSOR-WO10E-SLICE3-TEST",
        provenance=PROVENANCE,
    )
    source = Wo10EvidenceReference("WO10E-SOURCE", "WO10E-SOURCE-INTEGRITY")
    snapshot = create_wo10_evidence_snapshot(
        run=run,
        result=result,
        cycle=cycle,
        chart=chart,
        review_pack=pack,
        imported_visual_evidence=imported,
        market_family=IntradayMarketFamily.NSE_EQUITY,
        policy=policy,
        common_facts=common,
        family_extension=extension,
        source_references=(source,),
        provenance=PROVENANCE,
    )
    loaded = create_wo10_equity_policy_evidence(
        snapshot=snapshot,
        source_semantic_evidence=mapping.semantic_evidence,
        one_day_context=daily_fact,
        one_hour_regime=hour_fact,
        fifteen_minute_structure=fifteen_fact,
        five_minute_progression=five_fact,
        rsi=rsi,
        railway_track=railway,
        structural_location=location,
        volume_telemetry=volume,
        nifty_fifteen_minute_context=nifty_fifteen,
        nifty_one_hour_context=nifty_hour,
        nifty_relationship=nifty_relationship,
        imported_visual_evidence=imported,
    )
    decision = Wo10PolicyRegistry((Wo10EquityPolicy((loaded,)),)).evaluate(
        request=request,
        evidence=snapshot,
    )
    return decision, request, snapshot, loaded


def test_policy_publication_is_exact_deterministic_and_has_no_hidden_thresholds() -> None:
    first = wo10_equity_policy_binding()
    assert first == wo10_equity_policy_binding()
    assert first.policy_identity == WO10_EQUITY_POLICY_IDENTITY
    assert first.policy_version == WO10_EQUITY_POLICY_VERSION
    assert first.publication_identity == WO10_EQUITY_POLICY_PUBLICATION_IDENTITY
    assert first.policy_checksum == WO10_EQUITY_POLICY_CHECKSUM
    assert re.fullmatch(r"[0-9a-f]{64}", first.policy_checksum)
    assert {classification for _, classification in WO10_EQUITY_POLICY_UNRESOLVED} == {
        "INFORMATIONAL_DEFERRED"
    }


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    (
        ({"missing_hour": True}, Wo10State.CONTEXT_INCOMPLETE),
        ({"fifteen": SemanticDirection.SHORT}, Wo10State.INVALIDATED),
        ({
            "five": SemanticDirection.SHORT,
            "visual": {"Q5": "OPPOSING_STRUCTURE_VISIBLE"},
        }, Wo10State.WEAKENING),
        ({"one_hour": SemanticDirection.SHORT}, Wo10State.HELD_BY_CONTRADICTION),
        ({"fifteen": SemanticDirection.NON_DIRECTIONAL}, Wo10State.WAIT_SETUP_DEVELOPMENT),
        ({"five": SemanticDirection.NON_DIRECTIONAL}, Wo10State.WAIT_IMMEDIATE_CONFIRMATION),
        ({}, Wo10State.PROMOTION_READY),
    ),
)
def test_exact_seven_state_precedence(
    kwargs, expected: Wo10State  # type: ignore[no-untyped-def]
) -> None:
    decision, *_ = _fixture(**kwargs)
    assert decision.state is expected
    assert decision.inherited_direction is SemanticDirection.LONG


def test_higher_precedence_states_win_when_multiple_conditions_are_present() -> None:
    incomplete, *_ = _fixture(
        missing_hour=True,
        fifteen=SemanticDirection.SHORT,
        five=SemanticDirection.SHORT,
        visual={"Q4": "OPPOSING", "Q5": "OPPOSING_STRUCTURE_VISIBLE"},
    )
    invalidated, *_ = _fixture(
        fifteen=SemanticDirection.SHORT,
        five=SemanticDirection.SHORT,
        visual={"Q4": "OPPOSING", "Q5": "OPPOSING_STRUCTURE_VISIBLE"},
    )
    weakening, *_ = _fixture(
        five=SemanticDirection.SHORT,
        visual={"Q4": "OPPOSING", "Q5": "OPPOSING_STRUCTURE_VISIBLE"},
    )
    assert incomplete.state is Wo10State.CONTEXT_INCOMPLETE
    assert invalidated.state is Wo10State.INVALIDATED
    assert weakening.state is Wo10State.WEAKENING


def test_equity_family_is_exact_and_index_mcx_have_no_fallback() -> None:
    registry = Wo10PolicyRegistry((Wo10EquityPolicy(()),))
    resolved = registry.resolve(wo10_equity_policy_binding())
    assert resolved.binding.supported_market_family is IntradayMarketFamily.NSE_EQUITY
    for family in (IntradayMarketFamily.NSE_INDEX, IntradayMarketFamily.MCX):
        with pytest.raises(Wo10ContractError, match="WO10_POLICY_UNKNOWN"):
            registry.resolve(_policy(family))


def test_direction_is_inherited_and_cannot_be_flipped() -> None:
    decision, _, snapshot, _ = _fixture()
    assert decision.inherited_direction is snapshot.inherited_direction is SemanticDirection.LONG
    with pytest.raises(Wo10ContractError, match="WO10_EVIDENCE_SNAPSHOT_INVALID"):
        replace(snapshot, inherited_direction=SemanticDirection.SHORT)


def test_nifty_opposition_is_informational_and_cannot_rescue_stock_failure() -> None:
    supported, *_ = _fixture(nifty_conflicting=True)
    failed, *_ = _fixture(
        nifty_conflicting=False,
        fifteen=SemanticDirection.SHORT,
        five=SemanticDirection.LONG,
    )
    assert supported.state is Wo10State.PROMOTION_READY
    assert failed.state is Wo10State.INVALIDATED


def test_nifty_context_preserves_exact_identity_boundary_and_relationship() -> None:
    _, _, snapshot, loaded = _fixture(nifty_conflicting=True)
    assert loaded.nifty_fifteen_minute_context.canonical_subject_identity == "NSE-INDEX-NIFTY"
    assert loaded.nifty_one_hour_context.canonical_subject_identity == "NSE-INDEX-NIFTY"
    assert loaded.nifty_fifteen_minute_context.analysis_boundary == snapshot.analysis_boundary
    assert loaded.nifty_one_hour_context.analysis_boundary == snapshot.analysis_boundary
    assert loaded.nifty_relationship.relationship is NiftyRelationship.CONFLICTING


def test_rsi_volume_railway_and_locations_have_no_independent_state_authority() -> None:
    decision, _, _, loaded = _fixture()
    assert loaded.rsi.condition.value == "OVERBOUGHT"
    assert loaded.volume_telemetry.volume_ratio_to_median == Decimal(100)
    assert loaded.railway_track.policy_unresolved == (
        "MATERIAL_CRISSCROSS_THRESHOLD",
        "MATERIAL_SEPARATION_THRESHOLD",
    )
    assert loaded.structural_location.policy_unresolved
    assert decision.state is Wo10State.PROMOTION_READY


def test_visual_support_alone_does_not_promote_and_native_visual_conflict_holds() -> None:
    native_forming, *_ = _fixture(fifteen=SemanticDirection.NON_DIRECTIONAL)
    conflict, *_ = _fixture(visual={"Q4": "OPPOSING"})
    assert native_forming.state is Wo10State.WAIT_SETUP_DEVELOPMENT
    assert conflict.state is Wo10State.HELD_BY_CONTRADICTION


def test_five_minute_progression_cannot_rescue_failed_primary_structure() -> None:
    decision, *_ = _fixture(
        fifteen=SemanticDirection.SHORT,
        five=SemanticDirection.LONG,
    )
    assert decision.state is Wo10State.INVALIDATED


def test_policy_contract_has_no_kr370_or_downstream_authority_fields() -> None:
    names = {
        item.name
        for item in fields(type(_fixture()[3]))
    }
    prohibited = {
        "buy", "sell", "entry", "stop", "sl", "target", "rr", "score",
        "weight", "rank", "quota", "risk", "paper", "live", "broker",
    }
    assert names.isdisjoint(prohibited)
    source = __import__("inspect").getsource(Wo10EquityPolicy)
    assert not any(token in source for token in ("BUY", "SELL", "KR_370", "KR-370"))
