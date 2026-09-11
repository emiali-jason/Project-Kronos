from dataclasses import replace
from datetime import datetime, timezone

import pytest

from kronos.application.intraday_wo09 import IntradayWo09Application
from kronos.application.intraday_runtime import create_intraday_runtime, create_intraday_workstation
from kronos.application.intraday_wo09_notifications import (
    deduplicate_sources, project_notification, project_reassessment_notification,
)
from kronos.application.notification_centre import SponsorNotificationCentre, SponsorNotificationLifecycleStore
from kronos.browser.intraday_wo09_control import active_attention_cards, project_analysis_details, project_card
from kronos.browser.intraday_wo09_control import IntradayWo09Projection, WO09_PRODUCT_ROUTE
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import BrowserGetRequest
from kronos.intraday.review import ObservationStatus
from kronos.intraday.visual_contract_v2 import MCX_QUESTIONS, NSE_QUESTIONS, VisualObservationV2
from kronos.intraday.visual_reconciliation_v2 import (
    NativeMarketAuthority, Q10Classification, ReconciliationPrerequisites, VisualReconciliationInput,
    VisualReconciliationOutcome, create_reconciliation_record,
)
from kronos.intraday.wo09_persistence import Wo09PersistenceError, Wo09Store
from kronos.intraday.wo09_readiness import (
    AttentionState, CriterionId, CriterionState, CurrentnessState, HardGate,
    HISTORICAL_ELIGIBILITY_VALUE, Monitorability, ReadinessState,
    Wo07fCompatibilityAdapter, Wo09Evidence, create_next_wo_handoff,
    evaluate_readiness,
)
from kronos.intraday.wo09_watch import WatchState, mark_disconnect_gap, transition_watch
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.provider.test_shared_provider_runtime import _shared


NOW = datetime(2026, 9, 11, 3, 0, tzinfo=timezone.utc)
POSITIVE = {
    "Q1": "SUPPORTIVE", "Q2": "CLEAN_DIRECTIONAL_STRUCTURE",
    "Q3": "CLEAR_BASE_OR_CONSOLIDATION", "Q4": "CLEAR_FOLLOW_THROUGH",
    "Q5": "ORDERLY", "Q6": "NOT_OBSERVABLE", "Q7": "CLEAR_SPACE",
    "Q8": "NOT_VISIBLY_EXTENDED", "Q9": "NOT_OBSERVABLE", "Q10": "NONE",
}


def observation(qid, answer):
    q = next(item for item in NSE_QUESTIONS if item.question_id == qid)
    return VisualObservationV2(qid, ObservationStatus.OBSERVED, answer,
                               q.timeframe_scope, "visible", None, None)


def source(*, subject="NSE-EQ-TEST", direction="LONG", answers=None, prerequisites=None):
    values = dict(POSITIVE); values.update(answers or {})
    request = VisualReconciliationInput(
        subject, direction, "run", "result", "cycle", "pack", "chart", "answer",
        "a" * 64, "visual", "correspondence", ("machine",),
        tuple(observation(f"Q{i}", values[f"Q{i}"]) for i in range(1, 11)),
        prerequisites=prerequisites or ReconciliationPrerequisites(),
        q10_classification=Q10Classification.NOT_APPLICABLE,
    )
    return create_reconciliation_record(request, created_at=NOW)


def evidence(*, subject="NSE-EQ-TEST", direction="LONG", one_hour=None,
             fifteen=None, follow="CLEAR_FOLLOW_THROUGH", space="CLEAR_SPACE",
             extension="NOT_VISIBLY_EXTENDED", **overrides):
    values = dict(
        canonical_subject_identity=subject, market_family="NSE", direction=direction,
        analysis_boundary=NOW, session_identity="NSE-2026-09-11",
        one_hour_direction=direction if one_hour is None else one_hour,
        fifteen_minute_direction=direction if fifteen is None else fifteen,
        follow_through=follow, trade_space=space, extension=extension,
        machine_evidence_identity="machine", machine_evidence_integrity="machine-integrity",
        visual_evidence_identity="visual", visual_evidence_integrity="visual-integrity",
    )
    values.update(overrides)
    return Wo09Evidence(**values)


