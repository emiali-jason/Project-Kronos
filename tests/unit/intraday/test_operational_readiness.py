from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timedelta, timezone

import pytest

from kronos.intraday.operational_readiness import (
    WO_B_AUTHORITY,
    WO_B_CONTRACT_VERSION,
    WO_B_POLICY_IDENTITY,
    WO_B_POLICY_VERSION,
    WO_B_PRODUCT_IDENTITY,
    WoBClassificationBasis,
    WoBContractError,
    WoBPolicyBinding,
    WoBReviewClassification,
    WoBSourceBoundary,
    canonical_document_bytes,
    create_operational_review_snapshot,
    create_review_item,
    create_source_artifact_reference,
    wo_b_policy_from_dict,
)
from kronos.intraday.universe import IntradayMarketFamily


BOUNDARY = datetime(2026, 9, 4, 9, 45, tzinfo=timezone.utc)


def _reference(
    *,
    source_boundary: WoBSourceBoundary = WoBSourceBoundary.WO14_RISK_OBSERVATION,
    candidate: str = "INTRADAY-CANDIDATE-1",
    run: str = "INTRADAY-PROBABLES-RUN-1",
    instrument: str = "NSE-INSTRUMENT-1",
    contract: str | None = None,
    state: str = "RISK_REJECTED",
    reason: str | None = "RISK_EVIDENCE_UNAVAILABLE",
    diagnostic: str | None = "SOURCE_STATE_PRESERVED",
    current: bool = True,
    superseded: bool = False,
    currentness_required: bool = True,
):
    return create_source_artifact_reference(
        source_boundary=source_boundary,
        artifact_identity=f"ARTIFACT-{source_boundary.value}",
        artifact_schema_identity=f"SCHEMA-{source_boundary.value}",
        artifact_schema_version="1.0.0",
        source_policy_identity=f"POLICY-{source_boundary.value}",
        source_policy_version="1.0.0",
        source_integrity_identity=f"INTEGRITY-{source_boundary.value}",
        candidate_identity=candidate,
        analysis_run_identity=run,
        canonical_instrument_identity=instrument,
        active_contract_identity=contract,
        exact_source_state=state,
        exact_source_reason=reason,
        bounded_diagnostic=diagnostic,
        observed_at=BOUNDARY - timedelta(minutes=1),
        current_at_review_boundary=current,
        superseded=superseded,
        currentness_required=currentness_required,
    )


def _snapshot(*, references=None, items=None, boundary=BOUNDARY, mcx=False):  # type: ignore[no-untyped-def]
    if references is None:
        reference = _reference(
            contract="MCX-GOLDM-202609" if mcx else None,
            instrument="MCX-INSTRUMENT-GOLDM" if mcx else "NSE-INSTRUMENT-1",
        )
        references = (reference,)
    if items is None:
        items = (
            create_review_item(
                source_boundary=references[0].source_boundary,
                classification_basis=WoBClassificationBasis.SOURCE_BLOCKED,
                source_reference=references[0],
                next_governed_stage="WO15_TIMING_HANDOFF",
            ),
        )
    return create_operational_review_snapshot(
        review_boundary=boundary,
        created_at=boundary + timedelta(seconds=1),
        candidate_identity="INTRADAY-CANDIDATE-1",
        opportunity_identity="INTRADAY-OPPORTUNITY-1",
        analysis_run_lineage=("INTRADAY-DISCOVERY-RUN-1", "INTRADAY-PROBABLES-RUN-1"),
        canonical_subject_identity=("MCX-SUBJECT-GOLDM" if mcx else "NSE-EQ-TEST"),
        market_family=(IntradayMarketFamily.MCX if mcx else IntradayMarketFamily.NSE_EQUITY),
        canonical_instrument_identity=("MCX-INSTRUMENT-GOLDM" if mcx else "NSE-INSTRUMENT-1"),
        active_contract_identity=("MCX-GOLDM-202609" if mcx else None),
        source_artifact_references=references,
        review_items=items,
        provenance=("ADR-0029", "WO-B1"),
    )


def test_product_policy_and_negative_authority_are_exact() -> None:
    policy = WoBPolicyBinding()
    assert (
        policy.product_identity,
        policy.policy_identity,
        policy.policy_version,
        policy.authority,
    ) == (
        WO_B_PRODUCT_IDENTITY,
        WO_B_POLICY_IDENTITY,
        WO_B_POLICY_VERSION,
        WO_B_AUTHORITY,
    )
    assert WO_B_CONTRACT_VERSION == "1.0.0"
    assert policy.global_trade_ready_boolean == "PROHIBITED"
    assert not any(
        value
        for name, value in asdict(policy).items()
        if name.endswith("_authority")
    )


