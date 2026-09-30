"""Isolated MCX Review/V2 handoff checks; no commissioning or live authority."""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from kronos.swing.v1.analytical_promotion_v2 import create_record, evaluate_governed
from kronos.swing.v1.review_evidence_binding import ReviewAcceptanceReceipt
from kronos.swing.v1.mcx_step31_prepared_handoff import (
    MCX_STEP31_COMMISSIONING,
    McxStep31ChartBinding,
    McxStep31CurrentReadSet,
    McxStep31HandoffRejected,
    McxStep31RequestBinding,
    prepare_mcx_review_v2_step31_handoff,
)
from tests.unit.application.test_swing_mtf_facts import _instrument
from tests.unit.browser.test_swing_review_intake_binding import (
    _accepted_native,
    _inventory,
    native_intake,
)
from tests.unit.swing.v1.test_analytical_promotion import _extension, _path
from tests.unit.swing.v1.test_analytical_promotion_v2 import NOW, criteria


FAMILIES = ("GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS")


def _current(workflow, root: Path, *, promotion_at=NOW) -> McxStep31CurrentReadSet:
    market, family, publication, _, _, commit = _accepted_native(workflow, root)
    assert market == "MCX"
    requirement = workflow._requirements(market, (family,))[0]
    _, facts, _ = workflow._context()
    evaluated = evaluate_governed(
        requirement=requirement, facts=facts,
        path_clearance=_path(facts, requirement, True),
        extension=_extension(facts, requirement, False), store=workflow.store,
        commit_identity=commit.identity,
        receipt_identity=commit.receipts[0].receipt_id,
        current_manifest=lambda: "a" * 64, created_at=promotion_at,
        visual=None, nse_request=None,
    )
    assert evaluated.value["promotion_state"] == "BUY_READY"
    # Explicit synthetic 5/5 fixture: real exact acceptance/source/confirmation;
    # the sealed criteria are fixture inputs, never a production reclassification.
    promoted = create_record(
        source=evaluated.value["source"], criteria=criteria(5),
        confirmation=evaluated.value["confirmation"], created_at=promotion_at,
    )
    assert promoted.value["promotion_state"] == "BUY_NOW"
    request_bindings = tuple(McxStep31RequestBinding(
        role, mapping["request_identity"], mapping["request_sha256"],
    ) for role, mapping in (("NATIVE_MCX", publication.native.value),
                            ("SUPPORTING_REFERENCE", publication.reference.value)))
    chart_bindings = tuple(McxStep31ChartBinding(
        item["role"], item["timeframe"], item["chart_revision_identity"],
        item["chart_sha256"],
    ) for item in promoted.value["source"]["acceptance"]["visual_bindings"])
    return McxStep31CurrentReadSet(
        run_identity=facts.run_identity, manifest_sha256="a" * 64,
        requirement=requirement, facts=facts, publication=publication,
        commit=commit, receipt=commit.receipts[0], promotion=promoted,
        derivative=_instrument(family, "MCX"),
        request_bindings=request_bindings, chart_bindings=chart_bindings,
    )


@pytest.mark.parametrize("native_intake", [f"{family}-LINEAGE" for family in FAMILIES], indirect=True)
def test_five_family_exact_preparation_is_non_actionable(native_intake, tmp_path):
    read = _current(native_intake, tmp_path)
    before = _inventory(tmp_path)
    prepared = prepare_mcx_review_v2_step31_handoff(lambda: read, prepared_at=NOW)
    assert prepared.bound.family.value == read.requirement.canonical_instrument
    assert prepared.bound.receipt_identity == read.receipt.receipt_id
    assert prepared.bound.promotion_identity == read.promotion.identity
    assert prepared.bound.derivative_proof_state == "REQUEST_BOUND_MASTER_AND_SPECIFICATION_UNVERIFIED"
    assert prepared.commissioning_state == MCX_STEP31_COMMISSIONING
    assert not prepared.permits_new_entry
    assert not any((prepared.geometry_authority, prepared.risk_authority,
                    prepared.sponsor_decision_authority, prepared.entry_authority,
                    prepared.position_authority, prepared.execution_authority,
                    prepared.broker_authority))
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_changed_current_pointers_fail_without_durable_effect(native_intake, tmp_path):
    read = _current(native_intake, tmp_path)
    original = _inventory(tmp_path)
    changed_receipt_body = read.receipt.body
    changed_receipt_body["answer"]["answer_identity"] += "-OTHER"
    changed_receipt_body["comparison_evidence"]["answer_identity"] += "-OTHER"
    changed_receipt = ReviewAcceptanceReceipt.create(changed_receipt_body)
    changed_instrument = replace(read.facts.instrument("GOLDM"), completed_series=())
    changed_facts = replace(read.facts, instruments=tuple(
        changed_instrument if item.canonical_instrument == "GOLDM" else item
        for item in read.facts.instruments
    ))
    variants = (
        replace(read, run_identity="SWING-RUN-" + "B" * 32),
        replace(read, manifest_sha256="b" * 64),
        replace(read, derivative=replace(read.derivative, trading_symbol="GOLDMOTHERFUT")),
        replace(read, receipt=changed_receipt),
        replace(read, receipt=None),
        replace(read, facts=changed_facts),
        replace(read, request_bindings=(replace(read.request_bindings[0], request_sha256="b" * 64),
                                        read.request_bindings[1])),
        replace(read, chart_bindings=(replace(read.chart_bindings[0], chart_sha256="b" * 64),
                                      *read.chart_bindings[1:])),
        replace(read, promotion=create_record(
            source=read.promotion.value["source"], criteria=criteria(4),
            confirmation=read.promotion.value["confirmation"], created_at=NOW,
        )),
    )
    for changed in variants:
        with pytest.raises(McxStep31HandoffRejected):
            prepare_mcx_review_v2_step31_handoff(lambda changed=changed: changed, prepared_at=NOW)
        calls = iter((read, changed))
        with pytest.raises(McxStep31HandoffRejected, match="MCX_STEP31_BINDING_CHANGED"):
            prepare_mcx_review_v2_step31_handoff(lambda: next(calls), prepared_at=NOW)
        assert _inventory(tmp_path) == original


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_concurrent_readers_and_failure_cleanup_are_pure(native_intake, tmp_path):
    read = _current(native_intake, tmp_path)
    before = _inventory(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(
            lambda _: prepare_mcx_review_v2_step31_handoff(lambda: read, prepared_at=NOW),
            range(2),
        ))
    assert results[0] == results[1]
    assert not results[0].permits_new_entry
    with pytest.raises(McxStep31HandoffRejected, match="MCX_STEP31_BINDING_INCOMPLETE"):
        prepare_mcx_review_v2_step31_handoff(
            lambda: (_ for _ in ()).throw(KeyError("missing current pointer")),
            prepared_at=NOW,
        )
    assert _inventory(tmp_path) == before
