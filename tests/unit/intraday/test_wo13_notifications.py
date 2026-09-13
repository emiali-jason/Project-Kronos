from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kronos.application.intraday_notification_sources import (
    monitoring_indicator, ready, trade_candidate, track_events, unavailable,
)
from kronos.application.intraday_notifications import IntradayNotifications
from kronos.application.notification_centre import (
    SponsorNotificationCentre, SponsorNotificationLifecycleStore,
    SponsorNotificationQuery, SponsorNotificationState,
    project_sponsor_notifications,
)
from kronos.application.notifications import NotificationWorkspaceSnapshot
from kronos.browser.views import NotificationProduct, render_notifications
from kronos.intraday.notification_policy import (
    ACTION_REASONS, POLICY_CHECKSUM, POLICY_IDENTITY, POLICY_VERSION, TITLES,
    semantic_identity, telegram_text, validate,
)
from kronos.intraday.wo10_futures_contract import record as future_record
from kronos.intraday.wo11_lifecycle_contract import record as lifecycle_record
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.wo12_research_contract import opportunity_origin
from tests.unit.browser.test_browser_server import _ready
from tests.unit.intraday.test_wo09_readiness import NOW, evaluated
from tests.unit.intraday.test_probables_v2 import _opening_inputs, _run


ORIGIN_AT = NOW - timedelta(minutes=30)


def origin(subject="NSE-EQ-TEST", session="NSE-2026-09-11"):
    return opportunity_origin(
        canonical_subject_identity=subject, market_family="NSE",
        session_identity=session, origin_at=ORIGIN_AT,
        probable_result_identity="PROBABLE-1", probables_run_identity="RUN-1",
    )


def details(family="READY_FOUR", **overrides):
    base = {
        "opportunity_id": "TEST-20260911-083000",
        "opportunity_identity": "INTRADAY-WO12-OPPORTUNITY-TEST",
        "subject": "NSE-EQ-TEST", "direction": "LONG", "market_family": "NSE",
        "session_identity": "NSE-2026-09-11", "trading_date": "2026-09-11",
        "source_identity": "SOURCE-1", "source_integrity": "INTEGRITY-1",
        "event_identity": "EVENT-1", "event_at": NOW.isoformat(),
        "family": family, "semantic_transition": "FIRST_REACHED",
        "policy_identity": POLICY_IDENTITY, "policy_version": POLICY_VERSION,
        "policy_checksum": POLICY_CHECKSUM,
    }
    base.update(overrides)
    return base


def centre(tmp_path, at=NOW):
    return SponsorNotificationCentre(
        SponsorNotificationLifecycleStore(tmp_path / "notifications"), clock=lambda: at,
    )


@pytest.mark.parametrize("family", tuple(TITLES))
def test_every_commissioned_family_has_deterministic_identity_and_title(family):
    value = details(family)
    if family == "ACTION_REQUIRED":
        value["reason"] = sorted(ACTION_REASONS)[0]
    if family in {"PAPER_ENTRY", "OBSERVATION_ENTRY", "TARGET", "STOP_LOSS", "SPONSOR_EXIT"}:
        value.update(track_identity="TRACK-1", truth_class="PAPER_POSITION", lots=1)
    validate(value)
    assert semantic_identity(value) == semantic_identity(dict(reversed(tuple(value.items()))))
    assert TITLES[family] in telegram_text(value)


@pytest.mark.parametrize("state", ("LIVE", "INTERRUPTED", "IDLE", "NOT_REQUIRED", "UNAVAILABLE"))
def test_exact_external_monitoring_states_are_projected(state):
    value = details("PAPER_ENTRY", owner_identity="OWNER", track_identity="TRACK",
                    truth_class="PAPER_POSITION", lots=1)
    assert monitoring_indicator(value, {"OWNER": state}) == state


