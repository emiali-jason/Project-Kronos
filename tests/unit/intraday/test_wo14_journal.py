from dataclasses import dataclass
from pathlib import Path

import pytest

from kronos.application.intraday_journal import IntradayJournalApplication
from kronos.intraday.wo14_journal_contract import POLICY_CHECKSUM, revision
from kronos.intraday.wo14_journal_store import JournalStore


@dataclass(frozen=True)
class Fact:
    identity: str
    data: dict


class Facts:
    def __init__(self, *values):
        self.values = {value.identity: value for value in values}

    def load(self, identity):
        return self.values[identity]

    def records(self, schema):
        return tuple(value for value in self.values.values() if value.data.get("schema") == schema)


class Lifecycle:
    def __init__(self, store, state="LIVE"):
        self.store = store
        self.state = state
        self.owner_count = 1
        self.subscription_count = 1

    def journal_monitoring_state(self, track_identity):
        assert track_identity == "AUTH"
        return self.state


def origin(identity="OPP-IDENTITY", readable="LUPIN-20260913-100000"):
    return Fact("ORIGIN", {"schema": "WO12_OPPORTUNITY_ORIGIN_V1", "opportunity_id": readable,
        "opportunity_identity": identity, "canonical_subject_identity": "NSE-EQ-LUPIN",
        "market_session_identity": "NSE-2026-09-13", "origin_at": "2026-09-13T10:00:00+05:30",
        "market_family": "NSE_EQUITY"})


def plan():
    return Fact("PLAN", {"session_identity": "NSE-2026-09-13", "entry": "100", "stop": "95",
        "target": "110", "model_rr": "2", "wo09": {"readiness_identity": "READINESS",
            "readiness_state": "BUY_NOW"}, "adapter": {"native_selection": {"setup_family": "PULLBACK"}}})


def comparison(opportunity="OPP-IDENTITY"):
    return {"subject": "NSE-EQ-LUPIN", "direction": "LONG", "opportunity_identity": opportunity,
        "plan_identity": "PLAN", "expression_identity": "EXPRESSION", "snapshot_identity": "SNAPSHOT",
        "readiness_identity": "READINESS"}


def build(tmp_path: Path, *, monitoring="LIVE", origin_fact=None):
    origin_fact = origin_fact or origin()
    selection = Fact("SELECTION", {"choice": "NONE", "comparison": comparison(),
        "selected_at": "2026-09-13T10:01:00+05:30", "sponsor_selected_lots": None})
    snapshot = Fact("SNAPSHOT", {"contract": {"trading_date": "2026-09-13"}})
    handoff = Fact("HANDOFF", {"selection": {"comparison": comparison(), "sponsor_selected_lots": 4,
        "comparison_identity": "COMPARISON"}, "plan": plan().data,
        "expression": {"future": {"tradingsymbol": "LUPIN26SEPFUT", "expiry": "2026-09-24"},
            "entry": "101", "stop": "96", "target": "111"}, "snapshot": snapshot.data})
    action = Fact("ACTION", {"action": "DO_NOTHING", "handoff_identity": "HANDOFF",
        "action_at": "2026-09-13T10:02:00+05:30"})
    expression = Fact("EXPRESSION", {"future": {"tradingsymbol": "LUPIN26SEPFUT", "expiry": "2026-09-24"},
        "entry": "101", "stop": "96", "target": "111"})
    authorization = Fact("AUTH", {"action_identity": "ARM-ACTION", "armed_at": "2026-09-13T10:03:00+05:30"})
    arm_action = Fact("ARM-ACTION", {"action": "ACTIVATE_PAPER"})
    metric = Fact("METRIC", {"points": "10", "model_r": "2", "mfe": "12", "mae": "2",
        "gross_model_result": "1000", "complete": True, "gaps": [], "samples": 7,
        "coverage_label": "ELIGIBLE_OBSERVATIONS", "coverage_start": "2026-09-13T10:05:00+05:30",
        "coverage_end": "2026-09-13T10:25:00+05:30"})
    track = Fact("TRACK", {"intake": {"subject": "NSE-EQ-LUPIN", "direction": "LONG",
        "session_identity": "NSE-2026-09-13", "opportunity_identity": "OPP-IDENTITY",
        "plan_identity": "PLAN", "expression_identity": "EXPRESSION", "selected_lots": 4,
        "contract": {"trading_date": "2026-09-13"}},
        "authorization_identity": "AUTH", "track_identity": "AUTH", "truth_class": "PAPER_POSITION",
        "state": "CLOSED", "display_state": "CLOSED", "monitoring": "AVAILABLE",
        "entry": {"price": "101", "at": "2026-09-13T10:05:00+05:30", "trigger_fact": "E1",
            "price_fact": "P1", "identity": "ENTRY"},
        "exit": {"price": "111", "at": "2026-09-13T10:25:00+05:30", "trigger_fact": "E2",
            "price_fact": "P2", "identity": "EXIT"}, "exit_reason": "TARGET", "terminal_status": "TARGET",
        "metrics": "METRIC"})
    futures = Facts(plan(), selection, handoff, expression, snapshot)
    lifecycle_store = Facts(action, authorization, arm_action, metric, track)
    lifecycle = Lifecycle(lifecycle_store, monitoring)
    store = JournalStore(tmp_path / "journal")
    app = IntradayJournalApplication(research=Facts(origin_fact), futures=futures,
        lifecycle=lifecycle, store=store)
    return app, futures, lifecycle, selection, action, track