def evaluated(*, direction="LONG", answers=None, **kwargs):
    return evaluate_readiness(source(direction=direction, answers=answers),
                              evidence(direction=direction, **kwargs), created_at=NOW)


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_i1_requires_completed_1h_and_15m_support(direction):
    record, _ = evaluated(direction=direction)
    assert record.criteria[0].state is CriterionState.SATISFIED
    other = "SHORT" if direction == "LONG" else "LONG"
    record, _ = evaluated(direction=direction, fifteen=other)
    assert record.hard_gate is HardGate.AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT
    assert record.criteria[0].state is CriterionState.NOT_APPLICABLE


@pytest.mark.parametrize("field", ["one_hour", "fifteen"])
def test_i1_missing_required_fact_is_unavailable(field):
    kwargs = {field: "UNAVAILABLE"}
    record, _ = evaluated(**kwargs)
    assert record.criteria[0].state is CriterionState.UNAVAILABLE
    assert record.readiness_state is ReadinessState.READINESS_UNAVAILABLE
    e = evidence(); object.__setattr__(e, "one_hour_direction", None)
    record, _ = evaluate_readiness(source(), e, created_at=NOW)
    assert record.readiness_state is ReadinessState.READINESS_UNAVAILABLE


@pytest.mark.parametrize(("value", "state"), [
    ("CLEAR_FOLLOW_THROUGH", CriterionState.SATISFIED),
    ("WEAK_OR_STALLING", CriterionState.OUTSTANDING), ("MIXED", CriterionState.OUTSTANDING),
    (None, CriterionState.UNAVAILABLE), ("UNCLEAR", CriterionState.UNAVAILABLE),
])
def test_i2_states(value, state):
    record, _ = evaluated(follow=value)
    assert record.criteria[1].state is state


@pytest.mark.parametrize(("value", "state"), [
    ("CLEAR_SPACE", CriterionState.SATISFIED), ("LIMITED_SPACE", CriterionState.OUTSTANDING),
    ("OBSTACLE_CLOSE", CriterionState.OUTSTANDING), ("UNCLEAR", CriterionState.UNAVAILABLE),
    ("NOT_OBSERVABLE", CriterionState.UNAVAILABLE),
])
def test_i3_states_and_no_numeric_gap(value, state):
    record, _ = evaluated(space=value)
    item = record.criteria[2]
    assert item.state is state and item.required_value is None
    if state is not CriterionState.SATISFIED:
        assert item.gap == "NUMERIC_GAP_NOT_GOVERNED"


@pytest.mark.parametrize("reason", [
    "Q2_MIXED_STRUCTURE", "Q2_CONGESTED_STRUCTURE", "Q3_WEAK_OR_MIXED_BASE",
    "Q3_NO_CLEAR_BASE", "Q5_MIXED", "Q5_DISORDERLY", "Q5_NO_CLEAR_PULLBACK_OR_PROGRESSION",
])
def test_i4_each_governed_setup_reason_is_outstanding(reason):
    qid, answer = reason.split("_", 1)
    record, _ = evaluated(answers={qid: answer})
    assert record.criteria[3].state is CriterionState.OUTSTANDING
    assert record.criteria[3].reason_codes == (reason,)


@pytest.mark.parametrize(("qid", "answer"), [
    ("Q1", "MIXED"), ("Q4", "WEAK_OR_STALLING"),
    ("Q7", "OBSTACLE_CLOSE"), ("Q8", "VISIBLY_EXTENDED"),
])
def test_i4_excludes_other_criterion_reason_families(qid, answer):
    record, _ = evaluated(answers={qid: answer},
                          follow=answer if qid == "Q4" else "CLEAR_FOLLOW_THROUGH",
                          space=answer if qid == "Q7" else "CLEAR_SPACE",
                          extension=answer if qid == "Q8" else "NOT_VISIBLY_EXTENDED")
    assert record.criteria[3].state is CriterionState.SATISFIED


@pytest.mark.parametrize(("value", "state"), [
    ("NOT_VISIBLY_EXTENDED", CriterionState.SATISFIED),
    ("VISIBLY_EXTENDED", CriterionState.OUTSTANDING), ("MIXED", CriterionState.OUTSTANDING),
    ("UNCLEAR", CriterionState.UNAVAILABLE), ("NOT_OBSERVABLE", CriterionState.UNAVAILABLE),
])
def test_i5_states(value, state):
    record, _ = evaluated(extension=value)
    assert record.criteria[4].state is state


