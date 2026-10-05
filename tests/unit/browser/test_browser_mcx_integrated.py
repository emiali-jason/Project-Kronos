"""One isolated MCX path; fixture facts never commission production entry."""

from dataclasses import replace
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from http import HTTPStatus
from io import BytesIO
from threading import Event, Thread
from types import SimpleNamespace
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pytest

from kronos.application.swing_mcx_integrated import SwingMcxIntegratedWorkflow
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.application import swing_opportunities as analysis_application
from kronos.application import swing_analysis_process as process
from kronos.provider.instrument_master_persistence import ProviderInstrumentSnapshotStore
from tests.unit.application.test_swing_opportunities import _Provider
from kronos.browser.server import _BrowserHandler
from kronos.browser.views import _native_active_lifecycle
from kronos.swing.v1.mcx_contract_profile import McxFamily, mcx_unit_profile
from kronos.swing.v1.mcx_quantity import McxQuantityProofOrigin, McxTypedQuantity
from kronos.swing.universe import SwingUniverseAssetClass
from kronos.swing.universe import SWING_PHASE1_UNIVERSE
from kronos.swing.v1 import opportunity_continuity as continuity
from kronos.swing.v1.relative_context import build_relative_context_run
from kronos.swing.v1.mcx_contract_selection import (
    LocalMcxSponsorSelectionStore, McxSelectionRole,
    V1_ADVISORY_SELECTION, prepare_mcx_contract_offer,
)
from kronos.swing.v1.mcx_prepared_plan_store import LocalMcxPreparedPlanStore
from kronos.swing.v1.mcx_trade_plan import (
    LocalMcxTradePlanStore, McxIsolatedAdmissionFacts, McxTradePlanRecord,
    admit_isolated_mcx_paper, construct_isolated_mcx_trade_plan,
    admit_v1_mcx_paper, construct_v1_mcx_advisory_plan, _digest as plan_digest,
)
from kronos.swing.v1.mcx_contract_lifecycle import (
    LocalMcxHistoricalContractStore, McxContractBoundLifecycle,
    McxConfirmedOneHourEntry,
)
from kronos.swing.v1.mcx_live_attestation import (
    LocalMcxLiveFillAttestationStore, McxLiveFillAttestation,
    admit_v1_mcx_manual_live,
)
from kronos.swing.v1.mcx_broker_fill_evidence import (
    LocalMcxBrokerFillEvidenceStore, McxBrokerFillCapture,
)
from kronos.swing.v1.mcx_kr380_issuer import RULE_ID
from kronos.swing.v1.mcx_kr380_issuer import (
    McxContinuityProof, McxCurrentAuthority, McxOneHourCandle,
)
from kronos.swing.v1.mcx_v1_advisory import LocalMcxV1AdvisoryStore
from kronos.swing.v1.mcx_v1_issuer import (
    McxV1SignalReadSet, issue_v1_isolated_signal,
)
from kronos.swing.v1.native_entry_timing import (
    KR380_CONTRACT_ID, KR380_CONTRACT_VERSION, KR380_POLICY_ID,
    KR380_POLICY_VERSION, NO_BROKER_AUTHORITY, Kr380EntryOutcomeV2,
    LocalKr380V2Store,
    Kr380V2State, _values_digest,
)
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecycleState, ActiveLifecycleMonitoringCoordinator,
    ActiveTradeLifecycleService, LocalActiveTradeLifecycleStore,
    TradeExitReason,
)
from kronos.swing.v1.native_sponsor_decision import (
    LocalSponsorDecisionStore, SponsorInitiationState,
    create_trade_plan_business_judgment, record_trade_plan_risk_result,
)
from kronos.swing.v1.step32 import RiskState
from kronos.provider.contracts.monitoring import MonitoringConnectionState, ProviderMarketTick
from kronos.market.calendar import MarketCalendarPublisher
from kronos.swing.v1.mcx_step31_construction import (
    McxContractProofPrerequisites, McxOneHourGeometry, McxProofOrigin,
    McxQuantitySemantics, select_owner_current_mcx_handoff,
)
from tests.unit.application.test_swing_mtf_facts import _instrument
from tests.unit.provider.test_instrument_master_snapshot import NOW as MASTER_NOW, _snapshot
from tests.unit.browser.test_swing_review_intake_binding import _inventory, native_intake
from tests.unit.swing.test_run_publication import make_checkpoint, provenance
from tests.unit.swing.v1.test_mcx_contract_lifecycle import _fixture as historical_fixture, _tick
from tests.unit.swing.v1.test_mcx_contract_selection import _fact
from tests.unit.swing.v1.test_mcx_step31_prepared_handoff import _current
from tests.unit.swing.v1.test_opportunity_continuity import later, scenario


