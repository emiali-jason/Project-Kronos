from __future__ import annotations

from datetime import timedelta
import inspect

import pytest

from kronos.application.intraday_wo11 import IntradayWo11Application
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10_persistence import Wo10Store
from kronos.intraday.wo11 import create_wo11_handoff_reference
from kronos.intraday.wo11_persistence import Wo11Store
from kronos.intraday.wo12 import create_wo12_handoff
from kronos.intraday.wo12_k5_foundation import (
    Wo12SetupFamily,
    derive_wo12_structural_origin,
)
from kronos.intraday.wo12_v2 import (
    Wo12CriterionIdentityV2,
    create_current_wo12_pointer_v2,
    create_wo12_evidence_v2,
    create_wo12_request_v2,
    create_wo12_result_v2,
    create_wo13_eligibility_v2,
)
from kronos.intraday.wo13_adapters import (
    WO13_FAMILY_GEOMETRY_ADAPTER_IDENTITY,
    finalize_wo13_family_geometry,
)
from kronos.intraday.wo13_geometry import (
    Wo13GeometryFailure,
    Wo13GeometryRejected,
    Wo13PriceAuthority,
    Wo13StructuralRole,
    Wo13TargetCandidateKind,
    create_wo13_structural_price_fact,
    create_wo13_target_candidate,
)
from kronos.intraday.wo13_handoff import create_wo13_step31_handoff
from kronos.intraday.wo13_pullback import construct_wo13_pullback_geometry
from kronos.intraday.wo13_targets import create_wo13_target_constraint_population
from kronos.validation.kr370 import Kr370CriterionState

from .test_wo10_contracts import REQUESTED_AT
from .test_wo11 import _request as _wo11_request
from .test_wo11 import _retain_source
from .test_wo13_contracts import _criterion
from .test_wo13_pullback import (
    _evidence as _pullback_evidence,
    _mcx_handoff,
)
from .test_wo13_targets import _constraint, _pullback


def _index_handoff(tmp_path):  # type: ignore[no-untyped-def]
    wo10 = Wo10Store((tmp_path / "index-wo10").resolve())
    source, _, _ = _retain_source(wo10, subject="NSE-INDEX-NIFTY")
    wo11 = Wo11Store((tmp_path / "index-wo11").resolve())
    published = IntradayWo11Application(wo10_store=wo10, store=wo11).execute(
        _wo11_request(source)
    )
    member = published.members[0]
    handoff = create_wo12_handoff(
        publication=published.publication,
        member=member,
        wo11_handoff=create_wo11_handoff_reference(published.publication, member),
    )
    request = create_wo12_request_v2(
        handoff=handoff,
        requested_at=REQUESTED_AT + timedelta(minutes=20),
        sponsor_operation_identity="SPONSOR-WO13-INDEX-SLICE5",
        provenance=("ADR-0022",),
    )
    evidence = create_wo12_evidence_v2(
        request=request,
        criteria=tuple(
            _criterion(item, Kr370CriterionState.SATISFIED)
            for item in Wo12CriterionIdentityV2
        ),
        exact_binding_valid=True,
        governing_15m_structure_failed=False,
        authoritative_directional_conflict=False,
    )
    result = create_wo12_result_v2(
        request=request,
        evidence=evidence,
        created_at=request.requested_at,
        provenance=("ADR-0022",),
    )
    eligibility = create_wo13_eligibility_v2(result, provenance=("ADR-0022",))
    pointer = create_current_wo12_pointer_v2(request, result, eligibility)
    snapshot = wo10.load_evidence_snapshot(handoff.wo10_evidence_identity)
    setup = derive_wo12_structural_origin(
        canonical_subject_identity=handoff.canonical_subject_identity,
        market_family=handoff.market_family,
        setup_family=Wo12SetupFamily.PULLBACK_CONTINUATION,
        inherited_direction=handoff.inherited_direction,
        analysis_boundary=handoff.analysis_boundary,
        evidence=None,
    )
    return create_wo13_step31_handoff(
        current_pointer=pointer,
        request=request,
        evidence=evidence,
        result=result,
        eligibility=eligibility,
        wo10_snapshot=snapshot,
        setup_evidence=setup,
    )