def test_empty_bind_and_policy_are_inert(tmp_path):
    app, futures, lifecycle, *_ = build(tmp_path)
    assert app.snapshot().records == ()
    app.bind()
    assert futures.journal_listener == app.consume_source
    assert lifecycle.store.journal_listener == app.consume_source
    assert lifecycle.owner_count == lifecycle.subscription_count == 1
    assert len(POLICY_CHECKSUM) == 64


@pytest.mark.parametrize(("kind", "index", "truth", "decision"), [
    ("SELECTION", 0, "NONE", "NONE"), ("ACTION", 1, "DO_NOTHING", "DO_NOTHING"),
    ("TRACK", 2, "PAPER_POSITION", "PAPER_POSITION"),
])
def test_sources_project_exact_identity_without_duplicates(tmp_path, kind, index, truth, decision):
    app, _, _, selection, action, track = build(tmp_path)
    source = (selection, action, track)[index]
    app.consume_source(kind, source.identity)
    first = app.snapshot().records[0]
    app.consume_source(kind, source.identity)
    snapshot = app.snapshot()
    assert len(snapshot.records) == 1
    assert snapshot.records[0].revision_identity == first.revision_identity
    assert first.data["opportunity_id"] == "LUPIN-20260913-100000"
    assert first.data["opportunity_identity"] == "OPP-IDENTITY"
    assert first.data["truth_class"] == truth and first.data["decision"] == decision
    assert first.data["decision_identity"] == ("ARM-ACTION" if kind == "TRACK" else source.identity)


def test_track_retains_compact_authoritative_lifecycle_facts(tmp_path):
    app, _, _, _, _, track = build(tmp_path)
    app.consume_source("TRACK", track.identity)
    data = app.snapshot().records[0].data
    assert data["track_identity"] == "AUTH"
    assert data["model_lots"] == 1 and data["selected_lots_context"] == 4
    assert data["entry"]["price"] == "101" and data["exit"]["price"] == "111"
    assert data["exit_reason"] == "TARGET" and data["metrics"]["model_r"] == "2"
    assert data["future"]["expiry"] == "2026-09-24"
    assert data["future_geometry"] == {"entry": "101", "stop": "96", "target": "111"}
    assert data["trading_date"] == "2026-09-13" and data["readiness_identity"] == "READINESS"
    assert "intake" not in data and "raw_ticks" not in data


@pytest.mark.parametrize("state", ["LIVE", "INTERRUPTED", "IDLE", "UNAVAILABLE"])
def test_monitoring_badge_uses_read_only_exact_owner_state(tmp_path, state):
    app, _, lifecycle, _, _, track = build(tmp_path, monitoring=state)
    mutable = dict(track.data); mutable["state"] = "ACTIVE"; mutable["display_state"] = "ACTIVE"
    mutable["entry"] = None; mutable["exit"] = None; mutable["exit_reason"] = None
    mutable["terminal_status"] = None; mutable["metrics"] = None
    lifecycle.store.values["TRACK"] = Fact("TRACK", mutable)
    app.consume_source("TRACK", "TRACK")
    snapshot = app.snapshot()
    assert dict(snapshot.monitoring)[snapshot.records[0].journal_identity] == state
    assert lifecycle.owner_count == lifecycle.subscription_count == 1