@pytest.mark.parametrize(("count", "direction", "state"), [
    (0, "LONG", ReadinessState.NO_FOCUS), (1, "LONG", ReadinessState.NO_FOCUS),
    (2, "SHORT", ReadinessState.NO_FOCUS), (3, "LONG", ReadinessState.NEAR_READY),
    (4, "LONG", ReadinessState.BUY_READY), (4, "SHORT", ReadinessState.SELL_READY),
    (5, "LONG", ReadinessState.BUY_NOW), (5, "SHORT", ReadinessState.SELL_NOW),
])
def test_zero_through_five_state_mapping(count, direction, state):
    # I1 is controlled by structure; I2/I3/I5 by facts; I4 by a bound Q2 reason.
    fail = 5 - count
    answers = {"Q2": "MIXED_STRUCTURE"} if fail >= 1 else {}
    kwargs = {}
    if fail >= 2: kwargs["extension"] = "VISIBLY_EXTENDED"
    if fail >= 3: kwargs["space"] = "OBSTACLE_CLOSE"
    if fail >= 4: kwargs["follow"] = "WEAK_OR_STALLING"
    if fail >= 5:
        kwargs["one_hour"] = "NON_DIRECTIONAL"
    record, _ = evaluated(direction=direction, answers=answers, **kwargs)
    assert record.satisfied_count == count and record.readiness_state is state


@pytest.mark.parametrize(("answer", "gate"), [
    ({"Q4": "FAILED_OR_RETURNED_THROUGH"}, HardGate.WO07F_CONTRADICTED),
])
def test_wo07f_hard_gate_count_not_applicable(answer, gate):
    record, _ = evaluated(answers=answer, follow="WEAK_OR_STALLING")
    assert record.hard_gate is gate and record.satisfied_count is None and record.outstanding_count is None


@pytest.mark.parametrize(("record", "gate"), [
    (source(answers={"Q7": "UNCLEAR"}), HardGate.WO07F_INSUFFICIENT),
    (source(prerequisites=ReconciliationPrerequisites(answer_accepted=False)),
     HardGate.WO07F_NOT_RECONCILABLE),
])
def test_remaining_wo07f_hard_gates_are_not_zero_scores(record, gate):
    result, requirements = evaluate_readiness(record, evidence(), created_at=NOW)
    assert result.hard_gate is gate
    assert result.satisfied_count is None and result.outstanding_count is None
    assert all(item.criterion.state is CriterionState.NOT_APPLICABLE for item in requirements)


@pytest.mark.parametrize(("field", "gate"), [
    ("governing_15m_structure_failed", HardGate.GOVERNING_15M_STRUCTURE_FAILED),
    ("authoritative_directional_conflict", HardGate.AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT),
    ("exact_binding_valid", HardGate.INVALID_EXACT_EVIDENCE_BINDING),
])
def test_machine_and_binding_hard_gates(field, gate):
    record, _ = evaluated(**{field: False if field == "exact_binding_valid" else True})
    assert record.hard_gate is gate


def test_machine_source_identity_is_exactly_bound():
    record, _ = evaluate_readiness(
        source(), evidence(machine_evidence_identity="different-machine-source"),
        created_at=NOW,
    )
    assert record.hard_gate is HardGate.INVALID_EXACT_EVIDENCE_BINDING


def test_natgas_held_is_hard_gate():
    record = source(direction="SHORT")
    e = evidence(subject="MCX-SUBJECT-NATGAS", direction="SHORT", market_family="MCX",
                 exact_mcx_contract_identity="MCX:NATGAS:202610",
                 exact_mcx_roll_lineage="ROLL-1", natgas_commissioning_state="HELD")
    result, _ = evaluate_readiness(record, e, created_at=NOW)
    assert result.hard_gate is HardGate.NATGAS_COMMISSIONING_HELD


