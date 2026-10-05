"""WO-12 update worker ownership and independent admitted-event inbox."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace

from kronos.application.swing_prospective_research import (
    SwingProspectiveResearchApplication, UpdateResult,
)
from kronos.application.swing_research_control import SwingResearchControl
from kronos.application.swing_research_inbox import SwingResearchInbox
from kronos.application.swing_research_integration import SwingResearchEventCapture
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.provider.contracts.monitoring import ProviderMarketTick
from kronos.swing.v1 import opportunity_continuity as continuity
from kronos.swing.v1.opportunity_continuity import prepare_continuity
from kronos.swing.v1.relative_context import build_relative_context_run
from kronos.swing.universe import SWING_PHASE1_UNIVERSE
from kronos.swing.v1.prospective_research import ProspectiveResearchStore
from tests.unit.swing.v1.test_opportunity_continuity import scenario, later
from tests.unit.application.test_swing_mtf_facts import _instrument
from tests.unit.swing.test_run_publication import make_checkpoint, provenance
from tests.unit.swing.v1.test_native_discovery import _fact, FactualTimeframe as TF


NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def _control(tmp_path: Path, *, inbox=None):
    research = SwingProspectiveResearchApplication(
        store=ProspectiveResearchStore(tmp_path / "research"),
        publication_root=tmp_path / "published")
    capture = SwingResearchEventCapture(research, inbox=inbox)
    return SwingResearchControl(
        application=SimpleNamespace(research_capture_status=lambda: None),
        intake=None, research=research, capture=capture, calendar=None,
        clock=lambda: NOW)


def _result(identity):
    return UpdateResult(identity, "CATCHUP_INCOMPLETE", 60, 0, 0, 0, 0,
                        (), None, 12)


def test_worker_returns_promptly_deduplicates_and_is_counted_through_drain(tmp_path):
    control = _control(tmp_path)
    started, finish = Event(), Event()
    calls = []

    def update(identity, *, progress):
        calls.append(identity)
        progress("ACQUISITION_AND_PUBLICATION")
        started.set()
        assert finish.wait(5)
        return _result(identity)

    control.update = update
    coordinator = MaintenanceAdmissionCoordinator()
    parent = coordinator.admit("BROWSER_POST")
    identity = "a" * 32
    before = monotonic()
    accepted = control.submit_update(identity, parent)
    elapsed = monotonic() - before
    assert elapsed < 1
    assert accepted["state"] == "QUEUED"
    assert started.wait(3)
    assert control.submit_update(identity, parent)["state"] == "RUNNING"
    assert control.submit_update("b" * 32, parent)["state"] == "BUSY"
    assert control.status()["operation"]["phase"] == "ACQUISITION_AND_PUBLICATION"
    parent.release()
    assert coordinator.snapshot()["owners"] == {"SWING_RESEARCH": 1}
    generation = "c" * 64
    assert coordinator.claim(generation)
    coordinator.draining(generation)
    drain_result = []
    waiter = Thread(target=lambda: drain_result.append(
        coordinator.wait_for_zero(generation, 5)))
    waiter.start()
    assert waiter.is_alive()
    finish.set()
    waiter.join(5)
    assert drain_result == [True]
    assert control.status()["operation"]["state"] == "COMPLETED"
    assert control.status()["operation"]["remaining_candle_requests"] == 12
    assert calls == [identity]
    control.close()

    # A new process-local worker sees the retained result, not an old queue.
    restarted = _control(tmp_path)
    new_parent = MaintenanceAdmissionCoordinator().admit("BROWSER_POST")
    assert restarted.submit_update(identity, new_parent)["state"] == "COMPLETED"
    new_parent.release()
    restarted.close()


def test_interrupted_operation_is_resumable_by_same_explicit_identity(tmp_path):
    original = _control(tmp_path)
    identity = "d" * 32
    original._operation_state(identity, "RUNNING", phase="ACQUISITION_AND_PUBLICATION")
    original.close()
    resumed = _control(tmp_path)
    done = Event()
    resumed.update = lambda value, *, progress: (done.set() or _result(value))
    coordinator = MaintenanceAdmissionCoordinator()
    parent = coordinator.admit("BROWSER_POST")
    assert resumed.submit_update(identity, parent)["state"] == "QUEUED"
    parent.release()
    assert done.wait(3)
    resumed.close()
    assert resumed.status()["operation"]["state"] == "COMPLETED"


def test_admitted_capture_inbox_is_independent_of_busy_research_ledger(scenario, tmp_path):
    snapshot, bindings = scenario
    contribution = prepare_continuity(snapshot, bindings)
    inbox = SwingResearchInbox(tmp_path / "inbox")
    control = _control(tmp_path, inbox=inbox)
    held, release = Event(), Event()

    def long_research_io():
        with control.research.store.transaction():
            held.set()
            assert release.wait(5)

    worker = Thread(target=long_research_io)
    worker.start()
    assert held.wait(2)
    before = monotonic()
    control.capture.retain_admission_event(contribution)
    assert monotonic() - before < 2
    receipt = inbox.read("ADMISSION", contribution.native_run.run_identity)
    assert receipt["continuity_sha256"] == contribution.integrity_sha256
    release.set()
    worker.join(5)
    assert not worker.is_alive()
    control.close()


def test_canonical_mcx_publication_recovers_factual_price_after_capture_failure(
        scenario, tmp_path, monkeypatch):
    snapshot, bindings = scenario
    gold = snapshot.instrument("GOLDM")
    failed = _fact(TF.FOUR_HOUR, close=80.0, bucket="FULL_DURATION")
    old_gold = replace(gold, timeframes=tuple(
        failed if fact.timeframe is TF.FOUR_HOUR else fact
        for fact in gold.timeframes))
    old = replace(snapshot, instruments=tuple(
        old_gold if item.canonical_instrument == "GOLDM" else item
        for item in snapshot.instruments))
    publication, _, _, _ = make_checkpoint(tmp_path / "canonical", old, bindings)
    changed = {fact.timeframe: replace(
        fact, observation_boundary=fact.observation_boundary + timedelta(hours=4),
        source_timestamp=fact.source_timestamp + timedelta(hours=4))
        for fact in gold.timeframes if fact.timeframe in {TF.FOUR_HOUR, TF.ONE_HOUR}}
    current = later(snapshot, 2, changes=changed)
    token, prior = publication.admit(current.run_identity, current.observed_at)
    draft = continuity.prepare_continuity(
        current, bindings, adopted_predecessor=prior)
    reference = publication.prepare(
        token, mtf=current, native=draft.native_run,
        relative=build_relative_context_run(current, SWING_PHASE1_UNIVERSE),
        provenance=provenance(current), continuity=draft)
    bundle = publication.publish(token, reference, current.observed_at)
    contribution = bundle.continuity.contribution
    row = next(item for item in contribution.rows
               if item.canonical_instrument == "GOLDM")
    assert row.disposition is continuity.ContinuityDisposition.ADMITTED
    instrument = _instrument("GOLDM", "MCX")
    tick = ProviderMarketTick(
        instrument, Decimal("101"), row.first_admitted, row.first_admitted,
        "KITE_CONNECT_WEBSOCKET", "MOCK-CONNECTION", 1, True, True, True)
    inbox = SwingResearchInbox(tmp_path / "canonical-inbox")
    control = _control(tmp_path, inbox=inbox)
    control.capture.retain_admission_event(contribution, ticks=(tick,))

    def fail_once(_value):
        raise OSError("injected downstream research-store failure")

    monkeypatch.setattr(control.research.store, "retain_origin", fail_once)
    import pytest
    with pytest.raises(OSError, match="downstream"):
        control.capture.replay_retained((bundle,), ())
    control.close()
    restored = _control(tmp_path, inbox=SwingResearchInbox(inbox.root))
    restored.capture.replay_retained((bundle,), ())
    restored.capture.replay_retained((bundle,), ())
    (origin,) = restored.research.store.origins()
    assert origin.data["market"] == "GOLDM"
    assert origin.data["reference_price"] == "101"
    assert origin.data["price_observed_at"] == row.first_admitted.isoformat()
    assert origin.data["price_received_at"] == row.first_admitted.isoformat()
    restored.close()