def _cleaned_fixture_worker(operation):
    # No child/channel/result directory is allocated by these substitutes.
    def run(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        finally:
            kwargs["cleanup_observer"]("COMPLETE")
    return run


CHOICE_TIME = datetime(2026, 8, 20, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
PLAN_NOW = datetime(2026, 8, 25, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def _handler(workflow, path, body=b"", application=None):
    handler = object.__new__(_BrowserHandler)
    handler.server = SimpleNamespace(mcx_slice3=workflow, application=application)
    handler.path = path
    handler.headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(body)),
    }
    handler.rfile = BytesIO(body)
    responses = []
    handler._html = lambda html: responses.append((HTTPStatus.OK, html))
    handler._text = lambda status, message: responses.append((status, message))
    handler._redirect = lambda location: responses.append((HTTPStatus.SEE_OTHER, location))
    return handler, responses


def test_mcx_v1_record_routes_hold_by_default_and_parse_before_any_owner_call():
    route = "/swing/mcx-v1/paper"
    valid = [
        ("run", "SWING-RUN-0123456789ABCDEF0123456789ABCDEF"),
        ("family", "GOLDM"),
        ("plan", "MCX-TRADE-PLAN-" + "a" * 64),
        ("plan_sha256", "b" * 64),
    ]
    handler, responses = _handler(None, route, urlencode(valid).encode())
    handler._mcx_v1_record_action(route)
    assert responses == [(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")]
    class Owner:
        def __init__(self):
            self.calls = []
        def admit_paper(self, **values):
            self.calls.append(values)
    owner = Owner()
    for fields in (valid + [("unexpected", "value")],
                   valid + [("family", "SILVERM")]):
        handler, responses = _handler(None, route, urlencode(fields).encode())
        handler.server.mcx_v1_control = owner
        handler._mcx_v1_record_action(route)
        assert responses == [(HTTPStatus.CONFLICT, "MCX V1 request rejected.")]
        assert owner.calls == []
    handler, responses = _handler(None, route, urlencode(valid).encode())
    handler.server.mcx_v1_control = owner
    handler._mcx_v1_record_action(route)
    assert responses == [(HTTPStatus.SEE_OTHER, "/swing/opportunities")]
    assert len(owner.calls) == 1
    assert owner.calls[0]["family"] is McxFamily.GOLDM


def test_mcx_v1_live_and_exit_routes_reject_ambiguous_forms_before_owner_call():
    class Owner:
        def __init__(self):
            self.calls = []
        def record_manual_live_entry(self, **values):
            self.calls.append(("entry", values))
        def record_manual_live_exit(self, **values):
            self.calls.append(("exit", values))
        def paper_exit(self, *_args):
            self.calls.append(("paper_exit", None))
    owner = Owner()
    fill = [
        ("contract", "GOLDM26OCTFUT"), ("expiry", "2026-10-05"),
        ("lots", "2"), ("fill_price", "105"),
        ("fill_at", PLAN_NOW.isoformat()),
        ("broker_evidence_id", "BROKER-MANUAL-1"),
        ("broker_evidence_sha256", sha256(b"sponsor evidence").hexdigest()),
        ("broker_evidence_b64", "c3BvbnNvciBldmlkZW5jZQ=="),
    ]
    entry = [
        ("run", "SWING-RUN-0123456789ABCDEF0123456789ABCDEF"),
        ("family", "GOLDM"),
        ("plan", "MCX-TRADE-PLAN-" + "a" * 64),
        ("plan_sha256", "b" * 64),
    ] + fill
    for route, fields in (
        ("/swing/mcx-v1/live", entry + [("unexpected", "1")]),
        ("/swing/mcx-v1/live", entry + [("lots", "3")]),
        ("/swing/mcx-v1/live", [
            (key, "2.5" if key == "lots" else value) for key, value in entry]),
        ("/swing/mcx-v1/live-exit", [
            ("position", "POSITION-1"), ("position_sha256", "c" * 64),
            *fill, ("reason", "SPONSOR_MANUAL_EXIT"), ("reason", "PAPER_STOP_HIT")]),
    ):
        handler, responses = _handler(None, route, urlencode(fields).encode())
        handler.server.mcx_v1_control = owner
        handler._mcx_v1_record_action(route)
        assert responses == [(HTTPStatus.CONFLICT, "MCX V1 request rejected.")]
        assert owner.calls == []
    handler, responses = _handler(
        None, "/swing/mcx-v1/live", urlencode(entry).encode())
    handler.server.mcx_v1_control = owner
    handler._mcx_v1_record_action("/swing/mcx-v1/live")
    assert responses == [(HTTPStatus.SEE_OTHER, "/swing/opportunities")]
    assert owner.calls[0][0] == "entry"
    assert owner.calls[0][1]["evidence_bytes"] == b"sponsor evidence"


def test_v1_offer_get_shows_both_listed_futures_snapshot_and_known_hold():
    acquired = CHOICE_TIME - timedelta(minutes=2)
    near = replace(_fact(McxFamily.COPPER, date(2026, 8, 28)),
                   snapshot_acquired_at=acquired)
    next_contract = replace(
        _fact(McxFamily.COPPER, date(2026, 9, 28)),
        snapshot_acquired_at=acquired,
        entry_until=CHOICE_TIME - timedelta(seconds=1))
    offer = prepare_mcx_contract_offer(
        "SWING-RUN-0123456789ABCDEF0123456789ABCDEF", McxFamily.COPPER,
        (near, next_contract), observed_at=CHOICE_TIME,
        selection_policy=V1_ADVISORY_SELECTION)
    class Owner:
        def offer(self, family):
            assert family is McxFamily.COPPER
            return offer

        def process_handoff(self):
            raise ValueError("not all choices recorded")

    handler, responses = _handler(
        Owner(), "/swing/mcx-contract-offer?family=COPPER")
    handler._mcx_contract_offer()
    assert responses[0][0] == HTTPStatus.OK
    html = responses[0][1]
    assert near.instrument.trading_symbol in html
    assert next_contract.instrument.trading_symbol in html
    assert acquired.isoformat() in html
    assert "MCX_KNOWN_ENTRY_SESSION_CLOSED" in html
    assert "Select NEXT_ELIGIBLE" not in html
    assert "broker restrictions UNKNOWN" in html


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_expiry_boundary_get_and_stale_choice_are_write_free(
    tmp_path, scenario, native_intake,
):
    workflow, _ = _workflow(tmp_path, scenario, native_intake)
    before_close = datetime(2026, 9, 30, 16, 59, 58,
                            tzinfo=ZoneInfo("Asia/Kolkata"))
    facts = tuple(replace(_fact(McxFamily.COPPER, expiry), entry_until=None)
                  for expiry in (date(2026, 9, 30), date(2026, 10, 30), date(2026, 11, 30)))
    offer = prepare_mcx_contract_offer(workflow.run_identity, McxFamily.COPPER,
        facts, observed_at=before_close, selection_policy=V1_ADVISORY_SELECTION)
    workflow.offers[McxFamily.COPPER] = offer
    workflow.clock = lambda: before_close + timedelta(seconds=2)
    retained = _inventory(tmp_path)
    for _ in range(2):
        handler, responses = _handler(workflow, "/swing/mcx-contract-offer?family=COPPER")
        handler._mcx_contract_offer()
        assert responses[0][0] == HTTPStatus.OK
        html = responses[0][1]
        assert "MCX_EXPIRY_SESSION_CLOSED" in html
        assert "Select NEAR COPPER26SEPFUT" not in html
        assert "Select NEXT_ELIGIBLE COPPER26OCTFUT" in html
        assert workflow.offers[McxFamily.COPPER] == offer
        assert _inventory(tmp_path) == retained
    fields = dict(run=workflow.run_identity, family="COPPER", role="NEAR",
                  offer_sha256=offer.offer_sha256)
    handler, responses = _handler(workflow, "/swing/mcx-contract-choice", urlencode(fields).encode())
    handler._mcx_contract_choice()
    assert responses == [(HTTPStatus.CONFLICT, "MCX_CONTRACT_CHOICE_REJECTED")]
    assert _inventory(tmp_path) == retained
    assert not workflow.selections._path(workflow.run_identity, McxFamily.COPPER).exists()


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_expiry_boundary_stale_analysis_post_rejects_before_dispatch_or_acquisition(
    tmp_path, scenario, native_intake,
):
    workflow, _ = _workflow(tmp_path, scenario, native_intake)
    before_close = datetime(2026, 9, 30, 16, 59, 58,
                            tzinfo=ZoneInfo("Asia/Kolkata"))
    clock = [before_close + timedelta(seconds=1)]
    workflow.clock = lambda: clock[0]
    for family in McxFamily:
        expiries = ((date(2026, 9, 30), date(2026, 10, 30), date(2026, 11, 30))
                    if family is McxFamily.COPPER else (date(2026, 10, 30), date(2026, 11, 30)))
        offer = prepare_mcx_contract_offer(workflow.run_identity, family,
            tuple(replace(_fact(family, expiry), entry_until=None) for expiry in expiries),
            observed_at=before_close, selection_policy=V1_ADVISORY_SELECTION)
        workflow.offers[family] = offer
        workflow.choose(family, McxSelectionRole.NEAR, offer.offer_sha256,
                        recorded_at=clock[0])
    handoff = workflow.process_handoff()
    clock[0] += timedelta(seconds=1)
    calls = []
    application = SimpleNamespace(run_analysis=lambda *_args: calls.append("dispatch"))
    before = _inventory(tmp_path)
    handler, responses = _handler(workflow, "/swing/mcx-reserved-analysis", urlencode(
        dict(run=workflow.run_identity, handoff_sha256=handoff.integrity_sha256)).encode(), application)
    handler._mcx_reserved_analysis()
    assert responses == [(HTTPStatus.CONFLICT, "MCX_RESERVED_ANALYSIS_REJECTED")]
    assert calls == []
    assert _inventory(tmp_path) == before
    assert workflow.selections.load(workflow.run_identity, McxFamily.COPPER).trading_symbol == "COPPER26SEPFUT"


def _facts(family):
    near = replace(
        _fact(family, date(2026, 8, 28)),
        instrument=_instrument(family.value, "MCX"),
    )
    next_contract = _fact(family, date(2026, 9, 28))
    return near, next_contract


def _confirmed_entry(plan, risk, *, state=None):
    boundary = PLAN_NOW + timedelta(hours=1)
    state = state or (Kr380V2State.LONG_ENTRY_TRIGGERED
                      if plan.native_direction.value == "LONG"
                      else Kr380V2State.SHORT_ENTRY_TRIGGERED)
    values = dict(
        entry_outcome_id="KR380-V2-ISOLATED-MCX-1H-ENTRY",
        native_run_identity=plan.native_run_identity,
        canonical_instrument=plan.canonical_instrument,
        direction=plan.native_direction.value,
        kr370_source_identity=plan.readiness_record_identity,
        trade_plan_id=plan.trade_plan_id,
        trade_plan_sha256=plan.integrity_hash,
        risk_result_id=risk.risk_result_id,
        ecpc_context_identity="ISOLATED-MCX-1H-CONTEXT",
        monitoring_binding_id="ISOLATED-MCX-CONTRACT-MONITORING",
        observation_boundary=boundary,
        source_observation_ids=("ISOLATED-COMPLETED-1H-PREVIOUS",
                                "ISOLATED-COMPLETED-1H-CURRENT"),
        source_sequence=(1, 2), state=state,
        reason="MCX_COMPLETED_1H_CLOSE_CROSS",
        occurred_at=boundary,
        provenance=(RULE_ID, plan.completed_one_hour_sha256,
                    "c" * 64, "ISOLATED-MCX-1H"),
        contract_identity=KR380_CONTRACT_ID,
        contract_version=KR380_CONTRACT_VERSION,
        owner_identity="KR-380", state_family_identity="KR380_ENTRY_OUTCOME",
        policy_identity=KR380_POLICY_ID, policy_version=KR380_POLICY_VERSION,
        broker_authority=NO_BROKER_AUTHORITY,
    )
    outcome = Kr380EntryOutcomeV2(integrity_sha256=_values_digest(values), **values)
    entry_at = boundary + timedelta(seconds=1)
    paper_tick = ProviderMarketTick(
        _facts(plan.family)[0].instrument, Decimal("103"), entry_at,
        entry_at + timedelta(seconds=2), "KITE_CONNECT_WEBSOCKET", "ISOLATED-MCX-CONNECTION",
        123, True, True, True,
    )
    predecessor = ProviderMarketTick(
        paper_tick.instrument, Decimal("102"), boundary, boundary,
        paper_tick.source, paper_tick.connection_id, 122, True, True, True,
    )
    return McxConfirmedOneHourEntry(
        plan_id=plan.trade_plan_id, plan_sha256=plan.integrity_hash,
        run_identity=plan.native_run_identity, family=plan.family,
        contract_symbol=plan.contract_symbol, expiry=plan.expiry,
        setup_one_hour_sha256=plan.completed_one_hour_sha256,
        completed_entry_one_hour_sha256="c" * 64,
        completed_entry_boundary=boundary,
        confirmed_close=Decimal("102"), outcome=outcome,
        paper_cmp_predecessor=predecessor, paper_entry_tick=paper_tick,
    )


def _workflow(tmp_path, scenario, native_intake):
    snapshot, bindings = scenario
    publication, _, _, _ = make_checkpoint(
        tmp_path / "publication-fixture", later(snapshot, 2), bindings,
    )
    run = native_intake._context()[1].run_identity
    facts = {family: _facts(family) for family in McxFamily}
    workflow = SwingMcxIntegratedWorkflow.reserve(
        publication, LocalMcxSponsorSelectionStore(tmp_path / "choices"),
        LocalMcxPreparedPlanStore(tmp_path / "plans"), run, facts,
        observed_at=CHOICE_TIME, sponsor_identity="ISOLATED-SPONSOR-FIXTURE",
        clock=lambda: CHOICE_TIME + timedelta(seconds=1),
    )
    return workflow, facts


def test_reserved_run_becomes_exact_current_publication_before_review(tmp_path, scenario):
    snapshot, bindings = scenario
    publication, _, _, _ = make_checkpoint(
        tmp_path / "publication-fixture", later(snapshot, 2), bindings,
    )
    updated = replace(later(snapshot, 3), observed_at=CHOICE_TIME + timedelta(minutes=1))
    workflow = SwingMcxIntegratedWorkflow.reserve(
        publication, LocalMcxSponsorSelectionStore(tmp_path / "choices"),
        LocalMcxPreparedPlanStore(tmp_path / "plans"), updated.run_identity,
        {family: _facts(family) for family in McxFamily},
        observed_at=CHOICE_TIME, sponsor_identity="ISOLATED-SPONSOR-FIXTURE",
    )
    for family in McxFamily:
        workflow.choose(family, McxSelectionRole.NEAR,
                        workflow.offers[family].offer_sha256,
                        recorded_at=CHOICE_TIME + timedelta(seconds=1))
    assert workflow.process_handoff().generation == workflow.generation
    prepared = continuity.prepare_continuity(
        updated, bindings, adopted_predecessor=workflow.predecessor,
    )
    reference = publication.prepare(
        workflow.reservation_token, mtf=updated, native=prepared.native_run,
        relative=build_relative_context_run(updated, SWING_PHASE1_UNIVERSE),
        provenance=provenance(updated), continuity=prepared,
    )
    committed = publication.publish(
        workflow.reservation_token, reference, updated.observed_at,
    )
    assert committed is not None
    workflow._current()
    assert publication.current().reference == publication.status()["current_manifest"]
    with pytest.raises(ValueError, match="RESERVED_RUN_STALE"):
        workflow.offer(McxFamily.GOLDM)
    next_run = later(snapshot, 4)
    publication.admit(next_run.run_identity, updated.observed_at + timedelta(minutes=1))
    with pytest.raises(ValueError, match="RESERVED_RUN_STALE"):
        workflow._current()


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_refused_maintenance_claim_does_not_write_reserved_attempt(
    tmp_path, scenario, native_intake,
):
    snapshot, bindings = scenario
    publication, _, _, _ = make_checkpoint(
        tmp_path / "publication-fixture", later(snapshot, 2), bindings,
    )
    application = analysis_application.SwingOpportunitiesApplication(
        _Provider, run_publication=publication,
        market_calendar_publisher=MarketCalendarPublisher(),
    )
    application.bind_maintenance_admission(SimpleNamespace(admit=lambda _kind: None))
    workflow = SwingMcxIntegratedWorkflow.reserve(
        publication, LocalMcxSponsorSelectionStore(tmp_path / "choices"),
        LocalMcxPreparedPlanStore(tmp_path / "plans"),
        native_intake._context()[1].run_identity,
        {family: _facts(family) for family in McxFamily},
        observed_at=CHOICE_TIME, sponsor_identity="ISOLATED-SPONSOR-FIXTURE",
    )
    before = publication.status()
    assert application.run_analysis(workflow) is False
    assert publication.status() == before


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_selected_historical_master_record_is_exact_but_never_entry_authority(
    tmp_path, scenario, native_intake,
):
    snapshot, bindings = scenario
    publication, _, _, _ = make_checkpoint(
        tmp_path / "publication-fixture", later(snapshot, 2), bindings,
    )
    provider_snapshot = _snapshot()
    provider_store = ProviderInstrumentSnapshotStore(tmp_path / "provider-master")
    provider_store.retain(provider_snapshot)
    record = next(item for item in provider_snapshot.records
                  if item.trading_symbol == "GOLDM26AUGFUT")
    exact = _instrument(McxFamily.GOLDM.value, "MCX")
    exact = replace(exact, trading_symbol=record.trading_symbol,
                    expiry=record.expiry, tick_size=record.tick_size,
                    lot_size=record.lot_size)
    facts = {family: _facts(family) for family in McxFamily}
    near, later_fact = facts[McxFamily.GOLDM]
    facts[McxFamily.GOLDM] = (
        replace(near, instrument=exact,
                provider_snapshot_identity=provider_snapshot.snapshot_identity,
                provider_record_identity=record.provider_record_identity),
        replace(later_fact,
                provider_snapshot_identity=provider_snapshot.snapshot_identity),
    )
    workflow = SwingMcxIntegratedWorkflow.reserve(
        publication, LocalMcxSponsorSelectionStore(tmp_path / "choices"),
        LocalMcxPreparedPlanStore(tmp_path / "plans"),
        native_intake._context()[1].run_identity, facts,
        observed_at=CHOICE_TIME, sponsor_identity="ISOLATED-SPONSOR-FIXTURE",
    )
    workflow.choose(McxFamily.GOLDM, McxSelectionRole.NEAR,
                    workflow.offers[McxFamily.GOLDM].offer_sha256,
                    recorded_at=CHOICE_TIME + timedelta(seconds=1))
    match = workflow.retained_selected_contract(
        McxFamily.GOLDM, provider_store,
        acquired_at=MASTER_NOW + timedelta(days=1),
    )
    assert match.normalized_contract == exact
    assert match.record_identity == record.provider_record_identity
    assert match.permits_new_entry is False
    with pytest.raises(ValueError):
        workflow.retained_selected_contract(
            McxFamily.GOLDM, ProviderInstrumentSnapshotStore(tmp_path / "empty"),
            acquired_at=MASTER_NOW + timedelta(days=1),
        )


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_reserved_choices_reach_actual_application_process_dispatch_and_fail_cleanly(
    tmp_path, scenario, native_intake, monkeypatch,
):
    snapshot, bindings = scenario
    publication, _, _, _ = make_checkpoint(
        tmp_path / "publication-fixture", later(snapshot, 2), bindings,
    )
    queued = []
    owner = process.SwingAnalysisProcessOwner(timeout_seconds=12)
    application = analysis_application.SwingOpportunitiesApplication(
        _Provider, run_publication=publication,
        market_calendar_publisher=MarketCalendarPublisher(),
        analysis_process_owner=owner, clock=lambda: CHOICE_TIME + timedelta(seconds=2),
        background_runner=lambda operation, _name: queued.append(operation),
    )
    assert application.connect_provider()
    queued.pop(0)()  # Complete only the isolated Provider fixture connection.
    run = native_intake._context()[1].run_identity
    facts = {family: _facts(family) for family in McxFamily}
    workflow = SwingMcxIntegratedWorkflow.reserve(
        publication, LocalMcxSponsorSelectionStore(tmp_path / "choices"),
        LocalMcxPreparedPlanStore(tmp_path / "plans"), run, facts,
        observed_at=CHOICE_TIME, sponsor_identity="ISOLATED-SPONSOR-FIXTURE",
    )
    for family in McxFamily:
        workflow.choose(
            family, workflow.offers[family].selectable()[0],
            workflow.offers[family].offer_sha256,
            recorded_at=CHOICE_TIME + timedelta(seconds=1),
        )
    before_offer_get = _inventory(tmp_path)
    handler, responses = _handler(workflow, "/swing/mcx-contract-offer?family=GOLDM")
    handler._mcx_contract_offer()
    assert responses[0][0] == HTTPStatus.OK
    assert "Start reserved analysis" in responses[0][1]
    assert _inventory(tmp_path) == before_offer_get
    seen = []

    def fail_after_dispatch(*_args, **kwargs):
        seen.append((kwargs["mcx_handoff"], kwargs["swing_run_identity"], kwargs["now"]))
        raise process.SwingAnalysisProcessError("ISOLATED_MCX_WORKER_FAILURE")

    monkeypatch.setattr(process, "_run_worker", _cleaned_fixture_worker(fail_after_dispatch))
    expected_handoff = workflow.process_handoff()
    for malformed in (
        urlencode({"run": run, "handoff_sha256": "0" * 64}).encode(),
        urlencode({"run": run, "handoff_sha256": expected_handoff.integrity_sha256,
                   "unexpected": "1"}).encode(),
        urlencode((("run", run), ("run", "OTHER"),
                   ("handoff_sha256", expected_handoff.integrity_sha256))).encode(),
    ):
        handler, responses = _handler(workflow, "/swing/mcx-reserved-analysis",
                                      malformed, application)
        handler._mcx_reserved_analysis()
        assert responses == [(HTTPStatus.CONFLICT, "MCX_RESERVED_ANALYSIS_REJECTED")]
        assert not queued
    handler, responses = _handler(
        workflow, "/swing/mcx-reserved-analysis",
        urlencode({"run": run, "handoff_sha256": expected_handoff.integrity_sha256}).encode(),
        application,
    )
    handler._mcx_reserved_analysis()
    assert responses == [(HTTPStatus.SEE_OTHER, "/swing/opportunities")]
    assert len(queued) == 1
    queued.pop(0)()
    assert seen == [(expected_handoff, workflow.run_identity,
                     CHOICE_TIME)]
    assert workflow.publication.status()["latest_attempt"]["state"] == "FAILED"
    assert owner.status()["owned_workers"] == 0
    assert not queued
    before_replay = workflow.publication.status()
    handler, responses = _handler(
        workflow, "/swing/mcx-reserved-analysis",
        urlencode({"run": run, "handoff_sha256": expected_handoff.integrity_sha256}).encode(),
        application,
    )
    handler._mcx_reserved_analysis()
    assert responses == [(HTTPStatus.CONFLICT, "MCX_RESERVED_ANALYSIS_REJECTED")]
    assert workflow.publication.status() == before_replay
    assert not queued


@pytest.mark.parametrize("altered", (None, "observation", "source", "run"))
def test_delayed_reserved_analysis_publishes_one_epoch_and_rejects_alteration(
    tmp_path, scenario, monkeypatch, altered,
):
    # Reproduce the real failure shape: selection reserves the run, then the
    # process starts 204.685826 seconds later. Acquisition is isolated, while
    # the real analysis builder, continuity and publication owners are used.
    from tests.unit.application.test_swing_opportunities import _real_completed
    _real_completed(monkeypatch)
    snapshot, bindings = scenario
    publication, _, _, predecessor = make_checkpoint(
        tmp_path / "publication", later(snapshot, 2), bindings)
    run = "SWING-RUN-56C2E24455E94C82981E6CCCD5EB8FE9"
    started = CHOICE_TIME + timedelta(seconds=204, microseconds=685826)
    queued = []
    owner = process.SwingAnalysisProcessOwner(timeout_seconds=12)
    application = analysis_application.SwingOpportunitiesApplication(
        _Provider, run_publication=publication,
        market_calendar_publisher=MarketCalendarPublisher(),
        analysis_process_owner=owner, clock=lambda: started,
        background_runner=lambda operation, _name: queued.append(operation))
    assert application.connect_provider()
    queued.pop(0)()
    facts = {family: _facts(family) for family in McxFamily}
    workflow = SwingMcxIntegratedWorkflow.reserve(
        publication, LocalMcxSponsorSelectionStore(tmp_path / "choices"),
        LocalMcxPreparedPlanStore(tmp_path / "plans"), run, facts,
        observed_at=CHOICE_TIME, sponsor_identity="ISOLATED-SPONSOR-FIXTURE")
    for family in McxFamily:
        offer = workflow.offers[family]
        workflow.choose(family, offer.selectable()[0], offer.offer_sha256,
                        recorded_at=CHOICE_TIME + timedelta(seconds=1))
    selections = _inventory(tmp_path / "choices")
    master = tuple(f.instrument for rows in facts.values() for f in rows)
    class Instruments:
        def __init__(self, _capability):
            pass
        def retrieve(self, exchange):
            return master if exchange == "MCX" else ()
    monkeypatch.setattr(analysis_application, "KiteInstrumentProvider", Instruments)
    def factual(**kwargs):
        return replace(snapshot, run_identity=kwargs["run_identity"],
                       observed_at=kwargs["observed_at"])
    monkeypatch.setattr(analysis_application, "build_same_run_mtf_fact_snapshot", factual)
    original_selection = analysis_application.selected_mcx_instrument_before_acquisition
    acquisitions = []
    def selection(*args, **kwargs):
        acquisitions.append(kwargs["acquired_at"])
        return original_selection(*args, **kwargs)
    monkeypatch.setattr(analysis_application, "selected_mcx_instrument_before_acquisition", selection)
    dispatched = []
    manifests = _inventory(publication.root / "manifests")
    def worker(capability, co, calendar, token, **kwargs):
        dispatched.append(kwargs)
        completed = analysis_application.build_completed_swing_analysis(
            capability, analysis_run_identity=kwargs["analysis_run_identity"],
            swing_analysis_run_identity=run, run_created_at=kwargs["run_created_at"],
            now=kwargs["now"], pace=lambda: None,
            market_calendar_publisher=calendar, committed_predecessor=predecessor,
            prepare_publication=True, completion_clock=kwargs["completion_clock"],
            mcx_contract_choices=kwargs["mcx_handoff"].analysis_choices())
        mtf = completed.mtf_fact_snapshot
        if altered == "observation":
            mtf = replace(mtf, observed_at=started)
        elif altered == "source":
            mtf = replace(mtf, provider_source_identity="KITE-MTF-FACTS-" + "f" * 64)
        elif altered == "run":
            mtf = replace(mtf, run_identity="SWING-RUN-" + "F" * 32)
        provenance = analysis_application.SwingAnalysisRunProvenance(
            run, kwargs["run_created_at"], completed.evidence.observation_boundary,
            completed.evidence.market_data_snapshot_identity, started)
        ref = co.prepare(token, mtf=mtf, native=completed.native_discovery_run,
            relative=completed.relative_context_run, provenance=provenance,
            continuity=completed.continuity_contribution)
        with kwargs["commit_scope"]():
            assert kwargs["authorize_commit"](ref, started)
            committed = co.publish(token, ref, started)
        assert co.publish(token, ref, started) is None  # No second publication.
        result = process.SwingAnalysisProcessResult(completed, committed, 0, 0, 0, 0, 0)
        assert kwargs["install_result"](result)
        return result
    monkeypatch.setattr(process, "_run_worker", _cleaned_fixture_worker(worker))
    assert application.run_analysis(workflow)
    queued.pop(0)()
    assert len(dispatched) == 1
    assert acquisitions == [started] * 10  # Five pre-master + five exact-master fences.
    assert _inventory(tmp_path / "choices") == selections
    assert owner.status()["owned_workers"] == 0 and not queued
    if altered is None:
        assert publication.status()["latest_attempt"]["state"] == "SUCCEEDED"
        committed = publication.current()
        assert committed.mtf.observed_at == committed.native.observed_at == \
            committed.relative.created_at == committed.provenance.run_created_at == CHOICE_TIME
        assert committed.provenance.successful_completed_at == started
        assert committed.mtf.run_identity == run
    else:
        assert publication.status()["latest_attempt"]["state"] == "FAILED"
        assert publication.current().reference == predecessor.reference
        assert application.snapshot().analysis_failure == "SWING_ANALYSIS_FAILED"
        assert owner.status()["failure"] == (
            "SWING_PUBLICATION_RUN_MISMATCH" if altered == "run"
            else "SWING_PUBLICATION_BUNDLE_INVALID")
        assert _inventory(publication.root / "manifests") == manifests


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_reserved_analysis_replay_does_not_fail_queued_owner(
    tmp_path, scenario, native_intake, monkeypatch,
):
    snapshot, bindings = scenario
    publication, _, _, _ = make_checkpoint(
        tmp_path / "publication-fixture", later(snapshot, 2), bindings,
    )
    queued = []
    admission = MaintenanceAdmissionCoordinator()
    application = analysis_application.SwingOpportunitiesApplication(
        _Provider, run_publication=publication,
        market_calendar_publisher=MarketCalendarPublisher(),
        analysis_process_owner=process.SwingAnalysisProcessOwner(timeout_seconds=12),
        clock=lambda: CHOICE_TIME + timedelta(seconds=2),
        background_runner=lambda operation, _name: queued.append(operation),
    )
    application.bind_maintenance_admission(admission)
    assert application.connect_provider()
    queued.pop(0)()
    workflow = SwingMcxIntegratedWorkflow.reserve(
        publication, LocalMcxSponsorSelectionStore(tmp_path / "choices"),
        LocalMcxPreparedPlanStore(tmp_path / "plans"),
        native_intake._context()[1].run_identity,
        {family: _facts(family) for family in McxFamily},
        observed_at=CHOICE_TIME, sponsor_identity="ISOLATED-SPONSOR-FIXTURE",
    )
    for family in McxFamily:
        workflow.choose(
            family, workflow.offers[family].selectable()[0],
            workflow.offers[family].offer_sha256,
            recorded_at=CHOICE_TIME + timedelta(seconds=1),
        )
    assert application.run_analysis(workflow)
    before = _inventory(tmp_path)
    status = workflow.publication.status()
    owners = admission.snapshot()["owners"]
    assert status["latest_attempt"]["state"] == "RUNNING"
    assert len(queued) == 1

    assert application.run_analysis(workflow) is False
    assert application.publication_status()["request_result"] == "DUPLICATE_RUNNING"
    assert workflow.publication.status() == status
    assert _inventory(tmp_path) == before
    assert admission.snapshot()["owners"] == owners
    assert len(queued) == 1

    started, release = Event(), Event()
    acquisitions = []

    def completed_worker(*_args, **kwargs):
        acquisitions.append(kwargs["swing_run_identity"])
        started.set()
        assert release.wait(10)
        updated = replace(later(snapshot, 3), run_identity=workflow.run_identity,
                          observed_at=CHOICE_TIME + timedelta(seconds=3))
        prepared = continuity.prepare_continuity(
            updated, bindings, adopted_predecessor=workflow.predecessor,
        )
        reference = publication.prepare(
            workflow.reservation_token, mtf=updated, native=prepared.native_run,
            relative=build_relative_context_run(updated, SWING_PHASE1_UNIVERSE),
            provenance=provenance(updated), continuity=prepared,
        )
        assert kwargs["authorize_commit"](reference, updated.observed_at)
        with kwargs["commit_scope"]():
            committed = publication.publish(
                workflow.reservation_token, reference, updated.observed_at,
            )
            assert committed is not None
            workspace = replace(
                application.snapshot(), analysis_state=analysis_application.AnalysisState.READY,
                swing_analysis_run_identity=workflow.run_identity,
                observation_boundary=updated.observed_at,
            )
            result = process.SwingAnalysisProcessResult(
                SimpleNamespace(workspace=workspace, evidence=object()),
                committed, 0, 0, 0, 0, 0,
            )
            assert kwargs["install_result"](result)
        return result

    monkeypatch.setattr(process, "_run_worker", _cleaned_fixture_worker(completed_worker))
    worker = Thread(target=queued.pop(0))
    worker.start()
    assert started.wait(10)
    running_status = publication.status()
    running_inventory = _inventory(tmp_path)
    running_owners = admission.snapshot()["owners"]
    try:
        assert application.run_analysis(workflow) is False
        assert application.publication_status()["request_result"] == "DUPLICATE_RUNNING"
        assert publication.status() == running_status
        assert _inventory(tmp_path) == running_inventory
        assert admission.snapshot()["owners"] == running_owners
        assert acquisitions == [workflow.run_identity]
        assert not queued
    finally:
        release.set()
        worker.join(15)
    assert not worker.is_alive()
    assert publication.status()["latest_attempt"]["state"] == "SUCCEEDED"
    assert publication.current().native.run_identity == workflow.run_identity
    assert application.publication_status()["request_result"] == "SUCCEEDED"
    assert admission.snapshot()["owners"] == {}
    assert acquisitions == [workflow.run_identity]
    completed_inventory = _inventory(tmp_path)
    with pytest.raises(ValueError, match="MCX_RESERVED_RUN_STALE"):
        application.run_analysis(workflow)
    assert _inventory(tmp_path) == completed_inventory


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_reserved_analysis_dispatch_failure_fails_its_claimed_attempt(
    tmp_path, scenario, native_intake,
):
    snapshot, bindings = scenario
    publication, _, _, _ = make_checkpoint(
        tmp_path / "publication-fixture", later(snapshot, 2), bindings,
    )
    queued = []

    def dispatch(operation, name):
        if name == "kronos-browser-swing":
            raise RuntimeError("ISOLATED_DISPATCH_FAILURE")
        queued.append(operation)

    admission = MaintenanceAdmissionCoordinator()
    application = analysis_application.SwingOpportunitiesApplication(
        _Provider, run_publication=publication,
        market_calendar_publisher=MarketCalendarPublisher(),
        analysis_process_owner=process.SwingAnalysisProcessOwner(timeout_seconds=12),
        clock=lambda: CHOICE_TIME + timedelta(seconds=2),
        background_runner=dispatch,
    )
    application.bind_maintenance_admission(admission)
    assert application.connect_provider()
    queued.pop(0)()
    workflow = SwingMcxIntegratedWorkflow.reserve(
        publication, LocalMcxSponsorSelectionStore(tmp_path / "choices"),
        LocalMcxPreparedPlanStore(tmp_path / "plans"),
        native_intake._context()[1].run_identity,
        {family: _facts(family) for family in McxFamily},
        observed_at=CHOICE_TIME, sponsor_identity="ISOLATED-SPONSOR-FIXTURE",
    )
    for family in McxFamily:
        workflow.choose(
            family, workflow.offers[family].selectable()[0],
            workflow.offers[family].offer_sha256,
            recorded_at=CHOICE_TIME + timedelta(seconds=1),
        )
    assert application.run_analysis(workflow) is False
    assert publication.status()["latest_attempt"]["state"] == "FAILED"
    assert application.publication_status()["request_result"] == "DISPATCH_FAILED"
    assert application.analysis_work_status()["owned_work_count"] == 0
    assert admission.snapshot()["owners"] == {}
    assert not queued


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
@pytest.mark.parametrize("live_advisory", [True, False])
def test_browser_to_reserved_process_review_held_plan_and_historical_lifecycle(
    tmp_path, scenario, native_intake, monkeypatch, live_advisory,
):
    workflow, facts = _workflow(tmp_path, scenario, native_intake)
    for family in McxFamily:
        before = _inventory(tmp_path)
        handler, responses = _handler(workflow, f"/swing/mcx-contract-offer?family={family.value}")
        handler._mcx_contract_offer()
        assert responses[0][0] == HTTPStatus.OK
        assert "8 calendar days" in responses[0][1]
        assert _inventory(tmp_path) == before  # Browser GET is observational.
        role = McxSelectionRole.NEXT_ELIGIBLE if family is McxFamily.SILVERM else McxSelectionRole.NEAR
        form = urlencode({
            "run": workflow.run_identity, "family": family.value,
            "role": role.value, "offer_sha256": workflow.offers[family].offer_sha256,
        }).encode()
        handler, responses = _handler(workflow, "/swing/mcx-contract-choice", form)
        handler._mcx_contract_choice()
        assert responses == [(HTTPStatus.SEE_OTHER,
                              "/swing/mcx-contract-offer?family=" + family.value)]
        assert workflow.selections.load(workflow.run_identity, family).role is role

    handoff = workflow.process_handoff()
    assert handoff.generation == workflow.generation
    assert set(handoff.analysis_choices()) == set(McxFamily)
    worker_result = process.SwingAnalysisProcessResult(
        object(), object(), 0, 0, 0, 0, 0,
    )
    seen = []

    def isolated_worker(*_args, **kwargs):
        assert kwargs["mcx_handoff"] is handoff
        assert set(kwargs["mcx_handoff"].analysis_choices()) == set(McxFamily)
        seen.append(kwargs["swing_run_identity"])
        return worker_result

    monkeypatch.setattr(process, "_run_worker", _cleaned_fixture_worker(isolated_worker))
    owner = process.SwingAnalysisProcessOwner(timeout_seconds=12)
    assert owner.execute(
        object(), workflow.publication, object(), workflow.reservation_token,
        generation=workflow.generation, analysis_run_identity="ANALYSIS-000001",
        swing_run_identity=workflow.run_identity, run_created_at=CHOICE_TIME,
        now=CHOICE_TIME + timedelta(seconds=2), pace=lambda: None,
        progress_observer=lambda _value: None, completion_clock=lambda: CHOICE_TIME,
        authorize_commit=lambda *_args: True, is_current=lambda: True,
        commit_scope=nullcontext, install_result=lambda _result: True,
        mcx_handoff=handoff,
    ) is worker_result
    assert seen == [workflow.run_identity]
    owner.release(workflow.generation)
    assert workflow.selected_contract(
        McxFamily.GOLDM, (facts[McxFamily.GOLDM][0].instrument,),
        acquired_at=CHOICE_TIME + timedelta(seconds=2),
    ) == facts[McxFamily.GOLDM][0].instrument
    assert workflow.selected_contract(
        McxFamily.SILVERM, (facts[McxFamily.SILVERM][1].instrument,),
        acquired_at=CHOICE_TIME + timedelta(seconds=2),
    ) == facts[McxFamily.SILVERM][1].instrument

    # The actual daily-builder entry validates the five process-carried
    # choices against a fixture master before any historical candle call.
    master = tuple(item.instrument for rows in facts.values() for item in rows)
    acquired = []

    class Instruments:
        def __init__(self, _capability):
            pass

        def retrieve(self, exchange):
            return master if exchange == "MCX" else ()

        def resolve_from_records(self, _master, _request):
            return "NSE_UNCHANGED"

    class MarketData:
        def __init__(self, _capability):
            pass

        def historical_candles(self, _request):
            pytest.fail("candle requested after isolated stop boundary")

    def daily(_universe, *, resolve_instrument, **_kwargs):
        for family in McxFamily:
            member = SimpleNamespace(asset_class=SwingUniverseAssetClass.MCX_COMMODITY,
                                     canonical_identity=family.value)
            instrument = resolve_instrument(member)
            expected = facts[family][1 if family is McxFamily.SILVERM else 0].instrument
            assert instrument == expected
            acquired.append(instrument.trading_symbol)
        raise RuntimeError("STOP_AT_ISOLATED_ACQUISITION_BOUNDARY")

    monkeypatch.setattr(analysis_application, "KiteInstrumentProvider", Instruments)
    monkeypatch.setattr(analysis_application, "KiteMarketDataProvider", MarketData)
    monkeypatch.setattr(analysis_application, "build_swing_daily_dataset", daily)
    with pytest.raises(RuntimeError, match="STOP_AT_ISOLATED_ACQUISITION_BOUNDARY"):
        analysis_application.build_completed_swing_analysis(
            SimpleNamespace(active=True), analysis_run_identity="ANALYSIS-000001",
            swing_analysis_run_identity=workflow.run_identity,
            now=CHOICE_TIME + timedelta(seconds=2), pace=lambda: None,
            mcx_contract_choices=handoff.analysis_choices(),
        )
    assert len(acquired) == 5

    # Existing Review/Answer/V2 owners, with an explicitly synthetic 5/5 input.
    read = _current(native_intake, tmp_path, promotion_at=PLAN_NOW)
    assert read.run_identity == workflow.run_identity
    native_intake._v2_store.retain(read.promotion, current=native_intake._v2_current)
    native_intake._v2_promotions[(read.run_identity, "GOLDM")] = read.promotion
    selected = select_owner_current_mcx_handoff(
        native_intake, McxFamily.GOLDM, facts[McxFamily.GOLDM][0].instrument,
        prepared_at=PLAN_NOW,
    )
    bound = selected.prepared.bound
    proof = McxContractProofPrerequisites(
        family=bound.family, trading_symbol=bound.derivative_symbol,
        expiry=bound.derivative_expiry, origin=McxProofOrigin.ISOLATED_FIXTURE,
        provider_snapshot_identity="fixture-snapshot",
        provider_record_identity="fixture-record",
        normalized_instrument_sha256="a" * 64,
        effective_specification_sha256="b" * 64,
        quantity_semantics=McxQuantitySemantics.LOTS,
        expiry_session_identity="fixture-session",
        expiry_eligibility_boundary=PLAN_NOW + timedelta(days=1),
        entry_blackout_policy_identity="fixture-blackout",
    )
    geometry = McxOneHourGeometry(
        entry=Decimal("100"), stop=Decimal("95"), target=Decimal("110"),
        completed_one_hour_sha256=bound.completed_one_hour_sha256,
        completed_one_hour_boundary=bound.completed_one_hour_boundary,
    )
    v1_choice = workflow.selections.load(workflow.run_identity, McxFamily.GOLDM)
    v1_plan = construct_v1_mcx_advisory_plan(
        selected.prepared, v1_choice, geometry,
        opportunity=read.requirement.thesis.opportunity_identity,
        provider_snapshot_identity="fixture-snapshot",
        provider_record_identity="fixture-record",
        normalized_instrument_sha256=v1_choice.instrument_sha256,
        session_identity="fixture-session",
        entry_session_until=PLAN_NOW + timedelta(hours=8),
        created_at=PLAN_NOW,
    )
    assert v1_plan.quantity is None
    assert v1_plan.maximum_stop_risk is None
    assert v1_plan.quote_quantity_per_lot is None
    v1_judgment = create_trade_plan_business_judgment(
        v1_plan, validation_identity="ISOLATED-MCX-V1-ADVICE", created_at=PLAN_NOW,
    )
    v1_risk = record_trade_plan_risk_result(
        v1_plan, v1_judgment, RiskState.UNAVAILABLE,
        reason="MONETARY_MULTIPLIER_UNKNOWN", evaluated_at=PLAN_NOW,
    )
    v1_sponsor = LocalSponsorDecisionStore(tmp_path / "v1-sponsor")
    v1_result = admit_v1_mcx_paper(
        v1_plan, v1_judgment, v1_risk, v1_sponsor,
        current_plan_id=v1_plan.trade_plan_id,
        decided_at=PLAN_NOW + timedelta(seconds=1),
    )
    assert v1_result.position.lots == 1
    assert v1_result.position.mcx_quantity is None
    assert v1_result.position.mcx_v1_contract_symbol == v1_plan.contract_symbol
    v1_service = ActiveTradeLifecycleService(
        LocalActiveTradeLifecycleStore(tmp_path / "v1-lifecycle"))
    v1_active = v1_service.register(v1_result, v1_plan)
    assert v1_active.state is ActiveLifecycleState.PAPER_ARMED
    assert v1_active.mcx_v1_contract_symbol == v1_plan.contract_symbol
    assert v1_sponsor.load_plan(v1_plan.native_run_identity,
                                v1_plan.trade_plan_id) == v1_result
    v1_plan_store = LocalMcxTradePlanStore(tmp_path / "v1-plans")
    v1_plan_store.retain(v1_plan)
    # Exercise the real Browser record handler -> operational owner -> current
    # Review fence -> durable Sponsor/lifecycle/historical-contract stores.
    # Only transport subscription is replaced, explicitly inside this fixture.
    from kronos.application.swing_mcx_v1_operations import SwingMcxV1OperationalControl
    from kronos.browser import server as browser_server
    from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
    native = native_intake.native_review
    operational = SwingMcxV1OperationalControl(
        workflow, native_intake, native, v1_plan_store,
        native._sponsor_decision_store, native._active_lifecycle,
        native._mcx_historical_contract_store,
        LocalMcxV1AdvisoryStore(tmp_path / "operational-advisories"),
        ProviderInstrumentSnapshotStore(tmp_path / "operational-master"),
        MtfFactEvidenceStore(tmp_path / "operational-mtf"),
        lambda: (_ for _ in ()).throw(AssertionError("no acquisition during admission")),
        MarketCalendarPublisher(),
        LocalMcxLiveFillAttestationStore(tmp_path / "operational-attestations"),
        LocalMcxBrokerFillEvidenceStore(tmp_path / "operational-broker"),
        SimpleNamespace(active=True))
    attach_calls = []
    class Clock:
        @staticmethod
        def now(_zone):
            return PLAN_NOW + timedelta(seconds=5)
        fromisoformat = staticmethod(datetime.fromisoformat)
    operational_fields = [
        ("run", v1_plan.native_run_identity), ("family", v1_plan.family.value),
        ("plan", v1_plan.trade_plan_id), ("plan_sha256", v1_plan.integrity_hash)]
    operational_route = "/swing/mcx-v1/paper"
    if not live_advisory:
        operational_route = "/swing/mcx-v1/live"
        import base64
        broker_bytes = b"isolated Sponsor actual manual fill"
        operational_fields += [
            ("contract", v1_plan.contract_symbol), ("expiry", v1_plan.expiry),
            ("lots", "2"), ("fill_price", "101"),
            ("fill_at", (PLAN_NOW + timedelta(seconds=2)).isoformat()),
            ("broker_evidence_id", "ISOLATED-MANUAL-BROKER-RECEIPT"),
            ("broker_evidence_sha256", sha256(broker_bytes).hexdigest()),
            ("broker_evidence_b64", base64.b64encode(broker_bytes).decode())]
    with monkeypatch.context() as scoped:
        scoped.setattr(browser_server, "datetime", Clock)
        def failed_attach(*_args):
            raise ValueError("ACTIVE_LIFECYCLE_MONITORING_FAILED")
        scoped.setattr(native, "attach_lifecycle_monitoring", failed_attach)
        handler, responses = _handler(None, operational_route,
                                      urlencode(operational_fields).encode())
        handler.server.mcx_v1_control = operational
        handler._mcx_v1_record_action(operational_route)
        assert responses == [(HTTPStatus.CONFLICT, "MCX V1 request rejected.")]
        retained_admission = native._sponsor_decision_store.load_plan(
            v1_plan.native_run_identity, v1_plan.trade_plan_id)
        assert retained_admission.position is not None
        # Truthful failed subscription leaves recoverable durable admission;
        # explicit identical replay does not create another Sponsor position.
        before_attach_replay = _inventory(tmp_path)
        scoped.setattr(native, "attach_lifecycle_monitoring",
                       lambda *args: attach_calls.append(args))
        handler, responses = _handler(None, operational_route,
                                      urlencode(operational_fields).encode())
        handler.server.mcx_v1_control = operational
        handler._mcx_v1_record_action(operational_route)
        assert responses == [(HTTPStatus.SEE_OTHER, "/swing/opportunities")]
        assert _inventory(tmp_path) == before_attach_replay
        assert len(attach_calls) == 1
        retained_binding = native._mcx_historical_contract_store.load(
            retained_admission.position.position_id)
        assert retained_binding.instrument == facts[McxFamily.GOLDM][0].instrument
        assert not any(hasattr(operational, name) for name in
                       ("place_order", "modify_order", "cancel_order"))
    # The retained Review fixture's 1H anchor ends after the prior session.
    # A separate isolated candle fixture below must use a current session;
    # never reinterpret the actual Review evidence to force a positive signal.
    v1_schedule = MarketCalendarPublisher().schedule(
        "MCX", PLAN_NOW.date(), observed_at=PLAN_NOW)
    p_end = PLAN_NOW + timedelta(hours=1)
    values = {name: getattr(v1_plan, name) for name in v1_plan.__dataclass_fields__}
    values.update(created_at=p_end + timedelta(seconds=1),
                  observation_boundary=p_end,
                  completed_one_hour_sha256="b" * 64,
                  expiry_session_identity=v1_schedule.session_identity,
                  trade_plan_id="", integrity_hash="")
    synthetic_plan_id = "MCX-TRADE-PLAN-" + plan_digest(values)
    values["trade_plan_id"] = synthetic_plan_id
    values["integrity_hash"] = plan_digest(values)
    synthetic_plan = McxTradePlanRecord(**values)
    synthetic_judgment = create_trade_plan_business_judgment(
        synthetic_plan, validation_identity="ISOLATED-CURRENT-SESSION",
        created_at=synthetic_plan.created_at)
    synthetic_risk = record_trade_plan_risk_result(
        synthetic_plan, synthetic_judgment, RiskState.UNAVAILABLE,
        reason="MONETARY_MULTIPLIER_UNKNOWN",
        evaluated_at=synthetic_plan.created_at)
    synthetic_sponsor = LocalSponsorDecisionStore(tmp_path / "v1-current-sponsor")
    synthetic_result = admit_v1_mcx_paper(
        synthetic_plan, synthetic_judgment, synthetic_risk,
        synthetic_sponsor, current_plan_id=synthetic_plan.trade_plan_id,
        decided_at=synthetic_plan.created_at + timedelta(seconds=1))
    synthetic_plans = LocalMcxTradePlanStore(tmp_path / "v1-current-plans")
    synthetic_plans.retain(synthetic_plan)
    synthetic_service = ActiveTradeLifecycleService(
        LocalActiveTradeLifecycleStore(tmp_path / "v1-current-lifecycle"))
    synthetic_position = synthetic_service.register(synthetic_result, synthetic_plan)
    synthetic_monitor = ActiveLifecycleMonitoringCoordinator(
        synthetic_service, MarketCalendarPublisher(), clock=lambda: PLAN_NOW)
    synthetic_historical = LocalMcxHistoricalContractStore(
        tmp_path / "v1-current-historical")
    synthetic_bound = McxContractBoundLifecycle(synthetic_service,
                                                 synthetic_historical)
    synthetic_bound.retain_existing(synthetic_position.position_id,
                                    facts[McxFamily.GOLDM][0].instrument)
    synthetic_monitor.set_mcx_historical_contracts(synthetic_historical)
    with pytest.raises(ValueError, match="MCX_HISTORICAL_CONTRACT_MONITORING_MISMATCH"):
        synthetic_monitor.attach(
            synthetic_position.position_id, SimpleNamespace(active=True),
            facts[McxFamily.GOLDM][1].instrument)
    with pytest.raises(ValueError, match="MCX_V1_COMPLETED_1H_MONITOR_NOT_COMMISSIONED"):
        synthetic_monitor.attach(
            synthetic_position.position_id, SimpleNamespace(active=True),
            facts[McxFamily.GOLDM][0].instrument)
    assert synthetic_monitor.active_position_ids == ()
    long = synthetic_plan.native_direction.value == "LONG"
    previous_close = Decimal("99") if long else Decimal("101")
    current_close = Decimal("101") if long else Decimal("99")
    previous = McxOneHourCandle(
        synthetic_plan.native_run_identity, synthetic_plan.family,
        synthetic_plan.contract_symbol, synthetic_plan.expiry, 123,
        v1_schedule.session_identity, "V1-PREVIOUS", 1, 1,
        synthetic_plan.completed_one_hour_sha256,
        PLAN_NOW, p_end, previous_close, previous_close,
        previous_close, previous_close, True)
    current = McxOneHourCandle(
        synthetic_plan.native_run_identity, synthetic_plan.family,
        synthetic_plan.contract_symbol, synthetic_plan.expiry, 123,
        v1_schedule.session_identity, "V1-CURRENT", 1, 2, "c" * 64,
        p_end, p_end + timedelta(hours=1), previous_close,
        max(previous_close, current_close), min(previous_close, current_close),
        current_close, True)
    continuity_proof = McxContinuityProof(
        previous.candle_identity, previous.revision, previous.source_sha256,
        current.candle_identity, current.revision, current.source_sha256,
        current.session_identity, True, True, True,
        "ISOLATED-ORDERED-CANDLES", "d" * 64)
    authority = McxCurrentAuthority(
        synthetic_plan.native_run_identity, synthetic_plan.contract_symbol,
        synthetic_plan.expiry, 123, synthetic_plan.selection_sha256,
        "ISOLATED-RECEIPT", synthetic_plan.receipt_integrity_sha256,
        "ISOLATED-V2", synthetic_plan.promotion_integrity_sha256,
        "e" * 64)
    signal_read = McxV1SignalReadSet(
        synthetic_plan, synthetic_risk, previous, current, continuity_proof,
        authority, v1_schedule, "ISOLATED-MONITORING", Decimal("1"))
    v1_outcomes = LocalMcxV1AdvisoryStore(tmp_path / "v1-outcomes")
    v1_outcome = issue_v1_isolated_signal(
        lambda: signal_read, evaluated_at=current.closed_at,
        store=v1_outcomes, commit_guard=nullcontext,
        guarded_recheck=lambda _digest: True)
    cmp_at = current.closed_at + timedelta(seconds=2)
    v1_cmp = ProviderMarketTick(
        facts[McxFamily.GOLDM][0].instrument, Decimal("102"), cmp_at,
        cmp_at + timedelta(seconds=1), "KITE_CONNECT_WEBSOCKET",
        "ISOLATED-MCX-V1-CONNECTION", None, False, False, False)
    with pytest.raises(ValueError, match="MCX_CONFIRMED_1H_ENTRY_REQUIRED"):
        synthetic_bound.observe_tick(synthetic_position.position_id,
                                     v1_cmp, v1_schedule)
    before_v1_rejections = _inventory(tmp_path)
    for bad_cmp in (
        replace(v1_cmp, instrument=facts[McxFamily.GOLDM][1].instrument),
        replace(v1_cmp, observed_at=current.closed_at,
                received_at=current.closed_at),
        replace(v1_cmp, recovered=True),
    ):
        with pytest.raises(ValueError, match="MCX_V1_ENTRY_AUTHORITY_UNAVAILABLE"):
            synthetic_bound.activate_v1_paper_at_observed_cmp(
                synthetic_position.position_id, synthetic_plan, v1_outcome,
                bad_cmp, v1_schedule, plan_store=synthetic_plans,
                sponsor_store=synthetic_sponsor, outcome_store=v1_outcomes,
                connection_state=MonitoringConnectionState.CONNECTED,
                commit_guard=nullcontext,
                current_readset=lambda bad_cmp=bad_cmp:
                    (synthetic_plan, v1_outcome, bad_cmp))
    with pytest.raises(ValueError, match="MCX_V1_ENTRY_INPUT_INVALID"):
        synthetic_bound.activate_v1_paper_at_observed_cmp(
            synthetic_position.position_id, synthetic_plan, v1_outcome,
            v1_cmp, v1_schedule, plan_store=synthetic_plans,
            sponsor_store=synthetic_sponsor, outcome_store=v1_outcomes,
            connection_state=MonitoringConnectionState.DISCONNECTED,
            commit_guard=nullcontext,
            current_readset=lambda: (synthetic_plan, v1_outcome, v1_cmp))
    assert _inventory(tmp_path) == before_v1_rejections
    from kronos.provider.contracts.monitoring import MonitoringSubscriptionEvidence
    recovered_evidence = MonitoringSubscriptionEvidence(
        v1_cmp.instrument, v1_cmp.connection_id, current.closed_at,
        MonitoringConnectionState.CONTEXT_INCOMPLETE)
    for context, recheck in ((None, lambda: None),
                             (recovered_evidence, lambda: None)):
        with pytest.raises(ValueError, match="MCX_V1_ENTRY_SUBSCRIPTION_CHANGED"):
            synthetic_bound.activate_v1_paper_at_observed_cmp(
                synthetic_position.position_id, synthetic_plan, v1_outcome,
                v1_cmp, v1_schedule, plan_store=synthetic_plans,
                sponsor_store=synthetic_sponsor, outcome_store=v1_outcomes,
                connection_state=MonitoringConnectionState.CONTEXT_INCOMPLETE,
                subscription_evidence=context, current_subscription=recheck,
                commit_guard=nullcontext,
                current_readset=lambda: (synthetic_plan, v1_outcome, v1_cmp))
    assert _inventory(tmp_path) == before_v1_rejections
    outage_at = current.closed_at + timedelta(seconds=1)
    unavailable = synthetic_service.monitoring_unavailable(
        synthetic_position.position_id, occurred_at=outage_at,
        provider_context="ISOLATED_RECONNECT",
    )
    assert unavailable.state is ActiveLifecycleState.MONITORING_UNAVAILABLE
    before_cached_quote = _inventory(tmp_path)
    cached_quote = replace(v1_cmp, observed_at=outage_at)
    with pytest.raises(ValueError, match="MCX_V1_ENTRY_AUTHORITY_UNAVAILABLE"):
        synthetic_bound.activate_v1_paper_at_observed_cmp(
            synthetic_position.position_id, synthetic_plan, v1_outcome,
            cached_quote, v1_schedule, plan_store=synthetic_plans,
            sponsor_store=synthetic_sponsor, outcome_store=v1_outcomes,
            connection_state=MonitoringConnectionState.CONNECTED,
            commit_guard=nullcontext,
            current_readset=lambda: (synthetic_plan, v1_outcome, cached_quote))
    assert _inventory(tmp_path) == before_cached_quote
    # Exercise the retained advisory through actual owner -> hub -> adapter
    # reconnection. Only socket and current-session Review fixture are synthetic.
    from threading import RLock
    from tests.unit.swing.v1.test_mcx_contract_lifecycle import _wire_monitor
    clock = [outage_at + timedelta(milliseconds=100)]
    recovered_control = object.__new__(SwingMcxV1OperationalControl)
    recovered_control._lock = RLock()
    # Match the real constructor before binding the serial tick callback.
    recovered_control._research_capture = None
    recovered_control.research_capture_failure = None
    recovered_research = []
    if live_advisory:
        recovered_control.register_research_capture(
            lambda kind, value: recovered_research.append((kind, value)))
    recovered_control.lifecycle = synthetic_service
    recovered_control.workflow = SimpleNamespace(run_identity=synthetic_plan.native_run_identity)
    recovered_control.review_owner = native_intake
    recovered_control._plan = lambda *_args: synthetic_plan
    exact = facts[McxFamily.GOLDM][0].instrument
    recovered_control._current_plan_owner = lambda _plan: (
        exact, SimpleNamespace(final_fence=nullcontext))
    recovered_control.calendar = MarketCalendarPublisher()
    recovered_control.outcomes = v1_outcomes
    recovered_control.bound = synthetic_bound
    recovered_control.plans = synthetic_plans
    recovered_control.sponsor = synthetic_sponsor
    monitor, capability, hub = _wire_monitor(
        synthetic_service, synthetic_historical, exact, clock,
        recovered_control.on_paper_tick)
    monitor.attach(synthetic_position.position_id, capability, exact)
    old_consumer = monitor._consumers[synthetic_position.position_id]
    clock[0] += timedelta(milliseconds=100)
    capability.socket.on_close(capability.socket, 1006, "isolated outage")
    clock[0] += timedelta(milliseconds=100)
    capability.socket.on_connect(capability.socket, {})
    assert capability.session.state is MonitoringConnectionState.CONTEXT_INCOMPLETE
    assert len(capability.sessions) == hub.active_session_count == 1
    assert capability.socket.subscribed == [[202], [202]]
    before_fresh = _inventory(tmp_path)
    clock[0] = v1_cmp.received_at
    capability.tick(102, observed=outage_at)
    assert _inventory(tmp_path) == before_fresh
    assert v1_outcomes.load_for_plan(synthetic_plan.trade_plan_id) == v1_outcome
    if not live_advisory:
        monitor.close()
        synthetic_service = ActiveTradeLifecycleService(
            LocalActiveTradeLifecycleStore(tmp_path / "v1-current-lifecycle"))
        synthetic_bound = McxContractBoundLifecycle(synthetic_service, synthetic_historical)
        recovered_control.lifecycle = synthetic_service
        recovered_control.bound = synthetic_bound
        monitor, capability, hub = _wire_monitor(
            synthetic_service, synthetic_historical, exact, clock,
            recovered_control.on_paper_tick)
        assert monitor.restore(capability, lambda _: pytest.fail("family rebind")) == (synthetic_position.position_id,)
        old_consumer.on_connection_state(MonitoringConnectionState.DISCONNECTED)
        old_consumer.on_market_tick(v1_cmp)
        assert _inventory(tmp_path) == before_fresh
        cmp_at = clock[0] + timedelta(seconds=1)
        v1_cmp = replace(v1_cmp, observed_at=cmp_at,
                         received_at=cmp_at + timedelta(seconds=1))
    clock[0] = v1_cmp.received_at
    try:
        capability.tick(102, observed=v1_cmp.observed_at)
        v1_cmp, recorded_connection = monitor.latest_mcx_observation(synthetic_position.position_id)
        activated = synthetic_service._require(synthetic_position.position_id)
        assert hub.subscription_reference_count(exact) == 1
        assert len(capability.sessions) == 1
    finally:
        monitor.close()
    assert activated.state is ActiveLifecycleState.PAPER_ACTIVE
    assert activated.actual_entry == Decimal("102")
    assert recovered_control.research_capture_failure is None
    assert recovered_research == (
        [("LIFECYCLE", activated)] if live_advisory else [])
    assert activated.entry_timestamp == v1_cmp.received_at
    assert any(recorded_connection.value in event.provider_provenance
               and v1_cmp.connection_id in event.provider_provenance
               for event in synthetic_service.snapshot().events)
    assert synthetic_bound.activate_v1_paper_at_observed_cmp(
        synthetic_position.position_id, synthetic_plan, v1_outcome,
        v1_cmp, v1_schedule, plan_store=synthetic_plans,
        sponsor_store=synthetic_sponsor, outcome_store=v1_outcomes,
        connection_state=MonitoringConnectionState.CONNECTED,
        commit_guard=nullcontext,
        current_readset=lambda: (synthetic_plan, v1_outcome, v1_cmp)) == activated
    later_cmp = replace(v1_cmp, observed_at=cmp_at + timedelta(minutes=2),
                        received_at=cmp_at + timedelta(minutes=2, seconds=1),
                        last_price=Decimal("103"))
    with pytest.raises(ValueError, match="MCX_V1_ENTRY_REPLAY_MISMATCH"):
        synthetic_bound.activate_v1_paper_at_observed_cmp(
            synthetic_position.position_id, synthetic_plan, v1_outcome,
            later_cmp, v1_schedule, plan_store=synthetic_plans,
            sponsor_store=synthetic_sponsor, outcome_store=v1_outcomes,
            connection_state=MonitoringConnectionState.CONNECTED,
            commit_guard=nullcontext,
            current_readset=lambda: (synthetic_plan, v1_outcome, later_cmp))
    restarted_v1 = McxContractBoundLifecycle(
        ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(
            tmp_path / "v1-current-lifecycle")), synthetic_historical)
    with pytest.raises(ValueError, match="MCX_FACTUAL_EXIT_CMP_REQUIRED"):
        restarted_v1.manual_paper_exit_current(synthetic_position.position_id)
    clock[0] = v1_cmp.received_at + timedelta(seconds=1)
    monitor, capability, hub = _wire_monitor(
        restarted_v1.service, synthetic_historical, exact, clock)
    assert monitor.restore(capability, lambda _: pytest.fail("family rebind")) == (synthetic_position.position_id,)
    recovered_control.lifecycle = restarted_v1.service
    recovered_control.bound = restarted_v1
    recovered_control.native_review = SimpleNamespace(
        latest_mcx_observation=monitor.latest_mcx_observation)
    clock[0] += timedelta(seconds=1)
    capability.socket.on_close(capability.socket, 1006, "active fixture outage")
    clock[0] += timedelta(seconds=1)
    capability.socket.on_connect(capability.socket, {})
    assert capability.session.state is MonitoringConnectionState.CONTEXT_INCOMPLETE
    try:
        clock[0] = later_cmp.received_at
        capability.tick(103, observed=later_cmp.observed_at)
        active = restarted_v1.service._require(synthetic_position.position_id)
        assert active.actual_entry == activated.actual_entry
        assert active.entry_timestamp == activated.entry_timestamp
        assert active.mcx_activation_outcome_sha256 == v1_outcome.integrity_sha256
        assert sum(event.event_type.value == "PAPER_ENTRY_CAPTURED"
                   for event in restarted_v1.service.snapshot().events) == 1
        closure_v1 = recovered_control.paper_exit(active.position_id, active.integrity_hash)
    finally:
        monitor.close()
    assert closure_v1.actual_exit == Decimal("103")
    assert closure_v1.gross_pnl is None
    assert closure_v1.mcx_v1_contract_symbol == synthetic_plan.contract_symbol
    live_signal = v1_outcome if live_advisory else None
    live_signals = v1_outcomes if live_advisory else LocalMcxV1AdvisoryStore(tmp_path / "outside-model")
    live_entry_bytes = b"isolated sponsor broker entry receipt"
    live_fill_at = v1_cmp.received_at + timedelta(minutes=5)
    live_attestation = McxLiveFillAttestation.create(
        synthetic_plan, contract_symbol=synthetic_plan.contract_symbol,
        expiry=synthetic_plan.expiry, lots=3,
        provider_order_quantity=None, entry_outcome=live_signal,
        fill_price=Decimal("102"), fill_at=live_fill_at,
        broker_evidence_id="V1-LIVE-ENTRY",
        broker_evidence_sha256=sha256(live_entry_bytes).hexdigest(),
        attested_at=live_fill_at + timedelta(seconds=1), v1_manual=True)
    live_decided_at = live_attestation.attested_at + timedelta(seconds=1)
    live_attestations = LocalMcxLiveFillAttestationStore(
        tmp_path / "v1-live-attestations")
    live_broker = LocalMcxBrokerFillEvidenceStore(tmp_path / "v1-live-broker")
    live_sponsor = LocalSponsorDecisionStore(tmp_path / "v1-live-sponsor")
    before_live_rejection = _inventory(tmp_path)
    with pytest.raises(ValueError, match="MCX_LIVE_FILL_PLAN_MISMATCH"):
        admit_v1_mcx_manual_live(
            synthetic_plan, synthetic_judgment, synthetic_risk, live_signal,
            live_signals, McxLiveFillAttestation.create(
                synthetic_plan, contract_symbol="WRONG26OCTFUT",
                expiry=synthetic_plan.expiry, lots=3,
                provider_order_quantity=None, entry_outcome=live_signal,
                fill_price=Decimal("102"), fill_at=live_fill_at,
                broker_evidence_id="WRONG-ENTRY",
                broker_evidence_sha256=sha256(live_entry_bytes).hexdigest(),
                attested_at=live_fill_at + timedelta(seconds=1),
                v1_manual=True),
            live_attestations, live_broker, live_entry_bytes, live_sponsor,
            current_plan_id=synthetic_plan.trade_plan_id,
            decided_at=live_decided_at)
    with pytest.raises(ValueError, match="MCX_V1_BROKER_EVIDENCE_MISMATCH"):
        admit_v1_mcx_manual_live(
            synthetic_plan, synthetic_judgment, synthetic_risk, live_signal,
            live_signals, live_attestation, live_attestations,
            live_broker, b"conflicting broker receipt", live_sponsor,
            current_plan_id=synthetic_plan.trade_plan_id,
            decided_at=live_decided_at)
    assert _inventory(tmp_path) == before_live_rejection
    live_result = admit_v1_mcx_manual_live(
        synthetic_plan, synthetic_judgment, synthetic_risk, live_signal,
        live_signals, live_attestation, live_attestations, live_broker,
        live_entry_bytes, live_sponsor,
        current_plan_id=synthetic_plan.trade_plan_id,
        decided_at=live_decided_at)
    live_service = ActiveTradeLifecycleService(
        LocalActiveTradeLifecycleStore(tmp_path / "v1-live-lifecycle"))
    live_position = live_service.register(live_result, synthetic_plan)
    assert live_position.lots == 3
    assert "Intrabar trade continuity: UNVERIFIED" in _native_active_lifecycle(live_service.snapshot())
    assert live_attestation.model_relation == ("ADVISORY_CONFIRMED" if live_advisory else "SPONSOR_DIRECTED_OUTSIDE_MODEL")
    if not live_advisory:
        assert live_attestation.entry_outcome_id is None
        assert live_attestation.entry_outcome_at is None
        assert "SPONSOR-DIRECTED / OUTSIDE MODEL" in live_result.position.provenance
        assert "SPONSOR-DIRECTED / OUTSIDE MODEL" in _native_active_lifecycle(live_service.snapshot())
    assert live_position.actual_entry == Decimal("102")
    assert live_position.mcx_quantity is None
    live_historical = LocalMcxHistoricalContractStore(
        tmp_path / "v1-live-historical")
    live_bound = McxContractBoundLifecycle(live_service, live_historical)
    live_binding = live_bound.retain_existing(
        live_position.position_id, facts[McxFamily.GOLDM][0].instrument)
    live_broker.verify(McxBrokerFillCapture.from_attestation(
        live_position.position_id, live_attestation, live_entry_bytes),
        live_attestation, live_position, live_binding)
    assert admit_v1_mcx_manual_live(
        synthetic_plan, synthetic_judgment, synthetic_risk, live_signal,
        live_signals, live_attestation, live_attestations, live_broker,
        live_entry_bytes, live_sponsor,
        current_plan_id=synthetic_plan.trade_plan_id,
        decided_at=live_decided_at) == live_result
    live_exit_bytes = b"isolated sponsor broker exit receipt"
    exit_fill_at = live_fill_at + timedelta(minutes=10)
    exit_attestation = McxLiveFillAttestation.create(
        synthetic_plan, contract_symbol=synthetic_plan.contract_symbol,
        expiry=synthetic_plan.expiry, lots=3,
        provider_order_quantity=None, entry_outcome=live_signal,
        fill_price=Decimal("103"), fill_at=exit_fill_at,
        broker_evidence_id="V1-LIVE-EXIT",
        broker_evidence_sha256=sha256(live_exit_bytes).hexdigest(),
        attested_at=exit_fill_at + timedelta(seconds=1), v1_manual=True)
    original_exit = live_service.record_live_exit
    # Sponsor's factual broker exit is independent of Provider availability.
    # No new-entry gate or fictitious reconnect may be imposed on this exit.
    live_bound.monitoring_unavailable(
        live_position.position_id, occurred_at=live_fill_at + timedelta(minutes=1),
        provider_context="ISOLATED_DISCONNECT_BEFORE_ATTESTED_EXIT")
    monkeypatch.setattr(live_service, "record_live_exit",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            RuntimeError("ISOLATED_EXIT_INTERRUPTED")))
    with pytest.raises(RuntimeError, match="ISOLATED_EXIT_INTERRUPTED"):
        live_bound.record_live_exit(
            live_position.position_id, actual_exit=Decimal("103"),
            exit_timestamp=exit_fill_at,
            reason=TradeExitReason.SPONSOR_MANUAL_EXIT,
            attestation=exit_attestation,
            attestation_store=live_attestations,
            broker_store=live_broker, broker_bytes=live_exit_bytes)
    monkeypatch.setattr(live_service, "record_live_exit", original_exit)
    live_restarted = McxContractBoundLifecycle(
        ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(
            tmp_path / "v1-live-lifecycle")), live_historical)
    recovered = live_restarted.recover_retained_live_exit(
        live_position.position_id, live_attestations, live_broker)
    assert recovered.actual_exit == Decimal("103")
    assert recovered.gross_pnl is None
    assert not any(event.event_type.value == "MONITORING_RESUMED"
                   for event in live_restarted.service.snapshot().events)
    assert live_restarted.recover_retained_live_exit(
        live_position.position_id, live_attestations, live_broker) == recovered
    before_conflicting_exit = _inventory(tmp_path)
    conflicting_exit_bytes = b"different sponsor broker exit receipt"
    conflicting_exit = McxLiveFillAttestation.create(
        synthetic_plan, contract_symbol=synthetic_plan.contract_symbol,
        expiry=synthetic_plan.expiry, lots=3,
        provider_order_quantity=None, entry_outcome=live_signal,
        fill_price=Decimal("104"),
        fill_at=exit_fill_at + timedelta(seconds=1),
        broker_evidence_id="V1-LIVE-CONFLICT",
        broker_evidence_sha256=sha256(conflicting_exit_bytes).hexdigest(),
        attested_at=exit_fill_at + timedelta(seconds=2), v1_manual=True)
    with pytest.raises(ValueError, match="MCX_LIVE_EXIT_REPLAY_MISMATCH"):
        live_restarted.record_live_exit(
            live_position.position_id, actual_exit=Decimal("104"),
            exit_timestamp=conflicting_exit.fill_at,
            reason=TradeExitReason.SPONSOR_MANUAL_EXIT,
            attestation=conflicting_exit,
            attestation_store=live_attestations,
            broker_store=live_broker,
            broker_bytes=conflicting_exit_bytes)
    assert _inventory(tmp_path) == before_conflicting_exit
    live_broker.verify_exit(McxBrokerFillCapture.from_attestation(
        live_position.position_id, exit_attestation, live_exit_bytes),
        exit_attestation, recovered, live_binding)
    pending, record, path = workflow.prepare_durable_plan(
        native_intake, McxFamily.GOLDM, facts[McxFamily.GOLDM][0].instrument,
        proof, geometry, prepared_at=PLAN_NOW, lots=1,
        maximum_stop_risk=Decimal("1000000"),
    )
    assert path.is_file() and workflow.plans.load(path) == record
    assert record.receipt_integrity_sha256 == bound.receipt_integrity_sha256
    assert record.promotion_integrity_sha256 == bound.promotion_integrity_sha256
    reasons = workflow.sponsor_admission_reasons(
        record, pending, selected.prepared, proof, observed_at=PLAN_NOW,
    )
    assert "MCX_STEP31_NOT_COMMISSIONED" in reasons
    assert not pending.entry_authority

    # Explicit isolated dependencies complete the actual Trade Plan, Sponsor
    # record and one position. Production has no fixture adapter or route.
    fixture_facts = McxIsolatedAdmissionFacts(
        effective_specification_sha256=proof.effective_specification_sha256,
        quote_quantity_per_lot=pending.risk.quote_quantity_per_lot,
        provider_quantity_semantics=proof.quantity_semantics,
        expiry_session_identity=proof.expiry_session_identity,
        entry_blackout_policy_identity=proof.entry_blackout_policy_identity,
        one_hour_invalidation_policy_identity="ISOLATED-MCX-1H-STOP",
        sponsor_risk_policy_identity="ISOLATED-MCX-PAPER-RISK",
        paper_choice_policy_identity="ISOLATED-MCX-ONE-CONTRACT-PAPER",
        maximum_stop_risk=pending.risk.maximum_stop_risk,
        margin_policy_identity="ISOLATED-PAPER-NO-BROKER-MARGIN",
        quantity=McxTypedQuantity(
            lots=1,
            physical_quantity_per_lot=mcx_unit_profile(McxFamily.GOLDM).trading_quantity,
            physical_unit=mcx_unit_profile(McxFamily.GOLDM).trading_unit,
            quotation_base_quantity=mcx_unit_profile(McxFamily.GOLDM).quotation_quantity,
            quotation_unit=mcx_unit_profile(McxFamily.GOLDM).quotation_unit,
            rupees_per_price_point_per_lot=pending.risk.quote_quantity_per_lot,
            provider_order_quantity=1, provider_order_unit="LOTS",
            provider_conversion_identity="ISOLATED-GOLDM-LOTS-CONVERSION",
            proof_origin=McxQuantityProofOrigin.ISOLATED_FIXTURE,
        ),
    )
    before_conversion_rejection = _inventory(tmp_path)
    with pytest.raises(ValueError, match="MCX_TYPED_QUANTITY_INVALID"):
        replace(fixture_facts.quantity, provider_conversion_identity="")
    with pytest.raises(ValueError, match="MCX_ISOLATED_ADMISSION_FACTS_INVALID"):
        replace(fixture_facts, provider_quantity_semantics=McxQuantitySemantics.BASE_UNITS)
    assert _inventory(tmp_path) == before_conversion_rejection
    trade_plans = LocalMcxTradePlanStore(tmp_path / "trade-plans")
    plan, plan_path = workflow.construct_isolated_trade_plan(
        native_intake, McxFamily.GOLDM, facts[McxFamily.GOLDM][0].instrument,
        record, pending, geometry, proof, fixture_facts, trade_plans,
        opportunity=read.requirement.thesis.opportunity_identity,
        created_at=PLAN_NOW,
    )
    assert trade_plans.load(plan_path) == plan
    assert plan.contract_symbol == facts[McxFamily.GOLDM][0].instrument.trading_symbol
    assert plan.receipt_integrity_sha256 == record.receipt_integrity_sha256
    with pytest.raises(ValueError, match="QUALIFICATION_INVALID"):
        construct_isolated_mcx_trade_plan(
            record, pending, selected.prepared, geometry, proof,
            replace(fixture_facts, effective_specification_sha256="c" * 64),
            selection_sha256=workflow.selections.load(
                workflow.run_identity, McxFamily.GOLDM,
            ).integrity_sha256,
            opportunity=read.requirement.thesis.opportunity_identity,
            created_at=PLAN_NOW,
        )
    with pytest.raises(ValueError, match="QUALIFICATION_INVALID"):
        construct_isolated_mcx_trade_plan(
            record, pending, selected.prepared, geometry, proof, fixture_facts,
            selection_sha256=workflow.selections.load(
                workflow.run_identity, McxFamily.GOLDM,
            ).integrity_sha256,
            opportunity=read.requirement.thesis.opportunity_identity,
            created_at=proof.expiry_eligibility_boundary,
        )
    judgment = create_trade_plan_business_judgment(
        plan, validation_identity="ISOLATED-MCX-SPONSOR-JUDGMENT", created_at=PLAN_NOW,
    )
    risk = record_trade_plan_risk_result(
        plan, judgment, RiskState.APPROVED, reason="ISOLATED_FIXTURE_APPROVED",
        evaluated_at=PLAN_NOW,
    )
    sponsor_store = LocalSponsorDecisionStore(tmp_path / "sponsor")
    before_rejection = _inventory(tmp_path)
    with pytest.raises(ValueError, match="MCX_SPONSOR_PLAN_STALE"):
        admit_isolated_mcx_paper(
            plan, judgment, risk, sponsor_store,
            current_plan_id="MCX-TRADE-PLAN-" + "f" * 64,
            decided_at=PLAN_NOW + timedelta(seconds=1),
        )
    rejected_risk = record_trade_plan_risk_result(
        plan, judgment, RiskState.REJECTED, reason="ISOLATED_REJECTED",
        evaluated_at=PLAN_NOW,
    )
    with pytest.raises(ValueError, match="MCX_SPONSOR_RISK_UNAVAILABLE"):
        admit_isolated_mcx_paper(
            plan, judgment, rejected_risk, sponsor_store,
            current_plan_id=plan.trade_plan_id,
            decided_at=PLAN_NOW + timedelta(seconds=1),
        )
    assert _inventory(tmp_path) == before_rejection
    lifecycle_root = tmp_path / "actual-lifecycle"
    historical_root = tmp_path / "actual-historical"
    lifecycle_service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(lifecycle_root))
    historical_store = LocalMcxHistoricalContractStore(historical_root)
    initiation, admitted, contract_binding = workflow.admit_isolated_paper_position(
        native_intake, McxFamily.GOLDM, facts[McxFamily.GOLDM][0].instrument,
        plan, trade_plans, sponsor_store, lifecycle_service, historical_store,
        judgment, risk, decided_at=PLAN_NOW + timedelta(seconds=1),
    )
    assert initiation.state is SponsorInitiationState.PAPER_ARMED
    assert initiation.position.position_id == admitted.position_id
    assert initiation.position.lots == 1
    assert initiation.position.lot_size == 1
    assert initiation.position.underlying_quantity == 1
    assert initiation.position.mcx_quantity == plan.quantity
    assert plan.quantity.physical_quantity == Decimal("100")
    assert plan.quantity.price_to_rupee_multiplier == Decimal("10")
    assert initiation.decision.trade_plan_integrity_hash == plan.integrity_hash
    assert contract_binding.trade_plan_hash == plan.integrity_hash
    assert sponsor_store.load_plan(plan.native_run_identity, plan.trade_plan_id) == initiation
    before_replay = _inventory(tmp_path)
    replay = workflow.admit_isolated_paper_position(
        native_intake, McxFamily.GOLDM, facts[McxFamily.GOLDM][0].instrument,
        plan, trade_plans, sponsor_store, lifecycle_service, historical_store,
        judgment, risk, decided_at=PLAN_NOW + timedelta(seconds=1),
    )
    assert replay == (initiation, admitted, contract_binding)
    assert _inventory(tmp_path) == before_replay

    instrument = facts[McxFamily.GOLDM][0].instrument
    schedule = MarketCalendarPublisher().schedule(
        "MCX", PLAN_NOW.date(), observed_at=PLAN_NOW,
    )

    def tick(minute, price, contract=instrument):
        stamp = PLAN_NOW + timedelta(minutes=minute)
        return ProviderMarketTick(
            contract, Decimal(price), stamp, stamp, "KITE_CONNECT_WEBSOCKET",
            "ISOLATED-MCX-CONNECTION", minute, True, True, True,
        )

    bound_lifecycle = McxContractBoundLifecycle(lifecycle_service, historical_store)
    before_unconfirmed_tick = _inventory(tmp_path)
    with pytest.raises(ValueError, match="MCX_CONFIRMED_1H_ENTRY_REQUIRED"):
        bound_lifecycle.observe_tick(admitted.position_id, tick(1, "99"), schedule)
    with pytest.raises(ValueError, match="MCX_CONFIRMED_1H_ENTRY_REQUIRED"):
        bound_lifecycle.observe_tick(admitted.position_id, tick(2, "102"), schedule)
    assert _inventory(tmp_path) == before_unconfirmed_tick
    # Restart both retained owners; the *same* Sponsor position enters and exits.
    restarted = McxContractBoundLifecycle(
        ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(lifecycle_root)),
        LocalMcxHistoricalContractStore(historical_root),
    )
    assert restarted.service.snapshot().positions[0].position_id == admitted.position_id
    before_wrong_contract = restarted.service.snapshot()
    with pytest.raises(ValueError, match="TICK_MISMATCH"):
        restarted.observe_tick(
            admitted.position_id, tick(2, "102", facts[McxFamily.GOLDM][1].instrument),
            schedule,
        )
    assert restarted.service.snapshot() == before_wrong_contract
    authority = _confirmed_entry(plan, risk)
    outcome_store = LocalKr380V2Store(tmp_path / "kr380-outcomes")
    outcome_store.retain_current(authority.outcome)
    wrong_risk_authority = _confirmed_entry(
        plan, replace(risk, risk_result_id="WRONG-RISK"),
    )
    wrong_risk_store = LocalKr380V2Store(tmp_path / "wrong-risk-outcomes")
    wrong_risk_store.retain_current(wrong_risk_authority.outcome)
    before_rejected_entry = _inventory(tmp_path)
    with pytest.raises(ValueError, match="MCX_CONFIRMED_ENTRY_UNAVAILABLE"):
        restarted.activate_confirmed_entry(
            admitted.position_id, plan, None,
            schedule=schedule, plan_store=trade_plans, sponsor_store=sponsor_store, outcome_store=outcome_store,
            commit_guard=selected.final_fence,
            current_readset=lambda: (plan, authority),
        )
    with pytest.raises(ValueError, match="MCX_CONFIRMED_1H_ENTRY_INVALID"):
        _confirmed_entry(plan, risk, state=Kr380V2State.NO_TRIGGER)
    with pytest.raises(ValueError, match="MCX_CONFIRMED_1H_ENTRY_INVALID"):
        replace(authority, contract_symbol="GOLDM26SEPFUT")
    with pytest.raises(ValueError, match="MCX_CONFIRMED_1H_ENTRY_INVALID"):
        replace(authority, paper_entry_tick=replace(
            authority.paper_entry_tick, observed_at=authority.outcome.occurred_at))
    with pytest.raises(ValueError, match="MCX_CONFIRMED_1H_ENTRY_INVALID"):
        replace(authority, paper_entry_tick=replace(
            authority.paper_entry_tick,
            instrument=facts[McxFamily.GOLDM][1].instrument))
    with pytest.raises(ValueError, match="MCX_CONFIRMED_1H_ENTRY_INVALID"):
        replace(authority, setup_one_hour_sha256="e" * 64)
    with pytest.raises(ValueError, match="MCX_CONFIRMED_1H_ENTRY_INVALID"):
        replace(authority, paper_cmp_predecessor=replace(
            authority.paper_cmp_predecessor, source_sequence=120))
    with pytest.raises(ValueError, match="MCX_CONFIRMED_1H_ENTRY_INVALID"):
        replace(authority, paper_cmp_predecessor=replace(
            authority.paper_cmp_predecessor,
            received_at=authority.outcome.occurred_at + timedelta(seconds=1)))
    delayed = replace(authority, paper_entry_tick=replace(
        authority.paper_entry_tick,
        observed_at=authority.outcome.occurred_at + timedelta(minutes=5),
        received_at=authority.outcome.occurred_at + timedelta(minutes=5, seconds=2)))
    assert delayed.paper_entry_tick.received_at > authority.paper_entry_tick.received_at
    assert delayed.identity_sha256 != authority.identity_sha256
    with pytest.raises(ValueError, match="MCX_CONFIRMED_ENTRY_RETAINED_AUTHORITY_INVALID"):
        restarted.activate_confirmed_entry(
            admitted.position_id, plan, wrong_risk_authority,
            schedule=schedule, plan_store=trade_plans, sponsor_store=sponsor_store, outcome_store=wrong_risk_store,
            commit_guard=selected.final_fence,
            current_readset=lambda: (plan, wrong_risk_authority),
        )
    with pytest.raises(ValueError, match="MCX_CONFIRMED_ENTRY_STALE"):
        restarted.activate_confirmed_entry(
            admitted.position_id, plan, authority,
            schedule=schedule, plan_store=trade_plans, sponsor_store=sponsor_store, outcome_store=outcome_store,
            commit_guard=selected.final_fence,
            current_readset=lambda: (plan, replace(
                authority, paper_entry_tick=replace(
                    authority.paper_entry_tick, last_price=Decimal("104")))),
        )
    with pytest.raises(ValueError, match="MCX_TRADE_PLAN_INTEGRITY_INVALID"):
        restarted.activate_confirmed_entry(
            admitted.position_id, plan, authority,
            schedule=schedule, plan_store=LocalMcxTradePlanStore(tmp_path / "missing-trade-plans"),
            sponsor_store=sponsor_store, outcome_store=outcome_store,
            commit_guard=selected.final_fence,
            current_readset=lambda: (plan, authority),
        )
    assert _inventory(tmp_path) == before_rejected_entry
    active = restarted.activate_confirmed_entry(
        admitted.position_id, plan, authority,
        schedule=schedule, plan_store=trade_plans, sponsor_store=sponsor_store, outcome_store=outcome_store,
        commit_guard=selected.final_fence,
        current_readset=lambda: (plan, authority),
    )
    assert active.state is ActiveLifecycleState.PAPER_ACTIVE
    assert active.position_id == initiation.position.position_id
    assert active.actual_entry == Decimal("103")
    assert active.entry_timestamp == authority.paper_entry_tick.received_at
    assert active.entry_timestamp > authority.outcome.occurred_at
    assert active.mcx_activation_outcome_sha256 == authority.identity_sha256
    before_entry_replay = _inventory(tmp_path)
    assert restarted.activate_confirmed_entry(
        admitted.position_id, plan, authority,
        schedule=schedule, plan_store=trade_plans, sponsor_store=sponsor_store, outcome_store=outcome_store,
        commit_guard=selected.final_fence,
        current_readset=lambda: (plan, authority),
    ) == active
    assert _inventory(tmp_path) == before_entry_replay
    different_outcome = replace(authority, paper_entry_tick=replace(
        authority.paper_entry_tick, last_price=Decimal("104")))
    with pytest.raises(ValueError, match="MCX_ENTRY_REPLAY_MISMATCH"):
        restarted.activate_confirmed_entry(
            admitted.position_id, plan, different_outcome,
            schedule=schedule, plan_store=trade_plans, sponsor_store=sponsor_store, outcome_store=outcome_store,
            commit_guard=selected.final_fence,
            current_readset=lambda: (plan, different_outcome),
        )
    assert _inventory(tmp_path) == before_entry_replay
    restarted_again = McxContractBoundLifecycle(
        ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(lifecycle_root)),
        LocalMcxHistoricalContractStore(historical_root),
    )
    assert restarted_again.service.snapshot().positions[0].mcx_activation_outcome_sha256 == authority.identity_sha256
    assert restarted_again.activate_confirmed_entry(
        admitted.position_id, plan, authority,
        schedule=schedule, plan_store=trade_plans, sponsor_store=sponsor_store, outcome_store=outcome_store,
        commit_guard=selected.final_fence,
        current_readset=lambda: (plan, authority),
    ).position_id == admitted.position_id
    restarted_again.observe_tick(admitted.position_id, tick(61, "104"), schedule)
    assert "₹10" in _native_active_lifecycle(restarted_again.service.snapshot())
    closed = restarted_again.observe_tick(admitted.position_id, tick(62, "112"), schedule)
    assert closed.state is ActiveLifecycleState.CLOSED
    closure = restarted_again.service.snapshot().closures[0]
    assert closure.position_id == admitted.position_id
    assert closure.gross_pnl == Decimal("90")  # (112 - observed 103) * ten quoted units.
    assert closure.mcx_quantity == plan.quantity
    assert closure.cost_model == "NOT_INCLUDED_V0"
    assert any(value.startswith("MCX-CMP-") for value in closure.event_provenance)
    assert any(authority.paper_entry_observation_id in event.provider_provenance
               for event in restarted_again.service.snapshot().events)

    # LIVE uses a separate Sponsor attestation, never the PAPER CMP or Entry.
    live_store = LocalMcxLiveFillAttestationStore(tmp_path / "live-attestations")
    live_sponsor = LocalSponsorDecisionStore(tmp_path / "live-sponsor")
    live_root = tmp_path / "live-lifecycle"
    live_history_root = tmp_path / "live-historical"
    live_service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(live_root))
    live_history = LocalMcxHistoricalContractStore(live_history_root)
    fill_time = authority.outcome.occurred_at + timedelta(seconds=3)
    broker_fill_bytes = b"ISOLATED BROKER FILL RECEIPT GOLDM26OCTFUT 1 LOT 103"
    live_attestation = McxLiveFillAttestation.create(
        plan, contract_symbol=plan.contract_symbol, expiry=plan.expiry,
        lots=1, provider_order_quantity=plan.quantity.provider_order_quantity,
        entry_outcome=authority.outcome,
        fill_price=Decimal("103"), fill_at=fill_time,
        broker_evidence_id="ISOLATED-BROKER-FILL-1",
        broker_evidence_sha256=sha256(broker_fill_bytes).hexdigest(),
        attested_at=fill_time + timedelta(seconds=1),
    )
    live_before = _inventory(tmp_path)
    with pytest.raises(ValueError, match="MCX_LIVE_FILL_PLAN_MISMATCH"):
        workflow.admit_isolated_live_position(
            native_intake, McxFamily.GOLDM,
            facts[McxFamily.GOLDM][0].instrument,
            plan, trade_plans, live_sponsor, live_store,
            McxLiveFillAttestation.create(
                plan, contract_symbol="GOLDM-WRONG", expiry=plan.expiry,
                lots=1, provider_order_quantity=plan.quantity.provider_order_quantity,
                entry_outcome=authority.outcome,
                fill_price=Decimal("103"), fill_at=fill_time,
                broker_evidence_id="ISOLATED-BROKER-FILL-WRONG",
                broker_evidence_sha256="d" * 64,
                attested_at=fill_time + timedelta(seconds=1),
            ),
            authority.outcome, outcome_store,
            live_service, live_history, judgment, risk,
            decided_at=fill_time + timedelta(seconds=2),
        )
    with pytest.raises(ValueError, match="MCX_LIVE_FILL_PLAN_MISMATCH"):
        workflow.admit_isolated_live_position(
            native_intake, McxFamily.GOLDM,
            facts[McxFamily.GOLDM][0].instrument,
            plan, trade_plans, live_sponsor, live_store,
            McxLiveFillAttestation.create(
                plan, contract_symbol=plan.contract_symbol, expiry=plan.expiry,
                lots=2, provider_order_quantity=2,
                entry_outcome=authority.outcome,
                fill_price=Decimal("103"), fill_at=fill_time,
                broker_evidence_id="ISOLATED-BROKER-FILL-2",
                broker_evidence_sha256="e" * 64,
                attested_at=fill_time + timedelta(seconds=1),
            ), authority.outcome, outcome_store,
            live_service, live_history, judgment, risk,
            decided_at=fill_time + timedelta(seconds=2),
        )
    with pytest.raises(ValueError):
        workflow.admit_isolated_live_position(
            native_intake, McxFamily.GOLDM,
            facts[McxFamily.GOLDM][0].instrument,
            plan, trade_plans, live_sponsor, live_store, live_attestation,
            authority.outcome,
            LocalKr380V2Store(tmp_path / "missing-live-outcome"),
            live_service, live_history, judgment, risk,
            decided_at=fill_time + timedelta(seconds=2),
        )
    assert _inventory(tmp_path) == live_before
    live_result, live_position, live_binding = workflow.admit_isolated_live_position(
        native_intake, McxFamily.GOLDM, facts[McxFamily.GOLDM][0].instrument,
        plan, trade_plans, live_sponsor, live_store, live_attestation,
        authority.outcome, outcome_store,
        live_service, live_history, judgment, risk,
        decided_at=fill_time + timedelta(seconds=2),
    )
    assert live_store.load(plan.trade_plan_id) == live_attestation
    assert live_result.position.entry_timestamp == fill_time
    assert live_result.position.actual_entry == Decimal("103")
    assert live_attestation.integrity_sha256 in live_result.decision.provenance
    assert live_binding.instrument.trading_symbol == plan.contract_symbol
    capture = McxBrokerFillCapture.from_attestation(
        live_position.position_id, live_attestation, broker_fill_bytes,
    )
    broker_store = LocalMcxBrokerFillEvidenceStore(tmp_path / "isolated-broker-fill")
    broker_store.capture(capture, broker_fill_bytes)
    broker_store.verify(capture, live_attestation, live_position, live_binding)
    LocalMcxBrokerFillEvidenceStore(tmp_path / "isolated-broker-fill").verify(
        capture, live_attestation, live_position, live_binding,
    )
    with pytest.raises(ValueError, match="MCX_BROKER_FILL_BYTES_INVALID"):
        broker_store.capture(capture, b"CONFLICTING FILL")
    with pytest.raises(ValueError, match="MCX_BROKER_FILL_BINDING_INVALID"):
        broker_store.verify(replace(capture, contract_symbol="WRONG26OCTFUT"),
                            live_attestation, live_position, live_binding)
    tampered_store = LocalMcxBrokerFillEvidenceStore(tmp_path / "tampered-broker-fill")
    tampered_store.capture(capture, broker_fill_bytes)
    byte_path, _ = tampered_store._paths(capture)
    byte_path.write_bytes(b"TAMPERED")
    with pytest.raises(ValueError, match="MCX_BROKER_FILL_EVIDENCE_INVALID"):
        tampered_store.verify(capture, live_attestation, live_position,
                              live_binding)
    before_live_replay = _inventory(tmp_path)
    assert workflow.admit_isolated_live_position(
        native_intake, McxFamily.GOLDM, facts[McxFamily.GOLDM][0].instrument,
        plan, trade_plans, live_sponsor, live_store, live_attestation,
        authority.outcome, outcome_store,
        live_service, live_history, judgment, risk,
        decided_at=fill_time + timedelta(seconds=2),
    ) == (live_result, live_position, live_binding)
    with pytest.raises(ValueError, match="SPONSOR_DECISION_ALREADY_FINAL"):
        workflow.admit_isolated_live_position(
            native_intake, McxFamily.GOLDM, facts[McxFamily.GOLDM][0].instrument,
            plan, trade_plans, live_sponsor, live_store,
            McxLiveFillAttestation.create(
                plan, contract_symbol=plan.contract_symbol, expiry=plan.expiry,
                lots=1, provider_order_quantity=plan.quantity.provider_order_quantity,
                entry_outcome=authority.outcome,
                fill_price=Decimal("104"), fill_at=fill_time,
                broker_evidence_id="ISOLATED-CONFLICTING-FILL",
                broker_evidence_sha256="1" * 64,
                attested_at=fill_time + timedelta(seconds=1),
            ), authority.outcome, outcome_store,
            live_service, live_history, judgment, risk,
            decided_at=fill_time + timedelta(seconds=2),
        )
    assert _inventory(tmp_path) == before_live_replay
    live_restart = McxContractBoundLifecycle(
        ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(live_root)),
        LocalMcxHistoricalContractStore(live_history_root),
    )
    live_restart.observe_tick(live_position.position_id, tick(61, "104"), schedule)
    before_unattested_exit = _inventory(tmp_path)
    with pytest.raises(ValueError, match="MCX_LIVE_EXIT_ATTESTATION_UNAVAILABLE"):
        live_restart.record_live_exit(
            live_position.position_id, actual_exit=Decimal("108"),
            exit_timestamp=PLAN_NOW + timedelta(minutes=70),
            reason=TradeExitReason.SPONSOR_MANUAL_EXIT,
        )
    assert _inventory(tmp_path) == before_unattested_exit
    exit_at = PLAN_NOW + timedelta(minutes=70)
    broker_exit_bytes = b"ISOLATED BROKER EXIT RECEIPT GOLDM26OCTFUT 1 LOT 108"
    exit_attestation = McxLiveFillAttestation.create(
        plan, contract_symbol=plan.contract_symbol, expiry=plan.expiry,
        lots=1, provider_order_quantity=plan.quantity.provider_order_quantity,
        entry_outcome=authority.outcome,
        fill_price=Decimal("108"), fill_at=exit_at,
        broker_evidence_id="ISOLATED-BROKER-EXIT-1",
        broker_evidence_sha256=sha256(broker_exit_bytes).hexdigest(),
        attested_at=exit_at,
    )
    # The intent and attestation are durable before the lifecycle projection.
    # Interrupt exactly there, then restore from the retained pair once.
    original_exit = live_restart.service.record_live_exit
    def interrupted_exit(*args, **kwargs):
        raise RuntimeError("ISOLATED_EXIT_INTERRUPTION")
    monkeypatch.setattr(live_restart.service, "record_live_exit", interrupted_exit)
    with pytest.raises(RuntimeError, match="ISOLATED_EXIT_INTERRUPTION"):
        live_restart.record_live_exit(
            live_position.position_id, actual_exit=Decimal("108"),
            exit_timestamp=exit_at, reason=TradeExitReason.SPONSOR_MANUAL_EXIT,
            attestation=exit_attestation, attestation_store=live_store,
        )
    monkeypatch.setattr(live_restart.service, "record_live_exit", original_exit)
    assert live_store.load_exit(live_position.position_id) == exit_attestation
    assert not any(item.position_id == live_position.position_id
                   for item in live_restart.service.snapshot().closures)
    after_interruption = _inventory(tmp_path)
    conflicting_exit = McxLiveFillAttestation.create(
        plan, contract_symbol=plan.contract_symbol, expiry=plan.expiry,
        lots=1, provider_order_quantity=plan.quantity.provider_order_quantity,
        entry_outcome=authority.outcome, fill_price=Decimal("109"),
        fill_at=exit_at, broker_evidence_id="ISOLATED-CONFLICTING-EXIT",
        broker_evidence_sha256="a" * 64, attested_at=exit_at,
    )
    with pytest.raises(ValueError, match="MCX_LIVE_EXIT_INTENT_IMMUTABLE"):
        live_restart.record_live_exit(
            live_position.position_id, actual_exit=Decimal("109"),
            exit_timestamp=exit_at, reason=TradeExitReason.SPONSOR_MANUAL_EXIT,
            attestation=conflicting_exit, attestation_store=live_store,
        )
    assert _inventory(tmp_path) == after_interruption
    live_restart = McxContractBoundLifecycle(
        ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(live_root)),
        LocalMcxHistoricalContractStore(live_history_root),
    )
    original_position_write = live_restart.service.store.retain_position
    def interrupted_position_write(*args, **kwargs):
        raise RuntimeError("ISOLATED_POSITION_WRITE_INTERRUPTION")
    monkeypatch.setattr(live_restart.service.store, "retain_position",
                        interrupted_position_write)
    with pytest.raises(RuntimeError, match="ISOLATED_POSITION_WRITE_INTERRUPTION"):
        live_restart.recover_retained_live_exit(live_position.position_id, live_store)
    monkeypatch.setattr(live_restart.service.store, "retain_position",
                        original_position_write)
    assert any(item.position_id == live_position.position_id
               for item in live_restart.service.snapshot().closures)
    live_restart = McxContractBoundLifecycle(
        ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(live_root)),
        LocalMcxHistoricalContractStore(live_history_root),
    )
    live_closure = live_restart.recover_retained_live_exit(
        live_position.position_id, live_store,
    )
    recovered_snapshot = live_restart.service.snapshot()
    assert sum(item.position_id == live_position.position_id
               for item in recovered_snapshot.closures) == 1
    assert sum(item.position_id == live_position.position_id
               and item.event_type.value == "LIVE_EXIT_RECORDED"
               for item in recovered_snapshot.events) == 1
    assert live_restart.recover_retained_live_exit(
        live_position.position_id, live_store,
    ) == live_closure
    assert live_restart.service.snapshot() == recovered_snapshot
    live_closure = live_restart.record_live_exit(
        live_position.position_id, actual_exit=Decimal("108"),
        exit_timestamp=exit_at, reason=TradeExitReason.SPONSOR_MANUAL_EXIT,
        attestation=exit_attestation, attestation_store=live_store,
    )
    assert live_store.load_exit(live_position.position_id) == exit_attestation
    assert live_closure.gross_pnl == Decimal("50")
    assert live_closure.cost_model == "NOT_INCLUDED_V0"
    exit_capture = McxBrokerFillCapture.from_attestation(
        live_position.position_id, exit_attestation, broker_exit_bytes,
    )
    broker_store.capture(exit_capture, broker_exit_bytes)
    broker_store.verify_exit(exit_capture, exit_attestation, live_closure,
                             live_binding)
    assert live_restart.record_live_exit(
        live_position.position_id, actual_exit=Decimal("108"),
        exit_timestamp=exit_at, reason=TradeExitReason.SPONSOR_MANUAL_EXIT,
        attestation=exit_attestation, attestation_store=live_store,
    ) == live_closure
    with pytest.raises(ValueError, match="MCX_LIVE_EXIT_REPLAY_MISMATCH"):
        live_restart.record_live_exit(
            live_position.position_id, actual_exit=Decimal("108"),
            exit_timestamp=exit_at,
            reason=TradeExitReason.SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION,
            attestation=exit_attestation, attestation_store=live_store,
        )
    live_after_exit_restart = McxContractBoundLifecycle(
        ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(live_root)),
        LocalMcxHistoricalContractStore(live_history_root),
    )
    assert live_after_exit_restart.record_live_exit(
        live_position.position_id, actual_exit=Decimal("108"),
        exit_timestamp=exit_at, reason=TradeExitReason.SPONSOR_MANUAL_EXIT,
        attestation=exit_attestation, attestation_store=live_store,
    ) == live_closure
    intent_path = live_store.root / (live_position.position_id + ".exit-intent.json")
    retained_intent = intent_path.read_bytes()
    intent_path.unlink()  # Model a complete pre-2F isolated exit record.
    legacy_before = _inventory(tmp_path)
    assert live_after_exit_restart.record_live_exit(
        live_position.position_id, actual_exit=Decimal("108"),
        exit_timestamp=exit_at, reason=TradeExitReason.SPONSOR_MANUAL_EXIT,
        attestation=exit_attestation, attestation_store=live_store,
    ) == live_closure
    assert _inventory(tmp_path) == legacy_before
    intent_path.write_bytes(retained_intent)

    # A later admissible observed CMP is a fresh model fill; manual PAPER exit
    # requires another exact-contract factual CMP even after restoration.
    paper_root = tmp_path / "delayed-paper-lifecycle"
    paper_historical = tmp_path / "delayed-paper-historical"
    paper_service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(paper_root))
    paper_sponsor = LocalSponsorDecisionStore(tmp_path / "delayed-paper-sponsor")
    paper_binding = LocalMcxHistoricalContractStore(paper_historical)
    _, delayed_position, _ = workflow.admit_isolated_paper_position(
        native_intake, McxFamily.GOLDM, facts[McxFamily.GOLDM][0].instrument,
        plan, trade_plans, paper_sponsor, paper_service, paper_binding,
        judgment, risk, decided_at=PLAN_NOW + timedelta(seconds=1),
    )
    delayed_adapter = McxContractBoundLifecycle(paper_service, paper_binding)
    delayed_active = delayed_adapter.activate_confirmed_entry(
        delayed_position.position_id, plan, delayed,
        schedule=schedule, plan_store=trade_plans, sponsor_store=paper_sponsor,
        outcome_store=outcome_store, commit_guard=selected.final_fence,
        current_readset=lambda: (plan, delayed),
    )
    assert delayed_active.actual_entry == Decimal("103")
    assert delayed_active.entry_timestamp == delayed.paper_entry_tick.received_at
    assert delayed_active.lots == 1 and delayed_active.mcx_quantity.lots == 1
    delayed_restart = McxContractBoundLifecycle(
        ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(paper_root)),
        LocalMcxHistoricalContractStore(paper_historical),
    )
    before_bad_cmp = _inventory(tmp_path)
    with pytest.raises(ValueError, match="MCX_FACTUAL_EXIT_CMP_REQUIRED"):
        delayed_restart.manual_paper_exit_current(delayed_position.position_id)
    with pytest.raises(ValueError, match="MCX_FACTUAL_EXIT_CMP_UNAVAILABLE"):
        delayed_restart.manual_paper_exit_at_cmp(
            delayed_position.position_id, authority.paper_entry_tick, schedule,
        )
    with pytest.raises(ValueError, match="MCX_FACTUAL_EXIT_CMP_UNAVAILABLE"):
        delayed_restart.manual_paper_exit_at_cmp(
            delayed_position.position_id,
            tick(70, "104", facts[McxFamily.GOLDM][1].instrument), schedule,
        )
    assert _inventory(tmp_path) == before_bad_cmp
    paper_exit = delayed_restart.manual_paper_exit_at_cmp(
        delayed_position.position_id, tick(70, "104"), schedule,
    )
    assert paper_exit.actual_exit == Decimal("104")
    assert paper_exit.gross_pnl == Decimal("10")
    assert paper_exit.cost_model == "NOT_INCLUDED_V0"
    assert any(value.startswith("MCX-CMP-") for value in paper_exit.event_provenance)
    assert paper_exit == ActiveTradeLifecycleService(
        LocalActiveTradeLifecycleStore(paper_root),
    ).snapshot().closures[0]

    # An already-admitted historical contract is independent of the new run.
    position, old_contract, schedule, lifecycle, _, _ = historical_fixture(
        tmp_path / "historical",
    )
    with pytest.raises(ValueError, match="TICK_MISMATCH"):
        lifecycle.observe_tick(
            position.position_id, _tick(facts[McxFamily.GOLDM][0].instrument, 1, "99"),
            schedule,
        )
    lifecycle.observe_tick(position.position_id, _tick(old_contract, 1, "99"), schedule)
    lifecycle.observe_tick(position.position_id, _tick(old_contract, 2, "102"), schedule)
    assert lifecycle.manual_paper_exit_current(position.position_id).position_id == position.position_id


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_browser_choice_replay_stale_and_uninstalled_routes_fail_closed(
    tmp_path, scenario, native_intake,
):
    workflow, _ = _workflow(tmp_path, scenario, native_intake)
    handler, responses = _handler(None, "/swing/mcx-contract-offer?family=GOLDM")
    handler._mcx_contract_offer()
    assert responses == [(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")]
    handler, responses = _handler(None, "/swing/mcx-contract-choice", b"anything")
    handler._mcx_contract_choice()
    assert responses == [(HTTPStatus.CONFLICT, "MCX_STEP31_NOT_COMMISSIONED")]
    offer = workflow.offers[McxFamily.GOLDM]
    for fields in (
        [("run", workflow.run_identity), ("family", "GOLDM"),
         ("role", "NEAR"), ("offer_sha256", "0" * 64)],
        [("run", workflow.run_identity), ("family", "GOLDM"),
         ("role", "NEAR"), ("role", "NEXT_ELIGIBLE"),
         ("offer_sha256", offer.offer_sha256)],
    ):
        before = _inventory(tmp_path)
        handler, responses = _handler(workflow, "/swing/mcx-contract-choice", urlencode(fields).encode())
        handler._mcx_contract_choice()
        assert responses == [(HTTPStatus.CONFLICT, "MCX_CONTRACT_CHOICE_REJECTED")]
        assert _inventory(tmp_path) == before
    with pytest.raises(ValueError, match="MCX_SPONSOR_SELECTION_INTEGRITY_INVALID"):
        workflow.process_handoff()
    valid = urlencode({
        "run": workflow.run_identity, "family": "GOLDM", "role": "NEAR",
        "offer_sha256": offer.offer_sha256,
    }).encode()
    handler, responses = _handler(workflow, "/swing/mcx-contract-choice", valid)
    handler._mcx_contract_choice()
    assert responses[0][0] == HTTPStatus.SEE_OTHER
    before = _inventory(tmp_path)
    handler, responses = _handler(workflow, "/swing/mcx-contract-choice", valid)
    handler._mcx_contract_choice()
    assert responses == [(HTTPStatus.CONFLICT, "MCX_CONTRACT_CHOICE_REJECTED")]
    assert _inventory(tmp_path) == before
    workflow.publication.admit(
        "SWING-RUN-" + "F" * 32, CHOICE_TIME + timedelta(seconds=3),
    )
    before = _inventory(tmp_path)
    handler, responses = _handler(workflow, "/swing/mcx-contract-offer?family=GOLDM")
    handler._mcx_contract_offer()
    assert responses == [(HTTPStatus.CONFLICT, "MCX_CONTRACT_OFFER_UNAVAILABLE")]
    assert _inventory(tmp_path) == before