@pytest.mark.parametrize(("field", "value", "code"), (
    ("extra", "value", "WO13_COMPACT_FIELDS_INVALID"),
    ("source_identity", "/Users/name/private", "WO13_NONPORTABLE_PAYLOAD"),
    ("source_identity", "file://secret", "WO13_NONPORTABLE_PAYLOAD"),
    ("source_identity", "Bearer token", "WO13_NONPORTABLE_PAYLOAD"),
    ("event_at", "not-a-time", "WO13_EVENT_TIME_UNAVAILABLE"),
    ("direction", "FLAT", "WO13_POLICY_BINDING_INVALID"),
    ("truth_class", "LIVE_POSITION", "WO13_TRUTH_CLASS_INVALID"),
    ("lots", 2, "WO13_ONE_LOT_REQUIRED"),
))
def test_compact_contract_rejects_nonportable_or_unauthorized_values(field, value, code):
    item = details("PAPER_ENTRY", truth_class="PAPER_POSITION", lots=1)
    item[field] = value
    with pytest.raises(ValueError, match=code):
        validate(item)


def test_non_allowlisted_unavailable_reason_cannot_notify():
    value = details("ACTION_REQUIRED", reason="EVERY_TECHNICAL_ERROR")
    with pytest.raises(ValueError, match="WO13_ACTION_NOT_ALLOWLISTED"):
        validate(value)


def test_shared_centre_deduplicates_same_semantic_event(tmp_path):
    service = centre(tmp_path)
    first = service.accept_intraday(details())
    second = service.accept_intraday(details(source_identity="SOURCE-REFRESH-2",
                                               source_integrity="INTEGRITY-2",
                                               event_identity="EVENT-2"))
    assert first.notification_identity == second.notification_identity
    assert len(service.snapshot(product="INTRADAY").records) == 1


def test_four_to_five_is_new_event_and_expires_predecessor(tmp_path):
    service = centre(tmp_path, NOW + timedelta(minutes=2))
    four = service.accept_intraday(details("READY_FOUR"))
    five_details = details("READY_FIVE", semantic_transition="FIRST_REACHED",
                           event_at=(NOW + timedelta(minutes=1)).isoformat())
    five = service.accept_intraday(five_details)
    service.expire_intraday(five_details["opportunity_identity"], {"READY_FOUR"},
                            at=NOW + timedelta(minutes=1))
    assert service.record(four.notification_identity).state is SponsorNotificationState.EXPIRED
    assert service.record(five.notification_identity).state is SponsorNotificationState.LIVE


def test_dismissal_and_restoration_do_not_recreate_notification(tmp_path):
    service = centre(tmp_path, NOW + timedelta(minutes=1))
    item = service.accept_intraday(details())
    service.dismiss(item.notification_identity, item.integrity_sha256,
                    occurred_at=NOW + timedelta(minutes=1))
    restored = centre(tmp_path, NOW + timedelta(minutes=2))
    current = restored.accept_intraday(details(source_identity="ANOTHER-SOURCE"))
    assert current.dismissed is True
    assert restored.snapshot(product="INTRADAY").visible == ()


def test_delete_expired_is_product_scoped_and_presentation_only(tmp_path):
    service = centre(tmp_path, NOW + timedelta(minutes=2))
    item = service.accept_intraday(details())
    service.expire(item.notification_identity, item.integrity_sha256,
                   source_still_valid=False, occurred_at=NOW + timedelta(minutes=1))
    assert service.dismiss_expired(product="SWING", occurred_at=NOW + timedelta(minutes=2)) == 0
    assert service.dismiss_expired(product="INTRADAY", occurred_at=NOW + timedelta(minutes=2)) == 1
    assert service.record(item.notification_identity).dismissed is True


def test_snapshot_and_browser_render_are_read_only(tmp_path):
    service = centre(tmp_path)
    before = tuple((p, p.read_bytes()) for p in (tmp_path / "notifications").rglob("*.json"))
    first = service.snapshot(product="INTRADAY")
    second = service.snapshot(product="INTRADAY")
    projection = project_sponsor_notifications(second, SponsorNotificationQuery())
    html = render_notifications(
        _ready(), NotificationWorkspaceSnapshot(()),
        selected_product=NotificationProduct.INTRADAY,
        operational=projection, intraday_indicators={},
    )
    after = tuple((p, p.read_bytes()) for p in (tmp_path / "notifications").rglob("*.json"))
    assert first.revision == second.revision and before == after
    assert "No Intraday notifications." in html
    assert "/notifications/intraday" in html


