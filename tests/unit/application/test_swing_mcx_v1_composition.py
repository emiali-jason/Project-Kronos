"""Canonical MCX composition, isolated stores and no external acquisition."""
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from http import HTTPStatus
from types import SimpleNamespace
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pytest

from kronos.application.swing_mcx_v1_composition import install_canonical_mcx_v1
from kronos.application.swing_mcx_v1_composition import SwingMcxV1Composition
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server, _BrowserHandler
from kronos.browser.views import render_mcx_v1_workspace, _tab_link
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.instrument_master_persistence import ProviderInstrumentSnapshotStore
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_contract_selection import McxSelectionRole
from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore, FactualTimeframe
from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.provider.test_instrument_master_snapshot import _snapshot, _source
from tests.unit.swing.test_run_publication import make_checkpoint
from tests.unit.swing.v1.test_opportunity_continuity import scenario
from tests.unit.browser.test_swing_review_intake_binding import native_intake
from tests.unit.swing.v1.test_mcx_contract_lifecycle import _fixture, START, _tick, _wire_monitor
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveTradeLifecycleService, LocalActiveTradeLifecycleStore,
    ActiveLifecycleState,
)
from kronos.swing.v1.mcx_contract_lifecycle import LocalMcxHistoricalContractStore


NOW = datetime(2026, 9, 30, 14, 0, tzinfo=ZoneInfo('Asia/Kolkata'))


def test_implemented_mcx_tab_is_not_placeholder_and_unknown_tabs_stay_held():
    implemented = _tab_link('MCX V1', '/swing/mcx-v1', 'MCX V1')
    assert 'href="/swing/mcx-v1"' in implemented
    assert 'class="active"' in implemented
    assert 'Placeholder' not in implemented
    unknown = _tab_link('Unimplemented', '/unimplemented', '')
    assert '<span class="badge">Placeholder</span>' in unknown


def inventory(root):
    return {str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns,
            path.stat().st_ctime_ns, sha256(path.read_bytes()).hexdigest())
            for path in root.rglob('*') if path.is_file()}


def master_fixture(root):
    store = ProviderInstrumentSnapshotStore(root)
    records = tuple(_source(10000 + index * 2 + month,
        f'{family.value}26{label}FUT', exchange='MCX', segment='MCX-FUT',
        name=family.value, instrument_type='FUT', expiry=date(2026, month, 20),
        lot=1, tick='1') for index, family in enumerate(McxFamily)
        for month, label in ((11, 'NOV'), (12, 'DEC')))
    snapshot = _snapshot(records)
    store.retain(snapshot)
    path = store.path_for(provider='KITE', dataset_identity='KITE-INSTRUMENT-MASTER',
                          snapshot_identity=snapshot.snapshot_identity)
    return store, snapshot.snapshot_identity, sha256(path.read_bytes()).hexdigest()


def compose(tmp_path, publication=None, native=None):
    app = SwingOpportunitiesApplication(_Provider, run_publication=publication,
        mtf_fact_evidence_store=(publication.mtf_store if publication else
                                MtfFactEvidenceStore(tmp_path / 'mtf')))
    native = native or NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / 'review'))
    master, identity, digest = master_fixture(tmp_path / 'master')
    events = []
    original = app.register_sponsor_operability_restorer

    def register(callback):
        server = callback.__self__
        assert server.mcx_v1_control is server.mcx_v1_composition.control
        assert server.mcx_v1_control._maintenance_admission is server.maintenance_admission
        assert server.mcx_v1_control.native_review is native
        assert native._active_lifecycle_monitoring._monitoring_hub is server.swing_monitoring_hub
        events.append('installed-before-restoration')
        original(callback)

    app.register_sponsor_operability_restorer = register

    def factory(server):
        result = install_canonical_mcx_v1(server, master=master, calendar=MarketCalendarPublisher())
        result.clock = lambda: NOW
        return result

    server = create_browser_server(app, port=0, native_review=native,
        v1_review=SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path / 'charts')),
        mcx_v1_composition_factory=factory)
    assert events == ['installed-before-restoration']
    return server, identity, digest


