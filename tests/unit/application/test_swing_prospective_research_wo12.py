"""Synthetic publication qualification; production capture/button remain unwired."""
from dataclasses import replace
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import pytest

from kronos.application.swing_prospective_research import SwingProspectiveResearchApplication
from kronos.swing.v1.prospective_research import (
    FollowupCandle, GovernedCalendar, ProspectiveResearchStore, _digest,
    decision, lifecycle_track, origin,
)
from tests.unit.swing.v1.test_prospective_research_wo12 import (
    AT, _milestone, _origin, _sessions,
)


def _app(tmp_path, *, hook=None):
    store = ProspectiveResearchStore((tmp_path / "records").resolve())
    return SwingProspectiveResearchApplication(
        store=store, publication_root=(tmp_path / "Statistics" / "Swing").resolve(),
        clock=lambda: _sessions()[0].closes_at + timedelta(minutes=2), fault_hook=hook,
    )


def _fetch(contract, session):
    return FollowupCandle(contract, session.identity, "SOURCE-" + session.identity,
                          "1", session.closes_at + timedelta(minutes=1),
                          "102", "103", "99", True)


def _bytes(path):
    return Path(path).read_bytes()


def _calendar(market="NSE", *, sessions=None, source="CALENDAR-1",
              complete_through=date(2026, 10, 10)):
    return GovernedCalendar(market, source + "-" + market, "1", AT,
                            date(2026, 9, 29), complete_through,
                            _sessions(market) if sessions is None else sessions)


def test_six_market_origin_denominator_monthly_workbook_and_repeat_click(tmp_path):
    app = _app(tmp_path)
    for market in ("NSE", "GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"):
        o = _origin(market, identity="INSTANCE-" + market,
                    expiry=None if market == "NSE" else date(2026, 10, 20))
        if market == "NSE":
            app.capture_admitted(o, _milestone(o, 4),
                                 decision=decision(o, choice="IGNORE",
                                                   activation_disposition="NOT_APPLICABLE_IGNORE",
                                                   source_identity="DECISION-NSE", decided_at=AT))
        elif market == "GOLDM":
            app.capture_admitted(o, decision=decision(
                o, choice="PAPER", activation_disposition="BLOCKED_RISK_UNAVAILABLE",
                source_identity="DECISION-GOLDM", decided_at=AT))
        else:
            app.capture_admitted(o)  # admitted non-progressors stay in denominator
    assert app.status()["origins"] == 6
    goldm = next(o for o in app.store.origins() if o.data["market"] == "GOLDM")
    app.capture_lifecycle(goldm, lifecycle_track(
        goldm, truth_class="PAPER_OBSERVATION", track_identity="OBSERVATION-1",
        state="NO_ENTRY", source_event_identity="NO-ENTRY-1", source_version="1",
        observed_at=AT))
    sessions = {market: _calendar(market) for market in
                ("NSE", "GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS")}
    as_of = sessions["NSE"].sessions[0].closes_at + timedelta(minutes=2)
    before_status = app.status()
    assert app.status() == before_status
    calls = []
    def fetch(contract, session):
        calls.append((contract, session.identity))
        return _fetch(contract, session)
    result = app.update(operation_identity="CLICK-1", sessions=sessions,
                        fetch_missing=fetch, as_of=as_of)
    assert result.outcome == "PUBLISHED"
    assert len(calls) == 1
    assert result.new_candles == 1
    assert len(result.workbooks) == 1
    workbook = Path(result.workbooks[0])
    assert workbook.name == "KRONOS_Swing_Research_2026_09.xlsx"
    assert workbook.parent.name == "Swing"
    first_bytes = workbook.read_bytes()
    first_mtime = workbook.stat().st_mtime_ns
    with ZipFile(workbook) as archive:
        names = archive.namelist()
        assert len([n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]) == 6
        opportunities = archive.read("xl/worksheets/sheet1.xml").decode()
        tracks = archive.read("xl/worksheets/sheet2.xml").decode()
        assert "INSTANCE-NSE" in opportunities and "INSTANCE-NATURALGAS" in opportunities
        assert "IGNORE" in opportunities and "WITH_PREDICTION" in tracks
        assert "CANDLE_RESEARCH_NOT_LIFECYCLE_MFE_MAE" in tracks
        assert "PAPER_OBSERVATION" in tracks and "NO_ENTRY" in tracks
        assert "CANDLE_DIRECTION_ONLY" in tracks
        assert not any("externalLinks" in n or "vbaProject" in n for n in names)
    repeated = app.update(operation_identity="CLICK-1", sessions=sessions,
                          fetch_missing=fetch, as_of=as_of)
    assert repeated.outcome == "ALREADY_APPLIED"
    assert calls == [("NIFTY-EQ", sessions["NSE"].sessions[0].identity)]
    next_click = app.update(operation_identity="CLICK-2", sessions=sessions,
                            fetch_missing=fetch, as_of=as_of)
    assert next_click.outcome == "ALREADY_UP_TO_DATE"
    assert workbook.read_bytes() == first_bytes and workbook.stat().st_mtime_ns == first_mtime
    assert app.status()["last_successful_publication"] == as_of.isoformat()