@pytest.mark.parametrize("state", ("LIVE", "INTERRUPTED", "IDLE", "NOT_REQUIRED", "UNAVAILABLE"))
def test_browser_card_shows_exact_per_notification_monitoring_state(tmp_path, state):
    service = centre(tmp_path)
    item = service.accept_intraday(details("PAPER_ENTRY", track_identity="TRACK",
        owner_identity="OWNER", truth_class="PAPER_POSITION", lots=1))
    projection = project_sponsor_notifications(service.snapshot(product="INTRADAY"), SponsorNotificationQuery())
    html = render_notifications(_ready(), NotificationWorkspaceSnapshot(()),
        selected_product=NotificationProduct.INTRADAY, operational=projection,
        intraday_indicators={item.notification_identity: state})
    assert "MONITORING · " + state in html
    assert "SEE EACH EVENT" in html


def test_telegram_payload_is_compact_and_explicit_about_model_truth():
    value = details("OBSERVATION_ENTRY", track_identity="TRACK", truth_class="PAPER_OBSERVATION",
                    lots=1, contract="TEST26SEP", entry="101.25")
    message = telegram_text(value)
    assert "KRONOS · INTRADAY" in message
    assert "TEST-20260911-083000" in message
    assert "COUNTERFACTUAL MODEL · NO EXPOSURE" in message
    assert "source_identity" not in message and "{" not in message


def test_ready_adapter_consumes_retained_origin_and_notifies_only_four_or_five():
    five, _ = evaluated()
    four, _ = evaluated(follow="WEAK_OR_STALLING")
    assert ready(origin(), five)["family"] == "READY_FIVE"
    assert ready(origin(), four)["family"] == "READY_FOUR"
    three, _ = evaluated(follow="WEAK_OR_STALLING", space="LIMITED_SPACE")
    assert ready(origin(), three) is None


def test_ready_adapter_refuses_an_origin_from_after_the_event():
    five, _ = evaluated()
    later = opportunity_origin(canonical_subject_identity=five.canonical_subject_identity,
        market_family="NSE", session_identity=five.session_identity,
        origin_at=NOW + timedelta(seconds=1), probable_result_identity="P", probables_run_identity="R")
    with pytest.raises(ValueError, match="WO13_OPPORTUNITY_SOURCE_BINDING_INVALID"):
        ready(later, five)


def trade_records(*, executable=True):
    plan = future_record("WO10_CANONICAL_TRADE_PLAN_V1", state="AVAILABLE" if executable else "UNAVAILABLE",
                         session_identity="NSE-2026-09-11")
    expression = future_record("WO10_FUTURE_EXPRESSION_V1", state="EXECUTABLE" if executable else "UNAVAILABLE",
        future={"trading_symbol":"TEST26SEP", "expiry":"2026-09-24"}, entry="101", stop="99", target="105", model_rr="2")
    advisory = future_record("WO10_RISK_ADVISORY_V1", state="WITHIN_REFERENCE")
    comparison = future_record("WO10_SPONSOR_COMPARISON_V1", subject="NSE-EQ-TEST", direction="LONG",
        readiness_identity="READY", expression_identity=expression.identity, plan_identity=plan.identity,
        advisory_identity=advisory.identity, created_at=NOW, executability="EXECUTABLE" if executable else "UNAVAILABLE")
    return comparison, expression, plan, advisory


def test_trade_candidate_adapter_uses_authoritative_compact_wo10_facts():
    c, e, p, a = trade_records()
    value = trade_candidate(origin(), c, e, p, a)
    assert value["family"] == "TRADE_CANDIDATE"
    assert value["contract"] == "TEST26SEP" and value["entry"] == "101"


def test_unavailable_plan_never_masquerades_as_trade_candidate():
    c, e, p, a = trade_records(executable=False)
    assert trade_candidate(origin(), c, e, p, a) is None


