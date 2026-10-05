"""WO-12 admitted owner event and factual time integration; no Provider."""
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from kronos.application.swing_prospective_research import SwingProspectiveResearchApplication
from kronos.application.swing_research_integration import SwingResearchEventCapture, _price_at
from kronos.application.swing_research_integration import _contract_identity
from kronos.application.swing_research_control import SwingResearchControl
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.provider.contracts.monitoring import ProviderMarketTick
from kronos.swing.v1 import opportunity_continuity as continuity
from kronos.swing.v1.prospective_research import (
    GovernedSession, ProspectiveResearchStore, origin,
)
from tests.unit.application.test_swing_mtf_facts import _instrument
from tests.unit.swing.v1.test_opportunity_continuity import scenario


@pytest.mark.parametrize("family", ("NIFTY", "GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"))
def test_factual_tick_requires_exact_contract_and_receipt_before_event(family):
    instrument = _instrument(family, "NSE" if family == "NIFTY" else "MCX")
    binding = asdict(continuity.SourceBinding.from_instrument(family, instrument))
    from datetime import datetime, timezone
    event = datetime(2026, 9, 29, 10, tzinfo=timezone.utc)

    def tick(at, received, *, record=instrument):
        return ProviderMarketTick(record, Decimal("100"), at, received,
                                  "KITE_CONNECT_WEBSOCKET", "CONNECTION-1", 1,
                                  True, True, True)

    earlier = tick(event - timedelta(seconds=2), event - timedelta(seconds=1))
    assert _price_at(binding, event, (earlier,))["reference_price"] == "100"
    assert _price_at(binding, event, (tick(event - timedelta(seconds=2),
                                          event + timedelta(seconds=1)),)) == {}
    assert _price_at(binding, event, (tick(event + timedelta(seconds=1),
                                          event + timedelta(seconds=2)),)) == {}


def test_exact_committed_mcx_origin_is_durable_and_replay_deduplicates(scenario, tmp_path):
    snapshot, bindings = scenario
    contribution = continuity.prepare_continuity(snapshot, bindings)
    research = SwingProspectiveResearchApplication(
        store=ProspectiveResearchStore(tmp_path / "store"),
        publication_root=tmp_path / "published")
    capture = SwingResearchEventCapture(research)
    assert capture.capture_committed(contribution) == 1
    assert capture.capture_committed(contribution) == 0
    (origin,) = research.store.origins()
    row = next(item for item in contribution.rows if item.canonical_instrument == "GOLDM")
    assert origin.data["opportunity_identity"] == row.opportunity_id
    assert origin.data["source_sha256"] == contribution.integrity_sha256
    assert origin.data["contract_binding"]["expiry"] == row.source_binding.expiry
    assert origin.data["reference_price"] is None


def test_research_keeps_sponsor_choice_and_pre_entry_interruption_separate(scenario, tmp_path):
    snapshot, bindings = scenario
    contribution = continuity.prepare_continuity(snapshot, bindings)
    research = SwingProspectiveResearchApplication(
        store=ProspectiveResearchStore(tmp_path / "store"),
        publication_root=tmp_path / "published")
    capture = SwingResearchEventCapture(research)
    capture.capture_committed(contribution)
    when = next(row.first_admitted for row in contribution.rows
                if row.canonical_instrument == "GOLDM") + timedelta(minutes=1)
    enum = lambda value: SimpleNamespace(value=value)
    factual = SimpleNamespace(native_run_identity=contribution.native_run.run_identity,
                              canonical_instrument="GOLDM", decision=enum("PAPER"),
                              decision_id="DECISION-1", decision_timestamp=when)
    position = SimpleNamespace(mode=enum("PAPER"), state=enum("PAPER_ARMED"),
                               position_id="POSITION-1", integrity_hash="a" * 64,
                               contract_version="1", created_at=when,
                               actual_entry=None)
    result = SimpleNamespace(decision=factual, position=position,
                             state=enum("PAPER_ARMED"))
    capture.capture_native_sponsor(contribution, result)
    assert research.store.records("DECISION")[0].data["choice"] == "PAPER"
    armed = research.store.records("LIFECYCLE_TRACK")[0]
    assert armed.data["state"] == "PAPER_ARMED"
    assert armed.data["entry_price"] is None
    interrupted = SimpleNamespace(position_id="POSITION-1", mode=enum("PAPER"),
                                  state=enum("MONITORING_UNAVAILABLE"),
                                  lifecycle_event_ids=("EVENT-INTERRUPTED",),
                                  integrity_hash="b" * 64, policy_version="1",
                                  updated_at=when + timedelta(minutes=1),
                                  actual_entry=None)
    capture.capture_active_position(interrupted)
    capture.capture_active_position(interrupted)
    facts = research.store.records("LIFECYCLE_TRACK")
    assert len(facts) == 2
    assert next(item for item in facts if item.data["state"] == "MONITORING_UNAVAILABLE").data["entry_price"] is None


