from __future__ import annotations

from dataclasses import fields
from datetime import timedelta

import pytest

from kronos.application.intraday_wo12_v2 import IntradayWo12V2Application
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.wo12 import Wo12HardGate
from kronos.intraday.wo12_v2 import (
    WO12_V2_CONTRACT_VERSION,
    WO12_V2_EXTENSION_AUTHORITY,
    WO12_V2_POLICY_IDENTITY,
    Wo12CriterionIdentityV2,
    Wo12CriterionResultV2,
    Wo12EvidenceInputsV2,
    Wo13EligibilityV2,
    classify_wo12_v2,
    create_wo12_evidence_v2,
    create_wo12_request_v2,
    create_wo12_result_v2,
    create_wo13_eligibility_v2,
)
from kronos.intraday.wo12_v2_persistence import Wo12V2Store
from kronos.validation.kr370 import (
    Kr370AnalyticalClassification,
    Kr370CriterionState,
    classify_five_criteria,
)

from .test_wo10_contracts import REQUESTED_AT
from .test_wo12 import _foundation, _inputs


def _criterion(
    identity: Wo12CriterionIdentityV2,
    state: Kr370CriterionState,
) -> Wo12CriterionResultV2:
    return Wo12CriterionResultV2(
        identity=identity,
        state=state,
        reason=f"{identity.name}_{state.value}",
        evidence_identities=(f"EVIDENCE-{identity.value}",),
        evidence_integrities=(f"INTEGRITY-{identity.value}",),
    )


def _criteria(satisfied: int) -> tuple[Wo12CriterionResultV2, ...]:
    return tuple(
        _criterion(
            identity,
            Kr370CriterionState.SATISFIED
            if index < satisfied
            else Kr370CriterionState.UNSATISFIED,
        )
        for index, identity in enumerate(Wo12CriterionIdentityV2)
    )


def _v2_inputs(handoff, **changes):  # type: ignore[no-untyped-def]
    legacy = _inputs(handoff, **changes)
    return Wo12EvidenceInputsV2(
        fifteen_minute_structure=legacy.fifteen_minute_structure,
        cpr_acceptance=legacy.cpr_acceptance,
        path_clearance=legacy.path_clearance,
        setup_quality=legacy.setup_quality,
        governing_15m_structure_failed=legacy.governing_15m_structure_failed,
        authoritative_directional_conflict=legacy.authoritative_directional_conflict,
    )


def test_v2_contract_has_exactly_k1_to_k4_and_no_extension_decision_field() -> None:
    assert WO12_V2_POLICY_IDENTITY == "KRONOS-INTRADAY-WO12-KR370-POLICY-V2"
    assert WO12_V2_CONTRACT_VERSION == "2.0.0"
    assert WO12_V2_EXTENSION_AUTHORITY == "SUPPORTING_RESEARCH_TELEMETRY_WO15_ONLY"
    assert tuple(item.value for item in Wo12CriterionIdentityV2) == (
        "K1_15M_DIRECTIONAL_PROGRESSION",
        "K2_15M_CPR_ACCEPTANCE",
        "K3_15M_IMMEDIATE_PATH_CLEARANCE",
        "K4_15M_SETUP_QUALITY",
    )
    assert not hasattr(Wo12CriterionIdentityV2, "K5_15M_NON_EXTENSION")
    assert {item.name for item in fields(Wo12EvidenceInputsV2)}.isdisjoint(
        {"extension_measurement", "five_minute_evidence", "atr_factor"}
    )


@pytest.mark.parametrize(
    ("direction", "satisfied", "expected"),
    (
        (SemanticDirection.LONG, 4, Kr370AnalyticalClassification.BUY_NOW),
        (SemanticDirection.SHORT, 4, Kr370AnalyticalClassification.SELL_NOW),
        (SemanticDirection.LONG, 3, Kr370AnalyticalClassification.BUY_READY),
        (SemanticDirection.SHORT, 3, Kr370AnalyticalClassification.SELL_READY),
        (SemanticDirection.LONG, 2, Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP),
        (SemanticDirection.SHORT, 2, Kr370AnalyticalClassification.POTENTIAL_SELL_SETUP),
        (SemanticDirection.LONG, 1, Kr370AnalyticalClassification.NO_SETUP),
        (SemanticDirection.SHORT, 1, Kr370AnalyticalClassification.NO_SETUP),
        (SemanticDirection.LONG, 0, Kr370AnalyticalClassification.NO_SETUP),
        (SemanticDirection.SHORT, 0, Kr370AnalyticalClassification.NO_SETUP),
    ),
)
def test_four_criterion_mapping_is_symmetric(direction, satisfied, expected) -> None:  # type: ignore[no-untyped-def]
    state, actual, missing = classify_wo12_v2(direction, _criteria(satisfied))
    assert state is expected
    assert actual == satisfied
    assert missing == 4 - satisfied