def test_policy_is_immutable_and_external_fields_are_strict() -> None:
    policy = WoBPolicyBinding()
    with pytest.raises(FrozenInstanceError):
        policy.policy_version = "2.0.0"
    with pytest.raises(WoBContractError, match="WO_B_POLICY_BINDING_INVALID"):
        replace(policy, risk_authority=True)
    values = asdict(policy)
    values["unknown"] = False
    with pytest.raises(WoBContractError, match="WO_B_CONTRACT_FIELDS_INVALID"):
        wo_b_policy_from_dict(values)
    values = asdict(policy)
    values.pop("policy_identity")
    with pytest.raises(WoBContractError, match="WO_B_CONTRACT_FIELDS_INVALID"):
        wo_b_policy_from_dict(values)


@pytest.mark.parametrize(
    ("basis", "classification"),
    (
        (WoBClassificationBasis.CURRENT_VALID_SOURCE, WoBReviewClassification.AVAILABLE),
        (WoBClassificationBasis.SOURCE_WAITING, WoBReviewClassification.WAITING),
        (WoBClassificationBasis.SOURCE_BLOCKED, WoBReviewClassification.BLOCKED),
        (WoBClassificationBasis.SOURCE_UNAVAILABLE, WoBReviewClassification.UNAVAILABLE),
        (WoBClassificationBasis.SOURCE_TERMINAL, WoBReviewClassification.TERMINAL),
    ),
)
def test_source_backed_classifications_preserve_exact_state_and_reason(
    basis: WoBClassificationBasis,
    classification: WoBReviewClassification,
) -> None:
    reference = _reference()
    item = create_review_item(
        source_boundary=reference.source_boundary,
        classification_basis=basis,
        source_reference=reference,
    )
    assert item.review_classification is classification
    assert item.exact_source_state == "RISK_REJECTED"
    assert item.exact_source_reason == "RISK_EVIDENCE_UNAVAILABLE"
    assert item.source_reference_identity == reference.reference_identity


def test_not_reached_is_expected_absence_not_unavailable() -> None:
    item = create_review_item(
        source_boundary=WoBSourceBoundary.WO16_SPONSOR_LIFECYCLE,
        classification_basis=WoBClassificationBasis.EXPECTED_DOWNSTREAM_ABSENCE,
        next_governed_stage="WO16_SPONSOR_LIFECYCLE",
    )
    assert item.review_classification is WoBReviewClassification.NOT_REACHED
    assert item.source_reference_identity is None
    assert item.exact_source_state == "NOT_REACHED"
    with pytest.raises(WoBContractError, match="WO_B_REVIEW_SOURCE_BINDING_INVALID"):
        create_review_item(
            source_boundary=WoBSourceBoundary.WO16_SPONSOR_LIFECYCLE,
            classification_basis=WoBClassificationBasis.SOURCE_UNAVAILABLE,
        )


def test_snapshot_is_deterministic_and_canonical() -> None:
    first = _snapshot()
    second = _snapshot()
    assert first == second
    assert first.review_snapshot_identity == second.review_snapshot_identity
    assert first.snapshot_integrity_hash == second.snapshot_integrity_hash
    assert canonical_document_bytes(first) == canonical_document_bytes(second)
    assert b'"schema_version":"1.0.0"' in canonical_document_bytes(first)


def test_multi_domain_truths_are_preserved_without_global_readiness() -> None:
    timing = _reference(
        source_boundary=WoBSourceBoundary.WO15_TIMING_HANDOFF,
        state="TIMING_QUALIFIED",
        reason=None,
        diagnostic=None,
    )
    risk = _reference(
        source_boundary=WoBSourceBoundary.WO14_RISK_OBSERVATION,
        state="RISK_UNAVAILABLE",
        reason="CAPITAL_REFERENCE_UNAVAILABLE",
    )
    items = (
        create_review_item(
            source_boundary=timing.source_boundary,
            classification_basis=WoBClassificationBasis.CURRENT_VALID_SOURCE,
            source_reference=timing,
        ),
        create_review_item(
            source_boundary=risk.source_boundary,
            classification_basis=WoBClassificationBasis.SOURCE_UNAVAILABLE,
            source_reference=risk,
        ),
    )
    snapshot = _snapshot(references=(timing, risk), items=items)
    assert [item.exact_source_state for item in snapshot.review_items] == [
        "TIMING_QUALIFIED",
        "RISK_UNAVAILABLE",
    ]
    assert [item.review_classification for item in snapshot.review_items] == [
        WoBReviewClassification.AVAILABLE,
        WoBReviewClassification.UNAVAILABLE,
    ]
    assert not hasattr(snapshot, "trade_ready")
    assert not hasattr(snapshot, "ready")


def test_nse_and_mcx_instrument_contract_binding() -> None:
    nse = _snapshot()
    mcx = _snapshot(mcx=True)
    assert nse.active_contract_identity is None
    assert mcx.active_contract_identity == "MCX-GOLDM-202609"
    with pytest.raises(WoBContractError, match="WO_B_REVIEW_SNAPSHOT_INVALID"):
        replace(nse, active_contract_identity="INVENTED-MCX-CONTRACT")
    with pytest.raises(WoBContractError, match="WO_B_REVIEW_SNAPSHOT_INVALID"):
        replace(mcx, active_contract_identity=None)


