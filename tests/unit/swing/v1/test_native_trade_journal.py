from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecycleState,
    ActiveTradeLifecycleService,
    GovernedLifecycleObservation,
    LifecycleEventType,
    LocalActiveTradeLifecycleStore,
    TradeExitReason,
)
from kronos.swing.v1.native_sponsor_decision import (
    SponsorTradeChoice,
    create_trade_plan_business_judgment,
    initiate_sponsor_decision,
    record_trade_plan_risk_result,
)
from kronos.swing.v1.native_trade_construction import construct_trade_plan
from kronos.swing.v1.native_trade_journal import (
    FactualOutcome,
    JournalRecordType,
    LocalTradeJournalStore,
    TRADE_JOURNAL_CONTRACT_ID,
    TradeJournalService,
)
from kronos.swing.v1.step32 import RiskState
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.swing.v1.native_review import NativeLayer2EvidenceState, NativeReviewEvidenceStore
from tests.unit.swing.v1.test_native_readiness import _complete_visual_pairs
from tests.unit.swing.v1.test_native_review import _evidence_run, _layer2
from tests.unit.swing.v1.test_native_sponsor_decision import NOW, _go
from tests.unit.swing.v1.test_native_trade_construction import (
    _context,
    _inverse_ready,
    _package,
    _ready,
)


def _observation(position, number, price, *, continuous=True):  # type: ignore[no-untyped-def]
    stamp = NOW + timedelta(minutes=number)
    return GovernedLifecycleObservation(
        f"JOURNAL-OBS-{number}", position.canonical_instrument, Decimal(price),
        stamp, stamp, "KITE_CONNECT_WEBSOCKET", "JOURNAL-CONNECTION", number,
        continuous, continuous, continuous, "NSE-CM", "NSE-CALENDAR-2026",
        "2026.1", "NSE-SESSION", "NSE-WINDOW",
        ("KITE_CONNECT_WEBSOCKET", "DOMAIN-002", "DOMAIN-008"),
    )


def _short_go():  # type: ignore[no-untyped-def]
    readiness, requirement = _inverse_ready()
    context = _context(requirement.canonical_instrument)
    plan = construct_trade_plan(
        requirement, readiness, _package(requirement, readiness), context,
        created_at=NOW,
    )
    judgment = create_trade_plan_business_judgment(
        plan, validation_identity="JOURNAL-SHORT", created_at=NOW,
    )
    risk = record_trade_plan_risk_result(
        plan, judgment, RiskState.APPROVED, reason="APPROVED", evaluated_at=NOW,
    )
    result = initiate_sponsor_decision(
        plan, judgment, risk, context, SponsorTradeChoice.PAPER,
        current_trade_plan_id=plan.trade_plan_id, decided_at=NOW,
    )
    return result, plan, readiness


def _run_paper(tmp_path, *, exit_price="122", manual=False, short=False):  # type: ignore[no-untyped-def]
    if short:
        result, plan, readiness = _short_go()
        pre_entry, crossing = "96", "94"
    else:
        result, plan, *_ = _go(SponsorTradeChoice.PAPER)
        readiness, _ = _ready()
        pre_entry, crossing = "99", "102"
    lifecycle = ActiveTradeLifecycleService(
        LocalActiveTradeLifecycleStore((tmp_path / "lifecycle").resolve())
    )
    position = lifecycle.register(result, plan)
    lifecycle.observe(position.position_id, _observation(position, 1, pre_entry))
    active = lifecycle.observe(position.position_id, _observation(position, 2, crossing))
    if manual:
        closure = lifecycle.manual_paper_exit(
            active.position_id, _observation(active, 2, crossing),
        )
    else:
        lifecycle.observe(active.position_id, _observation(active, 3, exit_price))
        closure = lifecycle.snapshot().closures[0]
    journal = TradeJournalService(LocalTradeJournalStore((tmp_path / "journal").resolve()))
    snapshot = journal.reconcile((plan,), (readiness,), (result,), lifecycle.snapshot())
    return snapshot, journal, lifecycle, closure, result, plan, readiness


def test_completed_paper_target_becomes_immutable_journal_with_model_actual_separation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    snapshot, *_ = _run_paper(tmp_path)
    record = snapshot.records[0]
    assert record.contract_identity == TRADE_JOURNAL_CONTRACT_ID
    assert record.record_type is JournalRecordType.TRADE
    assert record.mode is SponsorTradeChoice.PAPER
    assert record.model_entry == Decimal("100.00")
    assert record.actual_entry == Decimal("102")
    assert record.model_target == Decimal("120.00")
    assert record.actual_exit == Decimal("122")
    assert record.model_risk_reward == Decimal("2")
    assert record.realised_r != record.model_risk_reward
    assert record.accounting_basis == "OBSERVATION_BASED_PAPER_ACCOUNTING"
    assert record.outcome is FactualOutcome.POSITIVE_PNL