def test_canonical_factory_installs_before_restore_and_get_is_observational(tmp_path):
    server, _, _ = compose(tmp_path)
    try:
        composition = server.mcx_v1_composition
        assert composition.control.workflow is None
        assert composition.control.worker_status()['pending'] == 0
        before = inventory(tmp_path)
        for _ in range(3):
            projection = composition.projection()
            body = render_mcx_v1_workspace(projection, composition.retained_snapshots())
            assert 'No broker orders' in body
            assert 'MCX_V1_PUBLICATION_OWNER_UNAVAILABLE' in body
            assert '/swing/mcx-v1/reserve' not in body
        assert inventory(tmp_path) == before
        assert server.maintenance_admission.snapshot()['owners'] == {}
        with pytest.raises(ValueError, match='PUBLICATION_OWNER_UNAVAILABLE'):
            composition.reserve('absent', 'a' * 64, 'b' * 64)
        assert inventory(tmp_path) == before
    finally:
        server.server_close()
    assert composition.control.worker_status()['state'] == 'CLOSED'


def test_explicit_reservation_choices_restart_and_stale_replay(tmp_path, scenario, monkeypatch):
    publication, *_ = make_checkpoint(tmp_path / 'checkpoint', *scenario)
    server, snapshot, digest = compose(tmp_path / 'browser', publication)
    try:
        composition = server.mcx_v1_composition
        before = inventory(tmp_path)
        stale = composition.publication_hash()
        with pytest.raises(ValueError, match='MASTER_CHANGED'):
            composition.reserve(snapshot, 'f' * 64, stale)
        assert inventory(tmp_path) == before
        status = server.application.analysis_work_status
        server.application.analysis_work_status = lambda: dict(state='QUEUED', owned_work_count=1)
        with pytest.raises(ValueError, match='ANALYSIS_OWNER_BUSY'):
            composition.reserve(snapshot, digest, stale)
        assert inventory(tmp_path) == before
        server.application.analysis_work_status = status
        workflow = composition.reserve(snapshot, digest, stale)
        assert workflow.reservation_token.run_id == workflow.run_identity
        assert publication.status()['latest_attempt']['state'] == 'RUNNING'
        for family in McxFamily:
            offer = workflow.offer(family)
            assert offer.near.instrument.expiry == date(2026, 11, 20)
            assert offer.next_eligible.instrument.expiry == date(2026, 12, 20)
            workflow.choose(family, McxSelectionRole.NEXT_ELIGIBLE,
                offer.offer_sha256, recorded_at=NOW)
        handoff = workflow.process_handoff()
        before = inventory(tmp_path)
        with pytest.raises(ValueError, match='PUBLICATION_CHANGED'):
            composition.reserve(snapshot, digest, stale)
        assert inventory(tmp_path) == before
        composition.restore_current()
        assert server.mcx_slice3.process_handoff() == handoff
        assert server.mcx_slice3.reservation_token == workflow.reservation_token
        assert inventory(tmp_path) == before
        monkeypatch.setattr('kronos.application.swing_mcx_v1_composition.select_owner_current_mcx_handoff',
            lambda *_args, **_kwargs: pytest.fail('reserved run attempted to reuse predecessor Review'))
        before = inventory(tmp_path)
        projection = composition.projection()
        assert projection['reserved'] and not projection['preparations'] and not projection['plans']
        assert inventory(tmp_path) == before
        assert composition.control._maintenance_admission is server.maintenance_admission
    finally:
        server.server_close()


@pytest.mark.parametrize('active', [False, True])
def test_historical_contract_restores_without_run_or_reservation(tmp_path, active):
    position, instrument, _, bound, root, binding_root = _fixture(
        tmp_path / 'historical', v1=True, active_v1=active)
    service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root))
    historical = LocalMcxHistoricalContractStore(binding_root)
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / 'review'),
        active_lifecycle_service=service, mcx_historical_contract_store=historical)
    server, _, _ = compose(tmp_path / 'browser', native=native)
    try:
        composition = server.mcx_v1_composition
        before = inventory(tmp_path)
        projection = composition.projection()
        body = render_mcx_v1_workspace(projection, composition.retained_snapshots())
        assert instrument.trading_symbol in body
        assert ('/swing/mcx-v1/paper-exit' in body) is active
        assert projection['positions'][0][1].instrument == instrument
        assert inventory(tmp_path) == before
        if not active:
            # No current entry authority: a tick cannot activate a historical
            # armed position or reserve/acquire a substitute current run.
            assert composition.control.on_paper_tick(position.position_id,
                _tick(instrument, 1, '110'),
                __import__('kronos.provider.contracts.monitoring', fromlist=['MonitoringConnectionState']).MonitoringConnectionState.CONNECTED) is None
            assert inventory(tmp_path) == before
        else:
            # Use actual shared/Kite fixture wiring against the retained future.
            clock = [START]
            monitor, capability, hub = _wire_monitor(service, historical, instrument, clock)
            try:
                monitor.attach(position.position_id, capability, instrument)
                capability.tick(110)
                assert service._require(position.position_id).actual_entry == position.actual_entry
                assert service._require(position.position_id).mcx_activation_outcome_sha256 == position.mcx_activation_outcome_sha256
            finally:
                monitor.close()
    finally:
        server.server_close()


