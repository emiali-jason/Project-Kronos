from dataclasses import replace

from kronos.browser.views import render_trade_journal
from kronos.intraday.wo14_journal_contract import JournalSnapshot, revision
from test_browser_views import _ready


def item():
    return revision(opportunity_id="LUPIN-20260913-100000", opportunity_identity="OPP", subject="NSE-EQ-LUPIN",
        direction="LONG", session_identity="NSE-1", decision="PAPER_OBSERVATION", decision_identity="D",
        decision_at="2026-09-13T10:00:00+05:30", truth_class="PAPER_OBSERVATION", track_identity="T",
        status="ACTIVE", terminal=False, source_identities=["O", "D", "T"], monitoring="IDLE", model_lots=1,
        entry={"price": "100"}, exit=None, exit_reason=None, terminal_status=None, metrics=None,
        trade_plan_identity="P", future={"tradingsymbol": "LUPIN26SEPFUT"},
        underlying_geometry={"entry": "99", "stop": "95", "target": "110"},
        future_geometry={"entry": "100", "stop": "96", "target": "111"}, planned_rr="2.2",
        selected_lots_context=3, setup_family="PULLBACK", market_family="NSE_EQUITY")


def test_intraday_journal_reuses_shared_route_and_renders_sponsor_labels():
    record = item()
    html = render_trade_journal(_ready(), None, operational=(), selected_product="INTRADAY",
        selected_record_id=record.journal_identity,
        intraday=JournalSnapshot((record,), (), ((record.journal_identity, "LIVE"),)))
    for text in ("SWING", "INTRADAY", "LUPIN-20260913-100000", "PAPER OBSERVATION",
                 "MONITORING LIVE", "DELETE", "SUPPRESS PRESENTATION", "SOURCE IDENTITIES"):
        assert text in html
    assert 'action="/journal/intraday/delete"' in html
    assert "SPONSOR EXIT" not in html
    assert "/Users/" not in html and "raw_ticks" not in html


def test_intraday_empty_state_and_complete_filter_vocabulary_render():
    html = render_trade_journal(_ready(), None, operational=(), selected_product="INTRADAY",
        intraday=JournalSnapshot((), ()))
    assert "NO INTRADAY JOURNAL RECORDS" in html
    for value in ("PAPER_POSITION", "PAPER_OBSERVATION", "DO_NOTHING", "INTERRUPTED", "NOT_REQUIRED",
                  "UNAVAILABLE", "CURRENT", "HISTORY"):
        assert 'value="' + value + '"' in html


def test_swing_route_remains_shared_and_brand_is_identical():
    swing = render_trade_journal(_ready(), None, operational=(), selected_product="SWING")
    intraday = render_trade_journal(_ready(), None, operational=(), selected_product="INTRADAY",
        intraday=JournalSnapshot((), ()))
    brand = 'src="/assets/brand/kronos-sidebar-mark.png" alt=""'
    assert brand in swing and brand in intraday
    assert "NO INTRADAY JOURNAL RECORDS" not in swing