def test_cross_month_checkpoint_revision_and_missing_acquisition_preserve_workbook(tmp_path):
    app = _app(tmp_path)
    o = _origin()
    app.capture_admitted(o, _milestone(o, 4))
    sessions = {"NSE": _calendar()}
    day_one = sessions["NSE"].sessions[0].closes_at + timedelta(minutes=2)
    result = app.update(operation_identity="DAY-1", sessions=sessions,
                        fetch_missing=_fetch, as_of=day_one)
    original = _bytes(result.workbooks[0])
    assert result.pending == 3
    day_three = sessions["NSE"].sessions[2].closes_at + timedelta(minutes=2)
    disconnected = app.update(operation_identity="DISCONNECTED", sessions=sessions,
                              fetch_missing=None, as_of=day_three)
    assert disconnected.outcome == "ACQUISITION_UNAVAILABLE"
    assert disconnected.remaining_candle_requests == 2
    assert _bytes(result.workbooks[0]) == original
    def missing(contract, session):
        return None
    unavailable = app.update(operation_identity="MISSING", sessions=sessions,
                             fetch_missing=missing, as_of=day_three)
    assert unavailable.outcome == "ACQUISITION_UNAVAILABLE"
    assert unavailable.remaining_candle_requests == 2
    assert _bytes(result.workbooks[0]) == original
    completed = app.update(operation_identity="DAY-3", sessions=sessions,
                           fetch_missing=_fetch, as_of=day_three)
    assert completed.outcome == "PUBLISHED"
    assert completed.updated_checkpoints > 0
    assert _bytes(result.workbooks[0]) != original
    assert Path(result.workbooks[0]).name.endswith("2026_09.xlsx")
    assert len(app.store.records("CHECKPOINT")) > 4  # append-only revisions retained


def test_publication_failure_rolls_back_and_crash_recovers_without_intraday_write(tmp_path):
    app = _app(tmp_path)
    o = _origin()
    app.capture_admitted(o)
    sessions = {"NSE": _calendar()}
    first = app.update(operation_identity="BASE", sessions=sessions,
                       fetch_missing=None, as_of=AT)
    path = Path(first.workbooks[0])
    baseline = path.read_bytes()
    baseline_hash = sha256(baseline).hexdigest()
    app.capture_admitted(o, _milestone(o, 4))
    def failure(point):
        if point == "after_replace":
            raise OSError("injected publication failure")
    app.fault_hook = failure
    with pytest.raises(OSError, match="injected"):
        app.update(operation_identity="FAIL", sessions=sessions,
                   fetch_missing=_fetch,
                   as_of=sessions["NSE"].sessions[0].closes_at + timedelta(minutes=2))
    assert path.read_bytes() == baseline
    assert sha256(path.read_bytes()).hexdigest() == baseline_hash
    assert app.store.pointer("RECEIPT", "2026_09").data["workbook_sha256"] == baseline_hash
    assert not (tmp_path / "Statistics" / "Intraday").exists()

    # Simulate process death after replacement: BaseException bypasses rollback.
    app.fault_hook = lambda point: (_ for _ in ()).throw(SystemExit("crash")) if point == "after_replace" else None
    with pytest.raises(SystemExit):
        app.update(operation_identity="CRASH", sessions=sessions,
                   fetch_missing=_fetch,
                   as_of=sessions["NSE"].sessions[0].closes_at + timedelta(minutes=2))
    assert path.read_bytes() != baseline
    restarted = _app(tmp_path)
    recovery = restarted.update(operation_identity="RESTART", sessions=sessions,
                                fetch_missing=_fetch,
                                as_of=sessions["NSE"].sessions[0].closes_at + timedelta(minutes=2))
    assert recovery.outcome == "PUBLISHED"
    assert restarted.store.pointer("RECEIPT", "2026_09").data["workbook_sha256"] == sha256(path.read_bytes()).hexdigest()
    assert not (tmp_path / "Statistics" / "Intraday").exists()