@pytest.mark.parametrize("reason", tuple(sorted(ACTION_REASONS)))
def test_only_allowlisted_wo10_unavailable_states_become_action_required(reason):
    item = future_record("WO10_CONSTRUCTION_UNAVAILABLE_V1", subject="NSE-EQ-TEST", direction="LONG",
                         readiness_identity="READY", reason=reason, created_at=NOW)
    assert unavailable(origin(), item, "NSE-2026-09-11")["family"] == "ACTION_REQUIRED"


def test_non_allowlisted_wo10_unavailable_state_is_silent():
    item = future_record("WO10_CONSTRUCTION_UNAVAILABLE_V1", subject="NSE-EQ-TEST", direction="LONG",
                         readiness_identity="READY", reason="INTERNAL_PARSE_FAILURE", created_at=NOW)
    assert unavailable(origin(), item, "NSE-2026-09-11") is None


def test_terminal_notifications_do_not_claim_live_monitoring():
    value = details("TARGET", track_identity="TRACK", owner_identity="OWNER",
                    truth_class="PAPER_POSITION", lots=1)
    assert monitoring_indicator(value, {"OWNER": "LIVE"}, terminal=True) == "NOT_REQUIRED"


def lifecycle_track(*, truth="PAPER_POSITION", exit_reason=None, monitoring="AVAILABLE"):
    entry = {"identity":"WO11_ENTRY_V1-" + "1" * 64, "at":NOW.isoformat(),
             "price":"101", "pricing_identity":"WO11_WEBSOCKET_LAST_PRICE_MODEL_V1"}
    exit_value = None if exit_reason is None else {
        "identity":"WO11_EXIT_V1-" + "2" * 64, "at":(NOW + timedelta(minutes=5)).isoformat(),
        "price":"105", "pricing_identity":"WO11_WEBSOCKET_LAST_PRICE_MODEL_V1",
        "reason":exit_reason, "close_request":"ACTION-1" if exit_reason == "SPONSOR_EXIT" else None,
    }
    return lifecycle_record("WO11_TRACK_V1", track_identity="TRACK-1", truth_class=truth, lots=1,
        state="ACTIVE" if exit_reason is None else "CLOSED", updated_at=NOW + timedelta(minutes=5),
        armed_at=ORIGIN_AT + timedelta(minutes=1),
        intake={"subject":"NSE-EQ-TEST", "direction":"LONG", "session_identity":"NSE-2026-09-11",
                "future":{"trading_symbol":"TEST26SEP", "expiry":"2026-09-24"},
                "stop":"99", "target":"105"},
        entry=entry, exit=exit_value, exit_reason=exit_reason,
        terminal_status=None if exit_reason is None else "CLOSED",
        monitoring=monitoring, gaps=[], metrics=None)


@pytest.mark.parametrize(("truth", "family"), (
    ("PAPER_POSITION", "PAPER_ENTRY"), ("PAPER_OBSERVATION", "OBSERVATION_ENTRY"),
))
def test_lifecycle_entry_family_preserves_truth_class_and_one_lot(truth, family):
    value, = track_events(origin(), lifecycle_track(truth=truth))
    assert value["family"] == family and value["truth_class"] == truth and value["lots"] == 1


@pytest.mark.parametrize("reason", ("TARGET", "STOP_LOSS", "SPONSOR_EXIT"))
def test_lifecycle_exit_family_consumes_retained_exit_without_recalculating_crossing(reason):
    values = track_events(origin(), lifecycle_track(exit_reason=reason))
    exit_notice = next(item for item in values if item["family"] == reason)
    assert exit_notice["exit"] == "105" and exit_notice["event_at"] == (NOW + timedelta(minutes=5)).isoformat()
    assert exit_notice["action_identity"] == ("ACTION-1" if reason == "SPONSOR_EXIT" else None)