def test_mcx_exact_contract_is_preserved_and_missing_native_criteria_fail_closed():
    native_answers = {
        "M1": "SUPPORTIVE", "M2": "CLEAN_DIRECTIONAL_STRUCTURE",
        "M3": "CLEAR_FOLLOW_THROUGH", "M4": "ORDERLY", "M5": "NOT_OBSERVABLE",
    }
    def mcx_observation(question, answer):
        return VisualObservationV2(
            question.question_id, ObservationStatus.OBSERVED, answer,
            question.timeframe_scope, "visible", None, None,
        )
    mcx = create_reconciliation_record(
        VisualReconciliationInput(
            "MCX-SUBJECT-CRUDE", "SHORT", "run", "result", "cycle", "pack",
            "chart", "answer", "a" * 64, "visual", "correspondence",
            ("machine", "MCX:CRUDE:202610", "ROLL-1"),
            tuple(
                mcx_observation(q, native_answers[q.question_id])
                for q in MCX_QUESTIONS if q.question_id.startswith("M")
            ),
            native_market=NativeMarketAuthority.MCX,
            supporting_reference_observations=tuple(
                mcx_observation(q, "NONE" if q.question_id == "X5" else q.allowed_answers[0])
                for q in MCX_QUESTIONS
                if q.question_id.startswith("R") or q.question_id.startswith("X")
            ),
            supporting_reference_authority="SUPPORTING_VISUAL_CONTEXT_ONLY",
            supporting_reference_independence="NOT_INDEPENDENTLY_ESTABLISHED",
        ),
        created_at=NOW,
    )
    e = evidence(
        subject="MCX-SUBJECT-CRUDE", direction="SHORT", market_family="MCX",
        space=None, extension=None, exact_mcx_contract_identity="MCX:CRUDE:202610",
        exact_mcx_roll_lineage="ROLL-1",
    )
    result, _ = evaluate_readiness(mcx, e, created_at=NOW)
    assert result.exact_mcx_contract_identity == "MCX:CRUDE:202610"
    assert result.exact_mcx_roll_lineage == "ROLL-1"
    assert result.criteria[2].state is CriterionState.UNAVAILABLE
    assert result.criteria[4].state is CriterionState.UNAVAILABLE
    assert result.readiness_state is ReadinessState.READINESS_UNAVAILABLE


def test_historical_eligibility_spelling_and_adapter_are_preserved():
    record = source()
    assert record.downstream_eligibility.value == HISTORICAL_ELIGIBILITY_VALUE
    assert Wo07fCompatibilityAdapter.eligible(record)


def test_monitorability_and_forbidden_authority():
    record, requirements = evaluated(space="OBSTACLE_CLOSE")
    i1, _, i3, i4, i5 = (item.criterion for item in requirements)
    assert Monitorability.COMPLETED_CANDLE_REQUIRED in i1.monitorability
    assert Monitorability.NO_AUTOMATIC_NUMERIC_WATCH in i3.monitorability
    assert Monitorability.WO07F_RECONCILIATION_REQUIRED in i4.monitorability
    assert Monitorability.WO07F_RECONCILIATION_REQUIRED in i5.monitorability
    assert "BROKER_AUTHORITY" in record.authority and record.outstanding_count == 1
    assert requirements[2].watch_identity is not None
    assert all(
        item.watch_identity is None
        for item in requirements if item.criterion.state is CriterionState.SATISFIED
    )


def test_persistence_idempotency_conflict_supersession_and_restoration(tmp_path):
    store = Wo09Store(tmp_path)
    record, reqs = evaluated(space="OBSTACLE_CLOSE")
    first = store.retain(record, reqs)
    assert store.retain(record, reqs) == first
    assert store.restore_current()[0][1] == record
    assert store.load_requirements(record.readiness_identity) == reqs
    newer, newer_reqs = evaluate_readiness(source(), evidence(space="LIMITED_SPACE"), created_at=NOW.replace(minute=1))
    pointer = store.retain(newer, newer_reqs)
    assert pointer.superseded_readiness_identity == record.readiness_identity
    assert store.load_readiness(record.readiness_identity) == record
    assert store.load_requirements(record.readiness_identity) == reqs
    with pytest.raises(Wo09PersistenceError, match="NON_FORWARD_SUPERSESSION"):
        store.retain(record, reqs)
    path = store.readiness / f"{record.readiness_identity}.json"
    path.write_bytes(b"{}")
    with pytest.raises(Wo09PersistenceError, match="IMMUTABILITY_CONFLICT"):
        store.retain(record, reqs)