@pytest.mark.parametrize("field", ("candidate", "run", "instrument"))
def test_foreign_source_bindings_fail_closed(field: str) -> None:
    values = {
        "candidate": "FOREIGN-CANDIDATE" if field == "candidate" else "INTRADAY-CANDIDATE-1",
        "run": "FOREIGN-RUN" if field == "run" else "INTRADAY-PROBABLES-RUN-1",
        "instrument": "FOREIGN-INSTRUMENT" if field == "instrument" else "NSE-INSTRUMENT-1",
    }
    reference = _reference(**values)
    item = create_review_item(
        source_boundary=reference.source_boundary,
        classification_basis=WoBClassificationBasis.SOURCE_BLOCKED,
        source_reference=reference,
    )
    with pytest.raises(WoBContractError, match="WO_B_REVIEW_SNAPSHOT_INVALID"):
        _snapshot(references=(reference,), items=(item,))


def test_stale_superseded_and_tampered_sources_fail_closed() -> None:
    with pytest.raises(WoBContractError, match="WO_B_SOURCE_REFERENCE_INVALID"):
        _reference(current=False, currentness_required=True)
    with pytest.raises(WoBContractError, match="WO_B_SOURCE_REFERENCE_INVALID"):
        _reference(current=False, superseded=True, currentness_required=True)
    reference = _reference()
    with pytest.raises(WoBContractError, match="WO_B_SOURCE_REFERENCE_INVALID"):
        replace(reference, source_integrity_identity="TAMPERED")


def test_noncurrent_diagnostic_source_cannot_be_projected_as_available() -> None:
    reference = _reference(
        current=False, superseded=True, currentness_required=False
    )
    available = create_review_item(
        source_boundary=reference.source_boundary,
        classification_basis=WoBClassificationBasis.CURRENT_VALID_SOURCE,
        source_reference=reference,
    )
    with pytest.raises(WoBContractError, match="WO_B_REVIEW_SNAPSHOT_INVALID"):
        _snapshot(references=(reference,), items=(available,))
    unavailable = create_review_item(
        source_boundary=reference.source_boundary,
        classification_basis=WoBClassificationBasis.SOURCE_UNAVAILABLE,
        source_reference=reference,
    )
    assert _snapshot(references=(reference,), items=(unavailable,)).review_items == (
        unavailable,
    )


def test_missing_mandatory_identity_and_foreign_contract_fail_closed() -> None:
    with pytest.raises(WoBContractError, match="WO_B_SOURCE_REFERENCE_INVALID"):
        _reference(candidate="")
    reference = _reference(
        instrument="MCX-INSTRUMENT-GOLDM", contract="MCX-GOLDM-FOREIGN"
    )
    item = create_review_item(
        source_boundary=reference.source_boundary,
        classification_basis=WoBClassificationBasis.SOURCE_BLOCKED,
        source_reference=reference,
    )
    with pytest.raises(WoBContractError, match="WO_B_REVIEW_SNAPSHOT_INVALID"):
        _snapshot(references=(reference,), items=(item,), mcx=True)


def test_invalid_version_time_and_classification_fail_closed() -> None:
    snapshot = _snapshot()
    with pytest.raises(WoBContractError, match="WO_B_REVIEW_SNAPSHOT_INVALID"):
        replace(snapshot, schema_version="2.0.0")
    reference = _reference()
    with pytest.raises(WoBContractError, match="WO_B_SOURCE_REFERENCE_INVALID"):
        replace(reference, observed_at=datetime(2026, 9, 4, 9, 44))
    item = snapshot.review_items[0]
    with pytest.raises(WoBContractError, match="WO_B_REVIEW_ITEM_INVALID"):
        replace(item, review_classification=WoBReviewClassification.AVAILABLE)


def test_source_state_reason_binding_cannot_be_rewritten() -> None:
    snapshot = _snapshot()
    item = snapshot.review_items[0]
    with pytest.raises(WoBContractError, match="WO_B_REVIEW_ITEM_INVALID"):
        replace(item, exact_source_state="TIMING_QUALIFIED")
    foreign_item = create_review_item(
        source_boundary=WoBSourceBoundary.WO14_RISK_OBSERVATION,
        classification_basis=WoBClassificationBasis.SOURCE_BLOCKED,
        source_reference=_reference(state="OTHER_BLOCKED"),
    )
    with pytest.raises(WoBContractError, match="WO_B_REVIEW_SNAPSHOT_INVALID"):
        replace(snapshot, review_items=(foreign_item,))


def test_snapshot_contract_is_immutable() -> None:
    snapshot = _snapshot()
    with pytest.raises(FrozenInstanceError):
        snapshot.candidate_identity = "OTHER"