@pytest.mark.parametrize("family", ("NIFTY", "GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"))
def test_explicit_fetch_uses_exact_provider_contract_and_complete_minute_window(
        family, tmp_path):
    from datetime import datetime, timezone
    instrument = _instrument(family, "NSE" if family == "NIFTY" else "MCX")
    binding = asdict(continuity.SourceBinding.from_instrument(family, instrument))
    market = "NSE" if family == "NIFTY" else family
    start = datetime(2026, 8, 20, 10, tzinfo=timezone.utc)
    end = start + timedelta(minutes=2)
    source = origin(continuity_identity="INSTANCE-" + family, market=market,
                    instrument=family, contract_identity=_contract_identity(binding),
                    contract_binding=binding, expiry=instrument.expiry,
                    direction="LONG", admitted_at=start - timedelta(hours=1),
                    source_identity="CONTINUITY-1", source_version="1",
                    source_sha256="a" * 64, origin_run_identity="RUN-1",
                    origin_assessment_sha256="b" * 64,
                    native_setup_identity="ESTABLISHED_TREND_STRUCTURAL_HOLD")
    research = SwingProspectiveResearchApplication(
        store=ProspectiveResearchStore(tmp_path / "store"),
        publication_root=tmp_path / "published")
    research.capture_admitted(source)
    session = GovernedSession("SESSION-" + family, market,
                              start.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata")).date(),
                              start, end)
    window = SimpleNamespace(window_open=start, window_close=end)
    schedule = SimpleNamespace(windows=(window,))
    calls = []
    factual_clock = [end + timedelta(minutes=1)]

    class Capability:
        active = True

        def instrument_records(self, exchange):
            assert exchange == instrument.exchange
            return (instrument,)

        def historical_candles(self, request):
            calls.append(request)
            factual_clock[0] += timedelta(seconds=7)
            assert request.instrument == instrument
            return (HistoricalCandle(start, 100.0, 102.0, 99.0, 101.0, 1),
                    HistoricalCandle(start + timedelta(minutes=1), 101.0, 103.0,
                                     100.0, 102.0, 1))

    calendar = SimpleNamespace(
        schedule=lambda *args, **kwargs: schedule,
        mcx_contract_session_profile=lambda **kwargs: SimpleNamespace(
            contract_eligible=True, continuous_trading=schedule))
    app = SimpleNamespace(authenticated_read_only_capability=lambda: Capability())
    capture = SwingResearchEventCapture(research)
    control = SwingResearchControl(application=app, intake=None, research=research,
                                   capture=capture, calendar=calendar, clock=lambda: factual_clock[0])
    result = control._fetcher(end + timedelta(minutes=1))(
        source.data["exact_contract_identity"], session)
    assert result is not None and result.coverage_complete
    assert result.retrieved_at == end + timedelta(minutes=1, seconds=7)
    assert result.close == "102.0" and result.high == "103.0"
    assert len(calls) == 1