def test_reassessment_pointer_preserves_snapshot(tmp_path):
    app = IntradayWo09Application(Wo09Store(tmp_path))
    record, requirements = evaluated()
    app.store.retain(record, requirements)
    pointer = app.mark_reassessment_due(record.canonical_subject_identity, at=NOW.replace(minute=2))
    assert pointer.currentness is CurrentnessState.REASSESSMENT_DUE
    assert app.store.load_readiness(record.readiness_identity).currentness is CurrentnessState.CURRENT
    assert app.store.load_notifications()[0].state.value == "STALE"


def test_watch_lifecycle_disconnect_and_no_tick_promotion(tmp_path):
    app = IntradayWo09Application(Wo09Store(tmp_path))
    record, reqs = evaluate_readiness(
        source(answers={"Q3": "WEAK_OR_MIXED_BASE", "Q7": "OBSTACLE_CLOSE"}),
        evidence(space="OBSTACLE_CLOSE"), created_at=NOW,
    )
    app.store.retain(record, reqs)
    assert record.readiness_state is ReadinessState.NEAR_READY
    watches = app.register_reassessment_watches(record, reqs, at=NOW)
    assert len(watches) == 2 and all(item.state is WatchState.ACTIVE for item in watches)
    with pytest.raises(ValueError, match="TICK_CANNOT_PROMOTE"):
        transition_watch(watches[0], WatchState.TRIGGERED, at=NOW)
    triggered = app.record_reassessment_event(
        record, watches[0], at=NOW.replace(second=1),
        governed_event_evidence_identity="governed-event",
    )
    event = project_reassessment_notification(
        record, triggered, effective_at=NOW.replace(second=1)
    )
    assert event.notification_type == "CRITERION_REASSESSMENT_EVENT:I3"
    assert app.store.load_readiness(record.readiness_identity) == record
    stale = mark_disconnect_gap(watches[0], at=NOW.replace(minute=1))
    assert stale.state is WatchState.STALE
    with pytest.raises(ValueError, match="REACQUISITION_REQUIRED"):
        transition_watch(stale, WatchState.ACTIVE, at=NOW.replace(minute=2))
    restored = transition_watch(stale, WatchState.ACTIVE, at=NOW.replace(minute=2), reacquisition_identity="fresh")
    assert restored.state is WatchState.ACTIVE
    with pytest.raises(ValueError, match="TRANSITION_TIME_INVALID"):
        transition_watch(restored, WatchState.INACTIVE, at=NOW)


def test_notification_dedup_priority_and_no_focus_suppression():
    no_focus, _ = evaluated(space="OBSTACLE_CLOSE", extension="VISIBLY_EXTENDED", follow="MIXED")
    assert project_notification(no_focus) is None
    ready, _ = evaluated(space="OBSTACLE_CLOSE")
    source_item = project_notification(ready)
    assert source_item is not None and source_item.priority == "HIGH"
    assert deduplicate_sources((source_item, source_item)) == (source_item,)


def test_durable_notification_centre_accepts_intraday_source_without_provider(tmp_path):
    ready, _ = evaluated(space="OBSTACLE_CLOSE")
    source_item = project_notification(ready)
    centre = SponsorNotificationCentre(SponsorNotificationLifecycleStore(tmp_path / "centre"), clock=lambda: NOW)
    snapshot = centre.synchronize_wo09((source_item,), websocket_state="DISCONNECTED")
    record = snapshot.records[0]
    assert record.product == "INTRADAY" and record.source_kind == "INTRADAY_WO09"
    assert record.action_path == "/intraday/wo09" and snapshot.websocket_state == "DISCONNECTED"
    restored = SponsorNotificationCentre(
        SponsorNotificationLifecycleStore(tmp_path / "centre"), clock=lambda: NOW
    ).synchronize_wo09((source_item,), websocket_state="DISCONNECTED")
    assert restored.records == snapshot.records
    withdrawn = centre.synchronize_wo09((), websocket_state="DISCONNECTED")
    assert withdrawn.records[0].state.value == "EXPIRED"