@pytest.mark.parametrize('path,fields', [
    ('/swing/mcx-v1/reserve', [('snapshot', 's'), ('master_sha256', 'a' * 64), ('publication_sha256', 'b' * 64)]),
    ('/swing/mcx-v1/plan', [('run', 'r'), ('family', 'GOLDM'), ('handoff_sha256', 'c' * 64)]),
])
def test_composition_forms_reject_extra_and_duplicate_before_side_effect(path, fields):
    for malformed in (fields + [('unexpected', 'x')], fields + [fields[0]]):
        body = urlencode(malformed).encode()
        calls = []
        handler = object.__new__(_BrowserHandler)
        handler.server = SimpleNamespace(mcx_v1_composition=SimpleNamespace(
            reserve=lambda *_: calls.append('reserve'), prepare_plan=lambda *_: calls.append('plan')))
        handler.path = path
        handler.headers = dict({'Content-Type': 'application/x-www-form-urlencoded',
                                'Content-Length': str(len(body))})
        handler.rfile = BytesIO(body)
        response = []
        handler._text = lambda status, message: response.append(status)
        handler._redirect = lambda *_: calls.append('redirect')
        handler._mcx_v1_composition_action(path)
        assert response == [HTTPStatus.CONFLICT] and calls == []


def test_expired_capability_does_not_equal_cached_connected_or_stream_health(tmp_path):
    from kronos.application.swing_opportunities import ProviderConnectionState
    server, _, _ = compose(tmp_path)
    try:
        app = server.application
        app._SwingOpportunitiesApplication__snapshot = replace(app.snapshot(),
            provider_state=ProviderConnectionState.CONNECTED)
        app.authenticated_read_only_capability = lambda: SimpleNamespace(active=False)
        before = inventory(tmp_path)
        server.restore_sponsor_operability()
        assert server.monitoring_restoration_state == 'DEFERRED_PROVIDER_DISCONNECTED'
        assert not server.mcx_v1_composition.projection()['capability_active']
        assert server.native_review.active_monitoring_count == 0
        with pytest.raises(ValueError, match='CAPABILITY_UNAVAILABLE'):
            server.mcx_v1_control._active_capability()
        assert inventory(tmp_path) == before
    finally:
        server.server_close()


def test_maintenance_fence_rejects_recovery_before_writes_and_closes_owner(tmp_path):
    server, _, _ = compose(tmp_path)
    try:
        assert server.maintenance_admission.claim('c' * 64)
        before = inventory(tmp_path)
        with pytest.raises(ValueError, match='RECOVERY_FENCED'):
            server.mcx_v1_composition.recover_historical_exits()
        assert server.maintenance_admission.snapshot()['owners'] == {}
        assert inventory(tmp_path) == before
    finally:
        server.server_close()
    assert server.mcx_v1_control.worker_status()['state'] == 'CLOSED'


