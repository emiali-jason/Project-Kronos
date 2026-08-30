from __future__ import annotations

from dataclasses import fields, replace
from datetime import timedelta
from decimal import Decimal
import inspect

import pytest

from kronos.application.intraday_wo11 import IntradayWo11Application
from kronos.application.intraday_wo12 import (
    IntradayWo12Application,
    Wo12ApplicationError,
)
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.probables_v2 import (
    SEMANTIC_FACT_V2_IDENTITY,
    V2_CONTRACT_VERSION,
    SemanticEvidenceRoleV2,
    SemanticQualificationFactV2,
    _identity as _v2_identity,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10_persistence import Wo10Store
from kronos.intraday.wo10 import create_wo10_policy_binding
from kronos.intraday.wo11_persistence import Wo11Store
from kronos.intraday.wo12 import (
    WO12_MATERIAL_EXTENSION_THRESHOLD,
    WO12_POLICY_IDENTITY,
    WO12_POLICY_VERSION,
    Wo12ContractError,
    Wo12CriterionIdentity,
    Wo12CriterionResult,
    Wo12Result,
    Wo12Handoff,
    Wo12HardGate,
    Wo13Eligibility,
    Wo13EligibilityRecord,
    classify_wo12,
    create_wo12_evidence,
    create_wo12_handoff,
    create_wo12_request,
    create_wo12_result,
    create_wo13_eligibility,
    _identity as _wo12_identity,
)
from kronos.intraday.wo12_facts import (
    Wo12CprAcceptanceFact,
    Wo12EvidenceInputs,
    Wo12PathClearanceFact,
    Wo12PathState,
    Wo12SetupQualityState,
    adapt_k1,
    adapt_k2,
    adapt_k3,
    adapt_k4,
    adapt_k5,
    create_wo12_cpr_acceptance_fact,
    create_wo12_extension_measurement,
    create_wo12_path_clearance_fact,
    create_wo12_setup_quality_fact,
)
from kronos.intraday.wo12_persistence import (
    Wo12PersistenceError,
    Wo12Store,
)
from kronos.validation.kr370 import (
    KR370_OWNER_IDENTITY,
    KR370_PROMOTION_AUTHORITY,
    KR370_PROMOTION_CONTRACT_ID,
    KR370_STATE_FAMILY_IDENTITY,
    Kr370AnalyticalClassification,
    Kr370CriterionState,
)

from .test_wo10_contracts import REQUESTED_AT
from .test_wo11 import _request as _wo11_request
from .test_wo11 import _retain_source


def _foundation(tmp_path):  # type: ignore[no-untyped-def]
    wo10 = Wo10Store((tmp_path / "wo10").resolve())
    source, _, _ = _retain_source(wo10)
    wo11 = Wo11Store((tmp_path / "wo11").resolve())
    published = IntradayWo11Application(wo10_store=wo10, store=wo11).execute(
        _wo11_request(source)
    )
    member = published.members[0]
    reference = wo11.load_handoff(
        published.publication.publication_identity,
        member.member_identity,
    )
    handoff = create_wo12_handoff(
        publication=published.publication,
        member=member,
        wo11_handoff=reference,
    )
    request = create_wo12_request(
        handoff=handoff,
        requested_at=REQUESTED_AT + timedelta(minutes=4),
        sponsor_operation_identity="SPONSOR-WO12-CORE-TEST",
        provenance=("KRONOS-WO12-CORE-TEST",),
    )
    return wo10, wo11, handoff, request


def _rebound(handoff: Wo12Handoff, **changes) -> Wo12Handoff:  # type: ignore[no-untyped-def]
    values = {
        item.name: getattr(handoff, item.name)
        for item in fields(Wo12Handoff)
        if item.name not in {"handoff_identity", "handoff_integrity"}
    }
    values.update(changes)
    return Wo12Handoff(
        handoff_identity=_wo12_identity("INTRADAY-WO12-HANDOFF-V1-", values),
        handoff_integrity=_wo12_identity(
            "INTEGRITY-INTRADAY-WO12-HANDOFF-V1-", values
        ),
        **values,
    )


def _semantic(
    handoff: Wo12Handoff,
    direction: SemanticDirection,
    *,
    available: bool = True,
) -> SemanticQualificationFactV2:
    values = {
        "family": "15M_STRUCTURE",
        "canonical_subject_identity": handoff.canonical_subject_identity,
        "analysis_boundary": handoff.analysis_boundary,
        "phase": handoff.phase,
        "availability": "AVAILABLE" if available else "UNAVAILABLE",
        "direction": direction if available else SemanticDirection.UNAVAILABLE,
        "evidence_role": SemanticEvidenceRoleV2.MANDATORY_DIRECTIONAL,
        "source_evidence_identities": ("GOVERNED-15M-STRUCTURE",),
        "attributes": (("completion", "COMPLETED_GOVERNED_15M"),),
        "schema_identity": SEMANTIC_FACT_V2_IDENTITY,
        "schema_version": V2_CONTRACT_VERSION,
    }
    return SemanticQualificationFactV2(
        fact_identity=_v2_identity("INTRADAY-SEMANTIC-V2-FACT-", values),
        integrity_identity=_v2_identity(
            "INTEGRITY-INTRADAY-SEMANTIC-V2-FACT-", values
        ),
        **values,
    )


def _inputs(
    handoff: Wo12Handoff,
    *,
    progression: SemanticDirection | None = None,
    close: Decimal | None = None,
    path: Wo12PathState = Wo12PathState.CLEAR,
    quality: Wo12SetupQualityState = Wo12SetupQualityState.ACCEPTABLE,
    measurement: bool = True,
    structure_failed: bool = False,
    conflict: bool = False,
) -> Wo12EvidenceInputs:
    direction = progression or handoff.inherited_direction
    selected_close = close
    if selected_close is None:
        selected_close = (
            Decimal("110")
            if handoff.inherited_direction is SemanticDirection.LONG
            else Decimal("90")
        )
    cpr = create_wo12_cpr_acceptance_fact(
        handoff=handoff,
        completed_close=selected_close,
        cpr_lower=Decimal("95"),
        cpr_upper=Decimal("105"),
        completed_candle_identity="GOVERNED-15M-CANDLE-CLOSE",
        cpr_evidence_identity="CPR-GOVERNED-EVIDENCE",
        source_evidence_integrities=("INTEGRITY-CANDLE", "INTEGRITY-CPR"),
    )
    path_fact = create_wo12_path_clearance_fact(
        canonical_subject_identity=handoff.canonical_subject_identity,
        market_family=handoff.market_family,
        analysis_boundary=handoff.analysis_boundary,
        state=path,
        source_evidence_identities=("GOVERNED-15M-BARRIER-INTERACTION",),
        source_evidence_integrities=("INTEGRITY-15M-BARRIER-INTERACTION",),
        predicate_identity="EXISTING-DETERMINISTIC-STRUCTURAL-OBSTRUCTION-V1",
    )
    quality_fact = create_wo12_setup_quality_fact(
        canonical_subject_identity=handoff.canonical_subject_identity,
        market_family=handoff.market_family,
        analysis_boundary=handoff.analysis_boundary,
        state=quality,
        source_evidence_identities=(handoff.wo10_evidence_identity,),
        source_evidence_integrities=(handoff.wo10_evidence_integrity,),
        adapter_identity="WO10-NATIVE-VISUAL-SETUP-QUALITY-ADAPTER-V1",
    )
    extension = None
    if measurement:
        extension = create_wo12_extension_measurement(
            handoff=handoff,
            structural_origin_identity="GOVERNED-15M-STRUCTURAL-ORIGIN",
            structural_origin_value=Decimal("100"),
            completed_close=selected_close,
            atr_value=Decimal("5"),
            atr_period=14,
            atr_calculation_identity="GOVERNED-15M-ATR-WILDER-14",
            source_evidence_identities=("ORIGIN-EVIDENCE", "ATR-EVIDENCE"),
            source_evidence_integrities=("INTEGRITY-ORIGIN", "INTEGRITY-ATR"),
        )
    return Wo12EvidenceInputs(
        fifteen_minute_structure=_semantic(handoff, direction),
        cpr_acceptance=cpr,
        path_clearance=path_fact,
        setup_quality=quality_fact,
        extension_measurement=extension,
        governing_15m_structure_failed=structure_failed,
        authoritative_directional_conflict=conflict,
    )


def _criterion(
    identity: Wo12CriterionIdentity,
    state: Kr370CriterionState,
) -> Wo12CriterionResult:
    return Wo12CriterionResult(
        identity=identity,
        state=state,
        reason=f"{identity.name}_{state.value}",
        evidence_identities=(f"EVIDENCE-{identity.value}",),
        evidence_integrities=(f"INTEGRITY-{identity.value}",),
    )


def _criteria(satisfied: int) -> tuple[Wo12CriterionResult, ...]:
    return tuple(
        _criterion(
            identity,
            Kr370CriterionState.SATISFIED
            if index < satisfied
            else Kr370CriterionState.UNSATISFIED,
        )
        for index, identity in enumerate(Wo12CriterionIdentity)
    )


def test_common_contract_and_exact_five_criterion_grammar_are_reused() -> None:
    assert KR370_PROMOTION_CONTRACT_ID == "KRONOS-KR-370-ANALYTICAL-PROMOTION-V1"
    assert KR370_STATE_FAMILY_IDENTITY == "KR370_ANALYTICAL_PROMOTION"
    assert KR370_OWNER_IDENTITY == "KR-370"
    assert KR370_PROMOTION_AUTHORITY == "ANALYTICAL_PROMOTION_ONLY"
    assert tuple(item.value for item in Wo12CriterionIdentity) == (
        "K1_15M_DIRECTIONAL_PROGRESSION",
        "K2_15M_CPR_ACCEPTANCE",
        "K3_15M_IMMEDIATE_PATH_CLEARANCE",
        "K4_15M_SETUP_QUALITY",
        "K5_15M_NON_EXTENSION",
    )
    assert tuple(item.value for item in Kr370CriterionState) == (
        "SATISFIED", "UNSATISFIED", "UNAVAILABLE"
    )
    assert not hasattr(Wo12CriterionIdentity, "K6")


@pytest.mark.parametrize(
    ("direction", "satisfied", "expected"),
    (
        (SemanticDirection.LONG, 5, Kr370AnalyticalClassification.BUY_NOW),
        (SemanticDirection.SHORT, 5, Kr370AnalyticalClassification.SELL_NOW),
        (SemanticDirection.LONG, 4, Kr370AnalyticalClassification.BUY_READY),
        (SemanticDirection.SHORT, 4, Kr370AnalyticalClassification.SELL_READY),
        (SemanticDirection.LONG, 3, Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP),
        (SemanticDirection.SHORT, 2, Kr370AnalyticalClassification.POTENTIAL_SELL_SETUP),
        (SemanticDirection.LONG, 1, Kr370AnalyticalClassification.NO_SETUP),
        (SemanticDirection.SHORT, 0, Kr370AnalyticalClassification.NO_SETUP),
    ),
)
def test_common_five_criterion_classifier_is_symmetric(
    direction: SemanticDirection,
    satisfied: int,
    expected: Kr370AnalyticalClassification,
) -> None:
    state, actual, missing = classify_wo12(direction, _criteria(satisfied))
    assert state is expected
    assert actual == satisfied
    assert missing == 5 - satisfied


def test_any_unavailable_fails_classifier_input_closed() -> None:
    criteria = list(_criteria(4))
    criteria[-1] = _criterion(
        Wo12CriterionIdentity.K5_15M_NON_EXTENSION,
        Kr370CriterionState.UNAVAILABLE,
    )
    with pytest.raises(Wo12ContractError, match="WO12_CLASSIFICATION_INPUT_INVALID"):
        classify_wo12(SemanticDirection.LONG, tuple(criteria))


def test_exact_wo11_handoff_preserves_all_lineage_and_rejects_mutation(tmp_path) -> None:
    _, _, handoff, request = _foundation(tmp_path)
    assert request.policy.policy_identity == WO12_POLICY_IDENTITY
    assert request.policy.policy_version == WO12_POLICY_VERSION
    assert handoff.wo11_downstream_eligibility.value == "ELIGIBLE_FOR_DOWNSTREAM_HANDOFF"
    assert handoff.wo10_result_identity
    assert handoff.wo10_evidence_identity
    assert handoff.probables_run_identity
    assert handoff.probable_result_identity
    assert handoff.source_integrities
    with pytest.raises(Wo12ContractError, match="WO12_HANDOFF_INVALID"):
        replace(handoff, inherited_direction=SemanticDirection.SHORT)


@pytest.mark.parametrize(
    ("field", "wrong"),
    (
        ("wo11_member_identity", "INTRADAY-WO11-MEMBER-WRONG"),
        ("wo10_result_integrity", "INTEGRITY-WO10-WRONG"),
        ("probables_run_identity", "INTRADAY-PROBABLES-RUN-WRONG"),
        ("probable_result_integrity", "INTEGRITY-PROBABLE-WRONG"),
        ("canonical_subject_identity", "NSE-EQ-WRONG"),
    ),
)
def test_wrong_exact_lineage_is_rejected_by_application(
    tmp_path,
    field: str,
    wrong: str,
) -> None:
    wo10, wo11, handoff, _ = _foundation(tmp_path)
    wrong_handoff = _rebound(handoff, **{field: wrong})
    request = create_wo12_request(
        handoff=wrong_handoff,
        requested_at=REQUESTED_AT + timedelta(minutes=5),
        sponsor_operation_identity="SPONSOR-WO12-WRONG-LINEAGE",
        provenance=("KRONOS-WO12-CORE-TEST",),
    )
    app = IntradayWo12Application(
        wo10_store=wo10,
        wo11_store=wo11,
        store=Wo12Store((tmp_path / "wo12").resolve()),
    )
    with pytest.raises(Wo12ApplicationError):
        app.execute(request, _inputs(wrong_handoff))


def test_cross_family_handoff_substitution_is_rejected(tmp_path) -> None:
    wo10, wo11, handoff, _ = _foundation(tmp_path)
    source_policy = handoff.wo10_policy
    mcx_policy = create_wo10_policy_binding(
        policy_identity=source_policy.policy_identity,
        policy_version=source_policy.policy_version,
        publication_identity=source_policy.publication_identity,
        policy_checksum=source_policy.policy_checksum,
        supported_market_family=IntradayMarketFamily.MCX,
    )
    wrong_handoff = _rebound(
        handoff,
        market_family=IntradayMarketFamily.MCX,
        wo10_policy=mcx_policy,
    )
    request = create_wo12_request(
        handoff=wrong_handoff,
        requested_at=REQUESTED_AT + timedelta(minutes=5),
        sponsor_operation_identity="SPONSOR-WO12-CROSS-FAMILY",
        provenance=("KRONOS-WO12-CORE-TEST",),
    )
    app = IntradayWo12Application(
        wo10_store=wo10,
        wo11_store=wo11,
        store=Wo12Store((tmp_path / "wo12").resolve()),
    )
    with pytest.raises(Wo12ApplicationError, match="WO12_WO11_HANDOFF_BINDING_INVALID"):
        app.execute(request, _inputs(wrong_handoff))


def test_k1_k2_k3_k4_adapters_and_k2_strict_close_semantics(tmp_path) -> None:
    _, _, handoff, _ = _foundation(tmp_path)
    assert adapt_k1(
        handoff, _semantic(handoff, SemanticDirection.LONG)
    ).state is Kr370CriterionState.SATISFIED
    assert adapt_k1(
        handoff, _semantic(handoff, SemanticDirection.SHORT)
    ).state is Kr370CriterionState.UNSATISFIED
    assert adapt_k1(
        handoff,
        _semantic(handoff, SemanticDirection.UNAVAILABLE, available=False),
    ).state is Kr370CriterionState.UNAVAILABLE

    long_above = adapt_k2(handoff, _inputs(handoff, close=Decimal("106")).cpr_acceptance)
    equal = adapt_k2(handoff, _inputs(handoff, close=Decimal("105")).cpr_acceptance)
    unavailable = create_wo12_cpr_acceptance_fact(
        handoff=handoff,
        completed_close=None,
        cpr_lower=None,
        cpr_upper=None,
        completed_candle_identity=None,
        cpr_evidence_identity=None,
        source_evidence_integrities=("INTEGRITY-UNAVAILABLE-CPR",),
    )
    assert long_above.state is Kr370CriterionState.SATISFIED
    assert equal.state is Kr370CriterionState.UNSATISFIED
    assert adapt_k2(handoff, unavailable).state is Kr370CriterionState.UNAVAILABLE
    assert {item.name for item in fields(Wo12CprAcceptanceFact)}.isdisjoint(
        {"high", "low", "last_traded_price", "ltp", "wick_crossed"}
    )

    short = _rebound(handoff, inherited_direction=SemanticDirection.SHORT)
    assert adapt_k2(
        short,
        _inputs(short, close=Decimal("94")).cpr_acceptance,
    ).state is Kr370CriterionState.SATISFIED
    assert adapt_k2(
        short,
        _inputs(short, close=Decimal("95")).cpr_acceptance,
    ).state is Kr370CriterionState.UNSATISFIED

    inputs = _inputs(handoff)
    assert adapt_k3(handoff, inputs.path_clearance).state is Kr370CriterionState.SATISFIED
    blocked = _inputs(handoff, path=Wo12PathState.BLOCKED).path_clearance
    assert adapt_k3(handoff, blocked).state is Kr370CriterionState.UNSATISFIED
    no_policy = _inputs(handoff, path=Wo12PathState.UNAVAILABLE).path_clearance
    assert adapt_k3(handoff, no_policy).state is Kr370CriterionState.UNAVAILABLE

    assert adapt_k4(
        handoff, _inputs(handoff).setup_quality
    ).state is Kr370CriterionState.SATISFIED
    assert adapt_k4(
        handoff,
        _inputs(handoff, quality=Wo12SetupQualityState.ADVERSE).setup_quality,
    ).state is Kr370CriterionState.UNSATISFIED
    assert adapt_k4(
        handoff,
        _inputs(handoff, quality=Wo12SetupQualityState.UNAVAILABLE).setup_quality,
    ).state is Kr370CriterionState.UNAVAILABLE
    unbound_quality = create_wo12_setup_quality_fact(
        canonical_subject_identity=handoff.canonical_subject_identity,
        market_family=handoff.market_family,
        analysis_boundary=handoff.analysis_boundary,
        state=Wo12SetupQualityState.ACCEPTABLE,
        source_evidence_identities=("UNRELATED-WO10-EVIDENCE",),
        source_evidence_integrities=("INTEGRITY-UNRELATED-WO10-EVIDENCE",),
        adapter_identity="WO10-NATIVE-VISUAL-SETUP-QUALITY-ADAPTER-V1",
    )
    with pytest.raises(
        Wo12ContractError, match="WO12_K4_WO10_EVIDENCE_BINDING_INVALID"
    ):
        adapt_k4(handoff, unbound_quality)


def test_k3_contract_has_no_distance_atr_or_trade_geometry() -> None:
    names = {item.name.lower() for item in fields(Wo12PathClearanceFact)}
    source = inspect.getsource(adapt_k3)
    assert "0.5" not in source
    assert "atr" not in source.lower()
    assert "r:r" not in source.lower()
    assert names.isdisjoint({"entry", "stop", "target", "risk"})


def test_k5_measurement_is_exact_but_consequence_remains_unavailable(tmp_path) -> None:
    _, _, handoff, _ = _foundation(tmp_path)
    inputs = _inputs(handoff, close=Decimal("110"))
    measurement = inputs.extension_measurement
    assert measurement is not None
    assert measurement.extension_atr_multiple == Decimal("2")
    assert measurement.structural_origin_identity == "GOVERNED-15M-STRUCTURAL-ORIGIN"
    assert measurement.threshold_status == WO12_MATERIAL_EXTENSION_THRESHOLD
    k5 = adapt_k5(handoff, measurement)
    missing = adapt_k5(handoff, None)
    assert k5.state is Kr370CriterionState.UNAVAILABLE
    assert k5.reason == "K5_THRESHOLD_POLICY_UNRESOLVED"
    assert missing.state is Kr370CriterionState.UNAVAILABLE
    assert "2" not in WO12_MATERIAL_EXTENSION_THRESHOLD
    assert "> 2" not in inspect.getsource(adapt_k5)
    assert ">2" not in inspect.getsource(adapt_k5)


def test_hard_gates_fail_closed_and_only_now_is_wo13_eligible(tmp_path) -> None:
    _, _, handoff, request = _foundation(tmp_path)
    criteria = list(_criteria(5))
    evidence = create_wo12_evidence(
        request=request,
        criteria=criteria,
        exact_binding_valid=True,
        governing_15m_structure_failed=True,
        authoritative_directional_conflict=True,
        extension_measurement_identity=None,
        extension_measurement_integrity=None,
    )
    result = create_wo12_result(
        request=request,
        evidence=evidence,
        created_at=request.requested_at,
        provenance=("WO12-HARD-GATE-TEST",),
    )
    assert result.classification is Kr370AnalyticalClassification.NO_SETUP
    assert result.hard_gates == (
        Wo12HardGate.GOVERNING_15M_STRUCTURE_FAILED,
        Wo12HardGate.AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT,
    )
    assert create_wo13_eligibility(
        result, provenance=("WO13-ELIGIBILITY-TEST",)
    ).eligibility is Wo13Eligibility.NOT_ELIGIBLE_FOR_WO13_STEP31

    clear = create_wo12_evidence(
        request=request,
        criteria=_criteria(5),
        exact_binding_valid=True,
        governing_15m_structure_failed=False,
        authoritative_directional_conflict=False,
        extension_measurement_identity=None,
        extension_measurement_integrity=None,
    )
    now = create_wo12_result(
        request=request,
        evidence=clear,
        created_at=request.requested_at,
        provenance=("WO12-NOW-FIXTURE",),
    )
    eligible = create_wo13_eligibility(now, provenance=("WO13-ELIGIBILITY-TEST",))
    assert now.classification is Kr370AnalyticalClassification.BUY_NOW
    assert eligible.eligibility is Wo13Eligibility.ELIGIBLE_FOR_WO13_STEP31
    assert not eligible.geometry_authority
    assert not eligible.risk_authority
    assert not eligible.broker_authority


def test_invalid_exact_binding_is_a_hard_gate(tmp_path) -> None:
    _, _, _, request = _foundation(tmp_path)
    evidence = create_wo12_evidence(
        request=request,
        criteria=_criteria(5),
        exact_binding_valid=False,
        governing_15m_structure_failed=False,
        authoritative_directional_conflict=False,
        extension_measurement_identity=None,
        extension_measurement_integrity=None,
    )
    result = create_wo12_result(
        request=request,
        evidence=evidence,
        created_at=request.requested_at,
        provenance=("WO12-INVALID-BINDING-TEST",),
    )
    assert result.classification is Kr370AnalyticalClassification.NO_SETUP
    assert result.hard_gates == (Wo12HardGate.INVALID_EXACT_EVIDENCE_BINDING,)


@pytest.mark.parametrize(
    ("satisfied", "expected"),
    (
        (4, Kr370AnalyticalClassification.BUY_READY),
        (3, Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP),
        (2, Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP),
        (1, Kr370AnalyticalClassification.NO_SETUP),
        (0, Kr370AnalyticalClassification.NO_SETUP),
    ),
)
def test_every_non_now_classification_is_not_wo13_eligible(
    tmp_path,
    satisfied: int,
    expected: Kr370AnalyticalClassification,
) -> None:
    _, _, _, request = _foundation(tmp_path)
    evidence = create_wo12_evidence(
        request=request,
        criteria=_criteria(satisfied),
        exact_binding_valid=True,
        governing_15m_structure_failed=False,
        authoritative_directional_conflict=False,
        extension_measurement_identity=None,
        extension_measurement_integrity=None,
    )
    result = create_wo12_result(
        request=request,
        evidence=evidence,
        created_at=request.requested_at,
        provenance=("WO12-NON-NOW-ELIGIBILITY-TEST",),
    )
    assert result.classification is expected
    assert create_wo13_eligibility(
        result, provenance=("WO13-NON-NOW-ELIGIBILITY-TEST",)
    ).eligibility is Wo13Eligibility.NOT_ELIGIBLE_FOR_WO13_STEP31


def test_application_persists_reloads_and_k5_holds_full_now(tmp_path) -> None:
    wo10, wo11, handoff, request = _foundation(tmp_path)
    store = Wo12Store((tmp_path / "wo12").resolve())
    app = IntradayWo12Application(wo10_store=wo10, wo11_store=wo11, store=store)
    inputs = _inputs(handoff)
    execution = app.execute(request, inputs)

    assert execution.result.classification is Kr370AnalyticalClassification.NO_SETUP
    assert execution.result.hard_gates == (Wo12HardGate.MANDATORY_K_UNAVAILABLE,)
    assert execution.result.unavailable_criteria == (
        Wo12CriterionIdentity.K5_15M_NON_EXTENSION,
    )
    assert execution.eligibility.eligibility is Wo13Eligibility.NOT_ELIGIBLE_FOR_WO13_STEP31
    assert store.load_result(execution.result.result_identity) == execution.result
    assert store.restore_current() == app.restore_current()
    assert store.restore_current().extension_measurement == inputs.extension_measurement  # type: ignore[union-attr]

    # Same content is idempotent and does not create a different result.
    repeated = app.execute(request, inputs)
    assert repeated.result == execution.result
    assert repeated.pointer == execution.pointer


def test_persistence_conflict_and_corruption_fail_closed(tmp_path) -> None:
    wo10, wo11, handoff, request = _foundation(tmp_path)
    store = Wo12Store((tmp_path / "wo12").resolve())
    execution = IntradayWo12Application(
        wo10_store=wo10, wo11_store=wo11, store=store
    ).execute(request, _inputs(handoff))
    path = store.root / "results" / f"{execution.result.result_identity}.json"
    path.write_bytes(path.read_bytes().replace(b"INTRADAY", b"XNTRADAY", 1))
    with pytest.raises(Wo12PersistenceError, match="WO12_ARTIFACT_INTEGRITY_INVALID"):
        store.restore_current()
    with pytest.raises(Wo12PersistenceError, match="WO12_PERSISTENCE_CONFLICT"):
        store.retain_result(execution.result)


def test_5m_trade_risk_and_broker_authority_are_absent() -> None:
    contract_names = {
        item.name.lower()
        for contract in (
            Wo12CriterionResult,
            Wo12Result,
            Wo13EligibilityRecord,
        )
        for item in fields(contract)
    }
    result_names = {item.name.lower() for item in fields(Wo12Result)}
    assert all("5m" not in item and "five_minute" not in item for item in contract_names)
    assert result_names.isdisjoint({"entry", "stop", "target", "rr", "quantity"})
    assert {item.value for item in Wo12HardGate} == {
        "INVALID_EXACT_EVIDENCE_BINDING",
        "MANDATORY_K_UNAVAILABLE",
        "GOVERNING_15M_STRUCTURE_FAILED",
        "AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT",
    }
    assert all("SWING" not in item.value for item in Wo12HardGate)
