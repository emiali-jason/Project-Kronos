"""Isolated prospective Swing research contract tests; no live Provider."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from kronos.swing.v1.prospective_research import (
    FollowupCandle, GovernedSession, ProspectiveResearchStore,
    candle_record, decision, evaluate, lifecycle_track, milestone,
    milestone_from_v2_promotion, origin,
)


IST = ZoneInfo("Asia/Kolkata")
AT = datetime(2026, 9, 29, 10, tzinfo=IST)


def _origin(market="NSE", *, identity="INSTANCE-1", direction="LONG", price="100",
            expiry=None, admitted_at=AT):
    return origin(continuity_identity=identity, market=market,
                  instrument="NIFTY" if market == "NSE" else market,
                  contract_identity=("NIFTY-EQ" if market == "NSE" else f"{market}-FUT-20261020"),
                  expiry=expiry if market != "NSE" else None,
                  direction=direction, admitted_at=admitted_at,
                  source_identity="CONTINUITY-1", source_version="1",
                  source_sha256="a" * 64,
                  origin_run_identity="RUN-1", origin_assessment_sha256="c" * 64,
                  native_setup_identity="ESTABLISHED_TREND_STRUCTURAL_HOLD",
                  reference_price=price,
                  price_observation_identity=None if price is None else "TICK-1",
                  price_observed_at=None if price is None else admitted_at,
                  price_received_at=None if price is None else admitted_at,
                  price_source=None if price is None else "GOVERNED_PRICE")


def _milestone(o, count=4, *, at=AT, price="100", source="PROMOTION-1"):
    return milestone(o, count=count,
                     readiness_state="BUY_READY" if count == 4 else "BUY_NOW",
                     source_identity=source, source_version="2",
                     source_sha256="b" * 64, occurred_at=at,
                     reference_price=price,
                     price_observation_identity=None if price is None else "OBS-PRICE-1",
                     price_observed_at=None if price is None else at,
                     price_received_at=None if price is None else at,
                     price_source=None if price is None else "GOVERNED_PRICE")


def _sessions(market="NSE", count=10):
    return tuple(GovernedSession(f"SESSION-{market}-{index}", market,
                                 date(2026, 10, index),
                                 datetime(2026, 10, index, 9, tzinfo=IST),
                                 datetime(2026, 10, index, 16, tzinfo=IST))
                 for index in range(1, count + 1))


def _candle(o, session, *, close="102", low="99", high="103", action=False,
            covered=True):
    return candle_record(FollowupCandle(
        o.data["exact_contract_identity"], session.identity,
        "CANDLE-" + session.identity, "1", session.closes_at + timedelta(minutes=1),
        close, high, low, covered, action,
    ))


@pytest.mark.parametrize("market", ("NSE", "GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"))
def test_all_six_markets_keep_exact_instance_contract_and_origin_month(market, tmp_path):
    expiry = None if market == "NSE" else date(2026, 10, 20)
    o = _origin(market, identity="INSTANCE-" + market, expiry=expiry)
    store = ProspectiveResearchStore(tmp_path.resolve())
    store.retain_origin(o)
    assert store.retain_origin(o) == o
    assert store.origins() == (o,)
    assert o.data["origin_month"] == "2026_09"
    if market != "NSE":
        assert market in o.data["exact_contract_identity"]
        assert o.data["expiry"] == "2026-10-20"
    with pytest.raises(ValueError, match="IDENTITY_CONFLICT"):
        store.retain_origin(_origin(market, identity="INSTANCE-" + market,
                                    expiry=expiry, direction="SHORT"))


def test_nonprogressor_ignore_and_first_linked_milestones_survive_replay(tmp_path):
    store = ProspectiveResearchStore(tmp_path.resolve())
    o = store.retain_origin(_origin(admitted_at=AT - timedelta(hours=1)))
    assert store.records("MILESTONE") == ()  # denominator retains non-progressor
    ignored = decision(o, choice="IGNORE", activation_disposition="NOT_APPLICABLE_IGNORE",
                       source_identity="DECISION-1", decided_at=AT)
    store.retain_decision(ignored)
    assert store.retain_decision(ignored) == ignored
    m4 = store.retain_milestone(_milestone(o, 4))
    store.retain_milestone(_milestone(o, 4, at=AT + timedelta(minutes=1), source="REFRESH-2"))
    assert store.records("MILESTONE") == (m4,)
    m5 = store.retain_milestone(_milestone(o, 5, at=AT + timedelta(hours=1), source="PROMOTION-5"))
    assert m4.data["origin_identity"] == m5.data["origin_identity"] == o.identity
    assert len(store.records("MILESTONE")) == 2
    with pytest.raises(ValueError, match="EARLIER_MILESTONE"):
        store.retain_milestone(_milestone(o, 4, at=AT - timedelta(minutes=1)))
    with pytest.raises(ValueError, match="DECISION_INVALID"):
        decision(o, choice="NONE", activation_disposition="NOT_APPLICABLE_IGNORE",
                 source_identity="X", decided_at=AT)


def test_completed_session_horizons_direction_zero_and_candle_excursion():
    o = _origin(direction="SHORT")
    m = _milestone(o)
    sessions = _sessions()
    candles = {s.identity: _candle(o, s, close="98", low="96", high="104") for s in sessions}
    first = evaluate(m, o, horizon=1, sessions=sessions, candles=candles,
                     as_of=sessions[0].closes_at + timedelta(minutes=5))
    assert first.data["status"] == "WITH_PREDICTION"
    assert Decimal(first.data["raw_pct"]) == Decimal("-2.00")
    assert Decimal(first.data["direction_adjusted_pct"]) == Decimal("2.00")
    assert Decimal(first.data["candle_excursion_favourable_pct"]) == Decimal("4.00")
    assert first.data["excursion_authority"] == "CANDLE_RESEARCH_NOT_LIFECYCLE_MFE_MAE"
    pending = evaluate(m, o, horizon=3, sessions=sessions, candles=candles,
                       as_of=sessions[0].closes_at + timedelta(minutes=5))
    assert pending.data["status"] == "PENDING"
    assert pending.data["due_session_identity"] == sessions[2].identity
    zero = evaluate(m, o, horizon=1, sessions=sessions,
                    candles={sessions[0].identity: _candle(o, sessions[0], close="100")},
                    as_of=sessions[0].closes_at + timedelta(minutes=5))
    assert zero.data["status"] == "UNCHANGED"


def test_missing_price_coverage_expiry_and_corporate_action_remain_explicit():
    sessions = _sessions()
    o = _origin()
    as_of = sessions[-1].closes_at + timedelta(minutes=2)
    missing_price = evaluate(_milestone(o, price=None), o, horizon=1,
                             sessions=sessions, candles={}, as_of=as_of)
    assert missing_price.data["reason"] == "MILESTONE_REFERENCE_PRICE_MISSING"
    gap = evaluate(_milestone(o), o, horizon=1, sessions=sessions, candles={}, as_of=as_of)
    assert gap.data["reason"] == "COMPLETED_SESSION_CANDLE_MISSING"
    partial = evaluate(_milestone(o), o, horizon=1, sessions=sessions,
                       candles={sessions[0].identity: _candle(o, sessions[0], covered=False)},
                       as_of=as_of)
    assert partial.data["reason"] == "CANDLE_INTERVAL_COVERAGE_INCOMPLETE"
    action = evaluate(_milestone(o), o, horizon=1, sessions=sessions,
                      candles={sessions[0].identity: _candle(o, sessions[0], action=True)},
                      as_of=as_of)
    assert action.data["reason"] == "CORPORATE_ACTION_BASIS_UNAVAILABLE"
    mcx = _origin("CRUDEOIL", expiry=date(2026, 10, 3))
    limited = evaluate(_milestone(mcx), mcx, horizon=5,
                       sessions=_sessions("CRUDEOIL"), candles={}, as_of=as_of)
    assert limited.data["status"] == "EXPIRY_LIMITED"


def test_wrong_contract_cannot_supply_future_checkpoint():
    o = _origin("GOLDM", expiry=date(2026, 10, 20))
    sessions = _sessions("GOLDM")
    wrong = candle_record(FollowupCandle("GOLDM-NEXT-EXPIRY", sessions[0].identity,
                                         "WRONG-EXPIRY", "1",
                                         sessions[0].closes_at + timedelta(minutes=1),
                                         "101", "103", "99", True))
    with pytest.raises(ValueError, match="CANDLE_BINDING_INVALID"):
        evaluate(_milestone(o), o, horizon=1, sessions=sessions,
                 candles={sessions[0].identity: wrong},
                 as_of=sessions[0].closes_at + timedelta(minutes=2))


def test_unverified_equity_price_basis_is_unavailable_without_claiming_an_action():
    o = _origin()
    session = _sessions()[0]
    candle = candle_record(FollowupCandle(
        o.data["exact_contract_identity"], session.identity,
        "CANDLE-UNVERIFIED", "1", session.closes_at + timedelta(minutes=1),
        "102", "103", "99", True, price_basis_verified=False))
    result = evaluate(_milestone(o), o, horizon=1, sessions=(session,),
                      candles={session.identity: candle},
                      as_of=session.closes_at + timedelta(minutes=2))
    assert result.data["status"] == "UNAVAILABLE"
    assert result.data["reason"] == "PRICE_BASIS_UNVERIFIED"
    assert candle.data["corporate_action"] is False


def test_exact_validated_v2_4_of_5_maps_without_inventing_5_of_5():
    from kronos.swing.v1.analytical_promotion_v2 import create_record
    from tests.unit.swing.v1.test_analytical_promotion_v2 import (
        NOW, criteria, nse, source,
    )
    promotion = create_record(source=source(), criteria=criteria(4),
                              confirmation=nse(), created_at=NOW + timedelta(minutes=5))
    factual = promotion.value["source"]
    admitted = datetime.fromisoformat(factual["analysis_boundary"].replace("Z", "+00:00"))
    o = origin(continuity_identity="CONTINUITY-INSTANCE-1", market="NSE",
               instrument=factual["canonical_instrument"],
               contract_identity=factual["canonical_instrument"], expiry=None,
               direction=factual["direction"], admitted_at=admitted,
               source_identity="CONTINUITY-RECORD-1", source_version="1",
               source_sha256="a" * 64, origin_run_identity=factual["native_run_identity"],
               origin_assessment_sha256=factual["native_assessment_sha256"],
               native_setup_identity=factual["native_opportunity_identity"])
    mapped = milestone_from_v2_promotion(o, promotion)
    assert mapped is not None
    assert mapped.data["score"] == 4
    assert mapped.data["readiness_state"] == "BUY_READY"
    assert mapped.data["source_identity"] == promotion.identity
    assert datetime.fromisoformat(mapped.data["analytical_at"]) == admitted
    assert datetime.fromisoformat(mapped.data["occurred_at"]) == NOW + timedelta(minutes=5)
    assert mapped.data["reference_price"] is None
    priced = milestone_from_v2_promotion(
        o, promotion, reference_price="100", price_observation_identity="TICK-2",
        price_observed_at=NOW + timedelta(minutes=2),
        price_received_at=NOW + timedelta(minutes=3),
        price_source="KITE_CONNECT_WEBSOCKET")
    assert priced.data["price_received_at"] != priced.data["analytical_at"]
    with pytest.raises(ValueError, match="MILESTONE_PRICE_BINDING_INVALID"):
        milestone_from_v2_promotion(
            o, promotion, reference_price="100", price_observation_identity="TICK-LATE",
            price_observed_at=NOW + timedelta(minutes=2),
            price_received_at=NOW + timedelta(minutes=6),
            price_source="KITE_CONNECT_WEBSOCKET")
    with pytest.raises(ValueError, match="PROMOTION_SOURCE_MISMATCH"):
        milestone_from_v2_promotion(_origin(), promotion)


def test_lifecycle_truth_classes_do_not_invent_fill_or_pool_observation_money(tmp_path):
    o = _origin()
    store = ProspectiveResearchStore(tmp_path.resolve())
    store.retain_origin(o)
    waiting = lifecycle_track(o, truth_class="PAPER_POSITION", track_identity="POSITION-1",
                              state="PAPER_ARMED", source_event_identity="EVENT-ARMED",
                              source_version="1", observed_at=AT)
    assert waiting.data["entry_price"] is waiting.data["gross_pnl"] is None
    store.retain_lifecycle_track(waiting)
    assert store.retain_lifecycle_track(waiting) == waiting
    with pytest.raises(ValueError, match="LIFECYCLE_TRUTH_INVALID"):
        lifecycle_track(o, truth_class="PAPER_OBSERVATION", track_identity="OBS-1",
                        state="COMPLETE", source_event_identity="EVENT-OBS",
                        source_version="1", observed_at=AT, gross_pnl="100")
    with pytest.raises(ValueError, match="LIFECYCLE_TRUTH_INVALID"):
        lifecycle_track(o, truth_class="LIVE_SPONSOR", track_identity="LIVE-1",
                        state="LIVE_ACTIVE", source_event_identity="EVENT-LIVE",
                        source_version="1", observed_at=AT, entry_price="101")
    with pytest.raises(ValueError, match="LIFECYCLE_TRUTH_INVALID"):
        lifecycle_track(o, truth_class="PAPER_POSITION", track_identity="PAPER-1",
                        state="PAPER_ACTIVE", source_event_identity="EVENT-PAPER",
                        source_version="1", observed_at=AT, gross_pnl="5")
    attested = lifecycle_track(o, truth_class="LIVE_SPONSOR", track_identity="LIVE-1",
                               state="LIVE_ACTIVE", source_event_identity="EVENT-LIVE",
                               source_version="1", observed_at=AT,
                               entry_price="101", sponsor_attested=True)
    store.retain_lifecycle_track(attested)
    assert len(store.records("LIFECYCLE_TRACK")) == 2


def test_explicit_candle_revision_retains_original_and_recomputes_checkpoint(tmp_path):
    o = _origin()
    m = _milestone(o)
    session = _sessions()[0]
    store = ProspectiveResearchStore(tmp_path.resolve())
    old = store.retain_candle(_candle(o, session, close="102"))
    before = evaluate(m, o, horizon=1, sessions=(session,),
                      candles={session.identity: old},
                      as_of=session.closes_at + timedelta(minutes=3))
    revised = candle_record(FollowupCandle(
        o.data["exact_contract_identity"], session.identity,
        "CORRECTED-SOURCE-1", "2", session.closes_at + timedelta(minutes=2),
        "101", "103", "99", True, False,
        supersedes_source_identity=old.data["source_identity"],
        revision_reason="OWNER_CORRECTED_COMPLETED_CANDLE",
    ))
    store.retain_candle(revised)
    assert store.retain_candle(revised) == revised
    assert len(store.records("CANDLE")) == 2
    assert store.current_candles()[(o.data["exact_contract_identity"], session.identity)] == revised
    after = evaluate(m, o, horizon=1, sessions=(session,),
                     candles={session.identity: revised},
                     as_of=session.closes_at + timedelta(minutes=3))
    assert before.data["direction_adjusted_pct"] != after.data["direction_adjusted_pct"]
    with pytest.raises(ValueError, match="CANDLE_REVISION_REQUIRES_OWNER_REVIEW"):
        store.retain_candle(_candle(o, session, close="100"))