@pytest.mark.parametrize('native_intake', ['GOLDM-LINEAGE'], indirect=True)
def test_explicit_plan_composition_current_review_bound_and_replay_write_free(
        tmp_path, scenario, native_intake, monkeypatch):
    """Real owners; synthetic 5/5 and geometry are isolated fixture inputs.

    Canonical installation is proved separately above; this test exercises its
    plan operation against the existing receipt fixture. It cannot commission
    production or claim that the retained live run has this geometry.
    """
    from dataclasses import asdict
    from kronos.application import swing_mcx_v1_composition as module
    from kronos.application.swing_mcx_evidence import listed_v1_mcx_offers
    from tests.unit.browser.test_browser_mcx_integrated import _workflow, PLAN_NOW
    from tests.unit.swing.v1.test_mcx_step31_prepared_handoff import _current
    from tests.unit.swing.v1.test_kr370_step31_handoff import _evidence
    from kronos.swing.v1.mcx_step31_construction import select_owner_current_mcx_handoff
    from kronos.swing.v1.mcx_step31_prepared_handoff import _digest
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator

    workflow, facts = _workflow(tmp_path, scenario, native_intake)
    rows = tuple(_source(1000 + index * 2 + offset,
        fact.instrument.trading_symbol, exchange='MCX', segment='MCX-FUT',
        name=family.value, instrument_type='FUT', expiry=fact.instrument.expiry,
        lot=fact.instrument.lot_size, tick=str(fact.instrument.tick_size))
        for index, family in enumerate(McxFamily)
        for offset, fact in enumerate(facts[family]))
    # The retained fixture master is acquired on 22 August, before the
    # 25 August plan, but after the old 20 August selection fixture.
    snapshot = _snapshot(rows)
    choice_time = snapshot.acquired_at
    master = ProviderInstrumentSnapshotStore(tmp_path / 'selected-master')
    master.retain(snapshot)
    workflow.offers = listed_v1_mcx_offers(master,
        snapshot_identity=snapshot.snapshot_identity,
        run_identity=workflow.run_identity, observed_at=choice_time)
    for family in McxFamily:
        workflow.choose(family, McxSelectionRole.NEAR, workflow.offers[family].offer_sha256,
                        recorded_at=choice_time)
    read = _current(native_intake, tmp_path, promotion_at=PLAN_NOW)
    native_intake._v2_store.retain(read.promotion, current=native_intake._v2_current)
    native_intake._v2_promotions[(read.run_identity, 'GOLDM')] = read.promotion
    # Exercise the actual, pure Step-31 fact builder before the deliberately
    # explicit geometry fixture used to isolate plan wiring below.
    actual = module.build_mcx_v1_trade_construction_evidence(
        read.requirement, read.facts, read.promotion)
    four_hour = read.facts.instrument('GOLDM').fact(FactualTimeframe.FOUR_HOUR)
    assert actual.qualification_candle.high == Decimal(str(four_hour.high))
    assert actual.governing_structural_low.price == Decimal(str(read.requirement.thesis.operative_anchor_price))
    mtf = MtfFactEvidenceStore(tmp_path / 'facts')
    mtf.retain(read.facts)
    app = native_intake.application
    app._SwingOpportunitiesApplication__publication = workflow.publication
    app.mtf_fact_evidence_store = lambda: mtf
    app.authenticated_read_only_capability = lambda: SimpleNamespace(active=True)
    server = SimpleNamespace(application=app, native_intake=native_intake,
        native_review=native_intake.native_review,
        maintenance_admission=MaintenanceAdmissionCoordinator())
    composition = SwingMcxV1Composition(server, master=master,
        provider=lambda: pytest.fail('startup/plan attempted Provider acquisition'),
        calendar=MarketCalendarPublisher(), clock=lambda: PLAN_NOW)
    try:
        composition.control.bind_workflow(workflow, native_intake)
        server.mcx_slice3 = workflow
        owner = select_owner_current_mcx_handoff(native_intake, McxFamily.GOLDM,
            facts[McxFamily.GOLDM][0].instrument, prepared_at=PLAN_NOW)
        digest = _digest(asdict(owner.prepared.bound))
        before = inventory(tmp_path)
        with pytest.raises(ValueError, match='HANDOFF_CHANGED'):
            composition.prepare_plan(workflow.run_identity, McxFamily.GOLDM, 'f' * 64)
        assert inventory(tmp_path) == before
        fixture_evidence = _evidence(SimpleNamespace(requirement=read.requirement,
            promotion=SimpleNamespace(analysis_boundary=read.facts.observed_at)))
        monkeypatch.setattr(module, 'build_mcx_v1_trade_construction_evidence',
                            lambda *_: fixture_evidence)
        plan, path = composition.prepare_plan(workflow.run_identity, McxFamily.GOLDM, digest)
        assert (plan.entry, plan.stop, plan.canonical_target) == (100, 90, 120)
        assert plan.contract_symbol == facts[McxFamily.GOLDM][0].instrument.trading_symbol
        assert plan.quote_quantity_per_lot is plan.maximum_stop_risk is None
        assert plan.receipt_integrity_sha256 == owner.prepared.bound.receipt_integrity_sha256
        assert composition.plans.load(path) == plan
        before = inventory(tmp_path)
        assert composition.prepare_plan(workflow.run_identity, McxFamily.GOLDM, digest) == (plan, path)
        assert inventory(tmp_path) == before
        # A changed geometry read must reject before any new plan retention.
        from kronos.swing.v1.review_evidence_store import PreparedReadFence
        marker = tmp_path / 'geometry-read'
        marker.write_bytes(b'revision-2')
        original = dict(entry=plan.entry, stop=plan.stop, target=plan.canonical_target)
        from kronos.swing.v1.mcx_step31_construction import McxOneHourGeometry
        geometry = McxOneHourGeometry(original['entry'], original['stop'], original['target'],
            owner.prepared.bound.completed_one_hour_sha256,
            owner.prepared.bound.completed_one_hour_boundary)
        from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
        schedule = MarketCalendarPublisher().schedule('MCX', PLAN_NOW.date(), observed_at=PLAN_NOW)
        schedule = MarketDaySchedule('MCX', schedule.trading_date, schedule.session_identity,
            schedule.timezone, TradingDayStatus.TRADING,
            tuple(MarketWindow(window.window_open, window.window_close) for window in schedule.windows),
            schedule.calendar_identity, schedule.calendar_version)
        before = inventory(tmp_path)
        with pytest.raises(ValueError, match='REVIEW_BINDING_STALE'):
            workflow.construct_v1_advisory_plan(native_intake, McxFamily.GOLDM,
                facts[McxFamily.GOLDM][0].instrument, geometry, master, schedule,
                composition.plans, opportunity=read.requirement.thesis.opportunity_identity,
                created_at=PLAN_NOW, geometry_fence=PreparedReadFence(((marker, b'revision-1'),)))
        assert inventory(tmp_path) == before
    finally:
        composition.control.close()