def _adapt(geometry, candidates=()):  # type: ignore[no-untyped-def]
    population = create_wo13_target_constraint_population(
        setup_geometry=geometry,
        candidates=candidates,
    )
    return finalize_wo13_family_geometry(
        setup_geometry=geometry,
        candidate_population=population,
    )


def test_equity_adapter_is_stock_local_and_deterministic(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    first = _adapt(geometry, (_constraint(geometry, "105"),))
    second = _adapt(geometry, (_constraint(geometry, "105"),))
    assert first == second
    assert first.schema_identity == WO13_FAMILY_GEOMETRY_ADAPTER_IDENTITY
    assert first.market_family is IntradayMarketFamily.NSE_EQUITY
    assert first.selection.canonical_target.selected_fact.canonical_subject_identity == (
        "NSE-EQ-RELIANCE"
    )


def test_index_adapter_completes_underlying_geometry_without_option_vehicle(tmp_path) -> None:
    handoff = _index_handoff(tmp_path)
    geometry = construct_wo13_pullback_geometry(_pullback_evidence(handoff))
    result = _adapt(geometry, (_constraint(geometry, "105"),))
    canonical = result.selection.canonical_target.selected_fact
    assert result.market_family is IntradayMarketFamily.NSE_INDEX
    assert canonical.canonical_subject_identity == "NSE-INDEX-NIFTY"
    assert canonical.price_authority is Wo13PriceAuthority.NSE_INDEX_UNDERLYING
    assert not hasattr(result, "execution_vehicle")
    assert not hasattr(result, "option_contract")


def test_mcx_adapter_binds_exact_active_contract_and_roll(tmp_path) -> None:
    handoff = _mcx_handoff(tmp_path)
    geometry = construct_wo13_pullback_geometry(
        _pullback_evidence(handoff)
    )
    result = _adapt(geometry, (_constraint(geometry, "105"),))
    canonical = result.selection.canonical_target.selected_fact
    assert result.market_family is IntradayMarketFamily.MCX
    assert canonical.actual_contract_identity == handoff.actual_contract_identity
    assert canonical.roll_lineage_identity == handoff.roll_lineage_identity
    assert canonical.instrument_identity == handoff.instrument_identity


def test_equity_nifty_fact_cannot_become_target_candidate(tmp_path) -> None:
    geometry = _pullback(tmp_path)
    entry = geometry.entry_reference.selected_fact
    nifty = create_wo13_structural_price_fact(
        canonical_subject_identity="NSE-INDEX-NIFTY",
        market_family=IntradayMarketFamily.NSE_INDEX,
        timeframe=IntradayTimeframe.DAILY,
        price="25000",
        structural_role=Wo13StructuralRole.PDH,
        price_authority=Wo13PriceAuthority.NSE_INDEX_UNDERLYING,
        structure_identity="NIFTY-PDH",
        source_evidence_identity="NIFTY-PDH-EVIDENCE",
        source_evidence_integrity="INTEGRITY-NIFTY-PDH-EVIDENCE",
        analysis_boundary=entry.analysis_boundary,
        instrument_identity="NSE:NIFTY",
        market_session_identity=entry.market_session_identity,
    )
    with pytest.raises(Wo13GeometryRejected) as failure:
        create_wo13_target_candidate(
            entry_reference=entry,
            candidate=nifty,
            direction=geometry.evidence.handoff.inherited_direction,
            kind=Wo13TargetCandidateKind.STRUCTURAL_CONSTRAINT,
        )
    assert failure.value.failure is Wo13GeometryFailure.TRUST_CONTEXT_MISMATCH


def test_index_option_premium_has_no_price_authority(tmp_path) -> None:
    handoff = _index_handoff(tmp_path)
    entry = construct_wo13_pullback_geometry(
        _pullback_evidence(handoff)
    ).entry_reference.selected_fact
    with pytest.raises(Wo13GeometryRejected) as failure:
        create_wo13_structural_price_fact(
            canonical_subject_identity=entry.canonical_subject_identity,
            market_family=entry.market_family,
            timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
            price="100",
            structural_role=Wo13StructuralRole.TARGET_CONSTRAINT,
            price_authority=Wo13PriceAuthority.OPTION_PREMIUM,
            structure_identity="OPTION-PREMIUM",
            source_evidence_identity="OPTION-PREMIUM",
            source_evidence_integrity="INTEGRITY-OPTION-PREMIUM",
            analysis_boundary=entry.analysis_boundary,
            instrument_identity=entry.instrument_identity,
            market_session_identity=entry.market_session_identity,
        )
    assert failure.value.failure is Wo13GeometryFailure.SOURCE_AUTHORITY_PROHIBITED


def test_mcx_cross_contract_constraint_fails_before_adapter(tmp_path) -> None:
    handoff = _mcx_handoff(tmp_path)
    geometry = construct_wo13_pullback_geometry(
        _pullback_evidence(handoff)
    )
    entry = geometry.entry_reference.selected_fact
    foreign = create_wo13_structural_price_fact(
        canonical_subject_identity=entry.canonical_subject_identity,
        market_family=entry.market_family,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
        price="105",
        structural_role=Wo13StructuralRole.PIVOT_RESISTANCE,
        price_authority=entry.price_authority,
        structure_identity="FOREIGN-CONTRACT-TARGET",
        source_evidence_identity="FOREIGN-CONTRACT-TARGET",
        source_evidence_integrity="INTEGRITY-FOREIGN-CONTRACT-TARGET",
        analysis_boundary=entry.analysis_boundary,
        instrument_identity=entry.instrument_identity,
        actual_contract_identity="MCX-CONTRACT-FOREIGN",
        roll_lineage_identity=entry.roll_lineage_identity,
        market_session_identity=entry.market_session_identity,
    )
    with pytest.raises(Wo13GeometryRejected) as failure:
        create_wo13_target_candidate(
            entry_reference=entry,
            candidate=foreign,
            direction=handoff.inherited_direction,
            kind=Wo13TargetCandidateKind.STRUCTURAL_CONSTRAINT,
        )
    assert failure.value.failure is Wo13GeometryFailure.TRUST_CONTEXT_MISMATCH


@pytest.mark.parametrize(
    "authority",
    (
        Wo13PriceAuthority.COMEX_REFERENCE,
        Wo13PriceAuthority.NYMEX_REFERENCE,
        Wo13PriceAuthority.USDINR_REFERENCE,
        Wo13PriceAuthority.SMA_CONTEXT,
    ),
)
def test_mcx_reference_and_sma_levels_have_no_target_authority(
    tmp_path, authority
) -> None:  # type: ignore[no-untyped-def]
    handoff = _mcx_handoff(tmp_path)
    entry = construct_wo13_pullback_geometry(
        _pullback_evidence(handoff)
    ).entry_reference.selected_fact
    with pytest.raises(Wo13GeometryRejected) as failure:
        create_wo13_structural_price_fact(
            canonical_subject_identity=entry.canonical_subject_identity,
            market_family=entry.market_family,
            timeframe=IntradayTimeframe.FIFTEEN_MINUTES,
            price="105",
            structural_role=Wo13StructuralRole.TARGET_CONSTRAINT,
            price_authority=authority,
            structure_identity=f"REFERENCE:{authority.value}",
            source_evidence_identity=f"REFERENCE:{authority.value}",
            source_evidence_integrity=f"INTEGRITY:REFERENCE:{authority.value}",
            analysis_boundary=entry.analysis_boundary,
            instrument_identity=entry.instrument_identity,
            actual_contract_identity=entry.actual_contract_identity,
            roll_lineage_identity=entry.roll_lineage_identity,
            market_session_identity=entry.market_session_identity,
        )
    assert failure.value.failure is Wo13GeometryFailure.SOURCE_AUTHORITY_PROHIBITED


def test_adapter_has_no_family_specific_rr_tick_repair_or_natgas_special_case(tmp_path) -> None:
    result = _adapt(_pullback(tmp_path))
    assert result.family_specific_rr_authority is False
    assert result.tick_repair_authority is False
    import kronos.intraday.wo13_adapters as module

    source = inspect.getsource(module)
    assert "NATGAS" not in source
    assert "kronos.provider" not in source
    assert "def persist" not in source
    assert "browser" not in source.lower()