def test_sixty_request_catchup_retains_progress_and_resumes_after_restart(tmp_path):
    app = _app(tmp_path)
    app.capture_admitted(_origin(identity="EARLIER-NONPROGRESSOR"))
    prior = app.update(operation_identity="EARLIER-PUBLICATION", sessions={},
                       fetch_missing=None, as_of=AT)
    prior_workbook = Path(prior.workbooks[0])
    prior_bytes = prior_workbook.read_bytes()
    for index in range(61):
        item = origin(continuity_identity=f"CATCHUP-{index}", market="NSE",
                      instrument="NIFTY", contract_identity=f"NIFTY-FUT-{index}",
                      expiry=date(2026, 10, 20), direction="LONG", admitted_at=AT,
                      source_identity=f"CONTINUITY-{index}", source_version="1",
                      source_sha256="a" * 64, origin_run_identity="RUN-1",
                      origin_assessment_sha256="c" * 64,
                      native_setup_identity="ESTABLISHED_TREND_STRUCTURAL_HOLD")
        app.capture_admitted(item, _milestone(item, 4))
    sessions = {"NSE": _calendar()}
    as_of = sessions["NSE"].sessions[0].closes_at + timedelta(minutes=2)
    calls = []
    def fetch(contract, session):
        calls.append((contract, session.identity))
        return _fetch(contract, session)
    partial = app.update(operation_identity="CATCHUP-CLICK", sessions=sessions,
                         fetch_missing=fetch, as_of=as_of)
    assert partial.outcome == "CATCHUP_INCOMPLETE"
    assert partial.new_candles == 60 and partial.remaining_candle_requests == 1
    assert len(calls) == 60
    assert len(app.store.records("CANDLE")) == 60
    assert not app.store.records("CHECKPOINT")
    assert prior_workbook.read_bytes() == prior_bytes
    assert app.store.pointer("RECEIPT", "2026_09").data["workbook_sha256"] == sha256(prior_bytes).hexdigest()

    restarted = _app(tmp_path)
    resumed = restarted.update(operation_identity="CATCHUP-CLICK", sessions=sessions,
                               fetch_missing=fetch, as_of=as_of)
    assert resumed.outcome == "PUBLISHED"
    assert resumed.new_candles == 1 and resumed.remaining_candle_requests == 0
    assert len(calls) == 61 and len(set(calls)) == 61
    assert len(restarted.store.records("CANDLE")) == 61
    assert len(resumed.workbooks) == 1
    workbook = Path(resumed.workbooks[0])
    baseline = workbook.read_bytes()
    duplicate = restarted.update(operation_identity="CATCHUP-CLICK", sessions=sessions,
                                 fetch_missing=fetch, as_of=as_of)
    assert duplicate.outcome == "ALREADY_APPLIED"
    next_click = restarted.update(operation_identity="ANOTHER-CLICK", sessions=sessions,
                                  fetch_missing=fetch, as_of=as_of)
    assert next_click.outcome == "ALREADY_UP_TO_DATE"
    assert len(calls) == 61 and workbook.read_bytes() == baseline