def test_monitoring_interruption_consumes_exact_retained_gap_identity():
    gap = lifecycle_record("WO11_GAP_V1", authorization_identity="AUTH",
        started_at=NOW + timedelta(minutes=2), reason="PROCESS_RESTORATION", previous_fact=None)
    current = lifecycle_track(monitoring="INTERRUPTED")
    current = lifecycle_record("WO11_TRACK_V1", **(current.data | {"gaps":[gap.identity]}))
    values = track_events(origin(), current, gap_record=gap)
    notice = next(item for item in values if item["family"] == "MONITORING_INTERRUPTED")
    assert notice["gap_identity"] == gap.identity
    assert notice["event_at"] == gap.data["started_at"]


def test_provider_state_cannot_fabricate_owner_monitoring_state():
    value = details("PAPER_ENTRY", track_identity="TRACK", owner_identity="OWNER",
                    truth_class="PAPER_POSITION", lots=1)
    assert monitoring_indicator(value, {}) == "UNAVAILABLE"


def test_notification_policy_does_not_commission_three_of_five():
    assert POLICY_CHECKSUM and "READY_THREE" not in TITLES


def test_governed_policy_publication_exactly_matches_implementation():
    root = Path(__file__).resolve().parents[3]
    publication = json.loads((root / "docs/architecture/products/intraday/"
        "KRONOS-INTRADAY-WO13-NOTIFICATIONS-POLICY-V1.json").read_text())
    from kronos.intraday.notification_policy import POLICY
    assert publication == {"checksum": POLICY_CHECKSUM, "policy": POLICY,
                           "status": "SPONSOR_POLICY_FROZEN_ENGINEERING_CANDIDATE"}


class _NotificationSourceStore:
    def __init__(self):
        self.notification_listener = None
    def restore(self):
        return ()


class _ResearchOriginSource:
    def __init__(self):
        self.store = SimpleNamespace(records=lambda _schema: ())
        self.published = []
    def publish_admitted_origins(self, run):
        self.published.append(run.run_identity)


def test_incremental_source_queue_restores_and_marks_exact_reference_done(tmp_path):
    shared = centre(tmp_path)
    research = _ResearchOriginSource()
    wo09, futures, lifecycle, probables = (_NotificationSourceStore() for _ in range(4))
    service = IntradayNotifications(centre=shared, research=research, wo09=wo09,
        futures=futures, lifecycle=lifecycle, background=False)
    service.bind(probables)
    assert probables.opportunity_origin_listener == research.publish_admitted_origins
    assert all(store.notification_listener == service.enqueue
               for store in (probables, wo09, futures, lifecycle))

    service.enqueue("PROBABLES", "RUN-1")
    pending, = service.root.glob("*.pending")
    service.drain()
    assert not pending.exists()
    assert len(tuple(service.root.glob("*.done"))) == 1
    assert shared.snapshot(product="INTRADAY").records == ()


def test_telegram_failure_is_retained_without_replaying_or_invalidating_event(tmp_path):
    class _Telegram:
        attempts = 0
        def status(self):
            return SimpleNamespace(private_chat_configured=True, delivery_enabled=True)
        def send(self, _message):
            self.attempts += 1
            raise RuntimeError("isolated transport failure")

    shared = centre(tmp_path)
    transport = _Telegram()
    service = IntradayNotifications(centre=shared, research=_ResearchOriginSource(),
        wo09=_NotificationSourceStore(), futures=_NotificationSourceStore(),
        lifecycle=_NotificationSourceStore(), telegram=transport, background=False)
    service._emit(details())
    service._emit(details(source_identity="SEMANTIC-REFRESH"))
    item, = shared.snapshot(product="INTRADAY").records
    assert item.telegram_delivery == "FAILED"
    assert item.state is SponsorNotificationState.LIVE
    assert transport.attempts == 1


def test_admitted_probables_persistence_commissions_origin_before_notification(tmp_path):
    *_, mapping = _opening_inputs()
    run = _run(mapping)
    store = ProbablesV2Store(tmp_path / "probables")
    observed = []
    store.opportunity_origin_listener = lambda retained: observed.append(("origin", retained.run_identity))
    store.notification_listener = lambda kind, identity: observed.append((kind, identity))

    store.retain_complete(run=run, mappings=(mapping,))

    assert observed == [("origin", run.run_identity), ("PROBABLES", run.run_identity)]