def test_terminal_and_no_entry_are_honest(tmp_path):
    app, _, lifecycle, _, _, track = build(tmp_path)
    mutable = dict(track.data); mutable["entry"] = mutable["exit"] = mutable["metrics"] = None
    mutable["exit_reason"] = None; mutable["terminal_status"] = "EXPIRED_BEFORE_ENTRY"
    lifecycle.store.values["TRACK"] = Fact("TRACK", mutable)
    app.consume_source("TRACK", "TRACK")
    data = app.snapshot().records[0].data
    assert data["entry"] is data["exit"] is data["metrics"] is None
    assert dict(app.snapshot().monitoring).popitem()[1] == "NOT_REQUIRED"


def test_presentation_suppression_is_persistent_and_source_inert(tmp_path):
    app, _, lifecycle, _, _, track = build(tmp_path)
    app.consume_source("TRACK", track.identity)
    item = app.snapshot().records[0]
    app.suppress(journal_identity=item.journal_identity, revision_identity=item.revision_identity,
        action_identity="SPONSOR-DELETE-1")
    assert app.snapshot().records == ()
    assert app.snapshot(include_suppressed=True).records == (item,)
    app.consume_source("TRACK", track.identity)
    restored, *_ = build(tmp_path)
    assert restored.snapshot().records == ()
    assert lifecycle.owner_count == lifecycle.subscription_count == 1


def test_suppression_is_record_specific_and_filters_sort_stably(tmp_path):
    app, futures, _, selection, _, _ = build(tmp_path)
    app.consume_source("SELECTION", selection.identity)
    first = app.snapshot().records[0]
    other_origin = origin("OPP-OTHER", "NTPC-20260913-100100")
    app.research.values[other_origin.identity + "2"] = Fact(other_origin.identity + "2", other_origin.data)
    other_comparison = comparison("OPP-OTHER") | {"subject": "NSE-EQ-NTPC"}
    other = Fact("SELECTION-2", {"choice": "NONE", "comparison": other_comparison,
        "selected_at": "2026-09-13T10:02:00+05:30", "sponsor_selected_lots": None})
    futures.values[other.identity] = other
    app.consume_source("SELECTION", other.identity)
    records = app.snapshot(search="NTPC", truth="NONE", scope="HISTORY").records
    assert [item.data["subject"] for item in records] == ["NSE-EQ-NTPC"]
    app.suppress(journal_identity=first.journal_identity, revision_identity=first.revision_identity,
        action_identity="SPONSOR-DELETE-2")
    assert [item.data["opportunity_identity"] for item in app.snapshot().records] == ["OPP-OTHER"]


@pytest.mark.parametrize("exit_reason", ["STOP_LOSS", "TARGET", "SPONSOR_EXIT"])
def test_only_governed_trading_exits_are_accepted(exit_reason):
    item = revision(opportunity_id="X-1", opportunity_identity="O", subject="X", direction="LONG",
        session_identity="S", decision="PAPER_POSITION", decision_identity="D", decision_at="2026-09-13T10:00:00+05:30",
        truth_class="PAPER_POSITION", track_identity="T", status="CLOSED", terminal=True,
        source_identities=["S"], monitoring="NOT_REQUIRED", model_lots=1, entry={"price": "1"},
        exit={"price": "2"}, exit_reason=exit_reason, terminal_status=exit_reason, metrics=None,
        trade_plan_identity="P", future=None, underlying_geometry=None, future_geometry=None,
        planned_rr=None, selected_lots_context=2, setup_family=None, market_family="NSE")
    assert item.data["exit_reason"] == exit_reason


def test_fourth_exit_reason_is_rejected():
    with pytest.raises(ValueError, match="WO14_JOURNAL_EXIT_REASON_INVALID"):
        revision(opportunity_id="X-1", opportunity_identity="O", subject="X", direction="LONG",
            session_identity="S", decision="PAPER_POSITION", decision_identity="D",
            decision_at="2026-09-13T10:00:00+05:30", truth_class="PAPER_POSITION", track_identity="T",
            status="CLOSED", terminal=True, source_identities=["S"], monitoring="NOT_REQUIRED", model_lots=1,
            entry={"price": "1"}, exit={"price": "2"}, exit_reason="ANALYTICAL_INVALIDATION",
            terminal_status="CLOSED", metrics=None, trade_plan_identity="P", future=None,
            underlying_geometry=None, future_geometry=None, planned_rr=None, selected_lots_context=2,
            setup_family=None, market_family="NSE")