def test_calendar_loss_truncation_and_recovery_preserve_verified_checkpoint(tmp_path):
    app = _app(tmp_path)
    item = _origin()
    milestone = _milestone(item)
    app.capture_admitted(item, milestone)
    sessions = {"NSE": _calendar()}
    as_of = sessions["NSE"].sessions[2].closes_at + timedelta(minutes=2)
    first = app.update(operation_identity="CALENDAR-BASE", sessions=sessions,
                       fetch_missing=_fetch, as_of=as_of)
    path = Path(first.workbooks[0])
    workbook = path.read_bytes()
    key = _digest({"milestone": milestone.identity, "horizon": 3})
    checkpoint = app.store.pointer("CHECKPOINT", key)
    assert checkpoint.data["due_session_identity"] == sessions["NSE"].sessions[2].identity
    assert checkpoint.data["status"] == "WITH_PREDICTION"
    count = len(app.store.records("CHECKPOINT"))

    lost = app.update(operation_identity="NO-CALENDAR", sessions={},
                      fetch_missing=_fetch, as_of=as_of)
    assert lost.outcome == "CALENDAR_UNAVAILABLE"
    assert lost.remaining_candle_requests is None
    assert lost.unavailable_sources == ("NSE:CALENDAR_UNAVAILABLE_OR_TRUNCATED",)
    assert lost.last_successful_publication == first.last_successful_publication
    assert path.read_bytes() == workbook
    assert app.store.pointer("CHECKPOINT", key) == checkpoint

    restarted = _app(tmp_path)
    shortened = {"NSE": _calendar(sessions=_sessions(count=2), source="TRUNCATED")}
    truncated = restarted.update(operation_identity="TRUNCATED-CALENDAR",
                                 sessions=shortened, fetch_missing=_fetch, as_of=as_of)
    assert truncated.outcome == "CALENDAR_UNAVAILABLE"
    assert truncated.unavailable_sources == ("NSE:SWING_WO12_CALENDAR_HISTORY_CONFLICT",)
    assert path.read_bytes() == workbook
    assert restarted.store.pointer("CHECKPOINT", key) == checkpoint
    assert len(restarted.store.records("CHECKPOINT")) == count

    shifted_rows = (replace(sessions["NSE"].sessions[0], identity="SHIFTED-FIRST-SESSION"),
                    *sessions["NSE"].sessions[1:])
    shifted = restarted.update(operation_identity="SHIFTED-CALENDAR",
                               sessions={"NSE": _calendar(sessions=shifted_rows, source="SHIFTED")},
                               fetch_missing=_fetch, as_of=as_of)
    assert shifted.outcome == "CALENDAR_UNAVAILABLE"
    assert shifted.unavailable_sources == ("NSE:SWING_WO12_CALENDAR_HISTORY_CONFLICT",)
    assert restarted.store.pointer("CHECKPOINT", key) == checkpoint

    stale = {"NSE": _calendar(source="STALE", complete_through=date(2026, 10, 2))}
    unavailable = restarted.update(operation_identity="STALE-CALENDAR", sessions=stale,
                                   fetch_missing=_fetch, as_of=as_of)
    assert unavailable.outcome == "CALENDAR_UNAVAILABLE"
    assert path.read_bytes() == workbook

    recovered = restarted.update(operation_identity="CALENDAR-RECOVERED", sessions=sessions,
                                 fetch_missing=_fetch, as_of=as_of)
    assert recovered.outcome == "ALREADY_UP_TO_DATE"
    assert recovered.updated_checkpoints == 0
    assert path.read_bytes() == workbook
    assert restarted.store.pointer("CHECKPOINT", key) == checkpoint


def test_interrupted_acquisition_retains_completed_candles_for_next_explicit_click(tmp_path):
    app = _app(tmp_path)
    for index in range(2):
        item = origin(continuity_identity=f"INTERRUPT-{index}", market="NSE",
                      instrument="NIFTY", contract_identity=f"NIFTY-FUT-INTERRUPT-{index}",
                      expiry=date(2026, 10, 20), direction="LONG", admitted_at=AT,
                      source_identity=f"CONTINUITY-INTERRUPT-{index}", source_version="1",
                      source_sha256="a" * 64, origin_run_identity="RUN-1",
                      origin_assessment_sha256="c" * 64,
                      native_setup_identity="ESTABLISHED_TREND_STRUCTURAL_HOLD")
        app.capture_admitted(item, _milestone(item))
    sessions = {"NSE": _calendar()}
    as_of = sessions["NSE"].sessions[0].closes_at + timedelta(minutes=2)
    attempted = []
    def interrupted(contract, session):
        attempted.append(contract)
        if len(attempted) == 2:
            raise ConnectionError("synthetic disconnect")
        return _fetch(contract, session)
    result = app.update(operation_identity="INTERRUPTED", sessions=sessions,
                        fetch_missing=interrupted, as_of=as_of)
    assert result.outcome == "ACQUISITION_UNAVAILABLE"
    assert result.new_candles == 1 and result.remaining_candle_requests == 1
    assert len(app.store.records("CANDLE")) == 1
    assert not app.store.records("CHECKPOINT")
    resumed_calls = []
    def resumed_fetch(contract, session):
        resumed_calls.append(contract)
        return _fetch(contract, session)
    restarted = _app(tmp_path)
    completed = restarted.update(operation_identity="INTERRUPTED", sessions=sessions,
                                 fetch_missing=resumed_fetch, as_of=as_of)
    assert completed.outcome == "PUBLISHED"
    assert completed.new_candles == 1
    assert len(resumed_calls) == 1 and resumed_calls[0] == attempted[1]