@pytest.mark.parametrize("unavailable", tuple(Wo12CriterionIdentityV2))
def test_any_k1_to_k4_unavailable_creates_mandatory_gate(tmp_path, unavailable) -> None:  # type: ignore[no-untyped-def]
    _, _, handoff, _ = _foundation(tmp_path)
    request = create_wo12_request_v2(
        handoff=handoff,
        requested_at=REQUESTED_AT + timedelta(minutes=12),
        sponsor_operation_identity="SPONSOR-WO12-V2-UNAVAILABLE",
        provenance=("ADR-0021",),
    )
    criteria = list(_criteria(4))
    index = tuple(Wo12CriterionIdentityV2).index(unavailable)
    criteria[index] = _criterion(unavailable, Kr370CriterionState.UNAVAILABLE)
    evidence = create_wo12_evidence_v2(
        request=request,
        criteria=criteria,
        exact_binding_valid=True,
        governing_15m_structure_failed=False,
        authoritative_directional_conflict=False,
    )
    result = create_wo12_result_v2(
        request=request,
        evidence=evidence,
        created_at=request.requested_at,
        provenance=("ADR-0021",),
    )
    assert result.classification is Kr370AnalyticalClassification.NO_SETUP
    assert result.hard_gates == (Wo12HardGate.MANDATORY_K_UNAVAILABLE,)


@pytest.mark.parametrize(
    ("structure_failed", "conflict", "expected"),
    (
        (True, False, Wo12HardGate.GOVERNING_15M_STRUCTURE_FAILED),
        (False, True, Wo12HardGate.AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT),
    ),
)
def test_hard_gates_override_four_satisfied(tmp_path, structure_failed, conflict, expected) -> None:  # type: ignore[no-untyped-def]
    _, _, handoff, _ = _foundation(tmp_path)
    request = create_wo12_request_v2(
        handoff=handoff,
        requested_at=REQUESTED_AT + timedelta(minutes=13),
        sponsor_operation_identity="SPONSOR-WO12-V2-GATE",
        provenance=("ADR-0021",),
    )
    evidence = create_wo12_evidence_v2(
        request=request,
        criteria=_criteria(4),
        exact_binding_valid=True,
        governing_15m_structure_failed=structure_failed,
        authoritative_directional_conflict=conflict,
    )
    result = create_wo12_result_v2(
        request=request,
        evidence=evidence,
        created_at=request.requested_at,
        provenance=("ADR-0021",),
    )
    assert result.classification is Kr370AnalyticalClassification.NO_SETUP
    assert expected in result.hard_gates


def test_only_now_is_wo13_eligible(tmp_path) -> None:
    _, _, handoff, _ = _foundation(tmp_path)
    request = create_wo12_request_v2(
        handoff=handoff,
        requested_at=REQUESTED_AT + timedelta(minutes=14),
        sponsor_operation_identity="SPONSOR-WO12-V2-ELIGIBILITY",
        provenance=("ADR-0021",),
    )
    for satisfied, expected in (
        (4, Wo13EligibilityV2.ELIGIBLE_FOR_WO13_STEP31),
        (3, Wo13EligibilityV2.NOT_ELIGIBLE_FOR_WO13_STEP31),
        (2, Wo13EligibilityV2.NOT_ELIGIBLE_FOR_WO13_STEP31),
        (1, Wo13EligibilityV2.NOT_ELIGIBLE_FOR_WO13_STEP31),
    ):
        evidence = create_wo12_evidence_v2(
            request=request,
            criteria=_criteria(satisfied),
            exact_binding_valid=True,
            governing_15m_structure_failed=False,
            authoritative_directional_conflict=False,
        )
        result = create_wo12_result_v2(
            request=request,
            evidence=evidence,
            created_at=request.requested_at,
            provenance=("ADR-0021",),
        )
        assert create_wo13_eligibility_v2(result, provenance=("ADR-0021",)).eligibility is expected


def test_application_persists_and_restores_v2_without_extension_dependency(tmp_path) -> None:
    wo10, wo11, handoff, _ = _foundation(tmp_path)
    request = create_wo12_request_v2(
        handoff=handoff,
        requested_at=REQUESTED_AT + timedelta(minutes=15),
        sponsor_operation_identity="SPONSOR-WO12-V2-APPLICATION",
        provenance=("ADR-0021",),
    )
    store = Wo12V2Store((tmp_path / "wo12-v2").resolve())
    application = IntradayWo12V2Application(
        wo10_store=wo10,
        wo11_store=wo11,
        store=store,
    )

    execution = application.execute(request, _v2_inputs(handoff))
    restored = application.restore_current()

    assert execution.result.classification is Kr370AnalyticalClassification.BUY_NOW
    assert execution.result.satisfied_count == 4
    assert execution.eligibility.eligibility is Wo13EligibilityV2.ELIGIBLE_FOR_WO13_STEP31
    assert restored is not None and restored.result == execution.result
    assert store.root.name == "wo12-v2"
    assert "extension" not in {item.name for item in fields(type(execution.evidence))}


def test_swing_common_five_criterion_classifier_remains_active() -> None:
    states = (Kr370CriterionState.SATISFIED,) * 5
    state, satisfied, missing = classify_five_criteria("LONG", states)
    assert state is Kr370AnalyticalClassification.BUY_NOW
    assert (satisfied, missing) == (5, 0)