def test_canonical_historical_live_exit_recovery_without_current_run(tmp_path):
    from datetime import timedelta
    from decimal import Decimal
    from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
    from kronos.swing.v1.native_active_trade_lifecycle import TradeExitReason
    from kronos.swing.v1.mcx_live_attestation import McxLiveFillAttestation, LocalMcxLiveFillAttestationStore
    from kronos.swing.v1.mcx_broker_fill_evidence import McxBrokerFillCapture, LocalMcxBrokerFillEvidenceStore
    position, instrument, _, _, root, binding_root = _fixture(
        tmp_path / 'historical', choice=SponsorTradeChoice.LIVE, v1=True)
    service = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root))
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / 'review'),
        active_lifecycle_service=service,
        mcx_historical_contract_store=LocalMcxHistoricalContractStore(binding_root))
    evidence_root = native.evidence_root / 'mcx-v1'
    attestations = LocalMcxLiveFillAttestationStore(evidence_root / 'live-attestations')
    broker = LocalMcxBrokerFillEvidenceStore(evidence_root / 'broker-evidence')
    plan = SimpleNamespace(trade_plan_id=position.trade_plan_id, integrity_hash=position.trade_plan_hash,
        native_run_identity='SWING-RUN-0123456789ABCDEF0123456789ABCDEF', family=McxFamily.GOLDM)
    entry_at = position.entry_timestamp
    for is_exit in (False, True):
        payload = b'isolated-sponsor-exit' if is_exit else b'isolated-sponsor-entry'
        attestation = McxLiveFillAttestation.create(plan, contract_symbol=instrument.trading_symbol,
            expiry=instrument.expiry.isoformat(), lots=position.lots, provider_order_quantity=None,
            entry_outcome=None, fill_price=Decimal('110') if is_exit else position.actual_entry,
            fill_at=entry_at + timedelta(minutes=1) if is_exit else entry_at,
            broker_evidence_id='exit-fixture' if is_exit else 'entry-fixture',
            broker_evidence_sha256=sha256(payload).hexdigest(),
            attested_at=entry_at + timedelta(minutes=2), v1_manual=True)
        broker.capture(McxBrokerFillCapture.from_attestation(position.position_id, attestation, payload), payload)
        if is_exit:
            attestations.retain_exit_intent(position.position_id, attestation, TradeExitReason.SPONSOR_MANUAL_EXIT.value)
            attestations.retain_exit(position.position_id, attestation)
        else:
            attestations.retain(attestation)
    server, _, _ = compose(tmp_path / 'browser', native=native)
    try:
        assert server.mcx_slice3 is None
        assert service._require(position.position_id).state is ActiveLifecycleState.CLOSED
        closure, = service.snapshot().closures
        assert closure.actual_exit == Decimal('110')
        assert server.maintenance_admission.snapshot()['owners'] == {}
        before = inventory(tmp_path)
        server.mcx_v1_composition.recover_historical_exits()
        assert len(service.snapshot().closures) == 1
        assert inventory(tmp_path) == before
    finally:
        server.server_close()


