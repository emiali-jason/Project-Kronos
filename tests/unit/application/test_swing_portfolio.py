"""WO-15 uses canonical owners; fixtures confer no live acceptance authority."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from threading import RLock
from types import SimpleNamespace

import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_portfolio import read_swing_portfolio, _groups
from kronos.application.swing_v1_browser import SwingV1BrowserOperationalization, BrowserCandidateRecord
from kronos.provider.contracts.monitoring import MonitoringConnectionState
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecycleState, ActiveTradeLifecycleEngine, ActiveTradeLifecycleService,
    LocalActiveTradeLifecycleStore, TradeExitReason,
)
from kronos.swing.v1.native_entry_timing import (
    LocalObjectiveModelV1Store, activate_objective_model_v1, produce_native_ecpc_v2,
    evaluate_kr380_v2, EcpcV2Outcome,
)
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.native_sponsor_decision import initiate_sponsor_decision
from kronos.swing.v1.native_sponsor_decision import (
    create_trade_plan_business_judgment, record_trade_plan_risk_result,
)
from kronos.swing.v1.paper_observation_track import LocalPaperObservationTrackStore, create_paper_observation_track
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.step32 import (
    SponsorDecisionMode, SponsorExecutionEvidence, create_sponsor_position,
    record_sponsor_decision, RiskState,
)
from tests.unit.swing.v1.test_native_active_trade_lifecycle import _position, _observation, NOW
from tests.unit.swing.v1.test_native_entry_timing import _ready, _risk, _observation as _model_observation
from tests.unit.swing.v1.test_native_entry_timing import NOW as MODEL_NOW
from tests.unit.swing.v1.test_paper_observation_track import _blocked
from tests.unit.swing.v1.test_step32_lifecycle import _model_fixture, _NOW
from tests.unit.swing.v1.test_kr370_step31_handoff import _context
from tests.unit.browser.test_browser_reports import _empty_mcx_reports_owner
from tests.unit.browser.test_wo14_mcx_journal_integration import fixture as mcx_fixture, START
from tests.unit.browser.test_swing_reports_wo16 import seed_live_attestation
from tests.unit.application.test_mcx_dedicated_exit_cleanup import paper_fixture


def window(root):
    return SimpleNamespace(
        _objective_model_store=LocalObjectiveModelV1Store(root / "models"),
        _production_models={}, _plans={}, _projection_lock=RLock(),
        _paper_observation_tracking=SimpleNamespace(_store=LocalPaperObservationTrackStore(root / "tracks")),
        reports_generation=lambda: 0,
    )


def native_owner(root, *, entered=False, live=False):
    lifecycle = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root / "lifecycle"))
    position, result, plan = _position(
        SponsorTradeChoice.LIVE if live else SponsorTradeChoice.PAPER,
        **(dict(actual_live_entry=Decimal("103.25"), live_lots=3) if live else {}))
    lifecycle.register(result, plan)
    if entered and not live:
        lifecycle.observe(position.position_id, _observation(position, 1, "99"))
        lifecycle.observe(position.position_id, _observation(position, 2, "102"))
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(root / "review"),
                                  active_lifecycle_service=lifecycle)
    return native, lifecycle.snapshot().positions[0]


def read(native, source, mcx, *, as_of=NOW + timedelta(days=1), step32=None, **filters):
    return read_swing_portfolio(native, step32 or SwingV1BrowserOperationalization(),
        as_of=as_of, trade_window=source, mcx_control=mcx, **filters)


def inventory(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns,
                                         path.stat().st_mode, path.stat().st_ino)
            for path in root.rglob("*") if path.is_file()}


def test_empty_is_verified_only_when_position_owners_loaded(tmp_path):
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    source = window(tmp_path / "window")
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    before = inventory(tmp_path)
    book = read(native, source, mcx)
    assert book.available and not book.positions and not book.exposure_groups
    assert book.coverage["position_sources_complete"]
    assert not book.coverage["current_plan_sources_complete"]
    assert book.coverage["monetary_total"] is None
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("missing", ["native", "window", "mcx", "models"])
def test_absent_required_owner_is_unavailable_never_empty(tmp_path, missing):
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    source = window(tmp_path / "window")
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    if missing == "native":
        native = None
    elif missing == "window":
        source = None
    elif missing == "mcx":
        mcx = None
    else:
        source._objective_model_store = None
    book = read(native, source, mcx)
    assert not book.available and book.source_status == "UNAVAILABLE"
    assert not book.coverage["source_complete"]
    assert book.coverage["monetary_total"] is None


@pytest.mark.parametrize("entered", [False, True])
def test_outage_and_restart_preserve_actual_waiting_or_entered_truth(tmp_path, entered):
    native, position = native_owner(tmp_path / "native", entered=entered)
    lifecycle = native._active_lifecycle
    lifecycle.monitoring_unavailable(position.position_id,
        occurred_at=NOW + timedelta(minutes=4), provider_context="ISOLATED_OUTAGE")
    source = window(tmp_path / "window")
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    before = inventory(tmp_path)
    first = read(native, source, mcx)
    assert first.available and len(first.positions) == int(entered)
    assert len(first.waiting_plans) == int(not entered)
    row = (first.positions or first.waiting_plans)[0]
    assert row["monitoring"] == "INTERRUPTED"
    assert row["current_price"] is None
    assert row["entry"] == (Decimal("102") if entered else None)
    assert row["last_price"] == (Decimal("102") if entered else None)
    assert "MONITORING INTERRUPTED" in row["attention"]
    restored = ActiveTradeLifecycleService(lifecycle.store)
    native._active_lifecycle = restored
    native._active_lifecycle_monitoring._service = restored
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    assert read(native, source, mcx) == first
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("market", ["NSE", *tuple(McxFamily)])
def test_each_market_keeps_exact_position_once_and_unknown_economics(tmp_path, market):
    if market == "NSE":
        native, position = native_owner(tmp_path / "native", entered=True)
        mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
        exact = None
    else:
        mcx, position, _, exact = mcx_fixture(tmp_path / "mcx", market, active=True)
        native = mcx.native_review
    source = window(tmp_path / "window")
    before = inventory(tmp_path)
    book = read(native, source, mcx, as_of=START + timedelta(days=1))
    assert book.available
    assert len(book.positions) == sum(group["position_count"] for group in book.exposure_groups) == 1
    row, = book.positions
    assert row["identity"] == position.position_id and row["exposure"]
    assert row["entry"] == position.actual_entry
    assert row["monetary_value"] is row["monetary_multiplier"] is None
    assert row["current_price"] is None
    if exact is not None:
        assert row["contract"] == exact.contract_symbol and row["expiry"] == exact.expiry
        assert row["market"] == "MCX" and row["family"] == market.value
        assert row["units"] is None and row["lots"] == position.lots
        assert book.exposure_groups[0]["known_units"] is None
    else:
        assert row["market"] == "NSE" and row["units"] == position.underlying_quantity
    assert read(native, source, mcx, as_of=START + timedelta(days=1)) == book
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("family", tuple(McxFamily))
def test_manual_live_attestation_is_required_and_remains_unverified(tmp_path, family):
    mcx, position, _, plan = mcx_fixture(tmp_path / "mcx", family, live=True)
    source = window(tmp_path / "window")
    assert not read(mcx.native_review, source, mcx, as_of=START).available
    seed_live_attestation(mcx, position, plan, tmp_path / "fills")
    before = inventory(tmp_path)
    book = read(mcx.native_review, source, mcx, as_of=START)
    assert book.available
    row, = book.positions
    assert row["entry"] == Decimal("103.25") and row["lots"] == 3
    assert ("LIVE evidence origin", "SPONSOR_SUBMITTED_UNVERIFIED") in row["evidence"]
    assert row["units"] is None and row["monetary_pnl"] is None
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("family", tuple(McxFamily))
def test_admitted_mcx_quote_uses_exact_live_owner_and_outage_retains_entry(tmp_path, family):
    (mcx, position, instrument, plan, monitor, capability, hub, clock,
     notifications) = paper_fixture(tmp_path / "mcx", family, "LONG")
    source = window(tmp_path / "window")
    try:
        monitor.attach(position.position_id, capability, instrument)
        clock[0] += timedelta(minutes=1)
        capability.tick(102)
        before = inventory(tmp_path)
        book = read(mcx.native_review, source, mcx, as_of=clock[0])
        assert book.available and len(book.positions) == 1
        row, = book.positions
        assert row["entry"] == position.actual_entry
        assert row["current_price"] == Decimal("102")
        assert row["current_price_at"] == clock[0]
        assert row["monitoring"] == "LIVE" and row["source_monitoring"] == "ACTIVE"
        assert row["contract"] == plan.contract_symbol
        assert row["valuation_state"] == "LATEST_ACCEPTED_OBSERVATION_FRESHNESS_UNKNOWN"
        assert row["monetary_value"] is row["monetary_pnl"] is None
        assert inventory(tmp_path) == before
        capability.socket.on_close(capability.socket, 1006, "isolated outage")
        before = inventory(tmp_path)
        interrupted = read(mcx.native_review, source, mcx, as_of=clock[0])
        row, = interrupted.positions
        assert row["monitoring"] == "INTERRUPTED" and row["current_price"] is None
        assert row["last_price"] == Decimal("102")
        assert row["entry"] == position.actual_entry and row["lots"] == position.lots
        assert "KNOWN EXPOSURE RETAINED" in row["attention"]
        assert inventory(tmp_path) == before
    finally:
        monitor.close()


def test_missing_retained_position_with_readable_cache_is_unavailable(tmp_path):
    native, position = native_owner(tmp_path / "native", entered=True)
    source = window(tmp_path / "window")
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    path = native._active_lifecycle.store.root / position.position_id / "position.json"
    path.unlink()
    before = inventory(tmp_path)
    book = read(native, source, mcx)
    assert not book.available
    assert book.issues == ("SWING_PORTFOLIO_RETAINED_LIFECYCLE_CHANGED",)
    assert inventory(tmp_path) == before


def test_missing_current_model_pointer_cannot_erase_known_model_reference(tmp_path):
    native, _ = native_owner(tmp_path / "native", entered=True)
    source = window(tmp_path / "window")
    source._production_models["KNOWN-PLAN"] = SimpleNamespace(
        model_trade_id="KNOWN-MODEL", source_integrity_sha256="a" * 64)
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    before = inventory(tmp_path)
    book = read(native, source, mcx)
    assert not book.available
    assert book.issues == ("SWING_PORTFOLIO_OBJECTIVE_CURRENT_POINTER_UNAVAILABLE",)
    assert inventory(tmp_path) == before


def test_unavailable_current_advisory_run_preserves_historical_position(tmp_path):
    mcx, position, _, plan = mcx_fixture(tmp_path / "mcx", McxFamily.GOLDM, active=True)
    def unavailable():
        raise ValueError("RESERVED_RUN_STALE")
    mcx.workflow = SimpleNamespace(run_identity=plan.native_run_identity,
                                  _current=unavailable)
    source = window(tmp_path / "window")
    before = inventory(tmp_path)
    book = read(mcx.native_review, source, mcx, as_of=START)
    assert book.available and len(book.positions) == 1
    assert book.positions[0]["identity"] == position.position_id
    assert not book.coverage["current_plan_sources_complete"]
    assert book.coverage["position_sources_complete"]
    assert "CURRENT_ADVISORY_SUBSET_UNAVAILABLE" in book.coverage["completeness"]
    assert inventory(tmp_path) == before


def test_current_advisory_enumeration_does_not_scan_unreferenced_historical_plans(tmp_path):
    # Isolate enumeration only; the existing real plan validator owns readiness.
    mcx, _, _, _ = mcx_fixture(tmp_path / "mcx", McxFamily.GOLDM, active=True)
    historical = mcx.plans.root / "OLD-UNREFERENCED-RUN" / "GOLDM" / "bad.json"
    historical.parent.mkdir(parents=True)
    historical.write_text("invalid historical unreferenced bytes")
    current_checks = []
    mcx.workflow = SimpleNamespace(run_identity="CURRENT-EMPTY-RUN",
        _current=lambda: current_checks.append(True))
    source = window(tmp_path / "window")
    before = inventory(tmp_path)
    book = read(mcx.native_review, source, mcx, as_of=START)
    assert book.available and len(book.positions) == 1
    assert book.coverage["current_plan_sources_complete"]
    assert len(current_checks) == 4  # before/after each repeatable source read
    assert inventory(tmp_path) == before


def test_changed_generation_withholds_mixed_book(tmp_path):
    native, _ = native_owner(tmp_path / "native", entered=True)
    source = window(tmp_path / "window")
    values = iter((0, 0, 1, 1))
    source.reports_generation = lambda: next(values)
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    book = read(native, source, mcx)
    assert not book.available and book.issues == ("SWING_PORTFOLIO_SOURCE_CHANGED",)


def test_notification_and_journal_suppression_and_reconciliation_are_not_sources(tmp_path):
    native, _ = native_owner(tmp_path / "native", entered=True)
    source = window(tmp_path / "window")
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    def forbidden(*args, **kwargs):
        raise AssertionError("Portfolio attempted unrelated authority")
    native.journal_current_snapshot = native.reports_journal_snapshot = forbidden
    native._trade_journal = SimpleNamespace(snapshot=forbidden)
    source.reconcile_journal_read_models = forbidden
    source._observation_research_v2 = SimpleNamespace(synchronize=forbidden)
    source._notification_suppression = {"all": True}
    before = inventory(tmp_path)
    book = read(native, source, mcx)
    assert book.available and len(book.positions) == 1
    del source._notification_suppression
    assert read(native, source, mcx) == book
    assert inventory(tmp_path) == before


def test_authoritative_closure_removes_current_exposure_without_journal_repair(tmp_path):
    native, position = native_owner(tmp_path / "native", entered=True)
    source = window(tmp_path / "window")
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    native._active_lifecycle.observe(position.position_id, _observation(position, 3, "122"))
    before = inventory(tmp_path)
    book = read(native, source, mcx)
    assert book.available and not book.positions and not book.exposure_groups
    row, = book.closed_positions
    assert row["state"] == "CLOSED" and row["exit"] == Decimal("122")
    assert row["exit_at"] is not None and row["closure_reason"] == "PAPER_TARGET_HIT"
    assert not row["exposure"]
    assert inventory(tmp_path) == before


def test_live_touch_needs_action_until_factual_manual_closure(tmp_path):
    native, position = native_owner(tmp_path / "native", live=True)
    source = window(tmp_path / "window")
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    native._active_lifecycle.observe(position.position_id, _observation(position, 3, "122"))
    before = inventory(tmp_path)
    active = read(native, source, mcx)
    assert active.available and len(active.positions) == 1
    assert active.positions[0]["attention"].startswith("LIVE ACTION REQUIRED")
    assert active.positions[0]["exit"] is None
    assert inventory(tmp_path) == before
    native._active_lifecycle.record_live_exit(position.position_id,
        actual_exit=Decimal("121"), exit_timestamp=NOW + timedelta(minutes=4),
        reason=TradeExitReason.SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION)
    closed = read(native, source, mcx)
    assert closed.available and not closed.positions
    assert closed.closed_positions[0]["exit"] == Decimal("121")
    assert not closed.closed_positions[0]["attention"].startswith("LIVE ACTION REQUIRED")


def test_native_objective_and_sponsor_are_related_without_summing_model_quantity(tmp_path):
    completed, plan, handoff = _ready(tmp_path / "model")
    risk = _risk(plan, handoff, completed)
    context = produce_native_ecpc_v2(plan, risk, monitoring_binding_id="PORTFOLIO-MONITOR",
        session_identity="NSE-20260821", observation_boundary=plan.observation_boundary,
        outcome=EcpcV2Outcome.QUALIFIED, blockers=())
    outcome = evaluate_kr380_v2(plan, risk, context,
        kr370_source_identity=completed.promotion.integrity_sha256,
        previous=_model_observation(plan, "PORTFOLIO-MONITOR", plan.entry - 1, 1),
        current=_model_observation(plan, "PORTFOLIO-MONITOR", plan.entry, 2),
        evaluated_at=MODEL_NOW + timedelta(minutes=2))
    model = activate_objective_model_v1(plan, outcome,
        monitoring_state=MonitoringConnectionState.CONNECTED)
    judgment = create_trade_plan_business_judgment(plan,
        validation_identity="PORTFOLIO-SPONSOR", created_at=MODEL_NOW)
    approval = record_trade_plan_risk_result(plan, judgment, RiskState.APPROVED,
        reason="APPROVED", evaluated_at=MODEL_NOW)
    result = initiate_sponsor_decision(plan, judgment, approval,
        _context(plan.canonical_instrument), SponsorTradeChoice.PAPER,
        current_trade_plan_id=plan.trade_plan_id, decided_at=MODEL_NOW)
    lifecycle = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(tmp_path / "native-lifecycle"))
    position = lifecycle.register(result, plan)
    for index, price in ((1, plan.entry - 1), (2, plan.entry)):
        stamp = MODEL_NOW + timedelta(minutes=index)
        observation = replace(_observation(position, index, str(price)),
                              observed_at=stamp, observation_boundary=stamp)
        lifecycle.observe(position.position_id, observation)
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"),
                                  active_lifecycle_service=lifecycle)
    source = window(tmp_path / "window")
    source._objective_model_store.retain_current(model)
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    book = read(native, source, mcx, as_of=MODEL_NOW + timedelta(days=1))
    assert book.available and len(book.positions) == len(book.objective_models) == 1
    row, = book.objective_models
    assert row["units"] is row["lots"] is None and not row["exposure"]
    assert sum(group["position_count"] for group in book.exposure_groups) == 1
    assert row["related_positions"] == (position.position_id,)
    assert book.positions[0]["related_models"] == (model.model_trade_id,)


def test_legacy_objective_and_explicit_live_are_validation_only_zero_production_exposure(tmp_path):
    candidate, risk, lifecycle, _, outcome, model = _model_fixture()
    decision = record_sponsor_decision(candidate, risk, lifecycle, SponsorDecisionMode.LIVE,
                                      clock=_NOW)
    evidence = SponsorExecutionEvidence("EVIDENCE-PORTFOLIO", Decimal("101"),
                                       Decimal("2"), _NOW + timedelta(minutes=2))
    sponsor = create_sponsor_position(decision, candidate, risk, model,
                                     actual_evidence=evidence, clock=_NOW + timedelta(minutes=2))
    legacy = SwingV1BrowserOperationalization(recovered_records=(
        BrowserCandidateRecord(candidate, risk=risk, lifecycle=lifecycle,
            sponsor_decision=decision, objective_model=model, sponsor_position=sponsor),))
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    source = window(tmp_path / "window")
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    book = read(native, source, mcx, step32=legacy)
    assert book.available and not book.positions and not book.exposure_groups
    assert len(book.objective_models) == len(book.validation_positions) == 1
    row, = book.validation_positions
    assert row["units"] == Decimal("2") and not row["exposure"]
    assert "VALIDATION ONLY" in row["authority"]


def test_observation_track_reads_metadata_only_and_contributes_zero_exposure(tmp_path, monkeypatch):
    decision = _blocked(tmp_path / "decision")
    track = create_paper_observation_track(decision,
        current_run_identity=decision.snapshot.native_run_identity,
        created_at=decision.decision.decision_timestamp)
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    source = window(tmp_path / "window")
    store = source._paper_observation_tracking._store
    store.retain_track(track)
    monkeypatch.setattr(store, "facts", lambda *args: (_ for _ in ()).throw(
        AssertionError("Portfolio must not read market history")))
    mcx = _empty_mcx_reports_owner(tmp_path / "mcx", native)
    before = inventory(tmp_path)
    book = read(native, source, mcx,
                as_of=decision.decision.decision_timestamp + timedelta(days=1))
    assert book.available and not book.positions and not book.exposure_groups
    row, = book.observations
    assert row["identity"] == track.track_identity and not row["exposure"]
    assert row["state"] == "OBSERVATION_OPEN"
    assert book.coverage["observation_exposure"] == 0
    assert inventory(tmp_path) == before


def test_incompatible_units_and_lots_are_never_summed_across_instruments():
    common = dict(market="NSE", family="NSE", direction="LONG", mode="PAPER",
        expiry=None, quantity_provenance="CANONICAL_SPONSOR_POSITION",
        lots=1, current_price=None)
    groups = _groups([
        common | dict(instrument="NIFTY", contract="NIFTY26OCTFUT", units=65),
        common | dict(instrument="SBIN", contract="SBIN26OCTFUT", units=750),
    ])
    assert len(groups) == 2
    assert {group["known_units"] for group in groups} == {Decimal(65), Decimal(750)}
    assert all(group["known_lots"] == 1 and group["monetary_value"] is None for group in groups)


@pytest.mark.parametrize("filters", [
    {"market": "NFO"}, {"family": "GOLD"}, {"mode": "AUTO"},
    {"state": "ENTER"}, {"direction": "BUY"}, {"monitoring": "CONNECTED"},
    {"search": "x" * 81},
])
def test_filters_fail_closed_before_owner_reads(filters):
    with pytest.raises(ValueError, match="FILTER_INVALID"):
        read(None, None, None, **filters)