def test_paper_stop_negative_flat_and_short_inverse_arithmetic(tmp_path) -> None:  # type: ignore[no-untyped-def]
    stopped, *_ = _run_paper(tmp_path / "stop", exit_price="88")
    assert stopped.records[0].outcome is FactualOutcome.NEGATIVE_PNL
    assert stopped.records[0].gross_pnl < 0
    short, *_ = _run_paper(tmp_path / "short", exit_price="79", short=True)
    assert short.records[0].direction is V1Direction.SHORT
    assert short.records[0].gross_pnl > 0
    # Factual zero has no hidden threshold.
    manual, *_ = _run_paper(tmp_path / "flat", manual=True)
    assert manual.records[0].outcome is FactualOutcome.FLAT_PNL


def test_live_closure_retains_sponsor_attested_fill_and_lifecycle(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result, plan, *_ = _go(
        SponsorTradeChoice.LIVE, actual_live_entry=Decimal("101"), live_lots=2,
    )
    readiness, _ = _ready()
    lifecycle = ActiveTradeLifecycleService(
        LocalActiveTradeLifecycleStore((tmp_path / "lifecycle").resolve())
    )
    position = lifecycle.register(result, plan)
    lifecycle.observe(position.position_id, _observation(position, 1, "122"))
    assert lifecycle.snapshot().positions[0].state is ActiveLifecycleState.LIVE_ACTIVE
    closure = lifecycle.record_live_exit(
        position.position_id, actual_exit=Decimal("121.5"),
        exit_timestamp=NOW + timedelta(minutes=2),
        reason=TradeExitReason.SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION,
    )
    journal = TradeJournalService(LocalTradeJournalStore((tmp_path / "journal").resolve()))
    record = journal.reconcile((plan,), (readiness,), (result,), lifecycle.snapshot()).records[0]
    assert closure is not None
    assert record.mode is SponsorTradeChoice.LIVE
    assert record.accounting_basis == "SPONSOR_ATTESTED_ACTUAL_BROKER_EXECUTION"
    assert LifecycleEventType.TARGET_HIT in record.observed_events
    assert record.actual_exit == Decimal("121.5")


def test_ignore_creates_history_without_position_entry_exit_or_pnl(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result, plan, *_ = _go(SponsorTradeChoice.IGNORE)
    readiness, _ = _ready()
    journal = TradeJournalService(LocalTradeJournalStore(tmp_path.resolve()))
    snapshot = journal.reconcile((plan,), (readiness,), (result,), _empty_lifecycle())
    record = snapshot.records[0]
    assert record.record_type is JournalRecordType.IGNORED_OPPORTUNITY
    assert record.mode is SponsorTradeChoice.IGNORE
    assert record.actual_entry is record.actual_exit is record.gross_pnl is None
    assert record.outcome is FactualOutcome.OUTCOME_UNAVAILABLE
    assert snapshot.analytics.total_completed_trades == 0
    assert snapshot.analytics.ignored_opportunities == 1
    assert snapshot.analytics.win_rate is None


def test_idempotency_restart_analytics_and_grouping_do_not_double_count(tmp_path) -> None:  # type: ignore[no-untyped-def]
    snapshot, journal, lifecycle, _, result, plan, readiness = _run_paper(tmp_path)
    repeated = journal.reconcile((plan,), (readiness,), (result,), lifecycle.snapshot())
    restored_service = TradeJournalService(LocalTradeJournalStore((tmp_path / "journal").resolve()))
    restored = restored_service.reconcile(
        (plan,), (readiness,), (result,), lifecycle.snapshot(),
    )
    assert repeated == restored == snapshot
    analytics = restored.analytics
    assert analytics.total_completed_trades == analytics.paper_trades == 1
    assert analytics.live_trades == analytics.ignored_opportunities == 0
    assert analytics.positive_results == 1 and analytics.win_rate == Decimal("100")
    assert analytics.total_gross_pnl == restored.records[0].gross_pnl
    assert analytics.total_realised_r == restored.records[0].realised_r
    assert {item.dimension for item in analytics.breakdowns} == {
        "SETUP", "DIRECTION", "MODE", "INSTRUMENT",
    }
    assert restored.validation.opportunities_reviewed == 1
    assert restored.validation.ready_for_trade_construction == 1
    assert restored.validation.trade_plans_produced == 1
    assert restored.validation.paper_entries_triggered == 1
    assert restored.validation.paper_trades_closed == 1


def test_event_unresolved_never_fabricates_journal_outcome(tmp_path) -> None:  # type: ignore[no-untyped-def]
    result, plan, *_ = _go(SponsorTradeChoice.PAPER)
    readiness, _ = _ready()
    lifecycle = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore((tmp_path / "lifecycle").resolve()))
    position = lifecycle.register(result, plan)
    lifecycle.observe(position.position_id, _observation(position, 1, "99"))
    lifecycle.observe(position.position_id, _observation(position, 2, "122", continuous=False))
    journal = TradeJournalService(LocalTradeJournalStore((tmp_path / "journal").resolve()))
    snapshot = journal.reconcile((plan,), (readiness,), (result,), lifecycle.snapshot())
    assert snapshot.records == ()
    assert snapshot.analytics.total_completed_trades == 0


def test_mismatched_immutable_chain_fails_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    snapshot, _, lifecycle, _, result, plan, _ = _run_paper(tmp_path / "good")
    foreign_readiness, _ = _inverse_ready()
    journal = TradeJournalService(LocalTradeJournalStore((tmp_path / "bad").resolve()))
    with pytest.raises(ValueError, match="READINESS_BINDING_INVALID"):
        journal.reconcile((plan,), (foreign_readiness,), (result,), lifecycle.snapshot())
    assert snapshot.records[0].integrity_hash


def test_no_openai_broker_or_upstream_mutation_authority() -> None:
    prohibited = {
        "place_order", "modify_order", "cancel_order", "analyze_chart",
        "change_readiness", "change_trade_plan",
    }
    assert prohibited.isdisjoint(dir(TradeJournalService))


def test_full_native_workflow_paper_target_publishes_closed_and_journal_atomically_and_restores(tmp_path) -> None:  # type: ignore[no-untyped-def]
    facts, run, _ = _evidence_run()
    root = tmp_path.resolve()
    workflow = NativeReviewWorkflow(NativeReviewEvidenceStore(root), clock=lambda: NOW)
    prepared = workflow.prepare(run, facts)
    for request, response in _complete_visual_pairs():
        workflow.ingest_visual_v2(request, response)
    requirement = prepared.requirements[0]
    readiness = workflow.ingest_readiness(
        _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS),
        created_at=NOW,
    )
    context = _context(requirement.canonical_instrument)
    plan = workflow.construct_trade_plan(
        requirement.canonical_instrument, _package(requirement, readiness), context,
    )
    judgment = create_trade_plan_business_judgment(
        plan, validation_identity="STEP33-E2E", created_at=NOW,
    )
    risk = record_trade_plan_risk_result(
        plan, judgment, RiskState.APPROVED, reason="APPROVED", evaluated_at=NOW,
    )
    workflow.bind_step32_inputs(plan.trade_plan_id, judgment, risk, context)
    initiated = workflow.initiate_sponsor_decision(plan.trade_plan_id, SponsorTradeChoice.PAPER)
    position = workflow.snapshot().active_lifecycle.active[0]
    assert workflow.snapshot().trade_journal.records == ()
    workflow.record_lifecycle_observation(position.position_id, _observation(position, 1, "99"))
    active = workflow.record_lifecycle_observation(position.position_id, _observation(position, 2, "102"))
    assert active.state is ActiveLifecycleState.PAPER_ACTIVE
    assert workflow.snapshot().trade_journal.records == ()
    closed = workflow.record_lifecycle_observation(position.position_id, _observation(active, 3, "122"))
    final = workflow.snapshot()
    assert closed.state is ActiveLifecycleState.CLOSED
    assert len(final.active_lifecycle.closures) == 1
    assert len(final.trade_journal.records) == 1
    assert final.trade_journal.records[0].sponsor_decision_id == initiated.decision.decision_id
    restored = NativeReviewWorkflow(NativeReviewEvidenceStore(root)).restore(run, facts)
    assert restored.trade_journal == final.trade_journal
    assert restored.active_lifecycle.closures == final.active_lifecycle.closures


