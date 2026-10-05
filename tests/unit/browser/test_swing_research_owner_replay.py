"""Actual NSE/MCX retained V2 and NSE Sponsor owners survive capture failure."""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from kronos.application.swing_research_inbox import SwingResearchInbox, restore_price_fact
from kronos.application.swing_visual_v3_live import NativeReviewIntakeWorkflow
from kronos.swing.v1.prospective_research import milestone_from_v2_promotion, origin
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.swing.v1.native_review import NativeLayer2EvidenceState, NativeReviewEvidenceStore
from kronos.swing.v1.native_sponsor_decision import (
    SponsorTradeChoice, create_trade_plan_business_judgment,
    record_trade_plan_risk_result,
)
from kronos.swing.v1.step32 import RiskState
from tests.unit.browser.test_swing_review_intake_binding import (
    native_intake, _accepted_native,
)
from tests.unit.swing.v1.test_native_review import _evidence_run, _layer2
from tests.unit.swing.v1.test_native_readiness import _complete_visual_pairs
from tests.unit.swing.v1.test_native_sponsor_decision import NOW, _context, _package


@pytest.mark.parametrize("native_intake", ["NSE", "GOLDM"], indirect=True)
def test_retained_v2_owner_price_receipt_survives_failed_projection_and_restart(
        native_intake, tmp_path):
    inbox = SwingResearchInbox(tmp_path / "price-inbox")
    seen = []

    def admitted(promotion):
        at = datetime.fromisoformat(promotion.value["created_at"].replace("Z", "+00:00"))
        source = promotion.value["source"]
        payload = {"run": source["native_run_identity"],
                   "assessment": source["native_assessment_sha256"],
                   "price": {"reference_price": "100",
                             "price_observation_identity": "MOCK-TICK-" + promotion.identity,
                             "price_observed_at": (at - timedelta(seconds=1)).isoformat(),
                             "price_received_at": at.isoformat(),
                             "price_source": "MOCK_OWNER_TICK"}}
        inbox.retain("V2", promotion.identity, payload)
        seen.append(promotion.identity)
        raise OSError("injected downstream research projection failure")

    native_intake.register_research_capture(admitted)
    market, instrument, *_ = _accepted_native(native_intake, tmp_path)
    assert native_intake.research_capture_failure == "CAPTURE_REPLAY_REQUIRED"
    assert len(seen) == 1
    retained = native_intake.v2_for(native_intake._context()[1].run_identity, instrument)
    assert retained is not None
    restarted = NativeReviewIntakeWorkflow(
        native_intake.application, native_intake.native_review,
        native_intake.live, native_intake.store)
    restarted.restore()
    assert retained in restarted.retained_research_promotions()
    receipt = inbox.read("V2", retained.identity)
    assert receipt["run"] == retained.value["source"]["native_run_identity"]
    at = datetime.fromisoformat(retained.value["created_at"].replace("Z", "+00:00"))
    source = retained.value["source"]
    admitted_source = origin(
        continuity_identity="REPLAY-" + instrument, market="NSE" if market == "NSE" else "GOLDM",
        instrument=instrument, contract_identity="EXACT-" + instrument,
        expiry=None if market == "NSE" else date(2026, 10, 30),
        direction=source["direction"], admitted_at=at - timedelta(minutes=1),
        source_identity="CANONICAL-OWNER-" + instrument, source_version="1",
        source_sha256="a" * 64, origin_run_identity=source["native_run_identity"],
        origin_assessment_sha256=source["native_assessment_sha256"],
        native_setup_identity=source["native_opportunity_identity"])
    milestone = milestone_from_v2_promotion(
        admitted_source, retained, **restore_price_fact(receipt["price"]))
    if (retained.value["evaluation_disposition"] == "EVALUATED"
            and retained.value["satisfied_count"] in {4, 5}):
        assert milestone is not None
        assert milestone.data["reference_price"] == "100"
        assert milestone.data["analytical_at"] != milestone.data["price_received_at"]
        assert milestone.data["price_received_at"] == at.isoformat()
    else:
        # Canonical owner retained a real lower-score assessment. Replay keeps
        # its factual receipt but must not promote it into a WO-12 milestone.
        assert milestone is None
        assert restore_price_fact(receipt["price"])["price_received_at"] == at


def test_nse_sponsor_owner_retains_waiting_truth_after_capture_failure(tmp_path):
    facts, run, _ = _evidence_run()
    root = tmp_path / "canonical-native"
    workflow = NativeReviewWorkflow(NativeReviewEvidenceStore(root), clock=lambda: NOW)
    prepared = workflow.prepare(run, facts)
    for request, response in _complete_visual_pairs():
        workflow.ingest_visual_v2(request, response)
    requirement = prepared.requirements[0]
    readiness = workflow.ingest_readiness(
        _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS),
        created_at=NOW)
    context = _context(requirement.canonical_instrument)
    plan = workflow.construct_trade_plan(
        requirement.canonical_instrument, _package(requirement, readiness), context)
    judgment = create_trade_plan_business_judgment(
        plan, validation_identity="VALIDATION-RESEARCH-REPLAY", created_at=NOW)
    risk = record_trade_plan_risk_result(
        plan, judgment, RiskState.APPROVED, reason="APPROVED", evaluated_at=NOW)
    workflow.bind_step32_inputs(plan.trade_plan_id, judgment, risk, context)
    def fail_capture(kind, value):
        assert kind == "SPONSOR" and value.position.actual_entry is None
        raise OSError("injected research failure")
    workflow.register_research_capture(fail_capture)
    result = workflow.initiate_sponsor_decision(plan.trade_plan_id, SponsorTradeChoice.PAPER)
    assert workflow.research_capture_failure == "CAPTURE_REPLAY_REQUIRED"
    assert result.position.actual_entry is None
    restored = NativeReviewWorkflow(NativeReviewEvidenceStore(root)).restore(run, facts)
    assert restored.sponsor_initiations == (result,)
    assert restored.active_lifecycle.positions[0].actual_entry is None
    assert restored.active_lifecycle.positions[0].state.value == "PAPER_ARMED"