def test_browser_projects_persisted_authority_and_progressive_details():
    record, reqs = evaluated(space="OBSTACLE_CLOSE")
    card = project_card(record, reqs)
    assert card.score == "4 / 5" and card.highest_priority_outstanding == ("I3",)
    details = project_analysis_details(record, reqs)
    assert tuple(details) == (
        "A. WHAT NATIVE / MACHINE ANALYSIS SAYS", "B. WHAT CHART ANALYST SAYS",
        "C. WHAT WO-07F RECONCILED", "D. WHAT WO-09 READINESS SAYS",
        "E. REQUIREMENTS TO PROGRESS", "F. WHAT HAPPENS NEXT", "G. TECHNICAL EVIDENCE",
    )
    assert details["B. WHAT CHART ANALYST SAYS"]["criteria"]["I3"] == "OBSTACLE_CLOSE"
    assert details["G. TECHNICAL EVIDENCE"]["answer_source_sha256"] == "a" * 64
    assert active_attention_cards((card,)) == (card,)
    no_focus, no_focus_requirements = evaluated(
        follow="MIXED", space="OBSTACLE_CLOSE", extension="VISIBLY_EXTENDED"
    )
    assert active_attention_cards((project_card(no_focus, no_focus_requirements),)) == ()


def test_next_wo_handoff_only_for_now_and_contains_no_trade_fields():
    now_record, _ = evaluated()
    handoff = create_next_wo_handoff(
        now_record, created_at=NOW,
        current_readiness_identity=now_record.readiness_identity,
        current_pointer_integrity="pointer-integrity",
        currentness=CurrentnessState.CURRENT,
        superseded_readiness_identity=None,
    )
    assert handoff.satisfied_count == 5 and handoff.readiness_state is ReadinessState.BUY_NOW
    assert handoff.current_readiness_identity == now_record.readiness_identity
    assert not {"entry", "stop", "target", "quantity", "risk", "broker"}.intersection(handoff.__slots__)
    ready, _ = evaluated(space="OBSTACLE_CLOSE")
    with pytest.raises(ValueError, match="HANDOFF_INVALID"):
        create_next_wo_handoff(
            ready, created_at=NOW,
            current_readiness_identity=ready.readiness_identity,
            current_pointer_integrity="pointer-integrity",
            currentness=CurrentnessState.CURRENT,
            superseded_readiness_identity=None,
        )


def test_application_handoff_binds_current_pointer_and_restores(tmp_path):
    app = IntradayWo09Application(Wo09Store(tmp_path))
    record, requirements = evaluated()
    app.store.retain(record, requirements)
    handoff = app.create_handoff(record, created_at=NOW)
    pointer = app.store.load_pointer(record.canonical_subject_identity)
    assert pointer is not None
    assert handoff.current_pointer_integrity == pointer.integrity_identity
    assert app.store.load_handoff(handoff.handoff_identity) == handoff
    app.mark_reassessment_due(record.canonical_subject_identity, at=NOW.replace(minute=1))
    with pytest.raises(ValueError, match="SOURCE_NOT_CURRENT"):
        app.create_handoff(record, created_at=NOW.replace(minute=2))