def test_restart_preserves_paper_armed_paper_active_and_live_action_required(tmp_path) -> None:  # type: ignore[no-untyped-def]
    paper, paper_plan, *_ = _go(SponsorTradeChoice.PAPER)
    paper_root = (tmp_path / "paper").resolve()
    paper_service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(paper_root))
    armed = paper_service.register(paper, paper_plan)
    assert ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(paper_root)).snapshot().positions[0] == armed
    paper_service.observe(armed.position_id, _observation(armed, 1, "99"))
    active = paper_service.observe(armed.position_id, _observation(armed, 2, "102"))
    restored_active = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(paper_root)).snapshot()
    assert restored_active.positions[0] == active
    assert active.state is ActiveLifecycleState.PAPER_ACTIVE

    live, live_plan, *_ = _go(
        SponsorTradeChoice.LIVE, actual_live_entry=Decimal("101"), live_lots=1,
    )
    live_root = (tmp_path / "live").resolve()
    live_service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(live_root))
    live_position = live_service.register(live, live_plan)
    live_service.observe(live_position.position_id, _observation(live_position, 1, "122"))
    before = live_service.snapshot()
    restored_live = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(live_root)).snapshot()
    assert restored_live == before
    assert restored_live.positions[0].state is ActiveLifecycleState.LIVE_ACTIVE
    assert restored_live.notifications[0].action_required is True


def _empty_lifecycle():
    from kronos.swing.v1.native_active_trade_lifecycle import ActiveTradeLifecycleSnapshot
    return ActiveTradeLifecycleSnapshot((), (), (), ())