def test_incomplete_historical_exit_intent_blocks_canonical_installation(tmp_path):
    from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
    position, _, _, _, root, binding_root = _fixture(
        tmp_path / 'historical', choice=SponsorTradeChoice.LIVE, v1=True)
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / 'review'),
        active_lifecycle_service=ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(root)),
        mcx_historical_contract_store=LocalMcxHistoricalContractStore(binding_root))
    directory = native.evidence_root / 'mcx-v1' / 'live-attestations'
    directory.mkdir(parents=True)
    (directory / (position.position_id + '.exit-intent.json')).write_bytes(b'{}')
    before = inventory(tmp_path)
    with pytest.raises((ValueError, KeyError)):
        compose(tmp_path / 'browser', native=native)
    assert native._active_lifecycle._require(position.position_id).state is not ActiveLifecycleState.CLOSED
    assert {path: value for path, value in inventory(tmp_path).items() if not path.startswith('browser/')} == before


def test_installed_worker_drains_final_write_before_canonical_close(tmp_path):
    from threading import Event
    server, _, _ = compose(tmp_path)
    started, release, written = Event(), Event(), Event()
    admission = server.maintenance_admission
    ticket = admission.admit('MONITORING_CALLBACK')
    output = tmp_path / 'isolated-final-write'

    def work():
        started.set()
        assert release.wait(5)
        output.write_bytes(b'completed-before-release')
        written.set()

    try:
        assert server.mcx_v1_control._advisory_worker.submit('fixture-position', 'hour-1', work, ticket)
        assert started.wait(5)
        generation = 'd' * 64
        assert admission.claim(generation)
        assert admission.snapshot()['owners'] == {'MONITORING_CALLBACK': 1}
        assert admission.admit('MONITORING_CALLBACK') is None
        admission.draining(generation)
        release.set()
        assert admission.wait_for_zero(generation, 5)
        assert written.is_set() and output.read_bytes() == b'completed-before-release'
    finally:
        release.set()
        server.server_close()
    assert server.mcx_v1_control.worker_status()['pending'] == 0
    assert server.mcx_v1_control.worker_status()['state'] == 'CLOSED'


def test_published_offer_is_observational_and_requires_new_reservation_for_new_choice(tmp_path):
    from kronos.application.swing_mcx_evidence import listed_v1_mcx_offers
    master, snapshot, _ = master_fixture(tmp_path / 'master')
    offers = listed_v1_mcx_offers(master, snapshot_identity=snapshot,
        run_identity='SWING-RUN-0123456789ABCDEF0123456789ABCDEF', observed_at=NOW)
    checks = []
    workflow = SimpleNamespace(offers=offers,
        _current=lambda: checks.append('current'),
        publication=SimpleNamespace(status=lambda: {'latest_attempt': {'state': 'SUCCEEDED'}}),
        offer=lambda *_: pytest.fail('published GET attempted reserved-only selection'),
        process_handoff=lambda: pytest.fail('published GET attempted a new dispatch'))
    handler = object.__new__(_BrowserHandler)
    handler.path = '/swing/mcx-contract-offer?family=GOLDM'
    handler.server = SimpleNamespace(mcx_slice3=workflow, mcx_v1_composition=object())
    output = []
    handler._html = output.append
    handler._text = lambda *_: pytest.fail('published display refused')
    before = inventory(tmp_path)
    handler._mcx_contract_offer()
    assert checks == ['current']
    assert 'GOLDM26NOVFUT' in output[0] and 'GOLDM26DECFUT' in output[0]
    assert '<form' not in output[0]
    assert inventory(tmp_path) == before
    projection = dict(run=offers[McxFamily.GOLDM].run_identity, current=True,
        reserved=False, error=None, publication_sha256='a' * 64,
        capability_active=False, preparations=(), plans=(), positions=())
    body = render_mcx_v1_workspace(projection, ((snapshot, NOW.isoformat(), 'b' * 64),))
    assert '/swing/mcx-v1/reserve' in body
    assert 'retained exact-future selection' in body