@pytest.mark.parametrize(("subject", "answers", "follow", "space", "extension", "expected"), [
    ("NSE-EQ-YESBANK", {"Q3": "WEAK_OR_MIXED_BASE", "Q7": "OBSTACLE_CLOSE", "Q8": "VISIBLY_EXTENDED"}, "CLEAR_FOLLOW_THROUGH", "OBSTACLE_CLOSE", "VISIBLY_EXTENDED", (2, "NO_FOCUS")),
    ("NSE-EQ-JUBLFOOD", {"Q1": "MIXED", "Q3": "WEAK_OR_MIXED_BASE", "Q7": "OBSTACLE_CLOSE"}, "CLEAR_FOLLOW_THROUGH", "OBSTACLE_CLOSE", "NOT_VISIBLY_EXTENDED", (3, "NEAR_READY")),
    ("NSE-EQ-VEDL", {"Q1": "MIXED", "Q3": "NO_CLEAR_BASE", "Q7": "OBSTACLE_CLOSE", "Q8": "VISIBLY_EXTENDED"}, "CLEAR_FOLLOW_THROUGH", "OBSTACLE_CLOSE", "VISIBLY_EXTENDED", (2, "NO_FOCUS")),
    ("NSE-EQ-NTPC", {"Q1": "MIXED", "Q2": "CONGESTED_STRUCTURE", "Q4": "WEAK_OR_STALLING", "Q5": "MIXED", "Q7": "OBSTACLE_CLOSE"}, "WEAK_OR_STALLING", "OBSTACLE_CLOSE", "NOT_VISIBLY_EXTENDED", (2, "NO_FOCUS")),
    ("NSE-EQ-INDIGO", {"Q3": "NO_CLEAR_BASE", "Q7": "OBSTACLE_CLOSE", "Q8": "VISIBLY_EXTENDED"}, "CLEAR_FOLLOW_THROUGH", "OBSTACLE_CLOSE", "VISIBLY_EXTENDED", (2, "NO_FOCUS")),
    ("NSE-EQ-MOTHERSON", {"Q1": "MIXED", "Q2": "CONGESTED_STRUCTURE", "Q4": "WEAK_OR_STALLING", "Q5": "MIXED", "Q7": "OBSTACLE_CLOSE"}, "WEAK_OR_STALLING", "OBSTACLE_CLOSE", "NOT_VISIBLY_EXTENDED", (2, "NO_FOCUS")),
    ("NSE-EQ-LUPIN", {"Q2": "MIXED_STRUCTURE", "Q3": "WEAK_OR_MIXED_BASE", "Q4": "MIXED", "Q7": "OBSTACLE_CLOSE", "Q8": "VISIBLY_EXTENDED"}, "MIXED", "OBSTACLE_CLOSE", "VISIBLY_EXTENDED", (1, "NO_FOCUS")),
])
def test_ordered_current_seven_policy_mapping(subject, answers, follow, space, extension, expected):
    record = source(subject=subject, direction="SHORT", answers=answers)
    result, _ = evaluate_readiness(record, evidence(subject=subject, direction="SHORT", follow=follow,
                                                    space=space, extension=extension), created_at=NOW)
    assert (result.satisfied_count, result.readiness_state.value) == expected


def test_nifty_contradicted_is_hard_gated():
    record = source(subject="NSE-INDEX-NIFTY", answers={"Q4": "FAILED_OR_RETURNED_THROUGH"})
    result, _ = evaluate_readiness(record, evidence(subject="NSE-INDEX-NIFTY", follow="FAILED_OR_RETURNED_THROUGH"), created_at=NOW)
    assert result.hard_gate is HardGate.WO07F_CONTRADICTED
    assert result.satisfied_count is None


def test_runtime_composes_inert_wo09_owner_and_historical_wo12(tmp_path):
    shared, provider, factory_calls = _shared()
    runtime = create_intraday_runtime(shared, evidence_root=tmp_path.resolve())
    assert runtime.promotion_readiness_owner == "INTRADAY_WO09"
    assert runtime.wo09_application.store is runtime.wo09_store
    assert runtime.wo09_application.restore() == ()
    assert not runtime.wo09_store.root.exists()
    assert runtime.wo12_v2_runtime.prospective_execution_enabled is False
    assert runtime.wo12_v2_runtime.status.state == "NOT_YET_RUN"
    assert provider.capability.calls == 0 and provider.begin_count == 0 and factory_calls == []


def test_browser_route_reads_persisted_cards_without_calculation(tmp_path):
    store = Wo09Store(tmp_path.resolve())
    app = IntradayWo09Application(store)
    record, requirements = evaluated(answers={"Q7": "OBSTACLE_CLOSE"}, space="OBSTACLE_CLOSE")
    store.retain(record, requirements)
    projection = IntradayWo09Projection(store)
    status = projection.status_document()
    assert status["calculations"] == 0 and status["provider_calls"] == 0
    routes = IntradayBrowserRoutes(create_intraday_workstation(), wo09_projection=projection)
    response = routes.handle_get(BrowserGetRequest(WO09_PRODUCT_ROUTE, {}), _snapshot)
    assert response is not None and response.status.value == 200
    assert "Governed Promotion &amp; Active Readiness" in response.body
    assert "BUY_READY" in response.body and "4 / 5" in response.body
    assert "A. WHAT NATIVE / MACHINE ANALYSIS SAYS" in response.body
    assert "G. TECHNICAL EVIDENCE" in response.body
    app.mark_reassessment_due("NSE-EQ-TEST", at=NOW.replace(minute=2))
    status = projection.status_document()
    assert status["cards"][0].monitorability_state == "REASSESSMENT_DUE"
    assert status["cards"][0].next_action == "GOVERNED_REASSESSMENT_REQUIRED"
