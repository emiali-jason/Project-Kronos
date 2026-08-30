from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timedelta
from decimal import Decimal
import inspect
import re

import pytest

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.probables_v2 import (
    SemanticEvidenceRoleV2,
    SemanticQualificationFactV2,
    _identity as _v2_identity,
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
    create_wo10_index_extension,
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
    WO10_INDEX_POLICY_CHECKSUM,
    WO10_INDEX_POLICY_IDENTITY,
    WO10_INDEX_POLICY_PUBLICATION_IDENTITY,
    WO10_INDEX_POLICY_UNRESOLVED,
    WO10_INDEX_POLICY_VERSION,
    WO10_INDEX_SUBJECTS,
    Wo10EquityPolicy,
    Wo10IndexPolicy,
    Wo10PolicyRegistry,
    create_wo10_index_policy_evidence,
    wo10_equity_policy_binding,
    wo10_index_policy_binding,
)
from kronos.intraday.review_v2 import (
    bind_imported_visual_evidence_v2,
    create_chart_revision_v2,
    create_question_pack_v2,
    create_review_cycle_v2,
    create_review_handoff_v2,
)

from .test_probables_v2 import _opening_inputs, _run
from .test_review import _png
from .test_wo10_contracts import _policy, _resolver
from .test_wo10_equity import _answer, _reference, _semantic_fact
from .test_wo10_facts import _series


PROVENANCE = ("KRONOS-WO-10I-SLICE-4-TEST",)
REQUESTED_AT = datetime.fromisoformat("2026-08-30T14:00:00+05:30")
NIFTY = "NSE-INDEX-NIFTY"
BANKNIFTY = "NSE-INDEX-BANKNIFTY"