def test_mcx_multi_window_fetch_uses_one_request_and_excludes_break(tmp_path):
    from datetime import datetime, timezone
    instrument = _instrument("GOLDM", "MCX")
    binding = asdict(continuity.SourceBinding.from_instrument("GOLDM", instrument))
    start = datetime(2026, 8, 20, 10, tzinfo=timezone.utc)
    end = start + timedelta(minutes=4)
    source = origin(continuity_identity="INSTANCE-GOLDM", market="GOLDM",
                    instrument="GOLDM", contract_identity=_contract_identity(binding),
                    contract_binding=binding, expiry=instrument.expiry,
                    direction="LONG", admitted_at=start - timedelta(hours=1),
                    source_identity="CONTINUITY-1", source_version="1",
                    source_sha256="a" * 64, origin_run_identity="RUN-1",
                    origin_assessment_sha256="b" * 64,
                    native_setup_identity="ESTABLISHED_TREND_STRUCTURAL_HOLD")
    research = SwingProspectiveResearchApplication(
        store=ProspectiveResearchStore(tmp_path / "store"),
        publication_root=tmp_path / "published")
    research.capture_admitted(source)
    session = GovernedSession("SESSION-GOLDM", "GOLDM",
                              start.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata")).date(),
                              start, end)
    windows = (SimpleNamespace(window_open=start,
                               window_close=start + timedelta(minutes=1)),
               SimpleNamespace(window_open=start + timedelta(minutes=3),
                               window_close=end))
    schedule = SimpleNamespace(windows=windows)
    calls = []

    class Capability:
        active = True

        def instrument_records(self, exchange):
            return (instrument,)

        def historical_candles(self, request):
            calls.append(request)
            return (HistoricalCandle(start, 100.0, 102.0, 99.0, 101.0, 1),
                    HistoricalCandle(start + timedelta(minutes=3), 101.0, 103.0,
                                     100.0, 102.0, 1))

    calendar = SimpleNamespace(
        schedule=lambda *args, **kwargs: schedule,
        mcx_contract_session_profile=lambda **kwargs: SimpleNamespace(
            contract_eligible=True, continuous_trading=schedule))
    control = SwingResearchControl(
        application=SimpleNamespace(authenticated_read_only_capability=lambda: Capability()),
        intake=None, research=research, capture=SwingResearchEventCapture(research),
        calendar=calendar)
    result = control._fetcher(end + timedelta(minutes=1))(
        source.data["exact_contract_identity"], session)
    assert result is not None and result.coverage_complete
    assert result.close == "102.0"
    assert len(calls) == 1 and calls[0].start == start and calls[0].end == end


def test_release_commissioning_excludes_older_owner_history_and_status_is_read_only(
        scenario, tmp_path):
    snapshot, bindings = scenario
    contribution = continuity.prepare_continuity(snapshot, bindings)
    admitted = next(row.first_admitted for row in contribution.rows
                    if row.canonical_instrument == "GOLDM")
    research = SwingProspectiveResearchApplication(
        store=ProspectiveResearchStore(tmp_path / "store"),
        publication_root=tmp_path / "published")
    from kronos.application.swing_research_inbox import SwingResearchInbox
    capture = SwingResearchEventCapture(research, require_commissioning=True,
        inbox=SwingResearchInbox(tmp_path / "inbox"))
    app = SimpleNamespace(committed_research_replay_history=lambda: (),
                          research_capture_status=lambda: None)
    control = SwingResearchControl(application=app, intake=None, research=research,
                                   capture=capture, calendar=None,
                                   clock=lambda: admitted + timedelta(minutes=1),
                                   release_verifier=SimpleNamespace(verify=lambda release, data, digest: {
                                       "release_identity": release, "source_manifest_sha256": digest}))
    with pytest.raises(ValueError, match="COMMISSIONING_REQUIRED"):
        capture.capture_committed(contribution)
    marker = control.commission(release_identity="RELEASE-1",
                                source_manifest_sha256="a" * 64, manifest_bytes=b"fixture")
    assert control.commission(release_identity="RELEASE-1",
                              source_manifest_sha256="a" * 64, manifest_bytes=b"fixture") == marker
    assert capture.capture_committed(contribution) == 0
    assert research.store.origins() == ()
    # Retained pre-commission V2 history may predate available committed-run
    # ancestry. It is outside the commissioned capture window.
    capture.replay_retained((), (SimpleNamespace(value={
        "created_at": (admitted - timedelta(minutes=1)).isoformat()}),))
    before = {str(path.relative_to(tmp_path)): path.read_bytes()
              for path in tmp_path.rglob("*") if path.is_file()}
    for _ in range(3):
        assert control.status()["commissioned_at"] == marker.data["commissioned_at"]
    after = {str(path.relative_to(tmp_path)): path.read_bytes()
             for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before