def _map_fact(
    *,
    subject: str,
    family: str,
    phase,
    boundary: datetime,
    relationship: str,
) -> SemanticQualificationFactV2:
    values = {
        "family": family,
        "canonical_subject_identity": subject,
        "analysis_boundary": boundary,
        "phase": phase,
        "availability": "AVAILABLE",
        "direction": SemanticDirection.NON_DIRECTIONAL,
        "evidence_role": SemanticEvidenceRoleV2.INFORMATIONAL,
        "source_evidence_identities": (f"SOURCE-{subject}-{family}",),
        "attributes": (("structural_relationship", relationship),),
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


def _location(subject: str, boundary: datetime) -> Wo10StructuralLocationFacts:
    values = {
        "canonical_subject_identity": subject,
        "market_family": IntradayMarketFamily.NSE_INDEX,
        "observation_boundary": boundary,
        "market_session_identity": "NSE-20260826",
        "mapping_identity": f"MAPPING-{subject}",
        "actual_contract_identity": None,
        "roll_lineage_identity": None,
        "context_evidence_identity": "WO10I-DAILY-CONTEXT",
        "context_integrity_identity": "WO10I-DAILY-CONTEXT-INTEGRITY",
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
    subject: str = NIFTY,
    one_hour: SemanticDirection = SemanticDirection.LONG,
    fifteen: SemanticDirection = SemanticDirection.LONG,
    five: SemanticDirection = SemanticDirection.LONG,
    visual: dict[str, str] | None = None,
    missing_hour: bool = False,
    include_weekly: bool = True,
    include_daily_map: bool = True,
    evaluate: bool = True,
):
    _, _, _, _, mapping = _opening_inputs(subject, subject_exchange="NSE")
    run = _run(mapping)
    result = run.results[0]
    boundary = result.analysis_boundary
    phase = result.phase
    assert phase is not None
    handoff = create_review_handoff_v2(run, result, mapping)
    cycle = create_review_cycle_v2(handoff)
    chart = create_chart_revision_v2(
        cycle,
        revision_ordinal=1,
        payload=_png(83),
        media_type="image/png",
        received_at=boundary + timedelta(seconds=1),
    )
    pack = create_question_pack_v2(handoff, cycle, chart)
    imported = bind_imported_visual_evidence_v2(
        pack,
        _answer(pack, visual),
        imported_at=boundary + timedelta(seconds=2),
        visual_identity_resolver=_resolver(subject, "Visible RELIANCE", boundary),
    )

    weekly = _map_fact(
        subject=subject,
        family="WEEKLY_STRUCTURAL_MAP",
        phase=phase,
        boundary=boundary,
        relationship="OPPOSING_HIGHER_ORDER_LOCATION",
    ) if include_weekly else None
    daily_map = _map_fact(
        subject=subject,
        family="DAILY_STRUCTURAL_MAP",
        phase=phase,
        boundary=boundary,
        relationship="ABOVE_DAILY_CPR",
    ) if include_daily_map else None
    daily = _semantic_fact(
        subject=subject,
        family="1D_CONTEXT",
        direction=SemanticDirection.NON_DIRECTIONAL,
        phase=phase,
        boundary=boundary,
    )
    hour = None if missing_hour else _semantic_fact(
        subject=subject,
        family="1H_REGIME",
        direction=one_hour,
        phase=phase,
        boundary=boundary,
    )
    primary = _semantic_fact(
        subject=subject,
        family="15M_STRUCTURE",
        direction=fifteen,
        phase=phase,
        boundary=boundary,
    )
    immediate = _semantic_fact(
        subject=subject,
        family="5M_PROGRESSION",
        direction=five,
        phase=phase,
        boundary=boundary,
    )
    rsi = build_wo10_rsi_fact(_series(
        15,
        subject=subject,
        family=IntradayMarketFamily.NSE_INDEX,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        observation_boundary=boundary,
    ))
    railway = build_wo10_sma_facts(_series(
        205,
        subject=subject,
        family=IntradayMarketFamily.NSE_INDEX,
        timeframe=IntradayTimeframe.ONE_HOUR,
        observation_boundary=boundary,
    ))
    volume = build_wo10_volume_fact(_series(
        21,
        subject=subject,
        family=IntradayMarketFamily.NSE_INDEX,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        volumes=tuple(100 for _ in range(20)) + (10_000,),
        observation_boundary=boundary,
    ))
    location = _location(subject, boundary)
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
    extension = create_wo10_index_extension(
        weekly_structural_map=None if weekly is None else _reference(weekly),
        daily_structural_map=(
            None if daily_map is None else _reference(daily_map)
        ),
        underlying_authority=Wo10EvidenceReference(
            result.result_identity,
            result.integrity_identity,
        ),
    )
    policy = wo10_index_policy_binding()
    request = create_wo10_reconciliation_request(
        run=run,
        results=(result,),
        market_family=IntradayMarketFamily.NSE_INDEX,
        policy=policy,
        requested_at=REQUESTED_AT,
        sponsor_operation_identity="SPONSOR-WO10I-SLICE4-TEST",
        provenance=PROVENANCE,
    )
    snapshot = create_wo10_evidence_snapshot(
        run=run,
        result=result,
        cycle=cycle,
        chart=chart,
        review_pack=pack,
        imported_visual_evidence=imported,
        market_family=IntradayMarketFamily.NSE_INDEX,
        policy=policy,
        common_facts=common,
        family_extension=extension,
        source_references=(Wo10EvidenceReference(
            "WO10I-SOURCE", "WO10I-SOURCE-INTEGRITY"
        ),),
        provenance=PROVENANCE,
    )
    loaded = create_wo10_index_policy_evidence(
        snapshot=snapshot,
        source_semantic_evidence=mapping.semantic_evidence,
        weekly_structural_map=weekly,
        daily_structural_map=daily_map,
        one_day_context=daily,
        one_hour_regime=hour,
        fifteen_minute_structure=primary,
        five_minute_progression=immediate,
        rsi=rsi,
        railway_track=railway,
        structural_location=location,
        volume_telemetry=volume,
        imported_visual_evidence=imported,
    )
    registry = Wo10PolicyRegistry((Wo10IndexPolicy((loaded,)),))
    decision = (
        registry.evaluate(request=request, evidence=snapshot)
        if evaluate else None
    )
    return decision, request, snapshot, loaded, registry


def test_policy_publication_is_exact_deterministic_and_unresolved_is_deferred() -> None:
    first = wo10_index_policy_binding()
    assert first == wo10_index_policy_binding()
    assert first.policy_identity == WO10_INDEX_POLICY_IDENTITY
    assert first.policy_version == WO10_INDEX_POLICY_VERSION
    assert first.publication_identity == WO10_INDEX_POLICY_PUBLICATION_IDENTITY
    assert first.policy_checksum == WO10_INDEX_POLICY_CHECKSUM
    assert re.fullmatch(r"[0-9a-f]{64}", first.policy_checksum)
    assert {item for _, item in WO10_INDEX_POLICY_UNRESOLVED} == {
        "INFORMATIONAL_DEFERRED"
    }


@pytest.mark.parametrize("subject", (NIFTY, BANKNIFTY))
def test_exact_governed_index_subjects_are_accepted(subject: str) -> None:
    decision, _, snapshot, _, _ = _fixture(subject=subject)
    assert decision.state is Wo10State.PROMOTION_READY
    assert decision.canonical_subject_identity == subject
    assert snapshot.canonical_subject_identity in WO10_INDEX_SUBJECTS


def test_index_family_is_exact_and_equity_mcx_have_no_fallback() -> None:
    registry = Wo10PolicyRegistry((Wo10IndexPolicy(()), Wo10EquityPolicy(())))
    assert registry.resolve(wo10_index_policy_binding()).binding.supported_market_family \
        is IntradayMarketFamily.NSE_INDEX
    assert registry.resolve(wo10_equity_policy_binding()).binding.supported_market_family \
        is IntradayMarketFamily.NSE_EQUITY
    with pytest.raises(Wo10ContractError, match="WO10_POLICY_UNKNOWN"):
        registry.resolve(_policy(IntradayMarketFamily.MCX))


def test_unknown_index_subject_is_rejected_without_fallback() -> None:
    _, request, snapshot, loaded, _ = _fixture(
        subject="NSE-INDEX-UNKNOWN",
        evaluate=False,
    )
    policy = Wo10IndexPolicy((loaded,))
    with pytest.raises(Wo10ContractError, match="WO10_INDEX_POLICY_FAMILY_INVALID"):
        policy.evaluate(request=request, evidence=snapshot)


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


def test_higher_precedence_states_win_when_conditions_overlap() -> None:
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


def test_direction_is_inherited_and_mutation_is_rejected() -> None:
    decision, _, snapshot, loaded, _ = _fixture()
    extension = snapshot.family_extension
    assert decision.inherited_direction is snapshot.inherited_direction
    assert extension.underlying_authority == Wo10EvidenceReference(
        snapshot.probable_result_identity,
        snapshot.probable_result_integrity,
    )
    with pytest.raises(Wo10ContractError, match="WO10_EVIDENCE_SNAPSHOT_INVALID"):
        replace(snapshot, inherited_direction=SemanticDirection.SHORT)
    assert not any(
        "option" in item.name.lower() or "premium" in item.name.lower()
        for item in fields(type(loaded))
    )


def test_weekly_map_is_optional_and_has_no_promotion_or_veto_authority() -> None:
    mapped, *_ = _fixture(include_weekly=True)
    absent, *_ = _fixture(include_weekly=False)
    forming, *_ = _fixture(
        include_weekly=True,
        fifteen=SemanticDirection.NON_DIRECTIONAL,
    )
    assert mapped.state is Wo10State.PROMOTION_READY
    assert absent.state is Wo10State.PROMOTION_READY
    assert forming.state is Wo10State.WAIT_SETUP_DEVELOPMENT


def test_missing_mandatory_daily_structural_map_fails_closed() -> None:
    decision, *_ = _fixture(include_daily_map=False)
    assert decision.state is Wo10State.CONTEXT_INCOMPLETE


def test_daily_map_and_visual_support_cannot_create_promotion() -> None:
    daily_only, *_ = _fixture(fifteen=SemanticDirection.NON_DIRECTIONAL)
    visual_support, *_ = _fixture(
        fifteen=SemanticDirection.NON_DIRECTIONAL,
        visual={"Q2": "SUPPORTIVE", "Q4": "SUPPORTIVE"},
    )
    assert daily_only.state is Wo10State.WAIT_SETUP_DEVELOPMENT
    assert visual_support.state is Wo10State.WAIT_SETUP_DEVELOPMENT


def test_native_visual_conflict_holds_and_five_cannot_rescue_failed_fifteen() -> None:
    conflict, *_ = _fixture(visual={"Q4": "OPPOSING"})
    failed, *_ = _fixture(
        fifteen=SemanticDirection.SHORT,
        five=SemanticDirection.LONG,
        visual={"Q2": "SUPPORTIVE", "Q4": "SUPPORTIVE"},
    )
    assert conflict.state is Wo10State.HELD_BY_CONTRADICTION
    assert failed.state is Wo10State.INVALIDATED


def test_rsi_volume_railway_and_location_have_no_independent_state_authority() -> None:
    promoted, _, _, loaded, _ = _fixture()
    invalidated, *_ = _fixture(fifteen=SemanticDirection.SHORT)
    assert loaded.rsi.value == Decimal(100)
    assert loaded.volume_telemetry.volume_ratio_to_median == Decimal(100)
    assert loaded.railway_track.policy_unresolved == (
        "MATERIAL_CRISSCROSS_THRESHOLD",
        "MATERIAL_SEPARATION_THRESHOLD",
    )
    assert loaded.structural_location.policy_unresolved
    assert promoted.state is Wo10State.PROMOTION_READY
    assert invalidated.state is Wo10State.INVALIDATED


def test_no_option_downstream_score_or_kr370_authority_exists() -> None:
    loaded = _fixture()[3]
    names = {item.name.lower() for item in fields(type(loaded))}
    prohibited = {
        "option", "premium", "strike", "expiry", "buy", "sell", "entry",
        "stop", "sl", "target", "rr", "score", "weight", "rank", "quota",
        "risk", "paper", "live", "broker",
    }
    assert names.isdisjoint(prohibited)
    source = inspect.getsource(Wo10IndexPolicy)
    assert not any(token in source for token in (
        "BUY", "SELL", "KR_370", "KR-370", "ENTRY", "TARGET", "RISK",
    ))
